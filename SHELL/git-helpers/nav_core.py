"""Read-only Git comparisons and complete-source structural evidence."""

import argparse
import ast
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class NavError(Exception):
    pass


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    data: bytes | None = None,
    ok: tuple[int, ...] = (0,),
) -> bytes:
    if os.environ.get("G_HELPERS_ECHO") == "1":
        print("+ " + shlex.join(args), file=sys.stderr)
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_PAGER="cat", PAGER="cat")
    result = subprocess.run(
        args, cwd=cwd, input=data, capture_output=True, env=env, check=False
    )
    if result.returncode not in ok:
        raise NavError(
            f"{shlex.join(args)}: {decode(result.stderr).strip()} "
            f"(exit {result.returncode})"
        )
    if result.stderr:
        print(decode(result.stderr).rstrip(), file=sys.stderr)
    return result.stdout


def decode(value: bytes) -> str:
    return value.decode("utf-8", "surrogateescape")


def label(value: str) -> str:
    return (
        json.dumps(value, ensure_ascii=True)
        if any(ord(c) < 32 or ord(c) > 126 for c in value)
        else value
    )


@dataclass
class Change:
    status: str
    old: str
    new: str
    old_mode: str
    new_mode: str
    old_oid: str
    new_oid: str
    added: str = "?"
    deleted: str = "?"
    category: str = "unknown"

    @property
    def path(self) -> str:
        return self.new

    @property
    def display(self) -> str:
        return (
            label(self.old) + " -> " + label(self.new)
            if self.old != self.new
            else label(self.new)
        )


@dataclass
class Comparison:
    args: list[str]
    title: str
    commit: str | None = None
    worktree: bool = False


@dataclass
class Symbol:
    name: str
    start: int
    end: int
    signature: str


@dataclass
class Hunk:
    text: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int

    def matches(self, pattern: re.Pattern[str]) -> bool:
        return any(
            pattern.search(line[1:])
            for line in self.text.splitlines()[1:]
            if line.startswith(("+", "-"))
        )


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*$", re.MULTILINE)
COLLAPSED = {"lock", "generated", "vendored"}
LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".rb": "ruby",
    ".sh": "bash",
    ".bash": "bash",
}


def split_hunks(patch: str) -> tuple[str, list[Hunk]]:
    matches = list(HUNK.finditer(patch))
    header = patch[: matches[0].start()] if matches else patch
    hunks = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(patch)
        hunks.append(
            Hunk(
                patch[match.start() : end],
                int(match[1]),
                int(match[2] or 1),
                int(match[3]),
                int(match[4] or 1),
            )
        )
    return header, hunks


def intersects(start: int, end: int, line: int, count: int) -> bool:
    # A zero-width side is an insertion/deletion boundary, not a changed source line.
    return count > 0 and start <= line + count - 1 and end >= line


