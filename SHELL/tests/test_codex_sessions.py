import json
import os
import pty
import select
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = ROOT / ".bash_agents"
HELPER = ROOT / "codex_sessions.py"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-sessions-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.env = dict(os.environ)
        for name in (
            "CODEX_HOME",
            "CODEX_BARE_STATE_ROOT",
            "CODEX_FRESH_STATE_ROOT",
            "CODEX_WRAPPER_SCOPE",
            "CODEX_SQLITE_HOME",
            "CODEX_RESUME_LAUNCHER",
        ):
            self.env.pop(name, None)
        self.env.update(
            CODEX_CANONICAL_HOME=str(self.root / "canonical"),
            CODEX_STATE_ROOT=str(self.root / "state"),
            CODEX2_HOME=str(self.root / "canonical2"),
            CODEX2_STATE_ROOT=str(self.root / "state2"),
            CODEX_SESSION_HELPER=str(HELPER),
            CODEX_RESUME_CONFIG=str(self.root / "resume.conf"),
        )
        for name in ("canonical", "canonical2"):
            home = self.root / name
            home.mkdir()
            (home / "auth.json").write_text("{}\n")
            (home / "skills").mkdir()

    def shell(self, body, *args, check=True):
        return subprocess.run(
            ["bash", "-c", 'source "$1"; shift; ' + body, "test", str(WRAPPERS), *args],
            env=self.env,
            cwd=self.project,
            text=True,
            capture_output=True,
            check=check,
        )

    def rollout(self, home, session_id=None, cwd=None, archived=False):
        session_id = session_id or str(uuid.uuid4())
        directory = home / ("archived_sessions" if archived else "sessions/2026/09/15")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"rollout-2026-09-15T12-00-00-{session_id}.jsonl"
        metadata = {
            "id": session_id,
            "cwd": str(cwd or self.project),
            "source": "cli",
            "timestamp": "2026-09-15T12:00:00Z",
            "originator": "codex_cli_rs",
            "cli_version": "0.154.0",
            "model_provider": "openai",
        }
        path.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "timestamp": metadata["timestamp"],
                    "payload": metadata,
                }
            )
            + "\n"
        )
        return session_id

    def helper(self, *args, check=True):
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            env=self.env,
            cwd=self.project,
            text=True,
            capture_output=True,
            check=check,
        )

    def stub_codex(self):
        directory = self.root / "bin"
        directory.mkdir()
        stub = directory / "codex"
        stub.write_text(
            "#!" + sys.executable + "\nimport json, os, sys\n"
            'print(json.dumps({"args": sys.argv[1:], "env": dict(os.environ)}))\n'
            'sys.exit(int(os.environ.get("TEST_CODEX_EXIT", "0")))\n'
        )
        stub.chmod(0o755)
        self.env["PATH"] = str(directory) + os.pathsep + self.env["PATH"]


