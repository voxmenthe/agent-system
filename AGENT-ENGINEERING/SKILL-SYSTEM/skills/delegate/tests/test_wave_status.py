"""Fleet-view CLI contracts using local artifacts, never model calls."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/wave-status"


class WaveStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="delegate status ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.jobs = self.root / "jobs"
        self.jobs.mkdir()

    def worker(self, name: str, status: str | None = "0", out: str | None = "",
               stderr: str | None = "") -> None:
        for suffix, text in (("task", "ROLE: review\n"), ("status", status),
                             ("out", out), ("stderr", stderr)):
            if text is not None:
                (self.jobs / f"{name}.{suffix}").write_text(text, encoding="utf-8")

    def manifest(self, names: list[str], filename: str = "WAVE.tsv",
                 launcher: str = "cdm2") -> None:
        header = "name\tlauncher" + ("\texit\tout-bytes" if filename == "SUMMARY.tsv" else "")
        suffix = "\t0\t0" if filename == "SUMMARY.tsv" else ""
        (self.jobs / filename).write_text(
            header + "\n" + "".join(f"{name}\t{launcher}{suffix}\n" for name in names),
            encoding="utf-8")

    def run_status(self, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(SCRIPT), self.jobs.name, *flags], cwd=self.root,
                              text=True, encoding="utf-8", capture_output=True, timeout=5)

    def rows(self, result: subprocess.CompletedProcess[str]) -> list[list[str]]:
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        return [line.split("  ") for line in result.stdout.splitlines()[1:]
                if not line.startswith("…")]

    def make_fleet(self) -> list[str]:
        names = [f"worker-{index:03d}" for index in range(100)]
        failures = {6: "rate-limited: quota exhausted", 44: "quarantined: account paused",
                    98: "unclassified"}
        for index, name in enumerate(names):
            if index in failures:
                self.worker(name, "1", stderr="delegate worker: failure class: " + failures[index] + "\n")
            elif index in (29, 90):
                self.worker(name, out="**STATUS:** blocked\n**BLOCKERS:** needs parent input\n")
            else:
                self.worker(name, out="STATUS: done\n")
        self.manifest(names)
        return names

    def test_each_state_group_order_and_wave_metadata_precedence(self) -> None:
        names = ["returned-z", "failed-z", "blocked-z", "unsettled-z", "queued-z",
                 "failed-a", "blocked-a", "returned-a", "unsettled-a", "queued-a"]
        self.worker("returned-z", out="STATUS: done\n")
        self.worker("failed-z", "17")
        self.worker("blocked-z", out="STATUS: blocked\nBLOCKERS: needs auth\n")
        self.worker("unsettled-z", None)
        self.worker("queued-z", "not-started (rate-limited on cdm2)", None, None)
        self.worker("failed-a", "timeout")
        self.worker("blocked-a", out="- STATUS: blocked\n")
        self.worker("returned-a")
        self.worker("unsettled-a", "unconfirmed", stderr=None)
        self.worker("queued-a", "not-started", None, None)
        self.manifest(list(reversed(names)), "SUMMARY.tsv", "agg")
        self.manifest(names)
        result = self.run_status()
        rows = self.rows(result)
        self.assertEqual(
            "jobs: 10 workers · 2 returned · 2 blocked · 2 failed (1 unclassified, 1 timeout)"
            " · 2 unsettled · 2 not started", result.stdout.splitlines()[0])
        self.assertEqual(
            ["failed-z", "failed-a", "blocked-z", "blocked-a", "unsettled-z",
             "unsettled-a", "queued-z", "queued-a", "returned-z", "returned-a"],
            [row[1] for row in rows])
        self.assertTrue(all(len(row) == 5 and row[2] == "cdm2" for row in rows), rows)
        by_name = {row[1]: row for row in rows}
        self.assertEqual(["blocked", "blocked-z", "cdm2", "needs auth", "jobs/blocked-z.out"],
                         by_name["blocked-z"])
        self.assertEqual("STATUS: blocked", by_name["blocked-a"][3])
        self.assertEqual("(rate-limited on cdm2)", by_name["queued-z"][3])
        self.assertEqual("jobs/queued-z.task", by_name["queued-z"][4])
        self.assertEqual("jobs/unsettled-z.stderr", by_name["unsettled-z"][4])
        self.assertEqual("jobs/unsettled-a.task", by_name["unsettled-a"][4])
        self.assertEqual("unconfirmed", by_name["unsettled-a"][3])
        self.assertEqual("jobs/failed-z.stderr", by_name["failed-z"][4])
        self.assertEqual("returned", by_name["returned-z"][0])
        self.assertEqual("jobs/returned-z.out", by_name["returned-z"][4])

    def test_markdown_blocked_labels_and_multiline_blockers(self) -> None:
        cases = [
            ("STATUS: blocked\nBLOCKERS: needs auth", "needs auth"),
            ("**STATUS:** blocked\n**BLOCKERS:** needs auth", "needs auth"),
            ("- STATUS: blocked\n- BLOCKERS: needs auth", "needs auth"),
            ("  + __sTaTuS__: **BlOcKeD**\n* __bLoCkErS:__ needs auth", "needs auth"),
            ("*STATUS: blocked*\nBLOCKERS:\n\n  needs auth\nsecond detail", "needs auth"),
            ("STATUS: blocked\nBLOCKERS:\n", "STATUS: blocked"),
            ("STATUS: blocked\nBLOCKERS: " + "x" * 200, "x" * 99 + "…"),
        ]
        for output, detail in cases:
            with self.subTest(output=output):
                self.worker("worker", out=output)
                row, = self.rows(self.run_status())
                self.assertEqual("blocked", row[0])
                self.assertEqual(detail, row[3])
        self.worker("worker", out="Narrative: STATUS: blocked\nSTATUS: unblocked\n")
        row, = self.rows(self.run_status())
        self.assertEqual("returned", row[0])

    def test_failure_classes_tail_and_read_only_artifacts(self) -> None:
        self.worker("rate", "1", stderr="large diagnostic body\n" * 40000 +
                    "delegate worker: failure class: rate-limited: quota exhausted\n\n  \n")
        self.worker("quarantined", "2", stderr="delegate worker: failure class: quarantined: paused\n")
        self.worker("filtered", "1", stderr="delegate worker: failure class: content-filtered: task text; bars no launcher\n")
        self.worker("unclassified", "3", stderr="delegate worker: failure class: unclassified\n")
        self.worker("timeout", "timeout", stderr="delegate worker: failure class: rate-limited: stale\n")
        self.worker("old", "4", stderr="old adapter diagnostics\n")
        self.worker("not-last", "5", stderr="delegate worker: failure class: rate-limited: stale\nlast diagnostic\n")
        self.worker("missing-stderr", "6", stderr=None)
        self.worker("unknown-class", "-9", stderr="delegate worker: failure class: other: unknown\n")
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                  for path in self.jobs.iterdir()}
        result = self.run_status()
        rows = {row[1]: row for row in self.rows(result)}
        self.assertIn("9 failed (1 rate-limited, 1 quarantined, 1 content-filtered, 5 unclassified, 1 timeout)", result.stdout)
        self.assertEqual("exit 1; rate-limited: quota exhausted", rows["rate"][3])
        self.assertEqual("exit 2; quarantined: paused", rows["quarantined"][3])
        self.assertEqual("exit 1; content-filtered: task text; bars no launcher", rows["filtered"][3])
        self.assertEqual("exit 3; unclassified", rows["unclassified"][3])
        self.assertEqual("timeout", rows["timeout"][3])
        for name, status in (("old", "4"), ("not-last", "5"), ("missing-stderr", "6"),
                             ("unknown-class", "-9")):
            self.assertEqual(f"exit {status}; unclassified", rows[name][3])
        self.assertTrue(all(row[0] == "failed" and row[4].endswith(".stderr") for row in rows.values()))
        after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                 for path in self.jobs.iterdir()}
        self.assertEqual(before, after)

    def test_legacy_summary_order_and_task_only_enumeration(self) -> None:
        self.worker("z", "7", stderr="older diagnostics")
        self.worker("a", "9")
        self.manifest(["z", "orphan", "a"], "SUMMARY.tsv", "agg")
        (self.jobs / "orphan.status").write_text("1")
        rows = self.rows(self.run_status())
        self.assertEqual(["z", "a"], [row[1] for row in rows])
        self.assertTrue(all(row[2] == "agg" and row[3].endswith("unclassified") for row in rows))
        self.assertFalse((self.jobs / "WAVE.tsv").exists())

    def test_no_manifest_and_unknown_statuses_remain_unsettled(self) -> None:
        unknown = "unexpected  state: " + "x" * 120
        for name, status in (("z", None), ("a", unknown), ("empty", "")):
            self.worker(name, status, stderr=None)
        result = self.run_status()
        rows = self.rows(result)
        self.assertEqual(["a", "empty", "z"], [row[1] for row in rows])
        self.assertIn(f"unsettled  a  -  {unknown}  jobs/a.task\n", result.stdout)
        self.assertTrue(all(row[0] == "unsettled" and row[2] == "-" for row in rows))
        self.assertNotIn("failed (", result.stdout)

    def test_a_dispatched_worker_without_status_differs_from_an_undispatched_one(self) -> None:
        # The runner opens .out and .stderr just before spawning the adapter.
        self.worker("running", None)
        self.worker("queued", None, None, None)
        details = {row[1]: row[3] for row in self.rows(self.run_status())}
        self.assertEqual({"running": "output opened, no status", "queued": "no status"}, details)

    def test_hundred_workers_are_bounded_without_hiding_failures_or_blockers(self) -> None:
        self.make_fleet()
        result = self.run_status()
        rows = self.rows(result)
        self.assertLess(len(result.stdout.splitlines()), 40)
        self.assertEqual(25, len(rows))
        self.assertEqual(["worker-006", "worker-044", "worker-098", "worker-029", "worker-090"],
                         [row[1] for row in rows[:5]])
        self.assertEqual(20, sum(row[0] == "returned" for row in rows))
        self.assertEqual("… 75 more rows omitted (--all shows them)", result.stdout.splitlines()[-1])
        self.assertEqual(
            "jobs: 100 workers · 95 returned · 2 blocked · 3 failed "
            "(1 rate-limited, 1 quarantined, 1 unclassified) · 0 unsettled · 0 not started",
            result.stdout.splitlines()[0])

    def test_all_prints_every_row(self) -> None:
        names = self.make_fleet()
        result = self.run_status("--all")
        rows = self.rows(result)
        self.assertEqual(100, len(rows))
        self.assertEqual(set(names), {row[1] for row in rows})
        self.assertNotIn("omitted", result.stdout)

    def test_non_wave_paths_exit_two_with_one_line_error_and_help_works(self) -> None:
        ordinary_file = self.root / "ordinary file"
        ordinary_file.write_text("not a directory")
        (self.jobs / "orphan.out").write_text("STATUS: done")
        for path in (self.jobs, self.root / "missing", ordinary_file):
            with self.subTest(path=path):
                result = subprocess.run([str(SCRIPT), str(path)], text=True,
                                        capture_output=True, timeout=5)
                self.assertEqual(2, result.returncode)
                self.assertEqual("", result.stdout)
                self.assertEqual(1, len(result.stderr.splitlines()))
                self.assertTrue(result.stderr.startswith("wave-status: "), result.stderr)
        result = subprocess.run([str(SCRIPT), "--help"], text=True,
                                capture_output=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("usage: wave-status", result.stdout)
        self.assertIn("--all", result.stdout)
        self.assertEqual("", result.stderr)


if __name__ == "__main__":
    unittest.main()
