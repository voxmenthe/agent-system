#!/usr/bin/env python3
"""Antigravity adapter using pre-invocation snapshots and deferred context."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

PLUGIN_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = (
    PLUGIN_ROOT
    if (PLUGIN_ROOT / "runtime").is_dir()
    else Path(__file__).resolve().parents[3]
)
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from antigravity_state import (  # noqa: E402
    AntigravityDeliveryStore,
    DeliveryMetadata,
    DeliveryReference,
    DeliveryStateError,
    SnapshotReference,
)

from runtime.delivery import render_decision  # noqa: E402
from runtime.review_core import (  # noqa: E402
    MAX_TARGETS,
    ReviewAfterCommit,
    ReviewDecision,
)


class AdapterError(ValueError):
    """Antigravity input cannot satisfy the exact lifecycle contract."""


def _write_json(value: Mapping[str, Any]) -> None:
    json.dump(value, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise AdapterError("hook field {!r} must be a non-empty string".format(field))
    return value


def _required_index(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if type(value) is not int or value < 0:
        raise AdapterError("hook field {!r} must be non-negative".format(field))
    return value


def _payload() -> Dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise AdapterError("hook input must be a JSON object")
    return value


def _reviewer() -> ReviewAfterCommit:
    return ReviewAfterCommit.from_environment(
        "ANTIGRAVITY_HOOK_STATE_DIR",
        "ANTIGRAVITY_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY",
        "ANTIGRAVITY_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY",
        "REVIEW_AFTER_COMMIT_MODE",
    )


def _store() -> AntigravityDeliveryStore:
    raw = os.environ.get("ANTIGRAVITY_HOOK_STATE_DIR")
    if not raw:
        raise AdapterError("ANTIGRAVITY_HOOK_STATE_DIR is required")
    return AntigravityDeliveryStore(Path(raw).expanduser() / "delivery")


def _sha256_contract(name: str, *parts: str) -> str:
    payload = "{}\0{}".format(name, "\0".join(parts)).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _target_identity(target: Mapping[str, Any]) -> str:
    cwd = target.get("cwd")
    argv = target.get("argv")
    if not isinstance(cwd, str) or not isinstance(argv, list):
        raise AdapterError("commit target is malformed")
    material = json.dumps(
        {"cwd": cwd, "argv": argv}, sort_keys=True, separators=(",", ":")
    )
    return _sha256_contract("review-antigravity-target/v1", material)


def _tool_event_id(
    conversation_id: str, phase: str, number: int, target: str
) -> str:
    conversation = _sha256_contract(
        "review-antigravity-conversation/v1", conversation_id
    )
    return _sha256_contract(
        "review-antigravity-tool-event/v1",
        conversation,
        phase,
        str(number),
        target,
    )


def _workspace_targets(
    reviewer: ReviewAfterCommit, workspace_paths: Any
) -> Dict[str, Dict[str, Any]]:
    if not isinstance(workspace_paths, list):
        raise AdapterError("workspacePaths must be a list")
    targets: Dict[str, Dict[str, Any]] = {}
    for raw in workspace_paths:
        if not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
            raise AdapterError("workspacePaths must contain absolute paths")
        for target in reviewer.find_commit_targets("git commit", raw):
            identity = _target_identity(target)
            targets.setdefault(identity, target)
            if len(targets) > MAX_TARGETS:
                raise AdapterError(
                    "workspace snapshot exceeds the bounded repository count"
                )
    return targets


def _decision_metadata(decision: ReviewDecision) -> DeliveryMetadata:
    return DeliveryMetadata(
        tuple(request.repository.digest for request in decision.requests),
        tuple(request.event_id for request in decision.requests),
    )


def _render_delivery(
    reviewer: ReviewAfterCommit,
    conversation_id: str,
    reference: DeliveryReference,
) -> str:
    decision = reviewer.review_event(conversation_id, reference.tool_event_id)
    if decision is None:
        raise DeliveryStateError("deferred request no longer resolves to a decision")
    metadata = _decision_metadata(decision)
    if (
        metadata.repositories != reference.repositories
        or metadata.events != reference.events
    ):
        raise DeliveryStateError("deferred request changed after it was recorded")
    deliveries = reviewer.record_delivery(
        decision, "antigravity", reference.delivery_id
    )
    return render_decision(decision, deliveries)


def _pre_invocation(payload: Dict[str, Any]) -> None:
    conversation_id = _required_string(payload, "conversationId")
    invocation = _required_index(payload, "invocationNum")
    reviewer = _reviewer()
    store = _store()
    targets = _workspace_targets(reviewer, payload.get("workspacePaths"))
    event_ids = {
        target: _tool_event_id(conversation_id, "invocation", invocation, target)
        for target in targets
    }
    action = store.begin_invocation(conversation_id, invocation, event_ids)

    for tool_event_id in action.retire:
        reviewer.discard_pending(conversation_id, tool_event_id)
    store.confirm_retired(conversation_id, action.retire)

    prepared: List[SnapshotReference] = []
    for reference in action.prepare:
        target = targets.get(reference.target)
        if target is None:
            raise DeliveryStateError("preparing target is outside the current workspace")
        reviewer.record_before(
            conversation_id, reference.tool_event_id, [target]
        )
        prepared.append(reference)
    if prepared:
        store.mark_ready(conversation_id, invocation, prepared)

    messages = [
        _render_delivery(reviewer, conversation_id, reference)
        for reference in action.deliveries
    ]
    for notice in reviewer.take_operational_notices():
        print(notice, file=sys.stderr)
    if messages:
        _write_json(
            {
                "injectSteps": [
                    {"ephemeralMessage": "\n\n".join(messages)}
                ]
            }
        )
    else:
        _write_json({})


def _post_tool_use(payload: Dict[str, Any]) -> None:
    conversation_id = _required_string(payload, "conversationId")
    step = _required_index(payload, "stepIdx")
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict) or tool_call.get("name") != "run_command":
        _write_json({})
        return
    error = payload.get("error")
    if error not in (None, ""):
        if not isinstance(error, str):
            raise AdapterError("hook error field must be a string")
        _write_json({})
        return
    arguments = tool_call.get("args")
    if not isinstance(arguments, dict):
        raise AdapterError("run_command args must be an object")
    command = _required_string(arguments, "CommandLine")
    cwd = _required_string(arguments, "Cwd")
    reviewer = _reviewer()
    targets = reviewer.find_commit_targets(command, cwd)
    if not targets:
        _write_json({})
        return
    by_identity = {_target_identity(target): target for target in targets}
    if len(by_identity) != len(targets):
        raise AdapterError("run_command contains duplicate commit targets")
    command_identity = _sha256_contract(
        "review-antigravity-command/v1", command, cwd
    )
    store = _store()
    claims = store.claim_tools(
        conversation_id,
        [
            (target, step, command_identity)
            for target in sorted(by_identity)
        ],
    )
    for claim in claims:
        if claim.duplicate:
            continue
        target = by_identity[claim.target]
        try:
            decision = reviewer.review_event(conversation_id, claim.tool_event_id)
            next_tool_event_id = _tool_event_id(
                conversation_id, "post-tool", step, claim.target
            )
            reviewer.record_before(conversation_id, next_tool_event_id, [target])
            store.complete_tool(
                conversation_id,
                claim.target,
                step,
                command_identity,
                next_tool_event_id,
                _decision_metadata(decision) if decision is not None else None,
            )
        except Exception:
            store.abandon_tool(
                conversation_id,
                claim.target,
                step,
                command_identity,
            )
            raise
    for notice in reviewer.take_operational_notices():
        print(notice, file=sys.stderr)
    _write_json({})


def main(argv: Sequence[str]) -> int:
    if len(argv) != 1 or argv[0] not in {"pre-invocation", "post-tool-use"}:
        raise AdapterError("adapter requires a supported lifecycle event")
    if os.environ.get("REVIEW_AFTER_COMMIT_MODE") is None:
        _write_json({})
        return 0
    payload = _payload()
    if argv[0] == "pre-invocation":
        _pre_invocation(payload)
    else:
        _post_tool_use(payload)
    return 0


def _error_message(error: Exception) -> str:
    if isinstance(error, (AdapterError, DeliveryStateError)):
        return str(error)
    return type(error).__name__


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as error:
        print(
            "review-after-commit Antigravity hook: {}".format(
                _error_message(error)
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error
