from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "hosts/kimi/adapter.py"
CODEX_ADAPTER = ROOT / "hosts/codex/adapter.py"
FIXTURES = ROOT / "tests/fixtures"


class KimiAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo with space"
        self.state_dir = self.root / "kimi-state"
        self.outcome_state = self.root / "outcomes"
        self._git("init", "-q", str(self.repo), cwd=self.root)
        self._git("config", "user.email", "hook-test@example.invalid")
        self._git("config", "user.name", "Hook Test")
        self._git("commit", "--allow-empty", "-qm", "initial")

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.strip()

    def _fixture(self, event: str) -> dict:
        name = {
            "PreToolUse": "kimi-pre-tool-use.json",
            "Stop": "kimi-stop.json",
        }[event]
        payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        payload["cwd"] = str(self.repo)
        return payload

    def invoke(
        self,
        *,
        event: str,
        command: str = "git status",
        tool_call_id: str = "fixture-tool",
        standard_every: int | None = None,
        branch_every: int | None = None,
        enabled: str = "1",
        mode: str = "cadence",
    ) -> subprocess.CompletedProcess[str]:
        payload = self._fixture(event)
        if event == "PreToolUse":
            payload["tool_call_id"] = tool_call_id
            payload["tool_input"] = {"command": command}
        env = os.environ.copy()
        env["KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED"] = enabled
        env["KIMI_HOOK_STATE_DIR"] = str(self.state_dir)
        env["REVIEW_AFTER_COMMIT_MODE"] = mode
        env["REVIEW_AFTER_COMMIT_OUTCOME_STATE"] = str(self.outcome_state)
        for name, value in (
            ("KIMI_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY", standard_every),
            ("KIMI_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY", branch_every),
        ):
            if value is None:
                env.pop(name, None)
            else:
                env[name] = str(value)
        return subprocess.run(
            ["/usr/bin/python3", str(ADAPTER)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def record_before(
        self,
        command: str,
        *,
        tool_call_id: str,
        standard_every: int | None = None,
        branch_every: int | None = None,
        mode: str = "cadence",
    ) -> None:
        result = self.invoke(
            event="PreToolUse",
            command=command,
            tool_call_id=tool_call_id,
            standard_every=standard_every,
            branch_every=branch_every,
            mode=mode,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    @staticmethod
    def denial_reason(result: subprocess.CompletedProcess[str]) -> str:
        output = json.loads(result.stdout)
        hook_output = output["hookSpecificOutput"]
        if hook_output["permissionDecision"] != "deny":
            raise AssertionError("Kimi delivery must use the verified deny boundary")
        return hook_output["permissionDecisionReason"]

    @staticmethod
    def request_json(context: str) -> dict:
        opening = context.index("<review-request-json")
        json_start = context.index("\n", opening) + 1
        json_end = context.index("\n</review-request-json>", json_start)
        return json.loads(context[json_start:json_end])

    def test_stop_delivers_pending_exact_read_only_request(self) -> None:
        command = "git commit --allow-empty -m one"
        before = self._git("rev-parse", "HEAD")
        self.record_before(command, tool_call_id="commit-1")
        self._git("commit", "--allow-empty", "-qm", "one")
        after = self._git("rev-parse", "HEAD")

        result = self.invoke(event="Stop")

        self.assertEqual(0, result.returncode, result.stderr)
        reason = self.denial_reason(result)
        request = self.request_json(reason)
        self.assertEqual(before, request["range"]["before"])
        self.assertEqual(after, request["range"]["after"])
        self.assertEqual("read-only-advisory-review", request["authority"])
        self.assertIn("Do not edit, stage, commit, publish", reason)
        self.assertNotIn("retry the blocked Bash command", reason)
        repeated = self.invoke(event="Stop")
        self.assertEqual(0, repeated.returncode, repeated.stderr)
        self.assertEqual("", repeated.stdout)

    def test_next_bash_delivers_pending_request_and_retry_reminder(self) -> None:
        command = "git commit --allow-empty -m one"
        self.record_before(command, tool_call_id="commit-1")
        self._git("commit", "--allow-empty", "-qm", "one")

        result = self.invoke(
            event="PreToolUse", command="git status", tool_call_id="status-1"
        )

        self.assertEqual(0, result.returncode, result.stderr)
        reason = self.denial_reason(result)
        self.assertIn("retry the blocked Bash command", reason)
        repeated = self.invoke(
            event="PreToolUse", command="git status", tool_call_id="status-1"
        )
        self.assertEqual(0, repeated.returncode, repeated.stderr)
        self.assertEqual("", repeated.stdout)

    def test_auto_stop_delivers_selected_evidence_and_records_delivery(self) -> None:
        self.repo.joinpath("module.py").write_text(
            "def choose(value=None):\n    return value\n", encoding="utf-8"
        )
        self._git("add", "module.py")
        self._git("commit", "-qm", "base")
        command = "git commit -am change"
        self.record_before(command, tool_call_id="commit-1", mode="auto")
        self.repo.joinpath("module.py").write_text(
            "def choose(value=[]):\n    return value\n", encoding="utf-8"
        )
        self._git("commit", "-am", "change", "-q")

        result = self.invoke(event="Stop", mode="auto")

        self.assertEqual(0, result.returncode, result.stderr)
        context = self.denial_reason(result)
        request = self.request_json(context)
        self.assertEqual("auto", request["mode"])
        self.assertIsNotNone(request["evidence"])
        self.assertIn("record-review-outcome", context)
        histories = list(self.outcome_state.glob("repositories/*/outcomes.jsonl"))
        self.assertEqual(1, len(histories))
        event = json.loads(histories[0].read_text(encoding="utf-8"))
        self.assertEqual("kimi", event["deliveries"][0]["host"])

    def test_standard_and_branch_intervals_match_shared_core(self) -> None:
        outputs = []
        for index in range(1, 7):
            command = "git commit --allow-empty -m {}".format(index)
            tool_id = "commit-{}".format(index)
            self.record_before(
                command,
                tool_call_id=tool_id,
                standard_every=2,
                branch_every=6,
            )
            self._git("commit", "--allow-empty", "-qm", str(index))
            outputs.append(
                self.invoke(
                    event="Stop", standard_every=2, branch_every=6
                )
            )

        self.assertEqual(
            [False, True, False, True, False, True],
            [bool(result.stdout) for result in outputs],
        )
        self.assertEqual(
            "recent", self.request_json(self.denial_reason(outputs[1]))["kind"]
        )
        self.assertEqual(
            "branch", self.request_json(self.denial_reason(outputs[5]))["kind"]
        )

    def test_disabled_registration_is_dormant_even_for_invalid_input(self) -> None:
        env = os.environ.copy()
        env["KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED"] = "0"
        result = subprocess.run(
            ["/usr/bin/python3", str(ADAPTER)],
            input="not json",
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        self.assertFalse(self.state_dir.exists())

    def test_error_log_does_not_copy_hook_payload(self) -> None:
        secret = "payload-secret-that-must-not-be-logged"
        env = os.environ.copy()
        env["KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED"] = "1"
        env["KIMI_HOOK_STATE_DIR"] = str(self.state_dir)
        result = subprocess.run(
            ["/usr/bin/python3", str(ADAPTER)],
            input=secret,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        self.assertNotEqual(0, result.returncode)
        log = (self.state_dir / "hook.log").read_text(encoding="utf-8")
        self.assertNotIn(secret, log)

    def test_codex_and_kimi_deliver_the_same_semantic_request(self) -> None:
        command = "git commit --allow-empty -m one"
        codex_state = self.root / "codex-state"
        codex_env = os.environ.copy()
        codex_env["CODEX_HOOK_STATE_DIR"] = str(codex_state)
        codex_env["REVIEW_AFTER_COMMIT_MODE"] = "cadence"
        codex_pre = json.loads(
            (FIXTURES / "codex-pre-tool-use.json").read_text(encoding="utf-8")
        )
        codex_pre["cwd"] = str(self.repo)
        codex_pre["tool_input"] = {"command": command}
        kimi_pre = self.invoke(
            event="PreToolUse", command=command, tool_call_id="fixture-tool"
        )
        self.assertEqual(0, kimi_pre.returncode, kimi_pre.stderr)
        codex_before = subprocess.run(
            ["/usr/bin/python3", str(CODEX_ADAPTER)],
            input=json.dumps(codex_pre),
            text=True,
            capture_output=True,
            env=codex_env,
            check=False,
        )
        self.assertEqual(0, codex_before.returncode, codex_before.stderr)
        self._git("commit", "--allow-empty", "-qm", "one")

        kimi_result = self.invoke(event="Stop")
        codex_post = json.loads(
            (FIXTURES / "codex-post-tool-use.json").read_text(encoding="utf-8")
        )
        codex_post["cwd"] = str(self.repo)
        codex_post["tool_input"] = {"command": command}
        codex_result = subprocess.run(
            ["/usr/bin/python3", str(CODEX_ADAPTER)],
            input=json.dumps(codex_post),
            text=True,
            capture_output=True,
            env=codex_env,
            check=False,
        )

        self.assertEqual(0, kimi_result.returncode, kimi_result.stderr)
        self.assertEqual(0, codex_result.returncode, codex_result.stderr)
        kimi_request = self.request_json(self.denial_reason(kimi_result))
        codex_context = json.loads(codex_result.stdout)["hookSpecificOutput"][
            "additionalContext"
        ]
        self.assertEqual(kimi_request, self.request_json(codex_context))


if __name__ == "__main__":
    unittest.main()
