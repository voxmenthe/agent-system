from __future__ import annotations

import unittest

from scan_helpers import TemporaryGitRepo

from runtime.analysis.ast_spans import parse_python
from runtime.analysis.git_snapshot import capture_snapshot
from runtime.analysis.model import AnalysisStatus
from runtime.analysis.ruff_runner import RuffDiagnostic, RuffResult
from runtime.analysis.structural_policy import analyze_structural


class StructuralPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TemporaryGitRepo()

    def tearDown(self) -> None:
        self.repo.close()

    def _snapshot(self, before_source: str, after_source: str):
        self.repo.write("module.py", before_source)
        before = self.repo.commit("base")
        self.repo.write("module.py", after_source)
        after = self.repo.commit("change")
        snapshot = capture_snapshot(self.repo.path, before, after)
        item = snapshot.python_files[0]
        before_parsed = {
            item.path: parse_python(item.path, item.before_blob or b"")
        }
        after_parsed = {item.path: parse_python(item.path, item.after_blob or b"")}
        return snapshot, before_parsed, after_parsed

    @staticmethod
    def _metric(side: str, code: str, value: int, limit: int, row: int = 1):
        return RuffDiagnostic(
            side,
            "module.py",
            code,
            "metric ({} > {})".format(value, limit),
            row,
            1,
            value,
            limit,
        )

    def test_static_debt_and_improvement_do_not_become_regressions(self) -> None:
        snapshot, before_parsed, after_parsed = self._snapshot(
            "def work(value):\n    return value\n",
            "def work(value):\n    return value + 1\n",
        )
        report = RuffResult(
            AnalysisStatus.OK,
            "ruff 0.16.5",
            (
                self._metric("before", "C901", 20, 10),
                self._metric("after", "C901", 19, 10),
            ),
        )

        analysis = analyze_structural(
            snapshot, before_parsed, after_parsed, report
        )

        self.assertEqual((), analysis.signals)
        self.assertTrue(analysis.policy("static-structural-presence").matched)
        self.assertFalse(analysis.policy("structural-regression").matched)

    def test_material_c901_requires_same_function_corroboration(self) -> None:
        snapshot, before_parsed, after_parsed = self._snapshot(
            "def work(value):\n    return value\n",
            "def work(value):\n    if value:\n        return value\n    return 0\n",
        )
        report = RuffResult(
            AnalysisStatus.OK,
            "ruff 0.16.5",
            (
                self._metric("before", "C901", 11, 10),
                self._metric("after", "C901", 13, 10),
                self._metric("after", "PLR0912", 13, 12),
            ),
        )

        analysis = analyze_structural(
            snapshot, before_parsed, after_parsed, report
        )

        self.assertEqual({"C901", "PLR0912"}, {item.code for item in analysis.signals})
        self.assertTrue(analysis.policy("material-corroborated-regression").matched)
        self.assertTrue(analysis.auto_candidate.matched)

    def test_one_point_hotspot_drift_is_not_material(self) -> None:
        snapshot, before_parsed, after_parsed = self._snapshot(
            "def work(value):\n    return value\n",
            "def work(value):\n    return value + 1\n",
        )
        report = RuffResult(
            AnalysisStatus.OK,
            "ruff 0.16.5",
            (
                self._metric("before", "C901", 267, 10),
                self._metric("after", "C901", 268, 10),
                self._metric("before", "PLR0915", 617, 50),
                self._metric("after", "PLR0915", 620, 50),
            ),
        )

        analysis = analyze_structural(
            snapshot, before_parsed, after_parsed, report
        )

        self.assertTrue(analysis.policy("corroborated-structural-regression").matched)
        self.assertFalse(analysis.policy("material-corroborated-regression").matched)
        self.assertFalse(analysis.auto_candidate.matched)

    def test_correctness_is_new_changed_line_only_with_report_only_rules(self) -> None:
        snapshot, before_parsed, after_parsed = self._snapshot(
            "def factory():\n    return 1\n",
            "def factory(items=[]):\n    return items\n",
        )
        report = RuffResult(
            AnalysisStatus.OK,
            "ruff 0.16.5",
            (
                RuffDiagnostic(
                    "after",
                    "module.py",
                    "B006",
                    "Do not use mutable data structures for argument defaults",
                    1,
                    19,
                ),
                RuffDiagnostic(
                    "after",
                    "module.py",
                    "B023",
                    "Function definition does not bind loop variable",
                    1,
                    1,
                ),
                RuffDiagnostic(
                    "after",
                    "module.py",
                    "PLE1205",
                    "Too many arguments for logging format string",
                    1,
                    1,
                ),
            ),
        )

        analysis = analyze_structural(
            snapshot, before_parsed, after_parsed, report
        )

        by_code = {item.code: item for item in analysis.signals}
        self.assertEqual({"B006", "B023", "PLE1205"}, set(by_code))
        self.assertEqual("candidate-strict", by_code["B006"].evidence["disposition"])
        self.assertEqual("report-only", by_code["B023"].evidence["disposition"])
        self.assertEqual("report-only", by_code["PLE1205"].evidence["disposition"])
        self.assertEqual(("B006",), tuple(item.code for item in analysis.auto_candidate.signals))

    def test_multiset_matching_emits_only_the_additional_diagnostic(self) -> None:
        snapshot, before_parsed, after_parsed = self._snapshot(
            "def factory(value):\n    return value\n",
            "def factory(value):\n    return value + 1\n",
        )
        message = "Do not use mutable data structures for argument defaults"
        report = RuffResult(
            AnalysisStatus.OK,
            "ruff 0.16.5",
            (
                RuffDiagnostic("before", "module.py", "B006", message, 2, 1),
                RuffDiagnostic("after", "module.py", "B006", message, 2, 1),
                RuffDiagnostic("after", "module.py", "B006", message, 2, 2),
            ),
        )

        analysis = analyze_structural(
            snapshot, before_parsed, after_parsed, report
        )

        self.assertEqual(1, len(analysis.signals))
        self.assertEqual(2, analysis.signals[0].column)


if __name__ == "__main__":
    unittest.main()
