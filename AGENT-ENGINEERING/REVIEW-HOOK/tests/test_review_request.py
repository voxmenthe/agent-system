from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, fields

from runtime import (
    AnalysisHealth,
    AnalysisStatus,
    CapabilityRef,
    CommitRange,
    ContractError,
    CoverageReceipt,
    EvidenceContext,
    EvidenceLane,
    EvidenceProvenance,
    Finding,
    FindingClass,
    FindingStatus,
    PolicyIdentity,
    PromptIntent,
    PythonTarget,
    PythonTargetSource,
    RepositoryIdentity,
    ReviewAuthority,
    ReviewEvidence,
    ReviewKind,
    ReviewMode,
    ReviewRequest,
    ReviewVerdict,
    Signal,
    SourceLocation,
    Target,
    TargetRole,
    review_verdict,
)

BEFORE = "a" * 40
AFTER = "b" * 40
EVENT_ID = "sha256:" + "c" * 64
DIGEST = "sha256:" + "d" * 64


def policy() -> PolicyIdentity:
    return PolicyIdentity("auto-attention", "v1", DIGEST)


def commit_range() -> CommitRange:
    return CommitRange(BEFORE, AFTER, 1)


def evidence() -> ReviewEvidence:
    return ReviewEvidence(
        event_id=EVENT_ID,
        commit_range=commit_range(),
        health=AnalysisHealth(AnalysisStatus.OK),
        policies=(policy(),),
        attention=True,
        targets=(
            Target("t1", "pkg/module.py", 18, "Decoder.decode", TargetRole.PRODUCTION),
        ),
        signals=(
            Signal(
                EvidenceLane.STRUCTURAL,
                "C901",
                ("t1",),
                before=11,
                after=14,
                limit=10,
            ),
        ),
        context=EvidenceContext(
            tests_changed=True,
            test_paths=("tests/test_module.py",),
            files_changed=2,
            python_files_changed=2,
        ),
        ruff_version="0.16.5",
        python_target=PythonTarget.PY313,
        python_target_source=PythonTargetSource.REQUIRES_PYTHON,
    )


