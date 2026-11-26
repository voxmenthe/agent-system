import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WRAPPERS = Path(__file__).resolve().parents[1] / ".bash_agents"
BASH = shutil.which("bash")
RETIRED_MODEL_WRAPPERS = (
    "ocsf", "cmsb", "cmfg", "oc", "ocu", "ocsb", "ocex", "ocfa", "ocli", "ocsbf", "oclf",
    "cmm31", "ommm31z", "ommm31g", "cmq",
    "pg", "pd", "pq", "pk",
)

PROVIDERS = (
    "Claude:",
    "Grok:",
    "Antigravity:",
    "Codex:",
    "Kimi:",
    "Devin:",
    "Command Code:",
    "OpenCode:",
    "Pi:",
)


class AgentsTests(unittest.TestCase):
    def run_agents(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                BASH,
                "--noprofile",
                "--norc",
                "-c",
                'source "$1"; shift; agents "$@"',
                "agents-test",
                str(WRAPPERS),
                *args,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=20,
            env=dict(os.environ),
        )

    def test_full_listing_covers_every_provider(self) -> None:
        process = self.run_agents()
        self.assertEqual(0, process.returncode, process.stderr.decode())
        text = process.stdout.decode()
        for provider in PROVIDERS:
            self.assertIn(provider, text)
        # Spot-check one row per provider, including the newest wrapper.
        for row in (
            "ccbfmm", "ccxX", "ccmM", "grok2xh", "grok3xh", "aggbtp", "cdxr", "cdxk", "ctx", "ctm",
            "caxX", "camM", "caxX2", "camM2",
            "cdxX", "cdmM", "cdxX2", "cdmM2", "kimbs",
            "aghh", "aghhb", "aghx", "aghxb", "agcm", "agcmb", "agch", "agchb",
            "agnm", "agnmb", "agnh", "agnhb", "agnx", "agnxb", "agk",
            "dfusx", "dsweo", "cmm26p", "ocargh", "ochy", "ocbp", "pqx",
            "ocs62x", "ocopmm", "ocnx", "occh", "dnx",
            "cmdglyph", "cmdflint", "ochy4flash", "oclongcat", "ociceman",
            "pihy4flash", "pilongcat", "piiceman",
        ):
            self.assertIn(row, text)
        for base, effort in (("ctx", "xhigh"), ("ctm", "max")):
            for suffix, mode in (("", "scoped home"), ("b", "bare home"),
                                 ("2", "secondary scoped home"), ("b2", "secondary bare home")):
                self.assertRegex(
                    text, rf"(?m)^  {base}{suffix}\s+gpt-6\.1-terra\s+{effort}\s+{mode}$")
        self.assertRegex(
            text, r"(?m)^  pqx\s+opencode-go/qwen4-max\s+xhigh\s+no prompts by design$"
        )
        for wrapper, model, effort in (
            ("pihy4flash", r"opencode-go/hy4-flash-free", "high"),
            ("pilongcat", r"opencode-go/longcat-2\.5-free", "-"),
            ("piiceman", r"opencode-go/iceman-contributor-free", "-"),
        ):
            self.assertRegex(
                text, rf"(?m)^  {wrapper}\s+{model}\s+{effort}\s+no prompts by design$"
            )
        self.assertRegex(
            text, r"(?m)^  dnh\s+gemini-4-neon-high\s+high in id\s+bypass permissions$"
        )
        self.assertRegex(
            text, r"(?m)^  dswe\s+swe-2-1-max\s+-\s+bypass permissions$"
        )
        self.assertRegex(
            text, r"(?m)^  dsweo\s+swe-2-max\s+-\s+bypass permissions$"
        )
        # Key-auth Claude wrappers track the opus/fable aliases, never pins.
        self.assertNotIn("claude-opus-4-8", text)
        self.assertNotIn("|claude-fable-5|", text)
        self.assertEqual(b"", process.stderr)
        self.assertEqual(list(PROVIDERS), [line for line in text.splitlines()
                                          if line.endswith(":")])

    def test_filter_opencode(self) -> None:
        process = self.run_agents("--opencode")
        self.assertEqual(0, process.returncode, process.stderr.decode())
        text = process.stdout.decode()
        self.assertIn("OpenCode:", text)
        listed = set(re.findall(r"^  ([a-zA-Z0-9_-]+) {2,}\S+", text, re.M)) - {"WRAPPER"}
        self.assertEqual(
            {"ocs", "ocargh", "ocnm", "ocnh", "ochy", "ocq4h", "ocq4x", "ocmm26", "oclc", "ocmf",
             "ocnu", "ocbp", "ommp", "ocs62x", "ocs62mm", "oca62m", "oca62h", "oca62x", "oca62mm",
             "ocopm", "ocoph", "ocopx", "ocopmm", "ochl", "ochm", "ochh", "ochx", "ocnl", "ocnx",
             "occl", "occm", "occh", "ochy4flash", "oclongcat", "ociceman"}, listed)
        self.assertRegex(text, r"ocmm26\s+opencode/mimo-v2\.6-flash-free\s+-\s+auto-approve")
        self.assertRegex(text, r"ocargh\s+opencode-go/gemini-4-argon\s+high\s+auto-approve")
        self.assertRegex(text, r"ocnm\s+google/gemini-4-neon\s+medium\s+auto-approve")
        self.assertRegex(text, r"ocnh\s+google/gemini-4-neon\s+high\s+auto-approve")
        self.assertRegex(text, r"ochy\s+opencode-go/hy4\s+high\s+auto-approve")
        self.assertRegex(text, r"ocq4h\s+opencode-go/qwen4-max\s+high\s+auto-approve")
        self.assertRegex(text, r"ocq4x\s+opencode-go/qwen4-max\s+xhigh\s+auto-approve")
        self.assertRegex(text, r"ochy4flash\s+opencode-go/hy4-flash-free\s+high\s+auto-approve")
        self.assertRegex(text, r"oclongcat\s+opencode-go/longcat-2\.5-free\s+-\s+auto-approve")
        self.assertRegex(text, r"ociceman\s+opencode-go/iceman-contributor-free\s+-\s+auto-approve")
        self.assertRegex(text, r"ocs62mm\s+openai/gpt-6\.2-sol\s+max\s+auto-approve")
        self.assertRegex(text, r"oca62x\s+openai/gpt-6\.2-astra\s+xhigh\s+auto-approve")
        self.assertRegex(text, r"ocopmm\s+anthropic/claude-opus-5-5\s+max\s+auto-approve")
        self.assertRegex(text, r"ochl\s+google/gemini-4-hydrogen\s+low\s+auto-approve")
        self.assertRegex(text, r"ocnl\s+google/gemini-4-neon\s+low\s+auto-approve")
        self.assertRegex(text, r"ocnx\s+google/gemini-4-neon\s+xhigh\s+auto-approve")
        self.assertRegex(text, r"occh\s+google/gemini-4-carbon\s+high\s+auto-approve")
        self.assertNotIn("nemotron-3.5-lightning", text)
        self.assertNotIn("occx", text)
        self.assertNotIn("Codex:", text)
        self.assertNotIn("  cdx ", text)

    def test_removed_provider_flag_fails(self) -> None:
        process = self.run_agents("--mimo")
        self.assertEqual(1, process.returncode)
        self.assertIn("unrecognized option", process.stderr.decode())
        self.assertEqual(b"", process.stdout)

    def test_removed_wrappers_are_not_defined(self) -> None:
        process = subprocess.run(
            [BASH, "--noprofile", "--norc", "-c",
             'source "$1"; shift; declare -F "$@"',
             "agents-test", str(WRAPPERS),
             "mmp", "mmf", "agc", "agcbs", "agctp", "agcb", "agcbbs", "agcbtp",
             *RETIRED_MODEL_WRAPPERS],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
            env=dict(os.environ),
        )
        self.assertEqual(1, process.returncode)
        self.assertEqual(b"", process.stdout)
        self.assertEqual(b"", process.stderr)

    def test_filter_union(self) -> None:
        process = self.run_agents("--codex", "--opencode")
        self.assertEqual(0, process.returncode, process.stderr.decode())
        text = process.stdout.decode()
        self.assertIn("Codex:", text)
        self.assertIn("OpenCode:", text)
        self.assertNotIn("Claude:", text)
        self.assertNotIn("  ccm ", text)

    def test_alias_flags(self) -> None:
        for flag, title in (("--agy", "Antigravity:"), ("--oc", "OpenCode:"),
                            ("--command-code", "Command Code:")):
            with self.subTest(flag=flag):
                process = self.run_agents(flag)
                self.assertEqual(0, process.returncode, process.stderr.decode())
                self.assertIn(title, process.stdout.decode())

    def test_every_antigravity_wrapper_has_a_second_account_twin(self) -> None:
        process = self.run_agents("--agy")
        self.assertEqual(0, process.returncode, process.stderr.decode())
        text = process.stdout.decode()
        self.assertIn("`2`-suffixed twin on the second account (~/.agy2)", text)
        listed = set(re.findall(r"^  ([a-z0-9]+) {2,}\S+", text, re.M)) - {"WRAPPER"}
        self.assertIn("aggbtp", listed)
        self.assertIn("agk", listed)
        definitions = subprocess.run(
            [BASH, "--noprofile", "--norc", "-c", 'source "$1"; declare -F', "twin-test", str(WRAPPERS)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
        )
        defined = {line.split()[-1] for line in definitions.stdout.splitlines()}
        self.assertIn("agk", defined)
        self.assertEqual(set(), {name + "2" for name in (listed - {"agk"})} - defined)

    def test_hydrogen_wrappers_pin_model_and_bare_agent(self) -> None:
        import json
        import os
        import tempfile
        from pathlib import Path

        cases = (
            ("aghh", "gemini-4-hydrogen-high", False),
            ("aghhb", "gemini-4-hydrogen-high", True),
            ("aghx", "gemini-4-hydrogen-xhigh", False),
            ("aghxb", "gemini-4-hydrogen-xhigh", True),
            ("agcm", "gemini-4-carbon-medium", False),
            ("agcmb", "gemini-4-carbon-medium", True),
            ("agch", "gemini-4-carbon-high", False),
            ("agchb", "gemini-4-carbon-high", True),
            ("agnm", "gemini-4-neon-medium", False),
            ("agnmb", "gemini-4-neon-medium", True),
            ("agnh", "gemini-4-neon-high", False),
            ("agnhb", "gemini-4-neon-high", True),
            ("agnx", "gemini-4-neon-xhigh", False),
            ("agnxb", "gemini-4-neon-xhigh", True),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_dir = root / ".agents/skills/delegate/scripts"
            scripts_dir.mkdir(parents=True)
            real_filter = (
                WRAPPERS.resolve().parent.parent
                / "AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/agy-final-output.py"
            )
            (scripts_dir / "agy-final-output.py").symlink_to(real_filter)
            stub = root / "agy"
            args_file = root / "args.json"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib, sys\n"
                "pathlib.Path(os.environ['ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n"
            )
            stub.chmod(0o755)
            env = dict(os.environ, HOME=str(root), STUB_AGY=str(stub), ARGS_FILE=str(args_file))
            for wrapper, model, bare in cases:
                with self.subTest(wrapper=wrapper):
                    if args_file.exists():
                        args_file.unlink()
                    res = subprocess.run(
                        [
                            BASH,
                            "--noprofile",
                            "--norc",
                            "-c",
                            'source "$1"; _agy_bin() { printf "%s\\n" "$STUB_AGY"; }; '
                            '_agy_trust_workspace() { :; }; shift; "$@" "hello"',
                            "hydrogen-test",
                            str(WRAPPERS),
                            wrapper,
                        ],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=20,
                        env=env,
                    )
                    self.assertEqual(0, res.returncode, res.stderr)
                    argv = json.loads(args_file.read_text())
                    model_idx = argv.index("--model")
                    self.assertEqual(model, argv[model_idx + 1])
                    self.assertNotIn("--effort", argv)
                    if bare:
                        agent_idx = argv.index("--agent")
                        self.assertEqual("agy-bare", argv[agent_idx + 1])
                    else:
                        self.assertNotIn("--agent", argv)

    def test_swe_wrappers_pin_current_and_legacy_devin_models(self) -> None:
        cases = (
            ("dswe", "swe-2-1-max"),
            ("dsweo", "swe-2-max"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            args_file = root / "args.json"
            stub = bin_dir / "devin"
            stub.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, sys\n"
                "pathlib.Path(os.environ['ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n"
            )
            stub.chmod(0o755)
            env = dict(
                os.environ,
                PATH=f"{bin_dir}:{os.environ['PATH']}",
                ARGS_FILE=str(args_file),
            )
            for wrapper, model in cases:
                with self.subTest(wrapper=wrapper):
                    if args_file.exists():
                        args_file.unlink()
                    res = subprocess.run(
                        [
                            BASH,
                            "--noprofile",
                            "--norc",
                            "-c",
                            'source "$1"; shift; "$@" "hello"',
                            "devin-test",
                            str(WRAPPERS),
                            wrapper,
                        ],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=20,
                        env=env,
                    )
                    self.assertEqual(0, res.returncode, res.stderr)
                    argv = json.loads(args_file.read_text())
                    self.assertEqual(model, argv[argv.index("--model") + 1])
                    self.assertEqual("bypass", argv[argv.index("--permission-mode") + 1])
                    self.assertEqual("hello", argv[-1])

    def test_filter_command_code_lists_current_models(self) -> None:
        process = self.run_agents("--cmd")
        self.assertEqual(0, process.returncode, process.stderr.decode())
        text = process.stdout.decode()
        self.assertRegex(text, r"cmds\s+deepseek/deepseek-v4\.1-flash\s+max\s+yolo")
        self.assertRegex(text, r"cmm26p\s+xiaomi/mimo-v2\.6-pro\s+-\s+yolo")
        for wrapper, model, effort in (
            ("cmqh", r"Qwen/Qwen4-Max", "high"),
            ("cmqx", r"Qwen/Qwen4-Max", "xhigh"),
            ("cm62h", r"gpt-6\.2-sol", "high"),
            ("cm62x", r"gpt-6\.2-sol", "xhigh"),
            ("cm62mm", r"gpt-6\.2-sol", "max"),
            ("cmcm", r"google/gemini-4-carbon", "medium"),
            ("cmch", r"google/gemini-4-carbon", "high"),
            ("cmnh", r"google/gemini-4-neon", "high"),
            ("cmnx", r"google/gemini-4-neon", "xhigh"),
            ("cmhy", r"tencent/hy4", "high"),
            ("cmdglyph", r"stealth/glyph-cluster:free", "xhigh"),
            ("cmdflint", r"recursive/flint-v1\.0:free", "-"),
        ):
            self.assertRegex(text, rf"{wrapper}\s+{model}\s+{effort}\s+yolo")

    def test_inventory_has_no_retired_or_undefined_launchers(self) -> None:
        process = self.run_agents()
        self.assertEqual(0, process.returncode, process.stderr.decode())
        listed = set(re.findall(
            r"^  ([a-zA-Z0-9_-]+) {2,}\S+", process.stdout.decode(), re.M)) - {"WRAPPER"}
        self.assertTrue(listed)
        self.assertFalse(listed.intersection(RETIRED_MODEL_WRAPPERS))
        definitions = subprocess.run(
            [BASH, "--noprofile", "--norc", "-c", 'source "$1"; declare -F',
             "inventory-test", str(WRAPPERS)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(0, definitions.returncode, definitions.stderr)
        defined = {line.split()[-1] for line in definitions.stdout.splitlines()}
        self.assertFalse(listed - defined, listed - defined)

    def test_help(self) -> None:
        process = self.run_agents("--help")
        self.assertEqual(0, process.returncode, process.stderr.decode())
        self.assertIn("Usage: agents", process.stdout.decode())

    def test_unknown_flag_fails(self) -> None:
        process = self.run_agents("--bogus")
        self.assertEqual(1, process.returncode)
        self.assertIn("unrecognized option", process.stderr.decode())


class CodexLaunchTests(unittest.TestCase):
    def test_terra_model_effort_passthrough_and_final_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex-terra-") as directory:
            home = Path(directory).resolve()
            canonical = home / "canonical"
            canonical2 = home / "canonical2"
            for account_home in (canonical, canonical2):
                account_home.mkdir()
                (account_home / "auth.json").write_text("{}\n")
                (account_home / "skills").mkdir()
            binary = home / "bin" / "codex"
            binary.parent.mkdir()
            binary.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, sys\n"
                "args = sys.argv[1:]\n"
                "payload = json.dumps({'args': args, 'home': os.environ['CODEX_HOME']})\n"
                "if '--output-last-message' in args:\n"
                "    pathlib.Path(args[args.index('--output-last-message') + 1]).write_text(payload)\n"
                "    print('intermediate transcript')\n"
                "else:\n"
                "    print(payload)\n"
                "sys.exit(int(os.environ['TEST_EXIT']))\n"
            )
            binary.chmod(0o755)
            for wrapper, effort in (
                ("ctx", "xhigh"), ("ctxb", "xhigh"),
                ("ctx2", "xhigh"), ("ctxb2", "xhigh"),
                ("ctm", "max"), ("ctmb", "max"),
                ("ctm2", "max"), ("ctmb2", "max"),
            ):
                account_home = canonical2 if wrapper.endswith("2") else canonical
                bare = wrapper.removesuffix("2").endswith("b")
                for headless in (False, True):
                    for status in (0, 23):
                        with self.subTest(wrapper=wrapper, headless=headless, status=status):
                            arguments = ["-p", "literal task $()"] if headless else ["--no-alt-screen"]
                            result = subprocess.run(
                                [BASH, "--noprofile", "--norc", "-c",
                                 'source "$1"; shift; "$@"', "codex-test",
                                 str(WRAPPERS), wrapper, *arguments],
                                env=dict(os.environ, PATH=f"{binary.parent}:{os.environ['PATH']}",
                                         CODEX_CANONICAL_HOME=str(canonical),
                                         CODEX2_HOME=str(canonical2),
                                         CODEX_STATE_ROOT=str(home / "state"),
                                         CODEX2_STATE_ROOT=str(home / "state2"),
                                         CODEX_BARE_STATE_ROOT=str(home / "state" / "bare"),
                                         CODEX_WRAPPER_SCOPE="global", TEST_EXIT=str(status)),
                                cwd=home,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
                            )
                            self.assertEqual(status, result.returncode, result.stderr)
                            payload = json.loads(result.stdout)
                            argv = payload["args"]
                            launched_home = Path(payload["home"])
                            if bare:
                                state_root = home / ("state2" if wrapper.endswith("2") else "state")
                                self.assertTrue(launched_home.is_relative_to(state_root / "bare"))
                                self.assertEqual(account_home / "auth.json",
                                                 (launched_home / "auth.json").resolve())
                            else:
                                self.assertEqual(account_home, launched_home)
                            self.assertEqual("gpt-6.1-terra", argv[argv.index("-m") + 1])
                            self.assertIn(f"model_reasoning_effort={effort}", argv)
                            self.assertEqual("danger-full-access", argv[argv.index("-s") + 1])
                            if headless:
                                self.assertIn("exec", argv)
                                self.assertIn("--output-last-message", argv)
                                self.assertEqual(["--", "literal task $()"], argv[-2:])
                            else:
                                self.assertNotIn("exec", argv)
                                self.assertEqual("--no-alt-screen", argv[-1])

    def test_bare_home_keeps_core_tools_chrome_browser_and_arxiv(self) -> None:
        import tomllib

        with tempfile.TemporaryDirectory(prefix="codex-bare-") as directory:
            home = Path(directory).resolve()
            canonical = home / "canonical"
            canonical.mkdir()
            (canonical / "auth.json").write_text("{}\n")
            (canonical / "skills").mkdir()
            binary = home / "bin" / "codex"
            binary.parent.mkdir()
            binary.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "print(json.dumps({'args': sys.argv[1:], 'home': os.environ['CODEX_HOME']}))\n"
            )
            binary.chmod(0o755)

            def launch() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [BASH, "--noprofile", "--norc", "-c", 'source "$1"; cdxb --no-alt-screen',
                     "codex-test", str(WRAPPERS)],
                    env=dict(os.environ, PATH=f"{binary.parent}:{os.environ['PATH']}",
                             CODEX_CANONICAL_HOME=str(canonical),
                             CODEX_STATE_ROOT=str(home / "state"),
                             CODEX_BARE_STATE_ROOT=str(home / "state" / "bare")),
                    cwd=home, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
                )

            # Without a canonical node_repl entry: warn, no browser server.
            result = launch()
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("browser use unavailable", result.stderr)
            payload = json.loads(result.stdout)
            config = tomllib.loads((Path(payload["home"]) / "config.toml").read_text())
            self.assertNotIn("mcp_servers", config)
            self.assertIn('mcp_servers.arxiv.command="uvx"', payload["args"])
            features = config["features"]
            for name in ("apps", "plugins", "remote_plugin", "plugin_sharing", "computer_use",
                         "goals", "image_generation", "in_app_browser", "skill_search",
                         "skill_mcp_dependency_install", "tool_suggest", "memories"):
                self.assertIs(False, features[name], name)
            self.assertIs(True, features["browser_use"])
            self.assertIs(True, features["browser_use_external"])
            self.assertEqual("danger-full-access", config["sandbox_mode"])

            (canonical / "config.toml").write_text(
                '[mcp_servers.node_repl]\ncommand = "/app/node_repl"\nargs = []\n'
                'startup_timeout_sec = 120\n[mcp_servers.node_repl.env]\n'
                'BROWSER_USE_AVAILABLE_BACKENDS = "chrome,iab,mcpapps"\nCODEX_HOME = "/x"\n'
                '[mcp_servers.lovable]\nurl = "https://example.invalid"\n'
            )
            result = launch()
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("browser use unavailable", result.stderr)
            config = tomllib.loads((Path(json.loads(result.stdout)["home"]) / "config.toml").read_text())
            self.assertEqual(["node_repl"], list(config["mcp_servers"]))
            node_repl = config["mcp_servers"]["node_repl"]
            self.assertEqual("/app/node_repl", node_repl["command"])
            self.assertEqual({"BROWSER_USE_AVAILABLE_BACKENDS": "chrome", "CODEX_HOME": "/x"},
                             node_repl["env"])

    def test_codex_speed_and_api_key_account_isolation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex-api-") as directory:
            home = Path(directory).resolve()
            canonical = home / "canonical"
            canonical2 = home / "canonical2"
            api_home = home / "api"
            for account_home in (canonical, canonical2, api_home):
                account_home.mkdir()
                (account_home / "auth.json").write_text("{}\n")
                (account_home / "skills").mkdir()
            binary = home / "bin" / "codex"
            binary.parent.mkdir()
            binary.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, sys\n"
                "args = sys.argv[1:]\n"
                "payload = json.dumps({\n"
                "    'args': args,\n"
                "    'home': os.environ['CODEX_HOME'],\n"
                "    'env': {k: os.environ[k] for k in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN') if k in os.environ},\n"
                "})\n"
                "if '--output-last-message' in args:\n"
                "    pathlib.Path(args[args.index('--output-last-message') + 1]).write_text(payload)\n"
                "else:\n"
                "    print(payload)\n"
            )
            binary.chmod(0o755)
            base_env = dict(
                os.environ,
                HOME=str(home),
                PATH=f"{binary.parent}:{os.environ['PATH']}",
                CODEX_CANONICAL_HOME=str(canonical),
                CODEX2_HOME=str(canonical2),
                CODEX_API_HOME=str(api_home),
                CODEX_STATE_ROOT=str(home / "state"),
                CODEX2_STATE_ROOT=str(home / "state2"),
                CODEX_API_STATE_ROOT=str(home / "state-api"),
                CODEX_BARE_STATE_ROOT=str(home / "state" / "bare"),
                CODEX_FRESH_STATE_ROOT=str(home / "state" / "fresh"),
                CODEX_WRAPPER_SCOPE="global",
                OPENAI_API_KEY="ambient-openai-key",
                CODEX_API_KEY="ambient-codex-key",
                CODEX_ACCESS_TOKEN="ambient-access-token",
            )

            def run_codex(*args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [BASH, "--noprofile", "--norc", "-c",
                     'source "$1"; shift; "$@"', "codex-api-test",
                     str(WRAPPERS), *args],
                    env=base_env,
                    cwd=home,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
                )

            cases = (
                (("cdxk",), api_home, "gpt-6.2-sol", "xhigh", False),
                (("cdxk", "-p", "api prompt"), api_home, "gpt-6.2-sol", "xhigh", True),
                (("cdxk", "cam", "-p", "wrapped"), api_home, "gpt-6.2-astra", "max", True),
                (("cdx", "--api-key", "--no-alt-screen"), api_home, "gpt-6.2-sol", "xhigh", False),
                (("cam", "-ak", "-p", "flag prompt"), api_home, "gpt-6.2-astra", "max", True),
                (("cdx", "--", "--api-key"), canonical, "gpt-6.2-sol", "xhigh", False),
                (("cdx2", "-p", "secondary prompt"), canonical2, "gpt-6.2-sol", "xhigh", True),
            )
            for cmd, expected_home, expected_model, expected_effort, headless in cases:
                with self.subTest(cmd=cmd):
                    res = run_codex(*cmd)
                    self.assertEqual(0, res.returncode, res.stderr)
                    payload = json.loads(res.stdout)
                    self.assertEqual(str(expected_home), payload["home"])
                    self.assertEqual({}, payload["env"])
                    argv = payload["args"]
                    self.assertEqual(expected_model, argv[argv.index("-m") + 1])
                    self.assertIn(f"model_reasoning_effort={expected_effort}", argv)
                    tiers = [arg for arg in argv if arg.startswith("service_tier=")]
                    self.assertEqual(["service_tier=default"] if expected_home == canonical else [], tiers)
                    if headless:
                        self.assertIn("exec", argv)
                    if cmd == ("cdx", "--", "--api-key"):
                        self.assertEqual(["--", "--api-key"], argv[-2:])
                    else:
                        self.assertNotIn("--api-key", argv)
                        self.assertNotIn("-ak", argv)

            speed_cases = (
                (("cdx",), "default", "gpt-6.2-sol", "xhigh", ()),
                (("cdx", "-f"), "fast", "gpt-6.2-sol", "xhigh", ()),
                (("cam", "-uf"), "ultrafast", "gpt-6.2-astra", "max", ()),
                (("cdxf",), "fast", "gpt-6.2-sol", "xhigh", ()),
                (("cdxf2",), "fast", "gpt-6.2-sol", "xhigh", ()),
                (("cdx", "-uf", "-p", "task"), "ultrafast", "gpt-6.2-sol", "xhigh", ("--", "task")),
                (("cdx", "-p", "task", "-f", "--json"), "fast", "gpt-6.2-sol", "xhigh", ("--", "task")),
                (("cdxe", "-uf", "task"), "ultrafast", "gpt-6.2-sol", "xhigh", ("--", "task")),
                (("cdx", "-p", "-f"), "default", "gpt-6.2-sol", "xhigh", ("--", "-f")),
                (("cdx", "--", "-uf"), "default", "gpt-6.2-sol", "xhigh", ("--", "-uf")),
            )
            for cmd, tier, model, effort, prompt_tail in speed_cases:
                with self.subTest(cmd=cmd):
                    res = run_codex(*cmd)
                    self.assertEqual(0, res.returncode, res.stderr)
                    argv = json.loads(res.stdout)["args"]
                    tiers = [arg for arg in argv if arg.startswith("service_tier=")]
                    self.assertTrue(tiers, argv)
                    self.assertEqual(f"service_tier={tier}", tiers[-1])
                    self.assertEqual(model, argv[argv.index("-m") + 1])
                    self.assertIn(f"model_reasoning_effort={effort}", argv)
                    flags = argv[:-len(prompt_tail)] if prompt_tail else argv
                    self.assertNotIn("-f", flags)
                    self.assertNotIn("-uf", flags)
                    if prompt_tail:
                        self.assertEqual(list(prompt_tail), argv[-len(prompt_tail):])
                    if "--json" in cmd:
                        self.assertIn("--json", argv)
                        self.assertNotIn("--output-last-message", argv)

            for cmd in (("cdx2", "-f"), ("cdxk", "-uf"), ("cdx", "-f", "--api-key")):
                with self.subTest(cmd=cmd):
                    res = run_codex(*cmd)
                    self.assertEqual(2, res.returncode, res.stderr)
                    self.assertIn("main Codex account", res.stderr)
                    self.assertEqual("", res.stdout)

            # Final mode keeps literal flag text inside prompts after leading flags.
            final_res = run_codex("cdxe", "--api-key", "prompt about --api-key")
            self.assertEqual(0, final_res.returncode, final_res.stderr)
            final_payload = json.loads(final_res.stdout)
            self.assertEqual(str(api_home), final_payload["home"])
            self.assertEqual({}, final_payload["env"])
            self.assertEqual(["--", "prompt about --api-key"], final_payload["args"][-2:])

            # Bare API-key launch links auth.json from CODEX_API_HOME into CODEX_API_STATE_ROOT.
            bare_res = run_codex("cdxk", "cdxb", "--no-alt-screen")
            self.assertEqual(0, bare_res.returncode, bare_res.stderr)
            bare_payload = json.loads(bare_res.stdout)
            bare_home = Path(bare_payload["home"])
            self.assertTrue(bare_home.is_relative_to(home / "state-api" / "bare"))
            self.assertEqual(api_home / "auth.json", (bare_home / "auth.json").resolve())
            self.assertEqual({}, bare_payload["env"])
            self.assertFalse((home / "state" / "bare" / "repos").exists())

            # Mixing cdxk with secondary-account *2 wrappers fails loudly.
            bad_res = run_codex("cdxk", "cdx2")
            self.assertEqual(2, bad_res.returncode)
            self.assertIn("cannot combine API-key mode", bad_res.stderr)
            self.assertEqual("", bad_res.stdout)

            # _codex_use_api_env updates auth.json when OPENAI_API_KEY changes, skips rewrite when unchanged,
            # keeps existing auth.json when unset, and refuses to overwrite ChatGPT OAuth or symlinks.
            auth_file = api_home / "auth.json"
            self.assertEqual(
                {"auth_mode": "apikey", "OPENAI_API_KEY": "ambient-openai-key"},
                json.loads(auth_file.read_text()),
            )
            self.assertEqual(0o600, auth_file.stat().st_mode & 0o777)

            before_inode = auth_file.stat().st_ino
            same_res = run_codex("cdxk")
            self.assertEqual(0, same_res.returncode, same_res.stderr)
            self.assertEqual(before_inode, auth_file.stat().st_ino)

            rotated_env = dict(base_env, OPENAI_API_KEY="rotated-openai-key")
            rotated_res = subprocess.run(
                [BASH, "--noprofile", "--norc", "-c",
                 'source "$1"; shift; "$@"', "codex-api-test", str(WRAPPERS), "cdx", "--api-key"],
                env=rotated_env, cwd=home,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(0, rotated_res.returncode, rotated_res.stderr)
            self.assertEqual(
                {"auth_mode": "apikey", "OPENAI_API_KEY": "rotated-openai-key"},
                json.loads(auth_file.read_text()),
            )

            unset_env = {k: v for k, v in rotated_env.items() if k != "OPENAI_API_KEY"}
            unset_res = subprocess.run(
                [BASH, "--noprofile", "--norc", "-c",
                 'source "$1"; shift; "$@"', "codex-api-test", str(WRAPPERS), "cdxk"],
                env=unset_env, cwd=home,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(0, unset_res.returncode, unset_res.stderr)
            self.assertEqual(
                {"auth_mode": "apikey", "OPENAI_API_KEY": "rotated-openai-key"},
                json.loads(auth_file.read_text()),
            )

            oauth_payload = {"auth_mode": "chatgpt", "tokens": {"access_token": "secret"}}
            auth_file.write_text(json.dumps(oauth_payload))
            for guard_cmd in (("cdxk",), ("cdx", "--api-key")):
                guard_res = subprocess.run(
                    [BASH, "--noprofile", "--norc", "-c",
                     'source "$1"; shift; "$@"', "codex-api-test", str(WRAPPERS), *guard_cmd],
                    env=rotated_env, cwd=home,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(1, guard_res.returncode)
                self.assertIn("ChatGPT OAuth credentials", guard_res.stderr)
                self.assertEqual("", guard_res.stdout)
                self.assertEqual(oauth_payload, json.loads(auth_file.read_text()))

            auth_file.unlink()
            auth_file.symlink_to(canonical / "auth.json")
            symlink_res = subprocess.run(
                [BASH, "--noprofile", "--norc", "-c",
                 'source "$1"; shift; "$@"', "codex-api-test", str(WRAPPERS), "cdxk"],
                env=rotated_env, cwd=home,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(1, symlink_res.returncode)
            self.assertIn("symlinked auth file", symlink_res.stderr)
            self.assertEqual("", symlink_res.stdout)
            self.assertEqual("{}\n", (canonical / "auth.json").read_text())


class ClaudeLaunchTests(unittest.TestCase):
    """_cc_launch composes the claude argv; a fake binary echoes it."""

    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="cc-wrapper-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env_file = self.home / ".env"
        self.env_file.write_text(
            'ANTHROPIC_API_KEY="sk-ant-dotenv-key"\n'
            'OTHER_DOTENV_VAR="should-not-leak"\n'
        )
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n')
        fake.chmod(0o755)
        self.path = f"{bin_dir}:/usr/bin:/bin"

    def launch(self, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("CLAUDE_ENV_FILE", "OTHER_DOTENV_VAR")
        }
        env.update(HOME=str(self.home), PATH=self.path)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [BASH, "--noprofile", "--norc", "-c", 'source "$1"; shift; "$@"',
             "cc-test", str(WRAPPERS), *args],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20, env=env,
        )

    def run_api_key_helper(self, command: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin"}
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["/bin/sh", "-c", command],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10, env=env,
        )

    def model_arg(self, wrapper: str) -> str:
        process = self.launch(wrapper)
        self.assertEqual(0, process.returncode, process.stderr)
        argv = process.stdout.splitlines()
        return argv[argv.index("--model") + 1]

    def test_model_wrappers_request_the_1m_window(self) -> None:
        # Without [1m], Opus/Fable get native 1M only on a first-party
        # ANTHROPIC_BASE_URL; behind a local proxy they fall back to 200k.
        for wrapper, model in (
            ("ccxX", "opus[1m]"), ("ccmM", "opus[1m]"),
            ("ccmm", "opus[1m]"), ("ccbm", "opus[1m]"), ("cckmm", "opus[1m]"),
            ("cckbm", "opus[1m]"), ("cckbu", "opus[1m]"), ("ccfmm", "fable[1m]"),
            ("ccbfm", "fable[1m]"), ("cckfmm", "fable[1m]"), ("cckbfm", "fable[1m]"),
            ("cshh", "claude-sonnet-5-5[1m]"), ("csbmm", "claude-sonnet-5-5[1m]"),
            ("chx", "claude-haiku-5-5[1m]"), ("chbh", "claude-haiku-5-5[1m]"),
        ):
            with self.subTest(wrapper=wrapper):
                self.assertEqual(model, self.model_arg(wrapper))

    def test_api_key_flag_switches_any_wrapper_and_reads_dotenv_key(self) -> None:
        for args, expected_mode_flag, expected_model, expected_tail in (
            (("csm", "--api-key", "-p", "hello"), None, "claude-sonnet-5-5[1m]", ["-p", "hello"]),
            (("chh", "-ak"), None, "claude-haiku-5-5[1m]", []),
            (("ccbm", "--api-key"), "--bare", "opus[1m]", []),
            (("cckbm",), "--bare", "opus[1m]", []),
        ):
            with self.subTest(args=args):
                process = self.launch(*args, extra_env={"ANTHROPIC_API_KEY": "sk-stale-ambient"})
                self.assertEqual(0, process.returncode, process.stderr)
                argv = process.stdout.splitlines()
                self.assertNotIn("--api-key", argv)
                self.assertNotIn("-ak", argv)
                self.assertNotIn("--safe-mode", argv)
                self.assertFalse(any("sk-ant-dotenv-key" in token for token in argv))
                settings = json.loads(argv[argv.index("--settings") + 1])
                helper_res = self.run_api_key_helper(
                    settings["apiKeyHelper"],
                    extra_env={"ANTHROPIC_API_KEY": "sk-stale-ambient"},
                )
                self.assertEqual(0, helper_res.returncode, helper_res.stderr)
                self.assertEqual("sk-ant-dotenv-key", helper_res.stdout.strip())
                self.assertEqual(expected_model, argv[argv.index("--model") + 1])
                if expected_mode_flag:
                    self.assertIn(expected_mode_flag, argv)
                else:
                    self.assertNotIn("--bare", argv)
                for item in expected_tail:
                    self.assertIn(item, argv)

        alt_env = self.home / "custom.env"
        alt_env.write_text('export ANTHROPIC_API_KEY="sk-ant-custom-env-file"\n')
        custom_proc = self.launch("cckx", extra_env={"CLAUDE_ENV_FILE": str(alt_env)})
        self.assertEqual(0, custom_proc.returncode, custom_proc.stderr)
        custom_argv = custom_proc.stdout.splitlines()
        custom_settings = json.loads(custom_argv[custom_argv.index("--settings") + 1])
        custom_helper = self.run_api_key_helper(
            custom_settings["apiKeyHelper"],
            extra_env={"CLAUDE_ENV_FILE": str(alt_env)},
        )
        self.assertEqual(0, custom_helper.returncode, custom_helper.stderr)
        self.assertEqual("sk-ant-custom-env-file", custom_helper.stdout.strip())

        after_ddash = self.launch("csm", "--", "-ak")
        self.assertEqual(0, after_ddash.returncode, after_ddash.stderr)
        argv = after_ddash.stdout.splitlines()
        self.assertNotIn("--settings", argv)
        self.assertEqual(["--", "-ak"], argv[-2:])

    def test_key_mode_merges_settings_overlays_and_fails_loudly_on_bad_input(self) -> None:
        extra_file = self.home / "extra.json"
        extra_file.write_text(json.dumps({"env": {"EXTRA_FLAG": "yes"}}))

        for args, expected_env in (
            (("ccxX", "--api-key"), {
                "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "300000",
                "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "0",
                "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "16",
                "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "2",
            }),
            (("cckm", f"--settings={extra_file}", "--settings", '{"apiKeyHelper":"wrong","model":"custom"}'), {
                "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "300000",
                "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "0",
                "EXTRA_FLAG": "yes",
            }),
        ):
            with self.subTest(args=args):
                process = self.launch(*args)
                self.assertEqual(0, process.returncode, process.stderr)
                argv = process.stdout.splitlines()
                self.assertEqual(1, argv.count("--settings"))
                merged = json.loads(argv[argv.index("--settings") + 1])
                helper_res = self.run_api_key_helper(merged["apiKeyHelper"])
                self.assertEqual(0, helper_res.returncode, helper_res.stderr)
                self.assertEqual("sk-ant-dotenv-key", helper_res.stdout.strip())
                self.assertFalse(merged["includeCoAuthoredBy"])
                for key, val in expected_env.items():
                    self.assertEqual(val, merged["env"][key])

        missing_extra = self.launch("cckm", "--settings", str(self.home / "missing.json"))
        self.assertNotEqual(0, missing_extra.returncode)
        self.assertIn("settings file not found", missing_extra.stderr)

        self.env_file.unlink()
        missing_key = self.launch("ccxX", "--api-key")
        self.assertEqual(2, missing_key.returncode)
        self.assertIn("requires ANTHROPIC_API_KEY", missing_key.stderr)
        self.assertEqual("", missing_key.stdout)

    def test_key_mode_clears_inherited_provider_and_model_overrides(self) -> None:
        (self.home / "bin" / "claude").write_text(
            '#!/bin/bash\nprintf "%s|%s|%s|%s|%s\\n" '
            '"${ANTHROPIC_BASE_URL-unset}" "${ANTHROPIC_MODEL-unset}" '
            '"${ANTHROPIC_API_KEY-unset}" "${ANTHROPIC_AUTH_TOKEN-unset}" '
            '"${OTHER_DOTENV_VAR-unset}"\n'
        )
        for wrapper in ("ccx", "cckx"):
            with self.subTest(wrapper=wrapper):
                process = self.launch(
                    wrapper,
                    extra_env={
                        "ANTHROPIC_BASE_URL": "https://example.invalid/proxy",
                        "ANTHROPIC_MODEL": "kimi-for-coding",
                        "ANTHROPIC_API_KEY": "sk-stale",
                        "ANTHROPIC_AUTH_TOKEN": "tok-stale",
                    },
                )
                self.assertEqual(0, process.returncode, process.stderr)
                self.assertEqual("unset|unset|unset|unset|unset", process.stdout.strip())

    def test_code_mode_flag_scopes_env_disables_chrome_and_agent_teams_and_merges_overlays(self) -> None:
        for args, expected_mode_flag, expected_extra_env in (
            (("ccx", "--code-mode", "-p", "hi"), None, {}),
            (("ccbm", "--code-mode"), "--safe-mode", {}),
            (("ccxX", "--code-mode"), None, {
                "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "16",
                "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "2",
            }),
        ):
            with self.subTest(args=args):
                process = self.launch(
                    *args,
                    extra_env={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "true"},
                )
                self.assertEqual(0, process.returncode, process.stderr)
                argv = process.stdout.splitlines()
                self.assertNotIn("--code-mode", argv)
                self.assertIn("--no-chrome", argv)
                if expected_mode_flag:
                    self.assertIn(expected_mode_flag, argv)
                self.assertEqual(1, argv.count("--settings"))
                merged = json.loads(argv[argv.index("--settings") + 1])
                self.assertEqual("1", merged["env"]["CLAUDE_CODE_EXPERIMENTAL_CODE_MODE"])
                self.assertEqual("", merged["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"])
                for key, val in expected_extra_env.items():
                    self.assertEqual(val, merged["env"][key])

        # Verify child env swaps CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC for narrower
        # opt-outs without leaking out of the wrapper subshell, and default runs keep it.
        (self.home / "bin" / "claude").write_text(
            '#!/bin/bash\nprintf "%s|%s|%s|%s|%s\\n" '
            '"${CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC-unset}" '
            '"${DISABLE_AUTOUPDATER-unset}" "${DISABLE_ERROR_REPORTING-unset}" '
            '"${DISABLE_FEEDBACK_COMMAND-unset}" "${CLAUDE_CODE_EXPERIMENTAL_CODE_MODE-unset}"\n'
        )
        env = {
            key: value for key, value in os.environ.items()
            if key not in (
                "DISABLE_AUTOUPDATER", "DISABLE_ERROR_REPORTING",
                "DISABLE_FEEDBACK_COMMAND", "CLAUDE_CODE_EXPERIMENTAL_CODE_MODE",
            )
        }
        env.update(HOME=str(self.home), PATH=self.path, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="true")
        scoped = subprocess.run(
            [
                BASH, "--noprofile", "--norc", "-c",
                'source "$1"; ccx --code-mode; '
                'printf "parent:%s|%s|%s\\n" '
                '"${CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC-unset}" '
                '"${DISABLE_AUTOUPDATER-unset}" "${CLAUDE_CODE_EXPERIMENTAL_CODE_MODE-unset}"',
                "cc-test", str(WRAPPERS),
            ],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20, env=env,
        )
        self.assertEqual(0, scoped.returncode, scoped.stderr)
        self.assertEqual(
            ["unset|1|1|1|1", "parent:true|unset|unset"],
            scoped.stdout.splitlines(),
        )

        # Incompatible combinations and passthrough after `--`.
        (self.home / "bin" / "claude").write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n')
        for bad_args, expected_err in (
            (("cckx", "--code-mode"), "cannot be combined with API-key mode"),
            (("ccx", "--api-key", "--code-mode"), "cannot be combined with API-key mode"),
            (("ccx", "--code-mode", "--chrome"), "cannot be combined with --chrome"),
        ):
            with self.subTest(bad_args=bad_args):
                bad = self.launch(*bad_args)
                self.assertEqual(2, bad.returncode)
                self.assertIn(expected_err, bad.stderr)
                self.assertEqual("", bad.stdout)

        after_ddash = self.launch(
            "ccx", "--", "--code-mode",
            extra_env={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "true"},
        )
        self.assertEqual(0, after_ddash.returncode, after_ddash.stderr)
        tail_argv = after_ddash.stdout.splitlines()
        self.assertNotIn("--no-chrome", tail_argv)
        self.assertNotIn("--settings", tail_argv)
        self.assertEqual(["--", "--code-mode"], tail_argv[-2:])

    def test_hist_parent_names_only_a_plain_claude_shell(self) -> None:
        (self.home / "bin" / "claude").write_text(
            '#!/bin/bash\nprintf "%s\\n" "${HIST_PARENT-unset}"\n')
        base = {key: value for key, value in os.environ.items()
                if key not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "HIST_PARENT")}
        base.update(HOME=str(self.home), PATH=self.path)
        stale = {"HIST_PARENT": "claude:stale"}
        for extra, expected in (
            ({"CLAUDE_CODE_SESSION_ID": "s1"}, "claude:s1"),
            ({**stale, "CLAUDE_CODE_SESSION_ID": "s1"}, "claude:s1"),
            ({**stale, "CLAUDE_CODE_SESSION_ID": "s1", "CODEX_THREAD_ID": "t1"}, "unset"),
            (stale, "unset"),
        ):
            with self.subTest(extra=extra):
                process = subprocess.run(
                    [BASH, "--noprofile", "--norc", "-c", 'source "$1"; csx',
                     "cc-test", str(WRAPPERS)],
                    stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
                    env={**base, **extra},
                )
                self.assertEqual(0, process.returncode, process.stderr.decode())
                self.assertEqual(expected, process.stdout.decode().strip())


class CommandLaunchTests(unittest.TestCase):
    def test_current_models_preserve_effort_arguments_and_exit_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cmd-wrapper-") as directory:
            home = Path(directory)
            binary = home / "bin" / "cmd"
            binary.parent.mkdir()
            binary.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\nexit "${TEST_EXIT:-0}"\n')
            binary.chmod(0o755)
            arguments = ["--no-auto-update", "--output-format", "json", "-p", "literal task $()"]
            for launcher, model, effort in (
                ("cmds", "deepseek/deepseek-v4.1-flash", "max"),
                ("cmm26p", "xiaomi/mimo-v2.6-pro", ""),
                ("cmqh", "Qwen/Qwen4-Max", "high"),
                ("cmqx", "Qwen/Qwen4-Max", "xhigh"),
                ("cm62h", "gpt-6.2-sol", "high"),
                ("cm62x", "gpt-6.2-sol", "xhigh"),
                ("cm62mm", "gpt-6.2-sol", "max"),
                ("cmcm", "google/gemini-4-carbon", "medium"),
                ("cmch", "google/gemini-4-carbon", "high"),
                ("cmnh", "google/gemini-4-neon", "high"),
                ("cmnx", "google/gemini-4-neon", "xhigh"),
                ("cmhy", "tencent/hy4", "high"),
                ("cmdglyph", "stealth/glyph-cluster:free", "xhigh"),
                ("cmdflint", "recursive/flint-v1.0:free", ""),
            ):
                for status in (0, 23):
                    with self.subTest(launcher=launcher, status=status):
                        process = subprocess.run(
                            [BASH, "--noprofile", "--norc", "-c",
                             'source "$1"; shift; "$@"',
                             "cmd-test", str(WRAPPERS), launcher, *arguments],
                            env=dict(os.environ, HOME=str(home), PATH=f"{binary.parent}:/usr/bin:/bin",
                                     TEST_EXIT=str(status)),
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
                        )
                        self.assertEqual(status, process.returncode, process.stderr)
                        self.assertEqual(
                            ["--model", model, "--max-turns", "9999",
                             *(["--effort", effort] if effort else []),
                             "--yolo", *arguments], process.stdout.splitlines())


class KimiLaunchTests(unittest.TestCase):
    def test_managed_default_is_k31_pro_with_each_wrappers_effort(self) -> None:
        with tempfile.TemporaryDirectory(prefix="kimi-wrapper-") as directory:
            home = Path(directory)
            canonical = home / ".kimi-code"
            (canonical / "bin").mkdir(parents=True)
            (canonical / "credentials").mkdir()
            (home / ".agents" / "skills").mkdir(parents=True)
            config = (WRAPPERS.parents[1] / "AGENT-ENGINEERING" /
                      "PERSISTENT-GUIDANCE" / "config" / "kimi" / "config.toml")
            # A live config: canonical plus the keys Kimi writes itself.
            top, tables = (
                Path(__file__).parent / "fixtures" / "kimi-host-written.toml"
            ).read_text().split("\n[", 1)
            (canonical / "config.toml").write_text(
                top + "\n" + config.read_text() + "\n[" + tables
            )
            fake = canonical / "bin" / "kimi"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, tomllib\n"
                "config = tomllib.loads((pathlib.Path(os.environ['KIMI_CODE_HOME']) / "
                "'config.toml').read_text())\n"
                "alias = config['default_model']\n"
                "model = config['models'][alias]\n"
                "metadata = {'alias': alias, 'upstream': model['model'], "
                "'provider': model['provider'], 'effort': "
                "os.environ['KIMI_MODEL_THINKING_EFFORT']}\n"
                "print(json.dumps({'role': 'assistant', 'content': json.dumps(metadata)}))\n"
            )
            fake.chmod(0o755)
            environment = dict(
                os.environ, HOME=str(home), KIMI_CANONICAL_HOME=str(canonical),
                KIMI_STATE_ROOT=str(home / "state"),
            )
            for wrapper, effort in (
                ("kimm", "max"), ("kimh", "high"), ("kiml", "low"),
                ("kimb", "max"), ("kimbs", "max"),
            ):
                with self.subTest(wrapper=wrapper):
                    process = subprocess.run(
                        [BASH, "--noprofile", "--norc", "-c",
                         'source "$1"; "$2" -p probe', "kimi-test",
                         str(WRAPPERS), wrapper],
                        cwd=home, env=environment, stdin=subprocess.DEVNULL,
                        capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(0, process.returncode, process.stderr)
                    self.assertEqual(
                        {"alias": "kimi-code/k3.1-pro", "upstream": "k3.1-pro",
                         "provider": "managed:kimi-code", "effort": effort},
                        json.loads(process.stdout),
                    )


class AntigravityLaunchTests(unittest.TestCase):
    """_agy_launch handles API-key auth, --settings merging, env fallback, and guards."""

    def test_api_key_wrappers_and_flags(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agy-api-wrapper-") as directory:
            home = Path(directory)
            (home / ".gemini" / "antigravity-cli").mkdir(parents=True)
            (home / ".gemini" / "antigravity-cli" / "settings.json").write_text("{}\n")
            (home / ".gemini" / "config").mkdir(parents=True)
            agy2 = home / ".agy2"
            token = agy2 / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
            token.parent.mkdir(parents=True)
            token.write_text("oauth-token")
            (agy2 / ".gemini" / "antigravity-cli" / "settings.json").write_text("{}\n")

            scripts_dir = home / ".agents" / "skills" / "delegate" / "scripts"
            scripts_dir.mkdir(parents=True)
            real_filter = (
                WRAPPERS.resolve().parent.parent
                / "AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/agy-final-output.py"
            )
            (scripts_dir / "agy-final-output.py").symlink_to(real_filter)

            bin_dir = home / "bin"
            bin_dir.mkdir()
            args_file = home / "agy-args.json"
            stub = bin_dir / "agy"
            stub.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, sys\n"
                "payload = {\n"
                "    'args': sys.argv[1:],\n"
                "    'gemini_key': os.environ.get('GEMINI_API_KEY'),\n"
                "    'base_url': os.environ.get('GOOGLE_GEMINI_BASE_URL'),\n"
                "    'other_env': os.environ.get('OTHER_DOTENV_VAR'),\n"
                "}\n"
                "pathlib.Path(os.environ['ARGS_FILE']).write_text(json.dumps(payload))\n"
                "for ev in (\n"
                "    {'event': 'init'},\n"
                "    {'event': 'step_update', 'step_update': {'step_index': 1, 'step_type': 'agent_response', 'state': 'DONE', 'text_delta': 'ok'}},\n"
                "    {'event': 'result', 'result': {'status': 'SUCCESS', 'response': 'ok'}},\n"
                "):\n"
                "    print(json.dumps(ev))\n"
            )
            stub.chmod(0o755)

            env_file = home / ".env"
            env_file.write_text(
                "export GEMINI_API_KEY='dotenv-gemini-key'\n"
                "export OTHER_DOTENV_VAR='should-not-leak'\n"
            )
            extra_settings_file = home / "extra.json"
            extra_settings_file.write_text('{"colorScheme":"light","extraFlag":true}\n')

            base_env = {
                key: value
                for key, value in os.environ.items()
                if key not in ("GEMINI_API_KEY", "GOOGLE_GEMINI_BASE_URL", "AGY_KEEP_BASE_URL", "OTHER_DOTENV_VAR")
            }
            base_env.update(
                HOME=str(home),
                AGY2_HOME=str(agy2),
                AGY_ENV_FILE=str(env_file),
                ARGS_FILE=str(args_file),
                PATH=f"{bin_dir}:/opt/homebrew/bin:/usr/bin:/bin",
            )

            def run_agy(*args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
                if args_file.exists():
                    args_file.unlink()
                env = dict(base_env)
                if extra_env:
                    env.update(extra_env)
                return subprocess.run(
                    [BASH, "--noprofile", "--norc", "-c", 'source "$1"; shift; "$@"',
                     "agy-api-test", str(WRAPPERS), *args],
                    env=env, cwd=home, stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, timeout=20,
                )

            # Defaults to aghh, loads GEMINI_API_KEY from ~/.env when unset without leaking other vars.
            for cmd, expected_model, bare in (
                (("agk",), "gemini-4-hydrogen-high", False),
                (("agk", "-p", "api task"), "gemini-4-hydrogen-high", False),
                (("agk", "aghxb", "-p", "bare task"), "gemini-4-hydrogen-xhigh", True),
                (("agk", "agcmb", "-p", "carbon bare"), "gemini-4-carbon-medium", True),
                (("agk", "agnxb", "-p", "neon bare"), "gemini-4-neon-xhigh", True),
                (("aghx", "--api-key", "-p", "flag task"), "gemini-4-hydrogen-xhigh", False),
                (("agch", "--api-key", "-p", "carbon high"), "gemini-4-carbon-high", False),
                (("agnh", "--api-key", "-p", "neon high"), "gemini-4-neon-high", False),
                (("argm", "-ak", "-p", "short task"), "gemini-4-argon-medium", False),
            ):
                with self.subTest(cmd=cmd):
                    res = run_agy(*cmd, extra_env={"GOOGLE_GEMINI_BASE_URL": "https://proxy.invalid"})
                    self.assertEqual(0, res.returncode, res.stderr)
                    payload = json.loads(args_file.read_text())
                    argv = payload["args"]
                    self.assertEqual(expected_model, argv[argv.index("--model") + 1])
                    self.assertEqual({"modelProvider": "gemini"}, json.loads(argv[argv.index("--settings") + 1]))
                    self.assertEqual("dotenv-gemini-key", payload["gemini_key"])
                    self.assertIsNone(payload["base_url"])
                    self.assertIsNone(payload["other_env"])
                    self.assertNotIn("--api-key", argv)
                    self.assertNotIn("-ak", argv)
                    if bare:
                        self.assertEqual("agy-bare", argv[argv.index("--agent") + 1])
                    else:
                        self.assertNotIn("--agent", argv)

            # Explicit env GEMINI_API_KEY and AGY_KEEP_BASE_URL=1 override ~/.env / base URL clearing.
            env_res = run_agy(
                "agk", "agg", "-p", "explicit",
                extra_env={
                    "GEMINI_API_KEY": "explicit-env-key",
                    "GOOGLE_GEMINI_BASE_URL": "https://custom.example",
                    "AGY_KEEP_BASE_URL": "1",
                },
            )
            self.assertEqual(0, env_res.returncode, env_res.stderr)
            env_payload = json.loads(args_file.read_text())
            self.assertEqual("explicit-env-key", env_payload["gemini_key"])
            self.assertEqual("https://custom.example", env_payload["base_url"])

            # --settings overlays are jq-merged with modelProvider: "gemini" winning.
            merge_res = run_agy(
                "aghh", "--api-key",
                f"--settings={extra_settings_file}",
                "--settings", '{"modelProvider":"agent-platform","thinkingLevel":"high"}',
                "-p", "merged",
            )
            self.assertEqual(0, merge_res.returncode, merge_res.stderr)
            merge_argv = json.loads(args_file.read_text())["args"]
            self.assertEqual(1, merge_argv.count("--settings"))
            self.assertEqual(
                {
                    "colorScheme": "light",
                    "extraFlag": True,
                    "thinkingLevel": "high",
                    "modelProvider": "gemini",
                },
                json.loads(merge_argv[merge_argv.index("--settings") + 1]),
            )

            # `--` stops flag scanning; normal subscription wrappers stay unaffected.
            passthrough_res = run_agy("agg", "--", "--api-key")
            self.assertEqual(0, passthrough_res.returncode, passthrough_res.stderr)
            passthrough_argv = json.loads(args_file.read_text())["args"]
            self.assertNotIn("--settings", passthrough_argv)
            self.assertEqual(["--", "--api-key"], passthrough_argv[-2:])

            # Secondary account without --api-key stays on OAuth and ignores GEMINI_API_KEY settings.
            sec_res = run_agy("agg2", "-p", "secondary")
            self.assertEqual(0, sec_res.returncode, sec_res.stderr)
            self.assertNotIn("--settings", json.loads(args_file.read_text())["args"])

            # Incompatible targets and missing keys fail loudly with exit 2 before running agy.
            for bad_cmd, expected_err in (
                (("agk", "agom"), "cannot use agom"),
                (("agk", "agoh"), "cannot use agoh"),
                (("agom", "--api-key"), "Gemini models only"),
                (("agoh", "-ak"), "Gemini models only"),
                (("agk", "agg2"), "cannot use agg2"),
                (("agg2", "--api-key"), "cannot be combined with secondary account"),
            ):
                with self.subTest(bad_cmd=bad_cmd):
                    bad_res = run_agy(*bad_cmd)
                    self.assertEqual(2, bad_res.returncode)
                    self.assertIn(expected_err, bad_res.stderr)
                    self.assertFalse(args_file.exists())

            missing_settings = run_agy("aghh", "--api-key", "--settings", str(home / "nope.json"))
            self.assertNotEqual(0, missing_settings.returncode)
            self.assertIn("settings file not found", missing_settings.stderr)
            self.assertFalse(args_file.exists())

            env_file.unlink()
            missing_key_res = run_agy("agk", "-p", "missing")
            self.assertEqual(2, missing_key_res.returncode)
            self.assertIn("requires GEMINI_API_KEY", missing_key_res.stderr)
            self.assertFalse(args_file.exists())


if __name__ == "__main__":
    unittest.main()
