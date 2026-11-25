"""Read-only fzf drill-down; picker values are opaque integer IDs, never paths."""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from nav_core import (
    Change,
    Comparison,
    NavError,
    Repo,
    batch_name_status,
    commit_meta,
    comparison_from_meta,
    decode,
    label,
    split_hunks,
    syntax_patch,
)

# Preview coloring: delta when installed, else a compact built-in colorizer.
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_CYAN = "\x1b[36m"
_ADD = "\x1b[38;5;114m"
_ADD_BG = "\x1b[48;5;22m"
_DEL = "\x1b[38;5;167m"
_DEL_BG = "\x1b[48;5;52m"


@dataclass
class CommitChoice:
    comparison: Comparison
    headline: str
    reasons: list[str]
    evidence: list[str]

    @property
    def display(self) -> str:
        reason = ", ".join(self.reasons) if self.reasons else "other changes"
        return f"{'*' if self.reasons else ' '} {reason} | {self.headline}"


def suggest_commits(
    repo: Repo, commits: list[str], paths: list[str], chronological: bool
) -> list[CommitChoice]:
    """Score commits with two batched git calls, not per-commit diffs."""
    kinds = {
        "source": "code",
        "test": "tests",
        "guidance": "agent guidance",
        "build": "build/setup",
    }
    meta = commit_meta(repo, commits)
    files = batch_name_status(repo, commits, paths)
    choices = []
    for sha in commits:
        if sha not in meta:
            continue
        short, subject, parents = meta[sha]
        reasons = []
        evidence = []
        counts: Counter[str] = Counter()
        shell = False
        for status, old, new in files.get(sha, []):
            category = repo.classify(new)
            counts[category] += 1
            if category == "source" and Path(new).name.startswith((".bash", ".zsh")):
                shell = True
            if category in kinds:
                display = label(old) + " -> " + label(new) if old != new else label(new)
                evidence.append(f"{status} {display}")
        reasons.extend(
            f"{count} {kinds[kind]}" for kind, count in counts.items() if kind in kinds
        )
        if shell:
            reasons.append("shell helpers")
        comparison = comparison_from_meta(repo, sha, short, parents)
        choices.append(
            CommitChoice(comparison, f"{short} {subject}", reasons, evidence)
        )
    if not chronological:
        # Stable grouping keeps recency within each group, without rewarding bulk edits.
        choices.sort(key=lambda choice: not choice.reasons)
    return choices


def preview_width() -> str:
    return os.environ.get("FZF_PREVIEW_COLUMNS") or str(
        shutil.get_terminal_size().columns
    )


def colorize_patch(text: str) -> str:
    """ANSI highlight for a git/difft patch when delta is unavailable."""
    out = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\n")
        ending = line[len(body) :]
        if body.startswith(("diff --git", "diff --cc", "--- ", "+++ ")):
            out.append(f"{_BOLD}{body}{_RESET}{ending}")
        elif body.startswith("@@"):
            out.append(f"{_BOLD}{_CYAN}{body}{_RESET}{ending}")
        elif body.startswith("+"):
            out.append(f"{_ADD_BG}{_ADD}{body}{_RESET}{ending}")
        elif body.startswith("-"):
            out.append(f"{_DEL_BG}{_DEL}{body}{_RESET}{ending}")
        elif body.startswith(("\\ No newline", "index ", "new file mode", "deleted file mode", "similarity index", "rename ", "copy ", "old mode", "new mode")):
            out.append(f"{_DIM}{body}{_RESET}{ending}")
        elif body:
            out.append(f"{_DIM}{body}{_RESET}{ending}")
        else:
            out.append(line)
    return "".join(out)


def format_patch(text: str) -> str:
    """Colorize patch-like preview body; prefer delta, fall back to built-in."""
    if shutil.which("delta"):
        result = subprocess.run(
            [
                "delta",
                "--paging=never",
                "--width",
                preview_width(),
                "--line-numbers",
                "--keep-plus-minus-markers",
                "--side-by-side=false",
                "--hyperlinks=false",
                "--navigate=false",
            ],
            input=text.encode("utf-8", "surrogateescape"),
            capture_output=True,
            check=False,
            env=dict(
                os.environ,
                GIT_PAGER="cat",
                PAGER="cat",
                DELTA_PAGER="cat",
                LESS="-R",
            ),
        )
        if result.returncode == 0:
            return decode(result.stdout)
    return colorize_patch(text)


