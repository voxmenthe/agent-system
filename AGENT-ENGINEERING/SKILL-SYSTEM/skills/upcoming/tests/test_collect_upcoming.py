from __future__ import annotations

import json
import sys
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import collect_upcoming as upcoming


class WindowTests(unittest.TestCase):
    def test_half_open_window_tracks_dst_in_display_timezone(self) -> None:
        window = upcoming.Window.build(date(2026, 3, 7), 3, "America/New_York")

        self.assertEqual("2026-03-07T05:00:00Z", window.as_dict()["start_utc"])
        self.assertEqual(
            "2026-03-10T04:00:00Z",
            window.as_dict()["end_utc_exclusive"],
        )
        self.assertTrue(
            window.contains_instant(datetime(2026, 3, 10, 3, 59, tzinfo=UTC))
        )
        self.assertFalse(
            window.contains_instant(datetime(2026, 3, 10, 4, 0, tzinfo=UTC))
        )


class ParserTests(unittest.TestCase):
    def test_ics_parser_unfolds_text_and_converts_timezone(self) -> None:
        payload = b"""BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
UID:bls-1\r
DTSTART;TZID=US-Eastern:20260810T083000\r
SUMMARY:Employment Situa\r
 tion\\, July\r
DTSTAMP:20260809T120000Z\r
SEQUENCE:2\r
STATUS:TENTATIVE\r
URL:https://www.bls.gov/example\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:outside\r
DTSTART;TZID=US-Eastern:20260815T083000\r
SUMMARY:Outside\r
END:VEVENT\r
END:VCALENDAR\r
"""
        window = upcoming.Window.build(date(2026, 8, 10), 5, "America/Los_Angeles")

        events = upcoming.parse_ics_candidates(
            payload,
            window=window,
            provider="bls",
            schedule_url=upcoming.BLS_SCHEDULE_URL,
            default_timezone="America/New_York",
            country="United States",
        )

        self.assertEqual(1, len(events))
        self.assertEqual("Employment Situation, July", events[0]["title"])
        self.assertEqual("2026-08-10", events[0]["local_date"])
        self.assertEqual("05:30", events[0]["local_time"])
        self.assertEqual("2026-08-10T12:30:00Z", events[0]["starts_at_utc"])
        self.assertEqual("tentative", events[0]["schedule_status"])
        self.assertEqual("20260810T083000", events[0]["source_starts_at"])
        self.assertEqual("US-Eastern", events[0]["source_timezone"])
        self.assertEqual("2026-08-09T12:00:00Z", events[0]["last_updated"])
        self.assertEqual(2, events[0]["source_sequence"])

    def test_ics_parser_preserves_cancelled_state(self) -> None:
        payload = b"""BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
DTSTART:20260810T123000Z\r
SUMMARY:Cancelled release\r
STATUS:CANCELLED\r
END:VEVENT\r
END:VCALENDAR\r
"""
        window = upcoming.Window.build(date(2026, 8, 10), 1, "America/New_York")

        events = upcoming.parse_ics_candidates(
            payload,
            window=window,
            provider="bea",
            schedule_url=upcoming.BEA_SCHEDULE_URL,
            default_timezone="America/New_York",
            country="United States",
        )

        self.assertEqual("cancelled", events[0]["schedule_status"])
        self.assertEqual("CANCELLED", events[0]["source_status"])
        self.assertEqual("UTC", events[0]["source_timezone"])

    def test_finnhub_preserves_native_session_and_period(self) -> None:
        payload = json.dumps(
            {
                "earningsCalendar": [
                    {
                        "date": "2026-08-10",
                        "epsEstimate": 1.25,
                        "hour": "bmo",
                        "quarter": 2,
                        "symbol": "BIG",
                        "year": 2026,
                    }
                ]
            }
        ).encode()
        window = upcoming.Window.build(date(2026, 8, 10), 5, "America/New_York")

        batch = upcoming.parse_finnhub_candidates(
            payload,
            window=window,
            expected_from=date(2026, 8, 10),
            expected_through=date(2026, 8, 14),
        )

        self.assertEqual(1, batch.raw_count)
        self.assertEqual(1, len(batch.events))
        event = batch.events[0]
        self.assertEqual("BIG", event["symbol"])
        self.assertEqual("pre-market", event["session"])
        self.assertEqual("bmo", event["source_session"])
        self.assertEqual("Q2 2026", event["period"])
        self.assertEqual("expected", event["schedule_status"])

    def test_finnhub_rejects_rows_outside_requested_partition(self) -> None:
        payload = json.dumps(
            {
                "earningsCalendar": [
                    {"date": "2026-08-15", "hour": "amc", "symbol": "LATE"}
                ]
            }
        ).encode()
        window = upcoming.Window.build(date(2026, 8, 10), 10, "America/New_York")

        with self.assertRaisesRegex(
            upcoming.ProviderFailure, "outside requested partition"
        ):
            upcoming.parse_finnhub_candidates(
                payload,
                window=window,
                expected_from=date(2026, 8, 10),
                expected_through=date(2026, 8, 14),
            )

    def test_finnhub_rejects_unknown_session(self) -> None:
        payload = json.dumps(
            {
                "earningsCalendar": [
                    {"date": "2026-08-10", "hour": "overnight", "symbol": "BIG"}
                ]
            }
        ).encode()
        window = upcoming.Window.build(date(2026, 8, 10), 1, "America/New_York")

        with self.assertRaisesRegex(upcoming.ProviderFailure, "unsupported hour"):
            upcoming.parse_finnhub_candidates(
                payload,
                window=window,
                expected_from=date(2026, 8, 10),
                expected_through=date(2026, 8, 10),
            )

    def test_alpha_vantage_marks_dates_expected_and_preserves_session(self) -> None:
        payload = b"""symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay
BIG,Big Company,2026-08-10,2026-06-30,1.25,USD,post-market
LATE,Later Company,2026-08-20,2026-06-30,0.50,USD,pre-market
"""
        window = upcoming.Window.build(date(2026, 8, 10), 5, "America/New_York")

        events = upcoming.parse_alpha_vantage_candidates(payload, window=window)

        self.assertEqual(1, len(events))
        self.assertEqual("BIG", events[0]["symbol"])
        self.assertEqual("expected", events[0]["schedule_status"])
        self.assertEqual("session", events[0]["time_precision"])
        self.assertEqual("post-market", events[0]["session"])
        self.assertEqual("post-market", events[0]["source_session"])
        self.assertIsNone(events[0]["starts_at_utc"])

    def test_alpha_vantage_rejects_blank_company_identity(self) -> None:
        payload = b"""symbol,name,reportDate,timeOfTheDay
,Missing Symbol,2026-08-10,pre-market
"""
        window = upcoming.Window.build(date(2026, 8, 10), 1, "America/New_York")

        with self.assertRaisesRegex(upcoming.ProviderFailure, "missing name or symbol"):
            upcoming.parse_alpha_vantage_candidates(payload, window=window)

    def test_alpha_vantage_allows_missing_optional_session_column(self) -> None:
        payload = b"""symbol,name,reportDate
BIG,Big Company,2026-08-10
"""
        window = upcoming.Window.build(date(2026, 8, 10), 1, "America/New_York")

        events = upcoming.parse_alpha_vantage_candidates(payload, window=window)

        self.assertEqual("date", events[0]["time_precision"])
        self.assertIsNone(events[0]["session"])

    def test_alpha_vantage_rejects_non_csv_error_payload(self) -> None:
        payload = b'{"Information":"rate limit reached"}'
        window = upcoming.Window.build(date(2026, 8, 10), 1, "America/New_York")

        with self.assertRaisesRegex(upcoming.ProviderFailure, "non-CSV response"):
            upcoming.parse_alpha_vantage_candidates(payload, window=window)

    def test_fred_filters_allowlist_without_making_up_time(self) -> None:
        payload = json.dumps(
            {
                "count": 3,
                "offset": 0,
                "limit": 1000,
                "release_dates": [
                    {
                        "release_id": 10,
                        "release_name": "Consumer Price Index",
                        "date": "2026-08-12",
                    },
                    {
                        "release_id": 101,
                        "release_name": "FOMC Press Release",
                        "date": "2026-08-12",
                    },
                    {
                        "release_id": 180,
                        "release_name": "Unemployment Insurance Weekly Claims Report",
                        "date": "2026-08-15",
                    },
                ],
            }
        ).encode()
        window = upcoming.Window.build(date(2026, 8, 10), 7, "America/New_York")

        page = upcoming.parse_fred_release_dates_candidates(payload, window=window)

        self.assertEqual(3, page.total_count)
        self.assertEqual(1, len(page.events))
        event = page.events[0]
        self.assertEqual("Consumer Price Index", event["title"])
        self.assertEqual("date", event["time_precision"])
        self.assertIsNone(event["local_time"])
        self.assertIsNone(event["starts_at_utc"])

    def test_fred_fails_if_an_allowlisted_release_name_drifts(self) -> None:
        payload = json.dumps(
            {
                "count": 1,
                "offset": 0,
                "limit": 1000,
                "release_dates": [
                    {
                        "release_id": 10,
                        "release_name": "Renamed CPI Feed",
                        "date": "2026-08-12",
                    }
                ],
            }
        ).encode()
        window = upcoming.Window.build(date(2026, 8, 10), 5, "America/New_York")

        with self.assertRaisesRegex(upcoming.ProviderFailure, "release name changed"):
            upcoming.parse_fred_release_dates_candidates(payload, window=window)


