from __future__ import annotations

import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.analysis.evidence_package import ReviewScanResult, failed_scan_result
from runtime.analysis.model import (
    AnalysisHealth,
    AnalysisStatus,
    CommitRange,
    EvidenceContext,
    EvidenceLane,
    PolicyIdentity,
    PythonTarget,
    PythonTargetSource,
    RepositoryIdentity,
    ReviewEvidence,
    Signal,
    Target,
    TargetRole,
)
from runtime.analysis.outcomes import (
    OutcomeStore,
    OutcomeStoreError,
    build_auto_outcome,
    delivery_identity,
    outcome_evidence,
)
from runtime.analysis.structural_policy import (
    CandidateSignal,
    ObservationTarget,
    PolicyDecision,
)

OID_A = "1" * 40
OID_B = "2" * 40
OID_C = "3" * 40
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def scan_result(after: str = OID_B, event_id: str = DIGEST_A) -> ReviewScanResult:
    repository = RepositoryIdentity(DIGEST_B)
    suite = PolicyIdentity("review-scan-suite", "v1", DIGEST_A)
    automatic = PolicyIdentity("auto-attention-v1", "v1", DIGEST_C)
    target = Target("t1", "pkg/module.py", 1, "choose", TargetRole.PRODUCTION)
    signal = Signal(
        EvidenceLane.CORRECTNESS,
        "B006",
        ("t1",),
        message="Do not use mutable data structures for argument defaults",
    )
    evidence = ReviewEvidence(
        event_id=event_id,
        commit_range=CommitRange(OID_A, after, 1),
        health=AnalysisHealth(AnalysisStatus.OK),
        policies=(suite, automatic),
        attention=True,
        targets=(target,),
        signals=(signal,),
        context=EvidenceContext(
            False,
            files_changed=1,
            python_files_changed=1,
            ordered_commits=(after,),
        ),
        ruff_version="0.16.5",
        python_target=PythonTarget.PY313,
        python_target_source=PythonTargetSource.FLEET_FALLBACK,
    )
    candidate = CandidateSignal(
        EvidenceLane.CORRECTNESS,
        "B006",
        (ObservationTarget("pkg/module.py", 1, "choose", TargetRole.PRODUCTION),),
        message="Do not use mutable data structures for argument defaults",
    )
    return ReviewScanResult(
        evidence,
        repository,
        (
            PolicyDecision("auto-attention-v1", (candidate,)),
            PolicyDecision("review-scan-suite", (candidate,)),
        ),
        True,
        12,
    )


class OutcomeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = OutcomeStore(self.root / "state")
        self.result = scan_result()
        self.event = build_auto_outcome(
            self.result,
            repository_path=self.root / "private-repository",
            captured_at=100,
        )

    def test_scan_delivery_and_reviewer_result_are_private_and_automatic(self) -> None:
        payload = json.dumps(self.event, sort_keys=True)
        self.assertNotIn(str(self.root), payload)
        self.assertTrue(self.event["selected"])
        self.assertEqual([], self.event["deliveries"])
        self.assertEqual(self.result.evidence, outcome_evidence(self.event, self.result.repository))

        self.assertTrue(self.store.append(self.result.repository, self.event))
        delivery = delivery_identity(self.event["event_id"], "codex", "session")
        self.assertTrue(
            self.store.record_delivery(
                self.result.repository,
                self.event["event_id"],
                delivery,
                "codex",
                delivered_at=110,
            )
        )
        self.assertTrue(
            self.store.record_review(
                self.result.repository,
                self.event["event_id"],
                delivery,
                2,
                reviewed_at=120,
            )
        )

        stored = self.store.load(self.result.repository)[0]
        self.assertEqual("findings", stored["deliveries"][0]["review"]["result"])
        self.assertEqual(2, stored["deliveries"][0]["review"]["finding_count"])
        summary = self.store.summary()
        self.assertEqual(1, summary["scans"]["selected"])
        self.assertEqual(1, summary["deliveries"]["total"])
        self.assertEqual(1, summary["reviews"]["with_findings"])
        self.assertEqual(2, summary["reviews"]["finding_count"])

    def test_replays_are_idempotent_and_conflicts_fail_loudly(self) -> None:
        self.assertTrue(self.store.append(self.result.repository, self.event))
        replay = json.loads(json.dumps(self.event))
        replay["duration_ms"] += 1
        replay["captured_at"] += 1
        self.assertFalse(self.store.append(self.result.repository, replay))

        delivery = delivery_identity(self.event["event_id"], "kimi", "session")
        self.assertTrue(
            self.store.record_delivery(
                self.result.repository, self.event["event_id"], delivery, "kimi"
            )
        )
        self.assertFalse(
            self.store.record_delivery(
                self.result.repository, self.event["event_id"], delivery, "kimi"
            )
        )
        self.assertTrue(
            self.store.record_review(
                self.result.repository, self.event["event_id"], delivery, 0
            )
        )
        self.assertFalse(
            self.store.record_review(
                self.result.repository, self.event["event_id"], delivery, 0
            )
        )
        with self.assertRaisesRegex(OutcomeStoreError, "conflicts"):
            self.store.record_review(
                self.result.repository, self.event["event_id"], delivery, 1
            )

    def test_concurrent_scan_replay_writes_one_complete_record(self) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(
                pool.map(
                    lambda _: self.store.append(self.result.repository, self.event),
                    range(16),
                )
            )

        self.assertEqual(1, outcomes.count(True))
        self.assertEqual(15, outcomes.count(False))
        self.assertEqual(1, len(self.store.load(self.result.repository)))

    def test_malformed_partial_and_duplicate_history_are_loud(self) -> None:
        path = self.store.event_path(self.result.repository)
        path.parent.mkdir(parents=True)
        cases = (
            (b"not-json\n", "malformed JSON"),
            (json.dumps({"schema": "unknown"}).encode("utf-8") + b"\n", "invalid field set"),
            (json.dumps(self.event).encode("utf-8"), "partial record"),
            (
                (json.dumps(self.event) + "\n" + json.dumps(self.event) + "\n").encode(
                    "utf-8"
                ),
                "duplicate event",
            ),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                path.write_bytes(payload)
                with self.assertRaisesRegex(OutcomeStoreError, message):
                    self.store.load(self.result.repository)

    def test_failed_finalization_preserves_previous_history(self) -> None:
        self.store.append(self.result.repository, self.event)
        second = scan_result(after=OID_C, event_id=DIGEST_C)
        second_event = build_auto_outcome(second, captured_at=101)

        with mock.patch(
            "runtime.analysis.outcomes.os.replace",
            side_effect=OSError("injected finalization failure"),
        ):
            with self.assertRaisesRegex(OSError, "injected finalization failure"):
                self.store.append(second.repository, second_event)

        self.assertEqual((self.event,), self.store.load(self.result.repository))
        self.assertEqual(
            [],
            list(self.store.event_path(self.result.repository).parent.glob(".outcomes.*")),
        )

    def test_failure_and_absolute_path_leaks_are_sanitized_or_rejected(self) -> None:
        sanitized = failed_scan_result(
            self.result.repository,
            CommitRange(OID_A, OID_B, 1),
            (OID_B,),
            issue='ruff-unavailable:"/private/repo/assets/ruff"',
        )
        sanitized_event = build_auto_outcome(sanitized, captured_at=100)
        serialized = json.dumps(sanitized_event, sort_keys=True)
        self.assertNotIn("/private/repo", serialized)
        self.assertIn("<absolute-path>", serialized)

        leaked = json.loads(json.dumps(self.event))
        leaked["evidence"]["signals"][0]["message"] = (
            'failed at "C:\\private\\repo\\a.py"'
        )
        with self.assertRaisesRegex(OutcomeStoreError, "absolute-path fragment"):
            self.store.append(self.result.repository, leaked)


if __name__ == "__main__":
    unittest.main()
