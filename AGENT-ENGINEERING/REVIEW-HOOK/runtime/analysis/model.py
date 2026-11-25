"""Immutable, host-neutral Review Scan contracts.

These types deliberately reject abbreviated Git identities, incomplete target
manifests, untyped analysis failures, score-like payloads, and target-repository
authority. They contain observations for a reviewer, never a quality verdict.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple, Union

EVIDENCE_SCHEMA = "review-evidence/v2"
_FULL_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_KEBAB_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_TARGET_ID = re.compile(r"^t[1-9][0-9]*$")
_SIGNAL_CODE = re.compile(r"^[A-Z][A-Z0-9_-]*$")
_AT_OR_BELOW = re.compile(r"^<=[0-9]+$")
_FORBIDDEN_PAYLOAD_KEYS = (
    "absolute_path",
    "author",
    "credential",
    "environment",
    "grade",
    "prompt",
    "quality",
    "rating",
    "score",
    "source_body",
    "source_text",
    "transcript",
    "verdict",
)


class ContractError(ValueError):
    """A caller attempted to create an ambiguous or unsafe contract value."""


class AnalysisStatus(str, Enum):
    OK = "ok"
    SKIPPED_NO_PYTHON = "skipped-no-python"
    SKIPPED_MODE = "skipped-mode"
    INCONCLUSIVE_PARSE = "inconclusive-parse"
    INCONCLUSIVE_RENAME = "inconclusive-rename"
    INCONCLUSIVE_SCOPE_OVERFLOW = "inconclusive-scope-overflow"
    INCOMPATIBLE_PYTHON_TARGET = "incompatible-python-target"
    INCOMPATIBLE_RUFF_CONTRACT = "incompatible-ruff-contract"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


class PythonTarget(str, Enum):
    PY312 = "py312"
    PY313 = "py313"
    PY314 = "py314"


class PythonTargetSource(str, Enum):
    EXPLICIT = "explicit"
    REQUIRES_PYTHON = "requires-python"
    FLEET_FALLBACK = "fleet-fallback"
    PACKAGE_MAP = "package-map"


@dataclass(frozen=True)
class PackagePythonTarget:
    root: str
    target: PythonTarget

    def __post_init__(self) -> None:
        if self.root != ".":
            _validate_relative_path(self.root, "package root")
        if not isinstance(self.target, PythonTarget):
            raise ContractError("package target must be typed")


class TargetRole(str, Enum):
    PRODUCTION = "production"
    TEST = "test"
    GENERATED = "generated"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class EvidenceLane(str, Enum):
    CORRECTNESS = "correctness"
    STRUCTURAL = "structural"
    DESIGN = "design"
    DESIGN_CONTEXT = "design-context"


def _require_text(value: str, name: str, maximum: int = 512) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError("{} must be non-empty text".format(name))
    if len(value) > maximum:
        raise ContractError("{} exceeds {} characters".format(name, maximum))
    if "\x00" in value:
        raise ContractError("{} contains a NUL byte".format(name))


def _validate_oid(value: str, name: str) -> None:
    if not isinstance(value, str) or _FULL_OID.fullmatch(value) is None:
        raise ContractError(
            "{} must be a full lowercase 40- or 64-hex Git object ID".format(name)
        )


def _validate_sha256_id(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise ContractError("{} must use sha256:<64 lowercase hex>".format(name))


def _validate_relative_path(value: str, name: str = "path") -> None:
    _require_text(value, name, maximum=4096)
    path = PurePosixPath(value)
    if path.is_absolute() or value in (".", "..") or ".." in path.parts:
        raise ContractError("{} must be a repository-relative POSIX path".format(name))


def _freeze_json(value: Any, path: str = "payload") -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("{} contains a non-finite number".format(path))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        frozen: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ContractError("{} keys must be non-empty strings".format(path))
            normalized = key.lower().replace("-", "_")
            if any(token in normalized for token in _FORBIDDEN_PAYLOAD_KEYS):
                raise ContractError(
                    "{} contains forbidden field {!r}".format(path, key)
                )
            frozen[key] = _freeze_json(item, "{}.{}".format(path, key))
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(
            _freeze_json(item, "{}[{}]".format(path, index))
            for index, item in enumerate(value)
        )
    raise ContractError("{} contains a non-JSON value".format(path))


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class CommitRange:
    before: str
    after: str
    commits: int

    def __post_init__(self) -> None:
        _validate_oid(self.before, "before")
        _validate_oid(self.after, "after")
        if isinstance(self.commits, bool) or not isinstance(self.commits, int):
            raise ContractError("commits must be an integer")
        if self.commits < 1:
            raise ContractError("commits must be at least one")
        if self.before == self.after:
            raise ContractError("before and after must identify different Git objects")


@dataclass(frozen=True)
class RepositoryIdentity:
    digest: str

    def __post_init__(self) -> None:
        _validate_sha256_id(self.digest, "repository identity")


@dataclass(frozen=True)
class PolicyIdentity:
    name: str
    version: str
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or _KEBAB_NAME.fullmatch(self.name) is None:
            raise ContractError("policy name must be lowercase kebab-case")
        if not isinstance(self.version, str) or _KEBAB_NAME.fullmatch(self.version) is None:
            raise ContractError("policy version must be lowercase kebab-case")
        _validate_sha256_id(self.digest, "policy digest")


@dataclass(frozen=True)
class AnalysisHealth:
    status: AnalysisStatus
    issues: Tuple[str, ...] = ()
    target_complete: bool = True
    truncated: bool = False
    retrieval_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, AnalysisStatus):
            raise ContractError("analysis status must be typed")
        if not isinstance(self.target_complete, bool) or not isinstance(
            self.truncated, bool
        ):
            raise ContractError("analysis completeness flags must be Boolean")
        if isinstance(self.issues, str):
            raise ContractError("analysis issues must be a sequence of issue strings")
        object.__setattr__(self, "issues", tuple(self.issues))
        for issue in self.issues:
            _require_text(issue, "analysis issue", maximum=240)
        if self.status is AnalysisStatus.OK and self.issues:
            raise ContractError("ok analysis cannot carry failure issues")
        if self.status is AnalysisStatus.OK and not self.target_complete:
            raise ContractError("ok analysis must be target-complete")
        if self.truncated and not self.retrieval_ref:
            raise ContractError("truncated analysis requires a retrieval reference")
        if self.retrieval_ref is not None:
            _require_text(self.retrieval_ref, "retrieval_ref", maximum=512)


@dataclass(frozen=True)
class Target:
    id: str
    path: str
    line: int
    symbol: str
    role: TargetRole

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or _TARGET_ID.fullmatch(self.id) is None:
            raise ContractError("target id must be t1, t2, ...")
        _validate_relative_path(self.path)
        if isinstance(self.line, bool) or not isinstance(self.line, int) or self.line < 1:
            raise ContractError("target line must be a positive integer")
        _require_text(self.symbol, "target symbol", maximum=512)
        if not isinstance(self.role, TargetRole):
            raise ContractError("target role must be typed")


MetricBefore = Optional[Union[int, str]]


@dataclass(frozen=True)
class Signal:
    lane: EvidenceLane
    code: str
    target_ids: Tuple[str, ...]
    message: Optional[str] = None
    before: MetricBefore = None
    after: Optional[int] = None
    limit: Optional[int] = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.lane, EvidenceLane):
            raise ContractError("signal lane must be typed")
        if not isinstance(self.code, str) or _SIGNAL_CODE.fullmatch(self.code) is None:
            raise ContractError("signal code must be stable uppercase identifier text")
        if isinstance(self.target_ids, str):
            raise ContractError("signal target_ids must be a sequence")
        target_ids = tuple(self.target_ids)
        object.__setattr__(self, "target_ids", target_ids)
        if not target_ids or len(set(target_ids)) != len(target_ids):
            raise ContractError("signal target_ids must be non-empty and unique")
        if any(
            not isinstance(identifier, str)
            or _TARGET_ID.fullmatch(identifier) is None
            for identifier in target_ids
        ):
            raise ContractError("signal target_ids must use normalized target IDs")
        if self.message is not None:
            _require_text(self.message, "signal message", maximum=400)
        if self.lane is EvidenceLane.CORRECTNESS and self.message is None:
            raise ContractError("correctness signals must retain the diagnostic message")
        metric_fields = (self.before, self.after, self.limit)
        has_metric = any(value is not None for value in metric_fields)
        if self.lane is EvidenceLane.STRUCTURAL and not has_metric:
            raise ContractError("structural signals require a before/after/limit delta")
        if has_metric:
            if isinstance(self.before, bool) or not (
                isinstance(self.before, int)
                or (
                    isinstance(self.before, str)
                    and (self.before == "new" or _AT_OR_BELOW.fullmatch(self.before))
                )
            ):
                raise ContractError(
                    "metric before must be an integer, 'new', or an explicit <=N state"
                )
            for name, value in (("after", self.after), ("limit", self.limit)):
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ContractError("metric {} must be a non-negative integer".format(name))
        object.__setattr__(self, "evidence", _freeze_json(self.evidence, "signal.evidence"))


@dataclass(frozen=True)
class EvidenceContext:
    tests_changed: bool
    test_paths: Tuple[str, ...] = ()
    files_changed: int = 0
    python_files_changed: int = 0
    ordered_commits: Tuple[str, ...] = ()
    first_parent_resolution: bool = False
    scope_files: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.tests_changed, bool):
            raise ContractError("tests_changed must be Boolean")
        if isinstance(self.test_paths, str):
            raise ContractError("test_paths must be a sequence")
        test_paths = tuple(self.test_paths)
        object.__setattr__(self, "test_paths", test_paths)
        for path in test_paths:
            _validate_relative_path(path, "test path")
        for name, value in (
            ("files_changed", self.files_changed),
            ("python_files_changed", self.python_files_changed),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractError("{} must be a non-negative integer".format(name))
        if self.python_files_changed > self.files_changed:
            raise ContractError("python_files_changed cannot exceed files_changed")
        if bool(test_paths) != self.tests_changed:
            raise ContractError("tests_changed must agree with the test path manifest")
        if isinstance(self.ordered_commits, str):
            raise ContractError("ordered_commits must be a sequence")
        ordered_commits = tuple(self.ordered_commits)
        object.__setattr__(self, "ordered_commits", ordered_commits)
        for commit in ordered_commits:
            _validate_oid(commit, "ordered commit")
        if len(set(ordered_commits)) != len(ordered_commits):
            raise ContractError("ordered commits must be unique")
        if not isinstance(self.first_parent_resolution, bool):
            raise ContractError("first_parent_resolution must be Boolean")
        if isinstance(self.scope_files, str):
            raise ContractError("scope_files must be a sequence")
        scope_files = tuple(self.scope_files)
        object.__setattr__(self, "scope_files", scope_files)
        for path in scope_files:
            _validate_relative_path(path, "scope file")
        if len(set(scope_files)) != len(scope_files):
            raise ContractError("scope files must be unique")


@dataclass(frozen=True)
class ReviewEvidence:
    event_id: str
    commit_range: CommitRange
    health: AnalysisHealth
    policies: Tuple[PolicyIdentity, ...]
    attention: bool
    targets: Tuple[Target, ...]
    signals: Tuple[Signal, ...]
    context: EvidenceContext
    ruff_version: Optional[str] = None
    python_target: Optional[PythonTarget] = None
    python_target_source: Optional[PythonTargetSource] = None
    python_target_map: Tuple[PackagePythonTarget, ...] = ()
    truncated: bool = False
    retrieval_ref: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_sha256_id(self.event_id, "event_id")
        if not isinstance(self.commit_range, CommitRange):
            raise ContractError("evidence commit_range must be typed")
        if not isinstance(self.health, AnalysisHealth):
            raise ContractError("evidence health must be typed")
        if not isinstance(self.context, EvidenceContext):
            raise ContractError("evidence context must be typed")
        if not isinstance(self.attention, bool) or not isinstance(self.truncated, bool):
            raise ContractError("evidence decision flags must be Boolean")
        for name, values, expected_type in (
            ("policies", self.policies, PolicyIdentity),
            ("targets", self.targets, Target),
            ("signals", self.signals, Signal),
        ):
            if isinstance(values, str) or not all(
                isinstance(value, expected_type) for value in values
            ):
                raise ContractError("evidence {} must be typed".format(name))
        policies = tuple(self.policies)
        targets = tuple(self.targets)
        signals = tuple(self.signals)
        object.__setattr__(self, "policies", policies)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "signals", signals)
        if not policies or len({(item.name, item.version) for item in policies}) != len(policies):
            raise ContractError("evidence policies must be non-empty and unique")
        expected_ids = tuple("t{}".format(index) for index in range(1, len(targets) + 1))
        actual_ids = tuple(target.id for target in targets)
        if actual_ids != expected_ids:
            raise ContractError("targets must use complete sequential IDs in manifest order")
        target_ids = set(actual_ids)
        referenced_ids = {identifier for signal in signals for identifier in signal.target_ids}
        if not referenced_ids.issubset(target_ids):
            raise ContractError("every signal target must appear in the target manifest")
        if target_ids != referenced_ids:
            raise ContractError("every selected target must be referenced by evidence")
        if self.attention:
            if not targets or not signals:
                raise ContractError("attention evidence requires targets and signals")
            if self.truncated or self.health.truncated:
                raise ContractError("attention evidence cannot be truncated")
            if not self.health.target_complete:
                raise ContractError("attention evidence must be target-complete")
        elif targets or signals:
            raise ContractError("non-attention packages must not expose selected targets")
        if self.truncated and not self.retrieval_ref:
            raise ContractError("truncated evidence requires a retrieval reference")
        if self.retrieval_ref is not None:
            _require_text(self.retrieval_ref, "retrieval_ref", maximum=512)
        if self.health.status is AnalysisStatus.OK:
            if self.ruff_version is None:
                raise ContractError("ok Review Scan evidence requires a Ruff version")
            _require_text(self.ruff_version, "ruff_version", maximum=64)
            if not isinstance(self.python_target, PythonTarget):
                raise ContractError("ok Review Scan evidence requires a typed Python target")
            if not isinstance(self.python_target_source, PythonTargetSource):
                raise ContractError("ok Review Scan evidence requires target provenance")
        elif self.attention:
            raise ContractError("attention evidence requires valid analysis")
        if self.health.status is AnalysisStatus.SKIPPED_NO_PYTHON and any(
            value is not None
            for value in (self.ruff_version, self.python_target, self.python_target_source)
        ):
            raise ContractError("no-Python evidence cannot claim a Ruff or Python target")
        if isinstance(self.python_target_map, str) or not all(
            isinstance(item, PackagePythonTarget) for item in self.python_target_map
        ):
            raise ContractError("python_target_map must contain typed package targets")
        python_target_map = tuple(self.python_target_map)
        object.__setattr__(self, "python_target_map", python_target_map)
        if len({item.root for item in python_target_map}) != len(python_target_map):
            raise ContractError("package target roots must be unique")
        if self.python_target_source is PythonTargetSource.PACKAGE_MAP:
            if len(python_target_map) < 2:
                raise ContractError("package-map provenance requires multiple package targets")
        elif python_target_map:
            raise ContractError("package targets are valid only with package-map provenance")
        ordered_commits = self.context.ordered_commits
        if ordered_commits:
            if len(ordered_commits) != self.commit_range.commits:
                raise ContractError("ordered commit count must match the exact range")
            if ordered_commits[-1] != self.commit_range.after:
                raise ContractError("ordered commits must end at the exact head")
        if self.health.status is AnalysisStatus.INCONCLUSIVE_SCOPE_OVERFLOW:
            if not self.context.scope_files:
                raise ContractError("scope overflow evidence must retain every affected file")
        elif self.context.scope_files:
            raise ContractError("scope files are reserved for scope overflow evidence")

    @property
    def targets_total(self) -> int:
        return len(self.targets)

    def to_dict(self) -> Dict[str, Any]:
        analysis = {
            "status": self.health.status.value,
            "issues": list(self.health.issues),
            "target_complete": self.health.target_complete,
            "ruff": self.ruff_version,
            "python_target": self.python_target.value if self.python_target else None,
            "python_target_source": (
                self.python_target_source.value if self.python_target_source else None
            ),
            "python_target_map": [
                _plain(item) for item in self.python_target_map
            ],
        }
        return {
            "schema": EVIDENCE_SCHEMA,
            "event_id": self.event_id,
            "range": _plain(self.commit_range),
            "analysis": analysis,
            "decision": {
                "attention": self.attention,
                "policies": [_plain(policy) for policy in self.policies],
                "targets_total": self.targets_total,
                "truncated": self.truncated,
                "retrieval_ref": self.retrieval_ref,
            },
            "targets": [_plain(target) for target in self.targets],
            "signals": [_plain(signal) for signal in self.signals],
            "context": _plain(self.context),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
