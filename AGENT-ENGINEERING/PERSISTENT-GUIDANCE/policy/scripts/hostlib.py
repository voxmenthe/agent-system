from __future__ import annotations

import contextlib
import copy
import difflib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from configlib import ABSENT, ConfigFormat, config_view, merge_config, select_config

HOST_MANIFEST = "hosts.json"
# Per-machine, untracked; bootstrap writes it. Absent means every host is enabled.
MACHINE_FILE = Path(".config/agent-system/machine.json")
STATE_SCHEMA_VERSION = 1
# Projections without `independent` share one group, so the kernel fan-out and
# the policy tree it routes to are always applied together or not at all.
SHARED_SYNC_GROUP = "shared"
SEMANTIC_PARSERS = {".json": json.loads, ".toml": tomllib.loads}
UNOWNED_CONFLICT = "existing target is not owned by this manager"
UNOWNED_BACKUP = "not written by this manager; sync keeps the old file as a backup"
# Canonical text writes this where the home directory goes; sync renders it and
# adopt turns the home path back into it, so config/ holds no machine's path.
HOME_TOKEN = b"@HOME@"
# Rendered into JSON, TOML and shell strings unescaped, so only plain path characters.
_PLAIN_HOME = re.compile(r"/[A-Za-z0-9._/-]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)[^:=\n]*[:=]"
)


class GuidanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Operation:
    operation_id: str
    kind: Literal["write", "retire"]
    target_relative: Path
    hosts: tuple[str, ...]
    desired: bytes | None = None
    source_relative: Path | None = None
    adopt_sha256: frozenset[str] = frozenset()
    reason: str = ""
    sync_group: str = SHARED_SYNC_GROUP
    # None means byte comparison only; a tuple (possibly empty) opts into
    # parsed comparison that ignores formatting and these host-written keys.
    host_owned_keys: tuple[tuple[str, ...], ...] | None = None
    managed_keys: tuple[tuple[str, ...], ...] | None = None
    # Sync adds execute bits where the target has read bits; it never removes them.
    executable: bool = False

    @property
    def desired_sha256(self) -> str | None:
        return sha256_bytes(self.desired) if self.desired is not None else None

    @property
    def config_format(self) -> ConfigFormat:
        assert self.source_relative is not None
        return "json" if self.source_relative.suffix == ".json" else "toml"


@dataclass(frozen=True)
class OperationStatus:
    operation: Operation
    state: str
    current_sha256: str | None = None
    detail: str = ""
    # What sync writes when it is not the canonical bytes: canonical content
    # merged into the live file's host-owned or unmanaged values.
    merged_target: bytes | None = None

    @property
    def is_conflict(self) -> bool:
        return self.state == "conflict"

    @property
    def needs_change(self) -> bool:
        return self.state in {
            "missing",
            "legacy",
            "managed-stale",
            "replace-unowned",
            "retirement-needed",
        }


@dataclass(frozen=True)
class SyncPlan:
    root: Path
    home: Path
    state_dir: Path
    manifest: dict[str, Any]
    state: dict[str, Any]
    statuses: tuple[OperationStatus, ...]
    source_fingerprint: str
    enabled_hosts: frozenset[str]
    # Opt-in: back up and replace files this manager never wrote, instead of
    # reporting them as conflicts.
    replace_unowned: bool = False

    @property
    def conflicts(self) -> tuple[OperationStatus, ...]:
        return tuple(status for status in self.statuses if status.is_conflict)

    @property
    def changes(self) -> tuple[OperationStatus, ...]:
        return tuple(status for status in self.statuses if status.needs_change)

    @property
    def applicable(self) -> tuple[OperationStatus, ...]:
        """Enabled statuses outside every sync group that contains a conflict."""
        blocked = {status.operation.sync_group for status in self.conflicts}
        return tuple(
            status
            for status in self.statuses
            if status.operation.sync_group not in blocked
            and status.state != "disabled"
        )


@dataclass(frozen=True)
class SyncResult:
    plan: SyncPlan
    transaction_id: str | None


