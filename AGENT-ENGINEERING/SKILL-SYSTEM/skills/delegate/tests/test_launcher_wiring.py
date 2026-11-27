"""Static wiring invariants across launcher-routes.tsv, run-worker.sh, run-wave.sh, and pick-launcher."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
RUN_WORKER = SCRIPTS / "run-worker.sh"
RUN_WAVE = SCRIPTS / "run-wave.sh"
ROUTES = SCRIPTS / "launcher-routes.tsv"
PICK_LAUNCHER = SCRIPTS / "pick-launcher"

OPENCODE_PAID = ("ochy", "ocq4h", "ocq4x")
COMMAND_PAID = ("cmqh", "cmqx", "cmhy")
MARKET_LAUNCHERS = (
    *OPENCODE_PAID,
    *COMMAND_PAID,
    "aghh", "aghh2", "agnh", "agnh2", "aghx", "agnx", "aggb",
    "dswe", "cmds", "kimm", "cdx", "cdm",
    "ochy4flash", "cmdglyph", "oclongcat", "ociceman",
)


def parse_routes() -> dict[str, tuple[str, str]]:
    """launcher -> (harness, account) from launcher-routes.tsv."""
    mapping: dict[str, tuple[str, str]] = {}
    for line in ROUTES.read_text(encoding="utf-8").splitlines()[1:]:
        harness, account, launchers = line.split("\t")
        for launcher in launchers.split():
            mapping[launcher] = (harness, account)
    return mapping


def parse_run_worker_modes() -> dict[str, str]:
    """launcher -> output mode from run-worker.sh's main case statement."""
    text = RUN_WORKER.read_text(encoding="utf-8")
    match = re.search(
        r'\nresolved_launcher="\$launcher"\ncase "\$launcher" in\n(.*?)\nesac\n',
        text,
        re.DOTALL,
    )
    if not match:
        raise AssertionError("could not locate main case \"$launcher\" block in run-worker.sh")
    body = match.group(1)
    modes: dict[str, str] = {}
    for branch in re.split(r"\n\s*;;\s*\n", body):
        branch = branch.strip()
        if not branch:
            continue
        header_match = re.match(r"^([^\n]+)\)\s*\n(.*)$", branch, re.DOTALL)
        if not header_match:
            continue
        patterns, statements = header_match.group(1), header_match.group(2)
        if patterns.strip() in ("*", "cmd:?*"):
            continue
        mode_match = re.search(r'mode="([^"]+)"', statements)
        if not mode_match:
            continue
        mode = mode_match.group(1)
        for token in patterns.split("|"):
            name = token.strip()
            if name:
                modes[name] = mode
    return modes


def parse_run_wave_allowlist() -> set[str]:
    """Plain launcher allowlist from run-wave.sh's manifest parser."""
    text = RUN_WAVE.read_text(encoding="utf-8")
    match = re.search(
        r"case \$launcher in\n\s*cdxk\|cdxk:\*\|agk\|agk:\*\) ;;\n\s*([^\n]+)\) ;;",
        text,
    )
    if not match:
        raise AssertionError("could not locate launcher allowlist in run-wave.sh")
    return {token.strip() for token in match.group(1).split("|") if token.strip()}


def parse_api_prefix_targets(prefix: str) -> set[str]:
    """Supported <prefix>:<target> targets from run-worker.sh."""
    text = RUN_WORKER.read_text(encoding="utf-8")
    match = re.search(
        rf'case "\$\{{requested_launcher#{prefix}:\}}" in\n\s*([^\n]+)\) ;;',
        text,
    )
    if not match:
        raise AssertionError(f"could not locate {prefix} target allowlist in run-worker.sh")
    return {f"{prefix}:{token.strip()}" for token in match.group(1).split("|") if token.strip()}


