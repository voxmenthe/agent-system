#!/usr/bin/env python3
"""Check an explain-research HTML artifact's citation links and quotations.

    python3 citation_ledger.py ARTIFACT.html [--source FILE ...] [--prefix src-]

The HTML file is the manifest. A line starting with DEFECT: reports no citation
link (an in-page link to an id starting with the prefix); an in-page link
(href="#id") to an id the page does not define; an id defined twice; an empty
<q> or <blockquote>; and, with --source, a <q> or <blockquote> found verbatim
in no source file. Matching ignores case, whitespace, curly quotes and dashes,
HTML tags, and Markdown emphasis, link and blockquote markup; an ellipsis
splits a quotation into parts that must appear in order in one source.

It also counts citation links, [unverified] markers, and prose blocks (p, li,
td, dd, figcaption, outside navigation, quotations and bibliography entries)
that carry neither; those are not checked, because this script never verifies
a paraphrase.

Exit status: 0 with no defect, 1 with a defect, 2 when a file cannot be read.
Standard library only; reads files, writes nothing.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

MARKER = "[unverified]"
PROSE_TAGS = {"p", "li", "td", "dd", "figcaption"}
QUOTE_TAGS = {"q", "blockquote"}
ATTRIBUTION_TAGS = {"cite", "footer", "sup"}  # inside a quotation, but not quoted wording
OPAQUE_TAGS = {"script", "style", "template"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
MIN_PROSE_WORDS = 4
FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
MARKDOWN_QUOTE = re.compile(r"(?m)^[ \t]*>[ \t]?")
TAG = re.compile(r"<[^>]*>")
MARKUP = re.compile(r"[*_`]|\\(?=[^\sA-Za-z0-9])")
ELLIPSIS = re.compile(r"\[?(?:…|\.\.\.)\]?")


@dataclass
class Frame:
    """One open element; prose and quotation elements also collect what they contain."""

    tag: str
    line: int
    prose: bool = False
    quote: bool = False
    hides_quote_text: bool = False
    stops_prose: bool = False
    words: int = 0
    cited: bool = False
    marked: bool = False
    parts: list[str] = field(default_factory=list)


class LedgerParser(HTMLParser):
    def __init__(self, prefix: str) -> None:
        super().__init__(convert_charrefs=True)
        self.prefix = prefix
        self.ids: Counter[str] = Counter()
        self.links: list[tuple[str, int]] = []
        self.quotes: list[Frame] = []
        self.prose: list[Frame] = []
        self.markers = 0
        self.stack: list[Frame] = []

    def _in(self, tags: set[str]) -> bool:
        return any(frame.tag in tags for frame in self.stack)

    def _prose(self) -> Frame | None:
        return next((frame for frame in reversed(self.stack) if frame.prose), None)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._in({"template"}):
            return  # inert until cloned: its ids and links are not on the page
        data = {name: value or "" for name, value in attrs}
        element_id, href = data.get("id", ""), data.get("href", "")
        if element_id:
            self.ids[element_id] += 1
        if tag == "p" and self.stack and self.stack[-1].tag == "p":
            self._close(len(self.stack) - 1)  # a <p> ends the open <p>
        if tag == "a" and len(href) > 1 and href.startswith("#"):
            self.links.append((href[1:], self.getpos()[0]))
            block = self._prose()
            if block and href[1:].startswith(self.prefix):
                block.cited = True
        if tag in VOID_TAGS:
            return
        frame = Frame(tag, self.getpos()[0], quote=tag in QUOTE_TAGS)
        # Contents, quotations (checked as quotations) and bibliography entries are not prose.
        frame.stops_prose = tag in {"nav", "blockquote"} or element_id.startswith(self.prefix)
        frame.prose = tag in PROSE_TAGS and not frame.stops_prose and not any(f.stops_prose for f in self.stack)
        frame.hides_quote_text = tag in ATTRIBUTION_TAGS or (tag == "a" and href.startswith("#"))
        self.stack.append(frame)

    def handle_endtag(self, tag: str) -> None:
        if tag != "template" and self._in({"template"}):
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                self._close(index)
                return

    def handle_data(self, data: str) -> None:
        if self._in(OPAQUE_TAGS):
            return
        block = self._prose()
        if block:
            block.words += len(data.split())
            block.marked = block.marked or MARKER in data
        self.markers += data.count(MARKER)
        for index, frame in enumerate(self.stack):
            if frame.quote and not any(inner.hides_quote_text for inner in self.stack[index + 1 :]):
                frame.parts.append(data)

    def _close(self, index: int) -> None:
        for frame in reversed(self.stack[index:]):
            if frame.prose and frame.words >= MIN_PROSE_WORDS:
                self.prose.append(frame)
            if frame.quote:
                self.quotes.append(frame)
        del self.stack[index:]

    def close(self) -> None:
        super().close()
        self._close(0)


def normalize(text: str) -> str:
    """Comparison key: markup, case and every kind of whitespace removed."""
    text = html.unescape(TAG.sub("", MARKDOWN_LINK.sub(r"\1", MARKDOWN_QUOTE.sub("", text))))
    return "".join(MARKUP.sub("", text.translate(FOLD)).split()).casefold()


def found_in(segments: list[str], source: str) -> bool:
    """True when every segment occurs in source, in order and without overlap."""
    position = 0
    for segment in segments:
        position = source.find(segment, position)
        if position < 0:
            return False
        position += len(segment)
    return True


def check(artifact: str, sources: list[str], prefix: str = "src-") -> tuple[list[str], list[str]]:
    """(defects, report lines) for one artifact against normalized source texts."""
    parser = LedgerParser(prefix)
    parser.feed(artifact)
    parser.close()
    defects, report = [], []
    citations = [target for target, _ in parser.links if target.startswith(prefix)]
    if not citations:
        defects.append(f'no citation link: link each claim to its bibliography entry with href="#{prefix}<n>"')
    defects += [f'line {line}: link href="#{target}" has no matching id'
                for target, line in parser.links if target not in parser.ids]
    defects += [f'id "{name}" is defined {count} times' for name, count in sorted(parser.ids.items()) if count > 1]
    for quote in parser.quotes:
        text = " ".join("".join(quote.parts).split())
        segments = [key for key in (normalize(part).strip("\"'") for part in ELLIPSIS.split(text)) if key]
        if not segments:
            defects.append(f"line {quote.line}: <{quote.tag}> is empty")
        elif sources and not any(found_in(segments, source) for source in sources):
            defects.append(f'line {quote.line}: <{quote.tag}> found verbatim in no --source: "{text[:70]}"')
    if parser.quotes and not sources:
        report.append(f"{len(parser.quotes)} quotation(s) not checked: pass the quoted sources with --source")
    entries = sorted(name for name in parser.ids if name.startswith(prefix))
    unmarked = sum(1 for block in parser.prose if not (block.cited or block.marked))
    report.append(
        f"provenance: {len(citations)} citation link(s) to {len(set(citations) & set(entries))} of "
        f"{len(entries)} source(s); {parser.markers} {MARKER} marker(s); {len(parser.quotes)} quotation(s); "
        f"{unmarked} of {len(parser.prose)} prose block(s) carry neither a citation nor {MARKER} (not checked)"
    )
    uncited = [name for name in entries if name not in citations]
    if uncited:
        report.append("bibliography entries never cited: " + ", ".join(uncited))
    return defects, report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--source", type=Path, nargs="+", default=[], help="text of a quoted source")
    parser.add_argument("--prefix", default="src-", help="id prefix of bibliography entries (default src-)")
    args = parser.parse_args(argv)
    try:
        artifact = args.artifact.read_text(encoding="utf-8", errors="replace")
        sources = [normalize(path.read_text(encoding="utf-8", errors="replace")) for path in args.source]
    except OSError as error:
        print(f"not checked: {error}")
        return 2
    defects, report = check(artifact, sources, args.prefix)
    print("\n".join([f"DEFECT: {line}" for line in defects] + report))
    print(f"{args.artifact}: {len(defects)} defect(s)" if defects else f"{args.artifact}: no defect in what was checked")
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
