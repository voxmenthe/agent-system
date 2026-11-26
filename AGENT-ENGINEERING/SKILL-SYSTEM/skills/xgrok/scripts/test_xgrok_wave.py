#!/usr/bin/env python3
"""Unit tests for the pure pieces of xgrok_wave.py and xgrok_roster.py.

Run: python3 scripts/test_xgrok_wave.py   (test_xgrok.sh also runs this)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xgrok_roster  # noqa: E402
import xgrok_wave  # noqa: E402

# Literal lines from the 2026-09-21 wave-2 briefs whose bounds silently failed.
E1_ELECTION_LINE = (
    "5. Election/run-hot lane. Keyword Latest, Monday 06:30-16:10 PDT: `(Bessent OR Treasury) (midterm OR "
    'midterms OR election OR "run hot")` restricted to quality accounts: from:dampedspring OR from:chabot_ben OR '
    "from:DannyDayan5 OR from:stevenkelly49 OR from:NathanTankus OR from:jasonfurman. Then one unrestricted pass."
)
E1_BESSENT_SPAN_LINE = (
    "6. Bessent's own words: `(from:FinancialJuice OR from:DeItaone OR from:LiveSquawk OR from:FirstSquawk OR "
    "from:unusual_whales) Bessent since:2026-09-21_03:00:00_PDT until:2026-09-21_16:10:00_PDT` - recover verbatim."
)
E3_SINGLE_HANDLE_LINE = (
    "4. Single-handle Latest, Monday 10:00-16:10 PDT, for from:MenthorQ, from:Ksidiii, from:ZeroGEXOptions "
    "(check `2102133156283346995` for a self-thread continuation), from:quantedOptions, from:LeopoldQF, "
    "from:Morpheu5Watcher, from:OptionsDepth. Recover the post-close positioning statements verbatim."
)
B1_PAREN_LINE = (
    "Queries to run (adapt): (from:isellpremium OR from:traderhc OR from:GammaGirlLab OR from:saltydocEM OR "
    "from:wey_how12640 OR from:cfromhertz) with the window bounds; the same batch with (bought OR buying OR hedging)."
)
COMMON_TAIL_METHOD_LINE = (
    "(2) Single-handle Latest (`from:<handle>` alone, never an OR batch) when the brief asks whether a specific "
    "account posted; an under-limit return is the only acceptable proof of silence."
)


class QueryLintTests(unittest.TestCase):
    def errors_and_warnings(self, text: str):
        findings = xgrok_wave.lint_query_shapes(text)
        return [f for f in findings if f.is_error], [f for f in findings if not f.is_error]

    def test_roster_in_prose_after_backticked_keywords_is_an_error(self):
        errors, _ = self.errors_and_warnings(E1_ELECTION_LINE)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].from_count, 6)
        self.assertIn("Bessent", errors[0].keywords)

    def test_code_span_with_five_handles_and_keyword_is_an_error(self):
        errors, _ = self.errors_and_warnings(E1_BESSENT_SPAN_LINE)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].from_count, 5)
        self.assertEqual(errors[0].keywords, ("Bessent",))

    def test_parenthesized_roster_and_keyword_group_is_an_error(self):
        errors, _ = self.errors_and_warnings(B1_PAREN_LINE)
        self.assertEqual(len(errors), 1)
        self.assertIn("bought", errors[0].keywords)

    def test_single_handle_list_with_post_id_span_is_only_a_warning(self):
        errors, warnings = self.errors_and_warnings(E3_SINGLE_HANDLE_LINE)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].from_count, 7)

    def test_four_handles_with_keywords_is_clean(self):
        text = "`(from:a OR from:b OR from:c OR from:d) (CPI OR inflation) since:2026-09-21_06:30:00_PDT`"
        self.assertEqual(xgrok_wave.lint_query_shapes(text), [])

    def test_two_small_spans_on_one_line_are_clean(self):
        text = "Run `(from:a OR from:b OR from:c) CPI` then `(from:d OR from:e OR from:f) payrolls`."
        self.assertEqual(xgrok_wave.lint_query_shapes(text), [])

    def test_calls_on_one_line_are_linted_one_call_at_a_time(self):
        text = (
            "Call 1: (from:a OR from:b OR from:c) (oil OR crude) Latest. "
            "Call 2: (from:d OR from:e OR from:f) (CPI OR inflation) Latest."
        )
        self.assertEqual(xgrok_wave.lint_query_shapes(text), [])
        errors, _ = self.errors_and_warnings(
            text + " Call 3: (from:g OR from:h OR from:i OR from:j OR from:k) (gold OR silver) Latest."
        )
        self.assertEqual([e.from_count for e in errors], [5])
        self.assertTrue(errors[0].text.startswith("(from:g"), errors[0].text)

    def test_numbered_and_semicolon_queries_on_one_line_are_linted_one_query_at_a_time(self):
        # 2026-10-19 09:58: one Search design line of numbered ';'-separated queries read as "7 from: handles
        # combined with keyword terms", though no single query had more than four.
        text = ("Search design: each query carries the tail's bounds: (1) (from:a OR from:b OR from:c) (CRWV OR "
                "CoreWeave) min_faves:3; (2) (from:d OR from:e OR from:f OR from:g) (NBIS OR Nebius); (3) "
                "from:h CoreWeave Latest.")
        self.assertEqual(xgrok_wave.lint_query_shapes(text), [])
        errors, _ = self.errors_and_warnings(text.replace("from:g)", "from:g OR from:x)"))
        self.assertEqual([e.from_count for e in errors], [5])
        self.assertEqual(errors[0].keywords[:2], ("NBIS", "Nebius"))

    def test_a_plan_numbered_n_paren_on_one_line_is_linted_one_call_at_a_time(self):
        # 2026-10-23: call plans written "1) ...; 2) ..." on one line read as "12 from: handles combined with keyword
        # terms", and six briefs were refused; "5-6)" numbers a pair of calls.
        text = ("Call plan (6 calls): 1) from:AndreasSteno OR from:BobEUnlimited OR from:MacroAlf OR from:TimmerFidelity "
                "(France OR OAT); 2) from:mark_dow OR from:robin_j_brooks OR from:michaelxpettis OR from:Brad_Setser "
                "(France OR spreads); 3) from:super_macro OR from:oddlots OR from:PolemicTMM (oil OR bonds); 5-6) "
                "thread-fetch and floor-free conversation on the best root, from:robin_j_brooks if he revises.")
        self.assertEqual(xgrok_wave.lint_query_shapes(text), [])
        # Digits closing a group after an operator are not a call number.
        errors, _ = self.errors_and_warnings(
            "1) (from:a OR from:b OR from:c OR from:d OR from:e) (oil OR crude min_faves:20) Latest.")
        self.assertEqual([e.from_count for e in errors], [5])

    def test_a_semicolon_before_prose_keeps_the_query_whole(self):
        # "the same batch with (...)" refers back to the handles before the ';', so it is one query.
        errors, _ = self.errors_and_warnings(B1_PAREN_LINE)
        self.assertEqual(len(errors), 1)

    def test_placeholder_handle_and_prose_are_clean(self):
        self.assertEqual(xgrok_wave.lint_query_shapes(COMMON_TAIL_METHOD_LINE), [])

    def test_fenced_query_lines_are_checked_individually(self):
        text = "```text\n(from:a OR from:b OR from:c OR from:d OR from:e) (oil OR crude) since:2026-09-01\n```\n"
        errors, _ = self.errors_and_warnings(text)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].line_no, 2)

    def test_keyword_terms_drop_operators_ids_and_stop_words(self):
        terms = xgrok_wave.keyword_terms(
            '(from:a OR from:b) ("rate cut" OR FOMC) since:2026-09-21_06:30:00_PDT until:x min_faves:3 Latest 2102133156283346995'
        )
        self.assertEqual(terms, ['"rate', 'cut"', "FOMC"])


# Literal line from the 2026-10-08 update run: the floored 14-term query returned nothing.
FLOORED_LONG_OR_LINE = (
    "3. One call, Latest, ($SPX OR $SPY OR $QQQ OR $ES_F OR $NQ_F) (bounce OR oversold OR \"lower lows\" OR "
    "\"negative gamma\" OR \"put wall\" OR flush OR capitulation OR \"short squeeze\" OR \"more downside\") "
    "min_faves:5 since:2026-10-08_09:40:00_PDT until:2026-10-08_10:21:58_PDT."
)
# The /macro token pack: about 20 terms with a floor, scoped to a list, which keeps its own "drop the floor" rule.
LIST_TOKEN_PACK_LINE = (
    "`list:209841180 since:{bound} -filter:replies (yields OR FOMC OR CPI OR Fed OR rates OR inflation OR \"10y\" OR "
    "dollar OR DXY OR credit OR recession OR payrolls OR PCE OR ECB) min_faves:3`"
)


class FlooredOrListTests(unittest.TestCase):
    def test_a_floored_open_query_with_a_long_or_list_warns(self):
        warnings = xgrok_wave.lint_floored_or_lists(FLOORED_LONG_OR_LINE)
        self.assertEqual(len(warnings), 1)
        self.assertIn("14 OR terms", warnings[0])

    def test_semicolon_separated_queries_are_counted_one_at_a_time(self):
        # 2026-10-19 09:45, 11-focus-crowd: six short Top queries on one line read as "12 OR terms".
        text = ("Search design: one Top query per company, each with the tail's since: (newest slice) and until: "
                "bounds and min_faves:3: ($SPCX OR SpaceX) ; ($TSLA OR Tesla) ; ($META OR \"Meta Platforms\") ; "
                "($SNDK OR SanDisk) -solana -token -USDT -moonshot ; ($AMD OR \"Advanced Micro\") ; ($MSFT OR "
                "Microsoft). Then one spare call to split the most crowded name with -filter:replies or a "
                "since:2026-10-19_06:30:00_PDT session slice. 7 calls maximum.")
        self.assertEqual(xgrok_wave.lint_floored_or_lists(text), [])
        self.assertEqual(len(xgrok_wave.lint_floored_or_lists(text.replace(" ; ", " "))), 1)

    def test_list_scoped_short_or_unfloored_queries_are_clean(self):
        for text in (LIST_TOKEN_PACK_LINE,
                     "($NVDA OR $AVGO OR $MU OR $CEG OR $VST) since:x -filter:replies min_faves:10",
                     FLOORED_LONG_OR_LINE.replace("min_faves:5 ", ""),
                     "(from:a OR from:b) (one OR two OR three OR four OR five OR six OR seven OR eight OR nine) min_faves:5"):
            self.assertEqual(xgrok_wave.lint_floored_or_lists(text), [], text)

    def test_the_warning_reaches_validation_without_blocking_launch(self):
        utc_line = (
            FLOORED_LONG_OR_LINE
            .replace("since:2026-10-08_09:40:00_PDT", "since:2026-10-08_16:40:00_UTC")
            .replace(" until:2026-10-08_10:21:58_PDT", "")
        )
        job = xgrok_wave.BriefJob("b", Path("/dev/null"), "harvest", utc_line)
        errors, warnings = xgrok_wave.validate_jobs([job], True)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("b: line 1: floored open query"), warnings)


class BroadTopicWordLintTests(unittest.TestCase):
    # 2026-10-21 evening, 03-focus-a: "($AAPL OR Apple) rates" found another sense of "rates", and AAPL stance after
    # 12:21 stayed unproven; the lane's own follow-up lead was to rerun it without the word.
    def test_a_single_ticker_query_requiring_a_broad_macro_word_warns(self):
        for query in ("`($AAPL OR Apple) rates since:2026-10-21_12:21:00_PDT until:2026-10-21_22:00:22_PDT`",
                      "1) $XOM (oil OR yields) min_faves:5 2) $NVDA capex"):
            warnings = xgrok_wave.lint_broad_topic_words(query)
            self.assertEqual(len(warnings), 1, (query, warnings))
            self.assertIn("single-ticker query requires a broad macro word", warnings[0])
        self.assertIn("'rates'", xgrok_wave.lint_broad_topic_words("`($AAPL OR Apple) rates`")[0])

    def test_company_topic_words_several_tickers_and_alternatives_are_clean(self):
        for text in ("`($NVDA OR NVIDIA) capex since:x`",
                     "`($XOM OR $CVX OR $OXY) oil since:x`",  # a basket on the word is the word's own conversation
                     "`$AAPL (iPhone OR rates) since:x`",       # an alternative, not a requirement
                     "`$AAPL -rates since:x`",
                     "`(rates OR yields) (from:a OR from:b) since:x`"):
            self.assertEqual(xgrok_wave.lint_broad_topic_words(text), [], text)

    def test_the_warning_reaches_validation_without_blocking_launch(self):
        job = xgrok_wave.BriefJob("f", Path("/dev/null"), "harvest", "`($AAPL OR Apple) rates since:x`")
        errors, warnings = xgrok_wave.validate_jobs([job], True)
        self.assertEqual(errors, [])
        self.assertEqual([w[:30] for w in warnings], ["f: line 1: single-ticker query"])


# Executed queries from the 2026-11-19 DLR v7 waves (both manifests). The unparenthesized ones returned posts outside
# their bounds, the first handle's back to 2025, yet the audit labeled every one within-approved-query-bounds.
V7_UNSCOPED_ROSTER_QUERY = ("from:stellaathena OR from:rasbt OR from:Tim_Dettmers OR from:OfirPress -filter:replies "
                            "since:2026-11-13_02:43:00_UTC until:2026-11-20_02:43:00_UTC")
V7_UNSCOPED_PHRASE_QUERY = ('"weight-space programming" OR "weight space programming" (SFT OR obsolete OR sparks) '
                            "since:2026-11-13_02:43:00_UTC until:2026-11-20_02:43:00_UTC")
V7_SCOPED_ROSTER_QUERY = ("(from:aimalysheva OR from:cwolferesearch OR from:HeMuyu0327 OR from:huskydogewoof) "
                          "-filter:replies since:2026-11-13_02:43:00_UTC until:2026-11-20_02:43:00_UTC")
V7_NESTED_GROUP_QUERY = ('("GUARD" (arxiv OR "memory pollution" OR "80.80" OR "Meta-Harness")) '
                         "since:2026-11-13_02:43:00_UTC until:2026-11-20_02:43:00_UTC")


class OrScopeTests(unittest.TestCase):
    LAUNCH = datetime(2026, 11, 20, 2, 43, 14, tzinfo=timezone.utc)
    METADATA = ("# fresh_since: 2026-11-13T02:43:00+00:00\n# fresh_until: 2026-11-20T02:43:00+00:00\n"
                "# context_since: 2026-10-30T00:00:00+00:00\n")

    def status(self, query: str) -> str:
        window = xgrok_wave.approved_window(self.METADATA, self.LAUNCH)
        audit = xgrok_wave.audit_query_clocks([{"arguments": {"query": query}}], window, self.LAUNCH)
        self.assertEqual(audit[0]["silence_support"], "not-established")
        return audit[0]["window_status"]

    def test_a_top_level_or_carrying_bounds_or_filters_is_not_within_bounds(self):
        for query in (V7_UNSCOPED_ROSTER_QUERY, V7_UNSCOPED_PHRASE_QUERY, "from:a OR from:b -filter:replies",
                      "from:a OR from:b lang:en min_faves:3"):
            with self.subTest(query=query):
                self.assertEqual(self.status(query), "or-scope-unbounded")

    def test_parenthesized_nested_and_quoted_or_keep_their_bound_status(self):
        for query, expected in ((V7_SCOPED_ROSTER_QUERY, "within-approved-query-bounds"),
                                (V7_NESTED_GROUP_QUERY, "within-approved-query-bounds"),
                                ('"this OR that" since:2026-11-14_00:00:00_UTC until:2026-11-15_00:00:00_UTC',
                                 "within-approved-query-bounds"),
                                ("from:a OR from:b", "unbounded")):
            with self.subTest(query=query):
                self.assertEqual(self.status(query), expected)

    def test_the_brief_lint_warns_on_a_literal_unscoped_or_without_blocking_launch(self):
        job = xgrok_wave.BriefJob("b", Path("/dev/null"), "harvest",
                                  f"Seed batch: `{V7_UNSCOPED_ROSTER_QUERY}`\nRoots: `{V7_SCOPED_ROSTER_QUERY}`\n")
        errors, warnings = xgrok_wave.validate_jobs([job], True)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1, warnings)
        self.assertTrue(warnings[0].startswith("b: line 1: top-level OR"), warnings)


class BriefValidationTests(unittest.TestCase):
    def test_a_future_upper_bound_is_refused_before_launch(self):
        text = '# fresh_since: 2026-09-29T19:01:00+00:00\n# fresh_until: 2099-09-29T22:35:03+00:00\n'
        job = xgrok_wave.BriefJob("time", Path("brief.md"), "harvest", text)
        errors, _ = xgrok_wave.validate_jobs([job], False)
        self.assertTrue(any("future" in error for error in errors), errors)

    def test_naive_or_reversed_windows_are_rejected(self):
        for since, until in (("2026-09-29T19:01:00", "2026-09-29T22:35:03+00:00"),
                              ("2026-09-29T23:01:00+00:00", "2026-09-29T22:35:03+00:00")):
            text = f'# fresh_since: {since}\n# fresh_until: {until}\n'
            errors, _ = xgrok_wave.validate_jobs([xgrok_wave.BriefJob("time", Path("brief.md"), "harvest", text)], False)
            self.assertTrue(errors)

    def job(self, mode: str, text: str) -> xgrok_wave.BriefJob:
        return xgrok_wave.BriefJob(name="b", brief_path=Path("/dev/null"), mode=mode, text=text)

    def test_macro_brief_without_delegated_budget_line_is_an_error(self):
        errors, _ = xgrok_wave.validate_jobs([self.job("macro", "# mode: macro\nBudget: 16 calls.\n")], True)
        self.assertEqual(len(errors), 1)
        self.assertIn("Delegated budget:", errors[0])

    def test_macro_brief_with_delegated_budget_line_passes(self):
        text = "# mode: macro\nBudget: 16 calls.\n- **Delegated budget:** the parent expands the /macro default to 30 receipts / 5,000 words.\n"
        self.assertEqual(xgrok_wave.validate_jobs([self.job("macro", text)], True), ([], []))

    def test_harvest_brief_needs_no_delegated_budget_line(self):
        self.assertEqual(xgrok_wave.validate_jobs([self.job("harvest", "Budget: 16 calls.\n")], True), ([], []))

    def test_delegated_budget_line_in_common_tail_satisfies_macro_check(self):
        composed = xgrok_wave.compose_brief("# mode: macro\nObjective: x\n", "Delegated budget: parent expands to 20 receipts.\n")
        self.assertEqual(xgrok_wave.validate_jobs([self.job("macro", composed)], True), ([], []))

    def test_lint_can_be_disabled(self):
        errors, warnings = xgrok_wave.validate_jobs([self.job("harvest", E1_ELECTION_LINE)], lint_queries=False)
        self.assertEqual((errors, warnings), ([], []))

    def test_compose_brief_separates_with_blank_line(self):
        self.assertEqual(xgrok_wave.compose_brief("brief\n\n\n", "\ntail\n"), "brief\n\ntail\n")

    def test_mode_inference_from_frontmatter_and_comment(self):
        self.assertEqual(xgrok_wave.infer_brief_mode("---\nmode: macro\n---\nx"), "macro")
        self.assertEqual(xgrok_wave.infer_brief_mode("# mode: agents\nx"), "agents")
        self.assertEqual(xgrok_wave.infer_brief_mode("# mode: bogus\nx"), "harvest")


class BriefSettingsTests(unittest.TestCase):
    def test_frontmatter_parses_new_keys_alongside_mode(self):
        text = "---\nmode: macro\neffort: medium\nmodel: grok-4.6\nsystem_prompt: lean\n---\nObjective: x\n"
        self.assertEqual(xgrok_wave.infer_brief_mode(text), "macro")
        self.assertEqual(xgrok_wave.infer_brief_effort(text), "medium")
        self.assertEqual(xgrok_wave.infer_brief_model(text), "grok-4.6")
        self.assertEqual(xgrok_wave.infer_brief_system_prompt(text), "lean")

    def test_comment_parses_new_keys_alongside_mode(self):
        text = "# mode: harvest\n# effort: low\n# model: grok-4.6\n# system_prompt: lean\nObjective: x\n"
        self.assertEqual(xgrok_wave.infer_brief_mode(text), "harvest")
        self.assertEqual(xgrok_wave.infer_brief_effort(text), "low")
        self.assertEqual(xgrok_wave.infer_brief_model(text), "grok-4.6")
        self.assertEqual(xgrok_wave.infer_brief_system_prompt(text), "lean")

    def test_html_comment_parses_new_keys(self):
        text = "<!-- mode: harvest -->\n<!-- effort: high -->\n<!-- model: grok-4.7 -->\n<!-- system_prompt: default -->\n"
        self.assertEqual(xgrok_wave.infer_brief_mode(text), "harvest")
        self.assertEqual(xgrok_wave.infer_brief_effort(text), "high")
        self.assertEqual(xgrok_wave.infer_brief_model(text), "grok-4.7")
        self.assertEqual(xgrok_wave.infer_brief_system_prompt(text), "default")

    def test_frontmatter_takes_precedence_over_comment(self):
        text = "---\neffort: high\n---\n# effort: low\nObjective: x\n"
        self.assertEqual(xgrok_wave.infer_brief_effort(text), "high")

    def test_unset_keys_return_none(self):
        self.assertIsNone(xgrok_wave.infer_brief_effort("Objective: x\n"))
        self.assertIsNone(xgrok_wave.infer_brief_model("Objective: x\n"))
        self.assertIsNone(xgrok_wave.infer_brief_system_prompt("Objective: x\n"))

    def test_collect_jobs_reads_file_and_manifest_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = root / "a.md"
            brief.write_text("---\neffort: medium\nmodel: grok-4.6\nsystem_prompt: lean\n---\nObjective: x\n")
            jobs = xgrok_wave.collect_jobs([brief], None, None, "harvest")
            self.assertEqual(jobs[0].effort, "medium")
            self.assertEqual(jobs[0].model, "grok-4.6")
            self.assertEqual(jobs[0].system_prompt, "lean")
            plain = root / "b.md"
            plain.write_text("Objective: y\n")
            manifest = root / "m.json"
            manifest.write_text(json.dumps({
                "briefs": [{"path": str(plain), "name": "bjob", "effort": "low",
                            "model": "grok-4.7", "system_prompt": "default"}]
            }))
            jobs2 = xgrok_wave.collect_jobs([], None, manifest, "harvest")
            self.assertEqual(jobs2[0].effort, "low")
            self.assertEqual(jobs2[0].model, "grok-4.7")
            self.assertEqual(jobs2[0].system_prompt, "default")

    def test_invalid_settings_fail_validation(self):
        bad_effort = xgrok_wave.BriefJob(name="b", brief_path=Path("/dev/null"),
                                         mode="harvest", text="x", effort="bogus")
        errors, _ = xgrok_wave.validate_jobs([bad_effort], True)
        self.assertTrue(any("effort" in e for e in errors))
        low_effort = xgrok_wave.BriefJob(name="b", brief_path=Path("/dev/null"),  # workers skipped searches at low
                                         mode="harvest", text="x", effort="low")
        errors, _ = xgrok_wave.validate_jobs([low_effort], True)
        self.assertTrue(any("effort" in e for e in errors))
        bad_model = xgrok_wave.BriefJob(name="b", brief_path=Path("/dev/null"),
                                        mode="harvest", text="x", model="not-a-model")
        errors, _ = xgrok_wave.validate_jobs([bad_model], True)
        self.assertTrue(any("model" in e for e in errors))
        bad_sp = xgrok_wave.BriefJob(name="b", brief_path=Path("/dev/null"),
                                     mode="harvest", text="x", system_prompt="bogus")
        errors, _ = xgrok_wave.validate_jobs([bad_sp], True)
        self.assertTrue(any("system_prompt" in e for e in errors))
        good = xgrok_wave.BriefJob(name="b", brief_path=Path("/dev/null"),
                                   mode="harvest", text="x", effort="medium",
                                   model="grok-4.6", system_prompt="lean")
        self.assertEqual(xgrok_wave.validate_jobs([good], True), ([], []))


class WaveSettingsCliTests(unittest.TestCase):
    def _write_env_recording_launcher(self, root: Path) -> Path:
        launcher = root / "launcher"
        launcher.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\nfrom pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "brief = sys.argv[-1]\n"
            "eff = os.environ.get('XGROK_EFFORT', '<unset>')\n"
            "mod = os.environ.get('XGROK_MODEL', '<unset>')\n"
            "sp = os.environ.get('XGROK_SYSTEM_PROMPT', '<unset>')\n"
            "with (root / 'env.log').open('a') as f:\n"
            "    f.write(f\"{Path(brief).name}|{eff}|{mod}|{sp}\\n\")\n"
            "print(json.dumps({'text': 'ok', 'usage': {'output_tokens': 1}}))\n"
        )
        launcher.chmod(0o755)
        return launcher

    def _clean_xgrok_env(self) -> dict[str, str | None]:
        saved: dict[str, str | None] = {}
        for key in ("XGROK_EFFORT", "XGROK_MODEL", "XGROK_SYSTEM_PROMPT"):
            saved[key] = os.environ.pop(key, None)
        return saved

    def _restore_xgrok_env(self, saved: dict[str, str | None]) -> None:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_validation_error_exits_before_any_launch(self):
        for bad_text, needle in [
            ("---\neffort: bogus\n---\nObjective: x\n", "effort"),
            ("---\nmodel: bad-model\n---\nObjective: x\n", "model"),
            ("---\nsystem_prompt: bogus\n---\nObjective: x\n", "system_prompt"),
        ]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                brief = root / "bad.md"
                brief.write_text(bad_text)
                launcher = root / "launcher"
                launcher.write_text(
                    f"#!{sys.executable}\n"
                    "from pathlib import Path\n"
                    "Path(__file__).with_name('launched').touch()\n"
                    "print('{\"text\": \"hi\"}')\n"
                )
                launcher.chmod(0o755)
                for extra in ([], ["--dry-run"]):
                    result = subprocess.run(
                        [sys.executable, str(Path(xgrok_wave.__file__)), str(brief),
                         "--xgrok-bin", str(launcher), "--output-dir", str(root / "out"),
                         *extra],
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(needle, result.stderr)
                    self.assertFalse((root / "launched").exists())
                self.assertFalse((root / "out").exists())

    def test_an_empty_grok_home_is_refused_before_any_launch(self):
        # A failed $(xgrok --pick-account) substitutes "", which the runner silently ran as ~/.grok.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = root / "brief.md"
            brief.write_text("Objective: x\n")
            launcher = root / "launcher"
            launcher.write_text(f"#!{sys.executable}\nfrom pathlib import Path\n"
                                "Path(__file__).with_name('launched').touch()\nprint('{\"text\": \"hi\"}')\n")
            launcher.chmod(0o755)
            for extra in ([], ["--dry-run"]):
                result = subprocess.run(
                    [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--xgrok-bin", str(launcher),
                     "--output-dir", str(root / "out"), "--grok-home", "", *extra],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("--grok-home requires a non-empty path", result.stderr)
                self.assertFalse((root / "launched").exists())

    def test_env_contains_exactly_requested_keys_and_manifest_records_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = self._clean_xgrok_env()
            try:
                full = root / "full.md"
                full.write_text("---\neffort: medium\nmodel: grok-4.6\nsystem_prompt: lean\n---\nObjective: x\n")
                empty = root / "empty.md"
                empty.write_text("Objective: y\n")
                launcher = self._write_env_recording_launcher(root)
                result = subprocess.run(
                    [sys.executable, str(Path(xgrok_wave.__file__)), str(full), str(empty),
                     "--xgrok-bin", str(launcher), "--output-dir", str(root / "out"),
                     "--max-workers", "1"],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = (root / "env.log").read_text().splitlines()
                # Each launch records exactly its requested keys; unset stays unset.
                full_line = [l for l in lines if l.startswith("full.md|")][0]
                empty_line = [l for l in lines if l.startswith("empty.md|")][0]
                self.assertEqual(full_line, "full.md|medium|grok-4.6|lean")
                self.assertEqual(empty_line, "empty.md|<unset>|<unset>|<unset>")
                manifest = json.loads((root / "out" / "manifest.json").read_text())
                self.assertIn("stagger_seconds", manifest)
                self.assertEqual(manifest["stagger_seconds"], 0.0)
                by_name = {w["name"]: w for w in manifest["workers"]}
                self.assertEqual(by_name["full"]["effort"], "medium")
                self.assertEqual(by_name["full"]["model"], "grok-4.6")
                self.assertEqual(by_name["full"]["system_prompt"], "lean")
                self.assertIsNone(by_name["empty"]["effort"])
                self.assertIsNone(by_name["empty"]["model"])
                self.assertIsNone(by_name["empty"]["system_prompt"])
                self.assertIn("medium", result.stdout)
                self.assertIn("grok-4.6", result.stdout)
            finally:
                self._restore_xgrok_env(saved)

    def test_the_composed_brief_carries_each_rostered_handles_role(self):
        # TM (10-20): a worker labeled @tracyalloway "off-list context" although the roster lists the account; ME
        # (10-19): @traderhc's replies say "AI agent, automated reply", so its levels are not anyone's position.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            roster = root / "roster.tsv"
            roster.write_text("handle\tregistries\tverified\tnote\n"
                              "tracyalloway\tcredible-sources:Rates, Fed, US macro\t2026-09-27\t\n"
                              "traderhc\tequity-sentiment-panel:Tape and first-person action\t2026-09-21\t"
                              "automated: self-labeled; levels are inferred inventory, never a stance voice\n"
                              "unused\tcredible-sources:Rates, Fed, US macro\t\t\n")
            brief = root / "rates.md"
            brief.write_text("Lane: rates.\nAnchors: @tracyalloway @traderhc ; @offlist (context)\n"
                             "Search design: `from:tracyalloway since:x`\n")
            tail = root / "tail.md"
            tail.write_text("Return a compact packet.\n")
            launcher = root / "launcher"
            launcher.write_text(f"#!{sys.executable}\nprint('{{\"text\": \"hi\"}}')\n")
            launcher.chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--xgrok-bin", str(launcher),
                 "--output-dir", str(root / "out"), "--common-tail", str(tail), "--roster", str(roster)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            composed = (root / "out" / "composed" / "rates.md").read_text()
            self.assertEqual(composed, brief.read_text() + "\n" + (
                "Roster roles (the roster's entry for each handle above; copy it into the receipt's Author line "
                "instead of guessing):\n"
                "- @tracyalloway: credible-sources:Rates, Fed, US macro\n"
                "- @traderhc: equity-sentiment-panel:Tape and first-person action; automated: self-labeled; levels are "
                "inferred inventory, never a stance voice\n") + "\nReturn a compact packet.\n")
        self.assertEqual(xgrok_wave.roster_roles("Lane: x. No handles.\n", {}), "")

    def test_dry_run_lists_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = root / "a.md"
            brief.write_text("---\neffort: medium\nmodel: grok-4.6\nsystem_prompt: lean\n---\nObjective: x\n")
            launcher = root / "launcher"
            launcher.write_text(f"#!{sys.executable}\nprint('{{}}')\n")
            launcher.chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), str(brief),
                 "--xgrok-bin", str(launcher), "--dry-run"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("effort=medium", result.stdout)
            self.assertIn("grok-4.6", result.stdout)
            self.assertIn("lean", result.stdout)

    def test_account_flags_pick_one_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = root / "a.md"
            brief.write_text("Objective: x\n")
            command = [sys.executable, str(Path(xgrok_wave.__file__)), str(brief),
                       "--xgrok-bin", sys.executable, "--dry-run"]
            env = dict(os.environ, GROK2_HOME=str(root / "two"), GROK3_HOME=str(root / "three"))
            for flag, home in (("--grok2", "two"), ("--grok3", "three")):
                with self.subTest(flag=flag):
                    result = subprocess.run(command + [flag], capture_output=True, text=True, timeout=10, env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"GROK_HOME: {root / home}\n", result.stdout)
            both = subprocess.run(command + ["--grok2", "--grok3"], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(both.returncode, 2)
            self.assertIn("not allowed with argument", both.stderr)

    def test_priority_orders_launches_and_queued_lanes_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "01-tape.md").write_text("Objective: x\n")
            (root / "02-news.md").write_text("# priority: 2\nObjective: y\n")
            (root / "12-mood.md").write_text("# priority: 1\nObjective: z\n")
            launcher = root / "launcher"
            launcher.write_text(f"#!{sys.executable}\nprint('{{}}')\n")
            launcher.chmod(0o755)
            command = [sys.executable, str(Path(xgrok_wave.__file__)), "--briefs-dir", str(root),
                       "--xgrok-bin", str(launcher), "--dry-run"]
            result = subprocess.run(command + ["--max-workers", "2"], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            order = [line.split()[2] for line in result.stdout.splitlines() if line.startswith("  0")]
            self.assertEqual(order, ["12-mood", "02-news", "01-tape"])
            self.assertIn("3 lanes on 2 workers, so 01-tape wait", result.stderr)
            roomy = subprocess.run(command + ["--max-workers", "3"], capture_output=True, text=True, timeout=10)
            self.assertNotIn("free slot", roomy.stderr)
            # 10-20: "# priority: 99" meant last, but every prioritized brief started before every unprioritized one.
            (root / "03-late.md").write_text("# priority: 99\nObjective: w\n")
            late = subprocess.run(command, capture_output=True, text=True, timeout=10)
            order = [line.split()[2] for line in late.stdout.splitlines() if line.startswith("  0")]
            self.assertEqual(order, ["12-mood", "02-news", "01-tape", "03-late"])
            (root / "02-news.md").write_text("# priority: high\nObjective: y\n")
            bad = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(bad.returncode, 2)
            self.assertIn("02-news.md': priority must be an integer", bad.stderr)

    def test_stagger_delays_second_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a.md"
            first.write_text("Objective: x\n")
            second = root / "b.md"
            second.write_text("Objective: y\n")
            launcher = root / "launcher"
            # The first lane stays running until the second has started (up to 5 s), so "the stagger did not wait
            # for the first lane to finish" is a fact about order, not a wall-clock bound a loaded machine can break.
            launcher.write_text(
                f"#!{sys.executable}\n"
                "import json, sys, time\nfrom pathlib import Path\n"
                "root = Path(__file__).parent\n"
                "name = Path(sys.argv[-1]).stem\n"
                "(root / f'{name}.start').write_text(f'{time.monotonic():.6f}')\n"
                "if name == 'a':\n"
                "    give_up = time.monotonic() + 5\n"
                "    while not (root / 'b.start').exists() and time.monotonic() < give_up:\n"
                "        time.sleep(0.02)\n"
                "    (root / 'a.end').write_text(f'{time.monotonic():.6f}')\n"
                "print(json.dumps({'text': 'ok'}))\n"
            )
            launcher.chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), str(first), str(second),
                 "--xgrok-bin", str(launcher), "--output-dir", str(root / "out"),
                 "--max-workers", "2", "--stagger", "0.5"],
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            stamp = {n: float((root / n).read_text()) for n in ("a.start", "b.start", "a.end")}
            self.assertLess(stamp["b.start"], stamp["a.end"], "stagger waited for the first lane to finish")
            delta = stamp["b.start"] - stamp["a.start"]
            # 0.5 s of stagger less up to 0.25 s of interpreter-startup difference between the two launches.
            self.assertGreaterEqual(delta, 0.25, f"stagger did not delay second launch: {delta}")
            manifest = json.loads((root / "out" / "manifest.json").read_text())
            self.assertAlmostEqual(manifest["stagger_seconds"], 0.5)


def write_transcript(home: Path, session_id: str, tool_names: list[str]) -> None:
    """A Grok session transcript with one completed tool-call update per name (plus an in-progress echo)."""
    session = home / "sessions" / "%2Ftmp%2Fxgrok-worker-home" / session_id
    session.mkdir(parents=True)
    lines = []
    for i, name in enumerate(tool_names):
        for status in ("in_progress", "completed"):
            lines.append(json.dumps({"method": "session/update", "params": {"sessionId": session_id, "update": {
                "sessionUpdate": "tool_call_update", "toolCallId": f"call-{i}", "status": status,
                "rawOutput": {"name": name, "call_id": f"call-{i}"}}}}))
    lines.append("not json")
    (session / "updates.jsonl").write_text("\n".join(lines) + "\n")


def write_retried_transcript(home: Path, session_id: str) -> None:
    """10-28's macro-threads transcript, trimmed: two X calls, the CLI's retry after its response stream broke (the
    first attempt's second call completing after it), then the retried request running both calls again."""
    session = home / "sessions" / "%2Ftmp%2Fxgrok-worker-home" / session_id
    session.mkdir(parents=True)

    def call(request: str, n: int, post: str) -> dict:
        cid = f"ctc_{request}_call-b4d2ba34-{n}"
        return {"timestamp": 1793210472 + n, "params": {"update": {
            "sessionUpdate": "tool_call_update", "toolCallId": cid, "status": "completed",
            "rawOutput": {"name": "x_thread_fetch", "call_id": "xs_" + cid, "input": json.dumps({"post_id": post})}}}}
    retry = {"timestamp": 1793210535, "params": {"update": {
        "sessionUpdate": "retry_state", "type": "retrying", "attempt": 1, "max_retries": 15,
        "reason": "reqwest error stream: Transport error: error decoding response body", "error_type": "http"}}}
    events = [call("300b4d99", 0, "2115476685953085621"), retry, call("300b4d99", 1, "2115458980608987569"),
              call("7c6d900e", 0, "2115476685953085621"), call("7c6d900e", 1, "2115458980608987569")]
    (session / "updates.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))


class XToolCallCountTests(unittest.TestCase):
    def test_query_outcomes_require_an_explicit_unambiguous_return(self):
        calls = [{"id": str(n), "tool": "x_keyword_search", "arguments": {"query": query},
                  "outcome": "unknown", "retried": False}
                 for n, query in enumerate(("empty", "failed", "missing", "twice", "twice"))]
        packet = '\n'.join('- Query result: ' + json.dumps(row) for row in (
            {"query": "empty", "outcome": "returned", "count": 0},
            {"query": "failed", "outcome": "error", "error": "429/1015"},
            {"query": "twice", "outcome": "returned", "count": 4}))
        outcomes = xgrok_wave.query_outcomes(calls, packet)
        self.assertEqual([row["outcome"] for row in outcomes], ["returned", "error", "unknown", "unknown", "unknown"])
        self.assertEqual(outcomes[0]["outcome_source"], "worker-reported")
        self.assertEqual(outcomes[0]["result_count"], 0)

    def test_malformed_executed_clock_is_unavailable_not_an_audit_crash(self):
        launch = datetime(2026, 9, 29, 23, 0, tzinfo=timezone.utc)
        window = {'since': '2026-09-29T19:00:00+00:00', 'until': '2026-09-29T22:35:03+00:00'}
        calls = [{'arguments': {'query': 'since:2026-99-29_19:00:00_UTC until:2026-09-29_22:35:00_UTC'}}]
        audit = xgrok_wave.audit_query_clocks(calls, window, launch)
        self.assertEqual(audit[0]['window_status'], 'unavailable-bound-clock')

    def test_clock_audit_distinguishes_context_missing_bounds_and_timezone(self):
        launch = datetime(2026, 9, 29, 23, 0, tzinfo=timezone.utc)
        window = xgrok_wave.approved_window(
            '# fresh_since: 2026-09-29T12:00:00-07:00\n# fresh_until: 2026-09-29T15:35:03-07:00\n'
            '# context_since: 2026-09-01T00:00:00-07:00\n', launch)
        for query, expected in (
            ('since:2026-09-29_19:00:00_UTC until:2026-09-29_22:35:03_UTC', 'within-approved-query-bounds'),
            ('since:2026-09-28_12:00:00_PDT until:2026-09-29_15:35:03_PDT', 'context-lookback'),
            ('since:2026-09-29_15:35:03_PDT until:2026-09-29_12:00:00_PDT', 'reversed'),
            ('since:2026-09-29 until:2026-09-30', 'unavailable-bound-clock'),
            ('from:alpha', 'unbounded')):
            with self.subTest(query=query):
                audit = xgrok_wave.audit_query_clocks([{'arguments': {'query': query}, 'fetched_at': None}], window, launch)
                self.assertEqual(audit[0]['window_status'], expected)
                self.assertIsNone(audit[0]['fetched_at'])
        self.assertIsNone(xgrok_wave.audit_query_clocks(None, window, launch))

    def test_lane_clock_metadata_overrides_common_tail_and_future_is_rejected(self):
        launch = datetime(2026, 9, 29, 23, 0, tzinfo=timezone.utc)
        tail = '# fresh_since: 2026-09-29T12:00:00-07:00\n# fresh_until: 2026-09-29T15:35:03-07:00\n'
        lane = '# fresh_since: 2026-09-29T14:00:00-07:00\n'
        self.assertEqual(xgrok_wave.approved_window(lane + tail, launch)['since'], '2026-09-29T14:00:00-07:00')
        with self.assertRaisesRegex(ValueError, 'future'):
            xgrok_wave.approved_window(tail.replace('15:35:03', '16:00:01'), launch)

    def test_query_audit_keeps_exact_bounds_and_actual_completion_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            write_transcript(home, "sess-time-test", ["x_keyword_search"])
            transcript = next((home / "sessions").glob("*/sess-time-test/updates.jsonl"))
            event = {"timestamp": 1790721371, "params": {"update": {
                "sessionUpdate": "tool_call_update", "toolCallId": "call-0", "status": "completed",
                "rawOutput": {"name": "x_keyword_search", "input": json.dumps({
                    "query": "from:alpha since:2026-09-29_19:01:00_UTC until:2026-09-29_22:36:00_UTC", "mode": "Latest", "limit": 6})}}}}
            transcript.write_text(json.dumps(event) + "\n")
            calls = xgrok_wave.read_x_tool_calls("sess-time-test", [home])
            window = {"since": "2026-09-29T19:01:00+00:00", "until": "2026-09-29T22:35:03+00:00", "context_since": None}
            audit = xgrok_wave.audit_query_clocks(calls, window, datetime(2026, 9, 29, 22, 40, tzinfo=timezone.utc))
            self.assertEqual(audit[0]["window_status"], "widened")
            self.assertEqual(audit[0]["fetched_at"], "2026-09-29T22:36:11+00:00")
            self.assertEqual(audit[0]["silence_support"], "not-established")

    def test_counts_distinct_x_calls_and_ignores_other_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok"
            write_transcript(home, "01a0e8b9-aaaa", ["x_keyword_search", "x_thread_fetch", "read_file"])
            homes = xgrok_wave.session_homes(str(home))
            self.assertEqual(homes, [Path(f"{home}-xworker"), home])
            self.assertEqual(xgrok_wave.count_x_tool_calls("01a0e8b9-aaaa", homes), 2)

    def test_calls_in_a_request_the_cli_retried_still_count_and_are_marked(self):
        # 10-28 and 10-29: each of the 9 workers whose packet's call count disagreed with execution had one CLI retry
        # after a broken response stream, and its packet counted only the final attempt (16 vs 8, 14 vs 7, ...).
        with tempfile.TemporaryDirectory() as tmp:
            write_retried_transcript(Path(tmp), "sess-retry")
            calls = xgrok_wave.read_x_tool_calls("sess-retry", [Path(tmp)])
            self.assertEqual([call["retried"] for call in calls], [True, True, False, False])
            self.assertEqual(xgrok_wave.count_x_tool_calls("sess-retry", [Path(tmp)]), 4)

    def test_worker_home_transcript_is_found_and_zero_is_distinct_from_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "grok"
            write_transcript(Path(f"{home}-xworker"), "01a0e8b6-bbbb", [])
            homes = xgrok_wave.session_homes(str(home))
            self.assertEqual(xgrok_wave.count_x_tool_calls("01a0e8b6-bbbb", homes), 0)
            self.assertIsNone(xgrok_wave.count_x_tool_calls("01a0e8b6-cccc", homes))
            self.assertIsNone(xgrok_wave.count_x_tool_calls("../../etc", homes))
            self.assertIsNone(xgrok_wave.count_x_tool_calls(None, homes))


FIXTURES = Path(__file__).resolve().parent / "fixtures"
E_SEMIS1 = "01a1d358-ae5d-7b40-aaee-df09ced26b6b"
# E (11-12, 21:19 PT) 12-semis1's composed brief opening: the lane timed out at 900 s with no envelope.
E_SEMIS1_REQUEST = ("# mode: harvest\n# effort: medium\n# template: semis-infra\nLane: 12-semis1. Standing anchors, "
                    "roster-checked from the 2026-09-28 run; add the day's names below them.\n")


def write_session(home: Path, session_id: str, request: str, created: str, updates: str = "") -> Path:
    """A worker session as Grok writes it: summary.json's creation clock, the prompt (protocol, then the request) in
    chat_history.jsonl beside a CLI-added reminder that is not the prompt, and updates.jsonl."""
    session = home / "sessions" / "%2Fprivate%2Ftmp%2Fxgrok-worker-home" / session_id
    session.mkdir(parents=True)
    (session / "summary.json").write_text(json.dumps({"info": {"id": session_id}, "created_at": created}))
    prompt = "# XGrok worker protocol\n\n# Delegated retrieval brief\n\n" + request
    (session / "chat_history.jsonl").write_text("".join(json.dumps(entry) + "\n" for entry in (
        {"type": "system", "content": "You are Grok."},
        {"type": "user", "content": [{"type": "text", "text": "<system-reminder>skills</system-reminder>"}],
         "synthetic_reason": "skills"},
        {"type": "user", "content": [{"type": "text", "text": prompt}], "prompt_index": 0})))
    (session / "updates.jsonl").write_text(updates)
    return session


class LostEnvelopeTelemetryTests(unittest.TestCase):
    """11-13 plan, item 12: a lane that times out, is cancelled or crashes returns no envelope, so no sessionId; E's
    three timeouts (51 calls, 29 in retried requests) read as unknown until their transcripts were found by hand."""

    def test_e_semis1_timeout_replays_from_its_saved_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".grok2"
            write_session(home, E_SEMIS1, E_SEMIS1_REQUEST, "2026-11-13T05:19:26.822712Z",
                          (FIXTURES / "e-semis1-updates.jsonl").read_text())
            # 13-semis2 launched 2 s later in the same account, a different request: never attributed to semis1
            write_session(home, "01a1d358-b620-79c3-984c-73f02d401674", "Lane: 13-semis2.\n", "2026-11-13T05:19:28.8Z")
            job = xgrok_wave.BriefJob("12-semis1", Path(tmp) / "12-semis1.md", "harvest", E_SEMIS1_REQUEST)
            lost = xgrok_wave.lost_envelope_telemetry(job, str(home), datetime.fromisoformat("2026-11-13T05:19:26.567666+00:00"),
                                                      datetime.fromisoformat("2026-11-13T05:34:27.259928+00:00"))
            self.assertEqual((lost["session_id"], lost["x_tool_calls"], lost["x_tool_calls_retried"]), (E_SEMIS1, 21, 14))
            self.assertTrue(lost["session_source"].startswith("matched"))
            self.assertEqual([b["at"] for b in lost["stream_breaks"]],
                             ["2026-11-13T05:25:04+00:00", "2026-11-13T05:29:45+00:00"])  # 21:25:04 and 21:29:45 PT
            self.assertEqual(lost["last_update_at"], "2026-11-13T05:34:26+00:00")

    def test_ambiguous_absent_late_and_other_account_sessions_stay_unknown(self):
        started = datetime(2026, 11, 13, 5, 19, 26, tzinfo=timezone.utc)
        ended = datetime(2026, 11, 13, 5, 34, 27, tzinfo=timezone.utc)
        job = xgrok_wave.BriefJob("12-semis1", Path("12-semis1.md"), "harvest", E_SEMIS1_REQUEST)
        calls = (FIXTURES / "e-semis1-updates.jsonl").read_text()
        cases = {
            # two lanes launched the same request at once: neither is attributed
            "ambiguous: 2 sessions": [(".grok2", "sess-one", "2026-11-13T05:19:26.8Z"),
                                      (".grok2-xworker", "sess-two", "2026-11-13T05:19:27.1Z")],
            "no session": [],
            # created before the launch (an earlier wave's same brief) or after the kill
            "no session ": [(".grok2", "sess-early", "2026-11-13T05:14:20Z"), (".grok2", "sess-late", "2026-11-13T05:40:00Z")],
            # the same request in another account's home is never searched
            "no session  ": [(".grok3", "sess-other", "2026-11-13T05:19:26.8Z")]}
        for expected, sessions in cases.items():
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                for home, sid, created in sessions:
                    write_session(Path(tmp) / home, sid, E_SEMIS1_REQUEST, created, calls)
                lost = xgrok_wave.lost_envelope_telemetry(job, str(Path(tmp) / ".grok2"), started, ended)
                self.assertEqual((lost["session_id"], lost["x_tool_calls"], lost["x_tool_calls_retried"]), (None, None, None))
                self.assertTrue(lost["session_source"].startswith(expected.strip()), lost["session_source"])

    def test_an_unreadable_transcript_leaves_the_counts_unknown_rather_than_losing_the_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".grok2"
            session = write_session(home, E_SEMIS1, E_SEMIS1_REQUEST, "2026-11-13T05:19:26.8Z")
            (session / "updates.jsonl").unlink()
            (session / "updates.jsonl").mkdir()  # matched, but its transcript cannot be read
            job = xgrok_wave.BriefJob("12-semis1", Path("12-semis1.md"), "harvest", E_SEMIS1_REQUEST)
            lost = xgrok_wave.lost_envelope_telemetry(job, str(home), datetime(2026, 11, 13, 5, 19, 26, tzinfo=timezone.utc),
                                                      datetime(2026, 11, 13, 5, 34, 27, tzinfo=timezone.utc))
            self.assertEqual((lost["session_id"], lost["x_tool_calls"]), (None, None))
            self.assertTrue(lost["session_source"].startswith("unreadable: IsADirectoryError"), lost["session_source"])

    def _hanging_launcher(self, root: Path, session_id: str) -> None:
        """A launcher that starts a session as Grok would (its prompt carries the composed request), runs two X calls
        with a stream break between them, then streams on until the runner stops it."""
        updates = "".join(json.dumps(event) + "\n" for event in (
            {"timestamp": 1794547213, "params": {"update": {"sessionUpdate": "tool_call_update", "toolCallId":
             "ctc_a_call-0", "status": "completed", "rawOutput": {"name": "x_keyword_search", "input": "{}"}}}},
            {"timestamp": 1794547504, "params": {"update": {"sessionUpdate": "retry_state", "reason": "stream broke"}}},
            {"timestamp": 1794547510, "params": {"update": {"sessionUpdate": "tool_call_update", "toolCallId":
             "ctc_b_call-0", "status": "completed", "rawOutput": {"name": "x_keyword_search", "input": "{}"}}}}))
        (root / "updates.jsonl").write_text(updates)
        launcher = root / "launcher"
        launcher.write_text(
            f"#!{sys.executable}\n"
            "import json, sys, time\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
            "from test_xgrok_wave import write_session\n"
            "root = Path(__file__).parent\n"
            f"write_session(root / 'grok', {session_id!r}, Path(sys.argv[-1]).read_text(), "
            "datetime.now(timezone.utc).isoformat(), (root / 'updates.jsonl').read_text())\n"
            "(root / 'started').touch()\n"
            "time.sleep(60)\n")
        launcher.chmod(0o755)

    def test_a_timed_out_lane_keeps_its_status_and_unknown_cost_but_counts_its_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._hanging_launcher(root, "sess-hang")
            (root / "lane.md").write_text("Lane: hang.\n")
            result = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), str(root / "lane.md"), "--xgrok-bin",
                 str(root / "launcher"), "--output-dir", str(root / "out"), "--grok-home", str(root / "grok"),
                 "--timeout", "2"], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stderr)
            worker = json.loads((root / "out" / "manifest.json").read_text())["workers"][0]
            self.assertEqual((worker["status"], worker["usage"], worker["raw_json_path"]), ("timeout", {}, None))
            self.assertEqual((worker["session_id"], worker["x_tool_calls"], worker["x_tool_calls_retried"]),
                             ("sess-hang", 2, 1))
            self.assertIsNone(worker["x_queries"])  # counted, not returned evidence: the lane has no packet
            self.assertIn("[lane] timeout: 2 X calls ran (1 in a request the CLI retried); stream broke at 05:25:04Z",
                          result.stderr)

    def test_cancellation_after_launch_counts_but_never_started_work_is_not_searched(self):
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._hanging_launcher(root, "sess-cancel")
            (root / "lane.md").write_text("Lane: cancel.\n")
            job = xgrok_wave.BriefJob("lane", root / "lane.md", "harvest", "Lane: cancel.\n")
            (root / "out").mkdir()
            stop = threading.Event()
            threading.Thread(target=lambda: (_wait_for(root / "started"), stop.set()), daemon=True).start()
            result = xgrok_wave.run_single_worker(job, root / "launcher", root / "out", 30, str(root / "grok"),
                                                  stop_requested=stop)
            self.assertEqual((result["status"], result["x_tool_calls"], result["session_id"]), ("cancelled", 2, "sess-cancel"))
            # never started: a matching session already on disk is not this lane's
            result = xgrok_wave.run_single_worker(job, root / "launcher", root / "out", 30, str(root / "grok"),
                                                  stop_requested=stop)
            self.assertEqual((result["status"], result["launched_at"]), ("cancelled", None))
            self.assertNotIn("session_id", result)
            self.assertNotIn("x_tool_calls", result)


