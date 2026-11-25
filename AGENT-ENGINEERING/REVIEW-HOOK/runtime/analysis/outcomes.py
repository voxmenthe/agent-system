"""Private automatic-review decisions, deliveries, and reviewer outcomes.

The store contains hashed repository and event identities plus deterministic
Review Scan evidence. It never records a repository location, source body,
prompt, host transcript, credential, author, or environment dump.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .evidence_package import ReviewScanResult
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
    TargetRole,
)

OUTCOME_SCHEMA = "review-auto-outcome"
SUMMARY_SCHEMA = "review-auto-outcome-summary"
MAX_EVENT_BYTES = 8_000_000
HOSTS = frozenset(("codex", "kimi", "antigravity"))
REVIEW_RESULTS = frozenset(("findings", "no-findings"))
_FORBIDDEN_KEYS = frozenset(
    {
        "absolute_path",
        "author",
        "credential",
        "credentials",
        "environment",
        "environment_dump",
        "prompt",
        "prompt_body",
        "repo_path",
        "repository_path",
        "source_body",
        "source_text",
        "transcript",
    }
)
_ABSOLUTE_FRAGMENTS = (
    re.compile(r'''(^|[\s:=({\['"])/(?!/)[^\s,;)}\]'\"]+'''),
    re.compile(r'''(^|\s)//[^\s,;)}\]'\"]+'''),
    re.compile(r'''(^|[\s:=({\['"])[A-Za-z]:[\\/][^\s,;)}\]'\"]+'''),
)
_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class OutcomeStoreError(ValueError):
    """Automatic-review state is unsafe, malformed, or conflicting."""


def default_outcome_root() -> Path:
    configured = os.environ.get("REVIEW_AFTER_COMMIT_OUTCOME_STATE")
    if configured:
        return Path(configured).expanduser()
    xdg_state = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state).expanduser() if xdg_state else Path.home() / ".local/state"
    return base / "review-after-commit"


def _repository_key(repository: RepositoryIdentity) -> str:
    if not isinstance(repository, RepositoryIdentity):
        raise OutcomeStoreError("repository identity must be typed")
    return repository.digest.split(":", 1)[1]


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise OutcomeStoreError("{} must be a full SHA-256 identity".format(name))
    return value


def _private_payload(value: Any, path: str = "outcome") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise OutcomeStoreError("{} has an invalid field name".format(path))
            normalized = key.lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise OutcomeStoreError(
                    "{} contains forbidden field {!r}".format(path, key)
                )
            _private_payload(item, "{}.{}".format(path, key))
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _private_payload(item, "{}[{}]".format(path, index))
        return
    if isinstance(value, str):
        if "\x00" in value:
            raise OutcomeStoreError("{} contains a NUL byte".format(path))
        if any(pattern.search(value) for pattern in _ABSOLUTE_FRAGMENTS):
            raise OutcomeStoreError(
                "{} contains an absolute-path fragment".format(path)
            )
        return
    if value is None or type(value) in (bool, int, float):
        return
    raise OutcomeStoreError("{} contains a non-JSON value".format(path))


def _review_evidence(value: Any) -> ReviewEvidence:
    """Rebuild a typed evidence object and reject any unrecognized shape."""

    try:
        if not isinstance(value, dict) or value.get("schema") != "review-evidence/v2":
            raise OutcomeStoreError("outcome evidence has an unsupported shape")
        exact_range = value["range"]
        analysis = value["analysis"]
        decision = value["decision"]
        context = value["context"]
        evidence = ReviewEvidence(
            event_id=value["event_id"],
            commit_range=CommitRange(
                exact_range["before"], exact_range["after"], exact_range["commits"]
            ),
            health=AnalysisHealth(
                AnalysisStatus(analysis["status"]),
                tuple(analysis["issues"]),
                target_complete=analysis["target_complete"],
                truncated=decision["truncated"],
                retrieval_ref=decision["retrieval_ref"],
            ),
            policies=tuple(
                PolicyIdentity(item["name"], item["version"], item["digest"])
                for item in decision["policies"]
            ),
            attention=decision["attention"],
            targets=tuple(
                Target(
                    item["id"],
                    item["path"],
                    item["line"],
                    item["symbol"],
                    TargetRole(item["role"]),
                )
                for item in value["targets"]
            ),
            signals=tuple(
                Signal(
                    EvidenceLane(item["lane"]),
                    item["code"],
                    tuple(item["target_ids"]),
                    message=item["message"],
                    before=item["before"],
                    after=item["after"],
                    limit=item["limit"],
                    evidence=item["evidence"],
                )
                for item in value["signals"]
            ),
            context=EvidenceContext(
                context["tests_changed"],
                tuple(context["test_paths"]),
                context["files_changed"],
                context["python_files_changed"],
                tuple(context["ordered_commits"]),
                context["first_parent_resolution"],
                tuple(context["scope_files"]),
            ),
            ruff_version=analysis["ruff"],
            python_target=(
                PythonTarget(analysis["python_target"])
                if analysis["python_target"] is not None
                else None
            ),
            python_target_source=(
                PythonTargetSource(analysis["python_target_source"])
                if analysis["python_target_source"] is not None
                else None
            ),
            python_target_map=tuple(
                PackagePythonTarget(item["root"], PythonTarget(item["target"]))
                for item in analysis["python_target_map"]
            ),
            truncated=decision["truncated"],
            retrieval_ref=decision["retrieval_ref"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, OutcomeStoreError):
            raise
        raise OutcomeStoreError("outcome evidence is malformed") from error
    if evidence.to_dict() != value:
        raise OutcomeStoreError("outcome evidence contains unsupported fields")
    if decision["targets_total"] != evidence.targets_total:
        raise OutcomeStoreError("outcome target count differs from its manifest")
    return evidence


def build_auto_outcome(
    result: ReviewScanResult,
    *,
    repository_path: Optional[Path] = None,
    captured_at: Optional[int] = None,
) -> Dict[str, Any]:
    """Build one automatically captured scan and selection decision."""

    if not isinstance(result, ReviewScanResult):
        raise OutcomeStoreError("scan result must be typed")
    selected = result.auto_available and result.auto_candidate.matched
    event: Dict[str, Any] = {
        "schema": OUTCOME_SCHEMA,
        "event_id": result.evidence.event_id,
        "repository": result.repository.digest,
        "analyzer": result.analyzer_version,
        "mode": "auto",
        "captured_at": int(time.time()) if captured_at is None else captured_at,
        "duration_ms": result.duration_ms,
        "selected": selected,
        "evidence": result.evidence.to_dict(),
        "deliveries": [],
    }
    _validate_event(event, result.repository)
    if repository_path is not None:
        exact_path = str(Path(repository_path).expanduser().resolve())
        serialized = json.dumps(event, sort_keys=True, separators=(",", ":"))
        if exact_path and exact_path in serialized:
            raise OutcomeStoreError("automatic outcome contains the repository path")
    return event


def delivery_identity(event_id: str, host: str, delivery_context: str) -> str:
    _require_sha256(event_id, "event identity")
    if host not in HOSTS:
        raise OutcomeStoreError("unsupported review host")
    if not isinstance(delivery_context, str) or not delivery_context:
        raise OutcomeStoreError("delivery context must be non-empty")
    material = json.dumps(
        {"event": event_id, "host": host, "context": delivery_context},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _validate_delivery(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "delivery_id",
        "host",
        "delivered_at",
        "review",
    }:
        raise OutcomeStoreError("automatic delivery has an invalid field set")
    _require_sha256(value["delivery_id"], "delivery identity")
    if value["host"] not in HOSTS:
        raise OutcomeStoreError("automatic delivery has an unsupported host")
    if type(value["delivered_at"]) is not int or value["delivered_at"] < 0:
        raise OutcomeStoreError("automatic delivery time must be non-negative")
    review = value["review"]
    if review is None:
        return
    if not isinstance(review, dict) or set(review) != {
        "result",
        "finding_count",
        "reviewed_at",
    }:
        raise OutcomeStoreError("automatic review result has an invalid field set")
    count = review["finding_count"]
    if (
        review["result"] not in REVIEW_RESULTS
        or type(count) is not int
        or count < 0
        or type(review["reviewed_at"]) is not int
        or review["reviewed_at"] < 0
        or (review["result"] == "findings") != (count > 0)
    ):
        raise OutcomeStoreError("automatic review result is inconsistent")


def _validate_event(event: Any, repository: RepositoryIdentity) -> None:
    if not isinstance(event, dict) or set(event) != {
        "schema",
        "event_id",
        "repository",
        "analyzer",
        "mode",
        "captured_at",
        "duration_ms",
        "selected",
        "evidence",
        "deliveries",
    }:
        raise OutcomeStoreError("automatic outcome has an invalid field set")
    if event["schema"] != OUTCOME_SCHEMA:
        raise OutcomeStoreError("automatic outcome has an unsupported schema")
    if event["repository"] != repository.digest:
        raise OutcomeStoreError("automatic outcome repository does not match its store")
    _require_sha256(event["event_id"], "event identity")
    if not isinstance(event["analyzer"], str) or not event["analyzer"]:
        raise OutcomeStoreError("automatic outcome analyzer must be non-empty")
    if event["mode"] != "auto":
        raise OutcomeStoreError("automatic outcomes must use auto mode")
    if type(event["captured_at"]) is not int or event["captured_at"] < 0:
        raise OutcomeStoreError("automatic outcome time must be non-negative")
    if type(event["duration_ms"]) is not int or event["duration_ms"] < 0:
        raise OutcomeStoreError("automatic outcome duration must be non-negative")
    if type(event["selected"]) is not bool:
        raise OutcomeStoreError("automatic outcome selection must be Boolean")
    evidence = _review_evidence(event["evidence"])
    if evidence.event_id != event["event_id"]:
        raise OutcomeStoreError("outcome and evidence identities differ")
    if event["selected"] and not evidence.attention:
        raise OutcomeStoreError("a selected outcome requires attention evidence")
    deliveries = event["deliveries"]
    if not isinstance(deliveries, list):
        raise OutcomeStoreError("automatic deliveries must be a list")
    if deliveries and not event["selected"]:
        raise OutcomeStoreError("an unselected outcome cannot have deliveries")
    identities = []
    for delivery in deliveries:
        _validate_delivery(delivery)
        identities.append(delivery["delivery_id"])
    if len(identities) != len(set(identities)):
        raise OutcomeStoreError("automatic outcome contains duplicate deliveries")
    _private_payload(event)


def outcome_evidence(
    event: Mapping[str, Any], repository: RepositoryIdentity
) -> ReviewEvidence:
    candidate = dict(event)
    _validate_event(candidate, repository)
    return _review_evidence(candidate["evidence"])


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _same_scan(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_stable = dict(left)
    right_stable = dict(right)
    for value in (left_stable, right_stable):
        value.pop("captured_at", None)
        value.pop("duration_ms", None)
        value.pop("deliveries", None)
    return left_stable == right_stable


class OutcomeStore:
    """One atomic JSONL outcome history per hashed repository identity."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()

    def event_path(self, repository: RepositoryIdentity) -> Path:
        return self.root / "repositories" / _repository_key(repository) / "outcomes.jsonl"

    def _prepare_directory(self, repository: RepositoryIdentity) -> Path:
        directory = self.event_path(repository).parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise OutcomeStoreError(
                "automatic outcome state is not an ordinary directory"
            )
        return directory

    def _decode(
        self, payload: bytes, repository: RepositoryIdentity
    ) -> List[Dict[str, Any]]:
        if not payload:
            return []
        if not payload.endswith(b"\n"):
            raise OutcomeStoreError("automatic outcome history has a partial record")
        events: List[Dict[str, Any]] = []
        identities = set()
        for line_number, raw in enumerate(payload.splitlines(), start=1):
            if not raw:
                raise OutcomeStoreError(
                    "automatic outcome history has a blank record at line {}".format(
                        line_number
                    )
                )
            try:
                event = json.loads(raw)
            except (UnicodeDecodeError, ValueError) as error:
                raise OutcomeStoreError(
                    "automatic outcome history has malformed JSON at line {}".format(
                        line_number
                    )
                ) from error
            _validate_event(event, repository)
            identity = event["event_id"]
            if identity in identities:
                raise OutcomeStoreError(
                    "automatic outcome history contains duplicate event {}".format(
                        identity
                    )
                )
            identities.add(identity)
            events.append(event)
        return events

    def _read_unlocked(
        self, path: Path, repository: RepositoryIdentity
    ) -> Tuple[bytes, List[Dict[str, Any]]]:
        if not path.exists():
            return b"", []
        if path.is_symlink() or not path.is_file():
            raise OutcomeStoreError("automatic outcome history is not an ordinary file")
        payload = path.read_bytes()
        return payload, self._decode(payload, repository)

    def _replace_unlocked(self, path: Path, events: Iterable[Mapping[str, Any]]) -> None:
        payload = b"".join(
            (
                json.dumps(dict(event), sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            for event in events
        )
        handle, temporary_name = tempfile.mkstemp(prefix=".outcomes.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            os.chmod(temporary, 0o600)
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            _fsync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _locked_events(
        self, repository: RepositoryIdentity, *, exclusive: bool
    ) -> Tuple[Any, Path, List[Dict[str, Any]]]:
        directory = self._prepare_directory(repository)
        path = directory / "outcomes.jsonl"
        lock_path = directory / "outcomes.lock"
        if lock_path.is_symlink():
            raise OutcomeStoreError("automatic outcome lock must not be a symlink")
        lock = lock_path.open("a+b")
        try:
            os.chmod(lock_path, 0o600)
            fcntl.flock(
                lock.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            )
            _, events = self._read_unlocked(path, repository)
        except Exception:
            lock.close()
            raise
        return lock, path, events

    def append(
        self, repository: RepositoryIdentity, event: Mapping[str, Any]
    ) -> bool:
        """Record one scan once; identical concurrent scans are harmless."""

        candidate = dict(event)
        _validate_event(candidate, repository)
        encoded = (
            json.dumps(candidate, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        if len(encoded) > MAX_EVENT_BYTES:
            raise OutcomeStoreError(
                "automatic outcome exceeds {} bytes".format(MAX_EVENT_BYTES)
            )
        lock, path, events = self._locked_events(repository, exclusive=True)
        try:
            for prior in events:
                if prior["event_id"] == candidate["event_id"]:
                    if not _same_scan(prior, candidate):
                        raise OutcomeStoreError(
                            "automatic outcome identity has conflicting scan content"
                        )
                    return False
            self._replace_unlocked(path, (*events, candidate))
            return True
        finally:
            lock.close()

    def record_delivery(
        self,
        repository: RepositoryIdentity,
        event_id: str,
        delivery_id: str,
        host: str,
        *,
        delivered_at: Optional[int] = None,
    ) -> bool:
        _require_sha256(event_id, "event identity")
        _require_sha256(delivery_id, "delivery identity")
        if host not in HOSTS:
            raise OutcomeStoreError("unsupported review host")
        lock, path, events = self._locked_events(repository, exclusive=True)
        try:
            event = next((item for item in events if item["event_id"] == event_id), None)
            if event is None:
                raise OutcomeStoreError("automatic outcome event is missing")
            if not event["selected"]:
                raise OutcomeStoreError("cannot deliver an unselected outcome")
            for delivery in event["deliveries"]:
                if delivery["delivery_id"] == delivery_id:
                    if delivery["host"] != host:
                        raise OutcomeStoreError("delivery identity has conflicting host")
                    return False
            event["deliveries"].append(
                {
                    "delivery_id": delivery_id,
                    "host": host,
                    "delivered_at": int(time.time()) if delivered_at is None else delivered_at,
                    "review": None,
                }
            )
            _validate_event(event, repository)
            self._replace_unlocked(path, events)
            return True
        finally:
            lock.close()

    def record_review(
        self,
        repository: RepositoryIdentity,
        event_id: str,
        delivery_id: str,
        finding_count: int,
        *,
        reviewed_at: Optional[int] = None,
    ) -> bool:
        _require_sha256(event_id, "event identity")
        _require_sha256(delivery_id, "delivery identity")
        if type(finding_count) is not int or finding_count < 0:
            raise OutcomeStoreError("finding count must be a non-negative integer")
        result = "findings" if finding_count else "no-findings"
        review = {
            "result": result,
            "finding_count": finding_count,
            "reviewed_at": int(time.time()) if reviewed_at is None else reviewed_at,
        }
        lock, path, events = self._locked_events(repository, exclusive=True)
        try:
            event = next((item for item in events if item["event_id"] == event_id), None)
            if event is None:
                raise OutcomeStoreError("automatic outcome event is missing")
            delivery = next(
                (
                    item
                    for item in event["deliveries"]
                    if item["delivery_id"] == delivery_id
                ),
                None,
            )
            if delivery is None:
                raise OutcomeStoreError("automatic delivery is missing")
            previous = delivery["review"]
            if previous is not None:
                if (
                    previous["result"] != result
                    or previous["finding_count"] != finding_count
                ):
                    raise OutcomeStoreError("automatic review outcome conflicts with prior result")
                return False
            delivery["review"] = review
            _validate_event(event, repository)
            self._replace_unlocked(path, events)
            return True
        finally:
            lock.close()

    def load(self, repository: RepositoryIdentity) -> Tuple[Dict[str, Any], ...]:
        lock, _, events = self._locked_events(repository, exclusive=False)
        try:
            return tuple(events)
        finally:
            lock.close()

    def find(
        self, repository: RepositoryIdentity, exact_range: CommitRange
    ) -> Optional[Dict[str, Any]]:
        for event in self.load(repository):
            evidence = event["evidence"]
            if evidence["range"] == {
                "before": exact_range.before,
                "after": exact_range.after,
                "commits": exact_range.commits,
            }:
                return event
        return None

    def _all_events(self) -> Tuple[Dict[str, Any], ...]:
        repositories = self.root / "repositories"
        if not repositories.exists():
            return ()
        if repositories.is_symlink() or not repositories.is_dir():
            raise OutcomeStoreError("automatic outcome root is not an ordinary directory")
        events: List[Dict[str, Any]] = []
        for directory in sorted(repositories.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                raise OutcomeStoreError("automatic outcome repository entry is invalid")
            repository = RepositoryIdentity("sha256:" + directory.name)
            events.extend(self.load(repository))
        return tuple(events)

    def summary(self) -> Dict[str, Any]:
        events = self._all_events()
        statuses: Dict[str, int] = {}
        delivery_hosts = {host: 0 for host in sorted(HOSTS)}
        review_hosts = {host: 0 for host in sorted(HOSTS)}
        deliveries = 0
        reviews = 0
        findings = 0
        no_findings = 0
        finding_count = 0
        awaiting_review = 0
        repository_ids = set()
        for event in events:
            repository_ids.add(event["repository"])
            status = event["evidence"]["analysis"]["status"]
            statuses[status] = statuses.get(status, 0) + 1
            for delivery in event["deliveries"]:
                deliveries += 1
                delivery_hosts[delivery["host"]] += 1
                review = delivery["review"]
                if review is None:
                    awaiting_review += 1
                    continue
                reviews += 1
                review_hosts[delivery["host"]] += 1
                finding_count += review["finding_count"]
                if review["result"] == "findings":
                    findings += 1
                else:
                    no_findings += 1
        selected = sum(1 for event in events if event["selected"])
        delivered_events = sum(1 for event in events if event["deliveries"])
        captured = [event["captured_at"] for event in events]
        return {
            "schema": SUMMARY_SCHEMA,
            "repositories": len(repository_ids),
            "scans": {
                "total": len(events),
                "python": sum(
                    1
                    for event in events
                    if event["evidence"]["context"]["python_files_changed"] > 0
                ),
                "selected": selected,
                "selected_not_delivered": selected - delivered_events,
                "by_status": dict(sorted(statuses.items())),
                "first_captured_at": min(captured) if captured else None,
                "last_captured_at": max(captured) if captured else None,
            },
            "deliveries": {
                "total": deliveries,
                "awaiting_review": awaiting_review,
                "by_host": delivery_hosts,
            },
            "reviews": {
                "total": reviews,
                "with_findings": findings,
                "without_findings": no_findings,
                "finding_count": finding_count,
                "by_host": review_hosts,
            },
        }


__all__ = [
    "OUTCOME_SCHEMA",
    "OutcomeStore",
    "OutcomeStoreError",
    "build_auto_outcome",
    "default_outcome_root",
    "delivery_identity",
    "outcome_evidence",
]
