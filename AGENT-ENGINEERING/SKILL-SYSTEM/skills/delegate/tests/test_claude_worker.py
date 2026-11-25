"""run-worker.sh Claude adapter: final-result extraction; no model calls."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "scripts/run-worker.sh"
CLAUDE_LAUNCHERS = (
    "csx", "chx", "ccx", "ccbx", "ccfh", "ccbfh",
    "ccm", "ccbm", "ccmm", "ccfx", "ccbfx", "ccmM", "ccxX",
    "cck", "cckm", "ccku", "cckx", "cckh", "cckmm",
    "cckbm", "cckbu", "cckbx", "cckbh", "cckbmm",
    "cckfm", "cckfu", "cckfx", "cckfh", "cckfmm",
    "cckbfm", "cckbfu", "cckbfx", "cckbfh", "cckbfmm",
)


class ClaudeWorkerTests(unittest.TestCase):
    def run_worker(self, output: str, status: int = 0,
                   launcher: str = "csx") -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            wrappers = Path(tmp) / "wrappers"
            # The fake answers only when invoked in Claude's JSON print mode.
            wrappers.write_text(
                f"{launcher}() {{ [[ \"$*\" == '--output-format json -p TASK' ]] || return 9; "
                f"printf '%s\\n' '{output}'; return {status}; }}\n")
            # Outside any agent session, so the runner adds no hist-parent line.
            env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
            return subprocess.run(
                ["bash", str(RUNNER), launcher], input=b"TASK", capture_output=True,
                timeout=20, env=dict(env, BASH_AGENTS_FILE=str(wrappers)))

    def test_single_result_object(self) -> None:
        for launcher in CLAUDE_LAUNCHERS:
            with self.subTest(launcher=launcher):
                result = self.run_worker(
                    '{"type":"result","is_error":false,"result":"FINAL"}', launcher=launcher)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(b"FINAL\n", result.stdout)

    def test_event_array_returns_only_the_result(self) -> None:
        for launcher in CLAUDE_LAUNCHERS:
            with self.subTest(launcher=launcher):
                result = self.run_worker(
                    '[{"type":"assistant","text":"PRIVATE"},{"type":"result","is_error":false,"result":"FINAL"}]',
                    launcher=launcher)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(b"FINAL\n", result.stdout)

    def test_error_result_fails_without_stdout(self) -> None:
        for launcher in CLAUDE_LAUNCHERS:
            with self.subTest(launcher=launcher):
                result = self.run_worker(
                    '{"type":"result","is_error":true,"result":"PARTIAL"}', launcher=launcher)
                self.assertEqual(1, result.returncode)
                self.assertEqual(b"", result.stdout)
                self.assertIn(b"no successful final result", result.stderr)

    def test_help_lists_claude_launchers_and_exits_zero(self) -> None:
        result = subprocess.run(["bash", str(RUNNER), "--help"], capture_output=True, timeout=20)
        self.assertEqual(0, result.returncode, result.stderr)
        for launcher in CLAUDE_LAUNCHERS:
            self.assertIn(launcher.encode(), result.stdout)


if __name__ == "__main__":
    unittest.main()
