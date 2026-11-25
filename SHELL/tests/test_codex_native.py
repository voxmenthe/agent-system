"""Opt-in local CLI checks; no authenticated model calls or real session writes."""

import json
import os
import selectors
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from test_codex_sessions import Fixture


class NativeServer:
    def __init__(self, home, cwd, env):
        self.errors = (home / f"probe-stderr-{time.monotonic_ns()}").open("w")
        self.process = subprocess.Popen(
            [shutil.which("codex"), "app-server"],
            cwd=cwd,
            env=dict(env, CODEX_HOME=str(home)),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = b""
        self.counter = 0
        reply = self.request(
            "initialize", {"clientInfo": {"name": "bare_resume_test", "version": "1"}}
        )
        if "error" in reply:
            self.close()
            raise AssertionError(reply)
        self.send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    def send(self, message):
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()

    def request(self, method, params):
        self.counter += 1
        self.send(
            {"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params}
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                reply = json.loads(line)
                if reply.get("id") == self.counter:
                    return reply
            if self.selector.select(timeout=0.1):
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise AssertionError("Native app-server exited before replying")
                self.buffer += chunk
        raise AssertionError(f"Native app-server timed out: {method}")

    def close(self):
        self.selector.close()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.process.stdout.close()
        self.errors.close()


@unittest.skipUnless(
    os.environ.get("CODEX_NATIVE_TESTS") == "1",
    "set CODEX_NATIVE_TESTS=1 for installed-CLI probes",
)
class NativeTests(Fixture):
    def setUp(self):
        super().setUp()
        for key in ("OPENAI_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_BASE_URL"):
            self.env.pop(key, None)

    def test_persistent_bare_prompt_stays_minimal_with_saved_history(self):
        canonical = self.root / "canonical"
        (canonical / "AGENTS.md").write_text("CANONICAL_LEAK_MARKER")
        skill = canonical / "skills/probe-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: SKILL_LEAK_MARKER\ndescription: Unexpected skill inventory\n---\nBody"
        )
        (self.project / "AGENTS.md").write_text("PROJECT_LEAK_MARKER")
        (self.project / ".codex").mkdir()
        (self.project / ".codex/config.toml").write_text(
            'developer_instructions = "CONFIG_LEAK_MARKER"\n'
        )
        home = Path(self.shell('_codex_prepare_bare_home "$PWD"').stdout.strip())

        def render():
            output = subprocess.run(
                [
                    shutil.which("codex"),
                    "-m",
                    "gpt-5.6-sol",
                    "debug",
                    "prompt-input",
                    "CURRENT_USER_MARKER",
                ],
                cwd=self.project,
                env=dict(self.env, CODEX_HOME=str(home)),
                text=True,
                capture_output=True,
                check=True,
                timeout=15,
            )
            value = json.loads(output.stdout)
            return [
                c["text"]
                for item in value
                if item.get("type") == "message"
                for c in item.get("content", [])
                if "text" in c
            ]

        before = render()
        self.rollout(home)
        (home / "memories").mkdir(exist_ok=True)
        (home / "memories/memory_summary.md").write_text("MEMORY_LEAK_MARKER")
        (home / "history.jsonl").write_text(
            json.dumps({"session_id": "old", "ts": 1, "text": "HISTORY_LEAK_MARKER"})
            + "\n"
        )
        again = Path(self.shell('_codex_prepare_bare_home "$PWD"').stdout.strip())
        self.assertEqual(home, again)
        after = render()
        self.assertEqual(before, after)
        self.assertIn("CURRENT_USER_MARKER", str(after))
        self.assertNotIn("LEAK_MARKER", str(after))

    def test_native_resume_uses_original_history_and_writer_lock(self):
        home = self.root / "state2/bare/codex-bare.fixture"
        session_id = self.rollout(home)
        (home / "config.toml").write_text("""model = "gpt-5.6-sol"
model_provider = "fixture"
project_doc_max_bytes = 0
[model_providers.fixture]
name = "Local fixture (no turns are submitted)"
base_url = "http://127.0.0.1:1/v1"
wire_api = "responses"
requires_openai_auth = false
[features]
apps = false
plugins = false
memories = false
""")
        rollout = next((home / "sessions").glob("*/*/*/*.jsonl"))
        row = json.loads(rollout.read_text())
        row["payload"]["model_provider"] = "fixture"
        rollout.write_text(json.dumps(row) + "\n")
        with rollout.open("a") as handle:
            for role, kind, text in (
                ("user", "input_text", "Earlier saved user text"),
                ("assistant", "output_text", "Earlier saved assistant text"),
            ):
                handle.write(
                    json.dumps(
                        {
                            "timestamp": row["timestamp"],
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": role,
                                "content": [{"type": kind, "text": text}],
                            },
                        }
                    )
                    + "\n"
                )
                event = {
                    "type": "user_message" if role == "user" else "agent_message",
                    "message": text,
                }
                if role == "user":
                    event.update(images=[], local_images=[], text_elements=[])
                handle.write(
                    json.dumps(
                        {
                            "timestamp": row["timestamp"],
                            "type": "event_msg",
                            "payload": event,
                        }
                    )
                    + "\n"
                )
        plan = json.loads(self.helper(session_id, "--dry-run").stdout)
        self.assertEqual(plan["home"], str(home))
        self.assertEqual(plan["account"], "2")
        first = NativeServer(Path(plan["home"]), self.project, self.env)
        self.addCleanup(first.close)
        read = first.request(
            "thread/read", {"threadId": session_id, "includeTurns": True}
        )
        self.assertNotIn("error", read, read)
        self.assertIn("Earlier saved user text", json.dumps(read))
        resumed = first.request("thread/resume", {"threadId": session_id})
        self.assertNotIn("error", resumed, resumed)
        self.assertEqual(resumed["result"]["thread"]["id"], session_id)
        second = NativeServer(home, self.project, self.env)
        self.addCleanup(second.close)
        conflict = second.request("thread/resume", {"threadId": session_id})
        self.assertIn("error", conflict)
        self.assertIn("writer", json.dumps(conflict).lower())


if __name__ == "__main__":
    unittest.main()
