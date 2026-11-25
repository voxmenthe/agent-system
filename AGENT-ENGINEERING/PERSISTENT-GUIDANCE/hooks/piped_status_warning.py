#!/usr/bin/env python3
"""Warn, never block, when a Bash command pipes a check through a filter and then reads `$?`.

`$?` after `CHECK | tail` is tail's status, so a failed check reads as a pass. The testing pack's rule
did not stop it: 22 such commands in the 15 days before the October 27 sync, five in the five days
after (RX-2). The warning reaches the agent as context before the command runs; the command still
runs. The patterns are the RX-2 helper's
(.learning-workspace/reference-readacross/helpers/piped_status_misreads.py), so its counts stay
comparable.
"""

from __future__ import annotations

import json
import re
import sys

CHECK = re.compile(r"\b(tsc|pytest|unittest|npm (run )?test|go test|cargo|check|validate|lint|ruff|mypy|"
                   r"shellcheck|bun test|vitest)\b")
MISREAD = re.compile(r"([^|;\n&]+)\|[^;\n&]*?\b(tail|head|grep|sed|awk|cut|sort|wc)\b[^;\n|&]*;\s*"
                     r"(echo[^;\n]*\$\?|[A-Za-z_]+=\$\?)")
# A heredoc's body is text the command writes, such as notes quoting an earlier misread, not commands it runs.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", re.DOTALL | re.MULTILINE)
# Single-quoted text is never expanded or run: a prompt for an agent CLI, a regex, a quoted example.
SINGLE_QUOTED = re.compile(r"'[^']*'")
WARNING = ("This command reads `$?` after piping `{check}` through `{filter}`: that is {filter}'s status, "
           "not the check's, so a failure would read as a pass. Read `${{PIPESTATUS[0]}}` immediately after "
           "the pipeline, or write the output to a file and read the check's own status.")


def warning(command: str) -> str | None:
    if "PIPESTATUS" in command or "pipefail" in command:
        return None
    found = MISREAD.search(SINGLE_QUOTED.sub("", HEREDOC.sub("", command)).replace("2>&1", ""))
    if found is None or CHECK.search(found.group(1)) is None:
        return None
    return WARNING.format(check=found.group(1).strip(), filter=found.group(2))


def _run() -> int:
    event = json.load(sys.stdin)
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command")
    message = warning(command) if isinstance(command, str) else None
    if message:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": message}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_run())
    except (ValueError, TypeError, AttributeError) as error:
        # Exit 1 is a non-blocking hook error: the command still runs.
        print(f"piped-status-warning: {str(error).replace(chr(10), ' ')}", file=sys.stderr)
        sys.exit(1)
