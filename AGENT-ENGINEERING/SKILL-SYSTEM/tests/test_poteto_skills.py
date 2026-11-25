from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from skill_system import content_hash
from tests.helpers import tree_snapshot


ROOT = Path(__file__).resolve().parents[1]
NAMES = ("create-verification-skill", "maintain-verification-skill", "poteto")
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class PotetoSkillTests(unittest.TestCase):
    def test_packages_declare_effects_dependencies_and_source_identity(self) -> None:
        records = json.loads((ROOT / "registry.json").read_text())["skills"]
        expected_dependencies = {
            "create-verification-skill": set(),
            "maintain-verification-skill": set(),
            "poteto": {
                "frame-change", "map-change", "architecture-plan",
                "implement-change", "diff-review", "verify-change",
                "create-verification-skill", "maintain-verification-skill",
                "show-me-clearly",
            },
        }
        for name in NAMES:
            with self.subTest(skill=name):
                record = records[name]
                skill = ROOT / "skills" / name
                self.assertEqual("custom", record["ownership"])
                self.assertEqual("experimental", record["lifecycle"])
                self.assertEqual(f"skills/{name}", record["source"])
                self.assertEqual([f"~/.agents/skills/{name}"], record["install_targets"])
                self.assertEqual(expected_dependencies[name], set(record["dependencies"]))
                self.assertEqual(
                    "external-write" if name == "poteto" else "local-write",
                    record["effect_ceiling"],
                )
                self.assertEqual(content_hash(skill), record["provenance"]["revision"])
                if name != "poteto":
                    self.assertEqual("MIT", record["provenance"]["license"])
                    self.assertEqual(
                        "93b00b89ef425a9c1bac0d0b317dfc49c930ac99",
                        record["provenance"]["reference_revision"],
                    )
                    self.assertTrue((skill / "LICENSE").is_file())
                    self.assertTrue((skill / "NOTICE.md").is_file())

    def test_all_bundled_references_resolve_inside_each_portable_package(self) -> None:
        for name in NAMES:
            root = (ROOT / "skills" / name).resolve()
            linked: set[Path] = set()
            for path in root.rglob("*.md"):
                for raw in LINK.findall(path.read_text()):
                    target = raw.split("#", 1)[0].strip()
                    if not target or target.startswith(("https://", "http://", "#")):
                        continue
                    with self.subTest(skill=name, path=path, target=target):
                        resolved = (path.parent / target).resolve()
                        self.assertTrue(resolved.is_relative_to(root))
                        self.assertTrue(resolved.is_file())
                        linked.add(resolved)
            self.assertTrue(set(root.glob("references/*.md")) <= linked)

    def test_exact_cli_projection_and_rollback_preserve_other_skills_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            unrelated = home / ".agents" / "skills" / "unmanaged"
            unrelated.mkdir(parents=True)
            (unrelated / "owner.txt").write_text("owner work\n")
            proof = home / "task" / "proof.txt"
            proof.parent.mkdir()
            proof.write_text("retained task evidence\n")
            before = tree_snapshot(home)

            def command(*arguments: str) -> dict:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "bin" / "skill-system"),
                     "--root", str(ROOT), "--home", str(home), *arguments],
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                return json.loads(result.stdout)

            operations: dict[str, str] = {}
            for name in NAMES:
                preview = command("install", name, "--dry-run")
                self.assertFalse(preview["applied"])
                self.assertEqual(before, tree_snapshot(home))
            for name in NAMES:
                result = command("install", name, "--apply")
                self.assertTrue(result["applied"])
                operations[name] = result["operation_id"]
                self.assertEqual(
                    content_hash(ROOT / "skills" / name),
                    content_hash(home / ".agents" / "skills" / name),
                )
                self.assertFalse(command("install", name, "--apply")["applied"])

            command("rollback", operations["poteto"], "--apply")
            self.assertFalse((home / ".agents" / "skills" / "poteto").exists())
            for name in NAMES[:2]:
                self.assertTrue((home / ".agents" / "skills" / name / "SKILL.md").is_file())
            for name in reversed(NAMES[:2]):
                command("rollback", operations[name], "--apply")
            status = command("status")
            self.assertEqual([], status["incomplete_operations"])
            for name in NAMES:
                self.assertEqual("absent", status["skills"][name]["state"])
            self.assertEqual("owner work\n", (unrelated / "owner.txt").read_text())
            self.assertEqual("retained task evidence\n", proof.read_text())


if __name__ == "__main__":
    unittest.main()
