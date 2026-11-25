"""create-formal-verification-skill contract and its bundled runner's coverage contract; no Java or TLC runs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "create-formal-verification-skill"
RUNNER = SKILL_ROOT / "scripts" / "check"
SKILL = ".agents/skills/verify-store/SKILL.md"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


class CoveredRepository:
    """A git repository with one verification target whose manifest selects no checks."""

    def __init__(self, root: Path) -> None:
        self.root = root
        git(root, "init", "-q")
        self.write("store.py", "class Store:\n    def save(self):\n        return 1\n")
        self.write("run.sh", "stop() {\n  kill \"$1\"\n}\n# begin loop\nwhile :; do\n  sleep 1\ndone\n# end loop\n")
        self.write(SKILL, "Sync commit: <sync-commit>.\n")
        coverage = [
            {"file": "store.py", "kind": "py-function", "unit": "Store.save", "sha256": ""},
            {"file": "run.sh", "kind": "sh-function", "unit": "stop", "sha256": ""},
            {"file": "run.sh", "kind": "sh-region", "unit": "loop", "from": "# begin loop",
             "to": "# end loop", "sha256": ""},
        ]
        manifest = {"spec": "Store.tla", "skill": SKILL, "tlaTools": {}, "checks": [],
                    "coverage": {"syncCommit": "", "code": coverage}}
        self.write("verification/store/manifest.json", json.dumps(manifest, indent=2) + "\n")
        shutil.copy(RUNNER, root / "verification" / "check")
        self.commit()

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def edit(self, name: str, old: str, new: str) -> None:
        path = self.root / name
        path.write_text(path.read_text().replace(old, new))

    def commit(self) -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "change")
        return git(self.root, "rev-parse", "HEAD")[:12]

    def check(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(self.root / "verification" / "check"), "store", *args],
            capture_output=True, text=True, timeout=60, env=env,
        )

    def manifest(self) -> dict:
        return json.loads((self.root / "verification/store/manifest.json").read_text())

    def sync_commit(self) -> str:
        return self.manifest()["coverage"]["syncCommit"][:12]


# TLC as the runner sees it: a `java` on PATH that prints a recorded run. FAKE_TLC_SLEEP holds it after a progress
# line, the way a state space too large for its budget would.
FAKE_JAVA = """#!/usr/bin/env python3
import os, sys, time
if sys.argv[1:] == ["-version"]:
    sys.exit(0)
print("Progress(5) at 2026-10-27 10:00:00: 1,234 states generated, 1,200 distinct states found", flush=True)
time.sleep(float(os.environ.get("FAKE_TLC_SLEEP", "0")))
sys.stdout.write(open(os.environ["FAKE_TLC_LOG"]).read())
"""
# TLC prints a long value over several indented lines.
VIOLATION = """Error: Invariant Safe is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ sigs = [ a |-> 1,
            b |-> 2 ]
/\\ x = 0

State 2: <Bump line 9, col 1 to line 10, col 20 of module Store>
/\\ sigs = [ a |-> 1,
            b |-> 3 ]
/\\ x = 0

12 states generated, 7 distinct states found, 0 states left on queue.
"""

# A liveness counterexample as TLC 1.7.4 prints it: the trace ends by looping back to an earlier state, or stuttering.
LOOP = """Error: Temporal properties were violated.

Error: The following behavior constitutes a counter-example:

State 1: <Initial predicate>
/\\ x = 0
/\\ y = 0

State 2: <Inc line 5, col 8 to line 5, col 26 of module Store>
/\\ x = 1
/\\ y = 0

State 3: <Inc line 5, col 8 to line 5, col 26 of module Store>
/\\ x = 2
/\\ y = 0

Back to state 2: <Back line 6, col 9 to line 6, col 23 of module Store>

4 states generated, 3 distinct states found, 0 states left on queue.
"""
STUTTER = LOOP.replace("Back to state 2: <Back line 6, col 9 to line 6, col 23 of module Store>", "State 4: Stuttering")
# An action from an instantiated module carries its instance name, as in `C!Back`.
QUALIFIED = LOOP.replace("<Inc line", "<C!Inc line").replace("<Back line", "<C!Back line")


class FakeTlc:
    """A fake java and a pinned jar whose digest the manifest records, so the runner's TLC path runs end to end."""

    def __init__(self, repo: CoveredRepository, scratch: Path, check: dict) -> None:
        (scratch / "bin").mkdir()
        java = scratch / "bin" / "java"
        java.write_text(FAKE_JAVA)
        java.chmod(0o755)
        jar = scratch / "cache" / "tla2tools" / "test" / "tla2tools.jar"
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"not a real jar")
        (scratch / "tlc.log").write_text(VIOLATION)
        manifest = repo.manifest()
        manifest["tlaTools"] = {"version": "test", "url": "http://invalid.example/tla2tools.jar",
                                "sha256": hashlib.sha256(b"not a real jar").hexdigest()}
        manifest["checks"] = [{"config": "store.cfg", "quick": True, "what": "the store stays safe", **check}]
        repo.write("verification/store/manifest.json", json.dumps(manifest, indent=2) + "\n")
        self.env = {**os.environ, "PATH": f"{scratch / 'bin'}{os.pathsep}{os.environ['PATH']}",
                    "XDG_CACHE_HOME": str(scratch / "cache"), "FAKE_TLC_LOG": str(scratch / "tlc.log")}


