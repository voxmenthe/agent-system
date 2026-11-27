from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import tempfile
import unittest

from skill_system import SkillSystem


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def broken_links(markdown_files: list[Path], root: Path) -> list[tuple[Path, str]]:
    # Prose may name host paths; validate links, not prose.
    # Only links inside the skill system are checked: folders outside it can
    # move without the skill system changing.
    root = root.resolve()
    broken = []
    for path in markdown_files:
        for raw in LINK.findall(path.read_text()):
            target = raw.split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (path.parent / target).resolve()
            if resolved.is_relative_to(root) and not resolved.exists():
                broken.append((path, target))
    return broken
RETIRED_SKILLS = {
    "ask-matt",
    "batch-grill-me",
    "code-review",
    "codebase-design",
    "diagnosing-bugs",
    "design-an-interface",
    "docs-update",
    "domain-modeling",
    "edit-article",
    "explain-codebase",
    "explain-diff",
    "explain-progress",
    "git-publish",
    "grill-me",
    "grill-with-docs",
    "handoff",
    "implement",
    "improve-codebase-architecture",
    "loop-me",
    "production-debugging",
    "prototype",
    "ponytail-audit",
    "ponytail-review",
    "request-refactor-plan",
    "route-policy",
    "scaffold-exercises",
    "show-code-change",
    "show-code-flow",
    "show-code-structure",
    "to-spec",
    "to-questionnaire",
    "wayfinder",
}
REMOVED_SKILLS = {"find-skills", "migration-safety"}


