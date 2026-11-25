from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REGISTRY_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1
OPERATION_SCHEMA_VERSION = 1
LIFECYCLES = {"reference", "experimental", "stable", "deprecated", "retired"}
EFFECT_CEILINGS = {
    "read-only",
    "local-write",
    "git-mutation",
    "external-write",
    "destructive",
}
OWNERSHIPS = {"custom", "legacy-unmanaged", "external"}
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CONTENT_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FORBIDDEN_ASSUMPTIONS = (
    re.compile(r"(?i)(?:^|[\s`])/(?:setup|wayfinder|ask-matt)(?:\s|`|$)"),
    re.compile(r"(?i)\b(?:progress|task)\s+tracker\b"),
)


class SkillSystemError(RuntimeError):
    """Base error for expected, user-actionable failures."""


class ValidationError(SkillSystemError):
    """A source, registry, state, or operation contract is invalid."""


class CollisionError(SkillSystemError):
    """A live path is not safe for the requested managed operation."""


class LockBusyError(SkillSystemError):
    """Another process owns the advisory operation lock."""


class IncompleteOperationError(SkillSystemError):
    """A prior mutation requires explicit recovery."""


@dataclass(frozen=True)
class AuditReport:
    ok: bool
    registry_hash: str
    custom_skills: tuple[str, ...]
    legacy_skills: tuple[str, ...]
    external_skills: tuple[str, ...]
    source_hashes: dict[str, str] = field(default_factory=dict)
    grok_skills: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillState:
    name: str
    ownership: str
    lifecycle: str | None
    state: str
    source_hash: str | None = None
    target_hash: str | None = None


@dataclass(frozen=True)
class StatusReport:
    skills: dict[str, SkillState]
    incomplete_operations: tuple[str, ...] = ()
    grok: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationResult:
    operation_id: str | None
    applied: bool
    reason: str
    changes: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    quarantine_path: Path | None = None


@dataclass(frozen=True)
class RefreshResult:
    applied: bool
    reason: str
    operations: dict[str, OperationResult] = field(default_factory=dict)
    excluded: dict[str, tuple[str, ...]] = field(default_factory=dict)
    claude: OperationResult | None = None
    mimo: OperationResult | None = None
    grok: OperationResult | None = None



