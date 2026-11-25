#!/usr/bin/env python3
"""Whether a failed launch was refused by the launcher, so later tasks on it would fail the same way.

    refusals.py [--launcher NAME] FILE...

prints "rate-limited: REASON" (a rate limit or quota), "quarantined: REASON" (an expired key, a missing
credential, a signed-out CLI, a free window or plan that ended, a model the provider no longer routes, or another
non-retryable refusal) or "unclassified", from the last 8 KiB of each FILE, where a CLI's final error lands. A rate
limit counts only on a line the CLI writes as its own error record: a worker's transcript that quotes one is not a
refusal. An unclassified failure may be the task's own.
A plan quota that leaves no allowance on the whole account reads "rate-limited: account quota exhausted on
HARNESS", HARNESS as in launcher-routes.tsv; run-wave.sh then bars every launcher on that account.
A record one harness writes (a Codex quota, an OpenCode no-route) counts only from that harness's launchers when
--launcher names the one that failed: another harness's transcript may print it verbatim (`cat E.stderr`).

This is the one table: run-worker.sh prints its answer as a failed run's last stderr line, and the market pool
(scripts/grok-X-adhoc/delegate_pool.py) loads it from the installed skill.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TAIL_BYTES = 8192
# Marks a tail's first line when the cut fell inside it: no ^-anchored record can match there.
CUT = "\0"

# 10-20: OpenCode Go, `"type":"provider.quota","message":"Go usage limit exceeded","status":429`, limitName
# "5 hour" in the morning and "weekly" by 10:55. 10-24: Devin's "Your weekly usage quota has been exhausted"
# (resource_exhausted) and Codex's "You’ve hit your usage limit" (a curly apostrophe), both read as ordinary
# failures. 10-29: run-worker.sh's own line when /usage shows a failed Antigravity run's model group spent on
# every signed-in account; Antigravity meters each model group apart, so it bars the launcher, not the account.
# Checked first, and only on ERROR_RECORD_RE's lines: a quota refusal can also be non-retryable.
RATE_LIMIT_RE = re.compile(r'"type"\s*:\s*"provider\.quota"|"status(?:Code)?"\s*:\s*429\b|\bHTTP[/\d.]* 429\b'
                           r"|\b429 Too Many Requests|usage limit exceeded|rate.?limit(?:ed| exceeded| reached)"
                           r"|usage quota has been exhausted|You.ve hit your usage limit"
                           r"|^delegate worker: Antigravity quota exhausted on every signed-in account",
                           re.IGNORECASE | re.MULTILINE)
LIMIT_NAME_RE = re.compile(r'limitName\\*"\s*:\s*\\*"([^"\\]+)')
FINAL_TEXT_RE = re.compile(r'("finalText"\s*:\s*)"(?:[^"\\]|\\.)*"')
# The lines a CLI writes as its own error record: plain-text errors (Codex, Devin), JSON error objects (OpenCode,
# providers), Command Code's run_error event and error result, Claude's error result, an HTTP status line, and
# run-worker.sh's own lines.
# 10-31: two empty ocargh answers read "rate-limited" because a tool result inside their JSON event stream quoted
# the quota messages above; the CLI itself reported no error.
ERROR_RECORD_RE = re.compile(r'^(?:(?:ERROR|Error|error)\b|\{"error"|\{"type":"error"'
                             r'|\{"type":"event","event":\{"type":"run_error"|\{"type":"result","subtype":"error|\{"type":"result"[^\n]*"is_error":true'
                             r'|HTTP/[\d.]+ 429\b|429 Too Many Requests|delegate worker: )')
# Exhaustion of a plan's whole allowance, by the harness whose plan it is: only the three recorded messages
# above, in their plan-wide form (Codex's ends "usage limit." where a one-model limit would go on), so a bare
# 429 or one model's limit still bars only its launcher. Each must open a line as the CLI's own error record
# does; a worker's transcript quoting one is no refusal at all, since RATE_LIMIT_RE reads only error records.
ACCOUNT_QUOTAS = (
    (re.compile(r"^ERROR: You.ve hit your usage limit\.", re.MULTILINE), "codex"),
    (re.compile(r"^Error: Agent error: Your weekly usage quota has been exhausted", re.MULTILINE), "devin"),
    # 10-31: OpenCode's records now carry a timestamp and session ID before the error object.
    (re.compile(r'^\{"type":"error"[^\n]*"error":\{"type":"provider\.quota","message":"Go usage limit exceeded"',
                re.MULTILINE), "opencode"),
)
# (pattern, reason, harness): None for a record any harness, or run-worker.sh, may write.
QUARANTINES = (
    # 10-18: `"type":"provider.auth"`, 401, "This API key has expired"; signing in again does not renew it.
    (re.compile(r'"type"\s*:\s*"provider\.auth"|API key has expired|api_key_expired'),
     "expired or rejected API key (a user action; not repaired here)", None),
    # 09-30, 10-01: mmp's membership 403.
    (re.compile(r'"isRetryable"\s*:\s*false|membership_required'), "non-retryable provider error", None),
    # 10-06: kimbs exited 1 within a second and was found 15 minutes later.
    (re.compile(r"no credential configured"), "no credential configured (a user action; not repaired here)", None),
    # 10-22: cmm31, "403 The free MiniMax M3.1 Flash window has ended", read as an ordinary failure.
    (re.compile(r"\b403\b[^\n]*\b(?:free|plan)\b[^\n]*\bended\b", re.IGNORECASE),
     "free window or plan ended (a provider change; not repaired here)", None),
    # 10-28: cmds, signed out, failed two challenge backups in 4 and 6 s and read as unclassified, so it stayed
    # eligible. Its own error records open a line, as text and as the final JSON result; a transcript quoting one
    # does not bar the launcher.
    (re.compile(r'^Error: Authentication failed\. Please run "[^"\n]+ login" first'
                r'|^\{"type":"result","subtype":"error"[^\n]*"error":"Error: Authentication failed\. Please run \\"',
                re.MULTILINE),
     "signed out: authentication failed (a user action; not repaired here)", "cmd"),
    # 10-31: ocargh named a model OpenCode Go had retired: `"type":"provider.no-route"`, "Model unavailable". Every later
    # task on the launcher fails the same way until its definition changes. The record ends the run, so it must be
    # the last line: one a transcript printed mid-run (a worker reading a failed seat's stderr) does not count.
    (re.compile(r'^\{"type":"error"[^\n]*"error":\{"type":"provider\.no-route"[^\n]*\s*\Z', re.MULTILINE),
     "no route to the launcher's model (a launcher definition to update; not repaired here)", "opencode"),
    # ~/.bash_agents refuses a headless run on a signed-out second account rather than open a browser login.
    (re.compile(r"^Antigravity account 2 is not signed in", re.MULTILINE),
     "signed out: Antigravity account 2 (a user action; not repaired here)", "antigravity"),
)


def harness(launcher: str) -> str | None:
    """The launcher's harness in launcher-routes.tsv, or None for a launcher it does not list."""
    if launcher.startswith("cmd:"):
        return "cmd"
    # Read here, not at import: the market pool runs this file's source without a __file__.
    routes = Path(__file__).resolve().parent / "launcher-routes.tsv"
    for line in routes.read_text().splitlines()[1:]:
        name, _, launchers = line.split("\t")
        if launcher in launchers.split():
            return name
    return None


