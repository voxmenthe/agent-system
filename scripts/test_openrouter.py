import argparse
import unittest
from datetime import datetime, timezone

from scripts import openrouter

OCT_7 = datetime(2026, 10, 7, tzinfo=timezone.utc).timestamp()
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc).timestamp()


def _model(model_id: str, created: float, price: str = "0.000001") -> openrouter.Model:
    return {
        "id": model_id,
        "name": model_id,
        "created": created,
        "pricing": {"prompt": price, "completion": price},
    }


class ParseSinceTest(unittest.TestCase):
    def test_date_means_utc_midnight(self) -> None:
        self.assertEqual(openrouter.parse_since("2026-10-07", NOW), OCT_7)

    def test_number_means_past_n_days(self) -> None:
        self.assertEqual(openrouter.parse_since("30", NOW), NOW - 30 * 86_400)

    def test_rejects_other_values(self) -> None:
        for value in ("0", "-5", "abc", "2026-13-01", "10/07/2026"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                openrouter.parse_since(value, NOW)


class SelectModelsTest(unittest.TestCase):
    def test_since_is_inclusive_and_combines_with_other_filters(self) -> None:
        models = [
            _model("acme/before", OCT_7 - 1, price="0"),
            _model("acme/at-midnight", OCT_7, price="0"),
            _model("acme/later", OCT_7 + 86_400, price="0"),
            _model("acme/paid", OCT_7 + 86_400),
            _model("other/later", OCT_7 + 86_400, price="0"),
        ]
        selected = openrouter.select_models(models, ["acme"], True, OCT_7)
        self.assertEqual([m["id"] for m in selected], ["acme/later", "acme/at-midnight"])


def _key(limit: float | None, remaining: float | None) -> dict:
    return {
        "limit": limit,
        "limit_remaining": remaining,
        "limit_reset": None,
        "usage": 0.5,
        "usage_daily": 0,
        "usage_weekly": 0,
        "usage_monthly": 0.5,
        "expires_at": None,
    }


class KeySummaryTest(unittest.TestCase):
    def _spendable(self, key: dict, credits: dict | None) -> str:
        return openrouter.format_key_summary(key, credits).splitlines()[0]

    def test_spendable_is_the_smaller_of_key_limit_and_account_balance(self) -> None:
        cases = [
            (_key(50, 49.5), {"total_credits": 100, "total_usage": 10}, "$49.50", "key limit"),
            (_key(50, 49.5), {"total_credits": 100, "total_usage": 95}, "$5.00", "account balance"),
            (_key(None, None), {"total_credits": 100, "total_usage": 95}, "$5.00", "account balance"),
        ]
        for key, credits, amount, cap in cases:
            with self.subTest(amount=amount, cap=cap):
                line = self._spendable(key, credits)
                self.assertIn(amount, line)
                self.assertIn(f"{cap} is the tighter cap", line)

    def test_unreadable_account_balance_is_flagged_not_assumed(self) -> None:
        self.assertIn("may be lower", self._spendable(_key(50, 49.5), None))
        self.assertIn("unknown", self._spendable(_key(None, None), None))

    def test_sub_cent_amounts_are_not_rounded_away(self) -> None:
        line = self._spendable(_key(50, 49.99863273), None)
        self.assertIn("$49.9986", line)


if __name__ == "__main__":
    unittest.main()
