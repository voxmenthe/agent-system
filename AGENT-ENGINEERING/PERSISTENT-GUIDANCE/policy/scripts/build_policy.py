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
    pack_path,
    render_routing_table,
    replace_generated_table,
)

# Marked regions of a pack hold the block an installed CLI ships, so the CLI's
# repository stays the one source for that text.
EMBEDDED_BLOCKS = {
    "OMEM INSTRUCTIONS": ("memory", "instructions"),
    "HIST INSTRUCTIONS": ("hist", "instructions"),
}


def markers(name: str) -> tuple[str, str]:
    return f"<!-- BEGIN {name} -->", f"<!-- END {name} -->"


def cli_block(command: tuple[str, ...]) -> str:
    """Return the canonical block an installed CLI prints."""

    shown = " ".join(command)
    try:
        result = subprocess.run(
            list(command), capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise PolicyError(f"cannot run `{shown}`: {exc}") from exc
    if result.returncode != 0 or not result.stdout.strip():
        detail = result.stderr.strip() or "empty output"
        raise PolicyError(f"`{shown}` failed: {detail}")
    return result.stdout.strip()


def embed_block(text: str, name: str, block: str) -> str:
    """Replace the region of a pack marked `name` with the canonical block."""

    begin, end = markers(name)
    if begin not in text and end not in text:
        return text
    if text.count(begin) != 1 or text.count(end) != 1:
        raise PolicyError(f"pack has malformed {name} markers")
    before, rest = text.split(begin, 1)
    inside, after = rest.split(end, 1)
    return f"{before}{begin}\n{block}\n{end}{after}"


def expected_outputs(policy_root: Path) -> dict[Path, str]:
    manifest = load_manifest(policy_root)
    agents_path = policy_root / "AGENTS.md"
    agents_source = agents_path.read_text(encoding="utf-8")
    table = render_routing_table(manifest)
    updated_agents = replace_generated_table(agents_source, table).rstrip() + "\n"

    outputs: dict[Path, str] = {}
    pack_texts: dict[str, str] = {}
    blocks: dict[str, str] = {}
    for name in manifest["packs"]:
        path = pack_path(policy_root, manifest, name)
        source = path.read_text(encoding="utf-8")
        embedded = source
        for block_name, command in EMBEDDED_BLOCKS.items():
            if not any(marker in embedded for marker in markers(block_name)):
                continue
            if block_name not in blocks:
                blocks[block_name] = cli_block(command)
            embedded = embed_block(embedded, block_name, blocks[block_name])
        if embedded != source:
            outputs[path] = embedded
        pack_texts[name] = embedded.strip()

    generated_table = (
        "# Generated routing table\n\n"
        "> Generated from `policy/manifest.json`; do not edit manually.\n\n"
        + table.rstrip()
        + "\n"
    )

    full_parts = [
        "# Full agent policy profile\n\n",
        (
            "> Generated from `AGENTS.md` and `policy/manifest.json`. "
            "Use for audits or high-risk sessions; do not edit manually.\n\n"
        ),
        updated_agents.rstrip(),
        "\n\n# Expanded instruction packs\n",
    ]
    for name in manifest["packs"]:
        full_parts.append(f"\n\n---\n\n## Expanded pack: `{name}`\n\n")
        full_parts.append(pack_texts[name])
    full_profile = "".join(full_parts).rstrip() + "\n"

    outputs[agents_path] = updated_agents
    outputs[policy_root / "policy/generated/routing-table.md"] = generated_table
    outputs[policy_root / "AGENTS.full.md"] = full_profile
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build generated global policy artifacts."
    )
    parser.add_argument(
        "--root", "--codex-home", dest="root", type=Path, default=default_policy_root()
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="write generated files (default)"
    )
    mode.add_argument(
        "--check", action="store_true", help="fail if generated files are stale"
    )
    args = parser.parse_args()
    policy_root = args.root.expanduser().resolve()

    try:
        outputs = expected_outputs(policy_root)
    except (PolicyError, OSError) as exc:
        print(f"policy build error: {exc}", file=sys.stderr)
        return 2

    stale: list[Path] = []
    for path, expected in outputs.items():
        actual = path.read_text(encoding="utf-8") if path.exists() else None
        if actual != expected:
            stale.append(path)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(expected, encoding="utf-8")
                print(f"wrote {path.relative_to(policy_root)}")

    if args.check and stale:
        print("stale generated policy files:", file=sys.stderr)
        for path in stale:
            print(f"  {path.relative_to(policy_root)}", file=sys.stderr)
        print("run: ./guidance build", file=sys.stderr)
        return 1
    if args.check:
        print("generated policy files are current")
    elif not stale:
        print("generated policy files already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
