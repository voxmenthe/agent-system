#!/usr/bin/env python3
"""Check mechanical output constraints for show-me-clearly artifacts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote


DATED_NAME = re.compile(r".+-\d{8}\.md$")
FENCE = re.compile(r"^```\s*([A-Za-z0-9_-]*)\s*$")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
HTML_TAG = re.compile(r"<[^>]+>")
LINK = re.compile(r"\[[^]]*\]\(([^)]+)\)")
LINE_FRAGMENT = re.compile(r"^(.*)#L([1-9][0-9]*)$")


@dataclass(frozen=True)
class Visual:
    kind: str
    heading: str
    start_line: int
    lines: tuple[str, ...]


def visible_width(value: str) -> int:
    """Return a dependency-free approximation of terminal display width."""
    width = 0
    for character in value:
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"F", "W"} else 1
    return width


def visible_html(value: str) -> str:
    return unescape(HTML_TAG.sub("", value))


def extract_visuals(text: str) -> list[Visual]:
    visuals: list[Visual] = []
    current_heading = ""
    fence_kind: str | None = None
    fence_start = 0
    fence_lines: list[str] = []
    pre_start: int | None = None
    pre_lines: list[str] = []

    for number, line in enumerate(text.splitlines(), start=1):
        if fence_kind is not None:
            if line == "```":
                if fence_kind in {"text", "diff"}:
                    visuals.append(
                        Visual(
                            kind=fence_kind,
                            heading=current_heading,
                            start_line=fence_start,
                            lines=tuple(fence_lines),
                        )
                    )
                fence_kind = None
                fence_lines = []
            else:
                fence_lines.append(line)
            continue

        if pre_start is not None:
            if line.strip() == "</pre>":
                visuals.append(
                    Visual(
                        kind="html-pre",
                        heading=current_heading,
                        start_line=pre_start,
                        lines=tuple(visible_html(item) for item in pre_lines),
                    )
                )
                pre_start = None
                pre_lines = []
            else:
                pre_lines.append(line)
            continue

        heading = HEADING.match(line)
        if heading:
            current_heading = visible_html(heading.group(1))
            continue

        fence = FENCE.match(line)
        if fence:
            fence_kind = fence.group(1).lower()
            fence_start = number
            fence_lines = []
            continue

        if line.strip() == "<pre>":
            pre_start = number
            pre_lines = []

    return visuals


def check_visuals(visuals: list[Visual]) -> list[str]:
    errors: list[str] = []
    if not visuals:
        return ["no renderer-independent text, diff, or <pre> visual found"]

    for visual in visuals:
        nonblank = [line for line in visual.lines if line.strip()]
        is_zoom = "zoom" in visual.heading.casefold()
        line_limit = 12 if is_zoom else 16
        if len(nonblank) > line_limit:
            errors.append(
                f"line {visual.start_line}: {visual.kind} visual under "
                f"{visual.heading!r} has {len(nonblank)} nonblank lines; "
                f"limit is {line_limit}"
            )
        for offset, line in enumerate(visual.lines, start=1):
            width = visible_width(line)
            if width > 88:
                errors.append(
                    f"line {visual.start_line + offset}: visual is {width} "
                    "columns wide; limit is 88"
                )
    return errors


def normalized_link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return unquote(target)


def check_links(artifact: Path, text: str) -> tuple[list[str], int]:
    errors: list[str] = []
    source_links = 0
    for match in LINK.finditer(text):
        target = normalized_link_target(match.group(1))
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        fragment = LINE_FRAGMENT.match(target)
        path_text = fragment.group(1) if fragment else target.split("#", 1)[0]
        target_path = (artifact.parent / path_text).resolve()
        if not target_path.is_file():
            errors.append(f"broken local link: {target}")
            continue
        if fragment:
            source_links += 1
            start_line = int(fragment.group(2))
            with target_path.open("r", encoding="utf-8", errors="replace") as handle:
                line_count = sum(1 for _ in handle)
            if start_line > line_count:
                errors.append(
                    f"source link starts at line {start_line}, but "
                    f"{target_path} has {line_count} lines"
                )
    if source_links == 0:
        errors.append("no repository-relative source link with a #L line anchor found")
    return errors, source_links


def check_artifact(artifact: Path) -> tuple[list[str], int, int]:
    errors: list[str] = []
    if not artifact.is_file():
        return [f"artifact does not exist: {artifact}"], 0, 0
    if not DATED_NAME.fullmatch(artifact.name):
        errors.append("artifact name must end with -YYYYMMDD.md")

    text = artifact.read_text(encoding="utf-8")
    visuals = extract_visuals(text)
    errors.extend(check_visuals(visuals))
    link_errors, source_links = check_links(artifact, text)
    errors.extend(link_errors)
    return errors, len(visuals), source_links


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check mechanical show-me-clearly output constraints."
    )
    parser.add_argument("artifact", type=Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(arguments)
    artifact = options.artifact.resolve()
    errors, visual_count, source_link_count = check_artifact(artifact)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"OK: {artifact} ({visual_count} visual(s), "
        f"{source_link_count} source link(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