class BareHomeTests(Fixture):
    def test_reuses_home_and_keeps_saved_session(self):
        first = Path(self.shell('_codex_prepare_bare_home "$PWD"').stdout.strip())
        (first / "sessions").mkdir()
        (first / "sessions" / "saved").write_text("retained")
        second = Path(self.shell('_codex_prepare_bare_home "$PWD"').stdout.strip())
        self.assertEqual(first, second)
        self.assertEqual((second / "sessions/saved").read_text(), "retained")

    def test_rejects_retained_home_instructions_without_removing_them(self):
        home = Path(self.shell('_codex_prepare_bare_home "$PWD"').stdout.strip())
        for name in ("AGENTS.md", "AGENTS.override.md"):
            with self.subTest(name=name):
                marker = home / name
                marker.write_text("do not delete")
                result = self.shell('_codex_prepare_bare_home "$PWD"', check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name, result.stderr)
                self.assertEqual(marker.read_text(), "do not delete")
                marker.unlink()

    def test_account_project_and_hook_isolation(self):
        plain = Path(self.shell('_codex_prepare_bare_home "$PWD"').stdout.strip())
        hook = Path(
            self.shell(
                '_codex_prepare_bare_home "$PWD" review-after-commit'
            ).stdout.strip()
        )
        secondary = Path(
            self.shell(
                '_codex_secondary _codex_prepare_bare_home "$PWD"'
            ).stdout.strip()
        )
        other = self.root / "other" / self.project.name
        other.mkdir(parents=True)
        different_project = Path(
            self.shell('_codex_prepare_bare_home "$1"', str(other)).stdout.strip()
        )
        self.assertEqual(len({plain, hook, secondary, different_project}), 4)
        self.assertEqual(
            (secondary / "auth.json").resolve(), self.root / "canonical2/auth.json"
        )
        self.assertFalse((plain / "hooks").exists())
        config = tomllib.loads((plain / "config.toml").read_text())
        self.assertFalse(config["skills"]["include_instructions"])
        self.assertFalse(config["memories"]["use_memories"])
        self.assertEqual(
            config["projects"][str(self.project)]["trust_level"], "untrusted"
        )

    def test_refreshes_config_without_partial_writes_or_losing_sessions(self):
        home = Path(self.shell('_codex_prepare_bare_home "$PWD"').stdout.strip())
        (home / "config.toml").write_text('developer_instructions = "unwanted"\n')
        processes = [
            subprocess.Popen(
                [
                    "bash",
                    "-c",
                    'source "$1"; _codex_prepare_bare_home "$PWD"',
                    "test",
                    str(WRAPPERS),
                ],
                cwd=self.project,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(4)
        ]
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(Path(stdout.strip()), home)
        config = tomllib.loads((home / "config.toml").read_text())
        self.assertNotIn("developer_instructions", config)
        self.assertEqual(list(home.glob(".config.toml.*")), [])

    def test_does_not_overwrite_config_symlink(self):
        home = Path(self.shell('_codex_prepare_bare_home "$PWD"').stdout.strip())
        target = self.root / "unowned.toml"
        target.write_text("# preserve\n")
        (home / "config.toml").unlink()
        (home / "config.toml").symlink_to(target)
        result = self.shell('_codex_prepare_bare_home "$PWD"', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "# preserve\n")

    def test_launch_and_resume_use_same_home_and_forward_cd(self):
        self.stub_codex()
        other = self.root / "other"
        other.mkdir()
        first = json.loads(self.shell('cdxb -C "$1"', str(other)).stdout)
        second = json.loads(self.shell('cdxb -C "$1" resume --last', str(other)).stdout)
        self.assertEqual(first["env"]["CODEX_HOME"], second["env"]["CODEX_HOME"])
        config = tomllib.loads(
            (Path(first["env"]["CODEX_HOME"]) / "config.toml").read_text()
        )
        self.assertIn(str(other), config["projects"])
        self.assertIn("resume", second["args"])


class ResumeTests(Fixture):
    def test_storage_redirect_does_not_split_writer_lock_domain(self):
        session_id = self.rollout(self.root / "canonical")
        for options in (
            ("-c", 'sqlite_home="/tmp/other"'),
            ('--config=sqlite_home="/tmp/other"',),
            ('-csqlite_home="/tmp/other"',),
            ("--remote=unix:///tmp/other",),
        ):
            with self.subTest(options=options):
                result = self.helper(
                    session_id, "--dry-run", "--", *options, check=False
                )
                self.assertNotEqual(result.returncode, 0)

    @unittest.skipUnless(shutil.which("fzf"), "fzf is not installed")
    def test_real_fzf_picker_in_a_pty_selects_the_correct_account(self):
        primary_id = self.rollout(self.root / "canonical")
        home = self.root / "state2/bare/codex-bare.legacy"
        session_id = self.rollout(home)
        Path(self.env["CODEX_RESUME_CONFIG"]).write_text("limit=1\n")
        primary = next(
            (self.root / "canonical/sessions").glob(f"*/*/*/*{primary_id}.jsonl")
        )
        os.utime(primary, (time.time() + 60, time.time() + 60))
        env = dict(self.env, FZF_DEFAULT_OPTS=f"--filter={session_id}")
        child, terminal = pty.fork()
        if child == 0:
            os.chdir(self.project)
            os.execvpe(
                "bash",
                [
                    "bash",
                    "-c",
                    'source "$1"; cdxr --all --dry-run',
                    "pty-test",
                    str(WRAPPERS),
                ],
                env,
            )
        output = bytearray()
        status = None
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if select.select([terminal], [], [], 0.1)[0]:
                    try:
                        data = os.read(terminal, 65536)
                    except OSError:
                        break
                    if not data:
                        break
                    output.extend(data)
                exited, status = os.waitpid(child, os.WNOHANG)
                if exited:
                    break
            else:
                self.fail("PTY picker timed out")
            if status is None:
                _, status = os.waitpid(child, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), 0, output.decode())
            selected = json.loads(output)
            self.assertEqual(selected["id"], session_id)
            self.assertEqual(selected["account"], "2")
            self.assertEqual(selected["home"], str(home))
        finally:
            os.close(terminal)
            try:
                exited, _ = os.waitpid(child, os.WNOHANG)
                if not exited:
                    os.kill(child, 15)
                    os.waitpid(child, 0)
            except ChildProcessError:
                pass

    def test_resume_defaults_keep_native_explicit_effort_authoritative(self):
        Path(self.env["CODEX_RESUME_CONFIG"]).write_text(
            "any=1 # all directories\nlimit=50\neffort=high # old default\nfull_auto=1\n"
        )
        session_id = self.rollout(self.root / "canonical", cwd=self.root / "elsewhere")
        result = json.loads(self.helper("--last", "--dry-run").stdout)
        self.assertEqual(result["id"], session_id)
        self.assertIn('model_reasoning_effort="high"', result["command"])
        native = json.loads(
            self.helper(
                session_id, "-c", 'model_reasoning_effort="max"', "--dry-run"
            ).stdout
        )
        self.assertNotIn('model_reasoning_effort="high"', native["command"])
        self.assertNotIn("--full-auto", native["command"])

    def test_child_sessions_are_opt_in_but_direct_ids_always_work(self):
        home = self.root / "canonical"
        session_id = self.rollout(home)
        path = next((home / "sessions").glob("*/*/*/*.jsonl"))
        row = json.loads(path.read_text())
        row["payload"]["source"] = {"subagent": {"thread_spawn": {}}}
        path.write_text(json.dumps(row) + "\n")
        self.assertEqual(json.loads(self.helper("--list", "--json").stdout), [])
        self.assertEqual(
            len(
                json.loads(
                    self.helper("--list", "--json", "--include-subagents").stdout
                )
            ),
            1,
        )
        self.assertEqual(
            json.loads(self.helper(session_id, "--dry-run").stdout)["id"], session_id
        )

    def test_old_metadata_without_cwd_is_visible_only_without_directory_filter(self):
        home = self.root / "canonical"
        session_id = self.rollout(home)
        path = next((home / "sessions").glob("*/*/*/*.jsonl"))
        path.write_text(
            json.dumps(
                {
                    "id": session_id,
                    "timestamp": "2025-09-03T00:00:00Z",
                    "instructions": "",
                }
            )
            + "\n"
        )
        self.assertEqual(json.loads(self.helper("--list", "--json").stdout), [])
        listed = json.loads(self.helper("--list", "--all", "--json").stdout)
        self.assertEqual(listed[0]["id"], session_id)
        self.assertEqual(listed[0]["cwd"], "")
        rejected = self.helper(session_id, "--dry-run", check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("requires format conversion", rejected.stderr)

    def test_archived_resume_unarchives_only_the_selected_source(self):
        self.stub_codex()
        home = self.root / "canonical2"
        session_id = self.rollout(home, archived=True)
        plan = json.loads(self.helper(session_id, "--dry-run").stdout)
        self.assertEqual(plan["before_resume"], ["codex", "unarchive", session_id])
        actual = [
            json.loads(line) for line in self.helper(session_id).stdout.splitlines()
        ]
        self.assertEqual(
            [call["args"][:2] for call in actual],
            [["unarchive", session_id], ["resume", session_id]],
        )
        self.assertTrue(all(call["env"]["CODEX_HOME"] == str(home) for call in actual))
        self.env["TEST_CODEX_EXIT"] = "13"
        failed = self.helper(session_id, check=False)
        self.assertEqual(failed.returncode, 13)
        self.assertEqual(len(failed.stdout.splitlines()), 1)

    def test_custom_bare_root_keeps_bare_classification(self):
        bare = self.root / "state/custom-bare"
        self.env["CODEX_BARE_STATE_ROOT"] = str(bare)
        session_id = self.rollout(bare / "codex-bare.old")
        row = json.loads(self.helper(session_id, "--dry-run").stdout)
        self.assertEqual(row["kind"], "bare")

    def test_all_layouts_and_accounts_including_legacy_bare(self):
        homes = []
        for suffix in ("", "2"):
            state = self.root / f"state{suffix}"
            homes += [
                self.root / f"canonical{suffix}",
                state / "repos/project-key",
                state / "fresh/codex-fresh.old",
                state / "bare/codex-bare.old",
                state / "bare/repos/project-key/plain",
                state / "bare/repos/project-key/review-after-commit",
                state / "old-repo/feature",
            ]
        ids = {self.rollout(home) for home in homes}
        outside = self.rollout(homes[0], cwd=self.root / "another-project")
        visible = json.loads(
            self.helper("--list", "--json", "--all", "--limit", "0").stdout
        )
        self.assertEqual({s["id"] for s in visible}, ids | {outside})
        current = json.loads(self.helper("--list", "--json").stdout)
        self.assertEqual({s["id"] for s in current}, ids)
        selected = json.loads(self.helper(outside, "--dry-run").stdout)
        self.assertEqual(selected["id"], outside)
        for account in ("1", "2"):
            filtered = json.loads(
                self.helper("--list", "--json", "--all", "--account", account).stdout
            )
            self.assertEqual({s["account"] for s in filtered}, {account})

    def test_database_only_paginated_and_archive_metadata(self):
        home = self.root / "canonical2"
        session_id = str(uuid.uuid4())
        archived_id = self.rollout(home)
        with sqlite3.connect(home / "state_5.sqlite") as db:
            db.execute(
                "CREATE TABLE threads (id TEXT, cwd TEXT, title TEXT, name TEXT, updated_at INTEGER, updated_at_ms INTEGER, source TEXT, history_mode TEXT, archived INTEGER)"
            )
            db.executemany(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        session_id,
                        str(self.project),
                        "old title",
                        "named session",
                        1,
                        5000,
                        "exec",
                        "paginated",
                        0,
                    ),
                    (
                        archived_id,
                        str(self.project),
                        "archived",
                        None,
                        1,
                        2000,
                        "cli",
                        "legacy",
                        1,
                    ),
                ],
            )
        before = (home / "state_5.sqlite").read_bytes()
        rows = json.loads(self.helper("--list", "--json").stdout)
        self.assertEqual([r["id"] for r in rows], [session_id])
        self.assertEqual(rows[0]["history_mode"], "paginated")
        self.assertEqual(rows[0]["updated"], 5)
        self.assertEqual(
            len(
                json.loads(self.helper("--list", "--json", "--include-archived").stdout)
            ),
            2,
        )
        launch = json.loads(self.helper("named session", "--dry-run").stdout)
        self.assertEqual(launch["command"], ["codex", "resume", session_id])
        self.assertEqual((home / "state_5.sqlite").read_bytes(), before)

    def test_duplicate_ids_require_source_home(self):
        one, two = self.root / "canonical", self.root / "canonical2"
        session_id = self.rollout(one)
        self.rollout(two, session_id)
        result = self.helper(session_id, "--dry-run", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ambiguous", result.stderr)
        selected = json.loads(
            self.helper(session_id, "--home", str(two), "--dry-run").stdout
        )
        self.assertEqual(selected["account"], "2")

    def test_unindexed_session_name_and_last(self):
        home = self.root / "canonical"
        first = self.rollout(home)
        second = self.rollout(home)
        (home / "session_index.jsonl").write_text(
            json.dumps({"id": first, "thread_name": "earlier"}) + "\n" + '{"id":'
        )
        files = list((home / "sessions").glob("*/*/*/*.jsonl"))
        for path in files:
            timestamp = 10 if first in path.name else 20
            os.utime(path, (timestamp, timestamp))
        named = json.loads(self.helper("earlier", "--dry-run").stdout)
        self.assertEqual(named["id"], first)
        self.assertEqual(
            json.loads(self.helper("--last", "--dry-run").stdout)["id"], second
        )

    def test_cdxr_keeps_source_account_and_native_arguments_and_exit_status(self):
        self.stub_codex()
        home = self.root / "state2/bare/codex-bare.old"
        session_id = self.rollout(home)
        self.env.update(
            OPENAI_API_KEY="ambient-fixture",
            CODEX_API_KEY="ambient-fixture",
            CODEX_ACCESS_TOKEN="ambient-fixture",
            CODEX_SQLITE_HOME=str(self.root / "wrong-database"),
            TEST_CODEX_EXIT="17",
        )
        result = self.shell(
            'cdxr "$1" --ctx-mgmt -m test-model -- "continuation with spaces"',
            session_id,
            check=False,
        )
        self.assertEqual(result.returncode, 17, result.stderr)
        captured = json.loads(result.stdout)
        self.assertEqual(captured["env"]["CODEX_HOME"], str(home))
        self.assertEqual(
            captured["env"]["CODEX_CANONICAL_HOME"], str(self.root / "canonical2")
        )
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "CODEX_SQLITE_HOME"):
            self.assertNotIn(key, captured["env"])
        self.assertEqual(captured["args"][:2], ["resume", session_id])
        self.assertIn(
            "features.context_management.experimental_mode=true", captured["args"]
        )
        self.assertIn("test-model", captured["args"])
        self.assertIn("continuation with spaces", captured["args"])

    def test_context_flag_stays_before_native_prompt_delimiter(self):
        self.stub_codex()
        session_id = self.rollout(self.root / "canonical")
        result = self.shell(
            'cdxr "$1" --ctx-mgmt -- -- "--remote is prompt text"', session_id
        )
        arguments = json.loads(result.stdout)["args"]
        self.assertLess(
            arguments.index("features.context_management.experimental_mode=true"),
            arguments.index("--"),
        )
        self.assertEqual(arguments[-1], "--remote is prompt text")

    def test_cdxr2_filters_secondary_and_does_not_create_scoped_home(self):
        self.rollout(self.root / "canonical")
        session_id = self.rollout(self.root / "state2/bare/codex-bare.old")
        result = self.shell("cdxr2 --list --json")
        rows = json.loads(result.stdout)
        self.assertEqual([s["id"] for s in rows], [session_id])
        self.assertFalse((self.root / "state/repos").exists())

    def test_bare_resume_rejects_home_instruction_leak(self):
        home = self.root / "state/bare/codex-bare.old"
        session_id = self.rollout(home)
        (home / "AGENTS.override.md").write_text("unwanted")
        result = self.helper(session_id, "--dry-run", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AGENTS.override.md", result.stderr)

    def test_corrupt_store_is_reported_and_other_account_still_discovered(self):
        (self.root / "canonical/state_5.sqlite").write_bytes(b"invalid sqlite")
        session_id = self.rollout(self.root / "canonical2")
        result = self.helper("--list", "--json")
        self.assertIn("cannot read", result.stderr)
        self.assertEqual([s["id"] for s in json.loads(result.stdout)], [session_id])

    def test_noninteractive_picker_does_not_launch_any_session(self):
        self.rollout(self.root / "canonical")
        result = self.helper(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs a terminal", result.stderr)


if __name__ == "__main__":
    unittest.main()