class RequestPolicyTests(unittest.TestCase):
    def test_rejects_unallowlisted_endpoint_and_query_parameter(self) -> None:
        valid_query = (
            ("function", "EARNINGS_CALENDAR"),
            ("horizon", "3month"),
            ("apikey", "secret"),
        )
        with self.assertRaisesRegex(
            upcoming.ProviderFailure, "endpoint is not allowlisted"
        ):
            upcoming.validate_request(
                upcoming.ProviderRequest(
                    provider="alpha-vantage",
                    endpoint="https://example.com/query",
                    query=valid_query,
                    accept="*/*",
                )
            )
        with self.assertRaisesRegex(upcoming.ProviderFailure, "query parameter"):
            upcoming.validate_request(
                upcoming.ProviderRequest(
                    provider="alpha-vantage",
                    endpoint=upcoming.ALPHA_VANTAGE_ENDPOINT,
                    query=valid_query + (("premium", "true"),),
                    accept="*/*",
                )
            )

    def test_request_repr_does_not_expose_query_or_header_credentials(self) -> None:
        request = upcoming.ProviderRequest(
            provider="finnhub",
            endpoint=upcoming.FINNHUB_EARNINGS_ENDPOINT,
            query=(("from", "2026-08-10"), ("to", "2026-08-14")),
            headers=(("X-Finnhub-Token", "top-secret"),),
            accept="application/json",
        )

        rendered = repr(request)

        self.assertNotIn("top-secret", rendered)
        self.assertNotIn("2026-08-10", rendered)

    def test_redirect_handler_refuses_redirects(self) -> None:
        handler = upcoming._NoRedirectHandler()

        redirected = handler.redirect_request(None, None, 302, "Found", {}, "https://x")

        self.assertIsNone(redirected)

    def test_transport_error_does_not_expose_credential_bearing_url(self) -> None:
        class FailingOpener:
            def open(self, request, timeout):  # type: ignore[no-untyped-def]
                del request, timeout
                raise HTTPError(
                    "https://www.alphavantage.co/query?apikey=top-secret",
                    403,
                    "Forbidden",
                    {},
                    None,
                )

        request = upcoming.ProviderRequest(
            provider="alpha-vantage",
            endpoint=upcoming.ALPHA_VANTAGE_ENDPOINT,
            query=(
                ("function", "EARNINGS_CALENDAR"),
                ("horizon", "3month"),
                ("apikey", "top-secret"),
            ),
            accept="*/*",
        )

        with patch.object(upcoming, "build_opener", return_value=FailingOpener()):
            with self.assertRaises(upcoming.ProviderFailure) as caught:
                upcoming.fetch_bytes(request)

        self.assertEqual("HTTP 403", str(caught.exception))
        self.assertNotIn("top-secret", str(caught.exception))


