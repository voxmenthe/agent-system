"""run-worker.sh names the launching session for hist in the task; no model calls."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "scripts/run-worker.sh"
CLAUDE = "5e000000-0000-4000-8000-0000000000c1"
CODEX = "019a0000-0000-7000-8000-0000000000c2"


class HistParentTests(unittest.TestCase):
    def task_received(self, **session: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            received = Path(tmp) / "received"
            wrappers = Path(tmp) / "wrappers"
            # Stands in for a headless worker: records the task it was given.
            wrappers.write_text('agg() { printf "%s" "$2" >"$RECEIVED_TASK"; echo FINAL; }\n')
            env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
            env.update(session, BASH_AGENTS_FILE=str(wrappers), RECEIVED_TASK=str(received))
            result = subprocess.run(["bash", str(RUNNER), "agg"], input="TASK", text=True,
                                    capture_output=True, timeout=20, env=env)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("FINAL\n", result.stdout)
            return received.read_text()

    def test_a_single_session_variable_names_the_parent(self) -> None:
        self.assertEqual(f"TASK\n\n[hist-parent claude:{CLAUDE}]",
                         self.task_received(CLAUDE_CODE_SESSION_ID=CLAUDE))
        self.assertEqual(f"TASK\n\n[hist-parent codex:{CODEX}]", self.task_received(CODEX_THREAD_ID=CODEX))

    def test_both_or_neither_name_no_parent(self) -> None:
        self.assertEqual("TASK", self.task_received(CLAUDE_CODE_SESSION_ID=CLAUDE, CODEX_THREAD_ID=CODEX))
        self.assertEqual("TASK", self.task_received())


if __name__ == "__main__":
    unittest.main()
