import base64
import hashlib
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

WRAPPERS = Path(__file__).resolve().parents[1] / ".bash_agents"
BASH = shutil.which("bash")


class UsageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="usage-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.home.mkdir()
        self.bin.mkdir()
        (self.bin / "jq").symlink_to(shutil.which("jq"))
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            PATH=f"{self.bin}:/usr/bin:/bin",
            TMPDIR=str(self.root),
        )
        for key in ("COMMAND_CODE_API_KEY", "OPENCODE_API_KEY", "CODEX2_HOME", "GROK2_HOME", "GROK3_HOME", "AGY2_HOME", "SSH_CONNECTION",
                    "CLAUDE_CONFIG_DIR", "XDG_CACHE_HOME", "USAGE_CLAUDE_CACHE_TTL",
                    "CLAUDE_CONSOLE_COOKIE_JAR",
                    "USAGE_ANTIGRAVITY_CACHE_TTL", "USAGE_ANTIGRAVITY_TIMEOUT"):
            self.env.pop(key, None)
        # Also makes the old, incorrect retry path fast for regression checks.
        self.env["USAGE_CLAUDE_RETRY_DELAY"] = "0"
        # Never read the developer's real macOS Keychain in these tests.
        self.executable("security", "#!/bin/sh\nexit 1\n")
        self.executable("curl", "#!/bin/sh\nexit 1\n")

    def executable(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def start(self, *usage_args: str) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            [
                BASH,
                "--noprofile",
                "--norc",
                "-c",
                'source "$1"; shift; usage "$@"',
                "usage-test",
                str(WRAPPERS),
                *usage_args,
            ],
            env=self.env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self.addCleanup(self.stop, process)
        return process

    def test_filter_claude_skips_unselected_clis_and_summary_entries(self) -> None:
        expiry = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        self.claude_response({
            "seven_day": {"utilization": 20, "resets_at": expiry},
            "cedar_ember": {"eligible": True, "grants": [
                {"resets_left": 2, "ends_at": expiry},
            ]},
        })
        for cli in ("codex", "agy", "grok", "cmd", "amp", "opencode"):
            self.executable(cli, '#!/bin/sh\ntouch "$TMPDIR/unselected-cli-ran"\nexit 1\n')
        process = self.start("-a", "claude")
        output, errors = process.communicate(timeout=5)
        text = output.decode()
        headers = [line.split(" ─", 1)[0] for line in text.splitlines()
                   if line.startswith("── ")]
        self.assertEqual(["── Claude", "── Credits expiring soonest"], headers)
        summary = text.split("── Credits expiring soonest", 1)[1]
        self.assertIn("Claude · Weekly [weekly]", summary)
        self.assertIn("Claude: 2 available", summary)
        self.assertFalse((self.root / "unselected-cli-ran").exists())
        self.assertEqual(0, process.returncode, errors.decode())
        self.assertEqual(b"", errors)
        self.assertEqual([], list(self.root.glob("usage.*")))

    def test_filter_multiple_harnesses_accepts_unquoted_and_quoted_commas(self) -> None:
        self.codex_responses(self.codex_quota())
        for names in (("claude,", "codex,", "devin"),
                      ("claude,codex,devin",),
                      (" claude , codex, devin ",),
                      ("codex,claude,devin,codex",)):
            with self.subTest(names=names):
                process = self.start("-a", *names)
                output, errors = process.communicate(timeout=5)
                text = output.decode()
                headers = [line.split(" ─", 1)[0] for line in text.splitlines()
                           if line.startswith("── ")]
                self.assertCountEqual(
                    ["── Claude", "── Codex", "── Devin", "── 5-hour limits",
                     "── Credits expiring soonest"],
                    headers,
                )
                self.assertEqual("── 5-hour limits", headers[-2])
                self.assertEqual("── Credits expiring soonest", headers[-1])
                five_hour = text.split("── 5-hour limits", 1)[1].split(
                    "── Credits expiring soonest", 1)[0]
                summary = text.split("── Credits expiring soonest", 1)[1]
                self.assertIn("Codex · Codex [5h]", five_hour)
                self.assertNotIn("Codex · Codex [5h]", summary)
                self.assertIn("Claude: no subscription login", summary)
                self.assertNotIn("Antigravity", text)
                self.assertNotIn("Kimi", text)
                self.assertEqual(1, process.returncode)
                self.assertEqual(b"", errors)

    def test_filter_rejects_invalid_arguments_before_any_work(self) -> None:
        self.executable("mktemp", '#!/bin/sh\ntouch "$TMPDIR/scratch-created"\nexit 1\n')
        self.executable("security", '#!/bin/sh\ntouch "$TMPDIR/keychain-read"\nexit 1\n')
        for args in (("-a",), ("-a", ""), ("-a", ","),
                     ("-a", "claude,,codex"), ("-a", "claude,"),
                     ("-a", "claude,unknown"), ("-a", "claude codex"),
                     ("-a", "claude\ncodex"), ("-a", "mimo"),
                     ("--unknown",), ("claude",)):
            with self.subTest(args=args):
                process = self.start(*args)
                output, errors = process.communicate(timeout=5)
                self.assertEqual(2, process.returncode)
                self.assertEqual(b"", output)
                self.assertIn(b"usage", errors)
                self.assertFalse((self.root / "scratch-created").exists())
                self.assertFalse((self.root / "keychain-read").exists())

    def test_short_harness_aliases(self) -> None:
        # oc/agy are short aliases for opencode/antigravity, matching the
        # agents inventory flags. Canonical names and aliases both work.
        for name, expected_header, absent_header in (
            ("oc", "── OpenCode Go", "── Antigravity"),
            ("agy", "── Antigravity", "── OpenCode Go"),
            ("opencode", "── OpenCode Go", "── Antigravity"),
            ("antigravity", "── Antigravity", "── OpenCode Go"),
        ):
            with self.subTest(name=name):
                process = self.start("-a", name)
                output, errors = process.communicate(timeout=5)
                text = output.decode()
                self.assertNotEqual(2, process.returncode, errors.decode())
                self.assertIn(expected_header, text)
                self.assertNotIn(absent_header, text)
                self.assertNotIn(b"unknown or empty harness", errors)

    @staticmethod
    def stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=5)

    def test_ready_sections_print_before_blocked_provider(self) -> None:
        release = self.root / "release"
        os.mkfifo(release)
        # Opening both ends here makes test cleanup independent of CLI startup.
        fd = os.open(release, os.O_RDWR)
        self.addCleanup(os.close, fd)
        self.env["RELEASE"] = str(release)
        self.executable("agy", '#!/bin/sh\nread line < "$RELEASE"\nexit 1\n')
        process = self.start()
        data = b""
        deadline = time.monotonic() + 2
        try:
            while b"amp is not on PATH" not in data and time.monotonic() < deadline:
                if select.select([process.stdout], [], [], 0.1)[0]:
                    data += os.read(process.stdout.fileno(), 65536)
            self.assertIn(b"amp is not on PATH", data)
            self.assertNotIn("── Antigravity ".encode(), data)
            self.assertNotIn(b"Credits expiring soonest", data)
            self.assertIsNone(process.poll())
        finally:
            os.write(fd, b"release\n")
            rest, errors = process.communicate(timeout=5)
        output = (data + rest).decode()
        self.assertEqual(1, process.returncode, errors.decode())
        headers = [line for line in output.splitlines() if line.startswith("── ")]
        self.assertEqual(11, len(headers))
        self.assertEqual(11, len(set(headers)))
        self.assertIn("Credits expiring soonest", headers[-1])
        self.assertEqual([], list(self.root.glob("usage.*")))

    def test_summary_leads_with_when_usage_ran(self) -> None:
        zone = ZoneInfo("America/Los_Angeles")
        before = datetime.now(zone) - timedelta(seconds=2)
        output, errors = self.start().communicate(timeout=10)
        after = datetime.now(zone) + timedelta(seconds=2)
        text = output.decode()
        summary = text.split("── Credits expiring soonest", 1)[-1]
        first_line = summary.splitlines()[1]
        match = re.fullmatch(
            r"  usage run (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (PST|PDT)", first_line
        )
        self.assertIsNotNone(match, first_line)
        ran_at = datetime.strptime(
            match.group(1), "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=zone)
        self.assertLessEqual(before, ran_at)
        self.assertLessEqual(ran_at, after)
        self.assertEqual(b"", errors)

    def claude_response(self, payload: dict, status: int = 200, *, file_login: bool = False) -> None:
        credentials = json.dumps({"claudeAiOauth": {
            "accessToken": "fake-claude-oauth-token", "refreshToken": "fake-refresh-token",
        }})
        if file_login:
            config = self.home / "custom-claude"
            config.mkdir()
            (config / ".credentials.json").write_text(credentials)
            self.env["CLAUDE_CONFIG_DIR"] = str(config)
            self.executable("security", '#!/bin/sh\ntouch "$TMPDIR/keychain-called"\nexit 1\n')
        else:
            self.executable("security", f"#!/bin/sh\nprintf '%s\\n' '{credentials}'\n")
        self.env["CLAUDE_USAGE_RESPONSE"] = json.dumps(payload)
        self.env["CLAUDE_USAGE_HTTP_STATUS"] = str(status)
        self.executable(
            "curl",
            f"#!{sys.executable}\n" + """
import json, os, pathlib, sys
pathlib.Path(os.environ["TMPDIR"], "curl-request.json").write_text(json.dumps({
    "args": sys.argv[1:], "config": sys.stdin.read()
}))
print(os.environ["CLAUDE_USAGE_RESPONSE"])
print(os.environ["CLAUDE_USAGE_HTTP_STATUS"], end="")
""",
        )

    def test_claude_scoped_limits_pacing_and_weekly_ranking(self) -> None:
        now = datetime.now(timezone.utc)
        reset = (now + timedelta(days=3)).isoformat()
        self.claude_response({
            "five_hour": {"utilization": 99, "resets_at": reset},
            "seven_day": {"utilization": 99, "resets_at": reset},
            "limits": [
                {"kind": "session", "group": "session", "percent": 7,
                 "resets_at": (now + timedelta(hours=2)).isoformat(), "scope": None},
                {"kind": "weekly_all", "group": "weekly", "percent": 32,
                 "resets_at": reset, "scope": None, "is_active": False},
                {"kind": "weekly_scoped", "group": "weekly", "percent": 48,
                 "resets_at": reset, "scope": {"model": {"display_name": "Fable"}},
                 "is_active": False},
            ],
        })
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("5h: [█░░░░░░░░░░░░░░░░░░░] 7% used, 93% remaining", text)
        self.assertIn("Weekly: [██████░░░░░░░░░░░░░░] 32% used, 68% remaining", text)
        self.assertIn("Weekly (Fable): [██████████░░░░░░░░░░] 48% used, 52% remaining", text)
        self.assertIn("Claude · Weekly [weekly]", text)
        self.assertIn("Claude · Weekly (Fable) [weekly]", text)
        self.assertNotIn("Claude · 5h [weekly]", text)
        self.assertNotIn("99% used", text)
        self.assertIn("%/hour avg so far", text)
        self.assertIn("%/day avg so far", text)
        self.assertEqual(b"", errors)
        request = json.loads((self.root / "curl-request.json").read_text())
        self.assertEqual(
            "https://api.anthropic.com/api/oauth/usage?cedar_ember=1&skip_spend=1",
            request["args"][-1],
        )
        self.assertRegex(" ".join(request["args"]), r"User-Agent: claude-cli/\d+\.\d+\.\d+")
        self.assertIn("--max-time", request["args"])
        self.assertNotIn("fake-claude-oauth-token", " ".join(request["args"]))
        self.assertIn("Authorization: Bearer fake-claude-oauth-token", request["config"])
        self.assertNotIn("fake-claude-oauth-token", text)

    def test_five_hour_limits_lead_in_their_own_section(self) -> None:
        now = datetime.now(timezone.utc)
        self.claude_response({
            "five_hour": {"utilization": 40,
                          "resets_at": (now + timedelta(hours=2)).isoformat()},
            "seven_day": {"utilization": 20,
                          "resets_at": (now + timedelta(days=3)).isoformat()},
        })
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        five_hour = text.split("── 5-hour limits", 1)[1].split(
            "── Credits expiring soonest", 1)[0]
        summary = text.split("── Credits expiring soonest", 1)[-1]
        self.assertIn("Claude · 5h [5h] · 40% used", five_hour)
        self.assertNotIn("Claude · 5h", summary)
        self.assertIn("Claude · Weekly [weekly] · 20% used", summary)
        # The fast-cycling five-hour section leads the slower weekly/monthly one.
        self.assertLess(text.index("── 5-hour limits"),
                        text.index("── Credits expiring soonest"))
        self.assertEqual(b"", errors)

    def codex_responses(self, primary: dict, secondary: dict | None = None) -> None:
        self.env["CODEX_USAGE_RESPONSES"] = json.dumps({
            "primary": primary, "secondary": secondary,
        })
        if secondary is not None:
            config = self.home / ".codex2"
            config.mkdir()
            (config / "auth.json").write_text("{}")
        self.executable("codex", f"#!{sys.executable}\n" + """
import json, os, pathlib, sys
account = "primary" if os.environ["CODEX_HOME"] == str(pathlib.Path.home() / ".codex") else "secondary"
responses = json.loads(os.environ["CODEX_USAGE_RESPONSES"])
for line in sys.stdin:
    request = json.loads(line)
    if request.get("id") == 1:
        print(json.dumps({"id": 1, "result": {}}), flush=True)
    elif request.get("method") == "account/rateLimits/read":
        print(json.dumps({"id": 2, "result": responses[account]}), flush=True)
""")

    def codex_quota(self, *, used: int = 12) -> dict:
        now = int(time.time())
        return {"rateLimitsByLimitId": {
            "codex": {
                "primary": {"usedPercent": used, "windowDurationMins": 300,
                            "resetsAt": now + 7200},
                "secondary": {"usedPercent": 34, "windowDurationMins": 10080,
                              "resetsAt": now + 3 * 86400},
            },
            "codex_bengalfox": {
                "limitName": "Spark",
                "primary": {"usedPercent": 80, "windowDurationMins": 300,
                            "resetsAt": now + 3600},
            },
        }}

    def grok_accounts(self, *homes: str) -> None:
        """Log in HOMES and fake `grok agent stdio`, whose billing tier names its GROK_HOME.
        GROK_BILLING_ERRORS maps a home to how many billing requests per session fail first."""
        for home in homes:
            (self.home / home).mkdir()
            (self.home / home / "auth.json").write_text("{}")
        self.env["GROK_BILLING_ERRORS"] = "{}"
        self.executable("grok", f"#!{sys.executable}\n" + """
import json, os, sys, time
stamp = lambda epoch: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))
now = int(time.time())
home = os.path.basename(os.environ["GROK_HOME"])
failures = json.loads(os.environ["GROK_BILLING_ERRORS"]).get(home, 0)
for line in sys.stdin:
    request = json.loads(line)
    if request.get("id") == 1:
        print(json.dumps({"id": 1, "result": {}}), flush=True)
    elif request.get("id") == 2 and failures:
        failures -= 1
        print(json.dumps({"id": 2, "error": {"code": -32603, "message": "Internal error",
            "data": "Billing service error: cursor billing: meter unavailable"}}), flush=True)
    elif request.get("id") == 2:
        print(json.dumps({"id": 2, "result": {
            "subscription_tier": "Tier " + os.path.basename(os.environ["GROK_HOME"]),
            "config": {"creditUsagePercent": 25, "currentPeriod": {
                "type": "USAGE_PERIOD_TYPE_WEEKLY",
                "start": stamp(now - 86400), "end": stamp(now + 6 * 86400)}}}}), flush=True)
""")

    def test_grok_reports_every_logged_in_account(self) -> None:
        self.grok_accounts(".grok", ".grok2", ".grok3")
        output, errors = self.start("-a", "grok").communicate(timeout=10)
        text = output.decode()
        for line in ("  Tier .grok: ", "  Tier .grok2 (grok2): ", "  Tier .grok3 (grok3): "):
            self.assertIn(line, text)
        summary = text.split("── Credits expiring soonest", 1)[1]
        for label in ("Grok · Tier .grok [", "Grok 2 · Tier .grok2 [", "Grok 3 · Tier .grok3 ["):
            self.assertIn(label, summary)
        self.assertEqual(b"", errors)

        (self.home / ".grok3" / "auth.json").unlink()
        output, errors = self.start("-a", "grok").communicate(timeout=10)
        self.assertIn("(grok2)", output.decode())
        self.assertNotIn("grok3", output.decode())

    def test_grok_resends_billing_requests_the_service_failed(self) -> None:
        self.grok_accounts(".grok", ".grok3")
        self.env["GROK_BILLING_ERRORS"] = '{".grok3": 3}'
        output, errors = self.start("-a", "grok").communicate(timeout=10)
        self.assertIn("  Tier .grok3 (grok3): ", output.decode())
        self.assertEqual(b"", errors)

        self.env["GROK_BILLING_ERRORS"] = '{".grok3": 4}'
        output, _ = self.start("-a", "grok").communicate(timeout=10)
        self.assertIn("  (grok3): unavailable (billing query failed: Billing service error: "
                      "cursor billing: meter unavailable)", output.decode())
        self.assertIn("  Tier .grok: ", output.decode())

    def test_codex_five_hour_limits_for_both_accounts_are_ranked(self) -> None:
        self.codex_responses(self.codex_quota(), self.codex_quota(used=56))
        output, errors = self.start().communicate(timeout=10)
        text = output.decode()
        five_hour = text.split("── 5-hour limits", 1)[1].split(
            "── Credits expiring soonest", 1)[0]
        summary = text.split("── Credits expiring soonest", 1)[-1]
        self.assertIn("Codex · Codex [5h] · 12% used", five_hour)
        self.assertIn("Codex 2 · Codex [5h] · 56% used", five_hour)
        self.assertNotIn("Codex 2 · Codex (weekly)", five_hour)
        # Five-hour windows lead their own section ahead of the weekly one.
        self.assertLess(text.index("── 5-hour limits"),
                        text.index("Codex 2 · Codex (weekly)"))
        self.assertNotIn("Spark", five_hour)
        self.assertNotIn("Spark", summary)
        self.assertEqual(b"", errors)

    def test_codex_summary_shows_soonest_available_banked_expiry_per_account(self) -> None:
        now = int(time.time())
        earliest = now + 86400
        second = now + 2 * 86400
        primary, secondary = self.codex_quota(), self.codex_quota()
        primary["rateLimitResetCredits"] = {"availableCount": 3, "credits": [
            {"status": "available", "expiresAt": now + 4 * 86400},
            {"status": "redeemed", "expiresAt": now + 60},
            {"status": "available", "expiresAt": now - 60},
            {"status": "available", "expiresAt": earliest},
            {"status": "available", "expiresAt": None},
        ]}
        secondary["rateLimitResetCredits"] = {"availableCount": 1, "credits": [
            {"status": "available", "expiresAt": second},
        ]}
        self.codex_responses(primary, secondary)
        output, errors = self.start().communicate(timeout=10)
        summary = output.decode().split("── Credits expiring soonest", 1)[-1]
        zone = ZoneInfo("America/Los_Angeles")
        for account, count, expiry in (("Codex", 3, earliest), ("Codex 2", 1, second)):
            pacific = datetime.fromtimestamp(expiry, zone).strftime("%Y-%m-%d %H:%M %Z")
            self.assertRegex(summary, re.escape(
                f"{account}: {count} available · next expires {pacific}"
            ) + r" · \d+ hours and \d+ minutes left")
        self.assertEqual(b"", errors)

    def test_codex_banked_count_without_expiry_is_not_treated_as_zero(self) -> None:
        for credits in (None, [], [{"status": "available", "expiresAt": None}]):
            with self.subTest(credits=credits):
                payload = self.codex_quota()
                payload["rateLimitResetCredits"] = {"availableCount": 2, "credits": credits}
                self.codex_responses(payload)
                output, errors = self.start().communicate(timeout=10)
                summary = output.decode().split("── Credits expiring soonest", 1)[-1]
                self.assertIn("Codex: 2 available · expiry unavailable", summary)
                self.assertNotIn("invalid banked reset", output.decode())
                self.assertEqual(b"", errors)

    def test_codex_missing_banked_count_is_unavailable_not_zero(self) -> None:
        payload = self.codex_quota()
        payload["rateLimitResetCredits"] = {"credits": []}
        self.codex_responses(payload)
        output, errors = self.start().communicate(timeout=10)
        self.assertIn(b"Banked resets: unavailable (invalid reset count)", output)
        self.assertNotIn(b"Banked resets: none available", output)
        self.assertEqual(b"", errors)

    def test_claude_banked_reset_grants_are_shown_live(self) -> None:
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=3)
        self.claude_response({
            "seven_day": {"utilization": 20, "resets_at": expiry.isoformat()},
            "cedar_ember": {"eligible": True, "grants": [
                {"resets_left": 1, "ends_at": (now + timedelta(days=5)).isoformat()},
                {"resets_left": 2, "ends_at": expiry.isoformat(), "usable_now": False,
                 "use_requires_limit": True},
                {"resets_left": 0, "ends_at": (now + timedelta(hours=1)).isoformat()},
                {"resets_left": 1, "ends_at": (now - timedelta(hours=1)).isoformat()},
                {"resets_left": 1, "ends_at": (now + timedelta(hours=1)).isoformat(),
                 "paused": True},
                {"resets_left": 1, "starts_at": (now + timedelta(days=1)).isoformat(),
                 "ends_at": (now + timedelta(days=2)).isoformat()},
            ]},
        })
        pacific = expiry.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M %Z")
        output, errors = self.start("-a", "claude").communicate(timeout=10)
        summary = output.decode().split("── Credits expiring soonest", 1)[-1]
        self.assertIn(f"Claude: 3 available · next expires {pacific}", summary)
        self.assertEqual(b"", errors)

    def claude_console_response(self, payload: dict, status: int = 200) -> Path:
        jar = self.home / ".cache/agent-usage/claude-console-cookies.txt"
        jar.parent.mkdir(parents=True, exist_ok=True)
        jar.write_text(
            "# Netscape HTTP Cookie File\n"
            "#HttpOnly_platform.claude.com\tFALSE\t/\tTRUE\t0\tlastActiveOrg\t"
            "12345678-1234-1234-1234-123456789abc\n"
            "#HttpOnly_platform.claude.com\tFALSE\t/\tTRUE\t0\tsessionKey\tfake-console-session\n"
        )
        self.claude_response({
            "seven_day": {"utilization": 20,
                          "resets_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()},
            "cedar_ember": {"eligible": True, "grants": []},
        })
        self.env["CONSOLE_RESPONSE"] = json.dumps(payload)
        self.env["CONSOLE_HTTP_STATUS"] = str(status)
        self.executable("curl", f"#!{sys.executable}\n" + """
import json, os, pathlib, sys
args = sys.argv[1:]
console = args[-1].startswith("https://platform.claude.com/api/organizations/")
pathlib.Path(os.environ["TMPDIR"], "console-request.json" if console else "curl-request.json").write_text(
    json.dumps({"args": args, "config": sys.stdin.read()})
)
print(os.environ["CONSOLE_RESPONSE" if console else "CLAUDE_USAGE_RESPONSE"])
print(os.environ["CONSOLE_HTTP_STATUS" if console else "CLAUDE_USAGE_HTTP_STATUS"], end="")
""")
        return jar

    @staticmethod
    def console_grant(remaining: int = 17550, *, expires: str | None = None) -> dict:
        return {"granted_amount_minor_units": 20000, "remaining_amount_minor_units": remaining,
                "currency": "USD", "expires_at": expires}

    def test_claude_console_credits_balance_expiration_and_separate_summary(self) -> None:
        expiry = datetime.now(timezone.utc) + timedelta(days=5)
        grant = self.console_grant(expires=expiry.isoformat())
        grant["scope"] = {"kind": "scoped", "applies_to": [{"product": "api"}]}
        self.claude_console_response({"amount": 99999, "promo_tranches": [grant]})
        process = self.start("-a", "claude")
        output, errors = process.communicate(timeout=5)
        text = output.decode()
        summary = text.split("── Credits expiring soonest", 1)[1]
        pacific = expiry.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M %Z")
        self.assertIn("API promotional credits: $175.50 remaining", text)
        self.assertIn(f"Claude API: $175.50 / $200.00 remaining · expires {pacific}", summary)
        self.assertIn("5d 0h left", summary)
        self.assertIn("separate from subscription limits", summary)
        self.assertIn("Claude · Weekly [weekly]", summary)
        self.assertNotIn("999.99", text)
        self.assertNotIn("fake-console-session", text + errors.decode())
        request = json.loads((self.root / "console-request.json").read_text())
        self.assertEqual("https://platform.claude.com/api/organizations/"
                         "12345678-1234-1234-1234-123456789abc/prepaid/credits", request["args"][-1])
        self.assertNotIn("fake-console-session", " ".join(request["args"]))
        self.assertIn("-b", request["args"])
        self.assertNotIn("-L", request["args"])
        self.assertEqual(0, process.returncode, errors.decode())
        self.assertEqual(b"", errors)

    def test_claude_console_filters_expired_and_non_api_grants_but_keeps_exhausted(self) -> None:
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=1)
        code_only = self.console_grant(remaining=19000, expires=(now + timedelta(days=10)).isoformat())
        code_only["scope"] = {"kind": "scoped", "applies_to": [{"product": "code_api"}]}
        self.claude_console_response({"promo_tranches": [
            self.console_grant(remaining=0, expires=(now + timedelta(days=4)).isoformat()),
            self.console_grant(remaining=1234, expires=soon.isoformat()),
            self.console_grant(remaining=18000, expires=(now - timedelta(seconds=1)).isoformat()),
            code_only,
        ]})
        output, errors = self.start("-a", "claude").communicate(timeout=5)
        summary = output.decode().split("── Credits expiring soonest", 1)[1]
        self.assertIn("Claude API: $0.00 / $200.00 remaining", summary)
        self.assertIn("Claude API: $12.34 / $200.00 remaining", summary)
        self.assertNotIn("$180.00", summary)
        self.assertNotIn("$190.00", summary)
        self.assertLess(summary.index("$12.34"), summary.index("$0.00"))
        self.assertEqual(b"", errors)

    def test_claude_console_missing_expiry_empty_grants_and_bad_schema(self) -> None:
        valid = self.console_grant()
        for payload, expected, status in (
            ({"promo_tranches": [valid]}, "Claude API: $175.50 / $200.00 remaining · expiry unavailable", 0),
            ({"promo_tranches": []}, "API promotional credits: none active", 0),
            ({}, "could not parse Console promotional grants", 1),
            ({"promo_tranches": None}, "could not parse Console promotional grants", 1),
            ({"promo_tranches": [dict(valid, remaining_amount_minor_units="17550")]},
             "could not parse Console promotional grants", 1),
            ({"promo_tranches": [dict(valid, remaining_amount_minor_units=20001)]},
             "could not parse Console promotional grants", 1),
            ({"promo_tranches": [dict(valid, remaining_amount_minor_units=-1)]},
             "could not parse Console promotional grants", 1),
            ({"promo_tranches": [dict(valid, currency="EUR")]},
             "could not parse Console promotional grants", 1),
            ({"promo_tranches": [dict(valid, expires_at="bad")]},
             "could not parse Console promotional grants", 1),
        ):
            with self.subTest(payload=payload):
                self.claude_console_response(payload)
                process = self.start("-a", "claude")
                output, errors = process.communicate(timeout=5)
                self.assertIn(expected, output.decode())
                self.assertEqual(status, process.returncode, errors.decode())
                self.assertEqual(b"", errors)

    def test_claude_console_failure_never_reuses_an_old_balance(self) -> None:
        self.claude_console_response({"promo_tranches": [self.console_grant()]})
        output, _ = self.start("-a", "claude").communicate(timeout=5)
        self.assertIn(b"$175.50", output)
        for code in (401, 403, 429, 500):
            with self.subTest(code=code):
                self.env["CONSOLE_HTTP_STATUS"] = str(code)
                process = self.start("-a", "claude")
                output, errors = process.communicate(timeout=5)
                self.assertIn(f"Console HTTP {code}", output.decode())
                self.assertNotIn(b"$175.50", output)
                self.assertIn(b"Claude ", output)
                self.assertIn(b"20% used", output)
                self.assertEqual(1, process.returncode)
                self.assertEqual(b"", errors)

    def test_claude_console_balance_survives_missing_subscription_login(self) -> None:
        self.claude_console_response({"promo_tranches": [self.console_grant()]})
        self.executable("security", "#!/bin/sh\nexit 1\n")
        output, errors = self.start("-a", "claude").communicate(timeout=5)
        self.assertIn(b"no Claude subscription login", output)
        self.assertIn(b"Claude API: $175.50 / $200.00 remaining", output)
        self.assertEqual(b"", errors)

    def test_claude_console_missing_session_invalid_org_and_network_failure(self) -> None:
        jar = self.claude_console_response({"promo_tranches": [self.console_grant()]})
        original = jar.read_bytes()
        for failure in ("no session", "bad organization", "network"):
            with self.subTest(failure=failure):
                jar.write_bytes(original)
                request = self.root / "console-request.json"
                request.unlink(missing_ok=True)
                if failure == "no session":
                    jar.unlink()
                    expected = "run claude-console-login"
                elif failure == "bad organization":
                    jar.write_text(jar.read_text().replace("12345678-1234-1234-1234-123456789abc", "bad"))
                    expected = "Console organization missing or invalid"
                else:
                    self.executable("curl", "#!/bin/sh\nexit 28\n")
                    expected = "Console request failed; network/timeout"
                process = self.start("-a", "claude")
                output, errors = process.communicate(timeout=5)
                self.assertIn(expected, output.decode())
                self.assertNotIn(b"$175.50", output)
                self.assertFalse(request.exists())
                self.assertEqual(0 if failure == "no session" else 1, process.returncode)
                self.assertEqual(b"", errors)

    def test_claude_console_login_import_is_private_and_rejects_bad_input_atomically(self) -> None:
        jar = self.home / "custom/console-cookies.txt"
        self.env["CLAUDE_CONSOLE_COOKIE_JAR"] = str(jar)
        original = None
        for cookie in (
            "Cookie: sessionKey=fake-console-session; lastActiveOrg=12345678-1234-1234-1234-123456789abc",
            "sessionKeyV3LC=fake-console-session; lastActiveOrg=12345678-1234-1234-1234-123456789abc",
            "sessionKey=fake-console-session",
            "sessionKey=fake-console-session; lastActiveOrg=bad",
        ):
            result = subprocess.run([BASH, "--noprofile", "--norc", "-c",
                                     'source "$1"; claude-console-login', "login-test", str(WRAPPERS)],
                                    input=cookie, text=True, capture_output=True, env=self.env, timeout=5)
            self.assertNotIn("fake-console-session", result.stdout + result.stderr)
            if "12345678-" in cookie:
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(0o600, jar.stat().st_mode & 0o777)
                self.assertIn("fake-console-session", jar.read_text())
                original = jar.read_bytes()
            else:
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(original, jar.read_bytes())

    def test_claude_banked_grants_are_not_promoted_from_stale_snapshot(self) -> None:
        path = self.claude_snapshot()
        timestamp, raw = path.read_text().split("\n", 1)
        data = json.loads(raw)
        data["cedar_ember"] = {"eligible": True, "grants": [
            {"resets_left": 1, "ends_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()},
        ]}
        path.write_text(f"{timestamp}\n{json.dumps(data)}")
        self.claude_stateful_response([({}, 500)])
        output, errors = self.start().communicate(timeout=10)
        summary = output.decode().split("── Credits expiring soonest", 1)[-1]
        self.assertIn("unavailable", output.decode())
        self.assertNotIn("snapshot", output.decode())
        self.assertNotIn("Claude: 1 available", summary)
        self.assertEqual(b"", errors)

    def test_claude_missing_empty_and_malformed_banked_grants(self) -> None:
        reset = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        for grants, expected in (
            (None, "unavailable (reset grants not provided)"),
            ({"eligible": False}, "0 available"),
            ({"eligible": True, "grants": []}, "0 available"),
            ({"eligible": True, "grants": [{"resets_left": 1, "ends_at": None}]}, "1 available"),
            ({"eligible": True, "grants": [{"resets_left": "bad"}]},
             "unavailable (could not parse Claude reset grants)"),
            ({"eligible": True, "grants": [{"resets_left": 1, "ends_at": "bad"}]},
             "unavailable (could not parse Claude reset grants)"),
        ):
            with self.subTest(grants=grants):
                self.env["USAGE_CLAUDE_CACHE_TTL"] = "0"
                self.claude_response({"seven_day": {"utilization": 20, "resets_at": reset},
                                      "cedar_ember": grants})
                output, errors = self.start().communicate(timeout=10)
                self.assertIn(f"Banked resets: {expected}", output.decode())
                summary = output.decode().split("── Credits expiring soonest", 1)[-1]
                if expected == "1 available":
                    self.assertIn("Claude: 1 available · expiry unavailable", summary)
                else:
                    self.assertNotIn("Claude: 1 available", summary)
                self.assertEqual(b"", errors)

    def test_claude_file_login_legacy_schema_and_idle_window(self) -> None:
        reset = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")
        self.claude_response({
            "five_hour": {"utilization": 0, "resets_at": None},
            "seven_day": {"utilization": 12.5, "resets_at": reset},
            "seven_day_sonnet": {"utilization": 3, "resets_at": reset},
            "seven_day_opus": None,
            "seven_day_breakdown": [],
        }, file_login=True)
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("0% used, 100% remaining; reset not scheduled", text)
        self.assertIn("12.5% used, 87.5% remaining", text)
        self.assertIn("Claude · Weekly (Sonnet) [weekly]", text)
        self.assertNotIn("Weekly (Opus)", text)
        self.assertFalse((self.root / "keychain-called").exists())
        self.assertEqual(b"", errors)

    def test_claude_http_errors_do_not_expose_response_or_report_quotas(self) -> None:
        for status, message in [(401, "access token rejected (HTTP 401)"),
                                (403, "usage endpoint access denied (HTTP 403)"),
                                (429, "rate limited"), (500, "returned an error")]:
            with self.subTest(status=status):
                # Subtests share one fake HOME: drop cached backoff/snapshot
                # state so each status starts fresh.
                shutil.rmtree(self.home / ".cache", ignore_errors=True)
                self.claude_response({"error": "private-server-error"}, status)
                output, errors = self.start().communicate(timeout=5)
                text = output.decode()
                self.assertIn(message, text)
                self.assertNotIn("private-server-error", text)
                self.assertNotIn("fake-claude-oauth-token", text)
                self.assertNotIn("claude auth login", text)
                self.assertNotIn("Claude · Weekly", text)
                self.assertEqual([], list(self.root.glob("claude-usage-headers.*")))
                self.assertEqual(b"", errors)

    def test_claude_invalid_response_is_unavailable(self) -> None:
        for payload in [{}, {"limits": [{"group": "weekly", "percent": "oops"}]},
                        {"limits": [{"group": "weekly", "percent": 4, "resets_at": "invalid"}]}]:
            with self.subTest(payload=payload):
                self.claude_response(payload)
                output, errors = self.start().communicate(timeout=5)
                self.assertIn(b"could not parse Claude usage limits", output)
                self.assertNotIn(b"Claude \xc2\xb7 Weekly", output.split(b"Credits expiring soonest")[-1])
                self.assertEqual(b"", errors)

    def test_claude_missing_login_does_not_query_usage(self) -> None:
        self.executable("curl", '#!/bin/sh\ntouch "$TMPDIR/unexpected-request"\nexit 1\n')
        output, errors = self.start().communicate(timeout=5)
        self.assertIn(b"no Claude subscription login", output)
        self.assertFalse((self.root / "unexpected-request").exists())
        self.assertEqual(b"", errors)

    def claude_security_only(self, *, expires_at: int | None = None,
                             refresh_token: bool = True) -> None:
        """Keychain login stub without touching the curl stub."""
        oauth = {"accessToken": "fake-claude-oauth-token"}
        if refresh_token:
            oauth["refreshToken"] = "fake-refresh-token"
        if expires_at is not None:
            oauth["expiresAt"] = expires_at
        credentials = json.dumps({"claudeAiOauth": oauth})
        self.executable("security", f"#!/bin/sh\nprintf '%s\\n' '{credentials}'\n")

    def claude_stateful_response(self, bodies: list, *, headers: str = "") -> None:
        """Fake curl serving one (payload, status) pair per call, in order."""
        self.claude_security_only()
        self.env["CLAUDE_USAGE_BODIES"] = json.dumps(bodies)
        self.env["CLAUDE_USAGE_HEADERS"] = headers
        self.executable(
            "curl",
            f"#!{sys.executable}\n" + """
import json, os, pathlib, sys
counter = pathlib.Path(os.environ["TMPDIR"], "curl-count")
n = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(n + 1))
with open(pathlib.Path(os.environ["TMPDIR"], "curl-configs"), "a") as fh:
    fh.write(sys.stdin.read() + "\\n---\\n")
args = sys.argv[1:]
pathlib.Path(args[args.index("-D") + 1]).write_text(os.environ["CLAUDE_USAGE_HEADERS"])
bodies = json.loads(os.environ["CLAUDE_USAGE_BODIES"])
payload, status = bodies[min(n, len(bodies) - 1)]
print(json.dumps(payload))
print(status, end="")
""",
        )

    def test_claude_rate_limit_does_not_retry_before_retry_after(self) -> None:
        reset = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        self.claude_stateful_response([
            ({"error": {"type": "rate_limit_error"}}, 429),
            ({"limits": [
                {"kind": "weekly_all", "group": "weekly", "percent": 32,
                 "resets_at": reset, "scope": None},
            ]}, 200),
        ], headers="HTTP/2 429\r\nRetry-After: 3600\r\n")
        before = int(time.time())
        output, errors = self.start().communicate(timeout=15)
        text = output.decode()
        summary = text.split("Credits expiring soonest")[-1]
        self.assertNotIn("Claude · Weekly [weekly]", summary)
        self.assertIn("rate limited (HTTP 429)", summary)
        self.assertEqual(1, int((self.root / "curl-count").read_text()))
        deadline = int((self.home / ".cache/agent-usage/claude-backoff").read_text())
        self.assertGreaterEqual(deadline, before + 3600)
        self.assertLessEqual(deadline, int(time.time()) + 3600)
        configs = (self.root / "curl-configs").read_text()
        self.assertEqual(1, configs.count("Authorization: Bearer fake-claude-oauth-token"))
        self.assertEqual(b"", errors)

    def test_claude_persistent_rate_limit_noted_in_summary(self) -> None:
        self.claude_stateful_response([
            ({"error": {"type": "rate_limit_error"}}, 429),
        ])
        output, errors = self.start().communicate(timeout=15)
        text = output.decode()
        self.assertIn("rate limited", text)
        summary = text.split("Credits expiring soonest")[-1]
        self.assertIn("Claude: usage endpoint rate limited (HTTP 429)", summary)
        self.assertIn("15-minute fallback cooldown", summary)
        self.assertNotIn("Claude · Weekly", text)
        self.assertEqual(1, int((self.root / "curl-count").read_text()))
        # Server-advised backoff is recorded for later runs.
        backoff = self.home / ".cache" / "agent-usage" / "claude-backoff"
        self.assertTrue(backoff.exists())
        self.assertGreater(int(backoff.read_text().strip()), 0)
        self.assertEqual(b"", errors)

    def test_claude_backoff_window_skips_request(self) -> None:
        cache_dir = self.home / ".cache" / "agent-usage"
        cache_dir.mkdir(parents=True)
        far_future = int(datetime.now(timezone.utc).timestamp()) + 3600
        (cache_dir / "claude-backoff").write_text(f"{far_future}\n")
        self.executable("curl", '#!/bin/sh\ntouch "$TMPDIR/unexpected-request"\nexit 1\n')
        self.claude_security_only()
        output, errors = self.start().communicate(timeout=15)
        text = output.decode()
        self.assertIn("retry after", text)
        summary = text.split("Credits expiring soonest")[-1]
        self.assertIn("local cooldown after an earlier HTTP 429", summary)
        self.assertIn("no request sent", summary)
        self.assertNotIn("Claude · Weekly", text)
        self.assertFalse((self.root / "unexpected-request").exists())
        self.assertEqual(b"", errors)

    def test_claude_fresh_snapshot_does_not_replace_a_live_request(self) -> None:
        reset = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        body = {
            "_usage_token_sha256": hashlib.sha256(b"fake-claude-oauth-token").hexdigest(),
            "limits": [
                {"kind": "weekly_all", "group": "weekly", "percent": 32,
                 "resets_at": reset, "scope": None},
            ],
        }
        cache_dir = self.home / ".cache" / "agent-usage"
        cache_dir.mkdir(parents=True)
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        (cache_dir / "claude-response").write_text(f"{now_epoch}\n{json.dumps(body)}")
        self.env["USAGE_CLAUDE_CACHE_TTL"] = "3600"
        self.claude_stateful_response([
            ({"seven_day": {"utilization": 45, "resets_at": reset}}, 200),
        ])
        output, errors = self.start("-a", "claude").communicate(timeout=5)
        text = output.decode()
        self.assertIn("45% used, 55% remaining", text)
        self.assertNotIn("32% used", text)
        self.assertNotIn("snapshot", text)
        summary = text.split("Credits expiring soonest")[-1]
        self.assertIn("Claude · Weekly [weekly]", summary)
        self.assertNotIn("Without expiration data", text)
        self.assertEqual(1, int((self.root / "curl-count").read_text()))
        self.assertEqual(b"", errors)

    def test_claude_idle_weekly_window_noted_in_summary(self) -> None:
        now = datetime.now(timezone.utc)
        self.claude_response({
            "limits": [
                {"kind": "session", "group": "session", "percent": 5,
                 "resets_at": (now + timedelta(hours=2)).isoformat(), "scope": None},
                {"kind": "weekly_all", "group": "weekly", "percent": 10,
                 "resets_at": None, "scope": None},
            ],
        })
        output, errors = self.start().communicate(timeout=15)
        text = output.decode()
        self.assertIn("reset not scheduled", text)
        summary = text.split("Credits expiring soonest")[-1]
        self.assertIn("Claude: no weekly window with a scheduled reset", summary)
        self.assertNotIn("Claude · Weekly", text)
        self.assertEqual(b"", errors)

    def claude_snapshot(self, *, age: int = 600, reset_after: int = 86400) -> Path:
        now = int(time.time())
        reset = datetime.fromtimestamp(now + reset_after, timezone.utc).isoformat()
        body = {
            "_usage_token_sha256": hashlib.sha256(b"fake-claude-oauth-token").hexdigest(),
            "seven_day": {"utilization": 32, "resets_at": reset},
        }
        path = self.home / ".cache/agent-usage/claude-response"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{now - age}\n{json.dumps(body)}")
        return path

    def claude_renewable(self, *, expires_at: int, renew: tuple[dict, int],
                         usage_payload: dict | None = None,
                         keychain_writable: bool = True, pad: int = 0) -> Path:
        """Writable Keychain stub plus a curl that serves both endpoints.

        Returns the path backing the fake Keychain item.
        """
        store = self.root / "keychain.json"
        store.write_text(json.dumps({"claudeAiOauth": {
            "accessToken": "stale-access-token",
            "refreshToken": "stored-refresh-token",
            "expiresAt": expires_at,
            "subscriptionType": "max",
            **({"pad": "p" * pad} if pad else {}),
        }}))
        self.env["KEYCHAIN_WRITABLE"] = "1" if keychain_writable else ""
        self.executable("security", f"#!{sys.executable}\n" + """
import os, pathlib, shlex, sys
store = pathlib.Path(os.environ["TMPDIR"], "keychain.json")
args = sys.argv[1:]
if args[:1] == ["find-generic-password"]:
    sys.stdout.write(store.read_text() if "-w" in args else '    "acct"<blob>="tester"\\n')
elif args[:1] == ["-i"]:
    # security -i takes the command on stdin; the real one rejects a value
    # longer than 4032 hex characters, after truncating what it stored.
    written = shlex.split(sys.stdin.read().strip())
    pathlib.Path(os.environ["TMPDIR"], "keychain-write-args").write_text(" ".join(written))
    if written[:1] != ["add-generic-password"] or not os.environ.get("KEYCHAIN_WRITABLE"):
        sys.exit(1)
    payload = written[written.index("-X") + 1]
    store.write_text(bytes.fromhex(payload[:4032]).decode())
    sys.exit(0 if len(payload) <= 4032 else 1)
else:
    sys.exit(1)
""")
        self.executable("claude", '#!/bin/sh\necho "2.1.278 (Claude Code)"\n')
        self.env["CLAUDE_RENEW_BODY"] = json.dumps(renew[0])
        self.env["CLAUDE_RENEW_STATUS"] = str(renew[1])
        self.env["CLAUDE_USAGE_RESPONSE"] = json.dumps(usage_payload or {})
        self.executable("curl", f"#!{sys.executable}\n" + """
import json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(os.environ["TMPDIR"])
if "oauth/token" in args[-1]:
    body = pathlib.Path(args[args.index("--data-binary") + 1].lstrip("@")).read_text()
    (root / "renew-request.json").write_text(json.dumps({"args": args, "body": body}))
    print(os.environ["CLAUDE_RENEW_BODY"])
    print(os.environ["CLAUDE_RENEW_STATUS"], end="")
else:
    (root / "curl-request.json").write_text(json.dumps({
        "args": args, "config": sys.stdin.read()}))
    print(os.environ["CLAUDE_USAGE_RESPONSE"])
    print("200", end="")
""")
        return store

    def renewed_body(self) -> dict:
        return {"access_token": "renewed-access-token", "expires_in": 28800,
                "refresh_token": "rotated-refresh-token",
                "refresh_token_expires_in": 2290031,
                "scope": "user:inference user:profile", "token_type": "Bearer"}

    def test_claude_expired_token_is_renewed_and_written_back(self) -> None:
        reset = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        store = self.claude_renewable(
            expires_at=int(time.time() * 1000) - 1000,
            renew=(self.renewed_body(), 200),
            usage_payload={"five_hour": {"utilization": 2, "resets_at": reset},
                           "seven_day": {"utilization": 11, "resets_at": reset}})
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("(renewed the expired access token)", text)
        self.assertIn("11% used, 89% remaining", text)
        stored = json.loads(store.read_text())["claudeAiOauth"]
        self.assertEqual("renewed-access-token", stored["accessToken"])
        self.assertEqual("rotated-refresh-token", stored["refreshToken"])
        self.assertEqual("max", stored["subscriptionType"])
        self.assertGreater(stored["expiresAt"], time.time() * 1000)
        self.assertGreater(stored["refreshTokenExpiresAt"], stored["expiresAt"])
        self.assertEqual(["user:inference", "user:profile"], stored["scopes"])
        renew = json.loads((self.root / "renew-request.json").read_text())
        self.assertEqual("stored-refresh-token", json.loads(renew["body"])["refresh_token"])
        self.assertNotIn("stored-refresh-token", " ".join(renew["args"]))
        usage = json.loads((self.root / "curl-request.json").read_text())
        self.assertIn("Authorization: Bearer renewed-access-token", usage["config"])
        self.assertNotIn("renewed-access-token", " ".join(usage["args"]))
        for secret in ("stale-access-token", "renewed-access-token",
                       "stored-refresh-token", "rotated-refresh-token"):
            self.assertNotIn(secret, text)
        self.assertFalse((self.home / ".claude" / ".storage-write.lock").exists())
        self.assertEqual(b"", errors)

    def test_claude_live_token_is_never_renewed(self) -> None:
        reset = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        store = self.claude_renewable(
            expires_at=int(time.time() * 1000) + 3_600_000,
            renew=(self.renewed_body(), 200),
            usage_payload={"seven_day": {"utilization": 11, "resets_at": reset}})
        before = store.read_text()
        output, errors = self.start().communicate(timeout=5)
        self.assertIn(b"11% used", output)
        self.assertFalse((self.root / "renew-request.json").exists())
        self.assertEqual(before, store.read_text())
        self.assertEqual(b"", errors)

    def test_claude_refused_renewal_keeps_stored_credentials(self) -> None:
        store = self.claude_renewable(
            expires_at=int(time.time() * 1000) - 1000,
            renew=({"error": "invalid_grant"}, 400))
        before = store.read_text()
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("renewal was refused (HTTP 400)", text)
        self.assertIn("claude auth login", text)
        self.assertNotIn("invalid_grant", text)
        self.assertEqual(before, store.read_text())
        self.assertFalse((self.root / "curl-request.json").exists())
        self.assertFalse((self.home / ".claude" / ".storage-write.lock").exists())
        self.assertEqual(b"", errors)

    def test_claude_unstorable_renewal_leaves_a_recovery_copy(self) -> None:
        self.claude_renewable(expires_at=int(time.time() * 1000) - 1000,
                              renew=(self.renewed_body(), 200), keychain_writable=False)
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        recovery = self.home / ".cache" / "agent-usage" / "claude-renewed-credentials.json"
        self.assertIn("could not be stored", text)
        self.assertIn(str(recovery), text)
        self.assertEqual(0o600, recovery.stat().st_mode & 0o777)
        saved = json.loads(recovery.read_text())["claudeAiOauth"]
        self.assertEqual("rotated-refresh-token", saved["refreshToken"])
        self.assertNotIn("rotated-refresh-token", text)
        self.assertFalse((self.root / "curl-request.json").exists())
        self.assertEqual(b"", errors)

    def test_claude_oversized_credential_is_never_written_truncated(self) -> None:
        # security caps the value it stores; a truncated credential is a dead
        # login, so an unstorable size must leave the stored one untouched.
        store = self.claude_renewable(expires_at=int(time.time() * 1000) - 1000,
                                      renew=(self.renewed_body(), 200), pad=2100)
        before = store.read_text()
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("could not be stored", text)
        self.assertEqual(before, store.read_text())
        self.assertEqual("stale-access-token",
                         json.loads(store.read_text())["claudeAiOauth"]["accessToken"])
        recovery = self.home / ".cache" / "agent-usage" / "claude-renewed-credentials.json"
        self.assertEqual("rotated-refresh-token",
                         json.loads(recovery.read_text())["claudeAiOauth"]["refreshToken"])
        self.assertEqual(b"", errors)

    def test_claude_renewal_defers_to_a_held_write_lock(self) -> None:
        store = self.claude_renewable(expires_at=int(time.time() * 1000) - 1000,
                                      renew=(self.renewed_body(), 200))
        before = store.read_text()
        lock = self.home / ".claude" / ".storage-write.lock"
        lock.mkdir(parents=True)
        output, errors = self.start().communicate(timeout=5)
        self.assertIn(b"another process is updating the credential", output)
        self.assertFalse((self.root / "renew-request.json").exists())
        self.assertEqual(before, store.read_text())
        self.assertTrue(lock.exists())
        self.assertEqual(b"", errors)

    def test_claude_expired_token_without_refresh_token_requires_login(self) -> None:
        self.claude_security_only(expires_at=int(time.time() * 1000) - 1000,
                                  refresh_token=False)
        self.executable("curl", '#!/bin/sh\ntouch "$TMPDIR/unexpected-request"\nexit 1\n')
        output, errors = self.start().communicate(timeout=5)
        self.assertIn(b"no refresh token", output)
        self.assertIn(b"claude auth login", output)
        self.assertFalse((self.root / "unexpected-request").exists())
        self.assertEqual(b"", errors)

    def test_claude_retry_after_date_and_invalid_values(self) -> None:
        future = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=2)
        for value in (format_datetime(future, usegmt=True), "0", "nonsense", "-1"):
            with self.subTest(retry_after=value):
                shutil.rmtree(self.home / ".cache", ignore_errors=True)
                (self.root / "curl-count").unlink(missing_ok=True)
                self.claude_stateful_response([({}, 429)],
                    headers=f"HTTP/2 429\r\nRETRY-AFTER: {value}\r\n")
                before = int(time.time())
                output, errors = self.start().communicate(timeout=5)
                deadline = int((self.home / ".cache/agent-usage/claude-backoff").read_text())
                if value == format_datetime(future, usegmt=True):
                    self.assertEqual(int(future.timestamp()), deadline)
                    self.assertNotIn(b"fallback cooldown", output)
                else:
                    self.assertGreaterEqual(deadline, before + 900)
                    self.assertLessEqual(deadline, int(time.time()) + 900)
                    self.assertIn(b"fallback cooldown", output)
                self.assertEqual(1, int((self.root / "curl-count").read_text()))
                self.assertEqual(b"", errors)

    def test_claude_failed_refresh_never_displays_cached_stats(self) -> None:
        for status in (401, 429, 500, 200):
            with self.subTest(status=status):
                shutil.rmtree(self.home / ".cache", ignore_errors=True)
                snapshot = self.claude_snapshot()
                original = snapshot.read_bytes()
                self.claude_stateful_response([({"unexpected": "invalid payload"}, status)])
                process = self.start("-a", "claude")
                output, errors = process.communicate(timeout=5)
                text = output.decode()
                claude_section = text.split("── Claude ", 1)[1].split("\n── ", 1)[0]
                summary = text.split("Credits expiring soonest")[-1]
                self.assertIn("unavailable", claude_section)
                self.assertNotIn("% used", claude_section)
                self.assertNotIn("snapshot", text)
                self.assertNotIn("Claude · Weekly", summary)
                self.assertEqual(original, snapshot.read_bytes())
                self.assertEqual(1, process.returncode)
                self.assertEqual(b"", errors)

    def test_claude_network_failure_does_not_display_cached_stats(self) -> None:
        self.claude_snapshot()
        self.claude_security_only()
        self.executable("curl", "#!/bin/sh\nexit 28\n")
        output, errors = self.start().communicate(timeout=5)
        self.assertIn(b"usage request failed", output)
        self.assertNotIn(b"snapshot", output)
        self.assertNotIn(b"% used", output)
        self.assertEqual(b"", errors)

    def test_claude_cooldown_reports_unavailable_without_cached_stats_or_request(self) -> None:
        snapshot = self.claude_snapshot()
        (snapshot.parent / "claude-backoff").write_text(str(int(time.time()) + 3600))
        self.claude_security_only()
        self.executable("curl", '#!/bin/sh\ntouch "$TMPDIR/unexpected-request"\nexit 1\n')
        output, errors = self.start().communicate(timeout=5)
        self.assertIn(b"local cooldown", output)
        self.assertIn(b"no request sent", output)
        self.assertIn(b"unavailable", output)
        self.assertNotIn(b"snapshot", output)
        self.assertNotIn(b"% used", output)
        self.assertFalse((self.root / "unexpected-request").exists())
        self.assertEqual(b"", errors)

    def test_claude_expired_token_does_not_display_cached_stats(self) -> None:
        for reset_after in (86400, -60):
            with self.subTest(reset_after=reset_after):
                self.claude_snapshot(reset_after=reset_after)
                self.claude_security_only(expires_at=int(time.time() * 1000) - 1000)
                output, errors = self.start().communicate(timeout=5)
                self.assertIn(b"access token expired", output)
                self.assertIn(b"unavailable", output)
                self.assertNotIn(b"snapshot", output)
                self.assertNotIn(b"% used", output)
                self.assertEqual(b"", errors)

    def test_claude_each_run_fetches_updated_stats_and_grants_without_a_snapshot(self) -> None:
        reset = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        self.claude_stateful_response([
            ({"seven_day": {"utilization": 12, "resets_at": reset},
              "cedar_ember": {"eligible": True, "grants": [
                  {"resets_left": 2, "ends_at": reset},
              ]}}, 200),
            ({"seven_day": {"utilization": 45, "resets_at": reset},
              "cedar_ember": {"eligible": True, "grants": []}}, 200),
        ])
        output, errors = self.start("-a", "claude").communicate(timeout=5)
        self.assertIn(b"12% used", output)
        self.assertIn(b"Claude: 2 available", output)
        self.assertEqual(b"", errors)
        snapshot = self.home / ".cache/agent-usage/claude-response"
        self.assertFalse(snapshot.exists())
        output, errors = self.start("-a", "claude").communicate(timeout=5)
        self.assertIn(b"45% used", output)
        self.assertNotIn(b"12% used", output)
        self.assertIn(b"Banked resets: 0 available", output)
        self.assertNotIn(b"Claude: 2 available", output)
        self.assertNotIn(b"snapshot", output)
        self.assertEqual(2, int((self.root / "curl-count").read_text()))
        self.assertFalse(snapshot.exists())
        self.assertEqual(b"", errors)

    def test_claude_forbidden_response_does_not_use_a_stale_snapshot(self) -> None:
        self.claude_snapshot()
        self.claude_stateful_response([({}, 403)])
        output, errors = self.start().communicate(timeout=5)
        self.assertIn(b"access denied (HTTP 403)", output)
        self.assertNotIn(b"claude auth login", output)
        self.assertNotIn(b"32% used", output)
        self.assertEqual(b"", errors)

    def test_claude_file_expiry_metadata_is_used(self) -> None:
        self.claude_response({}, file_login=True)
        # Renewal is the only path that would query or rewrite the file here.
        self.env["USAGE_CLAUDE_RENEW"] = "0"
        path = Path(self.env["CLAUDE_CONFIG_DIR"]) / ".credentials.json"
        for expires_at in (int(time.time() * 1000) - 1000, "invalid"):
            with self.subTest(expires_at=expires_at):
                data = json.loads(path.read_text())
                data["claudeAiOauth"]["expiresAt"] = expires_at
                path.write_text(json.dumps(data))
                original = path.read_bytes()
                output, errors = self.start().communicate(timeout=5)
                expected = b"access token expired" if isinstance(expires_at, int) else b"invalid stored access-token expiry"
                self.assertIn(expected, output)
                self.assertNotIn(b"claude auth login", output)
                self.assertFalse((self.root / "curl-request.json").exists())
                self.assertEqual(original, path.read_bytes())
                self.assertEqual(b"", errors)

    def cmd_responses(self, windows: dict) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.env["COMMAND_CODE_API_KEY"] = "fake-command-key"
        self.env["CMD_RESPONSES"] = json.dumps({
            "subscriptions": {"data": {
                "planId": "individual-pro-v1", "status": "active",
                "currentPeriodStart": now.isoformat(),
                "currentPeriodEnd": (now + timedelta(days=30)).isoformat(),
            }},
            "credits": {
                "credits": {"monthlyCredits": 80, "purchasedCredits": 0, "freeCredits": 0},
                "windowLimits": {"limited": True, **windows},
            },
            "summary": {"totalCost": 0, "totalCount": 0},
        })
        self.executable("curl", f"#!{sys.executable}\n" + """
import json, os, sys
endpoint = sys.argv[-1].split("?", 1)[0].rsplit("/", 1)[-1]
print(json.dumps(json.loads(os.environ["CMD_RESPONSES"])[endpoint]))
""")

    def test_command_code_rejected_key_reports_credential_source_and_recovery(self) -> None:
        for source in ("file", "env"):
            with self.subTest(source=source):
                self.cmd_responses({})
                auth_file = self.home / ".commandcode" / "auth.json"
                auth_file.parent.mkdir(exist_ok=True)
                original = json.dumps({"apiKey": "fake-stored-key"})
                auth_file.write_text(original)
                if source == "file":
                    self.env.pop("COMMAND_CODE_API_KEY")
                    recovery = "run cmd logout then cmd login"
                else:
                    recovery = "update or unset COMMAND_CODE_API_KEY"
                responses = json.loads(self.env["CMD_RESPONSES"])
                for endpoint in ("subscriptions", "credits"):
                    responses[endpoint] = {"success": False, "error": {
                        "code": "UNAUTHORIZED", "status": 401,
                        "message": "Invalid 'Authorization' header or token.",
                    }}
                self.env["CMD_RESPONSES"] = json.dumps(responses)
                process = self.start("-a", "cmd")
                output, errors = process.communicate(timeout=5)
                text = output.decode()
                self.assertIn("authentication rejected (HTTP 401)", text)
                self.assertIn(recovery, text)
                self.assertNotIn("usage query failed", text)
                self.assertNotIn("Spendable now", text)
                self.assertNotIn("fake-stored-key", text)
                self.assertNotIn("fake-command-key", text)
                self.assertEqual(original, auth_file.read_text())
                self.assertEqual(1, process.returncode)
                self.assertEqual(b"", errors)

    def test_command_code_only_scheduled_windows_get_countdowns_and_rankings(self) -> None:
        now = int(time.time())
        for five_after, weekly_after, fraction_used in (
            (0, 0, 0), (7200, 259200, 0), (7200, 0, 0.25), (0, 259200, 0.25),
        ):
            with self.subTest(five_after=five_after, weekly_after=weekly_after,
                              fraction_used=fraction_used):
                windows = {
                    key: {"used": cap * fraction_used if after else 0, "cap": cap,
                          "resetAt": (now + after) * 1000 if after else 0}
                    for key, cap, after in (
                        ("fiveHour", 16, five_after), ("weekly", 40, weekly_after),
                    )
                }
                self.cmd_responses(windows)
                process = self.start("-a", "cmd")
                output, errors = process.communicate(timeout=5)
                provider, summaries = output.decode().split("\n\n", 1)
                self.assertEqual(0, process.returncode, errors.decode())
                self.assertEqual(b"", errors)
                self.assertNotIn("reset due now", summaries)
                for label, period, key, after in (
                    ("5-hour", "5h", "fiveHour", five_after),
                    ("Weekly", "weekly", "weekly", weekly_after),
                ):
                    line = next(line for line in provider.splitlines()
                                if line.startswith(f"  {label}:"))
                    self.assertIn(f"/ ${windows[key]['cap']:.2f} used", line)
                    self.assertEqual(bool(after),
                                     f"Command Code · Pro Plan [{period}]" in summaries)
                    if after:
                        self.assertRegex(line, r"resets in [1-9]")
                    else:
                        self.assertIn("window not started yet; starts on first use", line)
                        self.assertIn(
                            f"Command Code: {label.lower()} window not started yet; starts on first use",
                            summaries,
                        )
                if not weekly_after:
                    self.assertNotIn("avg so far", provider)
                spendable = 16 - windows["fiveHour"]["used"]
                self.assertIn(f"Spendable now: ${spendable:.2f}", provider)
                self.assertIn("Command Code · Pro Plan [monthly]", summaries)

    def agy_stub(self, payload: dict, *, exit_code: int = 0) -> None:
        """Fake agy that records each invocation, so caching is observable."""
        self.env["AGY_PAYLOAD"] = json.dumps(payload)
        self.env["AGY_EXIT"] = str(exit_code)
        self.executable("agy", f"#!{sys.executable}\n" + """
import os, pathlib, sys
with open(pathlib.Path(os.environ["TMPDIR"], "agy-calls"), "a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\\n")
code = int(os.environ["AGY_EXIT"])
print(os.environ["AGY_PAYLOAD"])
sys.exit(code)
""")

    def agy_payload(self, *, weekly_reset: str, five_reset: str) -> dict:
        return {"status": "SUCCESS", "command": {"name": "usage", "data": {"groups": [
            {"name": "Gemini Models", "buckets": [
                {"name": "Weekly Limit Remaining", "remaining_fraction": 0.9,
                 "window": "weekly", "reset_time": weekly_reset},
                {"name": "Five Hour Limit Remaining", "remaining_fraction": 0.5,
                 "window": "5h", "reset_time": five_reset},
            ]},
        ]}}}

    def agy_resets(self) -> tuple[str, str]:
        # fromdateiso8601 rejects fractional seconds, as real payloads omit them.
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return ((now + timedelta(days=3)).isoformat().replace("+00:00", "Z"),
                (now + timedelta(hours=3)).isoformat().replace("+00:00", "Z"))

    def agy_calls(self) -> int:
        path = self.root / "agy-calls"
        return len(path.read_text().splitlines()) if path.exists() else 0

    def agy_snapshot(self, payload: dict) -> Path:
        path = self.home / ".cache/agent-usage/antigravity-response"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{int(time.time())}\n{json.dumps(payload)}")
        return path

    def test_antigravity_active_five_hour_buckets_are_ranked(self) -> None:
        weekly, five = self.agy_resets()
        earlier = (datetime.fromisoformat(five) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        payload = self.agy_payload(weekly_reset=weekly, five_reset=five)
        payload["command"]["data"]["groups"].append({
            "name": "Claude and GPT models", "buckets": [
                {"name": "Weekly Limit Remaining", "remaining_fraction": 0.7,
                 "window": "weekly", "reset_time": weekly},
                {"name": "Five Hour Limit Remaining", "remaining_fraction": 0.25,
                 "window": "5h", "reset_time": earlier},
            ],
        })
        self.agy_stub(payload)
        process = self.start("-a", "antigravity")
        output, errors = process.communicate(timeout=5)
        text = output.decode()
        self.assertIn("── 5-hour limits", text)
        five_hour = text.split("── 5-hour limits", 1)[1].split(
            "── Credits expiring soonest", 1)[0]
        summary = text.split("── Credits expiring soonest", 1)[1]
        self.assertIn("Antigravity · Gemini Models [5h] · 50% used", five_hour)
        self.assertIn("Antigravity · Claude and GPT models [5h] · 75% used", five_hour)
        self.assertLess(five_hour.index("Claude and GPT models"), five_hour.index("Gemini Models"))
        self.assertNotIn("[weekly]", five_hour)
        self.assertNotIn("[5h]", summary)
        self.assertIn("Antigravity · Gemini Models [weekly]", summary)
        self.assertIn("Antigravity · Claude and GPT models [weekly]", summary)
        self.assertEqual(0, process.returncode, text)
        self.assertEqual(b"", errors)

    def test_antigravity_each_run_fetches_updated_stats_despite_a_fresh_snapshot(self) -> None:
        weekly, five = self.agy_resets()
        payload = self.agy_payload(weekly_reset=weekly, five_reset=five)
        snapshot = self.agy_snapshot(payload)
        original = snapshot.read_bytes()
        self.env["USAGE_ANTIGRAVITY_CACHE_TTL"] = "3600"
        bucket = payload["command"]["data"]["groups"][0]["buckets"][0]
        bucket["remaining_fraction"] = 0.2
        self.agy_stub(payload)
        first, errors = self.start("-a", "antigravity").communicate(timeout=5)
        self.assertIn(b"80% used, 20% remaining", first)
        self.assertNotIn(b"90% remaining", first)
        self.assertEqual(b"", errors)
        self.assertEqual(1, self.agy_calls())
        bucket["remaining_fraction"] = 0.1
        self.agy_stub(payload)
        second, errors = self.start("-a", "antigravity").communicate(timeout=5)
        self.assertIn(b"90% used, 10% remaining", second)
        self.assertNotIn(b"snapshot", second)
        self.assertEqual(2, self.agy_calls())
        self.assertEqual(original, snapshot.read_bytes())
        self.assertEqual(b"", errors)

    def test_antigravity_exhausted_weekly_limit_accepts_disabled_five_hour_bucket(self) -> None:
        weekly, five = self.agy_resets()
        for fraction in (0.0023, None):
            with self.subTest(disabled_fraction=fraction):
                payload = self.agy_payload(weekly_reset=weekly, five_reset=five)
                group = {"name": "Claude and GPT models", "buckets": [
                    {"name": "Weekly Limit Remaining", "window": "weekly",
                     "remaining_fraction": 0, "reset_time": weekly},
                    {"name": "Five Hour Limit Remaining", "window": "5h", "disabled": True},
                ]}
                if fraction is not None:
                    group["buckets"][1]["remaining_fraction"] = fraction
                payload["command"]["data"]["groups"].append(group)
                self.agy_stub(payload)
                process = self.start("-a", "antigravity")
                output, errors = process.communicate(timeout=5)
                text = output.decode()
                self.assertIn("100% used, 0% remaining", text)
                self.assertIn("10% used, 90% remaining", text)
                disabled = next(line for line in text.splitlines()
                                if "Claude and GPT models · Five Hour" in line)
                self.assertIn("disabled", disabled)
                self.assertNotIn("%", disabled)
                summary = text.split("Credits expiring soonest")[-1]
                self.assertIn("Claude and GPT models [weekly] · 100% used · 0% left", summary)
                self.assertIn("── 5-hour limits", text)
                five_hour = text.split("── 5-hour limits", 1)[1].split(
                    "── Credits expiring soonest", 1)[0]
                self.assertIn("Antigravity · Gemini Models [5h]", five_hour)
                self.assertNotIn("Claude and GPT models", five_hour)
                self.assertEqual(0, process.returncode, text)
                self.assertEqual(b"", errors)

    def test_antigravity_failed_or_invalid_refresh_never_displays_cached_stats(self) -> None:
        weekly, five = self.agy_resets()
        payload = self.agy_payload(weekly_reset=weekly, five_reset=five)
        snapshot = self.agy_snapshot(payload)
        original = snapshot.read_bytes()
        for response, code in (({}, 1), ({"status": "SUCCESS"}, 0), (payload, 3)):
            with self.subTest(code=code):
                self.agy_stub(response, exit_code=code)
                process = self.start("-a", "antigravity")
                output, errors = process.communicate(timeout=5)
                self.assertIn(b"unavailable", output)
                self.assertNotIn(b"% remaining", output)
                self.assertNotIn(b"snapshot", output)
                self.assertNotIn(b"Antigravity \xc2\xb7 Gemini", output)
                self.assertEqual(1, process.returncode)
                self.assertEqual(original, snapshot.read_bytes())
                self.assertEqual(b"", errors)

    def test_antigravity_invalid_active_bucket_is_not_rendered(self) -> None:
        weekly, five = self.agy_resets()
        for field, value in (("reset_time", None), ("reset_time", "invalid"),
                             ("remaining_fraction", "0.5"), ("remaining_fraction", -0.1),
                             ("remaining_fraction", 1.1), ("disabled", "true")):
            with self.subTest(field=field, value=value):
                payload = self.agy_payload(weekly_reset=weekly, five_reset=five)
                payload["command"]["data"]["groups"][0]["buckets"][0][field] = value
                self.agy_stub(payload)
                process = self.start("-a", "antigravity")
                output, errors = process.communicate(timeout=5)
                self.assertIn(b"unavailable", output)
                self.assertNotIn(b"% remaining", output)
                self.assertEqual(1, process.returncode)
                self.assertEqual(b"", errors)

    def test_antigravity_query_is_capped_by_the_watchdog(self) -> None:
        # agy does not honour --print-timeout as a wall clock, so a hung query
        # must be killed rather than stalling the whole summary.
        weekly, five = self.agy_resets()
        self.agy_snapshot(self.agy_payload(weekly_reset=weekly, five_reset=five))
        self.executable("agy", '#!/bin/sh\nsleep 60\n')
        self.env["USAGE_ANTIGRAVITY_TIMEOUT"] = "1"
        started = time.monotonic()
        output, errors = self.start().communicate(timeout=30)
        self.assertLess(time.monotonic() - started, 20)
        self.assertIn(b"usage query timed out after 1s", output)
        self.assertNotIn(b"% remaining", output)
        self.assertEqual(b"", errors)

    def test_antigravity_failure_without_snapshot_is_unavailable(self) -> None:
        self.agy_stub({}, exit_code=1)
        output, errors = self.start().communicate(timeout=20)
        self.assertIn(b"unavailable (usage query failed)", output)
        self.assertEqual(b"", errors)

    def test_antigravity_second_account_is_queried_alongside_the_first(self) -> None:
        weekly, five = self.agy_resets()
        primary = self.agy_payload(weekly_reset=weekly, five_reset=five)
        second = self.agy_payload(weekly_reset=weekly, five_reset=five)
        second["command"]["data"]["groups"][0]["buckets"][0]["remaining_fraction"] = 0.3
        agy2 = self.home / ".agy2"
        token = agy2 / ".gemini/antigravity-cli/antigravity-oauth-token"
        token.parent.mkdir(parents=True)
        token.write_text("token")
        self.env.update(AGY_PRIMARY=json.dumps(primary), AGY_SECOND=json.dumps(second))
        # Each query waits until the other has started, so sequential queries fail.
        self.executable("agy", f"#!{sys.executable}\n" + """
import os, pathlib, sys, time
home = os.environ["HOME"]
second = home.endswith("/.agy2")
markers = pathlib.Path(os.environ["TMPDIR"])
(markers / ("started-second" if second else "started-primary")).write_text(os.environ.get("SSH_CONNECTION", ""))
other = markers / ("started-primary" if second else "started-second")
deadline = time.monotonic() + 5
while not other.exists() and time.monotonic() < deadline:
    time.sleep(0.05)
print(os.environ["AGY_SECOND" if second else "AGY_PRIMARY"] if other.exists() else "not concurrent")
""")
        output, errors = self.start("-a", "antigravity").communicate(timeout=20)
        text = output.decode()
        self.assertIn("Gemini Models · Weekly Limit Remaining: ", text)
        self.assertIn("10% used, 90% remaining", text)
        self.assertIn("Gemini Models (agy2) · Weekly Limit Remaining: ", text)
        self.assertIn("70% used, 30% remaining", text)
        self.assertIn("Antigravity 2 · Gemini Models [weekly]", text)
        self.assertNotIn("unavailable", text)
        self.assertEqual(b"", errors)
        # Only the second account presents an SSH session, which keeps AGY away from its missing keychain.
        self.assertEqual("", (self.root / "started-primary").read_text())
        self.assertNotEqual("", (self.root / "started-second").read_text())

    def test_antigravity_second_account_without_a_login_is_not_queried(self) -> None:
        weekly, five = self.agy_resets()
        (self.home / ".agy2/.gemini/antigravity-cli").mkdir(parents=True)
        self.agy_stub(self.agy_payload(weekly_reset=weekly, five_reset=five))
        output, errors = self.start("-a", "antigravity").communicate(timeout=20)
        self.assertEqual(1, self.agy_calls())
        self.assertNotIn(b"(agy2)", output)
        self.assertEqual(b"", errors)

    def kimi_credentials(self, token: str = "fake-kimi-token", *, expires_in: int = 3600) -> None:
        cred_dir = self.home / ".kimi-code" / "credentials"
        cred_dir.mkdir(parents=True, exist_ok=True)
        now = int(time.time())
        expires_at = now + expires_in
        (cred_dir / "kimi-code.json").write_text(
            json.dumps({
                "access_token": token,
                "refresh_token": "fake-kimi-refresh",
                "expires_at": expires_at,
                "expires_in": max(expires_in, 0),
                "scope": "kimi-code",
                "token_type": "Bearer",
            })
        )

    def kimi_curl(self, payload: dict, status: int = 200) -> None:
        self.kimi_credentials()
        self.env["KIMI_USAGE_RESPONSE"] = json.dumps(payload)
        self.env["KIMI_USAGE_HTTP_STATUS"] = str(status)
        self.executable(
            "curl",
            f"#!{sys.executable}\n"
            + r"""
import json, os, pathlib, sys
pathlib.Path(os.environ["TMPDIR"], "kimi-curl-requests.jsonl").open("a").write(
    json.dumps({"args": sys.argv[1:], "config": sys.stdin.read()}) + "\n"
)
joined = " ".join(sys.argv[1:])
if "oauth/token" in joined:
    print(json.dumps({
        "access_token": "fresh-kimi-token",
        "refresh_token": "fresh-kimi-refresh",
        "expires_in": 900,
        "scope": "kimi-code",
        "token_type": "Bearer",
    }))
    print("200", end="")
else:
    print(os.environ["KIMI_USAGE_RESPONSE"])
    print(os.environ["KIMI_USAGE_HTTP_STATUS"], end="")
""",
        )

    def test_kimi_refreshes_expired_token_before_query(self) -> None:
        self.kimi_credentials("stale-kimi-token", expires_in=-60)
        self.kimi_curl({
            "usage": {
                "limit": "100",
                "used": "42",
                "remaining": "58",
                "resetTime": "2026-09-20T05:19:23Z",
            },
            "limits": [{
                "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                "detail": {"limit": "100", "used": "10", "resetTime": "2026-09-18T21:19:23Z"},
            }],
            "usages": {},
        })
        # kimi_credentials was overwritten by kimi_curl; force expired state again.
        self.kimi_credentials("stale-kimi-token", expires_in=-60)
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("Weekly: [████████░░░░░░░░░░░░] 42% used", text)
        self.assertIn("Kimi [weekly]", text)
        requests = (self.root / "kimi-curl-requests.jsonl").read_text().splitlines()
        refresh = [json.loads(r) for r in requests if "oauth/token" in " ".join(json.loads(r)["args"])]
        usage = [json.loads(r) for r in requests if "usages" in " ".join(json.loads(r)["args"])]
        self.assertTrue(refresh, requests)
        self.assertTrue(usage, requests)
        self.assertIn("Authorization: Bearer fresh-kimi-token", usage[0]["config"])
        cred = json.loads((self.home / ".kimi-code/credentials/kimi-code.json").read_text())
        self.assertEqual("fresh-kimi-token", cred["access_token"])
        self.assertEqual(b"", errors)

    def amp_executable(self, details: str, providers: str) -> None:
        self.executable(
            "amp",
            "#!/bin/sh\n"
            'if [ "$*" = "--no-color usage --details" ]; then\n'
            "  cat <<'AMP_DETAILS'\n"
            f"{details}\n"
            "AMP_DETAILS\n"
            'elif [ "$*" = "--no-color config model-providers list" ]; then\n'
            "  cat <<'AMP_PROVIDERS'\n"
            f"{providers}\n"
            "AMP_PROVIDERS\n"
            "fi\n",
        )

    def test_amp_parses_new_cost_details_without_from_section(self) -> None:
        self.amp_executable(
            """# Usage

Signed in as test@example.com
**Individual credits:** $117.68 remaining (replenishes automatically) - https://ampcode.com/settings

Range: 2026-09-11T18:34:33.437Z to 2026-09-18T18:34:33.437Z (end exclusive; trailing 7 days)
Total Orb runtime: 0.000s (0 ms)
Total tokens: 0
Total recorded cost: $0

## Daily Recorded Cost
| Date (UTC) | Covered | Paid | Total |
| --- | ---: | ---: | ---: |
| No usage | $0 | $0 | $0 |

## Usage by Thread
| Thread | Main model | Tokens | Covered | Paid | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| No usage | N/A | $0 | $0 | $0 | $0 |
""",
            """# User model provider keys
active  ChatGPT Plus/Pro subscription      example@example.com's subscription      00000000-0000-4000-8000-000000000001
active  Grok subscription  Subscription                                00000000-0000-4000-8000-000000000002
""",
        )
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("Signed in as test@example.com", text)
        self.assertIn("**Individual credits:** $117.68 remaining", text)
        self.assertIn("Token usage by source:", text)
        self.assertIn("none recorded", text)
        self.assertIn("Total: 0 tokens", text)
        self.assertIn("Recorded cost: $0", text)
        self.assertIn("Range: 2026-09-11T18:34:33.437Z to 2026-09-18T18:34:33.437Z", text)
        self.assertIn("ChatGPT Plus/Pro", text)
        self.assertNotIn("could not parse detailed token usage", text)
        self.assertEqual(b"", errors)

    def test_amp_still_parses_legacy_from_token_table(self) -> None:
        self.amp_executable(
            """# Usage

Signed in as test@example.com
**Amp Megawatt Subscription:** 100% other usage remaining

Range: 2026-08-23T08:33:52.879Z to 2026-08-30T08:33:52.879Z (end exclusive)
Total tokens: 3,254,967

## From
| Source | Tokens |
| --- | ---: |
| ChatGPT Plus/Pro | 3,254,967 |

## Models
| Model | Tokens |
| --- | ---: |
| GPT-5.6 Sol | 3,254,967 |
""",
            "active  ChatGPT Plus/Pro subscription      Test subscription    00000000-0000-4000-8000-000000000001\n",
        )
        output, _ = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("ChatGPT Plus/Pro: 3,254,967 tokens", text)
        self.assertIn("Total: 3,254,967 tokens", text)
        self.assertIn("Range: 2026-08-23T08:33:52.879Z to 2026-08-30T08:33:52.879Z", text)
        self.assertNotIn("could not parse detailed token usage", text)

    def test_kimi_prefers_absolute_usage_over_stale_zero_ratio_fields(self) -> None:
        reset = "2026-09-20T05:19:23Z"
        five_reset = "2026-09-18T21:19:23Z"
        self.kimi_curl({
            "usage": {
                "limit": "100",
                "used": "65",
                "remaining": "35",
                "resetTime": reset,
            },
            "limits": [{
                "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                "detail": {"limit": "100", "used": "100", "resetTime": five_reset},
            }],
            "usages": {
                "limit_5h": {"used_ratio": 0, "reset_time": five_reset},
                "limit_7d": {"used_ratio": 0, "reset_time": reset},
            },
        })
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("Weekly: [█████████████░░░░░░░] 65% used, 35% remaining", text)
        self.assertIn("5h: [████████████████████] 100% used, 0% remaining", text)
        self.assertIn("Kimi [weekly]", text)
        self.assertNotIn("Weekly: [░░░░░░░░░░░░░░░░░░░░] 0% used", text)
        requests = [
            json.loads(line)
            for line in (self.root / "kimi-curl-requests.jsonl").read_text().splitlines()
        ]
        usage_requests = [r for r in requests if "usages" in " ".join(r["args"])]
        self.assertTrue(usage_requests)
        self.assertIn("api.kimi.com/coding/v1/usages", usage_requests[0]["args"][-1])
        self.assertIn("Authorization: Bearer fake-kimi-token", usage_requests[0]["config"])
        self.assertNotIn("fake-kimi-token", text)
        self.assertEqual(b"", errors)

    def test_kimi_derives_usage_from_limit_and_remaining(self) -> None:
        # The API dropped the `used` field and reports limit/remaining only.
        reset = "2026-09-20T05:19:23.904160Z"
        five_reset = "2026-09-18T21:19:23.904160Z"
        self.kimi_curl({
            "usage": {"limit": "100", "remaining": "40", "resetTime": reset},
            "limits": [{
                "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                "detail": {"limit": "200", "remaining": "50", "resetTime": five_reset},
            }],
            "usages": {
                "limit_5h": {"used_ratio": 0, "reset_time": five_reset},
                "limit_7d": {"used_ratio": 0, "reset_time": reset},
            },
        })
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("Weekly: [████████████░░░░░░░░] 60% used, 40% remaining", text)
        self.assertIn("5h: [███████████████░░░░░] 75% used, 25% remaining", text)
        self.assertNotIn("could not parse Kimi usage limits", text)
        self.assertEqual(b"", errors)

    def test_kimi_five_hour_window_is_ranked_in_summary(self) -> None:
        # Kimi's 5-hour window must feed the ranked "5-hour limits" section,
        # not just the per-provider Kimi block above it.
        reset = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        five_reset = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        self.kimi_curl({
            "usage": {
                "limit": "100", "used": "20", "remaining": "80", "resetTime": reset,
            },
            "limits": [{
                "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                "detail": {"limit": "100", "used": "40", "resetTime": five_reset},
            }],
            "usages": {},
        })
        output, errors = self.start("-a", "kimi").communicate(timeout=5)
        text = output.decode()
        five_hour = text.split("── 5-hour limits", 1)[1].split(
            "── Credits expiring soonest", 1)[0]
        self.assertIn("Kimi [5h]", five_hour)
        self.assertIn("40% used", five_hour)
        self.assertEqual(b"", errors)

    def test_kimi_missing_login_is_unavailable_without_request(self) -> None:
        self.executable(
            "curl",
            '#!/bin/sh\ntouch "$TMPDIR/kimi-unexpected-request"\nexit 1\n',
        )
        output, errors = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("no Kimi Code login", text)
        self.assertFalse((self.root / "kimi-unexpected-request").exists())
        self.assertNotIn("Kimi [weekly]", text)

    def test_kimi_expired_token_without_refresh_requires_login(self) -> None:
        self.kimi_credentials("stale-kimi-token", expires_in=-60)
        cred = self.home / ".kimi-code/credentials/kimi-code.json"
        data = json.loads(cred.read_text())
        data.pop("refresh_token", None)
        cred.write_text(json.dumps(data))
        self.executable(
            "curl",
            '#!/bin/sh\ntouch "$TMPDIR/kimi-unexpected-request"\nexit 1\n',
        )
        output, _ = self.start().communicate(timeout=5)
        text = output.decode()
        self.assertIn("Kimi Code login needs renewal", text)
        self.assertFalse((self.root / "kimi-unexpected-request").exists())

    def test_kimi_http_error_and_parse_error_are_unavailable(self) -> None:
        for status, payload, message in [
            (401, {"error": "nope"}, "login needs renewal"),
            (500, {"error": "nope"}, "HTTP 500"),
            (200, {"usages": {}}, "could not parse Kimi usage limits"),
        ]:
            with self.subTest(status=status, message=message):
                self.kimi_curl(payload, status)
                output, _ = self.start().communicate(timeout=5)
                text = output.decode()
                self.assertIn(message, text)
                self.assertNotIn("Weekly: [", text)
                self.assertNotIn("Kimi [weekly]", text)

    def opencode_response(self, payload: dict | str, status: int = 200, *,
                          curl_status: int = 0, key: str = "fake-go-key") -> None:
        auth = self.home / ".local/share/opencode/auth.json"
        auth.parent.mkdir(parents=True, exist_ok=True)
        auth.write_text(json.dumps({"opencode-go": {"type": "api", "key": "stale-legacy-key"}}))
        self.env["OPENCODE_AUTH_EXPORT"] = json.dumps([
            {"id": "cred-inactive", "integrationID": "opencode-go", "active": False,
             "label": "Old key", "value": {"type": "key", "key": "inactive-key"}},
            {"id": "cred-active", "integrationID": "opencode-go", "active": True,
             "label": "Current key", "value": {"type": "key", "key": "fake-go-key"}},
        ])
        self.executable("opencode", f"#!{sys.executable}\n" + """
import os, sys
if sys.argv[1:] != ["auth", "export", "opencode-go"]:
    sys.exit(2)
print(os.environ["OPENCODE_AUTH_EXPORT"])
""")
        self.env["OPENCODE_RESPONSE"] = payload if isinstance(payload, str) else json.dumps(payload)
        self.env["OPENCODE_HTTP_STATUS"] = str(status)
        self.env["OPENCODE_CURL_STATUS"] = str(curl_status)
        self.env["OPENCODE_EXPECTED_KEY"] = key
        self.executable("curl", f"#!{sys.executable}\n" + """
import os, sys
if "Authorization: Bearer " + os.environ["OPENCODE_EXPECTED_KEY"] not in sys.argv:
    sys.exit(22)
print(os.environ["OPENCODE_RESPONSE"])
if "--write-out" in sys.argv:
    print(os.environ["OPENCODE_HTTP_STATUS"], end="")
sys.exit(int(os.environ["OPENCODE_CURL_STATUS"]))
""")

    def test_opencode_limits_and_rankings(self) -> None:
        now = datetime.now(timezone.utc)
        self.opencode_response({"usage": {
            "rolling": {"status": "ok", "percent": 25,
                        "resetsAt": (now + timedelta(hours=2)).isoformat()},
            "weekly": {"status": "ok", "percent": 40,
                       "resetsAt": (now + timedelta(days=3)).isoformat()},
            "monthly": {"status": "ok", "percent": 60,
                        "resetsAt": (now + timedelta(days=20)).isoformat()},
        }})
        process = self.start("-a", "opencode")
        output, errors = process.communicate(timeout=5)
        text = output.decode()
        self.assertEqual(0, process.returncode, errors.decode())
        self.assertEqual(b"", errors)
        self.assertIn("25% used, 75% remaining", text)
        self.assertIn("40% used, 60% remaining", text)
        self.assertIn("60% used, 40% remaining", text)
        five_hour = text.split("── 5-hour limits", 1)[1].split(
            "── Credits expiring soonest", 1)[0]
        summary = text.split("── Credits expiring soonest", 1)[1]
        self.assertIn("OpenCode Go [5h]", five_hour)
        self.assertIn("OpenCode Go [weekly]", summary)
        self.assertIn("OpenCode Go [monthly]", summary)

    def test_opencode_environment_key_overrides_saved_auth_without_cli(self) -> None:
        now = datetime.now(timezone.utc)
        payload = {"usage": {
            window: {"status": "ok", "percent": 25,
                     "resetsAt": (now + timedelta(hours=2)).isoformat()}
            for window in ("rolling", "weekly", "monthly")
        }}
        for missing_cli in (False, True):
            with self.subTest(missing_cli=missing_cli):
                self.opencode_response(payload, key="environment-go-key")
                self.env["OPENCODE_API_KEY"] = "environment-go-key"
                if missing_cli:
                    (self.bin / "opencode").unlink()
                process = self.start("-a", "opencode")
                output, errors = process.communicate(timeout=5)
                self.assertEqual(0, process.returncode, output.decode())
                self.assertEqual(b"", errors)
                self.assertIn("25% used, 75% remaining", output.decode())
                self.assertNotIn("environment-go-key", output.decode())

    def test_opencode_rejected_environment_key_does_not_fall_back(self) -> None:
        self.opencode_response({"error": {"type": "AuthError", "message": "Unauthorized"}},
                               401, key="rejected-environment-key")
        self.env["OPENCODE_API_KEY"] = "rejected-environment-key"
        process = self.start("-a", "opencode")
        output, errors = process.communicate(timeout=5)
        self.assertEqual(1, process.returncode)
        self.assertEqual(b"", errors)
        self.assertIn("HTTP 401", output.decode())
        self.assertNotIn("rejected-environment-key", output.decode())

    def test_opencode_reports_expired_key_http_transport_and_parse_errors(self) -> None:
        expired = {"error": {
            "type": "authentication_error", "code": "api_key_expired",
            "message": "This API key has expired. Signing in again will not renew this key.",
        }}
        for payload, status, curl_status, message in [
            (expired, 401, 0, "OpenCode Go API key expired; create a new key in OpenCode Console"),
            ({"error": {"code": "invalid_api_key"}}, 401, 0, "HTTP 401"),
            ("Forbidden", 403, 0, "HTTP 403"),
            ({"error": "rate limited"}, 429, 0, "HTTP 429"),
            ({"error": "server error"}, 500, 0, "HTTP 500"),
            ("", 0, 28, "usage request failed"),
            ("not JSON", 200, 0, "could not parse OpenCode Go usage limits"),
            ({"usage": {}}, 200, 0, "could not parse OpenCode Go usage limits"),
        ]:
            with self.subTest(status=status, curl_status=curl_status, message=message):
                self.opencode_response(payload, status, curl_status=curl_status)
                process = self.start("-a", "opencode")
                output, errors = process.communicate(timeout=5)
                text = output.decode()
                self.assertEqual(1, process.returncode)
                self.assertEqual(b"", errors)
                self.assertIn(message, text)
                self.assertNotIn("OpenCode Go [", text)
                self.assertNotIn("fake-go-key", text)

    def test_opencode_invalid_native_credentials_do_not_use_legacy_key(self) -> None:
        self.opencode_response({"usage": {}})
        self.executable("curl", '#!/bin/sh\ntouch "$TMPDIR/unexpected-go-request"\nexit 1\n')
        for exported in ("not JSON", "[]", json.dumps([
            {"integrationID": "opencode-go", "active": False,
             "value": {"type": "key", "key": "inactive-key"}},
        ])):
            with self.subTest(exported=exported):
                self.env["OPENCODE_AUTH_EXPORT"] = exported
                process = self.start("-a", "opencode")
                output, errors = process.communicate(timeout=5)
                self.assertEqual(1, process.returncode)
                self.assertEqual(b"", errors)
                self.assertIn("active OpenCode Go API key", output.decode())
                self.assertFalse((self.root / "unexpected-go-request").exists())

    def test_opencode_missing_cli_does_not_use_legacy_key(self) -> None:
        self.opencode_response({"usage": {}})
        (self.bin / "opencode").unlink()
        self.executable("curl", '#!/bin/sh\ntouch "$TMPDIR/unexpected-go-request"\nexit 1\n')
        process = self.start("-a", "opencode")
        output, errors = process.communicate(timeout=5)
        self.assertEqual(1, process.returncode)
        self.assertEqual(b"", errors)
        self.assertIn("opencode is not on PATH", output.decode())
        self.assertFalse((self.root / "unexpected-go-request").exists())

    def test_opencode_native_export_failure_does_not_use_legacy_key(self) -> None:
        self.opencode_response({"usage": {}})
        self.executable("opencode", "#!/bin/sh\nexit 1\n")
        self.executable("curl", '#!/bin/sh\ntouch "$TMPDIR/unexpected-go-request"\nexit 1\n')
        process = self.start("-a", "opencode")
        output, errors = process.communicate(timeout=5)
        self.assertEqual(1, process.returncode)
        self.assertEqual(b"", errors)
        self.assertIn("could not export OpenCode Go credentials", output.decode())
        self.assertFalse((self.root / "unexpected-go-request").exists())

    TS_JAR = ".cache/agent-usage/typesafe-cookies.txt"
    TS_ACTION = ".cache/agent-usage/typesafe-billing-action"

    @staticmethod
    def typesafe_jwt(expires_at: str) -> str:
        def seg(obj: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
        return ".".join([
            seg({"alg": "none"}),
            seg({"exp": 1, "iat": 0, "https://stytch.com/session": {"expires_at": expires_at}}),
            "signature",
        ])

    def typesafe_jar(self, session: str | None = None, *, sid: str = "durable-session-id") -> Path:
        jar = self.home / self.TS_JAR
        jar.parent.mkdir(parents=True, exist_ok=True)
        if session is None:
            session = self.typesafe_jwt("2026-10-02T06:57:01Z")
        rows = [
            "# Netscape HTTP Cookie File",
            "#HttpOnly_console.typesafe.ai\tFALSE\t/\tTRUE\t9999999999\tsession_id\t" + sid,
            "#HttpOnly_console.typesafe.ai\tFALSE\t/\tTRUE\t9999999999\tsession\t" + session,
        ]
        jar.write_text("\n".join(rows) + "\n")
        return jar

    def typesafe_curl(self, plan: dict) -> None:
        # Answers the console endpoints from `plan`, and emulates curl's -b/-c jar.
        self.env["TYPESAFE_FAKE"] = json.dumps(plan)
        self.executable(
            "curl",
            f"#!{sys.executable}\n"
            + r'''
import json, os, pathlib, sys

plan = json.loads(os.environ["TYPESAFE_FAKE"])
args = sys.argv[1:]
url = next((a for a in args if a.startswith("https://")), "")
if "typesafe.ai" not in url:
    sys.exit(1)

def opt(flag):
    return args[args.index(flag) + 1] if flag in args else None

action = next((a.split(": ", 1)[1] for a in args if a.startswith("Next-Action: ")), None)
pathlib.Path(os.environ["TMPDIR"], "typesafe-curl.jsonl").open("a").write(
    json.dumps({"url": url, "args": args, "action": action}) + "\n"
)

if "/api/usage" in url:
    reply = plan.get("usage", {})
elif "/api/me" in url:
    reply = plan.get("me", {"status": 200, "body": "{}"})
elif "/_next/static/chunks/" in url:
    key = url.split("console.typesafe.ai", 1)[1].split("?", 1)[0]
    reply = {"status": 200, "body": plan.get("chunks", {}).get(key, "")}
elif "/settings/billing" in url and "--data" in args:
    reply = plan.get("billing_by_action", {}).get(action) or plan.get("billing", {})
else:
    reply = {"status": 200, "body": plan.get("page", "")}

status = str(reply.get("status", 200))
body = reply.get("body", "")

jar_out = opt("-c")
if jar_out:
    jar_in = opt("-b")
    existing = []
    if jar_in and os.path.exists(jar_in):
        existing = pathlib.Path(jar_in).read_text().splitlines()
    session = plan.get("session_out", "KEEP")
    if session == "KEEP":
        session = next((l.split("\t")[6] for l in existing if "\tsession\t" in l), "")
    kept = [l for l in existing if "\tsession\t" not in l]
    kept.append("#HttpOnly_console.typesafe.ai\tFALSE\t/\tTRUE\t9999999999\tsession\t" + session)
    pathlib.Path(jar_out).write_text("\n".join(kept) + "\n")

out = opt("-o")
if out and out != "/dev/null":
    pathlib.Path(out).write_text(body)
elif not out:
    sys.stdout.write(body)
if "--write-out" in args:
    sys.stdout.write(opt("--write-out").replace("%{http_code}", status))
''',
        )

    def typesafe_requests(self) -> list[dict]:
        path = self.root / "typesafe-curl.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    @staticmethod
    def typesafe_flight(billing: dict) -> str:
        return ('0:{"a":"$@1","f":"","q":"","i":true}\n'
                + "1:" + json.dumps({"ok": True, "data": {"billing": billing, "payments": []}}))

    def typesafe_plan(self, **overrides) -> dict:
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        billing = {
            "plan": "pay_as_you_go", "spent": 11.45, "freeCreditsRemaining": 0,
            "balance": 11.54, "purchased": 11.54, "resetsInDays": 9,
            "cycleLabel": "September 2026",
            "credits": [
                {"id": "free", "amount": 5, "remaining": 0,
                 "createdAt": iso(now - timedelta(days=6)),
                 "expiresAt": iso(now + timedelta(days=24)), "reason": "free_tier_credit"},
                {"id": "paid", "amount": 7, "remaining": 0.54,
                 "createdAt": iso(now - timedelta(days=3)),
                 "expiresAt": iso(now + timedelta(days=365)), "reason": "purchased_credits"},
            ],
        }
        bucket = lambda dt, requests, inp, out: {
            "day": dt.strftime("%Y-%m-%dT%H:00:00+00:00"), "apiKeyId": "key_1",
            "apiKeyName": "test1", "userId": None, "userEmail": "",
            "requests": requests, "inputTokens": inp, "outputTokens": out,
        }
        usage = {"buckets": [
            bucket(now - timedelta(hours=2), 10, 1_000_000, 5_000),
            bucket(now - timedelta(days=3), 28_463, 272_000_000, 33_000_000),
            bucket(now - timedelta(days=10), 1, 1_000_000_000, 1),
        ]}
        plan = {
            "billing": {"status": 200, "body": self.typesafe_flight(billing)},
            "usage": {"status": 200, "body": json.dumps(usage)},
        }
        plan.update(overrides)
        return plan

    def test_typesafe_without_a_console_session_makes_no_request(self) -> None:
        self.typesafe_curl(self.typesafe_plan())
        output, errors = self.start().communicate(timeout=10)
        text = output.decode()
        self.assertIn("── TypeSafe ", text)
        self.assertIn("unavailable (no console session;", text)
        self.assertIn("typesafe-login", text)
        self.assertEqual([], self.typesafe_requests())
        self.assertEqual(b"", errors)

    def test_typesafe_reports_balance_credits_and_estimated_spend(self) -> None:
        jar = self.typesafe_jar()
        (self.home / self.TS_ACTION).write_text("a" * 40)
        refreshed = self.typesafe_jwt("2026-10-09T06:57:01Z")
        self.typesafe_curl(self.typesafe_plan(session_out=refreshed))
        output, errors = self.start().communicate(timeout=10)
        text = output.decode()
        self.assertIn("  Pay as you go · credit balance $11.54 ($0.00 free, $11.54 purchased)\n", text)
        self.assertIn("  September 2026 cycle: $11.45 spent; resets in 9 days\n", text)
        self.assertIn("  Free tier credit: $0.00 of $5.00 left [████████████████████] 100% used; expires ", text)
        self.assertIn("  Purchased credit: $0.54 of $7.00 left [██████████████████░░] 92.3% used; expires ", text)
        self.assertIn("    last 24h: $0.04 · 10 requests · 1.0M in / 0.0M out\n", text)
        self.assertIn("    last 7d: $11.47 · 28,473 requests · 273.0M in / 33.0M out\n", text)
        self.assertIn("    test1 (7d): $11.47 · 28,473 requests · 273.0M in / 33.0M out\n", text)
        self.assertNotIn("$53.47", text)  # the 10-day-old bucket is outside every window
        self.assertIn("TypeSafe · Free tier credit [monthly]", text)
        self.assertNotIn("Purchased credit [monthly]", text)
        # The line reflects the refreshed session, proving the jar was promoted.
        self.assertIn("  Console session ends 2026-10-08 23:57 PDT (in ", text)
        # The refreshed session is kept, and no cookie ever reaches the argv.
        self.assertIn(refreshed, jar.read_text())
        self.assertIn("durable-session-id", jar.read_text())
        for request in self.typesafe_requests():
            self.assertNotIn("durable-session-id", " ".join(request["args"]))
        # Only the cached action id was used; no rediscovery was needed.
        self.assertEqual(["a" * 40], [r["action"] for r in self.typesafe_requests() if r["action"]])
        self.assertEqual(b"", errors)

    def test_typesafe_rediscovers_the_action_id_after_a_console_deploy(self) -> None:
        self.typesafe_jar()
        (self.home / self.TS_ACTION).write_text("b" * 40)
        fresh = "c" * 42
        chunk = "/_next/static/chunks/billing.js"
        plan = self.typesafe_plan(
            page='<script src="' + chunk + '?dpl=x"></script>',
            chunks={chunk: '(0,c.createServerReference)("' + fresh + '",c.callServer,void 0,'
                           'c.findSourceMapURL,"getBillingOverviewResult")'},
        )
        plan["billing_by_action"] = {
            "b" * 40: {"status": 404, "body": "Server action not found."},
            fresh: plan["billing"],
        }
        self.typesafe_curl(plan)
        output, errors = self.start().communicate(timeout=10)
        text = output.decode()
        self.assertIn("credit balance $11.54", text)
        self.assertEqual(fresh, (self.home / self.TS_ACTION).read_text())
        self.assertEqual(["b" * 40, fresh],
                         [r["action"] for r in self.typesafe_requests() if r["action"]])
        self.assertEqual(b"", errors)

    def test_typesafe_rejected_session_keeps_the_stored_jar_intact(self) -> None:
        jar = self.typesafe_jar()
        original = jar.read_text()
        (self.home / self.TS_ACTION).write_text("d" * 40)
        # A rejected request makes the console blank the session cookie.
        plan = self.typesafe_plan(session_out="")
        plan["billing"] = {"status": 401, "body": ""}
        self.typesafe_curl(plan)
        output, _ = self.start().communicate(timeout=10)
        text = output.decode()
        self.assertIn("unavailable (console session ended;", text)
        self.assertIn("typesafe-login", text)
        self.assertEqual(original, jar.read_text())

    def test_typesafe_missing_action_and_unparsable_billing_are_unavailable(self) -> None:
        self.typesafe_jar()
        plan = self.typesafe_plan(page='<script src="/_next/static/chunks/none.js"></script>',
                                  chunks={"/_next/static/chunks/none.js": "no reference here"})
        plan["billing"] = {"status": 404, "body": "Server action not found."}
        self.typesafe_curl(plan)
        output, _ = self.start().communicate(timeout=10)
        self.assertIn("unavailable (could not locate the console billing action", output.decode())

        (self.root / "typesafe-curl.jsonl").unlink()
        (self.home / self.TS_ACTION).write_text("e" * 40)
        plan = self.typesafe_plan()
        plan["billing"] = {"status": 200, "body": '0:{"a":"$@1"}\n1:"$Sreact.suspense"'}
        self.typesafe_curl(plan)
        output, _ = self.start().communicate(timeout=10)
        self.assertIn("unavailable (could not parse billing overview", output.decode())

    def test_usage_does_not_query_removed_desktop_bridge(self) -> None:
        self.executable(
            "mimo-preview-bridge",
            '#!/bin/sh\ntouch "$TMPDIR/desktop-bridge-ran"\nexit 1\n',
        )
        process = self.start()
        output, errors = process.communicate(timeout=10)
        self.assertNotIn("mimo", output.decode().lower())
        self.assertFalse((self.root / "desktop-bridge-ran").exists())
        self.assertEqual(1, process.returncode)
        self.assertEqual(b"", errors)

    def test_usage_stderr_has_no_setpgid_job_control_warning(self) -> None:
        process = subprocess.Popen(
            [
                BASH,
                "--noprofile",
                "--norc",
                "-c",
                'source "$1"; usage',
                "usage-test",
                str(WRAPPERS),
            ],
            env=self.env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=False,
        )
        self.addCleanup(self.stop, process)
        output, errors = process.communicate(timeout=8)
        self.assertNotIn(b"setpgid", errors)
        self.assertNotIn(b"Operation not permitted", errors)
        self.assertIn(b"Kimi", output)

    def test_cancellation_stops_provider_children_and_removes_scratch(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=signum):
                started = self.root / "started"
                self.env["STARTED"] = str(started)
                self.executable(
                    "agy",
                    "#!/bin/sh\nsleep 60 &\nchild=$!\n"
                    'printf \'%s %s\\n\' "$$" "$child" > "$STARTED"\n'
                    'wait "$child"\n',
                )
                process = self.start()
                deadline = time.monotonic() + 2
                while not started.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(started.exists(), "provider never started")
                pids = [int(pid) for pid in started.read_text().split()]
                self.assertEqual(2, len(pids))
                os.killpg(process.pid, signum)
                process.communicate(timeout=5)
                deadline = time.monotonic() + 2
                alive = pids[:]
                while alive and time.monotonic() < deadline:
                    for pid in alive[:]:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            alive.remove(pid)
                    time.sleep(0.01)
                self.assertEqual([], alive, "cancelled provider left child processes")
                self.assertEqual([], list(self.root.glob("usage.*")))
                started.unlink()


if __name__ == "__main__":
    unittest.main()
