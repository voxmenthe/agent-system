#!/usr/bin/env python3
"""Collect normalized upcoming macro and earnings candidates from stable feeds.

The output is deliberately a candidate set, not a completeness claim. The script
uses only the Python standard library and writes JSON to stdout.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BLS_SCHEDULE_URL = "https://www.bls.gov/schedule/"
BEA_ICS_URL = "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics"
BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
FINNHUB_EARNINGS_ENDPOINT = "https://finnhub.io/api/v1/calendar/earnings"
FINNHUB_EARNINGS_DOCS_URL = "https://finnhub.io/docs/api/earnings-calendar"
ALPHA_VANTAGE_ENDPOINT = "https://www.alphavantage.co/query"
ALPHA_VANTAGE_DOCS_URL = "https://www.alphavantage.co/documentation/"
FRED_RELEASES_DATES_ENDPOINT = "https://api.stlouisfed.org/fred/releases/dates"
FRED_RELEASES_DATES_DOCS_URL = (
    "https://fred.stlouisfed.org/docs/api/fred/releases_dates.html"
)
HTTP_TIMEOUT_SECONDS = 20
FRED_TIMEOUT_SECONDS = 45
FINNHUB_PARTITION_DAYS = 5
FINNHUB_POSSIBLE_CAP = 1500
FRED_PAGE_SIZE = 1000
USER_AGENT = "UpcomingCalendarCollector/1.0 (local research client)"
# Foreign issuers with U.S. read-through: zone, reporting months and IR calendar (references/sources.md).
FOREIGN_ISSUERS = Path(__file__).resolve().parents[1] / "references" / "foreign-issuers.tsv"


class ProviderFailure(RuntimeError):
    """A provider failed without exposing a credential-bearing request URL."""


@dataclass(frozen=True)
class ProviderRequest:
    """A validated GET request whose secrets stay out of repr and diagnostics."""

    provider: str
    endpoint: str
    query: tuple[tuple[str, str], ...] = field(default_factory=tuple, repr=False)
    headers: tuple[tuple[str, str], ...] = field(default_factory=tuple, repr=False)
    accept: str = "application/octet-stream"
    timeout_seconds: int = HTTP_TIMEOUT_SECONDS


@dataclass(frozen=True)
class _ProviderPolicy:
    endpoint: str
    allowed_query: frozenset[str]
    required_query: frozenset[str]
    fixed_query: tuple[tuple[str, str], ...]
    allowed_headers: frozenset[str]
    required_headers: frozenset[str]
    accept: str


_PROVIDER_POLICIES = {
    "bea": _ProviderPolicy(
        endpoint=BEA_ICS_URL,
        allowed_query=frozenset(),
        required_query=frozenset(),
        fixed_query=(),
        allowed_headers=frozenset(),
        required_headers=frozenset(),
        accept="text/calendar",
    ),
    "finnhub": _ProviderPolicy(
        endpoint=FINNHUB_EARNINGS_ENDPOINT,
        allowed_query=frozenset({"from", "to", "symbol", "international"}),
        required_query=frozenset({"from", "to", "international"}),
        fixed_query=(("international", "false"),),
        allowed_headers=frozenset({"x-finnhub-token"}),
        required_headers=frozenset({"x-finnhub-token"}),
        accept="application/json",
    ),
    "alpha-vantage": _ProviderPolicy(
        endpoint=ALPHA_VANTAGE_ENDPOINT,
        allowed_query=frozenset({"function", "horizon", "symbol", "apikey"}),
        required_query=frozenset({"function", "horizon", "apikey"}),
        fixed_query=(("function", "EARNINGS_CALENDAR"), ("horizon", "3month")),
        allowed_headers=frozenset(),
        required_headers=frozenset(),
        accept="*/*",
    ),
    "fred": _ProviderPolicy(
        endpoint=FRED_RELEASES_DATES_ENDPOINT,
        allowed_query=frozenset(
            {
                "api_key",
                "file_type",
                "include_release_dates_with_no_data",
                "realtime_start",
                "realtime_end",
                "limit",
                "offset",
                "order_by",
                "sort_order",
            }
        ),
        required_query=frozenset(
            {
                "api_key",
                "file_type",
                "include_release_dates_with_no_data",
                "realtime_start",
                "realtime_end",
                "limit",
                "offset",
                "order_by",
                "sort_order",
            }
        ),
        fixed_query=(
            ("file_type", "json"),
            ("include_release_dates_with_no_data", "true"),
            ("limit", str(FRED_PAGE_SIZE)),
            ("order_by", "release_date"),
            ("sort_order", "asc"),
        ),
        allowed_headers=frozenset(),
        required_headers=frozenset(),
        accept="application/json",
    ),
}

FetchBytes = Callable[[ProviderRequest], bytes]


@dataclass(frozen=True)
class Window:
    timezone_name: str
    from_date: date
    days: int
    start: datetime
    end: datetime

    @classmethod
    def build(cls, from_date: date, days: int, timezone_name: str) -> Window:
        if days < 1:
            raise ValueError("days must be at least 1")
        try:
            display_zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {timezone_name}") from exc
        start = datetime.combine(from_date, time.min, display_zone)
        end = datetime.combine(from_date + timedelta(days=days), time.min, display_zone)
        return cls(timezone_name, from_date, days, start, end)

    @property
    def through_date(self) -> date:
        return self.from_date + timedelta(days=self.days - 1)

    def contains_date(self, candidate: date) -> bool:
        return self.from_date <= candidate <= self.through_date

    def contains_instant(self, candidate: datetime) -> bool:
        if candidate.tzinfo is None:
            raise ValueError("candidate instant must be timezone-aware")
        return self.start <= candidate.astimezone(self.start.tzinfo) < self.end

    def as_dict(self) -> dict[str, object]:
        return {
            "timezone": self.timezone_name,
            "from_date": self.from_date.isoformat(),
            "through_date": self.through_date.isoformat(),
            "start_utc": _utc_iso(self.start),
            "end_utc_exclusive": _utc_iso(self.end),
        }


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def validate_request(request: ProviderRequest) -> None:
    """Reject any request outside the permanently free endpoint allowlist."""

    policy = _PROVIDER_POLICIES.get(request.provider)
    if policy is None:
        raise ProviderFailure("provider is not allowlisted")
    if request.endpoint != policy.endpoint:
        raise ProviderFailure("provider endpoint is not allowlisted")
    if "?" in request.endpoint or "#" in request.endpoint:
        raise ProviderFailure(
            "provider endpoint must not contain query or fragment data"
        )

    query_keys = [key for key, _ in request.query]
    if len(query_keys) != len(set(query_keys)):
        raise ProviderFailure("duplicate query parameter")
    unknown_query = set(query_keys) - policy.allowed_query
    if unknown_query:
        raise ProviderFailure("query parameter is not allowlisted")
    if not policy.required_query.issubset(query_keys):
        raise ProviderFailure("required query parameter is missing")
    query = dict(request.query)
    for key, expected in policy.fixed_query:
        if query.get(key) != expected:
            raise ProviderFailure("fixed query parameter has an unsafe value")

    header_names = [name.lower() for name, _ in request.headers]
    if len(header_names) != len(set(header_names)):
        raise ProviderFailure("duplicate request header")
    unknown_headers = set(header_names) - policy.allowed_headers
    if unknown_headers:
        raise ProviderFailure("request header is not allowlisted")
    if not policy.required_headers.issubset(header_names):
        raise ProviderFailure("required request header is missing")
    if any(not value for _, value in request.query + request.headers):
        raise ProviderFailure("request parameter or header is blank")
    if request.accept != policy.accept:
        raise ProviderFailure("request Accept value is not allowlisted")
    if request.timeout_seconds < 1 or request.timeout_seconds > FRED_TIMEOUT_SECONDS:
        raise ProviderFailure("request timeout is outside the allowlisted range")


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(  # type: ignore[no-untyped-def]
        self, req, fp, code, msg, headers, newurl
    ):
        del req, fp, code, msg, headers, newurl
        return None


def fetch_bytes(provider_request: ProviderRequest) -> bytes:
    validate_request(provider_request)
    query = urlencode(provider_request.query)
    url = (
        provider_request.endpoint
        if not query
        else f"{provider_request.endpoint}?{query}"
    )
    headers = {
        "Accept": provider_request.accept,
        "User-Agent": USER_AGENT,
        **dict(provider_request.headers),
    }
    request = Request(url, headers=headers, method="GET")
    opener = build_opener(_NoRedirectHandler())
    try:
        with opener.open(
            request, timeout=provider_request.timeout_seconds
        ) as response:
            return response.read()
    except HTTPError as exc:
        raise ProviderFailure(f"HTTP {exc.code}") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        reason_name = type(reason).__name__ if reason is not None else "unknown"
        raise ProviderFailure(f"network error ({reason_name})") from exc
    except TimeoutError as exc:
        raise ProviderFailure("request timed out") from exc


def _fetch(fetcher: FetchBytes, request: ProviderRequest) -> bytes:
    validate_request(request)
    return fetcher(request)


def _unfold_ics(text: str) -> list[str]:
    unfolded: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw_line[1:]
        else:
            unfolded.append(raw_line)
    return unfolded


def _ics_unescape(value: str) -> str:
    return (
        value.replace("\\N", "\n")
        .replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _ics_events(payload: bytes) -> list[dict[str, list[tuple[dict[str, str], str]]]]:
    events: list[dict[str, list[tuple[dict[str, str], str]]]] = []
    current: dict[str, list[tuple[dict[str, str], str]]] | None = None
    text = payload.decode("utf-8-sig")
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        raw_name, raw_value = line.split(":", 1)
        parts = raw_name.split(";")
        name = parts[0].upper()
        params: dict[str, str] = {}
        for parameter in parts[1:]:
            if "=" in parameter:
                key, value = parameter.split("=", 1)
                params[key.upper()] = value.strip('"')
        current.setdefault(name, []).append((params, _ics_unescape(raw_value)))
    return events


def _first_ics(
    event: dict[str, list[tuple[dict[str, str], str]]], name: str
) -> tuple[dict[str, str], str] | None:
    values = event.get(name)
    return values[0] if values else None


_TZID_ALIASES = {
    "US-Eastern": "America/New_York",
    "US/Eastern": "America/New_York",
    "Eastern Standard Time": "America/New_York",
}


def _parse_ics_start(
    params: dict[str, str], value: str, default_timezone: str
) -> tuple[date, datetime | None]:
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        try:
            parsed_date = date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:8]}")
        except ValueError as exc:
            raise ProviderFailure(f"invalid ICS date: {value!r}") from exc
        return parsed_date, None

    is_utc = value.endswith("Z")
    core = value[:-1] if is_utc else value
    parsed: datetime | None = None
    for pattern in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            parsed = datetime.strptime(core, pattern)  # noqa: DTZ007
            break
        except ValueError:
            continue
    if parsed is None:
        raise ProviderFailure(f"unsupported ICS DTSTART value: {value!r}")
    if is_utc:
        aware = parsed.replace(tzinfo=UTC)
    else:
        timezone_name = _TZID_ALIASES.get(
            params.get("TZID", default_timezone),
            params.get("TZID", default_timezone),
        )
        try:
            aware = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as exc:
            raise ProviderFailure(f"unknown ICS timezone: {timezone_name}") from exc
    return aware.date(), aware


def _empty_event() -> dict[str, object]:
    return {
        "event_type": None,
        "title": None,
        "local_date": None,
        "local_time": None,
        "timezone": None,
        "starts_at_utc": None,
        "time_precision": None,
        "schedule_status": None,
        "country": None,
        "company": None,
        "symbol": None,
        "period": None,
        "session": None,
        "source_session": None,
        "forecast": None,
        "provider_forecast": None,
        "previous": None,
        "estimate": None,
        "currency": None,
        "importance": None,
        "last_updated": None,
        "source_starts_at": None,
        "source_timezone": None,
        "source_status": None,
        "source_sequence": None,
        "source_id": None,
        "source": None,
    }


def _ics_source_timezone(
    params: dict[str, str], value: str, default_timezone: str
) -> str | None:
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        return params.get("TZID")
    if value.endswith("Z"):
        return "UTC"
    return params.get("TZID", default_timezone)


def _ics_last_updated(
    raw_event: dict[str, list[tuple[dict[str, str], str]]],
    default_timezone: str,
) -> str | None:
    updated_field = _first_ics(raw_event, "LAST-MODIFIED") or _first_ics(
        raw_event, "DTSTAMP"
    )
    if updated_field is None:
        return None
    _, instant = _parse_ics_start(updated_field[0], updated_field[1], default_timezone)
    if instant is None:
        raise ProviderFailure("ICS revision timestamp must include a time")
    return _utc_iso(instant)


def parse_ics_candidates(
    payload: bytes,
    *,
    window: Window,
    provider: str,
    schedule_url: str,
    default_timezone: str,
    country: str,
) -> list[dict[str, object]]:
    display_zone = ZoneInfo(window.timezone_name)
    candidates: list[dict[str, object]] = []
    for raw_event in _ics_events(payload):
        start_field = _first_ics(raw_event, "DTSTART")
        summary_field = _first_ics(raw_event, "SUMMARY")
        if start_field is None or summary_field is None:
            continue
        source_date, instant = _parse_ics_start(
            start_field[0], start_field[1], default_timezone
        )
        if instant is None:
            local_date = source_date
            local_time = None
            starts_at_utc = None
            precision = "date"
            if not window.contains_date(local_date):
                continue
        else:
            if not window.contains_instant(instant):
                continue
            displayed = instant.astimezone(display_zone)
            local_date = displayed.date()
            local_time = displayed.strftime("%H:%M")
            starts_at_utc = _utc_iso(instant)
            precision = "exact"

        uid_field = _first_ics(raw_event, "UID")
        url_field = _first_ics(raw_event, "URL")
        status_field = _first_ics(raw_event, "STATUS")
        sequence_field = _first_ics(raw_event, "SEQUENCE")
        source_status = status_field[1].strip().upper() if status_field else None
        schedule_status = {
            "CANCELLED": "cancelled",
            "TENTATIVE": "tentative",
        }.get(source_status, "official-scheduled")
        source_sequence: int | None = None
        if sequence_field is not None:
            try:
                source_sequence = int(sequence_field[1])
            except ValueError as exc:
                raise ProviderFailure("ICS SEQUENCE must be an integer") from exc
        event = _empty_event()
        event.update(
            {
                "event_type": "macro",
                "title": summary_field[1],
                "local_date": local_date.isoformat(),
                "local_time": local_time,
                "timezone": window.timezone_name,
                "starts_at_utc": starts_at_utc,
                "time_precision": precision,
                "schedule_status": schedule_status,
                "country": country,
                "last_updated": _ics_last_updated(raw_event, default_timezone),
                "source_starts_at": start_field[1],
                "source_timezone": _ics_source_timezone(
                    start_field[0], start_field[1], default_timezone
                ),
                "source_status": source_status,
                "source_sequence": source_sequence,
                "source_id": uid_field[1] if uid_field else None,
                "source": {
                    "provider": provider,
                    "authority": "official",
                    "schedule_url": schedule_url,
                    "item_url": url_field[1] if url_field else None,
                },
            }
        )
        candidates.append(event)
    return candidates


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class FinnhubBatch:
    events: list[dict[str, object]]
    raw_count: int


def parse_finnhub_candidates(
    payload: bytes,
    *,
    window: Window,
    expected_from: date,
    expected_through: date,
) -> FinnhubBatch:
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderFailure("invalid JSON response") from exc
    if not isinstance(document, dict):
        raise ProviderFailure("unexpected non-object JSON response")
    rows = document.get("earningsCalendar")
    if not isinstance(rows, list):
        raise ProviderFailure("unexpected earnings calendar schema")

    session_names = {
        "bmo": "pre-market",
        "amc": "post-market",
        "dmh": "during-market",
    }
    candidates: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ProviderFailure("earnings row is not an object")
        raw_date = _optional_text(row.get("date"))
        symbol = _optional_text(row.get("symbol"))
        if raw_date is None or symbol is None:
            raise ProviderFailure("earnings row is missing date or symbol")
        try:
            report_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ProviderFailure("earnings row has an invalid date") from exc
        if not expected_from <= report_date <= expected_through:
            raise ProviderFailure("earnings row is outside requested partition")
        if not window.contains_date(report_date):
            raise ProviderFailure("earnings row is outside requested window")

        source_session = _optional_text(row.get("hour"))
        if source_session is not None:
            source_session = source_session.lower()
            if source_session not in session_names:
                raise ProviderFailure("earnings row has an unsupported hour")
        session = session_names.get(source_session)
        year = _optional_text(row.get("year"))
        quarter = _optional_text(row.get("quarter"))
        period = f"Q{quarter} {year}" if quarter and year else year or quarter
        event = _empty_event()
        event.update(
            {
                "event_type": "earnings",
                "title": symbol,
                "symbol": symbol,
                "local_date": report_date.isoformat(),
                "local_time": None,
                "timezone": window.timezone_name,
                "starts_at_utc": None,
                "time_precision": "session" if session else "date",
                "schedule_status": "expected",
                "period": period,
                "session": session,
                "source_session": source_session,
                "estimate": _optional_text(row.get("epsEstimate")),
                "source_id": (
                    f"{symbol}:{report_date.isoformat()}:{year or ''}:Q{quarter or ''}"
                ),
                "source": {
                    "provider": "finnhub",
                    "authority": "aggregator",
                    "schedule_url": FINNHUB_EARNINGS_DOCS_URL,
                    "item_url": None,
                },
            }
        )
        candidates.append(event)
    return FinnhubBatch(events=candidates, raw_count=len(rows))


def _normalize_session(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "before-market": "pre-market",
        "before-market-open": "pre-market",
        "after-market": "post-market",
        "after-market-close": "post-market",
        "during-market": "during-market",
    }
    return aliases.get(normalized, normalized or None)


def parse_alpha_vantage_candidates(
    payload: bytes, *, window: Window
) -> list[dict[str, object]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProviderFailure("invalid CSV encoding") from exc
    if text.lstrip().startswith(("{", "[")):
        raise ProviderFailure("provider returned a non-CSV response")
    reader = csv.DictReader(io.StringIO(text))
    required = {"symbol", "name", "reportDate"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ProviderFailure("unexpected earnings CSV schema")

    candidates: list[dict[str, object]] = []
    for row in reader:
        raw_date = _optional_text(row.get("reportDate"))
        if raw_date is None:
            raise ProviderFailure("earnings row is missing reportDate")
        try:
            report_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ProviderFailure("earnings row has an invalid reportDate") from exc
        if not window.contains_date(report_date):
            continue
        company = _optional_text(row.get("name"))
        symbol = _optional_text(row.get("symbol"))
        if company is None or symbol is None:
            raise ProviderFailure("earnings row is missing name or symbol")
        source_session = _optional_text(row.get("timeOfTheDay"))
        session = _normalize_session(source_session)
        event = _empty_event()
        event.update(
            {
                "event_type": "earnings",
                "title": company,
                "company": company,
                "symbol": symbol,
                "local_date": report_date.isoformat(),
                "local_time": None,
                "timezone": window.timezone_name,
                "starts_at_utc": None,
                "time_precision": "session" if session else "date",
                "schedule_status": "expected",
                "period": _optional_text(row.get("fiscalDateEnding")),
                "session": session,
                "source_session": source_session,
                "estimate": _optional_text(row.get("estimate")),
                "currency": _optional_text(row.get("currency")),
                "source_id": f"{symbol}:{report_date.isoformat()}",
                "source": {
                    "provider": "alpha-vantage",
                    "authority": "aggregator",
                    "schedule_url": ALPHA_VANTAGE_DOCS_URL,
                    "item_url": None,
                },
            }
        )
        candidates.append(event)
    return candidates


FRED_RELEASE_ALLOWLIST = {
    9: "Advance Monthly Sales for Retail and Food Services",
    10: "Consumer Price Index",
    13: "G.17 Industrial Production and Capacity Utilization",
    27: "New Residential Construction",
    46: "Producer Price Index",
    180: "Unemployment Insurance Weekly Claims Report",
    188: "U.S. Import and Export Price Indexes",
    291: "Existing Home Sales",
    321: "Empire State Manufacturing Survey",
    351: "Manufacturing Business Outlook Survey",
}


@dataclass(frozen=True)
class FredPage:
    events: list[dict[str, object]]
    total_count: int
    offset: int
    row_count: int


def _required_nonnegative_int(document: Mapping[str, object], key: str) -> int:
    raw_value = document.get(key)
    try:
        value = int(raw_value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ProviderFailure(f"FRED response has an invalid {key}") from exc
    if value < 0:
        raise ProviderFailure(f"FRED response has an invalid {key}")
    return value


def parse_fred_release_dates_candidates(
    payload: bytes, *, window: Window
) -> FredPage:
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderFailure("invalid JSON response") from exc
    if not isinstance(document, dict):
        raise ProviderFailure("unexpected non-object JSON response")
    rows = document.get("release_dates")
    if not isinstance(rows, list):
        raise ProviderFailure("unexpected FRED release-dates schema")
    total_count = _required_nonnegative_int(document, "count")
    offset = _required_nonnegative_int(document, "offset")

    candidates: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ProviderFailure("FRED release row is not an object")
        try:
            release_id = int(row.get("release_id"))
        except (TypeError, ValueError) as exc:
            raise ProviderFailure("FRED release row has an invalid release_id") from exc
        expected_name = FRED_RELEASE_ALLOWLIST.get(release_id)
        if expected_name is None:
            continue
        release_name = _optional_text(row.get("release_name"))
        if release_name != expected_name:
            raise ProviderFailure(
                f"FRED release name changed for allowlisted id {release_id}"
            )
        raw_date = _optional_text(row.get("date"))
        if raw_date is None:
            raise ProviderFailure("FRED release row is missing date")
        try:
            release_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ProviderFailure("FRED release row has an invalid date") from exc
        if not window.contains_date(release_date) or release_date.weekday() >= 5:
            continue

        event = _empty_event()
        event.update(
            {
                "event_type": "macro",
                "title": release_name,
                "local_date": release_date.isoformat(),
                "local_time": None,
                "timezone": window.timezone_name,
                "starts_at_utc": None,
                "time_precision": "date",
                "schedule_status": "aggregated-scheduled",
                "country": "United States",
                "source_id": f"{release_id}:{release_date.isoformat()}",
                "source": {
                    "provider": "fred",
                    "authority": "aggregator-backstop",
                    "schedule_url": FRED_RELEASES_DATES_DOCS_URL,
                    "item_url": None,
                },
            }
        )
        candidates.append(event)
    return FredPage(
        events=candidates,
        total_count=total_count,
        offset=offset,
        row_count=len(rows),
    )


def _provider_report(
    provider: str,
    authority: str,
    source_url: str,
    status: str,
    *,
    event_count: int = 0,
    message: str | None = None,
    warnings: Iterable[str] = (),
) -> dict[str, object]:
    return {
        "provider": provider,
        "authority": authority,
        "status": status,
        "event_count": event_count,
        "message": message,
        "warnings": list(warnings),
        "source_url": source_url,
    }


def _deduplicate(events: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[object, ...]] = set()
    result: list[dict[str, object]] = []
    for event in events:
        source = event.get("source")
        provider = source.get("provider") if isinstance(source, dict) else None
        source_id = event.get("source_id")
        if source_id is not None:
            key = (provider, source_id)
        else:
            key = (
                provider,
                event.get("event_type"),
                event.get("title"),
                event.get("local_date"),
                event.get("local_time"),
                event.get("symbol"),
            )
        if key not in seen:
            seen.add(key)
            result.append(event)
    return result


def _event_sort_key(event: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(event.get("local_date") or ""),
        str(event.get("local_time") or "99:99"),
        str(event.get("event_type") or ""),
        str(event.get("title") or ""),
    )


def _lane_report(
    *,
    name: str,
    requested: bool,
    provider_names: set[str],
    events: list[dict[str, object]],
    providers: list[dict[str, object]],
) -> dict[str, object]:
    provider_statuses = {
        str(provider["provider"]): str(provider["status"])
        for provider in providers
        if provider["provider"] in provider_names
    }
    usable_events = [
        event
        for event in events
        if event.get("event_type") == name
        and event.get("schedule_status") != "cancelled"
    ]
    if not requested:
        status = "not-requested"
    elif usable_events:
        status = "candidate-set-available"
    else:
        status = "manual-collection-required"
    return {
        "status": status,
        "candidate_count": len(usable_events),
        "provider_statuses": provider_statuses,
    }


def _unexpected_message(exc: Exception) -> str:
    return f"unexpected {type(exc).__name__}"


def _date_partitions(window: Window) -> Iterable[tuple[date, date]]:
    partition_start = window.from_date
    while partition_start <= window.through_date:
        partition_end = min(
            partition_start + timedelta(days=FINNHUB_PARTITION_DAYS - 1),
            window.through_date,
        )
        yield partition_start, partition_end
        partition_start = partition_end + timedelta(days=1)


def load_foreign_issuers(path: Path = FOREIGN_ISSUERS) -> dict[str, dict[str, object]]:
    """Symbol -> its references/foreign-issuers.tsv row, months as a set of ints; a bad zone fails loudly."""
    issuers: dict[str, dict[str, object]] = {}
    for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")), delimiter="\t"):
        try:
            ZoneInfo(row["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"{path.name}: unknown IANA timezone {row['timezone']!r}") from exc
        issuers[row["symbol"].upper()] = {**row, "months": {int(m) for m in row["months"].split()}}
    return issuers


def foreign_issuer_notes(
    events: Iterable[dict[str, object]],
    issuers: Mapping[str, Mapping[str, object]],
    window: Window,
) -> tuple[list[str], list[str]]:
    """Stamp each foreign issuer's earnings row with its source_timezone, and return (rows whose issuer-local date
    may be the previous display date, listed issuers in a reporting month with no row in the window).

    A feed's date-only row carries the issuer's local date (10-11: TSMC's 14:00 Taipei call on Oct. 15 was 23:00
    PT on Oct. 14; ASML's 07:00 Amsterdam release on Oct. 14 was 22:00 PT on Oct. 13)."""
    display = ZoneInfo(window.timezone_name)
    early, seen = [], set()
    for event in events:
        issuer = issuers.get(str(event.get("symbol") or "").upper())
        if event.get("event_type") != "earnings" or issuer is None or event.get("local_time"):
            continue
        seen.add(str(event["symbol"]).upper())
        event["source_timezone"] = issuer["timezone"]
        noon = datetime.combine(date.fromisoformat(str(event["local_date"])), time(12))
        if noon.replace(tzinfo=ZoneInfo(str(issuer["timezone"]))).utcoffset() > noon.replace(tzinfo=display).utcoffset():
            early.append(f"{event['symbol']} {event['local_date']} ({issuer['timezone']})")
    months = {(window.from_date + timedelta(days=n)).month for n in range(window.days)}
    absent = [f"{row['company']} ({symbol}) {row['ir_url']}" for symbol, row in issuers.items()
              if symbol not in seen and months & row["months"]]
    return list(dict.fromkeys(early)), absent


def _next_actions(
    *,
    lanes: Mapping[str, Mapping[str, object]],
    providers: Iterable[Mapping[str, object]],
    earnings_requested: bool,
    window: Window | None = None,
    early_dates: Iterable[str] = (),
    absent_issuers: Iterable[str] = (),
) -> list[dict[str, object]]:
    statuses = {
        str(provider["provider"]): str(provider["status"]) for provider in providers
    }
    actions: list[dict[str, object]] = []
    zone = window.timezone_name if window else "the display zone"
    # The ICS returns 403 to scripts, but the monthly schedule page loaded for a delegate (10-11).
    bls_months = (
        sorted({(d.year, d.month) for d in (window.from_date, window.through_date)})
        if window else []
    )
    if statuses.get("bls") != "ok":
        actions.append(
            {
                "lane": "macro",
                "source": "BLS release calendar",
                "retrieval_mode": "approved browser or local ICS",
                "url": BLS_SCHEDULE_URL,
                "reason": (
                    "the bundled collector does not fetch the access-controlled BLS ICS"
                ),
                "required_for_claim": True,
                "fallback_source": " ".join(
                    f"https://www.bls.gov/schedule/{year}/{month:02d}_sched.htm"
                    for year, month in bls_months
                ) or None,
            }
        )
    actions.extend(
        [
            {
                "lane": "macro",
                "source": "Federal Reserve and FOMC calendars",
                "retrieval_mode": "official browser check",
                "url": "https://www.federalreserve.gov/newsevents/calendar.htm",
                "reason": "no accepted comprehensive programmatic calendar feed",
                "required_for_claim": True,
                "fallback_source": (
                    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
                ),
            },
            {
                "lane": "macro",
                "source": "Census economic indicators calendar",
                "retrieval_mode": "official browser check",
                "url": (
                    "https://www.census.gov/economic-indicators/calendar-listview.html"
                ),
                "reason": "no accepted stable documented calendar API",
                "required_for_claim": True,
                "fallback_source": None,
            },
            {
                "lane": "macro",
                "source": "Treasury tentative auction schedule",
                "retrieval_mode": "official PDF and announcement check",
                "url": (
                    "https://home.treasury.gov/system/files/221/"
                    "Tentative-Auction-Schedule.pdf"
                ),
                "reason": (
                    "the official schedule is a PDF and remains tentative until announced"
                ),
                "required_for_claim": True,
                "fallback_source": "https://www.treasurydirect.gov/auctions/upcoming/",
            },
        ]
    )
    if earnings_requested:
        if lanes["earnings"]["status"] != "candidate-set-available":
            actions.append(
                {
                    "lane": "earnings",
                    "source": "Nasdaq public earnings calendar",
                    "retrieval_mode": "manual browser discovery",
                    "url": "https://www.nasdaq.com/market-activity/earnings",
                    "reason": "the free API candidate lane returned no usable events",
                    "required_for_claim": True,
                    "fallback_source": None,
                }
            )
        actions.append(
            {
                "lane": "earnings",
                "source": "issuer investor relations",
                "retrieval_mode": "issuer page or dated announcement",
                "url": None,
                "reason": (
                    "every selected earnings candidate requires first-party confirmation"
                ),
                "required_for_claim": True,
                "fallback_source": None,
            }
        )
        if early := list(early_dates):
            actions.append(
                {
                    "lane": "earnings",
                    "source": "foreign issuer investor relations",
                    "retrieval_mode": "issuer page or dated announcement",
                    "url": None,
                    "reason": (
                        "feeds give these issuers' local dates, in zones ahead of "
                        f"{zone}; the release may fall on the previous {zone} date: "
                        + "; ".join(early)
                    ),
                    "required_for_claim": True,
                    "fallback_source": "the issuer's dated release on PR Newswire or Business Wire",
                }
            )
        if absent := list(absent_issuers):
            actions.append(
                {
                    "lane": "earnings",
                    "source": "foreign read-through issuers (references/foreign-issuers.tsv)",
                    "retrieval_mode": "issuer financial calendar",
                    "url": None,
                    "reason": (
                        "a reporting month overlaps the window and no feed row lists "
                        "them; check whether the release falls inside it: " + "; ".join(absent)
                    ),
                    "required_for_claim": False,
                    "fallback_source": "the issuer's dated release on PR Newswire or Business Wire",
                }
            )
    return actions


def collect(
    *,
    window: Window,
    skip_earnings: bool,
    use_fred: bool = False,
    strict: bool = False,
    bls_ics_payload: bytes | None = None,
    environment: Mapping[str, str] | None = None,
    fetcher: FetchBytes = fetch_bytes,
) -> tuple[dict[str, object], int]:
    env = os.environ if environment is None else environment
    events: list[dict[str, object]] = []
    providers: list[dict[str, object]] = []

    if bls_ics_payload is None:
        providers.append(
            _provider_report(
                "bls",
                "official",
                BLS_SCHEDULE_URL,
                "manual_download_required",
                message="pass an official BLS calendar file with --bls-ics",
            )
        )
    else:
        try:
            parsed = parse_ics_candidates(
                bls_ics_payload,
                window=window,
                provider="bls",
                schedule_url=BLS_SCHEDULE_URL,
                default_timezone="America/New_York",
                country="United States",
            )
            events.extend(parsed)
            providers.append(
                _provider_report(
                    "bls",
                    "official",
                    BLS_SCHEDULE_URL,
                    "ok",
                    event_count=len(parsed),
                )
            )
        except ProviderFailure as exc:
            providers.append(
                _provider_report(
                    "bls", "official", BLS_SCHEDULE_URL, "error", message=str(exc)
                )
            )
        except Exception as exc:  # noqa: BLE001 - isolate provider failures
            providers.append(
                _provider_report(
                    "bls",
                    "official",
                    BLS_SCHEDULE_URL,
                    "error",
                    message=_unexpected_message(exc),
                )
            )

    try:
        payload = _fetch(
            fetcher,
            ProviderRequest(
                provider="bea",
                endpoint=BEA_ICS_URL,
                accept="text/calendar",
            ),
        )
        parsed = parse_ics_candidates(
            payload,
            window=window,
            provider="bea",
            schedule_url=BEA_SCHEDULE_URL,
            default_timezone="America/New_York",
            country="United States",
        )
        events.extend(parsed)
        providers.append(
            _provider_report(
                "bea", "official", BEA_SCHEDULE_URL, "ok", event_count=len(parsed)
            )
        )
    except ProviderFailure as exc:
        providers.append(
            _provider_report(
                "bea", "official", BEA_SCHEDULE_URL, "error", message=str(exc)
            )
        )
    except Exception as exc:  # noqa: BLE001 - isolate provider failures
        providers.append(
            _provider_report(
                "bea",
                "official",
                BEA_SCHEDULE_URL,
                "error",
                message=_unexpected_message(exc),
            )
        )

    if use_fred:
        fred_key = env.get("FRED_API_KEY", "").strip()
        if fred_key:
            try:
                fred_events: list[dict[str, object]] = []
                offset = 0
                while True:
                    request = ProviderRequest(
                        provider="fred",
                        endpoint=FRED_RELEASES_DATES_ENDPOINT,
                        query=(
                            ("api_key", fred_key),
                            ("file_type", "json"),
                            ("include_release_dates_with_no_data", "true"),
                            ("realtime_start", window.from_date.isoformat()),
                            ("realtime_end", window.through_date.isoformat()),
                            ("limit", str(FRED_PAGE_SIZE)),
                            ("offset", str(offset)),
                            ("order_by", "release_date"),
                            ("sort_order", "asc"),
                        ),
                        accept="application/json",
                        timeout_seconds=FRED_TIMEOUT_SECONDS,
                    )
                    page = parse_fred_release_dates_candidates(
                        _fetch(fetcher, request), window=window
                    )
                    if page.offset != offset:
                        raise ProviderFailure(
                            "FRED response offset did not match request"
                        )
                    fred_events.extend(page.events)
                    next_offset = offset + page.row_count
                    if next_offset >= page.total_count:
                        break
                    if page.row_count == 0:
                        raise ProviderFailure("FRED pagination stopped before count")
                    offset = next_offset
                events.extend(fred_events)
                providers.append(
                    _provider_report(
                        "fred",
                        "aggregator-backstop",
                        FRED_RELEASES_DATES_DOCS_URL,
                        "ok",
                        event_count=len(fred_events),
                    )
                )
            except ProviderFailure as exc:
                providers.append(
                    _provider_report(
                        "fred",
                        "aggregator-backstop",
                        FRED_RELEASES_DATES_DOCS_URL,
                        "error",
                        message=str(exc),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                providers.append(
                    _provider_report(
                        "fred",
                        "aggregator-backstop",
                        FRED_RELEASES_DATES_DOCS_URL,
                        "error",
                        message=_unexpected_message(exc),
                    )
                )
        else:
            providers.append(
                _provider_report(
                    "fred",
                    "aggregator-backstop",
                    FRED_RELEASES_DATES_DOCS_URL,
                    "skipped_not_configured",
                    message="FRED_API_KEY is not configured",
                )
            )
    else:
        providers.append(
            _provider_report(
                "fred",
                "aggregator-backstop",
                FRED_RELEASES_DATES_DOCS_URL,
                "skipped_by_default",
                message="enable the conservative FRED gap detector with --use-fred",
            )
        )

    if skip_earnings:
        for provider, source_url in (
            ("finnhub", FINNHUB_EARNINGS_DOCS_URL),
            ("alpha-vantage", ALPHA_VANTAGE_DOCS_URL),
        ):
            providers.append(
                _provider_report(
                    provider,
                    "aggregator",
                    source_url,
                    "skipped_by_request",
                    message="earnings collection was disabled",
                )
            )
    else:
        finnhub_key = env.get("FINNHUB_API_KEY", "").strip()
        if finnhub_key:
            try:
                finnhub_events: list[dict[str, object]] = []
                warnings: list[str] = []
                for partition_start, partition_end in _date_partitions(window):
                    request = ProviderRequest(
                        provider="finnhub",
                        endpoint=FINNHUB_EARNINGS_ENDPOINT,
                        query=(
                            ("from", partition_start.isoformat()),
                            ("to", partition_end.isoformat()),
                            ("international", "false"),
                        ),
                        headers=(("X-Finnhub-Token", finnhub_key),),
                        accept="application/json",
                    )
                    batch = parse_finnhub_candidates(
                        _fetch(fetcher, request),
                        window=window,
                        expected_from=partition_start,
                        expected_through=partition_end,
                    )
                    finnhub_events.extend(batch.events)
                    if batch.raw_count == FINNHUB_POSSIBLE_CAP:
                        warnings.append(
                            "A partition returned exactly 1,500 rows; the response "
                            "may be capped. "
                            f"Cross-check {partition_start.isoformat()} through "
                            f"{partition_end.isoformat()} with Alpha Vantage and "
                            "issuer sources."
                        )
                finnhub_events = _deduplicate(finnhub_events)
                events.extend(finnhub_events)
                providers.append(
                    _provider_report(
                        "finnhub",
                        "aggregator",
                        FINNHUB_EARNINGS_DOCS_URL,
                        "ok",
                        event_count=len(finnhub_events),
                        warnings=warnings,
                    )
                )
            except ProviderFailure as exc:
                providers.append(
                    _provider_report(
                        "finnhub",
                        "aggregator",
                        FINNHUB_EARNINGS_DOCS_URL,
                        "error",
                        message=str(exc),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                providers.append(
                    _provider_report(
                        "finnhub",
                        "aggregator",
                        FINNHUB_EARNINGS_DOCS_URL,
                        "error",
                        message=_unexpected_message(exc),
                    )
                )
        else:
            providers.append(
                _provider_report(
                    "finnhub",
                    "aggregator",
                    FINNHUB_EARNINGS_DOCS_URL,
                    "skipped_not_configured",
                    message="FINNHUB_API_KEY is not configured",
                )
            )

        alpha_key = env.get("ALPHAVANTAGE_API_KEY", "").strip()
        if alpha_key:
            try:
                request = ProviderRequest(
                    provider="alpha-vantage",
                    endpoint=ALPHA_VANTAGE_ENDPOINT,
                    query=(
                        ("function", "EARNINGS_CALENDAR"),
                        ("horizon", "3month"),
                        ("apikey", alpha_key),
                    ),
                    accept="*/*",
                )
                parsed = parse_alpha_vantage_candidates(
                    _fetch(fetcher, request), window=window
                )
                events.extend(parsed)
                providers.append(
                    _provider_report(
                        "alpha-vantage",
                        "aggregator",
                        ALPHA_VANTAGE_DOCS_URL,
                        "ok",
                        event_count=len(parsed),
                    )
                )
            except ProviderFailure as exc:
                providers.append(
                    _provider_report(
                        "alpha-vantage",
                        "aggregator",
                        ALPHA_VANTAGE_DOCS_URL,
                        "error",
                        message=str(exc),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - isolate provider failures
                providers.append(
                    _provider_report(
                        "alpha-vantage",
                        "aggregator",
                        ALPHA_VANTAGE_DOCS_URL,
                        "error",
                        message=_unexpected_message(exc),
                    )
                )
        else:
            providers.append(
                _provider_report(
                    "alpha-vantage",
                    "aggregator",
                    ALPHA_VANTAGE_DOCS_URL,
                    "skipped_not_configured",
                    message="ALPHAVANTAGE_API_KEY is not configured",
                )
            )

    normalized_events = sorted(_deduplicate(events), key=_event_sort_key)
    early_dates, absent_issuers = (
        ([], []) if skip_earnings
        else foreign_issuer_notes(normalized_events, load_foreign_issuers(), window)
    )
    successful = [provider for provider in providers if provider["status"] == "ok"]
    lanes = {
        "macro": _lane_report(
            name="macro",
            requested=True,
            provider_names={"bls", "bea", "fred"},
            events=normalized_events,
            providers=providers,
        ),
        "earnings": _lane_report(
            name="earnings",
            requested=not skip_earnings,
            provider_names={"finnhub", "alpha-vantage"},
            events=normalized_events,
            providers=providers,
        ),
    }
    requested_lanes = [
        lane for lane in lanes.values() if lane["status"] != "not-requested"
    ]
    automation_status = (
        "candidate-sets-available"
        if requested_lanes
        and all(lane["status"] == "candidate-set-available" for lane in requested_lanes)
        else "manual-collection-required"
    )
    next_actions = _next_actions(
        lanes=lanes,
        providers=providers,
        earnings_requested=not skip_earnings,
        window=window,
        early_dates=early_dates,
        absent_issuers=absent_issuers,
    )
    output: dict[str, object] = {
        "schema_version": 1,
        "generated_at": _utc_iso(datetime.now(UTC)),
        "window": window.as_dict(),
        "coverage": {
            "claim": "candidate-set-only",
            "reason": (
                "No configured free feed is treated as a complete or final schedule; "
                "selected events require first-party verification."
            ),
            "providers": providers,
            "automation_status": automation_status,
            "lanes": lanes,
            "next_actions": next_actions,
            "manual_checks_required": [
                f"{action['source']}: {action['reason']}" for action in next_actions
            ],
        },
        "events": normalized_events,
    }
    # A lane can hold candidates while its main official source is missing (10-11: FRED's date-only backstop
    # rows filled the macro lane and --strict exited 0 without BLS), so strict also needs every official provider.
    official_missing = [
        provider
        for provider in providers
        if provider["authority"] == "official" and provider["status"] != "ok"
    ]
    if not successful:
        exit_code = 1
    elif strict and (
        official_missing
        or any(lane["status"] != "candidate-set-available" for lane in requested_lanes)
    ):
        exit_code = 2
    else:
        exit_code = 0
    return output, exit_code


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect source-labeled upcoming macro and earnings candidates."
    )
    parser.add_argument(
        "--from-date",
        type=_iso_date,
        help="first inclusive local date (default: today in --timezone)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=5,
        help="number of local calendar dates to include (default: 5)",
    )
    parser.add_argument(
        "--timezone",
        default="America/New_York",
        help="IANA timezone for filtering and display",
    )
    parser.add_argument(
        "--bls-ics",
        type=Path,
        help="locally downloaded official BLS iCalendar file",
    )
    parser.add_argument(
        "--skip-earnings",
        action="store_true",
        help="do not attempt the Finnhub and Alpha Vantage earnings calendars",
    )
    parser.add_argument(
        "--use-fred",
        action="store_true",
        help="enable the conservative, date-only FRED macro gap detector",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "return exit 2 when any requested lane has no usable candidates "
            "or an official source (BLS, BEA) did not load"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        display_zone = ZoneInfo(args.timezone)
        from_date = args.from_date or datetime.now(display_zone).date()
        window = Window.build(from_date, args.days, args.timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        parser.error(str(exc))
    try:
        bls_ics_payload = args.bls_ics.read_bytes() if args.bls_ics else None
    except OSError as exc:
        parser.error(f"cannot read --bls-ics: {exc.strerror or type(exc).__name__}")
    output, exit_code = collect(
        window=window,
        skip_earnings=args.skip_earnings,
        use_fred=args.use_fred,
        strict=args.strict,
        bls_ics_payload=bls_ics_payload,
    )
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
