from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skill_system.operations import SkillSystem
from tests.helpers import make_system, tree_snapshot


CLI = Path(__file__).resolve().parents[1] / "bin" / "skill-system"


class CodexAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "canonical"
        self.home = self.base / "home"
        self.skills = self.home / ".codex" / "skills"
        make_system(self.root, self.home)
        self.addCleanup(self.temporary.cleanup)

    def run_cli(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root),
             "--home", str(self.home), command],
            capture_output=True, text=True, check=False, timeout=10,
        )

    def declaration(self, relative: str, name: str) -> Path:
        path = self.skills / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nname: {name}\ndescription: Test skill\n---\nBody\n")
        return path

    def test_canonical_audit_can_pass_while_root_personal_skill_fails(self) -> None:
        path = self.declaration("SKILL.md", "orchestrate")
        before = tree_snapshot(self.base)
        self.assertEqual(0, self.run_cli("audit").returncode)
        result = self.run_cli("audit-codex")
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        entry, = report["personal_skills"]
        self.assertEqual(str(path), entry["path"])
        self.assertEqual("orchestrate", entry["declared_name"])
        self.assertIn("root-declaration", entry["issues"])
        self.assertEqual(before, tree_snapshot(self.base))

    def test_hidden_nested_names_and_malformed_declarations(self) -> None:
        mismatch = self.declaration(".hidden/nested/old-name/SKILL.md", '"new-name"')
        malformed = self.declaration("bad/SKILL.md", "[not-a-name]")
        duplicate = self.declaration("duplicate/SKILL.md", "first\nname: second")
        result = self.run_cli("audit-codex")
        self.assertEqual(1, result.returncode, result.stderr)
        entries = {entry["path"]: entry for entry in json.loads(result.stdout)["personal_skills"]}
        self.assertEqual("new-name", entries[str(mismatch)]["declared_name"])
        self.assertIn("name-directory-mismatch", entries[str(mismatch)]["issues"])
        for path in (malformed, duplicate):
            self.assertIsNone(entries[str(path)]["declared_name"])
            self.assertIn("malformed-declaration", entries[str(path)]["issues"])

    def test_missing_system_only_and_non_skill_entries_are_clean(self) -> None:
        for stage in ("missing", "system", "non-skill"):
            with self.subTest(stage=stage):
                if stage == "system":
                    self.declaration(".system/provider/SKILL.md", "provider")
                elif stage == "non-skill":
                    (self.skills / "notes.txt").write_text("not a declaration")
                before = tree_snapshot(self.base)
                result = self.run_cli("audit-codex")
                self.assertEqual(0, result.returncode, result.stderr)
                report = json.loads(result.stdout)
                self.assertTrue(report["ok"])
                self.assertEqual([], report["personal_skills"])
                if stage != "missing":
                    self.assertEqual(str(self.skills / ".system"), report["provider_entries"][0]["path"])
                if stage == "non-skill":
                    self.assertIn(str(self.skills / "notes.txt"), report["non_skill_entries"])
                self.assertEqual(before, tree_snapshot(self.base))

    def test_symlinks_are_reported_without_following_targets_or_cycles(self) -> None:
        external = self.base / "other-home" / "cache"
        external.mkdir(parents=True)
        (external / "SKILL.md").write_text("must not parse external files")
        self.skills.mkdir(parents=True)
        (self.skills / "outside").symlink_to(external, target_is_directory=True)
        (self.skills / "cycle").symlink_to(self.skills, target_is_directory=True)
        (self.skills / "broken").symlink_to(self.base / "missing")
        (self.skills / "SKILL.md").symlink_to(external / "SKILL.md")
        result = self.run_cli("audit-codex")
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual([], report["personal_skills"])
        self.assertEqual(4, len(report["symlinks"]))
        self.assertEqual({str(self.skills / name) for name in ("outside", "cycle", "broken", "SKILL.md")},
                         {entry["path"] for entry in report["symlinks"]})

    def test_symlinked_codex_root_is_not_traversed(self) -> None:
        external = self.base / "external"
        external.mkdir()
        (self.home / ".codex").symlink_to(external, target_is_directory=True)
        result = self.run_cli("audit-codex")
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual([], report["personal_skills"])
        self.assertEqual(str(self.home / ".codex"), report["symlinks"][0]["path"])

    def test_unreadable_declaration_encoding_and_missing_header_are_flagged(self) -> None:
        for payload in (b"\xff", b"name: no-frontmatter\n", b"---\nname: unclosed\n"):
            with self.subTest(payload=payload):
                path = self.declaration("broken/SKILL.md", "broken")
                path.write_bytes(payload)
                result = self.run_cli("audit-codex")
                self.assertEqual(1, result.returncode, result.stderr)
                entry, = json.loads(result.stdout)["personal_skills"]
                self.assertIsNone(entry["declared_name"])
                self.assertIn("malformed-declaration", entry["issues"])

    def test_provider_symlink_is_exempt_and_registry_is_not_required(self) -> None:
        self.skills.mkdir(parents=True)
        (self.skills / ".system").symlink_to(self.base / "absent-provider")
        (self.root / "registry.json").write_text("invalid registry")
        result = self.run_cli("audit-codex")
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual([], report["symlinks"])
        self.assertEqual(str(self.base / "absent-provider"), report["provider_entries"][0]["target"])

    def test_non_directory_root_reports_inspection_failure(self) -> None:
        self.skills.parent.mkdir(parents=True)
        self.skills.write_text("not a directory")
        result = self.run_cli("audit-codex")
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertTrue(result.stderr)

    def test_executable_file_symlink_is_non_skill_without_reading_target(self) -> None:
        executable = self.base / "external-runtime" / "codex"
        executable.parent.mkdir()
        executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
        link = self.skills / "node_modules" / ".bin" / "codex"
        link.parent.mkdir(parents=True)
        link.symlink_to(executable)
        before = tree_snapshot(self.base)

        result = self.run_cli("audit-codex")

        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertIn(str(link), report["non_skill_entries"])
        self.assertEqual([], report["symlinks"])
        self.assertEqual([], report["personal_skills"])
        with patch.object(Path, "open", side_effect=AssertionError("file content accessed")):
            self.assertTrue(SkillSystem(self.root, self.home).audit_codex().ok)
        self.assertEqual(before, tree_snapshot(self.base))


if __name__ == "__main__":
    unittest.main()
