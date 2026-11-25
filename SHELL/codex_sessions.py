#!/usr/bin/env python3
"""Discover local Codex sessions and resume in their original account and home."""

import argparse
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Account:
    number: str
    canonical: Path
    state: Path
    bare: Path
    fresh: Path


@dataclass(frozen=True)
class Home:
    path: Path
    account: Account
    kind: str


@dataclass(frozen=True)
class Session:
    home: Home
    id: str
    cwd: str
    title: str
    updated: float
    source: str
    history_mode: str
    archived: bool = False

    def record(self) -> dict[str, str | float | bool]:
        return {
            "id": self.id,
            "account": self.home.account.number,
            "home": str(self.home.path),
            "kind": self.home.kind,
            "cwd": self.cwd,
            "title": self.title,
            "updated": self.updated,
            "source": self.source,
            "history_mode": self.history_mode,
            "archived": self.archived,
        }


class DiscoveryError(ValueError):
    pass


def configured_accounts() -> list[Account]:
    def path(name: str, default: Path) -> Path:
        return Path(os.environ.get(name, str(default))).expanduser().resolve()

    user = Path.home()
    primary_state = path("CODEX_STATE_ROOT", user / ".codex-state")
    secondary_state = path("CODEX2_STATE_ROOT", user / ".codex-state2")
    return [
        Account(
            "1",
            path("CODEX_CANONICAL_HOME", user / ".codex"),
            primary_state,
            path("CODEX_BARE_STATE_ROOT", primary_state / "bare"),
            path("CODEX_FRESH_STATE_ROOT", primary_state / "fresh"),
        ),
        Account(
            "2",
            path("CODEX2_HOME", user / ".codex2"),
            secondary_state,
            secondary_state / "bare",
            secondary_state / "fresh",
        ),
    ]


def discover_homes(accounts: list[Account]) -> list[Home]:
    homes = {}
    for account in accounts:
        candidates = [(account.canonical, "global")]
        candidates += [(p, "repo") for p in (account.state / "repos").glob("*")]
        candidates += [(p, "fresh") for p in account.fresh.glob("codex-fresh.*")]
        candidates += [(p, "bare") for p in account.bare.glob("codex-bare.*")]
        candidates += [(p, "bare") for p in (account.bare / "repos").glob("*/*")]
        # The legacy branch layout has exactly two levels beneath the state root.
        for parent in account.state.glob("*"):
            if parent.is_dir() and parent.name not in {"repos", "bare", "fresh"}:
                candidates += [(p, "branch") for p in parent.glob("*")]
        for path, kind in candidates:
            if not path.is_dir():
                continue
            resolved = path.resolve()
            previous = homes.get(resolved)
            if previous and previous.account.number != account.number:
                raise DiscoveryError(f"Both accounts map to the same home: {resolved}")
            homes.setdefault(resolved, Home(resolved, account, kind))
    return list(homes.values())


def sqlite_directory(home: Home) -> Path:
    config = home.path / "config.toml"
    if not config.exists():
        return home.path
    with config.open("rb") as handle:
        value = tomllib.load(handle).get("sqlite_home")
    if value is None:
        return home.path
    if not isinstance(value, str) or not value:
        raise DiscoveryError(f"Invalid sqlite_home in {config}")
    # Config-relative paths are resolved by Codex from its launch directory.
    if not Path(value).is_absolute():
        raise DiscoveryError(
            f"Relative sqlite_home in {config}; use an absolute storage path"
        )
    return Path(value).resolve()


def read_database(home: Home) -> dict[str, Session]:
    databases = [
        p
        for p in sqlite_directory(home).glob("state_*.sqlite")
        if p.stem.removeprefix("state_").isdigit()
    ]
    if not databases:
        return {}
    database = max(databases, key=lambda p: int(p.stem.split("_")[1]))
    with sqlite3.connect(
        database.as_uri() + "?mode=ro", uri=True, timeout=1
    ) as connection:
        connection.execute("PRAGMA query_only=ON")
        columns = {r[1] for r in connection.execute("PRAGMA table_info(threads)")}
        required = {"id", "cwd", "title", "updated_at", "source", "archived"}
        if not required <= columns:
            raise DiscoveryError(f"Unsupported thread metadata schema: {database}")
        name = "COALESCE(NULLIF(name, ''), title)" if "name" in columns else "title"
        updated = (
            "COALESCE(updated_at_ms / 1000.0, updated_at)"
            if "updated_at_ms" in columns
            else "updated_at"
        )
        mode = "history_mode" if "history_mode" in columns else "'legacy'"
        rows = connection.execute(
            f"SELECT id, cwd, {name}, {updated}, source, {mode}, archived FROM threads"
        )
        return {
            r[0]: Session(home, r[0], r[1], r[2], r[3], r[4], r[5], bool(r[6]))
            for r in rows
        }


