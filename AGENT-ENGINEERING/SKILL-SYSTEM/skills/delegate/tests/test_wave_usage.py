"""Quota-warning CLI contracts using fake usage output, never provider calls."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/wave-usage"
SAMPLE = """── Devin ───────────────────────────────────────────────────────────────────
  Pro Daily: [░░░░░░░░░░░░░░░░░░░░] 0% used, 100% remaining; resets 2026-10-25 01:00
  Pro Weekly: [████████████████████] 100% used, 0% remaining; resets 2026-10-25 01:00
    15%/day avg so far, 0% left for the final 6 hours
── Kimi ────────────────────────────────────────────────────────────────────
  Weekly: [█████████████████░░░] 86% used, 14% remaining; resets 2026-10-24 22:19
  5h: [█░░░░░░░░░░░░░░░░░░░] 3% used, 97% remaining; resets 2026-10-24 20:19
── Codex ───────────────────────────────────────────────────────────────────
  Codex: [██░░░░░░░░░░░░░░░░░░] 11% used, 89% remaining; 7d window; resets 2026-10-30 14:47
  Banked resets: 2 available
  Codex (codex2): [███░░░░░░░░░░░░░░░░░] 16% used, 84% remaining; 5h window; resets 2026-10-24 23:06
  Codex (weekly) (codex2): [████░░░░░░░░░░░░░░░░] 18% used, 82% remaining; 7d window; resets 2026-10-30 23:23
── Grok ────────────────────────────────────────────────────────────────────
  X Premium+: [███████░░░░░░░░░░░░░] 34% used, 66% remaining; weekly; resets 2026-10-29 16:50
  SuperGrok Lite (grok2): [██████████████████░░] 89% used, 11% remaining; weekly; resets 2026-10-27 20:02
  SuperGrok (grok3): [███████████████████░] 93% used, 7% remaining; weekly; resets 2026-11-02 09:15
── Command Code ────────────────────────────────────────────────────────────
  Pro Plan · active
  Monthly: [█░░░░░░░░░░░░░░░░░░░] $4.65 / $80.00 used (6%) · $75.35 left · 3,358 requests · renews in 20d 21h
── Antigravity ─────────────────────────────────────────────────────────────
  Gemini Models · Weekly Limit Remaining: [░░░░░░░░░░░░░░░░░░░░] 1.8% used, 98.2% remaining; weekly window; resets 2026-10-31 10:23
  Gemini Models (agy2) · Weekly Limit Remaining: [█████████████████░░░] 86% used, 14% remaining; weekly window; resets 2026-11-04 08:00
── 5-hour limits ───────────────────────────────────────────────────────────
  Fake duplicate: [████] 99% used, 1% remaining; resets ignored
── Credits expiring soonest ────────────────────────────────────────────────
  Fake duplicate: [████] 100% used, 0% remaining; resets ignored
