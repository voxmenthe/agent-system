from __future__ import annotations

import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path
from typing import Any

from .backups import assert_same_filesystem, move_to_backup, restore_backup
from .model import (
    CollisionError,
    OperationResult,
    content_hash,
    ignore_skill_junk,
    is_ignored_skill_path,
    validate_canonical,
)

MARKER_NAME = ".mimo-projection.json"
LOCALE_CODES = ("en-US", "zh-CN")
_YAML_QUOTED = re.compile(r'^([A-Za-z0-9_]+):\s*"(.*)"\s*$')


def _is_active_custom_skill(record: dict[str, Any]) -> bool:
    return (
        record.get("ownership") == "custom"
        and record.get("lifecycle") not in {"reference", "retired"}
    )


def _parse_skill_description(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    try:
        content = skill_md.read_text()
    except (OSError, UnicodeError):
        return ""
    if not content.startswith("---\n"):
        return ""
    end = content.find("\n---\n", 4)
    if end == -1:
        return ""
    for line in content[4:end].splitlines():
        if not line.startswith("description:"):
            continue
        value = line.split(":", 1)[1].strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value[1:-1]
        return value
    return ""


def _interface_fields(skill_dir: Path) -> dict[str, str]:
    path = skill_dir / "agents" / "openai.yaml"
    if not path.is_file():
        return {}
    fields: dict[str, str] = {}
    in_interface = False
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError):
        return {}
    for line in lines:
        if not line.startswith(" "):
            in_interface = line.strip() == "interface:"
            continue
        if not in_interface or not line.startswith("  ") or line.startswith("   "):
            continue
        match = _YAML_QUOTED.match(line[2:])
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def _display_metadata(skill_dir: Path, name: str) -> tuple[str, str]:
    interface = _interface_fields(skill_dir)
    display_name = interface.get("display_name") or name.replace("-", " ").title()
    brief = interface.get("short_description") or _parse_skill_description(skill_dir)
    if not brief:
        brief = f"Shared skill {name}"
    return display_name, brief


def _locale_payload(display_name: str, brief: str) -> bytes:
    body = {"displayName": display_name, "brief": brief}
    return (json.dumps(body, ensure_ascii=False, separators=(", ", ": ")) + "\n").encode()


def _write_locales(skill_dir: Path, display_name: str, brief: str) -> list[str]:
    payload = _locale_payload(display_name, brief)
    locales = skill_dir / "locales"
    changed: list[str] = []
    locales.mkdir(parents=True, exist_ok=True)
    for code in LOCALE_CODES:
        path = locales / f"{code}.json"
        if path.is_file() and path.read_bytes() == payload:
            continue
        path.write_bytes(payload)
        changed.append(str(path))
    return changed


def _read_marker(skill_dir: Path) -> dict[str, str] | None:
    path = skill_dir / MARKER_NAME
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    source = value.get("source")
    source_hash = value.get("source_hash")
    if not isinstance(source, str) or not isinstance(source_hash, str):
        return None
    return {"source": source, "source_hash": source_hash}


def _write_marker(skill_dir: Path, source: Path, source_hash: str) -> None:
    payload = {
        "source": str(source),
        "source_hash": source_hash,
    }
    (skill_dir / MARKER_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


def _remove_managed_tree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def _copy_skill_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        _remove_managed_tree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, symlinks=True, ignore=ignore_skill_junk)


def _is_safe_managed_tree(path: Path) -> bool:
    """Reject special files and absolute/escaping symlinks before copy."""
    for item in [path, *path.rglob("*")]:
        if item != path and is_ignored_skill_path(item, path):
            continue
        metadata = item.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            target = Path(os.readlink(item))
            if target.is_absolute():
                return False
            resolved = (item.parent / target).resolve()
            try:
                resolved.relative_to(path.resolve())
            except ValueError:
                return False
        elif not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            return False
    return True