def read_rollout(home: Home, path: Path, archived: bool) -> Session:
    with path.open() as handle:
        first = handle.readline(8 * 1024 * 1024)
    value = json.loads(first)
    if not isinstance(value, dict):
        raise DiscoveryError(f"Invalid session metadata: {path}")
    metadata = value["payload"] if value.get("type") == "session_meta" else value
    if not isinstance(metadata, dict) or not isinstance(metadata.get("id"), str):
        raise DiscoveryError(f"Missing session metadata: {path}")
    cwd = metadata.get("cwd", "")
    if not isinstance(cwd, str):
        raise DiscoveryError(f"Invalid working directory in {path}")
    source = metadata.get("source", "unknown")
    if not isinstance(source, str):
        source = "subagent"
    mode = "legacy" if value.get("type") == "session_meta" else "pre-session-meta"
    return Session(
        home,
        metadata["id"],
        cwd,
        metadata["id"],
        path.stat().st_mtime,
        source,
        mode,
        archived,
    )


def read_sessions(home: Home) -> list[Session]:
    sessions = read_database(home)
    # Rollouts fill gaps in older/unindexed homes; the database owns indexed rows,
    # including paginated history, archived state and names.
    for directory, pattern, archived in (
        ("sessions", "*/*/*/rollout-*.jsonl", False),
        ("archived_sessions", "rollout-*.jsonl", True),
    ):
        for path in (home.path / directory).glob(pattern):
            if path.stem[-36:] in sessions:
                continue
            try:
                session = read_rollout(home, path, archived)
                sessions.setdefault(session.id, session)
            except (OSError, ValueError, KeyError) as error:
                print(f"codex-sessions: skipped {path}: {error}", file=sys.stderr)
    index = home.path / "session_index.jsonl"
    if index.exists():
        with index.open() as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue  # Another writer may still be appending the last line.
                if not isinstance(item, dict):
                    raise DiscoveryError(f"Invalid session-name record: {index}")
                if (
                    item.get("id") in sessions
                    and isinstance(item.get("thread_name"), str)
                    and item["thread_name"]
                ):
                    old = sessions[item["id"]]
                    sessions[old.id] = Session(
                        home,
                        old.id,
                        old.cwd,
                        item["thread_name"],
                        old.updated,
                        old.source,
                        old.history_mode,
                        old.archived,
                    )
    return list(sessions.values())


def discover_sessions(accounts: list[Account]) -> list[Session]:
    sessions = []
    for home in discover_homes(accounts):
        try:
            sessions.extend(read_sessions(home))
        except (OSError, ValueError, sqlite3.Error) as error:
            print(f"codex-sessions: cannot read {home.path}: {error}", file=sys.stderr)
    return sorted(
        sessions, key=lambda s: (s.updated, s.id, str(s.home.path)), reverse=True
    )


def display(session: Session) -> str:
    date = (
        datetime.fromtimestamp(session.updated, UTC)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
    )
    state = " [archived]" if session.archived else ""
    if session.history_mode == "pre-session-meta":
        state += " [old format: conversion required]"
    text = f"{date}  account {session.home.account.number}/{session.home.kind}{state}  {session.title[:100]}  {session.cwd or '(directory unknown)'}  {session.id}"
    return "".join(c if c.isprintable() else " " for c in text)


def choose(sessions: list[Session], selector: str | None, last: bool) -> Session:
    if selector:
        matches = [s for s in sessions if s.id == selector or s.title == selector]
        if not matches:
            raise DiscoveryError(f"No saved session matches {selector!r}")
        if len(matches) != 1:
            paths = "\n".join(
                f"  account {s.home.account.number}: {s.home.path}" for s in matches
            )
            raise DiscoveryError(
                f"Ambiguous session {selector!r}; select --home PATH:\n{paths}"
            )
        return matches[0]
    if not sessions:
        raise DiscoveryError(
            "No sessions match. Use --all for other working directories, or --include-archived."
        )
    if last:
        return choose(sessions, sessions[0].id, False)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise DiscoveryError(
            "The picker needs a terminal; use --list, --last, or a session ID."
        )
    if shutil.which("fzf"):
        lines = "\n".join(f"{i}\t{display(s)}" for i, s in enumerate(sessions))
        result = subprocess.run(
            [
                "fzf",
                "--delimiter=\t",
                "--with-nth=2..",
                "--no-multi",
                "--height=80%",
                "--reverse",
                "--prompt=Codex sessions > ",
            ],
            input=lines,
            text=True,
            stdout=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise KeyboardInterrupt
        index = int(result.stdout.split("\t", 1)[0])
    else:
        for i, session in enumerate(sessions, 1):
            print(f"[{i}] {display(session)}")
        index = int(input(f"Select [1-{len(sessions)}]: ")) - 1
    if not 0 <= index < len(sessions):
        raise DiscoveryError("Selection is outside the displayed list")
    return sessions[index]


def launch_environment(session: Session) -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "OPENAI_BASE_URL",
        "CODEX_SQLITE_HOME",
        "REVIEW_AFTER_COMMIT_MODE",
        "CODEX_HOOK_STATE_DIR",
        "CODEX_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY",
        "CODEX_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY",
    ):
        env.pop(key, None)
    env.update(
        CODEX_HOME=str(session.home.path),
        CODEX_CANONICAL_HOME=str(session.home.account.canonical),
        CODEX_STATE_ROOT=str(session.home.account.state),
    )
    return env


