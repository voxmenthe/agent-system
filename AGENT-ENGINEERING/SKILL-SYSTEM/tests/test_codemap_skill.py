from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from skill_system import SkillSystem, content_hash
from skill_system.model import validate_skill_tree


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "codemap"


class CodemapPackageTests(unittest.TestCase):
    def test_package_is_explicit_only_and_writes_local_documentation(self) -> None:
        validate_skill_tree(SKILL, "codemap")
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        record = registry["codemap"]
        self.assertEqual("skills/codemap", record["source"])
        self.assertEqual(["~/.agents/skills/codemap"], record["install_targets"])
        self.assertEqual("local-write", record["effect_ceiling"])
        self.assertEqual([], record["dependencies"])

        frontmatter = (SKILL / "SKILL.md").read_text().split("---", 2)[1]
        metadata = (SKILL / "agents" / "openai.yaml").read_text()
        self.assertRegex(frontmatter, r"(?m)^disable-model-invocation:\s*true\s*$")
        self.assertRegex(metadata, r"(?m)^  allow_implicit_invocation:\s*false\s*$")

    def test_managed_projection_preserves_the_package_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            target = home / ".agents" / "skills" / "codemap"
            preview = system.install("codemap", apply=False)
            self.assertEqual("dry-run", preview.reason)
            self.assertFalse(target.exists())

            applied = system.install("codemap", apply=True)
            self.assertEqual("installed", applied.reason)
            self.assertTrue(applied.applied)
            self.assertEqual(content_hash(SKILL), content_hash(target))
            projected = system.status().skills["codemap"]
            self.assertEqual("current", projected.state)
            self.assertEqual(projected.source_hash, projected.target_hash)
            self.assertEqual("already-current", system.install("codemap", apply=True).reason)

            self.assertIsNotNone(applied.operation_id)
            rolled_back = system.rollback(applied.operation_id, apply=True)
            self.assertEqual("rolled-back", rolled_back.reason)
            self.assertFalse(target.exists())
            restored = system.status()
            self.assertEqual("absent", restored.skills["codemap"].state)
            self.assertEqual((), restored.incomplete_operations)


if __name__ == "__main__":
    unittest.main()
