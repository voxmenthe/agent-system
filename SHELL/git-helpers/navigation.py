"""Human-facing navigation commands; project access is read-only."""

import argparse
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from nav_analysis import impact, line_history, outline, shape
from nav_core import (
    COLLAPSED,
    Change,
    Comparison,
    NavError,
    Repo,
    commit_comparison,
    decode,
    label,
    paths_for,
    range_spec,
    run,
    selected,
    split_hunks,
    syntax_patch,
)


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def selectors(parser: argparse.ArgumentParser, history: bool = False) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--commit", metavar="C")
    group.add_argument("--staged", action="store_true")
    group.add_argument("--unstaged", action="store_true")
    group.add_argument("--worktree", "--wt", action="store_true")
    group.add_argument("--branch", metavar="BASE")
    group.add_argument("--between", nargs=2, metavar=("A", "B"))
    if history:
        group.add_argument("--history", metavar="A..B")
    parser.add_argument("--parent", type=positive, default=1)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("map", "focus", "peek"):
        p = commands.add_parser(name)
        selectors(p, history=True)
        p.add_argument("--count", "-n", type=positive, default=30)
        p.add_argument(
            "--all",
            action="store_true",
            help="expand all bodies/hunks within selected paths",
        )
        p.add_argument(
            "--whole-change", action="store_true", help="also remove path restrictions"
        )
        p.add_argument("--first", metavar="PATH")
        p.add_argument("--order", choices=("path", "churn"), default="path")
        if name in {"focus", "peek"}:
            p.add_argument("--syntax", action="store_true")
            p.add_argument("-W", "--function-context", action="store_true")
            p.add_argument("--word", action="store_true")
            p.add_argument("--hunk", metavar="PYTHON_REGEX")
        if name == "peek":
            p.add_argument(
                "--list",
                action="store_true",
                help="print suggested commits without opening a picker",
            )
            p.add_argument(
                "--chronological",
                action="store_true",
                help="keep newest-first order instead of suggestions first",
            )
            p.add_argument(
                "--grep",
                metavar="TEXT",
                help="only sample commits whose message contains TEXT (fixed string, case-insensitive)",
            )
            p.add_argument("--dirs", action="store_true")
            p.add_argument("--directory-output", help=argparse.SUPPRESS)
        p.add_argument("paths", nargs="*")
    p = commands.add_parser("why")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--literal")
    group.add_argument("--regex", "-G")
    group.add_argument("--commit")
    p.add_argument("--all-refs", action="store_true")
    p.add_argument("--count", "-n", type=positive, default=20)
    p.add_argument("paths", nargs="*")
    p = commands.add_parser("outline")
    selectors(p)
    p.add_argument("--changed", action="store_true")
    p.add_argument("--at")
    p.add_argument("paths", nargs="*")
    p = commands.add_parser("line")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol")
    group.add_argument("--lines", help="START:END (inclusive)")
    p.add_argument("--at", default="HEAD")
    p.add_argument("--blame", action="store_true")
    p.add_argument("--ignore-space", action="store_true")
    p.add_argument("--moves", action="store_true", help="copy/move-aware blame (-M -C)")
    p.add_argument("--count", "-n", type=positive, default=20)
    p.add_argument("path")
    p = commands.add_parser("impact")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol")
    group.add_argument("--key")
    group.add_argument("--file")
    p.add_argument("--count", type=positive, default=100)
    p.add_argument("paths", nargs="*")
    p = commands.add_parser("shape")
    selectors(p)
    p.add_argument("--changed", action="store_true")
    p.add_argument("--lang", required=True)
    p.add_argument("--pattern", required=True)
    p.add_argument("paths", nargs="+")
    p = commands.add_parser("hot")
    p.add_argument("--since", default="90 days ago")
    p.add_argument("--count", "-n", type=positive, default=300)
    p.add_argument("--top", type=positive, default=20)
    p.add_argument("--with", dest="anchor")
    p.add_argument("--by", choices=("commits", "churn", "recent"), default="commits")
    p.add_argument("--exclude-bulk", type=positive, metavar="FILES")
    p.add_argument("--commit", help="mark companions absent from this comparison")
    p.add_argument("paths", nargs="*")
    p = commands.add_parser("range")
    p.add_argument("old")
    p.add_argument("new")
    commands.add_parser("doctor")
    return root


