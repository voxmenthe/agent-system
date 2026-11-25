from __future__ import annotations

import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.analysis.evidence_package import ReviewScanResult
from runtime.analysis.model import (
    AnalysisHealth,
    AnalysisStatus,
    CommitRange,
    EvidenceContext,
    PolicyIdentity,
    PythonTarget,
    PythonTargetSource,
    RepositoryIdentity,
    ReviewEvidence,
)
from runtime.operational_health import OperationalJournal, OperationalJournalError


def _result(
    index: int,
    status: AnalysisStatus,
    duration_ms: int,
    issues: tuple[str, ...] | None = None,
) -> ReviewScanResult:
    policy = PolicyIdentity(
        "review-scan-suite", "v1", "sha256:" + "a" * 64
    )
    health = AnalysisHealth(
        status,
        issues=(
            issues
            if issues is not None
            else (("typed-health",) if status is not AnalysisStatus.OK else ())
        ),
    )
    evidence = ReviewEvidence(
        event_id="sha256:" + format(index, "064x"),
        commit_range=CommitRange("b" * 40, format(index + 1, "040x"), 1),
        health=health,
        policies=(policy,),
        attention=False,
        targets=(),
        signals=(),
        context=EvidenceContext(
            False,
            files_changed=1,
            python_files_changed=1,
        ),
        ruff_version="0.16.5",
        python_target=PythonTarget.PY313,
        python_target_source=PythonTargetSource.FLEET_FALLBACK,
    )
    return ReviewScanResult(
        evidence=evidence,
        repository=RepositoryIdentity("sha256:" + "c" * 64),
        policy_decisions=(),
        auto_available=False,
        duration_ms=duration_ms,
    )


def _record_in_process(root: str, index: int) -> None:
    OperationalJournal(Path(root)).record(
        "session-{}".format(index),
        "auto",
        _result(index, AnalysisStatus.OK, index),
    )


class OperationalHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.journal = OperationalJournal(self.root)

    def test_summary_reports_latency_rates_policy_and_private_last_health(self) -> None:
        notices = []
        statuses = (
            AnalysisStatus.OK,
            AnalysisStatus.TIMEOUT,
            AnalysisStatus.INCOMPATIBLE_PYTHON_TARGET,
            AnalysisStatus.UNAVAILABLE,
        )
        for index, status in enumerate(statuses, start=1):
            notice = self.journal.record(
                "session-secret",
                "auto",
                _result(index, status, index * 10),
            )
            if notice:
                notices.append(notice)

        summary = self.journal.summary()

        self.assertEqual(4, summary["events"]["count"])
        self.assertEqual(4, summary["events"]["retained"])
        self.assertEqual(4, summary["duration_ms"]["sample_count"])
        self.assertGreater(summary["events"]["bytes"], 0)
        self.assertEqual(25, summary["duration_ms"]["p50"])
        self.assertEqual(40, summary["duration_ms"]["p95"])
        self.assertEqual(0.25, summary["rates"]["timeout"])
        self.assertEqual(0.25, summary["rates"]["unavailable"])
        self.assertEqual(0.25, summary["rates"]["incompatible"])
        self.assertEqual("unavailable", summary["last_health"]["status"])
        self.assertEqual("py313", summary["python_target"]["last"])
        self.assertEqual("fleet-fallback", summary["python_target"]["source"])
        self.assertEqual("auto", summary["selected_mode"])
        self.assertEqual(
            "sha256:" + "a" * 64,
            summary["policies"][0]["digest"],
        )
        self.assertEqual(1, len(notices))
        serialized = json.dumps(summary, sort_keys=True)
        self.assertNotIn("session-secret", serialized)
        self.assertNotIn(str(self.root), serialized)

    def test_identical_replay_is_idempotent_and_conflict_is_loud(self) -> None:
        result = _result(1, AnalysisStatus.OK, 10)
        self.assertIsNone(self.journal.record("session", "auto", result))
        self.assertIsNone(self.journal.record("session", "auto", result))
        self.assertEqual(1, self.journal.summary()["events"]["count"])

        with self.assertRaisesRegex(OperationalJournalError, "conflicting"):
            self.journal.record(
                "session", "auto", _result(1, AnalysisStatus.TIMEOUT, 10)
            )

    def test_diagnostic_detail_is_reduced_to_source_free_categories(self) -> None:
        result = _result(
            1,
            AnalysisStatus.TIMEOUT,
            10,
            issues=(
                "ruff-version:/private/repo/secret.py",
                "unstructured /private/repo/secret.py",
                "ruff-version:duplicate-detail",
            ),
        )

        notice = self.journal.record("session-secret", "auto", result)
        summary = self.journal.summary()
        serialized = json.dumps(summary, sort_keys=True)

        self.assertEqual(
            ["ruff-version", "timeout"], summary["last_health"]["issues"]
        )
        self.assertIn("ruff-version", notice)
        self.assertNotIn("private", serialized)
        self.assertNotIn("secret.py", serialized)

    def test_malformed_or_partial_history_is_never_repaired(self) -> None:
        path = self.root / "health.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema":"unknown"}', encoding="utf-8")
        before = path.read_bytes()

        with self.assertRaises(OperationalJournalError):
            self.journal.summary()

        self.assertEqual(before, path.read_bytes())

    def test_summary_state_is_bounded_while_counts_remain_cumulative(self) -> None:
        with mock.patch("runtime.operational_health.MAX_RECENT_RECORDS", 3):
            for index in range(1, 11):
                status = (
                    AnalysisStatus.TIMEOUT
                    if index in {1, 4, 7, 10}
                    else AnalysisStatus.OK
                )
                self.journal.record(
                    "session",
                    "auto",
                    _result(index, status, index * 10),
                )

            summary = self.journal.summary()
            state = json.loads((self.root / "health.json").read_text(encoding="utf-8"))

        self.assertEqual("review-operational-health-summary/v1", state["schema"])
        self.assertEqual(10, summary["events"]["count"])
        self.assertEqual(3, summary["events"]["retained"])
        self.assertEqual(3, summary["events"]["retention_limit"])
        self.assertEqual(3, summary["duration_ms"]["sample_count"])
        self.assertEqual(90, summary["duration_ms"]["p50"])
        self.assertEqual(100, summary["duration_ms"]["p95"])
        self.assertEqual(0.4, summary["rates"]["timeout"])
        self.assertEqual(3, len(state["recent"]))
        self.assertTrue(all("schema" not in event for event in state["recent"]))

    def test_failure_streak_tracking_is_bounded(self) -> None:
        with mock.patch("runtime.operational_health.MAX_SESSION_STREAKS", 2):
            for index in range(1, 6):
                self.journal.record(
                    "session-{}".format(index),
                    "auto",
                    _result(index, AnalysisStatus.TIMEOUT, 10),
                )
            state = json.loads((self.root / "health.json").read_text(encoding="utf-8"))

        self.assertEqual(2, len(state["failure_streaks"]))

    def test_concurrent_processes_do_not_lose_summary_updates(self) -> None:
        context = multiprocessing.get_context("fork")
        processes = [
            context.Process(target=_record_in_process, args=(str(self.root), index))
            for index in range(1, 9)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(0, process.exitcode)

        summary = self.journal.summary()
        self.assertEqual(8, summary["events"]["count"])
        self.assertEqual(8, summary["events"]["retained"])
