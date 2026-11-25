"""
chatgpt_lib: Drive chatgpt.com via the user's logged-in Chrome on macOS.

Capabilities:
- Own a dedicated Chrome window pinned to the chatgpt-logged-in profile
  (CHROME_PROFILE_EMAIL); every tab the skill creates or reads lives there.
- Open a fresh chat OR continue a specific conversation by id.
- Attach 1..10 files to the next message via DataTransfer.
- Switch the model picker to "Pro".
- Type a prompt and send.
- Poll the conversation API until the assistant message is complete and return it.

Mechanism: AppleScript -> Google Chrome -> execute javascript in the chatgpt.com
tab. Requires the user has enabled View > Developer > Allow JavaScript from
Apple Events in Chrome.

See docs/chatgpt_internal_api_guide.md for protocol reverse-engineering details.
"""

from __future__ import annotations

import base64
import contextlib
import fcntl
import json
import mimetypes
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Errors


class ChatGPTError(Exception):
    """Base class for tool-specific errors."""


class NotLoggedInError(ChatGPTError):
    """The Chrome session has no active chatgpt.com auth."""


class JSExecBlockedError(ChatGPTError):
    """Chrome's 'Allow JavaScript from Apple Events' setting is off."""


class ChatGPTTimeoutError(ChatGPTError):
    """An operation took too long."""


class ChatGPTReadThrottledError(ChatGPTTimeoutError):
    """ChatGPT refused a conversation read with a temporary throttle."""


# --------------------------------------------------------------------------- #
# AppleScript / JS bridge


CHATGPT_HOSTS = ("chatgpt.com", "chat.openai.com")
READ_THROTTLE_WAITS = (20.0, 60.0, 180.0)


