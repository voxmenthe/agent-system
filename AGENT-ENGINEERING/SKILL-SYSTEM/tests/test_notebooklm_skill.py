"""notebooklm skill contract, registry record, guide entry, and CLI argument checks; no browser."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "notebooklm"


def load_nblm():
    spec = importlib.util.spec_from_file_location("nblm", SKILL_ROOT / "scripts" / "nblm.py")
    nblm = importlib.util.module_from_spec(spec)
    # dataclasses resolves string annotations through sys.modules while the module loads
    with mock.patch.dict(sys.modules, {"nblm": nblm}):
        spec.loader.exec_module(nblm)
    return nblm


class NotebooklmSkillTests(unittest.TestCase):
    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "notebooklm"), r"^sha256:")
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("disable-model-invocation: true", (SKILL_ROOT / "SKILL.md").read_text())
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$notebooklm", metadata)

    def test_registry_record_and_guide_entry(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["notebooklm"]
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("skills/notebooklm", record["source"])
        self.assertEqual([], record["dependencies"])
        self.assertEqual("external-write", record["effect_ceiling"])
        self.assertEqual(["~/.agents/skills/notebooklm"], record["install_targets"])
        self.assertIn("[`notebooklm`](skills/notebooklm/SKILL.md)", (ROOT / "USER-GUIDE.md").read_text())


class CliArgumentTests(unittest.TestCase):
    """Local arguments are settled before Chrome is touched; the browser edge is stubbed to fail."""

    def setUp(self) -> None:
        self.nblm = load_nblm()
        self.tmp = Path(tempfile.mkdtemp())
        self.browser_calls: list[str] = []

        def no_browser(script: str) -> str:
            self.browser_calls.append(script)
            raise self.nblm.NblmError("no browser in tests", self.nblm.EXIT_BROWSER)

        state = self.tmp / "state"
        for name, value in {
            "_osascript": no_browser,
            "STATE_DIR": state,
            "STATE_FILE": state / "browser.json",
            "LOCK_FILE": state / "browser.lock",
        }.items():
            patcher = mock.patch.object(self.nblm, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, *argv: str) -> int:
        with mock.patch.object(sys, "argv", ["nblm.py", *argv]), mock.patch("sys.stderr"):
            return self.nblm.main()

    def test_missing_out_directory_is_created_before_browser_work(self) -> None:
        # 10-23: two weaker agents each passed a TEMP/ subfolder that did not exist yet
        out = self.tmp / "new" / "episodes"
        self.assertEqual(self.nblm.EXIT_BROWSER, self.run_cli("download", "nb", "art", "--out", str(out)))
        self.assertTrue(out.is_dir())

    def test_out_naming_an_existing_non_audio_file_is_rejected(self) -> None:
        out = self.tmp / "notes"
        out.write_text("keep")
        self.assertEqual(self.nblm.EXIT_USAGE, self.run_cli("download", "nb", "art", "--out", str(out)))
        self.assertEqual([], self.browser_calls)

    def test_bad_input_files_fail_before_anything_is_created(self) -> None:
        paper = self.tmp / "paper.pdf"
        paper.write_bytes(b"%PDF-1.4")
        unsupported = self.tmp / "paper.xyz"
        unsupported.write_text("x")
        missing = str(self.tmp / "typo.pdf")
        cases = [
            ("paper-audio", missing, "--out", str(self.tmp)),
            ("paper-audio", str(unsupported), "--out", str(self.tmp)),
            ("upload", "nb", str(paper), missing),
        ]
        for argv in cases:
            with self.subTest(argv=argv[:2]):
                self.assertEqual(self.nblm.EXIT_USAGE, self.run_cli(*argv))
                self.assertEqual([], self.browser_calls)


if __name__ == "__main__":
    unittest.main()
