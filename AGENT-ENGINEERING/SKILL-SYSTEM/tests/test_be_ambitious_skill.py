"""be-ambitious skill contract, registry record, provenance, guide entry and hand-offs; no model calls."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "be-ambitious"
BOUNDARY = re.compile(r"> (Use when the user invokes `\$be-ambitious`.*?)\n\n", re.S)
# Felix Rieseberg's prompt as RoboNuggets' SKILL.md quotes it at dc116a3.
DEPTH_PROMPT = (
    "I want a deeper version of this task, not a bigger one. Before rewriting it: (1) say what a top"
    " professional in this field would do here that I'm not asking for; (2) name the rawest material they"
    " would start from instead of what has already been digested for me; (3) name the specific methods and"
    " tools they would use; (4) say what, other than you or me, would show the result is right. Then"
    " rewrite my prompt to ask for exactly that."
)


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("> ", " "))


class BeAmbitiousSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (SKILL_ROOT / "SKILL.md").read_text()
        self.examples = (SKILL_ROOT / "references/examples.md").read_text()
        self.record = json.loads((ROOT / "registry.json").read_text())["skills"]["be-ambitious"]

    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "be-ambitious"), r"^sha256:")
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("disable-model-invocation: true", self.skill)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$be-ambitious", metadata)

    def test_registry_record(self) -> None:
        self.assertEqual("custom", self.record["ownership"])
        self.assertEqual("skills/be-ambitious", self.record["source"])
        self.assertEqual([], self.record["dependencies"])
        self.assertEqual("local-write", self.record["effect_ceiling"])
        self.assertEqual("experimental", self.record["lifecycle"])
        self.assertEqual(["~/.agents/skills/be-ambitious"], self.record["install_targets"])
        self.assertEqual("dc116a3ebd8cf772e4d0930626f67369bd60399d", self.record["provenance"]["reference_revision"])

    def test_notice_pins_the_registry_revision(self) -> None:
        notice = (SKILL_ROOT / "NOTICE.md").read_text()
        license_text = (SKILL_ROOT / "LICENSE").read_text()
        self.assertIn(self.record["provenance"]["reference_revision"], notice)
        self.assertTrue(license_text.startswith("MIT License"))
        self.assertIn("Copyright (c) 2026 RoboNuggets", license_text)

    def test_user_guide_carries_the_boundary_sentence(self) -> None:
        boundary = BOUNDARY.search(self.skill)
        self.assertIsNotNone(boundary)
        guide = flat((ROOT / "USER-GUIDE.md").read_text())
        self.assertIn(flat(boundary.group(1)).strip(), guide)
        self.assertIn("[`be-ambitious`](skills/be-ambitious/SKILL.md)", guide)

    def test_depth_prompt_is_verbatim(self) -> None:
        self.assertIn(DEPTH_PROMPT, flat(self.skill))

    def test_handoff_skills_exist(self) -> None:
        table = self.skill.split("\n## With other skills\n", 1)[1].split("\n## ", 1)[0]
        rows = [line.split("|") for line in table.splitlines() if line.startswith("| ") and "---" not in line]
        named = {name for row in rows[1:] for name in re.findall(r"`([a-z0-9-]+)`", row[2])}
        prompts = re.findall(r"^\s*\d+\. `(.*)`$", self.examples, re.M)
        self.assertEqual(12, len(prompts))
        named |= {name for prompt in prompts for name in re.findall(r"\$([a-z][a-z0-9-]*)", prompt)}
        self.assertGreaterEqual(len(named), 13)
        for name in sorted(named):
            with self.subTest(name=name):
                self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
