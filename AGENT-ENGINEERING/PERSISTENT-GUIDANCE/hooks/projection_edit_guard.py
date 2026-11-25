#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import json
import os
import shlex
import sys
from pathlib import Path

# Under HOME. `guidance sync` writes it, so the installed guard never reads the checkout.
INDEX = Path(".local/state/persistent-guidance/edit-guard.json")
INDEX_SCHEMA_VERSION = 1


def _absolute(path: str, base: Path, home: Path) -> Path:
    if not isinstance(path, str) or not path:
        raise ValueError("expected a non-empty path string")
    if path == "~" or path.startswith("~/"):
        path = str(home) + path[1:]
    return Path(os.path.normpath(base / path))


def _resolve(path: str, base: Path, home: Path) -> Path:
    # Symlinks resolve when the hook runs, so links made after sync still count.
    return Path(os.path.realpath(_absolute(path, base, home)))


def _matches(relative: str, pattern: str) -> bool:
    """Path.glob semantics, as sync uses: `*` stays in one segment, `**` spans any."""
    return _match_parts(relative.split("/"), pattern.split("/"))


def _match_parts(parts: list[str], pattern: list[str]) -> bool:
    if not pattern:
        return not parts
    if pattern[0] == "**":
        return any(_match_parts(parts[index:], pattern[1:]) for index in range(len(parts) + 1))
    return (
        bool(parts)
        and fnmatch.fnmatchcase(parts[0], pattern[0])
        and _match_parts(parts[1:], pattern[1:])
    )


def _rules(
    guidance: Path, skills: Path, home: Path, enabled_hosts: frozenset[str] | None
) -> list[tuple[Path, Path, list[str] | None, str]]:
    with (guidance / "hosts.json").open(encoding="utf-8") as stream:
        projections = json.load(stream)["projections"]
    with (skills / "registry.json").open(encoding="utf-8") as stream:
        records = json.load(stream)["skills"]
    if not isinstance(projections, list) or not isinstance(records, dict):
        raise TypeError("invalid projections/skills map shape")
    if not all(isinstance(item, dict) for item in [*projections, *records.values()]):
        raise TypeError("projection and skill records must be objects")
    guidance_sync = f"cd {shlex.quote(str(guidance))} && ./guidance sync"
    skill_sync = f"cd {shlex.quote(str(skills))} && bin/skill-system refresh --apply"
    rules = []
    for projection in projections:
        if "managed_keys" in projection:
            continue
        # A disabled host's projection is not installed, so its path is ordinary.
        if enabled_hosts is not None and not enabled_hosts & set(projection.get("hosts", [])):
            continue
        if "source" in projection:
            source, target, patterns = projection["source"], projection["target"], None
        else:
            source = projection["source_tree"]
            target, patterns = projection["target_tree"], projection["include"]
            if (
                not isinstance(patterns, list)
                or not patterns
                or not all(isinstance(pattern, str) and pattern for pattern in patterns)
            ):
                raise ValueError("tree include must be a non-empty list of patterns")
        rules.append(
            (
                _absolute(target, home, home),
                _absolute(source, guidance, home),
                patterns,
                guidance_sync,
            )
        )
    for record in records.values():
        # Legacy records are audit evidence, not managed projections, and lack sources.
        if record.get("ownership") == "legacy-unmanaged":
            continue
        source = _absolute(record["source"], skills, home)
        targets = record["install_targets"]
        if not isinstance(targets, list):
            raise TypeError("skill install_targets must be a list")
        for target in targets:
            rules.append((_absolute(target, home, home), source, ["**"], skill_sync))
    return rules


def build_index(
    guidance: Path, home: Path, enabled_hosts: frozenset[str] | None = None
) -> dict:
    """Every installed projection with its canonical source, for this checkout and home.

    `enabled_hosts` None means every host, as when no machine file exists.
    """
    guidance = Path(os.path.realpath(guidance))
    engineering = guidance.parent
    rules = _rules(
        guidance, engineering / "SKILL-SYSTEM", Path(os.path.realpath(home)), enabled_hosts
    )
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        # Canonical sources live here; edits inside it are never projections.
        "exempt": str(engineering),
        "rules": [
            {
                "installed": str(installed),
                "source": str(source),
                "patterns": patterns,
                "command": command,
            }
            for installed, source, patterns, command in rules
        ],
    }


def _load_index(home: Path) -> tuple[Path, list[tuple[Path, Path, list[str] | None, str]]]:
    path = home / INDEX
    with path.open(encoding="utf-8") as stream:
        index = json.load(stream)
    if not isinstance(index, dict) or index.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise ValueError(f"{path} needs schema_version {INDEX_SCHEMA_VERSION}; run guidance sync")
    rules = []
    for rule in index["rules"]:
        patterns = rule["patterns"]
        if not (
            all(isinstance(rule[key], str) and rule[key] for key in ("installed", "source", "command"))
            and (patterns is None or (isinstance(patterns, list) and all(isinstance(p, str) for p in patterns)))
        ):
            raise TypeError(f"invalid rule in {path}")
        rules.append(
            (
                Path(os.path.realpath(rule["installed"])),
                Path(os.path.realpath(rule["source"])),
                patterns,
                rule["command"],
            )
        )
    if not isinstance(index["exempt"], str):
        raise TypeError(f"invalid exempt root in {path}")
    return Path(index["exempt"]), rules


def _run() -> int:
    event = json.load(sys.stdin)
    if not isinstance(event, dict):
        raise TypeError("hook input must be an object")
    tool = event.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return 0
    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        raise TypeError("tool_input must be an object")
    path = tool_input.get("notebook_path" if tool == "NotebookEdit" else "file_path")
    if path is None:
        return 0
    home = Path.home()
    target = _resolve(path, _resolve(event["cwd"], Path.cwd(), home), home)
    engineering, rules = _load_index(home)
    if target.is_relative_to(engineering):
        return 0
    # A canonical source outside the exempt root (the shell layer) is still
    # canonical, also when an older setup linked the installed path to it.
    for installed, source, patterns, command in rules:
        if target == source or (patterns is not None and target.is_relative_to(source)):
            return 0
    for installed, source, patterns, command in rules:
        if not target.is_relative_to(installed):
            continue
        relative = target.relative_to(installed)
        if (patterns is None and target == installed) or (
            patterns is not None
            and any(_matches(relative.as_posix(), pattern) for pattern in patterns)
        ):
            print(
                f"{str(target)!r} is an installed projection; edit {str(source / relative)!r} "
                f"instead, then {command} (preview first with --dry-run).",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_run())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            f"projection-edit-guard: {str(error).replace(chr(10), ' ')}",
            file=sys.stderr,
        )
        sys.exit(1)
