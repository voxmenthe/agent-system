"""Free published Cboe/OCC inputs; Yahoo is optional context, never an SPX chain substitute."""

from __future__ import annotations

import csv
import io
import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import median
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from options_app.options_market_calendar import regular_session_bounds
from options_app.spx_report_store import SourceBlob

CBOE_URL = "https://cdn.cboe.com/resources/marking_prices/eod_marking_prices_list.csv"
OCC_URL = "https://marketdata.theocc.com/series-search?symbolType=U&symbol=SPX"
NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Contract:
    root: str
    expiry: str
    strike: float
    call_bid: float
    call_ask: float
    put_bid: float
    put_ask: float
    spot: float
    call_time: str
    put_time: str
    call_oi: int | None
    put_oi: int | None


def fetch_source(name: str, url: str) -> SourceBlob:
    if url not in (CBOE_URL, OCC_URL):
        raise ValueError("only the published Cboe/OCC downloads are supported")
    request = Request(
        url, headers={"User-Agent": "SPXDailyReport/1.0 (personal research)"}
    )
    with urlopen(request, timeout=45) as response:
        content = response.read(30_000_001)
    if not content or len(content) > 30_000_000:
        raise ValueError(f"{name}: empty or unexpectedly large download")
    return SourceBlob(name, url, datetime.now(UTC).isoformat(), content)


def _number(value: str, field: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"invalid {field}: {value!r}")
    return number


def _timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError(f"quote timestamp is not timezone-aware: {value}")
    return result


def parse_oi(content: bytes) -> dict[tuple[str, str, float], tuple[int, int]]:
    text = content.decode("utf-8-sig")
    if "Series Search Results for SPX" not in text or "Open Interest" not in text:
        raise ValueError("OCC response is not a recognized SPX series file")
    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        fields = line.split("\t")
        if fields[0].strip() not in ("SPX", "SPXW"):
            continue
        if len(fields) < 10 or fields[1].strip() or fields[7].split() != ["C", "P"]:
            raise ValueError(f"OCC layout changed on line {number}")
        expiry = date(int(fields[2]), int(fields[3]), int(fields[4])).isoformat()
        strike = _number(fields[5] + "." + fields[6], "strike")
        key = (fields[0].strip(), expiry, strike)
        values = (int(fields[8]), int(fields[9]))
        if min(values) < 0 or key in result:
            raise ValueError(f"OCC duplicate or negative OI on line {number}")
        result[key] = values
    if not result:
        raise ValueError("no standard SPX/SPXW OI records")
    return result


def parse_marks(
    content: bytes, oi: dict[tuple[str, str, float], tuple[int, int]]
) -> tuple[list[Contract], dict]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    required = {"root", "expiry", "strike", "call_underlying_value"}
    for side in ("call", "put"):
        required.update(
            {
                f"{side}_final_indicative_bid",
                f"{side}_final_indicative_ask",
                f"{side}_message_time",
            }
        )
    if not required.issubset(reader.fieldnames or []):
        raise ValueError(
            f"Cboe CSV schema missing fields: {sorted(required - set(reader.fieldnames or []))}"
        )
    contracts = []
    seen = set()
    dates = Counter()
    for row in reader:
        if row["root"] not in ("SPX", "SPXW"):
            continue
        expiry = date.fromisoformat(row["expiry"]).isoformat()
        strike = _number(row["strike"], "strike")
        key = (row["root"], expiry, strike)
        if key in seen or strike == 0:
            raise ValueError(f"Cboe duplicate/invalid contract: {key}")
        seen.add(key)
        times = [_timestamp(row[f"{s}_message_time"]) for s in ("call", "put")]
        dates.update(t.astimezone(NY).date().isoformat() for t in times)
        bids = [
            _number(row[f"{s}_final_indicative_{f}"], f"{s} {f}")
            for s in ("call", "put")
            for f in ("bid", "ask")
        ]
        spot = _number(row["call_underlying_value"], "underlying")
        if spot == 0:
            raise ValueError("Cboe underlying is zero")
        co, po = oi.get(key, (None, None))
        contracts.append(
            Contract(
                row["root"],
                expiry,
                strike,
                *bids,
                spot,
                *(t.isoformat() for t in times),
                co,
                po,
            )
        )
    if not contracts:
        raise ValueError("no SPX/SPXW marks in downloaded file")
    quote_date = dates.most_common(1)[0][0]
    bounds = regular_session_bounds(date.fromisoformat(quote_date))
    if bounds is None:
        raise ValueError(
            f"Cboe modal quote date is not a trading session: {quote_date}"
        )
    return contracts, {
        "quote_date": quote_date,
        "quote_at": bounds[1].isoformat(),
        "quote_date_method": "modal option-message date; regular-session close valuation clock",
        "spot": median(c.spot for c in contracts),
        "rows": len(contracts),
        "oi_matched_rows": sum(c.call_oi is not None for c in contracts),
        "quote_message_dates": dict(sorted(dates.items())),
    }


