"""Exercise real shell wrappers against simulated CLI event streams."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPERS = ROOT / "SHELL/.bash_agents"
BASH = shutil.which("bash")
FINAL = "Final answer\n  café\n"
LAUNCHERS = {
    "agy": (
        "agoh", "agom", "argm", "argh", "agg", "aggb",
        "aghh", "aghhb", "aghx", "aghxb",
        "agcm", "agcmb", "agch", "agchb",
        "agnm", "agnmb", "agnh", "agnhb", "agnx", "agnxb",
    ),
    "kimi": ("kimm", "kimh", "kiml", "kimb", "kimbs"),
    "grok": ("grokxh", "grok2", "grok2xh", "grok3", "grok3xh"),
    "opencode": (
        "ocs", "ocmm26", "oclc", "ocmf",
        "ocnl", "ocnu", "ocbp", "ommp", "ocargh", "ochy", "ocq4h", "ocq4x",
        "ochy4flash", "oclongcat", "ociceman",
        "ocnm", "ocnh", "ocs62x", "ocs62mm", "oca62m", "oca62h", "oca62x", "oca62mm",
        "ocopm", "ocoph", "ocopx", "ocopmm", "ochl", "ochm", "ochh", "ochx", "ocnx",
        "occl", "occm", "occh",
    ),
}


def fixture(provider: str) -> str:
    records = {
        "agy": [
            {"event": "init"},
            {"event": "step_update", "step_update": {
                "step_index": 1, "step_type": "agent_response",
                "state": "DONE", "text_delta": "PROGRESS"}},
            {"event": "step_update", "step_update": {
                "step_index": 2, "step_type": "tool", "state": "DONE"}},
            {"event": "step_update", "step_update": {
                "step_index": 3, "step_type": "agent_response",
                "state": "DONE", "text_delta": FINAL}},
            {"event": "result", "result": {
                "status": "SUCCESS", "response": "PROGRESS TOOL_OUTPUT " + FINAL}},
        ],
        "kimi": [
            {"role": "assistant", "content": "PROGRESS", "tool_calls": [{"id": "t1"}]},
            {"role": "tool", "content": "TOOL_OUTPUT"},
            {"role": "assistant", "content": FINAL},
            {"role": "meta", "type": "session.resume_hint", "content": "RESUME_HINT"},
        ],
        "grok": [{"text": FINAL, "stopReason": "end_turn", "sessionId": "s1", "other": "PROGRESS"}],
        "opencode": [
            {"type": "text", "part": {"messageID": "m1", "text": "PROGRESS"}},
            {"type": "tool_use", "part": {"messageID": "m1", "text": "TOOL_OUTPUT"}},
            {"type": "step_finish", "part": {"messageID": "m1", "reason": "tool-calls"}},
            {"type": "text", "part": {"messageID": "m2", "text": "Final answer\n"}},
            {"type": "text", "part": {"messageID": "m2", "text": "  café\n"}},
            {"type": "step_finish", "part": {"messageID": "m2", "reason": "stop"}},
        ],
    }[provider]
    return "".join(json.dumps(record) + "\n" for record in records)


class FinalOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="wrapper-final-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.output = self.home / "output.jsonl"
        self.arguments = self.home / "arguments.json"
        fake = self.bin / "fake-cli"
        fake.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "if sys.argv[1:3] == ['api', 'session.get']:\n"
            "    print(json.dumps({'data': {'id': 'ses_test', 'outcome': os.environ.get('TEST_OC_OUTCOME', 'succeeded'), 'time': {'idle': 20}}}))\n"
            "    sys.exit(0)\n"
            "pathlib.Path(os.environ['TEST_ARGUMENTS']).write_text(json.dumps({\n"
            "    'argv': sys.argv[1:], 'stdin': sys.stdin.read(),\n"
            "    'grok_home': os.environ.get('GROK_HOME'), 'home': os.environ.get('HOME'),\n"
            "    'zdotdir': os.environ.get('ZDOTDIR'), 'agy_user_home': os.environ.get('AGY_USER_HOME'),\n"
            "    'ssh_connection': os.environ.get('SSH_CONNECTION'), 'agy_fake_ssh': os.environ.get('AGY_FAKE_SSH')}))\n"
            "sys.stdout.write(pathlib.Path(os.environ['TEST_OUTPUT']).read_text())\n"
            "sys.stderr.write(os.environ.get('TEST_STDERR', ''))\n"
            "sys.exit(int(os.environ.get('TEST_EXIT', '0')))\n"
        )
        fake.chmod(0o755)
        for name in ("grok", "opencode", "agy"):
            (self.bin / name).symlink_to(fake)
        canonical = self.home / ".kimi-code"
        (canonical / "bin").mkdir(parents=True)
        (canonical / "credentials").mkdir()
        (canonical / "bin/kimi").symlink_to(fake)
        # A live config: canonical plus the keys Kimi writes itself.
        top, tables = (
            ROOT / "SHELL/tests/fixtures/kimi-host-written.toml"
        ).read_text().split("\n[", 1)
        (canonical / "config.toml").write_text(
            top + "\n"
            + (ROOT / "AGENT-ENGINEERING/PERSISTENT-GUIDANCE/config/kimi/config.toml").read_text()
            + "\n[" + tables
        )
        filters = self.home / ".agents/skills/delegate/scripts"
        filters.mkdir(parents=True)
        shutil.copyfile(
            ROOT / "AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/agy-final-output.py",
            filters / "agy-final-output.py",
        )
        self.env = dict(
            os.environ, HOME=str(self.home), PATH=f"{self.bin}:{os.environ['PATH']}",
            KIMI_CANONICAL_HOME=str(canonical), KIMI_STATE_ROOT=str(self.home / "state"),
            GROK2_HOME=str(self.home / ".grok2"), GROK3_HOME=str(self.home / ".grok3"),
            AGY2_HOME=str(self.home / ".agy2"),
            TEST_OUTPUT=str(self.output),
            TEST_ARGUMENTS=str(self.arguments),
        )
        for key in ("SSH_CONNECTION", "AGY_FAKE_SSH"):
            self.env.pop(key, None)

    def run_wrapper(
        self, provider: str, launcher: str, *arguments: str, **environment: str,
    ) -> subprocess.CompletedProcess[str]:
        self.output.write_text(environment.pop("transcript", fixture(provider)))
        return subprocess.run(
            [BASH, "--noprofile", "--norc", "-c",
             'source "$1"; shift; _agy_trust_workspace() { :; }; "$@"',
             "final-output-test", str(WRAPPERS), launcher, *arguments],
            cwd=self.home, env=dict(self.env, **environment), input="input payload\n",
            capture_output=True, text=True, timeout=20, check=False,
        )

    def test_plain_print_returns_only_final_text_for_every_wrapper(self) -> None:
        for provider, launchers in LAUNCHERS.items():
            for launcher in launchers:
                with self.subTest(launcher=launcher):
                    result = self.run_wrapper(provider, launcher, "-p", "task")
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(FINAL, result.stdout)
                    self.assertEqual("input payload\n", json.loads(self.arguments.read_text())["stdin"])

    def test_explicit_structured_formats_remain_native(self) -> None:
        for provider, format_name, value in (
            ("kimi", "--output-format", "stream-json"),
            ("grok", "--output-format", "json"),
            ("opencode", "--format", "json"),
        ):
            for option in ([format_name, value], [f"{format_name}={value}"]):
                with self.subTest(provider=provider, option=option):
                    result = self.run_wrapper(provider, LAUNCHERS[provider][0], *option, "-p", "task")
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(fixture(provider), result.stdout)

    def test_explicit_plain_formats_still_filter(self) -> None:
        for provider, flag, value in (
            ("kimi", "--output-format", "text"),
            ("grok", "--output-format", "plain"),
            ("opencode", "--format", "default"),
        ):
            with self.subTest(provider=provider):
                result = self.run_wrapper(provider, LAUNCHERS[provider][0], "-p", "task", flag, value)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(FINAL, result.stdout)

    def test_flag_like_prompts_are_literal(self) -> None:
        for provider in LAUNCHERS:
            with self.subTest(provider=provider):
                prompt = "--format=json" if provider == "opencode" else "--output-format=json"
                result = self.run_wrapper(provider, LAUNCHERS[provider][0], "-p", prompt)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(FINAL, result.stdout)
                argv = json.loads(self.arguments.read_text())["argv"]
                self.assertIn(prompt, argv)
                if provider == "opencode":
                    self.assertGreater(argv.index(prompt), argv.index("--"))

    def test_interactive_launch_and_flag_like_option_values_are_unchanged(self) -> None:
        for provider in LAUNCHERS:
            for arguments in ([], ["--agent", "-p"], ["--", "-p"]):
                with self.subTest(provider=provider, arguments=arguments):
                    result = self.run_wrapper(provider, LAUNCHERS[provider][0], *arguments)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(fixture(provider), result.stdout)

    def test_process_errors_preserve_status_and_diagnostics_without_partial_stdout(self) -> None:
        for provider in LAUNCHERS:
            with self.subTest(provider=provider):
                result = self.run_wrapper(
                    provider, LAUNCHERS[provider][0], "-p", "task",
                    TEST_EXIT="23", TEST_STDERR="auth failed\n",
                )
                self.assertEqual(23, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertIn("auth failed", result.stderr)

    def test_malformed_empty_or_missing_final_output_is_not_replayed(self) -> None:
        for provider in LAUNCHERS:
            for transcript in ("RAW_TRANSCRIPT", "", "{}\n"):
                with self.subTest(provider=provider, transcript=transcript):
                    result = self.run_wrapper(
                        provider, LAUNCHERS[provider][0], "-p", "task", transcript=transcript,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual("", result.stdout)
                    self.assertNotIn("RAW_TRANSCRIPT", result.stderr)

    def test_incomplete_tool_turns_are_not_final_answers(self) -> None:
        for provider in ("kimi", "opencode"):
            records = fixture(provider).splitlines()
            transcript = "\n".join(records[:2 if provider == "kimi" else 3]) + "\n"
            with self.subTest(provider=provider):
                result = self.run_wrapper(provider, LAUNCHERS[provider][0], "-p", "task", transcript=transcript)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("", result.stdout)

    def test_nonterminal_grok_stop_reason_is_not_a_final_answer(self) -> None:
        transcript = json.dumps({"text": "PARTIAL", "stopReason": "max_tokens"})
        result = self.run_wrapper("grok", "grokxh", "-p", "task", transcript=transcript)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("", result.stdout)

    def test_long_prompt_flags_and_options_before_prompt(self) -> None:
        for provider, flag in (("kimi", "--prompt"), ("grok", "--single"), ("opencode", "--prompt")):
            for arguments in (["--agent", "test-agent", flag, "task"], [f"{flag}=task"]):
                with self.subTest(provider=provider, arguments=arguments):
                    result = self.run_wrapper(provider, LAUNCHERS[provider][0], *arguments)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(FINAL, result.stdout)

    def test_missing_jq_fails_before_starting_cli(self) -> None:
        result = self.run_wrapper("grok", "grokxh", "-p", "task", PATH=str(self.bin))
        self.assertEqual(127, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("jq is required", result.stderr)
        self.assertFalse(self.arguments.exists())

    def test_opencode_explicit_run_filters_default_output(self) -> None:
        result = self.run_wrapper("opencode", "ocargh", "run", "task")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(FINAL, result.stdout)

    def test_opencode_pins_models_and_effort_for_interactive_and_headless_launches(self) -> None:
        for launcher, model, effort in (
            ("ocargh", "opencode-go/gemini-4-argon", "high"),
            ("ocq4h", "opencode-go/qwen4-max", "high"),
            ("ocq4x", "opencode-go/qwen4-max", "xhigh"),
            ("ocs", "opencode-go/muse-spark-1.3-contributor", "xhigh"),
            ("ocmm26", "opencode/mimo-v2.6-flash-free", ""),
            ("ocs62x", "openai/gpt-6.2-sol", "xhigh"),
            ("ocs62mm", "openai/gpt-6.2-sol", "max"),
            ("oca62m", "openai/gpt-6.2-astra", "medium"),
            ("oca62h", "openai/gpt-6.2-astra", "high"),
            ("oca62x", "openai/gpt-6.2-astra", "xhigh"),
            ("oca62mm", "openai/gpt-6.2-astra", "max"),
            ("ocopm", "anthropic/claude-opus-5-5", "medium"),
            ("ocoph", "anthropic/claude-opus-5-5", "high"),
            ("ocopx", "anthropic/claude-opus-5-5", "xhigh"),
            ("ocopmm", "anthropic/claude-opus-5-5", "max"),
            ("ochl", "google/gemini-4-hydrogen", "low"),
            ("ochm", "google/gemini-4-hydrogen", "medium"),
            ("ochh", "google/gemini-4-hydrogen", "high"),
            ("ochx", "google/gemini-4-hydrogen", "xhigh"),
            ("ocnl", "google/gemini-4-neon", "low"),
            ("ocnm", "google/gemini-4-neon", "medium"),
            ("ocnh", "google/gemini-4-neon", "high"),
            ("ocnx", "google/gemini-4-neon", "xhigh"),
            ("occl", "google/gemini-4-carbon", "low"),
            ("occm", "google/gemini-4-carbon", "medium"),
            ("occh", "google/gemini-4-carbon", "high"),
        ):
            for arguments in ([], ["-p", "task"], ["run", "--format", "json", "task"]):
                with self.subTest(launcher=launcher, arguments=arguments):
                    result = self.run_wrapper("opencode", launcher, *arguments)
                    self.assertEqual(0, result.returncode, result.stderr)
                    argv = json.loads(self.arguments.read_text())["argv"]
                    if arguments:
                        run_model = model + (f"#{effort}" if effort else "")
                        self.assertEqual(
                            ["run", "--model", run_model, "--auto", "--format", "json", "--", "task"],
                            argv,
                        )
                        self.assertEqual(fixture("opencode") if arguments[0] == "run" else FINAL, result.stdout)
                    else:
                        self.assertEqual(["--auto"], argv)
                    state = json.loads((self.home / ".local/state/opencode/model.json").read_text())
                    if effort:
                        self.assertEqual(effort, state["variant"][model])
                    else:
                        self.assertNotIn(model, state.get("variant", {}))
                    provider, model_id = model.split("/", 1)
                    self.assertEqual({"providerID": provider, "modelID": model_id}, state["recent"][0])
        result = self.run_wrapper("opencode", "ocargh", "-p", "task", TEST_EXIT="23")
        self.assertEqual(23, result.returncode)
        self.assertEqual("", result.stdout)

    def test_opencode_missing_finish_requires_native_completion_and_complete_text(
        self,
    ) -> None:
        records = [
            {"type": "step_start", "sessionID": "ses_test", "part": {"messageID": "m"}},
            {
                "type": "text",
                "sessionID": "ses_test",
                "part": {
                    "messageID": "m",
                    "text": FINAL,
                    "time": {"start": 1, "end": 10},
                },
            },
        ]
        transcript = "".join(json.dumps(row) + "\n" for row in records)
        result = self.run_wrapper(
            "opencode", "ocargh", "-p", "task", transcript=transcript
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(FINAL, result.stdout)
        for outcome in ("failed", "cancelled", "running"):
            with self.subTest(outcome=outcome):
                result = self.run_wrapper(
                    "opencode",
                    "ocargh",
                    "-p",
                    "task",
                    transcript=transcript,
                    TEST_OC_OUTCOME=outcome,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("", result.stdout)
        del records[-1]["part"]["time"]["end"]
        result = self.run_wrapper(
            "opencode",
            "ocargh",
            "-p",
            "task",
            transcript="".join(json.dumps(row) + "\n" for row in records),
        )
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("", result.stdout)

    def test_grok_account_homes_are_preserved(self) -> None:
        for launcher, home in (("grok2", ".grok2"), ("grok2xh", ".grok2"),
                               ("grok3", ".grok3"), ("grok3xh", ".grok3")):
            with self.subTest(launcher=launcher):
                result = self.run_wrapper("grok", launcher, "--single=task")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(FINAL, result.stdout)
                self.assertEqual(str(self.home / home), json.loads(self.arguments.read_text())["grok_home"])

    def sign_in_agy2(self) -> Path:
        agy2 = self.home / ".agy2"
        token = agy2 / ".gemini/antigravity-cli/antigravity-oauth-token"
        token.parent.mkdir(parents=True)
        token.write_text("token")
        return agy2

    def test_agy_second_account_runs_under_its_own_home(self) -> None:
        agy2 = self.sign_in_agy2()
        (self.home / ".gemini/config").mkdir(parents=True)
        for launcher in ("agg2", "aggbs2", "aggtp2", "aggb2", "aggbbs2", "aggbtp2",
                         "agom2", "agoh2", "argm2", "argh2",
                         "aghh2", "aghhb2", "aghx2", "aghxb2",
                         "agcm2", "agcmb2", "agch2", "agchb2",
                         "agnm2", "agnmb2", "agnh2", "agnhb2", "agnx2", "agnxb2"):
            with self.subTest(launcher=launcher):
                result = self.run_wrapper("agy", launcher, "-p", "task")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(FINAL, result.stdout)
                seen = json.loads(self.arguments.read_text())
                # A stand-in SSH session keeps AGY's token saves away from the missing keychain.
                self.assertEqual(
                    (str(agy2), str(agy2 / ".zdotdir"), str(self.home), True, "1"),
                    (seen["home"], seen["zdotdir"], seen["agy_user_home"], bool(seen["ssh_connection"]),
                     seen["agy_fake_ssh"]),
                )
        self.assertEqual(str(self.home / ".gemini/config"), os.readlink(agy2 / ".gemini/config"))

    def test_agy_primary_account_keeps_the_real_home(self) -> None:
        self.sign_in_agy2()
        result = self.run_wrapper("agy", "aggb", "-p", "task")
        self.assertEqual(0, result.returncode, result.stderr)
        seen = json.loads(self.arguments.read_text())
        self.assertEqual((str(self.home), None, None, None),
                         (seen["home"], seen["zdotdir"], seen["agy_user_home"], seen["ssh_connection"]))

    def test_agy_second_account_commands_get_the_real_home(self) -> None:
        zsh = shutil.which("zsh")
        if zsh is None:
            self.skipTest("zsh is not installed")
        agy2 = self.sign_in_agy2()
        (self.home / ".gemini/config").mkdir(parents=True)
        (self.home / ".zshenv").write_text("export USER_ZSHENV=loaded\n")
        real_ssh = "10.0.0.5 50000 10.0.0.9 22"
        # Commands lose the stand-in SSH session but keep a real one.
        for session, expected_ssh in (({}, "unset"), ({"SSH_CONNECTION": real_ssh}, real_ssh)):
            with self.subTest(ssh=expected_ssh):
                self.assertEqual(0, self.run_wrapper("agy", "agg2", "-p", "task", **session).returncode)
                seen = json.loads(self.arguments.read_text())
                agy_env = {"HOME": seen["home"], "ZDOTDIR": seen["zdotdir"], "AGY_USER_HOME": seen["agy_user_home"],
                           "SSH_CONNECTION": seen["ssh_connection"], "AGY_FAKE_SSH": seen["agy_fake_ssh"]}
                # AGY runs each command as `zsh -c` with the environment it was given.
                command = subprocess.run(
                    [zsh, "-c", 'print -r -- "$HOME|${ZDOTDIR-unset}|${AGY_USER_HOME-unset}|$USER_ZSHENV|'
                                '${SSH_CONNECTION-unset}|${AGY_FAKE_SSH-unset}"'],
                    env=dict(self.env, **{k: v for k, v in agy_env.items() if v is not None}),
                    capture_output=True, text=True, timeout=20, check=True,
                )
                self.assertEqual(f"{self.home}|unset|unset|loaded|{expected_ssh}|unset\n", command.stdout)

    def test_agy_second_account_signed_out_refuses_headless_runs(self) -> None:
        (self.home / ".gemini/config").mkdir(parents=True)
        result = self.run_wrapper("agy", "aggb2", "-p", "task")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Antigravity account 2 is not signed in", result.stderr)
        self.assertFalse(self.arguments.exists())
        # An interactive launch is how the account logs in, so it still starts.
        result = self.run_wrapper("agy", "agg2")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(str(self.home / ".agy2"), json.loads(self.arguments.read_text())["home"])


if __name__ == "__main__":
    unittest.main()
