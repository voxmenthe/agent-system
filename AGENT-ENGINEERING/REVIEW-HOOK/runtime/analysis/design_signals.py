"""Recall-biased exact-delta design observations for full scans and dogfooding.

The module consumes the shared immutable Git snapshot and already parsed ASTs.
It performs no worktree reads and deliberately excludes the rejected broad
module-fanout heuristic.
"""

from __future__ import annotations

import ast
import io
import itertools
import keyword
import re
import tokenize
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .ast_spans import ParsedPython
from .git_snapshot import GitSnapshot
from .model import EvidenceLane, TargetRole
from .structural_policy import CandidateSignal, ObservationTarget

REVIEW_DESIGN_CODES = frozenset(
    {
        "CLASS_SURFACE_GROWTH",
        "DEAD_CODE_GROWTH",
        "INTERFACE_SURFACE_GROWTH",
        "PARAMETER_CLUMP_GROWTH",
        "REPEATED_CROSS_FILE_CHANGE",
        "REPEATED_INTERFACE_STUB_GROWTH",
        "SCATTERED_SMALL_EDIT",
        "DISJOINT_RESPONSIBILITY_GROWTH",
        "PARAMETER_PROPAGATION_GROWTH",
        "THIN_DELEGATION_LAYER_GROWTH",
        "NEW_CYCLIC_IMPORT",
    }
)
DESIGN_CONTEXT_CODES = frozenset({"LOW_USAGE_INTERFACE_GROWTH"})
PARAMETER_STOP = frozenset({"self", "cls", "args", "kwargs"})
PARAMETER_PROPAGATION_STOP = frozenset(
    {"data", "item", "items", "name", "result", "results", "value", "values"}
)
IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b")
IDENTIFIER_STOP = frozenset(
    {
        *keyword.kwlist,
        "None",
        "True",
        "False",
        "self",
        "classmethod",
        "staticmethod",
        "property",
        "typing",
    }
)
CROSS_FILE_STOP = frozenset(
    item.casefold()
    for item in {
        "Any",
        "Callable",
        "Context",
        "Exception",
        "Optional",
        "Parameter",
        "Path",
        "Returns",
        "ValueError",
        "bool",
        "bytes",
        "context",
        "dict",
        "float",
        "input",
        "int",
        "item",
        "items",
        "list",
        "name",
        "object",
        "parameter",
        "path",
        "result",
        "results",
        "set",
        "str",
        "tuple",
        "value",
        "values",
    }
)
MAX_CROSS_FILE_PATHS = 12
MAX_PARAMETER_CLUMP_TARGETS = 12
MAX_CONTEXT_TARGETS = 8
_TRY_TYPES = (ast.Try,) + ((ast.TryStar,) if hasattr(ast, "TryStar") else ())


