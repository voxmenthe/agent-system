"""The refusal table on the error lines of real failures; no model calls."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REFUSALS = Path(__file__).resolve().parents[1] / "scripts/refusals.py"

# 10-24, three dargh workers: Devin's weekly quota (stderr, whole).
DEVIN_QUOTA = """delegate worker: dargh failed with status 1
Error: Agent error: Your weekly usage quota has been exhausted. Visit https://app.devin.ai/settings/usage to purchase on-demand usage or turn on auto-reload.: {
  "cognition.ai/errorKind": "resource_exhausted",
  "cognition.ai/retryable": true
}
"""
# 10-24, two cdm2 workers: the end of Codex's stderr, after up to 750 KB of tool transcript. The apostrophe is curly.
CODEX_QUOTA = """ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at Oct 24th, 2026 4:23 AM.
tokens used
68,344
"""
# 10-20, ocs: OpenCode Go's plan quota, as the market pool recorded it.
GO_QUOTA = ('{"type":"error","error":{"type":"provider.quota","message":"Go usage limit exceeded","status":429,'
            '"response":{"body":"{\\"type\\":\\"error\\",\\"error\\":{\\"type\\":\\"GoUsageLimitError\\"},'
            '\\"metadata\\":{\\"limitName\\":\\"weekly\\"}}"}}}\n')
# 10-28, cmds (challenge-checked-b.err), trimmed: signed out, after 4 s.
SIGNED_OUT = """delegate worker: cmds failed with status 3
Reasoning effort set to max for DeepSeek V4.1 Flash (latest).
Error: Authentication failed. Please run "cmd login" first.
{"type":"event","event":{"type":"run_error","error":{"name":"TransportError","message":"POST /alpha/generate \u2192 401 error: Invalid 'Authorization' header or token."}}}
"""
# Its last line, the CLI's JSON result, which is all the 8 KiB tail holds once a run_end event echoes the task.
SIGNED_OUT_RESULT = ('{"type":"result","subtype":"error","sessionId":"1493b3ad","usage":{"inputTokens":0},'
                     '"durationMs":1906,"finalText":"","error":"Error: Authentication failed. Please run \\"cmd login\\" first."}\n')
# A transcript line that quotes a limit message, as a worker reading this table would.
QUOTED = "exec rg -n 'rate limited|usage limit exceeded' scripts/refusals.py\n"
# 10-31, ocargh (council panel E.stderr), trimmed: an empty final answer whose OpenCode event stream carries a tool
# result quoting the quota messages; the CLI reported no error of its own.
EMPTY_ANSWER = (
    '{"type":"tool_use","timestamp":1793455800306,"sessionID":"ses_e6db","part":{"type":"tool","tool":"read",'
    '"state":{"status":"completed","output":"608:     - Codex\'s \\"You’ve hit your usage limit.\\" (with the curly '
    'apostrophe);\\n610:     - Devin\'s \\"Your weekly usage quota has been exhausted\\";\\n611:     - OpenCode Go\'s '
    '\\"Go usage limit exceeded\\".\\n613:   - A bare 429, one model\'s rate limit, and a one-model usage limit stay '
    '`rate limit or quota`."}}}\n'
    '{"type":"step_finish","timestamp":1793455821895,"sessionID":"ses_e6db","part":{"type":"step-finish",'
    '"reason":"stop","tokens":{"input":2049,"output":0,"reasoning":0,"cache":{"read":79242,"write":0}}}}\n')
# 10-31, ocargh (council panel E.stderr): OpenCode Go no longer routed the launcher's model id.
NO_ROUTE = ('{"type":"error","timestamp":1793434987246,"sessionID":"ses_e6ef1d546ffen60kAdDFo71EAS","error":'
            '{"type":"provider.no-route","message":"Model unavailable: opencode-go/gemini-4-argon-contributor"}}\n')
# 11-14, cdm (stance-tagger.err): stale codex binary rejected ~/.codex/config.toml before any model call.
CODEX_CONFIG_ERROR = """delegate worker: cdme failed with status 1
cdme(): codex exec failed with status 1
Error loading config.toml: invalid type: map, expected a boolean
in `features`
"""


class RefusalTests(unittest.TestCase):
    def classify(self, *texts: str, launcher: str | None = None) -> str:
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, text in enumerate(texts):
                path = Path(directory) / f"{index}.err"
                path.write_text(text)
                paths.append(str(path))
            option = ["--launcher", launcher] if launcher else []
            return subprocess.run([sys.executable, "-B", str(REFUSALS), *option, *paths], capture_output=True,
                                  text=True, check=True).stdout

    def test_the_recorded_plan_quota_refusals_exhaust_their_account(self) -> None:
        transcript = "exec cat notes.md\n" * 4000
        for text, harness in ([(DEVIN_QUOTA, "devin")] * 3 + [(transcript + CODEX_QUOTA, "codex")] * 2
                              + [(GO_QUOTA, 'opencode (limit "weekly")')]):
            with self.subTest(harness=harness):
                self.assertEqual(f"rate-limited: account quota exhausted on {harness}\n", self.classify(text))

    def test_other_rate_limits_stay_with_their_launcher(self) -> None:
        # None names a whole account's allowance: a bare 429, one model's rate limit, a one-model usage limit
        # (a form not yet seen) and another provider quota leave the account's other launchers usable.
        for text in ('{"error":{"message":"Too many requests","status":429}}\n',
                     "Error: rate limit exceeded for model gemini-4-argon, retry later\n",
                     "ERROR: You’ve hit your usage limit for gpt-6-astra. Switch to another model now.\n",
                     '{"type":"error","error":{"type":"provider.quota","message":"Model quota reached","status":429}}\n'):
            with self.subTest(text=text):
                self.assertTrue(self.classify(text).startswith("rate-limited: rate limit or quota"))

    def test_a_quoted_quota_message_is_not_a_refusal(self) -> None:
        # A failed worker's transcript that quotes a refusal (prose, grep output, a fixture, a doc or a tool result
        # inside a JSON event) is not the CLI's own error record, so it bars neither the account nor the launcher.
        for text in ('The plan quotes "You’ve hit your usage limit." as the Codex refusal\n',
                     "scripts/fixtures.txt:12:ERROR: You’ve hit your usage limit. Upgrade to Pro\n",
                     'CODEX_QUOTA = """ERROR: You’ve hit your usage limit. Upgrade to Pro\n',
                     "- Devin's \"Your weekly usage quota has been exhausted\";\n",
                     "  DEVIN = 'Error: Agent error: Your weekly usage quota has been exhausted.'\n",
                     "- OpenCode Go's \"Go usage limit exceeded\".\n",
                     "GO_QUOTA = ('" + GO_QUOTA, QUOTED, EMPTY_ANSWER):
            with self.subTest(text=text):
                self.assertEqual("unclassified\n", self.classify(text))

    def test_a_retired_model_is_quarantined_but_a_quoted_no_route_is_not(self) -> None:
        reason = "no route to the launcher's model (a launcher definition to update; not repaired here)"
        self.assertEqual(f"quarantined: {reason}\n", self.classify(NO_ROUTE))
        self.assertEqual("unclassified\n", self.classify("exec cat E.stderr\n  " + NO_ROUTE))

    def test_review_round_one_cases(self) -> None:
        # 11-01 review (cam, ccfx): a no-route record another harness's transcript printed mid-run; Claude's own
        # error result; a line separator inside a JSON string; OpenCode's quota record in its timestamped form;
        # a tail that starts inside one long record.
        codex_cat = "exec cat E.stderr\n" + NO_ROUTE + "ERROR: context window exceeded\n"
        self.assertEqual("unclassified\n", self.classify(codex_cat))
        claude = ('{"type":"result","subtype":"error_during_execution","is_error":true,'
                  '"errors":["rate limit exceeded"]}\n')
        self.assertEqual("rate-limited: rate limit or quota\n", self.classify(claude))
        separated = ('{"type":"tool_use","part":{"state":{"output":"notes: Error: rate limit exceeded '
                     'for gemini"}}}\n')
        self.assertEqual("unclassified\n", self.classify(separated))
        go_now = ('{"type":"error","timestamp":1793434987246,"sessionID":"ses_e6ef","error":{"type":"provider.quota",'
                  '"message":"Go usage limit exceeded","status":429,"response":{"body":"{\\"metadata\\":'
                  '{\\"limitName\\":\\"weekly\\"}}"}}}\n')
        self.assertEqual('rate-limited: account quota exhausted on opencode (limit "weekly")\n', self.classify(go_now))
        quoted = "Error: rate limit exceeded for gemini"
        record = '{"type":"tool_use","part":{"state":{"output":"' + "x" * 3000 + quoted + "y" * (8192 - len(quoted) - 5) + '"}}}\n'
        self.assertEqual("unclassified\n", self.classify(record))

    def test_review_round_two_cases(self) -> None:
        # 11-01 review round 2 (cam, ccfx). Claude's JSON output is one event array on one line, its result last.
        claude = ('[{"type":"system","subtype":"init"},{"type":"assistant","message":{"content":[{"type":"text",'
                  '"text":"PAD"}]}},{"type":"result","subtype":"error_during_execution","is_error":true,'
                  '"errors":["rate limit exceeded"]}]\n')
        for pad in ("Error: rate limit exceeded is quoted here", "x" * 9000):
            with self.subTest(pad=pad[:12]):
                self.assertEqual("rate-limited: rate limit or quota\n",
                                 self.classify(claude.replace("PAD", pad), launcher="ccfx"))
        success = '[{"type":"result","subtype":"success","is_error":false,"result":"rate limit exceeded"}]\n'
        self.assertEqual("unclassified\n", self.classify(success, launcher="ccfx"))
        # Another harness's record, printed by a Codex worker's transcript, is not that worker's refusal; the
        # market pool, which names no launcher, still reads every record.
        reason = "no route to the launcher's model (a launcher definition to update; not repaired here)"
        cat = "exec cat E.stderr\n" + NO_ROUTE
        self.assertEqual("unclassified\n", self.classify(cat, launcher="cax"))
        self.assertEqual(f"quarantined: {reason}\n", self.classify(NO_ROUTE, launcher="ocargh"))
        self.assertEqual(f"quarantined: {reason}\n", self.classify(cat))
        codex = ("exec cat E.stderr\ndelegate worker: ocargh failed with status 1\n" + GO_QUOTA
                 + "ERROR: context window exceeded\ntokens used\n68,344\n")
        # Bars the one launcher, not the OpenCode account (error records are not yet tied to their harness).
        self.assertEqual('rate-limited: rate limit or quota (limit "weekly")\n', self.classify(codex, launcher="cax"))
        self.assertEqual("unclassified\n", self.classify("exec cat cmds.err\n" + SIGNED_OUT, launcher="cax"))
        self.assertTrue(self.classify(SIGNED_OUT, launcher="cmds").startswith("quarantined: signed out"))
        # Command Code's error result carries the model's own final text, which may quote a quota message.
        quoting = ('{"type":"result","subtype":"error","sessionId":"x","finalText":"RATE_LIMIT_RE matches '
                   '\\"rate limit exceeded\\" on error records.","error":"Error: turn limit reached"}\n')
        self.assertEqual("unclassified\n", self.classify(quoting, launcher="cmds"))

    def test_a_signed_out_cli_is_quarantined_but_a_quoted_sign_out_is_not(self) -> None:
        for text in (SIGNED_OUT, "x" * 9000 + "\n" + SIGNED_OUT_RESULT):
            self.assertEqual("quarantined: signed out: authentication failed (a user action; not repaired here)\n",
                             self.classify(text))
        self.assertEqual("unclassified\n", self.classify('  print("Error: Authentication failed. Please run \\"cmd login\\" first.")\n'))

    def test_antigravity_quota_spent_on_every_account_bars_only_its_launcher(self) -> None:
        # Antigravity meters each model group apart: a spent Gemini group leaves agom's Claude group usable.
        spent = ("delegate worker: aggb2 failed with status 1\n"
                 "delegate worker: Antigravity quota exhausted on every signed-in account (Gemini Models)\n")
        self.assertEqual("rate-limited: rate limit or quota\n", self.classify(spent))

    def test_a_signed_out_second_antigravity_account_is_quarantined(self) -> None:
        signed_out = ("Antigravity account 2 is not signed in (/Users/me/.agy2); "
                      "run agg2 in a terminal once to log in\n")
        self.assertEqual("quarantined: signed out: Antigravity account 2 (a user action; not repaired here)\n",
                         self.classify(signed_out))
        self.assertEqual("unclassified\n", self.classify("  echo \"Antigravity account 2 is not signed in\"\n"))

    def test_a_startup_config_load_failure_is_quarantined_but_a_quoted_one_is_not(self) -> None:
        reason = "startup configuration load failed (a local CLI/config error; not repaired here)"
        for launcher in (None, "cdm", "cdx", "cdxk:cdx"):
            with self.subTest(launcher=launcher):
                self.assertEqual(f"quarantined: {reason}\n", self.classify(CODEX_CONFIG_ERROR, launcher=launcher))
        for text in ('  Error loading config.toml: invalid type: map, expected a boolean\n',
                     'exec rg "Error loading config.toml" scripts/refusals.py\n'):
            with self.subTest(quoted=text):
                self.assertEqual("unclassified\n", self.classify(text, launcher="cdm"))
        # Another harness printing Codex's error file verbatim is not its own startup failure.
        self.assertEqual("unclassified\n", self.classify("exec cat stance-tagger.err\n" + CODEX_CONFIG_ERROR, launcher="cmds"))
        self.assertEqual("unclassified\n", self.classify("exec cat stance-tagger.err\n" + CODEX_CONFIG_ERROR, launcher="ccfx"))

    def test_codex_api_key_launchers_keep_their_own_harness(self) -> None:
        self.assertEqual("rate-limited: account quota exhausted on codex\n",
                         self.classify(CODEX_QUOTA, launcher="cdxk:cdx"))
        self.assertEqual('rate-limited: rate limit or quota (limit "weekly")\n',
                         self.classify(GO_QUOTA, launcher="cdxk:cdx"))
        self.assertEqual("quarantined: signed out: Antigravity account 2 (a user action; not repaired here)\n",
                         self.classify("Antigravity account 2 is not signed in\n", launcher="agk:agnh"))
        self.assertEqual("rate-limited: rate limit or quota\n",
                         self.classify(CODEX_QUOTA, launcher="agk:agnh"))

    def test_an_unseen_message_is_unclassified(self) -> None:
        self.assertEqual("unclassified\n", self.classify("Error: context window exceeded\n"))

    def test_only_the_tail_is_read(self) -> None:
        limited = '{"error":{"message":"Too many requests","status":429}}\n'
        self.assertEqual("unclassified\n", self.classify(limited + "exec cat notes.md\n" * 1000))
        self.assertEqual("rate-limited: rate limit or quota\n", self.classify(limited))

    def test_the_market_pool_can_load_the_table(self) -> None:
        # scripts/grok-X-adhoc/delegate_pool.py runs this source with only a __name__, and calls classify(text).
        table = {"__name__": "refusals"}
        exec(compile(REFUSALS.read_text(), str(REFUSALS), "exec"), table)
        self.assertEqual(("rate-limited", "account quota exhausted on codex"), table["classify"](CODEX_QUOTA))

    def test_every_file_is_read(self) -> None:
        self.assertEqual("rate-limited: account quota exhausted on codex\n", self.classify("no answer\n", CODEX_QUOTA))


if __name__ == "__main__":
    unittest.main()
