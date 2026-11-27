#!/usr/bin/env python3
"""Whether a failed launch was refused by the launcher, so later tasks on it would fail the same way.

    refusals.py [--launcher NAME] FILE...

prints "rate-limited: REASON" (a rate limit or quota), "quarantined: REASON" (an expired key, a missing
credential, a signed-out CLI, a free window or plan that ended, a model the provider no longer routes, or another
non-retryable refusal), "content-filtered: task text; bars no launcher", or "unclassified", from the last 8 KiB of
each FILE, where a CLI's final error lands. Command Code's native terminal error can recover its reset event
from immediately before a large run_end record. A rate
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
import json
import re
import sys
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import BinaryIO

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
RESET_AT_RE = re.compile(r'\bresets at (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d))', re.I)
RETRY_AFTER_RE = re.compile(r'(?:"retryAfterMs"\s*:\s*|\bretryAfterMs:\s*)(\d{1,12})(?!\d)')
FINAL_TEXT_RE = re.compile(r'("finalText"\s*:\s*)"(?:[^"\\]|\\.)*"')
# The lines a CLI writes as its own error record: plain-text errors (Codex, Devin), JSON error objects (OpenCode,
# providers), Command Code's run_error event and error result, Claude's error result, an HTTP status line, and
# run-worker.sh's own lines.
# 10-31: two empty ocargh answers read "rate-limited" because a tool result inside their JSON event stream quoted
# the quota messages above; the CLI itself reported no error.
ERROR_RECORD_RE = re.compile(r'^(?:(?:ERROR|Error|error)\b|\{"error"|\{"type":"error"'
                             r'|\{"type":"event","event":\{"type":"run_error"|\{"type":"result","subtype":"error|\{"type":"result"[^\n]*"is_error":true'
                             r'|HTTP/[\d.]+ 429\b|429 Too Many Requests|delegate worker: )')
# Exhaustion of a plan's whole allowance, by the harness whose plan it is, so a bare
# 429 or one model's limit still bars only its launcher. Each must open a line as the CLI's own error record
# does; a worker's transcript quoting one is no refusal at all, since RATE_LIMIT_RE reads only error records.
OPENCODE_ERROR = r'^\{"type":"error"[^\n]*"error":\{"type":'
OPENCODE_QUOTA = re.compile(OPENCODE_ERROR + r'"provider\.(?:quota","message":"Go usage limit exceeded|go-limit")')
CONTENT_FILTER = re.compile(OPENCODE_ERROR + r'"provider\.(?:content-filter"|[^"\n]+","message":"[^"\n]*\[DataInspectionFailed\])')
CMD_RUN_ERROR = (r'^\{"type":"event","event":\{"type":"run_error","error":\{"name":"TransportError",'
                 r'"message":"POST /alpha/generate .+ 429 error: You.ve reached your weekly usage limit for your plan\.')
CMD_RUN_END = b'{"type":"event","event":{"type":"run_end"'
CMD_RESULT_QUOTA = (r'^\{"type":"result","subtype":"error"[^\n]*,"error":"Error: '
                    r"You.ve reached your weekly usage limit\. Resets in ")
ACCOUNT_QUOTAS = (
    (re.compile(r"^ERROR: You.ve hit your usage limit\."), "codex", None),
    (re.compile(r"^Error: Agent error: Your weekly usage quota has been exhausted"), "devin", None),
    (OPENCODE_QUOTA, "opencode", "go"),
    (re.compile(CMD_RUN_ERROR + r"|^Error: You.ve reached your weekly usage limit\. Resets in |" + CMD_RESULT_QUOTA),
     "cmd", None),
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
    # 11-14: cdm (stance-tagger.err): stale codex binary rejected ~/.codex/config.toml before any model call.
    # Anchored to column zero so a worker transcript quoting the message does not bar the launcher.
    (re.compile(r"^Error loading config\.toml\b", re.MULTILINE),
     "startup configuration load failed (a local CLI/config error; not repaired here)", "codex"),
)


@cache
def launcher_routes() -> dict[str, tuple[str, str]]:
    """Launcher -> (harness, account), one allowance per row of the sibling table."""
    routes = Path(__file__).resolve().parent / "launcher-routes.tsv"
    header, *rows = routes.read_text().splitlines()
    if header != "harness\taccount\tlaunchers":
        raise ValueError(f"{routes} lacks its header")
    by_name = {}
    for line in rows:
        name, account, launchers = line.split("\t")
        for launcher in launchers.split():
            if launcher in by_name:
                raise ValueError(f"{routes} lists {launcher} twice")
            by_name[launcher] = (name, account)
    return by_name


def launcher_route(launcher: str) -> tuple[str, str] | None:
    if launcher.startswith("cmd:"):
        return "cmd", "-"
    return launcher_routes().get(launcher)


def reset_clock(record: str) -> datetime | int | None:
    """Provider reset as an absolute timestamp or a millisecond delay, including the persisted reason form."""
    if match := RESET_AT_RE.search(record):
        try:
            return datetime.fromisoformat(match[1])
        except ValueError:
            pass
    if match := RETRY_AFTER_RE.search(record):
        return int(match[1])
    return None


def _quota_suffix(record: str) -> str:
    suffix = ""
    if limit := LIMIT_NAME_RE.search(record):
        suffix = f' (limit "{limit[1]}")'
    reset = reset_clock(record)
    if isinstance(reset, datetime):
        suffix += f" (resets at {RESET_AT_RE.search(record)[1]})"
    elif reset is not None:
        suffix += f" (retryAfterMs: {reset})"
    return suffix


def terminal_error(text: str) -> str | None:
    """Latest native error record, not the adapter's own teardown or classification footer."""
    for line in reversed(_records(text).split("\n")):
        if ERROR_RECORD_RE.match(line) and not line.startswith("delegate worker: "):
            if line.startswith("{"):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return line.strip()
                event = record.get("event")
                error = (event if isinstance(event, dict) else record).get("error")
                if isinstance(error, str):
                    return error.split("\n", 1)[0]
                if isinstance(error, dict) and isinstance(error.get("message"), str):
                    label = error.get("type") or error.get("name")
                    return (f"{label}: " if label else "") + error["message"].split("\n", 1)[0]
            return line.strip()
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


