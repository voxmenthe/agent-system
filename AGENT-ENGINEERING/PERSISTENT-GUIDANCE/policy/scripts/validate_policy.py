#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from policylib import (
    PolicyError,
    default_policy_root,
    load_manifest,
)

REQUIRED_HEADINGS = [
    "## Applies when",
    "## Does not apply when",
    "## Non-negotiable rules",
    "## Procedure",
    "## Done criteria",
]


def validate_pack_files(policy_root: Path, manifest: dict) -> list[str]:
    errors: list[str] = []
    for pack in manifest["packs"].values():
        path = policy_root / "policy" / pack["file"]
        text = path.read_text(encoding="utf-8")
        if not text.startswith("# "):
            errors.append(f"{path.relative_to(policy_root)} must start with one H1")
        for heading in REQUIRED_HEADINGS:
            if heading not in text:
                errors.append(f"{path.relative_to(policy_root)} is missing {heading!r}")
        if path.stat().st_size > 16 * 1024:
            errors.append(
                f"{path.relative_to(policy_root)} exceeds 16 KiB; split or compress it"
            )
    agents_size = (policy_root / "AGENTS.md").stat().st_size
    if agents_size > 24 * 1024:
        errors.append(f"AGENTS.md is {agents_size} bytes; keep the kernel below 24 KiB")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the global policy catalog, packs, and generated files."
    )
    parser.add_argument(
        "--root", "--codex-home", dest="root", type=Path, default=default_policy_root()
    )
    args = parser.parse_args()
    policy_root = args.root.expanduser().resolve()
    errors: list[str] = []

    try:
        manifest = load_manifest(policy_root)
        errors.extend(validate_pack_files(policy_root, manifest))
    except (PolicyError, OSError) as exc:
        errors.append(str(exc))

    build = subprocess.run(
        [
            sys.executable,
            str(policy_root / "policy/scripts/build_policy.py"),
            "--root",
            str(policy_root),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode != 0:
        errors.append((build.stderr or build.stdout).strip())

    if errors:
        print("policy validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("policy validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