def _is_test(path: str) -> bool:
    parts = tuple(part.lower() for part in Path(path).parts)
    name = parts[-1] if parts else ""
    return (
        any(part in {"test", "tests", "testing"} for part in parts[:-1])
        or name == "conftest.py"
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _is_nonproduction(path: str) -> bool:
    parts = tuple(part.lower() for part in Path(path).parts[:-1])
    return _is_test(path) or any(
        part
        in {
            "doc",
            "docs",
            "documentation",
            "example",
            "examples",
            "reference",
            "references",
            "tutorial",
            "tutorials",
        }
        for part in parts
    )


@dataclass(frozen=True)
class FunctionShape:
    path: str
    qualname: str
    line: int
    end_line: int
    parameters: Tuple[str, ...]
    statement_count: int
    parameter_usage: Tuple[Tuple[str, int, int], ...]
    self_attributes: Tuple[str, ...]
    thin_delegate: Optional[str]
    unreachable_count: int
    stub: bool
    abstract: bool

    def usage(self) -> Dict[str, Tuple[int, int]]:
        return {name: (loads, forwarded) for name, loads, forwarded in self.parameter_usage}


@dataclass(frozen=True)
class ClassShape:
    path: str
    qualname: str
    line: int
    end_line: int
    method_names: Tuple[str, ...]
    abstract_methods: Tuple[str, ...]
    stub_methods: Tuple[str, ...]
    statement_count: int
    bases: Tuple[str, ...]
    method_self_attributes: Tuple[Tuple[str, Tuple[str, ...]], ...]
    thin_delegate_methods: Tuple[Tuple[str, str], ...]

    def method_attributes(self) -> Dict[str, Tuple[str, ...]]:
        return dict(self.method_self_attributes)


@dataclass(frozen=True)
class ImportShape:
    module: str
    line: int


@dataclass(frozen=True)
class FileShape:
    path: str
    functions: Tuple[FunctionShape, ...]
    classes: Tuple[ClassShape, ...]
    imports: Tuple[ImportShape, ...]


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return "{}.{}".format(prefix, node.attr) if prefix else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _base_name(node: ast.AST) -> str:
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return _call_name(node)


def _parameters(node) -> Tuple[str, ...]:
    arguments = node.args
    names = [
        *[item.arg for item in getattr(arguments, "posonlyargs", ())],
        *[item.arg for item in arguments.args],
        *[item.arg for item in arguments.kwonlyargs],
    ]
    if arguments.vararg:
        names.append(arguments.vararg.arg)
    if arguments.kwarg:
        names.append(arguments.kwarg.arg)
    return tuple(name for name in names if name not in PARAMETER_STOP)


def _decorator_name(node: ast.AST) -> str:
    return _call_name(node)


def _is_abstract(node) -> bool:
    return any(
        _decorator_name(item).split(".")[-1] == "abstractmethod"
        for item in node.decorator_list
    )


def _not_implemented(node: Optional[ast.AST]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in {"NotImplemented", "NotImplementedError"}
    if isinstance(node, ast.Call):
        return _not_implemented(node.func)
    return False


def _is_stub(node) -> bool:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return True
    return all(
        isinstance(item, ast.Pass)
        or (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and item.value.value is Ellipsis
        )
        or (isinstance(item, ast.Raise) and _not_implemented(item.exc))
        for item in body
    )


def _literal_false(node: ast.AST) -> bool:
    try:
        return not bool(ast.literal_eval(node))
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False


def _nested_blocks(node: ast.AST) -> List[List[ast.stmt]]:
    blocks: List[List[ast.stmt]] = []
    for name in ("body", "orelse", "finalbody"):
        value = getattr(node, name, None)
        if isinstance(value, list):
            blocks.append(value)
    if isinstance(node, _TRY_TYPES):
        blocks.extend(handler.body for handler in node.handlers)
    if hasattr(ast, "Match") and isinstance(node, ast.Match):
        blocks.extend(case.body for case in node.cases)
    return blocks


def _unreachable(body: Sequence[ast.stmt]) -> int:
    total = 0
    terminated = False
    for node in body:
        if terminated:
            total += 1
        if isinstance(node, ast.If) and _literal_false(node.test):
            total += len(node.body)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            total += sum(_unreachable(block) for block in _nested_blocks(node))
        if isinstance(node, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            terminated = True
    return total


def _root_name(node: ast.AST) -> Optional[str]:
    current = node
    while isinstance(current, (ast.Attribute, ast.Subscript)):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _self_attribute(node: ast.Attribute) -> Optional[str]:
    current = node
    while isinstance(current.value, ast.Attribute):
        current = current.value
    if isinstance(current.value, ast.Name) and current.value.id == "self":
        return current.attr
    return None


class _FunctionVisitor(ast.NodeVisitor):
    def __init__(self, parameters: Sequence[str]) -> None:
        self.parameters = set(parameters)
        self.statements = 0
        self.self_attributes: Set[str] = set()
        self.loads: Counter = Counter()
        self.forwarded: Counter = Counter()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.statements += 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.statements += 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.statements += 1

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _root_name(node.value) == "self":
            name = _self_attribute(node)
            if name:
                self.self_attributes.add(name)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in self.parameters:
            self.loads[node.id] += 1

    def visit_Call(self, node: ast.Call) -> None:
        values = [*node.args, *[item.value for item in node.keywords]]
        for value in values:
            candidate = value.value if isinstance(value, ast.Starred) else value
            if isinstance(candidate, ast.Name) and candidate.id in self.parameters:
                self.forwarded[candidate.id] += 1
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, ast.stmt):
            self.statements += 1
        super().generic_visit(node)


def _thin_delegate(node) -> Optional[str]:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], (ast.Return, ast.Expr)):
        return None
    value = body[0].value
    if isinstance(value, ast.Await):
        value = value.value
    return _call_name(value.func) if isinstance(value, ast.Call) else None


