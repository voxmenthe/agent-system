"""explain-research's citation ledger, run as a caller runs it."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "skills" / "explain-research" / "scripts" / "citation_ledger.py"

SOURCE = """# Cache study

Results were **mixed**. As the authors put it:
“Warm caches cut median latency by 40%
on the [replay workload](https://example.org/replay), but the pool’s cold starts got *slower*.”

> Every run used the same 12 hosts.
"""
DOCUMENT = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Cache synthesis</title></head><body>
<nav><a href="#findings">Findings</a> <a href="#sources">Sources</a></nav>
<main><section id="findings"><h2>Findings</h2>
<p>Warm caches helped the replay workload in the one study inspected <a href="#src-1">[1]</a>.</p>
<blockquote><p>Warm caches cut median latency by 40% on the replay workload, but the pool's cold starts got slower.</p>
<footer>— <cite>Cache study</cite> <a href="#src-1">[1]</a></footer></blockquote>
<p>The hosts were fixed: <q>every run used the same … hosts</q> <a href="#src-2">[2]</a>.</p>
<p>Cold-start cost usually falls once a warm pool exists. [unverified]</p>
<p>Production traffic may not resemble the replay workload at all.</p>
</section>
<script type="application/json">{"note": "[unverified] <a href=\\"#src-9\\">x</a>"}</script>
<section id="sources"><h2>Sources</h2><ol>
<li id="src-1">Cache study, section Results (cache-study.md)</li>
<li id="src-2">Cache study, section Setup (cache-study.md)</li>
</ol></section></main></body></html>
"""


class CitationLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.directory / "cache-study.md"
        self.source.write_text(SOURCE, encoding="utf-8")

    def run_on(self, body: str, *sources: Path) -> subprocess.CompletedProcess[str]:
        path = self.directory / "synthesis.html"
        path.write_text(body, encoding="utf-8")
        command = [sys.executable, "-I", str(LEDGER), str(path)]
        if sources:
            command += ["--source", *map(str, sources)]
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_a_clean_document_passes_and_reports_its_provenance_counts(self) -> None:
        result = self.run_on(DOCUMENT, self.source)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("DEFECT", result.stdout)
        self.assertIn(
            "provenance: 3 citation link(s) to 2 of 2 source(s); 1 [unverified] marker(s); 2 quotation(s); "
            "1 of 4 prose block(s) carry neither a citation nor [unverified] (not checked)",
            result.stdout,
        )
        self.assertIn("no defect in what was checked", result.stdout)

    def test_a_fabricated_blockquote_is_a_defect_only_when_sources_are_given(self) -> None:
        fabricated = DOCUMENT.replace("cut median latency by 40%", "cut median latency by 60%")
        result = self.run_on(fabricated, self.source)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("DEFECT: line 6: <blockquote> found verbatim in no --source", result.stdout)
        unchecked = self.run_on(fabricated)
        self.assertEqual(unchecked.returncode, 0, unchecked.stdout)
        self.assertIn("2 quotation(s) not checked: pass the quoted sources with --source", unchecked.stdout)

    def test_quotation_parts_around_an_ellipsis_must_appear_in_order(self) -> None:
        swapped = DOCUMENT.replace("every run used the same … hosts", "12 hosts … every run used the same")
        result = self.run_on(swapped, self.source)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("DEFECT: line 8: <q> found verbatim in no --source", result.stdout)

    def test_a_dangling_citation_link_is_a_defect(self) -> None:
        result = self.run_on(DOCUMENT.replace('<a href="#src-2">[2]</a>', '<a href="#src-9">[9]</a>'), self.source)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('DEFECT: line 8: link href="#src-9" has no matching id', result.stdout)
        self.assertIn("bibliography entries never cited: src-2", result.stdout)

    def test_a_document_without_citation_links_fails(self) -> None:
        uncited = DOCUMENT.replace('href="#src-1"', 'href="#findings"').replace('href="#src-2"', 'href="#findings"')
        result = self.run_on(uncited)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('DEFECT: no citation link: link each claim to its bibliography entry with href="#src-<n>"',
                      result.stdout)

    def test_a_duplicate_id_is_a_defect(self) -> None:
        result = self.run_on(DOCUMENT.replace('<li id="src-2">', '<li id="src-1">'), self.source)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('DEFECT: id "src-1" is defined 2 times', result.stdout)

    def test_an_unreadable_source_is_not_checked(self) -> None:
        result = self.run_on(DOCUMENT, self.directory / "missing.txt")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("not checked", result.stdout)


if __name__ == "__main__":
    unittest.main()
