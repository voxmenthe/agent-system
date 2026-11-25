"""Command Code's terminal JSON result is the only successful output boundary."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


RUNNER = Path(__file__).resolve().parents[1] / "scripts/run-worker.sh"
# 10-31: cms twice ended its run on a narration message and returned no answer; every Command Code task carries this.
DELIVERY = ("\n\nDelivery: never send a progress note as a message; "
            "your final message holds the complete answer.")


class CommandWorkerTests(unittest.TestCase):
    def run_worker(self, output: str, status: int = 0,
                   launcher: str = "cmg") -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = root / "stream.jsonl"
            transcript.write_text(output)
            wrappers = root / "wrappers"
            wrappers.write_text(
                f'{launcher}() {{ [[ "$*" == "--no-auto-update --output-format json -p TASK{DELIVERY}" ]] || return 9; '
                f'cat "$COMMAND_TEST_OUTPUT"; return {status}; }}\n')
            # Outside any agent session, so the runner adds no hist-parent line.
            env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
            return subprocess.run(
                ["/bin/bash", str(RUNNER), launcher], input="TASK", text=True,
                capture_output=True, env=dict(
                    env, BASH_AGENTS_FILE=str(wrappers),
                    COMMAND_TEST_OUTPUT=str(transcript)))

    def test_only_terminal_success_text_is_returned(self) -> None:
        output = '\n'.join(json.dumps(row) for row in (
            {"type": "event", "event": {"type": "text_delta", "text": "PRIVATE"}},
            {"type": "event", "event": {"type": "tool_completed", "result": "PRIVATE"}},
            {"type": "result", "subtype": "success", "finalText": "FINAL\n  exact formatting"},
        ))
        for launcher in ("cmg", "cmds", "cmm26p", "cms", "cmdglyph", "cmdflint"):
            with self.subTest(launcher=launcher):
                result = self.run_worker(output, launcher=launcher)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("FINAL\n  exact formatting\n", result.stdout)

    def test_missing_malformed_nonterminal_and_failed_results_are_rejected(self) -> None:
        success = '{"type":"result","subtype":"success","finalText":"FINAL"}'
        cases = (
            "", "not json", '{"type":"event","event":{"text":"PARTIAL"}}',
            '{"type":"result","subtype":"error","finalText":"PARTIAL"}',
            '{"type":"result","subtype":"max_turns","finalText":"PARTIAL"}',
            '{"type":"result","subtype":"success","finalText":""}',
            '{"type":"result","subtype":"success","finalText":null}',
            success + '\n{"type":"event","event":{"text":"LATER"}}',
            success + '\n{"type":"result","subtype":"error","finalText":""}',
        )
        for output in cases:
            with self.subTest(output=output):
                result = self.run_worker(output)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertIn("no successful final result", result.stderr)

    def test_nonzero_exit_never_publishes_partial_stdout(self) -> None:
        for status in (7, 8):
            with self.subTest(status=status):
                result = self.run_worker(
                    '{"type":"result","subtype":"success","finalText":"PARTIAL"}', status)
                self.assertEqual(status, result.returncode)
                self.assertEqual("", result.stdout)


if __name__ == "__main__":
    unittest.main()