def _function_shape(path: str, qualname: str, node) -> FunctionShape:
    parameters = _parameters(node)
    visitor = _FunctionVisitor(parameters)
    for statement in node.body:
        visitor.visit(statement)
    return FunctionShape(
        path,
        qualname,
        node.lineno,
        node.end_lineno or node.lineno,
        parameters,
        visitor.statements,
        tuple(
            (name, visitor.loads[name], visitor.forwarded[name])
            for name in sorted(parameters)
        ),
        tuple(sorted(visitor.self_attributes)),
        _thin_delegate(node),
        _unreachable(node.body),
        _is_stub(node),
        _is_abstract(node),
    )


def _class_shape(path: str, qualname: str, node: ast.ClassDef) -> ClassShape:
    methods = [
        item
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    shapes = [
        _function_shape(path, "{}.{}".format(qualname, item.name), item)
        for item in methods
    ]
    return ClassShape(
        path,
        qualname,
        node.lineno,
        node.end_lineno or node.lineno,
        tuple(sorted(item.name for item in methods)),
        tuple(sorted(item.name for item in methods if _is_abstract(item))),
        tuple(sorted(item.name for item in methods if _is_stub(item))),
        sum(item.statement_count for item in shapes),
        tuple(sorted(filter(None, (_base_name(item) for item in node.bases)))),
        tuple(sorted((item.name, shape.self_attributes) for item, shape in zip(methods, shapes))),
        tuple(
            sorted(
                (item.name, shape.thin_delegate)
                for item, shape in zip(methods, shapes)
                if shape.thin_delegate is not None
            )
        ),
    )


def _package_parts(path: str) -> List[str]:
    parts = list(Path(path).with_suffix("").parts)
    if parts:
        parts.pop()
    return parts


def _imports(path: str, tree: ast.Module) -> Tuple[ImportShape, ...]:
    package = _package_parts(path)
    rows: Set[Tuple[str, int]] = set()

    def record(node) -> None:
        if isinstance(node, ast.Import):
            rows.update((alias.name, node.lineno) for alias in node.names if alias.name != "__future__")
        else:
            if node.module == "__future__":
                return
            if node.level:
                keep = max(0, len(package) - (node.level - 1))
                base = package[:keep]
                if node.module:
                    module = ".".join((*base, *node.module.split(".")))
                    if module:
                        rows.add((module, node.lineno))
                else:
                    for alias in node.names:
                        if alias.name != "*":
                            module = ".".join((*base, alias.name))
                            if module:
                                rows.add((module, node.lineno))
            elif node.module:
                rows.add((node.module, node.lineno))

    def walk(body: Sequence[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                record(node)
            elif isinstance(node, ast.If) and _call_name(node.test).split(".")[-1] == "TYPE_CHECKING":
                walk(node.orelse)
            elif not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for block in _nested_blocks(node):
                    walk(block)

    walk(tree.body)
    return tuple(ImportShape(module, line) for module, line in sorted(rows))


def _file_shape(parsed: ParsedPython) -> FileShape:
    functions: List[FunctionShape] = []
    classes: List[ClassShape] = []

    def walk(body: Sequence[ast.stmt], prefix: Tuple[str, ...]) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                qualname = ".".join((*prefix, node.name))
                classes.append(_class_shape(parsed.path, qualname, node))
                walk(node.body, (*prefix, node.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = ".".join((*prefix, node.name))
                functions.append(_function_shape(parsed.path, qualname, node))
                walk(node.body, (*prefix, node.name, "<locals>"))

    walk(parsed.tree.body, ())
    return FileShape(parsed.path, tuple(functions), tuple(classes), _imports(parsed.path, parsed.tree))


def _maps(files: Sequence[FileShape]):
    functions = {
        (function.path, function.qualname): function
        for file in files
        for function in file.functions
    }
    classes = {
        (shape.path, shape.qualname): shape for file in files for shape in file.classes
    }
    return functions, classes


def _function_signature(shape: Optional[FunctionShape]):
    if shape is None:
        return None
    return (
        shape.parameters,
        shape.statement_count,
        shape.parameter_usage,
        shape.self_attributes,
        shape.thin_delegate,
        shape.unreachable_count,
        shape.stub,
        shape.abstract,
    )


def _class_signature(shape: Optional[ClassShape]):
    if shape is None:
        return None
    return (
        shape.method_names,
        shape.abstract_methods,
        shape.stub_methods,
        shape.statement_count,
        shape.bases,
        shape.method_self_attributes,
        shape.thin_delegate_methods,
    )


def _target(shape) -> ObservationTarget:
    return ObservationTarget(shape.path, shape.line, shape.qualname, TargetRole.PRODUCTION)


def _signal(code: str, message: str, targets, evidence, *, context: bool = False):
    return CandidateSignal(
        EvidenceLane.DESIGN_CONTEXT if context else EvidenceLane.DESIGN,
        code,
        tuple(targets),
        message,
        evidence=evidence,
    )


def _dead_code(before, after):
    rows = []
    for key, current in after.items():
        previous = before.get(key)
        old = previous.unreachable_count if previous else 0
        if current.unreachable_count > old:
            rows.append(
                _signal(
                    "DEAD_CODE_GROWTH",
                    "new statically unreachable statements appeared",
                    (_target(current),),
                    {"unreachable_before": old, "unreachable_after": current.unreachable_count},
                )
            )
    return rows


def _class_growth(before, after):
    rows = []
    for key, current in after.items():
        previous = before.get(key)
        old_methods = len(previous.method_names) if previous else 0
        old_lines = previous.end_line - previous.line + 1 if previous else 0
        old_statements = previous.statement_count if previous else 0
        lines = current.end_line - current.line + 1
        if (
            len(current.method_names) - old_methods >= 2
            and len(current.method_names) >= 8
            and (lines - old_lines >= 25 or current.statement_count - old_statements >= 20)
        ):
            rows.append(
                _signal(
                    "CLASS_SURFACE_GROWTH",
                    "an already substantial class absorbed multiple methods and body growth",
                    (_target(current),),
                    {
                        "methods_before": old_methods,
                        "methods_after": len(current.method_names),
                        "lines_before": old_lines,
                        "lines_after": lines,
                        "statements_before": old_statements,
                        "statements_after": current.statement_count,
                    },
                )
            )
    return rows


def _interface_growth(before, after):
    rows = []
    new_stub_owners: Dict[str, List[ClassShape]] = defaultdict(list)
    for key, current in after.items():
        previous = before.get(key)
        old_contract = set(previous.abstract_methods if previous else ()) | set(previous.stub_methods if previous else ())
        new_contract = (set(current.abstract_methods) | set(current.stub_methods)) - old_contract
        if len(new_contract) >= 2:
            rows.append(
                _signal(
                    "INTERFACE_SURFACE_GROWTH",
                    "an interface-like class gained multiple abstract or stub methods",
                    (_target(current),),
                    {"new_contract_methods": sorted(new_contract), "bases": list(current.bases)},
                )
            )
        old_stubs = set(previous.stub_methods if previous else ())
        for method in set(current.stub_methods) - old_stubs:
            new_stub_owners[method].append(current)
    for method, owners in sorted(new_stub_owners.items()):
        distinct = {(owner.path, owner.qualname): owner for owner in owners}
        if len(distinct) >= 2:
            rows.append(
                _signal(
                    "REPEATED_INTERFACE_STUB_GROWTH",
                    "the same new stub obligation appeared in multiple classes",
                    tuple(_target(owner) for owner in distinct.values()),
                    {"method": method, "classes": len(distinct)},
                )
            )
    return rows


def _thin_delegation(before, after):
    rows = []
    for key, current in sorted(after.items()):
        previous = before.get(key)
        old = dict(previous.thin_delegate_methods) if previous else {}
        delegates = dict(current.thin_delegate_methods)
        added = sorted(set(delegates) - set(old))
        method_count = len(current.method_names)
        if len(added) >= 3 and len(delegates) >= 3 and method_count >= 3 and len(delegates) / method_count >= 0.6:
            rows.append(
                _signal(
                    "THIN_DELEGATION_LAYER_GROWTH",
                    "a class newly became dominated by methods that only delegate one call",
                    (_target(current),),
                    {
                        "class": current.qualname,
                        "methods_after": method_count,
                        "thin_delegates_before": len(old),
                        "thin_delegates_after": len(delegates),
                        "new_delegate_methods": added,
                        "delegate_targets": {name: delegates[name] for name in added},
                    },
                )
            )
    return rows


def _responsibility(before, after):
    rows = []
    for key, current in sorted(after.items()):
        previous = before.get(key)
        if previous is None:
            continue
        added_methods = sorted(set(current.method_names) - set(previous.method_names))
        if len(added_methods) < 2 or len(current.method_names) < 8:
            continue
        old_attributes = {attribute for values in previous.method_attributes().values() for attribute in values}
        current_attributes = current.method_attributes()
        added_attributes = {attribute for name in added_methods for attribute in current_attributes.get(name, ())}
        novel = added_attributes - old_attributes
        if (
            len(old_attributes) >= 2
            and len(added_attributes) >= 2
            and len(novel) >= 2
            and len(added_attributes & old_attributes) / len(added_attributes) <= 0.25
            and current.statement_count - previous.statement_count >= 10
        ):
            rows.append(
                _signal(
                    "DISJOINT_RESPONSIBILITY_GROWTH",
                    "new methods add a mostly disjoint state vocabulary to an established class",
                    (_target(current),),
                    {
                        "class": current.qualname,
                        "new_methods": added_methods,
                        "previous_state_members": sorted(old_attributes),
                        "added_state_members": sorted(added_attributes),
                        "novel_state_members": sorted(novel),
                        "statements_before": previous.statement_count,
                        "statements_after": current.statement_count,
                    },
                )
            )
    return rows


def _parameter_propagation(before, after):
    owners: Dict[str, List[Tuple[Tuple[str, str], bool, bool]]] = defaultdict(list)
    for key, current in after.items():
        previous = before.get(key)
        old_parameters = set(previous.parameters) if previous else set()
        usage = current.usage()
        for parameter in set(current.parameters) - old_parameters:
            if parameter in PARAMETER_PROPAGATION_STOP or parameter.startswith("_") or len(parameter) < 3:
                continue
            loads, forwarded = usage.get(parameter, (0, 0))
            owners[parameter].append((key, previous is not None, loads > 0 and loads == forwarded))
    candidates = []
    for parameter, entries in owners.items():
        if (
            len(entries) >= 3
            and len({key[0] for key, _, _ in entries}) >= 2
            and sum(existing for _, existing, _ in entries) >= 2
            and sum(forward for _, _, forward in entries) >= 2
        ):
            candidates.append((parameter, entries))
    grouped = defaultdict(list)
    for parameter, entries in candidates:
        grouped[tuple(sorted(key for key, _, _ in entries))].append((parameter, entries))
    rows = []
    groups = sorted(grouped.items(), key=lambda item: (-len(item[0]), tuple(row[0] for row in item[1])))
    for owner_keys, details in groups[:3]:
        per_parameter = {
            parameter: {
                "existing_functions_changed": sum(existing for _, existing, _ in entries),
                "forward_only_functions": sum(forward for _, _, forward in entries),
            }
            for parameter, entries in details
        }
        rows.append(
            _signal(
                "PARAMETER_PROPAGATION_GROWTH",
                "new parameters are threaded through several functions and mostly forwarded",
                tuple(_target(after[key]) for key in owner_keys),
                {
                    "parameters": sorted(per_parameter),
                    "functions": len(owner_keys),
                    "files": len({key[0] for key in owner_keys}),
                    "minimum_existing_functions_changed": min(item["existing_functions_changed"] for item in per_parameter.values()),
                    "minimum_forward_only_functions": min(item["forward_only_functions"] for item in per_parameter.values()),
                    "per_parameter": per_parameter,
                },
            )
        )
    return rows


def _module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _import_maps(files):
    module_paths = {_module_name(file.path): file.path for file in files}
    edges: Dict[str, Set[str]] = defaultdict(set)
    lines = {}
    for file in files:
        for imported in file.imports:
            target = module_paths.get(imported.module)
            if target is not None and target != file.path:
                edges[file.path].add(target)
                lines.setdefault((file.path, target), imported.line)
    return edges, lines


def _cycles(before_files, after_files):
    before_edges, _ = _import_maps(before_files)
    after_edges, lines = _import_maps(after_files)
    rows = []
    paths = sorted(after_edges)
    for offset, left in enumerate(paths):
        for right in paths[offset + 1 :]:
            now = right in after_edges.get(left, set()) and left in after_edges.get(right, set())
            existed = right in before_edges.get(left, set()) and left in before_edges.get(right, set())
            if now and not existed:
                rows.append(
                    _signal(
                        "NEW_CYCLIC_IMPORT",
                        "changed modules introduced a direct cyclic import",
                        (
                            ObservationTarget(left, lines[(left, right)], "<module>", TargetRole.PRODUCTION),
                            ObservationTarget(right, lines[(right, left)], "<module>", TargetRole.PRODUCTION),
                        ),
                        {"cycle": [left, right, left]},
                    )
                )
    return rows


def _parameter_groups(functions):
    rows = defaultdict(set)
    for key, function in functions.items():
        parameters = sorted(
            {name for name in function.parameters if name not in PARAMETER_STOP and not name.startswith("_") and len(name) >= 2}
        )[:12]
        for group in itertools.combinations(parameters, 3):
            rows[group].add(key)
    return rows


def _parameter_clumps(before, after):
    old = _parameter_groups(before)
    new = _parameter_groups(after)
    candidates = []
    for group, owners in new.items():
        old_count = len(old.get(group, set()))
        if len(owners) >= 3 and len({path for path, _ in owners}) >= 2 and len(owners) - old_count >= 2:
            candidates.append((len(owners), len(owners) - old_count, group, owners))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    covered = set()
    rows = []
    for count, growth, group, owners in candidates:
        if any(len(set(group) & set(existing)) >= 2 for existing in covered):
            continue
        changed = {key for key in owners if _function_signature(after[key]) != _function_signature(before.get(key))}
        if not changed or len(changed) > MAX_PARAMETER_CLUMP_TARGETS:
            continue
        covered.add(group)
        rows.append(
            _signal(
                "PARAMETER_CLUMP_GROWTH",
                "the same parameter triple newly travels through multiple functions and files",
                tuple(_target(after[key]) for key in sorted(changed)),
                {"parameters": list(group), "functions_after": count, "function_growth": growth, "changed_functions": len(changed)},
            )
        )
        if len(rows) >= 3:
            break
    return rows


def _added_identifier_locations(snapshot: GitSnapshot, paths: Sequence[str]):
    files = {item.path: item for item in snapshot.python_files}
    result = {}
    for path in paths:
        item = files[path]
        added_lines = {line for interval in item.after_changed_lines for line in range(interval.start, interval.end + 1)}
        locations: Dict[str, Set[int]] = defaultdict(set)
        source = item.after_blob
        if source is not None:
            try:
                for token_info in tokenize.tokenize(io.BytesIO(source).readline):
                    if (
                        token_info.type == tokenize.NAME
                        and token_info.start[0] in added_lines
                        and token_info.string not in IDENTIFIER_STOP
                        and not token_info.string.startswith("test_")
                        and IDENTIFIER.fullmatch(token_info.string)
                    ):
                        locations[token_info.string].add(token_info.start[0])
            except (tokenize.TokenError, IndentationError, SyntaxError):
                locations.clear()
        result[path] = {name: tuple(sorted(lines)) for name, lines in sorted(locations.items())}
    return result


def _dispersion(snapshot, paths, changed_functions, after_functions):
    if len(paths) < 3:
        return []
    added = _added_identifier_locations(snapshot, paths)
    owners: Dict[str, Set[str]] = defaultdict(set)
    for path, names in added.items():
        for name in names:
            owners[name].add(path)
    repeated = [
        (name, value)
        for name, value in owners.items()
        if len(value) >= 2 and name.casefold() not in CROSS_FILE_STOP
    ]
    repeated.sort(key=lambda item: (-len(item[1]), not item[0].startswith("_"), -len(item[0]), item[0]))
    rows = []
    selected = []
    token_paths: Set[str] = set()
    if repeated:
        selected.append(repeated[0])
        token_paths.update(repeated[0][1])
        for candidate in repeated[1:]:
            if candidate[1] <= token_paths:
                continue
            selected.append(candidate)
            token_paths.update(candidate[1])
            if len(selected) >= 3:
                break
    if len(token_paths) >= 3 and len(token_paths) <= MAX_CROSS_FILE_PATHS:
        selected_names = tuple(name for name, _ in selected)
        targets = []
        affected_scopes = 0
        file_scoped = []
        for path in sorted(token_paths):
            lines = sorted({line for name in selected_names for line in added[path].get(name, ())})
            scopes: Dict[str, int] = {}
            for line in lines:
                containing = [
                    shape
                    for (shape_path, _), shape in after_functions.items()
                    if shape_path == path and shape.line <= line <= shape.end_line
                ]
                symbol = min(containing, key=lambda shape: (shape.end_line - shape.line, -shape.line)).qualname if containing else "<module>"
                scopes[symbol] = min(scopes.get(symbol, line), line)
            nonmodule = {name: line for name, line in scopes.items() if name != "<module>"}
            review_scopes = nonmodule or scopes
            affected_scopes += len(review_scopes)
            if len(review_scopes) == 1:
                symbol, line = next(iter(review_scopes.items()))
            else:
                symbol = "<changed-file>"
                line = min(review_scopes.values())
                file_scoped.append(path)
            targets.append(ObservationTarget(path, line, symbol, TargetRole.PRODUCTION))
        rows.append(
            _signal(
                "REPEATED_CROSS_FILE_CHANGE",
                "related newly added identifiers span at least three Python files",
                targets,
                {
                    "identifiers": list(selected_names),
                    "files": sorted(token_paths),
                    "file_count": len(token_paths),
                    "target_count": len(targets),
                    "affected_scopes": affected_scopes,
                    "file_scoped_paths": file_scoped,
                },
            )
        )
    files = {item.path: item for item in snapshot.python_files}
    churn = [
        sum(
            (interval.end - interval.start + 1) if interval else 0
            for hunk in files[path].hunks
            for interval in (hunk.before, hunk.after)
        )
        for path in paths
    ]
    if (
        4 <= len(paths) <= MAX_CROSS_FILE_PATHS
        and len({path for path, _ in changed_functions}) >= 3
        and median(churn) <= 20
        and sum(churn) <= 120
    ):
        first = {}
        for (path, _), shape in sorted(changed_functions.items(), key=lambda item: (item[0][0], item[1].line)):
            first.setdefault(path, shape)
        targets = tuple(
            _target(first[path]) if path in first else ObservationTarget(path, 1, "<module>", TargetRole.PRODUCTION)
            for path in paths
        )
        rows.append(
            _signal(
                "SCATTERED_SMALL_EDIT",
                "small coordinated edits are dispersed across several Python files",
                targets,
                {"python_files": len(paths), "changed_functions": len(changed_functions), "total_line_churn": sum(churn), "median_file_churn": median(churn)},
            )
        )
    return rows


def _low_usage(snapshot, before, after):
    rows = []
    class_pattern_cache = {}
    for key, current in sorted(after.items()):
        if key in before:
            continue
        contract = set(current.abstract_methods) | set(current.stub_methods)
        interface_base = any(base.split(".")[-1] in {"ABC", "ABCMeta", "Protocol"} for base in current.bases)
        if len(contract) < 2 and not (interface_base and contract):
            continue
        identifier = current.qualname.rsplit(".", 1)[-1]
        class_pattern = class_pattern_cache.setdefault(
            identifier,
            re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s*\([^)]*\b" + re.escape(identifier) + r"\b"),
        )
        definition = re.compile(r"^\s*class\s+" + re.escape(identifier) + r"\b")
        imports = re.compile(r"^\s*(?:from\s+\S+\s+import|import)\b")
        implementations = []
        references = []
        for path, line, source in snapshot.grep_after(identifier):
            if _is_nonproduction(path) or definition.search(source):
                continue
            match = class_pattern.search(source)
            if match:
                implementations.append(ObservationTarget(path, line, match.group(1), TargetRole.PRODUCTION))
            elif not imports.search(source):
                references.append(ObservationTarget(path, line, "<module>", TargetRole.PRODUCTION))
        implementation_keys = {(item.path, item.line) for item in implementations}
        reference_keys = {(item.path, item.line) for item in references}
        if len(implementation_keys) > 1 or len(reference_keys) > 3:
            continue
        targets = [_target(current)]
        targets.extend(item for item in implementations if (item.path, item.line) != (current.path, current.line))
        targets.extend(references[: max(0, MAX_CONTEXT_TARGETS - len(targets))])
        rows.append(
            _signal(
                "LOW_USAGE_INTERFACE_GROWTH",
                "a new interface-like abstraction has few explicit production references or declared subclasses",
                targets[:MAX_CONTEXT_TARGETS],
                {
                    "abstraction": identifier,
                    "contract_methods": sorted(contract),
                    "bases": list(current.bases),
                    "declared_subclasses": len(implementation_keys),
                    "production_references": len(reference_keys),
                    "reference_paths": sorted({item.path for item in references}),
                },
                context=True,
            )
        )
        if len(rows) >= 5:
            break
    return rows


def analyze_design(
    snapshot: GitSnapshot,
    parsed_before: Mapping[str, ParsedPython],
    parsed_after: Mapping[str, ParsedPython],
) -> Tuple[CandidateSignal, ...]:
    """Return selected design observations; context is computed only after selection."""
    paths = tuple(
        item.path
        for item in snapshot.python_files
        if item.after_blob is not None and not _is_nonproduction(item.path)
    )
    before_files = tuple(_file_shape(parsed_before[path]) for path in paths if path in parsed_before)
    after_files = tuple(_file_shape(parsed_after[path]) for path in paths if path in parsed_after)
    before_functions, before_classes = _maps(before_files)
    after_functions, after_classes = _maps(after_files)
    changed_functions = {
        key: shape
        for key, shape in after_functions.items()
        if _function_signature(shape) != _function_signature(before_functions.get(key))
    }
    review = [
        *_dead_code(before_functions, after_functions),
        *_class_growth(before_classes, after_classes),
        *_interface_growth(before_classes, after_classes),
        *_thin_delegation(before_classes, after_classes),
        *_responsibility(before_classes, after_classes),
        *_parameter_propagation(before_functions, after_functions),
        *_cycles(before_files, after_files),
        *_parameter_clumps(before_functions, after_functions),
        *_dispersion(snapshot, paths, changed_functions, after_functions),
    ]
    context = _low_usage(snapshot, before_classes, after_classes) if review else []
    rows = [*review, *context]
    rows.sort(
        key=lambda signal: (
            1 if signal.lane is EvidenceLane.DESIGN_CONTEXT else 0,
            signal.code,
            signal.targets[0].path if signal.targets else "",
            signal.targets[0].line if signal.targets else 0,
        )
    )
    return tuple(rows)


__all__ = [
    "DESIGN_CONTEXT_CODES",
    "REVIEW_DESIGN_CODES",
    "analyze_design",
]
