"""The small semantic waist shared by review event producers and hosts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple

from .analysis.model import (
    AnalysisHealth,
    AnalysisStatus,
    CommitRange,
    ContractError,
    PolicyIdentity,
    RepositoryIdentity,
    ReviewEvidence,
    _plain,
    _require_text,
    _validate_relative_path,
    _validate_sha256_id,
)

REQUEST_SCHEMA = "review-request/v1"
_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class ReviewKind(str, Enum):
    RECENT = "recent"
    BRANCH = "branch"
    SIGNALS = "signals"


class ReviewMode(str, Enum):
    CADENCE = "cadence"
    AUTO = "auto"


class PromptIntent(str, Enum):
    REVIEW_RECENT = "review-recent-commits"
    REVIEW_BRANCH = "review-current-branch-diff"
    REVIEW_SIGNALS = "review-python-signals"


class ReviewAuthority(str, Enum):
    READ_ONLY_ADVISORY = "read-only-advisory-review"


@dataclass(frozen=True)
class CapabilityRef:
    name: str
    revision: str
    contract: str
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or _CAPABILITY_NAME.fullmatch(self.name) is None:
            raise ContractError("capability name must be lowercase kebab-case")
        _require_text(self.revision, "capability revision", maximum=128)
        _require_text(self.contract, "capability contract", maximum=128)
        _validate_sha256_id(self.digest, "capability digest")


@dataclass(frozen=True)
class ReviewRequest:
    event_id: str
    repository: RepositoryIdentity
    commit_range: CommitRange
    kind: ReviewKind
    mode: ReviewMode
    policies: Tuple[PolicyIdentity, ...]
    health: AnalysisHealth
    prompt_intent: PromptIntent
    expected_skill: Optional[CapabilityRef] = None
    evidence: Optional[ReviewEvidence] = None
    scope_files: Tuple[str, ...] = ()
    authority: ReviewAuthority = ReviewAuthority.READ_ONLY_ADVISORY

    def __post_init__(self) -> None:
        _validate_sha256_id(self.event_id, "event_id")
        if not isinstance(self.kind, ReviewKind):
            raise ContractError("review kind must be typed")
        if not isinstance(self.mode, ReviewMode):
            raise ContractError("review mode must be typed")
        if not isinstance(self.repository, RepositoryIdentity):
            raise ContractError("repository identity must be typed")
        if not isinstance(self.commit_range, CommitRange):
            raise ContractError("request commit_range must be typed")
        if not isinstance(self.health, AnalysisHealth):
            raise ContractError("request health must be typed")
        if self.expected_skill is not None and not isinstance(
            self.expected_skill, CapabilityRef
        ):
            raise ContractError("expected_skill must be a typed capability reference")
        if self.evidence is not None and not isinstance(self.evidence, ReviewEvidence):
            raise ContractError("evidence must be a typed ReviewEvidence")
        if self.authority is not ReviewAuthority.READ_ONLY_ADVISORY:
            raise ContractError("review requests have read-only advisory authority")
        if isinstance(self.policies, str) or not all(
            isinstance(policy, PolicyIdentity) for policy in self.policies
        ):
            raise ContractError("request policies must be typed")
        if isinstance(self.scope_files, str):
            raise ContractError("scope_files must be a sequence")
        policies = tuple(self.policies)
        scope_files = tuple(self.scope_files)
        object.__setattr__(self, "policies", policies)
        object.__setattr__(self, "scope_files", scope_files)
        if not policies or len({(item.name, item.version) for item in policies}) != len(policies):
            raise ContractError("request policies must be non-empty and unique")
        for path in scope_files:
            _validate_relative_path(path, "scope file")
        if len(set(scope_files)) != len(scope_files):
            raise ContractError("scope files must be unique")
        expected_intent = {
            ReviewKind.RECENT: PromptIntent.REVIEW_RECENT,
            ReviewKind.BRANCH: PromptIntent.REVIEW_BRANCH,
            ReviewKind.SIGNALS: PromptIntent.REVIEW_SIGNALS,
        }[self.kind]
        if self.prompt_intent is not expected_intent:
            raise ContractError("prompt intent must match review kind")
        if self.mode is ReviewMode.AUTO and self.kind is not ReviewKind.SIGNALS:
            raise ContractError("auto mode emits only immediate signal requests")
        if self.mode is not ReviewMode.AUTO and self.kind is ReviewKind.SIGNALS:
            raise ContractError("cadence mode emits only cadence decisions")
        if self.evidence is not None:
            if self.evidence.event_id != self.event_id:
                raise ContractError("request and evidence event IDs must match")
            if self.evidence.commit_range != self.commit_range:
                raise ContractError("request and evidence commit ranges must match")
            if self.evidence.policies != policies:
                raise ContractError("request and evidence policy identities must match")
            if self.evidence.health != self.health:
                raise ContractError("request and evidence analysis health must match")
        if self.kind is ReviewKind.SIGNALS:
            scope_overflow = (
                self.health.status is AnalysisStatus.INCONCLUSIVE_SCOPE_OVERFLOW
                and bool(scope_files)
            )
            complete_evidence = self.evidence is not None and self.evidence.attention
            if not complete_evidence and not scope_overflow:
                raise ContractError(
                    "signals requests need target-complete attention evidence or an explicit scope-overflow manifest"
                )
        elif self.evidence is not None:
            raise ContractError("cadence requests must not reveal Review Scan evidence")
        if self.health.status is AnalysisStatus.INCONCLUSIVE_SCOPE_OVERFLOW:
            if not scope_files:
                raise ContractError("scope overflow must name every affected file")
        elif scope_files:
            raise ContractError("scope files are reserved for explicit scope overflow")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": REQUEST_SCHEMA,
            "event_id": self.event_id,
            "repository": _plain(self.repository),
            "range": _plain(self.commit_range),
            "kind": self.kind.value,
            "mode": self.mode.value,
            "policies": [_plain(policy) for policy in self.policies],
            "analysis": _plain(self.health),
            "prompt_intent": self.prompt_intent.value,
            "authority": self.authority.value,
            "expected_skill": _plain(self.expected_skill) if self.expected_skill else None,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "scope_files": list(self.scope_files),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class FindingClass(str, Enum):
    CHANGE = "Change"
    VERIFY = "Verify"
    CONSIDER = "Consider"


class FindingStatus(str, Enum):
    INTRODUCED = "introduced"
    WORSENED = "worsened"
    PRE_EXISTING = "pre-existing"


class EvidenceProvenance(str, Enum):
    REPRODUCED_NOW = "reproduced-now"
    DETERMINISTIC_OBSERVATION = "deterministic-hook-observation"
    BUILDER_REPORTED = "builder-reported-not-repeated"
    SOURCE_OR_HISTORY_INFERENCE = "source-or-history-inference"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class SourceLocation:
    path: str
    line: int
    end_line: Optional[int] = None
    symbol: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        if isinstance(self.line, bool) or not isinstance(self.line, int) or self.line < 1:
            raise ContractError("finding line must be a positive integer")
        if self.end_line is not None:
            if (
                isinstance(self.end_line, bool)
                or not isinstance(self.end_line, int)
                or self.end_line < self.line
            ):
                raise ContractError("finding end_line must be at or after line")
        if self.symbol is not None:
            _require_text(self.symbol, "finding symbol", maximum=512)


@dataclass(frozen=True)
class Finding:
    finding_class: FindingClass
    priority: str
    status: FindingStatus
    location: SourceLocation
    evidence: str
    evidence_provenance: EvidenceProvenance
    consequence: str
    smallest_remedy: str
    preserved_invariants: Tuple[str, ...]
    verification: str
    confidence_basis: str

    def __post_init__(self) -> None:
        if not isinstance(self.finding_class, FindingClass):
            raise ContractError("finding class must be typed")
        if not isinstance(self.status, FindingStatus):
            raise ContractError("finding status must be typed")
        if not isinstance(self.evidence_provenance, EvidenceProvenance):
            raise ContractError("evidence provenance must be typed")
        if not isinstance(self.location, SourceLocation):
            raise ContractError("finding location must be typed")
        for name, value, maximum in (
            ("priority", self.priority, 240),
            ("evidence", self.evidence, 2000),
            ("consequence", self.consequence, 1000),
            ("smallest_remedy", self.smallest_remedy, 1000),
            ("verification", self.verification, 1000),
            ("confidence_basis", self.confidence_basis, 1000),
        ):
            _require_text(value, name, maximum=maximum)
        if re.fullmatch(r"[0-9.]+%?", self.priority.strip()):
            raise ContractError("priority must name a consequence, not a score")
        if isinstance(self.preserved_invariants, str):
            raise ContractError("preserved invariants must be a sequence")
        invariants = tuple(self.preserved_invariants)
        object.__setattr__(self, "preserved_invariants", invariants)
        if not invariants:
            raise ContractError("a finding must name preserved invariants")
        for invariant in invariants:
            _require_text(invariant, "preserved invariant", maximum=500)
        if re.search(r"(?<![0-9])[0-9]{1,3}%", self.confidence_basis):
            raise ContractError("confidence basis must not use an unsupported percentage")

    @property
    def blocking(self) -> bool:
        return self.finding_class is FindingClass.CHANGE and self.status in (
            FindingStatus.INTRODUCED,
            FindingStatus.WORSENED,
        )


class ReviewVerdict(str, Enum):
    BLOCKING_CHANGED_FINDINGS = "blocking changed findings"
    NO_BLOCKING_CHANGED_FINDINGS_RESIDUALS_REMAIN = (
        "no blocking changed findings; residuals remain"
    )
    NO_BLOCKING_CHANGED_FINDINGS = "no blocking changed findings in reviewed scope"


def review_verdict(findings: Sequence[Finding]) -> ReviewVerdict:
    items = tuple(findings)
    if any(finding.blocking for finding in items):
        return ReviewVerdict.BLOCKING_CHANGED_FINDINGS
    if items:
        return ReviewVerdict.NO_BLOCKING_CHANGED_FINDINGS_RESIDUALS_REMAIN
    return ReviewVerdict.NO_BLOCKING_CHANGED_FINDINGS


@dataclass(frozen=True)
class CoverageReceipt:
    exact_target_identity: str
    deeply_reviewed: Tuple[str, ...]
    mechanically_checked: Tuple[str, ...]
    collapsed: Tuple[str, ...]
    excluded: Tuple[str, ...]
    diagnostics_run: Tuple[str, ...]
    unverified_runtime: Tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.exact_target_identity, "exact target identity", maximum=512)
        for field_name in (
            "deeply_reviewed",
            "mechanically_checked",
            "collapsed",
            "excluded",
            "diagnostics_run",
            "unverified_runtime",
        ):
            raw_values = getattr(self, field_name)
            if isinstance(raw_values, str):
                raise ContractError("{} must be a sequence".format(field_name))
            values = tuple(raw_values)
            object.__setattr__(self, field_name, values)
            for value in values:
                _require_text(value, field_name, maximum=1000)
