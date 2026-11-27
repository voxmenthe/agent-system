"""The vendored statechart skill: package contract, its offline wrapper, and one real run when TLC can run here."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from skill_system import content_hash
from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "statechart"
RUN = SKILL_ROOT / "scripts" / "run"
PSTACK_REVISION = "0b46ec399d55f2829e88822998f53b84944837d3"
JAR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "tla2tools/1.7.4/tla2tools.jar"
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

SPEC = """---- MODULE Door ----
VARIABLE open
Init == open = FALSE
Open == ~open /\\ open' = TRUE
Close == open /\\ open' = FALSE
Next == Open \\/ Close
NeverOpen == ~open
====
"""

# TLC's -tool output for SPEC, trimmed to the messages the verdict and the plain text read.
TLC_OUT = """@!@!@STARTMSG 2262:0 @!@!@
TLC2 Version 2.19 of 08 August 2024 (rev: 5a47802)
@!@!@ENDMSG 2262 @!@!@
Parsing file /tmp/example/Door.tla
@!@!@STARTMSG 2190:0 @!@!@
Finished computing initial states: 1 distinct state generated at 2026-11-26 18:02:02.
@!@!@ENDMSG 2190 @!@!@
@!@!@STARTMSG 2110:1 @!@!@
Invariant NeverOpen is violated.
@!@!@ENDMSG 2110 @!@!@
@!@!@STARTMSG 2121:1 @!@!@
The behavior up to this point is:
@!@!@ENDMSG 2121 @!@!@
@!@!@STARTMSG 2217:4 @!@!@
1: <Initial predicate>
open = FALSE

@!@!@ENDMSG 2217 @!@!@
@!@!@STARTMSG 2217:4 @!@!@
2: <Open line 4, col 9 to line 4, col 29 of module Door>
open = TRUE

