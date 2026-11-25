#!/usr/bin/env python3
"""Read WSJ through the user's authenticated Chrome profile.

The browser is the transport. This script never reads cookies or credentials and
never uses a different Chrome profile as a fallback.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterator
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit


PROFILE_EMAIL = os.environ.get("CHROME_PROFILE_EMAIL")
# Confirmed via chrome://version during initial WSJ mapping on 2026-07-29.
# Local State remains authoritative whenever macOS permits it to be read.
OBSERVED_PROFILE_DIRECTORY = "Default"
CHROME_APP = "Google Chrome"
WSJ_HOME = "https://www.wsj.com/"
LATEST_URL = "https://www.wsj.com/news/latest-headlines"
STATE_DIR = Path.home() / ".codex" / "state" / "wsj-research"
STATE_FILE = STATE_DIR / "browser.json"
LOCK_FILE = STATE_DIR / "browser.lock"

EXIT_LOGIN_REQUIRED = 10
EXIT_JAVASCRIPT_DISABLED = 11
EXIT_BROWSER_TIMEOUT = 12
EXIT_USAGE = 64


class WsjError(RuntimeError):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def _run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        if "Allow JavaScript from Apple Events" in detail:
            raise WsjError(
                "Chrome blocks JavaScript from Apple Events. Enable "
                "View > Developer > Allow JavaScript from Apple Events, then retry.",
                EXIT_JAVASCRIPT_DISABLED,
            )
        raise WsjError(f"Chrome automation failed: {detail}")
    return result.stdout.rstrip("\n")


def _js_wrapper(source: str) -> str:
    encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
    return f'eval(atob("{encoded}"))'


def _execute_js(window_id: int, tab_id: int, source: str) -> str:
    wrapper = _js_wrapper(source).replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "{CHROME_APP}"
  set targetWindow to first window whose id is {window_id}
  set targetTab to first tab of targetWindow whose id is {tab_id}
  return execute targetTab javascript "{wrapper}"
end tell
'''
    return _run_applescript(script)


def _execute_json(window_id: int, tab_id: int, source: str) -> Any:
    raw = _execute_js(window_id, tab_id, source)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WsjError(f"WSJ returned malformed structured data: {exc}") from exc


def _window_ids() -> list[int]:
    raw = _run_applescript(
        f'''
tell application "{CHROME_APP}"
  set output to ""
  repeat with browserWindow in windows
    set output to output & (id of browserWindow as text) & linefeed
  end repeat
  return output
end tell
'''
    )
    return [int(value) for value in raw.splitlines() if value.strip().isdigit()]


def _tab_exists(window_id: int, tab_id: int) -> bool:
    """Whether the saved tab is still open, asked by its ids alone: walking every tab fails while other tabs open
    and close (TM, 10-20: -1719, "Can't get item 43 of every tab")."""
    return _run_applescript(
        f'''
tell application "{CHROME_APP}"
  try
    set targetWindow to first window whose id is {window_id}
    set targetTab to first tab of targetWindow whose id is {tab_id}
    return "yes"
  on error
    return "no"
  end try
end tell
'''
    ) == "yes"


def _all_tabs() -> list[dict[str, Any]]:
    """Every tab of every window. A tab opened or closed mid-walk makes AppleScript's index go stale (-1719), so a
    failed walk is retried once."""
    separator = "|||WSJ-RESEARCH|||"
    script = f'''
tell application "{CHROME_APP}"
  set output to ""
  repeat with browserWindow in windows
    repeat with browserTab in tabs of browserWindow
      set output to output & (id of browserWindow as text) & "{separator}" & ¬
        (id of browserTab as text) & "{separator}" & (URL of browserTab as text) & linefeed
    end repeat
  end repeat
  return output
end tell
'''
    try:
        raw = _run_applescript(script)
    except WsjError as error:
        if error.exit_code != 1:
            raise
        time.sleep(0.5)
        raw = _run_applescript(script)
    tabs: list[dict[str, Any]] = []
    for line in raw.splitlines():
        parts = line.split(separator, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            tabs.append(
                {"window_id": int(parts[0]), "tab_id": int(parts[1]), "url": parts[2]}
            )
    return tabs


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(target: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(target, indent=2) + "\n")
    temporary.replace(STATE_FILE)


@contextlib.contextmanager
def _browser_lock() -> Iterator[None]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _resolve_profile_directory() -> str:
    local_state = (
        Path.home()
        / "Library"
        / "Application Support"
        / "Google"
        / "Chrome"
        / "Local State"
    )
    try:
        profile_data = json.loads(local_state.read_text())
    except PermissionError:
        state_value = _load_state().get("profile_directory")
        return str(state_value or OBSERVED_PROFILE_DIRECTORY)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        state_value = _load_state().get("profile_directory")
        if state_value:
            return str(state_value)
        raise WsjError(
            f"Could not resolve the Chrome profile for {PROFILE_EMAIL}. "
            "Open Chrome in that profile and retry."
        )

    info_cache = profile_data.get("profile", {}).get("info_cache", {})
    for directory, record in info_cache.items():
        if record.get("user_name", "").casefold() == PROFILE_EMAIL.casefold():
            return directory
    raise WsjError(
        f"Chrome has no profile registered for {PROFILE_EMAIL}. "
        "Open Chrome in that profile and retry."
    )


def _window_profile_directory(window_id: int) -> str | None:
    js = r'''
(() => {
  const match = (document.body?.innerText || "").match(/Profile Path\s+([^\n]+)/);
  return match ? match[1].trim() : "";
})()
'''
    wrapper = _js_wrapper(js).replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "{CHROME_APP}"
  set targetWindow to first window whose id is {window_id}
  set probeTab to make new tab at end of tabs of targetWindow with properties {{URL:"chrome://version/"}}
  delay 0.6
  try
    set profilePath to execute probeTab javascript "{wrapper}"
  on error errText number errNumber
    close probeTab
    if errText contains "Allow JavaScript from Apple Events" then
      error errText number errNumber
    end if
    return ""
  end try
  close probeTab
  return profilePath
end tell
'''
    path = _run_applescript(script).strip()
    return Path(path).name if path else None


def _find_existing_target(profile_directory: str) -> dict[str, Any] | None:
    candidates = [
        tab
        for tab in _all_tabs()
        if urlsplit(tab["url"]).hostname in {"wsj.com", "www.wsj.com"}
    ]
    checked: dict[int, bool] = {}
    for tab in reversed(candidates):
        window_id = tab["window_id"]
        if window_id not in checked:
            checked[window_id] = (
                _window_profile_directory(window_id) == profile_directory
            )
        if checked[window_id]:
            return {
                "window_id": window_id,
                "tab_id": tab["tab_id"],
                "profile_email": PROFILE_EMAIL,
                "profile_directory": profile_directory,
            }
    return None


def _open_profile_window(profile_directory: str) -> dict[str, Any]:
    before = set(_window_ids())
    result = subprocess.run(
        [
            "open",
            "-na",
            CHROME_APP,
            "--args",
            f"--profile-directory={profile_directory}",
            "--new-window",
            WSJ_HOME,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise WsjError(f"Could not open Chrome: {result.stderr.strip()}")

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        time.sleep(0.25)
        after = set(_window_ids())
        new_ids = after - before
        tabs = _all_tabs()
        for tab in reversed(tabs):
            if tab["window_id"] in new_ids and "wsj.com" in tab["url"]:
                target = {
                    "window_id": tab["window_id"],
                    "tab_id": tab["tab_id"],
                    "profile_email": PROFILE_EMAIL,
                    "profile_directory": profile_directory,
                }
                # Verify Chrome honored --profile-directory before trusting it.
                if _window_profile_directory(tab["window_id"]) == profile_directory:
                    return target
        existing = _find_existing_target(profile_directory)
        if existing:
            return existing
    raise WsjError("Timed out opening the WSJ Chrome window.", EXIT_BROWSER_TIMEOUT)


def _target() -> dict[str, Any]:
    profile_directory = _resolve_profile_directory()
    state = _load_state()
    window_id, tab_id = state.get("window_id"), state.get("tab_id")
    if (
        state.get("profile_email") == PROFILE_EMAIL
        and state.get("profile_directory") == profile_directory
        and isinstance(window_id, int)
        and isinstance(tab_id, int)
        and _tab_exists(window_id, tab_id)
    ):
        return state

    target = _find_existing_target(profile_directory)
    if target is None:
        target = _open_profile_window(profile_directory)
    _save_state(target)
    return target


def _navigate(target: dict[str, Any], url: str) -> None:
    escaped_url = url.replace("\\", "\\\\").replace('"', '\\"')
    # A WSJ page already in the tab has __NEXT_DATA__ too, so readiness alone can pass on
    # the old document and the next read returns the previous page. Mark the old document
    # first; only a newly loaded one lacks the mark.
    leaving_js = "window.__wsjResearchLeaving = true; 'marked'"
    ready_js = (
        "document.getElementById('__NEXT_DATA__') && !window.__wsjResearchLeaving ? 'ready' : ''"
    ).replace('"', '\\"')
    script = f'''
tell application "{CHROME_APP}"
  set targetWindow to first window whose id is {target["window_id"]}
  set targetTab to first tab of targetWindow whose id is {target["tab_id"]}
  try
    execute targetTab javascript "{leaving_js}"
  end try
  set URL of targetTab to "{escaped_url}"
  repeat 120 times
    delay 0.25
    set pageReady to ""
    try
      set pageReady to execute targetTab javascript "{ready_js}"
    end try
    if pageReady is "ready" then exit repeat
  end repeat
  return pageReady & "|||WSJ-RESEARCH|||" & (URL of targetTab as text)
end tell
'''
    navigation_result = _run_applescript(script)
    readiness, separator, final_url = navigation_result.partition(
        "|||WSJ-RESEARCH|||"
    )
    if not separator or readiness != "ready" or not final_url:
        raise WsjError("WSJ navigation did not complete.", EXIT_BROWSER_TIMEOUT)
    time.sleep(0.65)


AUTH_JS = r'''
(() => {
  const headerNodes = [...document.querySelectorAll("header button, header a")];
  const labels = headerNodes.map(node => (node.innerText || "").trim()).filter(Boolean);
  const buttonLabels = [...document.querySelectorAll("header button")]
    .map(node => (node.innerText || "").trim()).filter(Boolean);
  const signedOut = labels.some(label => /^(sign in|log in)$/i.test(label));
  const account = buttonLabels.find(label =>
    !/^(search|open search|menu|more|subscribe|sign in|log in|home|english edition)$/i.test(label) &&
    label.split(/\s+/).length >= 2 &&
    label.length < 60
  ) || "";
  let entitled = false;
  try {
    const next = JSON.parse(document.getElementById("__NEXT_DATA__")?.textContent || "{}");
    entitled = Boolean(next?.props?.pageProps?.dylanEntitlementToken);
  } catch (_) {}
  // Older /articles/ templates render a minimal header with no account
  // button, so the account label is diagnostic only: entitlement plus no
  // Sign In control is sufficient evidence of the subscriber session.
  return JSON.stringify({
    authenticated: Boolean(!signedOut && entitled),
    account_label: account,
    header_sparse: Boolean(!account),
    signed_out_signal: signedOut,
    entitlement_present: entitled,
    url: location.href
  });
})()
'''


def _require_login(target: dict[str, Any]) -> dict[str, Any]:
    status: dict[str, Any] = {}
    for _ in range(30):
        status = _execute_json(target["window_id"], target["tab_id"], AUTH_JS)
        if status.get("authenticated"):
            return status
        if status.get("signed_out_signal"):
            break
        # The header can render after __NEXT_DATA__; retry briefly so a
        # late-rendering Sign In control can break the loop early.
        time.sleep(0.25)
    raise WsjError(
        f"WSJ is not logged in in the {PROFILE_EMAIL} Chrome profile. "
        "Stop and ask the user to log in there, then rerun the command.",
        EXIT_LOGIN_REQUIRED,
    )


def _clean_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def command_status(_: argparse.Namespace) -> None:
    target = _target()
    _navigate(target, WSJ_HOME)
    auth = _require_login(target)
    _print_json(
        {
            "authenticated": True,
            "profile_email": PROFILE_EMAIL,
            "profile_directory": target["profile_directory"],
            "window_id": target["window_id"],
            "tab_id": target["tab_id"],
            "account_label": auth["account_label"],
            "header_sparse": auth["header_sparse"],
            "url": auth["url"],
        }
    )


FRONTPAGE_JS = r'''
(() => {
  const page = JSON.parse(document.getElementById("__NEXT_DATA__")?.textContent || "{}")
    ?.props?.pageProps || {};
  const byHeadline = new Map();
  const seenObjects = new Set();
  function text(value) {
    if (value == null) return "";
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map(text).join("");
    if (typeof value === "object") return text(value.text ?? value.content ?? "");
    return "";
  }
  function walk(value) {
    if (!value || typeof value !== "object" || seenObjects.has(value)) return;
    seenObjects.add(value);
    if (value.headline && value.articleUrl) {
      byHeadline.set(String(value.headline).trim(), value);
    }
    Object.values(value).forEach(walk);
  }
  walk(page);
  let section = "Top Stories";
  const stories = [];
  const seenUrls = new Set();
  for (const heading of document.querySelectorAll("main h1, main h2, main h3")) {
    const label = (heading.innerText || "").trim();
    if (!label) continue;
    if (heading.tagName === "H2") {
      section = label;
      continue;
    }
    if (heading.tagName !== "H3") continue;
    const anchor = heading.closest("a") || heading.querySelector("a");
    const rawUrl = anchor?.href || "";
    if (!rawUrl || !/^https:\/\/(www\.)?wsj\.com\//.test(rawUrl)) continue;
    const url = rawUrl.split("?")[0].split("#")[0];
    if (seenUrls.has(url)) continue;
    seenUrls.add(url);
    const data = byHeadline.get(label) || {};
    const authors = (data.authors || []).map(a => a?.name).filter(Boolean);
    stories.push({
      section,
      headline: label,
      url,
      summary: text(data.summary),
      flashline: text(data.flashline),
      timestamp: data.timestamp || null,
      authors,
      is_opinion: data.isOpinion === true,
      module: data.modCode || new URL(rawUrl).searchParams.get("mod") || null
    });
  }
  return JSON.stringify({title: document.title, url: location.href, stories});
})()
'''


def classify_story(story: dict[str, Any]) -> dict[str, Any]:
    """Native flags/section and a URL path segment classify commentary, never the headline or query."""
    basis = []
    if story.get("is_opinion") is True:
        basis.append("native-flag")
    if re.search(r"\bopinion\b", str(story.get("section", "")), re.IGNORECASE):
        basis.append("native-section")
    if "opinion" in unquote(urlsplit(story["url"]).path).casefold().split("/"):
        basis.append("url-path")
    return {**story, "is_opinion": bool(basis), "opinion_basis": basis}


def command_frontpage(args: argparse.Namespace) -> None:
    target = _target()
    _navigate(target, WSJ_HOME)
    _require_login(target)
    data = _execute_json(target["window_id"], target["tab_id"], FRONTPAGE_JS)
    excluded = {"wsj | buy side", "videos"}
    stories = []
    for story in data["stories"]:
        story = classify_story(story)
        section = story["section"].casefold()
        if section in excluded and not args.include_extras:
            continue
        if story["is_opinion"] and args.exclude_opinion:
            continue
        stories.append(story)
        if len(stories) >= args.max:
            break
    data["stories"] = stories
    data["count"] = len(stories)
    data["profile_email"] = PROFILE_EMAIL
    _print_json(data)


LATEST_JS = r'''
(() => {
  const page = JSON.parse(document.getElementById("__NEXT_DATA__")?.textContent || "{}")
    ?.props?.pageProps || {};
  const text = value => Array.isArray(value)
    ? value.map(text).join("")
    : (value && typeof value === "object")
      ? text(value.text ?? value.content ?? "")
      : String(value ?? "");
  const stories = (page.latestHeadlines || []).map(item => ({
    headline: item.headline || "",
    url: (item.articleUrl || "").split("?")[0],
    summary: item.summary || "",
    timestamp: item.timestamp || null,
    flashline: item.flashline || "",
    authors: (item.bylineData || [])
      .filter(part => part?.type === "author")
      .map(part => part.name || part.text)
      .filter(Boolean),
    is_opinion: Boolean(item.isOpinion),
    is_video: Boolean(item.isVideo),
    type: item.type || ""
  }));
  return JSON.stringify({title: document.title, url: location.href, stories});
})()
'''


def command_latest(args: argparse.Namespace) -> None:
    target = _target()
    _navigate(target, LATEST_URL)
    _require_login(target)
    data = _execute_json(target["window_id"], target["tab_id"], LATEST_JS)
    stories = [
        story
        for story in map(classify_story, data["stories"])
        if not (args.exclude_opinion and story["is_opinion"])
        and not (args.exclude_video and story["is_video"])
    ][: args.max]
    data["stories"] = stories
    data["count"] = len(stories)
    data["profile_email"] = PROFILE_EMAIL
    _print_json(data)


SEARCH_JS = r'''
(() => {
  const page = JSON.parse(document.getElementById("__NEXT_DATA__")?.textContent || "{}")
    ?.props?.pageProps || {};
  const authors = byline => (byline || [])
    .filter(part => part?.type === "author")
    .map(part => part.name || part.text)
    .filter(Boolean);
  return JSON.stringify({
    query: page.queryValue || "",
    page_number: page.pageNumber || 1,
    results_count_meta: page.resultsCountMeta || null,
    advanced_search_fields: page.advancedSearchFields || {},
    results: (page.searchResults || []).map(item => ({
      headline: item.headline || "",
      url: (item.articleUrl || "").split("?")[0],
      summary: item.summary || "",
      timestamp: item.timestamp || null,
      flashline: item.flashline || "",
      authors: authors(item.bylineData),
      print_headline: item.printHeadline || "",
      print_publication_date: item.printPublicationDate || null,
      seo_path: item.seoPathValue || ""
    })),
    sponsored_count: (page.sponsoredContent || []).length
  });
})()
'''


def _parse_day(value: str | None, *, end: bool = False) -> dt.datetime | None:
    if not value:
        return None
    try:
        day = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise WsjError(f"Invalid date {value!r}; use YYYY-MM-DD.", EXIT_USAGE) from exc
    if end:
        day += dt.timedelta(days=1)
    return dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)


def _parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def command_search(args: argparse.Namespace) -> None:
    products = [item.strip() for item in args.products.split(",") if item.strip()]
    allowed_products = {"wsj", "video", "audio", "livecoverage", "buyside", "games"}
    unknown = set(products) - allowed_products
    if unknown:
        raise WsjError(
            f"Unknown product filter(s): {', '.join(sorted(unknown))}", EXIT_USAGE
        )
    start = _parse_day(args.from_date)
    end = _parse_day(args.to_date, end=True)
    if start and end and start >= end:
        raise WsjError("--from must be on or before --to.", EXIT_USAGE)
    sort = args.sort or ("desc" if start or end else "relevance")

    target = _target()
    all_results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    pages_fetched = 0
    first_metadata: dict[str, Any] = {}
    last_page_full = False
    stopped_at_boundary = False

    for page_number in range(1, args.pages + 1):
        params: dict[str, Any] = {
            "query": args.query,
            "dateRange": args.date_range,
            "products": ",".join(products),
            "sort": sort,
        }
        if page_number > 1:
            params["page"] = page_number
        url = "https://www.wsj.com/search?" + urlencode(params)
        _navigate(target, url)
        _require_login(target)
        page = _execute_json(target["window_id"], target["tab_id"], SEARCH_JS)
        pages_fetched += 1
        if page_number == 1:
            first_metadata = {
                "results_count_meta": page.get("results_count_meta"),
                "advanced_search_fields": page.get("advanced_search_fields"),
                "sponsored_count_page_1": page.get("sponsored_count", 0),
            }
        page_results = page.get("results", [])
        last_page_full = len(page_results) >= 20
        timestamps = [
            parsed
            for parsed in (_parse_timestamp(item.get("timestamp")) for item in page_results)
            if parsed
        ]
        for item in page_results:
            canonical = _clean_url(item["url"])
            if not canonical or canonical in seen_urls:
                continue
            timestamp = _parse_timestamp(item.get("timestamp"))
            if start and (timestamp is None or timestamp < start):
                continue
            if end and (timestamp is None or timestamp >= end):
                continue
            item["url"] = canonical
            seen_urls.add(canonical)
            all_results.append(item)
            if len(all_results) >= args.max_results:
                break
        if len(all_results) >= args.max_results or len(page_results) < 20:
            break
        if timestamps and sort == "desc" and start and min(timestamps) < start:
            stopped_at_boundary = True
            break
        if timestamps and sort == "asc" and end and max(timestamps) >= end:
            stopped_at_boundary = True
            break

    truncated = (
        len(all_results) >= args.max_results
        or (pages_fetched >= args.pages and last_page_full and not stopped_at_boundary)
    )
    output = {
        "query": args.query,
        "date_range": args.date_range,
        "from": args.from_date,
        "to": args.to_date,
        "sort": sort,
        "products": products,
        "pages_fetched": pages_fetched,
        "count": len(all_results),
        "truncated": truncated,
        "results": all_results,
        "profile_email": PROFILE_EMAIL,
        **first_metadata,
    }
    if truncated:
        output["warning"] = (
            "The page/result cap was reached. Increase --pages or --max-results "
            "before treating this as an exhaustive result set."
        )
    _print_json(output)


ARTICLE_JS = r'''
(() => {
  const next = JSON.parse(document.getElementById("__NEXT_DATA__")?.textContent || "{}");
  const page = next?.props?.pageProps || {};
  const article = page.articleData || null;
  function text(value) {
    if (value == null) return "";
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map(text).join("");
    if (typeof value === "object") {
      if (typeof value.text === "string") return value.text;
      if (value.content != null) return text(value.content);
      return "";
    }
    return "";
  }
  const blocks = [];
  const quickSummary = [];
  if (article?.flattenedBody) {
    for (const block of article.flattenedBody) {
      if (!block || block.type === "ad") continue;
      if (block.type === "paragraph") {
        const value = text(block.content).trim();
        if (value) blocks.push({type: "paragraph", text: value});
      } else if (block.type === "hed") {
        const value = text(block.content).trim();
        if (value) blocks.push({type: "heading", text: value});
      } else if (block.type === "inset" && block.insetType === "ai_summary_bullets") {
        for (const bullet of block.bullets || []) {
          const value = text(bullet).trim();
          if (value) quickSummary.push(value);
        }
      } else if (/list/i.test(block.type || "")) {
        const values = (block.items || block.content || [])
          .map(text).map(value => value.trim()).filter(Boolean);
        if (values.length) blocks.push({type: "list", items: values});
      }
    }
  }
  if (article) {
    return JSON.stringify({
      extraction: "articleData.flattenedBody",
      canonical_url: article.canonicalUrl || location.href.split("?")[0],
      headline: text(article.headline).trim() || article.printHeadline || "",
      dek: text(article.standFirst).trim(),
      flashline: text(article.flashline).trim(),
      section: article.sectionName || "",
      article_type: article.typeDisplayName || article.sectionType || "",
      byline: text(article.byline).trim(),
      authors: (article.authors || []).map(a => a?.name || a?.text).filter(Boolean),
      published_at: article.publishedDateTimeUtc || article.printPublicationDate || null,
      updated_at: article.updatedDateTimeUtc || null,
      is_free_article: page.isFreeArticle ?? null,
      paywall_index: page.paywallIndex ?? null,
      quick_summary: quickSummary,
      blocks,
      body_character_count: JSON.stringify(blocks).length
    });
  }
  let schema = {};
  for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const parsed = JSON.parse(node.textContent);
      const candidates = Array.isArray(parsed) ? parsed : [parsed];
      schema = candidates.find(item => /NewsArticle|Article/.test(item?.["@type"] || "")) || schema;
    } catch (_) {}
  }
  const paragraphs = [...document.querySelectorAll("main p")]
    .map(node => (node.innerText || "").trim())
    .filter(value => value.length >= 40);
  return JSON.stringify({
    extraction: "dom_fallback",
    canonical_url: schema.url || location.href.split("?")[0],
    headline: schema.headline || document.querySelector("main h1")?.innerText?.trim() || document.title,
    dek: schema.description || "",
    flashline: "",
    section: schema.articleSection || "",
    article_type: schema["@type"] || "",
    byline: "",
    authors: (Array.isArray(schema.author) ? schema.author : [schema.author])
      .filter(Boolean).map(a => typeof a === "string" ? a : a.name).filter(Boolean),
    published_at: schema.datePublished || null,
    updated_at: schema.dateModified || null,
    is_free_article: page.isFreeArticle ?? null,
    paywall_index: page.paywallIndex ?? null,
    quick_summary: [],
    blocks: paragraphs.map(value => ({type: "paragraph", text: value})),
    body_character_count: paragraphs.join("\n\n").length
  });
})()
'''


def command_article(args: argparse.Namespace) -> None:
    hostname = urlsplit(args.url).hostname
    if hostname not in {"wsj.com", "www.wsj.com"}:
        raise WsjError("Article URL must be on wsj.com.", EXIT_USAGE)
    target = _target()
    _navigate(target, args.url)
    _require_login(target)
    article = _execute_json(target["window_id"], target["tab_id"], ARTICLE_JS)
    blocks = article.get("blocks", [])
    if args.metadata_only:
        article.pop("blocks", None)
    elif args.max_characters:
        kept: list[dict[str, Any]] = []
        used = 0
        for block in blocks:
            size = len(json.dumps(block, ensure_ascii=False))
            if used + size > args.max_characters:
                article["body_truncated"] = True
                break
            kept.append(block)
            used += size
        article["blocks"] = kept
    article["profile_email"] = PROFILE_EMAIL
    _print_json(article)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Research WSJ through the authenticated Chrome profile named by CHROME_PROFILE_EMAIL."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Verify profile and WSJ login.")
    status.set_defaults(func=command_status)

    frontpage = subparsers.add_parser(
        "frontpage", help="Get the editorially ranked WSJ homepage."
    )
    frontpage.add_argument("--max", type=int, default=50)
    frontpage.add_argument(
        "--exclude-opinion", action="store_true", help="Omit Opinion stories."
    )
    frontpage.add_argument(
        "--include-extras",
        action="store_true",
        help="Include Buy Side and video modules.",
    )
    frontpage.set_defaults(func=command_frontpage)

    latest = subparsers.add_parser(
        "latest", help="Get the 50-item Latest Headlines feed."
    )
    latest.add_argument("--max", type=int, default=50)
    latest.add_argument("--exclude-opinion", action="store_true")
    latest.add_argument("--exclude-video", action="store_true")
    latest.set_defaults(func=command_latest)

    search = subparsers.add_parser(
        "search", help="Search WSJ, paginate, and optionally filter exact dates."
    )
    search.add_argument("query")
    search.add_argument(
        "--date-range",
        choices=["1d", "7d", "30d", "1yr", "all"],
        default="all",
    )
    search.add_argument("--sort", choices=["relevance", "desc", "asc"])
    search.add_argument(
        "--products",
        default="wsj",
        help="Comma-separated: wsj,video,audio,livecoverage,buyside,games.",
    )
    search.add_argument("--pages", type=int, default=3)
    search.add_argument("--max-results", type=int, default=200)
    search.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD")
    search.add_argument("--to", dest="to_date", metavar="YYYY-MM-DD")
    search.set_defaults(func=command_search)

    article = subparsers.add_parser(
        "article", help="Extract one authenticated WSJ article."
    )
    article.add_argument("url")
    article.add_argument("--metadata-only", action="store_true")
    article.add_argument(
        "--max-characters",
        type=int,
        default=100_000,
        help="Limit serialized body blocks (default: 100000).",
    )
    article.set_defaults(func=command_article)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "pages", 1) < 1 or getattr(args, "max", 1) < 1:
        parser.error("page and result limits must be positive")
    if not PROFILE_EMAIL:
        print(
            "wsj: CHROME_PROFILE_EMAIL is not set. Export the email of the Chrome profile "
            "signed in to WSJ, in ~/.config/agent-system/shell.local.sh.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        with _browser_lock():
            args.func(args)
        return 0
    except WsjError as exc:
        print(f"wsj: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("wsj: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
