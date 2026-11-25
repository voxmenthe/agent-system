from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "delegate"
RUNNER = SKILL_ROOT / "scripts" / "run-worker.sh"


class DelegateSkillTests(unittest.TestCase):
    def test_skill_is_explicit_only_and_preserves_parent_accountability(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text()
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text()
        record = json.loads((ROOT / "registry.json").read_text())["skills"][
            "delegate"
        ]

        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertRegex(content, r"(?i)never self-invoke")
        for launcher in ("ocsf", "cmm31", "ommm31z", "ommm31g"):
            self.assertNotIn(f"`{launcher}`", content)
        self.assertIn("Kimi Code — K3.1 Pro", content)
        self.assertRegex(content, r"(?i)user.*proportions")
        for launcher in ("agg", "aggb", "clm", "clmb", "cdx", "cdxb", "cdm", "cdmb", "ocs", "ommp"):
            self.assertIn(f"`{launcher}`", content)
        default_routes = content.split("### Explicit-user routes", 1)[0]
        sol_routes = [
            line for line in default_routes.splitlines()
            if line.startswith("| Codex") and " Sol " in line
        ]
        self.assertEqual(1, len(sol_routes))
        self.assertIn("GPT-6.1 Sol", sol_routes[0])
        self.assertIn("`cdx`", sol_routes[0])
        self.assertIn("`cdxb`", sol_routes[0])
        self.assertRegex(content, r"(?i)one active writer per owned file")
        self.assertRegex(content, r"(?i)verify independently")
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual("external-write", record["effect_ceiling"])
        self.assertEqual("skills/delegate", record["source"])

    def test_requested_routes_are_not_skill_selected_defaults(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text()
        defaults, explicit = content.split("### Explicit-user routes", 1)
        explicit = explicit.split("## Establish ownership", 1)[0]
        for launcher in (
            "ctx", "ctxb", "ctx2", "ctxb2", "ctm", "ctmb", "ctm2", "ctmb2",
            "argm", "agoh", "aghh", "aghhb", "aghx", "aghxb",
            "agcm", "agcmb", "agch", "agchb",
            "agnm", "agnmb", "agnh", "agnhb", "agnx", "agnxb",
            "argm2", "agoh2", "aghh2", "aghhb2", "aghx2", "aghxb2",
            "agcm2", "agcmb2", "agch2", "agchb2",
            "agnm2", "agnmb2", "agnh2", "agnhb2", "agnx2", "agnxb2",
            "clm2", "clmb2", "cdx2", "cdxb2", "cdm", "cdmb", "cdm2", "cdmb2",
            "cam2", "camb2", "cax2", "caxb2", "camm2", "cammb2",
            "cah", "cahb", "cah2", "cahb2", "ccm", "ccbm", "ccfx", "ccbfx",
            "ccmM", "ccxX", "cdmM", "cdxX", "camM", "caxX",
            "cdmM2", "cdxX2", "camM2", "caxX2",
            "cck", "cckm", "ccku", "cckx", "cckh", "cckmm",
            "cckbm", "cckbu", "cckbx", "cckbh", "cckbmm",
            "cckfm", "cckfu", "cckfx", "cckfh", "cckfmm",
            "cckbfm", "cckbfu", "cckbfx", "cckbfh", "cckbfmm",
            "ommp", "ocargh", "cmg", "cmds",
            "cmm26p", "cms", "ocmm26",
            "ochy4flash", "oclongcat", "ociceman",
            "cmdglyph", "cmdflint",
            "pihy4flash", "pilongcat", "piiceman",
        ):
            with self.subTest(launcher=launcher):
                self.assertIn(f"`{launcher}`", explicit)
                self.assertNotIn(f"`{launcher}`", defaults)

    def test_wave_reference_and_runner_project_with_existing_skill(self) -> None:
        # Keep this test runnable by the plan's repository-root command.
        sys.path.insert(0, str(ROOT))
        try:
            from skill_system import SkillSystem
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            applied = system.install("delegate", apply=True)
            self.assertTrue(applied.applied, applied)
            installed = home / ".agents/skills/delegate"
            skill = (installed / "SKILL.md").read_text()
            links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", skill)
            self.assertIn("references/wave-runner.md", links)
            for relative in ("references/wave-runner.md", "scripts/run-wave.sh"):
                source = SKILL_ROOT / relative
                target = installed / relative
                self.assertEqual(source.read_bytes(), target.read_bytes())
                self.assertEqual(source.stat().st_mode, target.stat().st_mode)
            self.assertEqual("current", system.status().skills["delegate"].state)

    def test_runner_normalizes_structured_and_final_only_launchers(self) -> None:
        fake_launchers = r'''agg() {
  printf 'ANTIGRAVITY:%s\n' "$2"
}
kimb() {
  printf '%s\n' \
    '{"role":"meta","type":"system.version","version":"test"}' \
    '{"role":"assistant","tool_calls":[{"type":"function"}]}' \
    '{"role":"tool","content":"tool trace"}' \
    '{"role":"assistant","content":"KIMI_FINAL"}' \
    '{"role":"meta","type":"session.resume_hint","content":"resume trace"}'
}
grokxh() {
  printf '%s\n' '{"text":"GROK_FINAL","thought":"PRIVATE_REASONING"}'
}
grok2xh() {
  printf '%s\n' '{"text":"GROK2_FINAL","thought":"PRIVATE_REASONING"}'
}
grok3xh() {
  printf '%s\n' '{"text":"GROK3_FINAL","thought":"PRIVATE_REASONING"}'
}
clme() {
  printf 'LUNA_SCOPED:%s\n' "$1"
}
clmbe() {
  printf 'LUNA_BARE:%s\n' "$1"
}
cdxe() {
  printf 'CODEX_SCOPED:%s\n' "$1"
}
cdxbe() {
  printf 'CODEX_BARE:%s\n' "$1"
}
cdme() {
  printf 'CODEX_MAX_SCOPED:%s\n' "$1"
}
cdmbe() {
  printf 'CODEX_MAX_BARE:%s\n' "$1"
}
cam() {
  [[ $# -eq 2 && "$1" == '-p' ]] || return 2
  printf 'ASTRA_MAX_SCOPED:%s\n' "$2"
}
camb() {
  [[ $# -eq 2 && "$1" == '-p' ]] || return 2
  printf 'ASTRA_MAX_BARE:%s\n' "$2"
}
ocs() {
  printf '%s\n' \
    '{"type":"step_start","part":{"type":"step-start"}}' \
    '{"type":"text","part":{"messageID":"m1","text":"intermediate commentary"}}' \
    '{"type":"tool_use","part":{"tool":"bash"}}' \
    '{"type":"step_finish","part":{"type":"step-finish","reason":"tool-calls"}}' \
    '{"type":"step_start","part":{"type":"step-start"}}' \
    '{"type":"text","part":{"messageID":"m2","text":"OPENCODE_FINAL"}}' \
    '{"type":"step_finish","part":{"type":"step-finish","reason":"stop"}}'
}
ommp() {
  printf '%s\n' \
    '{"type":"step_start","part":{"type":"step-start"}}' \
    '{"type":"text","part":{"messageID":"m1","text":"intermediate commentary"}}' \
    '{"type":"step_finish","part":{"type":"step-finish","reason":"tool-calls"}}' \
    '{"type":"step_start","part":{"type":"step-start"}}' \
    '{"type":"text","part":{"messageID":"m2","text":"OPENCODE_MIMO_FINAL"}}' \
    '{"type":"step_finish","part":{"type":"step-finish","reason":"stop"}}'
}
'''

        with tempfile.TemporaryDirectory() as temporary:
            launchers = Path(temporary) / ".bash_agents"
            launchers.write_text(fake_launchers)
            # Outside any agent session, so the runner adds no hist-parent line (test_hist_parent covers it).
            environment = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
            environment["BASH_AGENTS_FILE"] = str(launchers)
            # A signed-out second Antigravity account, so agg needs no /usage reading (test_agy_account covers it).
            environment["AGY2_HOME"] = temporary

            expected = {
                "agg": "ANTIGRAVITY:bounded task\n",
                "kimb": "KIMI_FINAL\n",
                "grokxh": "GROK_FINAL\n",
                "grok2xh": "GROK2_FINAL\n",
                "grok3xh": "GROK3_FINAL\n",
                "clm": "LUNA_SCOPED:bounded task\n",
                "clmb": "LUNA_BARE:bounded task\n",
                "cdx": "CODEX_SCOPED:bounded task\n",
                "cdxb": "CODEX_BARE:bounded task\n",
                "cdm": "CODEX_MAX_SCOPED:bounded task\n",
                "cdmb": "CODEX_MAX_BARE:bounded task\n",
                "cam": "ASTRA_MAX_SCOPED:bounded task\n",
                "camb": "ASTRA_MAX_BARE:bounded task\n",
                "ocs": "OPENCODE_FINAL\n",
                "ommp": "OPENCODE_MIMO_FINAL\n",
            }
            for launcher, output in expected.items():
                with self.subTest(launcher=launcher):
                    result = subprocess.run(
                        ["bash", str(RUNNER), launcher],
                        input="bounded task",
                        text=True,
                        capture_output=True,
                        cwd=ROOT,
                        env=environment,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(output, result.stdout)
                    self.assertNotIn("PRIVATE_REASONING", result.stdout)
                    self.assertNotIn("resume trace", result.stdout)

    def test_runner_supports_codex_api_key_prefixes(self) -> None:
        fake_launchers = r'''cdxk() {
  printf 'API'
  printf ' <%s>' "$@"
  printf '\n'
}
cdxe() { :; }
cdxbe() { :; }
cdme() { :; }
clme() { :; }
cam() { :; }
caxX() { :; }
cdmM() { :; }
cdu() { :; }
cdx-fresh() { :; }
cdxe-fresh() { :; }
cdube() { :; }
'''
        cases = (
            (("cdxk",), "API <cdxe> <bounded task>\n"),
            (("cdxk", "cdx"), "API <cdxe> <bounded task>\n"),
            (("cdxk:cdx",), "API <cdxe> <bounded task>\n"),
            (("cdxk:cdxb",), "API <cdxbe> <bounded task>\n"),
            (("cdxk", "cdm"), "API <cdme> <bounded task>\n"),
            (("cdxk:clm",), "API <clme> <bounded task>\n"),
            (("cdxk:cam",), "API <cam> <-p> <bounded task>\n"),
            (("cdxk:caxX",), "API <caxX> <-p> <bounded task>\n"),
            (("cdxk:cdmM",), "API <cdmM> <-p> <bounded task>\n"),
            (("cdxk:cdxe",), "API <cdxe> <bounded task>\n"),
            (("cdxk:cdu",), "API <cdu> <-p> <bounded task>\n"),
            (("cdxk:cdx-fresh",), "API <cdx-fresh> <-p> <bounded task>\n"),
            (("cdxk:cdxe-fresh",), "API <cdxe-fresh> <bounded task>\n"),
            (("cdxk:cdube",), "API <cdube> <bounded task>\n"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            launchers = Path(temporary) / ".bash_agents"
            launchers.write_text(fake_launchers)
            environment = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
            environment["BASH_AGENTS_FILE"] = str(launchers)
            for arguments, output in cases:
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        ["bash", str(RUNNER), *arguments],
                        input="bounded task",
                        text=True,
                        capture_output=True,
                        cwd=ROOT,
                        env=environment,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(output, result.stdout)

    def test_runner_rejects_invalid_codex_api_key_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            launchers = Path(temporary) / ".bash_agents"
            launchers.write_text("cdxk() { printf should-not-run; }\nagg() { printf should-not-run; }\n")
            environment = os.environ.copy()
            environment["BASH_AGENTS_FILE"] = str(launchers)
            for arguments in (("cdxk", "cdx2"), ("cdxk:cdx2",), ("cdxk:agg",), ("cdxk:cckx",), ("cdxk:arbitrary",)):
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        ["bash", str(RUNNER), *arguments],
                        input="bounded task",
                        text=True,
                        capture_output=True,
                        cwd=ROOT,
                        env=environment,
                        check=False,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("unsupported cdxk target", result.stderr)
                    self.assertNotIn("should-not-run", result.stdout)

    def test_runner_supports_antigravity_api_key_prefixes(self) -> None:
        fake_launchers = r'''agk() {
  printf 'AGK'
  printf ' <%s>' "$@"
  printf '\n'
}
aghh() { :; }
agcm() { :; }
agchb() { :; }
agnm() { :; }
agnh() { :; }
agnxb() { :; }
argm() { :; }
'''
        cases = (
            (("agk",), "AGK <aghh> <-p> <bounded task>\n"),
            (("agk", "agcm"), "AGK <agcm> <-p> <bounded task>\n"),
            (("agk:agchb",), "AGK <agchb> <-p> <bounded task>\n"),
            (("agk", "agnm"), "AGK <agnm> <-p> <bounded task>\n"),
            (("agk:agnh",), "AGK <agnh> <-p> <bounded task>\n"),
            (("agk:agnxb",), "AGK <agnxb> <-p> <bounded task>\n"),
            (("agk:argm",), "AGK <argm> <-p> <bounded task>\n"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            launchers = Path(temporary) / ".bash_agents"
            launchers.write_text(fake_launchers)
            environment = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
            environment["BASH_AGENTS_FILE"] = str(launchers)
            for arguments, output in cases:
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        ["bash", str(RUNNER), *arguments],
                        input="bounded task",
                        text=True,
                        capture_output=True,
                        cwd=ROOT,
                        env=environment,
                        check=False,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(output, result.stdout)

    def test_runner_rejects_invalid_antigravity_api_key_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            launchers = Path(temporary) / ".bash_agents"
            launchers.write_text("agk() { printf should-not-run; }\nagoh() { printf should-not-run; }\n")
            environment = os.environ.copy()
            environment["BASH_AGENTS_FILE"] = str(launchers)
            for arguments in (("agk", "agnh2"), ("agk:agnh2",), ("agk:agom",), ("agk:agoh",), ("agk:cdx",), ("agk:arbitrary",)):
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        ["bash", str(RUNNER), *arguments],
                        input="bounded task",
                        text=True,
                        capture_output=True,
                        cwd=ROOT,
                        env=environment,
                        check=False,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("unsupported agk target", result.stderr)
                    self.assertNotIn("should-not-run", result.stdout)

    def test_runner_rejects_unlisted_shell_functions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            launchers = Path(temporary) / ".bash_agents"
            launchers.write_text("arbitrary() { printf unsafe; }\n")
            environment = os.environ.copy()
            environment["BASH_AGENTS_FILE"] = str(launchers)

            result = subprocess.run(
                ["bash", str(RUNNER), "arbitrary"],
                input="bounded task",
                text=True,
                capture_output=True,
                cwd=ROOT,
                env=environment,
                check=False,
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unsupported launcher", result.stderr)


if __name__ == "__main__":
    unittest.main()
