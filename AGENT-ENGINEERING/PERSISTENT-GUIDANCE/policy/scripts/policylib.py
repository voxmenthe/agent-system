from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

POLICY_RELATIVE_PATH = Path("policy")
MANIFEST_RELATIVE_PATH = POLICY_RELATIVE_PATH / "manifest.json"
ROUTING_BEGIN = "<!-- BEGIN GENERATED ROUTING TABLE -->"
ROUTING_END = "<!-- END GENERATED ROUTING TABLE -->"


class PolicyError(RuntimeError):
    pass


def default_policy_root() -> Path:
    override = os.environ.get("PERSISTENT_GUIDANCE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def default_codex_home() -> Path:
    """Compatibility alias for callers of the original Codex-only builder."""
    return default_policy_root()


def load_manifest(policy_home: Path) -> dict[str, Any]:
    path = policy_home / MANIFEST_RELATIVE_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyError(f"Policy manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"Invalid JSON in {path}: {exc}") from exc
    validate_manifest_shape(data, policy_home)
    return data


def validate_manifest_shape(
    manifest: dict[str, Any], policy_home: Path | None = None
) -> None:
    errors: list[str] = []
    if manifest.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    if "router" in manifest:
        errors.append(
            "router configuration is retired; manifest.json is a static pack catalog"
        )

    packs = manifest.get("packs")
    if not isinstance(packs, dict) or not packs:
        errors.append("packs must be a non-empty object")
        raise PolicyError("; ".join(errors))

    required_fields = {
        "file",
        "description",
        "applies_to",
        "load_before",
        "risk",
        "dependencies",
    }
    retired_fields = {
        "prompt_patterns",
        "path_globs",
        "command_patterns",
        "trigger_summary",
    }
    for name, pack in packs.items():
        if not isinstance(pack, dict):
            errors.append(f"pack {name!r} must be an object")
            continue
        missing = required_fields - pack.keys()
        if missing:
            errors.append(f"pack {name!r} is missing: {', '.join(sorted(missing))}")
        retired = retired_fields & pack.keys()
        if retired:
            errors.append(
                f"pack {name!r} uses retired routing fields: {', '.join(sorted(retired))}"
            )
        if pack.get("risk") not in {"normal", "elevated", "high"}:
            errors.append(f"pack {name!r} risk must be normal, elevated, or high")
        for field in ("file", "description", "applies_to", "load_before"):
            if not isinstance(pack.get(field), str) or not pack[field].strip():
                errors.append(f"pack {name!r} {field} must be a non-empty string")
        dependencies = pack.get("dependencies")
        if not isinstance(dependencies, list):
            errors.append(f"pack {name!r} dependencies must be an array")
            continue
        for dependency in dependencies:
            if dependency not in packs:
                errors.append(f"pack {name!r} has unknown dependency {dependency!r}")
        if policy_home is not None and isinstance(pack.get("file"), str):
            path = policy_home / POLICY_RELATIVE_PATH / pack["file"]
            if not path.is_file():
                errors.append(f"pack {name!r} file does not exist: {path}")

    try:
        dependency_order(packs, manifest)
    except PolicyError as exc:
        errors.append(str(exc))
    if errors:
        raise PolicyError("; ".join(errors))


def dependency_order(names: Iterable[str], manifest: dict[str, Any]) -> list[str]:
    packs = manifest["packs"]
    wanted = set(names)
    visiting: set[str] = set()
    visited: set[str] = set()
    result: list[str] = []

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise PolicyError(f"dependency cycle includes {name!r}")
        if name not in packs:
            raise PolicyError(f"unknown policy pack {name!r}")
        visiting.add(name)
        for dependency in packs[name]["dependencies"]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        result.append(name)

    for name in packs:
        if name in wanted:
            visit(name)
    for name in sorted(wanted):
        visit(name)
    return result


def pack_path(policy_home: Path, manifest: dict[str, Any], name: str) -> Path:
    return policy_home / POLICY_RELATIVE_PATH / manifest["packs"][name]["file"]


def pack_text(policy_home: Path, manifest: dict[str, Any], name: str) -> str:
    return pack_path(policy_home, manifest, name).read_text(encoding="utf-8").strip()


def render_routing_table(manifest: dict[str, Any]) -> str:
    lines = [
        "| Pack | Read before | Applies to | Dependencies | Risk |",
        "|---|---|---|---|---|",
    ]
    for name, pack in manifest["packs"].items():
        dependencies = (
            ", ".join(f"`{dependency}`" for dependency in pack["dependencies"]) or "—"
        )
        lines.append(
            f"| [`{name}`](policy/{pack['file']}) | {pack['load_before']} | "
            f"{pack['applies_to']} | {dependencies} | {pack['risk']} |"
        )
    lines.extend(
        [
            "",
            (
                "Use semantic judgment to select packs from the requested work and discovered scope; "
                "do not route by keyword occurrence alone. Read each selected pack and its dependencies "
                "before the listed phase."
            ),
        ]
    )
    return "\n".join(lines)


def replace_generated_table(agents_text: str, table: str) -> str:
    if ROUTING_BEGIN not in agents_text or ROUTING_END not in agents_text:
        raise PolicyError("AGENTS.md is missing generated routing-table markers")
    before, rest = agents_text.split(ROUTING_BEGIN, 1)
    _, after = rest.split(ROUTING_END, 1)
    return f"{before}{ROUTING_BEGIN}\n{table}\n{ROUTING_END}{after}"
