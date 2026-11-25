from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "colgrep" / "agents"
SKILL_DIR = SCRIPT.parent / "skill"
LINKS = (
    ".config/devin/skills/colgrep",
    ".commandcode/skills/colgrep",
    ".kimi-code/skills/colgrep",
)
OPENCODE_AGENTS_MD = ".config/opencode/AGENTS.md"


@unittest.skipUnless(shutil.which("colgrep"), "colgrep is not installed")
class ColgrepAgentsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()

    def run_script(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), command],
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True,
            text=True,
        )

    def test_install_reaches_only_the_four_agents_and_uninstall_reverts(self) -> None:
        opencode = self.home / OPENCODE_AGENTS_MD
        opencode.parent.mkdir(parents=True)
        opencode.write_text("# Mine\n\nkeep this\n")

        self.assertEqual(self.run_script("install").returncode, 0)
        for link in LINKS:
            self.assertEqual((self.home / link).readlink(), SKILL_DIR)
        installed = opencode.read_text()
        self.assertIn("keep this", installed)
        self.assertIn("<!-- COLGREP_START -->\n# Semantic Code Search", installed)
        for shared in (".agents", ".claude", ".codex"):
            self.assertFalse((self.home / shared).exists(), shared)

        self.assertEqual(self.run_script("install").returncode, 0)
        self.assertEqual(opencode.read_text(), installed)
        self.assertIn("installed ", self.run_script("status").stdout)

        self.assertEqual(self.run_script("uninstall").returncode, 0)
        for link in LINKS:
            self.assertFalse((self.home / link).is_symlink(), link)
        self.assertEqual(opencode.read_text(), "# Mine\n\nkeep this\n")

    def test_install_refuses_to_replace_an_existing_skill(self) -> None:
        existing = self.home / ".commandcode/skills/colgrep"
        existing.mkdir(parents=True)
        (existing / "SKILL.md").write_text("someone else's skill\n")

        result = self.run_script("install")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace", result.stderr)
        self.assertEqual((existing / "SKILL.md").read_text(), "someone else's skill\n")

    def test_uninstall_removes_the_opencode_file_it_created(self) -> None:
        self.assertEqual(self.run_script("install").returncode, 0)
        self.assertEqual(self.run_script("uninstall").returncode, 0)
        self.assertFalse((self.home / OPENCODE_AGENTS_MD).exists())


if __name__ == "__main__":
    unittest.main()
