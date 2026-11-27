#!/usr/bin/env python3
"""Check, capture and trace chalk-talk board lessons (single-file HTML boards).

  check   load the board in headless Chromium, seek each beat on a frozen clock,
          save PNGs and print one DEFECT line per failed assertion
  render  capture an MP4 or GIF on a virtual clock and encode it with ffmpeg
  trace   turn a PNG into a coarse silhouette grid (at most 32 x 32 cells)

check and render need Playwright with Chromium. When this Python cannot import
Playwright, the tool creates ~/.cache/chalk-talk/venv, installs Playwright and
Chromium there once, and re-runs itself inside it. trace needs only the
standard library.

Board contract: the page defines window.chalkTalk with duration, beats,
seek(t), play(), pause(), replay() and state(), and marks its parts with
data-ct="board|play|replay|scrub" (see assets/starter.html).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any, Iterator
import zlib

MAX_GRID = 32
HEIGHT_TOLERANCE_PX = 2.0
REEXEC_FLAG = "CHALK_TALK_BOOTSTRAPPED"
LOCAL_SCHEMES = ("file:", "data:", "blob:", "about:")
CONTROLS = ('[data-ct="board"]', '[data-ct="play"]', '[data-ct="replay"]', '[data-ct="scrub"]')


class ToolError(Exception):
    """An expected, user-actionable failure; printed as one `error:` line."""


class TraceError(ToolError):
    """The image cannot be read or holds no traceable shape."""


@dataclass(frozen=True)
class Action:
    selector: str
    at: float


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    luma: list[float]
    alpha: list[int]


# ----------------------------------------------------------------- arguments

def _seconds(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of seconds: {raw!r}") from None
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"seconds must be finite and >= 0: {raw!r}")
    return value


def parse_times(raw: str) -> list[float]:
    """`0.2,4,9.5` -> [0.2, 4.0, 9.5]; sorted, duplicates dropped."""
    return sorted({_seconds(part.strip()) for part in raw.split(",")})


def parse_viewport(raw: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{3,4})x(\d{3,4})", raw.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"viewport must look like 1200x720: {raw!r}")
    width, height = int(match.group(1)), int(match.group(2))
    if not (240 <= width <= 4096 and 240 <= height <= 4096):
        raise argparse.ArgumentTypeError(f"viewport sides must be 240-4096 px: {raw!r}")
    return width, height


def parse_action(raw: str) -> Action:
    """`click:<css selector>@<seconds>`, for example `click:#jitter@3.5`."""
    kind, _, rest = raw.partition(":")
    selector, _, at = rest.rpartition("@")
    if kind != "click" or not selector.strip() or not at:
        raise argparse.ArgumentTypeError(f"action must look like click:<selector>@<seconds>: {raw!r}")
    return Action(selector.strip(), _seconds(at))


def _bounded(kind: type, low: float, high: float, label: str):
    def parse(raw: str):
        try:
            value = kind(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{label} must be a number: {raw!r}") from None
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"{label} must be between {low:g} and {high:g}: {raw!r}")
        return value
    return parse


# ----------------------------------------------------------------- Playwright

def venv_dir() -> Path:
    return Path.home() / ".cache" / "chalk-talk" / "venv"


def _say(message: str) -> None:
    print(f"chalk-talk: {message}", file=sys.stderr, flush=True)


def _run_step(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ToolError(f"bootstrap step failed: {' '.join(command)} ({exc})") from exc


def bootstrap_and_reexec() -> None:
    """Create the private venv with Playwright and Chromium, then re-run this command in it."""
    venv = venv_dir()
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
    if not python.exists():
        _say(f"Playwright is not importable by {sys.executable}; creating {venv}")
        venv.parent.mkdir(parents=True, exist_ok=True)
        _run_step([sys.executable, "-m", "venv", str(venv)])
    probe = subprocess.run([str(python), "-c", "import playwright"], capture_output=True)
    if probe.returncode != 0:
        _say("installing the playwright package into it (one time)")
        _run_step([str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "playwright"])
    marker = venv / ".chromium-installed"
    if not marker.exists():
        _say("installing Playwright's Chromium (one time; an existing download is reused)")
        _run_step([str(python), "-m", "playwright", "install", "chromium"])
        marker.write_text("ok\n")
    _say(f"re-running inside {venv}")
    os.execve(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]],
              {**os.environ, REEXEC_FLAG: "1"})


def import_playwright() -> tuple[Any, type[BaseException]]:
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        if os.environ.get(REEXEC_FLAG):
            raise ToolError(f"Playwright is still not importable in {sys.prefix}; delete {venv_dir()} and retry") from None
        bootstrap_and_reexec()
        raise AssertionError("unreachable: execve returned")
    return sync_playwright, Error


@dataclass
class Session:
    page: Any
    problems: list[str]


@contextmanager
def open_board(html: Path, viewport: tuple[int, int], *, reduced_motion: bool = False) -> Iterator[Session]:
    """Load the board with a paused virtual clock; collect console errors and external requests."""
    sync_playwright, PlaywrightError = import_playwright()
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            raise ToolError(f"cannot launch Chromium ({first}); run `{sys.executable} -m playwright install chromium`") from exc
        try:
            context = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                device_scale_factor=1,
                reduced_motion="reduce" if reduced_motion else "no-preference",
            )
            page = context.new_page()
            problems: list[str] = []
            page.on("console", lambda message: problems.append(f"console error: {message.text}")
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
            page.on("request", lambda request: None if request.url.startswith(LOCAL_SCHEMES)
                    else problems.append(f"external request: {request.url}"))
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            page.clock.install(time=start)
            page.clock.pause_at(start)
            page.goto(html.resolve().as_uri(), wait_until="load")
            yield Session(page, problems)
        finally:
            browser.close()


PROBE_JS = """() => {
  const ct = window.chalkTalk;
  const hook = !!ct && ['seek', 'state', 'replay', 'play', 'pause'].every((k) => typeof ct[k] === 'function');
  return {
    hook,
    duration: hook ? Number(ct.duration) : NaN,
    beats: hook && Array.isArray(ct.beats) ? ct.beats.map((b) => [Number(b.start), Number(b.end)]) : [],
    missing: %s.filter((s) => !document.querySelector(s)),
  };
}""" % json.dumps(list(CONTROLS))

SIGNATURE_JS = """() => {
  const html = document.querySelector('[data-ct="board"]').innerHTML;
  let h = 2166136261;
  for (let i = 0; i < html.length; i++) { h ^= html.charCodeAt(i); h = Math.imul(h, 16777619); }
  return { ...window.chalkTalk.state(), signature: (h >>> 0).toString(16) + ':' + html.length };
}"""

MEASURE_JS = """(at) => {
  window.chalkTalk.seek(at);
  const board = document.querySelector('[data-ct="board"]');
  const root = document.documentElement;
  const out = { overflow: root.scrollWidth - root.clientWidth, height: board.getBoundingClientRect().height,
    slots: [], clipped: [], overlaps: [], animations: 0 };
  for (const slot of board.querySelectorAll('[data-ct-slot]')) {
    if (slot.scrollHeight > slot.clientHeight + 1 || slot.scrollWidth > slot.clientWidth + 1)
      out.slots.push(slot.dataset.ctSlot + ' "' + slot.textContent.trim().slice(0, 50) + '"');
  }
  const svg = board.querySelector('svg');
  if (svg) {
    const frame = svg.getBoundingClientRect();
    const opacity = (node) => {
      let value = 1;
      for (let n = node; n && n !== svg; n = n.parentElement) {
        const style = getComputedStyle(n);
        if (style.display === 'none' || style.visibility === 'hidden') return 0;
        value *= parseFloat(style.opacity);
      }
      return value;
    };
    const solid = [];
    for (const node of svg.querySelectorAll('text')) {
      const label = node.textContent.trim();
      const seen = opacity(node);
      if (!label || seen < 0.05) continue;
      const r = node.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      if (r.left < frame.left - 1 || r.right > frame.right + 1 || r.top < frame.top - 1 || r.bottom > frame.bottom + 1)
        out.clipped.push(label.slice(0, 40));
      if (seen >= 0.9) solid.push([label, r]);
    }
    for (let i = 0; i < solid.length; i++) for (let j = i + 1; j < solid.length; j++) {
      const a = solid[i][1], b = solid[j][1];
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w > 0 && h > 0 && w * h > 0.3 * Math.min(a.width * a.height, b.width * b.height))
        out.overlaps.push(solid[i][0].slice(0, 30) + '" and "' + solid[j][0].slice(0, 30));
    }
  }
  out.animations = document.getAnimations().filter((a) => a.playState === 'running'
    && a.effect && a.effect.target && board.contains(a.effect.target)).length;
  return out;
}"""

BOARD_RECT_JS = """() => {
  const r = document.querySelector('[data-ct="board"]').getBoundingClientRect();
  return { x: Math.floor(r.left), y: Math.floor(r.top + scrollY), width: Math.ceil(r.width), height: Math.ceil(r.height) };
}"""

CLICK_JS = """(selector) => {
  const node = document.querySelector(selector);
  if (!node) return false;
  node.click();
  return true;
}"""


def _probe(session: Session) -> tuple[list[str], dict[str, Any]]:
    probe = session.page.evaluate(PROBE_JS)
    if not probe["hook"]:
        return ["DEFECT: page does not define window.chalkTalk with seek/state/replay/play/pause "
                "(keep the board contract from assets/starter.html)"], probe
    defects = [f"DEFECT: missing control {selector}" for selector in probe["missing"]]
    duration = probe["duration"]
    if not (isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0):
        defects.append(f"DEFECT: window.chalkTalk.duration must be a positive number of seconds, got {duration!r}")
    return defects, probe


def default_times(beats: list[list[float]]) -> list[float]:
    """One settled frame per beat: 85 % of the way through it."""
    return sorted({round(start + 0.85 * (end - start), 2) for start, end in beats if end > start})


def frame_defects(measured: dict[str, Any]) -> list[str]:
    """Failures seen in one measured frame, without the frame time."""
    defects = []
    if measured["overflow"] > 0:
        defects.append(f"horizontal overflow of {measured['overflow']} px")
    defects += [f"status slot overflows its fixed box: {slot}" for slot in measured["slots"]]
    defects += [f'visible text clipped by the board edge: "{label}"' for label in measured["clipped"]]
    defects += [f'visible labels overlap: "{pair}"' for pair in measured["overlaps"]]
    if measured["animations"]:
        defects.append("CSS animations or transitions run inside the board; drive motion from render(t)")
    return defects


def check_board(html: Path, times: list[float] | None, out_dir: Path,
                viewport: tuple[int, int]) -> tuple[list[str], list[str]]:
    """Return (report lines, DEFECT lines) for one board."""
    report: list[str] = []
    with open_board(html, viewport) as session:
        page = session.page
        defects, probe = _probe(session)
        if defects:
            return report, defects + [f"DEFECT: {problem}" for problem in session.problems]
        duration = float(probe["duration"])
        beats = probe["beats"]
        wanted = times if times is not None else default_times(beats)
        if not wanted:
            defects.append("DEFECT: no --at times given and window.chalkTalk.beats is empty")
        defects += [f"DEFECT: --at {at:g} is past the board duration {duration:g} s" for at in wanted if at > duration]
        frames = [("start", 0.0)]
        frames += [(f"beat-{index:02d}", at) for index, at in enumerate((at for at in wanted if at <= duration), 1)]
        frames.append(("end", duration))
        report.append(f"board {html} ({duration:g} s, {len(beats)} beats, viewport {viewport[0]}x{viewport[1]})")
        heights: list[tuple[float, float]] = []
        seen_at: dict[str, list[str]] = {}
        for index, (name, at) in enumerate(frames):
            measured = page.evaluate(MEASURE_JS, at)
            path = out_dir / f"{index:02d}-{name}-t{at:.2f}.png"
            page.screenshot(path=str(path), full_page=True)
            heights.append((measured["height"], at))
            for message in frame_defects(measured):
                seen_at.setdefault(message, []).append(f"{at:.2f}")
            report.append(f"  {name:<9} t={at:6.2f}  board {measured['height']:.1f} px  {path}")
        defects += [f"DEFECT: {message} at t={', '.join(ats)} s" for message, ats in seen_at.items()]
        low, high = min(heights), max(heights)
        if high[0] - low[0] > HEIGHT_TOLERANCE_PX:
            defects.append(f"DEFECT: board height changes by {high[0] - low[0]:.1f} px "
                           f"({low[0]:.1f} px at t={low[1]:g}, {high[0]:.1f} px at t={high[1]:g}); fix slot heights")

        page.evaluate("() => window.chalkTalk.seek(0)")
        start = page.evaluate(SIGNATURE_JS)
        page.evaluate("(end) => window.chalkTalk.seek(end)", duration)
        if page.evaluate(CLICK_JS, CONTROLS[2]):
            after = page.evaluate(SIGNATURE_JS)
            path = out_dir / f"{len(frames):02d}-replay.png"
            page.screenshot(path=str(path), full_page=True)
            report.append(f"  {'replay':<9} t={after['t']:6.2f}  playing={after['playing']}  {path}")
            if abs(after["t"]) > 1e-6:
                defects.append(f"DEFECT: Replay leaves t at {after['t']:.3f} s instead of 0")
            elif after["signature"] != start["signature"]:
                defects.append("DEFECT: Replay does not restore the exact t=0 board; render(t) depends on state other than t")
            if not after["playing"]:
                defects.append("DEFECT: Replay does not start playback")
            page.clock.run_for(1000)
            moved = page.evaluate("() => window.chalkTalk.state().t") - after["t"]
            if after["playing"] and not 0.5 <= moved <= 1.5:
                defects.append(f"DEFECT: one second of clock moved playback by {moved:.2f} s; "
                               "drive playback from requestAnimationFrame timestamps")
        print_state = page.evaluate("() => { dispatchEvent(new Event('beforeprint')); return window.chalkTalk.state(); }")
        if abs(print_state["t"] - duration) > 1e-6:
            defects.append(f"DEFECT: beforeprint shows t={print_state['t']:.2f} s instead of the final frame")
        page.evaluate("() => dispatchEvent(new Event('afterprint'))")
        defects += [f"DEFECT: {problem}" for problem in session.problems]

    with open_board(html, viewport, reduced_motion=True) as still:
        state = still.page.evaluate("() => window.chalkTalk && window.chalkTalk.state()")
        if not state or abs(state["t"] - duration) > 1e-6 or state["playing"]:
            defects.append("DEFECT: with prefers-reduced-motion the board must open paused on its final frame")
        defects += [f"DEFECT: {problem} (reduced-motion load)" for problem in still.problems]
    return report, list(dict.fromkeys(defects))


def command_check(args: argparse.Namespace) -> int:
    html = _existing(args.html)
    out_dir = args.dir or Path(tempfile.mkdtemp(prefix=f"chalk-talk-{html.stem}-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        report, defects = check_board(html, args.at, out_dir, args.viewport)
    except Exception as exc:  # a script error while driving the page surfaces as Playwright's own Error
        if not type(exc).__module__.startswith("playwright"):
            raise
        print(f"DEFECT: the page threw while being driven: {(str(exc).strip().splitlines() or [type(exc).__name__])[0]}")
        return 1
    print("\n".join(report))
    for line in defects:
        print(line)
    print(f"check: {len(defects)} defect(s); PNGs in {out_dir}")
    return 1 if defects else 0


# ------------------------------------------------------------------- render

MP4_ENCODERS = (
    ("libx264", ["-crf", "20"]),
    ("libopenh264", ["-b:v", "4M"]),
    ("h264_videotoolbox", ["-b:v", "6M"]),
    ("mpeg4", ["-q:v", "3"]),
)


def pick_mp4_encoder(listing: str) -> tuple[str, list[str]]:
    """Best available MP4 video encoder from `ffmpeg -encoders` output."""
    names = {line.split()[1] for line in listing.splitlines() if len(line.split()) > 1}
    for name, options in MP4_ENCODERS:
        if name in names:
            return name, options
    raise ToolError("ffmpeg has no MP4 video encoder (libx264, libopenh264, h264_videotoolbox or mpeg4); "
                    "use --format gif")


def encode_command(ffmpeg: str, pattern: str, rate: int, fmt: str, out: Path,
                   encoder: tuple[str, list[str]] = MP4_ENCODERS[0]) -> list[str]:
    base = [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(rate), "-i", pattern]
    if fmt == "gif":
        palette = "split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a"
        return [*base, "-vf", palette, "-loop", "0", str(out)]
    return [*base, "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", encoder[0], *encoder[1],
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]


def command_render(args: argparse.Namespace) -> int:
    html = _existing(args.html)
    fmt = args.format or ("gif" if args.out.suffix.lower() == ".gif" else "mp4")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ToolError("ffmpeg is not on PATH; install it (for example `brew install ffmpeg` or "
                        "`apt install ffmpeg`) or skip video capture")
    encoder = MP4_ENCODERS[0]
    if fmt == "mp4":
        listing = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
        encoder = pick_mp4_encoder(listing.stdout)
    with open_board(html, args.viewport) as session, tempfile.TemporaryDirectory(prefix="chalk-talk-frames-") as tmp:
        defects, probe = _probe(session)
        if defects:
            raise ToolError(defects[0].removeprefix("DEFECT: "))
        page = session.page
        total = args.duration if args.duration is not None else float(probe["duration"]) + 1.0
        late = [action for action in args.action if action.at > total]
        if late:
            raise ToolError(f"--action at {late[0].at:g} s is past the capture length {total:g} s")
        clip = None if args.page else page.evaluate(BOARD_RECT_JS)
        pending = sorted(args.action, key=lambda action: action.at)
        page.evaluate("() => window.chalkTalk.replay()")
        count, elapsed = max(1, round(total * args.rate)), 0
        for index in range(count):
            while pending and pending[0].at <= index / args.rate + 1e-9:
                action = pending.pop(0)
                if not page.evaluate(CLICK_JS, action.selector):
                    raise ToolError(f"--action selector matched nothing: {action.selector}")
            page.screenshot(path=os.path.join(tmp, f"f{index:05d}.png"), clip=clip, full_page=clip is not None)
            target = round((index + 1) * 1000 / args.rate)
            page.clock.run_for(target - elapsed)
            elapsed = target
        for problem in session.problems:
            print(f"warning: {problem}", file=sys.stderr)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        command = encode_command(ffmpeg, os.path.join(tmp, "f%05d.png"), args.rate, fmt, args.out, encoder)
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise ToolError(f"ffmpeg failed: {result.stderr.strip()[-400:]}")
    size = args.out.stat().st_size
    codec = "gif" if fmt == "gif" else encoder[0]
    print(f"render: {count} frames at {args.rate} fps ({total:g} s virtual) -> {args.out} ({codec}, {size / 1e6:.2f} MB)")
    return 0


# -------------------------------------------------------------------- trace

def _paeth(left: int, up: int, upleft: int) -> int:
    estimate = left + up - upleft
    da, db, dc = abs(estimate - left), abs(estimate - up), abs(estimate - upleft)
    if da <= db and da <= dc:
        return left
    return up if db <= dc else upleft


def unfilter(raw: bytes, height: int, stride: int, bpp: int) -> list[bytearray]:
    """Undo PNG scanline filters 0-4."""
    if len(raw) < height * (stride + 1):
        raise TraceError("PNG image data is truncated")
    rows: list[bytearray] = []
    prior = bytearray(stride)
    for y in range(height):
        offset = y * (stride + 1)
        kind, line = raw[offset], bytearray(raw[offset + 1:offset + 1 + stride])
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + prior[i]) & 255
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prior[i]) >> 1)) & 255
        elif kind == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upleft = prior[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prior[i], upleft)) & 255
        elif kind != 0:
            raise TraceError(f"unknown PNG filter type {kind} on row {y}")
        rows.append(line)
        prior = line
    return rows


def _samples(row: bytes, count: int, depth: int) -> list[int]:
    if depth == 8:
        return list(row[:count])
    if depth == 16:
        return [(row[2 * i] << 8) | row[2 * i + 1] for i in range(count)]
    mask = (1 << depth) - 1
    values = [(byte >> shift) & mask for byte in row for shift in range(8 - depth, -1, -depth)]
    return values[:count]


def read_png(path: Path) -> Raster:
    """Decode a non-interlaced PNG (any colour type, bit depth 1-16) with zlib only."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TraceError(f"cannot read {path}: {exc}") from exc
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise TraceError(f"{path} is not a PNG; convert it first, for example `ffmpeg -i in.jpg out.png`")
    header, palette, transparency, chunks, offset = None, b"", None, [], 8
    while offset + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[offset:offset + 8])
        body = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            transparency = body
        elif kind == b"IDAT":
            chunks.append(body)
        elif kind == b"IEND":
            break
    if header is None or not chunks:
        raise TraceError(f"{path} has no IHDR or IDAT chunk")
    width, height, depth, color, _, _, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    allowed = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if channels is None or depth not in allowed[color]:
        raise TraceError(f"unsupported PNG colour type {color} with bit depth {depth}")
    if interlace:
        raise TraceError("interlaced PNG is not supported; re-save it without interlacing")
    if width * height > 16_000_000:
        raise TraceError("image is too large; downscale it first, for example `ffmpeg -i big.png -vf scale=512:-1 small.png`")
    try:
        raw = zlib.decompress(b"".join(chunks))
    except zlib.error as exc:
        raise TraceError(f"corrupt PNG image data: {exc}") from exc
    bits = channels * depth
    rows = unfilter(raw, height, (width * bits + 7) // 8, max(1, bits // 8))
    top = (1 << depth) - 1
    key = None
    if transparency and color == 0:
        key = (struct.unpack(">H", transparency[:2])[0],)
    elif transparency and color == 2:
        key = struct.unpack(">HHH", transparency[:6])
    luma: list[float] = []
    alpha: list[int] = []
    for row in rows:
        values = _samples(row, width * channels, depth)
        for x in range(width):
            pixel = values[x * channels:(x + 1) * channels]
            if color == 3:
                index = pixel[0]
                if 3 * index + 3 > len(palette):
                    raise TraceError(f"palette index {index} is out of range")
                r, g, b = palette[3 * index:3 * index + 3]
                a = transparency[index] if transparency and index < len(transparency) else 255
            else:
                scaled = [value * 255 / top for value in pixel]
                if color in (0, 4):
                    r = g = b = scaled[0]
                else:
                    r, g, b = scaled[:3]
                if color in (4, 6):
                    a = round(scaled[-1])
                else:
                    a = 0 if key is not None and tuple(pixel[:len(key)]) == key else 255
            luma.append(0.2126 * r + 0.7152 * g + 0.0722 * b)
            alpha.append(a)
    return Raster(width, height, luma, alpha)


def otsu_threshold(values: list[float]) -> int:
    histogram = [0] * 256
    for value in values:
        histogram[min(255, max(0, int(value)))] += 1
    total, weighted = len(values), sum(i * count for i, count in enumerate(histogram))
    best, best_score, below, below_sum = 0, -1.0, 0, 0
    for level, count in enumerate(histogram):
        below += count
        if below == 0:
            continue
        above = total - below
        if above == 0:
            break
        below_sum += level * count
        spread = below * above * (below_sum / below - (weighted - below_sum) / above) ** 2
        if spread > best_score:
            best, best_score = level, spread
    return best


def foreground(raster: Raster, invert: bool = False) -> list[bool]:
    """Opaque pixels when the image has real transparency, else the side of an Otsu split away from the border."""
    if max(raster.alpha) - min(raster.alpha) >= 64:
        mask = [a >= 128 for a in raster.alpha]
    else:
        threshold = otsu_threshold(raster.luma)
        w, h = raster.width, raster.height
        border = [raster.luma[x] for x in range(w)] + [raster.luma[(h - 1) * w + x] for x in range(w)]
        border += [raster.luma[y * w] for y in range(h)] + [raster.luma[y * w + w - 1] for y in range(h)]
        dark_ink = sum(border) / len(border) > threshold
        mask = [(int(value) <= threshold) == dark_ink for value in raster.luma]  # same binning as the histogram
    return [not on for on in mask] if invert else mask


def silhouette(raster: Raster, columns: int = 24, *, fill: float = 0.4,
               invert: bool = False, crop: bool = True) -> list[str]:
    """Rows of '#' (shape) and '.' (empty), at most 32 x 32, keeping the shape's aspect ratio."""
    if not 1 <= columns <= MAX_GRID:
        raise TraceError(f"grid must be 1-{MAX_GRID} columns")
    mask, w = foreground(raster, invert), raster.width
    if crop:
        xs = [i % w for i, on in enumerate(mask) if on]
        ys = [i // w for i, on in enumerate(mask) if on]
        if not xs:
            raise TraceError("no foreground found; try --invert or a higher-contrast image")
        x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    else:
        x0, x1, y0, y1 = 0, w, 0, raster.height
    box_w, box_h = x1 - x0, y1 - y0
    rows = max(1, round(columns * box_h / box_w))
    if rows > MAX_GRID:
        rows, columns = MAX_GRID, max(1, round(MAX_GRID * box_w / box_h))

    def edges(start: int, size: int, cells: int) -> list[tuple[int, int]]:
        cuts = [start + (size * k) // cells for k in range(cells + 1)]
        return [(a, max(a + 1, b)) for a, b in zip(cuts, cuts[1:])]

    grid = []
    for top, bottom in edges(y0, box_h, rows):
        line = []
        for left, right in edges(x0, box_w, columns):
            hits = sum(mask[y * w + x] for y in range(top, bottom) for x in range(left, right))
            line.append("#" if hits >= fill * (bottom - top) * (right - left) else ".")
        grid.append("".join(line))
    return grid


def command_trace(args: argparse.Namespace) -> int:
    raster = read_png(_existing(args.image))
    grid = silhouette(raster, args.grid, fill=args.fill, invert=args.invert, crop=not args.no_crop)
    if args.format == "json":
        print(json.dumps({"columns": len(grid[0]), "rows": len(grid), "cells": grid}))
    else:
        print("\n".join(grid))
    print(f"trace: {len(grid[0])}x{len(grid)} grid from a {raster.width}x{raster.height} image", file=sys.stderr)
    return 0


# --------------------------------------------------------------------- main

def _existing(path: Path) -> Path:
    if not path.is_file():
        raise ToolError(f"no such file: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="board_tool.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True, metavar="{check,render,trace}")

    check = commands.add_parser("check", help="verify live beats in headless Chromium and save PNGs",
                                description="Seek every beat on a frozen clock, save PNGs, and assert: no console or "
                                "page errors or external requests; no horizontal overflow; no clipped, overlapping or "
                                "overflowing text; board height within 2 px; Replay restores t=0 exactly and plays; "
                                "print and reduced motion show the final frame. Exit 1 with one DEFECT line each.")
    check.add_argument("html", type=Path, help="the board HTML file")
    check.add_argument("--at", type=parse_times, metavar="T1,T2,...",
                       help="beat times in seconds (default: 85%% through every beat in window.chalkTalk.beats)")
    check.add_argument("--dir", type=Path, help="directory for PNGs (default: a new temporary directory)")
    check.add_argument("--viewport", type=parse_viewport, default=(1200, 800), metavar="WxH",
                       help="browser viewport (default 1200x800)")

    render = commands.add_parser("render", help="capture an MP4 or GIF on a virtual clock (needs ffmpeg)",
                                 description="Replay the board from t=0 on Playwright's virtual clock, screenshot "
                                 "every frame, apply optional clicks, and encode with ffmpeg.")
    render.add_argument("html", type=Path, help="the board HTML file")
    render.add_argument("--format", choices=("mp4", "gif"), help="default: from the --out suffix, else mp4")
    render.add_argument("--duration", type=_bounded(float, 0.1, 600, "--duration"),
                        help="seconds to capture (default: board duration + 1)")
    render.add_argument("--rate", type=_bounded(int, 1, 60, "--rate"), default=30, help="frames per second (default 30)")
    render.add_argument("--viewport", type=parse_viewport, default=(1200, 720), metavar="WxH",
                        help="browser viewport (default 1200x720)")
    render.add_argument("--action", type=parse_action, action="append", default=[], metavar="click:SELECTOR@SEC",
                        help="click an element at a capture time; repeatable")
    render.add_argument("--page", action="store_true", help="capture the whole viewport, not only the board")
    render.add_argument("--out", type=Path, required=True, help="output .mp4 or .gif path")

    trace = commands.add_parser("trace", help="coarse silhouette grid from a PNG (stdlib only)",
                                description="Print rows of # and . tracing the main shape of a PNG, cropped to the "
                                "shape and at most 32 x 32 cells, for grid silhouettes on a board.")
    trace.add_argument("image", type=Path, help="a non-interlaced PNG")
    trace.add_argument("--grid", type=_bounded(int, 2, MAX_GRID, "--grid"), default=24,
                       help=f"columns, 2-{MAX_GRID} (default 24); rows follow the aspect ratio")
    trace.add_argument("--fill", type=_bounded(float, 0.01, 1.0, "--fill"), default=0.4,
                       help="share of a cell that must be shape to mark it (default 0.4)")
    trace.add_argument("--invert", action="store_true", help="trace the background instead")
    trace.add_argument("--no-crop", action="store_true", help="keep the whole image instead of cropping to the shape")
    trace.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"check": command_check, "render": command_render, "trace": command_trace}
    try:
        return handlers[args.command](args)
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
