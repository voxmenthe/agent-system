#!/usr/bin/env python3
"""Read WSJ through the user's authenticated Chrome profile.

The browser is the transport. This script never reads cookies or credentials and
never uses a different Chrome profile as a fallback.

Two ways to drive that Chrome, tried in this order (`--transport auto`):

1. Claude in Chrome: a `claude --claude-in-chrome-mcp` server, spoken to over
   stdio. It works in a tab group behind the user's windows.
2. AppleScript, only when Claude in Chrome does not connect after one retry. It
   drives a window the helper opened itself, never a tab the user opened.

Each command's JSON says which transport ran. A fallback is explained on stderr.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import gzip
import json
import os
from pathlib import Path
import pwd
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Any, Iterator, Protocol
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit


PROFILE_EMAIL = os.environ.get("CHROME_PROFILE_EMAIL")
# Confirmed via chrome://version during initial WSJ mapping on 2026-07-29.
# Local State remains authoritative whenever macOS permits it to be read.
OBSERVED_PROFILE_DIRECTORY = "Default"
CHROME_APP = "Google Chrome"
CHROME_BUNDLE_ID = "com.google.Chrome"
WSJ_HOME = "https://www.wsj.com/"
LATEST_URL = "https://www.wsj.com/news/latest-headlines"
STATE_DIR = Path.home() / ".codex" / "state" / "wsj-research"
STATE_FILE = STATE_DIR / "browser.json"
LOCK_FILE = STATE_DIR / "browser.lock"

CLAUDE_IN_CHROME = "claude-in-chrome"
APPLESCRIPT = "applescript"
# Claude Code's login lives under the real home, also when a host runs this with
# another HOME (the second Antigravity account uses HOME=~/.agy2).
REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
CLAUDE_BINARY = REAL_HOME / ".local" / "bin" / "claude"
CIC_STATE_FILE = STATE_DIR / "claude-in-chrome.json"
CIC_DROPPED_ENV = frozenset({"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"})
# Activation trailed the new window by up to about 3 seconds (2026-11-24).
FRONT_APP_WATCH_SECONDS = 5
FRONT_APP_SETTLE_SECONDS = 0.5
FRONT_APP_RECHECK_SECONDS = 2
FRONT_APP_HAND_BACKS = 3
CIC_CONNECT_TIMEOUT = 20
# The extension stops page JavaScript after 45 seconds.
CIC_CALL_TIMEOUT = 60
# The extension cuts every returned string at 1,000 characters and a whole
# result at 51,200, so results come back as gzip+base64 parts of 997 characters,
# 45 per call. The "~" keeps a part from matching the extension's base64 filter.
CIC_PART_SIZE = 996
CIC_PARTS_PER_CALL = 45

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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _save_json(path: Path, value: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def _load_state() -> dict[str, Any]:
    return _load_json(STATE_FILE)


def _save_state(target: dict[str, Any]) -> None:
    _save_json(STATE_FILE, target)


def _front_bundle_id() -> str | None:
    """The frontmost app's bundle id, or None when macOS does not say."""
    try:
        front = subprocess.run(["lsappinfo", "front"], text=True, capture_output=True, check=False).stdout.strip()
        info = subprocess.run(["lsappinfo", "info", "-only", "bundleID", front], text=True, capture_output=True,
                              check=False).stdout
    except OSError:
        return None
    match = re.search(r'bundleID="([^"]+)"', info)
    return match.group(1) if match else None


@contextlib.contextmanager
def _returning_front_app() -> Iterator[None]:
    """Give the front back to the user's app after a step that creates a Chrome window.

    Chrome comes to the front whenever a window is created from outside it. This
    was observed for AppleScript `make new window`, `open -na`, and the window
    that holds a new Claude in Chrome tab group. Nothing is done when Chrome was
    already in front.
    """
    before = _front_bundle_id()
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        if before and before != CHROME_BUNDLE_ID:
            # A step that failed most likely created no window, so it gets one
            # look, not a wait.
            _hand_front_back(before, FRONT_APP_WATCH_SECONDS if succeeded else 0)


