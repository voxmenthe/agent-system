"""Private deferred-delivery state for the Antigravity lifecycle adapter."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

DELIVERY_SCHEMA = "review-antigravity-delivery/v1"
DEFAULT_DELIVERY_TTL_SECONDS = 15 * 60

_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_SNAPSHOT_STATES = frozenset(("preparing", "ready", "processing"))


class DeliveryStateError(ValueError):
    """Deferred state is malformed, conflicting, or attribution-unsafe."""


@dataclass(frozen=True)
class SnapshotReference:
    target: str
    tool_event_id: str


@dataclass(frozen=True)
class DeliveryReference:
    delivery_id: str
    tool_event_id: str
    repositories: Tuple[str, ...]
    events: Tuple[str, ...]


@dataclass(frozen=True)
class InvocationAction:
    retire: Tuple[str, ...]
    prepare: Tuple[SnapshotReference, ...]
    deliveries: Tuple[DeliveryReference, ...]


@dataclass(frozen=True)
class ToolClaim:
    target: str
    tool_event_id: str
    duplicate: bool


@dataclass(frozen=True)
class DeliveryMetadata:
    repositories: Tuple[str, ...]
    events: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.repositories or not self.events:
            raise DeliveryStateError("delivery metadata must identify a request")
        if len(set(self.repositories)) != len(self.repositories):
            raise DeliveryStateError("delivery repositories must be unique")
        if len(set(self.events)) != len(self.events):
            raise DeliveryStateError("delivery events must be unique")
        for value in (*self.repositories, *self.events):
            _require_sha256(value, "delivery identity")


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256_ID.fullmatch(value) is None:
        raise DeliveryStateError("{} must be a full SHA-256 identity".format(name))
    return value


def _conversation_key(conversation_id: str) -> str:
    if not isinstance(conversation_id, str) or not conversation_id:
        raise DeliveryStateError("conversation identity must be non-empty")
    return "sha256:" + hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()


def _now_seconds(value: Optional[int]) -> int:
    if value is None:
        return int(time.time())
    if type(value) is not int or value < 0:
        raise DeliveryStateError("delivery time must be a non-negative integer")
    return value


def _empty_state(conversation: str) -> Dict[str, Any]:
    return {
        "schema": DELIVERY_SCHEMA,
        "conversation": conversation,
        "invocation": None,
        "snapshots": {},
        "deliveries": {},
        "retiring": [],
        "last_steps": {},
    }


def _delivery_id(tool_event_id: str, metadata: DeliveryMetadata) -> str:
    payload = {
        "schema": "review-antigravity-delivery-id/v1",
        "tool_event_id": tool_event_id,
        "repositories": list(metadata.repositories),
        "events": list(metadata.events),
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _validate_state(value: Any, conversation: str) -> Dict[str, Any]:
    required = {
        "schema",
        "conversation",
        "invocation",
        "snapshots",
        "deliveries",
        "retiring",
        "last_steps",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise DeliveryStateError("Antigravity delivery state has an invalid field set")
    if value["schema"] != DELIVERY_SCHEMA or value["conversation"] != conversation:
        raise DeliveryStateError("Antigravity delivery state identity is incompatible")
    invocation = value["invocation"]
    if invocation is not None and (type(invocation) is not int or invocation < 0):
        raise DeliveryStateError("Antigravity invocation number is invalid")

    snapshots = value["snapshots"]
    if not isinstance(snapshots, dict):
        raise DeliveryStateError("Antigravity snapshots must be an object")
    snapshot_tools = set()
    for target, snapshot in snapshots.items():
        _require_sha256(target, "snapshot target")
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "tool_event_id",
            "status",
            "created_at",
            "step",
            "command",
        }:
            raise DeliveryStateError("Antigravity snapshot is malformed")
        tool_event_id = _require_sha256(snapshot["tool_event_id"], "snapshot event")
        if tool_event_id in snapshot_tools:
            raise DeliveryStateError("Antigravity snapshot event is duplicated")
        snapshot_tools.add(tool_event_id)
        status = snapshot["status"]
        if status not in _SNAPSHOT_STATES:
            raise DeliveryStateError("Antigravity snapshot status is invalid")
        if type(snapshot["created_at"]) is not int or snapshot["created_at"] < 0:
            raise DeliveryStateError("Antigravity snapshot time is invalid")
        step = snapshot["step"]
        command = snapshot["command"]
        if status == "processing":
            if type(step) is not int or step < 0:
                raise DeliveryStateError("processing snapshot step is invalid")
            _require_sha256(command, "processing command")
        elif step is not None or command is not None:
            raise DeliveryStateError("idle snapshot contains processing state")

    deliveries = value["deliveries"]
    if not isinstance(deliveries, dict):
        raise DeliveryStateError("Antigravity deliveries must be an object")
    for identity, delivery in deliveries.items():
        _require_sha256(identity, "delivery identity")
        if not isinstance(delivery, dict) or set(delivery) != {
            "tool_event_id",
            "repositories",
            "events",
            "created_at",
            "claimed_invocation",
        }:
            raise DeliveryStateError("Antigravity delivery is malformed")
        tool_event_id = _require_sha256(delivery["tool_event_id"], "delivery event")
        repositories = delivery["repositories"]
        events = delivery["events"]
        metadata = DeliveryMetadata(tuple(repositories), tuple(events)) if (
            isinstance(repositories, list) and isinstance(events, list)
        ) else None
        if metadata is None or identity != _delivery_id(tool_event_id, metadata):
            raise DeliveryStateError("Antigravity delivery identity is inconsistent")
        if type(delivery["created_at"]) is not int or delivery["created_at"] < 0:
            raise DeliveryStateError("Antigravity delivery time is invalid")
        claimed = delivery["claimed_invocation"]
        if claimed is not None and (type(claimed) is not int or claimed < 0):
            raise DeliveryStateError("Antigravity delivery claim is invalid")
        if invocation is not None and claimed is not None and claimed > invocation:
            raise DeliveryStateError("Antigravity delivery claim is from the future")

    retiring = value["retiring"]
    if (
        not isinstance(retiring, list)
        or len(retiring) != len(set(retiring))
        or any(_SHA256_ID.fullmatch(item) is None for item in retiring if isinstance(item, str))
        or any(not isinstance(item, str) for item in retiring)
    ):
        raise DeliveryStateError("Antigravity retiring events are invalid")

    last_steps = value["last_steps"]
    if not isinstance(last_steps, dict):
        raise DeliveryStateError("Antigravity last-step state must be an object")
    for target, item in last_steps.items():
        _require_sha256(target, "last-step target")
        if (
            not isinstance(item, dict)
            or set(item) != {"step", "command"}
            or type(item["step"]) is not int
            or item["step"] < 0
        ):
            raise DeliveryStateError("Antigravity last-step state is malformed")
        _require_sha256(item["command"], "last-step command")
    return value


class AntigravityDeliveryStore:
    """Journal deferred host delivery without storing paths or transcripts."""

    def __init__(
        self,
        root: Path,
        ttl_seconds: int = DEFAULT_DELIVERY_TTL_SECONDS,
    ) -> None:
        if type(ttl_seconds) is not int or ttl_seconds < 1:
            raise DeliveryStateError("delivery TTL must be a positive integer")
        self.root = Path(root).expanduser()
        self.ttl_seconds = ttl_seconds

    def _paths(self, conversation_id: str) -> Tuple[str, Path, Path]:
        conversation = _conversation_key(conversation_id)
        stem = conversation.split(":", 1)[1]
        return conversation, self.root / "{}.json".format(stem), self.root / "{}.lock".format(stem)

    @contextmanager
    def _locked(self, conversation_id: str) -> Iterator[Tuple[Path, Dict[str, Any]]]:
        conversation, state_path, lock_path = self._paths(conversation_id)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise DeliveryStateError("Antigravity delivery root is not a directory")
        with lock_path.open("a+", encoding="utf-8") as lock:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not state_path.exists():
                state = _empty_state(conversation)
            else:
                if state_path.is_symlink() or not state_path.is_file():
                    raise DeliveryStateError("Antigravity delivery state is not a file")
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, ValueError) as error:
                    raise DeliveryStateError("Antigravity delivery state is malformed") from error
                state = _validate_state(state, conversation)
            yield state_path, state

    def _write(self, path: Path, state: Dict[str, Any]) -> None:
        _validate_state(state, state["conversation"])
        payload = (
            json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        handle, name = tempfile.mkstemp(prefix=".delivery.", dir=self.root)
        temporary = Path(name)
        try:
            os.chmod(temporary, 0o600)
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            descriptor = os.open(str(self.root), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def begin_invocation(
        self,
        conversation_id: str,
        invocation: int,
        target_events: Mapping[str, str],
        *,
        now: Optional[int] = None,
    ) -> InvocationAction:
        if type(invocation) is not int or invocation < 0:
            raise DeliveryStateError("invocation number must be non-negative")
        if not isinstance(target_events, Mapping):
            raise DeliveryStateError("snapshot targets must be a mapping")
        for target, tool_event_id in target_events.items():
            _require_sha256(target, "snapshot target")
            _require_sha256(tool_event_id, "snapshot event")
        if len(set(target_events.values())) != len(target_events):
            raise DeliveryStateError("snapshot events must be unique")
        current_time = _now_seconds(now)
        with self._locked(conversation_id) as (path, state):
            current = state["invocation"]
            if current is not None and invocation < current:
                raise DeliveryStateError("invocation number moved backwards")
            if current is None or invocation > current:
                if any(
                    snapshot["status"] == "processing"
                    and max(0, current_time - snapshot["created_at"])
                    < self.ttl_seconds
                    for snapshot in state["snapshots"].values()
                ):
                    raise DeliveryStateError(
                        "cannot advance invocation while a tool delivery is processing"
                    )
                for snapshot in state["snapshots"].values():
                    event_id = snapshot["tool_event_id"]
                    if event_id not in state["retiring"]:
                        state["retiring"].append(event_id)
                for identity, delivery in list(state["deliveries"].items()):
                    claimed = delivery["claimed_invocation"]
                    age = max(0, current_time - delivery["created_at"])
                    if claimed is not None or age >= self.ttl_seconds:
                        del state["deliveries"][identity]
                state["invocation"] = invocation
                state["snapshots"] = {
                    target: {
                        "tool_event_id": tool_event_id,
                        "status": "preparing",
                        "created_at": current_time,
                        "step": None,
                        "command": None,
                    }
                    for target, tool_event_id in target_events.items()
                }
            elif set(target_events) != set(state["snapshots"]):
                raise DeliveryStateError(
                    "workspace snapshot targets changed within one invocation"
                )

            delivery_references: List[DeliveryReference] = []
            for identity, delivery in sorted(
                state["deliveries"].items(),
                key=lambda item: (item[1]["created_at"], item[0]),
            ):
                if delivery["claimed_invocation"] is None:
                    delivery["claimed_invocation"] = invocation
                if delivery["claimed_invocation"] == invocation:
                    delivery_references.append(
                        DeliveryReference(
                            identity,
                            delivery["tool_event_id"],
                            tuple(delivery["repositories"]),
                            tuple(delivery["events"]),
                        )
                    )
            prepare = tuple(
                SnapshotReference(target, snapshot["tool_event_id"])
                for target, snapshot in sorted(state["snapshots"].items())
                if snapshot["status"] == "preparing"
            )
            action = InvocationAction(
                tuple(state["retiring"]), prepare, tuple(delivery_references)
            )
            self._write(path, state)
            return action

    def confirm_retired(
        self, conversation_id: str, tool_event_ids: Sequence[str]
    ) -> None:
        requested = tuple(tool_event_ids)
        for item in requested:
            _require_sha256(item, "retiring event")
        with self._locked(conversation_id) as (path, state):
            if not requested:
                return
            state["retiring"] = [
                item for item in state["retiring"] if item not in set(requested)
            ]
            self._write(path, state)

    def mark_ready(
        self,
        conversation_id: str,
        invocation: int,
        snapshots: Sequence[SnapshotReference],
    ) -> None:
        with self._locked(conversation_id) as (path, state):
            if state["invocation"] != invocation:
                raise DeliveryStateError("snapshot invocation changed before activation")
            for reference in snapshots:
                current = state["snapshots"].get(reference.target)
                if current is None or current["tool_event_id"] != reference.tool_event_id:
                    raise DeliveryStateError("snapshot identity changed before activation")
                if current["status"] not in ("preparing", "ready"):
                    raise DeliveryStateError("processing snapshot cannot be reactivated")
                current["status"] = "ready"
                current["step"] = None
                current["command"] = None
            self._write(path, state)

    def claim_tools(
        self,
        conversation_id: str,
        claims: Sequence[Tuple[str, int, str]],
        *,
        now: Optional[int] = None,
    ) -> Tuple[ToolClaim, ...]:
        if not claims:
            return ()
        targets = [item[0] for item in claims]
        if len(targets) != len(set(targets)):
            raise DeliveryStateError("tool targets must be unique")
        for target, step, command in claims:
            _require_sha256(target, "tool target")
            if type(step) is not int or step < 0:
                raise DeliveryStateError("tool step must be non-negative")
            _require_sha256(command, "tool command")
        current_time = _now_seconds(now)
        with self._locked(conversation_id) as (path, state):
            actions: List[ToolClaim] = []
            for target, step, command in claims:
                previous = state["last_steps"].get(target)
                if previous is not None and step <= previous["step"]:
                    if step == previous["step"] and command == previous["command"]:
                        actions.append(ToolClaim(target, "", True))
                        continue
                    raise DeliveryStateError("tool step replay conflicts with prior input")
                snapshot = state["snapshots"].get(target)
                if snapshot is None:
                    raise DeliveryStateError(
                        "tool target has no exact pre-invocation snapshot"
                    )
                if snapshot["status"] == "preparing":
                    raise DeliveryStateError("pre-invocation snapshot is not ready")
                if snapshot["status"] == "processing":
                    if snapshot["step"] != step or snapshot["command"] != command:
                        raise DeliveryStateError(
                            "another tool is already using the pre-invocation snapshot"
                        )
                    age = max(0, current_time - snapshot["created_at"])
                    if age < self.ttl_seconds:
                        actions.append(ToolClaim(target, "", True))
                        continue
                else:
                    snapshot["status"] = "processing"
                    snapshot["step"] = step
                    snapshot["command"] = command
                snapshot["created_at"] = current_time
                actions.append(ToolClaim(target, snapshot["tool_event_id"], False))
            self._write(path, state)
            return tuple(actions)

    def abandon_tool(
        self,
        conversation_id: str,
        target: str,
        step: int,
        command: str,
        *,
        now: Optional[int] = None,
    ) -> None:
        """Release one matching claim after bounded processing fails."""

        _require_sha256(target, "tool target")
        _require_sha256(command, "tool command")
        if type(step) is not int or step < 0:
            raise DeliveryStateError("tool step must be non-negative")
        current_time = _now_seconds(now)
        with self._locked(conversation_id) as (path, state):
            snapshot = state["snapshots"].get(target)
            if (
                snapshot is None
                or snapshot["status"] != "processing"
                or snapshot["step"] != step
                or snapshot["command"] != command
            ):
                previous = state["last_steps"].get(target)
                if previous == {"step": step, "command": command}:
                    return
                raise DeliveryStateError("tool abandonment has no matching snapshot claim")
            snapshot["status"] = "ready"
            snapshot["created_at"] = current_time
            snapshot["step"] = None
            snapshot["command"] = None
            self._write(path, state)

    def complete_tool(
        self,
        conversation_id: str,
        target: str,
        step: int,
        command: str,
        next_tool_event_id: str,
        metadata: Optional[DeliveryMetadata],
        *,
        now: Optional[int] = None,
    ) -> None:
        _require_sha256(target, "tool target")
        _require_sha256(command, "tool command")
        _require_sha256(next_tool_event_id, "next snapshot event")
        if type(step) is not int or step < 0:
            raise DeliveryStateError("tool step must be non-negative")
        current_time = _now_seconds(now)
        with self._locked(conversation_id) as (path, state):
            snapshot = state["snapshots"].get(target)
            if (
                snapshot is None
                or snapshot["status"] != "processing"
                or snapshot["step"] != step
                or snapshot["command"] != command
            ):
                previous = state["last_steps"].get(target)
                if previous == {"step": step, "command": command}:
                    return
                raise DeliveryStateError("tool completion has no matching snapshot claim")
            if metadata is not None:
                identity = _delivery_id(snapshot["tool_event_id"], metadata)
                delivery = {
                    "tool_event_id": snapshot["tool_event_id"],
                    "repositories": list(metadata.repositories),
                    "events": list(metadata.events),
                    "created_at": current_time,
                    "claimed_invocation": None,
                }
                existing = state["deliveries"].get(identity)
                if existing is not None and existing != delivery:
                    raise DeliveryStateError("deferred delivery identity conflicts")
                state["deliveries"][identity] = delivery
            state["snapshots"][target] = {
                "tool_event_id": next_tool_event_id,
                "status": "ready",
                "created_at": current_time,
                "step": None,
                "command": None,
            }
            state["last_steps"][target] = {"step": step, "command": command}
            self._write(path, state)

    def summary(self, *, now: Optional[int] = None) -> Dict[str, Any]:
        """Return bounded aggregate pending facts without conversation identity."""

        current_time = _now_seconds(now)
        if not self.root.exists():
            return {
                "schema": DELIVERY_SCHEMA,
                "conversations": 0,
                "pending": 0,
                "oldest_pending_seconds": None,
                "stale": 0,
                "snapshots": {"preparing": 0, "ready": 0, "processing": 0},
            }
        if self.root.is_symlink() or not self.root.is_dir():
            raise DeliveryStateError("Antigravity delivery root is not a directory")
        conversations = 0
        ages: List[int] = []
        stale = 0
        snapshot_counts = {"preparing": 0, "ready": 0, "processing": 0}
        for path in sorted(self.root.glob("*.json")):
            stem = path.stem
            conversation = "sha256:{}".format(stem)
            if _SHA256_ID.fullmatch(conversation) is None or path.is_symlink():
                raise DeliveryStateError("Antigravity delivery journal is malformed")
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError) as error:
                raise DeliveryStateError("Antigravity delivery journal is malformed") from error
            state = _validate_state(state, conversation)
            conversations += 1
            for delivery in state["deliveries"].values():
                age = max(0, current_time - delivery["created_at"])
                ages.append(age)
                if delivery["claimed_invocation"] is None and age >= self.ttl_seconds:
                    stale += 1
            for snapshot in state["snapshots"].values():
                snapshot_counts[snapshot["status"]] += 1
        return {
            "schema": DELIVERY_SCHEMA,
            "conversations": conversations,
            "pending": len(ages),
            "oldest_pending_seconds": max(ages) if ages else None,
            "stale": stale,
            "snapshots": snapshot_counts,
        }