@dataclass(frozen=True)
class ConsumerVerification:
    host: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class Adoption:
    operation_id: str
    source_relative: Path
    target_relative: Path
    source_sha256: str
    target_sha256: str
    evidence: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(raw: object, label: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise GuidanceError(f"{label} must be a non-empty relative path")
    path = Path(raw)
    if path == Path(".") or path.is_absolute() or ".." in path.parts:
        raise GuidanceError(f"{label} must stay within its declared root: {raw!r}")
    return path


def _source_path(raw: object, label: str, *, may_climb: bool) -> Path:
    """A source path; leading `..` parts are allowed when the manifest names a repository root."""
    if not isinstance(raw, str) or not raw.strip():
        raise GuidanceError(f"{label} must be a non-empty relative path")
    path = Path(raw)
    climb = 0
    while climb < len(path.parts) and path.parts[climb] == "..":
        climb += 1
    if (
        path == Path(".")
        or path.is_absolute()
        or ".." in path.parts[climb:]
        or (climb and not may_climb)
    ):
        raise GuidanceError(f"{label} must stay within its declared root: {raw!r}")
    return path


def _string_list(raw: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(raw, list) or (not raw and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise GuidanceError(f"{label} must be {qualifier}")
    if any(not isinstance(item, str) or not item.strip() for item in raw):
        raise GuidanceError(f"{label} entries must be non-empty strings")
    return raw


def _hashes(raw: object, label: str) -> frozenset[str]:
    values = _string_list(raw if raw is not None else [], label, allow_empty=True)
    for value in values:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise GuidanceError(
                f"{label} contains an invalid SHA-256 digest: {value!r}"
            )
    return frozenset(values)


def load_host_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    path = root / HOST_MANIFEST
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GuidanceError(f"host manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GuidanceError(f"invalid JSON in {path}: {exc}") from exc
    validate_host_manifest(manifest, root)
    return manifest


def validate_host_manifest(manifest: dict[str, Any], root: Path) -> None:
    if not isinstance(manifest, dict):
        raise GuidanceError("hosts.json must contain an object")
    if manifest.get("schema_version") != 1:
        raise GuidanceError("hosts.json schema_version must be 1")
    if (
        not isinstance(manifest.get("manager_id"), str)
        or not manifest["manager_id"].strip()
    ):
        raise GuidanceError("hosts.json manager_id must be a non-empty string")

    _relative_path(manifest.get("state_dir"), "state_dir")
    # Sources may reach the rest of the checkout (the shell layer), never beyond it.
    repository = root
    if "repository_root" in manifest:
        raw = manifest["repository_root"]
        if not isinstance(raw, str) or not raw or any(part != ".." for part in Path(raw).parts):
            raise GuidanceError("repository_root must be a path of `..` parts, such as ../..")
        repository = (root / raw).resolve()
    may_climb = repository != root
    if "edit_guard" in manifest:
        guard = _relative_path(manifest["edit_guard"], "edit_guard")
        if not (root / guard).is_file():
            raise GuidanceError(f"edit_guard does not exist: {guard}")
    required_hosts = set(_string_list(manifest.get("required_hosts"), "required_hosts"))
    if len(required_hosts) != len(manifest["required_hosts"]):
        raise GuidanceError("required_hosts contains duplicates")

    protected = tuple(
        _relative_path(item, "protected_source_paths entry")
        for item in _string_list(
            manifest.get("protected_source_paths"),
            "protected_source_paths",
            allow_empty=True,
        )
    )
    for relative in protected:
        if not (root / relative).is_dir():
            raise GuidanceError(
                f"protected source directory does not exist: {relative}"
            )

    projections = manifest.get("projections")
    retirements = manifest.get("retirements")
    releases = manifest.get("releases")
    consumers = manifest.get("shared_consumers")
    if not isinstance(projections, list) or not projections:
        raise GuidanceError("projections must be a non-empty array")
    if not isinstance(retirements, list):
        raise GuidanceError("retirements must be an array")
    if not isinstance(releases, list):
        raise GuidanceError("releases must be an array")
    if not isinstance(consumers, list):
        raise GuidanceError("shared_consumers must be an array")

    ids: set[str] = set()
    targets: set[Path] = set()
    delivered_hosts: set[str] = set()
    projection_ids: set[str] = set()
    source_uses: dict[Path, int] = {}  # keyed by resolved source path
    independent_sources: dict[Path, str] = {}
    for index, projection in enumerate(projections):
        label = f"projections[{index}]"
        if not isinstance(projection, dict):
            raise GuidanceError(f"{label} must be an object")
        projection_id = projection.get("id")
        if not isinstance(projection_id, str) or not projection_id.strip():
            raise GuidanceError(f"{label}.id must be a non-empty string")
        if projection_id in ids:
            raise GuidanceError(f"duplicate operation id: {projection_id}")
        ids.add(projection_id)
        projection_ids.add(projection_id)
        hosts = set(_string_list(projection.get("hosts"), f"{label}.hosts"))
        unknown_hosts = hosts - required_hosts
        if unknown_hosts:
            raise GuidanceError(
                f"{label}.hosts contains unknown hosts: {sorted(unknown_hosts)}"
            )
        delivered_hosts.update(hosts)
        _hashes(projection.get("adopt_sha256"), f"{label}.adopt_sha256")

        is_file = "source" in projection or "target" in projection
        is_tree = (
            "source_tree" in projection
            or "target_tree" in projection
            or "include" in projection
        )
        if is_file == is_tree:
            raise GuidanceError(
                f"{label} must declare either a file projection or a tree projection"
            )
        independent = projection.get("independent", False)
        if not isinstance(independent, bool):
            raise GuidanceError(f"{label}.independent must be a boolean")
        if "sync_group" in projection:
            group = projection["sync_group"]
            if not isinstance(group, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", group):
                raise GuidanceError(f"{label}.sync_group must be a lowercase name")
            if independent:
                raise GuidanceError(f"{label}: sync_group and independent are exclusive")
        if is_tree and (
            "host_owned_keys" in projection or "managed_keys" in projection
        ):
            raise GuidanceError(
                f"{label}: config key ownership applies only to file projections"
            )
        sources: list[Path] = []
        if is_file:
            source = _source_path(
                projection.get("source"), f"{label}.source", may_climb=may_climb
            )
            target = _relative_path(projection.get("target"), f"{label}.target")
            _validate_source(root, repository, source, protected, label)
            _add_unique_target(targets, target, label)
            sources.append(source)
            if "host_owned_keys" in projection:
                if not independent:
                    raise GuidanceError(
                        f"{label}.host_owned_keys requires independent: true"
                    )
                host_owned = _key_paths(
                    projection["host_owned_keys"], f"{label}.host_owned_keys"
                )
                if source.suffix not in SEMANTIC_PARSERS:
                    raise GuidanceError(
                        f"{label}.host_owned_keys needs a {sorted(SEMANTIC_PARSERS)} source: {source}"
                    )
                _reject_overlapping(host_owned, f"{label}.host_owned_keys")
                try:
                    source_data = SEMANTIC_PARSERS[source.suffix](
                        (root / source).read_text(encoding="utf-8")
                    )
                    _, carried = config_view(
                        (root / source).read_bytes(),
                        host_owned,
                        file_format="json" if source.suffix == ".json" else "toml",
                    )
                except ValueError as exc:
                    raise GuidanceError(
                        f"{label} source does not parse as {source.suffix}: {exc}"
                    ) from exc
                # Comparison drops parents a host-owned key leaves empty, so an
                # empty one in canonical could never be told from the host's.
                empty_parents = [
                    ".".join(path[:depth])
                    for path in host_owned
                    for depth in range(1, len(path))
                    if _lookup(source_data, path[:depth]) == {}
                ]
                if empty_parents:
                    raise GuidanceError(
                        f"{label} source has empty parents of host-owned keys: {empty_parents}"
                    )
                # Host-written values stay on each machine; canonical never holds them.
                present = [
                    ".".join(path)
                    for path, value in zip(host_owned, carried, strict=True)
                    if value is not ABSENT
                ]
                if present:
                    raise GuidanceError(
                        f"{label} source carries host-owned keys: {present}"
                    )
            if "managed_keys" in projection:
                if not independent:
                    raise GuidanceError(
                        f"{label}.managed_keys requires independent: true"
                    )
                if "host_owned_keys" in projection:
                    raise GuidanceError(
                        f"{label}: managed_keys and host_owned_keys are exclusive"
                    )
                paths = _key_paths(projection["managed_keys"], f"{label}.managed_keys")
                if not paths or source.suffix not in SEMANTIC_PARSERS:
                    raise GuidanceError(
                        f"{label}.managed_keys needs non-empty paths and a JSON or TOML source"
                    )
                _reject_overlapping(paths, f"{label}.managed_keys")
                try:
                    unmanaged, _ = config_view(
                        (root / source).read_bytes(),
                        paths,
                        file_format="json" if source.suffix == ".json" else "toml",
                    )
                except ValueError as exc:
                    raise GuidanceError(
                        f"{label} source does not parse as managed config: {exc}"
                    ) from exc
                if unmanaged:
                    raise GuidanceError(
                        f"{label} source contains unmanaged keys: {sorted(unmanaged)}"
                    )
        else:
            source_tree = _source_path(
                projection.get("source_tree"), f"{label}.source_tree", may_climb=may_climb
            )
            target_tree = _relative_path(
                projection.get("target_tree"), f"{label}.target_tree"
            )
            patterns = _string_list(projection.get("include"), f"{label}.include")
            source_root = root / source_tree
            if not source_root.is_dir() or source_root.is_symlink():
                raise GuidanceError(
                    f"{label}.source_tree is not a regular directory: {source_tree}"
                )
            matches: set[Path] = set()
            for pattern in patterns:
                pattern_path = _relative_path(pattern, f"{label}.include entry")
                for path in source_root.glob(str(pattern_path)):
                    if path.is_file() and not path.is_symlink():
                        matches.add(path.relative_to(source_root))
            if not matches:
                raise GuidanceError(f"{label}.include matched no regular files")
            for relative in matches:
                source = source_tree / relative
                target = target_tree / relative
                _validate_source(root, repository, source, protected, label)
                _add_unique_target(targets, target, label)
                sources.append(source)
        for source in sources:
            # Two spellings of one file (`a` and `../source/a`) are one source.
            identity = (root / source).resolve()
            source_uses[identity] = source_uses.get(identity, 0) + 1
            if independent or "sync_group" in projection:
                independent_sources[identity] = projection_id

    for index, retirement in enumerate(retirements):
        label = f"retirements[{index}]"
        if not isinstance(retirement, dict):
            raise GuidanceError(f"{label} must be an object")
        operation_id = retirement.get("id")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise GuidanceError(f"{label}.id must be a non-empty string")
        if operation_id in ids:
            raise GuidanceError(f"duplicate operation id: {operation_id}")
        ids.add(operation_id)
        target = _relative_path(retirement.get("target"), f"{label}.target")
        _add_unique_target(targets, target, label)
        hosts = set(_string_list(retirement.get("hosts"), f"{label}.hosts"))
        if hosts - required_hosts:
            raise GuidanceError(
                f"{label}.hosts contains unknown hosts: {sorted(hosts - required_hosts)}"
            )
        _hashes(retirement.get("adopt_sha256"), f"{label}.adopt_sha256")
        if (
            not isinstance(retirement.get("reason"), str)
            or not retirement["reason"].strip()
        ):
            raise GuidanceError(f"{label}.reason must be a non-empty string")

    for source, projection_id in independent_sources.items():
        if source_uses[source] > 1:
            raise GuidanceError(
                f"projection {projection_id} has its own sync group but shares its source {source} "
                "with another projection"
            )

    for index, release in enumerate(releases):
        label = f"releases[{index}]"
        if not isinstance(release, dict):
            raise GuidanceError(f"{label} must be an object")
        _add_unique_target(
            targets, _relative_path(release.get("target"), f"{label}.target"), label
        )
        if not isinstance(release.get("reason"), str) or not release["reason"].strip():
            raise GuidanceError(f"{label}.reason must be a non-empty string")

    consumer_hosts: set[str] = set()
    for index, consumer in enumerate(consumers):
        label = f"shared_consumers[{index}]"
        if not isinstance(consumer, dict):
            raise GuidanceError(f"{label} must be an object")
        host = consumer.get("host")
        projection = consumer.get("projection")
        mechanism = consumer.get("mechanism")
        if host not in required_hosts:
            raise GuidanceError(f"{label}.host is unknown: {host!r}")
        if host in consumer_hosts:
            raise GuidanceError(f"shared consumer is duplicated: {host}")
        if projection not in projection_ids:
            raise GuidanceError(f"{label}.projection is unknown: {projection!r}")
        # A machine that enables only this host must still receive what it reads.
        if not any(
            item.get("id") == projection and host in item["hosts"] for item in projections
        ):
            raise GuidanceError(
                f"{label}: {host} reads {projection}, so that projection must list {host} in hosts"
            )
        if not isinstance(mechanism, str) or not mechanism.strip():
            raise GuidanceError(f"{label}.mechanism must be a non-empty string")
        verification = consumer.get("verification")
        if not isinstance(verification, dict):
            raise GuidanceError(f"{label}.verification must be an object")
        _string_list(verification.get("command"), f"{label}.verification.command")
        required_patterns = _string_list(
            verification.get("stdout_regex"),
            f"{label}.verification.stdout_regex",
            allow_empty=True,
        )
        forbidden_patterns = _string_list(
            verification.get("stdout_not_regex"),
            f"{label}.verification.stdout_not_regex",
            allow_empty=True,
        )
        for pattern in required_patterns + forbidden_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise GuidanceError(
                    f"{label} has invalid verification regex {pattern!r}: {exc}"
                ) from exc
        consumer_hosts.add(host)

    missing_hosts = required_hosts - delivered_hosts - consumer_hosts
    extra_hosts = (delivered_hosts | consumer_hosts) - required_hosts
    if missing_hosts or extra_hosts:
        raise GuidanceError(
            f"host delivery coverage mismatch; missing={sorted(missing_hosts)}, extra={sorted(extra_hosts)}"
        )


def _validate_source(
    root: Path,
    repository: Path,
    source: Path,
    protected: tuple[Path, ...],
    label: str,
) -> None:
    path = root / source
    resolved = path.resolve()
    # Resolved, so a `..` source cannot reach a protected directory sideways.
    if any(resolved.is_relative_to((root / item).resolve()) for item in protected):
        raise GuidanceError(f"{label} reads protected source path: {source}")
    if not path.is_file() or path.is_symlink():
        raise GuidanceError(f"{label} source is not a regular file: {source}")
    if not resolved.is_relative_to(repository):
        raise GuidanceError(f"{label} source escapes the repository root: {source}")


def _key_paths(raw: object, label: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw, list):
        raise GuidanceError(f"{label} must be an array of key paths")
    return tuple(
        tuple(_string_list(path, f"{label}[{index}]")) for index, path in enumerate(raw)
    )


def _reject_overlapping(paths: tuple[tuple[str, ...], ...], label: str) -> None:
    for index, path in enumerate(paths):
        if any(
            path[: len(other)] == other or other[: len(path)] == path
            for other in paths[:index]
        ):
            raise GuidanceError(f"{label} contains overlapping paths")


def _lookup(data: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _add_unique_target(targets: set[Path], target: Path, label: str) -> None:
    if target in targets:
        raise GuidanceError(f"{label} reuses target path: {target}")
    targets.add(target)


def render_home(data: bytes, home: Path) -> bytes:
    if HOME_TOKEN not in data:
        return data
    if not _PLAIN_HOME.fullmatch(str(home)):
        raise GuidanceError(
            f"cannot render {HOME_TOKEN.decode()} as {home}: "
            "a home path here may hold only letters, digits and . _ - /"
        )
    return data.replace(HOME_TOKEN, str(home).encode())


def tokenize_home(data: bytes, home: Path) -> bytes:
    """Replace the home path with the token where it starts and ends a path segment."""
    if home == Path("/"):
        return data
    pattern = rb"(?<![A-Za-z0-9._/-])" + re.escape(str(home).encode()) + rb"(?![A-Za-z0-9._-])"
    return re.sub(pattern, HOME_TOKEN, data)


def expand_operations(
    root: Path, manifest: dict[str, Any], home: Path
) -> tuple[Operation, ...]:
    operations: list[Operation] = []
    for projection in manifest["projections"]:
        hosts = tuple(projection["hosts"])
        hashes = _hashes(
            projection.get("adopt_sha256"), f"{projection['id']}.adopt_sha256"
        )
        # An independent tree is one group, so its files apply together or not at all.
        if "sync_group" in projection:
            sync_group = f"group:{projection['sync_group']}"
        elif projection.get("independent", False):
            sync_group = f"independent:{projection['id']}"
        else:
            sync_group = SHARED_SYNC_GROUP
        if "source" in projection:
            source = Path(projection["source"])
            host_owned = projection.get("host_owned_keys")
            managed = projection.get("managed_keys")
            operations.append(
                Operation(
                    operation_id=projection["id"],
                    kind="write",
                    source_relative=source,
                    target_relative=Path(projection["target"]),
                    desired=render_home((root / source).read_bytes(), home),
                    executable=_is_executable(root / source),
                    adopt_sha256=hashes,
                    hosts=hosts,
                    sync_group=sync_group,
                    host_owned_keys=(
                        None
                        if host_owned is None
                        else _key_paths(
                            host_owned, f"{projection['id']}.host_owned_keys"
                        )
                    ),
                    managed_keys=(
                        None
                        if managed is None
                        else _key_paths(managed, f"{projection['id']}.managed_keys")
                    ),
                )
            )
            continue

        source_tree = Path(projection["source_tree"])
        target_tree = Path(projection["target_tree"])
        source_root = root / source_tree
        matches: set[Path] = set()
        for pattern in projection["include"]:
            for path in source_root.glob(pattern):
                if path.is_file() and not path.is_symlink():
                    matches.add(path.relative_to(source_root))
        for relative in sorted(matches):
            source = source_tree / relative
            operations.append(
                Operation(
                    operation_id=f"{projection['id']}:{relative.as_posix()}",
                    kind="write",
                    source_relative=source,
                    target_relative=target_tree / relative,
                    desired=render_home((root / source).read_bytes(), home),
                    executable=_is_executable(root / source),
                    adopt_sha256=hashes,
                    hosts=hosts,
                    sync_group=sync_group,
                )
            )

    for retirement in manifest["retirements"]:
        operations.append(
            Operation(
                operation_id=retirement["id"],
                kind="retire",
                target_relative=Path(retirement["target"]),
                hosts=tuple(retirement["hosts"]),
                adopt_sha256=_hashes(
                    retirement.get("adopt_sha256"),
                    f"{retirement['id']}.adopt_sha256",
                ),
                reason=retirement["reason"],
            )
        )
    return tuple(operations)


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IXUSR)


def _with_execute_bits(mode: int) -> int:
    """Add an execute bit wherever `mode` has a read bit; never remove one."""
    return mode | (mode & 0o444) >> 2


def _empty_state(manager_id: str) -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "manager_id": manager_id,
        "targets": {},
    }


def load_state(state_dir: Path, manager_id: str) -> dict[str, Any]:
    path = state_dir / "state.json"
    if not path.exists():
        return _empty_state(manager_id)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuidanceError(f"cannot read managed state {path}: {exc}") from exc
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise GuidanceError(f"unsupported managed state schema in {path}")
    if state.get("manager_id") != manager_id:
        raise GuidanceError(f"managed state belongs to another manager: {path}")
    if not isinstance(state.get("targets"), dict):
        raise GuidanceError(f"managed state has invalid targets: {path}")
    return state


def load_enabled_hosts(home: Path, manifest: dict[str, Any]) -> frozenset[str]:
    """Hosts this machine enables: the machine file's list, or every known host."""
    known = frozenset(manifest["required_hosts"])
    path = home / MACHINE_FILE
    if not path.exists():
        return known
    try:
        machine = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuidanceError(f"cannot read machine file {path}: {exc}") from exc
    if not isinstance(machine, dict) or machine.get("schema_version") != 1:
        raise GuidanceError(f"machine file needs schema_version 1: {path}")
    hosts = _string_list(machine.get("hosts"), f"{path} hosts", allow_empty=True)
    # Names other managers own (for example mimo) are not guidance hosts.
    return known & frozenset(hosts)


def plan_sync(root: Path, home: Path, *, replace_unowned: bool = False) -> SyncPlan:
    root = root.resolve()
    home = home.expanduser().resolve()
    manifest = load_host_manifest(root)
    state_relative = Path(manifest["state_dir"])
    state_issue = _parent_path_issue(home, state_relative / "state.json")
    if state_issue:
        raise GuidanceError(f"unsafe managed state path: {state_issue}")
    state_dir = home / state_relative
    state = load_state(state_dir, manifest["manager_id"])
    operations = expand_operations(root, manifest, home)
    operation_targets = {
        operation.target_relative.as_posix() for operation in operations
    }
    released_targets = {release["target"] for release in manifest["releases"]}
    orphaned_targets = set(state["targets"]) - operation_targets - released_targets
    if orphaned_targets:
        raise GuidanceError(
            "managed state contains targets absent from hosts.json; add explicit retirements: "
            + ", ".join(sorted(orphaned_targets))
        )
    enabled = load_enabled_hosts(home, manifest)
    statuses = tuple(
        _classify(operation, home, state, state_dir, replace_unowned=replace_unowned)
        if enabled.intersection(operation.hosts)
        else OperationStatus(operation, "disabled")
        for operation in operations
    )
    fingerprint_rows = [
        f"{operation.operation_id}\0{operation.kind}\0{operation.target_relative.as_posix()}\0"
        f"{operation.desired_sha256 or '-'}"
        for operation in operations
    ]
    fingerprint = sha256_bytes("\n".join(fingerprint_rows).encode("utf-8"))
    return SyncPlan(
        root,
        home,
        state_dir,
        manifest,
        state,
        statuses,
        fingerprint,
        enabled,
        replace_unowned,
    )


def _classify(
    operation: Operation,
    home: Path,
    state: dict[str, Any],
    state_dir: Path,
    *,
    replace_unowned: bool = False,
) -> OperationStatus:
    target = home / operation.target_relative
    parent_issue = _parent_path_issue(home, operation.target_relative)
    if parent_issue:
        return OperationStatus(operation, "conflict", detail=parent_issue)
    key = operation.target_relative.as_posix()
    record = state["targets"].get(key, {})
    if not os.path.lexists(target):
        state_name = "missing" if operation.kind == "write" else "retired"
        return OperationStatus(operation, state_name)
    if target.is_symlink() or not target.is_file():
        return OperationStatus(
            operation, "conflict", detail="target is not a regular file"
        )

    current = sha256_file(target)
    if operation.kind == "retire":
        if record.get("kind") == "retire" and record.get("retired") is True:
            return OperationStatus(
                operation,
                "conflict",
                current,
                "previously retired target reappeared",
            )
        if current in operation.adopt_sha256:
            return OperationStatus(operation, "retirement-needed", current)
        return OperationStatus(
            operation,
            "conflict",
            current,
            "retirement target does not match an approved legacy hash",
        )

    replace = replace_unowned and not record
    if operation.managed_keys is not None:
        return _classify_managed_config(
            operation, target, current, record, state_dir, replace=replace
        )
    if operation.host_owned_keys is not None:
        return _classify_host_owned(
            operation, target, current, record, state_dir, replace=replace
        )
    desired = operation.desired_sha256
    if current == desired:
        mode = stat.S_IMODE(target.stat().st_mode)
        if operation.executable and _with_execute_bits(mode) != mode:
            return OperationStatus(
                operation, "managed-stale", current, "needs its execute bit"
            )
        return OperationStatus(operation, "current", current)
    if current in operation.adopt_sha256:
        return OperationStatus(operation, "legacy", current)
    if record.get("kind") == "write" and record.get("installed_sha256") == current:
        return OperationStatus(operation, "managed-stale", current)
    if replace:
        return OperationStatus(operation, "replace-unowned", current, UNOWNED_BACKUP)
    detail = "managed target has local drift" if record else UNOWNED_CONFLICT
    return OperationStatus(operation, "conflict", current, detail)


def _classify_managed_config(
    operation: Operation,
    target: Path,
    current: str,
    record: dict[str, Any],
    state_dir: Path,
    *,
    replace: bool,
) -> OperationStatus:
    assert operation.desired is not None
    assert operation.managed_keys is not None
    live = target.read_bytes()
    if sha256_bytes(live) != current:
        return OperationStatus(
            operation, "conflict", detail="target changed during inspection"
        )
    try:
        _, actual = config_view(
            live, operation.managed_keys, file_format=operation.config_format
        )
        _, desired = config_view(
            operation.desired,
            operation.managed_keys,
            file_format=operation.config_format,
        )
    except ValueError as exc:
        return OperationStatus(
            operation, "conflict", current, f"unparseable managed config: {exc}"
        )
    if actual == desired:
        return OperationStatus(operation, "current", current)
    installed = _load_installed_copy(state_dir, record.get("installed_sha256"))
    if not record and (replace or all(value is ABSENT for value in actual)):
        merged = merge_config(
            live,
            operation.desired,
            operation.managed_keys,
            file_format=operation.config_format,
        )
        if any(value is not ABSENT for value in actual):
            return OperationStatus(
                operation, "replace-unowned", current, UNOWNED_BACKUP, merged
            )
        return OperationStatus(
            operation, "managed-stale", current, merged_target=merged
        )
    if installed is not None:
        try:
            _, previous = config_view(
                installed, operation.managed_keys, file_format=operation.config_format
            )
            if actual == previous:
                merged = merge_config(
                    live,
                    operation.desired,
                    operation.managed_keys,
                    file_format=operation.config_format,
                )
                return OperationStatus(
                    operation, "managed-stale", current, merged_target=merged
                )
        except ValueError as exc:
            return OperationStatus(operation, "conflict", current, str(exc))
    changed = [
        ".".join(path)
        for path, actual_value, desired_value in zip(
            operation.managed_keys, actual, desired, strict=True
        )
        if actual_value != desired_value
    ]
    prefix = (
        "managed settings have local drift: "
        if record
        else UNOWNED_CONFLICT + "; its managed settings differ: "
    )
    return OperationStatus(operation, "conflict", current, prefix + ", ".join(changed))


def _classify_host_owned(
    operation: Operation,
    target: Path,
    current: str,
    record: dict[str, Any],
    state_dir: Path,
    *,
    replace: bool,
) -> OperationStatus:
    """Compare everything except host-owned keys; sync keeps the host's values.

    Formatting is ignored too, so a host that rewrites its own file without
    touching a canonical key stays current and is never written.
    """
    assert operation.desired is not None
    assert operation.host_owned_keys is not None
    keys = operation.host_owned_keys
    file_format = operation.config_format
    live = target.read_bytes()
    if sha256_bytes(live) != current:
        return OperationStatus(
            operation, "conflict", detail="target changed during inspection"
        )
    if current == operation.desired_sha256:
        return OperationStatus(operation, "current", current)
    try:
        live_view: Any = config_view(live, keys, file_format=file_format)[0]
        parse_error = ""
    except ValueError as exc:
        live_view, parse_error = None, str(exc)
    desired_view, _ = config_view(operation.desired, keys, file_format=file_format)
    if live_view is not None and live_view == desired_view:
        return OperationStatus(operation, "current", current)

    # Exact hashes prove which earlier content this is, even when it does not parse.
    if current in operation.adopt_sha256:
        state = "legacy"
    elif record.get("installed_sha256") == current:
        state = "managed-stale"
    elif not record and live_view is not None and not live_view:
        # A host's first-run file holding only its own keys: nothing to lose.
        state = "managed-stale"
    elif replace and live_view is not None:
        # Unreadable content would lose the host's values, so it stays a conflict.
        state = "replace-unowned"
    elif live_view is None:
        return OperationStatus(
            operation, "conflict", current, f"host wrote unparseable content: {parse_error}"
        )
    else:
        installed = _load_installed_copy(state_dir, record.get("installed_sha256"))
        try:
            installed_view = (
                None
                if installed is None
                else config_view(installed, keys, file_format=file_format)[0]
            )
        except ValueError:
            installed_view = None
        if installed_view is None or installed_view != live_view:
            detail = (
                "managed target has local drift"
                if record
                else UNOWNED_CONFLICT
            )
            return OperationStatus(operation, "conflict", current, detail)
        state = "managed-stale"
    detail = UNOWNED_BACKUP if state == "replace-unowned" else ""
    if live_view is None:
        # Nothing parseable to keep, so the canonical bytes go in as they are.
        return OperationStatus(operation, state, current, detail)
    try:
        merged = merge_config(operation.desired, live, keys, file_format=file_format)
    except ValueError as exc:
        return OperationStatus(
            operation, "conflict", current, f"cannot keep host-owned values: {exc}"
        )
    return OperationStatus(
        operation,
        state,
        current,
        detail or "keeps host-owned values",
        merged_target=merged,
    )

def _parent_path_issue(home: Path, relative: Path) -> str:
    current = home
    for part in relative.parts[:-1]:
        current /= part
        if not os.path.lexists(current):
            break
        if current.is_symlink():
            return f"parent path is a symlink: {current}"
        if not current.is_dir():
            return f"parent path is not a directory: {current}"
    return ""


def format_plan(plan: SyncPlan) -> str:
    lines: list[str] = []
    for status in plan.statuses:
        operation = status.operation
        host_label = ",".join(operation.hosts)
        suffix = f" ({status.detail})" if status.detail else ""
        lines.append(
            f"{status.state:18} {host_label:20} ~/{operation.target_relative.as_posix()}{suffix}"
        )
    for release in plan.manifest["releases"]:
        if release["target"] in plan.state["targets"]:
            lines.append(
                f"{'released':18} {'-':20} ~/{release['target']} ({release['reason']})"
            )
    for consumer in plan.manifest["shared_consumers"]:
        label = "shared" if consumer["host"] in plan.enabled_hosts else "disabled"
        lines.append(
            f"{label:18} {consumer['host']:20} via {consumer['projection']}: "
            f"{consumer['mechanism']}"
        )
    return "\n".join(lines)


def summarize_plan(plan: SyncPlan) -> str | None:
    """One line naming what needs attention, or None when every target is current."""
    conflicts = [status.operation.operation_id for status in plan.conflicts]
    pending = [status.operation.operation_id for status in plan.changes]
    if not conflicts and not pending:
        return None
    parts = []
    if conflicts:
        parts.append(f"{len(conflicts)} conflict(s): {', '.join(conflicts)}")
    if pending:
        parts.append(f"{len(pending)} pending: {', '.join(pending)}")
    return f"guidance: {'; '.join(parts)} -- cd {plan.root} && ./guidance status"




def plan_adoptions(plan: SyncPlan) -> tuple[OperationStatus, ...]:
    """Statuses whose host file can be pulled back into its canonical source.

    Only a `conflict` holds content this manager did not write. `legacy` is
    excluded because sync is meant to overwrite it, and `managed-stale`
    because its target still matches what sync installed apart from
    host-owned values, so adopting it would overwrite a pending canonical
    edit with the previous generation of that same file.
    """
    return tuple(
        status
        for status in plan.statuses
        if status.operation.kind == "write"
        and status.operation.source_relative is not None
        and status.state == "conflict"
        and status.current_sha256 is not None
    )


def adopt(
    root: Path,
    home: Path,
    *,
    operation_ids: frozenset[str] | None = None,
    dry_run: bool = False,
) -> tuple[Adoption, ...]:
    root = root.resolve()
    home = home.expanduser().resolve()
    plan = plan_sync(root, home)
    return _adopt_statuses(
        plan, plan_adoptions(plan), operation_ids=operation_ids, dry_run=dry_run
    )


def _adopt_statuses(
    plan: SyncPlan,
    candidates: tuple[OperationStatus, ...],
    *,
    operation_ids: frozenset[str] | None = None,
    dry_run: bool,
) -> tuple[Adoption, ...]:
    if operation_ids is not None:
        known = {status.operation.operation_id for status in plan.statuses}
        unknown = operation_ids - known
        if unknown:
            raise GuidanceError(f"unknown operation ids: {sorted(unknown)}")
        candidates = tuple(
            status
            for status in candidates
            if status.operation.operation_id in operation_ids
        )

    adoptions: list[Adoption] = []
    for status in candidates:
        operation = status.operation
        assert operation.source_relative is not None
        assert operation.desired is not None
        target = plan.home / operation.target_relative
        data = target.read_bytes()
        if sha256_bytes(data) != status.current_sha256:
            raise GuidanceError(f"target changed while adopting: {target}")
        source = plan.root / operation.source_relative
        installed = _load_installed_copy(
            plan.state_dir,
            plan.state["targets"]
            .get(operation.target_relative.as_posix(), {})
            .get("installed_sha256"),
        )
        adopted = data
        evidence_live = data
        evidence_canonical = operation.desired
        if operation.host_owned_keys:
            try:
                empty = b"{}" if operation.config_format == "json" else b""
                adopted = merge_config(
                    data,
                    empty,
                    operation.host_owned_keys,
                    file_format=operation.config_format,
                )
            except ValueError as exc:
                raise GuidanceError(f"cannot adopt {target}: {exc}") from exc
            evidence_live = adopted
            # Copies from before a key became host-owned still hold it, and the
            # stripped copies are re-serialized; compare like with like.
            evidence_canonical = merge_config(
                operation.desired,
                empty,
                operation.host_owned_keys,
                file_format=operation.config_format,
            )
            if installed is not None:
                try:
                    installed = merge_config(
                        installed,
                        empty,
                        operation.host_owned_keys,
                        file_format=operation.config_format,
                    )
                except ValueError:
                    installed = None
        if operation.managed_keys is not None:
            try:
                adopted = merge_config(
                    operation.desired,
                    data,
                    operation.managed_keys,
                    file_format=operation.config_format,
                )
                evidence_live = select_config(
                    data, operation.managed_keys, file_format=operation.config_format
                )
                if installed is not None:
                    installed = select_config(
                        installed,
                        operation.managed_keys,
                        file_format=operation.config_format,
                    )
            except ValueError as exc:
                raise GuidanceError(
                    f"cannot adopt managed config {target}: {exc}"
                ) from exc
        if not dry_run:
            _atomic_write(
                source,
                tokenize_home(adopted, plan.home),
                stat.S_IMODE(source.stat().st_mode),
            )
        adoptions.append(
            Adoption(
                operation_id=operation.operation_id,
                source_relative=operation.source_relative,
                target_relative=operation.target_relative,
                source_sha256=operation.desired_sha256 or "",
                target_sha256=sha256_bytes(data),
                evidence=_drift_evidence(
                    installed,
                    evidence_canonical,
                    evidence_live,
                ),
            )
        )
    return tuple(adoptions)


def _drift_evidence(installed: bytes | None, canonical: bytes, live: bytes) -> str:
    """Show what the host changed and what canonical changed, from the last sync."""
    if installed is None:
        return "no installed copy recorded; canonical -> live:\n" + _redacted_diff(
            canonical, live, "canonical", "live"
        )
    evidence = "host changed it since the last sync:\n" + _redacted_diff(
        installed, live, "installed", "live"
    )
    if installed != canonical:
        evidence += "\ncanonical also changed since the last sync:\n" + _redacted_diff(
            installed, canonical, "installed", "canonical"
        )
    return evidence


def _redacted_diff(
    before: bytes, after: bytes, before_name: str, after_name: str
) -> str:
    lines = []
    for line in difflib.unified_diff(
        before.decode("utf-8", errors="replace").splitlines(keepends=True),
        after.decode("utf-8", errors="replace").splitlines(keepends=True),
        before_name,
        after_name,
        n=1,
    ):
        match = _SECRET_ASSIGNMENT.search(line)
        if match and not line.startswith(("---", "+++")):
            line = line[: match.end()] + " <redacted>\n"
        lines.append(line if line.endswith("\n") else line + "\n")
    return "".join(lines) or "(no textual difference)\n"


def _installed_copy_path(state_dir: Path, sha256: str) -> Path:
    return state_dir / "installed" / sha256


def _load_installed_copy(state_dir: Path, sha256: object) -> bytes | None:
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        return None
    path = _installed_copy_path(state_dir, sha256)
    if not path.is_file():
        return None
    data = path.read_bytes()
    return data if sha256_bytes(data) == sha256 else None


def verify_shared_consumers(
    root: Path, home: Path, *, timeout_seconds: float = 20.0
) -> tuple[ConsumerVerification, ...]:
    manifest = load_host_manifest(root.resolve())
    home = home.expanduser().resolve()
    enabled = load_enabled_hosts(home, manifest)
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    results: list[ConsumerVerification] = []
    for consumer in manifest["shared_consumers"]:
        if consumer["host"] not in enabled:
            continue
        verification = consumer["verification"]
        command = verification["command"]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=environment,
                check=False,
            )
        except FileNotFoundError:
            results.append(
                ConsumerVerification(
                    consumer["host"], False, f"command not found: {command[0]}"
                )
            )
            continue
        except subprocess.TimeoutExpired:
            results.append(
                ConsumerVerification(
                    consumer["host"],
                    False,
                    f"verification timed out after {timeout_seconds:g}s",
                )
            )
            continue
        except OSError as exc:
            results.append(
                ConsumerVerification(
                    consumer["host"],
                    False,
                    f"verification command failed: {exc}",
                )
            )
            continue

        output = completed.stdout + "\n" + completed.stderr
        missing = [
            pattern
            for pattern in verification["stdout_regex"]
            if re.search(pattern, output) is None
        ]
        forbidden = [
            pattern
            for pattern in verification["stdout_not_regex"]
            if re.search(pattern, output) is not None
        ]
        if completed.returncode != 0:
            detail = f"command exited {completed.returncode}"
            results.append(ConsumerVerification(consumer["host"], False, detail))
        elif missing:
            results.append(
                ConsumerVerification(
                    consumer["host"],
                    False,
                    "required discovery evidence was absent",
                )
            )
        elif forbidden:
            results.append(
                ConsumerVerification(
                    consumer["host"],
                    False,
                    "a retired duplicate is still being discovered",
                )
            )
        else:
            results.append(
                ConsumerVerification(consumer["host"], True, consumer["mechanism"])
            )
    return tuple(results)


@contextlib.contextmanager
def _exclusive_lock(state_dir: Path) -> Iterator[None]:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "sync.lock"
    with path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GuidanceError(f"another guidance sync is active: {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def sync(
    root: Path, home: Path, *, dry_run: bool = False, replace_unowned: bool = False
) -> SyncResult:
    """Apply every sync group free of conflicts; never writes canonical sources.

    A conflict blocks only its own group; the returned plan still lists it, so
    callers decide how to report the partial result.
    """
    root = root.resolve()
    home = home.expanduser().resolve()
    manifest = load_host_manifest(root)
    state_dir = home / Path(manifest["state_dir"])
    # Built before any write, so a malformed manifest or registry stops sync cleanly.
    guard_index = (
        _edit_guard_index(
            root / manifest["edit_guard"], root, home, load_enabled_hosts(home, manifest)
        )
        if "edit_guard" in manifest
        else None
    )
    if dry_run:
        return SyncResult(plan_sync(root, home, replace_unowned=replace_unowned), None)
    with _exclusive_lock(state_dir):
        transaction_id = _apply_plan(
            plan_sync(root, home, replace_unowned=replace_unowned)
        )
        if guard_index is not None:
            path, payload = guard_index
            if not (path.is_file() and path.read_bytes() == payload):
                _atomic_write(path, payload, 0o644)
    return SyncResult(
        plan_sync(root, home, replace_unowned=replace_unowned), transaction_id
    )


def _edit_guard_index(
    guard_path: Path, root: Path, home: Path, enabled_hosts: frozenset[str]
) -> tuple[Path, bytes]:
    """Where the installed edit guard reads its rules, and their bytes; never the checkout."""
    spec = importlib.util.spec_from_file_location("projection_edit_guard", guard_path)
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    try:
        index = guard.build_index(root, home, enabled_hosts)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GuidanceError(f"cannot build the edit-guard index: {exc}") from exc
    payload = (json.dumps(index, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return home / guard.INDEX, payload


def _apply_plan(plan: SyncPlan) -> str | None:
    applied = plan.applicable
    releasing = any(
        release["target"] in plan.state["targets"] for release in plan.manifest["releases"]
    )
    if not applied and not releasing:
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    transaction_id = f"{timestamp}-{os.getpid()}"
    transaction_dir = plan.state_dir / "backups" / transaction_id
    state_path = plan.state_dir / "state.json"
    previous_state_exists = state_path.exists()
    previous_state_bytes = state_path.read_bytes() if previous_state_exists else b""
    changed_statuses = [status for status in applied if status.needs_change]
    entries: list[dict[str, Any]] = []

    if changed_statuses:
        # Backups hold copies of files that may have been private where they were.
        backups = transaction_dir.parent
        backups.mkdir(parents=True, exist_ok=True)
        backups.chmod(0o700)
        transaction_dir.mkdir(mode=0o700, exist_ok=False)
        if previous_state_exists:
            _atomic_write(
                transaction_dir / "state.before.json", previous_state_bytes, 0o600
            )

    try:
        for status in changed_statuses:
            operation = status.operation
            target = plan.home / operation.target_relative
            current_status = _classify(
                operation,
                plan.home,
                plan.state,
                plan.state_dir,
                replace_unowned=plan.replace_unowned,
            )
            if (
                current_status.state != status.state
                or current_status.current_sha256 != status.current_sha256
            ):
                raise GuidanceError(
                    f"target changed after preflight: {target} "
                    f"({status.state} -> {current_status.state})"
                )
            entry = _capture_preimage(
                operation, target, plan.state_dir, transaction_dir
            )
            entries.append(entry)
            if operation.kind == "write":
                mode = entry["before"].get("mode", 0o644)
                if operation.executable:
                    mode = _with_execute_bits(mode)
                data = (
                    operation.desired
                    if status.merged_target is None
                    else status.merged_target
                )
                assert data is not None
                _atomic_write(target, data, mode)
                entry["after"] = {"kind": "file", "sha256": sha256_bytes(data)}
            else:
                target.unlink()
                entry["after"] = {"kind": "absent"}

        postconditions = tuple(
            _classify(status.operation, plan.home, plan.state, plan.state_dir)
            for status in applied
        )
        failed_postconditions = [
            status
            for status in postconditions
            if status.state not in {"current", "retired"}
        ]
        if failed_postconditions:
            targets = ", ".join(
                str(plan.home / status.operation.target_relative)
                for status in failed_postconditions
            )
            raise GuidanceError(f"target changed while sync was applying: {targets}")

        # Content-addressed, so a rollback never leaves a copy describing the
        # wrong generation; adopt reads these to show what changed since sync.
        for status in applied:
            if status.operation.kind == "write":
                assert status.operation.desired is not None
                copy_path = _installed_copy_path(
                    plan.state_dir, sha256_bytes(status.operation.desired)
                )
                if not copy_path.exists():
                    _atomic_write(copy_path, status.operation.desired, 0o600)

        new_state = _updated_state(
            plan, applied, entries, transaction_id if entries else None
        )
        if entries:
            journal = {
                "schema_version": 1,
                "manager_id": plan.manifest["manager_id"],
                "transaction_id": transaction_id,
                "created_at": timestamp,
                "previous_state_exists": previous_state_exists,
                "entries": entries,
            }
            _atomic_write(
                transaction_dir / "transaction.json",
                (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                0o600,
            )
        _atomic_write(
            state_path,
            (json.dumps(new_state, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            0o600,
        )
    except BaseException as exc:  # Ctrl-C too: targets change before the journal exists
        rollback_error: Exception | None = None
        try:
            _restore_entries(plan.home, plan.state_dir, entries, verify_after=False)
            if previous_state_exists:
                _atomic_write(state_path, previous_state_bytes, 0o600)
            elif state_path.exists():
                state_path.unlink()
        except Exception as restore_exc:  # noqa: BLE001  # pragma: no cover
            rollback_error = restore_exc
        if rollback_error is not None:
            raise GuidanceError(
                f"sync failed ({exc!r}); automatic rollback also failed ({rollback_error})"
            ) from exc
        if not isinstance(exc, Exception):
            raise
        raise GuidanceError(f"sync failed and was rolled back: {exc}") from exc
    return transaction_id if entries else None


def _capture_preimage(
    operation: Operation,
    target: Path,
    state_dir: Path,
    transaction_dir: Path,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "operation_id": operation.operation_id,
        "target": operation.target_relative.as_posix(),
    }
    if target.is_symlink():
        raise GuidanceError(f"target became a symlink after preflight: {target}")
    if not target.exists():
        entry["before"] = {"kind": "absent"}
        return entry
    mode = stat.S_IMODE(target.stat().st_mode)
    backup = transaction_dir / "files" / operation.target_relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    entry["before"] = {
        "kind": "file",
        "backup": backup.relative_to(state_dir).as_posix(),
        "sha256": sha256_file(backup),
        "mode": mode,
    }
    return entry


def _updated_state(
    plan: SyncPlan,
    applied: tuple[OperationStatus, ...],
    entries: list[dict[str, Any]],
    transaction_id: str | None,
) -> dict[str, Any]:
    state = copy.deepcopy(plan.state)
    state["schema_version"] = STATE_SCHEMA_VERSION
    state["manager_id"] = plan.manifest["manager_id"]
    state["source_fingerprint"] = plan.source_fingerprint
    state["synced_at"] = datetime.now(UTC).isoformat()
    targets = state.setdefault("targets", {})
    backups_by_target = {
        entry["target"]: entry["before"].get("backup")
        for entry in entries
        if entry["before"].get("backup")
    }
    for release in plan.manifest["releases"]:
        targets.pop(release["target"], None)
    for status in applied:
        operation = status.operation
        key = operation.target_relative.as_posix()
        old_backups = list(targets.get(key, {}).get("backups", []))
        backup = backups_by_target.get(key)
        if backup:
            old_backups.append(backup)
        if operation.kind == "write":
            targets[key] = {
                "kind": "write",
                "operation_id": operation.operation_id,
                "installed_sha256": operation.desired_sha256,
                "backups": old_backups,
            }
        else:
            targets[key] = {
                "kind": "retire",
                "operation_id": operation.operation_id,
                "retired": True,
                "backups": old_backups,
            }
    if transaction_id is not None:
        state["last_transaction"] = transaction_id
    return state


def rollback(root: Path, home: Path) -> str:
    root = root.resolve()
    home = home.expanduser().resolve()
    manifest = load_host_manifest(root)
    state_dir = home / Path(manifest["state_dir"])
    with _exclusive_lock(state_dir):
        state = load_state(state_dir, manifest["manager_id"])
        transaction_id = state.get("last_transaction")
        if not isinstance(transaction_id, str) or not transaction_id:
            raise GuidanceError(
                "no file-changing guidance sync is available to roll back"
            )
        transaction_dir = state_dir / "backups" / transaction_id
        journal_path = transaction_dir / "transaction.json"
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GuidanceError(
                f"cannot read rollback journal {journal_path}: {exc}"
            ) from exc
        if journal.get("manager_id") != manifest["manager_id"]:
            raise GuidanceError(
                f"rollback journal belongs to another manager: {journal_path}"
            )
        entries = journal.get("entries")
        if not isinstance(entries, list) or not entries:
            raise GuidanceError(f"rollback journal has no entries: {journal_path}")

        _restore_entries(home, state_dir, entries, verify_after=True)
        state_path = state_dir / "state.json"
        if journal.get("previous_state_exists"):
            previous = transaction_dir / "state.before.json"
            _atomic_write(state_path, previous.read_bytes(), 0o600)
        else:
            state_path.unlink(missing_ok=True)
        journal["rolled_back_at"] = datetime.now(UTC).isoformat()
        _atomic_write(
            journal_path,
            (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            0o600,
        )
    return transaction_id


def _restore_entries(
    home: Path,
    state_dir: Path,
    entries: list[dict[str, Any]],
    *,
    verify_after: bool,
) -> None:
    if verify_after:
        for entry in entries:
            target_relative = _relative_path(entry.get("target"), "journal target")
            target = home / target_relative
            after = entry.get("after", {})
            if after.get("kind") == "absent":
                if os.path.lexists(target):
                    raise GuidanceError(
                        f"cannot roll back; target reappeared: {target}"
                    )
            elif after.get("kind") == "file":
                if target.is_symlink() or not target.is_file():
                    raise GuidanceError(
                        f"cannot roll back; managed target is missing: {target}"
                    )
                if sha256_file(target) != after.get("sha256"):
                    raise GuidanceError(
                        f"cannot roll back; managed target has local drift: {target}"
                    )
            else:
                raise GuidanceError(
                    f"rollback journal has an invalid after-state for {target}"
                )

    for entry in reversed(entries):
        target_relative = _relative_path(entry.get("target"), "journal target")
        target = home / target_relative
        before = entry.get("before", {})
        if before.get("kind") == "absent":
            if os.path.lexists(target):
                if target.is_symlink() or not target.is_file():
                    raise GuidanceError(
                        f"refusing to remove non-file during rollback: {target}"
                    )
                target.unlink()
            continue
        if before.get("kind") != "file":
            raise GuidanceError(
                f"rollback journal has an invalid before-state for {target}"
            )
        backup_relative = _relative_path(before.get("backup"), "journal backup")
        backup = state_dir / backup_relative
        try:
            backup.resolve().relative_to(state_dir.resolve())
        except ValueError as exc:
            raise GuidanceError(
                f"rollback backup escapes the state directory: {backup}"
            ) from exc
        if not backup.is_file() or backup.is_symlink():
            raise GuidanceError(f"rollback backup is missing: {backup}")
        if sha256_file(backup) != before.get("sha256"):
            raise GuidanceError(f"rollback backup checksum mismatch: {backup}")
        _atomic_write(target, backup.read_bytes(), int(before.get("mode", 0o644)))


def _atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
