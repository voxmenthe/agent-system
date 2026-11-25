#!/usr/bin/env python3
"""Tests for `xgrok --usage` and the xgrok_usage.py billing-RPC helper.

CLI tests run the real xgrok launcher against a fake `grok` executable that
speaks the agent-stdio JSON-RPC protocol; the scenario is selected with
XGROK_FAKE_SCENARIO and the captured GROK_HOME is written to
XGROK_FAKE_CAPTURE.

Run: PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_xgrok_usage.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xgrok_usage  # noqa: E402

LAUNCHER = Path(__file__).resolve().parent / "xgrok"

FAKE_GROK = r"""#!/usr/bin/env python3
import json
import os
import sys
import time

capture = os.environ.get("XGROK_FAKE_CAPTURE")
if capture:
    with open(capture, "w", encoding="utf-8") as fh:
        json.dump({"argv": sys.argv[1:], "grok_home": os.environ.get("GROK_HOME")}, fh)

pidfile = os.environ.get("XGROK_FAKE_PIDFILE")
if pidfile:
    with open(pidfile, "w") as fh:
        fh.write(str(os.getpid()))

scenario = os.environ.get("XGROK_FAKE_SCENARIO", "new")
if scenario == "silent":
    time.sleep(300)
    sys.exit(0)


def emit(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


RESPONSES = {
    "new": {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "config": {
                "creditUsagePercent": 42.5,
                "currentPeriod": {
                    "start": "2026-09-01T00:00:00Z",
                    "end": "2026-10-01T00:00:00Z",
                    "type": "USAGE_PERIOD_TYPE_MONTHLY",
                },
                "used": {"val": 4250},
                "monthlyLimit": {"val": 10000},
            },
            "subscription_tier": "SuperGrok",
        },
    },
    "legacy": {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "config": {
                "used": {"val": 400},
                "monthlyLimit": {"val": 1000},
                "billingPeriodStart": "2026-09-01T00:00:00+00:00",
                "billingPeriodEnd": "2026-10-01T00:00:00+00:00",
            },
            "subscription_tier": "Standard",
        },
    },
    "rpc_error": {
        "jsonrpc": "2.0",
        "id": 2,
        "error": {"code": -32603, "message": "Internal error", "data": "billing backend down"},
    },
    "malformed": {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {"config": {"creditUsagePercent": "soon"}},
    },
    "no_usage": {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "config": {
                "currentPeriod": {
                    "start": "2026-09-01T00:00:00Z",
                    "end": "2026-10-01T00:00:00Z",
                }
            },
            "subscription_tier": "SuperGrok",
        },
    },
}

interleave = os.environ.get("XGROK_FAKE_INTERLEAVE")
# Billing requests to fail before the scenario's answer, as xAI's service did for ~/.grok3.
billing_errors = int(os.environ.get("XGROK_FAKE_BILLING_ERRORS", "0"))

# The real CLI stays up after answering and takes about 2.3 s to exit once asked (10-29).
slow_exit = os.environ.get("XGROK_FAKE_SLOW_EXIT")
if slow_exit:
    import signal
    signal.signal(signal.SIGTERM, lambda *_: (time.sleep(3), sys.exit(0)))

