"""catchup skill contract, registry record and guide entry; no model calls."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "catchup"


class CatchupSkillTests(unittest.TestCase):
    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "catchup"), r"^sha256:")
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("disable-model-invocation: true", (SKILL_ROOT / "SKILL.md").read_text())
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$catchup", metadata)

    def test_answer_order_and_boundary_skips(self) -> None:
        body = (SKILL_ROOT / "SKILL.md").read_text()
        headings = ["**Changed.**", "**Needs you.**", "**Running.**", "**Not checked.**"]
        self.assertEqual(sorted(headings, key=body.index), headings)
        for skipped in ("<task-notification>", "Another Claude session sent a message", "/compact"):
            self.assertIn(skipped, body)

    def test_registry_record_and_guide_entry(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["catchup"]
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("skills/catchup", record["source"])
        self.assertEqual(["delegate"], record["dependencies"])
        self.assertEqual("read-only", record["effect_ceiling"])
        self.assertEqual(["~/.agents/skills/catchup"], record["install_targets"])
        self.assertIn("[`catchup`](skills/catchup/SKILL.md)", (ROOT / "USER-GUIDE.md").read_text())


if __name__ == "__main__":
    unittest.main()