class Repo:
    def __init__(self) -> None:
        self.cwd = Path.cwd()
        self.root = Path(
            decode(run(["git", "rev-parse", "--show-toplevel"])).rstrip("\n")
        )
        self.rules = []
        for path in (
            self.root / ".git-helpers-classes",
            Path(__file__).with_name("classes.tsv"),
        ):
            if not path.exists():
                continue
            for line in path.read_text().splitlines():
                if not line or line.startswith("#"):
                    continue
                fields = line.split("|")
                if len(fields) != 2 or not all(fields):
                    raise NavError(f"Invalid class rule in {path}: {line!r}")
                self.rules.append(tuple(fields))
        self._empty_tree: str | None = None

    @property
    def empty_tree(self) -> str:
        if self._empty_tree is None:
            self._empty_tree = decode(
                self.git("hash-object", "-t", "tree", "--stdin", data=b"")
            ).strip()
        return self._empty_tree

    def git(self, *args: str, data: bytes | None = None) -> bytes:
        return run(
            ["git", "--no-pager", "-c", "diff.relative=false", *args],
            cwd=self.root,
            data=data,
        )

    def rev(self, ref: str) -> str:
        return decode(
            self.git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
        ).strip()

    def head(self) -> str | None:
        found = (
            self.git("rev-parse", "--verify", "--quiet", "HEAD")
            if self.git("rev-parse", "--revs-only", "HEAD").strip()
            else b""
        )
        return decode(found).strip() or None

    def path(self, value: str) -> str:
        absolute = Path(os.path.abspath(self.cwd / value))
        try:
            return absolute.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise NavError(f"Path is outside this worktree: {value!r}") from exc

    def specs(self, paths: list[str]) -> list[str]:
        return [f":(top,literal){p}" for p in paths]

    def classify(self, path: str) -> str:
        for category, glob in self.rules:
            if fnmatch.fnmatchcase(path, glob) or (
                "/" not in glob and fnmatch.fnmatchcase(Path(path).name, glob)
            ):
                return category
        return "unknown"

    def comparison(self, opts: argparse.Namespace) -> Comparison:
        if opts.parent != 1 and not opts.commit:
            raise NavError("--parent requires --commit")
        if opts.commit or not any(
            (opts.staged, opts.unstaged, opts.worktree, opts.branch, opts.between)
        ):
            commit = self.rev(opts.commit or "HEAD")
            parents = decode(self.git("show", "-s", "--format=%P", commit)).split()
            if opts.parent < 1 or opts.parent > max(1, len(parents)):
                raise NavError("Requested parent does not exist")
            base = (
                parents[opts.parent - 1]
                if parents
                else decode(
                    self.git("hash-object", "-t", "tree", "--stdin", data=b"")
                ).strip()
            )
            title = f"commit: {base} -> {commit}"
            if len(parents) > 1:
                title += f" (parent {opts.parent}/{len(parents)}; parents: {' '.join(parents)})"
            return Comparison([base, commit], title, commit)
        if opts.between:
            a, b = [self.rev(ref) for ref in opts.between]
            return Comparison([a, b], f"endpoints: {a} -> {b}")
        if opts.branch:
            base, head = self.rev(opts.branch), self.rev("HEAD")
            bases = decode(self.git("merge-base", "--all", base, head)).split()
            if len(bases) != 1:
                raise NavError("Branch comparison requires one unambiguous merge base")
            return Comparison(
                [bases[0], head], f"branch (committed only): {bases[0]} -> {head}"
            )
        if opts.unstaged:
            return Comparison(
                [], "unstaged: index -> tracked working tree", worktree=True
            )
        head = self.head()
        if opts.staged:
            return Comparison(
                ["--cached", *([head] if head else [])],
                f"staged: {head or 'empty tree (unborn HEAD)'} -> index",
            )
        base = (
            head
            or decode(
                self.git("hash-object", "-t", "tree", "--stdin", data=b"")
            ).strip()
        )
        return Comparison(
            [base],
            f"worktree: {head or 'empty tree (unborn HEAD)'} -> tracked working tree",
            worktree=True,
        )

    def diff(self, comparison: Comparison, flags: list[str], paths: list[str]) -> bytes:
        return self.git(
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--ignore-submodules=none",
            "--find-renames",
            *flags,
            *comparison.args,
            "--",
            *self.specs(paths),
        )

    def changes(self, comparison: Comparison, paths: list[str]) -> list[Change]:
        raw = iter(
            self.diff(comparison, ["--raw", "--no-abbrev", "-z"], paths).split(b"\0")
        )
        changes = []
        for header in raw:
            if not header:
                continue
            mode_a, mode_b, oid_a, oid_b, status = decode(header).lstrip(":").split()
            old = decode(next(raw))
            new = decode(next(raw)) if status.startswith(("R", "C")) else old
            changes.append(
                Change(
                    status,
                    old,
                    new,
                    mode_a,
                    mode_b,
                    oid_a,
                    oid_b,
                    category=self.classify(new),
                )
            )
        stats = iter(self.diff(comparison, ["--numstat", "-z"], paths).split(b"\0"))
        counts = {}
        for row in stats:
            if not row:
                continue
            added, deleted, path = row.split(b"\t", 2)
            old = new = decode(path)
            if not path:
                old, new = decode(next(stats)), decode(next(stats))
            counts[(old, new)] = (decode(added), decode(deleted))
        for change in changes:
            change.added, change.deleted = counts[(change.old, change.new)]
        return changes

    def patch(
        self, comparison: Comparison, change: Change, flags: list[str] | None = None
    ) -> str:
        return decode(
            self.diff(
                comparison, flags or [], list(dict.fromkeys([change.old, change.new]))
            )
        )

    def blob(self, comparison: Comparison, change: Change, side: str) -> bytes:
        mode = change.old_mode if side == "before" else change.new_mode
        oid = change.old_oid if side == "before" else change.new_oid
        if change.status == "U":
            raise NavError(
                "Unresolved index entries have no single before/after blob; use the native patch"
            )
        if mode == "000000":
            return b""
        if mode == "160000":
            raise NavError("Submodule pointer, not a source blob; use the native patch")
        if side == "after" and comparison.worktree:
            path = self.root / change.new
            return (
                os.fsencode(os.readlink(path))
                if mode == "120000"
                else path.read_bytes()
            )
        return self.git("cat-file", "blob", oid)

    def tracked(self, paths: list[str], at: str | None = None) -> list[str]:
        args = (
            ["ls-tree", "-r", "--name-only", "-z", at]
            if at
            else ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        )
        return sorted(
            {
                decode(p)
                for p in self.git(*args, "--", *self.specs(paths)).split(b"\0")
                if p
            }
        )

    def source(self, path: str, at: str | None = None) -> bytes:
        if at:
            return self.git("show", f"{at}:{path}")
        target = self.root / path
        if target.is_symlink() or not target.is_file():
            raise NavError(f"Not a regular source file: {label(path)}")
        return target.read_bytes()