@dataclass(frozen=True)
class Registry:
    path: Path
    revision: str
    skills: dict[str, dict[str, Any]]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(
            path.read_text(),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(f"invalid {label} at {path}: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def validate_timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} must be a date-time string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(f"{label} must be a valid date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{label} must include a UTC offset")


IGNORED_SKILL_SUFFIXES = (".pyc", ".pyo")


def is_ignored_skill_path(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return (
        "__pycache__" in relative.parts
        or path.name.endswith(IGNORED_SKILL_SUFFIXES)
    )


def ignore_skill_junk(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith(IGNORED_SKILL_SUFFIXES)
    }


def content_hash(root: Path) -> str:
    """Hash names, types, modes, link targets, and file bytes deterministically."""
    if not root.is_dir():
        raise ValidationError(f"skill tree is not a directory: {root}")
    digest = hashlib.sha256()
    digest.update(b"skill-tree-v1\0")
    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if not is_ignored_skill_path(path, root)
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in paths:
        relative = path.relative_to(root).as_posix().encode()
        metadata = path.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISDIR(metadata.st_mode):
            kind = b"d"
            payload = b""
        elif stat.S_ISREG(metadata.st_mode):
            kind = b"f"
            payload = path.read_bytes()
        elif stat.S_ISLNK(metadata.st_mode):
            kind = b"l"
            payload = os.readlink(path).encode()
        else:
            kind = b"s"
            payload = b""
        digest.update(relative)
        digest.update(b"\0")
        digest.update(kind)
        digest.update(b"\0")
        digest.update(f"{mode:04o}".encode())
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return "sha256:" + digest.hexdigest()


def _expect_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def _expect_exact_keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    label: str,
) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise ValidationError(f"{label} missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ValidationError(f"{label} unknown field(s): {', '.join(sorted(unknown))}")


def _resolve_source(root: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ValidationError("custom source must be a non-empty path")
    candidate = root / raw
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValidationError(f"source path escapes canonical root: {raw}") from exc
    return resolved


def resolve_target(
    home: Path,
    raw: str,
    name: str,
    *,
    enforce_name: bool = True,
) -> Path:
    if not isinstance(raw, str) or not raw.startswith("~/"):
        raise ValidationError(f"install target must begin with ~/: {raw!r}")
    relative = raw[2:]
    candidate = (home / relative).resolve()
    allowed = (home / ".agents" / "skills").resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise ValidationError(f"install target escapes allowed root: {raw}") from exc
    if candidate.parent != allowed:
        raise ValidationError(
            f"install target must be directly under ~/.agents/skills: {raw}"
        )
    if enforce_name and candidate.name != name:
        raise ValidationError(
            f"install target must use the declared name {name}: {raw}"
        )
    return candidate


def _parse_yaml_string_scalar(raw: str, *, path: Path, number: int) -> str:
    if raw.startswith('"') or raw.endswith('"'):
        if not (raw.startswith('"') and raw.endswith('"')):
            raise ValidationError(
                f"frontmatter value must be a valid quoted YAML scalar "
                f"at {path}:{number}"
            )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"frontmatter value must be a valid quoted YAML scalar "
                f"at {path}:{number}"
            ) from exc
        if not isinstance(value, str):
            raise ValidationError(
                f"frontmatter value must be a string at {path}:{number}"
            )
        return value
    if (
        not raw
        or ": " in raw
        or raw.endswith(":")
        or " #" in raw
        or raw.startswith(("'", "[", "{", "|", ">", "&", "*", "!", "%", "@", "`"))
    ):
        raise ValidationError(
            f"frontmatter value must use a quoted YAML scalar at {path}:{number}"
        )
    return raw


def _parse_frontmatter(path: Path) -> dict[str, str]:
    try:
        content = path.read_text()
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read SKILL.md at {path}: {exc}") from exc
    if not content.startswith("---\n"):
        raise ValidationError(f"invalid frontmatter in {path}: missing opening delimiter")
    end = content.find("\n---\n", 4)
    if end == -1:
        raise ValidationError(f"invalid frontmatter in {path}: missing closing delimiter")
    result: dict[str, str] = {}
    for number, line in enumerate(content[4:end].splitlines(), 1):
        if not line or line.startswith((" ", "\t", "#")) or ":" not in line:
            raise ValidationError(f"invalid frontmatter line {number} in {path}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in result:
            raise ValidationError(f"duplicate frontmatter key {key} in {path}")
        result[key] = (
            value
            if key == "disable-model-invocation"
            else _parse_yaml_string_scalar(value, path=path, number=number)
        )
    unknown = result.keys() - {"name", "description", "disable-model-invocation"}
    if unknown:
        raise ValidationError(
            f"unsupported frontmatter key(s) in {path}: {', '.join(sorted(unknown))}"
        )
    if not {"name", "description"} <= result.keys():
        raise ValidationError(f"frontmatter in {path} requires name and description")
    if result.get("disable-model-invocation") not in {None, "true", "false"}:
        raise ValidationError(
            f"disable-model-invocation in {path} must be true or false"
        )
    if not SKILL_NAME.fullmatch(result["name"]):
        raise ValidationError(f"invalid skill name in frontmatter: {result['name']!r}")
    description = result["description"]
    if not description or len(description) > 1024 or "<" in description or ">" in description:
        raise ValidationError(f"invalid skill description in {path}")
    lowered = description.lower()
    if "use " not in lowered or not any(
        marker in lowered for marker in ("do not use", "use when", "use before", "use after")
    ):
        raise ValidationError(
            f"description in {path} must contain concrete positive and negative trigger language"
        )
    return result


def _parse_quoted_yaml(path: Path, name: str) -> dict[str, dict[str, Any]]:
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"invalid openai.yaml at {path}: {exc}") from exc
    sections: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for number, line in enumerate(lines, 1):
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            if not line.endswith(":"):
                raise ValidationError(f"invalid openai.yaml line {number} at {path}")
            current = line[:-1]
            if current not in {"interface", "policy"} or current in sections:
                raise ValidationError(f"invalid openai.yaml section {current!r} at {path}")
            sections[current] = {}
            continue
        if not line.startswith("  ") or line.startswith("   ") or current is None:
            raise ValidationError(f"invalid openai.yaml indentation line {number} at {path}")
        item = line[2:]
        if ":" not in item:
            raise ValidationError(f"invalid openai.yaml line {number} at {path}")
        key, raw = item.split(":", 1)
        raw = raw.strip()
        if key in sections[current]:
            raise ValidationError(f"duplicate openai.yaml key {key!r} at {path}")
        if current == "interface":
            if not (raw.startswith('"') and raw.endswith('"')):
                raise ValidationError(
                    f"openai.yaml interface strings must be double quoted at {path}:{number}"
                )
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"invalid quoted string at {path}:{number}") from exc
        else:
            if raw not in {"true", "false"}:
                raise ValidationError(f"policy values must be booleans at {path}:{number}")
            value = raw == "true"
        sections[current][key] = value
    if set(sections) - {"interface", "policy"} or "interface" not in sections:
        raise ValidationError(f"invalid openai.yaml sections at {path}")
    interface = sections["interface"]
    _expect_exact_keys(
        interface,
        required={"display_name", "short_description", "default_prompt"},
        optional={"icon_small", "icon_large", "brand_color"},
        label=f"interface in {path}",
    )
    if not all(isinstance(value, str) and value for value in interface.values()):
        raise ValidationError(f"openai.yaml interface values must be non-empty strings at {path}")
    short = interface["short_description"]
    if not 25 <= len(short) <= 64:
        raise ValidationError(f"openai.yaml short_description must be 25-64 characters at {path}")
    if f"${name}" not in interface["default_prompt"]:
        raise ValidationError(f"openai.yaml default_prompt must mention ${name} at {path}")
    if "policy" in sections:
        _expect_exact_keys(
            sections["policy"],
            required={"allow_implicit_invocation"},
            label=f"policy in {path}",
        )
    return sections


def _validate_local_links(skill_root: Path, skill_md: Path) -> None:
    content = skill_md.read_text()
    for raw in MARKDOWN_LINK.findall(content):
        target = raw.split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        candidate = (skill_md.parent / target).resolve()
        try:
            candidate.relative_to(skill_root.resolve())
        except ValueError as exc:
            raise ValidationError(f"local resource reference escapes skill: {raw}") from exc
        if not candidate.exists():
            raise ValidationError(f"broken local resource reference {raw} in {skill_md}")


def validate_skill_tree(skill_root: Path, expected_name: str) -> str:
    if not skill_root.is_dir():
        raise ValidationError(f"missing canonical skill directory: {skill_root}")
    for path in [skill_root, *skill_root.rglob("*")]:
        if path != skill_root and is_ignored_skill_path(path, skill_root):
            continue
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValidationError(f"symlink forbidden in canonical skill tree: {path}")
        if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            raise ValidationError(f"special file forbidden in canonical skill tree: {path}")
    skill_md = skill_root / "SKILL.md"
    frontmatter = _parse_frontmatter(skill_md)
    if frontmatter["name"] != expected_name or skill_root.name != expected_name:
        raise ValidationError(
            f"folder/frontmatter/registry key mismatch for {expected_name}: "
            f"{skill_root.name}/{frontmatter['name']}"
        )
    metadata = _parse_quoted_yaml(
        skill_root / "agents" / "openai.yaml", expected_name
    )
    model_invocation_disabled = (
        frontmatter.get("disable-model-invocation") == "true"
    )
    implicit_invocation_allowed = metadata.get("policy", {}).get(
        "allow_implicit_invocation", True
    )
    if model_invocation_disabled == implicit_invocation_allowed:
        raise ValidationError(
            f"invocation policy mismatch for {expected_name}: "
            "SKILL.md disable-model-invocation must be the inverse of "
            "agents/openai.yaml policy.allow_implicit_invocation"
        )
    _validate_local_links(skill_root, skill_md)
    content = skill_md.read_text()
    for pattern in FORBIDDEN_ASSUMPTIONS:
        if pattern.search(content):
            raise ValidationError(
                f"hidden framework assumption in {skill_md}: {pattern.pattern}"
            )
    return content_hash(skill_root)


def _validate_provenance(
    value: Any,
    *,
    ownership: str,
    label: str,
) -> dict[str, Any]:
    provenance = _expect_mapping(value, label)
    allowed = {
        "origin",
        "revision",
        "license",
        "observed_hash",
        "disposition",
        "exit_phase",
        "manager",
        "notes",
        "local_modifications",
        "reference_revision",
        "snapshot",
    }
    unknown = provenance.keys() - allowed
    if unknown:
        raise ValidationError(f"{label} unknown field(s): {', '.join(sorted(unknown))}")
    required = {"origin", "revision", "license"}
    if ownership == "legacy-unmanaged":
        required |= {"observed_hash", "disposition", "exit_phase"}
    if ownership == "external":
        required |= {"manager"}
    missing = required - provenance.keys()
    if missing:
        raise ValidationError(f"{label} missing field(s): {', '.join(sorted(missing))}")
    string_fields = allowed - {"exit_phase"}
    for key in provenance.keys() & string_fields:
        if not isinstance(provenance[key], str) or not provenance[key]:
            raise ValidationError(f"{label}.{key} must be a non-empty string")
    if "observed_hash" in provenance:
        observed = provenance["observed_hash"]
        if not isinstance(observed, str) or not CONTENT_HASH.fullmatch(observed):
            raise ValidationError(f"{label}.observed_hash is invalid")
    if ownership == "legacy-unmanaged":
        if (
            not isinstance(provenance["exit_phase"], int)
            or isinstance(provenance["exit_phase"], bool)
            or provenance["exit_phase"] < 1
        ):
            raise ValidationError(f"{label}.exit_phase must be an integer")
    return provenance


def load_registry(root: Path, home: Path) -> Registry:
    path = root / "registry.json"
    data = _expect_mapping(load_json(path, "registry.json"), "registry")
    _expect_exact_keys(
        data,
        required={"schema_version", "skills"},
        label="registry",
    )
    if data["schema_version"] != REGISTRY_SCHEMA_VERSION:
        raise ValidationError(
            f"unsupported registry schema_version {data['schema_version']!r}; "
            f"expected {REGISTRY_SCHEMA_VERSION}"
        )
    skills = _expect_mapping(data["skills"], "registry.skills")
    targets: dict[Path, str] = {}
    for name, raw_record in skills.items():
        if not isinstance(name, str) or not SKILL_NAME.fullmatch(name):
            raise ValidationError(f"invalid registry skill name: {name!r}")
        record = _expect_mapping(raw_record, f"registry.skills.{name}")
        ownership = record.get("ownership")
        if ownership not in OWNERSHIPS:
            raise ValidationError(f"invalid ownership for {name}: {ownership!r}")
        required = {
            "ownership",
            "install_targets",
            "dependencies",
            "effect_ceiling",
            "provenance",
            "evaluation_profile",
        }
        optional: set[str] = set()
        if ownership == "custom":
            required |= {"lifecycle", "source"}
        elif ownership == "legacy-unmanaged":
            required |= {"lifecycle"}
        else:
            optional.add("lifecycle")
        _expect_exact_keys(
            record,
            required=required,
            optional=optional,
            label=f"registry.skills.{name}",
        )
        lifecycle = record.get("lifecycle")
        if lifecycle is not None and lifecycle not in LIFECYCLES:
            raise ValidationError(f"invalid lifecycle for {name}: {lifecycle!r}")
        effect = record["effect_ceiling"]
        if effect not in EFFECT_CEILINGS:
            raise ValidationError(f"invalid effect_ceiling for {name}: {effect!r}")
        dependencies = record["dependencies"]
        if not isinstance(dependencies, list) or any(
            not isinstance(item, str) or not SKILL_NAME.fullmatch(item)
            for item in dependencies
        ):
            raise ValidationError(f"dependencies for {name} must be skill names")
        if len(dependencies) != len(set(dependencies)):
            raise ValidationError(f"duplicate dependency for {name}")
        install_targets = record["install_targets"]
        if not isinstance(install_targets, list) or len(install_targets) != 1:
            raise ValidationError(f"{name} requires exactly one install target in Release 1")
        target = resolve_target(
            home,
            install_targets[0],
            name,
            enforce_name=False,
        )
        if target in targets:
            raise ValidationError(
                f"duplicate install target for {name} and {targets[target]}: {target}"
            )
        if target.name != name:
            raise ValidationError(
                f"install target must use the declared name {name}: "
                f"{install_targets[0]}"
            )
        targets[target] = name
        _validate_provenance(
            record["provenance"],
            ownership=ownership,
            label=f"registry.skills.{name}.provenance",
        )
        profile = record["evaluation_profile"]
        if not isinstance(profile, str) or not profile:
            raise ValidationError(f"evaluation_profile for {name} must be non-empty")
        if ownership == "custom":
            source = _resolve_source(root, record["source"])
            if source.name != name:
                raise ValidationError(f"source folder does not match registry key {name}")
    for name, record in skills.items():
        for dependency in record["dependencies"]:
            if dependency not in skills:
                raise ValidationError(f"{name} has undeclared dependency {dependency}")
            if skills[dependency].get("lifecycle") == "retired":
                raise ValidationError(f"{name} depends on retired skill {dependency}")
    _validate_dependency_graph(skills)
    return Registry(path, sha256_bytes(path.read_bytes()), skills)


def _validate_dependency_graph(skills: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str, path: tuple[str, ...]) -> None:
        if name in visiting:
            raise ValidationError(f"dependency cycle: {' -> '.join((*path, name))}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in skills[name]["dependencies"]:
            visit(dependency, (*path, name))
        visiting.remove(name)
        visited.add(name)

    for name in skills:
        visit(name, ())


def validate_canonical(root: Path, home: Path) -> tuple[Registry, AuditReport]:
    registry = load_registry(root, home)
    source_hashes: dict[str, str] = {}
    custom: list[str] = []
    legacy: list[str] = []
    external: list[str] = []
    canonical_names = {
        path.name for path in (root / "skills").iterdir() if path.is_dir()
    } if (root / "skills").is_dir() else set()
    for name, record in registry.skills.items():
        ownership = record["ownership"]
        if ownership == "custom":
            custom.append(name)
            source_hashes[name] = validate_skill_tree(
                _resolve_source(root, record["source"]), name
            )
        elif ownership == "legacy-unmanaged":
            legacy.append(name)
        else:
            external.append(name)
    unexpected = canonical_names - set(custom)
    missing = set(custom) - canonical_names
    if unexpected:
        raise ValidationError(
            f"canonical skill directories lack custom registry records: "
            f"{', '.join(sorted(unexpected))}"
        )
    if missing:
        raise ValidationError(
            f"custom registry records lack canonical directories: "
            f"{', '.join(sorted(missing))}"
        )
    return registry, AuditReport(
        ok=True,
        registry_hash=registry.revision,
        custom_skills=tuple(sorted(custom)),
        legacy_skills=tuple(sorted(legacy)),
        external_skills=tuple(sorted(external)),
        source_hashes=dict(sorted(source_hashes.items())),
    )


def empty_install_state() -> dict[str, Any]:
    return {"schema_version": STATE_SCHEMA_VERSION, "managed": {}}


def load_install_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_install_state()
    data = _expect_mapping(load_json(path, "install-state.json"), "install state")
    _expect_exact_keys(
        data,
        required={"schema_version", "managed"},
        label="install state",
    )
    if data["schema_version"] != STATE_SCHEMA_VERSION:
        raise ValidationError(
            f"unsupported state schema_version {data['schema_version']!r}; "
            f"expected {STATE_SCHEMA_VERSION}"
        )
    managed = _expect_mapping(data["managed"], "install state managed")
    entry_keys = {
        "source",
        "source_hash",
        "target",
        "target_hash",
        "operation_id",
        "installed_at",
        "registry_revision",
        "status",
    }
    for name, entry_value in managed.items():
        if not SKILL_NAME.fullmatch(name):
            raise ValidationError(f"invalid managed skill name {name!r}")
        entry = _expect_mapping(entry_value, f"install state managed.{name}")
        _expect_exact_keys(
            entry,
            required=entry_keys,
            label=f"install state managed.{name}",
        )
        if entry["status"] != "committed":
            raise ValidationError(f"managed state for {name} is not committed")
        for key in entry_keys:
            if not isinstance(entry[key], str) or not entry[key]:
                raise ValidationError(f"managed state {name}.{key} is invalid")
        for key in ("source_hash", "target_hash", "registry_revision"):
            if not CONTENT_HASH.fullmatch(entry[key]):
                raise ValidationError(
                    f"managed state {name}.{key} must be a sha256 content hash"
                )
        validate_timestamp(
            entry["installed_at"],
            f"managed state {name}.installed_at",
        )
    return data


MACHINE_FILE = Path(".config/agent-system/machine.json")


def load_enabled_hosts(home: Path) -> frozenset[str] | None:
    """Hosts ~/.config/agent-system/machine.json enables; None (every host) when it is absent."""
    path = home / MACHINE_FILE
    if not path.exists():
        return None
    try:
        machine = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read machine file {path}: {exc}") from exc
    hosts = machine.get("hosts") if isinstance(machine, dict) else None
    if (
        not isinstance(machine, dict)
        or machine.get("schema_version") != 1
        or not isinstance(hosts, list)
        or not all(isinstance(host, str) for host in hosts)
    ):
        raise ValidationError(f"machine file needs schema_version 1 and a hosts list: {path}")
    return frozenset(hosts)


def validate_install_state(
    state: dict[str, Any],
    registry: Registry,
    root: Path,
    home: Path,
) -> None:
    for name, entry in state["managed"].items():
        record = registry.skills.get(name)
        if record is None:
            raise ValidationError(
                f"unknown managed skill or non-custom ownership: {name}"
            )
        pending_live_quarantine = (
            record["ownership"] == "legacy-unmanaged"
            and record.get("lifecycle") == "retired"
            and record["provenance"].get("disposition")
            == "canonical-retired-pending-live-quarantine"
        )
        if record["ownership"] == "custom":
            expected_source = str(_resolve_source(root, record["source"]))
        elif pending_live_quarantine:
            expected_source = str((root / "skills" / name).resolve())
            observed_hash = record["provenance"]["observed_hash"]
            if (
                entry["source_hash"] != observed_hash
                or entry["target_hash"] != observed_hash
            ):
                raise ValidationError(
                    f"pending live quarantine state hash disagrees with registry: {name}"
                )
        else:
            raise ValidationError(
                f"unknown managed skill or non-custom ownership: {name}"
            )
        if entry["source"] != expected_source:
            raise ValidationError(
                f"managed state {name} canonical source path disagrees with registry"
            )
        expected_target = str(
            resolve_target(home, record["install_targets"][0], name)
        )
        if entry["target"] != expected_target:
            raise ValidationError(
                f"managed state {name} canonical target path disagrees with registry"
            )


def iter_skill_states(
    registry: Registry,
    report: AuditReport,
    state: dict[str, Any],
    home: Path,
) -> Iterable[SkillState]:
    managed = state["managed"]
    for name, record in sorted(registry.skills.items()):
        target = resolve_target(home, record["install_targets"][0], name)
        ownership = record["ownership"]
        lifecycle = record.get("lifecycle")
        source_hash = report.source_hashes.get(name)
        target_hash = content_hash(target) if target.is_dir() else None
        if ownership == "custom":
            entry = managed.get(name)
            if target_hash is None:
                status = "missing-managed" if entry else "absent"
            elif entry is None:
                status = "unmanaged-collision"
            elif target_hash != entry["target_hash"]:
                status = "locally-modified"
            elif source_hash != entry["source_hash"]:
                status = "source-updated"
            else:
                status = "current"
        elif ownership == "legacy-unmanaged":
            observed = record["provenance"]["observed_hash"]
            pending_live_quarantine = (
                lifecycle == "retired"
                and record["provenance"].get("disposition")
                == "canonical-retired-pending-live-quarantine"
                and name in managed
            )
            if pending_live_quarantine and target_hash == observed:
                status = "retired-pending-live-quarantine"
            elif pending_live_quarantine and target_hash is None:
                status = "retired-pending-state-cleanup"
            elif target_hash is None:
                status = "legacy-absent"
            elif target_hash == observed:
                status = "legacy-current"
            else:
                status = "legacy-modified"
        else:
            status = "external-present" if target_hash else "external-absent"
        yield SkillState(
            name=name,
            ownership=ownership,
            lifecycle=lifecycle,
            state=status,
            source_hash=source_hash,
            target_hash=target_hash,
        )
