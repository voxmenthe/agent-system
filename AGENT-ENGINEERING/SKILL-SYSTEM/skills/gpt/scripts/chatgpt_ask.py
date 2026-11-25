#!/usr/bin/env python3
"""
chatgpt_ask: Agent-friendly CLI to query ChatGPT Pro with optional file
attachments, by driving the user's logged-in Chrome session.

Behavior is non-interactive and machine-parseable. Progress lines go to
stderr; the response markdown goes to --output (or stdout). Use --json to
get structured metadata on stdout instead of plain text. Use --send-only to
return after the prompt submission is verified, without reading the response.

Examples:
  chatgpt_ask.py --prompt "What is 2+2?" --output answer.md
  chatgpt_ask.py --prompt-file question.txt --files data.csv notes.md \\
                  --output report.md
  chatgpt_ask.py --prompt "Explain this article." --files article.md --send-only
  chatgpt_ask.py --prompt "follow up question" --continue  # current chat
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import re
import sys
import time
from pathlib import Path

# Make the sibling library importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Projected skills are hash-tracked: no bytecode beside the library.
sys.dont_write_bytecode = True
import chatgpt_lib as cgpt  # noqa: E402

EXIT_OK = 0
EXIT_NOT_LOGGED_IN = 10
EXIT_JS_BLOCKED = 11
EXIT_TIMEOUT = 12
EXIT_RATE_LIMITED = 13
EXIT_USAGE = 64
EXIT_ERROR = 1

# Every prompt send appends a timestamped line here (--fetch reads do not).
# This home-level log coordinates every GPT Pro send on the machine. Sends must
# satisfy both limits below, counting the send about to be made; over-limit sends
# exit EXIT_RATE_LIMITED untouched.
# The log is truncated to the newest CALL_LOG_MAX_ENTRIES on every write.
CALL_LOG = Path.home() / ".chatgpt_pro_requests.log"
CALL_LOG_LOCK = Path.home() / ".chatgpt_pro_requests.lock"
CALL_LOG_MAX_ENTRIES = 20
RATE_MAX_SENDS = 2
RATE_WINDOW_SECONDS = 1080.0
RATE_MIN_GAP_SECONDS = 420.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="chatgpt_ask.py",
        description="Query ChatGPT Pro via your logged-in Chrome (macOS).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", "-p", help="Prompt text (single arg).")
    src.add_argument("--prompt-file", type=Path, help="Read prompt text from this file.")
    src.add_argument(
        "--fetch",
        nargs="?",
        const="",
        metavar="CONVERSATION_ID",
        help="Recover the latest answer of an already-running/finished "
        "conversation BY ID (drift-proof; no new prompt is sent). Omit the id "
        "to use the last conversation this tool created. Useful when a Pro run "
        "(up to ~30 min) outlived the --timeout. For a newly sent Pro prompt, "
        "wait at least 9 minutes before the first recovery fetch.",
    )

    p.add_argument(
        "--files",
        "-f",
        nargs="*",
        type=Path,
        default=[],
        help="Up to 10 files to attach to the message.",
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write response markdown here. If omitted, writes to stdout.",
    )
    p.add_argument(
        "--send-only",
        action="store_true",
        help="Return after the prompt and attachments are submitted and the "
        "conversation is verified; do not wait for or read the response.",
    )
    p.add_argument(
        "--continue",
        dest="continue_chat",
        action="store_true",
        help="Continue the LAST conversation this tool created (uses the saved "
        "session id). For reliable threading across many open chatgpt tabs, prefer "
        "--conversation-id with the id from a prior --json run.",
    )
    p.add_argument(
        "--conversation-id",
        dest="conversation_id",
        default=None,
        metavar="ID",
        help="Continue an EXPLICIT conversation by id (from a prior --json "
        "'conversation_id'). Implies --continue and is the robust way to thread "
        "follow-ups: the send is bound to this exact conversation, not 'whatever "
        "Chrome tab is in front'. Still requires --prompt/--prompt-file (use "
        "--fetch to only read an answer).",
    )
    p.add_argument(
        "--conversation-url",
        dest="conversation_url",
        default=None,
        metavar="URL",
        help="Like --conversation-id but accepts a full https://chatgpt.com/c/<id> URL.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=1200.0,
        help="Max seconds to wait for the response (default: 1200; Pro + tool-use "
        "runs routinely take 5-15 min).",
    )
    p.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Print JSON metadata to stdout (response text still goes to --output).",
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress lines on stderr.",
    )
    args = p.parse_args()
    if args.send_only and args.fetch is not None:
        p.error("--send-only cannot be used with --fetch")
    if args.send_only and args.output is not None:
        p.error("--send-only cannot be used with --output because no response is read")
    return args


def _log(quiet: bool, msg: str) -> None:
    if not quiet:
        print(f"[chatgpt_ask] {msg}", file=sys.stderr, flush=True)


def _logged_send_times() -> list[float]:
    """Epoch timestamps of prior sends from CALL_LOG, sorted ascending."""
    if not CALL_LOG.is_file():
        return []
    times = []
    for line in CALL_LOG.read_text().splitlines():
        stamp = line.split("\t", 1)[0].strip()
        try:
            times.append(datetime.datetime.fromisoformat(stamp).timestamp())
        except ValueError:
            continue
    return sorted(times)


def _seconds_until_send_allowed() -> float:
    """0.0 if sending now satisfies the rolling window and minimum gap limits."""
    now = time.time()
    logged = _logged_send_times()
    waits = []
    if logged:
        waits.append(logged[-1] + RATE_MIN_GAP_SECONDS - now)
    recent = [t for t in logged if now - t < RATE_WINDOW_SECONDS]
    if len(recent) >= RATE_MAX_SENDS:
        waits.append(recent[-RATE_MAX_SENDS] + RATE_WINDOW_SECONDS - now)
    return max([0.0, *waits])


def _record_send(prompt: str) -> None:
    """Append a timestamped entry to CALL_LOG, keeping only the newest
    CALL_LOG_MAX_ENTRIES lines. Called just BEFORE the send, so attempts that
    fail mid-send still count toward the window (conservative)."""
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    snippet = " ".join(prompt.split())[:80]
    lines = CALL_LOG.read_text().splitlines() if CALL_LOG.is_file() else []
    lines.append(f"{stamp}\t{snippet}")
    CALL_LOG.write_text("\n".join(lines[-CALL_LOG_MAX_ENTRIES:]) + "\n")


def _reserve_send_slot(prompt: str) -> float:
    """Atomically check the shared send log and record this send if allowed."""
    with CALL_LOG_LOCK.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            wait_seconds = _seconds_until_send_allowed()
            if wait_seconds <= 0:
                _record_send(prompt)
            return wait_seconds
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _extract_cid(s: str | None) -> str | None:
    """Pull a conversation id out of a /c/<id> URL, or return a bare id as-is."""
    if not s:
        return None
    s = s.strip()
    m = re.search(r"/c/([\w-]+)", s)
    return m.group(1) if m else s


def _looks_like_cid(cid: str | None) -> bool:
    """A conversation id is a single path-free token (UUID-ish). Reject leftovers
    like a /share/<slug> link or a typo'd URL that _extract_cid passed through."""
    return bool(cid) and re.fullmatch(r"[\w-]{8,}", cid) is not None


