from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_system import (
    CollisionError,
    IncompleteOperationError,
    InjectedFailure,
    SkillSystem,
    ValidationError,
)
import skill_system.operations as operations
from skill_system.operations import EXPECTED_MATT_SKILLS
from tests.helpers import (
    Stopped,
    make_system,
    stop_before_journaling,
    tree_snapshot,
    write_json,
)


def lock_fixture() -> dict[str, object]:
    skills = {
        name: {
            "source": "mattpocock/skills",
            "sourceType": "github",
            "sourceUrl": "https://github.com/mattpocock/skills.git",
            "skillPath": f"skills/{name}/SKILL.md",
            "skillFolderHash": name,
        }
        for name in EXPECTED_MATT_SKILLS
    }
    skills["find-skills"] = {
        "source": "vercel-labs/skills",
        "sourceType": "github",
        "sourceUrl": "https://github.com/vercel-labs/skills.git",
        "skillPath": "skills/find-skills/SKILL.md",
        "skillFolderHash": "vercel",
    }
    return {
        "version": 3,
        "skills": skills,
        "dismissed": {"keep": True},
        "lastSelectedAgents": ["keep"],
        "unknown": {"nested": [1, 2, 3]},
    }


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "source"
        self.home = base / "home"
        make_system(self.root, self.home)
        self.lock = self.home / ".agents" / ".skill-lock.json"
        write_json(self.lock, lock_fixture())
        self.system = SkillSystem(self.root, self.home)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_lock_dry_run_is_byte_preserving_and_reports_exact_names(self) -> None:
        before = self.lock.read_bytes()
        result = self.system.migrate_lock(apply=False)
        self.assertFalse(result.applied)
        self.assertEqual(tuple(sorted(EXPECTED_MATT_SKILLS)), result.removed)
        self.assertEqual(before, self.lock.read_bytes())

    def test_apply_preserves_vercel_ui_and_unknown_state_then_rolls_back_exactly(self) -> None:
        before = self.lock.read_bytes()
        result = self.system.migrate_lock(apply=True)
        after = json.loads(self.lock.read_text())

        self.assertTrue(result.applied)
        self.assertEqual(["find-skills"], sorted(after["skills"]))
        self.assertEqual({"keep": True}, after["dismissed"])
        self.assertEqual(["keep"], after["lastSelectedAgents"])
        self.assertEqual({"nested": [1, 2, 3]}, after["unknown"])

        rollback = self.system.rollback(result.operation_id, apply=True)
        self.assertTrue(rollback.applied)
        self.assertEqual(before, self.lock.read_bytes())

    def test_apply_is_idempotent_after_a_recorded_success(self) -> None:
        first = self.system.migrate_lock(apply=True)
        after = self.lock.read_bytes()

        second = self.system.migrate_lock(apply=True)

        self.assertTrue(first.applied)
        self.assertFalse(second.applied)
        self.assertEqual("already-current", second.reason)
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertEqual(after, self.lock.read_bytes())

    def test_interrupted_lock_replacement_is_detected_and_recoverable(self) -> None:
        original = self.lock.read_bytes()
        for phase in ("prepared", "lock-replaced"):
            with self.subTest(phase=phase):
                write_json(self.lock, lock_fixture())
                with self.assertRaises(InjectedFailure) as caught:
                    self.system.migrate_lock(apply=True, fail_after=phase)
                with self.assertRaises(IncompleteOperationError):
                    self.system.migrate_lock(apply=True)

                recovered = self.system.rollback(
                    caught.exception.operation_id,
                    apply=True,
                )

                self.assertTrue(recovered.applied)
                self.assertEqual(original, self.lock.read_bytes())

    def test_a_stop_before_the_lock_replacement_is_journaled_rolls_back(self) -> None:
        original = self.lock.read_bytes()
        with stop_before_journaling("lock-replaced"):
            with self.assertRaises(Stopped) as caught:
                self.system.migrate_lock(apply=True)

        self.system.rollback(caught.exception.operation_id, apply=True)

        self.assertEqual(original, self.lock.read_bytes())
        self.assertEqual((), self.system.status().incomplete_operations)

    def test_a_lock_rollback_stopped_before_its_journal_write_resumes(self) -> None:
        original = self.lock.read_bytes()
        migrated = self.system.migrate_lock(apply=True)
        write_journal = operations.SkillSystem._write_journal

        def stop_at_rolled_back(system, transaction, journal):
            if journal["status"] == "rolled-back":
                raise Stopped(journal["operation_id"])
            write_journal(system, transaction, journal)

        with patch.object(operations.SkillSystem, "_write_journal", stop_at_rolled_back):
            with self.assertRaises(Stopped):
                self.system.rollback(migrated.operation_id, apply=True)
        self.assertEqual(
            (migrated.operation_id,), self.system.status().incomplete_operations
        )
        with self.assertRaises(IncompleteOperationError):
            self.system.migrate_lock(apply=True)

        resumed = self.system.rollback(migrated.operation_id, apply=True)

        self.assertEqual("rolled-back", resumed.reason)
        self.assertEqual(original, self.lock.read_bytes())

    def test_schema_provenance_and_expected_set_mismatch_fail_before_write(self) -> None:
        cases = []
        unknown_version = lock_fixture()
        unknown_version["version"] = 4
        cases.append(unknown_version)

        missing = lock_fixture()
        del missing["skills"][next(iter(EXPECTED_MATT_SKILLS))]
        cases.append(missing)

        wrong_owner = lock_fixture()
        wrong_owner["skills"][next(iter(EXPECTED_MATT_SKILLS))][
            "source"
        ] = "someone/else"
        cases.append(wrong_owner)

        for fixture in cases:
            with self.subTest(fixture=fixture):
                write_json(self.lock, fixture)
                before = self.lock.read_bytes()
                with self.assertRaises(ValidationError):
                    self.system.migrate_lock(apply=True)
                self.assertEqual(before, self.lock.read_bytes())

    def test_malformed_and_already_migrated_lock_fail_without_changes(self) -> None:
        self.lock.write_text("{")
        before = self.lock.read_bytes()
        with self.assertRaisesRegex(ValidationError, "lock"):
            self.system.migrate_lock(apply=True)
        self.assertEqual(before, self.lock.read_bytes())

        fixture = lock_fixture()
        fixture["skills"] = {"find-skills": fixture["skills"]["find-skills"]}
        write_json(self.lock, fixture)
        before = tree_snapshot(self.home)
        with self.assertRaisesRegex(ValidationError, "expected Matt"):
            self.system.migrate_lock(apply=True)
        self.assertEqual(before, tree_snapshot(self.home))

    def test_quarantine_is_dry_run_safe_and_rollback_restores_exact_tree(self) -> None:
        target = self.home / ".agents" / "skills" / "alpha"
        self.system.install("alpha", apply=True)
        before = tree_snapshot(target)

        preview = self.system.quarantine("alpha", apply=False)
        self.assertFalse(preview.applied)
        self.assertEqual(before, tree_snapshot(target))

        moved = self.system.quarantine("alpha", apply=True)
        self.assertTrue(moved.applied)
        self.assertFalse(target.exists())
        self.assertEqual(before, tree_snapshot(moved.quarantine_path))

        restored = self.system.rollback(moved.operation_id, apply=True)
        self.assertTrue(restored.applied)
        self.assertEqual(before, tree_snapshot(target))

    def test_quarantine_dry_run_validates_state_before_reporting_safe(self) -> None:
        self.system.install("alpha", apply=True)
        state_path = (
            self.home / ".agents" / ".skill-system" / "install-state.json"
        )
        state = json.loads(state_path.read_text())
        state["managed"]["alpha"]["target_hash"] = "not-a-hash"
        write_json(state_path, state)

        with self.assertRaisesRegex(ValidationError, "target_hash"):
            self.system.quarantine("alpha", apply=False)

    def test_interrupted_quarantine_phases_are_recoverable(self) -> None:
        target = self.home / ".agents" / "skills" / "alpha"
        self.system.install("alpha", apply=True)
        before = tree_snapshot(target)

        for phase in ("prepared", "target-quarantined", "state-committed"):
            with self.subTest(phase=phase):
                with self.assertRaises(InjectedFailure) as caught:
                    self.system.quarantine(
                        "alpha",
                        apply=True,
                        fail_after=phase,
                    )
                with self.assertRaises(IncompleteOperationError):
                    self.system.quarantine("alpha", apply=True)

                restored = self.system.rollback(
                    caught.exception.operation_id,
                    apply=True,
                )

                self.assertTrue(restored.applied)
                self.assertEqual(before, tree_snapshot(target))

    def test_a_stop_before_the_quarantine_move_is_journaled_rolls_back(self) -> None:
        target = self.home / ".agents" / "skills" / "alpha"
        self.system.install("alpha", apply=True)
        before = tree_snapshot(target)
        with stop_before_journaling("target-quarantined"):
            with self.assertRaises(Stopped) as caught:
                self.system.quarantine("alpha", apply=True)

        self.system.rollback(caught.exception.operation_id, apply=True)

        status = self.system.status()
        self.assertEqual("current", status.skills["alpha"].state)
        self.assertEqual((), status.incomplete_operations)
        self.assertEqual(before, tree_snapshot(target))

    def test_a_stopped_quarantine_rollback_resumes(self) -> None:
        target = self.home / ".agents" / "skills" / "alpha"
        self.system.install("alpha", apply=True)
        before = tree_snapshot(target)
        moved = self.system.quarantine("alpha", apply=True)
        write_bytes = operations.atomic_write_bytes

        def fail_state_write(path: Path, value: bytes, mode: int = 0o600) -> None:
            if path == self.system.state_path:
                raise OSError("injected install-state write failure")
            write_bytes(path, value, mode)

        with patch.object(operations, "atomic_write_bytes", fail_state_write):
            with self.assertRaises(OSError):
                self.system.rollback(moved.operation_id, apply=True)
        self.assertEqual(
            (moved.operation_id,), self.system.status().incomplete_operations
        )

        self.system.rollback(moved.operation_id, apply=True)

        status = self.system.status()
        self.assertEqual("current", status.skills["alpha"].state)
        self.assertEqual((), status.incomplete_operations)
        self.assertEqual(before, tree_snapshot(target))

    def test_quarantine_rollback_refuses_to_cross_newer_target_history(self) -> None:
        target = self.home / ".agents" / "skills" / "alpha"
        first_install = self.system.install("alpha", apply=True)
        first_quarantine = self.system.quarantine("alpha", apply=True)

        source = self.root / "skills" / "alpha" / "SKILL.md"
        source.write_text(source.read_text() + "\nsecond version\n")
        second_install = self.system.install("alpha", apply=True)
        second_quarantine = self.system.quarantine("alpha", apply=True)
        before = tree_snapshot(self.home)

        with self.assertRaisesRegex(CollisionError, "newer operation"):
            self.system.rollback(first_quarantine.operation_id, apply=True)

        self.assertEqual(before, tree_snapshot(self.home))
        self.system.rollback(second_quarantine.operation_id, apply=True)
        self.system.rollback(second_install.operation_id, apply=True)
        self.system.rollback(first_quarantine.operation_id, apply=True)
        self.assertEqual(first_install.operation_id, json.loads(
            (
                self.home
                / ".agents"
                / ".skill-system"
                / "install-state.json"
            ).read_text()
        )["managed"]["alpha"]["operation_id"])
        self.assertTrue(target.is_dir())


if __name__ == "__main__":
    unittest.main()
