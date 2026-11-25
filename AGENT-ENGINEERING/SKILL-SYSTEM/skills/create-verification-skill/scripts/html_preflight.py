#!/usr/bin/env python3
"""Preflight a generated HTML report or explainer before anyone looks at it.

    python3 html_preflight.py REPORT.html [MORE.html ...]

Reports, per file:

- a document that is not whole: no closing </html>, U+FFFD replacement
  characters (mojibake or a cut multi-byte character), or a container element
  that opens and closes a different number of times;
- SVG content painted past its viewBox, for rect, line, circle, ellipse,
  polygon, polyline and text (text by its anchor point only), under no
  transform or translate() only.

Everything else inside an SVG (path, use, image, other transforms, CSS that
moves or clips an element, nested SVGs) is listed as not checked; it is never
counted as passing. Standard library only; reads files, writes nothing.

Exit status: 0 when no defect was found in what was checked, 1 when a defect
was found, 2 when a file could not be read.

Adapted from diagram-design's scripts/self_check.py (MIT, Cathryn Lavery),
revision d35ae86: its completeness and viewBox checks, without its
diagram-specific accessibility, asset and motion contracts.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

VIEWBOX_TOLERANCE = 2.0
SVG_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
SVG_NUMBER_RE = re.compile(SVG_NUMBER)
SVG_PLAIN_NUMBER_RE = re.compile(rf"^\s*{SVG_NUMBER}\s*$")
TRANSLATE_RE = re.compile(rf"^\s*translate\(\s*({SVG_NUMBER})(?:[\s,]+({SVG_NUMBER}))?\s*\)\s*$")
REPLACEMENT_CHAR = "\ufffd"
# Elements whose end tag HTML requires, so unequal counts are damage. Void and
# optional-end-tag elements (html, head, body, p, li, tr, td, ...) stay out.
PAIRED_CONTAINER_TAGS = (
    "title", "desc", "div", "section", "main", "article", "header", "footer", "nav",
    "aside", "figure", "figcaption", "table", "ul", "ol", "details", "summary", "pre",
    "button", "a", "h1", "h2", "h3", "h4", "h5", "h6", "svg", "g", "defs", "pattern",
    "marker", "style", "script", "span", "text", "tspan",
)
# Definitions: their children are not painted where they are declared.
DEFINITION_TAGS = {"defs", "symbol", "marker", "pattern", "clippath", "mask"}
# Painted, but in a coordinate system or shape this check does not model.
UNMODELED_TAGS = {"svg", "foreignobject", "path", "use", "image"}
UNSTATIC_CSS_PROPERTIES = {
    "transform", "translate", "rotate", "scale", "display", "visibility",
    "x", "y", "cx", "cy", "r", "rx", "ry", "width", "height",
}
UNSTATIC_CSS_PREFIXES = ("animation", "offset", "clip", "mask")
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_KEYFRAMES_RE = re.compile(
    r"@(?:-[a-z]+-)?keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", re.IGNORECASE
)
CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_STRING_RE = re.compile(r"\"[^\"]*\"|'[^']*'")
CSS_PARENS_RE = re.compile(r"\([^()]*\)")
CSS_COMBINATOR_RE = re.compile(r"\s*[>+~]\s*|\s+")
CSS_TAG_RE = re.compile(r"^[a-zA-Z][\w-]*")
CSS_CLASS_RE = re.compile(r"\.([\w-]+)")
CSS_ID_RE = re.compile(r"#([\w-]+)")
CSS_ATTRIBUTE_RE = re.compile(r"\[\s*([\w:-]+)")
GEOMETRY_ATTRS = {
    "rect": ("x", "y", "width", "height"),
    "line": ("x1", "y1", "x2", "y2"),
    "circle": ("cx", "cy", "r"),
    "ellipse": ("cx", "cy", "rx", "ry"),
    "polygon": ("points",),
    "polyline": ("points",),
    "text": ("x", "y"),
}
UNPAINTED, UNCHECKED = "unpainted", "unchecked"
Subject = tuple[str, set[str], set[str], set[str]]


class BalanceParser(HTMLParser):
    """Counts start and end tags as parsed, so attribute values, scripts and styles stay opaque.

    <title> and <textarea> are RCDATA; markup inside them is text, which
    HTMLParser only separates itself from Python 3.13 on.
    """

    RCDATA_ELEMENTS = ("title", "textarea")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.opens: Counter[str] = Counter()
        self.closes: Counter[str] = Counter()
        self.rcdata = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.rcdata:
            return
        self.opens[tag] += 1
        if tag in self.RCDATA_ELEMENTS:
            self.rcdata = tag

    def handle_endtag(self, tag: str) -> None:
        if self.rcdata:
            if tag == self.rcdata:
                self.rcdata = ""
                self.closes[tag] += 1
            return
        self.closes[tag] += 1


def ends_with_html_close(source: str) -> bool:
    """True when the last markup, ignoring trailing comments and whitespace, is </html>."""
    tail = source.rstrip()
    while True:
        start = tail.rfind("<!--")
        if start < 0:
            break
        end = tail.find("-->", start + 4)
        if end < 0 or tail[end + 3 :].strip():
            break
        tail = tail[:start].rstrip()
    return re.search(r"</html\s*>\Z", tail, re.IGNORECASE) is not None


def completeness_defects(source: str) -> list[str]:
    defects = []
    if not ends_with_html_close(source):
        defects.append("document does not end with </html>; the file looks truncated")
    replacements = source.count(REPLACEMENT_CHAR)
    if replacements:
        line = source[: source.index(REPLACEMENT_CHAR)].count("\n") + 1
        defects.append(
            f"{replacements} U+FFFD replacement character(s), first on line {line}: "
            "mojibake or a cut multi-byte character"
        )
    parser = BalanceParser()
    parser.feed(source)
    parser.close()
    if parser.rcdata:
        # Everything after it reads as text, so tag counts would describe the damage, not the cause.
        return defects + [f"<{parser.rcdata}> is never closed; the rest of the document reads as its text"]
    for tag in PAIRED_CONTAINER_TAGS:
        opens, closes = parser.opens[tag], parser.closes[tag]
        if opens != closes:
            defects.append(f"<{tag}> opens {opens} time(s) and closes {closes} time(s)")
    return defects


def declares_unstatic_css(declarations: str) -> bool:
    for declaration in declarations.split(";"):
        name = declaration.split(":", 1)[0].strip().casefold()
        if name in UNSTATIC_CSS_PROPERTIES or name.startswith(UNSTATIC_CSS_PREFIXES):
            return True
    return False


def unstatic_css_subjects(source: str) -> list[Subject]:
    """Tag, classes, IDs and attribute names of stylesheet rules that move, hide or clip.

    Only each selector's last compound is kept and pseudo-classes are dropped,
    so this can match more elements than a browser does. That only moves
    elements to not checked; it never adds a defect.
    """
    styles = re.findall(r"<style\b[^>]*>(.*?)</style\s*>", source, re.IGNORECASE | re.DOTALL)
    sheet = CSS_KEYFRAMES_RE.sub("", CSS_COMMENT_RE.sub("", "\n".join(styles)))
    subjects = []
    for selector, declarations in CSS_RULE_RE.findall(sheet):
        if not declares_unstatic_css(declarations):
            continue
        for alternative in CSS_PARENS_RE.sub("", CSS_STRING_RE.sub("", selector)).split(","):
            parts = [part for part in CSS_COMBINATOR_RE.split(alternative.strip()) if part]
            if not parts:
                continue
            compound = parts[-1].split("::", 1)[0]
            tag = CSS_TAG_RE.match(compound)
            subjects.append((
                tag.group(0).casefold() if tag else "",
                set(CSS_CLASS_RE.findall(compound)),
                set(CSS_ID_RE.findall(compound)),
                {name.casefold() for name in CSS_ATTRIBUTE_RE.findall(compound)},
            ))
    return subjects


def matches_subject(tag: str, attrs: dict[str, str], subject: Subject) -> bool:
    subject_tag, classes, ids, attribute_names = subject
    return (
        subject_tag in {"", "*", tag}
        and classes <= set(attrs.get("class", "").split())
        and ids <= {attrs.get("id", "")}
        and attribute_names <= set(attrs)
    )


def svg_length(attrs: dict[str, str], name: str, default: float | None = None) -> float | None:
    value = attrs.get(name)
    if value is None:
        return default
    return float(value) if SVG_PLAIN_NUMBER_RE.match(value) else None


def painted_points(tag: str, attrs: dict[str, str]) -> list[tuple[float, float]] | None:
    """Extreme points of a supported primitive; None when its geometry is not plain numbers."""
    if tag == "rect":
        x, y = svg_length(attrs, "x", 0.0), svg_length(attrs, "y", 0.0)
        width, height = svg_length(attrs, "width"), svg_length(attrs, "height")
        if x is None or y is None or width is None or height is None:
            return None
        return [(x, y), (x + width, y + height)] if width > 0 and height > 0 else []
    if tag == "line":
        ends = [
            (svg_length(attrs, "x1", 0.0), svg_length(attrs, "y1", 0.0)),
            (svg_length(attrs, "x2", 0.0), svg_length(attrs, "y2", 0.0)),
        ]
        if any(x is None or y is None for x, y in ends):
            return None
        return ends  # type: ignore[return-value]
    if tag in {"circle", "ellipse"}:
        cx, cy = svg_length(attrs, "cx", 0.0), svg_length(attrs, "cy", 0.0)
        rx = svg_length(attrs, "r" if tag == "circle" else "rx")
        ry = svg_length(attrs, "r" if tag == "circle" else "ry")
        if cx is None or cy is None or rx is None or ry is None:
            return None
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)] if rx > 0 and ry > 0 else []
    if tag in {"polygon", "polyline"}:
        numbers = [float(value) for value in SVG_NUMBER_RE.findall(attrs.get("points", ""))]
        return list(zip(numbers[0::2], numbers[1::2]))
    x, y = svg_length(attrs, "x"), svg_length(attrs, "y")  # text
    return None if x is None or y is None else [(x, y)]


class SvgExtent:
    def __init__(self, attrs: dict[str, str]) -> None:
        self.attrs = attrs
        self.points: list[tuple[float, float, str]] = []
        self.checked = 0
        self.unchecked: Counter[str] = Counter()


class ViewBoxParser(HTMLParser):
    """Each top-level SVG's painted points in viewBox units, and what it could not place."""

    def __init__(self, css_subjects: list[Subject]) -> None:
        super().__init__(convert_charrefs=True)
        self.svgs: list[SvgExtent] = []
        self._css_subjects = css_subjects
        self._frames: list[tuple[str, tuple[float, float] | str]] = []

    def _offset(self, tag: str, attrs: dict[str, str]) -> tuple[float, float] | str:
        parent = self._frames[-1][1]
        if parent == UNPAINTED or tag in DEFINITION_TAGS:
            return UNPAINTED
        if attrs.get("display", "").strip().casefold() == "none":
            return UNPAINTED
        if attrs.get("visibility", "").strip().casefold() in {"hidden", "collapse"}:
            return UNPAINTED
        if parent == UNCHECKED or tag in UNMODELED_TAGS:
            return UNCHECKED
        if declares_unstatic_css(attrs.get("style", "")):
            return UNCHECKED
        if attrs.get("clip-path", "none").strip().casefold() != "none":
            return UNCHECKED
        if attrs.get("mask", "none").strip().casefold() != "none":
            return UNCHECKED
        if any(matches_subject(tag, attrs, subject) for subject in self._css_subjects):
            return UNCHECKED
        assert isinstance(parent, tuple)
        transform = attrs.get("transform")
        if transform is None:
            return parent
        match = TRANSLATE_RE.match(transform)
        if match is None:
            return UNCHECKED
        return parent[0] + float(match.group(1)), parent[1] + float(match.group(2) or 0)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        data = {key.casefold(): value or "" for key, value in attrs}
        if not self._frames:
            if tag == "svg":
                self.svgs.append(SvgExtent(data))
                self._frames.append((tag, (0.0, 0.0)))
            return
        offset = self._offset(tag, data)
        self._frames.append((tag, offset))
        svg = self.svgs[-1]
        if offset == UNPAINTED:
            return
        if offset == UNCHECKED:
            if tag in GEOMETRY_ATTRS or tag in UNMODELED_TAGS - {"svg"}:
                svg.unchecked[tag] += 1
            return
        if tag not in GEOMETRY_ATTRS:
            return
        points = painted_points(tag, data)
        if points is None:
            svg.unchecked[tag] += 1
            return
        assert isinstance(offset, tuple)
        svg.checked += 1
        label = " ".join(
            [f"<{tag}"] + [f'{name}="{data[name]}"' for name in GEOMETRY_ATTRS[tag] if name in data]
        ) + ">"
        for x, y in points:
            svg.points.append((x + offset[0], y + offset[1], label))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self._frames) - 1, -1, -1):
            if self._frames[index][0] == tag:
                del self._frames[index:]
                return