def _target_conversation_id(args) -> str | None:
    """Explicit conversation target from --conversation-url or --conversation-id."""
    return _extract_cid(
        getattr(args, "conversation_url", None) or getattr(args, "conversation_id", None)
    )


def _emit_conversation_hint(args, conversation_id: str) -> None:
    """Surface the stable URL and exact follow-up flag unless progress is quiet."""
    if not conversation_id or args.quiet:
        return
    print(
        f"[chatgpt_ask] conversation: https://chatgpt.com/c/{conversation_id}",
        file=sys.stderr,
    )
    print(
        f"[chatgpt_ask] thread a follow-up IN THIS conversation with: "
        f"--conversation-id {conversation_id}",
        file=sys.stderr,
        flush=True,
    )


def _emit(args, response, elapsed: float) -> None:
    """Write response text (to --output or stdout) and optional --json metadata."""
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(response.text)
        _log(args.quiet, f"wrote {len(response.text)} chars to {args.output}")
    elif not args.json_out:
        sys.stdout.write(response.text)
        if not response.text.endswith("\n"):
            sys.stdout.write("\n")
    if args.json_out:
        meta = {
            "status": "incomplete" if response.duration_seconds == -1.0 else "ok",
            "conversation_id": response.conversation_id,
            "conversation_url": f"https://chatgpt.com/c/{response.conversation_id}",
            "message_id": response.message_id,
            "model_slug": response.model_slug,
            "thinking_effort": response.thinking_effort,
            "duration_seconds": round(elapsed, 2),
            "response_chars": len(response.text),
            "output_path": str(args.output) if args.output else None,
            "citations": [
                {"name": c.get("name"), "id": c.get("id"), "type": c.get("type")}
                for c in (response.citations or [])
            ],
        }
        json.dump(meta, sys.stdout, indent=2)
        sys.stdout.write("\n")

    _emit_conversation_hint(args, response.conversation_id)


