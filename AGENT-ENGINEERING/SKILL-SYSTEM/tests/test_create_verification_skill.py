"""create-verification-skill's bundled HTML preflight, run as a caller runs it."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "skills" / "create-verification-skill" / "scripts" / "html_preflight.py"

SVG = (
    '<svg viewBox="0 0 100 50" role="img"><title id="t">Bars</title>'
    '<g transform="translate(10, 5)"><rect x="0" y="0" width="40" height="20"/>'
    '<text x="45" y="15">label</text></g><line x1="0" y1="49" x2="100" y2="49"/></svg>'
)
DOCUMENT = (
    "<!DOCTYPE html>\n<html><head><title>Report</title></head><body>"
    f"<main><div><p>Intro<div>{SVG}</div></div></main></body></html>\n"
)
IMAGE_FREE = (
    "<!DOCTYPE html>\n<html><head><title>Notes</title></head><body>"
    "<main><h1>Notes</h1><p>Text only.</p></main></body></html>\n"
)
# Counted: the <img>, the <canvas> and the outer role="img" <svg> (its nested <svg> belongs to it). Not counted:
# markup inside <title>, <script> and a comment, and the three decorative <svg>s.
MEDIA = (
    "<!DOCTYPE html>\n<html><head><title>Use <img> tags</title>"
    "<script>const html = '<img src=x.png>';</script></head><body><main>"
    '<!-- <img src="old.png"> --><figure><img src="chart.png" alt="Revenue by month"></figure>'
    '<canvas id="plot"></canvas>'
    '<svg viewBox="0 0 10 10" role="img"><svg viewBox="0 0 5 5"></svg></svg>'
    '<svg aria-hidden="true" viewBox="0 0 10 10"></svg>'
    '<svg role="presentation" viewBox="0 0 10 10"></svg><svg role="none" viewBox="0 0 10 10"></svg>'
    "</main></body></html>\n"
)


class HtmlPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.directory / "report.html"

    def run_on(self, body: str | bytes, *flags: str) -> subprocess.CompletedProcess[str]:
        if isinstance(body, str):
            self.path.write_text(body, encoding="utf-8")
        else:
            self.path.write_bytes(body)
        return subprocess.run(
            [sys.executable, "-I", str(PREFLIGHT), *flags, str(self.path)],
            capture_output=True, text=True, check=False,
        )

    def test_a_whole_document_inside_its_viewbox_has_no_defect(self) -> None:
        result = self.run_on(DOCUMENT + "<!-- trailing comment -->\n")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("no defect in what was checked", result.stdout)
        self.assertNotIn("not checked", result.stdout)

    def test_each_mutation_is_a_defect(self) -> None:
        cases = {
            "truncated": (DOCUMENT[: DOCUMENT.index("</main>")], "does not end with </html>"),
            "dropped end tag": (DOCUMENT.replace("</div></div>", "</div>", 1),
                                "<div> opens 2 time(s) and closes 1 time(s)"),
            "off-canvas rect": (DOCUMENT.replace('width="40"', 'width="120"'),
                                'paints 30 past the viewBox right edge'),
            "translated past the edge": (DOCUMENT.replace("translate(10, 5)", "translate(10, 40)"),
                                         "past the viewBox bottom edge"),
            "unclosed title": (DOCUMENT.replace("</title></head>", "</head>").replace('<title id="t">Bars</title>', ""),
                               "<title> is never closed"),
        }
        for name, (body, message) in cases.items():
            with self.subTest(name):
                result = self.run_on(body)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(message, result.stdout)

    def test_a_cut_multibyte_character_is_a_defect(self) -> None:
        body = DOCUMENT.encode().replace(b"Intro", "Intro —".encode()[:-1])
        result = self.run_on(body)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("1 U+FFFD replacement character(s), first on line 2", result.stdout)

    def test_unmodeled_geometry_is_listed_as_not_checked_never_passed(self) -> None:
        rotated = DOCUMENT.replace("translate(10, 5)", "rotate(45)").replace(
            "</svg>", '<path d="M0 0 L500 500"/></svg>'
        )
        result = self.run_on(rotated.replace('width="40"', 'width="400"'))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("svg 1: 1 element(s) checked; not checked: 1 <path>, 1 <rect>, 1 <text>", result.stdout)

    def test_expect_images_fails_an_image_free_report_and_the_default_run_is_unchanged(self) -> None:
        # explain-code and explain-research run the preflight without the flag and read this output.
        default = self.run_on(IMAGE_FREE)
        self.assertEqual((0, f"{self.path}: no defect in what was checked\n"), (default.returncode, default.stdout))

        expected = self.run_on(IMAGE_FREE, "--expect-images", "1")
        self.assertEqual(1, expected.returncode, expected.stdout)
        self.assertEqual(
            f"{self.path}: DEFECT 0 image(s) found, fewer than the 1 expected by --expect-images\n"
            f"{self.path}: media inventory: 0 <img>, 0 <canvas>, 0 <svg> (0 decorative <svg> not counted); "
            "0 image(s), 1 expected\n"
            f"{self.path}: 1 defect(s)\n",
            expected.stdout,
        )

    def test_expect_images_counts_img_canvas_and_non_decorative_outermost_svg(self) -> None:
        inventory = "media inventory: 1 <img>, 1 <canvas>, 1 <svg> (3 decorative <svg> not counted); 3 image(s)"
        enough = self.run_on(MEDIA, "--expect-images", "3")
        self.assertEqual(0, enough.returncode, enough.stdout)
        self.assertIn(f"{inventory}, 3 expected\n", enough.stdout)
        short = self.run_on(MEDIA, "--expect-images", "4")
        self.assertEqual(1, short.returncode, short.stdout)
        self.assertIn("DEFECT 3 image(s) found, fewer than the 4 expected", short.stdout)
        self.assertNotIn("media inventory", self.run_on(MEDIA).stdout)

    def test_an_invalid_image_count_is_refused(self) -> None:
        for value, message in (("-1", "-1 is negative"), ("two", "'two' is not a whole number")):
            with self.subTest(value=value):
                result = self.run_on(IMAGE_FREE, "--expect-images", value)
                self.assertEqual(2, result.returncode)
                self.assertIn(message, result.stderr)

    def test_an_unreadable_file_is_not_checked(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(PREFLIGHT), str(self.directory / "missing.html")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("not checked", result.stdout)


if __name__ == "__main__":
    unittest.main()
