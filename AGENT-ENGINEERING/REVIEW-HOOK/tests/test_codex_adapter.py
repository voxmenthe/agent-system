from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "hosts/codex/adapter.py"
FIXTURES = ROOT / "tests/fixtures"


class CodexAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo with space"
        self.state_dir = self.root / "state"
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
            "PreToolUse": "codex-pre-tool-use.json",
            "PostToolUse": "codex-post-tool-use.json",
        }[event]
        payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        payload["cwd"] = str(self.repo)
        return payload

    def invoke(
        self,
        *,
        event: str,
        command: str = "git commit --allow-empty -m fixture",
        tool_use_id: str = "fixture-tool",
        standard_every: int | None = None,
        branch_every: int | None = None,
        mode: str = "cadence",
        payload: dict | None = None,
    ) -> subprocess.CompletedProcess[str]:
        hook_payload = payload or self._fixture(event)
        hook_payload["hook_event_name"] = event
        hook_payload["tool_use_id"] = tool_use_id
        hook_payload["tool_input"] = {"command": command}
        env = os.environ.copy()
        env["CODEX_HOOK_STATE_DIR"] = str(self.state_dir)
        env["REVIEW_AFTER_COMMIT_MODE"] = mode
        env["REVIEW_AFTER_COMMIT_OUTCOME_STATE"] = str(self.outcome_state)
        for name, value in (
            ("CODEX_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY", standard_every),
            ("CODEX_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY", branch_every),
        ):
            if value is None:
                env.pop(name, None)
            else:
                env[name] = str(value)
        return subprocess.run(
            ["/usr/bin/python3", str(ADAPTER)],
            input=json.dumps(hook_payload),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def record_before(self, command: str, *, tool_use_id: str = "fixture-tool", **kwargs) -> None:
        result = self.invoke(
            event="PreToolUse",
            command=command,
            tool_use_id=tool_use_id,
            **kwargs,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    @staticmethod
    def request_json(context: str) -> dict:
        opening = context.index("<review-request-json")
        json_start = context.index("\n", opening) + 1
        json_end = context.index("\n</review-request-json>", json_start)
        return json.loads(context[json_start:json_end])

    def test_commit_delivers_exact_read_only_request_as_additional_context(self) -> None:
        command = "git commit --allow-empty -m one"
        before = self._git("rev-parse", "HEAD")
        self.record_before(command)
        self._git("commit", "--allow-empty", "-qm", "one")
        after = self._git("rev-parse", "HEAD")

        result = self.invoke(event="PostToolUse", command=command)

        self.assertEqual(0, result.returncode, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            "PostToolUse", output["hookSpecificOutput"]["hookEventName"]
        )
        self.assertNotIn("permissionDecision", output["hookSpecificOutput"])
        context = output["hookSpecificOutput"]["additionalContext"]
        request = self.request_json(context)
        self.assertEqual(before, request["range"]["before"])
        self.assertEqual(after, request["range"]["after"])
        self.assertEqual("read-only-advisory-review", request["authority"])
        self.assertEqual("recent", request["kind"])
        self.assertNotIn(str(self.repo), context)
        self.assertIn("Do not edit, stage, commit, publish", context)
        self.assertIn("create a review file, or otherwise mutate", context)

    def test_duplicate_post_is_idempotent(self) -> None:
        command = "git commit --allow-empty -m one"
        self.record_before(command)
        self._git("commit", "--allow-empty", "-qm", "one")

        first = self.invoke(event="PostToolUse", command=command)
        second = self.invoke(event="PostToolUse", command=command)

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertTrue(first.stdout)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual("", second.stdout)

    def test_auto_delivers_selected_evidence_and_records_delivery(self) -> None:
        self.repo.joinpath("module.py").write_text(
            "def choose(value=None):\n    return value\n", encoding="utf-8"
        )
        self._git("add", "module.py")
        self._git("commit", "-qm", "base")
        command = "git commit -am change"
        self.record_before(command, mode="auto")
        self.repo.joinpath("module.py").write_text(
            "def choose(value=[]):\n    return value\n", encoding="utf-8"
        )
        self._git("commit", "-am", "change", "-q")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _: self.invoke(event="PostToolUse", command=command, mode="auto"),
                range(2),
            ))
        for result in results:
            self.assertEqual(0, result.returncode, result.stderr)
        emitted = [result for result in results if result.stdout]
        self.assertEqual(1, len(emitted), "Concurrent callbacks must emit once")
        result = emitted[0]

        self.assertEqual(0, result.returncode, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        request = self.request_json(context)
        self.assertEqual("auto", request["mode"])
        self.assertIsNotNone(request["evidence"])
        self.assertIn("record-review-outcome", context)
        self.assertIn("FINDING_COUNT", context)
        histories = list(self.outcome_state.glob("repositories/*/outcomes.jsonl"))
        self.assertEqual(1, len(histories))
        event = json.loads(histories[0].read_text(encoding="utf-8"))
        self.assertTrue(event["selected"])
        self.assertEqual("codex", event["deliveries"][0]["host"])
        self.assertIsNone(event["deliveries"][0]["review"])
        history = histories[0].read_bytes()
        replay = self.invoke(event="PostToolUse", command=command, mode="auto")
        self.assertEqual(0, replay.returncode, replay.stderr)
        self.assertEqual("", replay.stdout)
        self.assertEqual(history, histories[0].read_bytes())

    def test_failed_or_dry_run_commit_is_silent(self) -> None:
        for index, command in enumerate(
            ("git commit -m impossible || true", "git commit --dry-run"), start=1
        ):
            with self.subTest(command=command):
                tool_id = "tool-{}".format(index)
                self.record_before(command, tool_use_id=tool_id)
                result = self.invoke(
                    event="PostToolUse", command=command, tool_use_id=tool_id
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)

    def test_adapter_preserves_standard_and_branch_precedence(self) -> None:
        results = []
        for index in range(1, 7):
            command = "git commit --allow-empty -m {}".format(index)
            tool_id = "tool-{}".format(index)
            self.record_before(
                command,
                tool_use_id=tool_id,
                standard_every=2,
                branch_every=6,
            )
            self._git("commit", "--allow-empty", "-qm", str(index))
            results.append(
                self.invoke(
                    event="PostToolUse",
                    command=command,
                    tool_use_id=tool_id,
                    standard_every=2,
                    branch_every=6,
                )
            )

        self.assertEqual([False, True, False, True, False, True], [bool(r.stdout) for r in results])
        self.assertEqual("recent", self.request_json(json.loads(results[1].stdout)["hookSpecificOutput"]["additionalContext"])["kind"])
        self.assertEqual("branch", self.request_json(json.loads(results[5].stdout)["hookSpecificOutput"]["additionalContext"])["kind"])

    def test_irrelevant_event_is_dormant_without_configuration(self) -> None:
        payload = self._fixture("PreToolUse")
        payload["tool_name"] = "Read"
        env = os.environ.copy()
        env.pop("CODEX_HOOK_STATE_DIR", None)
        result = subprocess.run(
            ["/usr/bin/python3", str(ADAPTER)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        self.assertFalse(self.state_dir.exists())

    def test_missing_pre_snapshot_and_invalid_payload_fail_loudly(self) -> None:
        missing = self.invoke(event="PostToolUse")
        self.assertNotEqual(0, missing.returncode)
        self.assertIn("missing PreToolUse snapshot", missing.stderr)

        env = os.environ.copy()
        result = subprocess.run(
            ["/usr/bin/python3", str(ADAPTER)],
            input="not json",
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("review-after-commit Codex hook", result.stderr)


if __name__ == "__main__":
    unittest.main()
