from __future__ import annotations

import json
import os
import signal
import tempfile
import unittest
from pathlib import Path

from scan_helpers import TemporaryGitRepo

from runtime.analysis.git_snapshot import capture_snapshot
from runtime.analysis.model import AnalysisStatus, PythonTarget
from runtime.analysis.python_target import resolve_python_targets
from runtime.analysis.ruff_runner import (
    EXPECTED_RUFF_VERSION,
    RuffConfig,
    run_ruff,
)


class RuffRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TemporaryGitRepo()

    def tearDown(self) -> None:
        self.repo.close()

    def _snapshot(self, files=None):
        rows = files or {"module.py": "VALUE = 1\n"}
        for path, source in rows.items():
            self.repo.write(path, source)
        before = self.repo.commit("base")
        for path, source in rows.items():
            self.repo.write(path, source.replace("1", "2"))
        after = self.repo.commit("change")
        return capture_snapshot(self.repo.path, before, after)

    def _fake_ruff(self, body: str, version: str = EXPECTED_RUFF_VERSION) -> Path:
        script = self.repo.write(
            "fake_ruff.py",
            "#!/usr/bin/env python3\n"
            "import os\n"
            "import sys\n"
            "log = os.environ.get('FAKE_RUFF_LOG')\n"
            "if log:\n"
            "    with open(log, 'a') as stream:\n"
            "        stream.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "if '--version' in sys.argv:\n"
            "    print({!r})\n"
            "else:\n{}\n".format(
                version,
                "\n".join("    " + line for line in body.splitlines()),
            ),
        )
        os.chmod(script, 0o755)
        return script

    def test_validates_version_once_and_splits_package_targets(self) -> None:
        self.repo.write(
            "pyproject.toml",
            '[project]\nrequires-python = ">=3.12"\n',
        )
        self.repo.write(
            "new/pyproject.toml",
            '[project]\nrequires-python = ">=3.14"\n',
        )
        self.repo.write("root.py", "ROOT = 1\n")
        self.repo.write("new/new.py", "NEW = 1\n")
        before = self.repo.commit("base")
        self.repo.write("root.py", "ROOT = 2\n")
        self.repo.write("new/new.py", "NEW = 2\n")
        after = self.repo.commit("change")
        snapshot = capture_snapshot(self.repo.path, before, after)
        targets = resolve_python_targets(snapshot)
        fake = self._fake_ruff("print('[]')")
        log = self.repo.path / "ruff.log"

        old_log = os.environ.get("FAKE_RUFF_LOG")
        os.environ["FAKE_RUFF_LOG"] = str(log)
        try:
            result = run_ruff(snapshot, targets, config=RuffConfig(binary=fake))
        finally:
            if old_log is None:
                os.environ.pop("FAKE_RUFF_LOG", None)
            else:
                os.environ["FAKE_RUFF_LOG"] = old_log

        self.assertEqual(AnalysisStatus.OK, result.status)
        invocations = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, sum("--version" in row for row in invocations))
        checks = [row for row in invocations if row.startswith("check ")]
        self.assertEqual(2, len(checks))
        self.assertTrue(any("--target-version py312" in row for row in checks))
        self.assertTrue(any("--target-version py314" in row for row in checks))

    def test_missing_binary_and_version_mismatch_are_typed(self) -> None:
        snapshot = self._snapshot()
        targets = resolve_python_targets(snapshot)

        missing = run_ruff(
            snapshot,
            targets,
            config=RuffConfig(binary=self.repo.path / "missing"),
        )
        mismatch = run_ruff(
            snapshot,
            targets,
            config=RuffConfig(binary=self._fake_ruff("print('[]')", "ruff 0.15.0")),
        )

        self.assertEqual(AnalysisStatus.UNAVAILABLE, missing.status)
        self.assertEqual(AnalysisStatus.INCOMPATIBLE_RUFF_CONTRACT, mismatch.status)

    def test_code_less_syntax_diagnostic_is_not_clean(self) -> None:
        snapshot = self._snapshot()
        targets = resolve_python_targets(snapshot)
        payload = [
            {
                "code": None,
                "message": "SyntaxError: invalid syntax",
                "filename": "after/module.py",
                "location": {"row": 1, "column": 1},
            }
        ]
        fake = self._fake_ruff("print({!r})".format(json.dumps(payload)))

        result = run_ruff(snapshot, targets, config=RuffConfig(binary=fake))

        self.assertEqual(AnalysisStatus.INCOMPATIBLE_PYTHON_TARGET, result.status)
        self.assertIn("module.py", result.issues[0])

    def test_timeout_reaps_child_and_removes_temporary_tree(self) -> None:
        snapshot = self._snapshot()
        targets = resolve_python_targets(snapshot)
        fake = self._fake_ruff("import time\ntime.sleep(5)\nprint('[]')")
        with tempfile.TemporaryDirectory() as parent:
            result = run_ruff(
                snapshot,
                targets,
                config=RuffConfig(
                    binary=fake,
                    timeout_seconds=0.1,
                    temporary_parent=Path(parent),
                ),
            )
            leftovers = tuple(Path(parent).iterdir())

        self.assertEqual(AnalysisStatus.TIMEOUT, result.status)
        self.assertEqual((), leftovers)

    def test_interrupt_reaps_child_and_removes_temporary_tree(self) -> None:
        snapshot = self._snapshot()
        targets = resolve_python_targets(snapshot)
        fake = self._fake_ruff("import time\ntime.sleep(5)\nprint('[]')")
        previous_handler = signal.getsignal(signal.SIGALRM)

        def interrupt(_signum, _frame):
            raise KeyboardInterrupt()

        with tempfile.TemporaryDirectory() as parent:
            signal.signal(signal.SIGALRM, interrupt)
            # Leave ample room for the one-time version subprocess; the check
            # subprocess then blocks for five seconds and receives the signal.
            signal.setitimer(signal.ITIMER_REAL, 0.75)
            try:
                result = run_ruff(
                    snapshot,
                    targets,
                    config=RuffConfig(
                        binary=fake,
                        timeout_seconds=5,
                        temporary_parent=Path(parent),
                    ),
                )
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
            leftovers = tuple(Path(parent).iterdir())

        self.assertEqual(AnalysisStatus.CANCELLED, result.status)
        self.assertEqual((), leftovers)

    def test_real_contract_reports_metric_and_correctness_diagnostics(self) -> None:
        self.repo.write("module.py", "def choose(items=None):\n    return items\n")
        before = self.repo.commit("base")
        branches = "\n".join(
            "    if value == {0}:\n        return {0}".format(index)
            for index in range(12)
        )
        self.repo.write(
            "module.py",
            "def choose(items=[]):\n    return items\n\n"
            "def complex(value):\n{}\n    return -1\n".format(branches),
        )
        after = self.repo.commit("diagnostics")
        snapshot = capture_snapshot(self.repo.path, before, after)
        targets = resolve_python_targets(snapshot, explicit=PythonTarget.PY313)

        result = run_ruff(snapshot, targets)

        self.assertEqual(AnalysisStatus.OK, result.status, result.issues)
        codes = {item.code for item in result.diagnostics if item.side == "after"}
        self.assertIn("B006", codes)
        self.assertIn("C901", codes)


if __name__ == "__main__":
    unittest.main()
