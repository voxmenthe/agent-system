from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AutoPolicyDecisionTests(unittest.TestCase):
    def test_auto_policy_activates_live_dogfooding(self) -> None:
        policy = json.loads(
            (ROOT / "policy/auto-attention-v1.json").read_text(encoding="utf-8")
        )

        self.assertIs(True, policy["automatic_delivery"])
        self.assertEqual("dogfood-active", policy["status"])
        self.assertNotIn("promotion_requirements", policy)


if __name__ == "__main__":
    unittest.main()
