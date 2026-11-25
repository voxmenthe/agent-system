from __future__ import annotations

import unittest

from scan_helpers import TemporaryGitRepo

from runtime.analysis.ast_spans import parse_python
from runtime.analysis.design_signals import analyze_design
from runtime.analysis.git_snapshot import capture_snapshot


class DesignSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TemporaryGitRepo()

    def tearDown(self) -> None:
        self.repo.close()

    def _analyze(self, before_files, after_files):
        for path, source in before_files.items():
            self.repo.write(path, source)
        before = self.repo.commit("base")
        for path, source in after_files.items():
            self.repo.write(path, source)
        after = self.repo.commit("change")
        snapshot = capture_snapshot(self.repo.path, before, after)
        parsed_before = {}
        parsed_after = {}
        for item in snapshot.python_files:
            if item.before_blob is not None:
                parsed_before[item.path] = parse_python(item.path, item.before_blob)
            if item.after_blob is not None:
                parsed_after[item.path] = parse_python(item.path, item.after_blob)
        return snapshot, analyze_design(snapshot, parsed_before, parsed_after)

    def test_cross_file_and_dead_code_have_exact_production_targets(self) -> None:
        snapshot, signals = self._analyze(
            {
                "pkg/a.py": "def first(value):\n    return value\n",
                "pkg/b.py": "def second(value):\n    return value\n",
                "tests/test_large.py": "def test_old():\n    assert True\n",
            },
            {
                "pkg/a.py": (
                    "def first(value):\n    return _normalize_payload(value)\n\n"
                    "def _normalize_payload(value):\n    return value.strip()\n\n"
                    "def accidental_dead_code():\n    return 1\n    print('unreachable')\n"
                ),
                "pkg/b.py": (
                    "from .a import _normalize_payload\n\n"
                    "def second(value):\n    return _normalize_payload(value)\n"
                ),
                "pkg/c.py": (
                    "from .a import _normalize_payload\n\n"
                    "def third(value):\n    return _normalize_payload(value)\n"
                ),
                "tests/test_large.py": "\n".join(
                    "def test_{}():\n    assert True".format(index)
                    for index in range(20)
                )
                + "\n",
            },
        )
        by_code = {signal.code: signal for signal in signals}

        self.assertEqual(4, len(snapshot.python_files))
        self.assertIn("DEAD_CODE_GROWTH", by_code)
        self.assertIn("REPEATED_CROSS_FILE_CHANGE", by_code)
        cross = by_code["REPEATED_CROSS_FILE_CHANGE"]
        self.assertEqual(3, cross.evidence["file_count"])
        self.assertEqual(["_normalize_payload"], cross.evidence["identifiers"])
        self.assertEqual(
            {"pkg/a.py", "pkg/b.py", "pkg/c.py"},
            {target.path for target in cross.targets},
        )
        self.assertFalse(
            any(target.path.startswith("tests/") for signal in signals for target in signal.targets)
        )

    def test_interface_delegation_and_low_usage_context_are_separate(self) -> None:
        _, signals = self._analyze(
            {"pkg/storage.py": "VALUE = 1\n"},
            {
                "pkg/storage.py": (
                    "from abc import ABC, abstractmethod\n\n"
                    "class StoragePort(ABC):\n"
                    "    @abstractmethod\n    def get(self, key):\n        raise NotImplementedError\n\n"
                    "    @abstractmethod\n    def put(self, key, value):\n        raise NotImplementedError\n\n"
                    "class FileStorage(StoragePort):\n"
                    "    def get(self, key):\n        return key\n\n"
                    "    def put(self, key, value):\n        return value\n\n"
                    "class StorageFacade:\n"
                    "    def get(self, key):\n        return self._storage.get(key)\n\n"
                    "    def put(self, key, value):\n        return self._storage.put(key, value)\n\n"
                    "    def delete(self, key):\n        return self._storage.delete(key)\n"
                )
            },
        )
        by_code = {signal.code: signal for signal in signals}

        self.assertIn("INTERFACE_SURFACE_GROWTH", by_code)
        self.assertIn("THIN_DELEGATION_LAYER_GROWTH", by_code)
        self.assertIn("LOW_USAGE_INTERFACE_GROWTH", by_code)
        self.assertEqual("design-context", by_code["LOW_USAGE_INTERFACE_GROWTH"].lane.value)
        self.assertEqual(1, by_code["LOW_USAGE_INTERFACE_GROWTH"].evidence["declared_subclasses"])

    def test_parameter_propagation_requires_forward_only_existing_functions(self) -> None:
        _, signals = self._analyze(
            {
                "pkg/a.py": (
                    "from .b import sink\n\n"
                    "def outer(payload):\n    return middle(payload)\n\n"
                    "def middle(payload):\n    return sink(payload)\n"
                ),
                "pkg/b.py": (
                    "def consume(payload, token=None):\n    return payload\n\n"
                    "def sink(payload):\n    return consume(payload)\n"
                ),
            },
            {
                "pkg/a.py": (
                    "from .b import sink\n\n"
                    "def outer(payload, trace_token):\n    return middle(payload, trace_token)\n\n"
                    "def middle(payload, trace_token):\n    return sink(payload, trace_token)\n"
                ),
                "pkg/b.py": (
                    "def consume(payload, token=None):\n    return payload\n\n"
                    "def sink(payload, trace_token):\n    return consume(payload, trace_token)\n"
                ),
            },
        )
        match = next(signal for signal in signals if signal.code == "PARAMETER_PROPAGATION_GROWTH")

        self.assertEqual(["trace_token"], match.evidence["parameters"])
        self.assertEqual(3, match.evidence["minimum_forward_only_functions"])

    def test_disjoint_responsibility_and_runtime_cycle_are_detected(self) -> None:
        before_service = (
            "class Service:\n"
            "    def __init__(self):\n        self.items = []\n        self.limit = 10\n\n"
            "    def add(self, value):\n        self.items.append(value)\n\n"
            "    def remove(self, value):\n        self.items.remove(value)\n\n"
            "    def full(self):\n        return len(self.items) >= self.limit\n\n"
            "    def clear(self):\n        self.items.clear()\n\n"
            "    def size(self):\n        return len(self.items)\n"
        )
        after_service = before_service.rstrip() + (
            "\n\n    def audit(self, event):\n"
            "        if self.audit_enabled:\n            self.audit_log.append(event)\n"
            "            if len(self.audit_log) > 100:\n                self.audit_log.pop(0)\n"
            "        return len(self.audit_log)\n\n"
            "    def clear_audit(self):\n"
            "        if self.audit_enabled:\n            count = len(self.audit_log)\n"
            "            self.audit_log.clear()\n            return count\n"
            "        return 0\n"
        )
        after_service = after_service.replace(
            "        self.limit = 10\n",
            "        self.limit = 10\n        self.audit_log = []\n        self.audit_enabled = True\n",
        )
        _, signals = self._analyze(
            {
                "pkg/service.py": before_service,
                "pkg/left.py": "class Left:\n    pass\n",
                "pkg/right.py": "class Right:\n    pass\n",
            },
            {
                "pkg/service.py": after_service,
                "pkg/left.py": "from .right import Right\n\nclass Left:\n    pass\n",
                "pkg/right.py": "from .left import Left\n\nclass Right:\n    pass\n",
            },
        )
        codes = {signal.code for signal in signals}

        self.assertIn("DISJOINT_RESPONSIBILITY_GROWTH", codes)
        self.assertIn("NEW_CYCLIC_IMPORT", codes)

    def test_class_stub_parameter_clump_and_scattered_growth(self) -> None:
        methods_before = "".join(
            "    def method_{0}(self, value):\n        return value\n\n".format(index)
            for index in range(6)
        )
        methods_after = methods_before + "".join(
            "    def added_{0}(self, value):\n".format(index)
            + "        value += 1\n" * 10
            + "        return value\n\n"
            for index in range(2)
        )
        before_files = {
            "pkg/model.py": "class Model:\n" + methods_before,
            "pkg/a.py": "class A:\n    pass\n\ndef one(value):\n    return value\n",
            "pkg/b.py": "class B:\n    pass\n\ndef two(value):\n    return value\n",
            "pkg/c.py": "def three(value):\n    return value\n",
        }
        after_files = {
            "pkg/model.py": "class Model:\n" + methods_after,
            "pkg/a.py": (
                "class A:\n    def sync(self):\n        ...\n\n"
                "def one(value, tenant, region, token):\n    return value\n"
            ),
            "pkg/b.py": (
                "class B:\n    def sync(self):\n        ...\n\n"
                "def two(value, tenant, region, token):\n    return value\n"
            ),
            "pkg/c.py": "def three(value, tenant, region, token):\n    return value\n",
        }
        _, signals = self._analyze(before_files, after_files)
        codes = {signal.code for signal in signals}

        self.assertIn("CLASS_SURFACE_GROWTH", codes)
        self.assertIn("REPEATED_INTERFACE_STUB_GROWTH", codes)
        self.assertIn("PARAMETER_CLUMP_GROWTH", codes)
        self.assertIn("SCATTERED_SMALL_EDIT", codes)

    def test_type_checking_and_local_imports_are_not_runtime_cycles(self) -> None:
        _, signals = self._analyze(
            {
                "pkg/left.py": "class Left:\n    pass\n",
                "pkg/right.py": "class Right:\n    pass\n",
            },
            {
                "pkg/left.py": (
                    "class Left:\n"
                    "    def build(self):\n"
                    "        from .right import Right\n"
                    "        return Right()\n"
                ),
                "pkg/right.py": (
                    "from typing import TYPE_CHECKING\n\n"
                    "if TYPE_CHECKING:\n    from .left import Left\n\n"
                    "class Right:\n    pass\n"
                ),
            },
        )

        self.assertNotIn("NEW_CYCLIC_IMPORT", {signal.code for signal in signals})


if __name__ == "__main__":
    unittest.main()