def _applescript_escape(text: str) -> str:
    """Escape a string for embedding inside an AppleScript "..." literal."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def _osascript(applescript: str, *, timeout: float = 30.0) -> str:
    """Run an AppleScript and return its stdout (trimmed). Raises ChatGPTError on
    failure, INCLUDING a hang past `timeout`: an unresponsive Chrome tab must
    surface as a retryable ChatGPTError, not an uncaught subprocess.TimeoutExpired
    (which crashed every run for a day when a frozen background tab hung the
    bridge)."""
    try:
        proc = subprocess.run(
            ["osascript"],
            input=applescript,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ChatGPTError(
            f"osascript hung past {timeout:.0f}s (the targeted Chrome tab is busy or unresponsive)"
        )
    if proc.returncode != 0:
        err = proc.stderr.strip()
        if "Allow JavaScript from Apple Events" in err:
            raise JSExecBlockedError(
                "Chrome's 'View > Developer > Allow JavaScript from Apple Events' "
                "must be enabled. Toggle it once, then retry."
            )
        raise ChatGPTError(f"osascript failed: {err}")
    return proc.stdout.rstrip("\n")


def _run_js(js_code: str, *, timeout: float = 30.0) -> str:
    """
    Execute synchronous JS in the active tab of the FRONT window. Last-resort
    only (used by `_front_conversation_id` for the human-CLI bare continue);
    everything else addresses a specific tab via `_run_js_in_tab`.
    """
    script = (
        'tell application "Google Chrome" to return execute '
        '(active tab of front window) javascript "' + _applescript_escape(js_code) + '"'
    )
    return _osascript(script, timeout=timeout)


def _js(target: tuple[int, int] | None, js_code: str, *, timeout: float = 30.0) -> str:
    """Run synchronous JS either in a SPECIFIC tab (window_id, tab_index) — the
    drift-proof path used for every write now — or, when target is None, in the
    front window (legacy fallback). `_run_js_in_tab` is defined further down; it
    resolves at call time, so the forward reference is fine."""
    if target is None:
        return _run_js(js_code, timeout=timeout)
    return _run_js_in_tab(target[0], target[1], js_code, timeout=timeout)


def _run_js_async(
    js_promise_expr: str,
    *,
    target: tuple[int, int] | None = None,
    timeout: float = 60.0,
    poll_interval: float = 0.3,
) -> Any:
    """
    Run an async JS expression (must evaluate to a Promise) and wait for the
    result. Stashes result on `window.__cgpt_async_result` and polls for it.

    When `target` is given the kickoff AND the poll both run in that exact tab,
    so the stash variable and its reader are the same JS context — no
    front-window drift between the kickoff and the read.

    Returns the resolved JSON-decoded value.
    """
    sentinel = "__cgpt_async_result_" + uuid.uuid4().hex[:8]
    wrapper = (
        f"window.{sentinel} = null; "
        "(async () => { "
        "  try { "
        f"    const v = await ({js_promise_expr}); "
        f"    window.{sentinel} = JSON.stringify({{ok: true, value: v}}); "
        "  } catch(e) { "
        f"    window.{sentinel} = JSON.stringify({{ok: false, err: String(e), "
        "stack: (e && e.stack) || null}); "
        "  } "
        "})(); 'kicked';"
    )
    _js(target, wrapper)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        raw = _js(target, f"window.{sentinel} || ''")
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if payload.get("ok"):
            return payload["value"]
        raise ChatGPTError(f"JS error: {payload.get('err')}")
    raise ChatGPTTimeoutError(
        f"Async JS did not complete within {timeout}s: {js_promise_expr[:120]}..."
    )


# --------------------------------------------------------------------------- #
# Drift-proof primitives (multi-window safe)
#
# The user routinely has many Chrome windows open with dozens of chatgpt.com
# tabs. "active tab of front window" drifts between osascript calls, so reading
# the conversation from the front-window URL is unreliable — you can end up
# polling a DIFFERENT conversation than the one you sent. The robust pattern,
# used below, is: (1) tolerate tabs/windows closing mid-scan, (2) read a
# conversation BY ID via a single synchronous XHR (one execute-javascript call,
# no async stash/poll, no cross-call drift — see docs §11.10), and (3) pin the
# conversation id we created and always fetch THAT id, never "whatever is front".

# Runtime state lives outside the skill: an installed skill is a hash-tracked copy, and a file written
# into it reads as a local edit that blocks the skill's next refresh.
_STATE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "gpt-skill"
_STATE_PATH = _STATE_DIR / "last_session.json"


def _save_session(conversation_id: str) -> None:
    """Record the last conversation id so an interrupted run can be recovered."""
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps({"conversation_id": conversation_id, "ts": time.time()}))
    except OSError:
        pass  # best-effort; never fail a run over state bookkeeping


def load_last_conversation_id() -> str | None:
    try:
        return json.loads(_STATE_PATH.read_text()).get("conversation_id") or None
    except (OSError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- #
# The dedicated, profile-pinned Chrome window
#
# Chrome's AppleScript dictionary has no notion of profiles: `windows` spans ALL
# profiles, and `front window` is whatever profile the user touched last. The
# user runs several profiles and only one (CHROME_PROFILE_EMAIL's) is logged in
# to chatgpt.com — so "front window" / "first chatgpt tab anywhere" could land
# in a logged-out profile or in a frozen background tab someone else owns.
#
# Instead the skill owns ONE window: opened via `open -na "Google Chrome"
# --args --profile-directory=<dir>`, which Chrome honors even when already
# running (the singleton forwards the command line), so the window is
# DETERMINISTICALLY in the right profile. Its id is persisted and reused; every
# tab the skill creates or reads lives in this window.

CHROME_PROFILE_EMAIL = os.environ.get("CHROME_PROFILE_EMAIL")
_CHROME_LOCAL_STATE = (
    Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Local State"
)
_WINDOW_STATE_PATH = _STATE_DIR / "dedicated_window.json"


def _chrome_profile_directory() -> str:
    """Profile directory (e.g. 'Default') whose primary Google account is
    CHROME_PROFILE_EMAIL, resolved from Chrome's Local State. Raises loudly when
    no profile matches — the skill must never guess a profile."""
    if not CHROME_PROFILE_EMAIL:
        raise ChatGPTError(
            "CHROME_PROFILE_EMAIL is not set. Export the email of the Chrome profile "
            "that is logged in to chatgpt.com, in ~/.config/agent-system/shell.local.sh."
        )
    try:
        cache = json.loads(_CHROME_LOCAL_STATE.read_text())["profile"]["info_cache"]
    except (OSError, KeyError, json.JSONDecodeError) as e:
        raise ChatGPTError(
            f"Could not resolve the {CHROME_PROFILE_EMAIL} Chrome profile from "
            f"{_CHROME_LOCAL_STATE}: {e}"
        )
    for dirname, meta in cache.items():
        if meta.get("user_name") == CHROME_PROFILE_EMAIL:
            return dirname
    raise ChatGPTError(
        f"No Chrome profile is signed in as {CHROME_PROFILE_EMAIL} "
        f"(profiles: {sorted(cache)}). Set CHROME_PROFILE_EMAIL if the "
        "chatgpt-logged-in profile changed."
    )


def _window_ids() -> list[int]:
    try:
        raw = _osascript('tell application "Google Chrome" to return id of every window')
    except ChatGPTError:
        return []
    return [w for w in (_as_int(t) for t in raw.split(",")) if w is not None]


def _find_tab_in_window(window_id: int, url_substr: str) -> tuple[int, int] | None:
    """(window_id, tab_index) of the first responsive tab in THIS window whose URL
    contains `url_substr`; None if absent or the window is gone."""
    script = (
        'tell application "Google Chrome"\n'
        "  try\n"
        f"    set us to URL of every tab of window id {window_id}\n"
        "    set i to 0\n"
        "    repeat with u in us\n"
        "      set i to i + 1\n"
        f'      if (u as string) contains "{_applescript_escape(url_substr)}" then\n'
        "        try\n"
        "          with timeout of 1 second\n"
        f'            execute (tab i of window id {window_id}) javascript "1"\n'
        "            return (i as string)\n"
        "          end timeout\n"
        "        end try\n"
        "      end if\n"
        "    end repeat\n"
        "  end try\n"
        "end tell\n"
        'return "0"'
    )
    try:
        idx = _as_int(_osascript(script).strip())
    except ChatGPTError:
        return None
    return (window_id, idx) if idx else None


def _open_profile_window(url: str = "https://chatgpt.com/", *, ready_timeout: float = 25.0) -> int:
    """Open a NEW Chrome window pinned to the CHROME_PROFILE_EMAIL profile at
    `url` and return its window id, identified by diffing window ids (never
    'front window'). This is the one operation that necessarily fronts Chrome."""
    profile_dir = _chrome_profile_directory()
    before = set(_window_ids())
    subprocess.run(
        [
            "open",
            "-na",
            "Google Chrome",
            "--args",
            f"--profile-directory={profile_dir}",
            "--new-window",
            url,
        ],
        check=False,
    )
    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        time.sleep(0.5)
        for wid in _window_ids():
            if wid not in before and _find_tab_in_window(wid, "chatgpt.com") is not None:
                return wid
    raise ChatGPTError(
        f"Opened a '{profile_dir}' profile window at {url} but it never appeared "
        "in Chrome's window list."
    )


def _load_dedicated_window_id() -> int | None:
    try:
        wid = json.loads(_WINDOW_STATE_PATH.read_text()).get("window_id")
    except (OSError, json.JSONDecodeError):
        return None
    return wid if isinstance(wid, int) else None


def _save_dedicated_window_id(window_id: int) -> None:
    try:
        _WINDOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _WINDOW_STATE_PATH.write_text(
            json.dumps(
                {
                    "window_id": window_id,
                    "profile_email": CHROME_PROFILE_EMAIL,
                    "ts": time.time(),
                }
            )
        )
    except OSError:
        pass  # best-effort; never fail a run over state bookkeeping


def dedicated_window() -> int:
    """Window id of the skill's own profile-pinned Chrome window. Reuses the saved
    one while it still exists and still holds a chatgpt tab (window ids reset on
    Chrome restart, and a recycled id without a chatgpt tab is rejected here;
    sends are additionally verified by conversation id). Opens a fresh
    profile-pinned window otherwise."""
    wid = _load_dedicated_window_id()
    if wid is not None and _find_tab_in_window(wid, "chatgpt.com") is not None:
        return wid
    for open_wid in _window_ids():
        if _find_tab_in_window(open_wid, "chatgpt.com") is not None:
            _save_dedicated_window_id(open_wid)
            return open_wid
    wid = _open_profile_window("https://chatgpt.com/")
    _save_dedicated_window_id(wid)
    return wid


def _new_tab_in_dedicated_window(url: str) -> tuple[int, int] | None:
    """Create a new tab at the end of the dedicated window. Returns (window_id,
    tab_index) or None on failure (caller falls back to reusing a tab there)."""
    wid = dedicated_window()
    script = (
        'tell application "Google Chrome"\n'
        "  try\n"
        f"    make new tab at end of tabs of window id {wid} with properties "
        f'{{URL:"{_applescript_escape(url)}"}}\n'
        f"    return count of tabs of window id {wid}\n"
        "  on error errMsg\n"
        '    return "err:" & errMsg\n'
        "  end try\n"
        "end tell"
    )
    try:
        out = _osascript(script).strip()
    except ChatGPTError:
        return None
    idx = _as_int(out)
    if idx is None or idx <= 0:
        return None
    return (wid, idx)


# --------------------------------------------------------------------------- #
# Send serialization
#
# Two concurrent invocations that both type into a composer and then try to
# identify "their" new conversation can cross-talk. We now bind every send to an
# explicit conversation id, which removes most of that risk, but the brief
# critical section (resolve tab -> select model -> type -> send -> capture/verify)
# is still cheap to serialize. The long wait_for_response runs OUTSIDE the lock
# (it is a pure by-id read), so a quick follow-up never blocks for a 20-minute
# Pro run.

_LOCK_PATH = _STATE_DIR / "send.lock"


@contextlib.contextmanager
def _send_lock(*, timeout: float = 600.0, poll: float = 0.5):
    """Serialize the send+capture critical section across processes. Yields True
    if the lock was acquired, False if it timed out (in which case we proceed
    anyway — a wedged lock must never permanently disable the tool).

    The default timeout must EXCEED the worst-case time a holder spends in the
    section: attach_files alone can wait ~90s for upload chips, and with
    get_session + select + send + verify a file-attached send can hold the lock a
    few minutes. A timeout shorter than that would make a contending run fall
    through and race exactly when contention is real, defeating the purpose. A
    small per-process jitter keeps two simultaneous waiters from giving up in
    lockstep. (os.close() releases the advisory lock implicitly; the explicit
    LOCK_UN is belt-and-suspenders, and flock auto-releases if a holder dies.)"""
    fd = None
    acquired = False
    jitter = (os.getpid() % 13) / 100.0
    try:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(_LOCK_PATH), os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                time.sleep(poll + jitter)
        yield acquired
    finally:
        if fd is not None:
            if acquired:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(fd)


def _as_int(s: str) -> int | None:
    """Parse an AppleScript-rendered integer token, defensively. Returns None for
    anything non-numeric (e.g. a window id that coerced to scientific notation, or
    a stray token from a closing tab) so a malformed value degrades to 'skip this
    window' instead of crashing the caller with an uncaught ValueError."""
    s = (s or "").strip()
    return int(s) if s.isdigit() else None


def _find_tab_by_url_contains(substr: str) -> tuple[int, int] | None:
    """(window_id, tab_index) of the first tab whose URL CONTAINS `substr`, without
    activating it. Tolerant of windows/tabs closing mid-scan. Used to locate the
    tab already showing a specific conversation (/c/<id>) so a follow-up types
    into the RIGHT thread rather than 'whatever is front'."""
    if not substr:
        return None  # AppleScript `x contains ""` is False; avoid surprises.
    try:
        raw = _osascript('tell application "Google Chrome" to return id of every window')
    except ChatGPTError:
        return None
    needle = _applescript_escape(substr)
    for wid_s in [w.strip() for w in raw.split(",") if w.strip()]:
        wid = _as_int(wid_s)
        if wid is None:
            continue
        script = (
            'tell application "Google Chrome"\n'
            "  try\n"
            f"    set us to URL of every tab of window id {wid}\n"
            "    set i to 0\n"
            "    repeat with u in us\n"
            "      set i to i + 1\n"
            f'      if (u as string) contains "{needle}" then\n'
            "        try\n"
            "          with timeout of 1 second\n"
            f'            execute (tab i of window id {wid}) javascript "1"\n'
            "            return (i as string)\n"
            "          end timeout\n"
            "        end try\n"
            "      end if\n"
            "    end repeat\n"
            "  end try\n"
            "end tell\n"
            'return "0"'
        )
        try:
            out = _osascript(script).strip()
        except ChatGPTError:
            continue
        idx = _as_int(out)
        if idx is not None and idx > 0:
            return (wid, idx)
    return None


