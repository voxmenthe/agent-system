"""Observable contracts in disposable repositories; no user repository mutations."""

import os
import pty
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HELPERS = Path(__file__).resolve().parents[1]
CLI = HELPERS / "navigation.py"
SHIM = HELPERS.parent / ".bash_git_helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))


class NavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="git-navigation-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo with spaces"
        self.root.mkdir()
        self.env = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="Fixture",
            GIT_COMMITTER_NAME="Fixture",
            GIT_AUTHOR_EMAIL="fixture@example.invalid",
            GIT_COMMITTER_EMAIL="fixture@example.invalid",
            GIT_CONFIG_COUNT="0",
            PYTHONDONTWRITEBYTECODE="1",
        )
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.hooksPath", os.devnull)
        self.git("config", "commit.gpgsign", "false")

    def execute(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        code: int = 0,
        env: dict[str, str] | None = None,
    ) -> str:
        result = subprocess.run(
            args,
            cwd=cwd or self.root,
            env=env or self.env,
            capture_output=True,
            check=False,
        )
        output = result.stdout.decode("utf-8", "surrogateescape")
        self.assertEqual(
            result.returncode,
            code,
            f"{args}\n{output}\n{result.stderr.decode(errors='replace')}",
        )
        return output

    def git(self, *args: str) -> str:
        return self.execute(["git", *args])

    def nav(self, *args: str, **kwargs) -> str:
        return self.execute([sys.executable, "-B", str(CLI), *args], **kwargs)

    def write(self, name: str, data: str | bytes) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)

    def commit(self, message: str) -> str:
        self.git("add", "--all")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip()

    def test_unborn_state_root_commit_and_staging_boundaries(self) -> None:
        self.write("file.py", "BASE\n")
        self.git("add", "file.py")
        self.assertIn("unborn", self.nav("map"))
        self.assertIn("+BASE", self.nav("focus", "--staged"))
        self.assertIn("+BASE", self.nav("focus", "--worktree"))
        self.commit("root")
        self.assertIn("+BASE", self.nav("focus", "--commit", "HEAD"))
        self.write("file.py", "STAGED\n")
        self.git("add", "file.py")
        self.write("file.py", "UNSTAGED\n")
        self.write("not tracked", "UNTRACKED\n")
        state = self.nav("map")
        for bucket in ("staged: 1", "unstaged: 1", "untracked: 1"):
            self.assertIn(bucket, state)
        self.assertIn("+STAGED", self.nav("focus", "--staged"))
        self.assertNotIn("UNSTAGED", self.nav("focus", "--staged"))
        self.assertIn("-STAGED\n+UNSTAGED", self.nav("focus", "--unstaged"))
        self.assertIn("Untracked (not in patch): 1", self.nav("map", "--worktree"))
        self.nav("map", "--staged", "--unstaged", code=2)

    def test_focus_collapses_only_known_noise_and_expands_explicit_file(self) -> None:
        self.write("src/api.py", "def api():\n    return 1\n")
        self.write("uv.lock", "old lock\n")
        self.write("settings.toml", "key=1\n")
        self.write("tests/test_api.py", "assert api() == 1\n")
        self.commit("root")
        self.write("src/api.py", "def api():\n    return 2\n")
        self.write("uv.lock", "new lock\n")
        self.write("settings.toml", "key=2\n")
        self.write("tests/test_api.py", "assert api() == 2\n")
        self.commit("update")
        output = self.nav("focus")
        self.assertIn("+key=2", output)
        self.assertIn("+assert api() == 2", output)
        self.assertNotIn("+new lock", output)
        self.assertIn("+new lock", self.nav("focus", "--all"))
        self.assertIn("+new lock", self.nav("focus", "--", "uv.lock"))
        self.assertIn(
            "+new lock", self.nav("focus", "--whole-change", "--", "src/api.py")
        )
        nested = self.nav("focus", "--", "api.py", cwd=self.root / "src")
        self.assertIn("src/api.py", nested)
        self.assertNotIn("settings.toml", nested)
        self.assertIn("+key=2", self.nav("focus", "--first", "settings.toml"))

    def test_hunk_filter_preserves_context_and_full_expansion(self) -> None:
        self.write("f.py", "key = 1\n" + "# middle\n" * 20 + "other = 1\n")
        self.commit("root")
        self.write("f.py", "key = 2\n" + "# middle\n" * 20 + "other = 2\n")
        self.commit("rewrite")
        output = self.nav("focus", "--hunk", "key")
        self.assertIn("+key = 2", output)
        self.assertNotIn("+other = 2", output)
        self.assertIn("hunks shown: 1/2", output)
        self.assertIn("+other = 2", self.nav("focus", "--all", "--hunk", "key"))
        self.nav("focus", "--hunk", "[", code=2)
        self.nav("focus", "--syntax", "--hunk", "key", code=2)

    def test_paths_are_data_and_metadata_stays_visible(self) -> None:
        unusual = [
            "-leading.py",
            "tab\tfile.py",
            "line\nfile.py",
            "$(touch BAD).py",
            "a'b.py",
            "literal[1]*.py",
        ]
        for path in unusual:
            self.write(path, "before\n")
        self.write("binary.bin", b"\x00one")
        self.write("mode.sh", "echo hi\n")
        self.write("gone", "bye\n")
        self.write("rename from", "stable contents\n")
        self.commit("root")
        for path in unusual:
            self.write(path, "after\n")
        self.write("binary.bin", b"\x00two")
        (self.root / "mode.sh").chmod(0o755)
        (self.root / "gone").unlink()
        self.git("mv", "rename from", "rename to")
        os.symlink("mode.sh", self.root / "link")
        self.commit("paths and metadata")
        output = self.nav("map", "--commit", "HEAD")
        self.assertIn("rename from -> rename to", output)
        self.assertIn("100644->100755", output)
        self.assertIn("120000", output)
        self.assertIn("+-/--", output)
        for path in unusual:
            self.assertIn("+after", self.nav("focus", "--", path))
        self.assertFalse((self.root / "BAD").exists())
        self.assertIn("deleted file mode", self.nav("focus", "--", "gone"))
        self.assertIn("Binary files", self.nav("focus", "--", "binary.bin"))

    def test_branch_endpoints_history_and_merge_parent_selection(self) -> None:
        self.write("base", "base\n")
        base = self.commit("root")
        self.git("switch", "-qc", "feature")
        self.write("feature", "one\n")
        feature = self.commit("feature")
        self.git("switch", "-q", "main")
        self.write("main", "main\n")
        self.commit("main edit")
        self.git("merge", "--no-ff", "-qm", "merge feature", "feature")
        output = self.nav("map", "--commit", "HEAD")
        self.assertIn("parent 1/2", output)
        self.assertIn("feature", output)
        self.assertIn("main", self.nav("map", "--commit", "HEAD", "--parent", "2"))
        self.nav("map", "--commit", "HEAD", "--parent", "3", code=2)
        self.assertIn("committed only", self.nav("map", "--branch", "feature"))
        self.assertIn("feature", self.nav("map", "--between", base, feature))
        self.assertIn("History:", self.nav("focus", "--history", f"{base}..{feature}"))
        self.nav("focus", "--history", "HEAD", code=2)

    def test_conflict_and_linked_worktree(self) -> None:
        self.write("conflict", "base\n")
        self.commit("root")
        self.git("switch", "-qc", "side")
        self.write("conflict", "side\n")
        self.commit("side")
        self.git("switch", "-q", "main")
        self.write("conflict", "main\n")
        self.commit("main")
        self.execute(["git", "merge", "side"], code=1)
        self.assertIn("conflicted: 1", self.nav("map"))
        self.assertIn("In progress: MERGE_HEAD", self.nav("map"))
        self.assertIn("conflict", self.nav("focus", "--unstaged"))
        linked = Path(self.temp.name) / "linked tree"
        self.git("worktree", "add", "--detach", str(linked), "side")
        self.assertIn(str(linked), self.nav("map", cwd=linked))
        self.assertIn("detached HEAD", self.nav("map", cwd=linked))

    def test_changed_symbols_ranges_decorators_removed_and_module_changes(self) -> None:
        self.write(
            "a.py",
            "import os\nclass A:\n    @decorator(1)\n    def same(self, x=1):\n        return x\nclass B:\n    def same(self):\n        return 2\ndef removed():\n    pass\n",
        )
        old = self.commit("root")
        self.write(
            "a.py",
            "import sys\nclass A:\n    @decorator(2)\n    def same(self, x=2):\n        return x + 1\nclass B:\n    def same(self):\n        return 2\n",
        )
        self.commit("contract")
        output = self.nav("outline", "--changed", "--commit", "HEAD", "--", "a.py")
        self.assertIn("~ A.same:", output)
        self.assertIn("- removed:", output)
        self.assertIn("module-level/unclassified", output)
        self.assertIn("@decorator(1)", output)
        self.assertIn("@decorator(2)", output)
        self.assertIn("removed", self.nav("outline", "--at", old, "--", "a.py"))
        self.assertIn(
            "return x + 1", self.nav("line", "--symbol", "A.same", "--", "a.py")
        )
        self.nav("line", "--symbol", "same", "--", "a.py", code=2)
        self.assertNotIn(
            "return x + 1",
            self.nav("line", "--at", old, "--symbol", "A.same", "--", "a.py"),
        )
        self.assertIn(
            "return 2", self.nav("line", "--blame", "--lines", "7:8", "--", "a.py")
        )

    def test_pickaxe_same_count_regex_and_unrestricted_context(self) -> None:
        self.write("src/a.py", "call(1)\n" + "# spacer\n" * 20 + "other(1)\n")
        self.write("settings.toml", "one\n")
        self.commit("introduction")
        self.write("src/a.py", "call(2)\n" + "# spacer\n" * 20 + "other(2)\n")
        self.write("settings.toml", "two\n")
        followup = self.commit("followup")
        literal = self.nav("why", "--literal", "call", "--", "src/")
        regex = self.nav("why", "--regex", "call", "--", "src/")
        self.assertNotIn("followup", literal)
        self.assertIn("followup", regex)
        self.assertNotIn("+other(2)", regex)
        self.assertIn("src/a.py:1:", regex)
        context = self.nav("why", "--commit", followup, "--", "src/")
        self.assertIn("settings.toml", context)
        self.nav("why", "--regex", "[", code=2)

    @unittest.skipUnless(shutil.which("rg"), "ripgrep unavailable")
    def test_impact_callback_and_string_wiring_test_leads(self) -> None:
        self.write(
            "src/load.py",
            "def load():\n    return 1\ncallback = load\nregistry = {'marker': load}\n",
        )
        self.write("tests/test_load.py", "assert load() == 1\n")
        self.commit("root")
        self.assertIn("callback = load", self.nav("impact", "--symbol", "load"))
        self.assertIn(
            "test candidate: direct text hit", self.nav("impact", "--symbol", "load")
        )
        self.assertIn("registry", self.nav("impact", "--key", "marker"))
        self.assertIn("def load()", self.nav("impact", "--file", "src/load.py"))

    @unittest.skipUnless(shutil.which("ast-grep"), "ast-grep unavailable")
    def test_structural_multiline_removal_and_same_count_edit(self) -> None:
        self.write("s.py", "x = value or default\nload(\n    1\n)\n")
        self.commit("root")
        self.write("s.py", "x = value\nload(\n    2\n)\n")
        self.commit("rewrite")
        removed = self.nav(
            "shape",
            "--changed",
            "--lang",
            "python",
            "--pattern",
            "$X or $DEFAULT",
            "--",
            "s.py",
        )
        self.assertIn("before s.py:1", removed)
        self.assertNotIn("after s.py:1", removed)
        rewritten = self.nav(
            "shape",
            "--changed",
            "--lang",
            "python",
            "--pattern",
            "load($$$ARGS)",
            "--",
            "s.py",
        )
        self.assertIn("before s.py:2-4", rewritten)
        self.assertIn("after s.py:2-4", rewritten)
        self.nav(
            "shape",
            "--lang",
            "not-a-language",
            "--pattern",
            "call()",
            "--",
            "s.py",
            code=2,
        )

    def test_hot_counts_denominator_filters_and_explicit_bulk_exclusion(self) -> None:
        self.write("anchor", "0\n")
        self.write("tests/test_anchor", "0\n")
        self.commit("root")
        self.write("anchor", "1\n")
        self.write("tests/test_anchor", "1\n")
        self.commit("together")
        self.write("anchor", "2\n")
        self.commit("anchor alone")
        output = self.nav("hot", "--with", "anchor", "--", "tests/")
        self.assertIn("shared 2/3", output)
        self.assertIn("touches 2", output)
        self.assertIn("truncated", self.nav("hot", "--count", "1"))
        self.assertIn(
            "Bulk commits excluded explicitly: 2",
            self.nav("hot", "--exclude-bulk", "1"),
        )

    def test_range_diff_revised_series(self) -> None:
        self.write("a", "0\n")
        base = self.commit("root")
        self.write("a", "1\n")
        old = self.commit("feature")
        self.git("switch", "-qc", "new", base)
        self.write("a", "2\n")
        self.commit("feature")
        self.write("b", "extra\n")
        new = self.commit("extra")
        result = self.nav("range", f"{base}..{old}", f"{base}..{new}")
        self.assertIn("feature", result)
        self.assertIn("extra", result)
        self.nav("range", "missing..HEAD", "main..HEAD", code=2)

    def test_dispatch_discovery_fallback_and_read_only(self) -> None:
        self.write("a.py", "x = 1\n")
        self.commit("root")
        before = self.git("status", "--porcelain=v1", "-z")
        for name in (
            "map",
            "focus",
            "peek",
            "why",
            "outline",
            "line",
            "impact",
            "shape",
            "hot",
            "range",
            "doctor",
        ):
            output = self.execute(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-c",
                    'source "$1"; g help "$2"',
                    "bash",
                    str(SHIM),
                    name,
                ]
            )
            self.assertIn("g" + name, output)
        self.assertIn(
            "gfocus",
            self.execute(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-c",
                    r'source "$1"; g \? hunks',
                    "bash",
                    str(SHIM),
                ]
            ),
        )
        self.assertIn("Non-interactive", self.nav("peek"))
        self.assertIn("shell location unchanged", self.nav("peek", "--dirs"))
        self.assertEqual(before, self.git("status", "--porcelain=v1", "-z"))

    def test_missing_optional_tools(self) -> None:
        self.write("a.py", "x = 1\n")
        self.commit("root")
        tools = Path(self.temp.name) / "limited-bin"
        tools.mkdir()
        (tools / "git").symlink_to(shutil.which("git"))
        env = dict(self.env, PATH=str(tools))
        self.assertIn("Non-interactive", self.nav("peek", env=env))
        self.assertIn("+x = 1", self.nav("focus", "--syntax", env=env))
        self.nav(
            "shape",
            "--lang",
            "python",
            "--pattern",
            "$X",
            "--",
            "a.py",
            env=env,
            code=2,
        )
        self.assertIn("Outline:", self.nav("outline", "--", "a.py", env=env))

    def test_g_find_preserves_quoted_arguments_without_shell_evaluation(self) -> None:
        self.write("space file.py", "value = 'two words'\n")
        self.commit("root")
        bindir = Path(self.temp.name) / "picker-bin"
        bindir.mkdir()
        fake = bindir / "fzf"
        fake.write_text("#!/bin/bash\nprintf 'enter\\n'\ncat | sed -n '/^gwhy|/p'\n")
        fake.chmod(0o755)
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-c",
                    'source "$1"; g find',
                    "bash",
                    str(SHIM),
                ],
                cwd=self.root,
                env=dict(self.env, PATH=str(bindir) + os.pathsep + self.env["PATH"]),
                stdin=slave,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            os.write(master, b'--literal "two words" -- "space file.py"\n')
            out, err = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 0, err.decode())
            self.assertIn("space file.py:1:", out.decode())
        finally:
            os.close(master)
            os.close(slave)

    @unittest.skipUnless(shutil.which("rg"), "ripgrep unavailable")
    def test_unicode_path_and_non_utf8_source_reference(self) -> None:
        path = "non-utf8-☃.py"
        self.write(path, b"value = 'marker-\xff'\n")
        self.commit("root")
        self.assertIn("marker", self.nav("impact", "--key", "marker"))
        self.assertIn("non-utf8", self.nav("map", "--commit", "HEAD"))

    def test_submodule_pointer_retains_native_evidence(self) -> None:
        self.write("a", "one\n")
        old = self.commit("root")
        self.write("a", "two\n")
        new = self.commit("next")
        self.git("update-index", "--add", "--cacheinfo", f"160000,{old},module")
        self.git("commit", "-qm", "add gitlink")
        self.git("update-index", "--cacheinfo", f"160000,{new},module")
        output = self.nav("focus", "--staged", "--syntax")
        self.assertIn("Subproject commit " + old, output)
        self.assertIn("Subproject commit " + new, output)

    def test_activity_recency_compares_instants_across_timezones(self) -> None:
        self.env["GIT_AUTHOR_DATE"] = self.env["GIT_COMMITTER_DATE"] = (
            "2026-09-10T16:00:00+02:00"
        )
        self.write("older", "first\n")
        self.commit("older instant")
        self.env["GIT_AUTHOR_DATE"] = self.env["GIT_COMMITTER_DATE"] = (
            "2026-09-10T12:00:00-07:00"
        )
        self.write("newer", "second\n")
        self.commit("newer instant")
        output = self.nav("hot", "--since", "2000-01-01", "--by", "recent")
        self.assertLess(output.index("newer: touches"), output.index("older: touches"))

    def test_peek_suggests_code_before_newer_reports_without_hiding_commits(
        self,
    ) -> None:
        self.write("src/task.py", "def run():\n    return 1\n")
        code = self.commit("plain update")
        self.write("research/report.json", '{"result": 1}\n')
        report = self.commit("critical important bug fix")
        output = self.nav("peek", "--list")
        self.assertLess(output.index("| " + code[:7]), output.index("| " + report[:7]))
        self.assertIn("1 code", output)
        self.assertIn("src/task.py", output)
        self.assertIn("other changes", output)
        chronological = self.nav("peek", "--list", "--chronological")
        self.assertLess(
            chronological.index("| " + report[:7]), chronological.index("| " + code[:7])
        )
        scoped = self.nav("peek", "--list", "--", "research/")
        self.assertNotIn(code[:7], scoped)
        self.assertIn(report[:7], scoped)
        self.assertNotIn("1 code", scoped)
        filtered = self.nav("peek", "--list", "--grep", "CRITICAL")
        self.assertIn(report[:7], filtered)
        self.assertNotIn(code[:7], filtered)
        self.assertIn("grep 'CRITICAL'", filtered)
        self.nav("peek", "--list", "--grep", "", code=2)
        self.nav("peek", "--list", "--grep", "critical", "--commit", "HEAD", code=2)

    def test_peek_recognizes_shell_guidance_and_build_changes_including_deletions(
        self,
    ) -> None:
        self.write("SHELL/.bash_functions", "f() { true; }\n")
        self.write("skills/example/SKILL.md", "Instructions\n")
        self.write("pyproject.toml", "[project]\n")
        self.commit("initial tooling")
        (self.root / "SHELL/.bash_functions").unlink()
        self.commit("removed function file")
        output = self.nav("peek", "--list")
        for evidence in (
            "shell helpers",
            "agent guidance",
            "build/setup",
            "D SHELL/.bash_functions",
        ):
            self.assertIn(evidence, output)

    def test_peek_bind_ctrl_t_toggles_preview_panel_width(self) -> None:
        from nav_browser import choose

        captured: dict[str, list[str]] = {}
        fake = mock.Mock(
            returncode=130, stdout=b"", stderr=b"cancelled"
        )

        def capture(args, **kwargs):
            captured["args"] = list(args)
            return fake

        with tempfile.TemporaryDirectory(prefix="git-nav-choose-test-") as directory:
            with mock.patch("nav_browser.subprocess.run", side_effect=capture):
                result = choose(
                    mock.Mock(cwd=str(self.root)),
                    Path(directory),
                    [{"kind": "commit"}],
                    ["abc1234 commit subject"],
                    "commit (* suggested)",
                )
        self.assertIsNone(result)
        self.assertIn("ctrl-t:toggle-preview", captured["args"])
        header = captured["args"][captured["args"].index("--header") + 1]
        self.assertIn("Ctrl-T", header)

    def test_preview_colorize_marks_added_and_deleted_lines(self) -> None:
        from nav_browser import colorize_patch

        patch = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,2 +1,2 @@\n"
            " keep\n"
            "-old\n"
            "+new\n"
        )
        colored = colorize_patch(patch)
        self.assertIn("\x1b[38;5;114m+new", colored)
        self.assertIn("\x1b[38;5;167m-old", colored)
        self.assertIn("\x1b[1m\x1b[36m@@", colored)
        self.assertIn("keep", colored)
        self.assertNotIn("\x1b[38;5;114m+new", patch)

    def test_preview_format_patch_prefers_delta_then_falls_back(self) -> None:
        from nav_browser import format_patch

        patch = "-old\n+new\n"
        with mock.patch("nav_browser.shutil.which", return_value="/usr/bin/delta"):
            with mock.patch(
                "nav_browser.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout=b"delta-out\n"),
            ) as run:
                self.assertEqual(format_patch(patch), "delta-out\n")
                args = run.call_args[0][0]
                self.assertEqual(args[0], "delta")
                self.assertIn("--paging=never", args)
        with mock.patch("nav_browser.shutil.which", return_value=None):
            self.assertIn("+new", format_patch(patch))
            self.assertIn("\x1b[", format_patch(patch))

    def test_file_list_footer_carries_full_commit_message_body(self) -> None:
        from nav_browser import choose, commit_footer

        self.write("a.py", "x = 1\n")
        self.commit("Subject line\n\nBody paragraph one.\nBody paragraph two.\n")
        comparison = mock.Mock(commit="HEAD", title="commit: HEAD")
        # Use a real Repo so git show works.
        import os
        from nav_core import Repo

        old_cwd = os.getcwd()
        os.chdir(self.root)
        try:
            repo = Repo()
            footer = commit_footer(repo, comparison)
        finally:
            os.chdir(old_cwd)
        self.assertIn("Subject line", footer)
        self.assertIn("Body paragraph one.", footer)
        self.assertIn("Body paragraph two.", footer)

        captured: dict[str, list[str]] = {}
        fake = mock.Mock(returncode=130, stdout=b"", stderr=b"cancelled")

        def capture(args, **kwargs):
            captured["args"] = list(args)
            return fake

        with tempfile.TemporaryDirectory(prefix="git-nav-choose-test-") as directory:
            with mock.patch("nav_browser.subprocess.run", side_effect=capture):
                choose(
                    mock.Mock(cwd=str(self.root)),
                    Path(directory),
                    [{"kind": "file"}],
                    ["M source +1/-0 a.py"],
                    "file",
                    footer=footer,
                )
        self.assertIn("--footer", captured["args"])
        self.assertEqual(captured["args"][captured["args"].index("--footer") + 1], footer)
        self.assertIn("--footer-border=line", captured["args"])

    def test_peek_suggestions_use_batched_git_not_per_commit_diffs(self) -> None:
        # 20 commits: launch must stay O(1) git processes for scoring, not O(N).
        for i in range(20):
            self.write(f"src/f{i}.py", f"x = {i}\n")
            self.commit(f"change {i}")
        result = subprocess.run(
            [sys.executable, "-B", str(CLI), "peek", "--list"],
            cwd=self.root,
            env=dict(self.env, G_HELPERS_ECHO="1"),
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        output = result.stdout.decode()
        stderr = result.stderr.decode()
        self.assertIn("1 code", output)
        self.assertIn("change 19", output)
        self.assertIn("change 0", output)
        # Exactly one batched name-status call; zero per-commit --raw diffs.
        name_status = [
            line for line in stderr.splitlines() if "diff-tree" in line and "--stdin" in line
        ]
        raw_diffs = [
            line
            for line in stderr.splitlines()
            if line.startswith("+ git") and "diff" in line and "--raw" in line
        ]
        self.assertEqual(len(name_status), 1, stderr)
        self.assertEqual(len(raw_diffs), 0, stderr)


if __name__ == "__main__":
    unittest.main()
