from __future__ import annotations

import fcntl
import json
import multiprocessing
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import skill_system.operations as operations
from skill_system import (
    CollisionError,
    IncompleteOperationError,
    InjectedFailure,
    LockBusyError,
    SkillSystem,
    ValidationError,
    content_hash,
)
from tests.helpers import (
    Stopped,
    make_system,
    stop_before_journaling,
    tree_snapshot,
    write_json,
)


def hold_lock(lock_path: str, ready: multiprocessing.connection.Connection) -> None:
    with Path(lock_path).open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        ready.send("locked")
        ready.recv()


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "source"
        self.home = base / "home"
        make_system(self.root, self.home)
        self.system = SkillSystem(self.root, self.home)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def target(self) -> Path:
        return self.home / ".agents" / "skills" / "alpha"

    @property
    def state_path(self) -> Path:
        return self.home / ".agents" / ".skill-system" / "install-state.json"

    def test_dry_run_is_byte_preserving(self) -> None:
        before = tree_snapshot(self.home)
        result = self.system.install("alpha", apply=False)
        self.assertFalse(result.applied)
        self.assertEqual(before, tree_snapshot(self.home))
        self.assertFalse(self.target.exists())

    def test_first_install_and_repeat_are_idempotent(self) -> None:
        first = self.system.install("alpha", apply=True)
        first_target_hash = content_hash(self.target)
        first_state = self.state_path.read_bytes()

        second = self.system.install("alpha", apply=True)

        self.assertTrue(first.applied)
        self.assertFalse(second.applied)
        self.assertEqual(second.reason, "already-current")
        self.assertEqual(first_target_hash, content_hash(self.target))
        self.assertEqual(first_state, self.state_path.read_bytes())

    def test_install_flushes_new_transaction_and_staging_parent_entries(self) -> None:
        with patch(
            "skill_system.operations._fsync_directory",
            wraps=operations._fsync_directory,
        ) as flush:
            result = self.system.install("alpha", apply=True)

        transaction = self.system.transactions / result.operation_id
        flushed = [call.args[0] for call in flush.call_args_list]
        self.assertIn(self.system.agents_root, flushed)
        self.assertIn(transaction.parent, flushed)
        self.assertIn(transaction / "staged", flushed)
        self.assertLess(
            flushed.index(transaction.parent),
            flushed.index(transaction),
        )

    def test_source_update_replaces_unchanged_managed_target_and_rolls_back(self) -> None:
        first = self.system.install("alpha", apply=True)
        old_bytes = (self.target / "SKILL.md").read_bytes()
        source = self.root / "skills" / "alpha" / "SKILL.md"
        source.write_text(source.read_text() + "\nNew canonical behavior.\n")

        update = self.system.install("alpha", apply=True)
        self.assertIn(b"New canonical behavior", (self.target / "SKILL.md").read_bytes())

        rollback = self.system.rollback(update.operation_id, apply=True)
        self.assertTrue(rollback.applied)
        self.assertEqual(old_bytes, (self.target / "SKILL.md").read_bytes())
        state = json.loads(self.state_path.read_text())
        self.assertEqual(first.operation_id, state["managed"]["alpha"]["operation_id"])

    def test_refresh_dry_run_selects_only_managed_source_updates(self) -> None:
        names = ("alpha", "beta", "delta", "epsilon", "gamma")
        make_system(self.root, self.home, names)
        self.system = SkillSystem(self.root, self.home)
        for name in ("alpha", "beta", "epsilon"):
            self.system.install(name, apply=True)

        alpha_source = self.root / "skills" / "alpha" / "SKILL.md"
        alpha_source.write_text(alpha_source.read_text() + "\nalpha update\n")
        epsilon_source = self.root / "skills" / "epsilon" / "SKILL.md"
        epsilon_source.write_text(epsilon_source.read_text() + "\nepsilon update\n")
        epsilon_target = self.home / ".agents" / "skills" / "epsilon"
        (epsilon_target / "local.txt").write_text("preserve me")
        delta_target = self.home / ".agents" / "skills" / "delta"
        delta_target.mkdir(parents=True)
        (delta_target / "unmanaged.txt").write_text("preserve me")
        before = tree_snapshot(self.home)

        result = self.system.refresh(apply=False)

        self.assertFalse(result.applied)
        self.assertEqual("dry-run", result.reason)
        self.assertEqual(("alpha",), tuple(result.operations))
        self.assertEqual(("beta",), result.excluded["current"])
        self.assertEqual(("gamma",), result.excluded["absent"])
        self.assertEqual(
            ("delta",), result.excluded["unmanaged-collision"]
        )
        self.assertEqual(
            ("epsilon",), result.excluded["locally-modified"]
        )
        self.assertEqual(before, tree_snapshot(self.home))

    def test_refresh_applies_updates_in_order_and_reruns_idempotently(self) -> None:
        make_system(self.root, self.home, ("alpha", "beta", "gamma"))
        self.system = SkillSystem(self.root, self.home)
        for name in ("beta", "alpha"):
            self.system.install(name, apply=True)
            source = self.root / "skills" / name / "SKILL.md"
            source.write_text(source.read_text() + f"\n{name} update\n")

        result = self.system.refresh(apply=True)

        self.assertTrue(result.applied)
        self.assertEqual("refreshed", result.reason)
        self.assertEqual(("alpha", "beta"), tuple(result.operations))
        self.assertTrue(all(item.applied for item in result.operations.values()))
        self.assertNotEqual(
            result.operations["alpha"].operation_id,
            result.operations["beta"].operation_id,
        )
        status = self.system.status()
        self.assertEqual("current", status.skills["alpha"].state)
        self.assertEqual("current", status.skills["beta"].state)
        self.assertEqual("absent", status.skills["gamma"].state)

        repeated = self.system.refresh(apply=True)

        self.assertFalse(repeated.applied)
        self.assertEqual("nothing-to-refresh", repeated.reason)
        self.assertEqual({}, repeated.operations)
        self.assertEqual(("alpha", "beta"), repeated.excluded["current"])

    def test_refresh_preflights_every_candidate_before_writing(self) -> None:
        make_system(self.root, self.home, ("alpha", "beta"))
        self.system = SkillSystem(self.root, self.home)
        for name in ("alpha", "beta"):
            self.system.install(name, apply=True)
            source = self.root / "skills" / name / "SKILL.md"
            source.write_text(source.read_text() + f"\n{name} update\n")
        before = tree_snapshot(self.home)

        with patch(
            "skill_system.operations.same_filesystem",
            side_effect=(True, False),
        ):
            with self.assertRaisesRegex(ValidationError, "beta.*same filesystem"):
                self.system.refresh(apply=True)

        self.assertEqual(before, tree_snapshot(self.home))

    def test_refresh_excludes_retired_managed_skills(self) -> None:
        make_system(self.root, self.home, ("alpha", "beta"))
        self.system = SkillSystem(self.root, self.home)
        self.system.install("beta", apply=True)
        source = self.root / "skills" / "beta" / "SKILL.md"
        source.write_text(source.read_text() + "\nretired update\n")
        registry_path = self.root / "registry.json"
        registry = json.loads(registry_path.read_text())
        registry["skills"]["beta"]["lifecycle"] = "retired"
        write_json(registry_path, registry)

        result = self.system.refresh(apply=True)

        self.assertFalse(result.applied)
        self.assertEqual({}, result.operations)
        self.assertEqual(("beta",), result.excluded["lifecycle-retired"])
        self.assertEqual("source-updated", self.system.status().skills["beta"].state)

    def test_refresh_partial_interruption_uses_child_recovery_and_reruns(self) -> None:
        make_system(self.root, self.home, ("alpha", "beta"))
        self.system = SkillSystem(self.root, self.home)
        for name in ("alpha", "beta"):
            self.system.install(name, apply=True)
            source = self.root / "skills" / name / "SKILL.md"
            source.write_text(source.read_text() + f"\n{name} update\n")
        install_under_lock = self.system._install_under_lock

        def interrupt_beta(
            name: str,
            *,
            apply: bool,
            fail_after: str | None = None,
        ):
            if name == "beta":
                fail_after = "target-installed"
            return install_under_lock(
                name,
                apply=apply,
                fail_after=fail_after,
            )

        with patch.object(
            self.system,
            "_install_under_lock",
            side_effect=interrupt_beta,
        ):
            with self.assertRaises(InjectedFailure) as caught:
                self.system.refresh(apply=True)

        interrupted = caught.exception.operation_id
        status = self.system.status()
        self.assertEqual("current", status.skills["alpha"].state)
        self.assertIn(interrupted, status.incomplete_operations)
        with self.assertRaises(IncompleteOperationError):
            self.system.refresh(apply=True)

        self.system.rollback(interrupted, apply=True)
        recovered = self.system.refresh(apply=True)

        self.assertEqual(("beta",), tuple(recovered.operations))
        self.assertEqual("current", self.system.status().skills["beta"].state)

    def test_rollback_refuses_to_cross_newer_operations_on_the_same_target(self) -> None:
        source = self.root / "skills" / "alpha" / "SKILL.md"
        original = source.read_bytes()
        first = self.system.install("alpha", apply=True)

        source.write_bytes(original + b"\nsecond version\n")
        second = self.system.install("alpha", apply=True)
        source.write_bytes(original)
        third = self.system.install("alpha", apply=True)
        before = tree_snapshot(self.home)

        with self.assertRaisesRegex(CollisionError, "newer operation"):
            self.system.rollback(first.operation_id, apply=True)

        self.assertEqual(before, tree_snapshot(self.home))
        self.system.rollback(third.operation_id, apply=True)
        self.system.rollback(second.operation_id, apply=True)
        self.system.rollback(first.operation_id, apply=True)
        self.assertFalse(self.target.exists())

    def test_rollback_restores_only_its_own_skill_state(self) -> None:
        make_system(self.root, self.home, ("alpha", "beta"))
        alpha = self.system.install("alpha", apply=True)
        beta = self.system.install("beta", apply=True)

        self.system.rollback(alpha.operation_id, apply=True)
        status = self.system.status()
        self.assertEqual("absent", status.skills["alpha"].state)
        self.assertEqual("current", status.skills["beta"].state)

        self.system.rollback(beta.operation_id, apply=True)
        status = self.system.status()
        self.assertEqual("absent", status.skills["alpha"].state)
        self.assertEqual("absent", status.skills["beta"].state)

    def test_refused_rollback_changes_nothing_and_blocks_nothing(self) -> None:
        installed = self.system.install("alpha", apply=True)
        (self.target / "local.txt").write_text("local edit\n")
        before = tree_snapshot(self.home)

        with self.assertRaisesRegex(CollisionError, "changed after operation"):
            self.system.rollback(installed.operation_id, apply=True)

        self.assertEqual(before, tree_snapshot(self.home))
        self.assertEqual((), self.system.status().incomplete_operations)

    def test_unmanaged_collision_is_refused_without_changes(self) -> None:
        self.target.mkdir(parents=True)
        (self.target / "owned.txt").write_text("unmanaged")
        before = tree_snapshot(self.home)
        with self.assertRaisesRegex(CollisionError, "unmanaged"):
            self.system.install("alpha", apply=True)
        self.assertEqual(before, tree_snapshot(self.home))

    def test_locally_modified_managed_target_is_refused_and_preserved(self) -> None:
        self.system.install("alpha", apply=True)
        local = self.target / "local.txt"
        local.write_text("keep me")
        before = tree_snapshot(self.target)
        with self.assertRaisesRegex(CollisionError, "locally modified"):
            self.system.install("alpha", apply=True)
        self.assertEqual(before, tree_snapshot(self.target))

    def test_unknown_state_schema_and_malformed_state_fail_before_target_change(self) -> None:
        write_json(self.state_path, {"schema_version": 99, "managed": {}})
        with self.assertRaisesRegex(ValidationError, "state schema_version"):
            self.system.install("alpha", apply=True)
        self.assertFalse(self.target.exists())

        self.state_path.write_text("{")
        with self.assertRaisesRegex(ValidationError, "install-state.json"):
            self.system.install("alpha", apply=True)
        self.assertFalse(self.target.exists())

    def test_invalid_install_state_field_type_fails_before_target_change(self) -> None:
        self.system.install("alpha", apply=True)
        state = json.loads(self.state_path.read_text())
        state["managed"]["alpha"]["installed_at"] = 42
        write_json(self.state_path, state)
        before = tree_snapshot(self.target)

        with self.assertRaisesRegex(ValidationError, "installed_at"):
            self.system.install("alpha", apply=True)

        self.assertEqual(before, tree_snapshot(self.target))

    def test_install_state_hash_time_membership_and_paths_are_strict(self) -> None:
        self.system.install("alpha", apply=True)
        original = json.loads(self.state_path.read_text())
        cases = {
            "source_hash": lambda state: state["managed"]["alpha"].update(
                {"source_hash": "not-a-hash"}
            ),
            "installed_at": lambda state: state["managed"]["alpha"].update(
                {"installed_at": "not-a-timestamp"}
            ),
            "unknown managed skill": lambda state: state["managed"].update(
                {"ghost": dict(state["managed"]["alpha"])}
            ),
            "canonical source path": lambda state: state["managed"]["alpha"].update(
                {"source": "/tmp/not-the-canonical-source"}
            ),
        }

        for message, mutate in cases.items():
            with self.subTest(message=message):
                state = json.loads(json.dumps(original))
                mutate(state)
                write_json(self.state_path, state)
                with self.assertRaisesRegex(ValidationError, message):
                    self.system.audit()

    def test_exact_pending_live_quarantine_state_remains_auditable(self) -> None:
        self.system.install("alpha", apply=True)
        installed_hash = content_hash(self.target)
        registry_path = self.root / "registry.json"
        registry = json.loads(registry_path.read_text())
        record = registry["skills"]["alpha"]
        record["ownership"] = "legacy-unmanaged"
        record["lifecycle"] = "retired"
        del record["source"]
        record["provenance"].update(
            {
                "observed_hash": installed_hash,
                "disposition": "canonical-retired-pending-live-quarantine",
                "exit_phase": 4,
            }
        )
        write_json(registry_path, registry)
        shutil.rmtree(self.root / "skills" / "alpha")

        self.system.audit()
        status = self.system.status()
        preview = self.system.quarantine("alpha", apply=False)

        self.assertEqual(
            "retired-pending-live-quarantine",
            status.skills["alpha"].state,
        )
        self.assertFalse(preview.applied)
        self.assertEqual("dry-run", preview.reason)

    def test_pending_live_quarantine_state_requires_exact_hashes(self) -> None:
        self.system.install("alpha", apply=True)
        registry_path = self.root / "registry.json"
        registry = json.loads(registry_path.read_text())
        record = registry["skills"]["alpha"]
        record["ownership"] = "legacy-unmanaged"
        record["lifecycle"] = "retired"
        del record["source"]
        record["provenance"].update(
            {
                "observed_hash": "sha256:" + "0" * 64,
                "disposition": "canonical-retired-pending-live-quarantine",
                "exit_phase": 4,
            }
        )
        write_json(registry_path, registry)
        shutil.rmtree(self.root / "skills" / "alpha")

        with self.assertRaisesRegex(
            ValidationError,
            "pending live quarantine state hash disagrees",
        ):
            self.system.audit()

    def test_invalid_staged_skill_fails_before_target_change(self) -> None:
        (self.root / "skills" / "alpha" / "SKILL.md").write_text("invalid")
        with self.assertRaises(ValidationError):
            self.system.install("alpha", apply=True)
        self.assertFalse(self.target.exists())

    def test_interruption_phases_are_detected_and_recoverable(self) -> None:
        self.system.install("alpha", apply=True)
        source = self.root / "skills" / "alpha" / "SKILL.md"
        original = (self.target / "SKILL.md").read_bytes()
        source.write_text(source.read_text() + "\nupdated\n")

        for phase in (
            "prepared",
            "preimage-preserved",
            "target-installed",
            "state-committed",
        ):
            with self.subTest(phase=phase):
                if b"updated" not in source.read_bytes():
                    source.write_text(source.read_text() + "\nupdated\n")
                with self.assertRaises(InjectedFailure) as caught:
                    self.system.install("alpha", apply=True, fail_after=phase)
                with self.assertRaises(IncompleteOperationError):
                    self.system.install("alpha", apply=True)
                recovery = self.system.rollback(
                    caught.exception.operation_id, apply=True
                )
                self.assertTrue(recovery.applied)
                self.assertEqual(original, (self.target / "SKILL.md").read_bytes())

    def test_stops_between_a_rename_and_its_journal_write_roll_back(self) -> None:
        with stop_before_journaling("target-installed"):
            with self.assertRaises(Stopped) as caught:
                self.system.install("alpha", apply=True)
        self.system.rollback(caught.exception.operation_id, apply=True)
        status = self.system.status()
        self.assertEqual("absent", status.skills["alpha"].state)
        self.assertEqual((), status.incomplete_operations)
        self.assertFalse(self.target.exists())

        self.system.install("alpha", apply=True)
        before = tree_snapshot(self.target)
        source = self.root / "skills" / "alpha" / "SKILL.md"
        source.write_text(source.read_text() + "\nupdated\n")
        expected = self.system.status().skills["alpha"].state
        for phase in ("preimage-preserved", "target-installed"):
            with self.subTest(phase=phase):
                with stop_before_journaling(phase):
                    with self.assertRaises(Stopped) as caught:
                        self.system.install("alpha", apply=True)
                self.system.rollback(caught.exception.operation_id, apply=True)
                status = self.system.status()
                self.assertEqual(expected, status.skills["alpha"].state)
                self.assertEqual((), status.incomplete_operations)
                self.assertEqual(before, tree_snapshot(self.target))

    def test_a_stopped_rollback_stays_incomplete_and_resumes(self) -> None:
        make_system(self.root, self.home, ("alpha", "beta"))
        self.system.install("beta", apply=True)
        installed = self.system.install("alpha", apply=True)
        write_bytes = operations.atomic_write_bytes

        def fail_state_write(path: Path, value: bytes, mode: int = 0o600) -> None:
            if path == self.system.state_path:
                raise OSError("injected install-state write failure")
            write_bytes(path, value, mode)

        with patch.object(operations, "atomic_write_bytes", fail_state_write):
            with self.assertRaises(OSError):
                self.system.rollback(installed.operation_id, apply=True)
        self.assertEqual(
            (installed.operation_id,), self.system.status().incomplete_operations
        )
        with self.assertRaises(IncompleteOperationError):
            self.system.install("alpha", apply=True)

        resumed = self.system.rollback(installed.operation_id, apply=True)

        self.assertEqual("rolled-back", resumed.reason)
        status = self.system.status()
        self.assertEqual((), status.incomplete_operations)
        self.assertEqual("absent", status.skills["alpha"].state)
        self.assertEqual("current", status.skills["beta"].state)

    def test_lock_contention_is_immediate_and_lingering_file_is_harmless(self) -> None:
        lock_path = (
            self.home / ".agents" / ".skill-system" / "operation.lock"
        )
        parent, child = multiprocessing.Pipe()
        process = multiprocessing.Process(
            target=hold_lock, args=(str(lock_path), child)
        )
        process.start()
        self.assertEqual("locked", parent.recv())
        try:
            with self.assertRaises(LockBusyError):
                self.system.install("alpha", apply=True)
        finally:
            parent.send("release")
            process.join(5)
        self.assertEqual(0, process.exitcode)

        lock_path.write_text("lingering path is not ownership")
        result = self.system.install("alpha", apply=True)
        self.assertTrue(result.applied)

    def test_cross_filesystem_projection_is_refused_before_writes(self) -> None:
        before = tree_snapshot(self.home)
        with patch("skill_system.operations.same_filesystem", return_value=False):
            with self.assertRaisesRegex(ValidationError, "same filesystem"):
                self.system.install("alpha", apply=True)
        self.assertEqual(before, tree_snapshot(self.home))

    def test_reconciliation_reports_current_modified_and_unmanaged(self) -> None:
        self.system.install("alpha", apply=True)
        self.assertEqual("current", self.system.status().skills["alpha"].state)

        (self.target / "local.txt").write_text("drift")
        self.assertEqual("locally-modified", self.system.status().skills["alpha"].state)

        self.state_path.unlink()
        self.assertEqual("unmanaged-collision", self.system.status().skills["alpha"].state)

    def test_operation_journal_phase_and_details_are_strict(self) -> None:
        installed = self.system.install("alpha", apply=True)
        journal_path = (
            self.home
            / ".agents"
            / ".skill-system"
            / "transactions"
            / installed.operation_id
            / "operation.json"
        )
        journal = json.loads(journal_path.read_text())
        journal["phase"] = "invented"
        write_json(journal_path, journal)
        with self.assertRaisesRegex(ValidationError, "phase"):
            self.system.rollback(installed.operation_id, apply=False)

        journal["phase"] = "committed"
        journal["details"]["unexpected"] = True
        write_json(journal_path, journal)
        with self.assertRaisesRegex(ValidationError, "unknown field"):
            self.system.rollback(installed.operation_id, apply=False)

        del journal["details"]["unexpected"]
        journal["created_at"] = "not-a-timestamp"
        write_json(journal_path, journal)
        with self.assertRaisesRegex(ValidationError, "created_at"):
            self.system.rollback(installed.operation_id, apply=False)


class SyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "source"
        self.home = base / "home"
        make_system(
            self.root,
            self.home,
            ("alpha", "beta", "gamma", "delta", "epsilon", "zeta"),
        )
        self.system = SkillSystem(self.root, self.home)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _target(self, name: str) -> Path:
        return self.home / ".agents" / "skills" / name

    def _state_path(self) -> Path:
        return self.home / ".agents" / ".skill-system" / "install-state.json"

    def _seed_state(self) -> None:
        # beta: current (installed, unchanged)
        self.system.install("beta", apply=True)
        # alpha: source-updated (installed, then canonical source changed)
        self.system.install("alpha", apply=True)
        alpha_source = self.root / "skills" / "alpha" / "SKILL.md"
        alpha_source.write_text(alpha_source.read_text() + "\nalpha update\n")
        # gamma: absent (never installed)
        # delta: unmanaged-collision (live dir, no managed state)
        delta_target = self._target("delta")
        delta_target.mkdir(parents=True)
        (delta_target / "unmanaged.txt").write_text("preserve me")
        # epsilon: locally-modified (installed, then live target edited)
        self.system.install("epsilon", apply=True)
        epsilon_target = self._target("epsilon")
        (epsilon_target / "local.txt").write_text("local edit")
        # zeta: retired custom skill (installed, then marked retired)
        self.system.install("zeta", apply=True)
        registry_path = self.root / "registry.json"
        registry = json.loads(registry_path.read_text())
        registry["skills"]["zeta"]["lifecycle"] = "retired"
        write_json(registry_path, registry)

    def test_sync_dry_run_selects_absent_and_source_updated_warns_collisions(self) -> None:
        self._seed_state()
        before = tree_snapshot(self.home)

        result = self.system.sync(apply=False, force=False)

        self.assertFalse(result.applied)
        self.assertEqual("dry-run", result.reason)
        self.assertEqual(
            ("alpha", "gamma"), tuple(result.operations)
        )
        self.assertEqual(("beta",), result.excluded["current"])
        self.assertEqual(
            ("delta",), result.excluded["unmanaged-collision"]
        )
        self.assertEqual(
            ("epsilon",), result.excluded["locally-modified"]
        )
        self.assertEqual(("zeta",), result.excluded["lifecycle-retired"])
        self.assertEqual(before, tree_snapshot(self.home))

    def test_sync_applies_absent_and_source_updated_and_is_idempotent(self) -> None:
        self._seed_state()

        result = self.system.sync(apply=True, force=False)

        self.assertTrue(result.applied)
        self.assertEqual("synced", result.reason)
        self.assertEqual(
            ("alpha", "gamma"), tuple(result.operations)
        )
        self.assertTrue(all(item.applied for item in result.operations.values()))
        status = self.system.status()
        self.assertEqual("current", status.skills["alpha"].state)
        self.assertEqual("current", status.skills["gamma"].state)
        # collisions untouched without force
        self.assertEqual(
            "unmanaged-collision", status.skills["delta"].state
        )
        self.assertEqual(
            "locally-modified", status.skills["epsilon"].state
        )

        repeated = self.system.sync(apply=True, force=False)
        self.assertFalse(repeated.applied)
        self.assertEqual("nothing-to-sync", repeated.reason)
        self.assertEqual({}, repeated.operations)

    def test_sync_without_force_preserves_collision_targets(self) -> None:
        self._seed_state()
        delta_target = self._target("delta")
        epsilon_target = self._target("epsilon")
        delta_before = (delta_target / "unmanaged.txt").read_bytes()
        epsilon_before = (epsilon_target / "local.txt").read_bytes()

        self.system.sync(apply=True, force=False)

        self.assertEqual(
            delta_before, (delta_target / "unmanaged.txt").read_bytes()
        )
        self.assertEqual(
            epsilon_before, (epsilon_target / "local.txt").read_bytes()
        )

    def test_sync_with_force_adopts_collisions_and_preserves_preimage(self) -> None:
        self._seed_state()
        delta_target = self._target("delta")
        epsilon_target = self._target("epsilon")
        delta_before = (delta_target / "unmanaged.txt").read_bytes()
        epsilon_before = (epsilon_target / "local.txt").read_bytes()

        result = self.system.sync(apply=True, force=True)

        self.assertTrue(result.applied)
        self.assertEqual("synced", result.reason)
        # install candidates (absent + source-updated) before force candidates
        self.assertEqual(
            ("alpha", "gamma", "delta", "epsilon"),
            tuple(result.operations),
        )
        self.assertTrue(all(item.applied for item in result.operations.values()))
        status = self.system.status()
        for name in ("alpha", "delta", "epsilon", "gamma"):
            self.assertEqual("current", status.skills[name].state)
        # canonical content now live
        alpha_source = (self.root / "skills" / "alpha" / "SKILL.md").read_bytes()
        self.assertEqual(
            alpha_source, (self._target("alpha") / "SKILL.md").read_bytes()
        )
        self.assertFalse((delta_target / "unmanaged.txt").exists())
        self.assertFalse((epsilon_target / "local.txt").exists())

        # rollback restores the displaced collision content
        delta_op = result.operations["delta"].operation_id
        self.system.rollback(delta_op, apply=True)
        self.assertEqual(
            delta_before,
            (self._target("delta") / "unmanaged.txt").read_bytes(),
        )
        epsilon_op = result.operations["epsilon"].operation_id
        self.system.rollback(epsilon_op, apply=True)
        self.assertEqual(
            epsilon_before,
            (self._target("epsilon") / "local.txt").read_bytes(),
        )

    def test_sync_force_dry_run_previews_collisions_without_writing(self) -> None:
        self._seed_state()
        before = tree_snapshot(self.home)

        result = self.system.sync(apply=False, force=True)

        self.assertFalse(result.applied)
        self.assertEqual("dry-run", result.reason)
        self.assertEqual(
            ("alpha", "gamma", "delta", "epsilon"),
            tuple(result.operations),
        )
        self.assertNotIn("unmanaged-collision", result.excluded)
        self.assertNotIn("locally-modified", result.excluded)
        self.assertEqual(before, tree_snapshot(self.home))

    def test_sync_excludes_retired_and_reports_lifecycle_reason(self) -> None:
        self._seed_state()
        result = self.system.sync(apply=True, force=True)
        # zeta is retired: never a candidate even with force
        self.assertNotIn("zeta", result.operations)
        self.assertEqual(("zeta",), result.excluded["lifecycle-retired"])


if __name__ == "__main__":
    unittest.main()
