from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scan_helpers import TemporaryGitRepo

from runtime.analysis.evidence_package import ReviewScanConfig, scan_range
from runtime.analysis.git_snapshot import SnapshotConfig
from runtime.analysis.model import (
    AnalysisStatus,
    EvidenceLane,
    PythonTarget,
    PythonTargetSource,
)
from runtime.analysis.ruff_runner import EXPECTED_RUFF_VERSION, RuffConfig


class EvidencePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TemporaryGitRepo()

    def tearDown(self) -> None:
        self.repo.close()

    def test_non_python_range_skips_ruff_and_records_commit_order(self) -> None:
        self.repo.write("notes.txt", "one\n")
        before = self.repo.commit("base")
        self.repo.write("notes.txt", "two\n")
        after = self.repo.commit("change")

        with mock.patch(
            "runtime.analysis.evidence_package.run_ruff"
        ) as runner:
            result = scan_range(self.repo.path, before, after)

        runner.assert_not_called()
        evidence = result.evidence
        self.assertEqual(AnalysisStatus.SKIPPED_NO_PYTHON, evidence.health.status)
        self.assertEqual((after,), evidence.context.ordered_commits)
        self.assertFalse(evidence.attention)
        self.assertIsNone(evidence.ruff_version)

    def test_dirty_worktree_cannot_change_event_or_evidence(self) -> None:
        self.repo.write("module.py", "def choose(items=None):\n    return items\n")
        before = self.repo.commit("base")
        self.repo.write("module.py", "def choose(items=[]):\n    return items\n")
        after = self.repo.commit("change")

        first = scan_range(self.repo.path, before, after)
        self.repo.write("module.py", "def choose(items=None):\n    return items\n")
        second = scan_range(self.repo.path, before, after)

        self.assertEqual(first.evidence.event_id, second.evidence.event_id)
        self.assertEqual(first.evidence.to_json(), second.evidence.to_json())
        self.assertEqual(("B006",), tuple(signal.code for signal in first.evidence.signals))

    def test_every_selected_target_survives_without_first_n_truncation(self) -> None:
        before_source = "\n\n".join(
            "def function_{0}(items=None):\n    return items".format(index)
            for index in range(9)
        ) + "\n"
        after_source = before_source.replace("items=None", "items=[]")
        self.repo.write("module.py", before_source)
        before = self.repo.commit("base")
        self.repo.write("module.py", after_source)
        after = self.repo.commit("change")

        evidence = scan_range(self.repo.path, before, after).evidence

        self.assertTrue(evidence.attention)
        self.assertEqual(9, len(evidence.targets))
        self.assertEqual(9, len(evidence.signals))
        self.assertFalse(evidence.truncated)
        self.assertEqual(
            {target.id for target in evidence.targets},
            {identifier for signal in evidence.signals for identifier in signal.target_ids},
        )

    def test_parse_ambiguous_rename_target_and_scope_failures_are_typed(self) -> None:
        self.repo.write("broken.py", "def valid():\n    return 1\n")
        parse_before = self.repo.commit("parse base")
        self.repo.write("broken.py", "def broken(:\n    return 1\n")
        parse_after = self.repo.commit("parse change")
        parse_result = scan_range(self.repo.path, parse_before, parse_after)
        self.assertEqual(AnalysisStatus.INCONCLUSIVE_PARSE, parse_result.evidence.health.status)

        self.repo.write(
            "source.py",
            "\n".join("VALUE_{} = {}".format(index, index) for index in range(40)) + "\n",
        )
        rename_before = self.repo.commit("rename base")
        self.repo.git("mv", "source.py", "destination.py")
        self.repo.write(
            "destination.py",
            "\n".join(
                "VALUE_{} = {!r}".format(index, "changed" if index < 8 else index)
                for index in range(40)
            )
            + "\n",
        )
        rename_after = self.repo.commit("rename change")
        rename_result = scan_range(self.repo.path, rename_before, rename_after)
        self.assertEqual(AnalysisStatus.INCONCLUSIVE_RENAME, rename_result.evidence.health.status)

        self.repo.write(
            "pyproject.toml",
            '[project]\nrequires-python = ">=3.11"\n',
        )
        target_before = self.repo.commit("target base")
        self.repo.write("target.py", "VALUE = 1\n")
        target_after = self.repo.commit("target change")
        target_result = scan_range(self.repo.path, target_before, target_after)
        self.assertEqual(
            AnalysisStatus.INCOMPATIBLE_PYTHON_TARGET,
            target_result.evidence.health.status,
        )

        self.repo.write("one.py", "ONE = 1\n")
        scope_before = self.repo.commit("scope base")
        self.repo.write("one.py", "ONE = 2\n")
        self.repo.write("two.py", "TWO = 2\n")
        scope_after = self.repo.commit("scope change")
        scope_result = scan_range(
            self.repo.path,
            scope_before,
            scope_after,
            config=ReviewScanConfig(snapshot=SnapshotConfig(max_python_files=1)),
        )
        self.assertEqual(
            AnalysisStatus.INCONCLUSIVE_SCOPE_OVERFLOW,
            scope_result.evidence.health.status,
        )
        self.assertEqual(("one.py", "two.py"), scope_result.evidence.context.scope_files)

    def test_package_target_map_and_design_lanes_are_explicit(self) -> None:
        self.repo.write(
            "pyproject.toml",
            '[project]\nrequires-python = ">=3.12"\n',
        )
        self.repo.write(
            "new/pyproject.toml",
            '[project]\nrequires-python = ">=3.14"\n',
        )
        self.repo.write("root.py", "ROOT = 1\n")
        self.repo.write("new/port.py", "VALUE = 1\n")
        before = self.repo.commit("base")
        self.repo.write("root.py", "ROOT = 2\n")
        self.repo.write(
            "new/port.py",
            "from typing import Protocol\n\n"
            "class Port(Protocol):\n"
            "    def read(self, key): ...\n"
            "    def write(self, key, value): ...\n",
        )
        after = self.repo.commit("change")

        evidence = scan_range(self.repo.path, before, after).evidence

        self.assertEqual(PythonTargetSource.PACKAGE_MAP, evidence.python_target_source)
        self.assertEqual(PythonTarget.PY312, evidence.python_target)
        self.assertEqual(2, len(evidence.python_target_map))
        self.assertIn(EvidenceLane.DESIGN, {signal.lane for signal in evidence.signals})
        payload = evidence.to_dict()
        self.assertNotIn("score", json.dumps(payload).lower())
        self.assertNotIn("verdict", json.dumps(payload).lower())

    def test_auto_policy_is_computed_and_available_for_dogfooding(self) -> None:
        self.repo.write("module.py", "def choose(items=None):\n    return items\n")
        before = self.repo.commit("base")
        self.repo.write("module.py", "def choose(items=[]):\n    return items\n")
        after = self.repo.commit("change")

        result = scan_range(self.repo.path, before, after)

        self.assertTrue(result.auto_candidate.matched)
        self.assertTrue(result.auto_available)
        self.assertEqual("review-scan-suite", result.evidence.policies[0].name)

    def test_ruff_timeout_is_typed_target_incomplete_and_cleans_temp_state(self) -> None:
        self.repo.write("module.py", "VALUE = 1\n")
        before = self.repo.commit("base")
        self.repo.write("module.py", "VALUE = 2\n")
        after = self.repo.commit("change")
        fake = self.repo.write(
            "fake_ruff.py",
            "#!/usr/bin/env python3\n"
            "import sys,time\n"
            "if '--version' in sys.argv:\n"
            "    print({!r})\n"
            "else:\n"
            "    time.sleep(5)\n"
            "    print('[]')\n".format(EXPECTED_RUFF_VERSION),
        )
        os.chmod(fake, 0o755)

        with tempfile.TemporaryDirectory() as parent:
            result = scan_range(
                self.repo.path,
                before,
                after,
                config=ReviewScanConfig(
                    ruff=RuffConfig(
                        binary=fake,
                        timeout_seconds=0.1,
                        temporary_parent=Path(parent),
                    )
                ),
            )
            leftovers = tuple(Path(parent).iterdir())

        self.assertEqual(AnalysisStatus.TIMEOUT, result.evidence.health.status)
        self.assertFalse(result.evidence.health.target_complete)
        self.assertFalse(result.evidence.attention)
        self.assertEqual((), leftovers)


if __name__ == "__main__":
    unittest.main()
