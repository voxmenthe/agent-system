#!/usr/bin/env python3
"""Download a complete user-visible ChatGPT conversation transcript."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence

# Projected skills are hash-tracked. Suppress bytecode only while loading the
# local runtime dependency, then restore the embedding process's setting.
_previous_dont_write_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    from chatgpt_transcript import (
        ExportWriteError,
        TranscriptError,
        build_export,
        parse_conversation_id,
        slugify_title,
        write_export,
    )
finally:
    sys.dont_write_bytecode = _previous_dont_write_bytecode


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_LOGGED_IN = 10
EXIT_JS_BLOCKED = 11
EXIT_TEMPORARY_READ_FAILURE = 12
EXIT_USAGE = 64


class DependencyError(RuntimeError):
    """The required sibling gpt skill is missing or cannot be loaded."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="download_chatgpt_conversation.py",
        description=(
            "Export a private ChatGPT conversation through the logged-in Chrome profile "
            "managed by the sibling gpt skill."
        ),
    )
    parser.add_argument(
        "conversation",
        help="A bare conversation id or https://chatgpt.com/c/<id> URL.",
    )
    parser.add_argument(
        "--output",
        default=None,
        type=Path,
        help="New directory for semantic-slug-named Markdown, JSON, and manifest files (default: CHATGPT-EXPORTS/<slug>).",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Optional explicit semantic slug override for filenames and default directory.",
    )
    return parser.parse_args(argv)


def load_gpt_bridge() -> ModuleType:
    """Load chatgpt_lib.py from the required sibling gpt skill by exact path."""
    skills_root = Path(__file__).resolve().parents[2]
    bridge_path = skills_root / "gpt" / "scripts" / "chatgpt_lib.py"
    if not bridge_path.is_file():
        raise DependencyError(
            "Required sibling skill 'gpt' is missing. Install/project both gpt and "
            "chats under the same skills root."
        )
    module_name = "_download_chatgpt_conversation_bridge"
    spec = importlib.util.spec_from_file_location(module_name, bridge_path)
    if spec is None or spec.loader is None:
        raise DependencyError(f"Could not load the gpt bridge from {bridge_path}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loaded = False
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
        loaded = True
    except (ImportError, OSError, SyntaxError) as error:
        raise DependencyError(
            f"Could not load the gpt bridge from {bridge_path}: {error}"
        ) from error
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        if not loaded:
            sys.modules.pop(module_name, None)
    return module


def download(
    conversation: str,
    output: Path | None,
    bridge: ModuleType,
    *,
    slug: str | None = None,
) -> dict[str, object]:
    """Fetch by id without navigation, then normalize and write a new export."""
    conversation_id = parse_conversation_id(conversation)
    target = bridge.ensure_chatgpt_available()
    bridge.get_session(target=target)
    raw = bridge.fetch_conversation(conversation_id, target=target)
    bundle = build_export(raw, conversation_id)
    title_val = bundle.normalized.get("source", {}).get("title")
    title_str = str(title_val) if isinstance(title_val, str) else None
    chosen_slug = (
        slug.strip()
        if slug and slug.strip()
        else slugify_title(title_str, fallback=conversation_id)
    )
    destination = output if output is not None else Path("CHATGPT-EXPORTS") / chosen_slug
    manifest = write_export(destination, bundle, slug=chosen_slug)
    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "conversation_url": manifest["conversation_url"],
        "slug": chosen_slug,
        "output_directory": str(destination.expanduser().resolve()),
        "files": [
            f"{chosen_slug}.md",
            f"{chosen_slug}.json",
            f"{chosen_slug}.manifest.json",
        ],
    }


def _bridge_error_types(
    bridge: ModuleType,
    *names: str,
) -> tuple[type[Exception], ...]:
    error_types: list[type[Exception]] = []
    for name in names:
        candidate = getattr(bridge, name, None)
        if (
            isinstance(candidate, type)
            and issubclass(candidate, Exception)
            and candidate not in error_types
        ):
            error_types.append(candidate)
    return tuple(error_types)


def main(argv: Sequence[str] | None = None, *, bridge: ModuleType | None = None) -> int:
    args = parse_args(argv)
    try:
        active_bridge = bridge if bridge is not None else load_gpt_bridge()
    except DependencyError as error:
        print(str(error), file=sys.stderr)
        return EXIT_ERROR

    try:
        result = download(args.conversation, args.output, active_bridge, slug=args.slug)
    except ExportWriteError as error:
        print(str(error), file=sys.stderr)
        return EXIT_ERROR
    except TranscriptError as error:
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