class ReviewContractTests(unittest.TestCase):
    def test_signal_request_round_trips_without_host_or_quality_fields(self) -> None:
        request = ReviewRequest(
            event_id=EVENT_ID,
            repository=RepositoryIdentity("sha256:" + "e" * 64),
            commit_range=commit_range(),
            kind=ReviewKind.SIGNALS,
            mode=ReviewMode.AUTO,
            policies=(policy(),),
            health=AnalysisHealth(AnalysisStatus.OK),
            prompt_intent=PromptIntent.REVIEW_SIGNALS,
            expected_skill=CapabilityRef("diff-review", "current", "diff-review", DIGEST),
            evidence=evidence(),
        )

        payload = json.loads(request.to_json())

        self.assertEqual("review-request/v1", payload["schema"])
        self.assertEqual("review-evidence/v2", payload["evidence"]["schema"])
        self.assertNotIn("schema", {field.name for field in fields(request)})
        self.assertNotIn("schema", {field.name for field in fields(request.evidence)})
        self.assertEqual(payload["authority"], "read-only-advisory-review")
        self.assertEqual(payload["range"]["before"], BEFORE)
        self.assertEqual(payload["evidence"]["decision"]["targets_total"], 1)
        self.assertNotIn("host", payload)
        self.assertNotIn("score", request.to_json().lower())
        self.assertNotIn("quality", request.to_json().lower())

    def test_abbreviated_or_unchanged_object_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "full lowercase"):
            CommitRange("a" * 12, AFTER, 1)
        with self.assertRaisesRegex(ContractError, "different Git objects"):
            CommitRange(BEFORE, BEFORE, 1)

    def test_sha256_git_object_ids_are_supported_when_complete(self) -> None:
        value = CommitRange("a" * 64, "b" * 64, 2)
        self.assertEqual(value.commits, 2)

    def test_target_manifest_must_be_complete_and_sequential(self) -> None:
        with self.assertRaisesRegex(ContractError, "complete sequential"):
            ReviewEvidence(
                event_id=EVENT_ID,
                commit_range=commit_range(),
                health=AnalysisHealth(AnalysisStatus.OK),
                policies=(policy(),),
                attention=True,
                targets=(Target("t2", "pkg/a.py", 1, "a", TargetRole.PRODUCTION),),
                signals=(
                    Signal(
                        EvidenceLane.STRUCTURAL,
                        "C901",
                        ("t2",),
                        before="new",
                        after=11,
                        limit=10,
                    ),
                ),
                context=EvidenceContext(False, files_changed=1, python_files_changed=1),
                ruff_version="0.16.5",
                python_target=PythonTarget.PY313,
                python_target_source=PythonTargetSource.FLEET_FALLBACK,
            )

        with self.assertRaisesRegex(ContractError, "every selected target"):
            ReviewEvidence(
                event_id=EVENT_ID,
                commit_range=commit_range(),
                health=AnalysisHealth(AnalysisStatus.OK),
                policies=(policy(),),
                attention=True,
                targets=(
                    Target("t1", "pkg/a.py", 1, "a", TargetRole.PRODUCTION),
                    Target("t2", "pkg/b.py", 1, "b", TargetRole.PRODUCTION),
                ),
                signals=(
                    Signal(
                        EvidenceLane.STRUCTURAL,
                        "C901",
                        ("t1",),
                        before=10,
                        after=11,
                        limit=10,
                    ),
                ),
                context=EvidenceContext(False, files_changed=2, python_files_changed=2),
                ruff_version="0.16.5",
                python_target=PythonTarget.PY313,
                python_target_source=PythonTargetSource.FLEET_FALLBACK,
            )

    def test_attention_package_cannot_claim_truncation(self) -> None:
        with self.assertRaisesRegex(ContractError, "cannot be truncated"):
            ReviewEvidence(
                event_id=EVENT_ID,
                commit_range=commit_range(),
                health=AnalysisHealth(AnalysisStatus.OK),
                policies=(policy(),),
                attention=True,
                targets=(Target("t1", "pkg/a.py", 1, "a", TargetRole.PRODUCTION),),
                signals=(
                    Signal(
                        EvidenceLane.STRUCTURAL,
                        "C901",
                        ("t1",),
                        before="<=10",
                        after=13,
                        limit=10,
                    ),
                ),
                context=EvidenceContext(False, files_changed=1, python_files_changed=1),
                ruff_version="0.16.5",
                python_target=PythonTarget.PY313,
                python_target_source=PythonTargetSource.FLEET_FALLBACK,
                truncated=True,
                retrieval_ref="event://complete",
            )

    def test_metric_baseline_cannot_invent_zero_or_ambiguous_text(self) -> None:
        with self.assertRaisesRegex(ContractError, "metric before"):
            Signal(
                EvidenceLane.STRUCTURAL,
                "C901",
                ("t1",),
                before="unknown",
                after=12,
                limit=10,
            )

    def test_correctness_observation_keeps_diagnostic_message(self) -> None:
        with self.assertRaisesRegex(ContractError, "retain the diagnostic"):
            Signal(EvidenceLane.CORRECTNESS, "B006", ("t1",))

    def test_unstructured_evidence_rejects_scores_and_source_bodies(self) -> None:
        for forbidden in ("quality_score", "source_body", "prompt_transcript"):
            with self.subTest(field=forbidden):
                with self.assertRaisesRegex(ContractError, "forbidden field"):
                    Signal(
                        EvidenceLane.DESIGN,
                        "THIN_DELEGATION_LAYER_GROWTH",
                        ("t1",),
                        message="new forwarding layer",
                        evidence={forbidden: "not allowed"},
                    )

    def test_cadence_request_rejects_scan_evidence(self) -> None:
        with self.assertRaisesRegex(ContractError, "must not reveal"):
            ReviewRequest(
                event_id=EVENT_ID,
                repository=RepositoryIdentity("sha256:" + "e" * 64),
                commit_range=commit_range(),
                kind=ReviewKind.RECENT,
                mode=ReviewMode.CADENCE,
                policies=(policy(),),
                health=AnalysisHealth(AnalysisStatus.OK),
                prompt_intent=PromptIntent.REVIEW_RECENT,
                evidence=evidence(),
            )

    def test_request_and_evidence_cannot_disagree_about_analysis_health(self) -> None:
        with self.assertRaisesRegex(ContractError, "analysis health must match"):
            ReviewRequest(
                event_id=EVENT_ID,
                repository=RepositoryIdentity("sha256:" + "e" * 64),
                commit_range=commit_range(),
                kind=ReviewKind.SIGNALS,
                mode=ReviewMode.AUTO,
                policies=(policy(),),
                health=AnalysisHealth(
                    AnalysisStatus.ERROR,
                    issues=("runner failed",),
                    target_complete=False,
                ),
                prompt_intent=PromptIntent.REVIEW_SIGNALS,
                evidence=evidence(),
            )

    def test_nested_contract_objects_must_be_typed(self) -> None:
        with self.assertRaisesRegex(ContractError, "context must be typed"):
            ReviewEvidence(
                event_id=EVENT_ID,
                commit_range=commit_range(),
                health=AnalysisHealth(AnalysisStatus.OK),
                policies=(policy(),),
                attention=False,
                targets=(),
                signals=(),
                context={},  # type: ignore[arg-type]
                ruff_version="0.16.5",
                python_target=PythonTarget.PY313,
                python_target_source=PythonTargetSource.FLEET_FALLBACK,
            )

    def test_auto_mode_cannot_be_reinterpreted_as_cadence(self) -> None:
        with self.assertRaisesRegex(ContractError, "auto mode"):
            ReviewRequest(
                event_id=EVENT_ID,
                repository=RepositoryIdentity("sha256:" + "e" * 64),
                commit_range=commit_range(),
                kind=ReviewKind.BRANCH,
                mode=ReviewMode.AUTO,
                policies=(policy(),),
                health=AnalysisHealth(AnalysisStatus.SKIPPED_MODE),
                prompt_intent=PromptIntent.REVIEW_BRANCH,
            )

    def test_scope_overflow_names_every_file_without_fake_target_completeness(self) -> None:
        request = ReviewRequest(
            event_id=EVENT_ID,
            repository=RepositoryIdentity("sha256:" + "e" * 64),
            commit_range=commit_range(),
            kind=ReviewKind.SIGNALS,
            mode=ReviewMode.AUTO,
            policies=(policy(),),
            health=AnalysisHealth(
                AnalysisStatus.INCONCLUSIVE_SCOPE_OVERFLOW,
                issues=("target identities exceed the delivery bound",),
                target_complete=False,
            ),
            prompt_intent=PromptIntent.REVIEW_SIGNALS,
            scope_files=("pkg/a.py", "pkg/b.py"),
        )
        self.assertEqual(request.scope_files, ("pkg/a.py", "pkg/b.py"))

    def test_authority_and_contracts_are_immutable(self) -> None:
        self.assertEqual(
            ReviewAuthority.READ_ONLY_ADVISORY.value,
            "read-only-advisory-review",
        )
        value = commit_range()
        with self.assertRaises(FrozenInstanceError):
            value.commits = 2  # type: ignore[misc]