def symbols(data: bytes, path: str) -> list[Symbol]:
    if Path(path).suffix == ".py":
        try:
            tree = ast.parse(data)
        except (SyntaxError, ValueError) as exc:
            raise NavError(
                f"Python extraction unavailable for {label(path)}: {exc}"
            ) from exc
        result = []

        def visit(node: ast.AST, prefix: str) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    name = prefix + child.name
                    start = min(
                        [child.lineno, *[d.lineno for d in child.decorator_list]]
                    )
                    if isinstance(child, ast.ClassDef):
                        bases = [ast.unparse(b) for b in child.bases + child.keywords]
                        signature = f"class {child.name}({', '.join(bases)})"
                    else:
                        signature = f"{'async ' if isinstance(child, ast.AsyncFunctionDef) else ''}def {child.name}({ast.unparse(child.args)})"
                        if child.returns:
                            signature += " -> " + ast.unparse(child.returns)
                    if child.decorator_list:
                        signature = (
                            " ".join("@" + ast.unparse(d) for d in child.decorator_list)
                            + " "
                            + signature
                        )
                    result.append(Symbol(name, start, child.end_lineno, signature))
                    visit(child, name + ".")
                else:
                    visit(child, prefix)

        visit(tree, "")
        return result
    lang = LANGUAGES.get(Path(path).suffix)
    if not lang or not shutil.which("ast-grep"):
        raise NavError(
            f"Structural extraction unavailable for {label(path)}; use explicit line ranges"
        )
    rows = json.loads(
        run(
            [
                "ast-grep",
                "outline",
                "--stdin",
                "--lang",
                lang,
                "--items",
                "all",
                "--view",
                "expanded",
                "--json=compact",
            ],
            data=data,
        )
    )
    result = []

    def flatten(items: list[dict], prefix: str = "") -> None:
        for item in items:
            name = prefix + item["name"]
            span = item["range"]
            result.append(
                Symbol(
                    name,
                    span["start"]["line"] + 1,
                    span["end"]["line"] + 1,
                    item["signature"],
                )
            )
            flatten(item.get("members", []), name + ".")

    for row in rows:
        flatten(row["items"])
    return result