def load_pick_launcher():
    loader = SourceFileLoader("pick_launcher_wiring_test", str(PICK_LAUNCHER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


class LauncherWiringTests(unittest.TestCase):
    def test_routes_table_matches_run_worker_usage_and_run_wave(self) -> None:
        routes = parse_routes()
        modes = parse_run_worker_modes()
        wave_allowlist = parse_run_wave_allowlist()

        plain_routes = {
            name for name in routes
            if ":" not in name and name not in ("cdxk", "agk")
        }
        self.assertEqual(
            plain_routes,
            set(modes),
            "launcher-routes.tsv and run-worker.sh output-mode branches drifted",
        )
        self.assertEqual(
            plain_routes,
            wave_allowlist,
            "launcher-routes.tsv and run-wave.sh allowlist drifted",
        )

        # Compound API-key routes stay in sync with run-worker.sh target allowlists.
        route_cdxk = {name for name in routes if name.startswith("cdxk:")}
        route_agk = {name for name in routes if name.startswith("agk:")}
        self.assertEqual(route_cdxk, parse_api_prefix_targets("cdxk"))
        self.assertEqual(route_agk, parse_api_prefix_targets("agk"))

        usage = subprocess.run(
            ["/bin/bash", str(RUN_WORKER), "--help"],
            capture_output=True, text=True, check=True,
        ).stdout
        usage_tokens = set(re.findall(r"\b[A-Za-z][A-Za-z0-9]*\b", usage))
        missing_from_usage = sorted(plain_routes - usage_tokens)
        self.assertEqual([], missing_from_usage, f"missing from run-worker.sh usage: {missing_from_usage}")

    def test_market_referenced_launchers_have_expected_modes_and_routes(self) -> None:
        routes = parse_routes()
        modes = parse_run_worker_modes()
        wave_allowlist = parse_run_wave_allowlist()

        for launcher in OPENCODE_PAID:
            with self.subTest(launcher=launcher):
                self.assertEqual("opencode-json", modes.get(launcher))
                self.assertEqual(("opencode", "go"), routes.get(launcher))
                self.assertIn(launcher, wave_allowlist)

        for launcher in COMMAND_PAID:
            with self.subTest(launcher=launcher):
                self.assertEqual("command-json", modes.get(launcher))
                self.assertEqual(("cmd", "-"), routes.get(launcher))
                self.assertIn(launcher, wave_allowlist)

        for launcher in MARKET_LAUNCHERS:
            with self.subTest(launcher=launcher):
                self.assertIn(launcher, routes)
                self.assertIn(launcher, modes)
                self.assertIn(launcher, wave_allowlist)

    def test_market_launchers_resolve_in_pick_launcher(self) -> None:
        repo_agents = SKILL.parents[3] / "SHELL/.bash_agents" if len(SKILL.parents) > 3 else Path("/nonexistent")
        agents_file = Path(os.environ.get("BASH_AGENTS_FILE", str(repo_agents if repo_agents.is_file() else Path.home() / ".bash_agents")))
        if not agents_file.is_file():
            self.skipTest(f"no shell definitions at {agents_file}")
        module = load_pick_launcher()
        self.addCleanup(sys.modules.pop, module.__name__, None)
        declared = subprocess.run(
            ["bash", "--noprofile", "--norc", "-c", 'source "$1" >/dev/null 2>&1; declare -f',
             "wiring-test", str(agents_file)],
            capture_output=True, text=True, check=True,
        ).stdout
        definitions = module.parse_definitions(declared)
        routes = parse_routes()
        for launcher in MARKET_LAUNCHERS:
            if routes.get(launcher, ("", ""))[0] == "kimi":
                continue
            with self.subTest(launcher=launcher):
                pool = module.resolve(launcher, definitions)
                self.assertEqual(routes[launcher][0], pool.harness)

    def test_paid_opencode_and_command_launchers_extract_final_output(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
        oc_json = "\n".join(json.dumps(row) for row in (
            {"type": "text", "part": {"messageID": "m1", "text": "INTERMEDIATE"}},
            {"type": "step_finish", "part": {"messageID": "m1", "reason": "tool-calls"}},
            {"type": "text", "part": {"messageID": "m2", "text": "FINAL_OC"}},
            {"type": "step_finish", "part": {"messageID": "m2", "reason": "stop"}},
        ))
        cmd_json = "\n".join(json.dumps(row) for row in (
            {"type": "event", "event": {"type": "text_delta", "text": "INTERMEDIATE"}},
            {"type": "result", "subtype": "success", "finalText": "FINAL_CMD"},
        ))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrappers = root / "wrappers.sh"
            lines = []
            for launcher in OPENCODE_PAID:
                lines.append(
                    f'{launcher}() {{ [[ "$1" == "run" && "$2" == "--format" && "$3" == "json" ]] || return 9; '
                    f"printf '%s\\n' '{oc_json}'; }}"
                )
            for launcher in COMMAND_PAID:
                lines.append(
                    f'{launcher}() {{ [[ "$1" == "--no-auto-update" && "$2" == "--output-format" && "$3" == "json" && "$4" == "-p" ]] || return 9; '
                    f"printf '%s\\n' '{cmd_json}'; }}"
                )
            wrappers.write_text("\n".join(lines) + "\n", encoding="utf-8")
            run_env = dict(env, BASH_AGENTS_FILE=str(wrappers))
            for launcher, expected in [*( (n, "FINAL_OC\n") for n in OPENCODE_PAID ), *( (n, "FINAL_CMD\n") for n in COMMAND_PAID )]:
                with self.subTest(launcher=launcher):
                    result = subprocess.run(
                        ["/bin/bash", str(RUN_WORKER), launcher],
                        input="PING", text=True, capture_output=True, env=run_env,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(expected, result.stdout)


if __name__ == "__main__":
    unittest.main()
