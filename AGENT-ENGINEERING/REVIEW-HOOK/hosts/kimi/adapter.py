#!/usr/bin/env python3
"""Kimi Code lifecycle adapter for the repository-owned review runtime."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

SOURCE_ROOT = Path(__file__).resolve().parents[2]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from runtime.delivery import render_decision  # noqa: E402
from runtime.review_core import ReviewAfterCommit  # noqa: E402

RETRY_REMINDER = (
    "After completing the advisory review, reconsider and retry the blocked "
    "Bash command if it is still necessary."
)


def _required_string(payload: Dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError("hook input field {!r} must be a non-empty string".format(field))
    return value


def _deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
        sort_keys=True,
    )
    sys.stdout.write("\n")


def main() -> int:
    enabled = os.environ.get("KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED")
    if enabled not in {None, "0", "1"}:
        raise ValueError("KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED must be 0 or 1")
    if enabled != "1":
        return 0

    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("hook input must be a JSON object")
    event = payload.get("hook_event_name")
    if event not in {"PreToolUse", "Stop"}:
        return 0
    if event == "PreToolUse" and payload.get("tool_name") != "Bash":
        return 0

    session_id = _required_string(payload, "session_id")
    reviewer = ReviewAfterCommit.from_environment(
        "KIMI_HOOK_STATE_DIR",
        "KIMI_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY",
        "KIMI_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY",
        "REVIEW_AFTER_COMMIT_MODE",
    )

    if event == "Stop":
        decision = reviewer.review_pending(session_id)
        deliveries = (
            reviewer.record_delivery(decision, "kimi", session_id)
            if decision is not None
            else {}
        )
        for notice in reviewer.take_operational_notices():
            print(notice, file=sys.stderr)
        if decision is not None:
            _deny(render_decision(decision, deliveries))
        return 0

    pending_decision = reviewer.review_pending(session_id)
    deliveries = (
        reviewer.record_delivery(pending_decision, "kimi", session_id)
        if pending_decision is not None
        else {}
    )
    for notice in reviewer.take_operational_notices():
        print(notice, file=sys.stderr)
    if pending_decision is not None:
        _deny(
            "{}\n\n{}".format(
                render_decision(pending_decision, deliveries), RETRY_REMINDER
            )
        )
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise ValueError("hook input field 'tool_input' must be an object")
    command = tool_input.get("command")
    if not isinstance(command, str):
        raise ValueError("hook command must be a string")
    targets = reviewer.find_commit_targets(
        command, _required_string(payload, "cwd")
    )
    if targets:
        reviewer.record_before(
            session_id,
            _required_string(payload, "tool_call_id"),
            targets,
        )
    return 0


def _report_error(error: Exception) -> None:
    message = "review-after-commit Kimi hook: {}".format(error)
    print(message, file=sys.stderr)
    state_dir = os.environ.get("KIMI_HOOK_STATE_DIR")
    if not state_dir:
        return
    try:
        log_dir = Path(state_dir).expanduser()
        log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (log_dir / "hook.log").open("a", encoding="utf-8") as stream:
            stream.write("{}\n".format(message))
    except OSError:
        pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as error:
        _report_error(error)
        raise SystemExit(1) from error
