"""chalk-talk skill: package shape, explicit-only metadata, registry record, projection, and
board_tool.py argument parsing and PNG tracing. No browser is launched."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from skill_system import SkillSystem, content_hash
from skill_system.model import _parse_frontmatter, _parse_quoted_yaml, validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "chalk-talk"
TOOL = SKILL_ROOT / "scripts" / "board_tool.py"
FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "assets/starter.html",
    "references/motion-and-layout.md",
    "scripts/board_tool.py",
}
SQUARE = ["........", "........", "..####..", "..####..", "..####..", "..####..", "........", "........"]


def load_tool():
    """Import board_tool.py without writing bytecode into the canonical skill tree."""
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("chalk_talk_board_tool", TOOL)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


board_tool = load_tool()


def paeth(left: int, up: int, upleft: int) -> int:
    estimate = left + up - upleft
    da, db, dc = abs(estimate - left), abs(estimate - up), abs(estimate - upleft)
    return left if da <= db and da <= dc else (up if db <= dc else upleft)


def filtered(kind: int, raw: bytes, prior: bytes, bpp: int) -> bytes:
    out = bytearray()
    for i, value in enumerate(raw):
        left = raw[i - bpp] if i >= bpp else 0
        upleft = prior[i - bpp] if i >= bpp else 0
        predictors = (0, left, prior[i], (left + prior[i]) // 2, paeth(left, prior[i], upleft))
        out.append((value - predictors[kind]) & 255)
    return bytes(out)


def png(width: int, height: int, rows: list[bytes], *, color: int = 6, depth: int = 8,
        palette: bytes = b"", filters: tuple[int, ...] = (0,), interlace: int = 0) -> bytes:
    """Encode raw scanlines as a PNG, cycling through the given filter types row by row."""
    bpp = max(1, {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color] * depth // 8)
    data, prior = bytearray(), bytes(len(rows[0]))
    for y, raw in enumerate(rows):
        kind = filters[y % len(filters)]
        data.append(kind)
        data += filtered(kind, raw, prior, bpp)
        prior = raw

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace))
    if palette:
        out += chunk(b"PLTE", palette)
    return out + chunk(b"IDAT", zlib.compress(bytes(data))) + chunk(b"IEND", b"")


def in_square(x: int, y: int) -> bool:
    return 2 <= x <= 5 and 2 <= y <= 5


def gray_value(x: int, y: int, *, light_ink: bool = False) -> int:
    """A textured image (so every filter type has real residuals) with a solid 4x4 square."""
    ink, paper = 10 + (x * 7 + y * 3) % 30, 200 + (x * 5 + y * 11) % 50
    if light_ink:
        ink, paper = 255 - ink, 255 - paper
    return ink if in_square(x, y) else paper


class ChalkTalkPackageTests(unittest.TestCase):
    def test_package_is_exactly_the_five_original_files(self) -> None:
        files = {
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }
        self.assertEqual(FILES, files)

    def test_no_fonts_binaries_or_notice(self) -> None:
        for path in SKILL_ROOT.rglob("*"):
            with self.subTest(path=path.name):
                self.assertNotIn(path.suffix.lower(), {".ttf", ".otf", ".woff", ".woff2"})
                self.assertFalse(path.name.upper().startswith("NOTICE"))
        for name in FILES:
            (SKILL_ROOT / name).read_text(encoding="utf-8")

    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "chalk-talk"), r"^sha256:")
        front = _parse_frontmatter(SKILL_ROOT / "SKILL.md")
        meta = _parse_quoted_yaml(SKILL_ROOT / "agents/openai.yaml", "chalk-talk")
        self.assertEqual("true", front["disable-model-invocation"])
        self.assertEqual({"allow_implicit_invocation": False}, meta["policy"])
        self.assertEqual(
            {
                "display_name": "Chalk Talk",
                "short_description": "Animated single-idea board lessons in self-contained HTML",
                "default_prompt": "Use $chalk-talk to turn one idea into an animated, self-contained HTML board lesson.",
            },
            meta["interface"],
        )

    def test_skill_md_budget_stop_rules_and_anchored_scripts(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text()
        self.assertGreaterEqual(len(text.encode()), 5500)
        self.assertLessEqual(len(text.encode()), 6500)
        self.assertLess(text.index("## Stop rules"), 1200)
        for command in ("check", "render"):
            self.assertIn(f"python3 <skill-directory>/scripts/board_tool.py {command}", text)
        self.assertNotRegex(text, r"python3 scripts/")
        self.assertIn("PLANS/EXPLANATIONS/<topic>-chalk-talk.html", text)
        self.assertIn("window.chalkTalk", text)

    def test_starter_is_self_contained(self) -> None:
        html = (SKILL_ROOT / "assets/starter.html").read_text()
        self.assertNotRegex(html, r"""(?i)(?:src|href)\s*=\s*["']?(?:https?:)?//""")
        self.assertNotRegex(html, r"(?i)url\(\s*['\"]?(?:https?:)?//")
        self.assertNotRegex(html, r"(?i)@import|<link\b|\bfetch\(|XMLHttpRequest|@font-face")
        self.assertEqual(["http://www.w3.org/2000/svg"], re.findall(r"https?://[^\s\"']+", html))

    def test_starter_keeps_the_board_contract_themes_and_fallbacks(self) -> None:
        html = (SKILL_ROOT / "assets/starter.html").read_text()
        for needle in (
            'data-theme="slate"', '[data-theme="paper"]', 'data-style="sketch"', '[data-style="sketch"]',
            "#182226", "#F0B45A", "#E87A6A", "#7AD0B0", "#FAF8F3", "#1F2428",
            "'Noteworthy','Chalkboard SE','Bradley Hand','Segoe Print',ui-rounded,cursive",
            "ui-monospace,'SF Mono',Menlo,Consolas,monospace", "system-ui", "ui-serif",
            'data-ct="board"', 'data-ct="play"', 'data-ct="replay"', 'data-ct="scrub"', "data-ct-slot",
            "window.chalkTalk", "function mulberry32", "function render(t)", "prefers-reduced-motion",
            "beforeprint", "afterprint", "@media print", "ResizeObserver", "postMessage",
            'event.key === " "', 'event.key === "r"', "ArrowLeft", "ArrowRight",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, html)
        self.assertNotIn("Math.random", html)
        self.assertNotIn("Date.now", html)

    def test_registry_record_is_owner_authored_with_no_dependencies(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["chalk-talk"]
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual("skills/chalk-talk", record["source"])
        self.assertEqual([], record["dependencies"])
        self.assertEqual("local-write", record["effect_ceiling"])
        self.assertEqual("explicit-only-animated-board-lessons", record["evaluation_profile"])
        self.assertEqual(["~/.agents/skills/chalk-talk"], record["install_targets"])
        self.assertEqual("owner-authored", record["provenance"]["license"])
        self.assertEqual("owner-authored", record["provenance"]["origin"])

    def test_projection_installs_idempotently_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            target = home / ".agents" / "skills" / "chalk-talk"
            self.assertEqual("dry-run", system.install("chalk-talk", apply=False).reason)
            self.assertFalse(target.exists())

            applied = system.install("chalk-talk", apply=True)
            self.assertEqual("installed", applied.reason)
            self.assertEqual(content_hash(SKILL_ROOT), content_hash(target))
            again = system.install("chalk-talk", apply=True)
            self.assertFalse(again.applied)
            self.assertEqual("already-current", again.reason)
            self.assertEqual("current", system.status().skills["chalk-talk"].state)

            rolled_back = system.rollback(applied.operation_id, apply=True)
            self.assertEqual("rolled-back", rolled_back.reason)
            self.assertFalse(target.exists())
            self.assertEqual("absent", system.status().skills["chalk-talk"].state)


class BoardToolCommandLineTests(unittest.TestCase):
    def run_tool(self, *args: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        """Run the CLI with a throwaway HOME so any accidental bootstrap would be visible."""
        home = Path(self.enterContext(tempfile.TemporaryDirectory()))
        env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("CHALK_TALK_BOOTSTRAPPED", None)
        result = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                                timeout=60, env=env)
        return result, home

    def test_tool_imports_only_the_standard_library_at_load(self) -> None:
        tree = ast.parse(TOOL.read_text())
        modules = {alias.name.split(".")[0] for node in tree.body if isinstance(node, ast.Import) for alias in node.names}
        modules |= {node.module.split(".")[0] for node in tree.body if isinstance(node, ast.ImportFrom) and node.module}
        self.assertLessEqual(modules - {"__future__"}, set(sys.stdlib_module_names))

    def test_help_for_every_subcommand_needs_no_browser(self) -> None:
        for args in ((), ("check",), ("render",), ("trace",)):
            with self.subTest(args=args):
                result, home = self.run_tool(*args, "--help")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("usage: board_tool.py", result.stdout)
                self.assertFalse((home / ".cache").exists())

    def test_bad_at_values_are_rejected_before_any_browser_work(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            board = Path(raw) / "board.html"
            board.write_text("<!doctype html>")
            for value in ("abc", "1,,2", "-1", "nan", "inf", ""):
                with self.subTest(value=value):
                    result, home = self.run_tool("check", str(board), "--at", value)
                    self.assertEqual(2, result.returncode)
                    self.assertIn("--at", result.stderr)
                    self.assertFalse((home / ".cache").exists())

    def test_parsers_normalise_valid_values(self) -> None:
        self.assertEqual([0.2, 4.0, 9.5], board_tool.parse_times("9.5, 0.2,4,4.0"))
        self.assertEqual((1200, 720), board_tool.parse_viewport("1200x720"))
        self.assertEqual(board_tool.Action("#mode@b", 2.5), board_tool.parse_action("click:#mode@b@2.5"))
        for parse, raw in (
            (board_tool.parse_viewport, "12x"), (board_tool.parse_viewport, "100x100"),
            (board_tool.parse_action, "hover:#x@1"), (board_tool.parse_action, "click:#x@soon"),
            (board_tool.parse_action, "click:@1"),
        ):
            with self.subTest(raw=raw), self.assertRaises(argparse.ArgumentTypeError):
                parse(raw)

    def test_bad_render_and_trace_flags_exit_2(self) -> None:
        for args in (
            ("render", "x.html", "--out", "a.mp4", "--format", "webm"),
            ("render", "x.html", "--out", "a.mp4", "--rate", "0"),
            ("render", "x.html", "--out", "a.mp4", "--action", "click:#x"),
            ("trace", "x.png", "--grid", "40"),
            ("trace", "x.png", "--fill", "0"),
        ):
            with self.subTest(args=args):
                result, _ = self.run_tool(*args)
                self.assertEqual(2, result.returncode)
                self.assertIn("error:", result.stderr)

    def test_mp4_encoder_falls_back_to_what_ffmpeg_has(self) -> None:
        listing = " V....D h264_videotoolbox    VideoToolbox H.264 Encoder\n V.S..D mpeg4   MPEG-4 part 2\n"
        self.assertEqual("h264_videotoolbox", board_tool.pick_mp4_encoder(listing)[0])
        self.assertEqual("mpeg4", board_tool.pick_mp4_encoder(" V.S..D mpeg4   MPEG-4 part 2\n")[0])
        with self.assertRaisesRegex(board_tool.ToolError, "--format gif"):
            board_tool.pick_mp4_encoder(" A....D aac   AAC\n")
        mp4 = board_tool.encode_command("ffmpeg", "f%05d.png", 30, "mp4", Path("o.mp4"), ("mpeg4", ["-q:v", "3"]))
        self.assertEqual(["-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p"], mp4[mp4.index("-c:v"):mp4.index("-movflags")])
        gif = board_tool.encode_command("ffmpeg", "f%05d.png", 10, "gif", Path("o.gif"))
        self.assertIn("-loop", gif)
        self.assertNotIn("-c:v", gif)

    def test_missing_board_fails_without_bootstrapping(self) -> None:
        result, home = self.run_tool("check", "/nonexistent/board.html")
        self.assertEqual(2, result.returncode)
        self.assertIn("no such file", result.stderr)
        self.assertFalse((home / ".cache").exists())


class TraceTests(unittest.TestCase):
    def write(self, data: bytes) -> Path:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = directory / "shape.png"
        path.write_bytes(data)
        return path

    def rgba(self, **kwargs: bool) -> list[bytes]:
        return [bytes(v for x in range(8) for v in (gray_value(x, y, **kwargs),) * 3 + (255,)) for y in range(8)]

    def test_every_filter_type_decodes_exactly(self) -> None:
        raster = board_tool.read_png(self.write(png(8, 8, self.rgba(), filters=(0, 1, 2, 3, 4))))
        self.assertEqual((8, 8), (raster.width, raster.height))
        expected = [gray_value(x, y) for y in range(8) for x in range(8)]
        for got, want in zip(raster.luma, expected):
            self.assertAlmostEqual(want, got, places=6)
        self.assertEqual({255}, set(raster.alpha))
        self.assertEqual(SQUARE, board_tool.silhouette(raster, 8, crop=False))

    def test_crop_keeps_aspect_and_caps_rows_at_32(self) -> None:
        raster = board_tool.read_png(self.write(png(8, 8, self.rgba(), filters=(4,))))
        self.assertEqual(["####"] * 4, board_tool.silhouette(raster, 4))
        wide = [bytes(0 if 2 <= x < 18 and 2 <= y < 6 else 255 for x in range(20)) for y in range(8)]
        self.assertEqual(["########"] * 2, board_tool.silhouette(board_tool.read_png(self.write(png(20, 8, wide, color=0))), 8))
        tall = [bytes((0, 0, 255, 255)) for _ in range(100)]
        grid = board_tool.silhouette(board_tool.read_png(self.write(png(4, 100, tall, color=0))), 24)
        self.assertEqual((32, 1), (len(grid), len(grid[0])))

    def test_polarity_follows_the_border_and_invert_flips_it(self) -> None:
        raster = board_tool.read_png(self.write(png(8, 8, self.rgba(light_ink=True), filters=(2, 3))))
        self.assertEqual(SQUARE, board_tool.silhouette(raster, 8, crop=False))
        flipped = board_tool.silhouette(raster, 8, crop=False, invert=True)
        self.assertEqual([row.translate(str.maketrans("#.", ".#")) for row in SQUARE], flipped)

    def test_transparency_defines_the_shape_when_present(self) -> None:
        rows = [bytes(v for x in range(8) for v in ((255, 255, 255, 255) if in_square(x, y) else (255, 255, 255, 0)))
                for y in range(8)]
        raster = board_tool.read_png(self.write(png(8, 8, rows, filters=(1,))))
        self.assertEqual(SQUARE, board_tool.silhouette(raster, 8, crop=False))

    def test_gray_palette_and_one_bit_images(self) -> None:
        gray = [bytes(gray_value(x, y) for x in range(8)) for y in range(8)]
        palette = bytes((250, 250, 245, 30, 30, 40))
        indexed = [bytes(1 if in_square(x, y) else 0 for x in range(8)) for y in range(8)]
        one_bit = [bytes((0b11000011 if 2 <= y <= 5 else 0xFF,)) for y in range(8)]
        for label, data in (
            ("gray", png(8, 8, gray, color=0, filters=(3, 4))),
            ("palette", png(8, 8, indexed, color=3, palette=palette)),
            ("1-bit", png(8, 8, one_bit, color=0, depth=1, filters=(0, 2))),
        ):
            with self.subTest(label=label):
                raster = board_tool.read_png(self.write(data))
                self.assertEqual(SQUARE, board_tool.silhouette(raster, 8, crop=False))

    def test_unsupported_or_empty_images_fail_with_a_clear_message(self) -> None:
        interlaced = png(8, 8, self.rgba(), interlace=1)
        with self.assertRaisesRegex(board_tool.TraceError, "interlaced"):
            board_tool.read_png(self.write(interlaced))
        with self.assertRaisesRegex(board_tool.TraceError, "not a PNG"):
            board_tool.read_png(self.write(b"GIF89a not a png"))
        blank = [bytes((200,) * 8) for _ in range(8)]
        with self.assertRaisesRegex(board_tool.TraceError, "no foreground"):
            board_tool.silhouette(board_tool.read_png(self.write(png(8, 8, blank, color=0))), 8)

    def test_trace_command_prints_rows_or_json(self) -> None:
        path = self.write(png(8, 8, self.rgba(), filters=(0, 4)))
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        text = subprocess.run([sys.executable, str(TOOL), "trace", str(path), "--grid", "8", "--no-crop"],
                              capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(0, text.returncode, text.stderr)
        self.assertEqual(SQUARE, text.stdout.splitlines())
        as_json = subprocess.run([sys.executable, str(TOOL), "trace", str(path), "--grid", "4", "--format", "json"],
                                 capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(0, as_json.returncode, as_json.stderr)
        self.assertEqual({"columns": 4, "rows": 4, "cells": ["####"] * 4}, json.loads(as_json.stdout))


if __name__ == "__main__":
    unittest.main()
