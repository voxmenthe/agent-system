"""Orchestrate a target-complete deterministic Review Scan."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .ast_spans import AstParseError, ParsedPython, parse_python
from .design_signals import analyze_design
from .git_snapshot import (
    ChangeKind,
    GitSnapshot,
    GitSnapshotError,
    SnapshotConfig,
    SnapshotScopeError,
    capture_snapshot,
)
from .model import (
    AnalysisHealth,
    AnalysisStatus,
    CommitRange,
    EvidenceContext,
    EvidenceLane,
    PackagePythonTarget,
    PolicyIdentity,
    PythonTarget,
    PythonTargetSource,
    RepositoryIdentity,
    ReviewEvidence,
    Signal,
    Target,
)
from .python_target import (
    PythonTargetError,
    PythonTargetResolution,
    resolve_python_targets,
)
from .ruff_runner import RuffConfig, run_ruff
from .structural_policy import (
    CandidateSignal,
    PolicyDecision,
    analyze_structural,
)

ANALYZER_VERSION = "review-scan-v1"
POLICY_SCHEMA = "review-scan-policy/v1"
_ABSOLUTE_PATH_FRAGMENTS = (
    re.compile(r'''(^|[\s:=({\['"])/(?!/)[^\s,;)}\]'\"]+'''),
    re.compile(r'''(^|\s)//[^\s,;)}\]'\"]+'''),
    re.compile(r'''(^|[\s:=({\['"])[A-Za-z]:[\\/][^\s,;)}\]'\"]+'''),
)


class ReviewScanError(RuntimeError):
    """The scan invocation itself is invalid and cannot produce typed evidence."""


@dataclass(frozen=True)
class PolicySpec:
    identity: PolicyIdentity
    automatic_delivery: bool
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class ReviewScanConfig:
    snapshot: SnapshotConfig = field(default_factory=SnapshotConfig)
    ruff: RuffConfig = field(default_factory=RuffConfig)
    explicit_python_target: Optional[PythonTarget] = None
    fleet_fallback: PythonTarget = PythonTarget.PY313
    include_design: bool = True
    policy_root: Path = Path(__file__).resolve().parents[2] / "policy"


@dataclass(frozen=True)
class ReviewScanResult:
    evidence: ReviewEvidence
    repository: RepositoryIdentity
    policy_decisions: Tuple[PolicyDecision, ...]
    auto_available: bool
    duration_ms: int
    analyzer_version: str = ANALYZER_VERSION

    @property
    def auto_candidate(self) -> PolicyDecision:
        for decision in self.policy_decisions:
            if decision.name == "auto-attention-v1":
                return decision
        return PolicyDecision("auto-attention-v1")


def _contains_forbidden_key(value: Any) -> bool:
    forbidden = ("score", "verdict", "quality", "rating", "prompt", "transcript")
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower().replace("-", "_") for token in forbidden)
            or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def load_policy(path: Path) -> PolicySpec:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, ValueError) as error:
        raise ReviewScanError("policy is missing or malformed: {}".format(path)) from error
    if not isinstance(payload, dict) or payload.get("schema") != POLICY_SCHEMA:
        raise ReviewScanError("policy has an unsupported schema: {}".format(path))
    if _contains_forbidden_key(payload):
        raise ReviewScanError("policy contains a score- or verdict-like field: {}".format(path))
    name = payload.get("name")
    version = payload.get("version")
    automatic = payload.get("automatic_delivery")
    if not isinstance(name, str) or not isinstance(version, str):
        raise ReviewScanError("policy identity fields are invalid: {}".format(path))
    if name == "auto-attention-v1":
        if type(automatic) is not bool:
            raise ReviewScanError("automatic policy activation is invalid: {}".format(path))
    elif "automatic_delivery" in payload:
        raise ReviewScanError("evidence policy must not own review delivery: {}".format(path))
    else:
        automatic = False
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    return PolicySpec(
        PolicyIdentity(name, version, digest), automatic, payload
    )


def _clip_issue(value: str) -> str:
    normalized = str(value).replace("\x00", "")
    for pattern in _ABSOLUTE_PATH_FRAGMENTS:
        normalized = pattern.sub(
            lambda match: match.group(1) + "<absolute-path>", normalized
        )
    return normalized if len(normalized) <= 240 else normalized[:239] + "…"


def _context(
    snapshot: GitSnapshot,
    *,
    scope_files: Sequence[str] = (),
) -> EvidenceContext:
    return EvidenceContext(
        tests_changed=bool(snapshot.test_paths),
        test_paths=snapshot.test_paths,
        files_changed=snapshot.files_changed,
        python_files_changed=len(snapshot.python_files),
        ordered_commits=snapshot.ordered_commits,
        first_parent_resolution=snapshot.first_parent_resolution,
        scope_files=tuple(scope_files),
    )


def _scope_context(error: SnapshotScopeError) -> EvidenceContext:
    return EvidenceContext(
        tests_changed=bool(error.test_paths),
        test_paths=tuple(error.test_paths),
        files_changed=error.files_changed,
        python_files_changed=len(error.paths),
        ordered_commits=tuple(error.ordered_commits),
        first_parent_resolution=error.first_parent_resolution,
        scope_files=tuple(error.paths),
    )


def _event_id(
    repository: RepositoryIdentity,
    commit_range,
    policies: Sequence[PolicyIdentity],
    *,
    ruff_version: Optional[str],
    target: Optional[PythonTarget],
    target_source: Optional[PythonTargetSource],
    package_map: Sequence[Tuple[str, PythonTarget]],
) -> str:
    material = {
        "schema": "review-scan-event/v1",
        "analyzer": ANALYZER_VERSION,
        "repository": repository.digest,
        "before": commit_range.before,
        "after": commit_range.after,
        "commits": commit_range.commits,
        "policies": [
            {
                "name": policy.name,
                "version": policy.version,
                "digest": policy.digest,
            }
            for policy in policies
        ],
        "ruff": ruff_version,
        "python_target": target.value if target else None,
        "python_target_source": target_source.value if target_source else None,
        "python_target_map": [
            {"root": root, "target": item.value} for root, item in package_map
        ],
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return "sha256:" + digest


def _failure_evidence(
    repository: RepositoryIdentity,
    commit_range,
    context: EvidenceContext,
    policies: Sequence[PolicySpec],
    status: AnalysisStatus,
    issues: Sequence[str],
    *,
    ruff_version: Optional[str] = None,
    target_resolution: Optional[PythonTargetResolution] = None,
) -> ReviewEvidence:
    target = target_resolution.primary if target_resolution else None
    source = target_resolution.source if target_resolution else None
    package_map = target_resolution.package_map if target_resolution else ()
    return ReviewEvidence(
        event_id=_event_id(
            repository,
            commit_range,
            tuple(policy.identity for policy in policies),
            ruff_version=ruff_version,
            target=target,
            target_source=source,
            package_map=package_map,
        ),
        commit_range=commit_range,
        health=AnalysisHealth(
            status,
            tuple(_clip_issue(issue) for issue in issues),
            target_complete=status is AnalysisStatus.SKIPPED_NO_PYTHON,
        ),
        policies=tuple(policy.identity for policy in policies),
        attention=False,
        targets=(),
        signals=(),
        context=context,
        ruff_version=ruff_version,
        python_target=target,
        python_target_source=source,
        python_target_map=tuple(
            PackagePythonTarget(root, item) for root, item in package_map
        ),
    )


def _signal_sort_key(item: CandidateSignal) -> Tuple[Any, ...]:
    order = {
        EvidenceLane.CORRECTNESS: 0,
        EvidenceLane.STRUCTURAL: 1,
        EvidenceLane.DESIGN: 2,
        EvidenceLane.DESIGN_CONTEXT: 3,
    }
    first = item.targets[0]
    delta = item.after - item.before if isinstance(item.before, int) and item.after is not None else 0
    return (
        order[item.lane],
        -delta,
        first.path,
        first.line,
        first.symbol,
        item.code,
        item.column,
        item.message or "",
    )


def _typed_package(signals: Sequence[CandidateSignal]):
    ordered = tuple(sorted(signals, key=_signal_sort_key))
    target_details: Dict[Tuple[str, str], Any] = {}
    for item in ordered:
        for target in item.targets:
            key = (target.path, target.symbol)
            previous = target_details.get(key)
            if previous is None or target.line < previous.line:
                target_details[key] = target
    target_ids: Dict[Tuple[str, str], str] = {}
    typed_targets: List[Target] = []
    typed_signals: List[Signal] = []
    for item in ordered:
        identifiers: List[str] = []
        for candidate in item.targets:
            key = (candidate.path, candidate.symbol)
            identifier = target_ids.get(key)
            if identifier is None:
                identifier = "t{}".format(len(typed_targets) + 1)
                target_ids[key] = identifier
                detail = target_details[key]
                typed_targets.append(
                    Target(
                        identifier,
                        detail.path,
                        detail.line,
                        detail.symbol,
                        detail.role,
                    )
                )
            if identifier not in identifiers:
                identifiers.append(identifier)
        typed_signals.append(
            Signal(
                lane=item.lane,
                code=item.code,
                target_ids=tuple(identifiers),
                message=item.message,
                before=item.before,
                after=item.after,
                limit=item.limit,
                evidence=item.evidence,
            )
        )
    return tuple(typed_targets), tuple(typed_signals)


def _empty_decisions() -> Tuple[PolicyDecision, ...]:
    return (
        PolicyDecision("auto-attention-v1"),
        PolicyDecision("review-design-v2"),
        PolicyDecision("review-scan-suite"),
    )


def scan_range(
    repo: Path,
    before: str,
    after: str,
    *,
    config: Optional[ReviewScanConfig] = None,
) -> ReviewScanResult:
    """Run a full read-only Review Scan over one exact net diff."""
    cfg = config or ReviewScanConfig()
    started = time.monotonic()
    suite_policy = load_policy(cfg.policy_root / "review-scan-suite.json")
    auto_policy = load_policy(cfg.policy_root / "auto-attention-v1.json")
    try:
        snapshot = capture_snapshot(Path(repo), before, after, config=cfg.snapshot)
    except SnapshotScopeError as error:
        if error.commit_range is None or error.repository is None:
            raise ReviewScanError("scope failure lacks exact range metadata") from error
        evidence = _failure_evidence(
            error.repository,
            error.commit_range,
            _scope_context(error),
            (suite_policy, auto_policy),
            AnalysisStatus.INCONCLUSIVE_SCOPE_OVERFLOW,
            (error.issue,),
        )
        return ReviewScanResult(
            evidence,
            error.repository,
            _empty_decisions(),
            auto_policy.automatic_delivery,
            int((time.monotonic() - started) * 1000),
        )
    except GitSnapshotError as error:
        raise ReviewScanError(str(error)) from error

    context = _context(snapshot)
    if not snapshot.python_files:
        evidence = _failure_evidence(
            snapshot.repository,
            snapshot.commit_range,
            context,
            (suite_policy, auto_policy),
            AnalysisStatus.SKIPPED_NO_PYTHON,
            (),
        )
        return ReviewScanResult(
            evidence,
            snapshot.repository,
            _empty_decisions(),
            auto_policy.automatic_delivery,
            int((time.monotonic() - started) * 1000),
        )
    ambiguous = tuple(
        item.path
        for item in snapshot.python_files
        if item.change is ChangeKind.RENAMED_AMBIGUOUS
    )
    if ambiguous:
        evidence = _failure_evidence(
            snapshot.repository,
            snapshot.commit_range,
            context,
            (suite_policy, auto_policy),
            AnalysisStatus.INCONCLUSIVE_RENAME,
            tuple("ambiguous-rename:{}".format(path) for path in ambiguous),
        )
        return ReviewScanResult(
            evidence,
            snapshot.repository,
            _empty_decisions(),
            auto_policy.automatic_delivery,
            int((time.monotonic() - started) * 1000),
        )

    try:
        targets = resolve_python_targets(
            snapshot,
            explicit=cfg.explicit_python_target,
            fallback=cfg.fleet_fallback,
        )
    except (PythonTargetError, SnapshotScopeError, GitSnapshotError) as error:
        evidence = _failure_evidence(
            snapshot.repository,
            snapshot.commit_range,
            context,
            (suite_policy, auto_policy),
            AnalysisStatus.INCOMPATIBLE_PYTHON_TARGET,
            (str(error),),
        )
        return ReviewScanResult(
            evidence,
            snapshot.repository,
            _empty_decisions(),
            auto_policy.automatic_delivery,
            int((time.monotonic() - started) * 1000),
        )

    parsed_before: Dict[str, ParsedPython] = {}
    parsed_after: Dict[str, ParsedPython] = {}
    parse_issues: List[str] = []
    for item in snapshot.python_files:
        for side, blob, destination in (
            ("before", item.before_blob, parsed_before),
            ("after", item.after_blob, parsed_after),
        ):
            if blob is None:
                continue
            try:
                destination[item.path] = parse_python(item.path, blob)
            except AstParseError as error:
                parse_issues.append("{}:{}".format(side, error))
    if parse_issues:
        evidence = _failure_evidence(
            snapshot.repository,
            snapshot.commit_range,
            context,
            (suite_policy, auto_policy),
            AnalysisStatus.INCONCLUSIVE_PARSE,
            parse_issues,
            target_resolution=targets,
        )
        return ReviewScanResult(
            evidence,
            snapshot.repository,
            _empty_decisions(),
            auto_policy.automatic_delivery,
            int((time.monotonic() - started) * 1000),
        )

    ruff = run_ruff(snapshot, targets, config=cfg.ruff)
    if ruff.status is not AnalysisStatus.OK:
        evidence = _failure_evidence(
            snapshot.repository,
            snapshot.commit_range,
            context,
            (suite_policy, auto_policy),
            ruff.status,
            ruff.issues,
            ruff_version=ruff.version,
            target_resolution=targets,
        )
        return ReviewScanResult(
            evidence,
            snapshot.repository,
            _empty_decisions(),
            auto_policy.automatic_delivery,
            int((time.monotonic() - started) * 1000),
        )

    structural = analyze_structural(snapshot, parsed_before, parsed_after, ruff)
    try:
        design = (
            analyze_design(snapshot, parsed_before, parsed_after)
            if cfg.include_design
            else ()
        )
    except GitSnapshotError as error:
        evidence = _failure_evidence(
            snapshot.repository,
            snapshot.commit_range,
            context,
            (suite_policy, auto_policy),
            AnalysisStatus.ERROR,
            ("design-analysis:{}".format(error),),
            ruff_version=ruff.version,
            target_resolution=targets,
        )
        return ReviewScanResult(
            evidence,
            snapshot.repository,
            structural.policies,
            auto_policy.automatic_delivery,
            int((time.monotonic() - started) * 1000),
        )

    all_signals = tuple((*structural.signals, *design))
    typed_targets, typed_signals = _typed_package(all_signals)
    design_review = tuple(
        item for item in design if item.lane is EvidenceLane.DESIGN
    )
    decisions = tuple(
        (
            *structural.policies,
            PolicyDecision("review-design-v2", design_review),
            PolicyDecision("review-scan-suite", all_signals),
        )
    )
    evidence = ReviewEvidence(
        event_id=_event_id(
            snapshot.repository,
            snapshot.commit_range,
            (suite_policy.identity, auto_policy.identity),
            ruff_version=ruff.version,
            target=targets.primary,
            target_source=targets.source,
            package_map=targets.package_map,
        ),
        commit_range=snapshot.commit_range,
        health=AnalysisHealth(AnalysisStatus.OK),
        policies=(suite_policy.identity, auto_policy.identity),
        attention=bool(typed_signals),
        targets=typed_targets,
        signals=typed_signals,
        context=context,
        ruff_version=ruff.version,
        python_target=targets.primary,
        python_target_source=targets.source,
        python_target_map=tuple(
            PackagePythonTarget(root, target)
            for root, target in targets.package_map
        ),
    )
    return ReviewScanResult(
        evidence,
        snapshot.repository,
        decisions,
        auto_policy.automatic_delivery,
        int((time.monotonic() - started) * 1000),
    )


def failed_scan_result(
    repository: RepositoryIdentity,
    commit_range: CommitRange,
    ordered_commits: Sequence[str],
    *,
    issue: str = "review-scan-invocation-failed",
    config: Optional[ReviewScanConfig] = None,
    duration_ms: int = 0,
) -> ReviewScanResult:
    """Represent an integration-layer scan failure without inventing clean data."""
    cfg = config or ReviewScanConfig()
    if type(duration_ms) is not int or duration_ms < 0:
        raise ReviewScanError("failure duration must be a non-negative integer")
    suite_policy = load_policy(cfg.policy_root / "review-scan-suite.json")
    auto_policy = load_policy(cfg.policy_root / "auto-attention-v1.json")
    context = EvidenceContext(
        tests_changed=False,
        files_changed=0,
        python_files_changed=0,
        ordered_commits=tuple(ordered_commits),
        first_parent_resolution=False,
    )
    evidence = _failure_evidence(
        repository,
        commit_range,
        context,
        (suite_policy, auto_policy),
        AnalysisStatus.ERROR,
        (issue,),
    )
    return ReviewScanResult(
        evidence,
        repository,
        _empty_decisions(),
        auto_policy.automatic_delivery,
        duration_ms,
    )


__all__ = [
    "ANALYZER_VERSION",
    "PolicySpec",
    "ReviewScanConfig",
    "ReviewScanError",
    "ReviewScanResult",
    "load_policy",
    "failed_scan_result",
    "scan_range",
]
