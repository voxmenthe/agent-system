from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import uuid

from .model import (
    CollisionError,
    OperationResult,
    SKILL_NAME,
    ValidationError,
    content_hash,
    is_ignored_skill_path,
)


GROK_HOMES = (".grok", ".grok2", ".grok3")


def validate_grok_sources(root: Path) -> dict[str, str]:
    """Check native Grok package envelopes; Grok owns full YAML interpretation."""
    sources = root / "grok-skills"
    if sources.is_symlink() or (sources.exists() and not sources.is_dir()):
        raise ValidationError(f"Grok source root must be a real directory: {sources}")
    if not sources.exists():
        return {}
    hashes: dict[str, str] = {}
    for skill in sorted(sources.iterdir()):
        if skill.name == "README.md" and skill.is_file() and not skill.is_symlink():
            continue
        if not SKILL_NAME.fullmatch(skill.name) or not skill.is_dir():
            raise ValidationError(f"invalid Grok skill directory: {skill}")
        for path in [skill, *skill.rglob("*")]:
            if path != skill and is_ignored_skill_path(path, skill):
                continue
            mode = path.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValidationError(f"symlink or special file in Grok source: {path}")
        skill_md = skill / "SKILL.md"
        try:
            text = skill_md.read_text()
        except (OSError, UnicodeError) as exc:
            raise ValidationError(f"cannot read Grok declaration: {skill_md}") from exc
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise ValidationError(f"invalid Grok frontmatter: {skill_md}")
        header = text[4:text.index("\n---\n", 4)]
        names = re.findall(r"^name:[ \t]*(\S[^\n]*)$", header, re.MULTILINE)
        if len(names) != 1:
            raise ValidationError(f"Grok declaration requires one name: {skill_md}")
        name = names[0].strip()
        if name.startswith('"'):
            try:
                name = json.loads(name)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"invalid Grok skill name: {skill_md}") from exc
        elif name.startswith("'") and name.endswith("'"):
            name = name[1:-1].replace("''", "'")
        if name != skill.name:
            raise ValidationError(f"Grok folder/name mismatch: {skill_md}")
        descriptions = re.findall(r"^description:([^\n]*)", header, re.MULTILINE)
        if len(descriptions) != 1 or not descriptions[0].strip():
            raise ValidationError(f"Grok declaration requires a description: {skill_md}")
        if descriptions[0].strip() in {">", "|", ">-", "|-", ">+", "|+"}:
            if not re.search(r"^description:[^\n]*\n[ \t]+\S", header, re.MULTILINE):
                raise ValidationError(f"empty Grok description block: {skill_md}")
        hashes[skill.name] = content_hash(skill)
    return hashes


def grok_status(
    root: Path, home: Path, accounts: tuple[str, ...] = GROK_HOMES
) -> dict[str, dict[str, str]]:
    hashes = validate_grok_sources(root)
    if not hashes:
        return {}
    states: dict[str, dict[str, str]] = {}
    for account in accounts:
        account_root = home / account
        skills = account_root / "skills"
        for boundary in (account_root, skills):
            if boundary.is_symlink() or (boundary.exists() and not boundary.is_dir()):
                raise CollisionError(f"Grok discovery root must be a real directory: {boundary}")
        states[account] = {}
        for name in hashes:
            source = root / "grok-skills" / name
            target = skills / name
            linked_source = None
            if target.is_symlink():
                try:
                    linked_source = target.resolve()
                except (OSError, RuntimeError):
                    pass
            if linked_source == source:
                state = "current"
            elif target.exists() or target.is_symlink():
                state = "unmanaged-collision"
            else:
                state = "absent"
            states[account][name] = state
    return states


def _flush_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def project_grok(
    root: Path,
    home: Path,
    *,
    apply: bool = False,
    force: bool = False,
    accounts: tuple[str, ...] = GROK_HOMES,
) -> OperationResult:
    """Caller holds the SkillSystem lock. Replaced entries are retained, never deleted."""
    states = grok_status(root, home, accounts)
    planned: list[tuple[Path, Path, bool]] = []
    changes: list[str] = []
    for account, skills in states.items():
        for name, state in skills.items():
            if state == "current":
                continue
            target = home / account / "skills" / name
            source = root / "grok-skills" / name
            collision = state == "unmanaged-collision"
            if collision and not force:
                raise CollisionError(f"preserve/import Grok collision before --force: {target}")
            if collision:
                changes.append(f"back up exact Grok entry: {target}")
            changes.append(f"link {target} -> {source}")
            planned.append((target, source, collision))
    if not apply:
        return OperationResult(None, False, "dry-run", tuple(changes))
    if not planned:
        return OperationResult(None, False, "already-current")

    backup_parent = home / ".agents" / ".skill-system" / "grok-backups"
    # Preflight all devices before moving any existing entry.
    for target, _, collision in planned:
        if not collision:
            continue
        existing_parent = backup_parent
        while not existing_parent.exists():
            existing_parent = existing_parent.parent
        if target.parent.stat().st_dev != existing_parent.stat().st_dev:
            raise ValidationError(f"Grok backup and target must share a filesystem: {target}")
    backup_root = backup_parent / uuid.uuid4().hex
    backups = False
    for target, source, collision in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = backup_root / target.parent.parent.name / target.name
        if collision:
            backup.parent.mkdir(parents=True, exist_ok=True)
            _flush_directory(backup_root)
            _flush_directory(backup_parent)
            target.rename(backup)
            _flush_directory(backup.parent)
            _flush_directory(target.parent)
            backups = True
        try:
            target.symlink_to(source, target_is_directory=True)
        except BaseException:
            if collision and not (target.exists() or target.is_symlink()):
                backup.rename(target)
                _flush_directory(target.parent)
            raise
        _flush_directory(target.parent)
    return OperationResult(
        None,
        True,
        "configured",
        tuple(changes),
        quarantine_path=backup_root if backups else None,
    )
