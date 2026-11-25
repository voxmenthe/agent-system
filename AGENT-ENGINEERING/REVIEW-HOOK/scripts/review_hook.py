#!/usr/bin/env python3
"""Validate, inspect, install, and roll back review-after-commit bundles."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SOURCE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA = "review-hook-bundle/v1"
RECEIPT_SCHEMA = "review-hook-install-receipt/v1"
ROLLBACK_SCHEMA = "review-hook-rollback-receipt/v1"
PROFILE_RECEIPT_SCHEMA = "review-hook-profile-receipt/v1"
KIMI_CONFIG_RECEIPT_SCHEMA = "review-hook-kimi-config-receipt/v1"
PLUGIN_STATE_RECEIPT_SCHEMA = "review-hook-plugin-state-receipt/v1"
MANIFEST_NAME = "BUNDLE-MANIFEST.json"

# Versions record what each adapter's fixtures were captured against; newer CLIs are not blocked.
SUPPORTED_HOST_CLI = {
    "codex": ("codex", "codex-cli 0.160.0"),
    "kimi": ("kimi", "0.39.1"),
    "antigravity": ("agy", "1.1.22"),
}
LEGACY_CORE_SHA256 = "98989c6d33b2d3a5155ace9086d73682f8c15f42201167e5301f90a2a2ffaa35"
RUFF_ASSET_SHA256 = "515c8e5e3c8c3cd9785f421e050c98748420aae9a02459b7232c89a46bbadba4"
RUFF_VERSION = "ruff 0.16.5"
ANALYZER_VERSION = "review-scan-v1"
MODE_CONTRACT = "review-modes/v1"
REVIEW_SCAN_POLICY_SCHEMA = "review-scan-policy/v1"
REVIEW_SCAN_CODES = frozenset(
    {
        "F601",
        "F634",
        "PLE0101",
        "PLE0704",
        "PLE1205",
        "PLE1206",
        "B006",
        "B012",
        "B023",
        "B029",
        "B030",
        "B031",
        "C901",
        "PLR0912",
        "PLR0915",
        "PLR1702",
        "PLR0916",
    }
)
REVIEW_SCAN_CORRECTNESS_CODES = frozenset(
    {
        "F601",
        "F634",
        "PLE0101",
        "PLE0704",
        "PLE1205",
        "PLE1206",
        "B006",
        "B012",
        "B023",
        "B029",
        "B030",
        "B031",
    }
)
REVIEW_SCAN_STRUCTURAL_CODES = frozenset(
    {"C901", "PLR0912", "PLR0915", "PLR1702", "PLR0916"}
)
REVIEW_SCAN_DESIGN_CODES = frozenset(
    {
        "CLASS_SURFACE_GROWTH",
        "DEAD_CODE_GROWTH",
        "DISJOINT_RESPONSIBILITY_GROWTH",
        "INTERFACE_SURFACE_GROWTH",
        "NEW_CYCLIC_IMPORT",
        "PARAMETER_CLUMP_GROWTH",
        "PARAMETER_PROPAGATION_GROWTH",
        "REPEATED_CROSS_FILE_CHANGE",
        "REPEATED_INTERFACE_STUB_GROWTH",
        "SCATTERED_SMALL_EDIT",
        "THIN_DELEGATION_LAYER_GROWTH",
    }
)

COMMON_FILES = (
    "scripts/review_hook.py",
    "runtime/__init__.py",
    "runtime/analysis/__init__.py",
    "runtime/analysis/ast_spans.py",
    "runtime/analysis/outcomes.py",
    "runtime/analysis/design_signals.py",
    "runtime/analysis/evidence_package.py",
    "runtime/analysis/git_snapshot.py",
    "runtime/analysis/model.py",
    "runtime/analysis/python_target.py",
    "runtime/analysis/ruff_runner.py",
    "runtime/analysis/structural_policy.py",
    "runtime/delivery.py",
    "runtime/operational_state.py",
    "runtime/operational_health.py",
    "runtime/review_core.py",
    "runtime/review_request.py",
    "runtime/prompts/review-current-branch-diff.txt",
    "runtime/prompts/review-most-recent-commit.txt",
    "runtime/prompts/review-python-signals.txt",
    "policy/auto-attention-v1.json",
    "policy/review-scan-suite.json",
    "policy/signals.ruff.toml",
    "assets/ruff",
    "assets/ruff.LICENSE",
    "assets/ruff.PROVENANCE.json",
    "shell/review-after-commit.bash",
)
HOST_FILES = {
    "codex": {
        "hosts/codex/adapter.py": "hosts/codex/adapter.py",
        "hosts/codex/__init__.py": "hosts/codex/__init__.py",
        "hosts/codex/profile.config.toml": "profile.config.toml",
        "hosts/codex/hooks.json": "hooks/hooks.json",
        "hosts/codex/plugin/.codex-plugin/plugin.json": ".codex-plugin/plugin.json",
    },
    "kimi": {
        "hosts/kimi/adapter.py": "hosts/kimi/adapter.py",
        "hosts/kimi/__init__.py": "hosts/kimi/__init__.py",
    },
    "antigravity": {
        "hosts/antigravity/plugin/adapter.py": "adapter.py",
        "hosts/antigravity/plugin/antigravity_state.py": "antigravity_state.py",
        "hosts/antigravity/plugin/hooks.json": "hooks.json",
        "hosts/antigravity/plugin/plugin.json": "plugin.json",
    },
}
EXECUTABLE_DESTINATIONS = frozenset(
    (
        "assets/ruff",
        "scripts/review_hook.py",
        "hosts/codex/adapter.py",
        "hosts/kimi/adapter.py",
        "adapter.py",
    )
)


class ManagementError(RuntimeError):
    """A management operation could not preserve its safety contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _projection(host: str) -> Dict[str, str]:
    if host not in HOST_FILES:
        raise ManagementError(
            "{} installation is unavailable until its host contract is proven".format(
                host
            )
        )
    projection = {path: path for path in COMMON_FILES}
    projection.update(HOST_FILES[host])
    return projection