def history(
    repo: Repo, value: str | None, count: int, paths: list[str], grep: str | None = None
) -> list[str]:
    spec = range_spec(repo, value) if value else repo.rev("HEAD")
    filters = (
        ["--grep=" + grep, "--fixed-strings", "--regexp-ignore-case"] if grep else []
    )
    commits = decode(
        repo.git(
            "log",
            f"-{count + 1}",
            "--format=%H",
            *filters,
            spec,
            "--",
            *repo.specs(paths),
        )
    ).splitlines()
    print(
        f"History: {spec}; limit {count}"
        + (f"; grep {grep!r}" if grep else "")
        + ("; truncated" if len(commits) > count else "")
    )
    return commits[:count]


def card(
    repo: Repo, comparison: Comparison, paths: list[str], opts: argparse.Namespace
) -> list[Change]:
    changes = repo.changes(comparison, paths)
    if opts.order == "churn":
        changes.sort(
            key=lambda c: -(int(c.added) + int(c.deleted)) if c.added.isdigit() else 0
        )
    else:
        changes.sort(key=lambda c: c.path)
    if opts.first:
        first = repo.path(opts.first)
        changes.sort(key=lambda c: c.path != first and c.old != first)
    print(comparison.title)
    if comparison.commit:
        print(
            decode(repo.git("show", "-s", "--format=%h %s", comparison.commit)).strip()
        )
    for change in changes:
        mode = (
            f" mode {change.old_mode}->{change.new_mode}"
            if change.old_mode != change.new_mode
            else ""
        )
        print(
            f"{change.status:4} {change.category:10} +{change.added}/-{change.deleted} {change.display}{mode}"
        )
    print(
        f"{len(changes)} changed records; classes: {dict(Counter(c.category for c in changes))}"
    )
    print(
        "Directories: "
        + str(dict(Counter(label(str(Path(c.path).parent)) for c in changes)))
    )
    if comparison.worktree:
        untracked = [
            decode(p)
            for p in repo.git(
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                *repo.specs(paths),
            ).split(b"\0")
            if p
        ]
        print(f"Untracked (not in patch): {len(untracked)}")
        for path in untracked:
            print("  ? " + label(path))
    return changes


