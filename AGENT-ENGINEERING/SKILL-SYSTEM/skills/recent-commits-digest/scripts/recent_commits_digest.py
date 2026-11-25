#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fast-forward pull the current branch and print recent one-line commits."
    )
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of commits to print.")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Optional file or directory path filter. May be repeated.",
    )
    parser.add_argument(
        "--no-pull",
        action="store_true",
        help="Skip git pull; useful after a pull was already run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count < 1:
        print("--count must be >= 1", file=sys.stderr)
        return 2

    before = run_git(["rev-parse", "HEAD"]).stdout.strip()
    pulled = "Skipped pull."
    new_commit_count: int | None = None

    if not args.no_pull:
        pull = run_git(["pull", "--ff-only"], check=False)
        if pull.returncode != 0:
            sys.stderr.write(pull.stdout)
            sys.stderr.write(pull.stderr)
            print("git pull --ff-only failed; no merge or rebase was attempted.", file=sys.stderr)
            return pull.returncode

        after = run_git(["rev-parse", "HEAD"]).stdout.strip()
        if before == after:
            pulled = "Already up to date."
            new_commit_count = 0
        else:
            count_proc = run_git(["rev-list", "--count", f"{before}..{after}"], check=False)
            if count_proc.returncode == 0:
                new_commit_count = int(count_proc.stdout.strip() or "0")
                pulled = f"Pulled: {new_commit_count} new commit{'s' if new_commit_count != 1 else ''}."
            else:
                pulled = "Pulled; could not count new commits."

    log_args = ["log", "--oneline", "-n", str(args.count)]
    if args.path:
        log_args.extend(["--", *args.path])
    log = run_git(log_args, check=False)
    if log.returncode != 0:
        sys.stderr.write(log.stderr)
        return log.returncode

    print(pulled)
    for line in log.stdout.splitlines():
        print(f"- {line}")

    if not log.stdout.strip():
        path_note = " for the requested path" if args.path else ""
        print(f"No commits found{path_note}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
