"""Regression checks for the observable headless-output contract (no API calls)."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
FILTER = SKILL / "scripts/agy-final-output.py"
RUNNER = SKILL / "scripts/run-worker.sh"
SHELL_DEFINITIONS = Path(os.environ.get("BASH_AGENTS_FILE", Path.home() / ".bash_agents"))
spec = importlib.util.spec_from_file_location("agy_final_output", FILTER)
agy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agy)


def step(index, kind, state="DONE", text=""):
    return {"event": "step_update", "step_update": {
        "step_index": index, "step_type": kind, "state": state, "text_delta": text}}


def result(**changes):
    return {"event": "result", "result": {
        "status": "SUCCESS", "response": "COMMENTARY SECRET_TOOL_RESULT FINAL", **changes}}


def events():
    return [
        {"event": "init"}, step(0, "user_input"),
        step(1, "agent_response", text="COMMENTARY\n"),
        step(2, "tool", text="SECRET_TOOL_RESULT"),
        step(3, "agent_response", "ACTIVE", "Final answer\n"),
        step(3, "agent_response", "DONE", "  exact formatting\n"),
        result(),
    ]


class ParserTests(unittest.TestCase):
    def parse(self, records, format="text"):
        parser = agy.FinalResponses()
        for record in records:
            parser.consume(record)
        return parser.render(format)

    def test_only_terminal_response_preserves_multiline_deltas(self):
        self.assertEqual(self.parse(events()), "Final answer\n  exact formatting\n")

    def test_json_replaces_concatenated_response(self):
        parsed = json.loads(self.parse(events(), "json"))
        self.assertEqual(parsed["response"], "Final answer\n  exact formatting\n")
        self.assertEqual(parsed["status"], "SUCCESS")

    def test_stream_outputs_only_result_events(self):
        rendered = self.parse(events() + events(), "stream-json")
        records = [json.loads(line) for line in rendered.splitlines()]
        self.assertEqual([record["event"] for record in records], ["result", "result"])
        self.assertNotIn("COMMENTARY", rendered)
        self.assertNotIn("SECRET_TOOL_RESULT", rendered)

    def test_out_of_order_updates_do_not_select_earlier_commentary(self):
        records = events()
        records.insert(-1, step(1, "agent_response", text="OLD COMMENTARY"))
        self.assertEqual(self.parse(records), "Final answer\n  exact formatting\n")

    def test_rejects_missing_incomplete_and_nonterminal_responses(self):
        cases = [[], events()[:-1], [result()],
                 [step(1, "agent_response", "ACTIVE", "partial"), result()],
                 [step(1, "agent_response", text="progress"), step(2, "tool"), result()],
                 [step(1, "agent_response", text=""), result()],
                 events() + [step(4, "agent_response", "ACTIVE", "partial")]]
        for records in cases:
            with self.subTest(records=records), self.assertRaises(agy.OutputError):
                self.parse(records)

    def test_non_success_does_not_expose_aggregate_response(self):
        with self.assertRaisesRegex(agy.OutputError, "timeout") as raised:
            self.parse([result(status="ERROR", error="timeout")])
        self.assertNotIn("SECRET_TOOL_RESULT", str(raised.exception))

    def test_unknown_event_fails_closed(self):
        with self.assertRaises(agy.OutputError):
            self.parse([{"event": "future-schema", "text": "secret"}])

    def test_slash_command_result(self):
        records = [{"event": "command_result", "command_result": {"name": "usage"}},
                   result(command={"name": "usage"}, response="usage table\n")]
        self.assertEqual(self.parse(records), "usage table\n")

    def test_multiple_turns_require_stream_or_text(self):
        self.assertEqual(self.parse(events() + events()), "Final answer\n  exact formatting\n" * 2)
        with self.assertRaises(agy.OutputError):
            self.parse(events() + events(), "json")


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agy-output-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / "stream.jsonl"
        self.fixture.write_text("".join(json.dumps(record) + "\n" for record in events()))
        self.args = self.root / "arguments.json"
        self.fake = self.root / "agy"
        self.fake.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ['AGY_TEST_ARGS']).write_text(json.dumps(sys.argv[1:]))
if os.environ.get('AGY_TEST_READ_STDIN'):
    Path(os.environ['AGY_TEST_STDIN']).write_text(sys.stdin.read())
sys.stdout.write(Path(os.environ['AGY_TEST_FIXTURE']).read_text())
sys.stderr.write(os.environ.get('AGY_TEST_STDERR', ''))
sys.exit(int(os.environ.get('AGY_TEST_EXIT', '0')))
''')
        self.fake.chmod(0o755)
        self.env = dict(os.environ, AGY_TEST_ARGS=str(self.args),
                        AGY_TEST_FIXTURE=str(self.fixture))

    def run_filter(self, *arguments, **environment):
        return subprocess.run(["python3", "-B", str(FILTER), str(self.fake), *arguments],
                              env=dict(self.env, **environment), text=True,
                              input="", capture_output=True)

    def test_all_print_aliases_and_equals_forms(self):
        for flag in ("-p", "--print", "--prompt", "-print", "-prompt"):
            for arguments in ([flag, "task"], [flag + "=task"]):
                with self.subTest(arguments=arguments):
                    completed = self.run_filter(*arguments)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stdout, "Final answer\n  exact formatting\n")

    def test_explicit_formats_cannot_enable_intermediate_output(self):
        for flag in (["--output-format", "json"], ["--output-format=stream-json"],
                     ["--output-format=text"], ["-output-format", "json"]):
            with self.subTest(flag=flag):
                completed = self.run_filter("-p", "task", *flag)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertNotIn("COMMENTARY", completed.stdout)
                arguments = json.loads(self.args.read_text())
                self.assertEqual(arguments[:2], ["--output-format", "stream-json"])
                self.assertEqual(arguments.count("--output-format"), 1)

    def test_literal_flag_like_prompt_is_preserved(self):
        self.run_filter("-p", "--output-format=json")
        self.assertEqual(json.loads(self.args.read_text())[-2:], ["-p", "--output-format=json"])

    def test_interactive_arguments_and_output_pass_through(self):
        for arguments in ([], ["-i", "-p"], ["--", "-p"]):
            with self.subTest(arguments=arguments):
                completed = self.run_filter(*arguments)
                self.assertEqual(completed.stdout, self.fixture.read_text())
                self.assertEqual(json.loads(self.args.read_text()), arguments)

    def test_nonzero_status_and_stderr_propagate_without_stdout(self):
        completed = self.run_filter("-p", "task", AGY_TEST_EXIT="23", AGY_TEST_STDERR="auth failed\n")
        self.assertEqual(completed.returncode, 23)
        self.assertEqual(completed.stdout, "")
        self.assertIn("auth failed", completed.stderr)
        self.assertNotIn("SECRET_TOOL_RESULT", completed.stderr)

    def test_malformed_output_fails_without_echoing_it(self):
        self.fixture.write_text("RAW_SECRET_TRANSCRIPT\n")
        completed = self.run_filter("-p", "task")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertNotIn("RAW_SECRET_TRANSCRIPT", completed.stderr)

    def test_stream_input_is_passed_to_child(self):
        target = self.root / "stdin.txt"
        completed = subprocess.run(
            ["python3", "-B", str(FILTER), str(self.fake), "--input-format", "stream-json",
             "--output-format", "stream-json"], input='{"prompt":"task"}\n', text=True,
            capture_output=True, env=dict(self.env, AGY_TEST_READ_STDIN="1", AGY_TEST_STDIN=str(target)))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(target.read_text(), '{"prompt":"task"}\n')
        self.assertEqual(json.loads(completed.stdout)["event"], "result")

    def test_real_shell_wrappers_dispatch_final_output(self):
        # Override only the binary and trust operation; no model or settings writes.
        command = '''source "$AGY_TEST_DEFINITIONS"
_agy_bin() { printf '%s\\n' "$AGY_TEST_BINARY"; }
_agy_trust_workspace() { return 0; }
"$AGY_TEST_LAUNCHER" -p task
'''
        for launcher in ("agg", "aggb"):
            with self.subTest(launcher=launcher):
                completed = subprocess.run(["bash", "-c", command], cwd=self.root,
                    env=dict(self.env, AGY_TEST_DEFINITIONS=str(SHELL_DEFINITIONS),
                             AGY_TEST_BINARY=str(self.fake), AGY_TEST_LAUNCHER=launcher),
                    text=True, input="", capture_output=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout, "Final answer\n  exact formatting\n")

    def test_delegate_failure_does_not_replay_partial_stdout(self):
        definitions = self.root / "wrappers.bash"
        definitions.write_text('agg() { echo PARTIAL_SECRET; echo auth-failed >&2; return 19; }\n')
        completed = subprocess.run(["bash", str(RUNNER), "agg"], input="verify", text=True,
            capture_output=True, env=dict(self.env, BASH_AGENTS_FILE=str(definitions)))
        self.assertEqual(completed.returncode, 19)
        self.assertEqual(completed.stdout, "")
        self.assertIn("auth-failed", completed.stderr)
        self.assertNotIn("PARTIAL_SECRET", completed.stderr)


if __name__ == "__main__":
    unittest.main()
