#!/usr/bin/env python3
"""Drive Gemini Notebook (notebook.google.com, formerly NotebookLM) from the shell.

The transport is the user's signed-in Chrome. AppleScript evaluates the sibling nblm.js in
one background tab this tool opens and owns, then calls its functions. The tool never reads
cookies, tokens, or Chrome profile files, and it never signs in.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import dataclasses
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

CHROME_APP = "Google Chrome"
HOME_URL = "https://notebook.google.com/"
ACCOUNT = os.environ.get("CHROME_PROFILE_EMAIL")
STATE_DIR = Path.home() / ".codex" / "state" / "nblm"
STATE_FILE = STATE_DIR / "browser.json"
LOCK_FILE = STATE_DIR / "browser.lock"
LIBRARY = Path(__file__).with_name("nblm.js")
DOWNLOADS = Path(os.environ.get("NBLM_DOWNLOADS", Path.home() / "Downloads"))
# Base64 characters per upload call; keeps each AppleScript literal near 1 MB.
CHUNK_CHARS = 1_000_000
MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".epub": "application/epub+zip",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

EXIT_SIGNED_OUT = 10
EXIT_JAVASCRIPT_DISABLED = 11
EXIT_BROWSER = 12
EXIT_APP = 13
EXIT_USAGE = 64


class NblmError(RuntimeError):
    def __init__(self, message: str, exit_code: int = EXIT_APP):
        super().__init__(message)
        self.exit_code = exit_code


@dataclasses.dataclass(frozen=True)
class Tab:
    window_id: int
    tab_id: int


def _osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript"], input=script, text=True, capture_output=True, check=False
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        if "Allow JavaScript from Apple Events" in detail:
            raise NblmError(
                "Chrome blocks JavaScript from Apple Events. Enable View > Developer > "
                "Allow JavaScript from Apple Events, then retry.",
                EXIT_JAVASCRIPT_DISABLED,
            )
        raise NblmError(f"Chrome automation failed: {detail}", EXIT_BROWSER)
    return result.stdout.rstrip("\n")


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _tab_ref(tab: Tab) -> str:
    return f"first tab of (first window whose id is {tab.window_id}) whose id is {tab.tab_id}"


def _eval(tab: Tab, source: str) -> str:
    """Evaluate JavaScript in the tab's AppleScript world and return its string result.

    That world shares the page DOM but not its globals; nblm.js accounts for this.
    """
    encoded = base64.b64encode(source.encode()).decode()
    wrapper = f'eval(new TextDecoder().decode(Uint8Array.from(atob("{encoded}"), c => c.charCodeAt(0))))'
    return _osascript(
        f'tell application "{CHROME_APP}"\n'
        f"  return execute ({_tab_ref(tab)}) javascript {_quote(wrapper)}\n"
        "end tell"
    )


def _tab_url(tab: Tab) -> str | None:
    url = _osascript(
        f'tell application "{CHROME_APP}"\n'
        f'  try\n    return URL of ({_tab_ref(tab)})\n  on error\n    return ""\n  end try\n'
        "end tell"
    )
    return url or None


def _all_tabs() -> list[tuple[Tab, str]]:
    separator = "|||NBLM|||"
    raw = _osascript(
        f'tell application "{CHROME_APP}"\n'
        '  set output to ""\n'
        "  repeat with w in windows\n"
        "    repeat with t in tabs of w\n"
        f'      set output to output & (id of w as text) & "{separator}" & (id of t as text) & "{separator}" & (URL of t) & linefeed\n'
        "    end repeat\n"
        "  end repeat\n"
        "  return output\n"
        "end tell"
    )
    tabs = []
    for line in raw.splitlines():
        parts = line.split(separator, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            tabs.append((Tab(int(parts[0]), int(parts[1])), parts[2]))
    return tabs


PAGE_STATE_JS = r"""
(() => {
  if (location.hostname === 'accounts.google.com') return JSON.stringify({state: 'signed_out'});
  if (location.hostname !== 'notebook.google.com' || document.readyState === 'loading') return JSON.stringify({state: 'loading'});
  const boot = [...document.scripts].map((s) => s.textContent).find((t) => t.includes('WIZ_global_data')) || '';
  const account = (boot.match(/"oPEP7c":"([^"]*)"/) || [])[1] || null;
  if (!/"SNlM0e":"[^"]+"/.test(boot)) return JSON.stringify({state: boot ? 'signed_out' : 'loading', account});
  return JSON.stringify({state: 'ready', account});
})()
"""


def _page_state(tab: Tab) -> dict[str, Any]:
    raw = _eval(tab, PAGE_STATE_JS)
    # A tab mid-navigation can answer `missing value` instead of running the script.
    return json.loads(raw) if raw.startswith("{") else {"state": "loading"}


def _wait_for_page(tab: Tab, timeout: float = 45) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        state = _page_state(tab)
        if state["state"] != "loading":
            return state
        if time.monotonic() > deadline:
            raise NblmError(
                "Gemini Notebook did not finish loading in the tool's tab.",
                EXIT_BROWSER,
            )
        time.sleep(0.5)


def _require_account(tab: Tab) -> None:
    if not ACCOUNT:
        raise NblmError(
            "CHROME_PROFILE_EMAIL is not set. Export the email of the Google account "
            "signed in to Gemini Notebook, in ~/.config/agent-system/shell.local.sh.",
            EXIT_USAGE,
        )
    state = _wait_for_page(tab)
    if state["state"] == "signed_out":
        raise NblmError(
            f"Gemini Notebook is signed out in Chrome. Ask the user to sign in as {ACCOUNT}, then retry.",
            EXIT_SIGNED_OUT,
        )
    if state["account"] != ACCOUNT:
        raise NblmError(
            f"The tool's tab is signed in as {state['account']}, not {ACCOUNT}. Set CHROME_PROFILE_EMAIL or open "
            f"Gemini Notebook in the Chrome profile for {ACCOUNT}, run `close`, and retry.",
            EXIT_SIGNED_OUT,
        )


def _open_tab() -> Tab:
    """Open a background tab, preferring a window that already shows Gemini Notebook."""
    windows = [tab.window_id for tab, url in _all_tabs() if url.startswith(HOME_URL)]
    if not windows:
        windows = [tab.window_id for tab, _ in _all_tabs()]
    if not windows:
        raise NblmError(
            "Chrome has no open window. Open Chrome, then retry.", EXIT_BROWSER
        )
    window_id = windows[0]
    tab_id = _osascript(
        f'tell application "{CHROME_APP}"\n'
        f"  set w to first window whose id is {window_id}\n"
        "  set previous to active tab index of w\n"
        f"  set t to make new tab at end of tabs of w with properties {{URL:{_quote(HOME_URL)}}}\n"
        "  set active tab index of w to previous\n"
        "  return id of t as text\n"
        "end tell"
    )
    return Tab(window_id, int(tab_id))


def _navigate(tab: Tab, url: str) -> None:
    _osascript(
        f'tell application "{CHROME_APP}" to set URL of ({_tab_ref(tab)}) to {_quote(url)}'
    )


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        return {}


def _save_state(tab: Tab) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(dataclasses.asdict(tab)) + "\n")
    temporary.replace(STATE_FILE)


@contextlib.contextmanager
def _browser_lock() -> Iterator[None]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _tool_tab() -> Tab:
    """The tool's own tab, signed in, on a notebook page, with nblm.js loaded."""
    state = _load_state()
    tab = Tab(state["window_id"], state["tab_id"]) if state else None
    url = _tab_url(tab) if tab else None
    if tab is None or url is None:
        tab = _open_tab()
        _save_state(tab)
    elif not url.startswith(HOME_URL):
        _navigate(tab, HOME_URL)
    _require_account(tab)
    _ensure_library(tab)
    return tab


