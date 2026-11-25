from __future__ import annotations

import unittest

from scan_helpers import TemporaryGitRepo

from runtime.analysis.git_snapshot import capture_snapshot
from runtime.analysis.model import PythonTarget, PythonTargetSource
from runtime.analysis.python_target import PythonTargetError, resolve_python_targets


class PythonTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TemporaryGitRepo()

    def tearDown(self) -> None:
        self.repo.close()

    def _range(self, pyproject: str = "", path: str = "module.py"):
        if pyproject:
            self.repo.write("pyproject.toml", pyproject)
        self.repo.write(path, "VALUE = 1\n")
        before = self.repo.commit("base")
        self.repo.write(path, "VALUE = 2\n")
        after = self.repo.commit("change")
        return capture_snapshot(self.repo.path, before, after), before, after

    def test_explicit_target_has_precedence(self) -> None:
        snapshot, _, _ = self._range(
            '[project]\nname = "example"\nrequires-python = ">=3.12"\n'
        )

        resolution = resolve_python_targets(snapshot, explicit=PythonTarget.PY314)

        self.assertEqual(PythonTarget.PY314, resolution.primary)
        self.assertEqual(PythonTargetSource.EXPLICIT, resolution.source)
        self.assertEqual(PythonTarget.PY314, resolution.target_for("module.py"))

    def test_uses_exact_committed_requires_python_lower_bound(self) -> None:
        snapshot, _, _ = self._range(
            '[project]\nname = "example"\nrequires-python = ">=3.12.1,<4"\n'
        )
        self.repo.write(
            "pyproject.toml",
            '[project]\nname = "example"\nrequires-python = ">=3.14"\n',
        )

        resolution = resolve_python_targets(snapshot)

        self.assertEqual(PythonTarget.PY312, resolution.primary)
        self.assertEqual(PythonTargetSource.REQUIRES_PYTHON, resolution.source)

    def test_uses_documented_fleet_fallback_without_lower_bound(self) -> None:
        snapshot, _, _ = self._range(
            '[project]\nname = "example"\nrequires-python = "<4"\n'
        )

        resolution = resolve_python_targets(snapshot)

        self.assertEqual(PythonTarget.PY313, resolution.primary)
        self.assertEqual(PythonTargetSource.FLEET_FALLBACK, resolution.source)

    def test_unsupported_minimum_fails_loudly(self) -> None:
        snapshot, _, _ = self._range(
            '[project]\nname = "example"\nrequires-python = ">=3.11"\n'
        )

        with self.assertRaisesRegex(PythonTargetError, "unsupported minimum"):
            resolve_python_targets(snapshot)

    def test_nested_packages_form_deterministic_package_map(self) -> None:
        self.repo.write(
            "pyproject.toml",
            '[project]\nname = "root"\nrequires-python = ">=3.12"\n',
        )
        self.repo.write(
            "packages/new/pyproject.toml",
            '[project]\nname = "new"\nrequires-python = ">=3.14"\n',
        )
        self.repo.write("root.py", "ROOT = 1\n")
        self.repo.write("packages/new/new.py", "NEW = 1\n")
        before = self.repo.commit("base")
        self.repo.write("root.py", "ROOT = 2\n")
        self.repo.write("packages/new/new.py", "NEW = 2\n")
        after = self.repo.commit("change")
        snapshot = capture_snapshot(self.repo.path, before, after)

        resolution = resolve_python_targets(snapshot)

        self.assertEqual(PythonTargetSource.PACKAGE_MAP, resolution.source)
        self.assertEqual(PythonTarget.PY312, resolution.primary)
        self.assertEqual(PythonTarget.PY312, resolution.target_for("root.py"))
        self.assertEqual(
            PythonTarget.PY314,
            resolution.target_for("packages/new/new.py"),
        )
        self.assertEqual(
            ((".", PythonTarget.PY312), ("packages/new", PythonTarget.PY314)),
            resolution.package_map,
        )

    def test_duplicate_requires_python_is_rejected_not_guessed(self) -> None:
        snapshot, _, _ = self._range(
            '[project]\nrequires-python = ">=3.12"\nrequires-python = ">=3.13"\n'
        )

        with self.assertRaisesRegex(PythonTargetError, "duplicate"):
            resolve_python_targets(snapshot)


if __name__ == "__main__":
    unittest.main()