@!@!@ENDMSG 2217 @!@!@
@!@!@STARTMSG 2199:0 @!@!@
2 states generated, 2 distinct states found, 0 states left on queue.
@!@!@ENDMSG 2199 @!@!@
"""

# Reads each TLC output file as a string and through run.ts's file reader; prints what the compiler takes from it.
READ_TLC_OUT = """
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
const [scripts, ...files] = process.argv.slice(1);
const load = (name) => import(pathToFileURL(path.join(scripts, name)).href);
const { readMessages } = await load("frontends/messages.ts");
const { readVerdict } = await load("frontends/verdict.ts");
const { plainText } = await load("backends/plain-text.ts");
const { fileLines } = await load("run.ts");
const read = (lines) => {
  const parts = [...readMessages(lines())];
  return { ...readVerdict(parts), plain: [...plainText(parts)].join("") };
};
console.log(JSON.stringify(files.map((f) => [read(() => fs.readFileSync(f, "utf8")), read(() => fileLines(f))])));
"""


def node_runs_typescript() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    major, minor = (int(part) for part in subprocess.run(
        [node, "--version"], capture_output=True, text=True, check=True,
    ).stdout.strip().lstrip("v").split(".")[:2])
    return major >= 24 or (major, minor) >= (23, 6) or (major == 22 and minor >= 18)


class StatechartSkillTests(unittest.TestCase):
    def test_package_is_explicit_only_attributed_and_without_upstream_tests(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "statechart"), r"^sha256:")
        self.assertIn("disable-model-invocation: true", (SKILL_ROOT / "SKILL.md").read_text())
        self.assertIn("allow_implicit_invocation: false", (SKILL_ROOT / "agents/openai.yaml").read_text())
        self.assertTrue((SKILL_ROOT / "LICENSE").is_file())
        self.assertIn(PSTACK_REVISION, (SKILL_ROOT / "NOTICE.md").read_text())
        self.assertFalse((SKILL_ROOT / "scripts/test").exists())

    def test_registry_record_names_its_source_and_content(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["statechart"]
        self.assertEqual("skills/statechart", record["source"])
        self.assertEqual(["~/.agents/skills/statechart"], record["install_targets"])
        self.assertEqual("MIT", record["provenance"]["license"])
        self.assertEqual(PSTACK_REVISION, record["provenance"]["reference_revision"])
        self.assertEqual(content_hash(SKILL_ROOT), record["provenance"]["revision"])

    def test_every_link_resolves_inside_the_package(self) -> None:
        root = SKILL_ROOT.resolve()
        for path in root.rglob("*.md"):
            for raw in LINK.findall(path.read_text()):
                target = raw.split("#", 1)[0].strip()
                if not target or target.startswith(("https://", "http://")):
                    continue
                with self.subTest(path=path.name, target=target):
                    resolved = (path.parent / target).resolve()
                    self.assertTrue(resolved.is_relative_to(root))
                    self.assertTrue(resolved.is_file())

    def test_wrapper_refuses_a_missing_or_unpinned_jar_without_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrong = Path(temporary) / "tla2tools.jar"
            wrong.write_bytes(b"not the pinned jar")
            for jar, message in ((Path(temporary) / "absent.jar", "no tla2tools.jar"), (wrong, "not the pinned")):
                with self.subTest(jar=jar.name):
                    result = subprocess.run(
                        [str(RUN), "Door.tla", "--out", str(Path(temporary) / "chart")],
                        capture_output=True, text=True, timeout=30, env={**os.environ, "TLA2TOOLS": str(jar)},
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn(message, result.stderr)
                    self.assertFalse((Path(temporary) / "chart").exists())

    @unittest.skipUnless(JAR.is_file() and node_runs_typescript(), "needs the cached tla2tools.jar and Node 22.18+")
    def test_a_broken_rule_is_reported_by_name(self) -> None:
        unset = {key: value for key, value in os.environ.items() if key not in ("TLA2TOOLS", "JAVA")}
        # A relative jar path is resolved against the caller's directory, though upstream starts Java elsewhere.
        for name, env, cwd in (("cached jar", unset, None),
                               ("relative jar", {**unset, "TLA2TOOLS": JAR.name}, JAR.parent)):
            with self.subTest(name), tempfile.TemporaryDirectory() as temporary:
                spec = Path(temporary) / "Door.tla"
                spec.write_text(SPEC)
                spec.with_suffix(".cfg").write_text("INIT Init\nNEXT Next\nINVARIANT NeverOpen\n")
                out = Path(temporary) / "chart"
                result = subprocess.run(
                    [str(RUN), str(spec), "--out", str(out)],
                    capture_output=True, text=True, timeout=120, env=env, cwd=cwd,
                )
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn("NeverOpen breaks", (out / "report.md").read_text())
                self.assertIn("stateDiagram", (out / "chart.mmd").read_text())

    @unittest.skipUnless(JAR.is_file() and node_runs_typescript(), "needs the cached tla2tools.jar and Node 22.18+")
    def test_a_spec_sany_cannot_read_gets_its_line_and_column_not_a_java_stack_trace(self) -> None:
        unset = {key: value for key, value in os.environ.items() if key not in ("TLA2TOOLS", "JAVA")}
        for what, body, where in (
            ("a parse error", "Init == x = = 0\nNext == x' = x", r'Encountered "0" at line 3, column 15'),
            ("an unknown name", "Init == x = 0\nNext == x' = y",
             r"line 4, col 14 to line 4, col 14 of module Broken\n+Unknown operator: `y'\."),
        ):
            with self.subTest(what), tempfile.TemporaryDirectory() as temporary:
                spec = Path(temporary) / "Broken.tla"
                spec.write_text(f"---- MODULE Broken ----\nVARIABLE x\n{body}\n====\n")
                spec.with_suffix(".cfg").write_text("INIT Init\nNEXT Next\n")
                out = Path(temporary) / "chart"
                result = subprocess.run(
                    [str(RUN), str(spec), "--out", str(out)],
                    capture_output=True, text=True, timeout=120, env=unset,
                )
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertRegex(result.stderr, r"(?m)^SANY could not read .*Broken\.tla \(exit 1\):\n")
                self.assertRegex(result.stderr, where)
                self.assertNotRegex(result.stderr, r"(?m)^\s+at tla2sany\.|Exception in thread")
                self.assertFalse(out.exists())

    @unittest.skipUnless(node_runs_typescript(), "needs Node 22.18+")
    def test_tlc_output_with_windows_line_ends_reads_as_with_unix_ones(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            unix, windows = Path(temporary) / "unix.out", Path(temporary) / "windows.out"
            unix.write_bytes(TLC_OUT.encode())
            windows.write_bytes(TLC_OUT.replace("\n", "\r\n").encode())
            result = subprocess.run(
                ["node", "--disable-warning=ExperimentalWarning", "--input-type=module", "-e", READ_TLC_OUT,
                 str(SKILL_ROOT / "scripts"), str(unix), str(windows)],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        (unix_text, unix_file), (windows_text, windows_file) = json.loads(result.stdout)
        self.assertEqual({"kind": "invariant", "name": "NeverOpen"}, unix_text["broke"])
        self.assertEqual(2, unix_text["distinct"])
        for name, read in (("file, unix", unix_file), ("string, windows", windows_text), ("file, windows", windows_file)):
            with self.subTest(name):
                self.assertEqual(unix_text, read)

    @unittest.skipUnless(JAR.is_file() and node_runs_typescript(), "needs the cached tla2tools.jar and Node 22.18+")
    def test_skill_install_view_reads_a_two_skill_counterexample(self) -> None:
        # The view must keep up with SkillInstall.tla: a renamed variable shows up as `undefined` or a crash.
        target = ROOT / "verification" / "skill-install"
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "chart"
            result = subprocess.run(
                [str(RUN), "SkillInstall.tla", "--config", "mutations/g-rollback-restores-whole-state.cfg",
                 "--view", "view.mjs", "--out", str(out)],
                capture_output=True, text=True, timeout=120, cwd=target,
            )
            self.assertEqual(1, result.returncode, result.stderr)
            report = (out / "report.md").read_text()
        self.assertIn("RollbackStaysOnItsSkill breaks", report)
        self.assertIn("Y: ", report)
        self.assertNotIn("undefined", report)


if __name__ == "__main__":
    unittest.main()