def _activate_tab(window_id: int, tab_index: int) -> None:
    """Bring exactly THIS tab to the front (window forward + active tab). Unlike the
    old 'activate first chatgpt tab found', this fronts the CORRECT tab — the one
    bound to the conversation we are about to drive. Activating does not reorder
    tabs, so (window_id, tab_index) stays valid afterward."""
    script = (
        'tell application "Google Chrome"\n'
        "  try\n"
        f"    set active tab index of window id {window_id} to {tab_index}\n"
        f"    set index of window id {window_id} to 1\n"
        "    activate\n"
        "  end try\n"
        "end tell"
    )
    _osascript(script)


def _navigate_tab(target: tuple[int, int], url: str) -> None:
    """Point a specific tab at `url` via AppleScript (reliable for background
    tabs, unlike setting location.href through execute-javascript)."""
    script = (
        'tell application "Google Chrome"\n'
        "  try\n"
        f'    set URL of tab {target[1]} of window id {target[0]} to "{_applescript_escape(url)}"\n'
        "  end try\n"
        "end tell"
    )
    _osascript(script)


def _wait_tab_ready(
    target: tuple[int, int],
    *,
    cid_substr: str | None = None,
    require_no_cid: bool = False,
    ready_timeout: float = 20.0,
) -> bool:
    """Wait until a specific tab has the composer textarea loaded, optionally also
    requiring it to be on a given conversation path (`cid_substr`) or, for a fresh
    chat, NOT on any `/c/<id>` path (`require_no_cid`). Returns True when ready.

    `require_no_cid` matters when a new chat had to reuse an existing tab: it makes
    readiness wait until the prior `/c/<old>` page is actually gone, so the send
    can't land in the stale thread (and a drifted tab index that still shows a
    conversation won't be mistaken for the fresh chat).

    Readiness gates on `#prompt-textarea` only — NOT the model pill — so a
    bundle/selector change to `button.__composer-pill` can't masquerade as 'page
    didn't load'; select_pro raises its own specific error if the pill is
    truly absent."""
    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        time.sleep(0.4)
        try:
            info = json.loads(
                _run_js_in_tab(
                    target[0],
                    target[1],
                    "JSON.stringify({"
                    "ready: !!document.querySelector('#prompt-textarea'), "
                    "path: location.pathname})",
                    timeout=10.0,
                )
            )
        except (ChatGPTError, json.JSONDecodeError):
            continue
        if not info.get("ready"):
            continue
        path = info.get("path") or ""
        if cid_substr and cid_substr not in path:
            continue
        if require_no_cid and "/c/" in path:
            continue
        return True
    return False


def _run_js_in_tab(window_id: int, tab_index: int, js_code: str, *, timeout: float = 45.0) -> str:
    """Execute JS in a SPECIFIC Chrome tab (addressed by window id + index) without
    bringing it to the front — so polling a long Pro run doesn't steal focus."""
    script = (
        'tell application "Google Chrome" to return execute '
        f'(tab {tab_index} of window id {window_id}) javascript "'
        + _applescript_escape(js_code)
        + '"'
    )
    return _osascript(script, timeout=timeout)


def _sync_xhr_js(path: str) -> str:
    """JS that does a synchronous same-origin XHR GET (auth via session token) and
    returns responseText. One call, no async stash/poll → no front-window drift."""
    return (
        "(function(){try{"
        "var s=new XMLHttpRequest();s.open('GET','/api/auth/session',false);s.send(null);"
        "var tok=JSON.parse(s.responseText).accessToken;"
        f"var x=new XMLHttpRequest();x.open('GET',{json.dumps(path)},false);"
        "x.setRequestHeader('Authorization','Bearer '+tok);x.send(null);"
        "return x.responseText;"
        "}catch(e){return JSON.stringify({__xhr_err:String(e)});}})()"
    )


def _sync_xhr_get(
    path: str, *, target: tuple[int, int] | None = None, timeout: float = 45.0
) -> str:
    """Sync XHR GET from a chatgpt tab WITHOUT stealing focus. Runs in `target`
    (the tab the caller owns) when given, falling back to a tab of the dedicated
    profile window — NEVER an arbitrary user tab: a frozen background tab hangs
    the synchronous XHR and with it the whole osascript bridge, which is exactly
    the failure that bricked every run when reads scanned all windows."""
    candidates = []
    if target is not None:
        candidates.append(target)
    wid = _load_dedicated_window_id()
    if wid is not None:
        tab = _find_tab_in_window(wid, "chatgpt.com")
        if tab is not None and tab not in candidates:
            candidates.append(tab)
    last_err: ChatGPTError | None = None
    for tab in candidates:
        try:
            return _run_js_in_tab(tab[0], tab[1], _sync_xhr_js(path), timeout=timeout)
        except ChatGPTError as e:
            last_err = e
    raise last_err or ChatGPTError(
        "No chatgpt tab available for a by-id read (no target given and the "
        "dedicated window is missing)."
    )


def _looks_read_throttled(payload: Any) -> bool:
    if isinstance(payload, dict):
        if "mapping" in payload:
            return False
        detail = payload.get("detail")
        if detail is not None:
            payload = detail
    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload, sort_keys=True)
        except TypeError:
            text = str(payload)
    lowered = text.lower()
    return "too many requests" in lowered or "rate limit" in lowered or "rate_limit" in lowered


def _read_throttle_error(conversation_id: str, last_err: str) -> ChatGPTReadThrottledError:
    return ChatGPTReadThrottledError(
        f"ChatGPT read-side throttle while fetching conversation {conversation_id}: "
        f"{last_err}. No prompt was sent. Wait several minutes, then retry the "
        "same --fetch <conversation_id> --json command; do not send a follow-up "
        "asking GPT to continue or expand."
    )


def fetch_conversation(
    conversation_id: str,
    *,
    retries: int = 6,
    retry_wait: float = 2.0,
    target: tuple[int, int] | None = None,
    read_throttle_waits: Iterable[float] | None = READ_THROTTLE_WAITS,
    on_read_throttle=None,
) -> dict:
    """Drift-proof read of a conversation BY ID, from `target` (the tab the
    caller owns) or a dedicated-window tab — no focus steal, and immune to the
    many-windows front-tab drift."""
    last_err = ""
    throttle_waits = tuple(read_throttle_waits or ())
    throttle_hits = 0

    def backoff_read_throttle() -> bool:
        nonlocal throttle_hits
        if throttle_hits >= len(throttle_waits):
            return False
        wait = throttle_waits[throttle_hits]
        throttle_hits += 1
        if on_read_throttle is not None:
            on_read_throttle(wait)
        time.sleep(wait)
        return True

    for _ in range(retries):
        try:
            raw = _sync_xhr_get(f"/backend-api/conversation/{conversation_id}", target=target)
            try:
                convo = json.loads(raw)
            except json.JSONDecodeError:
                if _looks_read_throttled(raw):
                    last_err = "Too many requests"
                    if backoff_read_throttle():
                        continue
                    raise _read_throttle_error(conversation_id, last_err)
                last_err = "unparseable response"
                time.sleep(retry_wait)
                continue

            if isinstance(convo, dict) and "mapping" in convo:
                return convo

            if _looks_read_throttled(convo):
                last_err = "Too many requests"
                if backoff_read_throttle():
                    continue
                raise _read_throttle_error(conversation_id, last_err)
        except ChatGPTReadThrottledError:
            raise
        except ChatGPTError as e:
            last_err = str(e)
            if _looks_read_throttled(last_err):
                if backoff_read_throttle():
                    continue
                raise _read_throttle_error(conversation_id, last_err)
            time.sleep(retry_wait)
            continue
        if isinstance(convo, dict) and "__xhr_err" in convo:
            last_err = f"xhr: {convo['__xhr_err']}"
        else:
            last_err = f"no mapping in response: {str(convo)[:80]}"
        time.sleep(retry_wait)
    if _looks_read_throttled(last_err):
        raise _read_throttle_error(conversation_id, last_err)
    raise ChatGPTError(f"Could not fetch conversation {conversation_id}: {last_err}")