class RepositoryArtifactTests(unittest.TestCase):
    def test_real_canonical_tree_and_accounting_validate_without_live_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = SkillSystem(ROOT, Path(temporary)).validate()

        self.assertTrue(report.ok)
        self.assertEqual(77, len(report.custom_skills))
        self.assertEqual(32, len(report.legacy_skills))
        self.assertEqual((), report.external_skills)

        registry = json.loads((ROOT / "registry.json").read_text())
        self.assertEqual(109, len(registry["skills"]))
        self.assertTrue(REMOVED_SKILLS.isdisjoint(registry["skills"]))
        for name in REMOVED_SKILLS:
            self.assertFalse((ROOT / "skills" / name).exists())
        self.assertEqual(
            RETIRED_SKILLS,
            {
                name
                for name, record in registry["skills"].items()
                if record.get("lifecycle") == "retired"
            },
        )
        for name in RETIRED_SKILLS:
            with self.subTest(name=name):
                self.assertEqual(
                    "quarantined-after-owner-approval",
                    registry["skills"][name]["provenance"]["disposition"],
                )
        for name in ("ponytail-audit", "ponytail-review"):
            self.assertNotIn("notes", registry["skills"][name]["provenance"])

    def test_promoted_review_portfolio_projects_and_rolls_back_in_fake_home(self) -> None:
        names = ("diff-review", "simplify-review", "simplify-audit", "ponytail")
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            operation_ids: list[str] = []

            for name in names:
                preview = system.install(name, apply=False)
                self.assertFalse(preview.applied)
                self.assertEqual("dry-run", preview.reason)
                self.assertFalse((home / ".agents" / "skills" / name).exists())

                applied = system.install(name, apply=True)
                self.assertTrue(applied.applied)
                self.assertEqual("installed", applied.reason)
                self.assertIsNotNone(applied.operation_id)
                operation_ids.append(applied.operation_id or "")

            projected = system.status()
            self.assertEqual([], list(projected.incomplete_operations))
            for name in names:
                with self.subTest(stage="projected", name=name):
                    self.assertEqual("current", projected.skills[name].state)
                    self.assertEqual(
                        projected.skills[name].source_hash,
                        projected.skills[name].target_hash,
                    )
            for name in ("ponytail-review", "ponytail-audit"):
                with self.subTest(stage="retired", name=name):
                    self.assertEqual("legacy-absent", projected.skills[name].state)
                    self.assertFalse((home / ".agents" / "skills" / name).exists())

            for operation in reversed(operation_ids):
                rolled_back = system.rollback(operation, apply=True)
                self.assertTrue(rolled_back.applied)
                self.assertEqual("rolled-back", rolled_back.reason)

            restored = system.status()
            self.assertEqual([], list(restored.incomplete_operations))
            for name in names:
                with self.subTest(stage="restored", name=name):
                    self.assertEqual("absent", restored.skills[name].state)
                    self.assertFalse((home / ".agents" / "skills" / name).exists())

    def test_consolidated_planning_skills_project_and_roll_back_in_fake_home(self) -> None:
        names = ("architecture-plan", "backwards")
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            operations: list[str] = []

            for name in names:
                with self.subTest(stage="install", name=name):
                    applied = system.install(name, apply=True)
                    self.assertTrue(applied.applied)
                    self.assertEqual("installed", applied.reason)
                    self.assertIsNotNone(applied.operation_id)
                    operations.append(applied.operation_id or "")

            projected = system.status()
            for name in names:
                with self.subTest(stage="projected", name=name):
                    self.assertEqual("current", projected.skills[name].state)
                    self.assertEqual(
                        projected.skills[name].source_hash,
                        projected.skills[name].target_hash,
                    )

            for operation in reversed(operations):
                rolled_back = system.rollback(operation, apply=True)
                self.assertTrue(rolled_back.applied)
                self.assertEqual("rolled-back", rolled_back.reason)

            restored = system.status()
            for name in names:
                with self.subTest(stage="restored", name=name):
                    self.assertEqual("absent", restored.skills[name].state)
                    self.assertFalse((home / ".agents" / "skills" / name).exists())

    def test_explicit_only_migrations_project_and_roll_back_in_fake_home(self) -> None:
        names = (
            "grilling",
            "research",
            "synthesize-market-state",
            "tdd",
            "ubiquitous-language",
        )
        retired = ("prototype", "scaffold-exercises", "to-questionnaire")
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            operations: list[str] = []

            for name in names:
                with self.subTest(stage="install", name=name):
                    applied = system.install(name, apply=True)
                    self.assertTrue(applied.applied)
                    self.assertEqual("installed", applied.reason)
                    self.assertIsNotNone(applied.operation_id)
                    operations.append(applied.operation_id or "")

            projected = system.status()
            for name in names:
                with self.subTest(stage="projected", name=name):
                    self.assertEqual("current", projected.skills[name].state)
                    self.assertEqual(
                        projected.skills[name].source_hash,
                        projected.skills[name].target_hash,
                    )
            for name in retired:
                with self.subTest(stage="retired", name=name):
                    self.assertEqual("legacy-absent", projected.skills[name].state)

            for operation in reversed(operations):
                rolled_back = system.rollback(operation, apply=True)
                self.assertTrue(rolled_back.applied)
                self.assertEqual("rolled-back", rolled_back.reason)

            restored = system.status()
            for name in names:
                with self.subTest(stage="restored", name=name):
                    self.assertEqual("absent", restored.skills[name].state)
                    self.assertFalse((home / ".agents" / "skills" / name).exists())

    def test_versioned_schemas_are_strict_json_artifacts(self) -> None:
        for name in (
            "registry.schema.json",
            "install-state.schema.json",
            "operation.schema.json",
        ):
            with self.subTest(name=name):
                schema = json.loads((ROOT / "schemas" / name).read_text())
                self.assertEqual(
                    "https://json-schema.org/draft/2020-12/schema",
                    schema["$schema"],
                )
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(1, schema["properties"]["schema_version"]["const"])

    def test_skill_scripts_write_no_bytecode_beside_their_sibling_modules(self) -> None:
        # An installed skill is a hash-tracked copy: bytecode an invocation writes into it (gpt, skiller)
        # reads as a local edit and blocks the skill's next refresh. A script that imports a module beside
        # it must turn bytecode off before the first such import.
        offenders = []
        for script in sorted((ROOT / "skills").glob("*/scripts/**/*")):
            if not script.is_file() or "__pycache__" in script.parts or script.name.startswith("test_"):
                continue
            source = script.read_text(errors="replace")
            if script.suffix != ".py" and not source.startswith("#!/usr/bin/env python3"):
                continue
            if "__main__" not in source and not source.startswith("#!"):
                continue  # a library module, imported only by an entry script
            siblings = {path.stem for path in script.parent.glob("*.py")} - {script.stem}
            tree = ast.parse(source)
            imports = [
                node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Import) and any(a.name.split(".")[0] in siblings for a in node.names)
                or isinstance(node, ast.ImportFrom) and node.level == 0
                and (node.module or "").split(".")[0] in siblings
            ]
            guards = [
                node.lineno for node in tree.body
                if isinstance(node, ast.Assign) and ast.unparse(node) == "sys.dont_write_bytecode = True"
            ]
            if imports and not (guards and min(guards) < min(imports)):
                offenders.append(script.relative_to(ROOT).as_posix())
        self.assertEqual([], offenders)

    def test_skills_hold_no_machine_paths(self) -> None:
        # Every machine installs these bytes, so a home or drive path in them works on one machine only.
        machine_path = re.compile(r"/Users/(?!me/)|/Volumes/")
        offenders = [
            f"{path.relative_to(ROOT).as_posix()}:{number}"
            for path in sorted((ROOT / "skills").rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1)
            if machine_path.search(line)
        ]
        self.assertEqual([], offenders)

    def test_repository_markdown_links_resolve(self) -> None:
        markdown_files = [
            *ROOT.glob("*.md"),
            *(ROOT / "skills").glob("*/SKILL.md"),
        ]
        self.assertEqual([], broken_links(markdown_files, ROOT))

    def test_link_check_ignores_targets_outside_the_skill_system(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "SKILL-SYSTEM"
            root.mkdir()
            (root / "present.md").write_text("present\n")
            doc = root / "README.md"
            doc.write_text(
                "[ok](present.md) [gone](missing.md) [moved](../ELSEWHERE/plan.md)\n"
            )
            self.assertEqual([(doc, "missing.md")], broken_links([doc], root))


if __name__ == "__main__":
    unittest.main()
