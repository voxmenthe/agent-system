"""bug-hunt skill contract: package shape, explicit-only parity, registry record, head-loaded stop rules."""
from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from skill_system import SkillSystem, content_hash
from skill_system.model import _parse_frontmatter, _parse_quoted_yaml, validate_skill_tree


ROOT = Path(__file__).resolve().parents[1]
NAME = "bug-hunt"
SKILL_ROOT = ROOT / "skills" / NAME
SKILL_MD = SKILL_ROOT / "SKILL.md"
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REFERENCES = {
    "references/ephyra-playbook.md",
    "references/framework-selection.md",
    "references/oracle-and-triage-patterns.md",
}
STATE_DIRECTORIES = (".hypothesis/", "proptest-regressions/", "testdata/fuzz/", "fuzz/", ".ephyra/")
TRIAGE_BUCKETS = (
    "Real product bug",
    "Spec / contract ambiguity",
    "Generator invalid-input bug",
    "Oracle / environment bug",
)


def sections(text: str) -> dict[str, str]:
    """Level-2 heading -> body, in file order."""
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {heading.strip(): body for heading, body in zip(parts[1::2], parts[2::2])}


def numbered_items(body: str) -> list[str]:
    return re.findall(r"^\d+\. (.+)$", body, flags=re.MULTILINE)


def markdown_files() -> list[Path]:
    return [SKILL_MD, *sorted((SKILL_ROOT / "references").glob("*.md"))]


class BugHuntSkillTests(unittest.TestCase):
    def test_package_is_exactly_the_skill_metadata_and_three_references(self) -> None:
        files = {
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual({"SKILL.md", "agents/openai.yaml", *REFERENCES}, files)
        for path in (SKILL_ROOT, *SKILL_ROOT.rglob("*")):
            self.assertFalse(path.is_symlink(), path)

    def test_tree_validates_and_both_hosts_are_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, NAME), r"^sha256:[0-9a-f]{64}$")
        frontmatter = _parse_frontmatter(SKILL_MD)
        metadata = _parse_quoted_yaml(SKILL_ROOT / "agents" / "openai.yaml", NAME)
        self.assertEqual(NAME, frontmatter["name"])
        self.assertEqual("true", frontmatter["disable-model-invocation"])
        self.assertIs(False, metadata["policy"]["allow_implicit_invocation"])
        interface = metadata["interface"]
        self.assertEqual("Hunt real bugs via inductive PBT and strong oracles", interface["short_description"])
        self.assertIn(f"${NAME}", interface["default_prompt"])
        self.assertIn(f"${NAME}", frontmatter["description"])

    def test_registry_record_is_owner_authored_experimental_and_dependency_free(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"][NAME]
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual(f"skills/{NAME}", record["source"])
        self.assertEqual([f"~/.agents/skills/{NAME}"], record["install_targets"])
        self.assertEqual([], record["dependencies"])
        self.assertEqual("local-write", record["effect_ceiling"])
        self.assertEqual("explicit-only-inductive-bug-hunting", record["evaluation_profile"])
        self.assertEqual("owner-authored", record["provenance"]["license"])
        self.assertEqual("owner-authored", record["provenance"]["origin"])

    def test_user_guide_lists_the_skill(self) -> None:
        guide = (ROOT / "USER-GUIDE.md").read_text()
        self.assertIn(f"[`{NAME}`](skills/{NAME}/SKILL.md)", guide)
        self.assertIn(f"`${NAME}`", guide)

    def test_skill_md_fits_its_budget_with_stop_rules_in_the_first_2_kb(self) -> None:
        raw = SKILL_MD.read_bytes()
        self.assertLessEqual(len(raw), 8000)
        text = raw.decode()
        headings = list(sections(text))
        self.assertEqual("Stop rules and isolation", headings[0])
        end_of_stop_rules = raw.index(f"## {headings[1]}".encode())
        self.assertLessEqual(end_of_stop_rules, 2048)
        stop_rules = sections(text)["Stop rules and isolation"]
        self.assertEqual(6, len(numbered_items(stop_rules)))
        for directory in STATE_DIRECTORIES:
            self.assertIn(f"`{directory}`", stop_rules)

    def test_boundary_matrix_names_existing_neighbour_skills(self) -> None:
        matrix = sections(SKILL_MD.read_text())["Pick the right skill"]
        rows = re.findall(r"^\| `([a-z*-]+)` \|", matrix, flags=re.MULTILINE)
        self.assertEqual(
            [
                "create-verification-skill",
                "create-formal-verification-skill",
                "debugging",
                "evidence-driven-loop-*",
                NAME,
            ],
            rows,
        )
        for row in rows[:-1]:
            with self.subTest(row=row):
                self.assertTrue(list((ROOT / "skills").glob(f"{row}/SKILL.md")), row)

    def test_five_phases_in_order_with_ladder_gates_and_triage_buckets(self) -> None:
        parts = sections(SKILL_MD.read_text())
        phases = [heading for heading in parts if heading.startswith("Phase ")]
        self.assertEqual([f"Phase {n}" for n in range(1, 6)], [h.split(":")[0] for h in phases])
        self.assertIn("Property Contract Table", phases[0])
        self.assertEqual(6, len(numbered_items(parts[phases[1]])))
        self.assertIn("**Seeded-mutant calibration gate.**", parts[phases[2]])
        self.assertIn("**Generator self-check.**", parts[phases[2]])
        buckets = [item.split(".**")[0].lstrip("*") for item in numbered_items(parts[phases[4]])]
        self.assertEqual(list(TRIAGE_BUCKETS), buckets)

    def test_every_reference_is_linked_from_skill_md_and_every_link_resolves(self) -> None:
        linked = {
            (SKILL_MD.parent / raw.split("#", 1)[0]).resolve()
            for raw in LINK.findall(SKILL_MD.read_text())
            if not raw.startswith(("http://", "https://", "#"))
        }
        self.assertEqual({(SKILL_ROOT / path).resolve() for path in REFERENCES}, linked)
        for path in markdown_files():
            for raw in LINK.findall(path.read_text()):
                target = raw.split("#", 1)[0].strip()
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                with self.subTest(path=path.name, target=target):
                    resolved = (path.parent / target).resolve()
                    self.assertTrue(resolved.is_relative_to(SKILL_ROOT.resolve()))
                    self.assertTrue(resolved.is_file())

    def test_guidance_is_public_and_names_other_skills_without_install_paths(self) -> None:
        for path in [*markdown_files(), SKILL_ROOT / "agents" / "openai.yaml"]:
            content = path.read_text()
            with self.subTest(path=path.name):
                for forbidden in ("/Users/", "/Volumes/", ".agents/skills/"):
                    self.assertNotIn(forbidden, content)

    def test_managed_install_dry_run_idempotence_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            target = home / ".agents" / "skills" / NAME
            self.assertEqual("dry-run", system.install(NAME, apply=False).reason)
            self.assertFalse(target.exists())
            result = system.install(NAME, apply=True)
            self.assertTrue(result.applied)
            self.assertEqual(content_hash(SKILL_ROOT), content_hash(target))
            self.assertEqual("already-current", system.install(NAME, apply=True).reason)
            self.assertIsNotNone(result.operation_id)
            assert result.operation_id is not None
            system.rollback(result.operation_id, apply=True)
            self.assertFalse(target.exists())
            self.assertEqual((), system.status().incomplete_operations)


if __name__ == "__main__":
    unittest.main()