def _wait_for(path: Path, seconds: float = 20) -> None:
    deadline = time.monotonic() + seconds
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError(f"{path} never appeared")
        time.sleep(0.05)


class WaveOutcomeCliTests(unittest.TestCase):
    def test_probe_dispatches_only_on_a_recorded_return_including_empty(self):
        for outcome in ("returned", "error", "unknown"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_transcript(root / "grok", "sess-transport", ["x_keyword_search"])
                transcript = next((root / "grok" / "sessions").glob("*/sess-transport/updates.jsonl"))
                transcript.write_text(json.dumps({"timestamp": 1790721371, "params": {"update": {
                    "sessionUpdate": "tool_call_update", "toolCallId": "call-0", "status": "completed",
                    "rawOutput": {"name": "x_keyword_search", "input": json.dumps({"query": "from:Reuters"})}}}}) + "\n")
                write_transcript(root / "grok", "sess-a", ["x_keyword_search"])
                answer = json.dumps({"outcome": outcome, "count": 0, "error": "429/1015" if outcome == "error" else None})
                self._launcher(root, f"print(json.dumps({{'text': {answer!r} if name == 'transport' else 'packet', "
                                     "'sessionId': 'sess-' + name}))\n")
                dry = self._run(root, ["a"], "--transport-probe", "--dry-run")
                self.assertEqual(dry.returncode, 0, dry.stderr)
                self.assertFalse((root / "native-probe.json").exists())
                self.assertFalse((root / "out" / "launched.json").exists())
                result = self._run(root, ["a"], "--transport-probe")
                record = json.loads((root / "native-probe.json").read_text())
                self.assertEqual(record["outcome"], outcome)
                self.assertEqual((root / "launch.log").read_text().split(),
                                 ["transport", "a"] if outcome == "returned" else ["transport"])
                self.assertEqual((root / "out" / "launched.json").exists(), outcome == "returned")
                self.assertEqual((root / "out" / "NOT-LAUNCHED.txt").exists(), outcome != "returned")
                self.assertEqual(result.returncode, 0 if outcome == "returned" else 3, result.stderr)
                if outcome == "returned":
                    self._run(root, ["a"], "--transport-probe", "--output-dir", str(root / "out2"))
                    self.assertEqual((root / "launch.log").read_text().split(), ["transport", "a", "a"])

    def _probe_launcher(self, root: Path, answer: str) -> None:
        """A launcher whose Nth transport attempt reports session sess-transport-N; it logs each job's effort."""
        self._launcher(root, "import os\n"
                             "with (root / 'effort.log').open('a') as f: "
                             "f.write(f\"{name} {os.environ.get('XGROK_EFFORT', 'default')}\\n\")\n"
                             "attempt = (root / 'launch.log').read_text().split().count('transport')\n"
                             f"print(json.dumps({{'text': {answer!r} if name == 'transport' else 'packet', "
                             "'sessionId': f'sess-transport-{attempt}' if name == 'transport' else 'sess-' + name}))\n")

    def _probe_transcript(self, root: Path, attempt: int, searched: bool) -> None:
        write_transcript(root / "grok", f"sess-transport-{attempt}", ["x_keyword_search"] if searched else [])
        if searched:
            transcript = next((root / "grok" / "sessions").glob(f"*/sess-transport-{attempt}/updates.jsonl"))
            transcript.write_text(json.dumps({"timestamp": 1790721371, "params": {"update": {
                "sessionUpdate": "tool_call_update", "toolCallId": "call-0", "status": "completed",
                "rawOutput": {"name": "x_keyword_search", "input": json.dumps({"query": "from:Reuters"})}}}}) + "\n")

    def test_probe_survives_a_worker_that_skipped_its_search_or_wrote_a_preamble(self):
        # Workers have answered the probe without searching, and often put a sentence before its JSON.
        answer = 'I\'ll run the single transport check now.{"outcome":"returned","count":1,"error":null}'
        for searched, expected in (((False, True), "returned"), ((False, False, False), "unknown")):
            with self.subTest(searched=searched), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for attempt, did_search in enumerate(searched, 1):
                    self._probe_transcript(root, attempt, did_search)
                write_transcript(root / "grok", "sess-a", ["x_keyword_search"])
                self._probe_launcher(root, answer)
                result = self._run(root, ["a"], "--transport-probe")
                record = json.loads((root / "native-probe.json").read_text())
                self.assertEqual((record["outcome"], record["attempts"]), (expected, len(searched)))
                # A's probe (11-12) said "matched to one executed keyword search" beside 0 calls
                self.assertEqual(record["outcome_source"], "worker-reported, matched to one executed keyword search"
                                 if expected == "returned" else "unmatched: no X call executed in 3 attempt(s)")
                launched = ["transport"] * len(searched) + (["a"] if expected == "returned" else [])
                self.assertEqual((root / "launch.log").read_text().split(), launched)
                self.assertEqual(result.returncode, 0 if expected == "returned" else 3, result.stderr)
                efforts = dict(line.split() for line in (root / "effort.log").read_text().splitlines())
                self.assertEqual((efforts["transport"], efforts.get("a", "default")), ("high", "default"))

    def _launcher(self, root: Path, body: str) -> Path:
        launcher = root / "launcher"
        launcher.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\nfrom pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "name = Path(sys.argv[-1]).stem\n"
            "with (root / 'launch.log').open('a') as f: f.write(name + '\\n')\n" + body
        )
        launcher.chmod(0o755)
        return launcher

    def _run(self, root: Path, briefs: list[str], *extra: str) -> subprocess.CompletedProcess:
        paths = []
        for name in briefs:
            (root / f"{name}.md").write_text("Objective: bounded worker.\n")
            paths.append(str(root / f"{name}.md"))
        return subprocess.run(
            [sys.executable, str(Path(xgrok_wave.__file__)), *paths, "--xgrok-bin", str(root / "launcher"),
             "--output-dir", str(root / "out"), "--grok-home", str(root / "grok"), "--max-workers", "1", *extra],
            capture_output=True, text=True, timeout=20,
        )

    def test_a_lane_that_never_searched_fails_and_keeps_its_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_transcript(root / "grok", "sess-searched", ["x_keyword_search"])
            write_transcript(root / "grok-xworker", "sess-idle", [])
            self._launcher(root, "print(json.dumps({'text': 'packet ' + name, 'sessionId': 'sess-' + name}))\n")
            result = self._run(root, ["searched", "idle"], "--abort-after", "0")
            self.assertEqual(result.returncode, 1, result.stderr)
            workers = {w["name"]: w for w in json.loads((root / "out" / "manifest.json").read_text())["workers"]}
            self.assertEqual((workers["searched"]["status"], workers["searched"]["x_tool_calls"]), ("success", 1))
            self.assertEqual((workers["idle"]["status"], workers["idle"]["x_tool_calls"]), ("failed", 0))
            self.assertIn("0 native X tool calls", workers["idle"]["error"])
            self.assertEqual((root / "out" / "idle-packet.md").read_text(), "packet idle")

    def test_each_lane_records_its_result_before_the_wave_ends(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_transcript(root / "grok", "sess-a", ["x_keyword_search"])
            # b launches after a (one worker) and records whether a's result was already on disk.
            self._launcher(root, "if name == 'b':\n"
                                 "    (root / 'seen').write_text(str((root / 'out' / 'a-result.json').is_file()))\n"
                                 "print(json.dumps({'text': 'ok', 'sessionId': 'sess-' + name}))\n")
            result = self._run(root, ["a", "b"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "seen").read_text(), "True")
            workers = {w["name"]: w for w in json.loads((root / "out" / "manifest.json").read_text())["workers"]}
            self.assertEqual(json.loads((root / "out" / "a-result.json").read_text()), workers["a"])

    def test_a_retried_requests_calls_are_named_in_the_manifest_and_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_retried_transcript(root / "grok", "sess-retried")
            self._launcher(root, "print(json.dumps({'text': 'ok', 'sessionId': 'sess-' + name}))\n")
            result = self._run(root, ["retried"])
            self.assertEqual(result.returncode, 0, result.stderr)
            worker = json.loads((root / "out" / "manifest.json").read_text())["workers"][0]
            self.assertEqual((worker["x_tool_calls"], worker["x_tool_calls_retried"]), (4, 2))
            self.assertIn("X calls: 4, 2 of them in a request the CLI retried", result.stderr)

    def test_unknown_transcript_keeps_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._launcher(root, "print(json.dumps({'text': 'ok', 'sessionId': 'sess-unknown'}))\n")
            result = self._run(root, ["a"])
            self.assertEqual(result.returncode, 0, result.stderr)
            worker = json.loads((root / "out" / "manifest.json").read_text())["workers"][0]
            self.assertEqual(worker["status"], "success")
            self.assertIsNone(worker["x_tool_calls"])

    def test_first_two_failures_stop_the_wave(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._launcher(root, "print('You are sending requests too quickly', file=sys.stderr)\nsys.exit(1)\n")
            result = self._run(root, ["a", "b", "c"])
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual((root / "launch.log").read_text().split(), ["a", "b"])
            manifest = json.loads((root / "out" / "manifest.json").read_text())
            self.assertIn("first 2 lanes to finish all failed", manifest["aborted"])
            self.assertEqual([w["status"] for w in manifest["workers"]], ["failed", "failed", "cancelled"])

    def test_abort_after_zero_runs_every_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._launcher(root, "sys.exit(1)\n")
            result = self._run(root, ["a", "b", "c"], "--abort-after", "0")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual((root / "launch.log").read_text().split(), ["a", "b", "c"])
            self.assertIsNone(json.loads((root / "out" / "manifest.json").read_text())["aborted"])

    def test_one_early_failure_does_not_stop_the_wave(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._launcher(root, "if name == 'a':\n    sys.exit(1)\nprint(json.dumps({'text': 'ok'}))\n")
            result = self._run(root, ["a", "b", "c"])
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual((root / "launch.log").read_text().split(), ["a", "b", "c"])
            manifest = json.loads((root / "out" / "manifest.json").read_text())
            self.assertIsNone(manifest["aborted"])
            self.assertEqual([w["status"] for w in manifest["workers"]], ["failed", "success", "success"])


ROSTER = {
    "chabot_ben": xgrok_roster.RosterEntry("chabot_ben", "credible-sources:Rates", date(2026, 9, 21), ""),
    "rory_johnston": xgrok_roster.RosterEntry("Rory_Johnston", "credible-sources:Energy", None, ""),
    "dampedspring": xgrok_roster.RosterEntry("dampedspring", "credible-sources:Core", date(2026, 7, 1), ""),
}


class PreflightCliTests(unittest.TestCase):
    def test_interrupt_stops_active_worker_and_skips_queued_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            launcher = root / "launcher"
            launcher.write_text(
                f"#!{sys.executable}\n"
                "import os, signal, time\nfrom pathlib import Path\n"
                "root = Path(__file__).parent\n"
                "signal.signal(signal.SIGTERM, lambda *_: ((root / 'stopped').touch(), exit(0)))\n"
                "with (root / 'started').open('a') as f: f.write(str(os.getpid()) + '\\n')\n"
                "time.sleep(30)\n"
            )
            launcher.chmod(0o755)
            briefs = [root / f"brief-{i}.md" for i in range(2)]
            for brief in briefs:
                brief.write_text("Objective: bounded worker.\n")
            process = subprocess.Popen(
                [sys.executable, str(Path(xgrok_wave.__file__)), *map(str, briefs),
                 "--xgrok-bin", str(launcher), "--output-dir", str(root / "out"), "--max-workers", "1"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                deadline = time.monotonic() + 5
                while not (root / "started").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((root / "started").exists(), "fixture worker never became ready")
                process.send_signal(signal.SIGINT)
                _, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 130, stderr)
                self.assertTrue((root / "stopped").exists())
                self.assertEqual(len((root / "started").read_text().splitlines()), 1)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
                if (root / "started").exists():
                    for pid in (root / "started").read_text().splitlines():
                        try:
                            os.killpg(int(pid), signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    def test_timeout_stops_launcher_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "child.py").write_text(
                "import signal, time\nfrom pathlib import Path\n"
                "signal.signal(signal.SIGTERM, lambda *_: (Path('stopped').touch(), exit(0)))\n"
                "Path('ready').touch()\ntime.sleep(30)\n"
            )
            launcher = root / "launcher"
            launcher.write_text(
                f"#!{sys.executable}\n"
                "import subprocess, sys\nfrom pathlib import Path\n"
                "child = subprocess.Popen([sys.executable, 'child.py'], cwd=Path(__file__).parent)\n"
                "Path(__file__).with_name('child.pid').write_text(str(child.pid))\nchild.wait()\n"
            )
            launcher.chmod(0o755)
            brief = root / "brief.md"
            brief.write_text("Objective: bounded worker.\n")
            try:
                result = subprocess.run(
                    [sys.executable, str(Path(xgrok_wave.__file__)), str(brief),
                     "--xgrok-bin", str(launcher), "--output-dir", str(root / "out"), "--timeout", "0.5"],
                    capture_output=True, text=True, timeout=6,
                )
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertTrue((root / "ready").exists(), "fixture child never became ready")
                self.assertTrue((root / "stopped").exists(), "timed-out launcher left its child running")
            finally:
                if (root / "child.pid").exists():
                    try:
                        os.kill(int((root / "child.pid").read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_timeout_default_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "brief.md"
            brief.write_text("Objective: bounded retrieval.\n")
            command = [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--dry-run"]
            default = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertIn("Timeout: 900.0s", default.stdout)
            override = subprocess.run(command + ["--timeout", "120"], capture_output=True, text=True, check=True)
            self.assertIn("Timeout: 120.0s", override.stdout)

    def test_roster_reminder_and_probe_target_only_used_stale_handles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            roster = root / "roster.tsv"
            xgrok_roster.save_roster(roster, ROSTER)
            brief = root / "brief.md"
            brief.write_text("Roster: @chabot_ben, @Rory_Johnston\n")
            command = [sys.executable, str(Path(xgrok_roster.__file__)), "--roster", str(roster),
                       "--today", "2026-09-22"]
            checked = subprocess.run(command + ["check", str(brief)], capture_output=True, text=True, check=True)
            self.assertIn(
                "STALE (>30d): 2 roster (1 unverified), 1 used in these briefs (1 unverified); --list-stale names them",
                checked.stdout,
            )
            self.assertNotIn("USED STALE: Rory_Johnston", checked.stdout)
            listed = subprocess.run(command + ["check", str(brief), "--list-stale"],
                                    capture_output=True, text=True, check=True)
            self.assertIn("USED STALE: Rory_Johnston (never verified)", listed.stdout)
            self.assertNotIn("USED STALE: dampedspring", listed.stdout)
            # Item 29: labeled off-roster handles collapse to 1 compact line unless --verbose; UNLABELED/PASTE stay verbatim.
            labeled_brief = root / "labeled.md"
            labeled_brief.write_text("Labels: @OffOne (context); @OffTwo (lead)\nAnchors: @OffOne @OffTwo\n")
            compact = subprocess.run(command + ["check", str(labeled_brief)], capture_output=True, text=True, check=True)
            self.assertIn("OFF-ROSTER (labeled context): 2 handle(s) across 1 brief(s) (--verbose lists them)", compact.stdout)
            self.assertNotIn("OffOne", compact.stdout)
            verbose = subprocess.run(command + ["check", str(labeled_brief), "--verbose"], capture_output=True, text=True, check=True)
            self.assertIn("OFF-ROSTER (labeled context): OffOne", verbose.stdout)
            self.assertIn("OFF-ROSTER (labeled context): OffTwo", verbose.stdout)
            self.assertIn("STALE (no verified date or older than 30d):", verbose.stdout)
            out = root / "probes"
            subprocess.run(command + ["probe-brief", "--briefs", str(brief), "--only-stale", "30", "--out", str(out)],
                           capture_output=True, text=True, check=True)
            probes = list(out.glob("*.md"))
            self.assertEqual(len(probes), 1)
            text = probes[0].read_text()
            self.assertIn("- @Rory_Johnston", text)
            self.assertNotIn("- @chabot_ben", text)
            self.assertNotIn("- @dampedspring", text)


class RosterCheckTests(unittest.TestCase):
    def test_typo_handle_is_unlabeled_with_near_match(self):
        briefs = {"e1": "Roster: @dampedspring, @ChabotBen (Constan counterparty).\nQuery from:RoryJohnston Latest."}
        report = xgrok_roster.check_briefs(briefs, ROSTER, today=date(2026, 9, 22))
        by_handle = {item.handle: item for item in report.off_roster}
        self.assertEqual(set(by_handle), {"ChabotBen", "RoryJohnston"})
        self.assertEqual(by_handle["ChabotBen"].near_matches, ("chabot_ben",))
        self.assertFalse(by_handle["ChabotBen"].labeled)
        self.assertEqual(by_handle["RoryJohnston"].near_matches, ("Rory_Johnston",))
        self.assertEqual(len(report.unlabeled), 2)

    def test_context_label_after_handle_marks_it_labeled(self):
        briefs = {"a1": "- Rates: @dampedspring, @GameIsAfoot (context; from morning packet), @LiveSquawk (Tier C relay, lead only)."}
        report = xgrok_roster.check_briefs(briefs, ROSTER, today=date(2026, 9, 22))
        self.assertEqual({item.handle for item in report.off_roster}, {"GameIsAfoot", "LiveSquawk"})
        self.assertTrue(all(item.labeled for item in report.off_roster))
        self.assertEqual(report.unlabeled, ())

    def test_label_belongs_to_the_nearest_handle_only(self):
        briefs = {"b": "@Alpha, @Beta (context)"}
        report = xgrok_roster.check_briefs(briefs, ROSTER, today=date(2026, 9, 22))
        by_handle = {item.handle: item.labeled for item in report.off_roster}
        self.assertEqual(by_handle, {"Alpha": False, "Beta": True})

    def test_group_header_labels_its_batch_until_the_next_semicolon(self):
        briefs = {"g": "Anchors: @dampedspring ; news relays (context): @Alpha @Beta ; @Gamma. "
                       "Freight analysts as context: @Delta. Roster: @Epsilon"}
        report = xgrok_roster.check_briefs(briefs, ROSTER, today=date(2026, 9, 22))
        by_handle = {item.handle: item.labeled for item in report.off_roster}
        self.assertEqual(by_handle, {"Alpha": True, "Beta": True, "Gamma": False, "Delta": True, "Epsilon": False})

    def test_a_held_receipts_line_is_cited_context_but_a_search_stays_strict(self):
        # 10-13, 10-14: follow-up briefs were refused for handles that appeared only on their held-receipts line.
        held = "Held receipts (cite by ID, do not re-fetch): @Alpha 2110053363970900357 (shorts); @Beta 2110081442579623979.\n"
        report = xgrok_roster.check_briefs({"f1": held + "Anchors: @Gamma\nCalls: from:Beta since:2026-10-14"}, ROSTER,
                                           today=date(2026, 9, 22))
        self.assertEqual({item.handle: item.labeled for item in report.off_roster},
                         {"Alpha": True, "Beta": False, "Gamma": False})
        beta = next(item for item in report.off_roster if item.handle == "Beta")
        self.assertIn("labeled on one line of f1 but not where it is searched", beta.hints[0])

    def test_a_labels_line_ends_at_the_next_field_and_an_unlabeled_name_on_it_is_explained(self):
        # 10-11: "Labels: @policytensor (off-list context). Held quote: ..." labeled nothing, and the refusal said not why.
        briefs = {"e": "Labels: @Alpha (off-list context). Held quote: (cite by ID) @Beta 2108507403054731504.\n"
                       "Labels: @Gamma @Delta (off-list context)\n"
                       "Calls: from:Alpha OR from:Gamma OR from:Delta since:2026-10-11"}
        report = xgrok_roster.check_briefs(briefs, ROSTER, today=date(2026, 9, 22))
        self.assertEqual({item.handle: item.labeled for item in report.off_roster},
                         {"Alpha": True, "Beta": True, "Gamma": False, "Delta": True})
        text = xgrok_roster.format_check_report(report, 30)
        self.assertIn("Gamma  in e  (Labels line e:2 gives it no context label right after it)", text)

    def test_stale_lists_unverified_and_old_entries(self):
        report = xgrok_roster.check_briefs({}, ROSTER, today=date(2026, 9, 22), stale_days=30)
        self.assertEqual([entry.handle for entry in report.stale], ["dampedspring", "Rory_Johnston"])

    def test_bare_handles_without_at_or_from_are_not_seen(self):
        report = xgrok_roster.check_briefs({"a1": "Roster: ChabotBen, dampedspring"}, ROSTER, today=date(2026, 9, 22))
        self.assertEqual(report.off_roster, ())


class RosterProbeAndVerifyTests(unittest.TestCase):
    def test_probe_briefs_shard_and_probe_each_handle_once(self):
        briefs = xgrok_roster.probe_briefs(ROSTER, today=date(2026, 9, 22), shard_size=2, since_days=30)
        self.assertEqual([name for name, _ in briefs], ["roster-probe-01", "roster-probe-02"])
        first = briefs[0][1]
        self.assertIn("# mode: harvest", first)
        self.assertIn("since:2026-08-23", first)
        self.assertIn("- @chabot_ben\n- @dampedspring", first)
        self.assertIn("at most 4 native X calls", first)
        self.assertIn("- @Rory_Johnston", briefs[1][1])

    def test_probe_only_stale_skips_recently_verified(self):
        briefs = xgrok_roster.probe_briefs(ROSTER, today=date(2026, 9, 22), shard_size=10, stale_days=30)
        self.assertEqual(len(briefs), 1)
        self.assertNotIn("@chabot_ben", briefs[0][1])
        self.assertIn("@dampedspring", briefs[0][1])

    def test_record_verified_updates_only_newer_dates_and_reports_unknown(self):
        updated, unknown = xgrok_roster.record_verified(
            ROSTER, {"Rory_Johnston", "chabot_ben", "nobody"}, date(2026, 9, 1)
        )
        self.assertEqual(unknown, ["nobody"])
        self.assertEqual(updated["rory_johnston"].verified, date(2026, 9, 1))
        self.assertEqual(updated["chabot_ben"].verified, date(2026, 9, 21))

    def test_handles_from_packets_uses_status_urls(self):
        packets = ["see https://x.com/dampedspring/status/2102059642872332449 and @mention only"]
        self.assertEqual(xgrok_roster.handles_from_packets(packets), {"dampedspring"})

    def test_roster_round_trip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roster.tsv"
            xgrok_roster.save_roster(path, ROSTER)
            loaded = xgrok_roster.load_roster(path)
            self.assertEqual(loaded, ROSTER)
            self.assertEqual(path.read_text().splitlines()[0], "handle\tregistries\tverified\tnote")

    def test_bad_header_fails_loudly(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roster.tsv"
            path.write_text("handle\tverified\nfoo\t\n")
            with self.assertRaises(ValueError):
                xgrok_roster.load_roster(path)


def _snowflake_for(moment: datetime) -> str:
    ms = int(moment.timestamp() * 1000) - xgrok_wave.TWITTER_EPOCH_MS
    return str(ms << 22)


class BoundPreflightAndEpochAuditTests(unittest.TestCase):
    LAUNCH = datetime(2026, 11, 23, 7, 10, 0, tzinfo=timezone.utc)
    WINDOW = {
        "since": "2026-11-21T16:10:00-08:00",  # 2026-11-22T00:10:00Z = 1795306200
        "until": "2026-11-22T23:09:36-08:00",  # 2026-11-23T07:09:36Z = 1795417776
        "context_since": "2026-10-29T00:00:00-07:00",
    }

    def test_epoch_bounds_audit_in_bounds_and_classify_bound_form(self):
        cases = [
            ("(from:fejau_inc OR from:INArteCarloDoss) since_time:1795309800 until_time:1795417776",
             "within-approved-query-bounds", "epoch", "1795309800", "1795417776"),
            ("from:alpha since_time:1795000000 until_time:1795417776",
             "context-lookback", "epoch", "1795000000", "1795417776"),
            ("from:alpha since_time:1795309800 until_time:1795420000",
             "future", "epoch", "1795309800", "1795420000"),
            ("from:alpha since_time:1795417776 until_time:1795309800",
             "reversed", "epoch", "1795417776", "1795309800"),
            ("from:alpha since_time:1795309800 until_time:1795417799",
             "widened", "epoch", "1795309800", "1795417799"),
            ("from:alpha since_time:badepoch until_time:1795417776",
             "unavailable-bound-clock", "mixed", "badepoch", "1795417776"),
            ("from:a OR from:b since_time:1795309800 until_time:1795417776",
             "or-scope-unbounded", "epoch", "1795309800", "1795417776"),
            ("from:alpha since:2026-11-22_01:10:00_UTC until:2026-11-23_07:09:36_UTC",
             "within-approved-query-bounds", "utc", "2026-11-22_01:10:00_UTC", "2026-11-23_07:09:36_UTC"),
            ("from:alpha since:2026-11-22_01:10:00_PST until:2026-11-22_23:09:36_PST",
             "within-approved-query-bounds", "pt", "2026-11-22_01:10:00_PST", "2026-11-22_23:09:36_PST"),
            ("from:alpha within_time:24h",
             "unbounded", "within-time", None, None),
            ("from:alpha",
             "unbounded", "unbounded", None, None),
        ]
        for query, expected_ws, expected_form, exp_s, exp_u in cases:
            with self.subTest(query=query):
                audited = xgrok_wave.audit_query_clocks([{"arguments": {"query": query}}], self.WINDOW, self.LAUNCH)
                row = audited[0]
                self.assertEqual(row["window_status"], expected_ws)
                self.assertEqual(row["bound_form"], expected_form)
                self.assertEqual(row["sent_since"], exp_s)
                self.assertEqual(row["sent_until"], exp_u)
        self.assertEqual(xgrok_wave.classify_bound_form(None), "unavailable")
        self.assertEqual(xgrok_wave.classify_bound_form("since:2026-11-22 until:2026-11-23"), "date-only")
        self.assertEqual(xgrok_wave.classify_bound_form("since:2026-11-22T01:00:00+00:00"), "iso")

    def test_pst_pdt_bounds_are_refused_and_near_present_string_upper_bound_warns(self):
        launch = datetime(2026, 11, 23, 7, 10, 0, tzinfo=timezone.utc)
        pst_job = xgrok_wave.BriefJob(
            "bad", Path("bad.md"), "harvest",
            "Query: `from:alpha since:2026-11-22_12:00:00_PST until:2026-11-22_23:00:00_PST`\n",
        )
        errors, _ = xgrok_wave.validate_jobs([pst_job], True, launch=launch)
        self.assertTrue(any("_PST/_PDT query bound refused" in e for e in errors), errors)

        near_utc = xgrok_wave.BriefJob(
            "near", Path("near.md"), "harvest",
            "Query: `from:alpha since:2026-11-23_06:00:00_UTC until:2026-11-23_06:50:00_UTC`\n",
        )
        errors, warnings = xgrok_wave.validate_jobs([near_utc], True, launch=launch)
        self.assertEqual(errors, [])
        self.assertTrue(any("within 60 min of launch" in w for w in warnings), warnings)

        # Epoch upper bound within 60m and >60m string upper bound do not trigger the string near-present warning.
        epoch_near = xgrok_wave.BriefJob(
            "ep", Path("ep.md"), "harvest",
            f"Query: `from:alpha since_time:{int(launch.timestamp()) - 1800} until_time:{int(launch.timestamp()) - 60}`\n",
        )
        old_utc = xgrok_wave.BriefJob(
            "old", Path("old.md"), "harvest",
            "Query: `from:alpha since:2026-11-22_12:00:00_UTC until:2026-11-23_05:00:00_UTC`\n",
        )
        errors, warnings = xgrok_wave.validate_jobs([epoch_near, old_utc], True, launch=launch)
        self.assertEqual((errors, warnings), ([], []))

    def test_bound_form_summary_lists_per_call_forms_and_ignores_prose_slashes_in_common_tail(self):
        tail = (
            "# fresh_since: 2026-11-22T00:00:00+00:00\n"
            "# fresh_until: 2026-11-23T07:00:00+00:00\n"
            "Exact query bounds: since:2026-11-23_01:00:00_UTC for the newest slice; "
            "until:2026-11-23_07:00:00_UTC as the upper bound. "
            "Never write _PST or _PDT query bounds (use _UTC or since_time:/until_time: Unix epochs). "
            "In-lane circuit breaker: no since:/until:/since_time:/until_time:).\n"
        )
        b_utc = xgrok_wave.BriefJob(
            "utc-lane", Path("u.md"), "harvest",
            xgrok_wave.compose_brief("1. `from:a since:2026-11-23_01:00:00_UTC until:2026-11-23_07:00:00_UTC`\n", tail),
            raw_text="1. `from:a since:2026-11-23_01:00:00_UTC until:2026-11-23_07:00:00_UTC`\n",
        )
        b_ep = xgrok_wave.BriefJob(
            "ep-lane", Path("e.md"), "harvest",
            xgrok_wave.compose_brief("1. `from:b since_time:1795309800 until_time:1795417776`\n", tail),
            raw_text="1. `from:b since_time:1795309800 until_time:1795417776`\n",
        )
        utc_info = xgrok_wave.brief_bound_forms(b_utc)
        self.assertEqual(utc_info["tail"], "utc")
        self.assertEqual(utc_info["forms"], ["utc"])
        self.assertFalse(utc_info["mixed"])
        ep_info = xgrok_wave.brief_bound_forms(b_ep)
        self.assertEqual(ep_info["calls"], ["epoch"])
        self.assertTrue(ep_info["mixed"])
        summary = "\n".join(xgrok_wave.format_bound_form_summary([b_utc, b_ep]))
        self.assertIn("WAVE MIXED: epoch, utc", summary)
        self.assertIn("utc-lane: call 1=utc; tail=utc", summary)
        self.assertIn("ep-lane: call 1=epoch; tail=utc [MIXED]", summary)

    def test_item22_brief_harvest_metadata_deterministically_overrides_common_tail(self):
        launch = datetime(2026, 11, 23, 7, 10, 0, tzinfo=timezone.utc)
        tail = (
            "Output orientation: participant-native.\n"
            "# fresh_since: 2026-11-21T20:00:00-08:00\n"
            "# fresh_until: 2026-11-22T23:09:00-08:00\n"
            "# context_since: 2026-10-29T00:00:00-07:00\n"
            "Exact query bounds: since:2026-11-22_04:00:00_UTC; until:2026-11-23_07:09:00_UTC.\n"
        )
        # Brief declares 30-day harvest window starting BEFORE tail's context_since and ending 1m before tail's fresh_until.
        brief_with_ctx = (
            "# mode: harvest\n# effort: medium\n"
            "# fresh_since: 2026-10-23T00:00:00-07:00\n"
            "# fresh_until: 2026-11-22T23:08:00-08:00\n"
            "# context_since: 2026-09-23T00:00:00-07:00\n"
            "Objective: candidate discovery.\n"
        )
        composed = xgrok_wave.compose_brief(brief_with_ctx, tail)
        win = xgrok_wave.approved_window(composed, launch, brief_text=brief_with_ctx)
        self.assertEqual(win, {
            "since": "2026-10-23T00:00:00-07:00",
            "until": "2026-11-22T23:08:00-08:00",
            "context_since": "2026-09-23T00:00:00-07:00",
        })
        # Also works without raw_text / brief_text, and when brief omits context_since (no reversed-window crash).
        brief_no_ctx = (
            "# mode: harvest\n# effort: medium\n"
            "# fresh_since: 2026-10-23T00:00:00-07:00\n"
            "# fresh_until: 2026-11-22T23:08:00-08:00\n"
            "Objective: candidate discovery.\n"
        )
        composed_no_ctx = xgrok_wave.compose_brief(brief_no_ctx, tail)
        win2 = xgrok_wave.approved_window(composed_no_ctx, launch)
        self.assertEqual(win2["since"], "2026-10-23T00:00:00-07:00")
        self.assertEqual(win2["until"], "2026-11-22T23:08:00-08:00")
        self.assertIsNone(win2["context_since"])
        # Validate job passes cleanly (tail's later until: does not falsely widen brief's fresh_until).
        job = xgrok_wave.BriefJob("cand", Path("cand.md"), "harvest", composed, effort="medium", raw_text=brief_with_ctx)
        errors, warnings = xgrok_wave.validate_jobs([job], True, launch=launch)
        self.assertEqual((errors, warnings), ([], []))
        # YAML frontmatter harvest window + common tail comments also splits cleanly without raw_text.
        fm_brief = (
            "---\nmode: harvest\nfresh_since: 2026-10-23T00:00:00-07:00\n"
            "fresh_until: 2026-11-22T23:08:00-08:00\n---\nObjective: frontmatter cand.\n"
        )
        win3 = xgrok_wave.approved_window(xgrok_wave.compose_brief(fm_brief, tail), launch)
        self.assertEqual(win3["since"], "2026-10-23T00:00:00-07:00")
        self.assertIsNone(win3["context_since"])


class PerAccountProbeAndCanaryTests(unittest.TestCase):
    def _write_fake_transport(
        self,
        root: Path,
        *,
        transport_outcomes: dict[str, dict],
        canary_hit: bool = True,
        canary_author_query_ok: bool = True,
    ) -> Path:
        """Fake launcher that reads GROK_HOME to decide per-account transport & bound-canary behavior."""
        cfg = {
            "transport": transport_outcomes,
            "canary_hit": canary_hit,
            "canary_author_query_ok": canary_author_query_ok,
        }
        (root / "fake_cfg.json").write_text(json.dumps(cfg))
        launcher = root / "launcher"
        launcher.write_text(
            f"#!{sys.executable}\n"
            "import json, os, re, sys\nfrom pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "cfg = json.loads((root / 'fake_cfg.json').read_text())\n"
            "grok_home = Path(sys.argv[sys.argv.index('--grok-home') + 1]) if '--grok-home' in sys.argv else Path(os.environ['GROK_HOME'])\n"
            "acct = grok_home.name\n"
            "brief_path = Path(sys.argv[-1])\n"
            "name = brief_path.stem\n"
            "brief_text = brief_path.read_text()\n"
            "with (root / 'launch.log').open('a') as f: f.write(f'{acct}:{name}\\n')\n"
            "def record_tx(sid, query):\n"
            "    sdir = grok_home / 'sessions' / 'w' / sid\n"
            "    sdir.mkdir(parents=True, exist_ok=True)\n"
            "    ev = {'timestamp': 1795417800, 'params': {'update': {'sessionUpdate': 'tool_call_update', "
            "'toolCallId': 'call-0', 'status': 'completed', "
            "'rawOutput': {'name': 'x_keyword_search', 'input': json.dumps({'query': query})}}}}\n"
            "    (sdir / 'updates.jsonl').write_text(json.dumps(ev) + '\\n')\n"
            "if name == 'transport':\n"
            "    ans = cfg['transport'][acct]\n"
            "    sid = f'sess-transport-{acct.lstrip(\".\")}'\n"
            "    record_tx(sid, 'from:Reuters')\n"
            "    print(json.dumps({'text': json.dumps(ans), 'sessionId': sid, 'total_cost_usd': 0.02}))\n"
            "elif name == 'bound-canary':\n"
            "    m = re.search(r'exact query: \"([^\"]+)\"', brief_text)\n"
            "    q = m.group(1) if m else ''\n"
            "    m_pid = re.search(r'in-window post (\\d+)', brief_text)\n"
            "    pid = m_pid.group(1) if m_pid else ''\n"
            "    sid = f'sess-canary-{acct.lstrip(\".\")}'\n"
            "    record_tx(sid, q if cfg['canary_author_query_ok'] else 'from:wrong')\n"
            "    hit = cfg['canary_hit']\n"
            "    ans = {'outcome': 'returned', 'count': 1 if hit else 0, 'matched_post_id': hit, "
            "'post_ids': [pid] if hit else [], 'error': None}\n"
            "    print(json.dumps({'text': json.dumps(ans), 'sessionId': sid, 'total_cost_usd': 0.02}))\n"
            "else:\n"
            "    sid = f'sess-{acct.lstrip(\".\")}-{name}'\n"
            "    record_tx(sid, 'from:alpha')\n"
            "    print(json.dumps({'text': 'packet ' + name, 'sessionId': sid, 'total_cost_usd': 0.05}))\n"
        )
        launcher.chmod(0o755)
        return launcher

    def test_per_account_probe_keys_accounts_and_failed_second_account_refuses_without_switching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid = _snowflake_for(datetime.now(timezone.utc) - timedelta(hours=2))
            launcher = self._write_fake_transport(
                root,
                transport_outcomes={
                    ".grok": {"outcome": "returned", "count": 1, "post_id": pid, "error": None},
                    ".grok2": {"outcome": "returned", "count": 1, "post_id": pid, "error": None},
                    ".grok3": {"outcome": "error", "count": 0, "post_id": None, "error": "429/1015"},
                },
            )
            brief = root / "lane.md"
            brief.write_text("Objective: unbounded test.\n")
            base = [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--xgrok-bin", str(launcher),
                    "--transport-probe", "--max-workers", "1"]

            # 1) First healthy account (.grok) probes once and launches; top-level legacy keys come from .grok.
            r1 = subprocess.run([*base, "--grok-home", str(root / ".grok"), "--output-dir", str(root / "w1")],
                                capture_output=True, text=True, timeout=20)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            doc = json.loads((root / "native-probe.json").read_text())
            self.assertEqual(doc["account"], ".grok")
            self.assertEqual(doc["outcome"], "returned")
            self.assertIn(".grok", doc["accounts"])

            # 2) Second healthy account (.grok2) probes once and launches; top-level legacy keys stay .grok.
            r2 = subprocess.run([*base, "--grok-home", str(root / ".grok2"), "--output-dir", str(root / "w2")],
                                capture_output=True, text=True, timeout=20)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            doc = json.loads((root / "native-probe.json").read_text())
            self.assertEqual(doc["account"], ".grok")
            self.assertEqual(doc["accounts"][".grok2"]["outcome"], "returned")

            # 3) Failed third account (.grok3) refuses without switching accounts and launches 0 lanes.
            r3 = subprocess.run([*base, "--grok-home", str(root / ".grok3"), "--output-dir", str(root / "w3")],
                                capture_output=True, text=True, timeout=20)
            self.assertEqual(r3.returncode, 3, r3.stderr)
            self.assertTrue((root / "w3" / "NOT-LAUNCHED.txt").is_file())
            self.assertIn("no account switching", (root / "w3" / "NOT-LAUNCHED.txt").read_text())
            doc = json.loads((root / "native-probe.json").read_text())
            self.assertEqual(doc["accounts"][".grok3"]["outcome"], "error")
            self.assertEqual(doc["accounts"][".grok"]["outcome"], "returned")

            # 4) First account (.grok) remains usable and reuses cached probe (no second transport call).
            r4 = subprocess.run([*base, "--grok-home", str(root / ".grok"), "--output-dir", str(root / "w4")],
                                capture_output=True, text=True, timeout=20)
            self.assertEqual(r4.returncode, 0, r4.stderr)
            log = (root / "launch.log").read_text().splitlines()
            self.assertEqual(log, [".grok:transport", ".grok:lane", ".grok2:transport", ".grok2:lane", ".grok3:transport", ".grok:lane"])

    def test_legacy_single_record_native_probe_replays_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "native-probe.json").write_text(json.dumps({
                "timestamp": "2026-11-20T18:00:00+00:00",
                "account": ".grok",
                "outcome": "returned",
                "count": 1,
            }))
            launcher = self._write_fake_transport(root, transport_outcomes={})
            brief = root / "lane.md"
            brief.write_text("Objective: unbounded.\n")
            res = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--xgrok-bin", str(launcher),
                 "--grok-home", str(root / ".grok"), "--output-dir", str(root / "w1"), "--transport-probe"],
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual((root / "launch.log").read_text().splitlines(), [".grok:lane"])

    def test_bound_canary_hit_launches_and_miss_refuses_recording_canary_failed(self):
        for hit in (True, False):
            with self.subTest(hit=hit), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                pid = _snowflake_for(datetime.now(timezone.utc) - timedelta(hours=2))
                launcher = self._write_fake_transport(
                    root,
                    transport_outcomes={".grok": {"outcome": "returned", "count": 1, "post_id": pid, "error": None}},
                    canary_hit=hit,
                )
                brief = root / "lane.md"
                brief.write_text("Query: `from:alpha since:2026-11-22_12:00:00_UTC until:2026-11-22_18:00:00_UTC`\n")
                res = subprocess.run(
                    [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--xgrok-bin", str(launcher),
                     "--grok-home", str(root / ".grok"), "--output-dir", str(root / "w1"), "--transport-probe"],
                    capture_output=True, text=True, timeout=20,
                )
                doc = json.loads((root / "native-probe.json").read_text())
                self.assertIn(".grok|utc|normal", doc["bound_canaries"])
                self.assertEqual(doc["canary_failed"], not hit)
                self.assertEqual(doc["bound_canary"]["outcome"], "passed" if hit else "canary_failed")
                if hit:
                    self.assertEqual(res.returncode, 0, res.stderr)
                    self.assertEqual((root / "launch.log").read_text().splitlines(),
                                     [".grok:transport", ".grok:bound-canary", ".grok:lane"])
                    manifest = json.loads((root / "w1" / "manifest.json").read_text())
                    self.assertEqual(manifest["bound_canary"]["outcome"], "passed")
                else:
                    self.assertEqual(res.returncode, 3, res.stderr)
                    self.assertEqual((root / "launch.log").read_text().splitlines(),
                                     [".grok:transport", ".grok:bound-canary"])
                    not_launched = (root / "w1" / "NOT-LAUNCHED.txt").read_text()
                    self.assertIn("fallback order:", not_launched)
                    self.assertFalse((root / "w1" / "manifest.json").exists())

    def test_late_slice_canary_requires_under_30m_control_and_uses_hydrated_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_pid = _snowflake_for(datetime.now(timezone.utc) - timedelta(hours=3))
            launcher = self._write_fake_transport(
                root,
                transport_outcomes={".grok": {"outcome": "returned", "count": 1, "post_id": old_pid, "error": None}},
                canary_hit=True,
            )
            brief = root / "late.md"
            brief.write_text("Query: `from:alpha since:2026-11-22_12:00:00_UTC until:2026-11-22_18:00:00_UTC`\n")
            base = [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--xgrok-bin", str(launcher),
                    "--grok-home", str(root / ".grok"), "--transport-probe", "--late-slice"]

            # Without a <30m control, late-slice canary refuses with canary_failed=True before any lane runs.
            r1 = subprocess.run([*base, "--output-dir", str(root / "w1")], capture_output=True, text=True, timeout=20)
            self.assertEqual(r1.returncode, 3, r1.stderr)
            doc = json.loads((root / "native-probe.json").read_text())
            self.assertTrue(doc["canary_failed"])
            self.assertIn("<30m", doc["bound_canary"]["error"])
            self.assertEqual((root / "launch.log").read_text().splitlines(), [".grok:transport"])

            # Add a <30m hydrated post: late-slice canary uses it, passes, and launches the lane.
            fresh_pid = _snowflake_for(datetime.now(timezone.utc) - timedelta(minutes=10))
            (root / "hydrated").mkdir()
            (root / "hydrated" / f"{fresh_pid}.json").write_text(json.dumps({
                "id_str": fresh_pid, "user": {"screen_name": "FreshAuthor"}, "text": "fresh",
            }))
            r2 = subprocess.run([*base, "--output-dir", str(root / "w2")], capture_output=True, text=True, timeout=20)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            doc = json.loads((root / "native-probe.json").read_text())
            self.assertFalse(doc["canary_failed"])
            self.assertEqual(doc["bound_canary"]["control_post_id"], fresh_pid)
            self.assertEqual(doc["bound_canary"]["control_author"], "FreshAuthor")
            self.assertIn(".grok|utc|late-slice", doc["bound_canaries"])


class DetachStatusAndRecoverTests(unittest.TestCase):
    def test_detach_runs_wave_in_background_and_status_tracks_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_transcript(root / "grok", "sess-a", ["x_keyword_search"])
            launcher = root / "launcher"
            launcher.write_text(
                f"#!{sys.executable}\nimport json, time\ntime.sleep(0.2)\n"
                "print(json.dumps({'text': 'detached packet', 'sessionId': 'sess-a'}))\n"
            )
            launcher.chmod(0o755)
            brief = root / "a.md"
            brief.write_text("Objective: detached worker.\n")
            out = root / "wave1"
            res = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--xgrok-bin", str(launcher),
                 "--grok-home", str(root / "grok"), "--output-dir", str(out), "--detach"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("started detached", res.stdout)
            _wait_for(out / "manifest.json", seconds=15)
            st = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), "status", str(out), "--json"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(st.returncode, 0, st.stderr)
            info = json.loads(st.stdout)
            self.assertEqual((info["state"], info["succeeded"], info["failed"]), ("done", 1, 0))

    def test_recover_reconstructs_packets_and_audited_manifest_with_unavailable_cost_and_zero_grok_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / ".grok"
            wave = root / "wave1"
            composed = wave / "composed"
            composed.mkdir(parents=True)
            launch_ts = "2026-11-22T01:14:35+00:00"
            (wave / "launched.json").write_text(json.dumps({"timestamp": launch_ts, "grok_home": str(home)}))
            req_ok = (
                "# mode: harvest\n# effort: medium\n"
                "# fresh_since: 2026-11-20T09:27:00-08:00\n"
                "# fresh_until: 2026-11-21T17:10:31-08:00\n"
                "Lane: 01-ok.\n"
            )
            req_miss = "# mode: harvest\n# effort: medium\nLane: 02-miss.\n"
            (composed / "01-ok.md").write_text(req_ok)
            (composed / "02-miss.md").write_text(req_miss)
            # Pre-existing finished lane is preserved as-is.
            (wave / "00-done-result.json").write_text(json.dumps({
                "name": "00-done", "status": "success", "returncode": 0, "usage": {"output_tokens": 10},
                "x_tool_calls": 1, "x_queries": [], "launched_at": launch_ts,
            }))
            # Native Grok session transcript for 01-ok with an epoch query + assistant message + turn_completed.
            q_ep = "from:dampedspring since_time:1795195620 until_time:1795309831"
            updates = "\n".join([
                json.dumps({"timestamp": 1795310105, "params": {"update": {
                    "sessionUpdate": "tool_call_update", "toolCallId": "ctc_req_call-0", "status": "completed",
                    "rawOutput": {"name": "x_keyword_search", "input": json.dumps({"query": q_ep, "mode": "Latest"})}}}}),
                json.dumps({"timestamp": 1795310120, "params": {"update": {"sessionUpdate": "turn_completed"}}}),
            ]) + "\n"
            sdir = write_session(home, "01a200d1-bd07-71f2-9129-9dabdd9905e2", req_ok, "2026-11-22T01:14:36Z", updates)
            packet_body = (
                "# X retrieval packet\n\n## Search log\n"
                f'- Query result: {{"query":"{q_ep}","outcome":"returned","count":5,"error":null}}\n'
            )
            with (sdir / "chat_history.jsonl").open("a") as fh:
                fh.write(json.dumps({"type": "assistant", "content": packet_body}) + "\n")

            # Status reports interrupted before recover.
            st1 = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), "status", str(wave), "--json"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(json.loads(st1.stdout)["state"], "interrupted")

            # Recover runs offline (empty PATH ensures zero Grok/subprocess calls).
            rec = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), "recover", str(wave)],
                capture_output=True, text=True, timeout=10, env={"PATH": ""},
            )
            self.assertEqual(rec.returncode, 1, rec.stderr)  # 02-miss failed -> exit 1
            manifest = json.loads((wave / "manifest.json").read_text())
            self.assertEqual((manifest["total_briefs"], manifest["succeeded"], manifest["failed"]), (3, 2, 1))
            self.assertEqual(manifest["recovery"]["cost_usd"], "unavailable")
            by_name = {w["name"]: w for w in manifest["workers"]}
            self.assertEqual(by_name["00-done"]["status"], "success")
            self.assertNotIn("recovered", by_name["00-done"])
            ok_w = by_name["01-ok"]
            self.assertEqual(ok_w["status"], "success")
            self.assertEqual(ok_w["cost_usd"], "unavailable")
            self.assertEqual(ok_w["x_tool_calls"], 1)
            self.assertEqual(ok_w["x_queries"][0]["window_status"], "within-approved-query-bounds")
            self.assertEqual(ok_w["x_queries"][0]["bound_form"], "epoch")
            self.assertEqual(ok_w["x_queries"][0]["result_count"], 5)
            self.assertEqual((wave / "01-ok-packet.md").read_text(), packet_body)
            raw_env = json.loads((wave / "01-ok-raw.json").read_text())
            self.assertIsNone(raw_env["total_cost_usd"])
            self.assertEqual(raw_env["cost_usd"], "unavailable")
            self.assertEqual(by_name["02-miss"]["status"], "failed")
            self.assertEqual(by_name["02-miss"]["cost_usd"], "unavailable")

            # Re-running without --overwrite refuses exit 2.
            again = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), "recover", str(wave)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(again.returncode, 2)
            # Status now reports recovered.
            st2 = subprocess.run(
                [sys.executable, str(Path(xgrok_wave.__file__)), "status", str(wave), "--json"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(json.loads(st2.stdout)["state"], "recovered")


class AccountFlagEdgeTests(unittest.TestCase):
    def test_empty_grok2_grok3_env_and_conflicting_flags_fail_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = root / "a.md"
            brief.write_text("Objective: x\n")
            launcher = root / "launcher"
            launcher.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath(__file__).with_name('ran').touch()\n")
            launcher.chmod(0o755)
            base = [sys.executable, str(Path(xgrok_wave.__file__)), str(brief), "--xgrok-bin", str(launcher), "--dry-run"]
            for flag, var in (("--grok2", "GROK2_HOME"), ("--grok3", "GROK3_HOME")):
                with self.subTest(flag=flag):
                    res = subprocess.run([*base, flag], capture_output=True, text=True, timeout=10,
                                         env={**os.environ, var: ""})
                    self.assertEqual(res.returncode, 2, res.stderr)
                    self.assertIn(f"{var} is set but empty", res.stderr)
                    self.assertFalse((root / "ran").exists())
            conflict = subprocess.run([*base, "--grok-home", str(root / "h"), "--grok2"],
                                      capture_output=True, text=True, timeout=10)
            self.assertEqual(conflict.returncode, 2)
            self.assertIn("not allowed with argument", conflict.stderr)


if __name__ == "__main__":
    unittest.main()
