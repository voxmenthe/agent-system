from __future__ import annotations

import errno
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_system import CollisionError, configure_mimo
from skill_system.cli import run
from tests.helpers import make_system, tree_snapshot


class MimoAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "source"
        self.home = base / "home"
        make_system(self.root, self.home, names=("alpha", "beta"))
        self.agents_skills = self.home / ".agents" / "skills"
        self.mimo_skills = self.home / ".config" / "mimocode" / "skills"

        for name in ("alpha", "beta"):
            destination = self.agents_skills / name
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                self.root / "skills" / name,
                destination,
                dirs_exist_ok=True,
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _backup_parent(self) -> Path:
        return (self.home / ".agents" / ".skill-system" / "mimo-backups").resolve()

    def test_configure_mimo_dry_run_and_apply(self) -> None:
        dry_run = configure_mimo(self.root, self.home, apply=False)
        self.assertFalse(dry_run.applied)
        self.assertEqual("dry-run", dry_run.reason)
        self.assertFalse(self.mimo_skills.exists())
        self.assertEqual(2, len(dry_run.changes))

        applied = configure_mimo(self.root, self.home, apply=True)
        self.assertTrue(applied.applied)
        self.assertEqual("configured", applied.reason)
        self.assertIsNone(applied.quarantine_path)
        self.assertFalse(self._backup_parent().exists())
        self.assertTrue((self.mimo_skills / "alpha" / "SKILL.md").is_file())
        self.assertTrue((self.mimo_skills / "beta" / "SKILL.md").is_file())
        self.assertFalse((self.mimo_skills / "alpha").is_symlink())

        marker = json.loads(
            (self.mimo_skills / "alpha" / ".mimo-projection.json").read_text()
        )
        self.assertEqual(
            str((self.agents_skills / "alpha").resolve()),
            marker["source"],
        )
        self.assertTrue(marker["source_hash"].startswith("sha256:"))

        locale = json.loads(
            (self.mimo_skills / "alpha" / "locales" / "en-US.json").read_text()
        )
        self.assertEqual("Alpha", locale["displayName"])
        self.assertTrue(locale["brief"])
        self.assertTrue(
            (self.mimo_skills / "alpha" / "locales" / "zh-CN.json").is_file()
        )

    def test_configure_mimo_is_idempotent(self) -> None:
        first = configure_mimo(self.root, self.home, apply=True)
        self.assertTrue(first.applied)

        second = configure_mimo(self.root, self.home, apply=True)
        self.assertFalse(second.applied)
        self.assertEqual("already-current", second.reason)

    def test_configure_mimo_refreshes_when_source_changes(self) -> None:
        configure_mimo(self.root, self.home, apply=True)
        skill_md = self.agents_skills / "alpha" / "SKILL.md"
        skill_md.write_text(skill_md.read_text() + "\nUpdated body.\n")

        refreshed = configure_mimo(self.root, self.home, apply=True)
        self.assertTrue(refreshed.applied)
        self.assertIsNone(refreshed.quarantine_path)
        self.assertIn(
            "refresh skill copy alpha -> "
            + str((self.mimo_skills / "alpha").resolve()),
            refreshed.changes,
        )
        self.assertIn(
            "Updated body.",
            (self.mimo_skills / "alpha" / "SKILL.md").read_text(),
        )

        # Under --force a managed copy (marker present) is still refreshed in place.
        skill_md.write_text(skill_md.read_text() + "\nForced body.\n")
        forced = configure_mimo(self.root, self.home, apply=True, force=True)
        self.assertTrue(forced.applied)
        self.assertIsNone(forced.quarantine_path)
        self.assertFalse(self._backup_parent().exists())
        self.assertIn(
            "Forced body.", (self.mimo_skills / "alpha" / "SKILL.md").read_text()
        )

    def test_configure_mimo_cleans_stale_managed_copies(self) -> None:
        configure_mimo(self.root, self.home, apply=True)
        stale = self.mimo_skills / "retired-skill"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "SKILL.md").write_text("stale")
        (stale / ".mimo-projection.json").write_text(
            json.dumps(
                {
                    "source": str(self.agents_skills / "retired-skill"),
                    "source_hash": "sha256:" + ("0" * 64),
                }
            )
        )

        result = configure_mimo(self.root, self.home, apply=True)
        self.assertTrue(result.applied)
        self.assertIn("remove stale MiMo skill: retired-skill", result.removed)
        self.assertFalse(stale.exists())

    def test_configure_mimo_preserves_unmanaged_local_directories(self) -> None:
        configure_mimo(self.root, self.home, apply=True)
        unmanaged = self.mimo_skills / "mimo-local-tool"
        unmanaged.mkdir(parents=True, exist_ok=True)
        (unmanaged / "SKILL.md").write_text("local only")

        result = configure_mimo(self.root, self.home, apply=True)
        self.assertFalse(result.applied)
        self.assertTrue(unmanaged.is_dir())
        self.assertEqual("local only", (unmanaged / "SKILL.md").read_text())

    def test_configure_mimo_refuses_unmanaged_collision_without_force(self) -> None:
        self.mimo_skills.mkdir(parents=True, exist_ok=True)
        colliding = self.mimo_skills / "alpha"
        colliding.mkdir(parents=True, exist_ok=True)
        (colliding / "local.txt").write_text("drifted")

        with self.assertRaises(CollisionError):
            configure_mimo(self.root, self.home, apply=False, force=False)

        with self.assertRaises(CollisionError):
            configure_mimo(self.root, self.home, apply=True, force=False)

    def test_configure_mimo_replaces_unmanaged_collision_with_force(self) -> None:
        self.mimo_skills.mkdir(parents=True, exist_ok=True)
        colliding = self.mimo_skills / "alpha"
        (colliding / "nested").mkdir(parents=True)
        (colliding / "local.txt").write_bytes(b"drifted \x00\xff sentinel\n")
        (colliding / "nested" / "notes.md").write_text("keep me")
        stray = self.mimo_skills / "beta"
        stray.write_bytes(b"not a directory\n")
        before = tree_snapshot(colliding)

        result = configure_mimo(self.root, self.home, apply=True, force=True)
        self.assertTrue(result.applied)
        self.assertTrue((colliding / "SKILL.md").is_file())
        self.assertFalse((colliding / "local.txt").exists())
        self.assertTrue((stray / "SKILL.md").is_file())
        # Both displaced entries are retained byte-identical outside discovery.
        self.assertIsNotNone(result.quarantine_path)
        self.assertEqual(self._backup_parent(), result.quarantine_path.parent)
        self.assertEqual(before, tree_snapshot(result.quarantine_path / "alpha"))
        self.assertEqual(
            b"not a directory\n", (result.quarantine_path / "beta").read_bytes()
        )

    def test_configure_mimo_restores_collision_when_replacement_fails(self) -> None:
        colliding = self.mimo_skills / "alpha"
        real_copyfile = shutil.copyfile
        copies: list[str] = []
        mid_replacement: list[bool] = []

        def note_replacement_in_progress() -> None:
            # Original moved aside and a replacement copy partly written.
            mid_replacement.append(
                any(colliding.rglob("*")) and not (colliding / "local.txt").exists()
            )

        def copy_once_then_fill_disk(source, destination, *args, **kwargs):
            copies.append(str(source))
            if len(copies) > 1:
                note_replacement_in_progress()
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_copyfile(source, destination, *args, **kwargs)

        def fail_marker_write(*args, **kwargs):
            note_replacement_in_progress()
            raise OSError(errno.ENOSPC, "No space left on device")

        failures = {
            "mid-copy": patch("shutil.copyfile", side_effect=copy_once_then_fill_disk),
            "marker-write": patch.object(Path, "write_text", side_effect=fail_marker_write),
        }
        for stage, failure in failures.items():
            with self.subTest(stage=stage):
                shutil.rmtree(self.mimo_skills, ignore_errors=True)
                shutil.rmtree(self._backup_parent(), ignore_errors=True)
                mid_replacement.clear()
                (colliding / "nested").mkdir(parents=True)
                (colliding / "local.txt").write_bytes(b"drifted \x00\xff sentinel\n")
                (colliding / "nested" / "notes.md").write_text("keep me")
                before = tree_snapshot(self.mimo_skills)

                with failure, self.assertRaises(OSError):
                    configure_mimo(self.root, self.home, apply=True, force=True)

                self.assertTrue(mid_replacement)
                self.assertNotIn(False, mid_replacement)
                # Original restored verbatim; no partial copy left anywhere.
                self.assertEqual(before, tree_snapshot(self.mimo_skills))
                leftovers = [
                    p for p in self._backup_parent().rglob("*") if not p.is_dir()
                ]
                self.assertEqual([], leftovers)

    def test_cli_configure_mimo(self) -> None:
        args = [
            "--root",
            str(self.root),
            "--home",
            str(self.home),
            "configure-mimo",
            "--apply",
        ]
        exit_code = run(args)
        self.assertEqual(0, exit_code)
        self.assertTrue((self.mimo_skills / "alpha" / "SKILL.md").is_file())

    def test_sync_automatically_projects_to_mimo(self) -> None:
        from skill_system import SkillSystem

        system = SkillSystem(self.root, self.home)
        self.assertFalse((self.mimo_skills / "alpha").exists())

        result = system.sync(apply=True)
        self.assertTrue(result.applied)
        self.assertIsNotNone(result.mimo)
        self.assertTrue(result.mimo.applied)
        self.assertTrue((self.mimo_skills / "alpha" / "SKILL.md").is_file())
        self.assertTrue((self.mimo_skills / "beta" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
