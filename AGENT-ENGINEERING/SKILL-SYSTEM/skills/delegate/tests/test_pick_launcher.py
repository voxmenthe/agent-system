"""pick-launcher contracts: real CLI runs against fake wrapper definitions and quota records, never provider calls."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts/pick-launcher"
# Wrapper bodies shaped like ~/.bash_agents; `usage --records` replays the test's records and logs its call.
DEFINITIONS = r'''
ccx()  ( _cc_launch "sub" "" "opus[1m]" "xhigh" "$@" )
ccfh() ( _cc_launch "sub" "" "fable[1m]" "high" "$@" )
ccxX() { ccx --settings "$_cc_boost_settings" "$@"; }
cckx() ( _cc_launch "key" "" "opus[1m]" "xhigh" "$@" )
cdm()  { _codex_launch "scoped" "stream" "gpt-6.2-sol" "max" -s danger-full-access "$@"; }
cdm2() { _codex_secondary cdm "$@"; }
agom()  ( _agy_launch "normal" "claude-opus-5-5-medium" "" "final" "" "$@" )
agom2() { _agy_secondary agom "$@"; }
argh()  ( _agy_launch "normal" "gemini-4-argon-high" "" "final" "" "$@" )
dopm() {
  local devin_bin
  devin_bin="$(_devin)" || return
  "$devin_bin" --model claude-opus-5-5-max --permission-mode bypass "$@"
}
cmnh()    ( _cmd_launch "google/gemini-4-neon" "high" "$@" )
grokxh()  ( _grok_launch --model grok-4.6 --effort xhigh --always-approve "$@" )
grok2xh() ( export GROK_HOME="${GROK2_HOME:-$HOME/.grok2}"; _grok_launch --model grok-4.6 "$@" )
ocargh()  ( _oc_launch "opencode-go/gemini-4-argon" "high" "$@" )
ocmf()    ( _oc_launch "opencode/mimo-v2.6-flash-free" "" "$@" )
ocnx()    ( _oc_launch "google/gemini-4-neon" "xhigh" "$@" )
pihy4flash() ( _pi_launch "opencode-go/hy4-flash-free" "high" "$@" )
pilongcat()  ( _pi_launch "opencode-go/longcat-2.5" "" "$@" )
kimm() { KIMI_MODEL_THINKING_EFFORT=max _kimi_launch "normal" "$@"; }
mixed() { _cmd_launch x; _devin; }
usage() { printf '%s\n' "$*" >> "$PICK_TEST_CALLS"; cat "$PICK_TEST_RECORDS"; }
'''
DAY = 86400


def window(harness: str, label: str, period: str, remaining: float, resets_in: float) -> str:
    seconds = {"5h": 18000, "daily": DAY, "weekly": 7 * DAY, "monthly": 30 * DAY}[period]
    return "\t".join(("window", harness, str(int(time.time() + resets_in)), label, period,
                      f"{100 - remaining:g}", f"{remaining:g}", str(seconds)))


class PickLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="pick-launcher-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "agents.sh").write_text(DEFINITIONS)
        self.calls = self.root / "calls"
        self.env = dict(os.environ, BASH_AGENTS_FILE=str(self.root / "agents.sh"),
                        PICK_TEST_CALLS=str(self.calls), PICK_TEST_RECORDS=str(self.root / "records"))

    def pick(self, records: list[str], *args: str) -> subprocess.CompletedProcess[str]:
        (self.root / "records").write_text("".join(line + "\n" for line in records))
        return subprocess.run([str(SCRIPT), *args], env=self.env, capture_output=True, text=True, timeout=30)

    def assertPicks(self, expected: str | None, records: list[str], *ranks: str, floor: str = "") -> None:
        result = self.pick(records, *(("--floor", floor) if floor else ()), *ranks)
        self.assertEqual((0, f"{expected}\n") if expected else (1, ""), (result.returncode, result.stdout),
                         result.stderr)
        # Every candidate gets a reading and verdict line on stderr.
        named = [line.split()[1] for line in result.stderr.splitlines() if line.startswith("pick-launcher: ")]
        self.assertTrue({name for rank in ranks for name in rank.split(",")} <= set(named), result.stderr)

    def test_proof_scenes_from_the_intent_brief(self) -> None:
        command_code = [window("cmd", "Command Code · Pro Plan", "weekly", 79, 1.5 * DAY),
                        window("cmd", "Command Code · Pro Plan", "monthly", 89, 23 * DAY)]
        devin_drained = [window("devin", "Devin · Pro", "daily", 100, DAY), window("devin", "Devin · Pro", "weekly", 1, DAY)]
        devin_healthy = [window("devin", "Devin · Pro", "daily", 100, DAY), window("devin", "Devin · Pro", "weekly", 40, DAY)]
        codex_healthy = [window("codex", "Codex · Codex", "weekly", 100, 7 * DAY),
                         window("codex", "Codex 2 · Codex (weekly)", "weekly", 86, DAY)]
        all_low = [window("codex", "Codex · Codex", "weekly", 5, 7 * DAY),
                   window("codex", "Codex 2 · Codex (weekly)", "weekly", 3, DAY),
                   window("antigravity", "Antigravity · Gemini 4 Argon", "weekly", 2, 2 * DAY)]
        for expected, records, args in (
            # Devin's expiring 1% is written off rather than starting work that will likely die.
            ("cmnh", devin_drained + command_code, ("dopm,cmnh",)),
            ("dopm", devin_healthy + command_code, ("dopm,cmnh",)),
            # Rank beats expiry: cdm2's credit expires sooner but cdm is ranked first and healthy.
            ("cdm", codex_healthy, ("cdm", "cdm2", "argh", "ocnx")),
            ("ocnx", all_low, ("cdm", "cdm2", "argh", "ocnx")),
            (None, all_low, ("cdm,cdm2", "argh")),
        ):
            with self.subTest(expected=expected, args=args):
                self.assertPicks(expected, records, *args)

    def test_unknown_quota_never_falls_through_to_pay_per_use(self) -> None:
        no_codex = [window("cmd", "Command Code · Pro Plan", "weekly", 3, DAY),
                    "unranked\tcodex\tCodex\tquery failed"]
        for expected, args in ((None, ("cdm", "ocnx")), (None, ("cdm,ocnx",)), (None, ("cdm", "cmnh,cckx")),
                               ("ocmf", ("cdm", "ocmf"))):
            with self.subTest(args=args):
                self.assertPicks(expected, no_codex, *args)
        self.assertIn("query failed", self.pick(no_codex, "cdm", "ocnx").stderr)

    def test_within_a_rank_subscription_then_free_then_pay_per_use(self) -> None:
        for expected, remaining, args in (("cmnh", 50, ("ocnx,ocmf,cmnh",)), ("ocmf", 5, ("ocnx,ocmf,cmnh",)),
                                          ("cckx", 5, ("cckx,ocnx,cmnh",))):
            with self.subTest(args=args, remaining=remaining):
                self.assertPicks(expected, [window("cmd", "Command Code · Pro Plan", "weekly", remaining, 6 * DAY)], *args)

    def test_soonest_expiring_credit_goes_first_among_equals(self) -> None:
        grok = [window("grok", "Grok · X Premium+", "weekly", 90, 5 * DAY),
                window("grok", "Grok 2 · SuperGrok Lite", "weekly", 30, 2 * DAY)]
        self.assertPicks("grok2xh", grok, "grokxh,grok2xh")
        opencode = [window("opencode", "OpenCode Go", "weekly", 50, DAY), window("opencode", "OpenCode Go", "5h", 90, 3600)]
        self.assertPicks("ocargh", opencode + grok, "grok2xh,ocargh")

    def test_room_is_the_tightest_window_that_applies_to_the_launcher(self) -> None:
        claude = [window("claude", "Claude · Weekly", "weekly", 50, 2 * DAY),
                  window("claude", "Claude · Weekly (Fable)", "weekly", 5, 2 * DAY)]
        self.assertPicks("ccx", claude, "ccfh,ccx")
        self.assertPicks("ccxX", claude, "ccfh,ccxX")
        self.assertPicks(None, claude, "ccfh")
        # Antigravity meters each model group per account: agom ignores its account's drained Gemini group.
        agy = [window("antigravity", "Antigravity · Claude and GPT models", "weekly", 60, 5 * DAY),
               window("antigravity", "Antigravity · Gemini Models", "weekly", 1, DAY),
               window("antigravity", "Antigravity 2 · Claude and GPT models", "weekly", 90, 2 * DAY)]
        self.assertPicks("agom2", agy, "agom,agom2")
        self.assertPicks("agom", agy, "argh,agom")

    def test_five_hour_windows_limit_room_but_are_not_expiring_credit(self) -> None:
        primary_expires_first = [window("codex", "Codex · Codex", "weekly", 80, 2 * DAY),
                                 window("codex", "Codex 2 · Codex (weekly)", "weekly", 90, 6 * DAY)]
        second_expires_first = [window("codex", "Codex · Codex", "weekly", 80, 6 * DAY),
                                window("codex", "Codex 2 · Codex (weekly)", "weekly", 90, 2 * DAY)]
        for expected, weekly, five_hour in (
            # Codex 2's five-hour window resets in an hour, but the primary's weekly credit expires first.
            ("cdm", primary_expires_first, window("codex", "Codex 2 · Codex", "5h", 50, 3600)),
            ("cdm2", second_expires_first, window("codex", "Codex 2 · Codex", "5h", 50, 3600)),
            ("cdm", second_expires_first, window("codex", "Codex 2 · Codex", "5h", 5, 3600)),
            # A window whose reset has passed is full again.
            ("cdm2", second_expires_first, window("codex", "Codex 2 · Codex", "5h", 0, -60)),
        ):
            with self.subTest(expected=expected, five_hour=five_hour):
                self.assertPicks(expected, weekly + [five_hour], "cdm,cdm2")

    def test_floor_option(self) -> None:
        devin = [window("devin", "Devin · Pro", "weekly", 1, DAY)]
        self.assertPicks(None, devin, "dopm")
        self.assertPicks("dopm", devin, "dopm", floor="0.3")
        self.assertEqual(2, self.pick(devin, "--floor", "150", "dopm").returncode)

    def test_names_that_are_not_one_known_launcher_exit_2_before_reading_quota(self) -> None:
        for args in (("nosuch",), ("kimm",), ("mixed",), ("usage",), ("cdm,cdm",), ("cdm", "cdm"),
                     ("cdm,",), ("cdxk:cdm",), ()):
            with self.subTest(args=args):
                result = self.pick([], *args)
                self.assertEqual((2, ""), (result.returncode, result.stdout), result.stderr)
                self.assertFalse(self.calls.exists())

    def test_pi_go_launchers_spend_the_opencode_go_quota(self) -> None:
        opencode = [window("opencode", "OpenCode Go", "weekly", 50, DAY)]
        self.assertPicks("pihy4flash", opencode, "pihy4flash,pilongcat")
        self.assertPicks("ocargh", opencode, "ocargh,pihy4flash")
        self.assertPicks(None, [window("opencode", "OpenCode Go", "weekly", 5, DAY)], "pihy4flash")
        self.assertEqual(["--records -a opencode"] * 3, self.calls.read_text().splitlines())

    def test_reads_only_the_harnesses_its_subscription_launchers_spend(self) -> None:
        self.assertPicks("ocmf", [], "ocnx,ocmf")
        self.assertFalse(self.calls.exists())
        self.assertPicks("cmnh", [window("cmd", "Command Code · Pro Plan", "weekly", 50, DAY)], "cmnh,ocnx,dopm")
        self.assertEqual("--records -a cmd,devin\n", self.calls.read_text())


class ResolutionParityTests(unittest.TestCase):
    """Every launcher in launcher-routes.tsv resolves, from the live shell definitions, to that row's account."""

    def test_routes_table_accounts_match_wrapper_definitions(self) -> None:
        agents_file = Path(os.environ.get("BASH_AGENTS_FILE", Path.home() / ".bash_agents"))
        if not agents_file.is_file():
            self.skipTest(f"no shell definitions at {agents_file}")
        loader = SourceFileLoader("pick_launcher", str(SCRIPT))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        sys.modules[loader.name] = module
        self.addCleanup(sys.modules.pop, loader.name)
        loader.exec_module(module)
        declared = subprocess.run(["bash", "--noprofile", "--norc", "-c", 'source "$1" >/dev/null 2>&1; declare -f',
                                   "parity", str(agents_file)], capture_output=True, text=True, check=True).stdout
        definitions = module.parse_definitions(declared)
        expected = {"-": (module.SUBSCRIPTION, 1), "agy2": (module.SUBSCRIPTION, 2), "codex2": (module.SUBSCRIPTION, 2),
                    "grok2": (module.SUBSCRIPTION, 2), "grok3": (module.SUBSCRIPTION, 3),
                    "key": (module.METERED, 1), "zen": (module.FREE, 1)}
        rows = (SKILL / "scripts/launcher-routes.tsv").read_text().splitlines()[1:]
        checked = 0
        for harness, account, launchers in (row.split("\t") for row in rows):
            if harness == "kimi":
                continue
            kind, number = expected[account]
            for launcher in launchers.split():
                with self.subTest(launcher=launcher):
                    pool = module.resolve(launcher, definitions)
                    self.assertEqual(kind, pool.kind)
                    if kind == module.SUBSCRIPTION:
                        self.assertEqual((harness, number), (pool.harness, pool.account))
                    checked += 1
        self.assertGreater(checked, 150)


if __name__ == "__main__":
    unittest.main()