def _hand_front_back(before: str, watch: float) -> None:
    """Return the front to BEFORE whenever Chrome takes it within WATCH seconds.

    Chrome activates in more than one step: on 2026-11-24 it took the front
    again 0.2 seconds after a first hand-back. So the helper lets Chrome settle
    before each hand-back and keeps watching afterward. It stops once the user
    is in a third app.
    """
    deadline = time.monotonic() + watch
    handed_back = 0
    while handed_back < FRONT_APP_HAND_BACKS:
        front = _front_bundle_id()
        if front == CHROME_BUNDLE_ID:
            time.sleep(FRONT_APP_SETTLE_SECONDS)
            if _front_bundle_id() == CHROME_BUNDLE_ID:
                subprocess.run(["open", "-b", before], capture_output=True, check=False)
                handed_back += 1
                deadline = max(deadline, time.monotonic() + FRONT_APP_RECHECK_SECONDS)
            continue
        if front != before or time.monotonic() >= deadline:
            return
        time.sleep(0.1)


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


def _open_profile_window(profile_directory: str) -> dict[str, Any]:
    """Open the helper's own WSJ window, so a tab the user opened is never navigated.

    `make new window` stays in the one running Chrome. `open -na`, used before
    2026-11-24, can start a second Chrome process for a moment, and AppleScript
    then fails with -609. The new window uses Chrome's most recently used
    profile, so the profile is checked once, in this window.
    """
    with _returning_front_app():
        window_id = int(
            _run_applescript(
                f'''
tell application "{CHROME_APP}"
  set helperWindow to make new window
  set URL of active tab of helperWindow to "{WSJ_HOME}"
  return id of helperWindow
end tell
'''
            )
        )
        found = _window_profile_directory(window_id)
    if found != profile_directory:
        _run_applescript(f'tell application "{CHROME_APP}" to close (first window whose id is {window_id})')
        raise WsjError(
            f"Chrome opened the helper's window in profile {found!r}, not {profile_directory!r} "
            f"({PROFILE_EMAIL}). Use a {PROFILE_EMAIL} Chrome window once so Chrome counts it as "
            "most recently used, then retry.",
            EXIT_BROWSER_TIMEOUT,
        )
    tab_id = int(
        _run_applescript(
            f'tell application "{CHROME_APP}" to return id of active tab of (first window whose id is {window_id})'
        )
    )
    return {
        "window_id": window_id,
        "tab_id": tab_id,
        "profile_email": PROFILE_EMAIL,
        "profile_directory": profile_directory,
        "owned": True,
    }


def _target() -> dict[str, Any]:
    """The helper's own saved tab, or a new window of its own. A saved tab without
    `owned` predates 2026-11-24 and may be a tab the user opened, so it is not reused."""
    profile_directory = _resolve_profile_directory()
    state = _load_state()
    window_id, tab_id = state.get("window_id"), state.get("tab_id")
    if (
        state.get("owned") is True
        and state.get("profile_email") == PROFILE_EMAIL
        and state.get("profile_directory") == profile_directory
        and isinstance(window_id, int)
        and isinstance(tab_id, int)
        and _tab_exists(window_id, tab_id)
    ):
        return state

    print("wsj: opening the helper's own Chrome window for AppleScript.", file=sys.stderr)
    target = _open_profile_window(profile_directory)
    _save_state(target)
    return target


# A WSJ page already in the tab has __NEXT_DATA__ too, so readiness alone can pass on
# the old document and the next read returns the previous page. Mark the old document
# first; only a newly loaded one lacks the mark.
LEAVING_JS = "window.__wsjResearchLeaving = true, 'marked'"
READY_JS = "document.getElementById('__NEXT_DATA__') && !window.__wsjResearchLeaving ? 'ready' : ''"
NAVIGATION_WAIT_SECONDS = 30
SETTLE_SECONDS = 0.65


def _navigate(target: dict[str, Any], url: str) -> None:
    escaped_url = url.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "{CHROME_APP}"
  set targetWindow to first window whose id is {target["window_id"]}
  set targetTab to first tab of targetWindow whose id is {target["tab_id"]}
  try
    execute targetTab javascript "{LEAVING_JS}"
  end try
  set URL of targetTab to "{escaped_url}"
  repeat 120 times
    delay 0.25
    set pageReady to ""
    try
      set pageReady to execute targetTab javascript "{READY_JS}"
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
    time.sleep(SETTLE_SECONDS)


class Tab(Protocol):
    """The one tab a command drives, whichever transport reaches it."""

    transport: str

    def navigate(self, url: str) -> None: ...

    def evaluate(self, source: str) -> str: ...

    def describe(self) -> dict[str, Any]: ...


class AppleScriptTab:
    transport = APPLESCRIPT

    def __init__(self, target: dict[str, Any]):
        self.target = target

    def navigate(self, url: str) -> None:
        _navigate(self.target, url)

    def evaluate(self, source: str) -> str:
        return _execute_js(self.target["window_id"], self.target["tab_id"], source)

    def describe(self) -> dict[str, Any]:
        return {key: self.target[key] for key in ("profile_directory", "window_id", "tab_id")}


