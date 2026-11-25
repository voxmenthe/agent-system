#!/usr/bin/env python3
"""
chatgpt_chat: Interactive human-friendly CLI for ChatGPT Pro automation.

Run with no args for an interactive prompt; or pass a question as the first
positional arg for one-shot use. Files can be added via --files.

Examples:
  chatgpt_chat.py                           # interactive
  chatgpt_chat.py "Summarize this:" -f notes.md
  chatgpt_chat.py --files report.pdf data.csv  # interactive but pre-filled
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Projected skills are hash-tracked: no bytecode beside the library.
sys.dont_write_bytecode = True
import chatgpt_lib as cgpt  # noqa: E402

USE_COLOR = sys.stderr.isatty() and os.environ.get("NO_COLOR") is None


def c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


BOLD = lambda s: c("1", s)  # noqa: E731
DIM = lambda s: c("2", s)  # noqa: E731
GREEN = lambda s: c("32", s)  # noqa: E731
YELLOW = lambda s: c("33", s)  # noqa: E731
RED = lambda s: c("31", s)  # noqa: E731
BLUE = lambda s: c("34", s)  # noqa: E731


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="chatgpt_chat.py",
        description="Ask ChatGPT Pro a question with optional file attachments.",
    )
    p.add_argument(
        "prompt",
        nargs="?",
        help="Optional inline prompt. If omitted, you'll be prompted interactively.",
    )
    p.add_argument(
        "--files",
        "-f",
        nargs="*",
        type=Path,
        default=[],
        help="Files to attach (up to 10).",
    )
    p.add_argument(
        "--continue",
        dest="continue_chat",
        action="store_true",
        help="Continue a previous conversation instead of starting fresh: the last "
        "one this tool created, or — if none — the conversation open in Chrome's "
        "front tab.",
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional file to save the response. By default it's printed to stdout.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Max seconds to wait for response (default: 600).",
    )
    return p.parse_args()


def banner() -> None:
    print(BOLD(BLUE("chatgpt_chat")) + DIM(" — drive ChatGPT Pro from your Chrome"))
    print(
        DIM(
            "  Tip: it brings the right tab forward to send, then reads the "
            "answer in the background."
        )
    )
    print()


def gather_prompt_interactive(initial: str | None) -> str:
    if initial:
        return initial
    print(BOLD("Your prompt") + DIM(" (end with Ctrl-D on its own line):"))
    try:
        lines: list[str] = []
        while True:
            line = input(DIM("> "))
            lines.append(line)
    except EOFError:
        text = "\n".join(lines).strip()
        print()
        return text


def gather_files_interactive(initial: list[Path]) -> list[Path]:
    if initial:
        return initial
    print(BOLD("Files to attach") + DIM(" (paths separated by spaces; blank for none):"))
    raw = input(DIM("> ")).strip()
    if not raw:
        return []
    paths = [Path(p).expanduser() for p in raw.split()]
    bad = [p for p in paths if not p.is_file()]
    if bad:
        print(RED(f"Not a file: {', '.join(str(b) for b in bad)}"))
        return gather_files_interactive([])
    return paths


def progress_logger():
    last_state = [""]
    start = [time.monotonic()]

    def log(state: str) -> None:
        if state == last_state[0]:
            return
        elapsed = time.monotonic() - start[0]
        print(DIM(f"  [{elapsed:5.1f}s] ") + state, file=sys.stderr, flush=True)
        last_state[0] = state

    return log


def main() -> int:
    args = parse_args()
    banner()

    is_interactive = sys.stdin.isatty() and not args.prompt
    try:
        if is_interactive:
            files = gather_files_interactive(args.files or [])
            prompt = gather_prompt_interactive(args.prompt)
        else:
            files = args.files or []
            prompt = args.prompt or sys.stdin.read()

        prompt = prompt.strip()
        if not prompt:
            print(RED("No prompt provided."), file=sys.stderr)
            return 64

        if len(files) > 10:
            print(RED(f"Max 10 files (got {len(files)})."), file=sys.stderr)
            return 64
        for fp in files:
            if not fp.is_file():
                print(RED(f"Not a file: {fp}"), file=sys.stderr)
                return 64

        # Summary before running
        print(DIM("─" * min(60, shutil.get_terminal_size().columns)))
        print(BOLD("Asking ChatGPT Pro…"))
        if files:
            print(DIM(f"  files: {', '.join(f.name for f in files)}"))
        if args.continue_chat:
            print(DIM("  mode: continuing previous conversation (last created, else front tab)"))
        else:
            print(DIM("  mode: new conversation"))
        preview = textwrap.shorten(prompt.replace("\n", " "), width=72, placeholder="…")
        print(DIM(f"  prompt: {preview}"))
        print(DIM("─" * min(60, shutil.get_terminal_size().columns)))

        log = progress_logger()
        try:
            response = cgpt.ask(
                prompt=prompt,
                files=files,
                new_chat=not args.continue_chat,
                timeout=args.timeout,
                on_progress=log,
            )
        except cgpt.NotLoggedInError as e:
            print(RED(str(e)), file=sys.stderr)
            return 10
        except cgpt.JSExecBlockedError as e:
            print(RED(str(e)), file=sys.stderr)
            return 11
        except cgpt.ChatGPTTimeoutError as e:
            print(RED(f"Timed out: {e}"), file=sys.stderr)
            return 12
        except cgpt.ChatGPTError as e:
            print(RED(f"Error: {e}"), file=sys.stderr)
            return 1

        # Result
        print(DIM("─" * min(60, shutil.get_terminal_size().columns)), file=sys.stderr)
        print(GREEN(f"✓ Response in {response.duration_seconds:5.1f}s"), file=sys.stderr)
        print(
            DIM(
                f"  conversation: https://chatgpt.com/c/{response.conversation_id}\n"
                f"  model: {response.model_slug}\n"
                f"  length: {len(response.text)} chars"
            ),
            file=sys.stderr,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(response.text)
            print(GREEN(f"  saved → {args.output}"), file=sys.stderr)
        else:
            print(file=sys.stderr)
            print(response.text)
        return 0
    except KeyboardInterrupt:
        print(RED("\nInterrupted."), file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