def _ensure_library(tab: Tab) -> None:
    source = LIBRARY.read_text()
    digest = hashlib.sha256(source.encode()).hexdigest()[:16]
    if _eval(tab, "String(window.nblmDigest)") == digest:
        return
    loaded = _eval(
        tab,
        f"delete window.nblm; const status = {source}\nwindow.nblmDigest = '{digest}'; status",
    )
    if not loaded.startswith("nblm v"):
        raise NblmError(f"nblm.js did not load: {loaded}", EXIT_BROWSER)


def _call(tab: Tab, method: str, *args: Any, timeout: float = 600) -> Any:
    job = _eval(
        tab, f"window.nblm.start({json.dumps(method)}, ...{json.dumps(list(args))})"
    )
    deadline = time.monotonic() + timeout
    while True:
        result = json.loads(_eval(tab, f"window.nblm.poll({json.dumps(job)})"))
        if result["done"]:
            if not result["ok"]:
                raise NblmError(result["error"])
            return result.get("value")
        if time.monotonic() > deadline:
            raise NblmError(
                f"{method} did not finish within {timeout:.0f}s", EXIT_BROWSER
            )
        time.sleep(0.3)


def call(method: str, *args: Any, timeout: float = 600) -> Any:
    with _browser_lock():
        return _call(_tool_tab(), method, *args, timeout=timeout)


