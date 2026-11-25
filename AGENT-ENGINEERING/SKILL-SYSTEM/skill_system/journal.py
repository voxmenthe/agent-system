from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .model import (
    OPERATION_SCHEMA_VERSION,
    ValidationError,
    load_json,
    validate_timestamp,
)


HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMON_KEYS = {
    "schema_version",
    "operation_id",
    "type",
    "status",
    "phase",
    "created_at",
    "updated_at",
    "changes",
    "details",
}
DETAIL_KEYS = {
    "install": {
        "skill",
        "source",
        "source_hash",
        "target",
        "target_hash_before",
        "new_hash",
        "preimage_exists",
        "state_preimage_exists",
        "registry_revision",
    },
    "quarantine": {
        "skill",
        "target",
        "target_hash",
        "quarantine_path",
        "state_preimage_exists",
    },
    "lock-migration": {
        "lock_path",
        "pre_hash",
        "post_hash",
        "removed",
    },
}
PHASES = {
    "install": {
        "prepared",
        "preimage-preserved",
        "target-installed",
        "state-committed",
        "committed",
        "rolled-back",
    },
    "quarantine": {
        "prepared",
        "target-quarantined",
        "state-committed",
        "committed",
        "rolled-back",
    },
    "lock-migration": {
        "prepared",
        "lock-replaced",
        "committed",
        "rolled-back",
    },
}


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing:
        raise ValidationError(f"{label} missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValidationError(f"{label} unknown field(s): {', '.join(sorted(unknown))}")


def _string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} must be a non-empty string")


def _hash(value: Any, label: str) -> None:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValidationError(f"{label} must be a sha256 content hash")


def _validate_details(kind: str, details_value: Any) -> None:
    details = _mapping(details_value, "operation journal details")
    _exact_keys(details, DETAIL_KEYS[kind], "operation journal details")
    if kind == "install":
        for key in ("skill", "source", "target"):
            _string(details[key], f"operation journal details.{key}")
        for key in ("source_hash", "new_hash", "registry_revision"):
            _hash(details[key], f"operation journal details.{key}")
        if details["target_hash_before"] is not None:
            _hash(
                details["target_hash_before"],
                "operation journal details.target_hash_before",
            )
        for key in ("preimage_exists", "state_preimage_exists"):
            if type(details[key]) is not bool:
                raise ValidationError(
                    f"operation journal details.{key} must be a boolean"
                )
    elif kind == "quarantine":
        for key in ("skill", "target", "quarantine_path"):
            _string(details[key], f"operation journal details.{key}")
        _hash(details["target_hash"], "operation journal details.target_hash")
        if type(details["state_preimage_exists"]) is not bool:
            raise ValidationError(
                "operation journal details.state_preimage_exists must be a boolean"
            )
    else:
        _string(details["lock_path"], "operation journal details.lock_path")
        _hash(details["pre_hash"], "operation journal details.pre_hash")
        _hash(details["post_hash"], "operation journal details.post_hash")
        removed = details["removed"]
        if (
            not isinstance(removed, list)
            or any(not isinstance(item, str) or not item for item in removed)
            or len(removed) != len(set(removed))
        ):
            raise ValidationError(
                "operation journal details.removed must contain unique names"
            )


def load_operation(path: Path) -> dict[str, Any]:
    data = _mapping(load_json(path, "operation journal"), "operation journal")
    _exact_keys(data, COMMON_KEYS, "operation journal")
    if data["schema_version"] != OPERATION_SCHEMA_VERSION:
        raise ValidationError(
            f"unsupported operation schema_version {data['schema_version']!r}"
        )
    kind = data["type"]
    if kind not in DETAIL_KEYS:
        raise ValidationError(f"invalid operation type {kind!r}")
    status = data["status"]
    if status not in {"in-progress", "rolling-back", "committed", "rolled-back"}:
        raise ValidationError(f"invalid operation status {status!r}")
    phase = data["phase"]
    if phase not in PHASES[kind]:
        raise ValidationError(f"invalid operation phase {phase!r} for {kind}")
    if status == "committed" and phase != "committed":
        raise ValidationError("committed operation must have committed phase")
    if status == "rolled-back" and phase != "rolled-back":
        raise ValidationError("rolled-back operation must have rolled-back phase")
    if status == "in-progress" and phase in {"committed", "rolled-back"}:
        raise ValidationError("in-progress operation has a terminal phase")
    if status == "rolling-back" and phase == "rolled-back":
        raise ValidationError("rolling-back operation has a rolled-back phase")
    _string(data["operation_id"], "operation journal.operation_id")
    for key in ("created_at", "updated_at"):
        validate_timestamp(data[key], f"operation journal.{key}")
    if path.parent.name != data["operation_id"]:
        raise ValidationError("operation journal ID does not match its directory")
    if not isinstance(data["changes"], list) or any(
        not isinstance(item, str) for item in data["changes"]
    ):
        raise ValidationError("operation journal changes must be strings")
    _validate_details(kind, data["details"])
    return data


def list_incomplete_operations(transactions: Path) -> tuple[str, ...]:
    if not transactions.is_dir():
        return ()
    incomplete: list[str] = []
    for operation_path in sorted(transactions.glob("*/operation.json")):
        operation = load_operation(operation_path)
        if operation["status"] in {"in-progress", "rolling-back"}:
            incomplete.append(operation["operation_id"])
    return tuple(incomplete)