def viewbox_findings(source: str) -> tuple[list[str], list[str]]:
    """(defects, not-checked notes) for every SVG not hidden from assistive technology."""
    parser = ViewBoxParser(unstatic_css_subjects(source))
    parser.feed(source)
    parser.close()
    defects, notes = [], []
    hidden = [number for number, svg in enumerate(parser.svgs, 1)
              if svg.attrs.get("aria-hidden", "").casefold() == "true"]
    if hidden:
        notes.append(f"{len(hidden)} aria-hidden (decorative) svg(s) not checked")
    for number, svg in enumerate(parser.svgs, 1):
        if number in hidden:
            continue
        box = [float(value) for value in SVG_NUMBER_RE.findall(svg.attrs.get("viewbox", ""))]
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            notes.append(f"svg {number}: no usable viewBox, not checked")
            continue
        left, top, width, height = box
        worst: dict[str, tuple[float, str]] = {}
        for x, y, label in svg.points:
            for side, overshoot in (
                ("left", left - x),
                ("top", top - y),
                ("right", x - (left + width)),
                ("bottom", y - (top + height)),
            ):
                if overshoot > VIEWBOX_TOLERANCE and overshoot > worst.get(side, (0.0, ""))[0]:
                    worst[side] = (overshoot, label)
        for side, (overshoot, label) in worst.items():
            defects.append(f"svg {number}: {label} paints {overshoot:g} past the viewBox {side} edge")
        if svg.unchecked:
            listed = ", ".join(f"{count} <{tag}>" for tag, count in sorted(svg.unchecked.items()))
            notes.append(f"svg {number}: {svg.checked} element(s) checked; not checked: {listed}")
    return defects, notes


def preflight(path: Path) -> tuple[list[str], list[str]]:
    source = path.read_bytes().decode("utf-8", errors="replace")
    defects, notes = viewbox_findings(source)
    return completeness_defects(source) + defects, notes


def main(argv: list[str]) -> int:
    if not argv or any(arg in {"-h", "--help"} for arg in argv):
        print(__doc__)
        return 0 if argv else 2
    status = 0
    for name in argv:
        path = Path(name)
        try:
            defects, notes = preflight(path)
        except OSError as error:
            print(f"{path}: not checked: {error}")
            status = 2
            continue
        for line in defects:
            print(f"{path}: DEFECT {line}")
        for line in notes:
            print(f"{path}: {line}")
        print(f"{path}: {len(defects)} defect(s)" if defects else f"{path}: no defect in what was checked")
        if defects and status == 0:
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
