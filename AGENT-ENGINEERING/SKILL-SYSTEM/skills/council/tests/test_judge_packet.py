"""Judge-packet contract on fixture run directories; no model calls."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/judge-packet.sh"


class JudgePacketTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.preamble = self.root / "preamble.md"
        self.preamble.write_text("judge preamble\n")

    def run_dir(self, name: str, task: str = "the task") -> Path:
        run = self.root / name
        (run / "parent").mkdir(parents=True)
        (run / "TASK.md").write_text(task)
        return run

    def panel(self, run: Path, jobs: str, letter: str, status: str | None, text: str) -> None:
        directory = run / jobs
        directory.mkdir(exist_ok=True)
        (directory / f"{letter}.task").write_text("task\n")
        (directory / f"{letter}.out").write_text(text + "\n")
        if status is not None:
            (directory / f"{letter}.status").write_text(status + "\n")

    def parent(self, run: Path, letter: str, text: str = "STATUS: done\nFINDINGS:\nparent answer\n") -> None:
        (run / "parent" / f"{letter}.md").write_text(text)

    def build(self, run: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SCRIPT), str(run), str(self.preamble)],
                              capture_output=True, text=True, check=False)

    def test_selects_usable_candidates_and_excludes_the_rest(self) -> None:
        run = self.run_dir("ok")
        self.panel(run, "panel-1", "A", "0", "STATUS: done\nFINDINGS:\nanswer A")
        self.panel(run, "panel-1", "B", "0", "**STATUS:** BLOCKED\nFINDINGS: none")
        self.panel(run, "panel-1", "D", "1", "crashed")
        self.panel(run, "panel-2", "D", "0", "STATUS: done\nFINDINGS:\nanswer D rerun")
        self.panel(run, "panel-1", "E", None, "partial")
        self.panel(run, "panel-1", "F", "timeout", "")
        self.parent(run, "C")
        result = self.build(run)
        self.assertEqual(0, result.returncode, result.stderr)
        packet = (run / "judge/packet.md").read_text()
        excluded = (run / "judge/excluded.txt").read_text()
        self.assertEqual(["A", "C", "D"], [line[-1] for line in packet.splitlines() if line.startswith("## Candidate ")])
        self.assertTrue(packet.startswith("judge preamble\n"))
        self.assertIn("\n# ORIGINAL TASK\n\nthe task\n# CANDIDATE ANSWERS\n", packet)
        self.assertIn("answer D rerun", packet)
        self.assertNotIn("crashed", packet)
        self.assertIn("B excluded: STATUS blocked", excluded)
        self.assertIn("E excluded: no status", excluded)
        self.assertIn("F excluded: exit timeout", excluded)
        self.assertNotIn("Lane:", packet)
        self.assertFalse((run / "judge/candidates.tmp").exists())

    def test_refuses_unsafe_or_thin_runs(self) -> None:
        cases = {
            "letter collision": (lambda run: (self.panel(run, "panel-1", "A", "0", "STATUS: done\nFINDINGS: a"),
                                              self.panel(run, "panel-1", "B", "0", "STATUS: done\nFINDINGS: b"),
                                              self.parent(run, "A")), "both the sealed parent"),
            "one external": (lambda run: (self.panel(run, "panel-1", "A", "0", "STATUS: done\nFINDINGS: a"),
                                          self.panel(run, "panel-1", "B", "2", "x"),
                                          self.parent(run, "C")), "only 1 usable external"),
            "unframed parent": (lambda run: (self.panel(run, "panel-1", "A", "0", "STATUS: done\nFINDINGS: a"),
                                             self.panel(run, "panel-1", "B", "0", "STATUS: done\nFINDINGS: b"),
                                             self.parent(run, "C", "plain prose answer\n")), "headings"),
        }
        for name, (populate, message) in cases.items():
            with self.subTest(name):
                run = self.run_dir(name.replace(" ", "-"))
                populate(run)
                result = self.build(run)
                self.assertNotEqual(0, result.returncode)
                self.assertIn(message, result.stderr)
                self.assertFalse((run / "judge/packet.md").exists())

    def test_lanes_label_every_candidate(self) -> None:
        run = self.run_dir("lanes")
        self.panel(run, "panel-1", "A", "0", "STATUS: done\nFINDINGS: a")
        self.panel(run, "panel-1", "B", "0", "STATUS: done\nFINDINGS: b")
        self.parent(run, "C")
        (run / "lanes.tsv").write_text("A\timplementer\tcomplete-answer\n"
                                       "B\tregression-reviewer\tcontributing\n"
                                       "C\tarchitect\tcomplete-answer\n")
        result = self.build(run)
        self.assertEqual(0, result.returncode, result.stderr)
        packet = (run / "judge/packet.md").read_text()
        self.assertIn("## Candidate A\n\nLane: implementer (complete-answer)\n\nSTATUS: done", packet)
        self.assertIn("## Candidate B\n\nLane: regression-reviewer (contributing)\n", packet)
        self.assertIn("## Candidate C\n\nLane: architect (complete-answer)\n", packet)

    def test_lanes_must_be_complete_and_well_formed(self) -> None:
        for name, lanes, message in [
            ("missing row", "A\timplementer\tcomplete-answer\nC\tarchitect\tcomplete-answer\n", "no row for candidate B"),
            ("bad kind", "A\timplementer\tbase\nB\tskeptic\tcomplete-answer\nC\tarchitect\tcomplete-answer\n", "line(s) 1 "),
            ("duplicate", "A\timplementer\tcomplete-answer\nA\tskeptic\tcomplete-answer\n", "line(s) 2 "),
        ]:
            with self.subTest(name):
                run = self.run_dir(name.replace(" ", "-"))
                self.panel(run, "panel-1", "A", "0", "STATUS: done\nFINDINGS: a")
                self.panel(run, "panel-1", "B", "0", "STATUS: done\nFINDINGS: b")
                self.parent(run, "C")
                (run / "lanes.tsv").write_text(lanes)
                result = self.build(run)
                self.assertNotEqual(0, result.returncode)
                self.assertIn(message, result.stderr)
                self.assertFalse((run / "judge/packet.md").exists())

    def test_packet_never_names_launchers(self) -> None:
        run = self.run_dir("blind")
        (run / "wave.txt").write_text("@@ launcher=dswe name=A\n@@ launcher=cax name=B\n")
        (run / "RUN.md").write_text("| A | panel | dswe |\n| B | panel | cax |\n")
        self.panel(run, "panel-1", "A", "0", "STATUS: done\nFINDINGS: a")
        self.panel(run, "panel-1", "B", "0", "STATUS: done\nFINDINGS: b")
        self.assertEqual(0, self.build(run).returncode)
        packet = (run / "judge/packet.md").read_text()
        self.assertNotIn("dswe", packet)
        self.assertNotIn("cax", packet)


if __name__ == "__main__":
    unittest.main()
