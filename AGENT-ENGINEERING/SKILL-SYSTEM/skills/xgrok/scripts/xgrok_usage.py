#!/usr/bin/env python3
"""Print the selected Grok account's subscription quota.

`xgrok --usage` execs this helper. It launches `grok agent stdio` under
GROK_HOME (default ~/.grok), performs the initialize handshake, issues the
_x.ai/billing RPC, and prints one summary line: fetched timestamp, used and
remaining credit percentage, time until reset, and the Pacific reset time.
It makes no model or X calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo

RPC_TIMEOUT_SECONDS = 20.0
READ_CHUNK_BYTES = 65536
MAX_LINE_BYTES = 4 * 1024 * 1024
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_GROK_HOME = str(Path.home() / ".grok")

INITIALIZE_REQUEST: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": 1,
        "clientCapabilities": {},
        "clientInfo": {"name": "xgrok-usage", "version": "1"},
    },
}
INITIALIZED_NOTIFICATION: dict[str, Any] = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
BILLING_REQUEST: dict[str, Any] = {"jsonrpc": "2.0", "id": 2, "method": "_x.ai/billing", "params": {}}
# xAI's billing service fails single requests on some accounts (~/.grok3, 10-29: 2 in 3 calls,
# "meter unavailable" or "snapshot failed"); a resend in the same session can succeed.
BILLING_ATTEMPTS = 4


class UsageError(Exception):
    """A user-facing quota lookup failure."""


class RpcError(UsageError):
    """grok agent stdio answered a request with a JSON-RPC error."""


@dataclass(frozen=True)
class Quota:
    name: str
    used_percent: float
    reset_epoch: float
    reported: bool = True  # False: the current period has no usage field yet, read as 0% used


def _send(proc: subprocess.Popen, message: dict[str, Any]) -> None:
    try:
        proc.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        proc.stdin.flush()
    except OSError as exc:
        raise UsageError(f"grok agent stdio is not accepting requests: {exc}") from exc


def _read_line(fd: int, buf: bytearray, deadline: float) -> bytes:
    """Return one stdout line without the newline, or b"" at EOF."""
    while True:
        newline = buf.find(b"\n")
        if newline >= 0:
            line = bytes(buf[:newline])
            del buf[: newline + 1]
            return line
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(fd, READ_CHUNK_BYTES)
        except OSError as exc:
            raise UsageError(f"reading grok agent stdio failed: {exc}") from exc
        if not chunk:
            line = bytes(buf)
            buf.clear()
            return line
        buf.extend(chunk)
        if len(buf) > MAX_LINE_BYTES:
            raise UsageError("grok agent stdio sent an unterminated oversized line")


def _await_response(
    proc: subprocess.Popen,
    buf: bytearray,
    request_id: int,
    label: str,
    deadline: float,
    timeout_s: float,
) -> dict[str, Any]:
    """Read stdout until the JSON-RPC response for request_id arrives.

    Notifications, peer requests, and non-JSON chatter are skipped.
    """
    fd = proc.stdout.fileno()
    while True:
        try:
            line = _read_line(fd, buf, deadline)
        except TimeoutError:
            raise UsageError(f"{label} request exceeded the {timeout_s:g}s deadline") from None
        if not line:
            raise UsageError(f"grok agent stdio exited before answering {label}")
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict) or "method" in message or message.get("id") != request_id:
            continue
        error = message.get("error")
        if error is not None:
            detail = error
            if isinstance(error, dict):
                detail = ": ".join(str(part) for part in (error.get("message"), error.get("data")) if part)
            raise RpcError(f"{label} RPC returned an error: {detail}")
        return message


def fetch_billing_response(grok_bin: str, grok_home: str, timeout_s: float) -> dict[str, Any]:
    """Run the initialize + _x.ai/billing handshake against `grok agent stdio`, resending a billing
    request the service answered with an error, BILLING_ATTEMPTS requests in all.

    The child is killed and reaped on every return path.
    """
    env = dict(os.environ)
    env["GROK_HOME"] = grok_home
    try:
        proc = subprocess.Popen(
            [grok_bin, "agent", "stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
            env=env,
        )
    except OSError as exc:
        raise UsageError(f"could not launch 'grok agent stdio': {exc}") from exc

    deadline = time.monotonic() + timeout_s
    buf = bytearray()
    try:
        _send(proc, INITIALIZE_REQUEST)
        _await_response(proc, buf, 1, "initialize", deadline, timeout_s)
        _send(proc, INITIALIZED_NOTIFICATION)
        for _ in range(BILLING_ATTEMPTS - 1):
            _send(proc, BILLING_REQUEST)
            try:
                return _await_response(proc, buf, 2, "_x.ai/billing", deadline, timeout_s)
            except RpcError:
                continue
        _send(proc, BILLING_REQUEST)
        return _await_response(proc, buf, 2, "_x.ai/billing", deadline, timeout_s)
    finally:
        # Asked to stop, grok takes about 2.3 s to exit (10-29), past the 2 s grace it once had, so every
        # reading waited 2 s and ended in a kill anyway. It keeps no state but its log: kill it at once.
        proc.kill()
        proc.wait()
        for pipe in (proc.stdin, proc.stdout):
            try:
                pipe.close()
            except OSError:
                pass


def _number(node: Any) -> float | None:
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        return None
    value = float(node)
    if not math.isfinite(value) or value < 0:
        raise UsageError("billing response contains an invalid quota number")
    return value


def _legacy_amount(node: Any) -> float | None:
    direct = _number(node)
    if direct is not None:
        return direct
    if isinstance(node, dict):
        return _number(node.get("val"))
    return None


def _iso_epoch(value: Any) -> float:
    if not isinstance(value, str):
        raise UsageError("billing response is missing a period bound")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise UsageError(f"billing response has an unparseable period bound: {value!r}") from None
    if parsed.tzinfo is None:
        raise UsageError(f"billing response period bound lacks a timezone: {value!r}")
    return parsed.timestamp()


def parse_quota(message: dict[str, Any]) -> Quota:
    """Extract name, used percentage, and reset time from a billing response.

    Accepts the current schema (config.creditUsagePercent + config.currentPeriod)
    and the legacy schema (config.used.val / config.monthlyLimit.val +
    config.billingPeriodStart/End). A current period with no creditUsagePercent key
    is 0% used: all six such responses (Oct 1-10, both accounts) came between a weekly
    reset and the first use, and the next reading was 2-7%. Any other unknown usage
    fails loudly, never as zero.
    """
    result = message.get("result")
    if not isinstance(result, dict):
        raise UsageError("billing response has no result object")
    config = result.get("config")
    if not isinstance(config, dict):
        raise UsageError("billing response has no config object")

    used_percent = _number(config.get("creditUsagePercent"))
    if used_percent is None:
        limit = _legacy_amount(config.get("monthlyLimit"))
        used = _legacy_amount(config.get("used"))
        if limit is not None and limit > 0 and used is not None:
            used_percent = used / limit * 100.0
    period = config.get("currentPeriod")
    reported = True
    if used_percent is None and "creditUsagePercent" not in config and isinstance(period, dict) \
            and isinstance(period.get("start"), str) and isinstance(period.get("end"), str):
        used_percent, reported = 0.0, False
    if used_percent is None:
        raise UsageError("billing response does not report credit usage")
    used_percent = min(100.0, max(0.0, used_percent))

    period = period if isinstance(period, dict) else {}
    start_raw = period.get("start") if isinstance(period.get("start"), str) else config.get("billingPeriodStart")
    end_raw = period.get("end") if isinstance(period.get("end"), str) else config.get("billingPeriodEnd")
    start_epoch = _iso_epoch(start_raw)
    reset_epoch = _iso_epoch(end_raw)
    if reset_epoch <= start_epoch:
        raise UsageError("billing response period end is not after its start")

    name = result.get("subscription_tier")
    if not isinstance(name, str) or not name.strip():
        name = "Usage"
    return Quota(name=name.strip(), used_percent=used_percent, reset_epoch=reset_epoch, reported=reported)


def _fmt_percent(value: float) -> str:
    rounded = round(value, 1)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"


def format_report(quota: Quota, grok_home: str, now: datetime | None = None) -> str:
    fetched = now or datetime.now(timezone.utc)
    remaining = max(0.0, 100.0 - quota.used_percent)
    seconds_left = max(0, int(quota.reset_epoch - fetched.timestamp()))
    total_minutes = (seconds_left + 59) // 60
    hours, minutes = divmod(total_minutes, 60)
    reset_pacific = datetime.fromtimestamp(quota.reset_epoch, PACIFIC_TZ)
    fetched_pacific = fetched.astimezone(PACIFIC_TZ)
    account = "" if grok_home == DEFAULT_GROK_HOME else f" [{grok_home}]"
    return (
        f"{quota.name}{account}: {_fmt_percent(quota.used_percent)}% used"
        f"{'' if quota.reported else ' (no usage reported this period)'}, "
        f"{_fmt_percent(remaining)}% remaining; {hours} hours and {minutes} minutes until reset "
        f"at {reset_pacific:%Y-%m-%d %H:%M %Z} (fetched {fetched_pacific:%Y-%m-%d %H:%M:%S %Z})"
    )


def _timeout_seconds() -> float:
    override = os.environ.get("XGROK_USAGE_TIMEOUT_S")
    if not override:
        return RPC_TIMEOUT_SECONDS
    try:
        value = float(override)
    except ValueError:
        raise UsageError(f"invalid XGROK_USAGE_TIMEOUT_S: {override!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise UsageError(f"invalid XGROK_USAGE_TIMEOUT_S: {override!r}")
    return value


def main() -> int:
    grok_home = os.environ.get("GROK_HOME") or DEFAULT_GROK_HOME
    grok_bin = shutil.which("grok")
    if grok_bin is None:
        sys.stderr.write("xgrok: grok is not on PATH\n")
        return 127
    try:
        response = fetch_billing_response(grok_bin, grok_home, _timeout_seconds())
        quota = parse_quota(response)
    except UsageError as exc:
        sys.stderr.write(f"xgrok: {exc}\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("xgrok: billing query interrupted\n")
        return 130
    print(format_report(quota, grok_home))
    return 0


if __name__ == "__main__":
    sys.exit(main())