class CreateFormalVerificationSkillTests(unittest.TestCase):
    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "create-formal-verification-skill"), r"^sha256:")
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("disable-model-invocation: true", (SKILL_ROOT / "SKILL.md").read_text())
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$create-formal-verification-skill", metadata)

    def test_this_repository_verifies_with_the_bundled_runner(self) -> None:
        self.assertEqual(RUNNER.read_bytes(), (ROOT / "verification" / "check").read_bytes())

    def test_runner_outside_a_repository_explains_itself(self) -> None:
        # The installed skill's copy is a template, not inside the repository it verifies.
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "check"
            shutil.copy(RUNNER, runner)
            usage = subprocess.run([sys.executable, "-B", str(runner), "--help"], capture_output=True, text=True)
            result = subprocess.run([sys.executable, "-B", str(runner), "store"], capture_output=True, text=True)
        self.assertEqual(0, usage.returncode)
        self.assertIn("--update-coverage", usage.stdout)
        self.assertEqual(2, result.returncode)
        self.assertIn("is not in a git repository; copy check into", result.stderr)

    def test_runner_reports_changed_coverage_and_keeps_the_skill_sync_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = CoveredRepository(Path(temporary))
            self.assertEqual(0, repo.check("--update-coverage").returncode)
            first = repo.sync_commit()
            # The first sync fills in the skill's <sync-commit>, so the next check needs no hand edit.
            self.assertEqual(f"Sync commit: {first}.\n", (repo.root / SKILL).read_text())
            passed = repo.check()
            self.assertEqual(0, passed.returncode, passed.stderr)

            repo.edit("store.py", "return 1", "return 2")
            second = repo.commit()
            drift = repo.check()
            self.assertEqual(1, drift.returncode)
            self.assertIn(f"covered code changed since {first}: store.py Store.save", drift.stderr)
            self.assertNotIn("run.sh", drift.stderr)

            self.assertEqual(0, repo.check("--update-coverage").returncode)
            self.assertEqual(second, repo.sync_commit())
            self.assertEqual(f"Sync commit: {second}.\n", (repo.root / SKILL).read_text())
            self.assertEqual(0, repo.check().returncode)

            repo.edit("run.sh", "sleep 1", "sleep 2")
            repo.edit("run.sh", 'kill "$1"', 'kill -9 "$1"')
            drift = repo.check()
            self.assertEqual(1, drift.returncode)
            self.assertIn("run.sh stop", drift.stderr)
            self.assertIn("run.sh loop", drift.stderr)
            refused = repo.check("--update-coverage")
            self.assertEqual(2, refused.returncode)
            self.assertIn("covered files differ from HEAD", refused.stderr)
            self.assertEqual(second, repo.sync_commit())

    def test_a_skill_that_cannot_take_the_sync_commit_stops_the_update_before_it_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = CoveredRepository(Path(temporary))
            repo.write(SKILL, "No commit named here.\n")
            repo.commit()
            before = repo.manifest()
            refused = repo.check("--update-coverage")
            self.assertEqual(2, refused.returncode)
            self.assertIn(f"{SKILL} does not name the sync commit <sync-commit>", refused.stderr)
            self.assertEqual(before, repo.manifest())
            self.assertEqual("No commit named here.\n", (repo.root / SKILL).read_text())

    def test_a_counterexample_shows_every_line_of_a_multiline_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "repo").mkdir()
            repo = CoveredRepository(Path(temporary) / "repo")
            tlc = FakeTlc(repo, Path(temporary), {"expect": "pass"})
            result = repo.check(env=tlc.env)
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("store.cfg: FAIL: Safe violated (7 states", result.stdout)
        self.assertIn("  1. Initial: (initial), sigs=[ a |-> 1, b |-> 2 ], x=0\n", result.stdout)
        self.assertIn("  2. Bump: sigs=[ a |-> 1, b |-> 3 ]\n", result.stdout)

    def test_a_liveness_counterexample_shows_where_it_loops_or_stutters(self) -> None:
        for log, step, last in ((LOOP, "Inc", "  then Back: back to step 2, and on from there forever\n"),
                                (STUTTER, "Inc", "  4. Stuttering: nothing changes from here on\n"),
                                (QUALIFIED, "C!Inc", "  then C!Back: back to step 2, and on from there forever\n")):
            with self.subTest(last=last.strip()), tempfile.TemporaryDirectory() as temporary:
                (Path(temporary) / "repo").mkdir()
                repo = CoveredRepository(Path(temporary) / "repo")
                tlc = FakeTlc(repo, Path(temporary), {"expect": "pass"})
                repo.write("verification/store/store.cfg", "PROPERTY Live\n")
                (Path(temporary) / "tlc.log").write_text(log)
                result = repo.check(env=tlc.env)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn("store.cfg: FAIL: Live violated", result.stdout)
                self.assertIn(f"  3. {step}: x=2\n" + last, result.stdout)

    def test_a_check_over_its_time_budget_could_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "repo").mkdir()
            repo = CoveredRepository(Path(temporary) / "repo")
            tlc = FakeTlc(repo, Path(temporary), {"expect": "pass", "timeoutSeconds": 1})
            result = repo.check(env={**tlc.env, "FAKE_TLC_SLEEP": "30"})
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("could not run: store.cfg exceeded its 1 s timeoutSeconds (last progress: 1,200 distinct "
                      "states)", result.stderr)


if __name__ == "__main__":
    unittest.main()
