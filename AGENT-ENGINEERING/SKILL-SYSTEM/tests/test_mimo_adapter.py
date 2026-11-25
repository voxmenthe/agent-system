from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from skill_system import CollisionError, configure_mimo
from skill_system.cli import run
from tests.helpers import make_system


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

    def test_configure_mimo_dry_run_and_apply(self) -> None:
        dry_run = configure_mimo(self.root, self.home, apply=False)
        self.assertFalse(dry_run.applied)
        self.assertEqual("dry-run", dry_run.reason)
        self.assertFalse(self.mimo_skills.exists())
        self.assertEqual(2, len(dry_run.changes))

        applied = configure_mimo(self.root, self.home, apply=True)
        self.assertTrue(applied.applied)
        self.assertEqual("configured", applied.reason)
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
        self.assertIn(
            "refresh skill copy alpha -> "
            + str((self.mimo_skills / "alpha").resolve()),
            refreshed.changes,
        )
        self.assertIn(
            "Updated body.",
            (self.mimo_skills / "alpha" / "SKILL.md").read_text(),
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
        colliding.mkdir(parents=True, exist_ok=True)
        (colliding / "local.txt").write_text("drifted")

        result = configure_mimo(self.root, self.home, apply=True, force=True)
        self.assertTrue(result.applied)
        self.assertTrue((colliding / "SKILL.md").is_file())
        self.assertFalse((colliding / "local.txt").exists())

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
