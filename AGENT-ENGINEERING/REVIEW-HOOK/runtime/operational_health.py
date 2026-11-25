"""Private bounded operational health for Review Scan runs.

The summary stores only typed analyzer facts and hashed session identity. It is
separate from cadence state and automatic-review outcomes so a telemetry
failure cannot alter review selection or repair another state domain.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import statistics
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .analysis.evidence_package import ReviewScanResult
from .analysis.model import AnalysisStatus

OPERATIONAL_HEALTH_SCHEMA = "review-operational-health-summary/v1"
FAILURE_NOTICE_INTERVAL = 5
MAX_RECENT_RECORDS = 128
MAX_SESSION_STREAKS = 64

_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_FAILURE_STATUSES = frozenset(
    {
        AnalysisStatus.INCOMPATIBLE_PYTHON_TARGET.value,
        AnalysisStatus.INCOMPATIBLE_RUFF_CONTRACT.value,
        AnalysisStatus.UNAVAILABLE.value,
        AnalysisStatus.TIMEOUT.value,
        AnalysisStatus.CANCELLED.value,
        AnalysisStatus.ERROR.value,
    }
)
_RATE_NAMES = ("timeout", "unavailable", "incompatible")


class OperationalJournalError(ValueError):
    """Operational summary state is malformed, unsafe, or incompatible."""


def _session_key(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id:
        raise OperationalJournalError("session identity must be non-empty")
    return "sha256:" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _record_id(event_id: str, session_key: str) -> str:
    material = "{}\0{}\0{}".format(
        OPERATIONAL_HEALTH_SCHEMA, event_id, session_key
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _validate_sha256(value: Any, name: str) -> None:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise OperationalJournalError(
            "{} must be a full SHA-256 identity".format(name)
        )


def _validate_token(value: Any, name: str) -> None:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        raise OperationalJournalError("{} must be a safe contract token".format(name))


def _operational_issues(
    status: AnalysisStatus, issues: Sequence[str]
) -> Tuple[str, ...]:
    """Reduce diagnostics to source-free categories before persistence."""

    if isinstance(issues, str):
        raise OperationalJournalError("operational issues must be a sequence")
    normalized = []
    for issue in issues:
        if not isinstance(issue, str) or not issue:
            raise OperationalJournalError(
                "operational issues must be non-empty strings"
            )
        if _SAFE_TOKEN.fullmatch(issue) is not None:
            token = issue
        else:
            prefix, separator, _ = issue.partition(":")
            token = (
                prefix
                if separator and _SAFE_TOKEN.fullmatch(prefix) is not None
                else status.value
            )
        if token not in normalized:
            normalized.append(token)
    return tuple(normalized)


def _validate_event(value: Any) -> Dict[str, Any]:
    required = {
        "record_id",
        "event_id",
        "session",
        "mode",
        "analyzer_version",
        "duration_ms",
        "status",
        "issues",
        "ruff_version",
        "python_target",
        "python_target_source",
        "policies",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise OperationalJournalError("operational event has an invalid field set")
    for field in ("record_id", "event_id", "session"):
        _validate_sha256(value[field], "operational {}".format(field))
    _validate_token(value["mode"], "operational mode")
    _validate_token(value["analyzer_version"], "analyzer version")
    _validate_token(value["status"], "analysis status")
    if value["status"] not in {item.value for item in AnalysisStatus}:
        raise OperationalJournalError("analysis status is unsupported")
    if type(value["duration_ms"]) is not int or value["duration_ms"] < 0:
        raise OperationalJournalError("operational duration must be non-negative")
    issues = value["issues"]
    if (
        not isinstance(issues, list)
        or len(issues) != len(set(issues))
        or any(
            not isinstance(issue, str) or _SAFE_TOKEN.fullmatch(issue) is None
            for issue in issues
        )
    ):
        raise OperationalJournalError("operational issues must be safe unique tokens")
    for field in ("ruff_version", "python_target", "python_target_source"):
        item = value[field]
        if item is not None and (
            not isinstance(item, str) or len(item) > 128 or "\x00" in item
        ):
            raise OperationalJournalError("operational {} is invalid".format(field))
    policies = value["policies"]
    if not isinstance(policies, list):
        raise OperationalJournalError("operational policies must be a list")
    identities = []
    for policy in policies:
        if not isinstance(policy, dict) or set(policy) != {"name", "version", "digest"}:
            raise OperationalJournalError("operational policy identity is malformed")
        _validate_token(policy["name"], "policy name")
        _validate_token(policy["version"], "policy version")
        _validate_sha256(policy["digest"], "operational policy digest")
        identities.append((policy["name"], policy["version"]))
    if len(identities) != len(set(identities)):
        raise OperationalJournalError("operational policies must be unique")
    if value["record_id"] != _record_id(value["event_id"], value["session"]):
        raise OperationalJournalError("operational record identity is inconsistent")
    return value


def _empty_state() -> Dict[str, Any]:
    return {
        "schema": OPERATIONAL_HEALTH_SCHEMA,
        "event_count": 0,
        "rate_counts": {name: 0 for name in _RATE_NAMES},
        "recent": [],
        "failure_streaks": [],
    }


def _validate_state(value: Any) -> Dict[str, Any]:
    required = {
        "schema",
        "event_count",
        "rate_counts",
        "recent",
        "failure_streaks",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise OperationalJournalError("operational summary has an invalid field set")
    if value["schema"] != OPERATIONAL_HEALTH_SCHEMA:
        raise OperationalJournalError("unsupported operational health schema")
    event_count = value["event_count"]
    if type(event_count) is not int or event_count < 0:
        raise OperationalJournalError("operational event count is invalid")
    rate_counts = value["rate_counts"]
    if not isinstance(rate_counts, dict) or set(rate_counts) != set(_RATE_NAMES):
        raise OperationalJournalError("operational rate counts are invalid")
    if any(
        type(rate_counts[name]) is not int
        or rate_counts[name] < 0
        or rate_counts[name] > event_count
        for name in _RATE_NAMES
    ) or sum(rate_counts.values()) > event_count:
        raise OperationalJournalError("operational rate counts are inconsistent")
    recent = value["recent"]
    if not isinstance(recent, list) or len(recent) > MAX_RECENT_RECORDS:
        raise OperationalJournalError("operational recent window is invalid")
    identities = []
    for event in recent:
        event = _validate_event(event)
        identities.append(event["record_id"])
    if len(identities) != len(set(identities)):
        raise OperationalJournalError("operational recent window has a duplicate record")
    if event_count < len(recent) or (event_count == 0) != (not recent):
        raise OperationalJournalError("operational recent window is inconsistent")
    failure_streaks = value["failure_streaks"]
    if (
        not isinstance(failure_streaks, list)
        or len(failure_streaks) > MAX_SESSION_STREAKS
    ):
        raise OperationalJournalError("operational failure streaks are invalid")
    sessions = []
    for streak in failure_streaks:
        if not isinstance(streak, dict) or set(streak) != {"session", "count"}:
            raise OperationalJournalError("operational failure streak is malformed")
        _validate_sha256(streak["session"], "operational failure session")
        if (
            type(streak["count"]) is not int
            or streak["count"] < 1
            or streak["count"] > event_count
        ):
            raise OperationalJournalError("operational failure count is invalid")
        sessions.append(streak["session"])
    if len(sessions) != len(set(sessions)):
        raise OperationalJournalError("operational failure sessions must be unique")
    return value


def _stable_event(value: Mapping[str, Any]) -> Dict[str, Any]:
    stable = dict(value)
    stable.pop("duration_ms", None)
    return stable


def _percentile_nearest_rank(values: Sequence[int], percentile: float) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int((len(ordered) * percentile) + 0.999999999))
    return ordered[min(rank, len(ordered)) - 1]


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


class OperationalJournal:
    """Maintain a bounded analyzer-health summary without source transcripts."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        self.path = self.root / "health.json"
        self.lock_path = self.root / "health.lock"

    def _read(self) -> Tuple[bytes, Dict[str, Any]]:
        if self.path.is_symlink():
            raise OperationalJournalError(
                "operational health summary is not an ordinary file"
            )
        if not self.path.exists():
            return b"", _empty_state()
        if not self.path.is_file():
            raise OperationalJournalError(
                "operational health summary is not an ordinary file"
            )
        payload = self.path.read_bytes()
        if not payload.endswith(b"\n"):
            raise OperationalJournalError(
                "operational health summary has a partial write"
            )
        try:
            state = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise OperationalJournalError(
                "operational health summary has malformed JSON"
            ) from error
        return payload, _validate_state(state)

    def _replace(self, payload: bytes) -> None:
        handle, temporary_name = tempfile.mkstemp(prefix=".health.", dir=self.root)
        temporary = Path(temporary_name)
        try:
            os.chmod(temporary, 0o600)
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            descriptor = os.open(str(self.root), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def record(
        self,
        session_id: str,
        mode: str,
        result: ReviewScanResult,
        *,
        status_override: Optional[AnalysisStatus] = None,
        issues_override: Optional[Sequence[str]] = None,
    ) -> Optional[str]:
        """Record once within the recent window and return a bounded notice."""

        if not isinstance(result, ReviewScanResult):
            raise OperationalJournalError("operational result must be typed")
        session = _session_key(session_id)
        evidence = result.evidence
        status = status_override or evidence.health.status
        if not isinstance(status, AnalysisStatus):
            raise OperationalJournalError("operational status override must be typed")
        issues = (
            tuple(issues_override)
            if issues_override is not None
            else tuple(evidence.health.issues)
        )
        issues = _operational_issues(status, issues)
        event = {
            "record_id": _record_id(evidence.event_id, session),
            "event_id": evidence.event_id,
            "session": session,
            "mode": mode,
            "analyzer_version": result.analyzer_version,
            "duration_ms": result.duration_ms,
            "status": status.value,
            "issues": list(issues),
            "ruff_version": evidence.ruff_version,
            "python_target": (
                evidence.python_target.value if evidence.python_target else None
            ),
            "python_target_source": (
                evidence.python_target_source.value
                if evidence.python_target_source
                else None
            ),
            "policies": [
                {
                    "name": policy.name,
                    "version": policy.version,
                    "digest": policy.digest,
                }
                for policy in evidence.policies
            ],
        }
        _validate_event(event)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise OperationalJournalError(
                "operational health root is not an ordinary directory"
            )
        if self.lock_path.is_symlink():
            raise OperationalJournalError("operational health lock is a symlink")
        consecutive = 0
        with self.lock_path.open("a+b") as lock:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            _, state = self._read()
            for prior in state["recent"]:
                if prior["record_id"] != event["record_id"]:
                    continue
                if _stable_event(prior) != _stable_event(event):
                    raise OperationalJournalError(
                        "operational record identity has conflicting content"
                    )
                return None

            state["event_count"] += 1
            if event["status"] == AnalysisStatus.TIMEOUT.value:
                state["rate_counts"]["timeout"] += 1
            if event["status"] == AnalysisStatus.UNAVAILABLE.value:
                state["rate_counts"]["unavailable"] += 1
            if event["status"].startswith("incompatible-"):
                state["rate_counts"]["incompatible"] += 1
            state["recent"].append(event)
            state["recent"] = state["recent"][-MAX_RECENT_RECORDS:]

            prior_streak = next(
                (
                    item
                    for item in state["failure_streaks"]
                    if item["session"] == session
                ),
                None,
            )
            state["failure_streaks"] = [
                item
                for item in state["failure_streaks"]
                if item["session"] != session
            ]
            if event["status"] in _FAILURE_STATUSES:
                consecutive = 1 + (prior_streak["count"] if prior_streak else 0)
                state["failure_streaks"].append(
                    {"session": session, "count": consecutive}
                )
                state["failure_streaks"] = state["failure_streaks"][
                    -MAX_SESSION_STREAKS:
                ]
            _validate_state(state)
            self._replace(_json_bytes(state))

        if event["status"] not in _FAILURE_STATUSES:
            return None
        if consecutive != 1 and consecutive % FAILURE_NOTICE_INTERVAL != 0:
            return None
        reason = event["issues"][0] if event["issues"] else event["status"]
        return (
            "review-after-commit analyzer health: {}; review delivery continues".format(
                reason
            )
        )

    def summary(self) -> Dict[str, Any]:
        """Return aggregate facts without exposing session identities."""

        payload, state = self._read()
        events = state["recent"]
        count = state["event_count"]
        if not events:
            return {
                "schema": OPERATIONAL_HEALTH_SCHEMA,
                "events": {
                    "count": 0,
                    "bytes": len(payload),
                    "retained": 0,
                    "retention_limit": MAX_RECENT_RECORDS,
                },
                "analyzer_version": None,
                "selected_mode": None,
                "last_health": None,
                "python_target": {"last": None, "source": None},
                "policies": [],
                "duration_ms": {
                    "sample_count": 0,
                    "sample_limit": MAX_RECENT_RECORDS,
                    "p50": None,
                    "p95": None,
                },
                "rates": {name: 0.0 for name in _RATE_NAMES},
            }
        last = events[-1]
        durations = [event["duration_ms"] for event in events]
        median = statistics.median(durations)
        return {
            "schema": OPERATIONAL_HEALTH_SCHEMA,
            "events": {
                "count": count,
                "bytes": len(payload),
                "retained": len(events),
                "retention_limit": MAX_RECENT_RECORDS,
            },
            "analyzer_version": last["analyzer_version"],
            "selected_mode": last["mode"],
            "last_health": {
                "status": last["status"],
                "issues": list(last["issues"]),
            },
            "python_target": {
                "last": last["python_target"],
                "source": last["python_target_source"],
            },
            "policies": list(last["policies"]),
            "duration_ms": {
                "sample_count": len(events),
                "sample_limit": MAX_RECENT_RECORDS,
                "p50": int(median) if float(median).is_integer() else median,
                "p95": _percentile_nearest_rank(durations, 0.95),
            },
            "rates": {
                name: state["rate_counts"][name] / count for name in _RATE_NAMES
            },
        }


__all__ = [
    "FAILURE_NOTICE_INTERVAL",
    "MAX_RECENT_RECORDS",
    "MAX_SESSION_STREAKS",
    "OPERATIONAL_HEALTH_SCHEMA",
    "OperationalJournal",
    "OperationalJournalError",
]
