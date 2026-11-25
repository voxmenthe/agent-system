"""review-identity on a throwaway repository: what changes a review target's identity and what does not."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/review-identity"


class ReviewIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.git("init", "-q")
        (self.repo / "docs").mkdir()
        (self.repo / "docs/plan.md").write_text("plan\n")
        (self.repo / "other.md").write_text("other\n")
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def identity(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT), *args], cwd=self.repo, capture_output=True, text=True, check=False)

    def scoped(self) -> str:
        result = self.identity(self.base, "docs")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_every_in_scope_change_gives_a_new_identity(self) -> None:
        seen = [self.scoped()]
        self.assertTrue(seen[0].startswith(self.base + " "))
        changes = {
            "a new untracked file": lambda: (self.repo / "docs/new.md").write_text("draft\n"),
            "an edit to that untracked file": lambda: (self.repo / "docs/new.md").write_text("draft 2\n"),
            "a mode change": lambda: (self.repo / "docs/new.md").chmod(0o755),
            "a deleted tracked file": lambda: (self.repo / "docs/plan.md").unlink(),
        }
        for name, change in changes.items():
            with self.subTest(name):
                change()
                seen.append(self.scoped())
                self.assertNotIn(seen[-1], seen[:-1])

    def test_changes_outside_the_paths_and_the_real_index_are_left_alone(self) -> None:
        before = self.scoped()
        (self.repo / "other.md").write_text("edited\n")
        (self.repo / "untracked.md").write_text("elsewhere\n")
        self.assertEqual(self.scoped(), before)
        self.assertEqual(self.git("status", "--porcelain"), "M other.md\n?? untracked.md")  # nothing staged

    def test_a_bad_base_prints_no_identity(self) -> None:
        result = self.identity("no-such-ref", "docs")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
