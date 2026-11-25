#!/usr/bin/env python3
"""List recent or date-bounded ChatGPT conversations through logged-in Chrome."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from types import ModuleType

# Projected skills are hash-tracked. Avoid creating bytecode beside the local
# modules while importing them, then restore the embedding process's setting.
_previous_dont_write_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    from chatgpt_conversation_index import (
        ConversationIndexError,
        ConversationIndexResult,
        calendar_date_bounds,
        format_utc,
        list_date_range,
        list_recent,
    )
    from download_chatgpt_conversation import (
        EXIT_ERROR,
        EXIT_JS_BLOCKED,
        EXIT_NOT_LOGGED_IN,
        EXIT_OK,
        EXIT_TEMPORARY_READ_FAILURE,
        EXIT_USAGE,
        DependencyError,
        _bridge_error_types,
        load_gpt_bridge,
    )
finally:
    sys.dont_write_bytecode = _previous_dont_write_bytecode


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="list_chatgpt_conversations.py",
        description=(
            "List private ChatGPT conversations through the logged-in Chrome profile "
            "managed by the sibling gpt skill. Output is versioned JSON on stdout."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    recent = commands.add_parser(
        "recent",
        help="List the N most recently updated conversations.",
    )
    recent.add_argument("--limit", required=True, type=_positive_int)
    recent.add_argument(
        "--archive-scope",
        choices=("active", "archived", "all"),
        default="active",
        help="Which archive partition to search (default: active).",
    )

    date_range = commands.add_parser(
        "range",
        help=(
            "List conversations created or updated in an inclusive "
            "calendar-date range."
        ),
    )
    date_range.add_argument("--from-date", required=True, metavar="YYYY-MM-DD")
    date_range.add_argument("--to-date", required=True, metavar="YYYY-MM-DD")
    date_range.add_argument(
        "--timezone",
        default="UTC",
        help="IANA timezone for both calendar dates (default: UTC).",
    )
    date_range.add_argument(
        "--date-field",
        choices=("created", "updated"),
        default="created",
        help="Timestamp to filter on (default: created).",
    )
    date_range.add_argument(
        "--archive-scope",
        choices=("active", "archived", "all"),
        default="all",
        help="Which archive partition to search (default: all).",
    )
    return parser.parse_args(argv)


def _query(
    args: argparse.Namespace,
    bridge: ModuleType,
) -> dict[str, object]:
    bounds = None
    if args.command == "range":
        # Validate all local inputs before opening or reading Chrome.
        bounds = calendar_date_bounds(args.from_date, args.to_date, args.timezone)

    target = bridge.ensure_chatgpt_available()
    bridge.get_session(target=target)

    def fetch_page(
        offset: int,
        limit: int,
        *,
        archived: bool,
    ) -> dict[str, object]:
        return bridge.fetch_conversations_page(
            offset,
            limit,
            archived=archived,
            target=target,
        )

    if args.command == "recent":
        result = list_recent(
            fetch_page,
            limit=args.limit,
            archive_scope=args.archive_scope,
        )
        query: dict[str, object] = {
            "mode": "recent",
            "limit": args.limit,
            "archive_scope": args.archive_scope,
            "sort": "updated_desc",
        }
    else:
        assert bounds is not None
        start, end = bounds
        result = list_date_range(
            fetch_page,
            start=start,
            end=end,
            date_field=args.date_field,
            archive_scope=args.archive_scope,
        )
        query = {
            "mode": "range",
            "from_date": args.from_date,
            "to_date": args.to_date,
            "timezone": args.timezone,
            "date_field": args.date_field,
            "archive_scope": args.archive_scope,
            "start_inclusive": format_utc(start),
            "end_exclusive": format_utc(end),
            "sort": f"{args.date_field}_desc",
        }
    return _result_payload(result, query)


def _result_payload(
    result: ConversationIndexResult,
    query: dict[str, object],
) -> dict[str, object]:
    conversations = [item.as_dict() for item in result.conversations]
    return {
        "schema_version": 1,
        "status": "ok",
        "snapshot_consistency": "best_effort",
        "query": query,
        "count": len(conversations),
        "pages_fetched": result.pages_fetched,
        "conversations": conversations,
    }


def main(argv: Sequence[str] | None = None, *, bridge: ModuleType | None = None) -> int:
    args = parse_args(argv)
    try:
        active_bridge = bridge if bridge is not None else load_gpt_bridge()
    except DependencyError as error:
        print(str(error), file=sys.stderr)
        return EXIT_ERROR

    try:
        result = _query(args, active_bridge)
    except ConversationIndexError as error:
        print(str(error), file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except _bridge_error_types(active_bridge, "NotLoggedInError") as error:
        print(str(error), file=sys.stderr)
        return EXIT_NOT_LOGGED_IN
    except _bridge_error_types(active_bridge, "JSExecBlockedError") as error:
        print(str(error), file=sys.stderr)
        return EXIT_JS_BLOCKED
    except _bridge_error_types(
        active_bridge,
        "ChatGPTReadThrottledError",
        "ChatGPTTimeoutError",
    ) as error:
        print(str(error), file=sys.stderr)
        return EXIT_TEMPORARY_READ_FAILURE
    except _bridge_error_types(active_bridge, "ChatGPTError") as error:
        print(str(error), file=sys.stderr)
        return EXIT_ERROR

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
