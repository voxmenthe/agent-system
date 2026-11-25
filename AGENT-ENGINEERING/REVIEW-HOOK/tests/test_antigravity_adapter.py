from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "hosts/antigravity/plugin/adapter.py"
HOOKS = ROOT / "hosts/antigravity/plugin/hooks.json"
FIXTURES = ROOT / "tests/fixtures"


class AntigravityAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo with space"
        self.other_repo = self.root / "other repo"
        self.state_dir = self.root / "antigravity-state"
        self.outcome_state = self.root / "outcomes"
        self._init_repo(self.repo)
        self._init_repo(self.other_repo)

    def _init_repo(self, path: Path) -> None:
        self._git("init", "-q", str(path), cwd=self.root)
        self._git("config", "user.email", "hook-test@example.invalid", cwd=path)
        self._git("config", "user.name", "Hook Test", cwd=path)
        self._git("commit", "--allow-empty", "-qm", "initial", cwd=path)

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

    def _pre_payload(
        self,
        invocation: int,
        *,
        conversation: str = "ec33ebf9-0cba-4100-8142-c61503f6c587",
        workspaces: list[Path] | None = None,
    ) -> dict:
        payload = json.loads(
            (FIXTURES / "antigravity-pre-invocation.json").read_text(
                encoding="utf-8"
            )
        )
        payload["invocationNum"] = invocation
        payload["conversationId"] = conversation
        payload["workspacePaths"] = [
            str(path) for path in (workspaces if workspaces is not None else [self.repo])
        ]
        return payload

    def _post_payload(
        self,
        command: str,
        *,
        cwd: Path | None = None,
        step: int = 1,
        conversation: str = "ec33ebf9-0cba-4100-8142-c61503f6c587",
        error: str = "",
    ) -> dict:
        payload = json.loads(
            (FIXTURES / "antigravity-post-tool-use.json").read_text(
                encoding="utf-8"
            )
        )
        payload["conversationId"] = conversation
        payload["stepIdx"] = step
        payload["error"] = error
        payload["workspacePaths"] = [str(self.repo)]
        payload["toolCall"]["args"]["CommandLine"] = command
        payload["toolCall"]["args"]["Cwd"] = str(cwd or self.repo)
        return payload

    def invoke(
        self,
        event: str,
        payload: dict | str,
        *,
        mode: str | None = "cadence",
        standard_every: int | None = None,
        branch_every: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["ANTIGRAVITY_HOOK_STATE_DIR"] = str(self.state_dir)
        env["REVIEW_AFTER_COMMIT_OUTCOME_STATE"] = str(self.outcome_state)
        if mode is None:
            env.pop("REVIEW_AFTER_COMMIT_MODE", None)
        else:
            env["REVIEW_AFTER_COMMIT_MODE"] = mode
        for name, value in (
            ("ANTIGRAVITY_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY", standard_every),
            ("ANTIGRAVITY_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY", branch_every),
        ):
            if value is None:
                env.pop(name, None)
            else:
                env[name] = str(value)
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            ["/usr/bin/python3", "-B", str(ADAPTER), event],
            input=stdin,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    @staticmethod
    def request_json(context: str) -> dict:
        opening = context.index("<review-request-json")
        json_start = context.index("\n", opening) + 1
        json_end = context.index("\n</review-request-json>", json_start)
        return json.loads(context[json_start:json_end])

    def test_commit_is_deferred_once_to_next_invocation(self) -> None:
        first = self.invoke("pre-invocation", self._pre_payload(0))
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual({}, json.loads(first.stdout))

        command = "git commit --allow-empty -m one"
        before = self._git("rev-parse", "HEAD")
        self._git("commit", "--allow-empty", "-qm", "one")
        after = self._git("rev-parse", "HEAD")
        post = self.invoke("post-tool-use", self._post_payload(command))
        self.assertEqual(0, post.returncode, post.stderr)
        self.assertEqual({}, json.loads(post.stdout))

        delivered = self.invoke("pre-invocation", self._pre_payload(1))
        self.assertEqual(0, delivered.returncode, delivered.stderr)
        output = json.loads(delivered.stdout)
        self.assertEqual(1, len(output["injectSteps"]))
        context = output["injectSteps"][0]["ephemeralMessage"]
        request = self.request_json(context)
        self.assertEqual(before, request["range"]["before"])
        self.assertEqual(after, request["range"]["after"])
        self.assertEqual("read-only-advisory-review", request["authority"])
        self.assertEqual("diff-review", request["expected_skill"]["name"])
        self.assertNotIn(str(self.repo), context)

        replay = self.invoke("pre-invocation", self._pre_payload(1))
        self.assertEqual(0, replay.returncode, replay.stderr)
        self.assertEqual(delivered.stdout, replay.stdout)
        acknowledged = self.invoke("pre-invocation", self._pre_payload(2))
        self.assertEqual(0, acknowledged.returncode, acknowledged.stderr)
        self.assertEqual({}, json.loads(acknowledged.stdout))

    def test_post_tool_replay_does_not_duplicate_or_lose_next_commit(self) -> None:
        self.assertEqual(
            0,
            self.invoke("pre-invocation", self._pre_payload(0)).returncode,
        )
        first_command = "git commit --allow-empty -m one"
        self._git("commit", "--allow-empty", "-qm", "one")
        payload = self._post_payload(first_command, step=1)
        first = self.invoke("post-tool-use", payload)
        replay = self.invoke("post-tool-use", payload)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, replay.returncode, replay.stderr)

        second_command = "git commit --allow-empty -m two"
        self._git("commit", "--allow-empty", "-qm", "two")
        second = self.invoke(
            "post-tool-use", self._post_payload(second_command, step=2)
        )
        self.assertEqual(0, second.returncode, second.stderr)
        delivered = self.invoke("pre-invocation", self._pre_payload(1))
        self.assertEqual(0, delivered.returncode, delivered.stderr)
        context = json.loads(delivered.stdout)["injectSteps"][0][
            "ephemeralMessage"
        ]
        self.assertEqual(2, context.count("<review-request-json"))

    def test_auto_selection_is_deferred_then_records_antigravity_delivery(self) -> None:
        module = self.repo / "module.py"
        module.write_text(
            "def choose(value=None):\n    return value\n", encoding="utf-8"
        )
        self._git("add", "module.py")
        self._git("commit", "-qm", "base")
        prepared = self.invoke("pre-invocation", self._pre_payload(0), mode="auto")
        self.assertEqual(0, prepared.returncode, prepared.stderr)

        module.write_text(
            "def choose(value=[]):\n    return value\n", encoding="utf-8"
        )
        command = "git commit -am change"
        self._git("commit", "-am", "change", "-q")
        post = self.invoke(
            "post-tool-use", self._post_payload(command), mode="auto"
        )
        self.assertEqual(0, post.returncode, post.stderr)

        delivered = self.invoke("pre-invocation", self._pre_payload(1), mode="auto")
        self.assertEqual(0, delivered.returncode, delivered.stderr)
        context = json.loads(delivered.stdout)["injectSteps"][0]["ephemeralMessage"]
        request = self.request_json(context)
        self.assertEqual("auto", request["mode"])
        self.assertIn("record-review-outcome", context)
        history = next(self.outcome_state.glob("repositories/*/outcomes.jsonl"))
        event = json.loads(history.read_text(encoding="utf-8"))
        self.assertEqual("antigravity", event["deliveries"][0]["host"])

    def test_failed_command_keeps_snapshot_for_later_success(self) -> None:
        self.assertEqual(
            0,
            self.invoke("pre-invocation", self._pre_payload(0)).returncode,
        )
        failed = self.invoke(
            "post-tool-use",
            self._post_payload("git commit -m impossible", error="exit status 1"),
        )
        self.assertEqual(0, failed.returncode, failed.stderr)
        self.assertEqual({}, json.loads(failed.stdout))

        command = "git commit --allow-empty -m one"
        self._git("commit", "--allow-empty", "-qm", "one")
        success = self.invoke(
            "post-tool-use", self._post_payload(command, step=2)
        )
        self.assertEqual(0, success.returncode, success.stderr)
        delivered = self.invoke("pre-invocation", self._pre_payload(1))
        self.assertIn("injectSteps", json.loads(delivered.stdout))

    def test_outside_snapshot_and_wrong_conversation_fail_loudly(self) -> None:
        self.assertEqual(
            0,
            self.invoke("pre-invocation", self._pre_payload(0)).returncode,
        )
        command = "git commit --allow-empty -m outside"
        self._git("commit", "--allow-empty", "-qm", "outside", cwd=self.other_repo)
        outside = self.invoke(
            "post-tool-use", self._post_payload(command, cwd=self.other_repo)
        )
        self.assertNotEqual(0, outside.returncode)
        self.assertIn("pre-invocation snapshot", outside.stderr)

        wrong = self.invoke(
            "post-tool-use",
            self._post_payload(
                command,
                conversation="4a7df45c-98fd-445e-a07e-5143fd2b5e85",
            ),
        )
        self.assertNotEqual(0, wrong.returncode)
        self.assertIn("pre-invocation snapshot", wrong.stderr)

    def test_unselected_handler_is_dormant_without_parsing_or_state(self) -> None:
        for event in ("pre-invocation", "post-tool-use"):
            with self.subTest(event=event):
                result = self.invoke(event, "not json", mode=None)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual({}, json.loads(result.stdout))
        self.assertFalse(self.state_dir.exists())

    def test_plugin_never_registers_a_permission_or_continuation_hook(self) -> None:
        hooks = json.loads(HOOKS.read_text(encoding="utf-8"))
        definition = hooks["review-after-commit"]
        self.assertEqual({"PreInvocation", "PostToolUse"}, set(definition))
        serialized = json.dumps(hooks, sort_keys=True)
        self.assertNotIn("PreToolUse", serialized)
        self.assertNotIn("Stop", serialized)
        self.assertNotIn("PostInvocation", serialized)


if __name__ == "__main__":
    unittest.main()