for raw in sys.stdin:
    try:
        msg = json.loads(raw)
    except ValueError:
        continue
    if msg.get("id") == 1:
        if interleave:
            emit({"jsonrpc": "2.0", "method": "agent/progress", "params": {"pct": 10}})
            emit({"jsonrpc": "2.0", "id": 99, "method": "server/ping", "params": {}})
        emit({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": 1, "capabilities": {}}})
    elif msg.get("id") == 2:
        if interleave:
            emit({"jsonrpc": "2.0", "method": "agent/progress", "params": {"pct": 90}})
            sys.stdout.write("non-json chatter on stdout\n")
            sys.stdout.flush()
        if billing_errors or scenario == "rpc_error":
            billing_errors -= 1
            emit(RESPONSES["rpc_error"])
            continue
        emit(RESPONSES[scenario])
        if slow_exit:
            continue
        sys.exit(0)
if slow_exit:
    time.sleep(3)
"""


class UsageCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin_dir = root / "bin"
        self.bin_dir.mkdir()
        fake = self.bin_dir / "grok"
        fake.write_text(FAKE_GROK)
        fake.chmod(0o755)
        self.capture = root / "capture.json"
        self.env = {
            "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}",
            "XGROK_FAKE_CAPTURE": str(self.capture),
        }

    def run_xgrok(self, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
        env = dict(self.env)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [str(LAUNCHER), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def captured_grok_home(self) -> str:
        return json.loads(self.capture.read_text())["grok_home"]

    def test_new_schema_reports_quota_for_default_account(self):
        result = self.run_xgrok("--usage", env_extra={"XGROK_FAKE_SCENARIO": "new"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SuperGrok", result.stdout)
        self.assertIn("42.5% used", result.stdout)
        self.assertIn("57.5% remaining", result.stdout)
        self.assertIn("hours and", result.stdout)
        self.assertIn("minutes until reset at 2026-09-30 17:00 PDT", result.stdout)
        self.assertIn("fetched", result.stdout)
        self.assertEqual(self.captured_grok_home(), str(Path.home() / ".grok"))

    def test_account_flags_route_to_their_homes(self):
        for flag, variable in (("--grok2", "GROK2_HOME"), ("--grok3", "GROK3_HOME")):
            with self.subTest(flag=flag):
                home = str(Path(self.tmp.name) / f"{variable}-home")
                result = self.run_xgrok(
                    "--usage", flag,
                    env_extra={"XGROK_FAKE_SCENARIO": "new", variable: home},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.captured_grok_home(), home)
                self.assertIn(home, result.stdout)

    def test_grok_home_flag_routes_custom_path(self):
        custom = str(Path(self.tmp.name) / "custom-home")
        result = self.run_xgrok(
            "--usage", "--grok-home", custom,
            env_extra={"XGROK_FAKE_SCENARIO": "new"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.captured_grok_home(), custom)

    def test_inherited_grok_home_env_is_preserved(self):
        preset = str(Path(self.tmp.name) / "preset-home")
        result = self.run_xgrok(
            "--usage",
            env_extra={"XGROK_FAKE_SCENARIO": "new", "GROK_HOME": preset},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.captured_grok_home(), preset)

    def test_legacy_schema_reports_derived_percentage(self):
        result = self.run_xgrok("--usage", env_extra={"XGROK_FAKE_SCENARIO": "legacy"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Standard", result.stdout)
        self.assertIn("40% used", result.stdout)
        self.assertIn("60% remaining", result.stdout)

    def test_interleaved_notifications_and_chatter_are_skipped(self):
        result = self.run_xgrok(
            "--usage",
            env_extra={"XGROK_FAKE_SCENARIO": "new", "XGROK_FAKE_INTERLEAVE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("42.5% used", result.stdout)

    def test_rpc_error_fails_nonzero(self):
        result = self.run_xgrok("--usage", env_extra={"XGROK_FAKE_SCENARIO": "rpc_error"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("billing backend down", result.stderr)
        self.assertNotIn("% used", result.stdout)

    def test_billing_errors_are_resent_within_the_session(self):
        result = self.run_xgrok("--usage", env_extra={"XGROK_FAKE_SCENARIO": "new", "XGROK_FAKE_BILLING_ERRORS": "3"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("42.5% used", result.stdout)
        result = self.run_xgrok("--usage", env_extra={"XGROK_FAKE_SCENARIO": "new", "XGROK_FAKE_BILLING_ERRORS": "4"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Internal error: billing backend down", result.stderr)

    def test_malformed_quota_fails_nonzero(self):
        result = self.run_xgrok("--usage", env_extra={"XGROK_FAKE_SCENARIO": "malformed"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credit usage", result.stderr)
        self.assertNotIn("% used", result.stdout)

    def test_a_period_with_no_usage_field_reads_as_none_used_yet(self):
        # Oct 1-10: all six responses without creditUsagePercent came between a weekly reset and the account's first
        # use, and the next reading was 2-7%; failing left a full account unchosen (~/.grok2, Oct 7-10).
        result = self.run_xgrok("--usage", env_extra={"XGROK_FAKE_SCENARIO": "no_usage"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0% used (no usage reported this period), 100% remaining", result.stdout)

    def test_deadline_is_enforced_and_child_is_reaped(self):
        pidfile = Path(self.tmp.name) / "fake.pid"
        result = self.run_xgrok(
            "--usage",
            env_extra={
                "XGROK_FAKE_SCENARIO": "silent",
                "XGROK_USAGE_TIMEOUT_S": "2",
                "XGROK_FAKE_PIDFILE": str(pidfile),
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("deadline", result.stderr)
        fake_pid = int(pidfile.read_text().strip())
        with self.assertRaises(ProcessLookupError):
            os.kill(fake_pid, 0)

    def test_a_slow_exiting_cli_does_not_delay_the_reading(self):
        pidfile = Path(self.tmp.name) / "fake.pid"
        env = {**os.environ, **self.env, "XGROK_FAKE_SLOW_EXIT": "1", "XGROK_FAKE_PIDFILE": str(pidfile)}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            started = time.monotonic()
            response = xgrok_usage.fetch_billing_response(str(self.bin_dir / "grok"), self.tmp.name, 10)
            elapsed = time.monotonic() - started
        self.assertEqual(42.5, response["result"]["config"]["creditUsagePercent"])
        self.assertLess(elapsed, 1.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)

    def test_usage_rejects_brief_file_and_mode(self):
        brief = Path(self.tmp.name) / "brief.md"
        brief.write_text("brief fixture\n")
        result = self.run_xgrok("--usage", str(brief))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--usage does not take a brief", result.stderr)
        result = self.run_xgrok("--usage", "--mode", "harvest")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--usage cannot be combined with --mode", result.stderr)

    def test_non_finite_deadlines_fail_before_launch(self):
        for bad in ("nan", "inf", "-inf"):
            result = self.run_xgrok("--usage", env_extra={"XGROK_USAGE_TIMEOUT_S": bad})
            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid XGROK_USAGE_TIMEOUT_S", result.stderr)
            self.assertFalse(self.capture.exists())

    def test_missing_grok_cli_fails(self):
        empty_bin = Path(self.tmp.name) / "empty-bin"
        empty_bin.mkdir()
        path = os.pathsep.join(
            [str(empty_bin), str(Path(sys.executable).parent), "/usr/bin", "/bin"]
        )
        result = self.run_xgrok("--usage", env_extra={"PATH": path})
        self.assertEqual(result.returncode, 127)
        self.assertIn("not on PATH", result.stderr)


class ParseQuotaTests(unittest.TestCase):
    def message(self, config: dict, tier: str = "SuperGrok") -> dict:
        return {"jsonrpc": "2.0", "id": 2, "result": {"config": config, "subscription_tier": tier}}

    def test_missing_result_or_config_fails(self):
        with self.assertRaises(xgrok_usage.UsageError):
            xgrok_usage.parse_quota({"id": 2, "result": None})
        with self.assertRaises(xgrok_usage.UsageError):
            xgrok_usage.parse_quota({"id": 2, "result": {"config": "nope"}})

    def test_missing_period_end_fails(self):
        msg = self.message({"creditUsagePercent": 10, "currentPeriod": {"start": "2026-09-01T00:00:00Z"}})
        with self.assertRaises(xgrok_usage.UsageError):
            xgrok_usage.parse_quota(msg)

    def test_inverted_period_fails(self):
        msg = self.message(
            {
                "creditUsagePercent": 10,
                "currentPeriod": {"start": "2026-10-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"},
            }
        )
        with self.assertRaises(xgrok_usage.UsageError):
            xgrok_usage.parse_quota(msg)

    def test_bool_or_string_percent_fails_without_legacy_fields(self):
        for bad in (True, "42.5", float("nan"), float("inf"), -1):
            msg = self.message(
                {
                    "creditUsagePercent": bad,
                    "currentPeriod": {"start": "2026-09-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
                }
            )
            with self.assertRaises(xgrok_usage.UsageError, msg=bad):
                xgrok_usage.parse_quota(msg)

    def test_missing_usage_without_a_current_period_still_fails(self):
        for config in ({}, {"billingPeriodStart": "2026-09-01T00:00:00Z", "billingPeriodEnd": "2026-10-01T00:00:00Z"},
                       {"creditUsagePercent": None,
                        "currentPeriod": {"start": "2026-09-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"}}):
            with self.assertRaises(xgrok_usage.UsageError, msg=config):
                xgrok_usage.parse_quota(self.message(config))

    def test_zero_limit_cannot_derive_percentage(self):
        msg = self.message(
            {
                "used": {"val": 0},
                "monthlyLimit": {"val": 0},
                "billingPeriodStart": "2026-09-01T00:00:00Z",
                "billingPeriodEnd": "2026-10-01T00:00:00Z",
            }
        )
        with self.assertRaises(xgrok_usage.UsageError):
            xgrok_usage.parse_quota(msg)

    def test_missing_tier_falls_back_to_generic_name(self):
        msg = self.message(
            {
                "creditUsagePercent": 100,
                "currentPeriod": {"start": "2026-09-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
            },
            tier="",
        )
        quota = xgrok_usage.parse_quota(msg)
        self.assertEqual(quota.name, "Usage")
        self.assertEqual(quota.used_percent, 100.0)


class FormatReportTests(unittest.TestCase):
    def test_countdown_and_percent_rendering(self):
        now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
        quota = xgrok_usage.Quota(
            name="SuperGrok",
            used_percent=42.0,
            reset_epoch=(now + timedelta(hours=3, minutes=11, seconds=30)).timestamp(),
        )
        report = xgrok_usage.format_report(quota, str(Path.home() / ".grok"), now=now)
        self.assertIn("SuperGrok: 42% used, 58% remaining", report)
        self.assertIn("3 hours and 12 minutes until reset", report)
        self.assertIn("fetched", report)

    def test_non_default_home_is_labeled(self):
        now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
        quota = xgrok_usage.Quota(name="Usage", used_percent=0, reset_epoch=now.timestamp())
        report = xgrok_usage.format_report(quota, "/tmp/custom-home", now=now)
        self.assertIn("[/tmp/custom-home]", report)
        self.assertIn("0 hours and 0 minutes until reset", report)


if __name__ == "__main__":
    unittest.main()