def resume_command(session: Session, native: list[str]) -> list[str]:
    if session.history_mode == "pre-session-meta":
        raise DiscoveryError(
            f"Session {session.id} predates native session metadata and requires format conversion before resume. Original files in {session.home.path} are unchanged."
        )
    for i, argument in enumerate(native):
        if argument == "--":
            break
        value = ""
        if argument in {"-c", "--config"} and i + 1 < len(native):
            value = native[i + 1]
        elif argument.startswith("--config="):
            value = argument[len("--config=") :]
        elif argument.startswith("-c"):
            value = argument[2:]
        if value.partition("=")[0].strip() == "sqlite_home":
            raise DiscoveryError(
                "sqlite_home overrides would separate the session store from its writer locks; resume in the original home"
            )
        if argument == "--remote" or argument.startswith("--remote="):
            raise DiscoveryError(
                "This picker selects local sessions; use native codex for remote-server attachment"
            )
    if session.home.kind == "bare":
        for name in ("AGENTS.md", "AGENTS.override.md"):
            path = session.home.path / name
            if path.exists() or path.is_symlink():
                raise DiscoveryError(
                    f"Bare home contains automatic instructions: {path}; relocate it before resuming"
                )
    # Keep storage and writer-lock ownership together. Native Codex handles history
    # replay, saved working-directory selection and active-writer exclusion.
    return ["codex", "resume", session.id, *native]


