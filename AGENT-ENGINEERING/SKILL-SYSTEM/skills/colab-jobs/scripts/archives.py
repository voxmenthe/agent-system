"""Archives for push and pull: which files a pushed folder includes, and the
checks a pulled archive passes before anything is extracted locally."""
from __future__ import annotations

import os
import tarfile
from pathlib import Path, PurePosixPath

JUNK_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".ipynb_checkpoints",
             ".mypy_cache", ".pytest_cache"}


class UnsafeArchive(ValueError):
    """An entry would land outside the destination, or is a link or device."""


def make_archive(root: Path, archive: Path) -> tuple[int, int]:
    count, size = 0, 0
    with tarfile.open(archive, "w:gz", dereference=True) as tar:
        for parent, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in JUNK_DIRS)
            for file_name in sorted(names):
                full = Path(parent) / file_name
                if file_name == ".DS_Store" or file_name.endswith(".pyc") or not full.is_file():
                    continue
                tar.add(full, arcname=full.relative_to(root).as_posix(), recursive=False)
                count += 1
                size += full.stat().st_size
    return count, size


def safe_extract(archive: Path, dest: Path) -> None:
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        for member in members:
            parts = PurePosixPath(member.name).parts
            if member.name.startswith("/") or ".." in parts or not (member.isfile() or member.isdir()):
                raise UnsafeArchive("refusing unsafe archive entry %r" % member.name)
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, members=members, filter="data")
        else:
            tar.extractall(dest, members=members)
