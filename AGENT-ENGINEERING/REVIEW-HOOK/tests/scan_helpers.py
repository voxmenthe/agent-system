"""Small disposable Git repositories for Review Scan tests."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class TemporaryGitRepo:
    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.path = Path(self._temporary.name) / "repository"
        self.git("init", "-q", str(self.path), cwd=Path(self._temporary.name))
        self.git("config", "user.email", "review-scan@example.invalid")
        self.git("config", "user.name", "Review Scan Test")

    def close(self) -> None:
        self._temporary.cleanup()

    def git(
        self,
        *arguments: str,
        cwd: Optional[Path] = None,
        input_bytes: Optional[bytes] = None,
    ) -> str:
        process = subprocess.run(
            ["git", *arguments],
            cwd=cwd or self.path,
            input=input_bytes,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            raise AssertionError(
                "git {} failed ({}): {}".format(
                    " ".join(arguments),
                    process.returncode,
                    process.stderr.decode("utf-8", "replace"),
                )
            )
        return process.stdout.decode("utf-8", "surrogateescape").strip()

    def write(self, relative: str, content: str) -> Path:
        destination = self.path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    def remove(self, relative: str) -> None:
        os.unlink(self.path / relative)

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def empty_tree(self) -> str:
        return self.git("hash-object", "-t", "tree", "--stdin", input_bytes=b"")