class CollectionTests(unittest.TestCase):
    def test_partial_failure_and_missing_keys_remain_visible(self) -> None:
        empty_ics = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

        requests: list[upcoming.ProviderRequest] = []

        def fake_fetch(request: upcoming.ProviderRequest) -> bytes:
            requests.append(request)
            if request.endpoint == upcoming.BEA_ICS_URL:
                return empty_ics
            self.fail(f"unexpected fetch: {request.provider}")

        output, exit_code = upcoming.collect(
            window=upcoming.Window.build(date(2026, 8, 10), 5, "America/New_York"),
            skip_earnings=False,
            environment={"TRADING_ECONOMICS_API_KEY": "must-never-be-used"},
            fetcher=fake_fetch,
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("candidate-set-only", output["coverage"]["claim"])
        status = {
            item["provider"]: item["status"] for item in output["coverage"]["providers"]
        }
        self.assertEqual("manual_download_required", status["bls"])
        self.assertEqual("ok", status["bea"])
        self.assertNotIn("trading-economics", status)
        self.assertEqual("skipped_not_configured", status["finnhub"])
        self.assertEqual("skipped_not_configured", status["alpha-vantage"])
        self.assertEqual("skipped_by_default", status["fred"])
        self.assertEqual(["bea"], [request.provider for request in requests])
        self.assertEqual(
            "manual-collection-required",
            output["coverage"]["automation_status"],
        )
        self.assertEqual(
            "manual-collection-required",
            output["coverage"]["lanes"]["macro"]["status"],
        )
        self.assertEqual(
            "manual-collection-required",
            output["coverage"]["lanes"]["earnings"]["status"],
        )
        self.assertTrue(output["coverage"]["next_actions"])

    def test_all_attempted_providers_failing_returns_nonzero(self) -> None:
        def fail_fetch(request: upcoming.ProviderRequest) -> bytes:
            del request
            raise upcoming.ProviderFailure("network error (TimeoutError)")

        output, exit_code = upcoming.collect(
            window=upcoming.Window.build(date(2026, 8, 10), 5, "America/New_York"),
            skip_earnings=True,
            environment={},
            fetcher=fail_fetch,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual([], output["events"])

    def test_finnhub_primary_partitions_and_alpha_accept(self) -> None:
        requests: list[upcoming.ProviderRequest] = []
        empty_ics = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

        def fake_fetch(request: upcoming.ProviderRequest) -> bytes:
            requests.append(request)
            if request.provider == "bea":
                return empty_ics
            if request.provider == "finnhub":
                query = dict(request.query)
                symbol = "FIRST" if query["from"] == "2026-08-10" else "SECOND"
                return json.dumps(
                    {
                        "earningsCalendar": [
                            {
                                "date": query["from"],
                                "hour": "amc",
                                "symbol": symbol,
                            }
                        ]
                    }
                ).encode()
            if request.provider == "alpha-vantage":
                return b"symbol,name,reportDate\nFIRST,First Co,2026-08-10\n"
            self.fail(f"unexpected provider: {request.provider}")

        output, exit_code = upcoming.collect(
            window=upcoming.Window.build(date(2026, 8, 10), 8, "America/New_York"),
            skip_earnings=False,
            environment={
                "FINNHUB_API_KEY": "finn-secret",
                "ALPHAVANTAGE_API_KEY": "alpha-secret",
            },
            fetcher=fake_fetch,
        )

        self.assertEqual(0, exit_code)
        finnhub_requests = [r for r in requests if r.provider == "finnhub"]
        self.assertEqual(2, len(finnhub_requests))
        self.assertEqual("2026-08-14", dict(finnhub_requests[0].query)["to"])
        self.assertEqual("2026-08-17", dict(finnhub_requests[1].query)["to"])
        self.assertEqual(
            (("X-Finnhub-Token", "finn-secret"),),
            finnhub_requests[0].headers,
        )
        self.assertNotIn("finn-secret", finnhub_requests[0].endpoint)
        alpha_request = next(r for r in requests if r.provider == "alpha-vantage")
        self.assertEqual("*/*", alpha_request.accept)
        self.assertEqual("alpha-secret", dict(alpha_request.query)["apikey"])
        self.assertNotIn("alpha-secret", alpha_request.endpoint)
        self.assertEqual(
            "candidate-set-available",
            output["coverage"]["lanes"]["earnings"]["status"],
        )

    def test_finnhub_exact_cap_is_reported_as_a_warning(self) -> None:
        empty_ics = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

        def fake_fetch(request: upcoming.ProviderRequest) -> bytes:
            if request.provider == "bea":
                return empty_ics
            if request.provider == "finnhub":
                rows = [
                    {
                        "date": "2026-08-10",
                        "hour": "",
                        "symbol": f"S{index}",
                    }
                    for index in range(1500)
                ]
                return json.dumps({"earningsCalendar": rows}).encode()
            self.fail(f"unexpected provider: {request.provider}")

        output, _ = upcoming.collect(
            window=upcoming.Window.build(date(2026, 8, 10), 1, "America/New_York"),
            skip_earnings=False,
            environment={"FINNHUB_API_KEY": "finn-secret"},
            fetcher=fake_fetch,
        )

        report = next(
            item
            for item in output["coverage"]["providers"]
            if item["provider"] == "finnhub"
        )
        self.assertEqual("ok", report["status"])
        self.assertRegex(report["warnings"][0], "1,500")

    def test_fred_is_opt_in_and_always_requests_future_release_dates(self) -> None:
        requests: list[upcoming.ProviderRequest] = []
        empty_ics = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

        def fake_fetch(request: upcoming.ProviderRequest) -> bytes:
            requests.append(request)
            if request.provider == "bea":
                return empty_ics
            if request.provider == "fred":
                return json.dumps(
                    {"count": 0, "offset": 0, "limit": 1000, "release_dates": []}
                ).encode()
            self.fail(f"unexpected provider: {request.provider}")

        output, _ = upcoming.collect(
            window=upcoming.Window.build(date(2026, 8, 10), 5, "America/New_York"),
            skip_earnings=True,
            use_fred=True,
            environment={"FRED_API_KEY": "fred-secret"},
            fetcher=fake_fetch,
        )

        fred_request = next(r for r in requests if r.provider == "fred")
        query = dict(fred_request.query)
        self.assertEqual("true", query["include_release_dates_with_no_data"])
        self.assertEqual("json", query["file_type"])
        self.assertEqual("fred-secret", query["api_key"])
        self.assertNotIn("fred-secret", fred_request.endpoint)
        status = {
            item["provider"]: item["status"] for item in output["coverage"]["providers"]
        }
        self.assertEqual("ok", status["fred"])

    def test_foreign_issuer_dates_carry_their_zone_and_listed_issuers_are_named(self) -> None:
        # Su§9 (10-11): feeds gave TSMC Oct. 15 and ASML Oct. 14, issuer-local dates that were the previous
        # evening in PT; LVMH, reporting that Monday, was in neither feed.
        empty_ics = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

        def fake_fetch(request: upcoming.ProviderRequest) -> bytes:
            if request.provider == "bea":
                return empty_ics
            rows = [{"date": d, "hour": "", "symbol": s}
                    for d, s in (("2026-10-15", "TSM"), ("2026-10-14", "ASML"), ("2026-10-14", "JPM"))]
            query = dict(request.query)
            rows = [row for row in rows if query["from"] <= row["date"] <= query["to"]]
            return json.dumps({"earningsCalendar": rows}).encode()

        def run(zone: str) -> dict[str, object]:
            output, _ = upcoming.collect(
                window=upcoming.Window.build(date(2026, 10, 12), 5, zone),
                skip_earnings=False,
                environment={"FINNHUB_API_KEY": "finn-secret"},
                fetcher=fake_fetch,
            )
            return output

        output = run("America/Los_Angeles")
        zones = {e["symbol"]: e["source_timezone"] for e in output["events"]}
        self.assertEqual(
            {"TSM": "Asia/Taipei", "ASML": "Europe/Amsterdam", "JPM": None}, zones
        )
        actions = {a["source"]: a for a in output["coverage"]["next_actions"]}
        early = actions["foreign issuer investor relations"]
        self.assertTrue(early["required_for_claim"])
        self.assertIn(
            "may fall on the previous America/Los_Angeles date: "
            "ASML 2026-10-14 (Europe/Amsterdam); TSM 2026-10-15 (Asia/Taipei)",
            early["reason"],
        )
        listed = actions["foreign read-through issuers (references/foreign-issuers.tsv)"]
        self.assertIn("LVMH Moët Hennessy Louis Vuitton (LVMUY) https://www.lvmh.com/", listed["reason"])
        self.assertNotIn("(TSM)", listed["reason"])
        self.assertEqual(
            "https://www.bls.gov/schedule/2026/10_sched.htm",
            actions["BLS release calendar"]["fallback_source"],
        )
        # Tokyo is ahead of Taipei and Amsterdam: no previous-date caveat.
        tokyo = {a["source"] for a in run("Asia/Tokyo")["coverage"]["next_actions"]}
        self.assertNotIn("foreign issuer investor relations", tokyo)

    def test_strict_mode_returns_two_when_a_requested_lane_is_unresolved(self) -> None:
        empty_ics = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

        def fake_fetch(request: upcoming.ProviderRequest) -> bytes:
            if request.provider == "bea":
                return empty_ics
            self.fail(f"unexpected provider: {request.provider}")

        _, exit_code = upcoming.collect(
            window=upcoming.Window.build(date(2026, 8, 10), 1, "America/New_York"),
            skip_earnings=False,
            strict=True,
            environment={},
            fetcher=fake_fetch,
        )

        self.assertEqual(2, exit_code)

    def test_strict_mode_returns_two_when_an_official_source_is_missing(self) -> None:
        # 10-11: other providers' rows filled the macro lane, so --strict passed while BLS was never loaded.
        bea_ics = b"""BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
DTSTART;TZID=US-Eastern:20260810T083000\r
SUMMARY:Personal Income and Outlays\r
END:VEVENT\r
END:VCALENDAR\r
"""

        def fake_fetch(request: upcoming.ProviderRequest) -> bytes:
            if request.provider == "bea":
                return bea_ics
            self.fail(f"unexpected provider: {request.provider}")

        window = upcoming.Window.build(date(2026, 8, 10), 1, "America/New_York")
        output, exit_code = upcoming.collect(
            window=window, skip_earnings=True, strict=True, environment={}, fetcher=fake_fetch
        )

        self.assertEqual(
            "candidate-set-available", output["coverage"]["lanes"]["macro"]["status"]
        )
        self.assertEqual(2, exit_code)
        _, exit_code = upcoming.collect(
            window=window,
            skip_earnings=True,
            strict=True,
            bls_ics_payload=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
            environment={},
            fetcher=fake_fetch,
        )
        self.assertEqual(0, exit_code)

    def test_cli_has_no_paid_provider_options(self) -> None:
        help_text = upcoming.build_parser().format_help()

        self.assertNotIn("Trading Economics", help_text)
        self.assertNotIn("--countries", help_text)
        self.assertNotIn("--macro-importance", help_text)
        self.assertIn("--use-fred", help_text)
        self.assertIn("--strict", help_text)


if __name__ == "__main__":
    unittest.main()
