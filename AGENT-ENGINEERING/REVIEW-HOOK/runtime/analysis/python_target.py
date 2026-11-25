"""Resolve Ruff's minimum Python target from one exact committed revision."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple

from .git_snapshot import GitSnapshot
from .model import PythonTarget, PythonTargetSource

_TABLE = re.compile(r"^\s*\[([^]]+)\]\s*(?:#.*)?$")
_ASSIGNMENT = re.compile(r"^\s*requires-python\s*=\s*(.+?)\s*(?:#.*)?$")
_QUOTED = re.compile(r"^(['\"])(.*)\1$")
_LOWER = re.compile(r"^(>=|>|~=|==)\s*([0-9]+)\.([0-9]+)(?:\.([0-9]+|\*))?.*$")
_TARGET_BY_MINOR = {
    12: PythonTarget.PY312,
    13: PythonTarget.PY313,
    14: PythonTarget.PY314,
}
_TARGET_ORDER = {
    PythonTarget.PY312: 12,
    PythonTarget.PY313: 13,
    PythonTarget.PY314: 14,
}


class PythonTargetError(ValueError):
    """The committed target metadata cannot be represented by the contract."""


@dataclass(frozen=True)
class PythonTargetResolution:
    primary: PythonTarget
    source: PythonTargetSource
    by_file: Tuple[Tuple[str, PythonTarget], ...]
    package_map: Tuple[Tuple[str, PythonTarget], ...] = ()

    def target_for(self, path: str) -> PythonTarget:
        for candidate, target in self.by_file:
            if candidate == path:
                return target
        raise PythonTargetError("no Python target was resolved for {}".format(path))

    def groups(self) -> Tuple[Tuple[PythonTarget, Tuple[str, ...]], ...]:
        grouped: Dict[PythonTarget, List[str]] = {}
        for path, target in self.by_file:
            grouped.setdefault(target, []).append(path)
        return tuple(
            (target, tuple(sorted(paths)))
            for target, paths in sorted(
                grouped.items(), key=lambda item: _TARGET_ORDER[item[0]]
            )
        )


def _unquote(raw: str, path: str) -> str:
    match = _QUOTED.fullmatch(raw)
    if match is None:
        raise PythonTargetError(
            "{} requires-python must be one quoted string".format(path)
        )
    value = match.group(2)
    if "\\" in value:
        raise PythonTargetError(
            "{} requires-python uses unsupported escapes".format(path)
        )
    return value


def _requires_python(source: bytes, path: str) -> Optional[str]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PythonTargetError("{} is not UTF-8 TOML".format(path)) from error
    table = ""
    values: List[str] = []
    for line in text.splitlines():
        table_match = _TABLE.match(line)
        if table_match is not None:
            table = table_match.group(1).strip()
            continue
        if table != "project":
            continue
        assignment = _ASSIGNMENT.match(line)
        if assignment is not None:
            values.append(_unquote(assignment.group(1), path))
    if len(values) > 1:
        raise PythonTargetError(
            "{} contains duplicate project.requires-python keys".format(path)
        )
    return values[0] if values else None


def _lower_bound(specifier: str, path: str) -> Optional[PythonTarget]:
    if "||" in specifier or ";" in specifier:
        raise PythonTargetError(
            "{} has an ambiguous requires-python expression".format(path)
        )
    lower_minors: List[int] = []
    for raw_clause in specifier.split(","):
        clause = raw_clause.strip()
        if not clause or clause.startswith(("<", "!=", "===")):
            continue
        match = _LOWER.match(clause)
        if match is None:
            raise PythonTargetError(
                "{} has an unsupported requires-python clause {!r}".format(
                    path, clause
                )
            )
        major = int(match.group(2))
        minor = int(match.group(3))
        if major != 3:
            raise PythonTargetError(
                "{} has unsupported Python major {}".format(path, major)
            )
        lower_minors.append(minor)
    if not lower_minors:
        return None
    minor = max(lower_minors)
    target = _TARGET_BY_MINOR.get(minor)
    if target is None:
        raise PythonTargetError(
            "{} has unsupported minimum Python 3.{}; supported targets are py312, py313, and py314".format(
                path, minor
            )
        )
    return target


def _package_root(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return "." if parent == "." else parent


def _contains(root: str, path: str) -> bool:
    return root == "." or path == root or path.startswith(root + "/")


def resolve_python_targets(
    snapshot: GitSnapshot,
    *,
    explicit: Optional[PythonTarget] = None,
    fallback: PythonTarget = PythonTarget.PY313,
) -> PythonTargetResolution:
    """Resolve one target per changed Python file without reading the worktree."""
    if explicit is not None and not isinstance(explicit, PythonTarget):
        raise PythonTargetError("explicit target must be py312, py313, or py314")
    if not isinstance(fallback, PythonTarget):
        raise PythonTargetError("fleet fallback must be py312, py313, or py314")
    paths = tuple(item.path for item in snapshot.python_files if item.after_blob is not None)
    if not paths:
        paths = tuple(item.path for item in snapshot.python_files)
    if explicit is not None:
        return PythonTargetResolution(
            explicit,
            PythonTargetSource.EXPLICIT,
            tuple((path, explicit) for path in sorted(paths)),
        )

    package_targets: Dict[str, PythonTarget] = {}
    for pyproject in snapshot.list_committed_paths("pyproject.toml"):
        requires = _requires_python(snapshot.read_after_blob(pyproject), pyproject)
        if requires is None:
            continue
        target = _lower_bound(requires, pyproject)
        if target is not None:
            package_targets[_package_root(pyproject)] = target

    by_file: List[Tuple[str, PythonTarget]] = []
    roots_used: Dict[str, PythonTarget] = {}
    for path in sorted(paths):
        candidates = [root for root in package_targets if _contains(root, path)]
        if candidates:
            root = max(candidates, key=lambda value: (value.count("/"), len(value)))
            target = package_targets[root]
            roots_used[root] = target
        else:
            root = "."
            target = fallback
            roots_used.setdefault(root, target)
        by_file.append((path, target))

    unique = {target for _, target in by_file}
    if not by_file:
        primary = fallback
        source = PythonTargetSource.FLEET_FALLBACK
        package_map: Tuple[Tuple[str, PythonTarget], ...] = ()
    elif len(unique) == 1:
        primary = next(iter(unique))
        source = (
            PythonTargetSource.REQUIRES_PYTHON
            if any(root in package_targets for root in roots_used)
            else PythonTargetSource.FLEET_FALLBACK
        )
        package_map = ()
    else:
        primary = min(unique, key=lambda target: _TARGET_ORDER[target])
        source = PythonTargetSource.PACKAGE_MAP
        package_map = tuple(
            sorted(
                roots_used.items(),
                key=lambda item: (item[0] != ".", item[0]),
            )
        )
    return PythonTargetResolution(primary, source, tuple(by_file), package_map)


__all__ = [
    "PythonTargetError",
    "PythonTargetResolution",
    "resolve_python_targets",
]

