from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "sgrep" / "agents"
KERNEL = ROOT.parent / "PERSISTENT-GUIDANCE" / "AGENTS.md"
LINKS = (".commandcode/skills/sgrep", ".pi/agent/skills/sgrep")
OPENCODE_AGENTS_MD = ".config/opencode/AGENTS.md"


class SgrepAgentsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.shared_skill = self.home / ".agents/skills/sgrep"
        self.shared_skill.mkdir(parents=True)
        (self.shared_skill / "SKILL.md").write_text("shared sgrep skill\n")

    def run_script(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), command],
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True,
            text=True,
        )

    def test_install_links_the_shared_skill_and_copies_the_kernel_section(self) -> None:
        opencode = self.home / OPENCODE_AGENTS_MD
        opencode.parent.mkdir(parents=True)
        opencode.write_text("# Mine\n\nkeep this\n")

        self.assertEqual(self.run_script("install").returncode, 0)
        for link in LINKS:
            self.assertEqual(
                (self.home / link).resolve(), self.shared_skill.resolve(), link
            )
        installed = opencode.read_text()
        self.assertIn("keep this", installed)
        kernel = KERNEL.read_text()
        section = installed.split("<!-- SGREP_START -->\n")[1].split("<!-- SGREP_END -->")[0]
        self.assertTrue(section.startswith("### Find code\n"))
        self.assertIn(section.strip(), kernel)

        self.assertEqual(self.run_script("install").returncode, 0)
        self.assertEqual(opencode.read_text(), installed)
        self.assertNotIn("missing", self.run_script("status").stdout)

        self.assertEqual(self.run_script("uninstall").returncode, 0)
        for link in LINKS:
            self.assertFalse((self.home / link).is_symlink(), link)
        self.assertEqual(opencode.read_text(), "# Mine\n\nkeep this\n")

    def test_install_requires_the_shared_skill(self) -> None:
        (self.shared_skill / "SKILL.md").unlink()

        result = self.run_script("install")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bin/skill-system install sgrep", result.stderr)
        for link in LINKS:
            self.assertFalse((self.home / link).is_symlink(), link)

    def test_install_refuses_to_replace_an_existing_skill(self) -> None:
        existing = self.home / ".commandcode/skills/sgrep"
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
