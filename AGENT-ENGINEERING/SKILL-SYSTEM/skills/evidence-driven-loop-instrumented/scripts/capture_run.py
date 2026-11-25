#!/usr/bin/env python3
"""Execute one command and write a task-local, mechanically scoped run receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid


SCHEMA_VERSION = 1
TIMEOUT_EXIT = 124
SPAWN_ERROR_EXIT = 125
INTERRUPTED_EXIT = 130
TERMINATION_GRACE_SECONDS = 2.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _positive_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def _slugify(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return (slug or "run")[:48].rstrip("-")


def _write_json_atomic(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_artifact_paths(cwd: Path, raw_paths: list[str]) -> None:
    for raw in raw_paths:
        relative = Path(raw)
        if not raw or relative.is_absolute():
            raise ValueError(f"artifact path must be relative to --cwd: {raw!r}")
        resolved = (cwd / relative).resolve(strict=False)
        if not _inside(resolved, cwd):
            raise ValueError(f"artifact path escapes --cwd: {raw!r}")


def _inspect_artifact(cwd: Path, raw: str) -> dict[str, object]:
    candidate = cwd / raw
    resolved = candidate.resolve(strict=False)
    result: dict[str, object] = {"path": raw}
    if not _inside(resolved, cwd):
        result.update(
            {
                "exists": candidate.exists() or candidate.is_symlink(),
                "error": "path resolves outside --cwd after command",
            }
        )
        return result
    if candidate.is_symlink():
        result.update({"exists": True, "kind": "symlink"})
    elif not candidate.exists():
        result.update({"exists": False, "kind": "missing"})
    elif candidate.is_file():
        result.update(
            {
                "exists": True,
                "kind": "file",
                "size_bytes": candidate.stat().st_size,
                "sha256": _sha256_file(candidate),
            }
        )
    elif candidate.is_dir():
        result.update({"exists": True, "kind": "directory"})
    else:
        result.update({"exists": True, "kind": "other"})
    return result


def _signal_process_group(process: subprocess.Popen[bytes], *, force: bool) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        elif force:
            process.kill()
        else:
            process.terminate()
    except ProcessLookupError:
        pass


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    _signal_process_group(process, force=False)
    try:
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    _signal_process_group(process, force=True)
    process.wait()


def _portable_child_exit(exit_code: int | None) -> int:
    if exit_code is not None and 0 <= exit_code <= 255:
        return exit_code
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one argv command and save stdout, stderr, timing, and a JSON "
            "receipt in a unique task-local directory."
        )
    )
    parser.add_argument("--records-dir", required=True, type=Path)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--label", required=True)
    parser.add_argument("--prediction", required=True)
    parser.add_argument("--success-condition", required=True)
    parser.add_argument("--timeout", type=_positive_float)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="RELATIVE_PATH",
        help="Path relative to --cwd to inspect after execution; repeatable.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command argv after --. Shell expansion is not performed.",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    cwd = args.cwd.resolve()
    records_dir = args.records_dir.resolve()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]

    if not cwd.is_dir():
        raise ValueError(f"--cwd is not a directory: {cwd}")
    if records_dir == Path(records_dir.anchor):
        raise ValueError("--records-dir cannot be a filesystem root")
    if not args.label.strip():
        raise ValueError("--label cannot be empty")
    if not args.prediction.strip():
        raise ValueError("--prediction cannot be empty")
    if not args.success_condition.strip():
        raise ValueError("--success-condition cannot be empty")
    if not command:
        raise ValueError("a command is required after --")
    _validate_artifact_paths(cwd, args.artifact)

    records_dir.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + f"-{_slugify(args.label)}-{uuid.uuid4().hex[:8]}"
    )
    run_dir = records_dir / run_id
    run_dir.mkdir(exist_ok=False)
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"

    intent: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "starting",
        "label": args.label,
        "prediction": args.prediction,
        "success_condition": args.success_condition,
        "started_at": started_at,
        "cwd": str(cwd),
        "command": command,
        "timeout_seconds": args.timeout,
        "artifact_paths": list(args.artifact),
    }
    _write_json_atomic(run_dir / "started.json", intent)

    status = "spawn-error"
    exit_code: int | None = None
    error: str | None = None
    timed_out = False
    interrupted = False
    wrapper_exit = SPAWN_ERROR_EXIT
    process: subprocess.Popen[bytes] | None = None
    monotonic_start = time.monotonic()

    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                start_new_session=os.name == "posix",
            )
            try:
                exit_code = process.wait(timeout=args.timeout)
                status = "completed" if exit_code == 0 else "failed"
                wrapper_exit = _portable_child_exit(exit_code)
            except subprocess.TimeoutExpired:
                timed_out = True
                status = "timed-out"
                _terminate_process(process)
                exit_code = process.returncode
                wrapper_exit = TIMEOUT_EXIT
            except KeyboardInterrupt:
                interrupted = True
                status = "interrupted"
                _terminate_process(process)
                exit_code = process.returncode
                wrapper_exit = INTERRUPTED_EXIT
        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"

    finished_at = _utc_now()
    receipt: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "label": args.label,
        "prediction": args.prediction,
        "success_condition": args.success_condition,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(time.monotonic() - monotonic_start, 6),
        "cwd": str(cwd),
        "command": command,
        "timeout_seconds": args.timeout,
        "timed_out": timed_out,
        "interrupted": interrupted,
        "exit_code": exit_code,
        "error": error,
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "artifacts": [_inspect_artifact(cwd, raw) for raw in args.artifact],
    }
    receipt_path = run_dir / "receipt.json"
    _write_json_atomic(receipt_path, receipt)
    print(f"receipt: {receipt_path}")
    return wrapper_exit


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return _run(args)
    except ValueError as exc:
        parser.error(str(exc))
    except OSError as exc:
        print(f"capture_run.py: {type(exc).__name__}: {exc}", file=sys.stderr)
        return SPAWN_ERROR_EXIT
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