def _records(text: str) -> str:
    """The text as the ^ anchors should see it: one record per line, the model's own words blanked.

    Lines are split on "\n" alone: str.splitlines also breaks on U+2028 and others, which JSON strings may hold.
    Claude's JSON output is one event array on one line, its result the last element: that element becomes a
    line of its own. Command Code's result carries the model's final text, which may quote any message here.
    """
    lines = []
    for line in text.split("\n"):
        head, mark, last = line.rpartition('{"type":"result"')
        if mark and line.endswith("}]"):
            lines += [head, mark + last]
        else:
            lines.append(line)
    return "\n".join(FINAL_TEXT_RE.sub(r'\1""', line) if line.startswith('{"type":"result"') else line
                     for line in lines)


def classify(text: str, harness: str | None = None) -> tuple[str, str] | None:
    """(kind, reason) for a launcher-side refusal, or None for a failure the task may have caused.

    HARNESS, when known, is the failed launcher's: a record another harness writes then does not count.
    """
    text = _records(text)
    limit = LIMIT_NAME_RE.search(text)
    suffix = f' (limit "{limit.group(1)}")' if limit else ""
    for pattern, owner in ACCOUNT_QUOTAS:
        if harness in (None, owner) and pattern.search(text):
            return "rate-limited", f"account quota exhausted on {owner}{suffix}"
    if RATE_LIMIT_RE.search("\n".join(line for line in text.split("\n") if ERROR_RECORD_RE.match(line))):
        return "rate-limited", "rate limit or quota" + suffix
    for pattern, reason, owner in QUARANTINES:
        if (owner is None or harness in (None, owner)) and pattern.search(text):
            return "quarantined", reason
    return None


def _tail(path: Path) -> str:
    with path.open("rb") as handle:
        start = max(0, handle.seek(0, 2) - TAIL_BYTES)
        handle.seek(max(0, start - 1))
        tail = handle.read()
    # A tail that starts inside a line would put that line's middle, perhaps quoted text, at a line start: mark
    # it unless the byte before it ends a line. It stays readable for a record that ends it (Claude's result).
    if start:
        before, tail = tail[:1], tail[1:]
        if before != b"\n":
            tail = CUT.encode() + tail
    return tail.decode(errors="replace")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--launcher", help="the launcher that failed, as run-worker.sh names it")
    parser.add_argument("files", nargs="+", type=Path)
    arguments = parser.parse_args()
    found = classify("\n".join(_tail(path) for path in arguments.files),
                     harness(arguments.launcher) if arguments.launcher else None)
    print(f"{found[0]}: {found[1]}" if found else "unclassified")
