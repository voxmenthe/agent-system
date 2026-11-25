"""skiller skill contract and its live catalog over the real canonical tree; no model calls."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from skill_system.model import _parse_frontmatter, _parse_quoted_yaml, validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
SKILL_ROOT = SKILLS / "skiller"
CATALOG = SKILL_ROOT / "scripts" / "catalog"


def run(*args: str, script: Path = CATALOG) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(script), *args], capture_output=True, text=True, timeout=30)


def expected() -> dict[str, tuple[str, str, str]]:
    """Each canonical skill's mode, brief and full description, as the skill system reads them."""
    skills = {}
    for root in sorted(path for path in SKILLS.iterdir() if (path / "SKILL.md").is_file()):
        front = _parse_frontmatter(root / "SKILL.md")
        meta = _parse_quoted_yaml(root / "agents/openai.yaml", root.name)
        mode = "explicit" if front.get("disable-model-invocation") == "true" else "auto"
        skills[root.name] = (mode, meta["interface"]["short_description"], front["description"])
    return skills


class SkillerSkillTests(unittest.TestCase):
    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "skiller"), r"^sha256:")
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("disable-model-invocation: true", (SKILL_ROOT / "SKILL.md").read_text())
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$skiller", metadata)

    def test_catalog_lists_every_skill_once_with_mode_and_brief_description(self) -> None:
        result = run()
        self.assertEqual(0, result.returncode, result.stderr)
        header, *lines = result.stdout.splitlines()
        skills = expected()
        self.assertTrue(header.startswith(f"{len(skills)} skills in {SKILLS} "), header)
        self.assertEqual([f"{name} · {mode} · {brief}" for name, (mode, brief, _) in skills.items()], lines)
        self.assertEqual({"auto", "explicit"}, {mode for mode, _, _ in skills.values()})

    def test_named_skills_print_their_full_description_in_order(self) -> None:
        skills = expected()
        result = run("intent", "frame-change")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [f"intent · {skills['intent'][0]}", f"  {skills['intent'][2]}",
             f"frame-change · {skills['frame-change'][0]}", f"  {skills['frame-change'][2]}"],
            result.stdout.splitlines(),
        )
        full = run("--full")
        self.assertEqual(0, full.returncode, full.stderr)
        self.assertEqual(2 * len(skills), len(full.stdout.splitlines()))
        for _, _, description in skills.values():
            self.assertIn(f"  {description}\n", full.stdout)

    def test_unknown_name_fails_naming_it_and_prints_nothing(self) -> None:
        result = run("intent", "no-such-skill")
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("no installed skill named no-such-skill", result.stderr)

    def test_a_symlinked_install_reads_the_directory_it_points_into(self) -> None:
        # Claude Code reaches skills through ~/.claude/skills/<name> -> ~/.agents/skills/<name>.
        with tempfile.TemporaryDirectory() as temporary:
            link = Path(temporary) / "skiller"
            link.symlink_to(SKILL_ROOT, target_is_directory=True)
            result = run(script=link / "scripts" / "catalog")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(run().stdout, result.stdout)

    def test_registry_record_and_guide_entries(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["skiller"]
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("skills/skiller", record["source"])
        self.assertEqual("read-only", record["effect_ceiling"])
        self.assertEqual(["~/.agents/skills/skiller"], record["install_targets"])
        guide = (ROOT / "USER-GUIDE.md").read_text()
        self.assertIn("[`skiller`](skills/skiller/SKILL.md)", guide)
        self.assertIn("| `$skiller` |", guide)


if __name__ == "__main__":
    unittest.main()
