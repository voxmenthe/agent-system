#!/usr/bin/env python3
"""Reliably normalize and clean up ChatGPT exports into semantic slugs.

This script audits and migrates directories in CHATGPT-EXPORTS (or a custom path):
1. Detects raw UUID or UUID-v* folder names, inspects conversation metadata,
   and renames folders to semantic slugs (preserving version suffixes if present).
2. Normalizes internal files (Markdown, JSON, manifest) to match <semantic-slug>.<suffix>.
3. Updates and reverifies manifest checksums and file maps.
4. Integrates with git (using `git mv`, `git rm`, `git add`) when paths are tracked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Sequence

# Projected skills are hash-tracked. Suppress bytecode during local import.
_previous_dont_write_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    from chatgpt_transcript import slugify_title
finally:
    sys.dont_write_bytecode = _previous_dont_write_bytecode


_UUID_FOLDER_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(-v\d+)?$"
)
_VERSION_SUFFIX_PATTERN = re.compile(r"(-v\d+)$")


def find_repo_root(start: Path) -> Path | None:
    """Find the root of the enclosing git repository, if any."""
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def is_git_tracked(path: Path, repo_root: Path | None) -> bool:
    """Check if a path is tracked in git."""
    if repo_root is None or not path.exists():
        return False
    try:
        rel_path = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    res = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(rel_path)],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return res.returncode == 0


def git_mv(src: Path, dst: Path, repo_root: Path) -> None:
    """Move a git-tracked file or directory."""
    rel_src = src.resolve().relative_to(repo_root.resolve())
    rel_dst = dst.resolve().relative_to(repo_root.resolve())
    subprocess.run(
        ["git", "mv", str(rel_src), str(rel_dst)],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_rm(path: Path, repo_root: Path) -> None:
    """Remove a git-tracked file."""
    rel_path = path.resolve().relative_to(repo_root.resolve())
    subprocess.run(
        ["git", "rm", "-f", str(rel_path)],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_add(path: Path, repo_root: Path) -> None:
    """Stage a file in git."""
    rel_path = path.resolve().relative_to(repo_root.resolve())
    subprocess.run(
        ["git", "add", str(rel_path)],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def inspect_export_directory(dir_path: Path) -> dict[str, Any]:
    """Inspect an export directory and identify transcript, markdown, and manifest files."""
    json_files: list[Path] = []
    manifest_files: list[Path] = []
    md_files: list[Path] = []

    for item in sorted(dir_path.iterdir()):
        if item.is_file():
            if item.name.endswith(".manifest.json") or item.name == "manifest.json":
                manifest_files.append(item)
            elif item.suffix == ".json":
                json_files.append(item)
            elif item.suffix == ".md":
                md_files.append(item)

    transcript_file: Path | None = None
    transcript_data: dict[str, Any] | None = None
    for candidate in json_files:
        data = _load_json(candidate)
        if data and ("source" in data or "messages" in data or "conversation_id" in data):
            transcript_file = candidate
            transcript_data = data
            break

    manifest_file: Path | None = manifest_files[0] if manifest_files else None
    manifest_data: dict[str, Any] | None = _load_json(manifest_file) if manifest_file else None
    md_file: Path | None = md_files[0] if md_files else None

    # Determine conversation title and id
    title: str | None = None
    conversation_id: str | None = None
    if transcript_data:
        source = transcript_data.get("source")
        if isinstance(source, dict):
            title = source.get("title")
            conversation_id = source.get("conversation_id")
        if not title:
            title = transcript_data.get("title")
        if not conversation_id:
            conversation_id = transcript_data.get("conversation_id")

    if not conversation_id and manifest_data:
        conversation_id = manifest_data.get("conversation_id")

    return {
        "dir_path": dir_path,
        "transcript_file": transcript_file,
        "transcript_data": transcript_data,
        "manifest_file": manifest_file,
        "manifest_data": manifest_data,
        "md_file": md_file,
        "title": title,
        "conversation_id": conversation_id,
    }


def clean_export_directory(
    info: dict[str, Any],
    repo_root: Path | None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Clean and normalize an export directory and its internal files."""
    dir_path: Path = info["dir_path"]
    title: str | None = info["title"]
    conversation_id: str | None = info["conversation_id"] or dir_path.name
    transcript_file: Path | None = info["transcript_file"]
    manifest_file: Path | None = info["manifest_file"]
    md_file: Path | None = info["md_file"]

    actions: list[str] = []
    current_dir_name = dir_path.name

    # Check if folder name is raw UUID
    is_uuid_folder = bool(_UUID_FOLDER_PATTERN.match(current_dir_name))
    base_slug = slugify_title(title, fallback=conversation_id)
    version_match = _VERSION_SUFFIX_PATTERN.search(current_dir_name)
    version_suffix = version_match.group(1) if version_match else ""

    if is_uuid_folder:
        target_dir_name = f"{base_slug}{version_suffix}"
    else:
        # Already semantic or custom directory name
        target_dir_name = current_dir_name

    target_dir_path = dir_path.parent / target_dir_name

    # Step 1: Rename directory if needed
    if target_dir_path != dir_path:
        actions.append(f"rename_directory: {current_dir_name} -> {target_dir_name}")
        if not dry_run:
            if is_git_tracked(dir_path, repo_root) and repo_root is not None:
                git_mv(dir_path, target_dir_path, repo_root)
            else:
                shutil.move(str(dir_path), str(target_dir_path))
            dir_path = target_dir_path
            if transcript_file:
                transcript_file = dir_path / transcript_file.name
            if manifest_file:
                manifest_file = dir_path / manifest_file.name
            if md_file:
                md_file = dir_path / md_file.name

    # File slug inside folder matches the folder's semantic name
    file_slug = target_dir_name
    expected_md = dir_path / f"{file_slug}.md"
    expected_json = dir_path / f"{file_slug}.json"
    expected_manifest = dir_path / f"{file_slug}.manifest.json"

    # Step 2: Normalize Markdown file
    if md_file and md_file.name != expected_md.name:
        actions.append(f"rename_file: {md_file.name} -> {expected_md.name}")
        if not dry_run:
            if is_git_tracked(md_file, repo_root) and repo_root is not None:
                git_mv(md_file, expected_md, repo_root)
            else:
                md_file.rename(expected_md)
            md_file = expected_md

    # Step 3: Normalize Transcript JSON file
    if transcript_file and transcript_file.name != expected_json.name:
        actions.append(f"rename_file: {transcript_file.name} -> {expected_json.name}")
        if not dry_run:
            if is_git_tracked(transcript_file, repo_root) and repo_root is not None:
                git_mv(transcript_file, expected_json, repo_root)
            else:
                transcript_file.rename(expected_json)
            transcript_file = expected_json

    # Step 4: Normalize & reverify Manifest
    manifest_needs_update = False
    if not manifest_file or manifest_file.name != expected_manifest.name:
        manifest_needs_update = True
    elif expected_md.exists() and expected_json.exists():
        # Check if manifest matches
        mdata = _load_json(expected_manifest)
        if not mdata or mdata.get("slug") != file_slug:
            manifest_needs_update = True
        else:
            files_map = mdata.get("files", {})
            if expected_md.name not in files_map or expected_json.name not in files_map:
                manifest_needs_update = True

    if manifest_needs_update:
        actions.append(f"update_manifest: {expected_manifest.name}")
        if not dry_run:
            target_md_path = md_file or expected_md
            target_json_path = transcript_file or expected_json

            md_bytes = target_md_path.read_bytes() if target_md_path.exists() else b""
            json_bytes = target_json_path.read_bytes() if target_json_path.exists() else b""

            manifest_content = info["manifest_data"] or {}
            manifest_content["schema_version"] = 1
            manifest_content["status"] = "complete"
            manifest_content["conversation_id"] = conversation_id
            manifest_content["conversation_url"] = (
                (info["transcript_data"] or {}).get("source", {}).get("conversation_url")
                or manifest_content.get("conversation_url")
                or f"https://chatgpt.com/c/{conversation_id}"
            )
            manifest_content["slug"] = file_slug
            manifest_content["files"] = {
                expected_json.name: {
                    "bytes": len(json_bytes),
                    "sha256": hashlib.sha256(json_bytes).hexdigest(),
                },
                expected_md.name: {
                    "bytes": len(md_bytes),
                    "sha256": hashlib.sha256(md_bytes).hexdigest(),
                },
            }

            old_manifest_was_tracked = (
                manifest_file is not None
                and is_git_tracked(manifest_file, repo_root)
                and repo_root is not None
            )

            expected_manifest.write_text(
                json.dumps(manifest_content, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            if manifest_file and manifest_file.resolve() != expected_manifest.resolve():
                if old_manifest_was_tracked and repo_root is not None:
                    git_rm(manifest_file, repo_root)
                    git_add(expected_manifest, repo_root)
                elif manifest_file.exists():
                    manifest_file.unlink()
            elif old_manifest_was_tracked and repo_root is not None:
                git_add(expected_manifest, repo_root)

    return {
        "directory": str(dir_path),
        "slug": file_slug,
        "title": title,
        "conversation_id": conversation_id,
        "status": "modified" if actions else "already_clean",
        "actions": actions,
    }


def cleanup_all(
    exports_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Clean all export subdirectories inside exports_dir."""
    if not exports_dir.is_dir():
        return {
            "status": "error",
            "message": f"Exports directory does not exist: {exports_dir}",
            "exports_directory": str(exports_dir.resolve()),
            "dry_run": dry_run,
            "modified_count": 0,
            "total_count": 0,
            "results": [],
        }

    repo_root = find_repo_root(exports_dir)
    subdirs = [p for p in sorted(exports_dir.iterdir()) if p.is_dir()]
    results: list[dict[str, Any]] = []
    modified_count = 0

    for subdir in subdirs:
        info = inspect_export_directory(subdir)
        res = clean_export_directory(info, repo_root, dry_run=dry_run)
        if res["status"] == "modified":
            modified_count += 1
        results.append(res)

    return {
        "status": "ok",
        "exports_directory": str(exports_dir.resolve()),
        "dry_run": dry_run,
        "total_count": len(subdirs),
        "modified_count": modified_count,
        "results": results,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cleanup_chatgpt_exports.py",
        description=(
            "Audit and normalize ChatGPT conversation exports to use semantic slugs for "
            "folder and filenames, updating integrity manifests and preserving git tracking."
        ),
    )
    parser.add_argument(
        "--exports-dir",
        default="CHATGPT-EXPORTS",
        help="Directory containing exported conversations (default: CHATGPT-EXPORTS).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview planned changes without writing to disk or git.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output to stdout.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    exports_candidate = Path(args.exports_dir)
    if not exports_candidate.is_dir():
        repo_root = find_repo_root(Path.cwd())
        if repo_root and (repo_root / args.exports_dir).is_dir():
            exports_candidate = repo_root / args.exports_dir
    exports_path = exports_candidate.resolve()
    result = cleanup_all(exports_path, dry_run=args.dry_run)

    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        prefix = "[DRY-RUN] " if args.dry_run else ""
        print(f"{prefix}ChatGPT Exports Cleanup Summary:")
        print(f"  Directory: {result['exports_directory']}")
        print(f"  Inspected: {result['total_count']} export(s)")
        print(f"  Modified : {result['modified_count']} export(s)\n")

        for item in result["results"]:
            status_tag = f"[{item['status'].upper()}]"
            print(f"  {status_tag:15} {item['slug']}")
            for action in item["actions"]:
                print(f"    - {action}")

    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
