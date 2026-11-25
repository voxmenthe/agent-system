from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "scientific-figure-making"
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class ScientificFigureMakingSkillTests(unittest.TestCase):
    def test_package_shape_and_links_match_the_public_contract(self) -> None:
        expected_files = {
            "LICENSE",
            "NOTICE.md",
            "SKILL.md",
            "agents/openai.yaml",
            "references/api.md",
            "references/common-patterns.md",
            "references/demos.md",
            "references/design-theory.md",
            "references/figure-gallery.md",
            "references/tutorials.md",
        }
        actual_files = {
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(expected_files, actual_files)

        for relative in expected_files:
            with self.subTest(relative=relative):
                self.assertGreater((SKILL_ROOT / relative).stat().st_size, 0)

        for path in (SKILL_ROOT / "SKILL.md", *SKILL_ROOT.glob("references/*.md")):
            content = path.read_text()
            self.assertNotIn("/Users/", content, path)
            for raw in LINK.findall(content):
                target = raw.split("#", 1)[0].strip()
                if not target or target.startswith(("http://", "https://", "#")):
                    continue
                with self.subTest(path=path, target=target):
                    resolved = (path.parent / target).resolve()
                    self.assertTrue(resolved.is_relative_to(SKILL_ROOT.resolve()))
                    self.assertTrue(resolved.is_file())

        for path in (SKILL_ROOT, *SKILL_ROOT.rglob("*")):
            with self.subTest(path=path):
                self.assertFalse(path.is_symlink())

    def test_registry_and_host_metadata_are_explicit_only(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        record = registry["scientific-figure-making"]
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text()

        self.assertEqual("custom", record["ownership"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual("skills/scientific-figure-making", record["source"])
        self.assertEqual(
            ["~/.agents/skills/scientific-figure-making"], record["install_targets"]
        )
        self.assertEqual([], record["dependencies"])
        self.assertEqual("local-write", record["effect_ceiling"])
        self.assertEqual(
            "explicit-only-publication-figures",
            record["evaluation_profile"],
        )
        self.assertEqual(
            "https://github.com/ChenLiu-1996/figures4papers",
            record["provenance"]["origin"],
        )
        self.assertEqual(
            "565e6b97a9609e14ac07bee83dcb94589034fe27",
            record["provenance"]["reference_revision"],
        )

        frontmatter = skill.split("---", 2)[1]
        self.assertIn("disable-model-invocation: true", frontmatter)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$scientific-figure-making", metadata)


if __name__ == "__main__":
    unittest.main()