def resume_defaults() -> dict[str, str | int | bool | Path]:
    path = Path(
        os.environ.get("CODEX_RESUME_CONFIG", str(Path.home() / ".codex/resume.conf"))
    ).expanduser()
    defaults = {}
    if not path.exists():
        return defaults
    keys = {
        "any": "all",
        "last": "last",
        "dir": "dir",
        "limit": "limit",
        "effort": "effort",
    }
    for line in path.read_text().splitlines():
        key, separator, raw = line.partition("=")
        key = key.strip()
        if not separator or key not in keys:
            continue
        words = shlex.split(raw, comments=True)
        if len(words) != 1:
            raise DiscoveryError(f"Invalid {key} in {path}")
        value = words[0]
        if key in {"any", "last"}:
            if value not in {"0", "1", "false", "true", "no", "yes", "off", "on"}:
                raise DiscoveryError(f"Invalid {key} in {path}")
            value = value in {"1", "true", "yes", "on"}
        elif key == "limit":
            value = int(value)
        elif key == "dir":
            value = Path(value).expanduser()
        defaults[keys[key]] = value
    return defaults


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Resume local Codex sessions across both accounts in their original homes. "
        "Default: current directory, both accounts, including headless sessions. "
        "Use --all to search every directory. Account selection filters sources; it does not switch a session's account.",
        epilog="Native Codex options and an optional continuation prompt may follow --. "
        "No credentials, conversations or databases are copied or merged.",
        allow_abbrev=False,
    )
    result.add_argument(
        "session",
        nargs="?",
        help="exact saved session ID or name (ignores directory filtering)",
    )
    result.add_argument("--account", choices=("1", "2", "all"), default="all")
    result.add_argument(
        "--home",
        type=Path,
        help="select one original home, including ambiguous duplicate IDs",
    )
    result.add_argument(
        "--all", "--any", action="store_true", help="search all working directories"
    )
    result.add_argument(
        "--dir", type=Path, help="filter to this saved working directory"
    )
    result.add_argument(
        "--last", action="store_true", help="resume the latest matching session"
    )
    result.add_argument(
        "--include-archived",
        action="store_true",
        help="also list archived sessions; selecting one unarchives it before resume",
    )
    result.add_argument(
        "--include-subagents",
        action="store_true",
        help="also show internal child-agent sessions",
    )
    result.add_argument(
        "--include-non-interactive",
        action="store_true",
        help="accepted for native compatibility; already included",
    )
    result.add_argument(
        "--list", action="store_true", help="list matching sessions without launching"
    )
    result.add_argument(
        "--json", action="store_true", help="machine-readable --list output"
    )
    result.add_argument(
        "--dry-run",
        action="store_true",
        help="print selected account, home and launch arguments without launching",
    )
    result.add_argument(
        "--limit",
        type=int,
        default=200,
        help="list size or explicit picker cap; the picker is otherwise unlimited; 0 means unlimited",
    )
    result.add_argument(
        "--refresh",
        action="store_true",
        help="accepted for compatibility; discovery is always live",
    )
    result.add_argument("--effort", help="override model_reasoning_effort")
    context = result.add_mutually_exclusive_group()
    context.add_argument("--ctx-mgmt", "-cm", action="store_true", default=None)
    context.add_argument("--no-ctx-mgmt", dest="ctx_mgmt", action="store_false")
    for short, long in (
        ("-c", "--config"),
        ("-m", "--model"),
        ("-C", "--cd"),
        ("-s", "--sandbox"),
        ("-a", "--ask-for-approval"),
    ):
        result.add_argument(short, long, action="append", default=[])
    result.add_argument("--profile", action="append", default=[])
    result.set_defaults(**resume_defaults())
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    native = []
    if "--" in arguments:
        split = arguments.index("--")
        native = arguments[split + 1 :]
        arguments = arguments[:split]
    cli = parser()
    args = cli.parse_args(arguments)
    if args.limit < 0 or (args.json and not args.list):
        cli.error("--limit must be nonnegative; --json requires --list")
    if args.session and "--last" in arguments:
        cli.error(
            "choose a session ID/name or --last, not both; put a continuation prompt after --"
        )
    overrides = []
    for field, flag in (
        ("config", "-c"),
        ("model", "-m"),
        ("cd", "-C"),
        ("sandbox", "-s"),
        ("ask_for_approval", "-a"),
        ("profile", "--profile"),
    ):
        for value in getattr(args, field):
            overrides += [flag, value]
    explicit_effort = "--effort" in arguments or any(
        a.startswith("--effort=") for a in arguments
    )
    if args.effort and (
        explicit_effort
        or not any("model_reasoning_effort=" in a for a in overrides + native)
    ):
        overrides += ["-c", f"model_reasoning_effort={json.dumps(args.effort)}"]
    if args.ctx_mgmt is not None:
        overrides += [
            "-c",
            f"features.context_management.experimental_mode={str(args.ctx_mgmt).lower()}",
        ]
    native = overrides + native
    accounts = [a for a in configured_accounts() if args.account in ("all", a.number)]
    sessions = discover_sessions(accounts)
    if args.home:
        sessions = [
            s for s in sessions if s.home.path == args.home.expanduser().resolve()
        ]
    if args.session:
        sessions = [
            s for s in sessions if s.id == args.session or s.title == args.session
        ]
    else:
        if args.last:
            sessions = [s for s in sessions if s.history_mode != "pre-session-meta"]
        if not args.include_subagents:
            sessions = [s for s in sessions if "subagent" not in s.source]
        if not args.include_archived:
            sessions = [s for s in sessions if not s.archived]
        if args.dir or not args.all:
            directory = (args.dir or Path.cwd()).resolve()
            sessions = [
                s for s in sessions if s.cwd and Path(s.cwd).resolve() == directory
            ]
    if args.list:
        listed = sessions[: args.limit] if args.limit else sessions
        print(
            json.dumps([s.record() for s in listed], indent=2)
            if args.json
            else "\n".join(display(s) for s in listed)
        )
        return 0
    explicit_limit = "--limit" in arguments or any(
        a.startswith("--limit=") for a in arguments
    )
    offered = sessions
    if explicit_limit and args.limit and not (args.session or args.last):
        offered = sessions[: args.limit]
    session = choose(offered, args.session, args.last)
    command = resume_command(session, native)
    unarchive = ["codex", "unarchive", session.id] if session.archived else []
    if args.dry_run:
        print(
            json.dumps(
                dict(session.record(), command=command, before_resume=unarchive),
                indent=2,
            )
        )
        return 0
    print(
        f"Resuming account {session.home.account.number}/{session.home.kind}: {session.id}\n"
        f"Home: {session.home.path}",
        file=sys.stderr,
    )
    env = launch_environment(session)
    if unarchive:
        result = subprocess.run(unarchive, env=env, check=False)
        if result.returncode:
            return result.returncode
    os.execvpe(command[0], command, env)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DiscoveryError, OSError, ValueError) as error:
        print(f"codex-sessions: {error}", file=sys.stderr)
        raise SystemExit(1)
    except (KeyboardInterrupt, EOFError):
        raise SystemExit(130)