def preview(manifest_path: str, index: str, mode: str) -> None:
    manifest = json.loads(Path(manifest_path).read_text())
    entry = manifest[int(index)]
    repo = Repo()
    comparison = Comparison(**entry["comparison"])
    print(comparison.title, flush=True)
    if entry["kind"] == "commit" or mode == "full":
        if entry["kind"] == "commit":
            print(
                "Suggested because: " + ", ".join(entry["reasons"])
                if entry["reasons"]
                else "No code/tooling signal; still available to inspect."
            )
            for path in entry["evidence"][:8]:
                print("  " + path)
            if len(entry["evidence"]) > 8:
                print(f"  ... {len(entry['evidence']) - 8} more matching files")
        if comparison.commit:
            print(decode(repo.git("show", "-s", "--format=%B", comparison.commit)))
        body = decode(
            repo.diff(
                comparison,
                ["--stat"] if entry["kind"] == "commit" and mode != "full" else [],
                [],
            )
        )
        if entry["kind"] == "commit" and mode != "full":
            # --stat is not a patch; keep it readable without delta reflow.
            print(body, end="")
        else:
            print(format_patch(body), end="")
        return
    change = Change(**entry["change"])
    print(change.display, flush=True)
    if mode in {"before", "after"}:
        data = repo.blob(comparison, change, mode)
        if b"\0" in data:
            print(f"{mode}: binary blob ({len(data)} bytes)")
        else:
            print(f"{mode}: complete source, historical coordinates")
            for n, line in enumerate(decode(data).splitlines(), 1):
                print(f"{n:5} {line}")
    elif mode == "syntax":
        print(format_patch(syntax_patch(repo, comparison, change)), end="")
    elif mode == "history":
        print(
            "File history at selected commit (or current HEAD for working comparisons):"
        )
        print(
            decode(
                repo.git(
                    "log",
                    "-15",
                    "--format=%h %s",
                    comparison.commit or "HEAD",
                    "--",
                    *repo.specs([change.old, change.new]),
                )
            )
        )
    else:
        patch = repo.patch(comparison, change, entry["flags"])
        if entry["kind"] == "hunk":
            header, hunks = split_hunks(patch)
            patch = header + hunks[entry["hunk"]].text
        print(format_patch(patch), end="")


def commit_footer(repo: Repo, comparison: Comparison) -> str | None:
    """Sticky commit-message body for the file/hunk list footer."""
    if comparison.commit:
        body = decode(repo.git("show", "-s", "--format=%B", comparison.commit))
    else:
        body = comparison.title
    body = body.strip("\n")
    return body or None


