from __future__ import annotations

import unittest

from runtime.analysis.ast_spans import AstParseError, SymbolKind, parse_python
from runtime.analysis.git_snapshot import DiffHunk, LineInterval


class AstSpanTests(unittest.TestCase):
    def test_qualified_spans_include_decorators_classes_and_locals(self) -> None:
        source = b"""\
def decorate(value):
    return value

class Container:
    @decorate
    async def method(self):
        def inner():
            return 1
        return inner()
"""

        parsed = parse_python("module.py", source)
        by_name = {span.qualname: span for span in parsed.spans}

        self.assertEqual(SymbolKind.CLASS, by_name["Container"].kind)
        self.assertEqual(5, by_name["Container.method"].start_line)
        self.assertEqual(6, by_name["Container.method"].definition_line)
        self.assertIn("Container.method.<locals>.inner", by_name)
        self.assertEqual(
            "Container.method.<locals>.inner", parsed.symbol_at(8).qualname
        )

    def test_duplicate_qualified_identity_is_inconclusive(self) -> None:
        source = b"""\
if FLAG:
    def choose():
        return 1
else:
    def choose():
        return 2
"""

        with self.assertRaisesRegex(AstParseError, "ambiguous-symbol:choose"):
            parse_python("module.py", source)

    def test_syntax_failure_retains_path_and_line(self) -> None:
        with self.assertRaisesRegex(AstParseError, "module.py:1"):
            parse_python("module.py", b"def broken(:\n    pass\n")

    def test_zero_context_hunks_touch_only_intersecting_symbols(self) -> None:
        parsed = parse_python(
            "module.py",
            b"def complex_one():\n    return 1\n\ndef clean():\n    return 2\n",
        )
        module_only = (DiffHunk(None, LineInterval(3, 3)),)
        function_change = (DiffHunk(LineInterval(5, 5), LineInterval(5, 5)),)

        self.assertEqual((), parsed.touched_symbols(module_only, side="after"))
        self.assertEqual(
            ("clean",),
            tuple(
                span.qualname
                for span in parsed.touched_symbols(function_change, side="after")
            ),
        )


if __name__ == "__main__":
    unittest.main()

