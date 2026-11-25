"""How colab_job.py shows a job's log in a terminal or an agent transcript.

Progress bars (carriage-return frames) collapse to their last frame, ANSI codes
are removed, and a character budget caps a long log while the last lines, where
errors appear, are always shown.
"""
from __future__ import annotations

import re
import sys
from collections import deque

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SHOW_CHARS = 12000


def clean_line(line: str) -> str:
    frames = [frame for frame in line.split("\r") if frame]
    return ANSI.sub("", frames[-1] if frames else "")


class LogPrinter:
    """Prints a job's log: progress bars collapse to their last frame; a budget caps
    the text, but the last lines are always shown so a final error is never hidden."""

    def __init__(self, budget: int = SHOW_CHARS, keep: int = 40) -> None:
        self.partial = ""
        self.budget = budget
        self.held: deque[str] = deque(maxlen=keep)
        self.held_count = 0

    def feed(self, text: str, keep_last: int | None = None, drop_first: bool = False) -> None:
        lines = (self.partial + text).split("\n")
        self.partial = clean_line(lines.pop())
        if drop_first:
            lines = lines[1:]
        if keep_last is not None:
            lines = lines[-keep_last:]
        for line in lines:
            self._show(clean_line(line))

    def _show(self, line: str) -> None:
        if len(line) < self.budget and not self.held_count:
            print(line, flush=True)
            self.budget -= len(line) + 1
        else:
            self.held.append(line)
            self.held_count += 1

    def close(self) -> None:
        if self.partial:
            self._show(self.partial)
            self.partial = ""
        if self.held_count > len(self.held):
            print("[colab-jobs] ... %d log lines not shown here (use logs) ..." % (self.held_count - len(self.held)))
        for line in self.held:
            print(line)
        self.held.clear()
        self.held_count = 0
        sys.stdout.flush()