def _conversation_index_throttle_error() -> ChatGPTReadThrottledError:
    return ChatGPTReadThrottledError(
        "ChatGPT read-side throttle while listing conversations. No prompt was "
        "sent; wait several minutes, then retry the same list command."
    )


def fetch_conversations_page(
    offset: int,
    limit: int,
    *,
    archived: bool,
    target: tuple[int, int] | None = None,
) -> dict:
    """Fetch one updated-descending conversation-index page from one archive scope.

    The website embeds full conversation mappings in these index items, so callers
    are deliberately limited to small pages. Pagination and filtering belong in a
    deterministic caller; this function is only the authenticated browser edge.
    """
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
        or limit > 20
    ):
        raise ValueError("limit must be an integer from 1 through 20")
    if not isinstance(archived, bool):
        raise ValueError("archived must be a boolean")

    archived_value = "true" if archived else "false"
    path = (
        f"/backend-api/conversations?offset={offset}&limit={limit}"
        f"&order=updated&is_archived={archived_value}"
    )
    try:
        raw = _sync_xhr_get(path, target=target)
    except ChatGPTError as error:
        if _looks_read_throttled(str(error)):
            raise _conversation_index_throttle_error() from error
        raise
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        if _looks_read_throttled(raw):
            raise _conversation_index_throttle_error() from error
        raise ChatGPTError(
            "ChatGPT returned an unparseable conversation page"
        ) from error
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        if any(not isinstance(item, dict) for item in data["items"]):
            raise ChatGPTError("ChatGPT returned a malformed conversation page item")
        return data
    if _looks_read_throttled(data):
        raise _conversation_index_throttle_error()
    raise ChatGPTError("ChatGPT returned a malformed conversation page")


def recent_conversation_ids(limit: int = 12, *, target: tuple[int, int] | None = None) -> list[str]:
    """Most-recently-updated conversation ids (drift-proof, no focus steal). Used to
    detect the NEW conversation a send created without trusting the front-window URL."""
    try:
        raw = _sync_xhr_get(
            f"/backend-api/conversations?offset=0&limit={limit}&order=updated",
            target=target,
        )
        data = json.loads(raw)
    except (ChatGPTError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    return [it.get("id") for it in data.get("items", []) if it.get("id")]


# --------------------------------------------------------------------------- #
# Identifying / verifying OUR send by user-message text
#
# Matching the conversation by the text of the user message we just sent is both
# drift-proof and concurrency-proof: it pins OUR message specifically, not
# "whatever conversation is newest". We exclude pre-existing user messages by id
# (no wall-clock comparison, so it is immune to client/server clock skew).


def _norm(s: str) -> str:
    """Whitespace-collapsed text for tolerant comparison."""
    return " ".join((s or "").split())


def _user_text_messages(convo: dict) -> list[dict]:
    """All genuine user messages carrying typed text (oldest-first).

    Accepts both `text` and `multimodal_text` content — a message sent WITH file
    attachments is stored as `multimodal_text` (parts = [<asset pointers>…, "the
    typed prompt"]), which is exactly chatgpt_ask.py's headline `--files` case, so
    excluding it would make every file-attached send invisible to the match layer.
    The `is_user_system_message` filter (the injected user_editable_context custom
    instructions, also author.role == 'user') is the load-bearing guard once
    multimodal_text is accepted — keep it."""
    out = []
    for node in (convo or {}).get("mapping", {}).values():
        m = (node or {}).get("message")
        if not m or (m.get("author") or {}).get("role") != "user":
            continue
        meta = m.get("metadata") or {}
        if meta.get("is_user_system_message"):
            continue
        content = m.get("content") or {}
        if content.get("content_type") not in ("text", "multimodal_text"):
            continue
        parts = content.get("parts") or []
        if not any(isinstance(p, str) and p.strip() for p in parts):
            continue
        out.append(m)
    out.sort(key=lambda m: m.get("create_time") or 0.0)
    return out


_PREFIX_MIN = 40  # only tolerate prefix (truncation) matches for genuinely long text


def _matching_user_msg(
    convo: dict, prompt: str, *, exclude_ids: frozenset[str] = frozenset()
) -> dict | None:
    """Return the user message in `convo` whose text matches `prompt`, ignoring any
    message id in `exclude_ids` (the user messages that existed BEFORE our send).

    Matching rules, tightened to avoid confirming the WRONG conversation:
      * compare FULL normalized text (no length cap), so two long prompts that
        merely share a boilerplate preamble don't collide;
      * exact equality is the primary test;
      * a one-directional prefix match is allowed ONLY when the shorter side is at
        least `_PREFIX_MIN` chars — this tolerates composer-side truncation while
        preventing short prompts ("yes", "ok", "continue") from prefix-matching an
        unrelated longer message;
      * iterate NEWEST-first (a just-sent message may briefly have a null
        create_time, treated as newest) so we lock onto the message we just sent.
    """
    want = _norm(prompt)
    if not want:
        return None
    msgs = _user_text_messages(convo)
    msgs.sort(
        key=lambda m: (m.get("create_time") is None, m.get("create_time") or 0.0),
        reverse=True,
    )
    for m in msgs:
        if m.get("id") in exclude_ids:
            continue
        parts = (m.get("content") or {}).get("parts") or []
        got = _norm("\n".join(p for p in parts if isinstance(p, str)))
        if not got:
            continue
        if got == want:
            return m
        if len(want) >= _PREFIX_MIN and got.startswith(want):
            return m
        if len(got) >= _PREFIX_MIN and want.startswith(got):
            return m
    return None


def verify_user_prompt_present(
    conversation_id: str,
    prompt: str,
    *,
    exclude_ids: frozenset[str] = frozenset(),
    timeout: float = 25.0,
    poll: float = 1.5,
    target: tuple[int, int] | None = None,
) -> bool:
    """Confirm that the prompt we just sent actually landed in `conversation_id`
    (a NEW user message, not one of `exclude_ids`). This is the guard that turns a
    mis-targeted follow-up into a LOUD failure instead of a stale answer."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            convo = fetch_conversation(
                conversation_id,
                retries=2,
                retry_wait=1.0,
                target=target,
                read_throttle_waits=(10.0,),
            )
        except ChatGPTError:
            time.sleep(poll)
            continue
        if _matching_user_msg(convo, prompt, exclude_ids=exclude_ids) is not None:
            return True
        time.sleep(poll)
    return False


def capture_conversation_for_prompt(
    prompt: str,
    prior_ids: set[str],
    *,
    timeout: float = 35.0,
    poll: float = 1.5,
    front_target: tuple[int, int] | None = None,
) -> str | None:
    """Identify the conversation our send created by matching the user-message
    TEXT in a conversation that did not exist before the send.

    If text matching never succeeds in time, we only fall back to an UNCONFIRMED
    id when it's unambiguous — exactly one brand-new conversation exists (safe
    under the send lock) — or when there was no prompt text to match at all.
    Otherwise we return None so ask() fails loudly rather than pinning a guessed
    (possibly foreign) conversation."""
    want = _norm(prompt)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        candidates: list[str] = []
        # Fast path: the tab we sent in usually navigated to /c/<newid>.
        if front_target is not None:
            try:
                p = _run_js_in_tab(
                    front_target[0],
                    front_target[1],
                    "(location.pathname.match(/\\/c\\/([\\w-]+)/) || [,''])[1]",
                )
                if p:
                    candidates.append(p)
            except ChatGPTError:
                pass
        for rid in recent_conversation_ids(target=front_target):
            if rid not in prior_ids and rid not in candidates:
                candidates.append(rid)
        for cid in candidates:
            try:
                convo = fetch_conversation(
                    cid,
                    retries=1,
                    retry_wait=0.5,
                    target=front_target,
                    read_throttle_waits=(),
                )
            except ChatGPTError:
                continue
            if not want or _matching_user_msg(convo, prompt) is not None:
                return cid
        time.sleep(poll)
    # Last-ditch — only when safe: no text to match, or a single unambiguous new id.
    new_ids = [rid for rid in recent_conversation_ids(target=front_target) if rid not in prior_ids]
    if not want and new_ids:
        return new_ids[0]
    if len(new_ids) == 1:
        return new_ids[0]
    return None


# --------------------------------------------------------------------------- #
# Public API


@dataclass
class Response:
    """A captured assistant response."""

    text: str
    conversation_id: str
    message_id: str
    model_slug: str | None
    thinking_effort: str | None
    citations: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class Submission:
    """A verified prompt submission that may still be generating a response."""

    conversation_id: str


@dataclass(frozen=True)
class _SubmittedTurn:
    """Private continuation state needed when a caller also waits for a response."""

    submission: Submission
    after_message_id: str | None
    target: tuple[int, int]


def ensure_chatgpt_available(*, ready_timeout: float = 15.0) -> tuple[int, int]:
    """Ensure a chatgpt.com tab exists IN THE DEDICATED PROFILE WINDOW (opening
    that window if needed) and return it as (window_id, tab_index), without
    stealing focus — except the one-time window open, which necessarily fronts
    Chrome. Never returns a tab from another profile's window."""
    wid = dedicated_window()
    deadline = time.monotonic() + ready_timeout
    while True:
        tab = _find_tab_in_window(wid, "chatgpt.com")
        if tab is not None:
            return tab
        if time.monotonic() >= deadline:
            raise ChatGPTError("The dedicated profile window has no chatgpt.com tab.")
        time.sleep(0.5)