def state(repo: Repo) -> None:
    print(f"Worktree: {label(str(repo.root))}")
    head = repo.head()
    branch = decode(
        run(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            cwd=repo.root,
            ok=(0, 1),
        )
    ).strip()
    print(f"Branch: {branch or 'detached HEAD'}; HEAD: {head or 'unborn'}")
    upstream = (
        decode(
            repo.git("for-each-ref", "--format=%(upstream)", "refs/heads/" + branch)
        ).strip()
        if head and branch
        else ""
    )
    if upstream:
        print(
            f"Upstream (local, not fetched): {upstream}; ahead/behind: "
            + decode(
                repo.git("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
            ).strip()
        )
    else:
        print("Upstream: none")
    for name in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-merge",
        "rebase-apply",
    ):
        path = Path(decode(repo.git("rev-parse", "--git-path", name)).strip())
        if (repo.root / path).exists():
            print("In progress: " + name)
    buckets = defaultdict(list)
    rows = iter(
        repo.git("status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    )
    for row in rows:
        if not row:
            continue
        xy, path = decode(row[:2]), decode(row[3:])
        if "R" in xy or "C" in xy:
            path = decode(next(rows)) + " -> " + path
        if xy in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}:
            buckets["conflicted"].append(path)
        elif xy == "??":
            buckets["untracked"].append(path)
        else:
            if xy[0] != " ":
                buckets["staged"].append(path)
            if xy[1] != " ":
                buckets["unstaged"].append(path)
    for key, action in (
        ("staged", "g focus --staged"),
        ("unstaged", "g focus --unstaged"),
        ("untracked", "git ls-files --others --exclude-standard"),
        ("conflicted", "git diff --cc"),
    ):
        print(f"{key}: {len(buckets[key])}  [{action}]")
        for path in buckets[key]:
            print("  " + label(path))
    print("Buckets may overlap; untracked content is not included in Git diffs.")
    print("Stashes: " + str(len(repo.git("stash", "list", "--format=%H").splitlines())))
    if head:
        print(decode(repo.git("show", "-s", "--format=Last: %h %s", head)).strip())


def render_focus(
    repo: Repo, comparison: Comparison, paths: list[str], opts: argparse.Namespace
) -> None:
    changes = card(repo, comparison, paths, opts)
    pattern = (
        re.compile(opts.hunk)
        if opts.hunk and not opts.all and not opts.whole_change
        else None
    )
    collapsed = shown = total = 0
    for change in changes:
        explicitly_selected = any(path in {change.old, change.new} for path in paths)
        if change.category in COLLAPSED and not (
            opts.all or opts.whole_change or explicitly_selected
        ):
            print(f"[collapsed body] {change.display}; select this file or use --all")
            collapsed += 1
            continue
        flags = ["-W"] if opts.function_context else []
        if opts.word:
            flags += ["--word-diff=plain"]
        patch = repo.patch(comparison, change, flags)
        header, hunks = split_hunks(patch)
        total += len(hunks)
        kept = [h for h in hunks if not pattern or h.matches(pattern)]
        shown += len(kept)
        if opts.syntax:
            print(syntax_patch(repo, comparison, change), end="")
        else:
            print(header + "".join(h.text for h in kept), end="")
    print(
        f"\nBodies collapsed: {collapsed}/{len(changes)}; hunks shown: {shown}/{total} in expanded bodies"
    )
    if pattern and not shown:
        print("No hunks matched this view; this does not mean nothing changed.")


def context(repo: Repo, commit: str) -> None:
    commit = repo.rev(commit)
    print(
        decode(
            repo.git(
                "show",
                "-s",
                "--format=Commit: %H%nParents: %P%nAuthor: %an%nDate: %aI%n%n%B",
                commit,
            )
        )
    )
    print("Local containing refs (not fetched):")
    print(
        decode(
            repo.git("for-each-ref", "--contains", commit, "--format=%(refname:short)")
        )
    )
    card(
        repo,
        commit_comparison(repo, commit),
        [],
        argparse.Namespace(order="path", first=None),
    )
    print(f"Whole patch: g focus --commit {commit} --whole-change")


def why(repo: Repo, opts: argparse.Namespace) -> None:
    if opts.commit:
        context(repo, opts.commit)
        return
    paths = paths_for(repo, opts)
    pattern = opts.literal if opts.literal is not None else opts.regex
    flag = "-S" if opts.literal is not None else "-G"
    scope = ["--all"] if opts.all_refs else [repo.rev("HEAD")]
    commits = decode(
        repo.git(
            "log",
            "--no-ext-diff",
            "--no-textconv",
            "--full-history",
            "--diff-merges=first-parent",
            "--no-patch",
            "--format=%H",
            f"-{opts.count + 1}",
            flag,
            pattern,
            *scope,
            "--",
            *repo.specs(paths),
        )
    ).splitlines()
    print(
        f"{'Literal occurrence-count (-S)' if flag == '-S' else 'Changed-line POSIX regex (-G)'} history; newest first; limit {opts.count}; "
        f"{'truncated' if len(commits) > opts.count else 'not truncated'}"
    )
    for commit in commits[: opts.count]:
        comparison = commit_comparison(repo, commit)
        print(comparison.title)
        print(decode(repo.git("show", "-s", "--format=%h %s", commit)).strip())
        for change in repo.changes(comparison, paths):
            header, hunks = split_hunks(repo.patch(comparison, change))
            kept = []
            for hunk in hunks:
                changed = "\n".join(
                    line[1:]
                    for line in hunk.text.splitlines()[1:]
                    if line.startswith(("+", "-"))
                )
                # Use the same POSIX regex dialect as Git -G, not Python/PCRE.
                match = (
                    pattern in changed
                    if flag == "-S"
                    else bool(
                        run(
                            ["grep", "-E", "-e", pattern],
                            data=changed.encode("utf-8", "surrogateescape"),
                            ok=(0, 1),
                        )
                    )
                )
                if match:
                    kept.append(hunk)
            if kept or not hunks:
                print(header + "".join(h.text for h in kept), end="")
                print(f"Hunks: {len(kept)}/{len(hunks)}")
        print(f"Whole context: g why --commit {commit}")
    print("Current locations (working source, including untracked; bounded display):")
    data = run(
        [
            "git",
            "grep",
            "--untracked",
            "--exclude-standard",
            "-n",
            "-I",
            "-z",
            "-F" if flag == "-S" else "-E",
            "-e",
            pattern,
            "--",
            *repo.specs(paths),
        ],
        cwd=repo.root,
        ok=(0, 1),
    )
    matches = re.findall(rb"([^\0]+)\0([0-9]+)\0([^\n]*)\n", data)
    for path, line, text in matches[:100]:
        print(f"{label(decode(path))}:{decode(line)}: {label(decode(text))}")
    print(
        f"Locations shown: {min(100, len(matches))}/{len(matches)}; no match is not proof of absence at runtime."
    )


def hot(repo: Repo, opts: argparse.Namespace) -> None:
    paths = paths_for(repo, opts)
    head = repo.rev("HEAD")
    commits = decode(
        repo.git(
            "log",
            "--no-merges",
            f"--since={opts.since}",
            f"-{opts.count + 1}",
            "--format=%H",
            head,
        )
    ).splitlines()
    merges = decode(
        repo.git("rev-list", "--count", "--merges", f"--since={opts.since}", head)
    ).strip()
    print(
        f"History: {head}; since {opts.since}; max {opts.count} non-merge commits; "
        f"{'truncated' if len(commits) > opts.count else 'not truncated'}; merges excluded in time window: {merges}"
    )
    anchor = repo.path(opts.anchor) if opts.anchor else None
    rows = defaultdict(
        lambda: {
            "commits": [],
            "added": 0,
            "deleted": 0,
            "recent": "",
            "timestamp": float("-inf"),
            "binary": 0,
        }
    )
    anchor_commits, omitted = set(), 0
    for commit in commits[: opts.count]:
        changes = repo.changes(commit_comparison(repo, commit), [])
        if opts.exclude_bulk and len(changes) > opts.exclude_bulk:
            omitted += 1
            continue
        date = decode(repo.git("show", "-s", "--format=%cI", commit)).strip()
        timestamp = datetime.fromisoformat(date).timestamp()
        if anchor and any(anchor in (c.old, c.new) for c in changes):
            anchor_commits.add(commit)
        for change in changes:
            row = rows[change.path]
            row["commits"].append(commit)
            if timestamp > row["timestamp"]:
                row["recent"], row["timestamp"] = date, timestamp
            if change.added.isdigit():
                row["added"] += int(change.added)
                row["deleted"] += int(change.deleted)
            else:
                row["binary"] += 1
    print(
        f"Bulk commits excluded explicitly: {omitted}; paths tracked by recorded names (no inferred rename lineage)"
    )
    present = (
        {c.path for c in repo.changes(commit_comparison(repo, opts.commit), [])}
        if opts.commit
        else None
    )
    display = []
    for path, row in rows.items():
        if paths and not any(
            path == p or path.startswith(p.rstrip("/") + "/") or p == "." for p in paths
        ):
            continue
        shared = [c for c in row["commits"] if c in anchor_commits]
        if anchor and (path == anchor or not shared):
            continue
        value = (
            len(shared)
            if anchor
            else {
                "commits": len(row["commits"]),
                "churn": row["added"] + row["deleted"],
                "recent": row["timestamp"],
            }[opts.by]
        )
        display.append((value, path, row, shared))
    for _, path, row, shared in sorted(
        display, key=lambda item: (item[0], item[1]), reverse=True
    )[: opts.top]:
        companion = f"shared {len(shared)}/{len(anchor_commits)}; " if anchor else ""
        absent = (
            "; absent from selected commit"
            if present is not None and path not in present
            else ""
        )
        examples = (shared or row["commits"])[:3]
        print(
            f"{label(path)}: {companion}touches {len(row['commits'])}; +{row['added']}/-{row['deleted']}; "
            f"binary touches {row['binary']}; last {row['recent']}; examples {' '.join(examples)}{absent}"
        )
    print(
        f"Rows shown: {min(opts.top, len(display))}/{len(display)}; anchor commits: {len(anchor_commits)}"
        if anchor
        else f"Rows shown: {min(opts.top, len(display))}/{len(display)}"
    )
    print(
        "Historical association is not a dependency or an instruction to edit companions."
    )


def doctor() -> None:
    for tool in ("git", "python3", "rg", "fzf", "difft", "delta", "ast-grep"):
        print(f"{tool}: {shutil.which(tool) or 'unavailable'}")
    print(
        "Required: Git + Python 3.10+. rg is used by impact; fzf/difft/ast-grep are optional views."
    )
    print(
        "Python outlines and symbol history use the standard parser; no global diff driver required."
    )
    print(
        "Git attributes/configuration were not modified. G_HELPERS_ECHO=1 prints executed commands."
    )


def main() -> int:
    opts = parser().parse_args()
    if opts.command == "doctor":
        doctor()
        return 0
    repo = Repo()
    if opts.command in {"map", "focus", "peek"}:
        if opts.command in {"focus", "peek"} and (
            (opts.syntax or opts.word)
            and opts.hunk
            or opts.syntax
            and (opts.word or opts.function_context)
        ):
            raise NavError(
                "Use one of native hunk filtering, word diff, or syntax view"
            )
        paths = [] if opts.whole_change else paths_for(repo, opts)
        if opts.command == "peek":
            from nav_browser import browse

            browse(repo, opts, paths)
        elif opts.command == "map" and not selected(opts) and not opts.history:
            if paths:
                raise NavError("Path-scoped maps need an explicit comparison selector")
            state(repo)
        else:
            comparisons = (
                [
                    commit_comparison(repo, c)
                    for c in history(repo, opts.history, opts.count, paths)
                ]
                if opts.history
                else [repo.comparison(opts)]
            )
            for comparison in comparisons:
                if opts.command == "map":
                    card(repo, comparison, paths, opts)
                else:
                    render_focus(repo, comparison, paths, opts)
    elif opts.command == "range":
        old, new = range_spec(repo, opts.old), range_spec(repo, opts.new)
        print(
            f"Patch series (heuristic matching, not merge-resolution coverage): {old} versus {new}",
            flush=True,
        )
        print(decode(repo.git("range-diff", "--no-color", old, new)), end="")
    else:
        {
            "why": why,
            "outline": outline,
            "line": line_history,
            "impact": impact,
            "shape": shape,
            "hot": hot,
        }[opts.command](repo, opts)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BrokenPipeError, KeyboardInterrupt):
        sys.exit(130)
    except (NavError, OSError, ValueError, re.error, subprocess.SubprocessError) as exc:
        print(f"git-helpers: {exc}", file=sys.stderr)
        sys.exit(2)
