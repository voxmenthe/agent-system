"""Strict, session-scoped cadence state with durable atomic replacement."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

STATE_SCHEMA = "review-cadence-state/v1"

_FULL_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")

State = Dict[str, Any]
TargetValidator = Callable[[Any], bool]


def empty_state(
    branch_every: Optional[int],
    standard_every: int,
) -> State:
    """Return a new state document for one host session."""

    return {
        "schema": STATE_SCHEMA,
        "branch_every": branch_every,
        "standard_every": standard_every,
        "count": 0,
        "events": {},
        "commits": [],
        "pending": {},
        "ignored": [],
    }


def session_paths(state_dir: Path, session_id: str) -> Tuple[Path, Path]:
    """Create the private state root and derive non-identifying session paths."""

    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not state_dir.is_dir():
        raise ValueError("hook state root must be a directory: {}".format(state_dir))
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return state_dir / "{}.json".format(session_key), state_dir / "{}.lock".format(
        session_key
    )


@contextmanager
def locked_session(
    state_dir: Path,
    session_id: str,
    branch_every: Optional[int],
    standard_every: int,
    target_validator: TargetValidator,
) -> Iterator[Tuple[Path, State]]:
    """Lock and load one session; callers explicitly decide whether to write."""

    state_path, lock_path = session_paths(state_dir, session_id)
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield state_path, load_state(
            state_path,
            branch_every,
            standard_every,
            target_validator,
        )


def _valid_range(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "repository",
        "before",
        "after",
        "commits",
    }:
        return False
    commits = value["commits"]
    return (
        isinstance(value["repository"], str)
        and _SHA256_ID.fullmatch(value["repository"]) is not None
        and isinstance(value["before"], str)
        and _FULL_OID.fullmatch(value["before"]) is not None
        and isinstance(value["after"], str)
        and _FULL_OID.fullmatch(value["after"]) is not None
        and value["before"] != value["after"]
        and type(commits) is int
        and commits >= 1
    )


def load_state(
    path: Path,
    branch_every: Optional[int],
    standard_every: int,
    target_validator: TargetValidator,
) -> State:
    """Load and fully validate one current-format state document."""

    if not path.exists():
        return empty_state(branch_every, standard_every)
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("invalid hook state shape in {}".format(path))
    if state.get("schema") != STATE_SCHEMA:
        raise ValueError("unsupported hook state in {}".format(path))
    if set(state) != {
        "schema",
        "branch_every",
        "standard_every",
        "count",
        "events",
        "commits",
        "pending",
        "ignored",
    }:
        raise ValueError("invalid hook state shape in {}".format(path))

    stored_branch_every = state["branch_every"]
    stored_standard_every = state["standard_every"]
    if stored_branch_every is not None and (
        type(stored_branch_every) is not int or stored_branch_every < 1
    ):
        raise ValueError("invalid branch review interval in {}".format(path))
    if type(stored_standard_every) is not int or stored_standard_every < 1:
        raise ValueError("invalid standard review interval in {}".format(path))
    if stored_branch_every != branch_every:
        raise ValueError(
            "hook cadence changed for active state in {}: expected {!r}, received {!r}".format(
                path, stored_branch_every, branch_every
            )
        )
    if stored_standard_every != standard_every:
        raise ValueError(
            "hook cadence changed for active state in {}: expected {!r}, received {!r}".format(
                path, stored_standard_every, standard_every
            )
        )

    count = state["count"]
    events = state["events"]
    commits = state["commits"]
    pending = state["pending"]
    ignored = state["ignored"]
    if type(count) is not int or count < 0:
        raise ValueError("invalid hook count in {}".format(path))
    if not all(
        isinstance(value, expected)
        for value, expected in (
            (events, dict),
            (commits, list),
            (pending, dict),
            (ignored, list),
        )
    ):
        raise ValueError("invalid hook state collections in {}".format(path))

    flattened_counts = []
    for tool_id, event in events.items():
        if (
            not isinstance(tool_id, str)
            or not tool_id
            or not isinstance(event, dict)
            or set(event) != {"counts", "ranges"}
        ):
            raise ValueError("invalid hook event state in {}".format(path))
        counts = event["counts"]
        ranges = event["ranges"]
        if (
            not isinstance(counts, list)
            or not counts
            or any(type(event_count) is not int for event_count in counts)
        ):
            raise ValueError("invalid hook event state in {}".format(path))
        if (
            not isinstance(ranges, list)
            or not ranges
            or not all(_valid_range(item) for item in ranges)
            or sum(item["commits"] for item in ranges) != len(counts)
        ):
            raise ValueError("invalid exact ranges in {}".format(path))
        flattened_counts.extend(counts)
    if sorted(flattened_counts) != list(range(1, count + 1)):
        raise ValueError("inconsistent hook event count in {}".format(path))
    if (
        len(commits) != count
        or any(
            not isinstance(commit, str)
            or re.fullmatch(r"[0-9a-f]{64}", commit) is None
            for commit in commits
        )
        or len(set(commits)) != len(commits)
    ):
        raise ValueError("inconsistent recorded commits in {}".format(path))
    if any(
        not isinstance(tool_id, str)
        or not tool_id
        or not isinstance(targets, list)
        or not targets
        or not all(target_validator(target) for target in targets)
        for tool_id, targets in pending.items()
    ):
        raise ValueError("invalid pending hook state in {}".format(path))
    if any(not isinstance(tool_id, str) or not tool_id for tool_id in ignored):
        raise ValueError("invalid ignored hook state in {}".format(path))
    if len(set(ignored)) != len(ignored):
        raise ValueError("duplicate ignored hook events in {}".format(path))
    event_ids = set(events)
    pending_ids = set(pending)
    ignored_ids = set(ignored)
    if event_ids & pending_ids or event_ids & ignored_ids or pending_ids & ignored_ids:
        raise ValueError("overlapping hook event state in {}".format(path))
    return state


def write_state(path: Path, state: State) -> None:
    """Atomically replace one state file and durably sync its directory entry."""

    handle, temporary_name = tempfile.mkstemp(prefix=".{}.".format(path.name), dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)