def choose(
    repo: Repo,
    directory: Path,
    entries: list[dict],
    labels: list[str],
    title: str,
    cursor: int = 0,
    initial_view: str = "native",
    footer: str | None = None,
) -> tuple[str, int] | None:
    if not entries:
        return None
    with tempfile.NamedTemporaryFile(
        mode="w", dir=directory, suffix=".json", delete=False
    ) as handle:
        json.dump(entries, handle)
        manifest = Path(handle.name)
    preview_cmd = (
        shlex.join([sys.executable, "-B", str(Path(__file__).resolve()), str(manifest)])
        + " {1} "
    )
    args = [
        "fzf",
        "--no-multi",
        "--exact",
        "--delimiter=\t",
        "--with-nth=2..",
        "--layout=reverse",
        "--prompt",
        title + "> ",
        "--preview-window=right,55%,wrap",
        "--preview",
        preview_cmd + initial_view,
        "--header",
        "Type: substring filter (hash, title, path; 'word = fuzzy) | Enter: select/drill down | Esc: back\nCtrl-S/N: syntax/native | Ctrl-B/O: before/after\nCtrl-A: full change | Ctrl-L: history | Ctrl-T: toggle preview width | Ctrl-E: current editor (file list)",
        "--expect=enter,ctrl-e",
        "--bind",
        f"start:pos({cursor + 1})",
        "--bind",
        "ctrl-t:toggle-preview",
    ]
    if footer:
        args += ["--footer-border=line", "--footer", footer]
    for key, mode in (
        ("ctrl-s", "syntax"),
        ("ctrl-n", "native"),
        ("ctrl-b", "before"),
        ("ctrl-o", "after"),
        ("ctrl-a", "full"),
        ("ctrl-l", "history"),
    ):
        args += ["--bind", f"{key}:change-preview({preview_cmd}{mode})"]
    env = dict(
        os.environ,
        FZF_DEFAULT_OPTS="",
        FZF_DEFAULT_OPTS_FILE="",
        GIT_PAGER="cat",
        PAGER="cat",
    )
    result = subprocess.run(
        args,
        input="".join(
            f"{i}\t{label(text)}\n" for i, text in enumerate(labels)
        ).encode(),
        capture_output=True,
        cwd=repo.cwd,
        env=env,
        check=False,
    )
    if result.returncode in (1, 130):
        return None
    if result.returncode:
        raise NavError("fzf failed: " + decode(result.stderr))
    lines = decode(result.stdout).splitlines()
    if len(lines) < 2:
        return None
    index = int(lines[1].split("\t", 1)[0])
    if not 0 <= index < len(entries):
        raise NavError("Invalid picker selection")
    return lines[0], index


def directories(
    repo: Repo,
    comparison: Comparison,
    paths: list[str],
    output: str | None,
    interactive: bool,
) -> None:
    choices = {}
    for change in repo.changes(comparison, paths):
        original = repo.root / Path(change.path).parent
        existing = original
        while not existing.is_dir():
            existing = existing.parent
        text = label(str(original.relative_to(repo.root)))
        if existing != original:
            text += (
                " [deleted; existing ancestor: "
                + label(str(existing.relative_to(repo.root)))
                + "]"
            )
        choices[text] = existing
    if not interactive:
        print(comparison.title)
        print("Changed directories (non-interactive; shell location unchanged):")
        for text in choices:
            print("  " + text)
        return
    labels = sorted(choices)
    if not labels:
        print("No changed directories")
        return
    result = subprocess.run(
        ["fzf", "--delimiter=\t", "--with-nth=2..", "--prompt=changed directory> "],
        input="".join(f"{i}\t{text}\n" for i, text in enumerate(labels)).encode(),
        capture_output=True,
        env=dict(os.environ, FZF_DEFAULT_OPTS="", FZF_DEFAULT_OPTS_FILE=""),
        check=False,
    )
    if result.returncode in (1, 130):
        return
    if result.returncode:
        raise NavError("fzf directory selection failed: " + decode(result.stderr))
    index = int(decode(result.stdout).split("\t", 1)[0])
    if not output:
        raise NavError("Directory navigation must be invoked through gpeek or g peek")
    Path(output).write_bytes(os.fsencode(choices[labels[index]]) + b"\0")


