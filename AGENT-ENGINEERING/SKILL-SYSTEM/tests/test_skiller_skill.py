"""skiller skill contract and its live catalog over the real canonical tree; no model calls."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
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


def write_skill(root: Path, description: str, *, explicit: bool = False, metadata: str | None = None) -> None:
    root.mkdir(parents=True)
    flag = "disable-model-invocation: true\n" if explicit else ""
    (root / "SKILL.md").write_text(f"---\nname: {root.name}\ndescription: {json.dumps(description)}\n{flag}---\n\n# {root.name}\n")
    if metadata is not None:
        (root / "agents").mkdir()
        (root / "agents/openai.yaml").write_text(metadata)


# Five-character words: one ends at index 119, so keeping it whole plus "…" would make 121 characters.
LONG_SENTENCE = " ".join(["Sweep", *(f"w{index:03d}" for index in range(40))])
PROJECT_ALPHA = "Project alpha overrides the installed one. Use when testing shadows."
LOCAL_ONLY = "Only in this project. Use when testing project skills."


class CatalogFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.installed = base / "installed"
        self.project = base / "project"
        self.project_skills = self.project / ".agents" / "skills"
        script = self.installed / "skiller" / "scripts" / "catalog"
        script.parent.mkdir(parents=True)
        shutil.copy2(CATALOG, script)
        self.catalog = script
        self.alpha = "Installed alpha. Use when testing."
        write_skill(self.installed / "alpha", self.alpha,
                    metadata='interface:\n  display_name: "Alpha"\n  short_description: "Alpha brief from openai yaml"\n')
        write_skill(self.installed / "beta", f"{LONG_SENTENCE}. Second sentence must not appear.")
        write_skill(self.installed / "gamma", "Do the gamma thing. Use when gamma.", explicit=True,
                    metadata='interface:\n  display_name: "Gamma"\n')
        write_skill(self.project_skills / "alpha", PROJECT_ALPHA, explicit=True)
        write_skill(self.project_skills / "local-only", LOCAL_ONLY)

    def installed_listing(self) -> list[str]:
        result = run(script=self.catalog)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.splitlines()

    def test_brief_falls_back_to_the_first_sentence_without_openai_yaml_or_its_short_description(self) -> None:
        header, alpha, beta, gamma = self.installed_listing()
        self.assertTrue(header.startswith(f"3 skills in {self.installed} "), header)
        self.assertEqual("alpha · auto · Alpha brief from openai yaml", alpha)
        self.assertEqual("gamma · explicit · Do the gamma thing", gamma)
        prefix = "beta · auto · "
        self.assertTrue(beta.startswith(prefix), beta)
        brief = beta.removeprefix(prefix)
        self.assertLessEqual(len(brief), 120)
        self.assertGreater(len(brief), 100)
        self.assertTrue(brief.endswith("…"), brief)
        kept = brief.removesuffix("…")
        self.assertTrue(LONG_SENTENCE.startswith(kept), brief)
        self.assertEqual(" ", LONG_SENTENCE[len(kept)], "truncation must end on a whole word")

    def test_project_lists_its_skills_after_the_installed_ones_and_flags_shadows(self) -> None:
        result = run("--project", str(self.project), script=self.catalog)
        self.assertEqual(0, result.returncode, result.stderr)
        lines = result.stdout.splitlines()
        installed = self.installed_listing()
        self.assertEqual(installed, lines[: len(installed)])
        self.assertEqual(
            [f"[project] 2 skills in {self.project_skills}",
             "alpha · explicit · Project alpha overrides the installed one [shadows global]",
             "local-only · auto · Only in this project"],
            lines[len(installed):],
        )

    def test_project_names_resolve_positionally_including_project_skills(self) -> None:
        result = run("--project", str(self.project), "local-only", "alpha", script=self.catalog)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["local-only · auto [project]", f"  {LOCAL_ONLY}",
             "alpha · auto", f"  {self.alpha}",
             "alpha · explicit [project] [shadows global]", f"  {PROJECT_ALPHA}"],
            result.stdout.splitlines(),
        )
        missing = run("--project", str(self.project), "no-such-skill", script=self.catalog)
        self.assertEqual(2, missing.returncode)
        self.assertEqual("", missing.stdout)
        self.assertIn("no installed skill named no-such-skill", missing.stderr)
        full = run("--full", "--project", str(self.project), script=self.catalog)
        self.assertEqual(0, full.returncode, full.stderr)
        self.assertEqual(
            [f"[project] 2 skills in {self.project_skills}",
             "alpha · explicit [shadows global]", f"  {PROJECT_ALPHA}",
             "local-only · auto", f"  {LOCAL_ONLY}"],
            full.stdout.splitlines()[6:],
        )

    def test_project_must_name_an_existing_directory(self) -> None:
        result = run("--project", str(self.project / "absent"), script=self.catalog)
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("is not a directory", result.stderr)


if __name__ == "__main__":
    unittest.main()
