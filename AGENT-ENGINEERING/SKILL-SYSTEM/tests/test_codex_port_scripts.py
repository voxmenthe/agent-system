from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skill_system.model import validate_skill_tree

SKILLS = Path(__file__).resolve().parents[1] / "skills"


class CodexPortTests(unittest.TestCase):
    def test_canonical_packages(self) -> None:
        for name in ("prepare-context", "recent-commits-digest", "codebase-search-and-understanding-expert"):
            with self.subTest(name=name):
                validate_skill_tree(SKILLS / name, name)

    def test_relocated_resolver_and_bundle_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            package = base / "relocated package"
            shutil.copytree(SKILLS / "prepare-context", package)
            repo = base / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Widget project\n")
            (repo / "src").mkdir()
            (repo / "src/widget.py").write_text("def widget():\n    return 42\n")
            result = subprocess.run(
                [sys.executable, str(package / "scripts/resolve_prepare_context.py"),
                 "--repo-root", str(repo), "--create-output-dir", "--title", "widget", "widget behavior"],
                cwd=base, capture_output=True, text=True, check=True,
            )
            manifest = json.loads(result.stdout)
            self.assertEqual(json.loads((repo / manifest["manifest_path"]).read_text()), manifest)
            self.assertIn("src/widget.py", [c["path"] for c in manifest["starter_candidates"]["code"]])
            # Recommendations must run using native search, independent of host skill installs.
            command = manifest["recommended_tools"]["files"].format(repo_root=repo)
            listing = subprocess.run(shlex.split(command), capture_output=True, text=True, check=True)
            self.assertIn("widget.py", listing.stdout)
            self.assertFalse((repo / manifest["final_bundle_path"]).exists())
            self.assertEqual(manifest["assembly_order"], [manifest["request_summary_path"], *manifest["component_paths"].values()])
            components = ["# Prepared Context: Widget\n\n## Request\nReview widget behavior.\n",
                          "## Project / Task Overview\nWidget project.\n",
                          "## Plan Context\nNo plans.\n", "## Recent Change Context\nNo change narratives.\n",
                          "## Code Context\n`src/widget.py`: widget returns 42.\n\n## Open Questions For Reviewer\nIs 42 appropriate?\n"]
            for path, content in zip(manifest["assembly_order"], components, strict=True):
                (repo / path).write_text(content)
            final = repo / manifest["final_bundle_path"]
            final.write_text("\n".join((repo / path).read_text() for path in manifest["assembly_order"]))
            self.assertEqual(final.read_text(), "\n".join(components))

    def test_digest_local_history_fast_forward_and_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                       GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")

            def git(repo: Path, *args: str) -> str:
                return subprocess.run(["git", "-C", str(repo), *args], env=env,
                                      capture_output=True, text=True, check=True).stdout.strip()

            def commit(repo: Path, path: str, message: str) -> str:
                (repo / path).write_text(message)
                git(repo, "add", "--", path)
                git(repo, "commit", "-m", message)
                return git(repo, "rev-parse", "HEAD")

            def digest(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run([sys.executable, str(SKILLS / "recent-commits-digest/scripts/recent_commits_digest.py"), *args],
                                      cwd=repo, env=env, capture_output=True, text=True)

            remote, author, reader = (base / name for name in ("remote.git", "author", "reader"))
            git(base, "init", "--bare", str(remote))
            git(base, "clone", str(remote), str(author))
            commit(author, "target.txt", "first target")
            git(author, "push", "-u", "origin", "HEAD")
            git(base, "clone", str(remote), str(reader))
            commit(author, "other.txt", "other change")
            newest = commit(author, "target.txt", "second target")
            git(author, "push")
            local = digest(reader, "--no-pull", "--path", "target.txt", "--count", "1")
            self.assertEqual(local.returncode, 0, local.stderr)
            self.assertIn("first target", local.stdout)
            self.assertNotIn("second target", local.stdout)
            pulled = digest(reader, "--path", "target.txt", "-n", "1")
            self.assertEqual(pulled.returncode, 0, pulled.stderr)
            self.assertIn("Pulled: 2 new commits.", pulled.stdout)
            self.assertIn("second target", pulled.stdout)
            self.assertNotIn("first target", pulled.stdout)
            self.assertEqual(git(reader, "rev-parse", "HEAD"), newest)
            self.assertIn("Already up to date.", digest(reader).stdout)
            self.assertIn("No commits found", digest(reader, "--no-pull", "--path", "missing").stdout)
            self.assertEqual(digest(reader, "--count", "0").returncode, 2)
            local_head = commit(reader, "local.txt", "local branch")
            commit(author, "remote.txt", "remote branch")
            git(author, "push")
            failed = digest(reader)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("no merge or rebase was attempted", failed.stderr)
            self.assertEqual(git(reader, "rev-parse", "HEAD"), local_head)
            self.assertFalse((reader / ".git/MERGE_HEAD").exists())


if __name__ == "__main__":
    unittest.main()
