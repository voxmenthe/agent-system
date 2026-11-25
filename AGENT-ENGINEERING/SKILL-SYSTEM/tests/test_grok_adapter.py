from __future__ import annotations

from contextlib import redirect_stdout
import fcntl
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from skill_system import CollisionError, LockBusyError, SkillSystem, ValidationError
from skill_system.cli import run
from tests.helpers import make_system, tree_snapshot

ACCOUNTS = (".grok", ".grok2", ".grok3")


class GrokAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name).resolve()
        self.root = base / "source"
        self.home = base / "home"
        make_system(self.root, self.home)
        self.system = SkillSystem(self.root, self.home)
        self.source = self.root / "grok-skills" / "macro"
        (self.source / "references").mkdir(parents=True)
        (self.source / "SKILL.md").write_text(
            "---\nname: macro\ndescription: >\n"
            "  Use for native X research in Grok.\n"
            "metadata:\n  short-description: Native X research\n---\n\n"
            "# Macro\n\nRead references/roster.tsv.\n"
        )
        (self.source / "references" / "roster.tsv").write_text("handle\trole\n")

    def target(self, account: str = ".grok") -> Path:
        return self.home / account / "skills" / "macro"

    def test_native_sources_validate_without_codex_metadata(self) -> None:
        report = self.system.validate()
        self.assertTrue(report.ok)
        self.assertEqual({"macro"}, set(report.grok_skills))
        self.assertEqual(("alpha",), report.custom_skills)
        self.assertFalse((self.source / "agents" / "openai.yaml").exists())

    def test_absent_native_catalog_leaves_unrelated_grok_roots_uninspected(self) -> None:
        (self.root / "grok-skills").rename(self.home / "retained-catalog")
        (self.home / ".grok").symlink_to("missing-external-home")
        self.assertEqual({}, self.system.status().grok)
        self.assertEqual("already-current", self.system.configure_grok(apply=True).reason)

    def test_dry_run_changes_nothing_and_apply_links_every_account(self) -> None:
        before = tree_snapshot(self.home)
        preview = self.system.configure_grok()
        self.assertEqual("dry-run", preview.reason)
        self.assertEqual(len(ACCOUNTS), len(preview.changes))
        self.assertEqual(before, tree_snapshot(self.home))

        applied = self.system.configure_grok(apply=True)
        self.assertTrue(applied.applied)
        for account in ACCOUNTS:
            self.assertTrue(self.target(account).is_symlink())
            self.assertEqual(self.source, self.target(account).resolve())
            self.assertEqual("current", self.system.status().grok[account]["macro"])
        self.assertFalse((self.home / ".agents" / "skills" / "macro").exists())
        self.assertFalse(self.system.configure_grok(apply=True).applied)

    def test_source_updates_are_visible_without_copy_or_refresh(self) -> None:
        self.system.configure_grok(apply=True)
        roster = self.source / "references" / "roster.tsv"
        roster.write_text("new handle\trole\n")
        for account in ACCOUNTS:
            self.assertEqual(roster.read_bytes(), (self.target(account) / "references" / "roster.tsv").read_bytes())
        self.assertEqual("already-current", self.system.configure_grok(apply=True).reason)

    def test_force_retains_different_account_copies_and_unknown_entries(self) -> None:
        expected: dict[str, dict] = {}
        for account in ACCOUNTS:
            shutil.copytree(self.source, self.target(account))
            (self.target(account) / "SKILL.md").write_text(f"{account} original content\n")
            expected[account] = tree_snapshot(self.target(account))
            unknown = self.target(account).parent / "xgrok"
            unknown.mkdir()
            (unknown / "SKILL.md").write_text("unrelated shared skill copy\n")
            (self.home / account / "config.toml").write_text("account setting\n")

        before = tree_snapshot(self.home)
        preview = self.system.configure_grok(force=True)
        self.assertFalse(preview.applied)
        self.assertEqual(before, tree_snapshot(self.home))

        applied = self.system.configure_grok(apply=True, force=True)
        self.assertIsNotNone(applied.quarantine_path)
        for account in ACCOUNTS:
            self.assertEqual(expected[account], tree_snapshot(applied.quarantine_path / account / "macro"))
            self.assertEqual("unrelated shared skill copy\n", (self.target(account).parent / "xgrok" / "SKILL.md").read_text())
            self.assertEqual("account setting\n", (self.home / account / "config.toml").read_text())

        # Exercise documented recovery while retaining the generated link too.
        generated_link = applied.quarantine_path / "generated-link"
        self.target().rename(generated_link)
        (applied.quarantine_path / ".grok" / "macro").rename(self.target())
        self.assertEqual(expected[".grok"], tree_snapshot(self.target()))

    def test_collision_preflight_preserves_all_accounts(self) -> None:
        self.target(".grok2").mkdir(parents=True)
        (self.target(".grok2") / "local.txt").write_text("local drift")
        before = tree_snapshot(self.home)
        with self.assertRaises(CollisionError):
            self.system.configure_grok(apply=True)
        self.assertEqual(before, tree_snapshot(self.home))
        self.assertFalse(self.target().exists())

    def test_force_preserves_dangling_symlink_preimage(self) -> None:
        self.target().parent.mkdir(parents=True)
        self.target().symlink_to("missing-old-source")
        applied = self.system.configure_grok(apply=True, force=True)
        backup = applied.quarantine_path / ".grok" / "macro"
        self.assertTrue(backup.is_symlink())
        self.assertEqual("missing-old-source", str(backup.readlink()))
        self.assertEqual(self.source, self.target().resolve())

    def test_cyclic_live_symlink_is_a_collision_not_a_resolution_crash(self) -> None:
        self.target().parent.mkdir(parents=True)
        self.target().symlink_to("macro")
        self.assertEqual("unmanaged-collision", self.system.status().grok[".grok"]["macro"])
        with self.assertRaises(CollisionError):
            self.system.configure_grok()
        applied = self.system.configure_grok(apply=True, force=True)
        self.assertEqual("macro", str((applied.quarantine_path / ".grok" / "macro").readlink()))
        self.assertEqual(self.source, self.target().resolve())

    def test_failure_after_backup_restores_original_entry(self) -> None:
        shutil.copytree(self.source, self.target())
        expected = tree_snapshot(self.target())
        with patch.object(Path, "symlink_to", side_effect=OSError("injected link failure")):
            with self.assertRaises(OSError):
                self.system.configure_grok(apply=True, force=True)
        self.assertFalse(self.target().is_symlink())
        self.assertEqual(expected, tree_snapshot(self.target()))

    def test_symlinked_discovery_roots_are_rejected_even_with_force(self) -> None:
        external = self.home / "external"
        external.mkdir()
        (self.home / ".grok").symlink_to(external)
        with self.assertRaises(CollisionError):
            self.system.configure_grok(apply=True, force=True)
        self.assertEqual([], list(external.iterdir()))

    def test_source_symlinks_and_mismatched_declarations_fail_before_projection(self) -> None:
        (self.source / "escape").symlink_to(self.home)
        with self.assertRaises(ValidationError):
            self.system.configure_grok(apply=True)
        self.assertFalse(self.target().exists())
        (self.source / "escape").rename(self.home / "retained-test-symlink")
        declaration = self.source / "SKILL.md"
        declaration.write_text(declaration.read_text().replace("name: macro", "name: other"))
        with self.assertRaisesRegex(ValidationError, "mismatch"):
            self.system.validate()

    def test_projection_respects_existing_operation_lock(self) -> None:
        lock = self.home / ".agents" / ".skill-system" / "operation.lock"
        with lock.open("rb") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(LockBusyError):
                self.system.configure_grok(apply=True)
        self.assertFalse(self.target().exists())

    def test_sync_includes_grok_without_leaking_native_skills_to_other_hosts(self) -> None:
        preview = self.system.sync()
        self.assertIsNotNone(preview.grok)
        self.assertFalse(self.target().exists())
        applied = self.system.sync(apply=True)
        self.assertTrue(applied.grok.applied)
        self.assertTrue(self.target().is_symlink())
        for discovery in (".agents/skills", ".claude/skills", ".config/mimocode/skills"):
            self.assertFalse((self.home / discovery / "macro").exists())

    def test_sync_skips_hosts_the_machine_file_does_not_enable(self) -> None:
        machine = self.home / ".config" / "agent-system" / "machine.json"
        machine.parent.mkdir(parents=True)
        machine.write_text(json.dumps({"schema_version": 1, "hosts": ["codex", "grok2"]}))
        applied = self.system.sync(apply=True)
        self.assertTrue((self.home / ".agents" / "skills" / "alpha").is_dir())
        self.assertTrue(self.target(".grok2").is_symlink())
        self.assertEqual("host-disabled", applied.claude.reason)
        for absent in (".grok", ".grok3", ".claude", ".config/mimocode"):
            self.assertFalse((self.home / absent).exists(), absent)

        machine.write_text('{"schema_version": 1, "hosts": "codex"}')
        with self.assertRaisesRegex(ValidationError, "needs schema_version 1"):
            self.system.sync()

    def test_cli_exposes_dry_run_apply_and_native_status(self) -> None:
        args = ["--root", str(self.root), "--home", str(self.home)]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, run([*args, "configure-grok"]))
        self.assertEqual("dry-run", json.loads(output.getvalue())["reason"])
        self.assertFalse(self.target().exists())
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, run([*args, "configure-grok", "--apply"]))
        self.assertTrue(json.loads(output.getvalue())["applied"])


if __name__ == "__main__":
    unittest.main()
