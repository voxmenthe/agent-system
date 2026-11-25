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
PSTACK_REVISION = "4dd1d05818d19792e7cd6e818f1667f95f7e1dbe"
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