class ClaudeInChromeUnavailable(WsjError):
    """Claude in Chrome did not connect, so AppleScript may be used instead."""

    def __init__(self, message: str):
        super().__init__(message, EXIT_BROWSER_TIMEOUT)


class _ToolError(WsjError):
    """A Claude in Chrome tool answered with isError."""


class _McpServer:
    """One `claude --claude-in-chrome-mcp` process, spoken to as newline-delimited JSON-RPC over stdio."""

    def __init__(self) -> None:
        try:
            self._process = subprocess.Popen(
                [str(CLAUDE_BINARY), "--claude-in-chrome-mcp"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                # The bridge signs in with the user's Claude login, so an API key a
                # caller happens to export is never passed on.
                env={**{key: value for key, value in os.environ.items() if key not in CIC_DROPPED_ENV},
                     "HOME": str(REAL_HOME)},
                cwd=REAL_HOME,
            )
        except OSError as exc:
            raise ClaudeInChromeUnavailable(f"cannot start {CLAUDE_BINARY}: {exc}") from exc
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._pump_thread = threading.Thread(target=self._pump, daemon=True)
        self._pump_thread.start()
        self._last_id = 0

    def _pump(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, message: dict[str, Any]) -> None:
        assert self._process.stdin is not None
        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
        except OSError as exc:
            raise WsjError("The Claude in Chrome server exited.", EXIT_BROWSER_TIMEOUT) from exc

    def notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def request(self, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        self._last_id += 1
        request_id = self._last_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        late = WsjError(f"Claude in Chrome did not answer {method} within {timeout:g}s.", EXIT_BROWSER_TIMEOUT)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise late
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                raise late from None
            if line is None:
                raise WsjError("The Claude in Chrome server exited.", EXIT_BROWSER_TIMEOUT)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue  # a notification, or an answer to an earlier, abandoned request
            if "error" in message:
                raise WsjError(f"Claude in Chrome {method} failed: {message['error']}", EXIT_BROWSER_TIMEOUT)
            return message.get("result") or {}

    def tool(self, name: str, arguments: dict[str, Any], *, timeout: float = CIC_CALL_TIMEOUT,
             exit_code: int = EXIT_BROWSER_TIMEOUT) -> str:
        """The tool's answer text. Reminders the server adds for models are skipped."""
        result = self.request("tools/call", {"name": name, "arguments": arguments}, timeout)
        texts = [
            item.get("text", "")
            for item in result.get("content") or []
            if item.get("type") == "text" and not item.get("text", "").startswith("<system-reminder>")
        ]
        text = texts[0] if texts else ""
        if result.get("isError"):
            raise _ToolError(f"Claude in Chrome {name}: {text[:300]}", exit_code)
        return text

    def close(self) -> None:
        with contextlib.suppress(OSError):
            if self._process.stdin:
                self._process.stdin.close()
        try:
            self._process.wait(5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._pump_thread.join(5)
        if self._process.stdout and not self._pump_thread.is_alive():
            self._process.stdout.close()


# Runs SOURCE (an expression that yields a string), keeps the gzip+base64 of the
# result on `window`, and returns its first parts. __wsjResearchSlice(start)
# returns later parts. The extension returns an object as JSON, but a top-level
# array only as "Array(n)", and a promise unless awaited.
CIC_RESULT_JS = r'''await (async () => {
  const value = String(__SOURCE__);
  const stream = new Blob([value]).stream().pipeThrough(new CompressionStream("gzip"));
  const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  window.__wsjResearchResult = btoa(binary);
  window.__wsjResearchSlice = start => {
    const result = window.__wsjResearchResult, parts = [];
    for (let i = start; i < result.length && parts.length < __PARTS__; i += __SIZE__) {
      parts.push("~" + result.slice(i, i + __SIZE__));
    }
    return {total: result.length, parts};
  };
  return window.__wsjResearchSlice(0);
})()'''


def _cic_parts(page: Any) -> tuple[int, str]:
    """(total length, base64 text) from one CIC_RESULT_JS answer, refusing anything the extension rewrote."""
    if not isinstance(page, dict) or not isinstance(page.get("total"), int) or not isinstance(page.get("parts"), list):
        raise WsjError(f"Claude in Chrome returned an unexpected result: {str(page)[:200]}", EXIT_BROWSER_TIMEOUT)
    for part in page["parts"]:
        if not isinstance(part, str) or not part.startswith("~"):
            raise WsjError(f"Claude in Chrome altered a result part: {str(part)[:80]}", EXIT_BROWSER_TIMEOUT)
    return page["total"], "".join(part[1:] for part in page["parts"])


def _cic_decode(total: int, encoded: str) -> str:
    """The page's string from its gzip+base64 text. gzip's checksum catches a part the extension redacted."""
    try:
        if len(encoded) != total:
            raise ValueError(f"{len(encoded)} of {total} characters arrived")
        return gzip.decompress(base64.b64decode(encoded, validate=True)).decode("utf-8")
    except (ValueError, OSError, EOFError) as exc:
        raise WsjError(f"Claude in Chrome returned a damaged result ({exc}).", EXIT_BROWSER_TIMEOUT) from exc


def _cic_tab_ids(text: str) -> list[int]:
    """Tab ids in the shared tab group, from tabs_context_mcp's JSON; empty when it reports no group."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    tabs = data.get("availableTabs") if isinstance(data, dict) else None
    if not isinstance(tabs, list):
        return []
    return [tab["tabId"] for tab in tabs if isinstance(tab, dict) and isinstance(tab.get("tabId"), int)]


class ClaudeInChromeTab:
    """The helper's own tab in the one tab group that standalone Claude in Chrome servers share.

    The group's first tab, the one `tabs_context_mcp` creates with the group,
    anchors it: when that tab closes, the extension drops the group, and the
    group's other tabs stay open in Chrome where no tool can reach them (seen
    2026-11-24). So the helper keeps the tab it gets by creating the group, saved
    in CIC_STATE_FILE, and reuses it on later runs. That also keeps the group's
    window, and creating that window is the one step that brings Chrome to the
    front. In a group someone else created, the helper adds a tab for the run and
    closes it at the end. It never uses or closes a tab it did not create.
    """

    transport = CLAUDE_IN_CHROME

    def __init__(self, server: _McpServer, tab_id: int, keep: bool):
        self._server = server
        self.tab_id = tab_id
        self._keep = keep

    @classmethod
    def open(cls) -> "ClaudeInChromeTab":
        """Connect and claim the tab, retrying once on a fresh server."""
        reasons: list[str] = []
        for _ in range(2):
            server: _McpServer | None = None
            try:
                server = _McpServer()
                server.request(
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "wsj-research", "version": "1"},
                    },
                    CIC_CONNECT_TIMEOUT,
                )
                server.notify("notifications/initialized")
                return cls(server, *_claim_cic_tab(server))
            except WsjError as exc:
                if server is not None:
                    server.close()
                reasons.append(str(exc))
        raise ClaudeInChromeUnavailable(" Retried: ".join(reasons))

    def _js(self, text: str) -> str:
        return self._server.tool(
            "javascript_tool", {"action": "javascript_exec", "tabId": self.tab_id, "text": text}, exit_code=1
        )

    def _js_object(self, text: str) -> Any:
        raw = self._js(text)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise WsjError(f"Claude in Chrome returned an unexpected result: {raw[:200]}", EXIT_BROWSER_TIMEOUT)

    def evaluate(self, source: str) -> str:
        text = (CIC_RESULT_JS.replace("__PARTS__", str(CIC_PARTS_PER_CALL))
                .replace("__SIZE__", str(CIC_PART_SIZE)).replace("__SOURCE__", source.strip()))
        total, encoded = _cic_parts(self._js_object(text))
        while len(encoded) < total:
            _, more = _cic_parts(self._js_object(f"window.__wsjResearchSlice({len(encoded)})"))
            if not more:
                break
            encoded += more
        return _cic_decode(total, encoded)

    def navigate(self, url: str) -> None:
        with contextlib.suppress(WsjError):
            self.evaluate(LEAVING_JS)  # fails on a tab that shows no web page yet
        self._server.tool("navigate", {"tabId": self.tab_id, "url": url})
        deadline = time.monotonic() + NAVIGATION_WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                if self.evaluate(READY_JS) == "ready":
                    time.sleep(SETTLE_SECONDS)
                    return
            except WsjError:
                pass  # the page navigated mid-evaluation
            time.sleep(0.25)
        raise WsjError("WSJ navigation did not complete.", EXIT_BROWSER_TIMEOUT)

    def describe(self) -> dict[str, Any]:
        return {"tab_id": self.tab_id}

    def close(self) -> None:
        try:
            if not self._keep:
                with contextlib.suppress(WsjError):
                    self._server.tool("tabs_close_mcp", {"tabId": self.tab_id}, timeout=CIC_CONNECT_TIMEOUT)
        finally:
            self._server.close()


def _claim_cic_tab(server: _McpServer) -> tuple[int, bool]:
    """(tab id, keep it after the run).

    The saved anchor tab when it is still in the group; else a tab added for this
    run; else the anchor tab of a new group (one window, Chrome raised once).
    """
    saved = _load_json(CIC_STATE_FILE).get("tab_id")
    try:
        tabs = _cic_tab_ids(server.tool("tabs_context_mcp", {}, timeout=CIC_CONNECT_TIMEOUT))
    except _ToolError:
        tabs = []  # no group yet; creating one below says whether the browser is connected
    if tabs and saved in tabs:
        return saved, True
    if tabs:
        text = server.tool("tabs_create_mcp", {}, timeout=CIC_CONNECT_TIMEOUT)
        match = re.search(r"Tab ID: (\d+)", text)
        if not match:
            raise WsjError(f"Claude in Chrome did not report the new tab: {text[:200]}", EXIT_BROWSER_TIMEOUT)
        return int(match.group(1)), False
    with _returning_front_app():
        tabs = _cic_tab_ids(server.tool("tabs_context_mcp", {"createIfEmpty": True}, timeout=CIC_CONNECT_TIMEOUT))
    if not tabs:
        raise WsjError("Claude in Chrome did not create a tab group.", EXIT_BROWSER_TIMEOUT)
    _save_json(CIC_STATE_FILE, {"tab_id": tabs[0]})
    print("wsj: created the Claude in Chrome tab group; its new window brought Chrome to the front once.",
          file=sys.stderr)
    return tabs[0], True


@contextlib.contextmanager
def _connect(transport: str) -> Iterator[Tab]:
    """The tab commands drive. `auto` uses AppleScript only when Claude in Chrome does not connect."""
    if transport != APPLESCRIPT:
        try:
            tab = ClaudeInChromeTab.open()
        except ClaudeInChromeUnavailable as exc:
            if transport == CLAUDE_IN_CHROME:
                raise
            print(f"wsj: Claude in Chrome is unavailable ({exc}); using the AppleScript fallback.", file=sys.stderr)
        else:
            try:
                yield tab
            finally:
                tab.close()
            return
    yield AppleScriptTab(_target())


def _execute_json(tab: Tab, source: str) -> Any:
    raw = tab.evaluate(source)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WsjError(f"WSJ returned malformed structured data: {exc}") from exc


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


def _require_login(tab: Tab) -> dict[str, Any]:
    status: dict[str, Any] = {}
    for _ in range(30):
        status = _execute_json(tab, AUTH_JS)
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


def command_status(args: argparse.Namespace) -> None:
    with _connect(args.transport) as tab:
        tab.navigate(WSJ_HOME)
        auth = _require_login(tab)
    _print_json(
        {
            "authenticated": True,
            "transport": tab.transport,
            "profile_email": PROFILE_EMAIL,
            **tab.describe(),
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
    with _connect(args.transport) as tab:
        tab.navigate(WSJ_HOME)
        _require_login(tab)
        data = _execute_json(tab, FRONTPAGE_JS)
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
    data["transport"] = tab.transport
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
    with _connect(args.transport) as tab:
        tab.navigate(LATEST_URL)
        _require_login(tab)
        data = _execute_json(tab, LATEST_JS)
    stories = [
        story
        for story in map(classify_story, data["stories"])
        if not (args.exclude_opinion and story["is_opinion"])
        and not (args.exclude_video and story["is_video"])
    ][: args.max]
    data["stories"] = stories
    data["count"] = len(stories)
    data["profile_email"] = PROFILE_EMAIL
    data["transport"] = tab.transport
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

    all_results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    pages_fetched = 0
    first_metadata: dict[str, Any] = {}
    last_page_full = False
    stopped_at_boundary = False

    with _connect(args.transport) as tab:
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
            tab.navigate(url)
            _require_login(tab)
            page = _execute_json(tab, SEARCH_JS)
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
        "transport": tab.transport,
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
    with _connect(args.transport) as tab:
        tab.navigate(args.url)
        _require_login(tab)
        article = _execute_json(tab, ARTICLE_JS)
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
    article["transport"] = tab.transport
    _print_json(article)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Research WSJ through the authenticated Chrome profile named by CHROME_PROFILE_EMAIL."
    )
    parser.add_argument(
        "--transport",
        choices=["auto", CLAUDE_IN_CHROME, APPLESCRIPT],
        default="auto",
        help="auto (default): Claude in Chrome, and AppleScript only when it does not connect after one retry.",
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