def browse(repo: Repo, opts: argparse.Namespace, paths: list[str]) -> None:
    from navigation import card, history, selected

    interactive = (
        not opts.list
        and sys.stdin.isatty()
        and sys.stdout.isatty()
        and bool(shutil.which("fzf"))
    )
    if opts.grep is not None and not opts.grep:
        raise NavError("--grep needs non-empty text")
    if opts.grep and (opts.dirs or (selected(opts) and not opts.history)):
        raise NavError(
            "--grep filters sampled history; drop --dirs and single-comparison selectors such as --commit"
        )
    if opts.dirs:
        if opts.history:
            raise NavError("--dirs requires one comparison, not --history")
        directories(
            repo, repo.comparison(opts), paths, opts.directory_output, interactive
        )
        return
    commits = (
        history(repo, opts.history, opts.count, paths, opts.grep)
        if opts.history or not selected(opts)
        else []
    )
    choices = suggest_commits(repo, commits, paths, opts.chronological)
    if commits:
        print(
            "* Suggested from code/tests/agent guidance/build files; not a correctness or risk judgment."
        )
        print(
            "All sampled commits remain available. --chronological restores newest-first order."
        )
    if not interactive:
        print("Non-interactive browser; no picker, editor, or directory change.")
        if commits:
            for choice in choices:
                print(choice.display)
                for path in choice.evidence[:3]:
                    print("    " + path)
            print(
                "Next: g peek, then Enter on a suggested commit; no SHA needs typing."
            )
        elif not opts.history and selected(opts):
            card(repo, repo.comparison(opts), paths, opts)
        return
    comparisons = (
        [choice.comparison for choice in choices]
        if commits
        else [repo.comparison(opts)]
        if not opts.history
        else []
    )
    if not comparisons:
        print("No comparisons in this history")
        return
    with tempfile.TemporaryDirectory(prefix="git-nav-picker-") as temp:
        directory = Path(temp)
        ci = 0
        cursors = {}
        while True:
            if commits:
                entries = [
                    {
                        "kind": "commit",
                        "comparison": asdict(c.comparison),
                        "reasons": c.reasons,
                        "evidence": c.evidence,
                    }
                    for c in choices
                ]
                labels = [choice.display for choice in choices]
                picked = choose(
                    repo, directory, entries, labels, "commit (* suggested)", ci
                )
                if picked is None:
                    return
                _, ci = picked
            comparison = comparisons[ci]
            changes = repo.changes(comparison, paths)
            changes.sort(key=lambda c: c.path)
            if opts.order == "churn":
                changes.sort(
                    key=lambda c: (
                        -(int(c.added) + int(c.deleted)) if c.added.isdigit() else 0
                    )
                )
            if opts.first:
                first = repo.path(opts.first)
                changes.sort(key=lambda c: first not in {c.old, c.new})
            while True:
                flags = (["-W"] if opts.function_context else []) + (
                    ["--word-diff=plain"] if opts.word else []
                )
                footer = commit_footer(repo, comparison)
                entries = [
                    {
                        "kind": "file",
                        "comparison": asdict(comparison),
                        "change": asdict(c),
                        "flags": flags,
                    }
                    for c in changes
                ]
                picked = choose(
                    repo,
                    directory,
                    entries,
                    [
                        f"{c.status} {c.category} +{c.added}/-{c.deleted} {c.display}"
                        for c in changes
                    ],
                    "file",
                    cursors.get((ci,), 0),
                    "syntax" if opts.syntax else "native",
                    footer=footer,
                )
                if picked is None:
                    break
                key, fi = picked
                cursors[(ci,)] = fi
                change = changes[fi]
                if key == "ctrl-e":
                    editor = os.environ.get("G_HELPERS_EDITOR")
                    if not editor or not shutil.which(editor):
                        print(
                            "Set G_HELPERS_EDITOR to one editor executable (not a command string)."
                        )
                    elif not (repo.root / change.new).is_file():
                        print(
                            "Current file is unavailable; use before/after historical previews."
                        )
                    else:
                        subprocess.run(
                            [editor, str(repo.root / change.new)], check=True
                        )
                    continue
                _, hunks = split_hunks(repo.patch(comparison, change, flags))
                pattern = (
                    re.compile(opts.hunk)
                    if opts.hunk and not (opts.all or opts.whole_change)
                    else None
                )
                indices = [
                    i for i, h in enumerate(hunks) if not pattern or h.matches(pattern)
                ]
                hentries = [dict(entries[fi], kind="hunk", hunk=i) for i in indices]
                while hentries:
                    picked = choose(
                        repo,
                        directory,
                        hentries,
                        [hunks[i].text.splitlines()[0] for i in indices],
                        f"hunk ({len(indices)}/{len(hunks)})",
                        cursors.get((ci, fi), 0),
                        footer=footer,
                    )
                    if picked is None:
                        break
                    _, hi = picked
                    cursors[(ci, fi)] = hi
                    # The selected hunk stays in the preview; Esc returns to the file list.
            if not commits:
                return


if __name__ == "__main__":
    try:
        preview(*sys.argv[1:])
    except (NavError, OSError, ValueError, IndexError) as exc:
        print(f"Preview unavailable: {exc}", file=sys.stderr)
        sys.exit(2)