def _expected_mode(destination: str) -> int:
    return 0o755 if destination in EXECUTABLE_DESTINATIONS else 0o644


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _host_cli_version(host: str) -> str:
    resolved = shutil.which(SUPPORTED_HOST_CLI[host][0])
    if resolved is None:
        raise ManagementError("{} CLI is unavailable".format(host))
    result = subprocess.run(
        [resolved, "--version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    actual = (result.stdout or result.stderr).strip()
    if result.returncode != 0 or not actual:
        raise ManagementError("{} CLI failed to report its version".format(host))
    return actual


def _validate_profile(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = (
        "[[hooks.PreToolUse]]",
        "[[hooks.PostToolUse]]",
        "hosts/codex/adapter.py",
        "/usr/bin/python3 -B",
    )
    if any(item not in text for item in required):
        raise ManagementError("Codex profile template is missing its static hook contract")
    if "[hooks.state" in text or "trusted_hash" in text:
        raise ManagementError("Codex profile template contains machine-local trust state")
    if "REVIEW_AFTER_COMMIT_MODE=" in text:
        raise ManagementError("Codex profile template overrides the selected review mode")


def _adapter_source(host: str) -> str:
    return {
        "codex": "hosts/codex/adapter.py",
        "kimi": "hosts/kimi/adapter.py",
        "antigravity": "adapter.py",
    }[host]


def _validate_antigravity_source(root: Path) -> None:
    plugin = _load_json_object(root / "plugin.json")
    if set(plugin) != {"$schema", "name", "description"}:
        raise ManagementError("Antigravity plugin manifest has unsupported fields")
    if (
        plugin["$schema"] != "https://antigravity.google/schemas/v1/plugin.json"
        or plugin["name"] != "review-after-commit"
        or not isinstance(plugin["description"], str)
        or not plugin["description"]
    ):
        raise ManagementError("Antigravity plugin manifest is incompatible")
    hooks = _load_json_object(root / "hooks.json")
    if set(hooks) != {"review-after-commit"}:
        raise ManagementError("Antigravity hook namespace is incompatible")
    definition = hooks["review-after-commit"]
    if not isinstance(definition, dict) or set(definition) != {
        "PreInvocation",
        "PostToolUse",
    }:
        raise ManagementError(
            "Antigravity production hooks must use only PreInvocation and PostToolUse"
        )
    pre = definition["PreInvocation"]
    post = definition["PostToolUse"]
    if (
        not isinstance(pre, list)
        or len(pre) != 1
        or not isinstance(pre[0], dict)
        or pre[0].get("type") != "command"
        or pre[0].get("command")
        != "exec /usr/bin/python3 -B ./adapter.py pre-invocation"
        or type(pre[0].get("timeout")) is not int
        or not isinstance(post, list)
        or len(post) != 1
        or not isinstance(post[0], dict)
        or post[0].get("matcher") != "run_command"
        or not isinstance(post[0].get("hooks"), list)
        or len(post[0]["hooks"]) != 1
        or post[0]["hooks"][0].get("type") != "command"
        or post[0]["hooks"][0].get("command")
        != "exec /usr/bin/python3 -B ./adapter.py post-tool-use"
        or type(post[0]["hooks"][0].get("timeout")) is not int
    ):
        raise ManagementError("Antigravity hook handlers are incompatible")
    serialized = json.dumps(hooks, sort_keys=True)
    if any(name in serialized for name in ("PreToolUse", "PostInvocation", "Stop")):
        raise ManagementError("Antigravity plugin would alter permission or continuation")


def _load_json_object(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ManagementError("JSON contract is missing or malformed: {}".format(path)) from error
    if not isinstance(value, dict):
        raise ManagementError("JSON contract must be an object: {}".format(path))
    return value


def _validate_review_scan_sources() -> None:
    asset = SOURCE_ROOT / "assets/ruff"
    if _sha256(asset) != RUFF_ASSET_SHA256:
        raise ManagementError("bundled Ruff asset differs from its pinned digest")
    version = subprocess.run(
        [str(asset), "--version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    if version.returncode != 0 or version.stdout.strip() != RUFF_VERSION:
        raise ManagementError(
            "bundled Ruff contract expected {!r}, found {!r}".format(
                RUFF_VERSION, (version.stdout or version.stderr).strip()
            )
        )
    provenance = _load_json_object(SOURCE_ROOT / "assets/ruff.PROVENANCE.json")
    if (
        provenance.get("artifact_sha256") != RUFF_ASSET_SHA256
        or provenance.get("version_output") != RUFF_VERSION
        or provenance.get("platform") != "darwin-arm64"
    ):
        raise ManagementError("bundled Ruff provenance does not match the asset contract")

    auto = _load_json_object(SOURCE_ROOT / "policy/auto-attention-v1.json")
    suite = _load_json_object(SOURCE_ROOT / "policy/review-scan-suite.json")
    for name, policy in (("auto-attention-v1", auto), ("review-scan-suite", suite)):
        if (
            policy.get("schema") != REVIEW_SCAN_POLICY_SCHEMA
            or policy.get("name") != name
            or policy.get("version") != "v1"
        ):
            raise ManagementError("{} has an invalid policy identity".format(name))
    if (
        auto["automatic_delivery"] is not True
        or auto.get("status") != "dogfood-active"
        or "promotion_requirements" in auto
    ):
        raise ManagementError("auto-attention-v1 must remain active for dogfooding")
    if "automatic_delivery" in suite:
        raise ManagementError("the Review Scan suite is evidence only and must not own delivery")
    if (
        set(suite.get("correctness_codes", ())) != REVIEW_SCAN_CORRECTNESS_CODES
        or set(suite.get("report_only_correctness_codes", ()))
        != {"B023", "PLE1205"}
        or set(suite.get("structural_codes", ())) != REVIEW_SCAN_STRUCTURAL_CODES
        or set(suite.get("design_review_codes", ())) != REVIEW_SCAN_DESIGN_CODES
        or set(suite.get("design_context_codes", ()))
        != {"LOW_USAGE_INTERFACE_GROWTH"}
    ):
        raise ManagementError("the Review Scan suite code manifest is incomplete")

    config = SOURCE_ROOT / "policy/signals.ruff.toml"
    text = config.read_text(encoding="utf-8")
    selected = re.findall(r'^\s*"([A-Z][A-Z0-9]+)",\s*$', text, re.MULTILINE)
    required_fragments = (
        "preview = true",
        "max-complexity = 10",
        "max-branches = 12",
        "max-statements = 50",
        "max-nested-blocks = 5",
        "max-bool-expr = 5",
    )
    if (
        len(selected) != len(set(selected))
        or set(selected) != REVIEW_SCAN_CODES
        or any(fragment not in text for fragment in required_fragments)
        or "target-version" in text
    ):
        raise ManagementError("Review Scan Ruff policy differs from its isolated contract")
    contract_probe = subprocess.run(
        [
            str(asset),
            "check",
            "--config",
            str(config),
            "--target-version",
            "py313",
            "--output-format",
            "json",
            "--exit-zero",
            "--no-cache",
            "-",
        ],
        input="",
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if contract_probe.returncode != 0 or contract_probe.stdout.strip() != "[]":
        raise ManagementError("bundled Ruff cannot parse the isolated policy contract")


def _validate_source(host: str) -> Dict[str, str]:
    _validate_review_scan_sources()
    projection = _projection(host)
    source_hashes: Dict[str, str] = {}
    for source_name, destination in projection.items():
        source = SOURCE_ROOT / source_name
        if not source.is_file() or source.is_symlink():
            raise ManagementError("required source is not an ordinary file: {}".format(source))
        mode = stat.S_IMODE(source.stat().st_mode)
        expected_mode = _expected_mode(destination)
        if mode != expected_mode:
            raise ManagementError(
                "source mode for {} is {:o}, expected {:o}".format(
                    source_name, mode, expected_mode
                )
            )
        source_hashes[destination] = _sha256(source)
        if source.suffix == ".py":
            compile(source.read_text(encoding="utf-8"), str(source), "exec")
        elif source.suffix == ".json":
            json.loads(source.read_text(encoding="utf-8"))
    for prompt_name in (
        "runtime/prompts/review-current-branch-diff.txt",
        "runtime/prompts/review-most-recent-commit.txt",
        "runtime/prompts/review-python-signals.txt",
    ):
        prompt = (SOURCE_ROOT / prompt_name).read_text(encoding="utf-8").strip()
        if len(prompt) < 100 or "read-only advisory review" not in prompt:
            raise ManagementError("prompt lacks the read-only advisory contract: {}".format(prompt_name))
        if "code-reviews/" in prompt or "Write the review" in prompt:
            raise ManagementError("prompt retains a target-mutation instruction: {}".format(prompt_name))
    if host == "codex":
        _validate_profile(SOURCE_ROOT / "hosts/codex/profile.config.toml")
    elif host == "antigravity":
        _validate_antigravity_source(
            SOURCE_ROOT / "hosts/antigravity/plugin"
        )
    shell = (SOURCE_ROOT / "shell/review-after-commit.bash").read_text(
        encoding="utf-8"
    )
    required_shell_contract = (
        "review_after_commit_parse()",
        "review_after_commit_export_environment()",
        "review_after_commit_bundle_path()",
        "review_after_commit_append_kimi_config()",
        "review_after_commit_dispatch()",
    )
    if any(item not in shell for item in required_shell_contract):
        raise ManagementError("shell fragment is missing its launcher contract")
    return source_hashes


def expected_manifest(host: str) -> Dict[str, Any]:
    source_hashes = _validate_source(host)
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    from runtime.review_core import EXPECTED_DIFF_REVIEW

    policy_hashes = {
        name: source_hashes[name]
        for name in (
            "policy/auto-attention-v1.json",
            "policy/review-scan-suite.json",
            "policy/signals.ruff.toml",
        )
    }
    body = {
        "schema": MANIFEST_SCHEMA,
        "host": host,
        "runtime_contract": "review-request/v1",
        "evidence_contract": "review-evidence/v2",
        "mode_contract": MODE_CONTRACT,
        "analyzer_version": ANALYZER_VERSION,
        "ruff_version": RUFF_VERSION,
        "python_target_policy": {
            "supported": ["py312", "py313", "py314"],
            "fleet_fallback": "py313",
        },
        "expected_skill": asdict(EXPECTED_DIFF_REVIEW),
        "policy_hashes": policy_hashes,
        "host_cli": SUPPORTED_HOST_CLI[host][1],
        "files": source_hashes,
        "modes": {destination: _expected_mode(destination) for destination in source_hashes},
    }
    body["bundle_digest"] = "sha256:" + hashlib.sha256(_json_bytes(body)).hexdigest()
    return body


def _managed_files(root: Path) -> List[str]:
    files = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ManagementError("managed bundle contains a symlink: {}".format(path))
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return sorted(files)


def validate_bundle(root: Path, expected: Mapping[str, Any]) -> None:
    if not root.is_dir() or root.is_symlink():
        raise ManagementError("bundle root is not an ordinary directory: {}".format(root))
    manifest_path = root / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ManagementError("bundle manifest is missing or malformed") from error
    if manifest != expected:
        raise ManagementError("bundle manifest does not match the validated source")
    expected_files = sorted([*expected["files"], MANIFEST_NAME])
    if _managed_files(root) != expected_files:
        raise ManagementError("bundle contains files outside its host allowlist")
    for relative, digest in expected["files"].items():
        path = root / relative
        if not path.is_file() or path.is_symlink() or _sha256(path) != digest:
            raise ManagementError("bundle file differs from its manifest: {}".format(relative))
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != expected["modes"][relative]:
            raise ManagementError("bundle mode differs from its manifest: {}".format(relative))
        if path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        elif path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
    if stat.S_IMODE(manifest_path.stat().st_mode) != 0o644:
        raise ManagementError("bundle manifest mode must be 0644")
    if expected["host"] == "codex":
        _validate_profile(root / "profile.config.toml")
    elif expected["host"] == "antigravity":
        _validate_antigravity_source(root)


def _validate_host_bundle_cli(host: str, root: Path) -> None:
    if host != "antigravity":
        return
    executable = shutil.which(SUPPORTED_HOST_CLI[host][0])
    if executable is None:
        raise ManagementError("antigravity CLI is unavailable")
    with tempfile.TemporaryDirectory(prefix="review-antigravity-validate-home-") as home:
        environment = os.environ.copy()
        environment["HOME"] = home
        result = subprocess.run(
            [executable, "plugin", "validate", str(root)],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
            env=environment,
        )
    if result.returncode != 0:
        raise ManagementError("Antigravity CLI rejected the staged plugin bundle")


def build_bundle(host: str, destination: Path, expected: Mapping[str, Any]) -> None:
    if destination.exists() or destination.is_symlink():
        raise ManagementError("staging destination already exists: {}".format(destination))
    destination.mkdir(mode=0o755, parents=True)
    projection = _projection(host)
    for source_name, relative in projection.items():
        source = SOURCE_ROOT / source_name
        target = destination / relative
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(source, target, follow_symlinks=False)
        os.chmod(target, _expected_mode(relative))
    manifest_path = destination / MANIFEST_NAME
    manifest_path.write_bytes(_json_bytes(expected))
    os.chmod(manifest_path, 0o644)
    validate_bundle(destination, expected)


def validate_sources(hosts: Sequence[str]) -> Dict[str, Any]:
    results = {}
    for host in hosts:
        cli_version = _host_cli_version(host)
        expected = expected_manifest(host)
        with tempfile.TemporaryDirectory(prefix="review-hook-validate-") as temporary:
            bundle = Path(temporary) / "review-after-commit"
            build_bundle(host, bundle, expected)
            _validate_host_bundle_cli(host, bundle)
        results[host] = {
            "bundle_digest": expected["bundle_digest"],
            "host_cli": cli_version,
            "files": len(expected["files"]),
        }
    return results


def _default_home(host: str) -> Path:
    if host == "codex":
        return Path(os.environ.get("CODEX_CANONICAL_HOME", str(Path.home() / ".codex")))
    if host == "kimi":
        return Path(os.environ.get("KIMI_CANONICAL_HOME", str(Path.home() / ".kimi-code")))
    if host == "antigravity":
        return Path(
            os.environ.get(
                "ANTIGRAVITY_CONFIG_HOME",
                str(Path.home() / ".gemini" / "config"),
            )
        )
    raise ManagementError("unsupported host: {}".format(host))


def destination_for(host: str, home: Path) -> Path:
    if host in ("codex", "kimi"):
        return home / "hooks" / "review-after-commit"
    if host == "antigravity":
        return home / "plugins" / "review-after-commit"
    raise ManagementError("unsupported host: {}".format(host))


def control_root(home: Path) -> Path:
    return home / ".review-after-commit-installer"


def _antigravity_registry_paths(home: Path) -> Tuple[Path, Path]:
    return home / "config.json", home / "import_manifest.json"


def _read_shared_json(path: Path, default: Mapping[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return dict(default)
    if path.is_symlink() or not path.is_file():
        raise ManagementError("shared host file is not an ordinary file: {}".format(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ManagementError("shared host file is malformed: {}".format(path)) from error
    if not isinstance(value, dict):
        raise ManagementError("shared host file must be an object: {}".format(path))
    return value


def _antigravity_registry(home: Path) -> Dict[str, Any]:
    config_path, imports_path = _antigravity_registry_paths(home)
    config = _read_shared_json(config_path, {})
    plugins = config.get("plugins", {})
    if not isinstance(plugins, dict):
        raise ManagementError("Antigravity config.json plugins must be an object")
    preference = plugins.get("review-after-commit")
    if preference is not None and (
        not isinstance(preference, dict)
        or set(preference) != {"enabled"}
        or type(preference["enabled"]) is not bool
    ):
        raise ManagementError(
            "Antigravity config.json review-after-commit entry is incompatible"
        )

    manifest = _read_shared_json(imports_path, {"imports": []})
    imports = manifest.get("imports")
    if not isinstance(imports, list) or any(not isinstance(item, dict) for item in imports):
        raise ManagementError("Antigravity import_manifest.json imports must be a list")
    matches = [item for item in imports if item.get("name") == "review-after-commit"]
    if len(matches) > 1:
        raise ManagementError("Antigravity import_manifest.json has duplicate plugin entries")
    registered = bool(matches)
    if registered:
        entry = matches[0]
        if (
            entry.get("source") != "antigravity"
            or entry.get("components") != ["hooks"]
            or not isinstance(entry.get("importedAt"), str)
            or not entry["importedAt"]
        ):
            raise ManagementError(
                "Antigravity import_manifest.json plugin entry is incompatible"
            )
    return {
        "config": config,
        "manifest": manifest,
        "preference_present": preference is not None,
        "enabled": preference.get("enabled") if preference is not None else None,
        "registered": registered,
    }


def _snapshot_file(path: Path) -> Optional[bytes]:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ManagementError("shared host file is not an ordinary file: {}".format(path))
    return path.read_bytes()


def _restore_file(path: Path, payload: Optional[bytes]) -> None:
    if payload is None:
        path.unlink(missing_ok=True)
        if path.parent.exists():
            _fsync_directory(path.parent)
    else:
        _write_bytes_atomic(path, payload, 0o600)


def _write_antigravity_registry(
    home: Path,
    *,
    enabled: bool,
    imported_at: Optional[str] = None,
) -> Dict[str, str]:
    registry = _antigravity_registry(home)
    config = dict(registry["config"])
    plugins = dict(config.get("plugins", {}))
    plugins["review-after-commit"] = {"enabled": enabled}
    config["plugins"] = plugins

    manifest = dict(registry["manifest"])
    imports = list(manifest.get("imports", []))
    matches = [index for index, item in enumerate(imports) if item.get("name") == "review-after-commit"]
    entry = {
        "name": "review-after-commit",
        "source": "antigravity",
        "importedAt": imported_at
        or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "components": ["hooks"],
    }
    if matches:
        existing = imports[matches[0]]
        entry["importedAt"] = existing["importedAt"]
        imports[matches[0]] = entry
    else:
        imports.append(entry)
    manifest["imports"] = imports

    config_path, imports_path = _antigravity_registry_paths(home)
    _write_json_atomic(config_path, config)
    _write_json_atomic(imports_path, manifest)
    return {
        "config_digest": _digest_bytes(config_path.read_bytes()),
        "imports_digest": _digest_bytes(imports_path.read_bytes()),
    }


def _lexists(path: Path) -> bool:
    return os.path.lexists(str(path))


def _installed_manifest(destination: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads((destination / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _classify_managed_root(
    host: str,
    root: Path,
    expected: Optional[Mapping[str, Any]],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    manifest = _installed_manifest(root)
    if manifest is None:
        result["status"] = "unrecognized"
        result["reason"] = "managed target has no readable manifest"
        return result
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("host") != host:
        result["status"] = "contract-incompatible"
        result["reason"] = "managed manifest schema or host is incompatible"
        return result
    files = manifest.get("files")
    modes = manifest.get("modes")
    if not isinstance(files, dict) or not isinstance(modes, dict):
        result["status"] = "contract-incompatible"
        result["reason"] = "managed manifest lacks file or mode maps"
        return result
    if any(not isinstance(name, str) or not _safe_relative_path(name) for name in files):
        result["status"] = "contract-incompatible"
        result["reason"] = "managed manifest contains an unsafe path"
        return result
    try:
        actual_files = _managed_files(root)
    except ManagementError as error:
        result["status"] = "locally-modified"
        result["reason"] = str(error)
        return result
    if actual_files != sorted([*files, MANIFEST_NAME]):
        result["status"] = "locally-modified"
        result["reason"] = "managed file set changed"
        return result
    for relative, digest in files.items():
        path = root / relative
        if (
            not isinstance(digest, str)
            or not path.is_file()
            or path.is_symlink()
            or _sha256(path) != digest
            or modes.get(relative) != stat.S_IMODE(path.stat().st_mode)
        ):
            result["status"] = "locally-modified"
            result["reason"] = "managed content or mode changed at {}".format(relative)
            return result
    result["installed_bundle_digest"] = manifest.get("bundle_digest")
    result["managed_target"] = str(root)
    if expected is not None and manifest == expected:
        result["status"] = "current"
    else:
        result["status"] = "stale"
    return result


def classify(host: str, home: Path, expected: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    destination = destination_for(host, home)
    result: Dict[str, Any] = {"host": host, "home": str(home), "destination": str(destination)}
    registry = _antigravity_registry(home) if host == "antigravity" else None
    if not _lexists(destination):
        if registry is not None and (
            registry["registered"] or registry["preference_present"]
        ):
            result["status"] = "broken"
            result["reason"] = "Antigravity plugin registration exists without its bundle"
            result["plugin"] = {
                "registered": registry["registered"],
                "enabled": registry["enabled"],
                "dormant_without_selection": True,
            }
            return result
        result["status"] = "absent"
        return result
    if destination.is_symlink():
        if not destination.exists():
            result["status"] = "broken"
            result["reason"] = "broken destination symlink"
            return result
        target = destination.resolve()
        if (target / MANIFEST_NAME).is_file():
            managed = _classify_managed_root(host, target, expected, result)
            if registry is None:
                return managed
            managed["plugin"] = {
                "registered": registry["registered"],
                "enabled": registry["enabled"],
                "dormant_without_selection": True,
            }
            if not registry["registered"] or registry["enabled"] is None:
                managed["status"] = "contract-incompatible"
                managed["reason"] = (
                    "Antigravity plugin registration or explicit enablement is missing"
                )
            elif managed["status"] == "current" and not registry["enabled"]:
                managed["status"] = "installed-disabled"
            elif managed["status"] == "stale" and not registry["enabled"]:
                managed["status"] = "stale-disabled"
            return managed
        legacy_core = destination / "review_after_commit_core.py"
        if legacy_core.is_file() and _sha256(legacy_core) == LEGACY_CORE_SHA256:
            result["status"] = "legacy-symlink"
            result["legacy_target"] = os.readlink(str(destination))
            return result
        result["status"] = "unrecognized"
        result["reason"] = "destination symlink is not the frozen legacy source"
        return result
    if not destination.is_dir():
        result["status"] = "broken"
        result["reason"] = "destination is not a directory"
        return result
    if (destination / MANIFEST_NAME).is_file():
        result["status"] = "contract-incompatible"
        result["reason"] = "managed activation must be an atomic release pointer"
    else:
        result["status"] = "unrecognized"
        result["reason"] = "ordinary directory has no managed manifest"
    return result


def inspect_status(host: str, home: Path) -> Dict[str, Any]:
    """Report destination ownership separately from the live host contract."""
    expected = expected_manifest(host)
    result = classify(host, home, expected)
    result["source_contract"] = {
        "bundle_digest": expected["bundle_digest"],
        "runtime_digest": expected["files"]["runtime/review_core.py"],
        "adapter_digest": expected["files"][_adapter_source(host)],
        "policy_hashes": dict(expected["policy_hashes"]),
        "schemas": {
            "manifest": expected["schema"],
            "request": expected["runtime_contract"],
            "evidence": expected["evidence_contract"],
            "modes": expected["mode_contract"],
        },
        "ruff_version": expected["ruff_version"],
        "analyzer_version": expected["analyzer_version"],
        "python_target_policy": dict(expected["python_target_policy"]),
        "expected_skill": dict(expected["expected_skill"]),
    }
    runtime_home = (
        Path(
            os.environ.get(
                "ANTIGRAVITY_RUNTIME_HOME",
                str(home.parent / "antigravity-cli"),
            )
        )
        if host == "antigravity"
        else home
    )
    runtime_root = runtime_home / "hook-state" / "review-after-commit"
    operational_root = runtime_root / "operational"
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    try:
        from runtime.operational_health import OperationalJournal

        runtime_summary = OperationalJournal(operational_root).summary()
    except (OSError, TypeError, ValueError) as error:
        runtime_summary = {
            "status": "error",
            "reason": "operational health summary is malformed or unavailable",
            "error_type": type(error).__name__,
        }
    result["runtime"] = runtime_summary
    if host == "antigravity":
        try:
            from hosts.antigravity.plugin.antigravity_state import (
                AntigravityDeliveryStore,
            )

            result["pending_delivery"] = AntigravityDeliveryStore(
                runtime_root / "delivery"
            ).summary()
        except (OSError, TypeError, ValueError) as error:
            result["pending_delivery"] = {
                "status": "error",
                "reason": "Antigravity delivery history is malformed or unavailable",
                "error_type": type(error).__name__,
            }
    captured_cli = SUPPORTED_HOST_CLI[host][1]
    try:
        actual_cli = _host_cli_version(host)
    except (ManagementError, OSError, subprocess.SubprocessError) as error:
        result["host_contract"] = {
            "status": "unavailable",
            "captured_cli": captured_cli,
            "reason": str(error),
        }
    else:
        result["host_contract"] = {
            "status": "available",
            "captured_cli": captured_cli,
            "actual_cli": actual_cli,
        }
    return result


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _installer_lock(host: str, home: Path):
    lock_path = control_root(home) / "locks" / "{}.lock".format(host)
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def _status_fingerprint(status: Mapping[str, Any]) -> Tuple[Any, ...]:
    return (
        status.get("status"),
        status.get("installed_bundle_digest"),
        status.get("managed_target"),
        status.get("legacy_target"),
        status.get("reason"),
    )


def _make_symlink(target: Path, link: Path, relative_to: Path) -> None:
    raw_target = os.path.relpath(
        str(target.resolve()),
        str(relative_to.resolve()),
    )
    os.symlink(raw_target, link)


def _copy_symlink(source: Path, destination: Path) -> None:
    if not source.is_symlink():
        raise ManagementError("expected an activation symlink: {}".format(source))
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _make_symlink(source.resolve(), destination, destination.parent)


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _json_bytes(value), 0o600)


def _write_bytes_atomic(path: Path, value: bytes, mode: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=".{}.".format(path.name), dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, mode)
        with os.fdopen(handle, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _profile_sections(value: bytes) -> Tuple[bytes, bytes]:
    marker = b"\n[hooks.state"
    marker_index = value.find(marker)
    if marker_index < 0:
        return value, b""
    return value[:marker_index].rstrip() + b"\n", value[marker_index:]


def _profile_receipt(
    receipt_path: Path, profile_path: Path, static_prefix: bytes
) -> Dict[str, Any]:
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ManagementError("existing selected-home profile has no ownership receipt")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ManagementError("selected-home profile receipt is malformed") from error
    preimage = receipt.get("preimage") if isinstance(receipt, dict) else None
    valid_preimage = (
        isinstance(preimage, dict)
        and (
            (
                set(preimage) == {"kind"}
                and preimage.get("kind") == "absent"
            )
            or (
                set(preimage) == {"kind", "target"}
                and preimage.get("kind") == "symlink"
                and isinstance(preimage.get("target"), str)
                and bool(preimage["target"])
            )
        )
    )
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != PROFILE_RECEIPT_SCHEMA
        or receipt.get("profile") != str(profile_path)
        or receipt.get("static_digest") != _digest_bytes(static_prefix)
        or not valid_preimage
    ):
        raise ManagementError("selected-home static profile was modified locally")
    return receipt


def materialize_codex_profile(
    canonical_home: Path, selected_home: Path, apply: bool
) -> Dict[str, Any]:
    if apply:
        _materialize_codex_profile_unlocked(canonical_home, selected_home, False)
        with _installer_lock("codex-profile", selected_home):
            return _materialize_codex_profile_unlocked(
                canonical_home, selected_home, apply
            )
    return _materialize_codex_profile_unlocked(canonical_home, selected_home, apply)


def _materialize_codex_profile_unlocked(
    canonical_home: Path, selected_home: Path, apply: bool
) -> Dict[str, Any]:
    expected = _management_manifest("codex")
    canonical_status = classify("codex", canonical_home, expected)
    if canonical_status["status"] != "current":
        raise ManagementError(
            "Codex profile materialization requires a current canonical bundle"
        )
    template_path = destination_for("codex", canonical_home) / "profile.config.toml"
    template = template_path.read_bytes()
    _validate_profile(template_path)
    profile_path = selected_home / "review-after-commit.config.toml"
    receipt_path = selected_home / "review-after-commit.profile-receipt.json"
    if receipt_path.is_symlink():
        raise ManagementError("selected-home profile receipt must not be a symlink")

    legacy_target: Optional[str] = None
    if profile_path.is_symlink():
        legacy_target = os.readlink(profile_path)
        if legacy_target != str(template_path):
            raise ManagementError("refusing unknown profile symlink")
        if receipt_path.exists():
            raise ManagementError("legacy profile symlink has an unexpected receipt")
        existed = True
        existing = template
        preimage = {"kind": "symlink", "target": legacy_target}
    elif profile_path.exists():
        if not profile_path.is_file():
            raise ManagementError("selected-home profile must be an ordinary file")
        existed = True
        existing = profile_path.read_bytes()
        static_prefix, _ = _profile_sections(existing)
        receipt = _profile_receipt(receipt_path, profile_path, static_prefix)
        preimage = receipt["preimage"]
    else:
        if _lexists(profile_path):
            raise ManagementError("selected-home profile path is unsupported")
        if receipt_path.exists():
            raise ManagementError("selected-home profile receipt exists without its profile")
        existed = False
        existing = b""
        preimage = {"kind": "absent"}

    static_prefix, trust_suffix = _profile_sections(existing)

    new_profile = template.rstrip() + b"\n" + trust_suffix
    action = (
        "migrate-legacy-symlink"
        if legacy_target is not None
        else "none" if existed and new_profile == existing else "materialize"
    )
    result = {
        "apply": apply,
        "profile": str(profile_path),
        "action": action,
        "trust_suffix_preserved": bool(trust_suffix),
        "preimage": dict(preimage),
    }
    if not apply or result["action"] == "none":
        return result

    old_receipt = receipt_path.read_bytes() if receipt_path.exists() else None
    profile_receipt = {
        "schema": PROFILE_RECEIPT_SCHEMA,
        "profile": str(profile_path),
        "static_digest": _digest_bytes(template.rstrip() + b"\n"),
        "preimage": dict(preimage),
        "materialized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        _write_bytes_atomic(profile_path, new_profile, 0o600)
        _write_json_atomic(receipt_path, profile_receipt)
    except Exception:
        if legacy_target is not None:
            profile_path.unlink(missing_ok=True)
            os.symlink(legacy_target, profile_path)
            _fsync_directory(profile_path.parent)
        elif existed:
            _write_bytes_atomic(profile_path, existing, 0o600)
        else:
            profile_path.unlink(missing_ok=True)
        if old_receipt is not None:
            _write_bytes_atomic(receipt_path, old_receipt, 0o600)
        else:
            receipt_path.unlink(missing_ok=True)
        raise
    return result


def _management_manifest(host: str) -> Dict[str, Any]:
    manifest_path = SOURCE_ROOT / MANIFEST_NAME
    if not manifest_path.exists():
        return expected_manifest(host)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ManagementError("installed management manifest is not an ordinary file")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ManagementError("installed management manifest is malformed") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("host") != host
    ):
        raise ManagementError(
            "installed management manifest is not a {} bundle".format(host)
        )
    validate_bundle(SOURCE_ROOT, manifest)
    return manifest


def rollback_codex_profile(selected_home: Path, apply: bool) -> Dict[str, Any]:
    if apply:
        _rollback_codex_profile_unlocked(selected_home, False)
        with _installer_lock("codex-profile", selected_home):
            return _rollback_codex_profile_unlocked(selected_home, True)
    return _rollback_codex_profile_unlocked(selected_home, False)


def _rollback_codex_profile_unlocked(
    selected_home: Path, apply: bool
) -> Dict[str, Any]:
    profile_path = selected_home / "review-after-commit.config.toml"
    receipt_path = selected_home / "review-after-commit.profile-receipt.json"
    if profile_path.is_symlink() or not profile_path.is_file():
        raise ManagementError("managed selected-home profile is not an ordinary file")
    profile = profile_path.read_bytes()
    static_prefix, trust_suffix = _profile_sections(profile)
    receipt = _profile_receipt(receipt_path, profile_path, static_prefix)
    preimage = receipt["preimage"]
    restore = preimage["kind"]
    result = {
        "apply": apply,
        "profile": str(profile_path),
        "restore": restore,
        "trust_suffix_backed_up": bool(trust_suffix),
    }
    if not apply:
        return result

    transaction = _transaction_id("codex-profile")
    backup_dir = control_root(selected_home) / "profile-backups" / transaction
    backup_dir.mkdir(mode=0o700, parents=True)
    backup_profile = backup_dir / "profile.config.toml"
    backup_receipt = backup_dir / "profile-receipt.json"
    temporary_link = profile_path.parent / ".review-after-commit-profile-{}.link".format(
        transaction
    )
    profile_moved = False
    receipt_moved = False
    restored_link = False
    try:
        os.replace(profile_path, backup_profile)
        profile_moved = True
        if restore == "symlink":
            os.symlink(preimage["target"], temporary_link)
            os.replace(temporary_link, profile_path)
            restored_link = True
        os.replace(receipt_path, backup_receipt)
        receipt_moved = True
        _fsync_directory(profile_path.parent)
        _fsync_directory(backup_dir)
    except Exception:
        temporary_link.unlink(missing_ok=True)
        if receipt_moved and not receipt_path.exists():
            os.replace(backup_receipt, receipt_path)
        if restored_link and profile_path.is_symlink():
            profile_path.unlink()
        if profile_moved and not _lexists(profile_path):
            os.replace(backup_profile, profile_path)
        if profile_path.parent.exists():
            _fsync_directory(profile_path.parent)
        raise
    result["backup_profile"] = str(backup_profile)
    result["backup_receipt"] = str(backup_receipt)
    return result


_KIMI_CONFIG_NAMES = (
    "config.toml",
    ".canonical-config.sha256",
    ".generated-config.sha256",
)


def _owned_file_snapshot(path: Path) -> Optional[Tuple[bytes, int]]:
    if not _lexists(path):
        return None
    if path.is_symlink() or not path.is_file():
        raise ManagementError("managed file is not an ordinary file: {}".format(path))
    return path.read_bytes(), stat.S_IMODE(path.stat().st_mode)


def _restore_owned_snapshot(
    path: Path, snapshot: Optional[Tuple[bytes, int]]
) -> None:
    if snapshot is None:
        path.unlink(missing_ok=True)
        if path.parent.exists():
            _fsync_directory(path.parent)
        return
    payload, mode = snapshot
    _write_bytes_atomic(path, payload, mode)


def _validate_desired_kimi_config(
    canonical_config: Path, desired_config: Path
) -> Tuple[bytes, bytes]:
    for path, label in (
        (canonical_config, "canonical Kimi config"),
        (desired_config, "desired Kimi config"),
    ):
        if path.is_symlink() or not path.is_file():
            raise ManagementError("{} is not an ordinary file".format(label))
    canonical = canonical_config.read_bytes()
    desired = desired_config.read_bytes()
    if len(canonical) > 2 * 1024 * 1024 or len(desired) > 2 * 1024 * 1024:
        raise ManagementError("Kimi configuration exceeds the bounded size")
    if not desired.startswith(canonical):
        raise ManagementError("desired Kimi config does not preserve its canonical prefix")
    try:
        desired_text = desired.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ManagementError("desired Kimi config is not UTF-8") from error
    required = (
        'event = "PreToolUse"',
        'event = "Stop"',
        "hosts/kimi/adapter.py",
        "/usr/bin/python3 -B",
    )
    if any(fragment not in desired_text for fragment in required):
        raise ManagementError("desired Kimi config lacks the installed hook contract")
    if "kimi_hook.py" in desired_text:
        raise ManagementError("desired Kimi config retains the legacy adapter")
    return canonical, desired


def _kimi_config_paths(selected_home: Path) -> Dict[str, Path]:
    return {name: selected_home / name for name in _KIMI_CONFIG_NAMES}


def _validate_kimi_preimage(
    selected_home: Path, value: Any
) -> Dict[str, Dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(_KIMI_CONFIG_NAMES):
        raise ManagementError("Kimi config receipt has an invalid preimage map")
    backup_root = (control_root(selected_home) / "kimi-config-preimages").resolve()
    validated: Dict[str, Dict[str, Any]] = {}
    for name in _KIMI_CONFIG_NAMES:
        descriptor = value[name]
        if not isinstance(descriptor, dict):
            raise ManagementError("Kimi config preimage descriptor is malformed")
        if descriptor == {"kind": "absent"}:
            validated[name] = dict(descriptor)
            continue
        if set(descriptor) != {"kind", "backup", "digest", "mode"} or descriptor.get(
            "kind"
        ) != "file":
            raise ManagementError("Kimi config preimage descriptor is malformed")
        backup_raw = descriptor.get("backup")
        digest = descriptor.get("digest")
        mode = descriptor.get("mode")
        if (
            not isinstance(backup_raw, str)
            or not backup_raw
            or not isinstance(digest, str)
            or not isinstance(mode, int)
            or isinstance(mode, bool)
            or mode < 0
            or mode > 0o7777
        ):
            raise ManagementError("Kimi config preimage descriptor is malformed")
        backup = Path(backup_raw)
        try:
            contained = os.path.commonpath(
                (str(backup_root), str(backup.resolve()))
            ) == str(backup_root)
        except ValueError as error:
            raise ManagementError("Kimi config backup path is invalid") from error
        if not contained or backup.is_symlink() or not backup.is_file():
            raise ManagementError("Kimi config backup path is outside managed state")
        if _digest_bytes(backup.read_bytes()) != digest:
            raise ManagementError("Kimi config preimage backup was modified")
        validated[name] = dict(descriptor)
    return validated


def _read_kimi_config_receipt(
    selected_home: Path,
    paths: Mapping[str, Path],
    receipt_path: Path,
) -> Dict[str, Any]:
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ManagementError("managed Kimi config has no ownership receipt")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ManagementError("Kimi config receipt is malformed") from error
    snapshots = {name: _owned_file_snapshot(path) for name, path in paths.items()}
    if any(snapshot is None for snapshot in snapshots.values()):
        raise ManagementError("managed Kimi config is incomplete")
    config = snapshots["config.toml"]
    canonical_marker = snapshots[".canonical-config.sha256"]
    generated_marker = snapshots[".generated-config.sha256"]
    assert config is not None
    assert canonical_marker is not None
    assert generated_marker is not None
    config_digest = _digest_bytes(config[0])
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != KIMI_CONFIG_RECEIPT_SCHEMA
        or receipt.get("selected_home") != str(selected_home)
        or receipt.get("config") != str(paths["config.toml"])
        or receipt.get("current_digest") != config_digest
        or canonical_marker[0]
        != (str(receipt.get("canonical_digest", "")).removeprefix("sha256:") + "\n").encode(
            "ascii"
        )
        or generated_marker[0]
        != (config_digest.removeprefix("sha256:") + "\n").encode("ascii")
    ):
        raise ManagementError("managed Kimi config or receipt was modified locally")
    receipt["preimage"] = _validate_kimi_preimage(
        selected_home, receipt.get("preimage")
    )
    return receipt


def _legacy_kimi_config_preflight(
    paths: Mapping[str, Path],
) -> Dict[str, Optional[Tuple[bytes, int]]]:
    snapshots = {name: _owned_file_snapshot(path) for name, path in paths.items()}
    present = [snapshot is not None for snapshot in snapshots.values()]
    if not any(present):
        return snapshots
    if not all(present):
        raise ManagementError("unrecognized Kimi selected-config state")
    config = snapshots["config.toml"]
    canonical_marker = snapshots[".canonical-config.sha256"]
    generated_marker = snapshots[".generated-config.sha256"]
    assert config is not None
    assert canonical_marker is not None
    assert generated_marker is not None
    try:
        text = config[0].decode("utf-8")
        canonical_checksum = canonical_marker[0].strip().decode("ascii")
        generated_checksum = generated_marker[0].strip().decode("ascii")
    except UnicodeDecodeError as error:
        raise ManagementError("unrecognized Kimi selected-config state") from error
    if (
        re.fullmatch(r"[0-9a-f]{64}", canonical_checksum) is None
        or generated_checksum != hashlib.sha256(config[0]).hexdigest()
        or "kimi_hook.py" not in text
        or "hosts/kimi/adapter.py" in text
    ):
        raise ManagementError("unrecognized Kimi selected-config state")
    return snapshots


def _create_kimi_config_preimage(
    selected_home: Path,
    snapshots: Mapping[str, Optional[Tuple[bytes, int]]],
) -> Dict[str, Dict[str, Any]]:
    transaction = _transaction_id("kimi-config-preimage")
    backup_dir = (
        control_root(selected_home) / "kimi-config-preimages" / transaction
    )
    backup_dir.mkdir(mode=0o700, parents=True)
    preimage: Dict[str, Dict[str, Any]] = {}
    for name in _KIMI_CONFIG_NAMES:
        snapshot = snapshots[name]
        if snapshot is None:
            preimage[name] = {"kind": "absent"}
            continue
        payload, mode = snapshot
        backup = backup_dir / name
        _write_bytes_atomic(backup, payload, mode)
        preimage[name] = {
            "kind": "file",
            "backup": str(backup),
            "digest": _digest_bytes(payload),
            "mode": mode,
        }
    return preimage


def materialize_kimi_config(
    canonical_config: Path,
    selected_home: Path,
    desired_config: Path,
    apply: bool,
) -> Dict[str, Any]:
    if apply:
        _materialize_kimi_config_unlocked(
            canonical_config, selected_home, desired_config, False
        )
        with _installer_lock("kimi-config", selected_home):
            return _materialize_kimi_config_unlocked(
                canonical_config, selected_home, desired_config, True
            )
    return _materialize_kimi_config_unlocked(
        canonical_config, selected_home, desired_config, False
    )


def _materialize_kimi_config_unlocked(
    canonical_config: Path,
    selected_home: Path,
    desired_config: Path,
    apply: bool,
) -> Dict[str, Any]:
    _management_manifest("kimi")
    canonical, desired = _validate_desired_kimi_config(
        canonical_config, desired_config
    )
    paths = _kimi_config_paths(selected_home)
    receipt_path = selected_home / "review-after-commit.kimi-config-receipt.json"
    if receipt_path.is_symlink():
        raise ManagementError("Kimi config receipt must not be a symlink")
    receipt: Optional[Dict[str, Any]] = None
    if receipt_path.exists():
        receipt = _read_kimi_config_receipt(
            selected_home, paths, receipt_path
        )
        snapshots = {
            name: _owned_file_snapshot(path) for name, path in paths.items()
        }
        action = (
            "none"
            if receipt["current_digest"] == _digest_bytes(desired)
            and receipt["canonical_digest"] == _digest_bytes(canonical)
            else "refresh"
        )
        preimage = receipt["preimage"]
    else:
        snapshots = _legacy_kimi_config_preflight(paths)
        action = (
            "materialize"
            if all(snapshot is None for snapshot in snapshots.values())
            else "migrate-legacy-config"
        )
        preimage = None

    result = {
        "apply": apply,
        "selected_home": str(selected_home),
        "config": str(paths["config.toml"]),
        "action": action,
        "canonical_digest": _digest_bytes(canonical),
        "desired_digest": _digest_bytes(desired),
    }
    if not apply or action == "none":
        return result

    current = {
        name: _owned_file_snapshot(path) for name, path in paths.items()
    }
    old_receipt = _owned_file_snapshot(receipt_path)
    if preimage is None:
        preimage = _create_kimi_config_preimage(selected_home, current)
    new_receipt = {
        "schema": KIMI_CONFIG_RECEIPT_SCHEMA,
        "selected_home": str(selected_home),
        "config": str(paths["config.toml"]),
        "current_digest": _digest_bytes(desired),
        "canonical_digest": _digest_bytes(canonical),
        "preimage": preimage,
        "materialized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        _write_bytes_atomic(paths["config.toml"], desired, 0o600)
        _write_bytes_atomic(
            paths[".canonical-config.sha256"],
            (hashlib.sha256(canonical).hexdigest() + "\n").encode("ascii"),
            0o600,
        )
        _write_bytes_atomic(
            paths[".generated-config.sha256"],
            (hashlib.sha256(desired).hexdigest() + "\n").encode("ascii"),
            0o600,
        )
        _write_json_atomic(receipt_path, new_receipt)
    except Exception:
        for name, path in paths.items():
            _restore_owned_snapshot(path, current[name])
        _restore_owned_snapshot(receipt_path, old_receipt)
        raise
    return result


def rollback_kimi_config(selected_home: Path, apply: bool) -> Dict[str, Any]:
    if apply:
        _rollback_kimi_config_unlocked(selected_home, False)
        with _installer_lock("kimi-config", selected_home):
            return _rollback_kimi_config_unlocked(selected_home, True)
    return _rollback_kimi_config_unlocked(selected_home, False)


def _rollback_kimi_config_unlocked(
    selected_home: Path, apply: bool
) -> Dict[str, Any]:
    paths = _kimi_config_paths(selected_home)
    receipt_path = selected_home / "review-after-commit.kimi-config-receipt.json"
    receipt = _read_kimi_config_receipt(selected_home, paths, receipt_path)
    preimage = receipt["preimage"]
    restore = (
        "absent"
        if all(value["kind"] == "absent" for value in preimage.values())
        else "preimage"
    )
    result = {
        "apply": apply,
        "selected_home": str(selected_home),
        "restore": restore,
    }
    if not apply:
        return result

    current = {
        name: _owned_file_snapshot(path) for name, path in paths.items()
    }
    current_receipt = _owned_file_snapshot(receipt_path)
    transaction = _transaction_id("kimi-config-rollback")
    backup_dir = (
        control_root(selected_home) / "kimi-config-rollbacks" / transaction
    )
    backup_dir.mkdir(mode=0o700, parents=True)
    for name, snapshot in current.items():
        assert snapshot is not None
        _write_bytes_atomic(backup_dir / name, snapshot[0], snapshot[1])
    assert current_receipt is not None
    _write_bytes_atomic(
        backup_dir / "receipt.json",
        current_receipt[0],
        current_receipt[1],
    )
    try:
        for name, path in paths.items():
            descriptor = preimage[name]
            if descriptor["kind"] == "absent":
                _restore_owned_snapshot(path, None)
            else:
                backup = Path(descriptor["backup"])
                _restore_owned_snapshot(
                    path, (backup.read_bytes(), descriptor["mode"])
                )
        receipt_path.unlink()
        _fsync_directory(receipt_path.parent)
    except Exception:
        for name, path in paths.items():
            _restore_owned_snapshot(path, current[name])
        _restore_owned_snapshot(receipt_path, current_receipt)
        raise
    result["backup_config"] = str(backup_dir / "config.toml")
    result["backup_receipt"] = str(backup_dir / "receipt.json")
    return result


def _transaction_id(host: str) -> str:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return "{}-{:020d}-{}-{}".format(
        timestamp, time.time_ns(), host, uuid.uuid4().hex[:12]
    )


def _install_one(
    host: str,
    home: Path,
    expected: Mapping[str, Any],
    before_status: Mapping[str, Any],
) -> Dict[str, Any]:
    destination = destination_for(host, home)
    with _installer_lock(host, home):
        actual_before = classify(host, home, expected)
        if _status_fingerprint(actual_before) != _status_fingerprint(before_status):
            raise ManagementError("destination changed after preflight")
        destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        transaction = _transaction_id(host)
        control = control_root(home)
        backup_dir = control / "backups" / transaction
        backup_dir.mkdir(mode=0o700, parents=True)
        previous = backup_dir / "previous"
        failed_new = backup_dir / "failed-new"
        releases = control / "releases" / host
        releases.mkdir(mode=0o700, parents=True, exist_ok=True)
        release_name = expected["bundle_digest"].split(":", 1)[1]
        release = releases / release_name
        stage_root = Path(
            tempfile.mkdtemp(prefix=".review-after-commit-stage-", dir=releases)
        )
        staged = stage_root / "review-after-commit"
        temporary_link = destination.parent / ".review-after-commit-{}.link".format(
            transaction
        )
        had_previous = _lexists(destination)
        activated = False
        registry_changed = False
        antigravity_config_before: Optional[bytes] = None
        antigravity_imports_before: Optional[bytes] = None
        antigravity_enabled_after: Optional[bool] = None
        if host == "antigravity":
            config_path, imports_path = _antigravity_registry_paths(home)
            antigravity_config_before = _snapshot_file(config_path)
            antigravity_imports_before = _snapshot_file(imports_path)
            antigravity_enabled_after = (
                bool(actual_before["plugin"]["enabled"])
                if actual_before["status"]
                in ("current", "installed-disabled", "stale", "stale-disabled")
                else False
            )
            if antigravity_config_before is not None:
                _write_bytes_atomic(
                    backup_dir / "config.json.previous",
                    antigravity_config_before,
                    0o600,
                )
            if antigravity_imports_before is not None:
                _write_bytes_atomic(
                    backup_dir / "import_manifest.json.previous",
                    antigravity_imports_before,
                    0o600,
                )
        receipt_path = control / "receipts" / "{}.json".format(transaction)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "transaction": transaction,
            "phase": "prepared",
            "host": host,
            "destination": str(destination),
            "had_previous": had_previous,
            "backup": str(previous) if had_previous else None,
            "release": str(release),
            "bundle_digest": expected["bundle_digest"],
            "before_status": before_status["status"],
            "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if host == "antigravity":
            receipt["antigravity_registry"] = {
                "config_existed": antigravity_config_before is not None,
                "config_backup": (
                    str(backup_dir / "config.json.previous")
                    if antigravity_config_before is not None
                    else None
                ),
                "config_before_digest": (
                    _digest_bytes(antigravity_config_before)
                    if antigravity_config_before is not None
                    else None
                ),
                "imports_existed": antigravity_imports_before is not None,
                "imports_backup": (
                    str(backup_dir / "import_manifest.json.previous")
                    if antigravity_imports_before is not None
                    else None
                ),
                "imports_before_digest": (
                    _digest_bytes(antigravity_imports_before)
                    if antigravity_imports_before is not None
                    else None
                ),
                "enabled_after": antigravity_enabled_after,
            }
        try:
            if release.exists():
                validate_bundle(release, expected)
            else:
                build_bundle(host, staged, expected)
                os.replace(staged, release)
                _fsync_directory(releases)
            if had_previous:
                _copy_symlink(destination, previous)
            _make_symlink(release, temporary_link, destination.parent)
            _write_json_atomic(receipt_path, receipt)

            final_before = classify(host, home, expected)
            if _status_fingerprint(final_before) != _status_fingerprint(before_status):
                raise ManagementError("destination changed while the release was staged")
            if host == "antigravity":
                registry_changed = True
                registry_after = _write_antigravity_registry(
                    home, enabled=bool(antigravity_enabled_after)
                )
                receipt["antigravity_registry"].update(registry_after)
            os.replace(temporary_link, destination)
            activated = True
            _fsync_directory(destination.parent)
            validate_bundle(destination.resolve(), expected)
            after = classify(host, home, expected)
            expected_after_status = (
                "current"
                if host != "antigravity" or antigravity_enabled_after
                else "installed-disabled"
            )
            if after["status"] != expected_after_status:
                raise ManagementError("post-install status is not current")
            receipt["phase"] = "active"
            receipt["installed_at"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            _write_json_atomic(receipt_path, receipt)
            return {
                "host": host,
                "status": "installed",
                "receipt": str(receipt_path),
            }
        except Exception:
            if activated and destination.is_symlink():
                _copy_symlink(destination, failed_new)
                if had_previous and previous.is_symlink():
                    restore_link = destination.parent / ".review-after-commit-{}.restore".format(
                        transaction
                    )
                    _copy_symlink(previous, restore_link)
                    os.replace(restore_link, destination)
                else:
                    destination.unlink()
                _fsync_directory(destination.parent)
            if registry_changed:
                config_path, imports_path = _antigravity_registry_paths(home)
                _restore_file(config_path, antigravity_config_before)
                _restore_file(imports_path, antigravity_imports_before)
            raise
        finally:
            temporary_link.unlink(missing_ok=True)
            shutil.rmtree(stage_root, ignore_errors=True)


def install(
    hosts: Sequence[str], homes: Mapping[str, Path], apply: bool
) -> Dict[str, Any]:
    expected_by_host: Dict[str, Dict[str, Any]] = {}
    statuses: Dict[str, Dict[str, Any]] = {}
    for host in hosts:
        _host_cli_version(host)
        expected = expected_manifest(host)
        with tempfile.TemporaryDirectory(prefix="review-hook-preflight-") as temporary:
            bundle = Path(temporary) / "review-after-commit"
            build_bundle(host, bundle, expected)
            _validate_host_bundle_cli(host, bundle)
        expected_by_host[host] = expected
        status = classify(host, homes[host], expected)
        statuses[host] = status
        if status["status"] not in (
            "absent",
            "current",
            "installed-disabled",
            "stale",
            "stale-disabled",
            "legacy-symlink",
        ):
            raise ManagementError(
                "refusing {} install over {} destination: {}".format(
                    host, status["status"], status.get("reason", "ownership is unproven")
                )
            )

    plan = {
        "apply": apply,
        "operations": [
            {
                "host": host,
                "destination": str(destination_for(host, homes[host])),
                "before": statuses[host]["status"],
                "action": (
                    "none"
                    if statuses[host]["status"] in ("current", "installed-disabled")
                    else "install"
                ),
                "bundle_digest": expected_by_host[host]["bundle_digest"],
            }
            for host in hosts
        ],
        "results": [],
    }
    if not apply:
        return plan
    for host in hosts:
        if statuses[host]["status"] in ("current", "installed-disabled"):
            plan["results"].append({"host": host, "status": "already-current"})
            continue
        try:
            result = _install_one(
                host, homes[host], expected_by_host[host], statuses[host]
            )
        except Exception as error:
            plan["error"] = "{} install failed after {} completed host transaction(s): {}".format(
                host, len(plan["results"]), error
            )
            raise ManagementError(json.dumps(plan, sort_keys=True)) from error
        plan["results"].append(result)
    return plan


def set_antigravity_enabled(
    home: Path, enabled: bool, apply: bool
) -> Dict[str, Any]:
    """Enable or disable the proven plugin without changing its bundle."""

    if type(enabled) is not bool:
        raise ManagementError("Antigravity enabled state must be boolean")
    _host_cli_version("antigravity")
    expected = expected_manifest("antigravity")
    status = classify("antigravity", home, expected)
    desired_status = "current" if enabled else "installed-disabled"
    current_status = "current" if status.get("plugin", {}).get("enabled") else "installed-disabled"
    if status["status"] not in ("current", "installed-disabled"):
        raise ManagementError(
            "Antigravity activation requires a current managed plugin, found {}".format(
                status["status"]
            )
        )
    action = "none" if current_status == desired_status else ("enable" if enabled else "disable")
    plan: Dict[str, Any] = {
        "apply": apply,
        "host": "antigravity",
        "destination": str(destination_for("antigravity", home)),
        "before": status["status"],
        "after": desired_status,
        "action": action,
    }
    if not apply or action == "none":
        return plan

    with _installer_lock("antigravity-plugin-state", home):
        locked_status = classify("antigravity", home, expected)
        if (
            _status_fingerprint(locked_status) != _status_fingerprint(status)
            or locked_status.get("plugin") != status.get("plugin")
        ):
            raise ManagementError("Antigravity plugin state changed after preflight")
        registry = _antigravity_registry(home)
        config_path, _ = _antigravity_registry_paths(home)
        before = _snapshot_file(config_path)
        if before is None:
            raise ManagementError("Antigravity config.json disappeared after preflight")
        transaction = _transaction_id("antigravity-plugin-state")
        backup = control_root(home) / "backups" / transaction / "config.json.previous"
        _write_bytes_atomic(backup, before, 0o600)
        config = dict(registry["config"])
        plugins = dict(config.get("plugins", {}))
        plugins["review-after-commit"] = {"enabled": enabled}
        config["plugins"] = plugins
        receipt_path = control_root(home) / "receipts" / "{}.json".format(transaction)
        try:
            _write_json_atomic(config_path, config)
            after_status = classify("antigravity", home, expected)
            if after_status["status"] != desired_status:
                raise ManagementError("Antigravity plugin state did not reach its target")
            receipt = {
                "schema": PLUGIN_STATE_RECEIPT_SCHEMA,
                "transaction": transaction,
                "host": "antigravity",
                "destination": str(destination_for("antigravity", home)),
                "bundle_digest": expected["bundle_digest"],
                "enabled_before": not enabled,
                "enabled_after": enabled,
                "config_backup": str(backup),
                "config_before_digest": _digest_bytes(before),
                "config_after_digest": _digest_bytes(config_path.read_bytes()),
                "changed_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
            }
            _write_json_atomic(receipt_path, receipt)
            plan["receipt"] = str(receipt_path)
            return plan
        except Exception:
            _restore_file(config_path, before)
            raise


def _latest_install_receipt(host: str, home: Path) -> Tuple[Path, Dict[str, Any]]:
    receipts = sorted((control_root(home) / "receipts").glob("*.json"), reverse=True)
    for path in receipts:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if value.get("schema") == RECEIPT_SCHEMA and value.get("host") == host:
            return path, value
    raise ManagementError("no install receipt is available for {}".format(host))


def rollback(host: str, home: Path, apply: bool) -> Dict[str, Any]:
    expected = expected_manifest(host)
    status = classify(host, home, expected)
    if status["status"] not in (
        "current",
        "installed-disabled",
        "stale",
        "stale-disabled",
    ):
        raise ManagementError(
            "rollback requires an unchanged managed bundle, found {}".format(status["status"])
        )
    receipt_path, receipt = _latest_install_receipt(host, home)
    destination = destination_for(host, home)
    if receipt.get("destination") != str(destination):
        raise ManagementError("install receipt destination does not match the selected home")
    previous_raw = receipt.get("backup")
    previous = Path(previous_raw) if isinstance(previous_raw, str) else None
    had_previous = receipt.get("had_previous") is True
    if receipt.get("phase") != "active":
        raise ManagementError("latest install receipt is not active")
    if status.get("installed_bundle_digest") != receipt.get("bundle_digest"):
        raise ManagementError("active bundle does not match the latest install receipt")
    registry_receipt = receipt.get("antigravity_registry")
    if host == "antigravity":
        if not isinstance(registry_receipt, dict):
            raise ManagementError("Antigravity install receipt lacks registry ownership")
        config_path, imports_path = _antigravity_registry_paths(home)
        current_config = _snapshot_file(config_path)
        current_imports = _snapshot_file(imports_path)
        if (
            current_config is None
            or current_imports is None
            or _digest_bytes(current_config) != registry_receipt.get("config_digest")
            or _digest_bytes(current_imports) != registry_receipt.get("imports_digest")
        ):
            raise ManagementError(
                "Antigravity shared registry changed after the install transaction"
            )
    if had_previous and (
        previous is None or not previous.is_symlink() or not previous.exists()
    ):
        raise ManagementError("the recorded rollback backup is unavailable")
    plan = {
        "apply": apply,
        "host": host,
        "destination": str(destination),
        "receipt": str(receipt_path),
        "restore": str(previous) if previous else "absent",
    }
    if not apply:
        return plan
    with _installer_lock(host, home):
        locked_status = classify(host, home, expected)
        if _status_fingerprint(locked_status) != _status_fingerprint(status):
            raise ManagementError("destination changed after rollback preflight")
        transaction = _transaction_id("{}-rollback".format(host))
        replaced = control_root(home) / "backups" / transaction / "replaced"
        replaced.parent.mkdir(mode=0o700, parents=True)
        _copy_symlink(destination, replaced)
        restore_link = destination.parent / ".review-after-commit-{}.restore".format(
            transaction
        )
        changed = False
        registry_changed = False
        current_config = None
        current_imports = None
        try:
            if had_previous and previous is not None:
                _copy_symlink(previous, restore_link)
                os.replace(restore_link, destination)
            else:
                destination.unlink()
            changed = True
            _fsync_directory(destination.parent)
            if host == "antigravity":
                config_path, imports_path = _antigravity_registry_paths(home)
                current_config = _snapshot_file(config_path)
                current_imports = _snapshot_file(imports_path)
                config_backup = registry_receipt.get("config_backup")
                imports_backup = registry_receipt.get("imports_backup")
                config_before = (
                    Path(config_backup).read_bytes()
                    if isinstance(config_backup, str)
                    else None
                )
                imports_before = (
                    Path(imports_backup).read_bytes()
                    if isinstance(imports_backup, str)
                    else None
                )
                if (
                    (config_before is not None)
                    != bool(registry_receipt.get("config_existed"))
                    or (imports_before is not None)
                    != bool(registry_receipt.get("imports_existed"))
                    or (
                        config_before is not None
                        and _digest_bytes(config_before)
                        != registry_receipt.get("config_before_digest")
                    )
                    or (
                        imports_before is not None
                        and _digest_bytes(imports_before)
                        != registry_receipt.get("imports_before_digest")
                    )
                ):
                    raise ManagementError(
                        "Antigravity registry rollback backups are unavailable or changed"
                    )
                registry_changed = True
                _restore_file(config_path, config_before)
                _restore_file(imports_path, imports_before)
            rollback_receipt = {
                "schema": ROLLBACK_SCHEMA,
                "transaction": transaction,
                "host": host,
                "install_receipt": str(receipt_path),
                "replaced_bundle": str(replaced),
                "restored_previous": had_previous,
                "rolled_back_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
            }
            rollback_path = control_root(home) / "receipts" / "{}.json".format(
                transaction
            )
            _write_json_atomic(rollback_path, rollback_receipt)
            plan["rollback_receipt"] = str(rollback_path)
            return plan
        except Exception:
            if changed:
                recovery = destination.parent / ".review-after-commit-{}.recovery".format(
                    transaction
                )
                _copy_symlink(replaced, recovery)
                os.replace(recovery, destination)
                _fsync_directory(destination.parent)
            if registry_changed:
                config_path, imports_path = _antigravity_registry_paths(home)
                _restore_file(config_path, current_config)
                _restore_file(imports_path, current_imports)
            raise
        finally:
            restore_link.unlink(missing_ok=True)


def _parse_homes(values: Iterable[str]) -> Dict[str, Path]:
    homes: Dict[str, Path] = {}
    for value in values:
        host, separator, raw_path = value.partition("=")
        if not separator or host not in ("codex", "kimi", "antigravity") or not raw_path:
            raise ManagementError("--home must be HOST=/absolute/path")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise ManagementError("--home paths must be absolute")
        if host in homes:
            raise ManagementError("--home may be specified only once per host")
        homes[host] = path
    return homes


def _selected_homes(hosts: Sequence[str], overrides: Mapping[str, Path]) -> Dict[str, Path]:
    unused = set(overrides) - set(hosts)
    if unused:
        raise ManagementError("home override supplied for an unselected host: {}".format(", ".join(sorted(unused))))
    return {host: overrides.get(host, _default_home(host)) for host in hosts}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument(
        "--host", action="append", choices=("codex", "kimi", "antigravity")
    )

    status = subparsers.add_parser("status")
    status.add_argument("--host", action="append", choices=("codex", "kimi", "antigravity"))
    status.add_argument("--all-hosts", action="store_true")
    status.add_argument("--home", action="append", default=[])

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--host", action="append", required=True, choices=("codex", "kimi", "antigravity"))
    install_parser.add_argument("--home", action="append", default=[])
    install_parser.add_argument("--apply", action="store_true")

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument(
        "--host", required=True, choices=("codex", "kimi", "antigravity")
    )
    rollback_parser.add_argument("--home", action="append", default=[])
    rollback_parser.add_argument("--apply", action="store_true")

    for command in ("activate-antigravity", "deactivate-antigravity"):
        plugin_state_parser = subparsers.add_parser(command)
        plugin_state_parser.add_argument("--home")
        plugin_state_parser.add_argument("--apply", action="store_true")

    profile_parser = subparsers.add_parser("materialize-profile")
    profile_parser.add_argument("--canonical-home", required=True)
    profile_parser.add_argument("--selected-home", required=True)
    profile_parser.add_argument("--apply", action="store_true")

    profile_rollback_parser = subparsers.add_parser("rollback-profile")
    profile_rollback_parser.add_argument("--selected-home", required=True)
    profile_rollback_parser.add_argument("--apply", action="store_true")

    kimi_config_parser = subparsers.add_parser("materialize-kimi-config")
    kimi_config_parser.add_argument("--canonical-config", required=True)
    kimi_config_parser.add_argument("--selected-home", required=True)
    kimi_config_parser.add_argument("--desired-config", required=True)
    kimi_config_parser.add_argument("--apply", action="store_true")

    kimi_config_rollback_parser = subparsers.add_parser(
        "rollback-kimi-config"
    )
    kimi_config_rollback_parser.add_argument("--selected-home", required=True)
    kimi_config_rollback_parser.add_argument("--apply", action="store_true")

    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--repo", default=".")
    scan_parser.add_argument("--base", required=True)
    scan_parser.add_argument("--head", required=True)
    scan_parser.add_argument("--full", action="store_true", required=True)
    scan_parser.add_argument("--format", choices=("json",), default="json")

    outcome_status = subparsers.add_parser("outcome-status")
    outcome_status.add_argument("--root")

    record_outcome = subparsers.add_parser("record-review-outcome")
    record_outcome.add_argument("--root")
    record_outcome.add_argument("--repository", required=True)
    record_outcome.add_argument("--event", required=True)
    record_outcome.add_argument("--delivery", required=True)
    record_outcome.add_argument("--finding-count", required=True, type=int)
    return parser


def _scan_exact_range(arguments: argparse.Namespace) -> Dict[str, Any]:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    try:
        from runtime.analysis.evidence_package import ReviewScanError, scan_range

        result = scan_range(
            Path(arguments.repo).expanduser(), arguments.base, arguments.head
        )
    except ReviewScanError as error:
        raise ManagementError("Review Scan failed: {}".format(error)) from error
    return result.evidence.to_dict()


def _outcome_root(raw: Optional[str]) -> Path:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    from runtime.analysis.outcomes import default_outcome_root

    root = Path(raw).expanduser() if raw else default_outcome_root()
    if not root.is_absolute():
        raise ManagementError("automatic outcome root must be absolute")
    return root


def _outcome_status(arguments: argparse.Namespace) -> Dict[str, Any]:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    from runtime.analysis.outcomes import OutcomeStore

    return OutcomeStore(_outcome_root(arguments.root)).summary()


def _record_review_outcome(arguments: argparse.Namespace) -> Dict[str, Any]:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    from runtime.analysis.model import RepositoryIdentity
    from runtime.analysis.outcomes import OutcomeStore

    repository = RepositoryIdentity(arguments.repository)
    recorded = OutcomeStore(_outcome_root(arguments.root)).record_review(
        repository,
        arguments.event,
        arguments.delivery,
        arguments.finding_count,
    )
    return {
        "recorded": recorded,
        "result": "findings" if arguments.finding_count else "no-findings",
        "finding_count": arguments.finding_count,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "validate":
        hosts = arguments.host or ["codex", "kimi", "antigravity"]
        result = {"validation": validate_sources(hosts)}
    elif arguments.command == "status":
        if arguments.all_hosts and arguments.host:
            raise ManagementError("use --all-hosts or --host, not both")
        hosts = (
            ["codex", "kimi", "antigravity"]
            if arguments.all_hosts
            else arguments.host or ["codex", "kimi"]
        )
        if len(set(hosts)) != len(hosts):
            raise ManagementError("each host may be selected only once")
        homes = _selected_homes(hosts, _parse_homes(arguments.home))
        statuses = [inspect_status(host, homes[host]) for host in hosts]
        result = {"statuses": statuses}
    elif arguments.command == "install":
        hosts = arguments.host
        if len(set(hosts)) != len(hosts):
            raise ManagementError("each host may be selected only once")
        homes = _selected_homes(hosts, _parse_homes(arguments.home))
        result = install(hosts, homes, arguments.apply)
    elif arguments.command == "rollback":
        host = arguments.host
        homes = _selected_homes([host], _parse_homes(arguments.home))
        result = rollback(host, homes[host], arguments.apply)
    elif arguments.command == "materialize-profile":
        canonical_home = Path(arguments.canonical_home).expanduser()
        selected_home = Path(arguments.selected_home).expanduser()
        if not canonical_home.is_absolute() or not selected_home.is_absolute():
            raise ManagementError("profile home paths must be absolute")
        result = materialize_codex_profile(
            canonical_home, selected_home, arguments.apply
        )
    elif arguments.command == "rollback-profile":
        selected_home = Path(arguments.selected_home).expanduser()
        if not selected_home.is_absolute():
            raise ManagementError("selected profile home must be absolute")
        result = rollback_codex_profile(selected_home, arguments.apply)
    elif arguments.command == "materialize-kimi-config":
        canonical_config = Path(arguments.canonical_config).expanduser()
        selected_home = Path(arguments.selected_home).expanduser()
        desired_config = Path(arguments.desired_config).expanduser()
        if not all(
            path.is_absolute()
            for path in (canonical_config, selected_home, desired_config)
        ):
            raise ManagementError("Kimi config paths must be absolute")
        result = materialize_kimi_config(
            canonical_config, selected_home, desired_config, arguments.apply
        )
    elif arguments.command == "rollback-kimi-config":
        selected_home = Path(arguments.selected_home).expanduser()
        if not selected_home.is_absolute():
            raise ManagementError("selected Kimi home must be absolute")
        result = rollback_kimi_config(selected_home, arguments.apply)
    elif arguments.command in (
        "activate-antigravity",
        "deactivate-antigravity",
    ):
        home = (
            Path(arguments.home).expanduser()
            if arguments.home
            else _default_home("antigravity")
        )
        if not home.is_absolute():
            raise ManagementError("Antigravity config home must be absolute")
        result = set_antigravity_enabled(
            home,
            arguments.command == "activate-antigravity",
            arguments.apply,
        )
    elif arguments.command == "outcome-status":
        result = _outcome_status(arguments)
    elif arguments.command == "record-review-outcome":
        result = _record_review_outcome(arguments)
    else:
        result = _scan_exact_range(arguments)
    json.dump(result, sys.stdout, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ManagementError, OSError, subprocess.SubprocessError, ValueError) as error:
        raise SystemExit("review-hook management: {}".format(error)) from error
