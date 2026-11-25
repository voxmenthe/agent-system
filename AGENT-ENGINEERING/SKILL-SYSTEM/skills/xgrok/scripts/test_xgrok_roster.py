#!/usr/bin/env python3
"""Tests for xgrok_roster.py: probe briefs must pass the roster check they exist to serve.

Run: PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_xgrok_roster.py
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from xgrok_roster import find_handle_mentions

SCRIPT = Path(__file__).resolve().parent / "xgrok_roster.py"


class ProbeBriefTest(unittest.TestCase):
    def test_held_quote_mentions_are_not_search_targets(self) -> None:
        # The Sep 29 saved brief needed an owned label before @Muse in this held quote.
        line = ('- @RichLightShed (context) `2104924406107758644`: Held quote: '
                '"A few months ago everyone thought the AI SMB race was just Anthropic vs '
                'OpenAI with $META ignored 👋 @Muse"')
        self.assertEqual(find_handle_mentions(line)[-1], ("Muse", True))
        self.assertEqual(find_handle_mentions('Held quote: "@Muse"; Query: from:Muse')[-1], ("Muse", False))
        self.assertEqual(find_handle_mentions('Held quote: "@Muse" from:Muse')[-1], ("Muse", False))

    def test_a_labels_line_covers_a_literal_query(self) -> None:
        # 10-05: a "(context)" after a literal query's closing parenthesis did not label from:isellpremium,
        # so the handle was dropped from the batch to get past the check.
        query = "Query: `(from:options_insight OR from:isellpremium OR from:spotgamma) since:2026-10-05_09:45:00_PDT`\n"
        cases = {
            "": 1,
            "Labels: @isellpremium (off-list context, renamed SPXVIX)\n": 0,
            "Labels: @isellpremium (options seller)\n": 1,
            'Held quote: "selling premium into the close, h/t @isellpremium"\n': 1,
        }
        with tempfile.TemporaryDirectory() as tmp:
            roster = Path(tmp) / "roster.tsv"
            roster.write_text("handle\tregistries\tverified\tnote\noptions_insight\tcore\t\t\nspotgamma\tcore\t\t\n")
            for prefix, code in cases.items():
                with self.subTest(prefix=prefix):
                    brief = Path(tmp) / "options.md"
                    brief.write_text("Lane: options\n" + prefix + query)
                    checked = subprocess.run([sys.executable, str(SCRIPT), "--roster", str(roster), "check", str(brief)],
                                             capture_output=True, text=True, check=False)
                    self.assertEqual(checked.returncode, code, checked.stdout + checked.stderr)
                    self.assertIn("UNLABELED" if code else "labeled context", checked.stdout)

    def test_one_character_handles_are_prose_not_search_targets(self) -> None:
        # Su§4 (10-18): "four-handle groups (from:a OR from:b ...)" refused wave 2 for handles a to d.
        handles = [h for h, _ in find_handle_mentions("Use four-handle groups (from:a OR from:b OR from:c OR from:d).")]
        self.assertEqual(handles, [])
        self.assertEqual(find_handle_mentions("from:ab @x_y"), [("ab", False), ("x_y", False)])

    def test_a_parenthetical_held_span_labels_only_the_mentions_inside_it(self) -> None:
        # ME (10-19): "(held: @clausiusiv 2112216834196082756, ...)" inside a Priority names line was refused.
        line = "Priority names: CRWV, NBIS (held: @clausiusiv 2112216834196082756, @MikeZaccardi 2112), then @newname"
        self.assertEqual(find_handle_mentions(line),
                         [("clausiusiv", True), ("MikeZaccardi", True), ("newname", False)])
        self.assertEqual(find_handle_mentions("Names: X (Held receipts: @aa 1, @bb 2) and from:aa")[-1], ("aa", False))
        self.assertEqual(find_handle_mentions("Names (held: from:aa)")[0], ("aa", False))

    def test_a_handle_labeled_elsewhere_gets_a_ready_to_paste_labels_line(self) -> None:
        # Mo§2 (10-19): three handles labeled "(off-list context)" in Anchors: were searched unlabeled in a from:
        # group; the fix was mechanical, so the refusal prints it and the brief is left as written.
        brief_text = ("Anchors: @BondHawk (off-list context, rates relay); @CreditKid (off-list context)\n"
                      "Search design: (from:BondHawk OR from:CreditKid OR from:spotgamma) since:2026-10-19\n")
        with tempfile.TemporaryDirectory() as tmp:
            roster = Path(tmp) / "roster.tsv"
            roster.write_text("handle\tregistries\tverified\tnote\nspotgamma\tcore\t\t\n")
            brief = Path(tmp) / "15-crwv-credit.md"
            brief.write_text(brief_text)
            checked = subprocess.run([sys.executable, str(SCRIPT), "--roster", str(roster), "check", str(brief)],
                                     capture_output=True, text=True, check=False)
            self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
            self.assertIn("PASTE into 15-crwv-credit as its own line: Labels: @BondHawk (off-list context, rates "
                          "relay); @CreditKid (off-list context)", checked.stdout)
            self.assertEqual(brief.read_text(), brief_text)
            brief.write_text("Labels: @BondHawk (off-list context, rates relay); @CreditKid (off-list context)\n"
                             + brief_text)
            again = subprocess.run([sys.executable, str(SCRIPT), "--roster", str(roster), "check", str(brief)],
                                   capture_output=True, text=True, check=False)
            self.assertEqual(again.returncode, 0, again.stdout)
            self.assertNotIn("PASTE", again.stdout)

    def test_probe_briefs_pass_the_roster_check(self) -> None:
        # A literal placeholder such as `from:HANDLE` reads as an unlabeled off-roster handle,
        # so `mkt wave` refused to launch the probe wave on 2026-09-27.
        with tempfile.TemporaryDirectory() as tmp:
            roster = Path(tmp) / "roster.tsv"
            roster.write_text("handle\tregistries\tverified\tnote\nalpha_one\tcore\t\t\nBetaTwo\tpanel\t\t\n")
            out = Path(tmp) / "probes"

            def run(*args: str) -> subprocess.CompletedProcess:
                return subprocess.run([sys.executable, str(SCRIPT), "--roster", str(roster), *args],
                                      capture_output=True, text=True, check=False)

            made = run("probe-brief", "--out", str(out))
            self.assertEqual(made.returncode, 0, made.stderr)
            checked = run("check", str(out))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertNotIn("UNLABELED", checked.stdout)


if __name__ == "__main__":
    unittest.main()
