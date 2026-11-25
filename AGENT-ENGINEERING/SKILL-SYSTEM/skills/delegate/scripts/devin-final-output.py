#!/usr/bin/env python3
"""Extract a successful local Devin print run's committed terminal message, never its progress text."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys


def final_response(database: Path, stdout: str, prompt: str, cwd: str, started: int) -> str:
    """Read the actual main-chain head of this task's new local session; refuse ambiguity or schema drift."""
    if not database.is_file():
        raise ValueError("Devin session database unavailable; cannot isolate a final response")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        rows = connection.execute('''SELECT DISTINCT s.id, n.chat_message
            FROM sessions s JOIN prompt_history p ON p.session_id=s.id
            JOIN message_nodes n ON n.session_id=s.id AND n.node_id=s.main_chain_id
            WHERE s.created_at >= ? AND s.working_directory = ? AND p.content = ?''',
                                  (started, cwd, prompt)).fetchall()
    if len(rows) != 1:
        raise ValueError(f"expected one new Devin session for this task, found {len(rows)}; no raw-output fallback")
    message = json.loads(rows[0][1])
    if not isinstance(message, dict) or message.get("role") != "assistant" or message.get("tool_calls"):
        raise ValueError("Devin main-chain head is not a terminal assistant message")
    final = message.get("content")
    if not isinstance(final, str) or not final.strip():
        raise ValueError("Devin returned no nonempty final assistant text")
    final = final.rstrip()
    if not stdout.rstrip().endswith(final):
        raise ValueError("Devin stdout does not end with its committed terminal message")
    progress = stdout.rstrip()[:-len(final)]
    if progress.strip():
        print(progress, file=sys.stderr)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("stdout", type=Path)
    parser.add_argument("prompt", type=Path)
    parser.add_argument("cwd")
    parser.add_argument("started", type=int)
    args = parser.parse_args()
    try:
        final = final_response(args.database, args.stdout.read_text(), args.prompt.read_text(), args.cwd, args.started)
    except (OSError, ValueError, sqlite3.DatabaseError) as error:
        print(f"delegate worker: Devin final-response extraction failed: {error}", file=sys.stderr)
        return 1
    print(final)
    return 0


if __name__ == "__main__":
    sys.exit(main())