def _check_upload(path: Path) -> str:
    """The MIME type to send `path` as, settled before anything is created in the account."""
    mime = MIME_BY_SUFFIX.get(path.suffix.lower())
    if mime is None:
        raise NblmError(
            f"Unsupported file type {path.suffix!r}; supported: {', '.join(sorted(MIME_BY_SUFFIX))}",
            EXIT_USAGE,
        )
    if not path.is_file():
        raise NblmError(f"No such file: {path}", EXIT_USAGE)
    return mime


def upload(notebook_id: str, path: Path) -> dict[str, Any]:
    mime = _check_upload(path)
    encoded = base64.b64encode(path.read_bytes()).decode()
    key = f"upload-{os.getpid()}-{time.time_ns()}"
    with _browser_lock():
        tab = _tool_tab()
        for start in range(0, len(encoded), CHUNK_CHARS):
            _eval(
                tab,
                f"String(window.nblm.stage({json.dumps(key)}, {json.dumps(encoded[start : start + CHUNK_CHARS])}))",
            )
        return _call(tab, "uploadStaged", notebook_id, key, path.name, mime)


def _claim_download(before: set[str], timeout: float = 300) -> Path:
    """The new .m4a Chrome finished saving, once its size holds steady."""
    sizes: dict[Path, int] = {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(1)
        fresh = [p for p in DOWNLOADS.iterdir() if p.name not in before]
        if any(p.suffix == ".crdownload" for p in fresh):
            continue
        finished = [p for p in fresh if p.suffix == ".m4a"]
        if len(finished) > 1:
            raise NblmError(
                f"Several new audio files appeared in {DOWNLOADS}: {[p.name for p in finished]}; move the right one by hand"
            )
        if finished:
            size = finished[0].stat().st_size
            if sizes.get(finished[0]) == size:
                return finished[0]
            sizes[finished[0]] = size
    raise NblmError(
        f"No finished .m4a appeared in {DOWNLOADS} within {timeout:.0f}s. If Chrome asks where to save files, "
        "or saves them elsewhere, set NBLM_DOWNLOADS to that folder or turn the prompt off.",
        EXIT_BROWSER,
    )


def _check_out(out: Path) -> Path:
    """Settle the destination before any browser work, creating a missing directory."""
    if out.suffix == ".m4a":
        return out
    if out.exists() and not out.is_dir():
        raise NblmError(
            f"--out must be a directory or a .m4a path, got {out}", EXIT_USAGE
        )
    out.mkdir(parents=True, exist_ok=True)
    return out


def download(notebook_id: str, artifact_id: str, out: Path) -> dict[str, Any]:
    """Save a ready audio artifact the way the app's Download item does, then move it to `out`.

    The download rendition is served as an attachment, so pointing the tool tab at it makes
    Chrome save it at full speed while the tab stays put. The streaming rendition is throttled
    to about twice playback speed.
    """
    _check_out(out)
    with _browser_lock():
        tab = _tool_tab()
        artifacts = _call(tab, "listArtifacts", notebook_id)
        artifact = next((a for a in artifacts if a["id"] == artifact_id), None)
        if artifact is None or artifact["type"] != "audio":
            raise NblmError(
                f"No audio artifact {artifact_id} in notebook {notebook_id}", EXIT_USAGE
            )
        if artifact["status"] != "ready":
            raise NblmError(
                f"Audio {artifact_id} is {artifact['status']}, not ready; run `wait` first"
            )
        media = {m["kind"]: m for m in artifact["audio"]["media"]}
        if "mp4_download" not in media:
            raise NblmError(
                f"Audio {artifact_id} lists no download rendition: {sorted(media)}"
            )
        before = {p.name for p in DOWNLOADS.iterdir()}
        _navigate(tab, media["mp4_download"]["url"])
        saved = _claim_download(before)
    destination = out / saved.name if out.is_dir() else out
    if destination.exists():
        raise NblmError(
            f"{destination} already exists; the download is still at {saved}",
            EXIT_USAGE,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(saved, destination)
    audio = artifact["audio"]
    return {
        "path": str(destination),
        "bytes": destination.stat().st_size,
        "title": artifact["title"],
        "durationSeconds": audio["durationSeconds"],
        "format": audio["format"],
        "length": audio["length"],
    }


def wait_for_audio(
    notebook_id: str, artifact_id: str, timeout: float, interval: float
) -> dict[str, Any]:
    """Poll without holding the browser lock between polls, so other commands can run."""
    deadline = time.monotonic() + timeout
    while True:
        artifacts = call("listArtifacts", notebook_id)
        artifact = next((a for a in artifacts if a["id"] == artifact_id), None)
        if artifact is None:
            raise NblmError(
                f"Artifact {artifact_id} disappeared (generation failed or it was deleted)"
            )
        if artifact["status"] == "ready":
            return artifact
        if artifact["status"] != "generating":
            raise NblmError(
                f"Artifact {artifact_id} has unmapped status {artifact['status']}; check it in the app"
            )
        if time.monotonic() > deadline:
            raise NblmError(
                f"Audio {artifact_id} still generating after {timeout:.0f}s; run `wait` again later"
            )
        print(f"waiting: {artifact_id} generating", file=sys.stderr, flush=True)
        time.sleep(interval)


def _wait_for_sources(notebook_id: str, source_ids: list[str]) -> list[dict[str, Any]]:
    return call(
        "waitForSources", notebook_id, source_ids, {"timeoutMs": 600_000}, timeout=660
    )


def _audio_options(args: argparse.Namespace) -> dict[str, Any]:
    focus = Path(args.focus_file).read_text() if args.focus_file else args.focus
    options: dict[str, Any] = {
        "format": args.format,
        "language": args.language,
        "focus": focus or "",
    }
    if args.length:
        options["length"] = args.length
    if args.source:
        options["sourceIds"] = args.source
    return options


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def command_status(_: argparse.Namespace) -> None:
    with _browser_lock():
        tab = _tool_tab()
        _print(
            {
                **_call(tab, "status"),
                "usage": _call(tab, "usage"),
                "tab": dataclasses.asdict(tab),
            }
        )


def command_list(args: argparse.Namespace) -> None:
    _print(call("listNotebooks")[: args.limit])


def command_show(args: argparse.Namespace) -> None:
    _print(
        {
            **call("getNotebook", args.notebook),
            "artifacts": call("listArtifacts", args.notebook),
        }
    )


def command_create(args: argparse.Namespace) -> None:
    _print(call("createNotebook", args.title))


def command_rename(args: argparse.Namespace) -> None:
    _print(call("renameNotebook", args.notebook, args.title))


def command_upload(args: argparse.Namespace) -> None:
    paths = [Path(path) for path in args.files]
    for path in paths:
        _check_upload(path)
    uploaded = [upload(args.notebook, path) for path in paths]
    if args.wait:
        uploaded = _wait_for_sources(args.notebook, [s["id"] for s in uploaded])
    _print(uploaded)


def command_add_url(args: argparse.Namespace) -> None:
    _print(call("addUrls", args.notebook, args.urls))


def command_audio(args: argparse.Namespace) -> None:
    if args.out:
        _check_out(Path(args.out))
    created = call("createAudio", args.notebook, _audio_options(args))
    if args.out:
        wait_for_audio(args.notebook, created["id"], args.timeout, args.interval)
        created["download"] = download(args.notebook, created["id"], Path(args.out))
    _print(created)


def command_artifacts(args: argparse.Namespace) -> None:
    _print(call("listArtifacts", args.notebook))


def command_wait(args: argparse.Namespace) -> None:
    _print(wait_for_audio(args.notebook, args.artifact, args.timeout, args.interval))


def command_download(args: argparse.Namespace) -> None:
    _print(download(args.notebook, args.artifact, Path(args.out)))


def command_paper_audio(args: argparse.Namespace) -> None:
    path = Path(args.file)
    _check_upload(path)
    _check_out(Path(args.out))
    notebook = call("createNotebook", args.title or path.stem)
    source = upload(notebook["id"], path)
    _wait_for_sources(notebook["id"], [source["id"]])
    created = call("createAudio", notebook["id"], _audio_options(args))
    print(
        f"generating: notebook {notebook['id']} artifact {created['id']}",
        file=sys.stderr,
        flush=True,
    )
    wait_for_audio(notebook["id"], created["id"], args.timeout, args.interval)
    saved = download(notebook["id"], created["id"], Path(args.out))
    _print(
        {
            "notebook": {
                "id": notebook["id"],
                "title": notebook["title"],
                "url": f"{HOME_URL}notebook/{notebook['id']}",
            },
            "source": source,
            "audio": created,
            "download": saved,
        }
    )


def command_close(_: argparse.Namespace) -> None:
    with _browser_lock():
        state = _load_state()
        tab = Tab(state["window_id"], state["tab_id"]) if state else None
        closed = bool(tab and _tab_url(tab))
        if closed:
            _osascript(f'tell application "{CHROME_APP}" to close ({_tab_ref(tab)})')
        STATE_FILE.unlink(missing_ok=True)
    _print({"closed": closed, "note": "the next command opens a fresh tool tab"})


def _add_audio_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=["deep_dive", "brief", "critique", "debate"],
        default="deep_dive",
    )
    parser.add_argument(
        "--length",
        choices=["short", "default", "long"],
        help="deep_dive: short|default|long; critique, debate: short|default; brief: omit",
    )
    focus = parser.add_mutually_exclusive_group()
    focus.add_argument(
        "--focus",
        help="instructions for the AI hosts (the 'What should the AI hosts focus on' box)",
    )
    focus.add_argument("--focus-file", help="read the host instructions from this file")
    parser.add_argument(
        "--language", default="en", help="output language code (default en)"
    )
    parser.add_argument(
        "--timeout", type=float, default=3600, help="seconds to wait for generation"
    )
    parser.add_argument(
        "--interval", type=float, default=20, help="seconds between status polls"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "status", help="check the tool tab, account, and usage meter"
    ).set_defaults(run=command_status)
    listing = commands.add_parser("list", help="list notebooks, most recent first")
    listing.add_argument("--limit", type=int, default=20)
    listing.set_defaults(run=command_list)
    show = commands.add_parser("show", help="show a notebook's sources and artifacts")
    show.add_argument("notebook")
    show.set_defaults(run=command_show)
    create = commands.add_parser("create", help="create a notebook")
    create.add_argument("--title")
    create.set_defaults(run=command_create)
    rename = commands.add_parser("rename", help="rename a notebook")
    rename.add_argument("notebook")
    rename.add_argument("title")
    rename.set_defaults(run=command_rename)
    upload_parser = commands.add_parser("upload", help="upload local files as sources")
    upload_parser.add_argument("notebook")
    upload_parser.add_argument("files", nargs="+")
    upload_parser.add_argument(
        "--wait", action="store_true", help="wait until the sources finish processing"
    )
    upload_parser.set_defaults(run=command_upload)
    add_url = commands.add_parser(
        "add-url", help="add website or YouTube URLs as sources"
    )
    add_url.add_argument("notebook")
    add_url.add_argument("urls", nargs="+")
    add_url.set_defaults(run=command_add_url)
    audio = commands.add_parser(
        "audio", help="start an Audio Overview (and optionally wait and download)"
    )
    audio.add_argument("notebook")
    audio.add_argument(
        "--source",
        action="append",
        help="source id to include (repeat); default all ready sources",
    )
    audio.add_argument(
        "--out",
        help="wait for the audio, then save it into this directory (or to this .m4a path)",
    )
    _add_audio_flags(audio)
    audio.set_defaults(run=command_audio)
    artifacts = commands.add_parser(
        "artifacts", help="list a notebook's studio artifacts"
    )
    artifacts.add_argument("notebook")
    artifacts.set_defaults(run=command_artifacts)
    wait = commands.add_parser("wait", help="wait for an audio artifact to finish")
    wait.add_argument("notebook")
    wait.add_argument("artifact")
    wait.add_argument("--timeout", type=float, default=3600)
    wait.add_argument("--interval", type=float, default=20)
    wait.set_defaults(run=command_wait)
    download_parser = commands.add_parser(
        "download", help="download a ready audio artifact as .m4a"
    )
    download_parser.add_argument("notebook")
    download_parser.add_argument("artifact")
    download_parser.add_argument(
        "--out", required=True, help="directory (created if missing), or a .m4a path"
    )
    download_parser.set_defaults(run=command_download)
    paper = commands.add_parser(
        "paper-audio", help="new notebook + upload + audio + wait + download, in one go"
    )
    paper.add_argument("file")
    paper.add_argument("--title", help="notebook title (default: file name stem)")
    paper.add_argument(
        "--out",
        required=True,
        help="directory (created if missing), or a .m4a path, for the audio",
    )
    paper.add_argument("--source", action="append", help=argparse.SUPPRESS)
    _add_audio_flags(paper)
    paper.set_defaults(run=command_paper_audio)
    commands.add_parser(
        "close", help="close the tool tab; the next command opens a fresh one"
    ).set_defaults(run=command_close)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        args.run(args)
    except NblmError as error:
        print(f"nblm: {error}", file=sys.stderr)
        return error.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main())
