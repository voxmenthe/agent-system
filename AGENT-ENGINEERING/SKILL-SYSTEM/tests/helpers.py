from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from skill_system.operations import SkillSystem


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_skill(
    root: Path,
    name: str,
    *,
    description: str | None = None,
    body: str | None = None,
) -> Path:
    skill = root / "skills" / name
    (skill / "agents").mkdir(parents=True, exist_ok=True)
    description = description or (
        f"Use when a test needs the {name} workflow. "
        "Do not use for unrelated work."
    )
    body = body or "# Workflow\n\n1. Preserve the test invariant.\n"
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"
    )
    (skill / "agents" / "openai.yaml").write_text(
        "interface:\n"
        f'  display_name: "{name.replace("-", " ").title()}"\n'
        '  short_description: "Exercise a bounded test skill workflow"\n'
        f'  default_prompt: "Use ${name} for this bounded test task."\n'
    )
    return skill


def custom_record(name: str, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "lifecycle": "experimental",
        "ownership": "custom",
        "source": f"skills/{name}",
        "install_targets": [f"~/.agents/skills/{name}"],
        "dependencies": [],
        "effect_ceiling": "local-write",
        "provenance": {
            "origin": "test-fixture",
            "revision": "fixture-v1",
            "license": "owner-authored",
        },
        "evaluation_profile": "test",
    }
    record.update(overrides)
    return record


def make_system(root: Path, home: Path, names: tuple[str, ...] = ("alpha",)) -> None:
    for name in names:
        write_skill(root, name)
    write_json(
        root / "registry.json",
        {
            "schema_version": 1,
            "skills": {name: custom_record(name) for name in names},
        },
    )
    state = home / ".agents" / ".skill-system"
    state.mkdir(parents=True, exist_ok=True)
    (state / "operation.lock").touch()


def tree_snapshot(root: Path) -> dict[str, tuple[str, int, bytes]]:
    if not root.exists():
        return {}
    result: dict[str, tuple[str, int, bytes]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = ("symlink", path.lstat().st_mode, path.readlink().as_posix().encode())
        elif path.is_dir():
            result[relative] = ("directory", path.stat().st_mode, b"")
        else:
            result[relative] = ("file", path.stat().st_mode, path.read_bytes())
    return result


class Stopped(Exception):
    """A command stopped by a test between a step and the journal write recording it."""

    def __init__(self, operation_id: str) -> None:
        super().__init__(f"stopped {operation_id}")
        self.operation_id = operation_id


def stop_before_journaling(phase: str):
    """Stop the next command after the step that `phase` records, before the journal
    says so, as a crash would. fail_after stops only after a journal write."""
    original = SkillSystem._phase

    def stop(self, transaction, journal, name, fail_after):
        if name == phase:
            raise Stopped(journal["operation_id"])
        original(self, transaction, journal, name, fail_after)

    return patch.object(SkillSystem, "_phase", stop)
