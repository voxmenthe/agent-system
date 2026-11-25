from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from options_app.spx_report_store import SourceBlob
from spx_sources import CBOE_URL, OCC_URL, build_snapshot, fetch_yahoo_context, parse_oi
from spx_analytics import (
    analyze,
    black_price,
    build_surface,
    find_roots,
    gamma_matrix,
    implied_total_vol,
    outcome_scenarios,
    settlement_time,
)

FIXTURES = Path(__file__).parent / "fixtures"


def snapshot() -> dict:
    stamp = "2026-09-17T07:30:00+00:00"
    return build_snapshot(
        SourceBlob("marks", CBOE_URL, stamp, (FIXTURES / "marks.csv").read_bytes()),
        SourceBlob("oi", OCC_URL, stamp, (FIXTURES / "occ.txt").read_bytes()),
    )


class SPXContracts(unittest.TestCase):
    def test_zero_underflow_tails_do_not_create_gamma_flips(self) -> None:
        grid = np.arange(6, dtype=float)
        self.assertEqual(find_roots(grid, np.array([0, 0, 1, 2, 1, 0.0])), [])
        self.assertEqual(find_roots(grid[:3], np.array([1, 0, -1.0])), [1.0])

    def test_real_closing_quotes_reproduce_six_printed_delta_strikes(self) -> None:
        result = analyze(snapshot())
        for band, expected in zip(
            result["delta_bands"][2:], [(7441, 7635), (7466, 7619), (7499, 7597)]
        ):
            self.assertLess(abs(band["put"] - expected[0]), 2)
            self.assertLess(abs(band["call"] - expected[1]), 2)
        self.assertAlmostEqual(result["forward"], 7553.85, places=2)
        self.assertTrue(56 < result["straddle_points"] < 59)

    def test_gamma_matches_independent_price_finite_difference(self) -> None:
        rows, _ = build_surface(snapshot())
        row = min(rows, key=lambda r: abs(r.contract.strike - r.forward))
        spot = 7553.33
        h = 0.1

        def price(s: float) -> float:
            return black_price(
                row.forward * s / spot,
                row.contract.strike,
                row.a,
                row.side,
                row.discount,
            )

        finite = (price(spot + h) - 2 * price(spot) + price(spot - h)) / h**2
        calculated = gamma_matrix([row], np.array([spot]), spot)[0, 0]
        self.assertAlmostEqual(finite, calculated, places=6)
        self.assertAlmostEqual(
            implied_total_vol(
                row.forward, row.contract.strike, price(spot), row.side, row.discount
            ),
            row.a,
            places=8,
        )

    def test_model_bounds_have_no_fabricated_flip(self) -> None:
        result = analyze(snapshot())
        for p in result["profiles"]:
            if p["model"] == "all_short_bound":
                self.assertLess(p["gex_bn_per_1pct"], 0)
                self.assertEqual(p["roots"], [])
            if p["model"] == "all_long_bound":
                self.assertGreater(p["gex_bn_per_1pct"], 0)
                self.assertEqual(p["roots"], [])
        base = next(
            p
            for p in result["profiles"]
            if p["scope"] == "target" and p["model"] == "calls_long_puts_short"
        )
        self.assertTrue(7570 < base["roots"][0] < 7580)

    def test_overnight_envelope_expands_for_large_gap(self) -> None:
        distribution = outcome_scenarios(7554, 0.0095, 7553, 8160)
        self.assertGreater(distribution["grid"][-1], 8160)
        for curve in distribution["densities"]:
            area = np.trapezoid(curve["density"], distribution["grid"])
            self.assertTrue(0.995 < area < 1.001)
        ref = distribution["scenarios"][-1]
        self.assertLess(ref["low_3sigma"], 8160)
        self.assertGreater(ref["high_3sigma"], 8160)

    def test_early_close_and_am_settlement_are_not_both_four_pm(self) -> None:
        self.assertEqual(settlement_time("SPXW", "2026-11-27").hour, 18)
        self.assertEqual(settlement_time("SPX", "2026-11-27").hour, 14)
        self.assertEqual(settlement_time("SPX", "2026-11-27").minute, 30)

    def test_unknown_oi_date_and_missing_contract_are_not_invented(self) -> None:
        data = snapshot()
        self.assertIsNone(data["oi_asof"])
        first = data["contracts"][0]
        first["call_oi"] = first["put_oi"] = None
        self.assertIsNone(first["call_oi"])
        analyze(data)
        with self.assertRaises(ValueError):
            parse_oi(b"<html>Maintenance page</html>")
        raw = (FIXTURES / "occ.txt").read_bytes()
        with self.assertRaises(ValueError):
            parse_oi(raw + raw)

    def test_optional_yahoo_failure_preserves_core_analysis(self) -> None:
        from yfinance.exceptions import YFRateLimitError

        with patch("yfinance.Ticker", side_effect=YFRateLimitError()):
            context, source = fetch_yahoo_context()
        self.assertEqual(context["status"], "unavailable")
        self.assertEqual(len(context["warnings"]), 3)
        self.assertGreater(len(source.content), 0)
        data = snapshot()
        data["context"] = context
        self.assertTrue(analyze(data)["profiles"])

    def test_bad_black_inputs_fail_loudly(self) -> None:
        for price in (0, -1, float("nan"), 10000):
            with self.assertRaises(ValueError):
                implied_total_vol(7553, 7550, price, "call")


if __name__ == "__main__":
    unittest.main()
