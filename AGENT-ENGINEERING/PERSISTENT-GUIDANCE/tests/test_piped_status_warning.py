"""The piped-status hook warns on recorded misreads, stays silent otherwise, and never blocks."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "piped_status_warning.py"
# Recorded after the October 27 sync (hist tool calls), trimmed to the pipeline.
MISREADS = (
    'npm run lint --loglevel=error 2>&1 | tail -3; echo "exit $?"',
    './guidance validate 2>&1 | tail -3; echo "validate=$?"',
    'npx --loglevel=error tsc --noEmit -p . 2>&1 | grep -v "^npm" | head -5; echo tsc-exit=$?',
    "python3 - <<'EOF'\nopen('a', 'w').write('x')\nEOF\nnpx tsc --noEmit -p tsconfig.app.json 2>&1 | head -5; echo tsc=$?",
)


class PipedStatusWarningTests(unittest.TestCase):
    def hook(self, event: object) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(HOOK)], input=json.dumps(event), text=True,
                              capture_output=True, timeout=10)

    def bash(self, command: str) -> subprocess.CompletedProcess:
        return self.hook({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/tmp"})

    def test_a_recorded_misread_gets_a_warning_and_still_runs(self) -> None:
        for command in MISREADS:
            with self.subTest(command=command):
                result = self.bash(command)
                self.assertEqual(0, result.returncode, result.stderr)
                output = json.loads(result.stdout)["hookSpecificOutput"]
                self.assertEqual({"hookEventName", "additionalContext"}, set(output))
                self.assertIn("${PIPESTATUS[0]}", output["additionalContext"])

    def test_the_warning_names_the_check_and_the_filter(self) -> None:
        context = json.loads(self.bash(MISREADS[1]).stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(context.startswith(
            "This command reads `$?` after piping `./guidance validate` through `tail`: that is tail's status"))

    def test_the_checks_own_status_a_plain_pipe_and_quoted_text_are_silent(self) -> None:
        for command in (
            'npm run lint 2>&1 | tail -3; echo "exit ${PIPESTATUS[0]}"',
            "set -o pipefail; npx tsc --noEmit | head -5; echo tsc=$?",
            "npx tsc --noEmit > /tmp/tsc.out 2>&1; echo tsc=$?; head -5 /tmp/tsc.out",
            "ls | head -3; echo $?",
            "cat >> notes.md <<'EOF'\nTwo misreads: `npm run lint | tail -3; echo \"exit $?\"`.\nEOF",
            # 11-01: a prompt handed to an agent CLI quoted one, and the hook warned on it.
            "claude -p 'Run exactly this Bash command once: true --validate | tail -1; echo validate=$?' --model haiku",
        ):
            with self.subTest(command=command):
                result = self.bash(command)
                self.assertEqual((0, ""), (result.returncode, result.stdout), result.stderr)

    def test_other_tools_and_odd_input_never_block(self) -> None:
        self.assertEqual((0, ""), (self.hook({"tool_name": "Edit", "tool_input": {"command": MISREADS[0]}}).returncode,
                                   ""))
        self.assertEqual(0, self.hook({"tool_name": "Bash", "tool_input": {}}).returncode)
        broken = subprocess.run([sys.executable, "-B", str(HOOK)], input="not json", text=True, capture_output=True)
        self.assertEqual(1, broken.returncode)
        self.assertIn("piped-status-warning:", broken.stderr)


if __name__ == "__main__":
    unittest.main()
