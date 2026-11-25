"""Python AST attribution shared by structural and design analysis."""

from __future__ import annotations

import ast
import warnings
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from .git_snapshot import DiffHunk, LineInterval


class AstParseError(ValueError):
    """A committed Python blob cannot be attributed unambiguously."""


class SymbolKind(str, Enum):
    CLASS = "class"
    FUNCTION = "function"


@dataclass(frozen=True)
class SymbolSpan:
    qualname: str
    kind: SymbolKind
    start_line: int
    definition_line: int
    end_line: int

    def intersects(self, interval: Optional[LineInterval]) -> bool:
        return interval is not None and interval.intersects(
            self.start_line, self.end_line
        )


@dataclass(frozen=True)
class ParsedPython:
    path: str
    tree: ast.Module
    spans: Tuple[SymbolSpan, ...]

    def symbol_at(self, line: int) -> Optional[SymbolSpan]:
        candidates = [
            span for span in self.spans if span.start_line <= line <= span.end_line
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda span: (
                span.end_line - span.start_line,
                0 if span.kind is SymbolKind.FUNCTION else 1,
                -span.start_line,
                span.qualname,
            ),
        )

    def by_qualname(self, kind: Optional[SymbolKind] = None):
        return {
            span.qualname: span
            for span in self.spans
            if kind is None or span.kind is kind
        }

    def touched_symbols(
        self, hunks: Sequence[DiffHunk], *, side: str
    ) -> Tuple[SymbolSpan, ...]:
        if side not in ("before", "after"):
            raise ValueError("side must be before or after")
        intervals = tuple(
            getattr(hunk, side)
            for hunk in hunks
            if getattr(hunk, side) is not None
        )
        return tuple(
            span
            for span in self.spans
            if any(span.intersects(interval) for interval in intervals)
        )


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: List[str] = []
        self.spans: List[SymbolSpan] = []
        self.identities: Counter = Counter()

    @staticmethod
    def _start(node) -> int:
        decorator_lines = [item.lineno for item in getattr(node, "decorator_list", ())]
        return min([node.lineno, *decorator_lines])

    def _record(self, qualname: str, kind: SymbolKind, node) -> None:
        self.identities[(kind, qualname)] += 1
        self.spans.append(
            SymbolSpan(
                qualname=qualname,
                kind=kind,
                start_line=self._start(node),
                definition_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = ".".join((*self.scope, node.name))
        self._record(qualname, SymbolKind.CLASS, node)
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _visit_function(self, node) -> None:
        qualname = ".".join((*self.scope, node.name))
        self._record(qualname, SymbolKind.FUNCTION, node)
        self.scope.extend((node.name, "<locals>"))
        self.generic_visit(node)
        self.scope.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def parse_python(path: str, source: bytes) -> ParsedPython:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source, filename=path, type_comments=True)
    except SyntaxError as error:
        raise AstParseError(
            "{}:{}:syntax-error:{}".format(path, error.lineno or 1, error.msg)
        ) from error
    except (UnicodeDecodeError, ValueError, TypeError) as error:
        raise AstParseError(
            "{}:1:source-parse-error:{}".format(path, error)
        ) from error
    visitor = _Visitor()
    visitor.visit(tree)
    duplicates = sorted(
        qualname
        for (_, qualname), count in visitor.identities.items()
        if count > 1
    )
    if duplicates:
        raise AstParseError(
            "{}:1:ambiguous-symbol:{}".format(path, ",".join(duplicates))
        )
    return ParsedPython(
        path,
        tree,
        tuple(
            sorted(
                visitor.spans,
                key=lambda span: (
                    span.start_line,
                    span.end_line,
                    span.kind.value,
                    span.qualname,
                ),
            )
        ),
    )


__all__ = [
    "AstParseError",
    "ParsedPython",
    "SymbolKind",
    "SymbolSpan",
    "parse_python",
]