def prepare_continue_tab(conversation_id: str, *, ready_timeout: float = 20.0) -> tuple[int, int]:
    """Ensure SOME tab is showing `conversation_id` and return its
    (window_id, tab_index). Prefers a tab already on that conversation (no
    navigation, no clobber — the common ask-then-continue case, where the tab the
    original ask created is still open), else opens a fresh background tab AT that
    conversation. Only if a new tab cannot be created does it fall back to reusing
    an existing chatgpt tab, which DOES navigate that tab to the conversation
    (replacing whatever it was showing). Either way it verifies the URL before
    returning, so the follow-up types into the RIGHT thread regardless of how many
    other chatgpt tabs exist."""
    target = _find_tab_by_url_contains(f"/c/{conversation_id}")
    if target is not None:
        return target

    url = f"https://chatgpt.com/c/{conversation_id}"
    fresh = _new_tab_in_dedicated_window(url)
    if fresh is not None:
        target = fresh  # already opened AT the target url; no second navigation
    else:
        # No fresh tab available — reuse a dedicated-window chatgpt tab. This
        # replaces whatever it was showing (last-resort; normally we open a new one).
        target = ensure_chatgpt_available()
        _navigate_tab(target, url)
    if not _wait_tab_ready(target, cid_substr=f"/c/{conversation_id}", ready_timeout=ready_timeout):
        # Index may have shifted during navigation; re-resolve by URL and retry.
        target = _find_tab_by_url_contains(f"/c/{conversation_id}")
        if target is None or not _wait_tab_ready(
            target, cid_substr=f"/c/{conversation_id}", ready_timeout=5.0
        ):
            raise ChatGPTError(
                f"Navigated a tab to conversation {conversation_id} but it did not load in time."
            )
    return target


def _front_conversation_id() -> str | None:
    """Best-effort: the conversation id in the FRONT window's active tab. Used only
    as a last resort for a bare continue (no explicit id, no saved session) — e.g.
    the human CLI's "continue the conversation I'm looking at". We still bind to it
    by id afterward (prepare_continue_tab re-finds that same tab), so the run stays
    drift-safe even though the initial pick comes from the front window."""
    try:
        cid = _run_js("(location.pathname.match(/\\/c\\/([\\w-]+)/) || [,''])[1]")
    except ChatGPTError:
        return None
    return cid or None


def get_session(*, target: tuple[int, int] | None = None) -> dict:
    """
    Returns the auth session (`/api/auth/session`). Raises NotLoggedInError if
    the user isn't authenticated. When `target` is given, runs in that exact tab.
    """
    s = _run_js_async(
        "fetch('/api/auth/session', {credentials:'include'}).then(r => r.json())",
        target=target,
    )
    if not isinstance(s, dict) or not s.get("accessToken"):
        raise NotLoggedInError(
            "You're not logged in to chatgpt.com in this Chrome profile. "
            "Open https://chatgpt.com/ in Chrome and sign in, then retry."
        )
    # Cache the token in the page for fast subsequent calls.
    _js(target, f"window.__cgptToken = {json.dumps(s['accessToken'])};")
    return s


def attach_files(
    paths: list[Path], *, target: tuple[int, int] | None = None, ready_timeout: float = 90.0
) -> list[dict]:
    """
    Attach up to 10 files to the next message. Returns list of {name, size, mime}.
    Waits until each file's chip appears in the composer. When `target` is given,
    the upload and chip-poll run in that exact tab.
    """
    if not paths:
        return []
    if len(paths) > 10:
        raise ChatGPTError(f"Max 10 files per message; got {len(paths)}.")

    payload = []
    for p in paths:
        p = Path(p).expanduser().resolve()
        if not p.is_file():
            raise ChatGPTError(f"Not a file: {p}")
        data = p.read_bytes()
        mime, _ = mimetypes.guess_type(p.name)
        payload.append(
            {
                "name": p.name,
                "size": len(data),
                "mime": mime or "application/octet-stream",
                "b64": base64.b64encode(data).decode("ascii"),
            }
        )

    js = (
        "(async () => { "
        f"  const items = {json.dumps(payload)}; "
        "  const inp = document.querySelector('#upload-files'); "
        "  if (!inp) throw new Error('upload-files input not found'); "
        "  const dt = new DataTransfer(); "
        "  for (const it of items) { "
        "    const bytes = Uint8Array.from(atob(it.b64), c => c.charCodeAt(0)); "
        "    const file = new File([bytes], it.name, {type: it.mime}); "
        "    dt.items.add(file); "
        "  } "
        "  inp.files = dt.files; "
        "  inp.dispatchEvent(new Event('change', {bubbles:true, cancelable:true})); "
        "  return {count: items.length, names: items.map(i => i.name)}; "
        "})()"
    )
    _run_js_async(js, target=target)

    # Wait for chips to render. Each attachment gets a div whose innerText
    # contains the filename (and "Document"/"Image"/etc).
    target_names = {it["name"] for it in payload}
    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        time.sleep(0.4)
        try:
            chips_json = _js(
                target,
                "JSON.stringify("
                "Array.from(document.querySelectorAll('div'))"
                ".map(d => (d.innerText||'').slice(0,200))"
                ".filter(t => t && t.length < 200)"
                ")",
            )
            chip_texts = json.loads(chips_json)
        except (ChatGPTError, json.JSONDecodeError):
            continue
        seen = {n for n in target_names if any(n in t for t in chip_texts)}
        if seen == target_names:
            time.sleep(0.5)  # buffer for UI to settle
            return [{"name": it["name"], "size": it["size"], "mime": it["mime"]} for it in payload]
    raise ChatGPTTimeoutError(
        f"File chips didn't appear within {ready_timeout}s: {sorted(target_names)}"
    )