def expected_quote_date(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("collection clock must include a timezone")
    for ago in range(14):
        day = now.astimezone(NY).date() - timedelta(days=ago)
        bounds = regular_session_bounds(day)
        if bounds and bounds[1] + timedelta(minutes=30) <= now:
            return day.isoformat()
    raise ValueError("no completed session found")


def build_snapshot(
    marks: SourceBlob,
    oi: SourceBlob,
    *,
    oi_asof: str | None = None,
    oi_evidence: str | None = None,
    context: dict | None = None,
) -> dict:
    if bool(oi_asof) != bool(oi_evidence):
        raise ValueError("OI as-of date and evidence must be supplied together")
    if oi_asof:
        date.fromisoformat(oi_asof)
    contracts, metadata = parse_marks(marks.content, parse_oi(oi.content))
    captured = max(_timestamp(marks.retrieved_at), _timestamp(oi.retrieved_at))
    if metadata["quote_date"] > captured.astimezone(NY).date().isoformat():
        raise ValueError("quotes are from the future relative to collection time")
    if oi_asof and oi_asof > captured.astimezone(NY).date().isoformat():
        raise ValueError("OI as-of date is after collection")
    return {
        "schema_version": 1,
        "captured_at": captured.isoformat(),
        **metadata,
        "oi_asof": oi_asof,
        "oi_date_evidence": oi_evidence,
        "context": context or {"status": "not_requested", "quotes": [], "warnings": []},
        "contracts": [asdict(c) for c in contracts],
    }


def fetch_yahoo_context() -> tuple[dict, SourceBlob]:
    import json
    import yfinance as yf
    from requests.exceptions import RequestException
    from yfinance.exceptions import YFException
    from curl_cffi.requests.exceptions import RequestException as CurlRequestError

    quotes, warnings = [], []
    for symbol in ("^GSPC", "^VIX", "ES=F"):
        try:
            bars = yf.Ticker(symbol).history(
                period="5d",
                interval="5m",
                auto_adjust=False,
                prepost=True,
                raise_errors=True,
            )
        except (
            YFException,
            RequestException,
            CurlRequestError,
            ValueError,
            KeyError,
        ) as exc:
            warnings.append(f"{symbol}: {type(exc).__name__}: {exc}")
            continue
        closes = bars["Close"].dropna()
        if closes.empty or closes.index.tz is None:
            warnings.append(f"{symbol}: no timezone-aware recent prices")
            continue
        stamp = closes.index[-1].to_pydatetime().isoformat()
        price = float(closes.iloc[-1])
        if not math.isfinite(price) or price <= 0:
            warnings.append(f"{symbol}: invalid last price")
            continue
        quotes.append(
            {
                "symbol": symbol,
                "bar_start": stamp,
                "interval_minutes": 5,
                "close": price,
            }
        )
    context = {
        "status": "available" if quotes else "unavailable",
        "quotes": quotes,
        "warnings": warnings,
    }
    return context, SourceBlob(
        "yfinance-context",
        "https://ranaroussi.github.io/yfinance/",
        datetime.now(UTC).isoformat(),
        json.dumps(context, sort_keys=True).encode(),
    )