class FindingContractTests(unittest.TestCase):
    def finding(
        self,
        finding_class: FindingClass = FindingClass.CHANGE,
        status: FindingStatus = FindingStatus.INTRODUCED,
    ) -> Finding:
        return Finding(
            finding_class=finding_class,
            priority="incorrect event can be attributed to the wrong commit",
            status=status,
            location=SourceLocation("runtime/review_core.py", 12, symbol="review_event"),
            evidence="the event ID is derived before the post-event range is known",
            evidence_provenance=EvidenceProvenance.SOURCE_OR_HISTORY_INFERENCE,
            consequence="a reviewer may inspect unrelated immutable objects",
            smallest_remedy="derive the ID after exact before/after resolution",
            preserved_invariants=("event deduplication remains deterministic",),
            verification="run the exact-range regression fixture",
            confidence_basis="the data flow is directly visible; runtime fixture remains to run",
        )

    def test_only_changed_change_findings_block(self) -> None:
        self.assertTrue(self.finding().blocking)
        self.assertFalse(
            self.finding(FindingClass.VERIFY, FindingStatus.INTRODUCED).blocking
        )
        self.assertFalse(
            self.finding(FindingClass.CHANGE, FindingStatus.PRE_EXISTING).blocking
        )
        self.assertEqual(
            review_verdict((self.finding(),)),
            ReviewVerdict.BLOCKING_CHANGED_FINDINGS,
        )
        self.assertEqual(
            review_verdict(
                (self.finding(FindingClass.CONSIDER, FindingStatus.INTRODUCED),)
            ),
            ReviewVerdict.NO_BLOCKING_CHANGED_FINDINGS_RESIDUALS_REMAIN,
        )
        self.assertEqual(review_verdict(()), ReviewVerdict.NO_BLOCKING_CHANGED_FINDINGS)

    def test_priority_and_confidence_are_not_scores(self) -> None:
        with self.assertRaisesRegex(ContractError, "not a score"):
            value = self.finding()
            Finding(
                finding_class=value.finding_class,
                priority="92%",
                status=value.status,
                location=value.location,
                evidence=value.evidence,
                evidence_provenance=value.evidence_provenance,
                consequence=value.consequence,
                smallest_remedy=value.smallest_remedy,
                preserved_invariants=value.preserved_invariants,
                verification=value.verification,
                confidence_basis=value.confidence_basis,
            )
        with self.assertRaisesRegex(ContractError, "unsupported percentage"):
            value = self.finding()
            Finding(
                finding_class=value.finding_class,
                priority=value.priority,
                status=value.status,
                location=value.location,
                evidence=value.evidence,
                evidence_provenance=value.evidence_provenance,
                consequence=value.consequence,
                smallest_remedy=value.smallest_remedy,
                preserved_invariants=value.preserved_invariants,
                verification=value.verification,
                confidence_basis="92% confidence",
            )

    def test_coverage_receipt_keeps_exclusions_and_unverified_behavior_visible(self) -> None:
        receipt = CoverageReceipt(
            exact_target_identity="{}..{}".format(BEFORE, AFTER),
            deeply_reviewed=("runtime request contract",),
            mechanically_checked=("all changed Python files",),
            collapsed=("generated fixtures",),
            excluded=("Antigravity runtime: no supported lifecycle fixture",),
            diagnostics_run=("python3 -m unittest discover -s tests",),
            unverified_runtime=("real host delivery",),
        )
        self.assertEqual(receipt.unverified_runtime, ("real host delivery",))


if __name__ == "__main__":
    unittest.main()
