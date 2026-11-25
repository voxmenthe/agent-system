from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from skill_system import content_hash


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "learning-workspace"
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class LearningWorkspaceSkillTests(unittest.TestCase):
    def test_package_shape_limits_and_links_match_the_public_contract(self) -> None:
        expected_files = {
            "LICENSE",
            "NOTICE.md",
            "SKILL.md",
            "agents/openai.yaml",
            "references/failure-modes.md",
            "references/notes-template.md",
        }
        actual_files = {
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(expected_files, actual_files)

        # Raised 10-31 for the owner's task choices, the owed and inferred decisions, and the close-out.
        limits = {
            "SKILL.md": 8704,
            "references/notes-template.md": 3 * 1024,
            "references/failure-modes.md": 4 * 1024,
        }
        for relative, limit in limits.items():
            with self.subTest(relative=relative):
                path = SKILL_ROOT / relative
                self.assertGreater(path.stat().st_size, 0)
                self.assertLessEqual(path.stat().st_size, limit)

        linked_files: set[str] = set()
        for path in (SKILL_ROOT / "SKILL.md", *SKILL_ROOT.glob("references/*.md")):
            content = path.read_text()
            for raw in LINK.findall(content):
                target = raw.split("#", 1)[0].strip()
                if not target or target.startswith(("http://", "https://", "#")):
                    continue
                with self.subTest(path=path, target=target):
                    resolved = (path.parent / target).resolve()
                    self.assertTrue(resolved.is_relative_to(SKILL_ROOT.resolve()))
                    self.assertTrue(resolved.is_file())
                    linked_files.add(
                        resolved.relative_to(SKILL_ROOT.resolve()).as_posix()
                    )

        self.assertEqual(
            {
                "references/failure-modes.md",
                "references/notes-template.md",
            },
            linked_files,
        )

        for path in (SKILL_ROOT, *SKILL_ROOT.rglob("*")):
            with self.subTest(path=path):
                self.assertFalse(path.is_symlink())

    def test_registry_and_host_metadata_are_stable_and_agent_invocable(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        record = registry["learning-workspace"]
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text()

        self.assertEqual("custom", record["ownership"])
        self.assertEqual("stable", record["lifecycle"])
        self.assertEqual("skills/learning-workspace", record["source"])
        self.assertEqual(
            ["~/.agents/skills/learning-workspace"], record["install_targets"]
        )
        self.assertEqual([], record["dependencies"])
        self.assertEqual("local-write", record["effect_ceiling"])
        self.assertEqual(
            "task-local-continuity",
            record["evaluation_profile"],
        )
        self.assertEqual("MIT", record["provenance"]["license"])
        self.assertEqual(
            "6b33c1f7c2ad45997663c69157f5559d1be61bd9",
            record["provenance"]["reference_revision"],
        )
        self.assertEqual(content_hash(SKILL_ROOT), record["provenance"]["revision"])

        frontmatter = skill.split("---", 2)[1]
        self.assertNotIn("disable-model-invocation", frontmatter)
        self.assertIn("allow_implicit_invocation: true", metadata)


if __name__ == "__main__":
    unittest.main()