def _emit_submission(args, submission, elapsed: float) -> None:
    """Emit metadata for a verified send without reading an assistant response."""
    if args.json_out:
        meta = {
            "status": "submitted",
            "conversation_id": submission.conversation_id,
            "conversation_url": (f"https://chatgpt.com/c/{submission.conversation_id}"),
            "duration_seconds": round(elapsed, 2),
            "attached_files": [str(path) for path in args.files],
        }
        json.dump(meta, sys.stdout, indent=2)
        sys.stdout.write("\n")
    _emit_conversation_hint(args, submission.conversation_id)


def main() -> int:
    args = parse_args()

    # An explicit conversation target must look like an id, not a stray URL.
    explicit_cid = _target_conversation_id(args)
    if (args.conversation_id or args.conversation_url) and not _looks_like_cid(explicit_cid):
        print(
            "Could not parse a conversation id from --conversation-id/--conversation-url; "
            "expected a bare id or a https://chatgpt.com/c/<id> URL.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # Recovery mode: just read an existing conversation by id; send nothing.
    if getattr(args, "fetch", None) is not None:
        cid = args.fetch or explicit_cid or None
        try:
            response = cgpt.get_final_answer(
                cid,
                on_read_throttle=lambda wait: _log(
                    args.quiet,
                    "ChatGPT read-side throttle; backing off "
                    f"{int(wait)}s before retrying the same fetch "
                    "(no new prompt sent)",
                ),
            )
        except cgpt.NotLoggedInError as e:
            print(str(e), file=sys.stderr)
            return EXIT_NOT_LOGGED_IN
        except cgpt.JSExecBlockedError as e:
            print(str(e), file=sys.stderr)
            return EXIT_JS_BLOCKED
        except cgpt.ChatGPTReadThrottledError as e:
            print(str(e), file=sys.stderr)
            return EXIT_TIMEOUT
        except cgpt.ChatGPTError as e:
            print(f"Error: {e}", file=sys.stderr)
            return EXIT_ERROR
        if response.duration_seconds == -1.0:
            _log(
                args.quiet,
                "conversation still streaming; returning partial text (do not treat as final)",
            )
            _emit(args, response, 0.0)
            return EXIT_TIMEOUT
        _emit(args, response, 0.0)
        return EXIT_OK

    if args.prompt_file:
        if not args.prompt_file.is_file():
            print(f"prompt-file not found: {args.prompt_file}", file=sys.stderr)
            return EXIT_USAGE
        prompt = args.prompt_file.read_text()
    else:
        prompt = args.prompt or ""
    if not prompt.strip():
        print("Prompt is empty.", file=sys.stderr)
        return EXIT_USAGE

    files = list(args.files or [])
    if len(files) > 10:
        print(f"Max 10 files; got {len(files)}.", file=sys.stderr)
        return EXIT_USAGE
    for fp in files:
        if not fp.is_file():
            print(f"File not found: {fp}", file=sys.stderr)
            return EXIT_USAGE

    wait_seconds = _reserve_send_slot(prompt)
    if wait_seconds > 0:
        print(
            f"Rate limited: max {RATE_MAX_SENDS} sends per "
            f"{int(RATE_WINDOW_SECONDS)}s and at least "
            f"{int(RATE_MIN_GAP_SECONDS)}s between sends (log: {CALL_LOG}). "
            f"Retry in {int(wait_seconds) + 1}s.",
            file=sys.stderr,
        )
        return EXIT_RATE_LIMITED

    quiet = args.quiet
    started = time.monotonic()

    # An explicit conversation target implies continuing that conversation.
    target_cid = explicit_cid
    continue_chat = args.continue_chat or target_cid is not None

    try:
        if args.send_only:
            result = cgpt.submit(
                prompt=prompt,
                files=files,
                new_chat=not continue_chat,
                conversation_id=target_cid,
                on_progress=lambda s: _log(quiet, s),
            )
        else:
            result = cgpt.ask(
                prompt=prompt,
                files=files,
                new_chat=not continue_chat,
                conversation_id=target_cid,
                timeout=args.timeout,
                on_progress=lambda s: _log(quiet, s),
            )
    except cgpt.NotLoggedInError as e:
        print(str(e), file=sys.stderr)
        return EXIT_NOT_LOGGED_IN
    except cgpt.JSExecBlockedError as e:
        print(str(e), file=sys.stderr)
        return EXIT_JS_BLOCKED
    except cgpt.ChatGPTReadThrottledError as e:
        print(str(e), file=sys.stderr)
        return EXIT_TIMEOUT
    except cgpt.ChatGPTTimeoutError as e:
        print(str(e), file=sys.stderr)
        return EXIT_TIMEOUT
    except cgpt.ChatGPTError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return EXIT_ERROR

    elapsed = time.monotonic() - started
    if args.send_only:
        _emit_submission(args, result, elapsed)
    else:
        _emit(args, result, elapsed)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
