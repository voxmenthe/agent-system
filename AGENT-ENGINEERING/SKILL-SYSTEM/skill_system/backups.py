"""Move displaced host-discovery entries aside instead of deleting them.

Each move is one same-filesystem rename, so an interruption leaves the entry
either at its target or in its backup slot, never half-copied.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .model import CollisionError, ValidationError


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _nearest_existing(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate.parent == candidate:
            raise ValidationError(f"no existing parent for {path}")
        candidate = candidate.parent
    return candidate


def assert_same_filesystem(target: Path, backup_root: Path) -> None:
    """Raise ValidationError unless renaming target under backup_root stays on one device."""
    if target.lstat().st_dev != _nearest_existing(backup_root).stat().st_dev:
        raise ValidationError(
            f"backup root and target must share a filesystem: {target} -> {backup_root}"
        )


def move_to_backup(target: Path, backup_root: Path, name: str) -> Path:
    """Rename target to backup_root/name, flush both parents, and return the backup path."""
    if name in {"", ".", ".."} or Path(name).name != name:
        raise ValidationError(f"backup name must be one path component: {name!r}")
    backup = backup_root / name
    if backup.exists() or backup.is_symlink():
        raise CollisionError(f"backup slot already occupied: {backup}")
    assert_same_filesystem(target, backup_root)
    existing = _nearest_existing(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    # Make each newly created backup directory durable before it holds data.
    created = backup_root
    while True:
        _fsync_directory(created)
        if created == existing:
            break
        created = created.parent
    os.rename(target, backup)
    _fsync_directory(target.parent)
    _fsync_directory(backup_root)
    return backup


def restore_backup(backup: Path, target: Path) -> None:
    """Discard any partial replacement at target, then rename backup back to target."""
    if not (backup.exists() or backup.is_symlink()):
        raise ValidationError(f"backup to restore is missing: {backup}")
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        target.unlink()
    elif target.exists():
        shutil.rmtree(target)
    os.rename(backup, target)
    _fsync_directory(target.parent)
    _fsync_directory(backup.parent)
