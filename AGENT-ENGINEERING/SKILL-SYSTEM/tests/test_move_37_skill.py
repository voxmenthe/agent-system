"""move-37 skill contract, registry record, provenance, and guide entry; no model calls."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "move-37"
REFERENCE_REVISION = "6e6ffc686d7e9d5a181fba61ef7c13af294627ca"


class Move37SkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (SKILL_ROOT / "SKILL.md").read_text()
        self.record = json.loads((ROOT / "registry.json").read_text())["skills"]["move-37"]

    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "move-37"), r"^sha256:")
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("disable-model-invocation: true", self.skill)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$move-37", metadata)

    def test_registry_record(self) -> None:
        self.assertEqual("custom", self.record["ownership"])
        self.assertEqual("skills/move-37", self.record["source"])
        self.assertEqual([], self.record["dependencies"])
        self.assertEqual("read-only", self.record["effect_ceiling"])
        self.assertEqual("experimental", self.record["lifecycle"])
        self.assertEqual(["~/.agents/skills/move-37"], self.record["install_targets"])
        self.assertEqual("explicit-only-move-37-reframing", self.record["evaluation_profile"])
        self.assertEqual(REFERENCE_REVISION, self.record["provenance"]["reference_revision"])

    def test_notice_pins_the_registry_revision_and_license(self) -> None:
        notice = (SKILL_ROOT / "NOTICE.md").read_text()
        license_text = (SKILL_ROOT / "LICENSE").read_text()
        self.assertIn(REFERENCE_REVISION, notice)
        self.assertIn("https://github.com/DannyMac180/skills", notice)
        self.assertTrue(license_text.startswith("MIT License"))
        self.assertIn("Copyright (c) 2026 Dan McAteer", license_text)

    def test_reframe_contract_is_preserved(self) -> None:
        ordered = [
            "### 1. Restate the real problem (not the proposed solution)",
            "### 2. Surface 2–3 hidden assumptions",
            "### 3. Propose three structurally distinct moves",
            "### 4. Recommend and stop",
        ]
        positions = [self.skill.index(item) for item in ordered]
        self.assertEqual(positions, sorted(positions))
        for move in (
            "**The Direct Move (Baseline)**",
            "**The Upstream / Elimination Move**",
            "**Move 37 (The Non-Obvious Move)**",
        ):
            self.assertIn(move, self.skill)
        for field in (
            "**Core move:**",
            "**Assumption it breaks:**",
            "**Why it wins:**",
            "**Biggest risk:**",
            "**First cheap test:**",
        ):
            self.assertIn(field, self.skill)
        self.assertIn(
            "Stop there. Ask which move the user wants to pursue; do not write code or\n"
            "start executing until they choose.",
            self.skill,
        )

    def test_user_guide_carries_the_explicit_boundary(self) -> None:
        guide = (ROOT / "USER-GUIDE.md").read_text()
        self.assertIn("[`move-37`](skills/move-37/SKILL.md)", guide)
        self.assertIn("Explicit-only and read-only. It recommends and stops", guide)
        self.assertIn("`$move-37`", guide)


if __name__ == "__main__":
    unittest.main()
