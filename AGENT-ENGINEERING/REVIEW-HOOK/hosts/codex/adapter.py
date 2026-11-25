#!/usr/bin/env python3
"""Codex lifecycle adapter for the repository-owned review runtime."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

SOURCE_ROOT = Path(__file__).resolve().parents[2]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from runtime.delivery import render_decision  # noqa: E402
from runtime.review_core import ReviewAfterCommit  # noqa: E402


def _required_string(payload: Dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError("hook input field {!r} must be a non-empty string".format(field))
    return value


def main() -> int:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("hook input must be a JSON object")
    event = payload.get("hook_event_name")
    if event not in {"PreToolUse", "PostToolUse"} or payload.get("tool_name") != "Bash":
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise ValueError("hook input field 'tool_input' must be an object")
    command = tool_input.get("command")
    if not isinstance(command, str):
        raise ValueError("hook command must be a string")

    reviewer = ReviewAfterCommit.from_environment(
        "CODEX_HOOK_STATE_DIR",
        "CODEX_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY",
        "CODEX_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY",
        "REVIEW_AFTER_COMMIT_MODE",
    )
    targets = reviewer.find_commit_targets(command, _required_string(payload, "cwd"))
    if not targets:
        return 0

    session_id = _required_string(payload, "session_id")
    tool_use_id = _required_string(payload, "tool_use_id")
    if event == "PreToolUse":
        reviewer.record_before(session_id, tool_use_id, targets)
        return 0

    decision = reviewer.review_event(session_id, tool_use_id, replay_processed=False)
    deliveries = (
        reviewer.record_delivery(decision, "codex", session_id)
        if decision is not None
        else {}
    )
    for notice in reviewer.take_operational_notices():
        print(notice, file=sys.stderr)
    if decision is None:
        return 0
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": render_decision(decision, deliveries),
            }
        },
        sys.stdout,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as error:
        raise SystemExit("review-after-commit Codex hook: {}".format(error)) from error
