from __future__ import annotations

import concurrent.futures
import fcntl
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime import ReviewAfterCommit, ReviewKind, ReviewMode
from runtime import review_core as core
from runtime.analysis.evidence_package import ReviewScanError
from runtime.analysis.model import AnalysisStatus
from runtime.analysis.outcomes import OutcomeStore, OutcomeStoreError


class ReviewAfterCommitCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo with space"
        self.state_dir = self.root / "state"
        self._init_repo(self.repo)

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.strip()

    def _init_repo(self, path: Path) -> None:
        self._git("init", "-q", str(path), cwd=self.root)
        self._git("-C", str(path), "config", "user.email", "hook-test@example.invalid")
        self._git("-C", str(path), "config", "user.name", "Hook Test")
        self._git("-C", str(path), "commit", "--allow-empty", "-qm", "initial")

    def _reviewer(
        self,
        *,
        branch_every: int | None = None,
        standard_every: int = 1,
        state_dir: Path | None = None,
        mode: ReviewMode = ReviewMode.CADENCE,
        outcome_store: OutcomeStore | None = None,
    ) -> ReviewAfterCommit:
        return ReviewAfterCommit(
            state_dir or self.state_dir,
            branch_every,
            standard_every,
            mode,
            outcome_store,
        )

    def _commit_event(
        self,
        reviewer: ReviewAfterCommit,
        *,
        tool_id: str,
        message: str,
        repo: Path | None = None,
        session_id: str = "session-1",
    ):
        target_repo = repo or self.repo
        command = "git commit --allow-empty -m {}".format(message)
        targets = reviewer.find_commit_targets(command, str(target_repo))
        reviewer.record_before(session_id, tool_id, targets)
        self._git("-C", str(target_repo), "commit", "--allow-empty", "-qm", message)
        return reviewer.review_event(session_id, tool_id)

    def _state_path(self, session_id: str = "session-1") -> Path:
        key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return self.state_dir / "{}.json".format(key)

    def test_exact_full_range_and_hashed_repository_are_emitted(self) -> None:
        before = self._git("rev-parse", "HEAD")
        decision = self._commit_event(
            self._reviewer(), tool_id="tool-1", message="change"
        )
        after = self._git("rev-parse", "HEAD")

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(ReviewKind.RECENT, decision.kind)
        self.assertEqual((1,), decision.counts)
        self.assertEqual(1, len(decision.requests))
        request = decision.requests[0]
        self.assertEqual(before, request.commit_range.before)
        self.assertEqual(after, request.commit_range.after)
        self.assertEqual(1, request.commit_range.commits)
        self.assertTrue(request.repository.digest.startswith("sha256:"))
        self.assertNotIn(str(self.repo), request.to_json())
        self.assertEqual("read-only-advisory-review", request.authority.value)
        self.assertEqual(core.EXPECTED_DIFF_REVIEW, request.expected_skill)

    def test_initial_commit_uses_the_repository_empty_tree(self) -> None:
        new_repo = self.root / "created by tool"
        reviewer = self._reviewer()
        command = (
            "mkdir -p '{}' && cd '{}' && git init -q && "
            "git commit --allow-empty -m initial"
        ).format(new_repo, new_repo)
        targets = reviewer.find_commit_targets(command, str(self.root))
        reviewer.record_before("session-1", "tool-1", targets)
        self._git("init", "-q", str(new_repo), cwd=self.root)
        self._git("-C", str(new_repo), "config", "user.email", "hook-test@example.invalid")
        self._git("-C", str(new_repo), "config", "user.name", "Hook Test")
        self._git("-C", str(new_repo), "commit", "--allow-empty", "-qm", "initial")

        decision = reviewer.review_event("session-1", "tool-1")

        assert decision is not None
        expected_empty = self._git(
            "-C", str(new_repo), "hash-object", "-t", "tree", "--stdin"
        )
        self.assertEqual(expected_empty, decision.requests[0].commit_range.before)
        self.assertEqual(
            self._git("-C", str(new_repo), "rev-parse", "HEAD"),
            decision.requests[0].commit_range.after,
        )

    def test_parser_preserves_legacy_dry_run_and_command_position_rules(self) -> None:
        reviewer = self._reviewer()
        for command in (
            "git status",
            "echo git commit -m example",
            "echo 'git commit -m example'",
            "git commit --dry-run",
        ):
            with self.subTest(command=command):
                self.assertEqual([], reviewer.find_commit_targets(command, str(self.repo)))
        for command in (
            "git commit --allow-empty -m --dry-run",
            "git commit --allow-empty -am --dry-run",
            "git commit -m change -- --dry-run",
            "command git -c commit.gpgsign=false commit -m change",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    1, len(reviewer.find_commit_targets(command, str(self.repo)))
                )

    def test_git_global_options_and_cd_are_supported(self) -> None:
        reviewer = self._reviewer()
        for command, expected_cwd in (
            (
                "git -C '{}' -c commit.gpgsign=false commit -m change".format(
                    self.repo
                ),
                self.root.resolve(),
            ),
            (
                "cd '{}' && git commit -m change".format(self.repo),
                self.repo.resolve(),
            ),
        ):
            with self.subTest(command=command):
                targets = reviewer.find_commit_targets(command, str(self.root))
                self.assertEqual(1, len(targets))
                self.assertEqual(str(expected_cwd), targets[0]["cwd"])

    def test_standard_and_branch_cadences_are_independent(self) -> None:
        reviewer = self._reviewer(branch_every=6, standard_every=2)
        decisions = [
            self._commit_event(
                reviewer,
                tool_id="tool-{}".format(index),
                message="change-{}".format(index),
            )
            for index in range(1, 7)
        ]

        self.assertIsNone(decisions[0])
        self.assertEqual(ReviewKind.RECENT, decisions[1].kind)
        self.assertIsNone(decisions[2])
        self.assertEqual(ReviewKind.RECENT, decisions[3].kind)
        self.assertIsNone(decisions[4])
        self.assertEqual(ReviewKind.BRANCH, decisions[5].kind)

    def test_multiple_commits_advance_exact_counts_and_select_branch(self) -> None:
        reviewer = self._reviewer(branch_every=2)
        command = "git commit --allow-empty -m one && git commit --allow-empty -m two"
        targets = reviewer.find_commit_targets(command, str(self.repo))
        before = self._git("rev-parse", "HEAD")
        reviewer.record_before("session-1", "tool-1", targets)
        self._git("commit", "--allow-empty", "-qm", "one")
        self._git("commit", "--allow-empty", "-qm", "two")
        after = self._git("rev-parse", "HEAD")

        decision = reviewer.review_event("session-1", "tool-1")

        assert decision is not None
        self.assertEqual(ReviewKind.BRANCH, decision.kind)
        self.assertEqual((1, 2), decision.counts)
        self.assertEqual(before, decision.requests[0].commit_range.before)
        self.assertEqual(after, decision.requests[0].commit_range.after)
        self.assertEqual(2, decision.requests[0].commit_range.commits)
        next_decision = self._commit_event(
            reviewer, tool_id="tool-2", message="three"
        )
        self.assertEqual(ReviewKind.RECENT, next_decision.kind)
        self.assertEqual((3,), next_decision.counts)

    def test_one_event_across_repositories_emits_every_exact_range(self) -> None:
        second_repo = self.root / "second repo"
        self._init_repo(second_repo)
        reviewer = self._reviewer()
        command = (
            "git -C '{}' commit --allow-empty -m one && "
            "git -C '{}' commit --allow-empty -m two"
        ).format(self.repo, second_repo)
        targets = reviewer.find_commit_targets(command, str(self.root))
        before = {
            self._git("-C", str(repo), "rev-parse", "HEAD")
            for repo in (self.repo, second_repo)
        }
        reviewer.record_before("session-1", "tool-1", targets)
        self._git("-C", str(self.repo), "commit", "--allow-empty", "-qm", "one")
        self._git("-C", str(second_repo), "commit", "--allow-empty", "-qm", "two")

        decision = reviewer.review_event("session-1", "tool-1")

        assert decision is not None
        self.assertEqual(ReviewKind.BRANCH, decision.kind)
        self.assertEqual((1, 2), decision.counts)
        self.assertEqual(2, len(decision.requests))
        self.assertEqual(before, {item.commit_range.before for item in decision.requests})
        self.assertEqual(
            {
                self._git("-C", str(repo), "rev-parse", "HEAD")
                for repo in (self.repo, second_repo)
            },
            {item.commit_range.after for item in decision.requests},
        )
        self.assertEqual(
            2, len({item.repository.digest for item in decision.requests})
        )

    def test_duplicate_event_replays_request_without_advancing_counter(self) -> None:
        reviewer = self._reviewer(branch_every=2)
        first = self._commit_event(
            reviewer, tool_id="same-tool", message="one"
        )
        duplicate = reviewer.review_event("session-1", "same-tool")
        second = self._commit_event(
            reviewer, tool_id="next-tool", message="two"
        )

        self.assertEqual(first, duplicate)
        self.assertEqual((1,), duplicate.counts)
        self.assertEqual(ReviewKind.BRANCH, second.kind)
        self.assertEqual((2,), second.counts)

    def test_discard_pending_is_idempotent_and_never_discards_a_recorded_event(self) -> None:
        reviewer = self._reviewer()
        targets = reviewer.find_commit_targets(
            "git commit --allow-empty -m discarded", str(self.repo)
        )
        reviewer.record_before("session-1", "discarded", targets)
        reviewer.discard_pending("session-1", "discarded")
        reviewer.discard_pending("session-1", "discarded")
        self.assertIsNone(reviewer.review_event("session-1", "discarded"))

        targets = reviewer.find_commit_targets(
            "git commit --allow-empty -m kept", str(self.repo)
        )
        reviewer.record_before("session-1", "kept", targets)
        self._git("commit", "--allow-empty", "-qm", "kept")
        recorded = reviewer.review_event("session-1", "kept")
        reviewer.discard_pending("session-1", "kept")
        self.assertEqual(recorded, reviewer.review_event("session-1", "kept"))

    def test_counter_is_isolated_by_session(self) -> None:
        reviewer = self._reviewer(branch_every=2)
        first = self._commit_event(
            reviewer, tool_id="tool-1", message="one", session_id="session-1"
        )
        second = self._commit_event(
            reviewer, tool_id="tool-2", message="two", session_id="session-2"
        )

        self.assertEqual(ReviewKind.RECENT, first.kind)
        self.assertEqual(ReviewKind.RECENT, second.kind)
        self.assertEqual((1,), first.counts)
        self.assertEqual((1,), second.counts)

    def test_overlapping_same_repository_observations_do_not_double_count(self) -> None:
        reviewer = self._reviewer(branch_every=3)
        first = reviewer.find_commit_targets(
            "git commit --allow-empty -m one", str(self.repo)
        )
        second = reviewer.find_commit_targets(
            "git commit --allow-empty -m two", str(self.repo)
        )
        reviewer.record_before("session-1", "tool-1", first)
        reviewer.record_before("session-1", "tool-2", second)
        self._git("commit", "--allow-empty", "-qm", "one")
        self._git("commit", "--allow-empty", "-qm", "two")

        first_decision = reviewer.review_event("session-1", "tool-1")
        second_decision = reviewer.review_event("session-1", "tool-2")
        third_decision = self._commit_event(
            reviewer, tool_id="tool-3", message="three"
        )

        self.assertEqual((1, 2), first_decision.counts)
        self.assertIsNone(second_decision)
        self.assertEqual((3,), third_decision.counts)
        self.assertEqual(ReviewKind.BRANCH, third_decision.kind)

    def test_concurrent_post_events_do_not_lose_counts(self) -> None:
        reviewer = self._reviewer(branch_every=9)
        event_repos = []
        for index in range(8):
            repo = self.root / "concurrent-{}".format(index)
            self._init_repo(repo)
            tool_id = "tool-{}".format(index)
            command = "git -C '{}' commit --allow-empty -m change".format(repo)
            reviewer.record_before(
                "session-1",
                tool_id,
                reviewer.find_commit_targets(command, str(self.root)),
            )
            self._git("-C", str(repo), "commit", "--allow-empty", "-qm", "change")
            event_repos.append(tool_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            decisions = list(
                pool.map(
                    lambda tool_id: reviewer.review_event("session-1", tool_id),
                    event_repos,
                )
            )
        self.assertTrue(all(decision is not None for decision in decisions))
        ninth = self._commit_event(
            reviewer, tool_id="tool-9", message="ninth"
        )
        self.assertEqual((9,), ninth.counts)
        self.assertEqual(ReviewKind.BRANCH, ninth.kind)

    def test_git_probe_runs_without_holding_the_state_lock(self) -> None:
        reviewer = self._reviewer()
        targets = reviewer.find_commit_targets(
            "git commit --allow-empty -m one", str(self.repo)
        )
        reviewer.record_before("session-1", "tool-1", targets)
        self._git("commit", "--allow-empty", "-qm", "one")
        lock_path = self._state_path().with_suffix(".lock")
        original = core._commit_observations_after

        def assert_unlocked(snapshots):
            with lock_path.open("a+", encoding="utf-8") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return original(snapshots)

        with mock.patch.object(core, "_commit_observations_after", assert_unlocked):
            decision = reviewer.review_event("session-1", "tool-1")

        self.assertIsNotNone(decision)

    def test_noncontiguous_head_movement_fails_loudly(self) -> None:
        self._git("branch", "other")
        self._git("commit", "--allow-empty", "-qm", "advance-main")
        reviewer = self._reviewer()
        targets = reviewer.find_commit_targets(
            "git commit --allow-empty -m one", str(self.repo)
        )
        reviewer.record_before("session-1", "tool-1", targets)
        self._git("switch", "-q", "other")
        self._git("commit", "--allow-empty", "-qm", "one")

        with self.assertRaisesRegex(ValueError, "HEAD moved before"):
            reviewer.review_event("session-1", "tool-1")

    def test_repeated_reflog_lines_have_distinct_identities(self) -> None:
        target = {"cwd": str(self.repo), "argv": [core.TRUSTED_GIT]}
        before_first = core._resolve_target(target)
        head = self._git("rev-parse", "HEAD")
        line = (
            "{} {} Hook Test <hook-test@example.invalid> 0 +0000"
            "\tcommit: synthetic duplicate\n"
        ).format(head, head).encode("ascii")
        head_log = Path(before_first["head_log"])
        with head_log.open("ab") as stream:
            stream.write(line)
        first = core._new_commit_observations(before_first)

        before_second = core._resolve_target(target)
        with head_log.open("ab") as stream:
            stream.write(line)
        second = core._new_commit_observations(before_second)

        self.assertEqual(1, len(first))
        self.assertEqual(1, len(second))
        self.assertNotEqual(first[0].identity, second[0].identity)

    def test_legacy_state_is_rejected_without_rewrite(self) -> None:
        reviewer = self._reviewer(branch_every=4)
        self.assertIsNotNone(
            self._commit_event(reviewer, tool_id="tool-1", message="one")
        )
        path = self._state_path()
        state = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("review-cadence-state/v1", state["schema"])
        state.pop("schema")
        state["version"] = 5
        state["events"] = {
            tool_id: event["counts"] for tool_id, event in state["events"].items()
        }
        legacy_bytes = json.dumps(state, sort_keys=True).encode("utf-8")
        path.write_bytes(legacy_bytes)

        with self.assertRaisesRegex(ValueError, "unsupported hook state"):
            reviewer.review_event("session-1", "tool-1")
        self.assertEqual(legacy_bytes, path.read_bytes())

    def test_corrupt_or_cadence_inconsistent_state_fails_loudly(self) -> None:
        reviewer = self._reviewer(branch_every=4)
        targets = reviewer.find_commit_targets(
            "git commit --allow-empty -m pending", str(self.repo)
        )
        reviewer.record_before("session-1", "pending-tool", targets)
        path = self._state_path()
        baseline = json.loads(path.read_text(encoding="utf-8"))
        unsupported = dict(baseline)
        unsupported.pop("schema", None)
        unsupported["version"] = 999

        for mutation, message in (
            ({**baseline, "count": True}, "invalid hook count"),
            ({**baseline, "standard_every": True}, "invalid standard"),
            (unsupported, "unsupported hook state"),
        ):
            with self.subTest(message=message):
                path.write_text(json.dumps(mutation), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    reviewer.record_before("session-1", "another-tool", targets)

        path.write_text(json.dumps(baseline), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cadence changed"):
            self._reviewer(branch_every=3).record_before(
                "session-1", "another-tool", targets
            )

    def _python_change(
        self, reviewer: ReviewAfterCommit, *, selected: bool, pending: bool = False
    ):
        module = self.repo / "module.py"
        module.write_text("def choose(value=None):\n    return value\n", encoding="utf-8")
        self._git("add", "module.py")
        self._git("commit", "-qm", "python base")
        command = "git commit -am change"
        reviewer.record_before(
            "session-1",
            "tool-1",
            reviewer.find_commit_targets(command, str(self.repo)),
        )
        body = (
            "def choose(value=[]):\n    return value\n"
            if selected
            else "def choose(value=None):\n    return value or 1\n"
        )
        module.write_text(body, encoding="utf-8")
        self._git("commit", "-am", "change", "-q")
        return (
            reviewer.review_pending("session-1")
            if pending
            else reviewer.review_event("session-1", "tool-1")
        )

    def test_auto_selects_a_matching_python_change_and_includes_evidence(self) -> None:
        store = OutcomeStore(self.root / "outcomes")
        reviewer = self._reviewer(mode=ReviewMode.AUTO, outcome_store=store)

        decision = self._python_change(reviewer, selected=True)

        assert decision is not None
        self.assertEqual(ReviewKind.SIGNALS, decision.kind)
        request = decision.requests[0]
        self.assertEqual(ReviewMode.AUTO, request.mode)
        self.assertIsNotNone(request.evidence)
        self.assertTrue(request.evidence.attention)
        events = store.load(request.repository)
        self.assertEqual(1, len(events))
        self.assertTrue(events[0]["selected"])
        self.assertEqual("ok", events[0]["evidence"]["analysis"]["status"])

    def test_auto_silently_skips_a_nonmatching_python_change_but_records_it(self) -> None:
        store = OutcomeStore(self.root / "outcomes")
        reviewer = self._reviewer(mode=ReviewMode.AUTO, outcome_store=store)

        decision = self._python_change(reviewer, selected=False)

        self.assertIsNone(decision)
        paths = list((self.root / "outcomes").glob("repositories/*/outcomes.jsonl"))
        self.assertEqual(1, len(paths))
        event = json.loads(paths[0].read_text(encoding="utf-8"))
        self.assertFalse(event["selected"])
        self.assertEqual(1, event["evidence"]["context"]["python_files_changed"])

    def test_non_python_auto_event_is_recorded_without_running_ruff(self) -> None:
        notes = self.repo / "notes.txt"
        notes.write_text("one\n", encoding="utf-8")
        self._git("add", "notes.txt")
        self._git("commit", "-qm", "notes base")
        store = OutcomeStore(self.root / "outcomes")
        reviewer = self._reviewer(mode=ReviewMode.AUTO, outcome_store=store)
        command = "git commit -am notes"
        reviewer.record_before(
            "session-1",
            "tool-1",
            reviewer.find_commit_targets(command, str(self.repo)),
        )
        notes.write_text("two\n", encoding="utf-8")
        self._git("commit", "-am", "notes", "-q")

        with mock.patch("runtime.analysis.evidence_package.run_ruff") as ruff:
            decision = reviewer.review_event("session-1", "tool-1")

        ruff.assert_not_called()
        self.assertIsNone(decision)
        path = next((self.root / "outcomes").glob("repositories/*/outcomes.jsonl"))
        event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("skipped-no-python", event["evidence"]["analysis"]["status"])

    def test_scan_failure_is_recorded_and_does_not_invent_a_review(self) -> None:
        store = OutcomeStore(self.root / "outcomes")
        reviewer = self._reviewer(mode=ReviewMode.AUTO, outcome_store=store)
        module = self.repo / "module.py"
        module.write_text("VALUE = 1\n", encoding="utf-8")
        self._git("add", "module.py")
        self._git("commit", "-qm", "python base")
        command = "git commit -am change"
        reviewer.record_before(
            "session-1", "tool-1", reviewer.find_commit_targets(command, str(self.repo))
        )
        module.write_text("VALUE = 2\n", encoding="utf-8")
        self._git("commit", "-am", "change", "-q")

        with mock.patch.object(
            core, "scan_range", side_effect=ReviewScanError("injected /private/path")
        ):
            decision = reviewer.review_event("session-1", "tool-1")

        self.assertIsNone(decision)
        path = next((self.root / "outcomes").glob("repositories/*/outcomes.jsonl"))
        event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("error", event["evidence"]["analysis"]["status"])
        self.assertNotIn("/private/path", json.dumps(event))

    def test_outcome_store_failure_is_visible_without_suppressing_selected_review(self) -> None:
        store = OutcomeStore(self.root / "outcomes")
        reviewer = self._reviewer(mode=ReviewMode.AUTO, outcome_store=store)

        with mock.patch.object(
            store,
            "append",
            side_effect=OutcomeStoreError("injected /private/outcome path"),
        ):
            decision = self._python_change(reviewer, selected=True)

        self.assertIsNotNone(decision)
        self.assertIn(
            "review-after-commit analyzer health: outcome-store-error; review delivery continues",
            reviewer.take_operational_notices(),
        )
        summary = reviewer.operational_summary()
        self.assertEqual("error", summary["last_health"]["status"])
        self.assertEqual(["outcome-store-error"], summary["last_health"]["issues"])
        self.assertNotIn("/private/outcome", json.dumps(summary))

    def test_auto_scan_and_outcome_write_do_not_hold_the_cadence_lock(self) -> None:
        store = OutcomeStore(self.root / "outcomes")
        reviewer = self._reviewer(mode=ReviewMode.AUTO, outcome_store=store)
        module = self.repo / "module.py"
        module.write_text("def choose(value=None):\n    return value\n", encoding="utf-8")
        self._git("add", "module.py")
        self._git("commit", "-qm", "python base")
        command = "git commit -am change"
        reviewer.record_before(
            "session-1", "tool-1", reviewer.find_commit_targets(command, str(self.repo))
        )
        module.write_text("def choose(value=[]):\n    return value\n", encoding="utf-8")
        self._git("commit", "-am", "change", "-q")
        lock_path = self._state_path().with_suffix(".lock")
        original_scan = core.scan_range
        original_append = store.append

        def assert_cadence_unlocked():
            with lock_path.open("a+", encoding="utf-8") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        def scan_unlocked(*args, **kwargs):
            assert_cadence_unlocked()
            return original_scan(*args, **kwargs)

        def append_unlocked(*args, **kwargs):
            assert_cadence_unlocked()
            return original_append(*args, **kwargs)

        with mock.patch.object(core, "scan_range", side_effect=scan_unlocked), mock.patch.object(
            store, "append", side_effect=append_unlocked
        ):
            decision = reviewer.review_event("session-1", "tool-1")

        self.assertIsNotNone(decision)

    def test_pending_auto_event_delivers_and_duplicate_reconstructs_from_outcome(self) -> None:
        store = OutcomeStore(self.root / "outcomes")
        reviewer = self._reviewer(mode=ReviewMode.AUTO, outcome_store=store)

        decision = self._python_change(reviewer, selected=True, pending=True)

        assert decision is not None
        self.assertEqual(ReviewKind.SIGNALS, decision.kind)
        duplicate = reviewer.review_event("session-1", "tool-1")
        self.assertEqual(decision, duplicate)


if __name__ == "__main__":
    unittest.main()
