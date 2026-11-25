"""Bounded symbol, line-history, structural-pattern, and reference investigations."""

import argparse
import base64
import json
import re
import shlex
import shutil
from pathlib import Path

from nav_core import (
    LANGUAGES,
    NavError,
    Repo,
    decode,
    intersects,
    label,
    paths_for,
    run,
    selected,
    split_hunks,
    symbols,
)


def outline(repo: Repo, opts: argparse.Namespace) -> None:
    paths = paths_for(repo, opts)
    if opts.at and (opts.changed or selected(opts)):
        raise NavError("--at is for inventory; use comparison selectors with --changed")
    if selected(opts) and not opts.changed:
        raise NavError("Comparison selectors require --changed")
    if not paths:
        raise NavError("Choose explicit files or directories after --")
    if not opts.changed:
        at = repo.rev(opts.at) if opts.at else None
        print(f"Outline: {at or 'current working source'}")
        for path in repo.tracked(paths, at):
            try:
                for symbol in symbols(repo.source(path, at), path):
                    print(
                        f"{label(path)}:{symbol.start}-{symbol.end} {symbol.name} | {symbol.signature}"
                    )
            except NavError as exc:
                print(f"[unclassified] {exc}")
        return
    comparison = repo.comparison(opts)
    print(comparison.title)
    for change in repo.changes(comparison, paths):
        header, hunks = split_hunks(repo.patch(comparison, change, ["-U0"]))
        print(f"{change.status} {change.display}")
        if not hunks:
            print("[metadata/binary/unresolved] " + header.strip())
        sides = {}
        for side in ("before", "after"):
            path = change.old if side == "before" else change.new
            try:
                entries = symbols(repo.blob(comparison, change, side), path)
                sides[side] = entries
            except NavError as exc:
                print(f"[{side} unclassified] {exc}")
                for hunk in hunks:
                    print("context hint: " + hunk.text.splitlines()[0])
                continue
            emitted = set()
            for hunk in hunks:
                line, count = (
                    (hunk.old_start, hunk.old_count)
                    if side == "before"
                    else (hunk.new_start, hunk.new_count)
                )
                touched = [
                    s for s in entries if intersects(s.start, s.end, line, count)
                ]
                for symbol in touched:
                    if (symbol.name, symbol.start) not in emitted:
                        print(
                            f"{side} {label(path)}:{symbol.start}-{symbol.end} {symbol.name} | {symbol.signature}"
                        )
                        emitted.add((symbol.name, symbol.start))
                covered = {
                    n
                    for s in touched
                    for n in range(max(line, s.start), min(line + count - 1, s.end) + 1)
                }
                if len(covered) < count:
                    print(
                        f"{side} {label(path)}:{line} [module-level/unclassified changed lines]"
                    )
        if len(sides) == 2:
            old, new = sides["before"], sides["after"]
            names = sorted({s.name for s in old + new})
            for name in names:
                a, b = (
                    [s for s in old if s.name == name],
                    [s for s in new if s.name == name],
                )
                if len(a) > 1 or len(b) > 1:
                    print(f"? {name}: ambiguous identity; inspect before/after ranges")
                elif not a:
                    print(f"+ {name}: {b[0].signature}")
                elif not b:
                    print(f"- {name}: {a[0].signature}")
                elif a[0].signature != b[0].signature:
                    print(f"~ {name}: {a[0].signature} -> {b[0].signature}")
    print(
        "Unchanged declarations do not establish unchanged behavior; name pairing is a candidate identity."
    )


def line_history(repo: Repo, opts: argparse.Namespace) -> None:
    at, path = repo.rev(opts.at), repo.path(opts.path)
    data = repo.source(path, at)
    if opts.symbol:
        matches = [
            s
            for s in symbols(data, path)
            if s.name == opts.symbol or s.name.endswith("." + opts.symbol)
        ]
        if len(matches) != 1:
            raise NavError(
                f"Expected one symbol; found {len(matches)}. Use a qualified name or --lines."
            )
        start, end = matches[0].start, matches[0].end
    else:
        if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", opts.lines):
            raise NavError("--lines requires START:END")
        start, end = map(int, opts.lines.split(":"))
    if not 1 <= start <= end <= len(data.splitlines()):
        raise NavError("Line range does not exist at the selected revision")
    print(f"Range at {at}: {label(path)}:{start}-{end}", flush=True)
    if opts.blame:
        flags = (["-w"] if opts.ignore_space else []) + (
            ["-M", "-C"] if opts.moves else []
        )
        ignore = repo.root / ".git-blame-ignore-revs"
        if ignore.is_file():
            print("Using existing " + str(ignore))
            flags += ["--ignore-revs-file", str(ignore)]
        output = repo.git("blame", *flags, "-L", f"{start},{end}", at, "--", path)
    else:
        if opts.ignore_space or opts.moves:
            raise NavError("--ignore-space and --moves require --blame")
        output = repo.git(
            "log",
            "--no-ext-diff",
            "--no-textconv",
            f"-{opts.count}",
            "--format=medium",
            "-L",
            f"{start},{end}:{path}",
            at,
        )
    print(decode(output), end="")


def rg_text(field: dict[str, str]) -> str:
    return (
        field["text"] if "text" in field else decode(base64.b64decode(field["bytes"]))
    )


