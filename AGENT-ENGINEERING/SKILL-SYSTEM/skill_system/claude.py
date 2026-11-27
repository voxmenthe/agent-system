from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from .backups import assert_same_filesystem, move_to_backup, restore_backup
from .model import (
    CollisionError,
    OperationResult,
    ValidationError,
    validate_canonical,
)


def _is_active_custom_skill(record: dict[str, Any]) -> bool:
    return (
        record.get("ownership") == "custom"
        and record.get("lifecycle") not in {"reference", "retired"}
    )


def configure_claude(
    canonical_root: Path,
    home: Path,
    *,
    apply: bool = False,
    force: bool = False,
    clean_stale: bool = True,
) -> OperationResult:
    """Project active ~/.agents/skills into ~/.claude/skills and remove stale symlinks.

    With force, a real directory at an active skill's name is moved, not deleted,
    to ~/.agents/.skill-system/claude-backups/<id>/<name>; the result's
    quarantine_path names that backup root.
    """
    resolved_root = canonical_root.resolve()
    resolved_home = home.resolve()
    agents_skills = (resolved_home / ".agents" / "skills").resolve()
    claude_skills = (resolved_home / ".claude" / "skills").resolve()

    registry, report = validate_canonical(resolved_root, resolved_home)
    active_skills: dict[str, Path] = {}
    for name, record in registry.skills.items():
        if _is_active_custom_skill(record):
            target = agents_skills / name
            if target.is_dir():
                active_skills[name] = target

    changes: list[str] = []
    removed: list[str] = []
    collisions: list[Path] = []

    # Scan existing ~/.claude/skills if present
    existing_entries: dict[str, Path] = {}
    if claude_skills.exists():
        if not claude_skills.is_dir() or claude_skills.is_symlink():
            raise CollisionError(
                f"Claude skills path exists but is not a directory: {claude_skills}"
            )
        for child in sorted(claude_skills.iterdir()):
            existing_entries[child.name] = child
            if child.is_symlink():
                target_str = os.readlink(child)
                target_path = (claude_skills / target_str).resolve()
                is_dangling = not child.exists()

                # Check if it points to ~/.agents/skills
                points_to_agents = (
                    agents_skills in target_path.parents
                    or target_path.parent == agents_skills
                    or ".agents/skills" in target_str
                )

                if is_dangling:
                    if clean_stale:
                        removed.append(f"remove dangling symlink: {child.name} -> {target_str}")
                elif points_to_agents:
                    # Valid link into ~/.agents/skills
                    if child.name not in active_skills:
                        if clean_stale:
                            removed.append(f"remove retired symlink: {child.name} -> {target_str}")
                # Note: external non-dangling symlinks (e.g. pointing outside .agents) are preserved
            elif child.is_dir():
                if child.name in active_skills:
                    if not force:
                        raise CollisionError(
                            f"refusing to replace existing directory with symlink at {child} "
                            "without --force"
                        )
                    removed.append(
                        f"back up directory and replace with symlink: {child.name}"
                    )
                    collisions.append(child)

    # Determine required symlinks for active skills
    for name, agent_target in sorted(active_skills.items()):
        claude_target = claude_skills / name
        expected_rel_target = os.path.relpath(agent_target, claude_skills)

        if name in existing_entries:
            entry = existing_entries[name]
            if entry.is_symlink() and not (not entry.exists() and clean_stale):
                current_target = os.readlink(entry)
                resolved_current = (claude_skills / current_target).resolve()
                if resolved_current == agent_target:
                    # Already correctly linked
                    continue
                changes.append(f"update symlink {claude_target} -> {expected_rel_target}")
            elif not entry.is_symlink() and entry.is_dir() and force:
                changes.append(f"create symlink {claude_target} -> {expected_rel_target}")
            elif entry.is_symlink() and not entry.exists():
                # Was dangling, marked for removal above, now recreate
                changes.append(f"create symlink {claude_target} -> {expected_rel_target}")
        else:
            changes.append(f"create symlink {claude_target} -> {expected_rel_target}")

    if not apply:
        applied = False
        reason = "dry-run"
        return OperationResult(
            operation_id=None,
            applied=applied,
            reason=reason,
            changes=tuple(changes),
            removed=tuple(removed),
        )

    backup_root = (
        resolved_home / ".agents" / ".skill-system" / "claude-backups" / uuid.uuid4().hex
    )
    # Preflight every backup device before the first write.
    for entry in collisions:
        assert_same_filesystem(entry, backup_root)

    # Perform mutations
    claude_skills.mkdir(parents=True, exist_ok=True)

    # Process removals
    for item in removed:
        if item.startswith("remove dangling symlink: ") or item.startswith("remove retired symlink: "):
            skill_name = item.split(": ", 1)[1].split(" -> ")[0]
            link_path = claude_skills / skill_name
            if link_path.is_symlink():
                link_path.unlink()

    # Process additions / updates; displaced directories are retained.
    backed_up = False
    for name, agent_target in sorted(active_skills.items()):
        claude_target = claude_skills / name
        expected_rel_target = os.path.relpath(agent_target, claude_skills)
        backup: Path | None = None

        if claude_target.is_symlink():
            current_target = os.readlink(claude_target)
            resolved_current = (claude_skills / current_target).resolve()
            if resolved_current == agent_target:
                continue
            claude_target.unlink()
        elif claude_target.exists():
            if not (force and claude_target.is_dir()):
                continue
            backup = move_to_backup(claude_target, backup_root, name)
            backed_up = True

        try:
            claude_target.symlink_to(expected_rel_target)
        except BaseException:
            if backup is not None:
                restore_backup(backup, claude_target)
            raise

    # Flush directory changes
    descriptor = os.open(claude_skills, os.O_RDONLY)
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
