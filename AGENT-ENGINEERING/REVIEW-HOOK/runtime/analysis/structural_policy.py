"""Score-free correctness and structural delta policies."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .ast_spans import ParsedPython, SymbolKind
from .git_snapshot import ChangeKind, GitSnapshot, TargetRole
from .model import EvidenceLane
from .ruff_runner import (
    CORRECTNESS_CODES,
    STRUCTURAL_LIMITS,
    RuffDiagnostic,
    RuffResult,
)

REPORT_ONLY_CORRECTNESS = frozenset({"B023", "PLE1205"})
STRICT_CORRECTNESS = CORRECTNESS_CODES - REPORT_ONLY_CORRECTNESS
STRUCTURAL_CODES = tuple(STRUCTURAL_LIMITS)
STRUCTURAL_CORROBORATORS = tuple(
    code for code in STRUCTURAL_CODES if code != "C901"
)
POLICY_ORDER = (
    "static-structural-presence",
    "structural-regression",
    "corroborated-structural-regression",
    "material-corroborated-regression",
    "strict-correctness",
    "compound-structural",
    "material-single-c901",
    "auto-attention-v1",
)


@dataclass(frozen=True)
class ObservationTarget:
    path: str
    line: int
    symbol: str
    role: TargetRole


@dataclass(frozen=True)
class CandidateSignal:
    lane: EvidenceLane
    code: str
    targets: Tuple[ObservationTarget, ...]
    message: Optional[str] = None
    before: Optional[Any] = None
    after: Optional[int] = None
    limit: Optional[int] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    column: int = 1

    @property
    def target_key(self) -> Tuple[str, str]:
        target = self.targets[0]
        return target.path, target.symbol

    @property
    def numeric_delta(self) -> Optional[int]:
        if isinstance(self.before, int) and isinstance(self.after, int):
            return self.after - self.before
        return None


@dataclass(frozen=True)
class PolicyDecision:
    name: str
    signals: Tuple[CandidateSignal, ...] = ()

    @property
    def matched(self) -> bool:
        return bool(self.signals)


@dataclass(frozen=True)
class StructuralAnalysis:
    signals: Tuple[CandidateSignal, ...]
    policies: Tuple[PolicyDecision, ...]

    def policy(self, name: str) -> PolicyDecision:
        for decision in self.policies:
            if decision.name == name:
                return decision
        raise KeyError(name)

    @property
    def auto_candidate(self) -> PolicyDecision:
        return self.policy("auto-attention-v1")


def _sort_key(signal: CandidateSignal) -> Tuple[Any, ...]:
    lane_order = {
        EvidenceLane.CORRECTNESS: 0,
        EvidenceLane.STRUCTURAL: 1,
        EvidenceLane.DESIGN: 2,
        EvidenceLane.DESIGN_CONTEXT: 3,
    }
    target = signal.targets[0]
    magnitude = signal.numeric_delta or 0
    return (
        lane_order[signal.lane],
        -magnitude,
        target.path,
        target.line,
        target.symbol,
        signal.code,
        signal.column,
        signal.message or "",
    )


def _deduplicate(signals: Iterable[CandidateSignal]) -> Tuple[CandidateSignal, ...]:
    rows: Dict[Tuple[Any, ...], CandidateSignal] = {}
    for signal in signals:
        key = (
            signal.lane,
            signal.code,
            tuple((target.path, target.line, target.symbol) for target in signal.targets),
            signal.message,
            signal.before,
            signal.after,
            signal.limit,
            signal.column,
        )
        rows.setdefault(key, signal)
    return tuple(sorted(rows.values(), key=_sort_key))


def _attribute(
    diagnostics: Sequence[RuffDiagnostic],
    parsed_by_side: Mapping[str, Mapping[str, ParsedPython]],
) -> Dict[Tuple[str, str, str], Tuple[RuffDiagnostic, ...]]:
    grouped: Dict[Tuple[str, str, str], List[RuffDiagnostic]] = {}
    for diagnostic in diagnostics:
        parsed = parsed_by_side.get(diagnostic.side, {}).get(diagnostic.path)
        span = parsed.symbol_at(diagnostic.row) if parsed is not None else None
        symbol = span.qualname if span is not None else "<module>"
        grouped.setdefault(
            (diagnostic.side, diagnostic.path, symbol), []
        ).append(diagnostic)
    return {
        key: tuple(
            sorted(
                rows,
                key=lambda item: (
                    item.row, item.column, item.code, item.message
                ),
            )
        )
        for key, rows in grouped.items()
    }


def _new_diagnostics(
    before: Sequence[RuffDiagnostic], after: Sequence[RuffDiagnostic]
) -> Tuple[RuffDiagnostic, ...]:
    remaining = Counter(item.signature for item in before)
    new: List[RuffDiagnostic] = []
    for item in after:
        if remaining[item.signature]:
            remaining[item.signature] -= 1
        else:
            new.append(item)
    return tuple(new)


def _metric(
    rows: Sequence[RuffDiagnostic], code: str
) -> Optional[RuffDiagnostic]:
    matches = [item for item in rows if item.code == code]
    if len(matches) > 1:
        raise ValueError("Ruff emitted duplicate {} metrics for one symbol".format(code))
    return matches[0] if matches else None


def _changed_line(snapshot_file, row: int) -> bool:
    return snapshot_file.change is ChangeKind.ADDED or any(
        interval.contains(row) for interval in snapshot_file.after_changed_lines
    )


def _structural_signal(
    diagnostic: RuffDiagnostic,
    target: ObservationTarget,
    before: Any,
    change_kind: str,
) -> CandidateSignal:
    return CandidateSignal(
        lane=EvidenceLane.STRUCTURAL,
        code=diagnostic.code,
        targets=(target,),
        before=before,
        after=diagnostic.observed,
        limit=diagnostic.limit,
        evidence={"change_kind": change_kind},
        column=diagnostic.column,
    )


def _is_material(
    c901: CandidateSignal, corroborators: Sequence[CandidateSignal]
) -> bool:
    change_kind = c901.evidence.get("change_kind")
    if change_kind in ("new-function", "crossed-limit"):
        return True
    if c901.numeric_delta is not None and c901.numeric_delta >= 2:
        return True
    if len(corroborators) >= 2:
        return True
    return any(
        signal.code in ("PLR1702", "PLR0916")
        and signal.evidence.get("change_kind")
        in ("new-function", "crossed-limit")
        for signal in corroborators
    )


def analyze_structural(
    snapshot: GitSnapshot,
    parsed_before: Mapping[str, ParsedPython],
    parsed_after: Mapping[str, ParsedPython],
    ruff: RuffResult,
) -> StructuralAnalysis:
    """Compare exact attributed Ruff observations without producing a score."""
    if ruff.status.value != "ok":
        return StructuralAnalysis(
            (), tuple(PolicyDecision(name) for name in POLICY_ORDER)
        )
    attributed = _attribute(
        ruff.diagnostics,
        {"before": parsed_before, "after": parsed_after},
    )
    regressions: List[CandidateSignal] = []
    static_c901: List[CandidateSignal] = []
    correctness: List[CandidateSignal] = []

    for changed in snapshot.python_files:
        if not changed.comparison_safe:
            continue
        before_file = parsed_before.get(changed.path)
        after_file = parsed_after.get(changed.path)
        before_functions = (
            before_file.by_qualname(SymbolKind.FUNCTION) if before_file else {}
        )
        after_functions = (
            after_file.by_qualname(SymbolKind.FUNCTION) if after_file else {}
        )
        symbols = sorted(set(before_functions) | set(after_functions))
        for symbol in symbols:
            before_span = before_functions.get(symbol)
            after_span = after_functions.get(symbol)
            if after_span is None:
                continue
            touched = before_span is None or any(
                before_span is not None and before_span.intersects(hunk.before)
                or after_span.intersects(hunk.after)
                for hunk in changed.hunks
            )
            if not touched:
                continue
            before_rows = attributed.get(("before", changed.path, symbol), ())
            after_rows = attributed.get(("after", changed.path, symbol), ())
            target = ObservationTarget(
                changed.path,
                after_span.definition_line,
                symbol,
                changed.role,
            )
            for code in STRUCTURAL_CODES:
                before_item = _metric(before_rows, code)
                after_item = _metric(after_rows, code)
                if after_item is None:
                    continue
                if before_span is None:
                    before_value: Any = "new"
                    change_kind = "new-function"
                    regression = True
                elif before_item is None:
                    before_value = "<={}".format(after_item.limit)
                    change_kind = "crossed-limit"
                    regression = True
                else:
                    before_value = before_item.observed
                    regression = (
                        after_item.observed is not None
                        and before_item.observed is not None
                        and after_item.observed > before_item.observed
                    )
                    change_kind = "worsened-above-limit"
                signal = _structural_signal(
                    after_item, target, before_value, change_kind
                )
                if code == "C901":
                    static_c901.append(signal)
                if regression:
                    regressions.append(signal)

        correctness_symbols = sorted(
            {
                key[2]
                for key in attributed
                if key[1] == changed.path and key[0] in ("before", "after")
            }
        )
        for symbol in correctness_symbols:
            before_rows = tuple(
                item
                for item in attributed.get(("before", changed.path, symbol), ())
                if item.code in CORRECTNESS_CODES
            )
            after_rows = tuple(
                item
                for item in attributed.get(("after", changed.path, symbol), ())
                if item.code in CORRECTNESS_CODES
            )
            for diagnostic in _new_diagnostics(before_rows, after_rows):
                after_span = after_file.symbol_at(diagnostic.row) if after_file else None
                is_new_symbol = (
                    after_span is not None
                    and before_file is not None
                    and after_span.qualname not in before_file.by_qualname()
                ) or (after_span is not None and before_file is None)
                if not is_new_symbol and not _changed_line(changed, diagnostic.row):
                    continue
                target = ObservationTarget(
                    changed.path,
                    after_span.definition_line if after_span else diagnostic.row,
                    after_span.qualname if after_span else "<module>",
                    changed.role,
                )
                disposition = (
                    "report-only"
                    if diagnostic.code in REPORT_ONLY_CORRECTNESS
                    else "candidate-strict"
                )
                correctness.append(
                    CandidateSignal(
                        lane=EvidenceLane.CORRECTNESS,
                        code=diagnostic.code,
                        targets=(target,),
                        message=diagnostic.message,
                        evidence={"disposition": disposition},
                        column=diagnostic.column,
                    )
                )

    regression_rows = _deduplicate(regressions)
    correctness_rows = _deduplicate(correctness)
    all_rows = _deduplicate((*correctness_rows, *regression_rows))
    by_target: Dict[Tuple[str, str], List[CandidateSignal]] = {}
    for signal in regression_rows:
        by_target.setdefault(signal.target_key, []).append(signal)

    ordinary_c901 = tuple(
        signal for signal in regression_rows if signal.code == "C901"
    )
    corroborated: List[CandidateSignal] = []
    material: List[CandidateSignal] = []
    material_single: List[CandidateSignal] = []
    compound: List[CandidateSignal] = []
    for c901 in ordinary_c901:
        rows = by_target[c901.target_key]
        corroborators = [
            signal for signal in rows if signal.code in STRUCTURAL_CORROBORATORS
        ]
        if c901.evidence.get("change_kind") in (
            "new-function",
            "crossed-limit",
        ) or (c901.numeric_delta is not None and c901.numeric_delta >= 2):
            material_single.append(c901)
        if corroborators:
            corroborated.extend((c901, *corroborators))
            if _is_material(c901, corroborators):
                material.extend((c901, *corroborators))
    for rows in by_target.values():
        if len(rows) >= 2:
            compound.extend(rows)
    strict = tuple(
        signal for signal in correctness_rows if signal.code in STRICT_CORRECTNESS
    )
    auto = _deduplicate((*strict, *material))
    policies = (
        PolicyDecision("static-structural-presence", _deduplicate(static_c901)),
        PolicyDecision("structural-regression", ordinary_c901),
        PolicyDecision(
            "corroborated-structural-regression", _deduplicate(corroborated)
        ),
        PolicyDecision(
            "material-corroborated-regression", _deduplicate(material)
        ),
        PolicyDecision("strict-correctness", strict),
        PolicyDecision("compound-structural", _deduplicate(compound)),
        PolicyDecision("material-single-c901", _deduplicate(material_single)),
        PolicyDecision("auto-attention-v1", auto),
    )
    return StructuralAnalysis(all_rows, policies)


__all__ = [
    "CandidateSignal",
    "ObservationTarget",
    "POLICY_ORDER",
    "PolicyDecision",
    "REPORT_ONLY_CORRECTNESS",
    "STRICT_CORRECTNESS",
    "StructuralAnalysis",
    "analyze_structural",
]

