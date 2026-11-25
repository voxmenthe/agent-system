#!/usr/bin/env python3
"""Work offline with an X bookmark-folder capture exported by x-folder.js.

  summary CAPTURE [--since D] [--until D]   coverage, cursor timeline, window counts
  list CAPTURE [--since D] [--only in,boundary] [--format text|jsonl]
  diff CAPTURE PRIOR                         new and absent post IDs
  fetch URL --dest DIR [--name F] [--kind K] [--manifest M] [--ref URL]

Bookmark-added bounds come from X's page cursors, an inferred and undocumented
signal: items on pages 1..k were saved at or after page k's cursor, and items
on later pages before it. A window status of "boundary" means the bounds
straddle a window edge; never guess those.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

SCHEMA = "x-bookmark-folder-capture/1"
DEFAULT_TZ = "America/Los_Angeles"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a")


class CaptureError(Exception):
    """The capture or prior snapshot does not have the expected shape."""


class FetchError(Exception):
    """A transfer failed or its bytes failed validation."""


@dataclass(frozen=True)
class Window:
    since: datetime
    until: datetime | None
    label: str


def parse_time(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_capture(path: Path) -> dict:
    capture = json.loads(path.read_text())
    if capture.get("schema") != SCHEMA:
        raise CaptureError(f"{path}: schema is {capture.get('schema')!r}, expected {SCHEMA!r}")
    pages = {p["page"] for p in capture["pages"]}
    for record in capture["records"]:
        if record["page"] not in pages:
            raise CaptureError(f"{path}: record {record['id']} names missing page {record['page']}")
    return capture


def added_bounds(capture: dict) -> dict[str, tuple[datetime | None, datetime]]:
    """Map post ID to (saved no earlier than, saved no later than)."""
    pages = capture["pages"]
    by_page: dict[int, list[dict]] = {}
    for record in capture["records"]:
        by_page.setdefault(record["page"], []).append(record)
    bounds = {}
    for index, page in enumerate(pages):
        records = sorted(by_page.get(page["page"], []), key=lambda r: r["pos"])
        if not records:
            continue
        previous = pages[index - 1]["cursor_time"] if index else page["fetched_at"]
        upper = parse_time(previous)
        if upper is None:
            raise CaptureError(f"page {page['page']} has no upper bound: previous page lacks a cursor")
        # Later items were saved earlier, and each after it was published, so
        # the latest publish time at or below an item is a floor for its save.
        lower = parse_time(page["cursor_time"])
        for record in reversed(records):
            published = parse_time(record.get("published_at"))
            if published and (lower is None or published > lower):
                lower = published
            bounds[record["id"]] = (lower, upper)
    return bounds


def window_status(lower: datetime | None, upper: datetime, window: Window) -> str:
    if upper < window.since or (window.until and lower and lower >= window.until):
        return "out"
    if lower and lower >= window.since and (window.until is None or upper < window.until):
        return "in"
    return "boundary"


def window_covered(capture: dict, window: Window) -> bool:
    """True when every item saved inside the window is among the records."""
    exported = capture["pages"][: capture["exported_pages"]]
    if capture["complete"] and len(exported) == len(capture["pages"]):
        return True
    last_cursor = next((parse_time(p["cursor_time"]) for p in reversed(exported) if p["cursor_time"]), None)
    return last_cursor is not None and last_cursor < window.since


def make_window(since: str | None, until: str | None, tz_name: str) -> Window | None:
    if since is None:
        if until is not None:
            raise SystemExit("--until needs --since")
        return None
    tz = ZoneInfo(tz_name)

    def edge(value: str, inclusive_end: bool) -> datetime:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            day = date.fromisoformat(value) + timedelta(days=1 if inclusive_end else 0)
            return datetime.combine(day, time(), tz)
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise SystemExit(f"{value}: give a date or a datetime with an offset")
        return moment

    start = edge(since, False)
    end = edge(until, True) if until else None
    label = f"{since} through {until or 'capture'} ({tz_name}); end exclusive {end.isoformat() if end else 'none'}"
    return Window(start, end, label)


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if value else None


def command_summary(args: argparse.Namespace) -> int:
    capture = load_capture(args.capture)
    records = capture["records"]
    folder = capture["folder"]
    print(f"folder: {folder['label']!r} {folder['url']}")
    print(f"account: {capture['account']}  exported: {capture['exported_at']}")
    print(f"pages: {len(capture['pages'])} fetched, {capture['exported_pages']} exported; "
          f"records: {len(records)} ({len({r['id'] for r in records})} unique, "
          f"{sum(1 for r in records if r.get('unavailable'))} unavailable)")
    print(f"complete: {capture['complete']}  last stop: {capture['last_stop']}  http errors: {capture['http_errors']}")
    for page in capture["pages"]:
        print(f"  page {page['page']:>3}: {page['items']:>2} items, cursor {page['cursor_time']}")
    window = make_window(args.since, args.until, args.tz)
    if window:
        bounds = added_bounds(capture)
        counts: dict[str, int] = {}
        for record in records:
            status = window_status(*bounds[record["id"]], window)
            counts[status] = counts.get(status, 0) + 1
        print(f"window: {window.label}")
        print(f"  in {counts.get('in', 0)}, boundary {counts.get('boundary', 0)}, out {counts.get('out', 0)}")
        if not window_covered(capture, window):
            print("  NOT COVERED: older pages may hold in-window items; capture further with more({until})")
            return 2
    return 0


def command_list(args: argparse.Namespace) -> int:
    capture = load_capture(args.capture)
    window = make_window(args.since, args.until, args.tz)
    only = set(args.only.split(",")) if args.only else None
    if only and not window:
        raise SystemExit("--only needs --since")
    bounds = added_bounds(capture)
    for record in capture["records"]:
        lower, upper = bounds[record["id"]]
        status = window_status(lower, upper, window) if window else None
        if only and status not in only:
            continue
        row = {**record, "added_after": iso(lower), "added_before": iso(upper), "window": status}
        if args.format == "jsonl":
            print(json.dumps(row, ensure_ascii=False))
            continue
        head = f"[{status}] " if status else ""
        print(f"{head}{record['page']}.{record['pos']} {record['url']}")
        if record.get("unavailable"):
            print(f"  unavailable: {record['unavailable']}")
            continue
        print(f"  @{record['handle']} published {record['published_at']}; saved {iso(lower)} .. {iso(upper)}")
        text = record["text"] if args.chars == 0 else record["text"][: args.chars]
        print("  " + text.replace("\n", "\n  ") + ("…" if len(text) < len(record["text"]) else ""))
        extras = [*record["links"], *(m["video"] or m["url"] for m in record["media"])]
        if record.get("card_url") and record["card_url"] not in record["links"]:
            extras.append(f"card: {record['card_url']}")
        if record.get("article_title"):
            extras.append(f"article: {record['article_title']}")
        if record.get("quoted"):
            q = record["quoted"]
            extras.append(f"quotes {q.get('url', q['id'])}")
        for extra in extras:
            print(f"  - {extra}")
    return 0


PRIOR_LISTS = (("records", "id"), ("posts", "post_id"), ("bookmarks", "post_id"))


def prior_ids(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text())
    for key, id_field in PRIOR_LISTS:
        if isinstance(data.get(key), list):
            return {str(item[id_field]): item for item in data[key]}
    raise CaptureError(f"{path}: no records, posts, or bookmarks list")


def command_diff(args: argparse.Namespace) -> int:
    capture = load_capture(args.capture)
    prior = prior_ids(args.prior)
    current = {r["id"]: r for r in capture["records"]}
    new = [i for i in current if i not in prior]
    absent = [i for i in prior if i not in current]
    if args.format == "jsonl":
        for post_id, record in current.items():
            known = prior.get(post_id)
            print(json.dumps({"id": post_id, "url": record.get("url"), "status": "known" if known else "new",
                              "first_observed_at": (known or {}).get("first_observed_at") or
                              (None if known else capture["exported_at"])}))
        return 0
    print(f"current {len(current)}, prior {len(prior)}: {len(new)} new, {len(absent)} absent")
    if not (capture["complete"] and capture["exported_pages"] == len(capture["pages"])):
        print("capture stops before the folder end: absent IDs may simply be older than the captured pages")
    for post_id in new:
        print(f"new {current[post_id]['url']}")
    for post_id in absent:
        print(f"absent {post_id}")
    return 0


def kind_of(content_type: str, data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(IMAGE_MAGIC) or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        return "image"
    if data[4:8] == b"ftyp":
        return "video"
    if content_type == "text/html" or re.match(rb"\s*<(!doctype html|html)", data[:512], re.I):
        return "html"
    return "data"


def check(kind: str, data: bytes, staged: Path) -> dict:
    checks: dict = {"kind": kind}
    if kind == "pdf":
        checks["eof_marker"] = b"%%EOF" in data[-2048:]
        if not checks["eof_marker"]:
            raise FetchError("PDF has no %%EOF marker near its end: truncated transfer")
        if shutil.which("pdfinfo"):
            result = subprocess.run(["pdfinfo", str(staged)], capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise FetchError(f"pdfinfo rejected the file: {result.stderr.strip()[:200]}")
            info = dict(line.split(":", 1) for line in result.stdout.splitlines() if ":" in line)
            checks["pages"] = int(info.get("Pages", "0").strip() or 0)
            checks["title"] = info.get("Title", "").strip() or None
        else:
            checks["pdfinfo"] = "unavailable"
    return checks


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.+-]+", "-", name).strip("-.")
    if not cleaned:
        raise SystemExit("cannot derive a file name; pass --name")
    return cleaned


def command_fetch(args: argparse.Namespace) -> int:
    url = args.url
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise SystemExit(f"{url}: only http(s) URLs")
    headers = {"User-Agent": BROWSER_UA}
    if parts.hostname and parts.hostname.endswith("twimg.com"):
        headers["Referer"] = "https://x.com/"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            expected = response.headers.get("Content-Length")
            data = response.read()
    except http.client.IncompleteRead as error:
        raise FetchError(f"{url}: truncated transfer, {len(error.partial)} bytes read") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise FetchError(f"{url}: {error}") from error
    if expected is not None and int(expected) != len(data):
        raise FetchError(f"{url}: truncated transfer, {len(data)} of {expected} bytes")
    kind = kind_of(content_type, data)
    if kind == "html" and args.kind != "html":
        raise FetchError(f"{url}: server returned HTML (login, error, or landing page), not a file")
    if args.kind not in ("auto", kind):
        raise FetchError(f"{url}: expected {args.kind}, got {kind} ({content_type or 'no content type'})")
    with tempfile.TemporaryDirectory(prefix="xb-fetch-") as scratch:
        staged = Path(scratch) / "file"
        staged.write_bytes(data)
        checks = check(kind, data, staged)
    name = safe_name(args.name or Path(urllib.parse.urlsplit(final_url).path).name)
    if kind == "pdf" and not name.lower().endswith(".pdf"):
        name += ".pdf"
    digest = hashlib.sha256(data).hexdigest()
    args.dest.mkdir(parents=True, exist_ok=True)
    target = args.dest / name
    try:
        out = target.open("xb")
    except FileExistsError:
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise FetchError(f"{target} exists with different content; choose a distinct --name") from None
        status = "reused"
    else:
        with out:
            try:
                out.write(data)
            except OSError:
                target.unlink()
                raise
        status = "saved"
    row = {
        "status": status, "path": str(target), "bytes": len(data), "sha256": digest,
        "requested_url": url, "final_url": final_url, "content_type": content_type,
        "retrieved_at": iso(datetime.now(timezone.utc)),
        "checks": checks, "refs": args.ref,
    }
    if args.manifest:
        with args.manifest.open("a") as manifest:
            manifest.write(json.dumps(row) + "\n")
    print(json.dumps(row))
    return 0


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = main.add_subparsers(dest="command", required=True)

    def windowed(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("capture", type=Path)
        sub.add_argument("--since", help="window start: YYYY-MM-DD (inclusive) or ISO datetime with offset")
        sub.add_argument("--until", help="window end: YYYY-MM-DD (inclusive) or ISO datetime (exclusive)")
        sub.add_argument("--tz", default=DEFAULT_TZ, help=f"zone for date-only bounds (default {DEFAULT_TZ})")

    summary = commands.add_parser("summary", help="coverage, cursor timeline, window counts; exit 2 if the window is not covered")
    windowed(summary)
    summary.set_defaults(run=command_summary)

    listing = commands.add_parser("list", help="records with bookmark-added bounds and window status")
    windowed(listing)
    listing.add_argument("--only", help="comma list of window statuses to keep: in,boundary,out")
    listing.add_argument("--chars", type=int, default=400, help="text characters per record; 0 for all")
    listing.add_argument("--format", choices=("text", "jsonl"), default="text")
    listing.set_defaults(run=command_list)

    diff = commands.add_parser("diff", help="compare post IDs with a prior capture, capture snapshot, or intake manifest")
    diff.add_argument("capture", type=Path)
    diff.add_argument("prior", type=Path)
    diff.add_argument("--format", choices=("text", "jsonl"), default="text")
    diff.set_defaults(run=command_diff)

    fetch = commands.add_parser("fetch", help="download one public file, validate it, and save it without overwriting")
    fetch.add_argument("url")
    fetch.add_argument("--dest", type=Path, required=True)
    fetch.add_argument("--name", help="file name in --dest (default: last URL path segment)")
    fetch.add_argument("--kind", choices=("auto", "pdf", "image", "video", "data", "html"), default="auto")
    fetch.add_argument("--manifest", type=Path, help="append the result row to this JSONL file")
    fetch.add_argument("--ref", action="append", default=[], help="referring bookmark URL; repeatable")
    fetch.add_argument("--timeout", type=float, default=120)
    fetch.set_defaults(run=command_fetch)
    return main


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.run(args)
    except (CaptureError, FetchError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
