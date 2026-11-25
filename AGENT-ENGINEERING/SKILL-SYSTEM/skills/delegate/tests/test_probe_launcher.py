"""probe-launcher's report on stubbed launchers and a stubbed hist; no model calls."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

PROBE = Path(__file__).resolve().parents[1] / "scripts/probe-launcher"
PARENT = "5e000000-0000-4000-8000-0000000000c1"
# Stand-ins for ~/.bash_agents. cms reads the probe's file as a real worker would with a tool; cmg guesses; cmds
# ends its run on a progress note, as cms did twice on 10-31; ocargh names a model OpenCode Go has retired; cax (final
# text) answers in JSON naming a model of its own; kimm runs on Kimi, which hist does not record; cmm26p hangs.
WRAPPERS = r"""
probe_file() { grep -o '/[^ ]*\.txt' <<<"${!#}" | head -1; }
cms() {
  printf '%s\n' '{"type":"event","event":{"type":"session_info","model":"meta/muse-spark-1.3-contributor"}}'
  printf '{"type":"result","subtype":"success","finalText":"PROBE-OK %s"}\n' "$(cat "$(probe_file "$@")")"
}
cmg() { printf '%s\n' '{"type":"result","subtype":"success","finalText":"PROBE-OK 0123456789abcdef01234567"}'; }
cmds() { printf '%s\n' '{"type":"result","subtype":"success","finalText":"Now I will read the file."}'; }
ocargh() {
  printf '%s\n' '{"type":"error","timestamp":1793434987246,"sessionID":"ses_e6ef","error":{"type":"provider.no-route","message":"Model unavailable: opencode-go/gemini-4-argon-contributor"}}'
  return 1
}
cax() { printf '{"model":"model-claimed-by-the-assistant","answer":"PROBE-OK %s"}\n' "$(cat "$(probe_file "$@")")"; }
kimm() { printf '{"role":"assistant","content":"PROBE-OK %s"}\n' "$(cat "$(probe_file "$@")")"; }
cmm26p() { sleep 60 & echo $! >"$WORKER_PID"; wait; }
"""
# A hist that finds the worker's task under its parent, and records how it was asked.
HIST = """#!/bin/bash
printf '%s\\n' "$*" >>"$HIST_CALLS"
[[ -n "$HIST_MISS" ]] && { echo 'no matches'; exit 0; }
printf '1 hit, newest first\\nw-abcd1234:1+1|[s:abcd1234 commandcode] user: …Probe %s: a read-only check\\n' "$2"
"""


class ProbeLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "wrappers").write_text(WRAPPERS)
        (self.root / "bin").mkdir()
        hist = self.root / "bin/hist"
        hist.write_text(HIST)
        hist.chmod(0o755)
        self.calls = self.root / "hist-calls"
        self.env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
        self.env.update(BASH_AGENTS_FILE=str(self.root / "wrappers"), HIST_CALLS=str(self.calls),
                        PATH=f"{self.root / 'bin'}:{os.environ['PATH']}", CLAUDE_CODE_SESSION_ID=PARENT)

    def probe(self, launcher: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(PROBE), launcher, "--timeout", "30"],
                              capture_output=True, text=True, env=self.env, timeout=60)

    def test_a_working_route_passes_every_check(self) -> None:
        result = self.probe("cms")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"pass  launch: ok in \d+s")
        self.assertIn("pass  final message: the expected line, alone", result.stdout)
        self.assertIn("routed model: meta/muse-spark-1.3-contributor", result.stdout)
        self.assertIn(f"pass  hist parent: the worker s:abcd1234 (commandcode) is linked to claude:{PARENT}",
                      result.stdout)
        probe_id = result.stdout.split("(", 1)[1].split(")", 1)[0]
        self.assertEqual(f"find {probe_id} --session {PARENT} --kind user\n", self.calls.read_text())

    def test_a_retired_model_reports_no_route_and_starts_nothing_else(self) -> None:
        result = self.probe("ocargh")
        self.assertEqual(1, result.returncode)
        self.assertIn("FAIL  launch: failed with status 1", result.stdout)
        self.assertIn("failure class: quarantined: no route to the launcher's model", result.stdout)
        self.assertIn("hist parent: not checked: the launch failed", result.stdout)
        self.assertFalse(self.calls.exists())

    def test_an_answer_without_the_files_line_fails(self) -> None:
        # A guess, and a run that ended on a progress note: neither shows a tool call's result.
        for launcher, shown in (("cmg", "PROBE-OK 0123456789abcdef01234567"), ("cmds", "Now I will read the file.")):
            with self.subTest(launcher=launcher):
                result = self.probe(launcher)
                self.assertEqual(1, result.returncode)
                self.assertIn(f"FAIL  final message: lacks the file's line, so no tool call shows: {shown}",
                              result.stdout)
                self.assertIn("routed model: not named in the CLI's output", result.stdout)

    def test_outside_a_session_the_parent_link_is_not_checked(self) -> None:
        del self.env["CLAUDE_CODE_SESSION_ID"]
        result = self.probe("cms")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("hist parent: not checked: no single launching session", result.stdout)
        self.assertFalse(self.calls.exists())

    def test_a_worker_hist_cannot_find_under_its_parent_fails(self) -> None:
        loader = importlib.machinery.SourceFileLoader("probe_launcher", str(PROBE))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        module.HIST_WAIT_SECONDS = 0
        # The whole environment, so a CODEX_THREAD_ID inherited from a Codex session cannot leak in (11-01 review).
        with mock.patch.dict(os.environ, dict(self.env, HIST_MISS="1"), clear=True):
            self.assertEqual((False, f"no worker message carrying probe-x under claude:{PARENT}"),
                             module.hist_parent("probe-x", "cms"))
        self.assertEqual(module.HIST_ATTEMPTS, len(self.calls.read_text().splitlines()))

    def test_review_round_one_cases(self) -> None:
        # 11-01 review (cam, ccfx). A final-text answer in JSON names no routed model; a launcher that never ran
        # wrote no output; a harness hist does not record is not a failed parent link.
        claimed = self.probe("cax")
        self.assertEqual(0, claimed.returncode, claimed.stdout)
        self.assertIn("routed model: not exposed: this launcher's output is its final text", claimed.stdout)
        self.assertNotIn("model-claimed", claimed.stdout)
        unknown = self.probe("nosuch")
        self.assertIn("routed model: not exposed: the CLI wrote no output", unknown.stdout)
        self.calls.unlink(missing_ok=True)
        kimi = self.probe("kimm")
        self.assertEqual(0, kimi.returncode, kimi.stdout)
        self.assertIn("hist parent: not checked: hist records no kimi/- sessions", kimi.stdout)
        self.assertFalse(self.calls.exists())

    def test_an_interrupted_probe_stops_its_worker(self) -> None:
        pid_file = self.root / "worker.pid"
        probe = subprocess.Popen([sys.executable, "-B", str(PROBE), "cmm26p"], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=dict(self.env, WORKER_PID=str(pid_file)))
        deadline = time.monotonic() + 20
        while not (pid_file.exists() and pid_file.read_text().strip()) and time.monotonic() < deadline:
            time.sleep(0.1)
        worker = int(pid_file.read_text())
        probe.send_signal(signal.SIGINT)
        probe.communicate(timeout=20)
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(worker, 0)

    def test_an_interrupt_in_the_grace_after_sigterm_stops_its_worker(self) -> None:
        # 11-01 review round 2 (cam F4, ccfx N4): a worker that ignores SIGTERM, then a Ctrl-C during the grace.
        pid_file = self.root / "worker.pid"
        (self.root / "stubborn").write_text("cmm26p() { trap '' TERM; sleep 60 & echo $! >\"$WORKER_PID\"; wait; }\n")
        probe = subprocess.Popen([sys.executable, "-B", str(PROBE), "cmm26p", "--timeout", "1"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=dict(self.env, WORKER_PID=str(pid_file),
                                          BASH_AGENTS_FILE=str(self.root / "stubborn")))
        deadline = time.monotonic() + 20
        while not (pid_file.exists() and pid_file.read_text().strip()) and time.monotonic() < deadline:
            time.sleep(0.1)
        worker = int(pid_file.read_text())
        time.sleep(3)  # past the timeout and its SIGTERM, inside the ten-second grace
        os.kill(worker, 0)
        probe.send_signal(signal.SIGINT)
        probe.communicate(timeout=20)
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(worker, 0)

    def test_a_terminated_probe_stops_its_worker(self) -> None:
        # 11-01 review round 3 (cam F4): SIGTERM to the probe itself, whose default action skips all cleanup.
        pid_file = self.root / "worker.pid"
        probe = subprocess.Popen([sys.executable, "-B", str(PROBE), "cmm26p"], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=dict(self.env, WORKER_PID=str(pid_file)))
        deadline = time.monotonic() + 20
        while not (pid_file.exists() and pid_file.read_text().strip()) and time.monotonic() < deadline:
            time.sleep(0.1)
        worker = int(pid_file.read_text())
        probe.send_signal(signal.SIGTERM)
        probe.communicate(timeout=20)
        self.assertEqual(128 + signal.SIGTERM, probe.returncode)
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(worker, 0)

    def test_a_child_left_behind_by_the_adapter_is_stopped(self) -> None:
        # 11-01 review round 3 (cam N1): a child that ignores SIGTERM and holds none of the adapter's pipes
        # outlives it, after a timeout or a normal return; a wave would stop it, so the probe does too.
        pid_file = self.root / "worker.pid"
        spawn = "( trap '' TERM; exec sleep 60 ) </dev/null >/dev/null 2>&1 & echo $! >\"$WORKER_PID\""
        for name, body in (("timed out", f"{spawn}; sleep 60"),
                           ("returned", f"{spawn}; printf '%s\\n' '{{\"type\":\"result\",\"subtype\":"
                                        f"\"success\",\"finalText\":\"done\"}}'")):
            with self.subTest(name):
                pid_file.unlink(missing_ok=True)
                (self.root / "leaky").write_text(f"cmm26p() {{ {body}; }}\n")
                result = subprocess.run([sys.executable, "-B", str(PROBE), "cmm26p", "--timeout", "2"],
                                        capture_output=True, text=True, timeout=60,
                                        env=dict(self.env, WORKER_PID=str(pid_file),
                                                 BASH_AGENTS_FILE=str(self.root / "leaky")))
                self.assertIn("launch: timed out" if name == "timed out" else "launch: ok", result.stdout)
                time.sleep(0.5)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_file.read_text()), 0)

    def test_a_failed_final_text_launch_names_no_model(self) -> None:
        # 11-01 review round 2 (cam F5): a failed run's answer goes to stderr, so JSON it wrote is no metadata.
        (self.root / "failing").write_text(
            """cax() { printf '%s\\n' '{"model":"invented-by-assistant","answer":"partial"}'; return 1; }\n""")
        self.env["BASH_AGENTS_FILE"] = str(self.root / "failing")
        result = self.probe("cax")
        self.assertIn("routed model: not checked: the launch failed", result.stdout)
        self.assertNotRegex(result.stdout, "routed model: .*invented")

    def test_a_plain_antigravity_name_run_on_the_second_account_is_not_a_failed_link(self) -> None:
        # 11-01 review round 2 (cam F8, ccfx N1): aggb runs as aggb2 when the second account has more quota, and
        # hist does not record that account.
        home = self.root / "home"
        for account, room in ((home, 0.1), (home / ".agy2", 0.9)):
            account.mkdir(parents=True, exist_ok=True)
            buckets = [{"name": w, "window": w, "remaining_fraction": room} for w in ("weekly", "5h")]
            (account / "usage.json").write_text(json.dumps({"status": "SUCCESS", "command": {
                "name": "usage", "data": {"groups": [{"name": "Gemini Models", "buckets": buckets}]}}}))
        token = home / ".agy2/.gemini/antigravity-cli/antigravity-oauth-token"
        token.parent.mkdir(parents=True)
        token.write_text("token")
        agy = self.root / "bin/agy"
        agy.write_text('#!/bin/bash\ncat "$HOME/usage.json"\n')
        agy.chmod(0o755)
        (self.root / "accounts").write_text(
            "probe_file() { grep -o '/[^ ]*\\.txt' <<<\"${!#}\" | head -1; }\n"
            'aggb2() { printf \'PROBE-OK %s\\n\' "$(cat "$(probe_file "$@")")"; }\n')
        self.env.update(HOME=str(home), AGY2_HOME=str(home / ".agy2"), XDG_CACHE_HOME=str(self.root / "cache"),
                        BASH_AGENTS_FILE=str(self.root / "accounts"))
        result = self.probe("aggb")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("pass  final message: the expected line, alone", result.stdout)
        self.assertIn("hist parent: not checked: hist records no antigravity/agy2 sessions", result.stdout)
        self.assertFalse(self.calls.exists())

    def test_a_failed_raw_copy_leaves_the_failure_class_last(self) -> None:
        # The copy for probe-launcher must never push the failure-class sentinel off stderr's last line.
        (self.root / "failing").write_text('cmg() { echo "Error: rate limit exceeded"; return 1; }\n')
        result = subprocess.run(["bash", str(PROBE.parent / "run-worker.sh"), "cmg"], input="TASK", text=True,
                                capture_output=True, timeout=30,
                                env=dict(self.env, BASH_AGENTS_FILE=str(self.root / "failing"),
                                         DELEGATE_WORKER_RAW=str(self.root / "missing-dir/raw")))
        self.assertEqual("delegate worker: failure class: rate-limited: rate limit or quota",
                         result.stderr.rstrip("\n").splitlines()[-1])

    def test_codex_api_key_routes_use_the_api_key_account(self) -> None:
        loader = importlib.machinery.SourceFileLoader("probe_launcher", str(PROBE))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        self.assertEqual(("codex", "key"), module.route("cdxk"))
        self.assertEqual(("codex", "key"), module.route("cdxk:cdx"))
        self.assertIsNone(module.route("cdxk:cdx2"))
        self.assertIsNone(module.route("cdxk:agg"))

    def test_model_names_come_only_from_json_output(self) -> None:
        loader = importlib.machinery.SourceFileLoader("probe_launcher", str(PROBE))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        claude = '{"type":"result","result":"x","modelUsage":{"claude-opus-5-5":{},"claude-haiku-5-5":{}}}'
        self.assertEqual(["claude-opus-5-5", "claude-haiku-5-5"], module.models(claude))
        opencode = '{"part":{"modelID":"gemini-4-argon"}}\n{"part":{"modelID":"gemini-4-argon"}}\n'
        self.assertEqual(["gemini-4-argon"], module.models(opencode))
        self.assertIsNone(module.models("PROBE-OK abc\n42\n"))


if __name__ == "__main__":
    unittest.main()