def syntax_patch(repo: Repo, comparison: Comparison, change: Change) -> str:
    if not shutil.which("difft"):
        print("difft unavailable; showing native patch", file=sys.stderr)
        return repo.patch(comparison, change)
    if (
        change.old_mode in {"120000", "160000"}
        or change.new_mode in {"120000", "160000"}
        or change.status == "U"
    ):
        return repo.patch(comparison, change)
    with tempfile.TemporaryDirectory(prefix="git-nav-difft-") as directory:
        before = Path(directory) / ("before" + Path(change.old).suffix)
        after = Path(directory) / ("after" + Path(change.new).suffix)
        before.write_bytes(repo.blob(comparison, change, "before"))
        after.write_bytes(repo.blob(comparison, change, "after"))
        metadata, _ = split_hunks(repo.patch(comparison, change))
        width = os.environ.get(
            "FZF_PREVIEW_COLUMNS", str(shutil.get_terminal_size().columns)
        )
        rendered = decode(
            run(
                ["difft", "--color=never", "--width", width, str(before), str(after)],
                ok=(0, 1),
            )
        )
        return metadata + rendered.replace(
            str(before), "before: " + label(change.old)
        ).replace(str(after), "after: " + label(change.new))


def selected(opts: argparse.Namespace) -> bool:
    return any(
        (
            opts.commit,
            opts.staged,
            opts.unstaged,
            opts.worktree,
            opts.branch,
            opts.between,
        )
    )


def paths_for(repo: Repo, opts: argparse.Namespace) -> list[str]:
    return [repo.path(path) for path in opts.paths]


def range_spec(repo: Repo, value: str) -> str:
    pieces = value.split("..")
    if len(pieces) != 2 or any(not p or p.startswith(".") for p in pieces):
        raise NavError("Use an explicit two-tip range A..B")
    return "..".join(repo.rev(p) for p in pieces)


def commit_comparison(repo: Repo, commit: str) -> Comparison:
    opts = argparse.Namespace(
        commit=commit,
        parent=1,
        staged=False,
        unstaged=False,
        worktree=False,
        branch=None,
        between=None,
    )
    return repo.comparison(opts)


def commit_meta(
    repo: Repo, commits: list[str]
) -> dict[str, tuple[str, str, list[str]]]:
    """One git log for short hash, subject, and parents of each commit."""
    if not commits:
        return {}
    raw = decode(
        repo.git(
            "log",
            "--no-walk=unsorted",
            "--format=%H%x00%h%x00%s%x00%P",
            *commits,
        )
    )
    meta: dict[str, tuple[str, str, list[str]]] = {}
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\0")
        if len(parts) != 4:
            continue
        full, short, subject, parents = parts
        meta[full] = (short, subject, parents.split() if parents else [])
    return meta


def comparison_from_meta(
    repo: Repo, commit: str, short: str, parents: list[str]
) -> Comparison:
    base = parents[0] if parents else repo.empty_tree
    title = f"commit: {base} -> {commit}"
    if len(parents) > 1:
        title += f" (parent 1/{len(parents)}; parents: {' '.join(parents)})"
    return Comparison([base, commit], title, commit)


def batch_name_status(
    repo: Repo, commits: list[str], paths: list[str]
) -> dict[str, list[tuple[str, str, str]]]:
    """One diff-tree --stdin for path status; first parent only for merges.

    Returns commit -> [(status, old, new)] without line counts.
    """
    if not commits:
        return {}
    args = ["diff-tree", "--stdin", "--root", "-r", "--name-status", "-M", "-m"]
    if paths:
        args += ["--", *repo.specs(paths)]
    raw = decode(repo.git(*args, data=("".join(c + "\n" for c in commits)).encode()))
    by_commit: dict[str, list[tuple[str, str, str]]] = {sha: [] for sha in commits}
    current: str | None = None
    skipping = False  # skip extra parent blocks on merges
    seen: set[str] = set()
    for line in raw.splitlines():
        if not line:
            continue
        if re.fullmatch(r"[0-9a-f]{40,64}", line):
            current = line
            if current in seen:
                skipping = True
            else:
                seen.add(current)
                skipping = False
            continue
        if current is None or skipping or current not in by_commit:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status[:1] in {"R", "C"} and len(parts) >= 3:
            by_commit[current].append((status, parts[1], parts[2]))
        else:
            by_commit[current].append((status, parts[1], parts[1]))
    return by_commit
