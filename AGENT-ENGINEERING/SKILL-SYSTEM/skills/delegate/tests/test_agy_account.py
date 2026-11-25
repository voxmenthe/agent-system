"""The Antigravity account pick and quota overflow, against a fake agy that serves each HOME its own /usage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PICKER = SCRIPTS / "agy-account.py"
RUNNER = SCRIPTS / "run-worker.sh"

# Serves $HOME/usage.json as /usage, failing when it is absent; each query appends its HOME to $AGY_CALLS
# and leaves the SSH_CONNECTION it saw in $HOME/ssh_connection.
FAKE_AGY = """#!/usr/bin/env bash
printf '%s\\n' "$HOME" >>"$AGY_CALLS"
printf '%s' "${SSH_CONNECTION:-}" >"$HOME/ssh_connection"
[[ -n "$AGY_DELAY" ]] && sleep "$AGY_DELAY"
[[ -r "$HOME/usage.json" ]] || { echo 'not readable' >&2; exit 1; }
cat "$HOME/usage.json"
"""


def usage(**rooms: float | tuple[float, float] | str) -> dict:
    """A /usage reply; each group's value is its weekly and five-hour room, one room for both, or "spent" for an
    exhausted week (AGY then disables the five-hour bucket)."""
    groups = {"gemini": "Gemini Models", "claude": "Claude and GPT models", "argon": "Gemini 4 Argon"}
    reply = []
    for key, room in rooms.items():
        if room == "spent":
            buckets = [{"window": "weekly", "remaining_fraction": 0.0},
                       {"window": "5h", "remaining_fraction": 1.0, "disabled": True}]
        else:
            weekly, five = room if isinstance(room, tuple) else (room, room)
            buckets = [{"window": "weekly", "remaining_fraction": weekly},
                       {"window": "5h", "remaining_fraction": five}]
        reply.append({"name": groups[key], "buckets": [{"name": b["window"], **b} for b in buckets]})
    return {"status": "SUCCESS", "command": {"name": "usage", "data": {"groups": reply}}}


class FakeAgy(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.home, self.second = root / "home", root / "home" / ".agy2"
        bin_dir = root / "bin"
        for directory in (self.home, self.second, bin_dir):
            directory.mkdir(parents=True, exist_ok=True)
        (bin_dir / "agy").write_text(FAKE_AGY)
        (bin_dir / "agy").chmod(0o755)
        self.calls = root / "calls"
        self.env = {
            **{k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "AGY_DELAY", "SSH_CONNECTION")},
            "HOME": str(self.home), "AGY2_HOME": str(self.second), "XDG_CACHE_HOME": str(root / "cache"),
            "PATH": f"{bin_dir}:{os.environ['PATH']}", "AGY_CALLS": str(self.calls),
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def sign_in_second(self) -> None:
        token = self.second / ".gemini/antigravity-cli/antigravity-oauth-token"
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text("token")

    def serve(self, home: Path, reply: dict | None) -> None:
        path = home / "usage.json"
        if reply is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(reply))

    def picker(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["python3", str(PICKER), *args], env=self.env, capture_output=True, text=True,
                              check=False, timeout=30)

    def queried(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []


class AgyAccountTests(FakeAgy):
    def test_the_account_with_more_of_the_launchers_model_group_left_is_picked(self) -> None:
        spent = "spent"
        cases = [
            # launcher, primary reply, second reply, picked
            ("aggb", usage(gemini=0.4), usage(gemini=0.9), "aggb2"),
            ("aggb", usage(gemini=0.9), usage(gemini=0.4), "aggb"),
            ("aggb", usage(gemini=0.5), usage(gemini=0.5), "aggb"),
            # The tighter of the weekly and five-hour windows is the room.
            ("aggb", usage(gemini=(0.9, 0.1)), usage(gemini=(0.5, 0.5)), "aggb2"),
            # Each launcher reads its own model's group.
            ("agom", usage(gemini=0.9, claude=0.1), usage(gemini=0.1, claude=0.8), "agom2"),
            ("aggbs", usage(gemini=0.9, claude=0.1), usage(gemini=0.1, claude=0.8), "aggbs"),
            ("aghh", usage(gemini=0.1, argon=0.9), usage(gemini=0.8, argon=0.1), "aghh2"),
            ("aghhb", usage(gemini=0.8, argon=0.1), usage(gemini=0.1, argon=0.9), "aghhb"),
            ("aghx", usage(gemini=0.1, claude=0.9), usage(gemini=0.7, claude=0.1), "aghx2"),
            ("aghxb", usage(gemini=0.7, claude=0.1), usage(gemini=0.1, claude=0.9), "aghxb"),
            ("agcm", usage(gemini=0.1, argon=0.9), usage(gemini=0.8, argon=0.1), "agcm2"),
            ("agcmb", usage(gemini=0.8, argon=0.1), usage(gemini=0.1, argon=0.9), "agcmb"),
            ("agch", usage(gemini=0.1, claude=0.9), usage(gemini=0.7, claude=0.1), "agch2"),
            ("agchb", usage(gemini=0.7, claude=0.1), usage(gemini=0.1, claude=0.9), "agchb"),
            ("agnm", usage(gemini=0.1, argon=0.9), usage(gemini=0.8, argon=0.1), "agnm2"),
            ("agnmb", usage(gemini=0.8, argon=0.1), usage(gemini=0.1, argon=0.9), "agnmb"),
            ("agnh", usage(gemini=0.1, claude=0.9), usage(gemini=0.7, claude=0.1), "agnh2"),
            ("agnhb", usage(gemini=0.7, claude=0.1), usage(gemini=0.1, claude=0.9), "agnhb"),
            ("agnx", usage(gemini=0.1, argon=0.9), usage(gemini=0.6, argon=0.1), "agnx2"),
            ("agnxb", usage(gemini=0.6, argon=0.1), usage(gemini=0.1, argon=0.9), "agnxb"),
            ("argh", usage(gemini=0.1, argon=0.6), usage(gemini=0.9, argon=0.2), "argh"),
            # An exhausted week has no room, whatever its disabled five-hour bucket says.
            ("agg", usage(gemini=spent), usage(gemini=0.05), "agg2"),
            # Unknown is between room and none.
            ("aggb", None, usage(gemini=0.05), "aggb2"),
            ("aggb", usage(gemini=spent), None, "aggb2"),
            ("aggb", usage(gemini=0.05), None, "aggb"),
            ("aggb", None, None, "aggb"),
            ("aggb", usage(claude=0.9), usage(claude=0.9), "aggb"),
        ]
        self.sign_in_second()
        for launcher, primary, second, picked in cases:
            with self.subTest(launcher=launcher, primary=primary, second=second):
                self.serve(self.home, primary)
                self.serve(self.second, second)
                for cache in Path(self.env["XDG_CACHE_HOME"]).glob("agy-account/*"):
                    cache.unlink()
                result = self.picker("pick", launcher)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(f"{picked}\n", result.stdout)
                self.assertIn(f"agy-account: {picked} (", result.stderr)

    def test_a_signed_out_second_account_is_never_queried(self) -> None:
        self.serve(self.home, usage(gemini=0.01))
        self.serve(self.second, usage(gemini=0.99))
        result = self.picker("pick", "aggb")
        self.assertEqual("aggb\n", result.stdout)
        self.assertEqual([], self.queried())

    def test_only_the_second_account_presents_an_ssh_session(self) -> None:
        # AGY then keeps that account's tokens in its file instead of trying its missing keychain.
        self.sign_in_second()
        self.serve(self.home, usage(gemini=0.4))
        self.serve(self.second, usage(gemini=0.9))
        self.assertEqual("aggb2\n", self.picker("pick", "aggb").stdout)
        self.assertEqual("", (self.home / "ssh_connection").read_text())
        self.assertNotEqual("", (self.second / "ssh_connection").read_text())

    def test_a_recent_reading_is_shared_and_both_accounts_are_read_at_once(self) -> None:
        self.sign_in_second()
        self.serve(self.home, usage(gemini=0.4, claude=0.9))
        self.serve(self.second, usage(gemini=0.9, claude=0.4))
        self.env["AGY_DELAY"] = "1"
        started = time.monotonic()
        burst = [subprocess.Popen(["python3", str(PICKER), "pick", launcher], env=self.env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for launcher in ("aggb", "agom", "aggb", "agoh")]
        picked = [process.communicate(timeout=30)[0] for process in burst]
        elapsed = time.monotonic() - started
        self.assertEqual(["aggb2\n", "agom\n", "aggb2\n", "agoh\n"], picked)
        # One reading of each account serves the burst, and the two readings overlap.
        self.assertEqual(sorted([str(self.home), str(self.second)]), sorted(self.queried()))
        self.assertLess(elapsed, 1.9)

    def test_an_old_reading_is_read_again(self) -> None:
        self.sign_in_second()
        self.serve(self.home, usage(gemini=0.4))
        self.serve(self.second, usage(gemini=0.9))
        self.assertEqual("aggb2\n", self.picker("pick", "aggb").stdout)
        readings = Path(self.env["XDG_CACHE_HOME"], "agy-account", "readings.json")
        cached = json.loads(readings.read_text())
        for entry in cached.values():
            entry["at"] -= 600
        readings.write_text(json.dumps(cached))
        self.serve(self.second, usage(gemini=0.1))
        self.assertEqual("aggb\n", self.picker("pick", "aggb").stdout)
        self.assertEqual(4, len(self.queried()))

    def test_overflow_rereads_the_accounts_and_names_the_twin_with_quota(self) -> None:
        self.sign_in_second()
        cases = [
            # failed launcher, primary reply then, second reply then, answer
            ("aggb", usage(gemini="spent"), usage(gemini=0.5), "retry aggb2"),
            ("aggb2", usage(gemini=0.5), usage(gemini=0.0), "retry aggb"),
            ("aggb", usage(gemini=0.0), usage(gemini="spent"), "exhausted Gemini Models"),
            # The model's quota is not what stopped the run.
            ("aggb", usage(gemini=0.3), usage(gemini=0.9), "other"),
            ("aggb", None, usage(gemini=0.9), "other"),
            ("agom", usage(gemini=0.0, claude=0.3), usage(claude=0.9), "other"),
        ]
        for failed, primary, second, answer in cases:
            with self.subTest(failed=failed, primary=primary, second=second):
                # The cache holds a reading from before the run, which still showed room.
                self.serve(self.home, usage(gemini=0.9, claude=0.9))
                self.serve(self.second, usage(gemini=0.9, claude=0.9))
                for cache in Path(self.env["XDG_CACHE_HOME"]).glob("agy-account/*"):
                    cache.unlink()
                self.picker("pick", "aggb")
                self.serve(self.home, primary)
                self.serve(self.second, second)
                result = self.picker("overflow", failed)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(f"{answer}\n", result.stdout)

    def test_overflow_with_one_signed_in_account(self) -> None:
        self.serve(self.home, usage(gemini="spent"))
        self.assertEqual("exhausted Gemini Models\n", self.picker("overflow", "aggb").stdout)
        self.assertEqual("other\n", self.picker("overflow", "aggb2").stdout)

    def test_pick_rejects_a_pinned_or_unknown_launcher(self) -> None:
        for launcher in ("aggb2", "grok", "agg3"):
            with self.subTest(launcher=launcher):
                self.assertEqual(2, self.picker("pick", launcher).returncode)


class RunWorkerAccountTests(FakeAgy):
    """run-worker.sh picks the account for a plain name, pins a `2` name, and moves a quota-stopped task once."""

    LAUNCHERS = r'''
aggb() { _fake_agy primary "$@"; }
aggb2() { _fake_agy second "$@"; }
_fake_agy() {
  local account=$1
  printf '%s\n' "$account" >>"$RUNS"
  if [[ -e "$SPEND/$account" ]]; then
    # The run spends the account's last Gemini quota and stops.
    cp "$SPEND/$account" "$(if [[ $account == primary ]]; then echo "$HOME"; else echo "$AGY2_HOME"; fi)/usage.json"
    echo "agy: the model stopped responding" >&2
    return 1
  fi
  printf 'FINAL from %s: %s\n' "$account" "$3"
}
'''

    def setUp(self) -> None:
        super().setUp()
        root = Path(self.temporary.name)
        (root / "agents").write_text(self.LAUNCHERS)
        self.spend = root / "spend"
        self.spend.mkdir()
        self.runs = root / "runs"
        self.env.update(BASH_AGENTS_FILE=str(root / "agents"), SPEND=str(self.spend), RUNS=str(self.runs))
        self.sign_in_second()

    def run_worker(self, launcher: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(RUNNER), launcher], input="bounded task", env=self.env,
                              capture_output=True, text=True, check=False, timeout=60)

    def ran_on(self) -> list[str]:
        return self.runs.read_text().splitlines() if self.runs.exists() else []

    def test_a_plain_name_runs_on_the_account_with_more_quota(self) -> None:
        self.serve(self.home, usage(gemini=0.2))
        self.serve(self.second, usage(gemini=0.7))
        result = self.run_worker("aggb")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("FINAL from second: bounded task\n", result.stdout)
        self.assertEqual(["second"], self.ran_on())

    def test_a_pinned_name_runs_on_the_second_account_without_a_reading(self) -> None:
        self.serve(self.home, usage(gemini=0.9))
        self.serve(self.second, usage(gemini=0.1))
        result = self.run_worker("aggb2")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("FINAL from second: bounded task\n", result.stdout)
        self.assertEqual([], self.queried())

    def test_a_task_its_account_runs_out_on_moves_once_to_the_other(self) -> None:
        self.serve(self.home, usage(gemini=0.9))
        self.serve(self.second, usage(gemini=0.4))
        (self.spend / "primary").write_text(json.dumps(usage(gemini="spent")))
        result = self.run_worker("aggb")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("FINAL from second: bounded task\n", result.stdout)
        self.assertEqual(["primary", "second"], self.ran_on())
        self.assertIn("delegate worker: aggb ran out of quota; moving the task to aggb2", result.stderr)

    def test_a_task_both_accounts_run_out_on_is_rate_limited(self) -> None:
        self.serve(self.home, usage(gemini=0.9))
        self.serve(self.second, usage(gemini=0.4))
        (self.spend / "primary").write_text(json.dumps(usage(gemini="spent")))
        (self.spend / "second").write_text(json.dumps(usage(gemini=0.0)))
        result = self.run_worker("aggb")
        self.assertEqual(1, result.returncode)
        self.assertEqual(["primary", "second"], self.ran_on())
        self.assertEqual("delegate worker: failure class: rate-limited: rate limit or quota",
                         result.stderr.rstrip("\n").splitlines()[-1])

    def test_a_failure_with_quota_left_is_not_retried(self) -> None:
        self.serve(self.home, usage(gemini=0.9))
        self.serve(self.second, usage(gemini=0.4))
        (self.spend / "primary").write_text(json.dumps(usage(gemini=0.8)))
        result = self.run_worker("aggb")
        self.assertEqual(1, result.returncode)
        self.assertEqual(["primary"], self.ran_on())
        self.assertEqual("delegate worker: failure class: unclassified", result.stderr.rstrip("\n").splitlines()[-1])

    def test_a_pinned_name_is_not_moved(self) -> None:
        self.serve(self.home, usage(gemini=0.9))
        self.serve(self.second, usage(gemini=0.4))
        (self.spend / "second").write_text(json.dumps(usage(gemini="spent")))
        result = self.run_worker("aggb2")
        self.assertEqual(1, result.returncode)
        self.assertEqual(["second"], self.ran_on())


if __name__ == "__main__":
    unittest.main()
