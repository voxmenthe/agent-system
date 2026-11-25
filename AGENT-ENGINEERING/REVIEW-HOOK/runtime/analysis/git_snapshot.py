"""Byte-exact, read-only Git snapshots for one frozen review range.

Only immutable objects addressed by full object IDs are read.  The mutable
index and worktree are never consulted for measured source content.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .model import CommitRange, RepositoryIdentity, TargetRole

_FULL_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HUNK = re.compile(
    br"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@"
)


class GitSnapshotError(RuntimeError):
    """The requested immutable range could not be represented honestly."""


class GitSnapshotTimeout(GitSnapshotError):
    """A bounded Git operation exceeded its deadline."""


class SnapshotScopeError(GitSnapshotError):
    """The range exceeded a bound while retaining its complete file manifest."""

    def __init__(self, issue: str, paths: Sequence[str]) -> None:
        super().__init__(issue)
        self.issue = issue
        self.paths = tuple(paths)
        self.commit_range = None
        self.repository = None
        self.ordered_commits = ()
        self.first_parent_resolution = False
        self.files_changed = 0
        self.test_paths = ()

    def attach(
        self,
        *,
        commit_range: CommitRange,
        repository: RepositoryIdentity,
        ordered_commits: Sequence[str],
        files_changed: int,
        test_paths: Sequence[str],
        complete_python_paths: Sequence[str],
    ) -> "SnapshotScopeError":
        self.commit_range = commit_range
        self.repository = repository
        self.ordered_commits = tuple(ordered_commits)
        self.files_changed = files_changed
        self.test_paths = tuple(test_paths)
        self.paths = tuple(complete_python_paths)
        return self


class ChangeKind(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED_EXACT = "renamed-exact"
    RENAMED_AMBIGUOUS = "renamed-ambiguous"


@dataclass(frozen=True)
class LineInterval:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 1 or self.end < self.start:
            raise ValueError("line intervals must be positive and ordered")

    def contains(self, line: int) -> bool:
        return self.start <= line <= self.end

    def intersects(self, start: int, end: int) -> bool:
        return self.start <= end and start <= self.end


@dataclass(frozen=True)
class DiffHunk:
    before: Optional[LineInterval]
    after: Optional[LineInterval]


@dataclass(frozen=True)
class ChangedFile:
    path: str
    old_path: Optional[str]
    change: ChangeKind
    before_blob: Optional[bytes]
    after_blob: Optional[bytes]
    hunks: Tuple[DiffHunk, ...]
    role: TargetRole

    @property
    def is_python(self) -> bool:
        return self.path.endswith(".py") or bool(
            self.old_path and self.old_path.endswith(".py")
        )

    @property
    def comparison_safe(self) -> bool:
        return self.change is not ChangeKind.RENAMED_AMBIGUOUS

    @property
    def after_changed_lines(self) -> Tuple[LineInterval, ...]:
        return tuple(hunk.after for hunk in self.hunks if hunk.after is not None)


@dataclass(frozen=True)
class SnapshotConfig:
    git_timeout_seconds: float = 10.0
    max_python_files: int = 64
    max_blob_bytes: int = 2_000_000
    max_total_blob_bytes: int = 8_000_000
    max_tree_listing_bytes: int = 8_000_000

    def __post_init__(self) -> None:
        for name in (
            "max_python_files",
            "max_blob_bytes",
            "max_total_blob_bytes",
            "max_tree_listing_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError("{} must be a positive integer".format(name))
        if self.git_timeout_seconds <= 0:
            raise ValueError("git_timeout_seconds must be positive")


class _Git:
    def __init__(self, candidate: Path, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        root = self.run_at(candidate, ("rev-parse", "--show-toplevel"))
        decoded = root.decode("utf-8", "surrogateescape").strip()
        if not decoded:
            raise GitSnapshotError("git returned an empty repository root")
        self.root = Path(decoded).resolve()

    def process(
        self,
        cwd: Path,
        arguments: Sequence[str],
        *,
        input_bytes: Optional[bytes] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        try:
            process = subprocess.run(
                ["git", "-C", str(cwd), *arguments],
                input=input_bytes,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.TimeoutExpired):
                raise GitSnapshotTimeout(
                    "git command timed out: {}".format(" ".join(arguments[:4]))
                ) from error
            raise GitSnapshotError("git is unavailable: {}".format(error)) from error
        if check and process.returncode != 0:
            detail = process.stderr.decode("utf-8", "replace").strip()[:400]
            raise GitSnapshotError(
                "git {} failed ({}): {}".format(
                    " ".join(arguments[:5]), process.returncode, detail
                )
            )
        return process

    def run_at(
        self,
        cwd: Path,
        arguments: Sequence[str],
        *,
        input_bytes: Optional[bytes] = None,
        check: bool = True,
    ) -> bytes:
        return self.process(
            cwd, arguments, input_bytes=input_bytes, check=check
        ).stdout

    def run(
        self,
        arguments: Sequence[str],
        *,
        input_bytes: Optional[bytes] = None,
        check: bool = True,
    ) -> bytes:
        return self.run_at(
            self.root, arguments, input_bytes=input_bytes, check=check
        )

    def object_type(self, oid: str) -> str:
        return self.run(("cat-file", "-t", oid)).decode("ascii").strip()

    def empty_tree(self) -> str:
        return self.run(
            ("hash-object", "-t", "tree", "--stdin"), input_bytes=b""
        ).decode("ascii").strip()

    def blob(self, commit: str, path: str, maximum: int) -> bytes:
        spec = "{}:{}".format(commit, path)
        raw_size = self.run(("cat-file", "-s", spec)).decode("ascii").strip()
        try:
            size = int(raw_size)
        except ValueError as error:
            raise GitSnapshotError(
                "invalid blob size for {}: {!r}".format(path, raw_size)
            ) from error
        if size > maximum:
            raise SnapshotScopeError(
                "blob-too-large:{}:{}>{}".format(path, size, maximum), (path,)
            )
        blob = self.run(("cat-file", "blob", spec))
        if len(blob) != size:
            raise GitSnapshotError(
                "blob size changed while reading immutable object {}".format(spec)
            )
        return blob


@dataclass(frozen=True)
class GitSnapshot:
    repository_root: Path
    repository: RepositoryIdentity
    commit_range: CommitRange
    ordered_commits: Tuple[str, ...]
    first_parent_resolution: bool
    files: Tuple[ChangedFile, ...]
    _git: _Git
    _config: SnapshotConfig

    @property
    def python_files(self) -> Tuple[ChangedFile, ...]:
        return tuple(item for item in self.files if item.is_python)

    @property
    def files_changed(self) -> int:
        return len(self.files)

    @property
    def test_paths(self) -> Tuple[str, ...]:
        return tuple(
            sorted(item.path for item in self.files if item.role is TargetRole.TEST)
        )

    def list_committed_paths(self, basename: Optional[str] = None) -> Tuple[str, ...]:
        payload = self._git.run(
            ("ls-tree", "-r", "-z", "--name-only", self.commit_range.after)
        )
        if len(payload) > self._config.max_tree_listing_bytes:
            raise SnapshotScopeError(
                "tree-listing-too-large:{}>{}".format(
                    len(payload), self._config.max_tree_listing_bytes
                ),
                tuple(item.path for item in self.python_files),
            )
        paths = tuple(
            row.decode("utf-8", "surrogateescape")
            for row in payload.split(b"\0")
            if row
        )
        if basename is None:
            return paths
        return tuple(path for path in paths if Path(path).name == basename)

    def read_after_blob(self, path: str, maximum: int = 1_000_000) -> bytes:
        return self._git.blob(self.commit_range.after, path, maximum)

    def grep_after(self, identifier: str) -> Tuple[Tuple[str, int, str], ...]:
        process = self._git.process(
            self._git.root,
            (
                "grep",
                "-n",
                "-w",
                "-e",
                identifier,
                self.commit_range.after,
                "--",
                "*.py",
            ),
            check=False,
        )
        if process.returncode not in (0, 1):
            detail = process.stderr.decode("utf-8", "replace").strip()[:400]
            raise GitSnapshotError("git grep failed: {}".format(detail))
        prefix = (self.commit_range.after + ":").encode("ascii")
        rows: List[Tuple[str, int, str]] = []
        for raw in process.stdout.splitlines():
            if raw.startswith(prefix):
                raw = raw[len(prefix) :]
            parts = raw.split(b":", 2)
            if len(parts) != 3 or not parts[1].isdigit():
                continue
            rows.append(
                (
                    parts[0].decode("utf-8", "surrogateescape"),
                    int(parts[1]),
                    parts[2].decode("utf-8", "replace"),
                )
            )
        return tuple(rows)


@dataclass(frozen=True)
class _PathChange:
    change: ChangeKind
    old_path: Optional[str]
    new_path: Optional[str]

    @property
    def path(self) -> str:
        value = self.new_path or self.old_path
        if value is None:
            raise AssertionError("a changed path has no name")
        return value

    @property
    def is_python(self) -> bool:
        return self.path.endswith(".py") or bool(
            self.old_path and self.old_path.endswith(".py")
        )


def _decode_path(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


def _parse_name_status(payload: bytes) -> Tuple[_PathChange, ...]:
    tokens = [token for token in payload.split(b"\0") if token]
    rows: List[_PathChange] = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii", "strict")
        if status.startswith("R"):
            if index + 2 >= len(tokens):
                raise GitSnapshotError("truncated rename record in Git diff")
            score = int(status[1:]) if status[1:].isdigit() else 0
            rows.append(
                _PathChange(
                    ChangeKind.RENAMED_EXACT
                    if score == 100
                    else ChangeKind.RENAMED_AMBIGUOUS,
                    _decode_path(tokens[index + 1]),
                    _decode_path(tokens[index + 2]),
                )
            )
            index += 3
            continue
        if index + 1 >= len(tokens):
            raise GitSnapshotError("truncated path record in Git diff")
        code = status[:1]
        path = _decode_path(tokens[index + 1])
        change = {
            "A": ChangeKind.ADDED,
            "D": ChangeKind.DELETED,
            "M": ChangeKind.MODIFIED,
            "T": ChangeKind.MODIFIED,
        }.get(code)
        if change is None:
            raise GitSnapshotError("unsupported Git diff status: {}".format(status))
        rows.append(
            _PathChange(
                change,
                None if change is ChangeKind.ADDED else path,
                None if change is ChangeKind.DELETED else path,
            )
        )
        index += 2
    return tuple(rows)


def _interval(start: int, count: int) -> Optional[LineInterval]:
    if count == 0:
        return None
    return LineInterval(start, start + count - 1)


def _hunks(
    git: _Git, before: str, after: str, change: _PathChange
) -> Tuple[DiffHunk, ...]:
    paths = tuple(path for path in (change.old_path, change.new_path) if path)
    payload = git.run(("diff", "-U0", "-M", before, after, "--", *paths))
    rows: List[DiffHunk] = []
    for line in payload.splitlines():
        match = _HUNK.match(line)
        if match is None:
            continue
        before_start = int(match.group(1))
        before_count = int(match.group(2) or b"1")
        after_start = int(match.group(3))
        after_count = int(match.group(4) or b"1")
        rows.append(
            DiffHunk(
                _interval(before_start, before_count),
                _interval(after_start, after_count),
            )
        )
    return tuple(rows)


def target_role(path: str) -> TargetRole:
    lowered = tuple(part.lower() for part in Path(path).parts)
    filename = lowered[-1] if lowered else ""
    if (
        any(part in {"test", "tests", "testing"} for part in lowered[:-1])
        or filename == "conftest.py"
        or filename.startswith("test_")
        or filename.endswith("_test.py")
    ):
        return TargetRole.TEST
    if any(
        part in {"generated", "vendor", "vendored", "third_party"}
        for part in lowered[:-1]
    ) or filename.endswith(("_pb2.py", "_generated.py")):
        return TargetRole.GENERATED
    if filename in {"pyproject.toml", "setup.py", "setup.cfg"}:
        return TargetRole.CONFIGURATION
    if path.endswith(".py"):
        return TargetRole.PRODUCTION
    return TargetRole.UNKNOWN


def _validate_oid(value: str, name: str) -> None:
    if not isinstance(value, str) or _FULL_OID.fullmatch(value) is None:
        raise GitSnapshotError(
            "{} must be a full lowercase 40- or 64-hex object ID".format(name)
        )


def _repository_identity(git: _Git) -> RepositoryIdentity:
    payload = git.run(
        ("rev-parse", "--path-format=absolute", "--git-common-dir")
    )
    common = payload.decode("utf-8", "surrogateescape").strip()
    if not common or not Path(common).is_absolute():
        raise GitSnapshotError("Git returned an invalid common directory")
    canonical = str(Path(common).resolve())
    digest = hashlib.sha256(
        ("review-repository/v1\0" + canonical).encode("utf-8")
    ).hexdigest()
    return RepositoryIdentity("sha256:" + digest)


def capture_snapshot(
    repo: Path,
    before: str,
    after: str,
    *,
    config: Optional[SnapshotConfig] = None,
) -> GitSnapshot:
    """Capture one exact ancestor range from committed objects only."""
    cfg = config or SnapshotConfig()
    _validate_oid(before, "base")
    _validate_oid(after, "head")
    if before == after:
        raise GitSnapshotError("base and head must identify different objects")
    git = _Git(Path(repo), cfg.git_timeout_seconds)
    if git.object_type(after) != "commit":
        raise GitSnapshotError("head must identify a commit object")
    empty_tree = git.empty_tree()
    if before == empty_tree:
        parent_row = git.run(("rev-list", "--parents", "-n", "1", after)).split()
        if len(parent_row) != 1:
            raise GitSnapshotError(
                "the empty-tree base is valid only for an initial commit"
            )
        ordered = (after,)
    else:
        if git.object_type(before) != "commit":
            raise GitSnapshotError("base must identify a commit or the empty tree")
        ancestry = git.process(
            git.root,
            ("merge-base", "--is-ancestor", before, after),
            check=False,
        )
        if ancestry.returncode == 1:
            raise GitSnapshotError("base is not an ancestor of head")
        if ancestry.returncode != 0:
            detail = ancestry.stderr.decode("utf-8", "replace").strip()[:400]
            raise GitSnapshotError(
                "could not validate commit ancestry: {}".format(detail)
            )
        raw_ordered = git.run(
            ("rev-list", "--reverse", "--topo-order", "{}..{}".format(before, after))
        )
        ordered = tuple(
            row.decode("ascii") for row in raw_ordered.splitlines() if row
        )
    if not ordered or ordered[-1] != after:
        raise GitSnapshotError("Git returned an incomplete ordered commit range")

    raw_changes = git.run(
        ("diff", "--name-status", "-z", "-M", before, after, "--")
    )
    changes = _parse_name_status(raw_changes)
    python_paths = tuple(sorted(item.path for item in changes if item.is_python))
    commit_range = CommitRange(before, after, len(ordered))
    repository = _repository_identity(git)
    test_paths = tuple(
        sorted(item.path for item in changes if target_role(item.path) is TargetRole.TEST)
    )
    if len(python_paths) > cfg.max_python_files:
        raise SnapshotScopeError(
            "python-file-scope-too-large:{}>{}".format(
                len(python_paths), cfg.max_python_files
            ),
            python_paths,
        ).attach(
            commit_range=commit_range,
            repository=repository,
            ordered_commits=ordered,
            files_changed=len(changes),
            test_paths=test_paths,
            complete_python_paths=python_paths,
        )

    total_bytes = 0
    files: List[ChangedFile] = []
    try:
        for item in changes:
            before_blob = None
            after_blob = None
            if item.is_python and item.old_path is not None:
                before_blob = git.blob(before, item.old_path, cfg.max_blob_bytes)
                total_bytes += len(before_blob)
            if item.is_python and item.new_path is not None:
                after_blob = git.blob(after, item.new_path, cfg.max_blob_bytes)
                total_bytes += len(after_blob)
            if total_bytes > cfg.max_total_blob_bytes:
                raise SnapshotScopeError(
                    "python-blob-scope-too-large:{}>{}".format(
                        total_bytes, cfg.max_total_blob_bytes
                    ),
                    python_paths,
                )
            files.append(
                ChangedFile(
                    path=item.path,
                    old_path=(
                        item.old_path if item.old_path != item.new_path else None
                    ),
                    change=item.change,
                    before_blob=before_blob,
                    after_blob=after_blob,
                    hunks=_hunks(git, before, after, item) if item.is_python else (),
                    role=target_role(item.path),
                )
            )
    except SnapshotScopeError as error:
        raise error.attach(
            commit_range=commit_range,
            repository=repository,
            ordered_commits=ordered,
            files_changed=len(changes),
            test_paths=test_paths,
            complete_python_paths=python_paths,
        )

    return GitSnapshot(
        repository_root=git.root,
        repository=repository,
        commit_range=commit_range,
        ordered_commits=ordered,
        first_parent_resolution=False,
        files=tuple(sorted(files, key=lambda item: item.path)),
        _git=git,
        _config=cfg,
    )


__all__ = [
    "ChangeKind",
    "ChangedFile",
    "DiffHunk",
    "GitSnapshot",
    "GitSnapshotError",
    "GitSnapshotTimeout",
    "LineInterval",
    "SnapshotConfig",
    "SnapshotScopeError",
    "capture_snapshot",
    "target_role",
]
