"""Devin's local terminal-message boundary, with a real SQLite fixture and no model calls."""

import json
from contextlib import closing
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "scripts/run-worker.sh"
SCHEMA = '''CREATE TABLE sessions (id TEXT,working_directory TEXT,created_at INTEGER,main_chain_id INTEGER);
    CREATE TABLE prompt_history (session_id TEXT,content TEXT);
    CREATE TABLE message_nodes (session_id TEXT,node_id INTEGER,chat_message TEXT);'''
# Stands in for Devin itself: records the prompt it actually received, as Devin does.
RECORD_PROMPT = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('UPDATE prompt_history SET content=?', (sys.argv[2],)); c.commit()"
# A Devin session that commits its own row, then waits until a peer has too.
CONCURRENT_DEVIN = '''
import json, os, sqlite3, sys, time, uuid
database, prompt = sys.argv[1], sys.argv[2]
sid = uuid.uuid4().hex
connection = sqlite3.connect(database, timeout=10, isolation_level=None)  # polling must not hold a read lock
connection.execute("BEGIN IMMEDIATE")
connection.execute("INSERT INTO sessions VALUES (?,?,?,?)", (sid, os.getcwd(), int(time.time()), 3))
connection.execute("INSERT INTO prompt_history VALUES (?,?)", (sid, prompt))
connection.execute("INSERT INTO message_nodes VALUES (?,?,?)",
                   (sid, 3, json.dumps({"role": "assistant", "content": "FINAL " + sid, "tool_calls": []})))
connection.execute("COMMIT")
deadline = time.time() + 10
while connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] < 2 and time.time() < deadline:
    time.sleep(0.02)
connection.close()
print("FINAL " + sid)
'''


class DevinWorkerTests(unittest.TestCase):
    def run_worker(self, terminal=None, status=0, raw="Progress one.Progress two.FINAL\n", duplicate=False):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            database = home / ".local/share/devin/cli/sessions.db"
            database.parent.mkdir(parents=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript(SCHEMA)
                for sid in (["worker", "collision"] if duplicate else ["worker"]):
                    connection.execute("INSERT INTO sessions VALUES (?,?,?,?)", (sid, os.getcwd(), int(time.time()) + 1, 3))
                    connection.execute("INSERT INTO prompt_history VALUES (?,?)", (sid, "TASK"))
                    for node, message in ((1, {"role": "assistant", "content": "Progress one.", "tool_calls": [{"name": "exec"}]}),
                                          (3, terminal or {"role": "assistant", "content": "FINAL", "tool_calls": []}),
                                          (99, {"role": "assistant", "content": "Wrong branch", "tool_calls": []})):
                        connection.execute("INSERT INTO message_nodes VALUES (?,?,?)", (sid, node, json.dumps(message)))
                connection.commit()
            wrappers = home / "wrappers"
            wrappers.write_text(f'dswe() {{ python3 -c "{RECORD_PROMPT}" "{database}" "$2"; '
                                f'printf "%s" "$DEVIN_TEST_RAW"; return {status}; }}\n')
            return subprocess.run(["bash", str(RUNNER), "dswe"], input="TASK", text=True, capture_output=True,
                                  env={**os.environ, "HOME": str(home), "BASH_AGENTS_FILE": str(wrappers), "DEVIN_TEST_RAW": raw}, timeout=10)

    def test_tool_using_turn_returns_only_the_committed_terminal_message(self):
        result = self.run_worker()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "FINAL\n")
        self.assertIn("Progress one.Progress two.", result.stderr)
        self.assertNotIn("Wrong branch", result.stdout)

    def test_failure_after_partial_output_preserves_exit_and_no_final(self):
        result = self.run_worker(status=7)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "")

    def test_unknown_malformed_or_nonterminal_response_fails_closed(self):
        cases = [{"role": "tool", "content": "FINAL"}, {"role": "assistant", "content": "FINAL", "tool_calls": [{"name": "exec"}]},
                 {"role": "assistant", "content": ""}, {"future_schema": True}]
        for terminal in cases:
            with self.subTest(terminal=terminal):
                result = self.run_worker(terminal)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_stdout_mismatch_and_ambiguous_sessions_fail_closed(self):
        for options in ({"raw": "PARTIAL"}, {"duplicate": True}):
            with self.subTest(options=options):
                result = self.run_worker(**options)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_concurrent_same_task_workers_each_return_their_own_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            database = home / ".local/share/devin/cli/sessions.db"
            database.parent.mkdir(parents=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript(SCHEMA)
            fake = home / "devin.py"
            fake.write_text(CONCURRENT_DEVIN)
            wrappers = home / "wrappers"
            wrappers.write_text(f'dswe() {{ python3 "{fake}" "{database}" "$2"; }}\n'
                                f'dargh() {{ python3 "{fake}" "{database}" "$2"; }}\n')
            task = home / "task.md"
            task.write_text("SAME TASK")
            env = {**os.environ, "HOME": str(home), "BASH_AGENTS_FILE": str(wrappers)}
            workers = [subprocess.Popen(["bash", str(RUNNER), launcher, "--task-file", str(task)],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, env=env)
                       for launcher in ("dswe", "dargh")]
            results = [worker.communicate(timeout=30) for worker in workers]
            for worker, (stdout, stderr) in zip(workers, results):
                self.assertEqual(worker.returncode, 0, stderr)
                self.assertRegex(stdout, r"^FINAL [0-9a-f]{32}\n$")
            self.assertNotEqual(results[0][0], results[1][0])


if __name__ == "__main__":
    unittest.main()