def configure_mimo(
    canonical_root: Path,
    home: Path,
    *,
    apply: bool = False,
    force: bool = False,
    clean_stale: bool = True,
) -> OperationResult:
    """Copy active ~/.agents/skills entries into ~/.config/mimocode/skills.

    MiMo Desktop discovers skills only from MiMoCode roots and prefers real
    directory copies over symlinks. Each managed copy carries a marker with the
    projected source hash, plus locales/{en-US,zh-CN}.json display metadata.
    With force, an unmanaged entry (no marker) at an active skill's name is
    moved, not deleted, to ~/.agents/.skill-system/mimo-backups/<id>/<name>;
    the result's quarantine_path names that backup root.
    """
    resolved_root = canonical_root.resolve()
    resolved_home = home.resolve()
    agents_skills = (resolved_home / ".agents" / "skills").resolve()
    mimo_skills = (resolved_home / ".config" / "mimocode" / "skills").resolve()

    registry, _report = validate_canonical(resolved_root, resolved_home)
    active_skills: dict[str, Path] = {}
    for name, record in registry.skills.items():
        if not _is_active_custom_skill(record):
            continue
        target = agents_skills / name
        if target.is_dir() and not target.is_symlink():
            active_skills[name] = target

    changes: list[str] = []
    removed: list[str] = []

    existing_entries: dict[str, Path] = {}
    if mimo_skills.exists():
        if not mimo_skills.is_dir() or mimo_skills.is_symlink():
            raise CollisionError(
                f"MiMo skills path exists but is not a directory: {mimo_skills}"
            )
        for child in sorted(mimo_skills.iterdir()):
            existing_entries[child.name] = child

    planned_copies: dict[str, Path] = {}
    collisions: set[str] = set()
    for name, source in sorted(active_skills.items()):
        destination = mimo_skills / name
        if not _is_safe_managed_tree(source):
            raise CollisionError(f"refusing to project unsafe skill tree: {source}")
        source_hash = content_hash(source)
        display_name, brief = _display_metadata(source, name)
        expected_locales = {
            code: _locale_payload(display_name, brief) for code in LOCALE_CODES
        }

        entry = existing_entries.get(name)
        if entry is None:
            changes.append(f"copy skill {name} -> {destination}")
            planned_copies[name] = source
            continue

        if entry.is_symlink() or not entry.is_dir():
            if not force:
                raise CollisionError(
                    f"refusing non-directory MiMo skill entry without --force: {entry}"
                )
            changes.append(f"back up and replace non-directory entry: {entry}")
            planned_copies[name] = source
            collisions.add(name)
            continue

        marker = _read_marker(entry)
        if marker is None:
            if not force:
                raise CollisionError(
                    f"refusing unmanaged MiMo skill directory without --force: {entry}"
                )
            changes.append(f"back up and replace unmanaged directory: {entry}")
            planned_copies[name] = source
            collisions.add(name)
            continue

        locales_current = all(
            (entry / "locales" / f"{code}.json").is_file()
            and (entry / "locales" / f"{code}.json").read_bytes() == payload
            for code, payload in expected_locales.items()
        )
        if marker.get("source_hash") == source_hash and locales_current:
            continue

        changes.append(f"refresh skill copy {name} -> {destination}")
        planned_copies[name] = source

    backup_root = (
        resolved_home / ".agents" / ".skill-system" / "mimo-backups" / uuid.uuid4().hex
    )
    if apply:
        # Preflight every backup device before the first write.
        for name in sorted(collisions):
            assert_same_filesystem(mimo_skills / name, backup_root)

    for name, entry in sorted(existing_entries.items()):
        if name in active_skills:
            continue
        marker = _read_marker(entry) if entry.is_dir() and not entry.is_symlink() else None
        if marker is None:
            # Preserve unmanaged local skills with non-colliding names.
            continue
        if not clean_stale:
            continue
        removed.append(f"remove stale MiMo skill: {name}")
        if apply:
            _remove_managed_tree(entry)

    if not apply:
        return OperationResult(
            operation_id=None,
            applied=False,
            reason="dry-run",
            changes=tuple(changes),
            removed=tuple(removed),
        )

    mimo_skills.mkdir(parents=True, exist_ok=True)

    backed_up = False
    for name, source in sorted(planned_copies.items()):
        destination = mimo_skills / name
        backup: Path | None = None
        if name in collisions and (destination.exists() or destination.is_symlink()):
            backup = move_to_backup(destination, backup_root, name)
            backed_up = True
        try:
            _copy_skill_tree(source, destination)
            display_name, brief = _display_metadata(source, name)
            _write_locales(destination, display_name, brief)
            _write_marker(destination, source, content_hash(source))
        except BaseException:
            if backup is not None:
                restore_backup(backup, destination)
            raise

    # Flush directory changes
    descriptor = os.open(mimo_skills, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    applied = bool(changes or removed)
    reason = "configured" if applied else "already-current"
    return OperationResult(
        operation_id=None,
        applied=applied,
        reason=reason,
        changes=tuple(changes),
        removed=tuple(removed),
        quarantine_path=backup_root if backed_up else None,
    )
