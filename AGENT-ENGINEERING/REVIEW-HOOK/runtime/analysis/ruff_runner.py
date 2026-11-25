"""Pinned Ruff execution over materialized committed blobs."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .git_snapshot import GitSnapshot
from .model import AnalysisStatus, PythonTarget
from .python_target import PythonTargetResolution

EXPECTED_RUFF_VERSION = "ruff 0.16.5"
STRUCTURAL_LIMITS = {
    "C901": 10,
    "PLR0912": 12,
    "PLR0915": 50,
    "PLR1702": 5,
    "PLR0916": 5,
}
CORRECTNESS_CODES = frozenset(
    {
        "F601",
        "F634",
        "PLE0101",
        "PLE0704",
        "PLE1205",
        "PLE1206",
        "B006",
        "B012",
        "B023",
        "B029",
        "B030",
        "B031",
    }
)
SELECTED_CODES = frozenset((*STRUCTURAL_LIMITS, *CORRECTNESS_CODES))
_METRIC = re.compile(r"\((\d+)\s*>\s*(\d+)\)\s*$")


@dataclass(frozen=True)
class RuffConfig:
    binary: Optional[Path] = None
    config_path: Path = Path(__file__).resolve().parents[2] / "policy" / "signals.ruff.toml"
    expected_version: str = EXPECTED_RUFF_VERSION
    timeout_seconds: float = 20.0
    version_timeout_seconds: float = 5.0
    max_output_bytes: int = 2_000_000
    temporary_parent: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.version_timeout_seconds <= 0:
            raise ValueError("Ruff timeouts must be positive")
        if type(self.max_output_bytes) is not int or self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be a positive integer")

    def resolve_binary(self) -> Path:
        if self.binary is not None:
            return self.binary
        override = os.environ.get("REVIEW_HOOK_RUFF")
        if override:
            return Path(override)
        source_root = Path(__file__).resolve().parents[2]
        bundled = source_root / "assets" / "ruff"
        if bundled.is_file():
            return bundled
        repository_candidate = Path(__file__).resolve().parents[4] / ".venv" / "bin" / "ruff"
        if repository_candidate.is_file():
            return repository_candidate
        found = shutil.which("ruff")
        return Path(found) if found else bundled


@dataclass(frozen=True)
class RuffDiagnostic:
    side: str
    path: str
    code: str
    message: str
    row: int
    column: int
    observed: Optional[int] = None
    limit: Optional[int] = None

    @property
    def signature(self) -> Tuple[str, str]:
        return self.code, self.message


@dataclass(frozen=True)
class RuffResult:
    status: AnalysisStatus
    version: Optional[str]
    diagnostics: Tuple[RuffDiagnostic, ...] = ()
    issues: Tuple[str, ...] = ()
    duration_ms: int = 0


def _result(
    status: AnalysisStatus,
    version: Optional[str],
    issue: Optional[str] = None,
    *,
    diagnostics: Sequence[RuffDiagnostic] = (),
    duration_ms: int = 0,
) -> RuffResult:
    return RuffResult(
        status,
        version,
        tuple(diagnostics),
        (issue,) if issue else (),
        duration_ms,
    )


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.communicate()


def _validate_version(binary: Path, config: RuffConfig) -> RuffResult:
    if not binary.is_file() or not os.access(str(binary), os.X_OK):
        return _result(
            AnalysisStatus.UNAVAILABLE,
            None,
            "ruff-unavailable:{}".format(binary),
        )
    try:
        process = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=config.version_timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return _result(
            AnalysisStatus.UNAVAILABLE, None, "ruff-version:{}".format(error)
        )
    version = process.stdout.strip()
    if process.returncode != 0:
        return _result(
            AnalysisStatus.UNAVAILABLE,
            version or None,
            "ruff-version-exit:{}".format(process.returncode),
        )
    if version != config.expected_version:
        return _result(
            AnalysisStatus.INCOMPATIBLE_RUFF_CONTRACT,
            version or None,
            "ruff-version-mismatch:expected={}:actual={}".format(
                config.expected_version, version
            ),
        )
    if not config.config_path.is_file():
        return _result(
            AnalysisStatus.UNAVAILABLE,
            version,
            "ruff-config-missing:{}".format(config.config_path),
        )
    return _result(AnalysisStatus.OK, version)


def _relative_filename(root: Path, filename: str) -> Tuple[str, str]:
    candidate = Path(filename)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError("ruff-path-outside-root:{}".format(filename)) from error
    side, separator, path = relative.partition("/")
    if not separator or side not in ("before", "after") or not path:
        raise ValueError("ruff-path-missing-side:{}".format(relative))
    return side, path


def _parse_payload(root: Path, payload: bytes) -> Tuple[RuffDiagnostic, ...]:
    try:
        decoded = json.loads(payload or b"[]")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("ruff-json:{}".format(error)) from error
    if not isinstance(decoded, list):
        raise ValueError("ruff-json:not-a-list")
    rows: List[RuffDiagnostic] = []
    for item in decoded:
        if not isinstance(item, dict):
            raise ValueError("ruff-json:diagnostic-not-an-object")
        code = item.get("code")
        message = item.get("message")
        filename = item.get("filename")
        location = item.get("location")
        if code is None:
            if not isinstance(message, str) or not isinstance(filename, str):
                raise ValueError("ruff-json:code-less-diagnostic-missing-fields")
            side, path = _relative_filename(root, filename)
            raise SyntaxError("{}:{}:{}".format(side, path, message[:240]))
        if (
            not isinstance(code, str)
            or code not in SELECTED_CODES
            or not isinstance(message, str)
            or not isinstance(filename, str)
            or not isinstance(location, dict)
            or type(location.get("row")) is not int
            or type(location.get("column")) is not int
        ):
            raise ValueError("ruff-json:missing-or-unexpected-field")
        side, path = _relative_filename(root, filename)
        observed = None
        limit = None
        if code in STRUCTURAL_LIMITS:
            match = _METRIC.search(message)
            if match is None:
                raise ValueError("ruff-metric-contract:{}:{}".format(code, message))
            observed = int(match.group(1))
            limit = int(match.group(2))
            if limit != STRUCTURAL_LIMITS[code]:
                raise ValueError(
                    "ruff-threshold-contract:{}:{}!={}".format(
                        code, limit, STRUCTURAL_LIMITS[code]
                    )
                )
        rows.append(
            RuffDiagnostic(
                side,
                path,
                code,
                message,
                location["row"],
                location["column"],
                observed,
                limit,
            )
        )
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                item.side,
                item.path,
                item.row,
                item.column,
                item.code,
                item.message,
            ),
        )
    )


def _run_group(
    binary: Path,
    version: str,
    root: Path,
    files: Sequence[Path],
    target: PythonTarget,
    config: RuffConfig,
) -> RuffResult:
    if not files:
        return _result(AnalysisStatus.OK, version)
    command = [
        str(binary),
        "check",
        "--config",
        str(config.config_path.resolve()),
        "--target-version",
        target.value,
        "--output-format",
        "json",
        "--exit-zero",
        "--no-cache",
        *[str(path) for path in files],
    ]
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        return _result(
            AnalysisStatus.UNAVAILABLE,
            version,
            "ruff-start:{}".format(error),
        )
    try:
        stdout, stderr = process.communicate(timeout=config.timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate(process)
        return _result(
            AnalysisStatus.TIMEOUT,
            version,
            "ruff-timeout:{}s".format(config.timeout_seconds),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except KeyboardInterrupt:
        _terminate(process)
        return _result(
            AnalysisStatus.CANCELLED,
            version,
            "ruff-cancelled",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except BaseException:
        _terminate(process)
        raise
    duration = int((time.monotonic() - started) * 1000)
    if process.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip()[:400]
        return _result(
            AnalysisStatus.ERROR,
            version,
            "ruff-exit:{}:{}".format(process.returncode, detail),
            duration_ms=duration,
        )
    if len(stdout) > config.max_output_bytes:
        return _result(
            AnalysisStatus.INCONCLUSIVE_SCOPE_OVERFLOW,
            version,
            "ruff-output-too-large:{}>{}".format(
                len(stdout), config.max_output_bytes
            ),
            duration_ms=duration,
        )
    try:
        diagnostics = _parse_payload(root, stdout)
    except SyntaxError as error:
        return _result(
            AnalysisStatus.INCOMPATIBLE_PYTHON_TARGET,
            version,
            "ruff-incompatible-syntax:{}".format(error),
            duration_ms=duration,
        )
    except ValueError as error:
        return _result(
            AnalysisStatus.INCOMPATIBLE_RUFF_CONTRACT,
            version,
            str(error),
            duration_ms=duration,
        )
    return _result(
        AnalysisStatus.OK,
        version,
        diagnostics=diagnostics,
        duration_ms=duration,
    )


def run_ruff(
    snapshot: GitSnapshot,
    targets: PythonTargetResolution,
    *,
    config: Optional[RuffConfig] = None,
) -> RuffResult:
    """Run the pinned contract, validating its version exactly once per event."""
    cfg = config or RuffConfig()
    binary = cfg.resolve_binary()
    validation = _validate_version(binary, cfg)
    if validation.status is not AnalysisStatus.OK:
        return validation
    assert validation.version is not None
    started = time.monotonic()
    all_diagnostics: List[RuffDiagnostic] = []
    with tempfile.TemporaryDirectory(
        prefix="review-scan-", dir=str(cfg.temporary_parent) if cfg.temporary_parent else None
    ) as temporary:
        root = Path(temporary)
        materialized: Dict[str, Tuple[Path, ...]] = {}
        by_path = {item.path: item for item in snapshot.python_files}
        for path, target in targets.by_file:
            item = by_path[path]
            rows: List[Path] = []
            for side, blob in (("before", item.before_blob), ("after", item.after_blob)):
                if blob is None:
                    continue
                destination = root / side / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(blob)
                rows.append(destination)
            materialized[path] = tuple(rows)
        for target, paths in targets.groups():
            files = tuple(
                file_path
                for path in paths
                for file_path in materialized.get(path, ())
            )
            result = _run_group(binary, validation.version, root, files, target, cfg)
            if result.status is not AnalysisStatus.OK:
                return result
            all_diagnostics.extend(result.diagnostics)
    return _result(
        AnalysisStatus.OK,
        validation.version,
        diagnostics=sorted(
            all_diagnostics,
            key=lambda item: (
                item.side,
                item.path,
                item.row,
                item.column,
                item.code,
                item.message,
            ),
        ),
        duration_ms=int((time.monotonic() - started) * 1000),
    )


__all__ = [
    "CORRECTNESS_CODES",
    "EXPECTED_RUFF_VERSION",
    "RuffConfig",
    "RuffDiagnostic",
    "RuffResult",
    "SELECTED_CODES",
    "STRUCTURAL_LIMITS",
    "run_ruff",
]