def _composer_mode_state(target: tuple[int, int] | None) -> dict[str, Any]:
    """Return the current Chat/Work composer mode without changing the page."""
    raw = _js(
        target,
        "(() => {"
        "  const radios = Array.from(document.querySelectorAll('button[role=radio]'));"
        "  const label = e => (((e && e.innerText) || '').trim().split('\\n')[0] || '').trim();"
        "  const chat = radios.find(e => label(e) === 'Chat');"
        "  const work = radios.find(e => label(e) === 'Work');"
        "  const selected = e => !!e && (e.getAttribute('aria-checked') === 'true' || "
        "e.getAttribute('data-state') === 'on');"
        "  const pill = document.querySelector('button.__composer-pill');"
        "  return JSON.stringify({"
        "    has_mode_controls: !!(chat || work),"
        "    chat_selected: selected(chat),"
        "    work_selected: selected(work),"
        "    composer_ready: !!document.querySelector('#prompt-textarea'),"
        "    pill: label(pill)"
        "  });"
        "})()",
    )
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ChatGPTError(f"Could not read the Chat/Work composer mode: {e}") from e
    if not isinstance(state, dict):
        raise ChatGPTError("Could not read the Chat/Work composer mode.")
    return state


def ensure_chat_mode(
    *,
    target: tuple[int, int] | None = None,
    discovery_timeout: float = 3.0,
    switch_timeout: float = 8.0,
) -> None:
    """Select and verify Chat mode before attaching files or choosing Pro.

    ChatGPT serves Chat and Work from the same root URL. Work exposes Codex-style
    model and effort choices rather than the Chat model picker, so merely waiting
    for a composer is not enough to establish that Pro can be selected.
    """
    deadline = time.monotonic() + discovery_timeout
    state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        state = _composer_mode_state(target)
        if state.get("chat_selected"):
            return
        if state.get("work_selected"):
            break
        pill = str(state.get("pill", "")).lower()
        if not state.get("has_mode_controls") and pill in {
            "instant",
            "pro",
            "thinking",
        }:
            return
        time.sleep(0.2)
    else:
        pill = str(state.get("pill", "") or "unknown")
        raise ChatGPTError(
            "Could not verify Chat mode before selecting Pro "
            f"(current composer pill: {pill!r})."
        )

    _js(
        target,
        "(() => {"
        "  const chat = Array.from(document.querySelectorAll('button[role=radio]'))"
        "    .find(e => (((e.innerText || '').trim().split('\\n')[0] || '').trim()) === 'Chat');"
        "  if (!chat) throw new Error('Chat mode control missing');"
        "  chat.focus();"
        "  chat.click();"
        "})()",
    )

    deadline = time.monotonic() + switch_timeout
    while time.monotonic() < deadline:
        time.sleep(0.2)
        state = _composer_mode_state(target)
        if state.get("chat_selected") and state.get("composer_ready"):
            time.sleep(0.4)
            if _composer_mode_state(target).get("chat_selected"):
                return
    raise ChatGPTError(
        "Selected Chat mode, but the composer did not remain in Chat mode."
    )