def impact(repo: Repo, opts: argparse.Namespace) -> None:
    paths = paths_for(repo, opts)
    print(
        "Current working source; static leads, not resolved callers, dataflow, or established test coverage."
    )
    if opts.file:
        path = repo.path(opts.file)
        print("Boundary shortlist:")
        try:
            for symbol in symbols(repo.source(path), path):
                print(
                    f"{label(path)}:{symbol.start} {symbol.name} | {symbol.signature}"
                )
        except NavError as exc:
            print(str(exc))
        needle = Path(path).stem
        print(
            f"File-mode import/name leads for {needle!r}; select a symbol for a focused follow-up."
        )
    else:
        needle = opts.symbol.split(".")[-1] if opts.symbol else opts.key
    if not shutil.which("rg"):
        raise NavError("gimpact requires ripgrep (rg)")
    rows = []
    output = run(
        [
            "rg",
            "--json",
            "--hidden",
            "-g",
            "!.git",
            "-F",
            "-e",
            needle,
            "--",
            *(paths or ["."]),
        ],
        cwd=repo.root,
        ok=(0, 1),
    )
    for raw in output.splitlines():
        row = json.loads(raw)
        if row["type"] == "match":
            rows.append(row["data"])
    source_files = {}
    if opts.symbol:
        print("Definition/declaration candidates (bounded to matching source files):")
        candidates = list(
            dict.fromkeys(rg_text(row["path"]).removeprefix("./") for row in rows)
        )[: opts.count]
        for path in candidates:
            if Path(path).suffix not in LANGUAGES:
                continue
            source_files[path] = repo.source(path)
            try:
                definitions = symbols(source_files[path], path)
            except NavError as exc:
                print(f"[text-only] {exc}")
                continue
            for definition in definitions:
                if definition.name == opts.symbol or definition.name.endswith(
                    "." + opts.symbol
                ):
                    print(
                        f"{label(path)}:{definition.start}-{definition.end} {definition.name} | {definition.signature}"
                    )
    print(f"Literal references: showing {min(opts.count, len(rows))}/{len(rows)}")
    touched = set()
    for row in sorted(rows, key=lambda r: repo.classify(rg_text(r["path"])) == "test")[
        : opts.count
    ]:
        path = rg_text(row["path"]).removeprefix("./")
        touched.add(path)
        reason = (
            "test candidate: direct text hit"
            if repo.classify(path) == "test"
            else "production/docs/config reference (text hit)"
        )
        print(
            f"[{reason}] {label(path)}:{row['line_number']}: {label(rg_text(row['lines']).rstrip())}"
        )
        if path not in source_files:
            source_files[path] = repo.source(path)
        source = decode(source_files[path]).splitlines()
        number = row["line_number"]
        for n in range(max(1, number - 1), min(len(source), number + 2) + 1):
            if n != number:
                print(f"  {n}: {label(source[n - 1])}")
    for path in repo.tracked(paths):
        if (
            path not in touched
            and repo.classify(path) == "test"
            and needle in Path(path).stem
        ):
            print(f"[test candidate: filename convention] {label(path)}")
    print(
        "Next: inspect definitions, callback/string wiring, returned values and effects at the hits above."
    )
    print(
        "Use the repository's documented test/debug entry point; no test runner was inferred or executed."
    )
    print(
        "History: " + shlex.join(["g", "why", "--literal", needle, "--", *opts.paths])
    )
    print(
        "No references does not mean unused; dynamic dispatch may require another key/scope."
    )


def shape(repo: Repo, opts: argparse.Namespace) -> None:
    if not shutil.which("ast-grep"):
        raise NavError(
            "gshape requires ast-grep; no textual fallback is presented as structural"
        )
    paths = paths_for(repo, opts)
    if selected(opts) and not opts.changed:
        raise NavError("Comparison selectors require --changed")
    command = [
        "ast-grep",
        "run",
        "--lang",
        opts.lang,
        "--pattern",
        opts.pattern,
        "--json=compact",
    ]
    if not opts.changed:
        print(
            "Structural matches in current working source (ast-grep ignore rules apply):"
        )
        matches = json.loads(run([*command, "--", *paths], cwd=repo.root, ok=(0, 1)))
        for match in matches:
            print(
                f"{label(match['file'])}:{match['range']['start']['line'] + 1}: {match['text']}"
            )
        print(f"Structural occurrences: {len(matches)}")
        return
    comparison = repo.comparison(opts)
    print(comparison.title)
    count = 0
    for change in repo.changes(comparison, paths):
        if LANGUAGES.get(Path(change.path).suffix) != opts.lang:
            print(f"[not parsed as {opts.lang}] {change.display}")
            continue
        _, hunks = split_hunks(repo.patch(comparison, change, ["-U0"]))
        for side in ("before", "after"):
            matches = json.loads(
                run(
                    [*command, "--stdin"],
                    data=repo.blob(comparison, change, side),
                    ok=(0, 1),
                )
            )
            for match in matches:
                start, end = (
                    match["range"]["start"]["line"] + 1,
                    match["range"]["end"]["line"] + 1,
                )
                if any(
                    intersects(start, end, h.old_start, h.old_count)
                    if side == "before"
                    else intersects(start, end, h.new_start, h.new_count)
                    for h in hunks
                ):
                    path = change.old if side == "before" else change.new
                    print(f"{side} {label(path)}:{start}-{end}: {match['text']}")
                    count += 1
    print(
        f"Changed structural occurrences: {count}; before/after matches are separate evidence, not identity pairs."
    )
