from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_system import CollisionError, SkillSystem, configure_claude
from skill_system.cli import run
from tests.helpers import make_system, tree_snapshot, write_json, write_skill


class ClaudeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "source"
        self.home = base / "home"
        make_system(self.root, self.home, names=("alpha", "beta"))
        self.agents_skills = self.home / ".agents" / "skills"
        self.claude_skills = self.home / ".claude" / "skills"

        # Install alpha into .agents/skills
        (self.agents_skills / "alpha").mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            self.root / "skills" / "alpha",
            self.agents_skills / "alpha",
            dirs_exist_ok=True,
        )

        # Install beta into .agents/skills
        (self.agents_skills / "beta").mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            self.root / "skills" / "beta",
            self.agents_skills / "beta",
            dirs_exist_ok=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _unmanaged_alpha(self) -> tuple[Path, dict[str, tuple[str, int, bytes]]]:
        colliding = self.claude_skills / "alpha"
        (colliding / "nested").mkdir(parents=True)
        (colliding / "local.txt").write_bytes(b"drifted \x00\xff sentinel\n")
        (colliding / "nested" / "notes.md").write_text("keep me")
        return colliding, tree_snapshot(colliding)

    def _backup_parent(self) -> Path:
        return (self.home / ".agents" / ".skill-system" / "claude-backups").resolve()

    def test_configure_claude_dry_run_and_apply(self) -> None:
        dry_run = configure_claude(self.root, self.home, apply=False)
        self.assertFalse(dry_run.applied)
        self.assertEqual("dry-run", dry_run.reason)
        self.assertFalse(self.claude_skills.exists())
        self.assertEqual(2, len(dry_run.changes))

        applied = configure_claude(self.root, self.home, apply=True)
        self.assertTrue(applied.applied)
        self.assertEqual("configured", applied.reason)
        self.assertIsNone(applied.quarantine_path)
        self.assertFalse(self._backup_parent().exists())
        self.assertTrue(self.claude_skills.exists())

        # Verify symlinks
        alpha_link = self.claude_skills / "alpha"
        beta_link = self.claude_skills / "beta"
        self.assertTrue(alpha_link.is_symlink())
        self.assertTrue(beta_link.is_symlink())
        self.assertEqual(
            (self.agents_skills / "alpha").resolve(),
            alpha_link.resolve(),
        )
        self.assertEqual(
            (self.agents_skills / "beta").resolve(),
            beta_link.resolve(),
        )

    def test_configure_claude_is_idempotent(self) -> None:
        first = configure_claude(self.root, self.home, apply=True)
        self.assertTrue(first.applied)

        second = configure_claude(self.root, self.home, apply=True)
        self.assertFalse(second.applied)
        self.assertEqual("already-current", second.reason)

    def test_configure_claude_cleans_dangling_symlinks(self) -> None:
        self.claude_skills.mkdir(parents=True, exist_ok=True)
        dangling = self.claude_skills / "old-skill"
        dangling.symlink_to("../../.agents/skills/nonexistent-skill")

        result = configure_claude(self.root, self.home, apply=True)
        self.assertTrue(result.applied)
        self.assertIn("remove dangling symlink: old-skill -> ../../.agents/skills/nonexistent-skill", result.removed)
        self.assertFalse(dangling.exists())
        self.assertFalse(dangling.is_symlink())

    def test_configure_claude_cleans_retired_symlinks(self) -> None:
        self.claude_skills.mkdir(parents=True, exist_ok=True)
        # Create retired directory in .agents/skills
        retired_dir = self.agents_skills / "retired-skill"
        retired_dir.mkdir(parents=True, exist_ok=True)
        # Link it in claude
        retired_link = self.claude_skills / "retired-skill"
        retired_link.symlink_to("../../.agents/skills/retired-skill")

        result = configure_claude(self.root, self.home, apply=True)
        self.assertTrue(result.applied)
        self.assertIn("remove retired symlink: retired-skill -> ../../.agents/skills/retired-skill", result.removed)
        self.assertFalse(retired_link.exists())

    def test_configure_claude_preserves_external_valid_symlinks(self) -> None:
        self.claude_skills.mkdir(parents=True, exist_ok=True)
        external_target = self.temporary.name + "/external-skill"
        Path(external_target).mkdir(parents=True, exist_ok=True)
        external_link = self.claude_skills / "external-skill"
        external_link.symlink_to(external_target)

        result = configure_claude(self.root, self.home, apply=True)
        self.assertTrue(result.applied)
        self.assertTrue(external_link.is_symlink())
        self.assertTrue(external_link.exists())
        self.assertEqual(Path(external_target).resolve(), external_link.resolve())

    def test_configure_claude_preserves_unmanaged_local_directories(self) -> None:
        self.claude_skills.mkdir(parents=True, exist_ok=True)
        unmanaged_dir = self.claude_skills / "claude-local-tool"
        unmanaged_dir.mkdir(parents=True, exist_ok=True)
        (unmanaged_dir / "SKILL.md").write_text("local only")

        result = configure_claude(self.root, self.home, apply=True)
        self.assertTrue(result.applied)
        self.assertTrue(unmanaged_dir.is_dir())
        self.assertEqual("local only", (unmanaged_dir / "SKILL.md").read_text())

    def test_configure_claude_refuses_directory_collision_without_force(self) -> None:
        self.claude_skills.mkdir(parents=True, exist_ok=True)
        colliding = self.claude_skills / "alpha"
        colliding.mkdir(parents=True, exist_ok=True)
        (colliding / "local.txt").write_text("drifted")

        with self.assertRaises(CollisionError):
            configure_claude(self.root, self.home, apply=False, force=False)

        with self.assertRaises(CollisionError):
            configure_claude(self.root, self.home, apply=True, force=False)

    def test_configure_claude_replaces_directory_collision_with_force(self) -> None:
        colliding, before = self._unmanaged_alpha()

        result = configure_claude(self.root, self.home, apply=True, force=True)
        self.assertTrue(result.applied)
        self.assertTrue((self.claude_skills / "alpha").is_symlink())
        self.assertEqual(
            (self.agents_skills / "alpha").resolve(),
            (self.claude_skills / "alpha").resolve(),
        )
        # The displaced directory is retained byte-identical outside discovery.
        self.assertIsNotNone(result.quarantine_path)
        self.assertEqual(self._backup_parent(), result.quarantine_path.parent)
        self.assertEqual(before, tree_snapshot(result.quarantine_path / "alpha"))
        self.assertEqual(["alpha"], sorted(p.name for p in result.quarantine_path.iterdir()))

    def test_configure_claude_restores_collision_when_symlink_fails(self) -> None:
        colliding, before = self._unmanaged_alpha()
        real_symlink = os.symlink

        def link_then_interrupt(source, link, target_is_directory=False):
            real_symlink(source, link, target_is_directory)
            raise KeyboardInterrupt

        with patch("os.symlink", side_effect=link_then_interrupt):
            with self.assertRaises(KeyboardInterrupt):
                configure_claude(self.root, self.home, apply=True, force=True)

        self.assertFalse(colliding.is_symlink())
        self.assertEqual(before, tree_snapshot(colliding))
        self.assertEqual(["alpha"], sorted(p.name for p in self.claude_skills.iterdir()))
        leftovers = [p for p in self._backup_parent().rglob("*") if not p.is_dir()]
        self.assertEqual([], leftovers)

    def test_sync_force_retains_claude_collision(self) -> None:
        _, before = self._unmanaged_alpha()

        result = SkillSystem(self.root, self.home).sync(apply=True, force=True)
        self.assertIsNotNone(result.claude)
        self.assertTrue((self.claude_skills / "alpha").is_symlink())
        self.assertEqual(before, tree_snapshot(result.claude.quarantine_path / "alpha"))

    def test_cli_configure_claude(self) -> None:
        args = [
            "--root",
            str(self.root),
            "--home",
            str(self.home),
            "configure-claude",
            "--apply",
        ]
        exit_code = run(args)
        self.assertEqual(0, exit_code)
        self.assertTrue((self.claude_skills / "alpha").is_symlink())

    def test_sync_automatically_projects_to_claude(self) -> None:
        system = SkillSystem(self.root, self.home)
        self.assertFalse((self.claude_skills / "alpha").exists())

        result = system.sync(apply=True)
        self.assertTrue(result.applied)
        self.assertIsNotNone(result.claude)
        self.assertTrue(result.claude.applied)
        self.assertTrue((self.claude_skills / "alpha").is_symlink())
        self.assertTrue((self.claude_skills / "beta").is_symlink())


if __name__ == "__main__":
    unittest.main()

