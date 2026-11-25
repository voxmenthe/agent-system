from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .antigravity import configure_antigravity
from .claude import configure_claude
from .mimo import configure_mimo
from .model import SkillSystemError
from .operations import SkillSystem


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _mutation_flags(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="enumerate changes without writing (the default)",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="perform the explicitly scoped mutation",
    )


def build_parser() -> argparse.ArgumentParser:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        prog="skill-system",
        description=(
            "Validate and project owner-controlled skills. Mutations are "
            "dry-run unless --apply is explicit."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help=f"canonical skill-system root (default: {default_root})",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help="home directory containing .agents (default: current user home)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("validate", help="validate canonical sources only")
    commands.add_parser(
        "audit",
        help="validate canonical sources and strictly parse install state",
    )
    commands.add_parser(
        "audit-codex",
        help="read-only inventory of personal ~/.codex/skills entries",
    )
    commands.add_parser(
        "status",
        help="reconcile registry, install state, and live target hashes",
    )

    install = commands.add_parser(
        "install",
        help="project one custom skill into ~/.agents/skills",
    )
    install.add_argument("skill")
    _mutation_flags(install)

    refresh = commands.add_parser(
        "refresh",
        help="update every managed skill whose canonical source changed",
    )
    _mutation_flags(refresh)

    sync = commands.add_parser(
        "sync",
        help=(
            "install absent and refresh source-updated custom skills; "
            "warn about collisions unless forced"
        ),
    )
    _mutation_flags(sync)
    sync.add_argument(
        "--force",
        action="store_true",
        help="adopt unmanaged-collision and locally-modified targets (canonical wins)",
    )

    rollback = commands.add_parser(
        "rollback",
        help="restore the retained preimage for one operation",
    )
    rollback.add_argument("operation_id")
    _mutation_flags(rollback)

    quarantine = commands.add_parser(
        "quarantine",
        help="move one exact live skill outside discovery without deleting it",
    )
    quarantine.add_argument("skill")
    _mutation_flags(quarantine)

    migrate = commands.add_parser(
        "migrate-lock",
        help="remove only the verified Matt entries from the v3 skill lock",
    )
    _mutation_flags(migrate)

    antigravity = commands.add_parser(
        "configure-antigravity",
        help="declare ~/.agents/skills in Antigravity CLI global discovery",
    )
    _mutation_flags(antigravity)

    claude = commands.add_parser(
        "configure-claude",
        help="project active ~/.agents/skills into ~/.claude/skills and remove stale symlinks",
    )
    _mutation_flags(claude)
    claude.add_argument(
        "--force",
        action="store_true",
        help="replace colliding directories in ~/.claude/skills with symlinks",
    )

    mimo = commands.add_parser(
        "configure-mimo",
        help=(
            "copy active ~/.agents/skills into ~/.config/mimocode/skills "
            "in MiMo Desktop layout"
        ),
    )
    _mutation_flags(mimo)
    mimo.add_argument(
        "--force",
        action="store_true",
        help="replace unmanaged colliding directories in ~/.config/mimocode/skills",
    )
    grok = commands.add_parser(
        "configure-grok",
        help="link Grok-only canonical skills into ~/.grok/skills, ~/.grok2/skills and ~/.grok3/skills",
    )
    _mutation_flags(grok)
    grok.add_argument(
        "--force",
        action="store_true",
        help="back up colliding Grok entries outside discovery before replacing them",
    )
    relocate = commands.add_parser(
        "relocate",
        help="point install state and Grok links from a previous checkout at this one",
    )
    _mutation_flags(relocate)
    relocate.add_argument(
        "--from",
        dest="old_root",
        type=Path,
        required=True,
        help="the previous checkout's SKILL-SYSTEM directory",
    )
    return parser


def run(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(arguments)
    system = SkillSystem(options.root, options.home)
    try:
        if options.command == "validate":
            result = system.validate()
        elif options.command == "audit":
            result = system.audit()
        elif options.command == "audit-codex":
            result = system.audit_codex()
        elif options.command == "status":
            result = system.status()
        elif options.command == "install":
            result = system.install(options.skill, apply=options.apply)
        elif options.command == "refresh":
            result = system.refresh(apply=options.apply)
        elif options.command == "sync":
            result = system.sync(apply=options.apply, force=options.force)
        elif options.command == "rollback":
            result = system.rollback(options.operation_id, apply=options.apply)
        elif options.command == "quarantine":
            result = system.quarantine(options.skill, apply=options.apply)
        elif options.command == "migrate-lock":
            result = system.migrate_lock(apply=options.apply)
        elif options.command == "configure-antigravity":
            result = configure_antigravity(
                options.home,
                apply=options.apply,
            )
        elif options.command == "configure-claude":
            result = configure_claude(
                options.root,
                options.home,
                apply=options.apply,
                force=options.force,
            )
        elif options.command == "configure-mimo":
            result = configure_mimo(
                options.root,
                options.home,
                apply=options.apply,
                force=options.force,
            )
        elif options.command == "configure-grok":
            result = system.configure_grok(apply=options.apply, force=options.force)
        elif options.command == "relocate":
            result = system.relocate(options.old_root, apply=options.apply)
        else:
            raise AssertionError(f"unhandled command: {options.command}")
    except SkillSystemError as exc:
        print(f"skill-system: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(_json_value(result), indent=2, sort_keys=True))
    if options.command == "audit-codex" and not result.ok:
        return 1
    return 0



def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