"""


class WaveUsageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="delegate usage ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wave = self.root / "wave.txt"
        self.output = self.root / "usage.txt"
        self.output.write_text(SAMPLE, encoding="utf-8")
        self.arguments = self.root / "usage.args"
        self.agents = self.root / "fake agents"
        self.agents.write_text(
            "printf 'source noise\\n'\nprintf 'source diagnostic\\n' >&2\n"
            "usage() {\n"
            "  printf '%s\\n' \"$@\" > \"$WAVE_USAGE_ARGS\"\n"
            "  printf 'usage diagnostic\\n' >&2\n"
            "  cat \"$WAVE_USAGE_OUTPUT\"\n"
            "  return \"${WAVE_USAGE_EXIT:-0}\"\n}\n", encoding="utf-8")
        self.env = dict(os.environ, BASH_AGENTS_FILE=str(self.agents),
                        WAVE_USAGE_ARGS=str(self.arguments), WAVE_USAGE_OUTPUT=str(self.output),
                        WAVE_USAGE_EXIT="0")

    def manifest(self, *launchers: str) -> None:
        self.wave.write_text(
            "COMMON:\nROLE: review\nWORKSPACE: " + str(self.root) + "\n"
            "CONTEXT: Local quota check.\nCONSTRAINTS: Read only.\n"
            "OBJECTIVE: Inspect quotas.\nSCOPE: No edits.\nVERIFY: Read warnings.\n\n" +
            "".join(f"@@ launcher={launcher} name=worker-{index}\n"
                    for index, launcher in enumerate(launchers)), encoding="utf-8")

    def run_usage(self, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(SCRIPT), self.wave.name, *flags], cwd=self.root,
                              env=self.env, text=True, encoding="utf-8",
                              capture_output=True, timeout=5)

    def warnings(self) -> list[str]:
        result = self.run_usage()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        return result.stdout.splitlines()

    def test_sample_warns_only_for_used_harnesses_and_accounts(self) -> None:
        self.manifest("dargh", "cdm2", "kimm")
        self.assertEqual([
            "wave-usage: devin Pro Weekly 100% used, resets 2026-10-25 01:00 (dargh)",
            "wave-usage: kimi Weekly 86% used, resets 2026-10-24 22:19 (kimm)",
        ], self.warnings())
        self.assertEqual(["-a", "devin,codex,kimi"], self.arguments.read_text().splitlines())

    def test_grok_accounts_are_separate(self) -> None:
        self.manifest("grok2")
        self.assertEqual([
            "wave-usage: grok SuperGrok Lite (grok2) 89% used, "
            "resets 2026-10-27 20:02 (grok2)",
        ], self.warnings())
        self.manifest("grok3xh")
        self.assertEqual([
            "wave-usage: grok SuperGrok (grok3) 93% used, "
            "resets 2026-11-02 09:15 (grok3xh)",
        ], self.warnings())
        self.manifest("grok")
        self.assertEqual([], self.warnings())
        self.assertEqual(["-a", "grok"], self.arguments.read_text().splitlines())

    def test_antigravity_accounts_are_separate(self) -> None:
        self.manifest("aggb2", "agoh2")
        self.assertEqual([
            "wave-usage: antigravity Gemini Models (agy2) · Weekly Limit Remaining 86% used, "
            "resets 2026-11-04 08:00 (aggb2, agoh2)",
        ], self.warnings())
        self.manifest("aggb")
        self.assertEqual([], self.warnings())
        self.assertEqual(["-a", "antigravity"], self.arguments.read_text().splitlines())

    def test_codex_accounts_and_each_window_are_separate(self) -> None:
        self.output.write_text(SAMPLE.replace("11% used", "99% used")
                               .replace("16% used", "81.5% used")
                               .replace("18% used", "90% used"), encoding="utf-8")
        self.manifest("cdm2", "cax2", "cam2", "cdx2", "clm2", "cah2", "ctx2", "ctxb2", "ctm2", "ctmb2",
                      "cdm", "caxX", "ctx", "ctxb", "ctm", "ctmb")
        self.assertEqual([
            "wave-usage: codex Codex (codex2) 81.5% used, "
            "resets 2026-10-24 23:06 (cdm2, cax2, cam2, cdx2, clm2, cah2, ctx2, ctxb2, ctm2, ctmb2)",
            "wave-usage: codex Codex (weekly) (codex2) 90% used, "
            "resets 2026-10-30 23:23 (cdm2, cax2, cam2, cdx2, clm2, cah2, ctx2, ctxb2, ctm2, ctmb2)",
            "wave-usage: codex Codex 99% used, resets 2026-10-30 14:47 "
            "(cdm, caxX, ctx, ctxb, ctm, ctmb)",
        ], self.warnings())
        self.assertEqual(["-a", "codex"], self.arguments.read_text().splitlines())

    def test_codex_api_key_routes_are_separate_from_subscription_quota(self) -> None:
        self.manifest("cdxk", "cdxk:cdx", "cdxk:cam", "cdm")
        self.output.write_text(SAMPLE.replace("11% used", "99% used"), encoding="utf-8")
        self.assertEqual([
            "wave-usage: codex (key) quota unknown (cdxk, cdxk:cdx, cdxk:cam)",
            "wave-usage: codex Codex 99% used, resets 2026-10-30 14:47 (cdm)",
        ], self.warnings())
        self.assertEqual(["-a", "codex"], self.arguments.read_text().splitlines())
        self.manifest("cdxk:cdx2", "cdxk:agg", "cdxk:arbitrary")
        self.assertEqual([
            "wave-usage: cdxk:cdx2 quota unknown (cdxk:cdx2)",
            "wave-usage: cdxk:agg quota unknown (cdxk:agg)",
            "wave-usage: cdxk:arbitrary quota unknown (cdxk:arbitrary)",
        ], self.warnings())

    def test_antigravity_api_key_routes_are_separate_from_subscription_quota(self) -> None:
        self.manifest("agk", "agk:agnh", "agk:agcm", "agnx")
        self.output.write_text(SAMPLE.replace("1.8% used, 98.2%", "85% used, 15%"), encoding="utf-8")
        self.assertEqual([
            "wave-usage: antigravity (key) quota unknown (agk, agk:agnh, agk:agcm)",
            "wave-usage: antigravity Gemini Models · Weekly Limit Remaining 85% used, "
            "resets 2026-10-31 10:23 (agnx)",
        ], self.warnings())
        self.assertEqual(["-a", "antigravity"], self.arguments.read_text().splitlines())
        self.manifest("agk:agnh2", "agk:agoh", "agk:arbitrary")
        self.assertEqual([
            "wave-usage: agk:agnh2 quota unknown (agk:agnh2)",
            "wave-usage: agk:agoh quota unknown (agk:agoh)",
            "wave-usage: agk:arbitrary quota unknown (agk:arbitrary)",
        ], self.warnings())

    def test_shared_harness_deduplicates_launchers_not_windows(self) -> None:
        self.manifest("dswe", "dargh", "dswe")
        self.output.write_text(SAMPLE.replace("0% used, 100%", "80.1% used, 19.9%"),
                               encoding="utf-8")
        self.assertEqual([
            "wave-usage: devin Pro Daily 80.1% used, resets 2026-10-25 01:00 (dswe, dargh)",
            "wave-usage: devin Pro Weekly 100% used, resets 2026-10-25 01:00 (dswe, dargh)",
        ], self.warnings())
        self.assertEqual(["-a", "devin"], self.arguments.read_text().splitlines())

    def test_missing_unparseable_and_wrong_account_sections_are_unknown(self) -> None:
        cases = [
            ("dargh", "", "devin"),
            ("dargh", "── Devin ───\n  unavailable (network error)\n", "devin"),
            ("dargh", "── Devin ───\n  Weekly: [bar] ?% used\n", "devin"),
            ("grok2", "── Grok ───\n  X Premium+: [bar] 2% used\n", "grok (grok2)"),
            ("cdm2", "── Codex ───\n  Codex: [bar] 2% used\n", "codex (codex2)"),
            ("cdm", "── Codex ───\n  Codex (codex2): [bar] 2% used\n", "codex"),
        ]
        for launcher, output, label in cases:
            with self.subTest(launcher=launcher, output=output):
                self.manifest(launcher)
                self.output.write_text(output, encoding="utf-8")
                self.assertEqual([f"wave-usage: {label} quota unknown ({launcher})"],
                                 self.warnings())

    def test_usage_failure_is_a_warning_even_with_partial_output(self) -> None:
        self.manifest("dswe", "cdm2", "cdm", "grok2")
        self.env["WAVE_USAGE_EXIT"] = "1"
        for output in ("", SAMPLE):
            with self.subTest(output=bool(output)):
                self.output.write_text(output, encoding="utf-8")
                self.assertEqual([
                    "wave-usage: devin quota unknown (dswe)",
                    "wave-usage: codex (codex2) quota unknown (cdm2)",
                    "wave-usage: codex quota unknown (cdm)",
                    "wave-usage: grok (grok2) quota unknown (grok2)",
                ], self.warnings())

    def test_missing_agents_file_is_unknown(self) -> None:
        self.manifest("dswe")
        self.env["BASH_AGENTS_FILE"] = str(self.root / "missing agents")
        self.assertEqual(["wave-usage: devin quota unknown (dswe)"], self.warnings())

    def test_safe_windows_are_silent_and_do_not_change_artifacts(self) -> None:
        self.manifest("cdm2", "grok", "agg")
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                  for path in self.root.iterdir()}
        self.assertEqual([], self.warnings())
        after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                 for path in self.root.iterdir() if path != self.arguments}
        self.assertEqual(before, after)

    def test_strict_threshold_and_decimal_percentages(self) -> None:
        self.manifest("agg")
        for percent in ("0", "1.8", "79.99", "80", "80.0", "80.01"):
            with self.subTest(percent=percent):
                self.output.write_text("── Antigravity ───\n"
                                       f"  Weekly: [bar] {percent}% used\n", encoding="utf-8")
                expected = ["wave-usage: antigravity Weekly 80.01% used (agg)"]
                self.assertEqual(expected if percent == "80.01" else [], self.warnings())

    def test_command_code_parenthesized_percent_and_native_id(self) -> None:
        self.manifest("cmg", "cmd:provider/model+1")
        self.assertEqual([], self.warnings())
        self.assertEqual(["-a", "cmd"], self.arguments.read_text().splitlines())
        self.output.write_text(SAMPLE.replace("used (6%)", "used (86%)"), encoding="utf-8")
        self.assertEqual([
            "wave-usage: cmd Monthly 86% used, renews in 20d 21h (cmg, cmd:provider/model+1)",
        ], self.warnings())

    def test_launcher_families(self) -> None:
        cases = [
            ("aggbs aggbbs agom agoh argm argh aghh aghhb aghx aghxb agcm agcmb agch agchb agnm agnmb agnh agnhb agnx agnxb", "Antigravity", "antigravity"),
            ("kimb kimbs", "Kimi", "kimi"),
            ("dglm dopmm doph dopx dopm", "Devin", "devin"),
            ("clm clmbe ctx ctxb ctm ctmb cdmbe cammb cdmM cdxX camM caxX", "Codex", "codex"),
            ("ocs ommp ocargh ochy ocq4h ocq4x", "OpenCode Go", "opencode"),
            ("cmds cmm26p cmqh cmqx cms cmhy cmdglyph cmdflint", "Command Code", "cmd"),
            ("csm csu csx cshh csmm csbm chm chbh ccx ccbfh ccmM ccxX", "Claude", "claude"),
        ]
        for launchers, section, harness in cases:
            with self.subTest(harness=harness):
                self.manifest(*launchers.split())
                self.output.write_text(f"── {section} ───\n  Weekly: [bar] 91% used\n",
                                       encoding="utf-8")
                self.assertEqual([f"wave-usage: {harness} Weekly 91% used "
                                  f"({', '.join(launchers.split())})"], self.warnings())
                self.assertEqual(["-a", harness], self.arguments.read_text().splitlines())

    def test_open_code_free_models_are_not_on_the_metered_go_quota(self) -> None:
        self.manifest("ocs", "ochy4flash", "pihy4flash", "ocmm26")
        self.output.write_text("── OpenCode Go ───\n  Weekly: [bar] 91% used\n", encoding="utf-8")
        self.assertEqual(["wave-usage: opencode Weekly 91% used (ocs)",
                          "wave-usage: opencode (free) quota unknown (ochy4flash, pihy4flash)",
                          "wave-usage: opencode (zen) quota unknown (ocmm26)"], self.warnings())
        # cck* runs on ANTHROPIC_API_KEY, outside the Claude OAuth subscription whose windows usage reports.
        self.manifest("ccx", "cckx", "cckbfh")
        self.output.write_text("── Claude ───\n  Weekly: [bar] 91% used\n", encoding="utf-8")
        self.assertEqual(["wave-usage: claude Weekly 91% used (ccx)",
                          "wave-usage: claude (key) quota unknown (cckx, cckbfh)"], self.warnings())

    def test_routes_come_from_the_sibling_table(self) -> None:
        alone = self.root / "alone"
        alone.mkdir()
        shutil.copy2(SCRIPT, alone / "wave-usage")
        self.manifest("dswe")
        result = subprocess.run([str(alone / "wave-usage"), self.wave.name], cwd=self.root, env=self.env,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("launcher-routes.tsv", result.stderr)
        self.assertEqual(1, len(result.stderr.splitlines()))

    def test_unknown_launchers_do_not_start_usage(self) -> None:
        self.manifest("mystery", "mystery", "codex")
        self.assertEqual(["wave-usage: mystery quota unknown (mystery)",
                          "wave-usage: codex quota unknown (codex)"], self.warnings())
        self.assertFalse(self.arguments.exists())

    def test_bad_manifests_exit_two_with_one_line_error_and_help_works(self) -> None:
        for manifest in ("", "COMMON:\nROLE: review\n", "  @@ launcher=dswe name=quoted\n"):
            with self.subTest(manifest=manifest):
                self.wave.write_text(manifest, encoding="utf-8")
                result = self.run_usage()
                self.assertEqual(2, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertEqual(1, len(result.stderr.splitlines()))
                self.assertTrue(result.stderr.startswith("wave-usage: "), result.stderr)
        self.wave.unlink()
        for path in (self.wave, self.root):
            result = subprocess.run([str(SCRIPT), str(path)], cwd=self.root, env=self.env,
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(2, result.returncode)
            self.assertEqual("", result.stdout)
            self.assertEqual(1, len(result.stderr.splitlines()))
        result = self.run_usage("--help")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("usage: wave-usage", result.stdout)
        self.assertEqual("", result.stderr)
        self.assertFalse(self.arguments.exists())


if __name__ == "__main__":
    unittest.main()
