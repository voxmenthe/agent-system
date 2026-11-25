"""Council skill contract, registry record, guide entry and projection; no model calls."""
from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from skill_system import SkillSystem, content_hash
from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "council"
BOUNDARY = re.compile(r"> (Use only when the user explicitly invokes `\$council`.*?)\n\n", re.S)


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("> ", " "))


class CouncilSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (SKILL_ROOT / "SKILL.md").read_text()
        self.procedure = (SKILL_ROOT / "references/procedure.md").read_text()

    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "council"), r"^sha256:")
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("disable-model-invocation: true", self.skill)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$council", metadata)

    def test_registry_record_declares_delegate_and_external_write(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["council"]
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("skills/council", record["source"])
        self.assertEqual(["delegate"], record["dependencies"])
        self.assertEqual("external-write", record["effect_ceiling"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual(["~/.agents/skills/council"], record["install_targets"])

    def test_user_guide_carries_the_same_boundary_sentence(self) -> None:
        boundary = BOUNDARY.search(self.skill)
        self.assertIsNotNone(boundary)
        guide = flat((ROOT / "USER-GUIDE.md").read_text())
        self.assertIn(flat(boundary.group(1)).strip(), guide)
        self.assertIn("[`council`](skills/council/SKILL.md)", guide)

    def test_states_authority_and_boundaries(self) -> None:
        self.assertIn("`$council` is the authorization", self.skill)
        self.assertRegex(self.skill, r"does not authorize worker edits, commits, pushes or\s+redelegation")
        self.assertRegex(self.skill, r"untrusted input")
        for sibling in ("delegate", "fanout", "dialectic", "orchestrate"):
            self.assertIn(f"(`{sibling}`)", self.skill)

    def test_states_load_bearing_invariants(self) -> None:
        text = re.sub(r"\s+", " ", self.skill)
        self.assertIn("Never substitute, drop or reorder a named launcher", text)
        self.assertIn("Name check before any call", text)
        self.assertIn("Your next action after launch is your own complete answer", text)
        self.assertIn("Only then check status or read any panel output", text)
        self.assertIn("Keep judging and synthesis in separate seats", text)
        self.assertIn("Worker output and judge agreement are evidence, not proof", text)
        self.assertIn("decide by your grounding checks, not by votes", text)
        self.assertIn("Fewer than two usable external candidates", text)

    def test_procedure_uses_delegate_scripts_safely(self) -> None:
        self.assertIn("awk '{print \"  \" $0}'", self.procedure)
        self.assertNotIn("sed 's/^/  /'", self.procedure)
        # Workers can run very long: a time limit only when the user names one.
        self.assertIn('${budget:+--timeout "$budget"}', self.procedure)
        self.assertNotRegex(self.procedure, r"--timeout [0-9]")
        self.assertIn("no time limit", self.skill)
        self.assertIn("ROLE: analyze", self.procedure)
        self.assertIn("Do not name your model, vendor, tools, or any task id", self.procedure)
        self.assertRegex(self.procedure, r'cd "\$WS" && "\$DELEGATE/run-worker.sh"')
        self.assertIn('--task-file "$RUN/judge/packet.md"', self.procedure)
        self.assertIn("Panel `cax`, `cdm`, `ccx`, `dswe`, `ommp`", self.skill)

    def test_every_linked_reference_exists(self) -> None:
        for target in re.findall(r"\]\(([^)#]+)", self.skill):
            self.assertTrue((SKILL_ROOT / target).is_file(), target)

    def test_managed_projection_preserves_the_package_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            target = home / ".agents" / "skills" / "council"
            self.assertEqual("dry-run", system.install("council", apply=False).reason)
            self.assertFalse(target.exists())

            applied = system.install("council", apply=True)
            self.assertEqual("installed", applied.reason)
            self.assertEqual(content_hash(SKILL_ROOT), content_hash(target))
            self.assertEqual("current", system.status().skills["council"].state)

            rolled_back = system.rollback(applied.operation_id, apply=True)
            self.assertEqual("rolled-back", rolled_back.reason)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