def classify(text: str, route: tuple[str, str] | None = None) -> tuple[str, str] | None:
    """(kind, reason) for a recognized refusal, including a task-local content filter.

    ROUTE, when known, is the failed launcher's (harness, account). Another harness's plan record is not a refusal.
    """
    text = _records(text)
    records = [line for line in reversed(text.split("\n")) if ERROR_RECORD_RE.match(line)]
    for pattern, harness, account in ACCOUNT_QUOTAS:
        if route is not None and (route[0] != harness or account not in (None, route[1])):
            continue
        matching = [line for line in records if pattern.match(line)]
        if matching:
            record = next((line for line in matching if reset_clock(line) is not None), matching[0])
            return "rate-limited", f"account quota exhausted on {harness}{_quota_suffix(record)}"
    if any(CONTENT_FILTER.match(line) for line in records) and (route is None or route[0] == "opencode"):
        return "content-filtered", "task text; bars no launcher"
    for line in records:
        if RATE_LIMIT_RE.search(line) and not any(pattern.match(line) for pattern, _, _ in ACCOUNT_QUOTAS):
            return "rate-limited", "rate limit or quota" + _quota_suffix(line)
    for pattern, reason, owner in QUARANTINES:
        if (owner is None or route is None or route[0] == owner) and pattern.search(text):
            return "quarantined", reason
    return None


def _command_reset_before_tail(handle: BinaryIO, offset: int, start: int, tail: bytes) -> str:
    """Recover the native run_error immediately before run_end if a weekly quota result survived the cut."""
    result_re = re.compile(CMD_RESULT_QUOTA.encode())
    result = next((line for line in reversed(tail.split(b"\n")[1:]) if result_re.match(line)), None)
    if result is None:
        return ""
    result_start = start + tail.rfind(result)
    handle.seek(offset)
    previous, penultimate = b"", b""
    while handle.tell() < result_start:
        penultimate, previous = previous, handle.readline()[:TAIL_BYTES]
        if not previous:
            return ""
    if handle.tell() == result_start and previous.startswith(CMD_RUN_END) and re.match(CMD_RUN_ERROR.encode(), penultimate):
        return penultimate.decode(errors="replace").rstrip("\r\n") + "\n"
    return ""


def failure_tail(path: Path, offset: int = 0) -> str:
    recovered = ""
    with path.open("rb") as handle:
        start = max(offset, handle.seek(0, 2) - TAIL_BYTES)
        handle.seek(max(offset, start - 1))
        tail = handle.read()
        # A cut inside a line would make quoted text appear at column zero. The sentinel prevents this while
        # preserving Claude's result array suffix. A recognized Command Code result can recover its adjacent clock.
        if start > offset:
            before, tail = tail[:1], tail[1:]
            if before != b"\n":
                recovered = _command_reset_before_tail(handle, offset, start, tail)
                tail = CUT.encode() + tail
    return recovered + tail.decode(errors="replace")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--launcher", help="the launcher that failed, as run-worker.sh names it")
    parser.add_argument("files", nargs="+", type=Path)
    arguments = parser.parse_args()
    found = classify("\n".join(failure_tail(path) for path in arguments.files),
                     launcher_route(arguments.launcher) if arguments.launcher else None)
    print(f"{found[0]}: {found[1]}" if found else "unclassified")
