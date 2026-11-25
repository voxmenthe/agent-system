from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from .model import CollisionError, OperationResult, ValidationError, load_json


def _declares_shared_skills(value: Any, shared_skills: str) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        return False
    return any(
        isinstance(entry, dict) and entry.get("path") == shared_skills
        for entry in value["entries"]
    )


def _existing_declaration_is_current(target: Path, shared_skills: str) -> bool:
    if target.is_symlink() or not target.is_file():
        return False
    try:
        value = load_json(target, "Antigravity skills config")
    except ValidationError:
        return False
    return _declares_shared_skills(value, shared_skills)


def _create_exclusive(target: Path, payload: bytes) -> bool:
    """Create without replacement; return false if another writer won."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.tmp-{uuid.uuid4().hex}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            return False
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def configure_antigravity(
    home: Path,
    *,
    apply: bool = False,
) -> OperationResult:
    resolved_home = home.resolve()
    # agy 1.1.15 rejects the documented ~/ form as a non-absolute path.
    shared_skills = str(resolved_home / ".agents" / "skills")
    declaration = {"entries": [{"path": shared_skills}]}
    payload = json.dumps(declaration, indent=2, sort_keys=True).encode() + b"\n"
    target = resolved_home / ".gemini" / "config" / "skills.json"
    if target.is_symlink():
        raise CollisionError(
            f"refusing to replace existing Antigravity config: {target} is a symlink"
        )
    if target.exists():
        if _existing_declaration_is_current(target, shared_skills):
            return OperationResult(None, False, "already-current")
        raise CollisionError(
            "refusing to replace existing Antigravity config without the shared "
            f"skills declaration: {target}"
        )

    changes = (str(target),)
    if not apply:
        return OperationResult(None, False, "dry-run", changes=changes)

    try:
        created = _create_exclusive(target, payload)
    except OSError as exc:
        raise CollisionError(
            f"could not create Antigravity config at {target}: {exc}"
        ) from exc
    if not created:
        if _existing_declaration_is_current(target, shared_skills):
            return OperationResult(None, False, "already-current")
        raise CollisionError(
            "refusing to replace Antigravity config created concurrently without "
            f"the shared skills declaration: {target}"
        )
    return OperationResult(None, True, "configured", changes=changes)
