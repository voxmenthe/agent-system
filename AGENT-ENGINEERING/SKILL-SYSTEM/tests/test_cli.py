from __future__ import annotations

import json
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import make_system


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "skill-system"


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "canonical"
        self.home = base / "home"
        make_system(self.root, self.home)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--root",
                str(self.root),
                "--home",
                str(self.home),
                *arguments,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_help_matches_the_narrow_command_surface(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        for command in (
            "audit",
            "validate",
            "status",
            "install",
            "refresh",
            "sync",
            "rollback",
            "quarantine",
            "migrate-lock",
            "configure-antigravity",
        ):
            self.assertIn(command, result.stdout)
        self.assertNotIn("--force", result.stdout)

    def test_validate_and_status_emit_machine_readable_reconciliation(self) -> None:
        validate = self.run_cli("validate")
        self.assertEqual(0, validate.returncode, validate.stderr)
        report = json.loads(validate.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(["alpha"], report["custom_skills"])

        status = self.run_cli("status")
        self.assertEqual(0, status.returncode, status.stderr)
        reconciliation = json.loads(status.stdout)
        self.assertEqual("absent", reconciliation["skills"]["alpha"]["state"])
        self.assertEqual([], reconciliation["incomplete_operations"])

    def test_install_defaults_to_dry_run_and_requires_apply_to_mutate(self) -> None:
        dry_run = self.run_cli("install", "alpha")
        self.assertEqual(0, dry_run.returncode, dry_run.stderr)
        result = json.loads(dry_run.stdout)
        self.assertEqual("dry-run", result["reason"])
        self.assertFalse((self.home / ".agents" / "skills" / "alpha").exists())

        applied = self.run_cli("install", "alpha", "--apply")
        self.assertEqual(0, applied.returncode, applied.stderr)
        result = json.loads(applied.stdout)
        self.assertTrue(result["applied"])
        self.assertTrue((self.home / ".agents" / "skills" / "alpha").is_dir())

    def test_refresh_defaults_to_dry_run_and_requires_apply_to_update(self) -> None:
        installed = self.run_cli("install", "alpha", "--apply")
        self.assertEqual(0, installed.returncode, installed.stderr)
        target = self.home / ".agents" / "skills" / "alpha" / "SKILL.md"
        original = target.read_bytes()
        source = self.root / "skills" / "alpha" / "SKILL.md"
        source.write_text(source.read_text() + "\nrefreshed behavior\n")

        dry_run = self.run_cli("refresh")

        self.assertEqual(0, dry_run.returncode, dry_run.stderr)
        preview = json.loads(dry_run.stdout)
        self.assertEqual("dry-run", preview["reason"])
        self.assertEqual(["alpha"], list(preview["operations"]))
        self.assertEqual(original, target.read_bytes())

        applied = self.run_cli("refresh", "--apply")

        self.assertEqual(0, applied.returncode, applied.stderr)
        result = json.loads(applied.stdout)
        self.assertTrue(result["applied"])
        self.assertEqual("refreshed", result["reason"])
        self.assertIn(b"refreshed behavior", target.read_bytes())

    def test_expected_failures_are_nonzero_and_do_not_emit_success_json(self) -> None:
        target = self.home / ".agents" / "skills" / "alpha"
        target.mkdir(parents=True)
        (target / "local.txt").write_text("unmanaged")

        result = self.run_cli("install", "alpha", "--apply")

        self.assertEqual(2, result.returncode)
        self.assertIn("unmanaged target collision", result.stderr)
        self.assertEqual("", result.stdout)

    def test_dry_run_and_apply_are_mutually_exclusive(self) -> None:
        result = self.run_cli("install", "alpha", "--dry-run", "--apply")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not allowed with argument", result.stderr)

    def test_sync_warns_about_collisions_and_force_adopts_them(self) -> None:
        # alpha: unmanaged collision (live dir, no managed state)
        collision = self.home / ".agents" / "skills" / "alpha"
        collision.mkdir(parents=True)
        (collision / "local.txt").write_text("unmanaged")
        original = (collision / "local.txt").read_bytes()

        dry_run = self.run_cli("sync")

        self.assertEqual(0, dry_run.returncode, dry_run.stderr)
        preview = json.loads(dry_run.stdout)
        self.assertEqual("dry-run", preview["reason"])
        self.assertIn("alpha", preview["excluded"]["unmanaged-collision"])
        # collision content preserved without force
        self.assertEqual(original, (collision / "local.txt").read_bytes())

        # --force --apply adopts the collision (canonical wins)
        applied = self.run_cli("sync", "--force", "--apply")

        self.assertEqual(0, applied.returncode, applied.stderr)
        result = json.loads(applied.stdout)
        self.assertTrue(result["applied"])
        self.assertEqual("synced", result["reason"])
        self.assertIn("alpha", result["operations"])
        self.assertTrue(
            (self.home / ".agents" / "skills" / "alpha" / "SKILL.md").is_file()
        )
        # displaced local content is gone from the live target
        self.assertFalse((collision / "local.txt").exists())

    def test_sync_help_advertises_force_flag(self) -> None:
        result = self.run_cli("sync", "--help")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--force", result.stdout)

    def test_configure_antigravity_defaults_to_dry_run_then_creates_declaration(
        self,
    ) -> None:
        target = self.home / ".gemini" / "config" / "skills.json"

        dry_run = self.run_cli("configure-antigravity")

        self.assertEqual(0, dry_run.returncode, dry_run.stderr)
        preview = json.loads(dry_run.stdout)
        self.assertFalse(preview["applied"])
        self.assertEqual("dry-run", preview["reason"])
        self.assertEqual([str(target.resolve())], preview["changes"])
        self.assertFalse(target.exists())

        applied = self.run_cli("configure-antigravity", "--apply")

        self.assertEqual(0, applied.returncode, applied.stderr)
        result = json.loads(applied.stdout)
        self.assertTrue(result["applied"])
        self.assertEqual("configured", result["reason"])
        self.assertEqual(
            {
                "entries": [
                    {"path": str(self.home.resolve() / ".agents" / "skills")}
                ]
            },
            json.loads(target.read_text()),
        )
        self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))

    def test_configure_antigravity_is_idempotent_when_declaration_exists(self) -> None:
        target = self.home / ".gemini" / "config" / "skills.json"
        target.parent.mkdir(parents=True)
        shared_skills = str(self.home.resolve() / ".agents" / "skills")
        target.write_text(
            json.dumps(
                {
                    "entries": [
                        {"path": "~/other-skills"},
                        {"path": shared_skills},
                    ]
                }
            )
        )
        original = target.read_bytes()

        result = self.run_cli("configure-antigravity", "--apply")

        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["applied"])
        self.assertEqual("already-current", report["reason"])
        self.assertEqual(original, target.read_bytes())

    def test_configure_antigravity_preserves_unsupported_existing_configs(self) -> None:
        target = self.home / ".gemini" / "config" / "skills.json"
        target.parent.mkdir(parents=True)
        for contents in (
            '{"entries": [{"path": "~/.agents/skills"}]}\n',
            '{"entries": [',
        ):
            with self.subTest(contents=contents):
                target.write_text(contents)
                original = target.read_bytes()

                result = self.run_cli("configure-antigravity", "--apply")

                self.assertEqual(2, result.returncode)
                self.assertIn(
                    "refusing to replace existing Antigravity config",
                    result.stderr,
                )
                self.assertEqual("", result.stdout)
                self.assertEqual(original, target.read_bytes())

    def test_configure_claude_cli_defaults_to_dry_run_then_applies(self) -> None:
        agents_alpha = self.home / ".agents" / "skills" / "alpha"
        agents_alpha.mkdir(parents=True, exist_ok=True)
        (agents_alpha / "SKILL.md").write_text("dummy")

        dry_run = self.run_cli("configure-claude")
        self.assertEqual(0, dry_run.returncode, dry_run.stderr)
        preview = json.loads(dry_run.stdout)
        self.assertFalse(preview["applied"])
        self.assertEqual("dry-run", preview["reason"])

        applied = self.run_cli("configure-claude", "--apply")
        self.assertEqual(0, applied.returncode, applied.stderr)
        result = json.loads(applied.stdout)
        self.assertTrue(result["applied"])
        self.assertEqual("configured", result["reason"])
        claude_alpha = self.home / ".claude" / "skills" / "alpha"
        self.assertTrue(claude_alpha.is_symlink())


if __name__ == "__main__":
    unittest.main()