def select_pro(*, target: tuple[int, int] | None = None) -> None:
    """
    Switch the model picker to the current Pro variant.

    Uses the composer pill menu, which only exposes the current major version's
    Instant/Thinking/Pro flavors. To pick a different version, drive the
    "Configure..." modal (not implemented here). When `target` is given, the
    whole menu interaction runs in that exact tab.
    """

    ensure_chat_mode(target=target)

    def _pill_first_line() -> str:
        try:
            txt = _js(
                target,
                "((document.querySelector('button.__composer-pill') || {innerText:''})"
                ".innerText || '')",
            )
        except ChatGPTError:
            return ""
        return (txt.strip().split("\n")[0] or "").strip()

    def _pill_shows_pro() -> bool:
        return "pro" in _pill_first_line().lower()

    if _pill_shows_pro():
        return

    def _open_pill_menu() -> None:
        _js(
            target,
            "(() => {"
            "  const b = document.querySelector('button.__composer-pill');"
            "  if (!b) throw new Error('composer pill button missing');"
            "  b.focus();"
            "  b.dispatchEvent(new KeyboardEvent('keydown', "
            "{key:'Enter', bubbles:true, cancelable:true}));"
            "  b.dispatchEvent(new KeyboardEvent('keyup', "
            "{key:'Enter', bubbles:true, cancelable:true}));"
            "})()",
        )
        time.sleep(0.4)

    def _wait_menu_open(open_: bool, *, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                state = _js(
                    target,
                    "(document.querySelector('button.__composer-pill') || {}).getAttribute"
                    " && document.querySelector('button.__composer-pill')"
                    ".getAttribute('data-state')",
                )
            except ChatGPTError:
                state = ""
            if (open_ and state == "open") or (not open_ and state == "closed"):
                return
            time.sleep(0.15)

    _open_pill_menu()
    _wait_menu_open(True)

    # The pill menu shows the current major version's flavors. Match by a stable
    # data-testid suffix where possible, then fall back to the first visible line.
    pro_state = _js(
        target,
        "(() => {"
        "  let pro = document.querySelector('[role=menuitemradio][data-testid$=\"-pro\"]');"
        "  if (!pro) pro = Array.from(document.querySelectorAll("
        "'[role=menuitemradio],[role=menuitem]'))"
        "    .find(e => (((e.innerText||'').trim().split('\\n')[0]||'').trim())"
        ".startsWith('Pro'));"
        "  return pro ? (pro.getAttribute('aria-checked') || 'unchecked') : 'missing';"
        "})()",
    )
    if pro_state == "missing":
        raise ChatGPTError(
            "Couldn't find a 'Pro' option in the model picker. "
            "Your account may not have access to Pro models, or the UI "
            "for the current major version doesn't expose a Pro variant."
        )
    if pro_state != "true":
        _js(
            target,
            "(() => {"
            "  let pro = document.querySelector('[role=menuitemradio][data-testid$=\"-pro\"]');"
            "  if (!pro) pro = Array.from(document.querySelectorAll("
            "'[role=menuitemradio],[role=menuitem]'))"
            "    .find(e => (((e.innerText||'').trim().split('\\n')[0]||'').trim())"
            ".startsWith('Pro'));"
            "  pro.focus();"
            "  pro.dispatchEvent(new KeyboardEvent('keydown', "
            "{key:'Enter', bubbles:true, cancelable:true}));"
            "  pro.dispatchEvent(new KeyboardEvent('keyup', "
            "{key:'Enter', bubbles:true, cancelable:true}));"
            "})()",
        )
        time.sleep(0.6)
    else:
        # The checked Pro item means only that the menu selection is already
        # correct. Toggle the pill to close the menu before returning.
        _open_pill_menu()
    _wait_menu_open(False)
    if not _pill_shows_pro():
        raise ChatGPTError("Selected the 'Pro' model option, but the composer did not confirm Pro.")


def send_prompt(text: str, *, target: tuple[int, int] | None = None) -> None:
    """Type `text` into the composer and click Send. When `target` is given, the
    typing and the send-button click run in that exact tab."""
    if not text.strip():
        raise ChatGPTError("Prompt is empty.")
    js_type = (
        "(() => {"
        "  const ed = document.querySelector('#prompt-textarea');"
        "  if (!ed) throw new Error('composer textarea missing');"
        "  ed.focus();"
        f"  ed.innerHTML = {json.dumps('<p>' + _html_escape(text) + '</p>')};"
        "  ed.dispatchEvent(new InputEvent('input', {bubbles:true, cancelable:true, "
        f"    inputType:'insertText', data:{json.dumps(text)}}}));"
        "})()"
    )
    _js(target, js_type)
    time.sleep(0.25)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        clicked = _js(
            target,
            "(() => {"
            "  const b = document.querySelector('[data-testid=send-button]');"
            "  if (!b || b.disabled) return 'no';"
            "  b.focus(); b.click();"
            "  return 'yes';"
            "})()",
        )
        if clicked == "yes":
            return
        time.sleep(0.4)
    raise ChatGPTTimeoutError("Send button never became enabled.")


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wait_for_response(
    *,
    conversation_id: str,
    after_message_id: str | None = None,
    timeout: float = 1200.0,
    poll: float = 2.0,
    on_progress=None,
    settle_confirmations: int = 2,
    min_settle_seconds: float = 6.0,
    target: tuple[int, int] | None = None,
) -> Response:
    """
    Wait until the assistant's *final* answer for a new turn past
    `after_message_id` is complete, then return it.

    The conversation is read BY ID via a drift-proof synchronous XHR every poll,
    from `target` (the tab the run owns) or a dedicated-window tab — immune to
    the front-window drift you get with many open chatgpt tabs.

    "Final" means a `text` assistant message that is (a) complete, and (b) the
    tail of the turn — i.e. no assistant message of ANY type (thoughts, code,
    tool-use) was created after it. Reasoning/Pro models emit short interim
    `text` status lines mid-run with end_turn=True and then keep working, so the
    tail check is what prevents returning a premature interim emission. The
    qualifying state must repeat for `settle_confirmations` consecutive polls AND
    persist `min_settle_seconds` of wall-clock before returning, so a brief
    thinking pause (where a preamble momentarily looks like the tail) does not
    settle early.

    `on_progress(state: str)` is called periodically with informational state.
    """
    progress = on_progress or (lambda s: None)
    started = time.monotonic()
    deadline = started + timeout
    confirmed = 0
    stable_key: tuple[str, int] | None = None
    first_qualified_at: float | None = None
    cid = conversation_id

    while time.monotonic() < deadline:
        try:
            convo = fetch_conversation(
                cid,
                retries=2,
                retry_wait=1.0,
                target=target,
                on_read_throttle=lambda wait: progress(
                    "ChatGPT read-side throttle; backing off "
                    f"{int(wait)}s before retrying the same conversation"
                ),
            )
        except ChatGPTReadThrottledError as e:
            progress(f"read-side throttle (retrying same conversation): {e}")
            time.sleep(max(poll, 60.0))
            continue
        except ChatGPTError as e:
            progress(f"poll error (retrying): {e}")
            time.sleep(poll)
            continue

        last = _last_text_assistant(convo)
        if last is None:
            progress("assistant working (no answer text yet)")
            confirmed = 0
            time.sleep(poll)
            continue

        msg_id = last.get("id") or ""
        if msg_id == after_message_id:
            progress("waiting for new turn")
            confirmed = 0
            time.sleep(poll)
            continue

        parts = (last.get("content") or {}).get("parts", []) or []
        text = "\n".join(p for p in parts if isinstance(p, str))

        if not _is_message_complete(last):
            progress(f"streaming answer… ({len(text)} chars)")
            confirmed = 0
            time.sleep(poll)
            continue

        if not _is_final_text_assistant(convo, last):
            # The latest *text* is complete but newer thoughts/code/tool-use
            # exist: this is an interim status line, not the final answer.
            progress(f"model still working past interim text ({len(text)} chars)")
            confirmed = 0
            time.sleep(poll)
            continue

        key = (msg_id, len(text))
        if key == stable_key:
            confirmed += 1
        else:
            confirmed = 0
            first_qualified_at = time.monotonic()
        stable_key = key
        dwell = time.monotonic() - (first_qualified_at or time.monotonic())
        if confirmed < settle_confirmations or dwell < min_settle_seconds:
            progress(f"final answer settling ({len(text)} chars, {dwell:.0f}s)")
            time.sleep(poll)
            continue

        meta = last.get("metadata") or {}
        return Response(
            text=text,
            conversation_id=cid,
            message_id=msg_id,
            model_slug=meta.get("model_slug"),
            thinking_effort=meta.get("thinking_effort"),
            citations=meta.get("content_references", []) or [],
            duration_seconds=time.monotonic() - started,
        )
    raise ChatGPTTimeoutError(
        f"No completed assistant response within {timeout}s. The conversation may "
        f"still be running; check Chrome, or read it from "
        f"GET /backend-api/conversation/<id>."
    )


def _last_text_assistant(convo: dict) -> dict | None:
    """Return the most recent non-empty text assistant message in the tree."""
    texts = _assistant_text_messages(convo)
    return texts[-1] if texts else None


def _assistant_text_messages(convo: dict) -> list[dict]:
    """All assistant `text` messages with non-empty parts, oldest-first."""
    out = []
    for node in (convo or {}).get("mapping", {}).values():
        m = (node or {}).get("message")
        if not m or (m.get("author") or {}).get("role") != "assistant":
            continue
        if (m.get("content") or {}).get("content_type") != "text":
            continue
        parts = (m.get("content") or {}).get("parts") or []
        if not any(isinstance(p, str) and p.strip() for p in parts):
            continue
        out.append(m)
    out.sort(key=lambda m: m.get("create_time") or 0.0)
    return out


def _max_assistant_activity_time(convo: dict) -> float:
    """Latest create_time across ALL assistant messages of any content_type.

    Reasoning models post interim `text` status lines (with end_turn=True) while
    still working, then continue emitting `thoughts`/`code`/tool-use messages and
    only later produce the real answer. Comparing the latest *text* message's
    create_time against the latest assistant activity of *any* type tells us
    whether the text is the true tail of the turn or just an interim emission.
    """
    latest = 0.0
    for node in (convo or {}).get("mapping", {}).values():
        m = (node or {}).get("message")
        if not m or (m.get("author") or {}).get("role") != "assistant":
            continue
        ts = m.get("create_time") or 0.0
        if ts > latest:
            latest = ts
    return latest


def _is_message_complete(m: dict) -> bool:
    meta = m.get("metadata") or {}
    return bool(
        meta.get("is_complete")
        or m.get("end_turn") is True
        or m.get("status") == "finished_successfully"
    )


def _is_final_text_assistant(convo: dict, m: dict) -> bool:
    """True when `m` is complete text and no later assistant activity exists."""
    if not _is_message_complete(m):
        return False
    last_ts = m.get("create_time") or 0.0
    return last_ts >= _max_assistant_activity_time(convo)


def _response_from_convo(convo: dict, conversation_id: str) -> Response:
    """Build a Response from the latest complete assistant text in a conversation."""
    last = _last_text_assistant(convo)
    if last is None:
        raise ChatGPTError(f"No assistant text in conversation {conversation_id}.")
    parts = (last.get("content") or {}).get("parts") or []
    text = "\n".join(p for p in parts if isinstance(p, str))
    meta = last.get("metadata") or {}
    return Response(
        text=text,
        conversation_id=conversation_id,
        message_id=last.get("id") or "",
        model_slug=meta.get("model_slug"),
        thinking_effort=meta.get("thinking_effort"),
        citations=meta.get("content_references", []) or [],
    )


def get_final_answer(conversation_id: str | None = None, *, on_read_throttle=None) -> Response:
    """Fetch the latest assistant answer of a known conversation by id (recovery
    path for an interrupted run). Defaults to the last conversation this tool
    created. Drift-proof: reads BY ID, not from the front window."""
    cid = conversation_id or load_last_conversation_id()
    if not cid:
        raise ChatGPTError("No conversation id given and no saved session to recover from.")
    # Surface a logged-out Chrome as NotLoggedInError (exit 10) up front, rather
    # than letting the by-id XHR fail with an opaque error (which the CLI would
    # report as a generic exit 1). get_session raises NotLoggedInError if needed.
    tab = ensure_chatgpt_available()
    get_session(target=tab)
    convo = fetch_conversation(
        cid,
        target=tab,
        on_read_throttle=on_read_throttle,
    )
    last = _last_text_assistant(convo)
    if last is not None and not _is_final_text_assistant(convo, last):
        # Still streaming or past interim text; surface what exists but flag it.
        resp = _response_from_convo(convo, cid)
        resp.duration_seconds = -1.0  # sentinel: incomplete
        return resp
    return _response_from_convo(convo, cid)


# --------------------------------------------------------------------------- #
# High-level orchestration


def _submit_turn(
    prompt: str,
    *,
    files: Iterable[str | Path] = (),
    new_chat: bool = True,
    conversation_id: str | None = None,
    on_progress=None,
) -> _SubmittedTurn:
    """
    Ensure login, target a chat, attach files, select Pro, send the prompt, and
    verify which conversation received it. Does not wait for or read the answer.

    Conversation targeting (the fix for "follow-up landed in the wrong thread"):
    every write — model select, typing, send — is bound to ONE specific Chrome
    tab that we have confirmed is showing the target conversation. Nothing
    depends on "active tab of front window" or "first chatgpt tab anywhere", so
    other chatgpt windows/tabs (including other Chrome profiles') cannot divert
    the send. All tabs live in the skill's dedicated, profile-pinned window (see
    `dedicated_window`), so they are always in the chatgpt-logged-in profile.

      * new_chat=True  → open a fresh tab in the dedicated window (does not
        clobber whatever the user is viewing), send there, then identify the new
        conversation by matching the user-message text we sent.
      * new_chat=False → target `conversation_id` (or the last one this tool
        created), navigate/verify a tab onto it, send, and VERIFY the message
        landed there — otherwise raise loudly instead of treating a different
        thread as the target.

    Passing `conversation_id` always implies continuing that thread: if it is set
    while new_chat is left True, new_chat is forced to False (a target conversation
    must never be discarded into a fresh chat).
    """
    progress = on_progress or (lambda s: None)
    paths = [Path(p) for p in files]

    # A specific conversation target always means "continue that thread", never
    # "start fresh" — so a caller passing conversation_id can't silently spawn a new
    # conversation by leaving new_chat at its default.
    if conversation_id and new_chat:
        new_chat = False

    progress(f"ensuring the dedicated chatgpt window ({CHROME_PROFILE_EMAIL} profile)")
    existing_tab = ensure_chatgpt_available()  # a dedicated-window chatgpt tab

    pinned_cid: str | None = None
    baseline_msg_id: str | None = None

    # Serialize the brief send+capture critical section; the long wait runs OUTSIDE
    # the lock (it is a pure by-id read), so a quick follow-up never blocks on
    # someone else's 20-minute Pro run. The --continue cid is resolved INSIDE the
    # lock so the single-slot last-session read can't interleave with a writer.
    with _send_lock() as got_lock:
        if not got_lock:
            progress("warning: proceeding without send lock (another run may be active)")

        if new_chat:
            progress("opening a new chat tab in the dedicated window")
            target = _new_tab_in_dedicated_window("https://chatgpt.com/")
            if target is None:
                # No fresh tab could be created — reuse a dedicated-window tab and
                # navigate IT to a new chat. Still bound by (wid,idx), never the
                # drifting front window.
                progress("could not create a tab; reusing one in the dedicated window")
                target = existing_tab
                _navigate_tab(target, "https://chatgpt.com/")
            _activate_tab(*target)
            # require_no_cid: for a new chat the tab must be on a fresh (non-/c/)
            # page — so if we had to reuse a tab, we don't send into its old thread.
            if not _wait_tab_ready(target, require_no_cid=True, ready_timeout=20.0):
                raise ChatGPTTimeoutError("New chat composer didn't load in time.")
            progress("checking login")
            get_session(target=target)
            prior_ids = set(recent_conversation_ids(target=target))
            pre_user_ids: frozenset[str] = frozenset()
        else:
            pinned_cid = conversation_id or load_last_conversation_id()
            if not pinned_cid:
                # Last resort for a bare continue: the conversation currently visible
                # in the front window (the human-CLI "continue what I'm looking at").
                # It is then bound by id like any other target, so this stays
                # drift-safe.
                pinned_cid = _front_conversation_id()
            if not pinned_cid:
                raise ChatGPTError(
                    "Continue requested but no conversation id is known. Pass an "
                    "explicit conversation id (the --conversation-id flag), open the "
                    "conversation in Chrome's front tab, or run a fresh ask first so "
                    "a 'last conversation' exists."
                )
            progress(f"locating the tab for conversation {pinned_cid}")
            target = prepare_continue_tab(pinned_cid)
            _activate_tab(*target)
            progress("checking login")
            get_session(target=target)
            # Read the target conversation ONCE to seed both the baseline assistant
            # message id and the set of pre-existing user messages — both from the
            # pinned conversation (NOT the front window), so a divergent front tab
            # can't corrupt either.
            try:
                convo0 = fetch_conversation(
                    pinned_cid,
                    retries=3,
                    retry_wait=1.0,
                    target=target,
                    read_throttle_waits=(20.0, 60.0),
                )
            except ChatGPTError as e:
                raise ChatGPTError(f"Could not read conversation {pinned_cid} to continue it: {e}")
            baseline_msg_id = (_last_text_assistant(convo0) or {}).get("id")
            pre_user_ids = frozenset(
                m.get("id") for m in _user_text_messages(convo0) if m.get("id")
            )
            prior_ids = set()

        progress("selecting Chat mode")
        ensure_chat_mode(target=target)

        if paths:
            progress(f"attaching {len(paths)} file(s)")
            attach_files(paths, target=target)

        progress("selecting Pro")
        select_pro(target=target)

        progress("sending prompt")
        send_prompt(prompt, target=target)

        if new_chat:
            progress("capturing conversation id")
            pinned_cid = capture_conversation_for_prompt(prompt, prior_ids, front_target=target)
            if not pinned_cid:
                raise ChatGPTError(
                    "Sent the prompt but could not identify the new conversation id. "
                    "If it is still running, recover the answer later with --fetch."
                )
            _save_session(pinned_cid)
            progress(f"pinned conversation {pinned_cid}")
        else:
            progress("verifying the follow-up landed in the target thread")
            if not verify_user_prompt_present(
                pinned_cid, prompt, exclude_ids=pre_user_ids, target=target
            ):
                raise ChatGPTError(
                    f"The follow-up did NOT appear in conversation {pinned_cid} within "
                    "the verification window — it was likely typed into a different "
                    "tab/thread. Aborting instead of returning a stale answer. Re-run "
                    "with an explicit --conversation-id, and make sure that "
                    "conversation's tab is reachable."
                )
            _save_session(pinned_cid)
    # Lock released. A caller may now return immediately or wait by id.

    if pinned_cid is None:
        raise ChatGPTError("The prompt was sent, but no conversation id was captured.")
    return _SubmittedTurn(
        submission=Submission(conversation_id=pinned_cid),
        after_message_id=baseline_msg_id,
        target=target,
    )


def submit(
    prompt: str,
    *,
    files: Iterable[str | Path] = (),
    new_chat: bool = True,
    conversation_id: str | None = None,
    on_progress=None,
) -> Submission:
    """Submit and verify a Pro prompt without waiting for its response."""
    return _submit_turn(
        prompt,
        files=files,
        new_chat=new_chat,
        conversation_id=conversation_id,
        on_progress=on_progress,
    ).submission


def ask(
    prompt: str,
    *,
    files: Iterable[str | Path] = (),
    new_chat: bool = True,
    conversation_id: str | None = None,
    timeout: float = 1200.0,
    on_progress=None,
) -> Response:
    """Submit a verified Pro prompt, then wait for its completed response."""
    progress = on_progress or (lambda s: None)
    turn = _submit_turn(
        prompt,
        files=files,
        new_chat=new_chat,
        conversation_id=conversation_id,
        on_progress=progress,
    )
    progress("waiting for response")
    resp = wait_for_response(
        conversation_id=turn.submission.conversation_id,
        after_message_id=turn.after_message_id,
        timeout=timeout,
        on_progress=progress,
        target=turn.target,
    )
    # NOTE: the cid was already saved inside the lock and does not change during
    # the wait, so we deliberately do NOT _save_session here — a long Pro run that
    # finishes minutes later must not overwrite a more recent send's saved cid.
    return resp


__all__ = [
    "ChatGPTError",
    "NotLoggedInError",
    "JSExecBlockedError",
    "ChatGPTTimeoutError",
    "ChatGPTReadThrottledError",
    "Response",
    "Submission",
    "ensure_chatgpt_available",
    "dedicated_window",
    "prepare_continue_tab",
    "get_session",
    "attach_files",
    "ensure_chat_mode",
    "select_pro",
    "send_prompt",
    "wait_for_response",
    "verify_user_prompt_present",
    "capture_conversation_for_prompt",
    "submit",
    "ask",
    "fetch_conversation",
    "fetch_conversations_page",
    "get_final_answer",
    "recent_conversation_ids",
    "load_last_conversation_id",
    "CHROME_PROFILE_EMAIL",
]
