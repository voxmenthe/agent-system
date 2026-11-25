"""Solutionize skill contract, registry record, guide entry, draw command and projection; no model calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from skill_system import SkillSystem, content_hash
from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "solutionize"
BOUNDARY = re.compile(r"> (Use when the user invokes `\$solutionize`.*?)\n\n", re.S)
DRAW = re.compile(r"^DRAW='\n(.*?)'$", re.S | re.M)
DIRECTORY_FEED = re.compile(r"`\(cd <dir> && (find .*? -print0) \| python3 -c \"\$DRAW\"\)`")


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("> ", " "))


def nonblank_lines(path: Path) -> list[tuple[int, str]]:
    with open(path, encoding="utf-8") as lines:
        return [(number, line.rstrip()[:200]) for number, line in enumerate(lines, 1) if line.strip()]


class SolutionizeSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (SKILL_ROOT / "SKILL.md").read_text()
        self.briefs = (SKILL_ROOT / "references/briefs.md").read_text()
        self.angles = (SKILL_ROOT / "references/angles.md").read_text()
        self.running = (SKILL_ROOT / "references/running.md").read_text()

    def draw(self, feed: str, cwd: Path) -> str:
        result = subprocess.run(
            ["bash", "-c", f'{feed} | python3 -c "$DRAW"'],
            cwd=cwd,
            env={**os.environ, "DRAW": DRAW.search(self.running).group(1)},
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def assert_passage_from(self, output: str, root: Path, allowed: set[str]) -> None:
        header, *passage = output.splitlines()
        path, start = header.rsplit(":", 1)
        self.assertIn(path, allowed)
        self.assertTrue(3 <= len(passage) <= 5, output)
        lines = nonblank_lines(root / path)
        first = [number for number, _ in lines].index(int(start))
        self.assertEqual([line for _, line in lines[first:first + len(passage)]], passage)

    def test_validates_and_is_explicit_only(self) -> None:
        self.assertRegex(validate_skill_tree(SKILL_ROOT, "solutionize"), r"^sha256:")
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("disable-model-invocation: true", self.skill)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$solutionize", metadata)

    def test_registry_record_declares_dependencies_and_external_write(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["solutionize"]
        self.assertEqual("custom", record["ownership"])
        self.assertEqual("skills/solutionize", record["source"])
        self.assertEqual(["delegate", "learning-workspace", "orchestrate"], record["dependencies"])
        self.assertEqual("external-write", record["effect_ceiling"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual(["~/.agents/skills/solutionize"], record["install_targets"])

    def test_user_guide_carries_the_same_boundary_sentence(self) -> None:
        boundary = BOUNDARY.search(self.skill)
        self.assertIsNotNone(boundary)
        guide = flat((ROOT / "USER-GUIDE.md").read_text())
        self.assertIn(flat(boundary.group(1)).strip(), guide)
        self.assertIn("[`solutionize`](skills/solutionize/SKILL.md)", guide)

    def test_description_and_boundary_exclude_no_other_skill(self) -> None:
        # Explicit-only: exclusions do no routing work and could only make the agent resist an invocation.
        description = re.search(r'^description: "(.*)"$', self.skill, re.M).group(1)
        boundary = BOUNDARY.search(self.skill).group(1)
        siblings = ("fanout", "council", "debugging", "evidence-driven", "delegate", "orchestrate", "dialectic")
        for sibling in siblings:
            self.assertNotIn(sibling, description + boundary)

    def test_states_load_bearing_rules(self) -> None:
        text = flat(self.skill)
        self.assertIn("Hunt on the premise; claim only what the check confirms.", text)
        self.assertIn("The check must confirm it on a rerun from a clean start.", text)
        self.assertIn("Never stop because the problem looks hard or progress is slow.", text)
        self.assertIn("Web: whether agents may search, and for what; by default, not at all.", text)
        self.assertIn("Local files: which paths agents may read;", text)
        self.assertIn('never as verdicts ("X does not work")', text)
        self.assertIn("Keep the run in a learning workspace in the repository", text)
        self.assertIn("About one line in four across the run is a wildcard line", text)
        self.assertIn("`$solutionize` authorizes four things", text)
        self.assertIn(
            "It does not authorize changes to the user's working tree outside the workspace, commits, pushes,"
            " or redelegation by workers.",
            text,
        )

    def test_angles_are_optional_and_reached_only_from_the_stall_step(self) -> None:
        link = re.compile(r"\]\((?:references/)?angles\.md\)")
        texts = {
            "SKILL.md": self.skill,
            "briefs.md": self.briefs,
            "angles.md": self.angles,
            "running.md": self.running,
        }
        links = {name: len(link.findall(text)) for name, text in texts.items()}
        self.assertEqual({"SKILL.md": 1, "briefs.md": 0, "angles.md": 0, "running.md": 0}, links)
        stall_step = re.search(r"^\d+\. \*\*When a wave adds nothing new.*?(?=^\S)", self.skill, re.S | re.M)
        self.assertIn("](references/angles.md)", stall_step.group(0))
        note, body = self.angles.split("\n## ", 1)
        label = ("Inspiration only", "to build on", "not meant to be exhaustive", "only when the run has stalled")
        for phrase in label:
            self.assertIn(phrase, flat(note))
        # One angle per line, so a random draw from the file yields whole angles.
        for line in ("## " + body).splitlines():
            if line.strip():
                self.assertRegex(line, r"^(## |- )")

    def test_briefs_state_the_premise_and_the_answer_header(self) -> None:
        self.assertIn("A solution to this problem already exists.", self.briefs)
        self.assertIn("Do not search the web.", self.briefs)
        header = re.search(r"starting with this header:\n((?:    .*\n)+)", self.briefs).group(1)
        fields = [line.split(":", 1)[0].strip() for line in header.splitlines() if ":" in line]
        self.assertEqual(["RESULT", "LINE", "CLAIM", "REPRODUCE", "WEAKEST POINT", "NEXT"], fields)
        self.assertIn("RESULT: solved | partial | not yet\n", header)

    def test_running_keeps_the_run_contained(self) -> None:
        # Workers can run very long: a time limit only when the user names one.
        self.assertIn('${budget:+--timeout "$budget"}', self.running)
        self.assertNotRegex(self.running, r"--timeout [0-9]")
        # Git reports resolved worktree paths, and cleanup matches them against $RUN.
        self.assertLess(self.running.index('RUN=$(cd "$RUN" && pwd -P)'), self.running.index("worktree add"))
        self.assertIn("printf 'tree/\\n' > \"$RUN/.gitignore\"", self.running)
        self.assertEqual(2, self.running.count('status --porcelain -- ":(exclude)$WS_PATH"'))
        self.assertEqual(1, self.running.count("worktree remove --force"))
        self.assertRegex(
            self.running,
            r'grep "\^\$RUN/" \|\n\s+while read -r tree; do git -C "\$REPO" worktree remove --force',
        )

    def test_stall_draw_reads_the_installed_angles(self) -> None:
        record = json.loads((ROOT / "registry.json").read_text())["skills"]["solutionize"]
        installed = record["install_targets"][0].replace("~", "$HOME", 1) + "/references/angles.md"
        self.assertIn(f"printf '%s\\0' \"{installed}\" | python3 -c \"$DRAW\"", self.running)

    def test_draw_reads_only_usable_text_files(self) -> None:
        feed = DIRECTORY_FEED.search(self.running).group(1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sub").mkdir()
            (root / ".hidden").mkdir()
            (root / "a.txt").write_text("one\n\ntwo\nthree\n" + "x" * 300 + "\nfive\nsix\n")
            (root / "sub/b.md").write_text("alpha\nbeta\ngamma\n")
            (root / ".dotfile.txt").write_text("h1\nh2\nh3\nh4\n")
            (root / ".hidden/c.txt").write_text("d1\nd2\nd3\nd4\n")
            (root / "binary.bin").write_bytes(b"\xff\xfe\x00\x01\n" * 8)
            (root / "latin1.txt").write_bytes("café\n".encode("latin-1") * 4)
            (root / "short.txt").write_text("only\ntwo\n")
            (root / "blank.txt").write_text("\n \n\n")
            for _ in range(20):
                self.assert_passage_from(self.draw(feed, root), root, {"./a.txt", "./sub/b.md"})

    def test_draw_never_skips_a_file_shorter_than_the_span(self) -> None:
        feed = DIRECTORY_FEED.search(self.running).group(1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "three.txt").write_text("alpha\nbeta\ngamma\n")
            (root / "short.txt").write_text("only\ntwo\n")
            for _ in range(10):
                self.assertEqual("./three.txt:1\nalpha\nbeta\ngamma\n", self.draw(feed, root))
            (root / "three.txt").unlink()
            self.assertEqual("", self.draw(feed, root))

    def test_draw_from_the_angles_file_gives_consecutive_angles(self) -> None:
        angles = SKILL_ROOT / "references/angles.md"
        for _ in range(10):
            self.assert_passage_from(self.draw(f"printf '%s\\0' '{angles}'", ROOT), ROOT, {str(angles)})

    def test_every_linked_reference_exists(self) -> None:
        for path in [SKILL_ROOT / "SKILL.md", *(SKILL_ROOT / "references").glob("*.md")]:
            for target in re.findall(r"\]\(([^)#]+)", path.read_text()):
                self.assertTrue((path.parent / target).is_file(), (path.name, target))

    def test_managed_projection_preserves_the_package_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            target = home / ".agents" / "skills" / "solutionize"
            self.assertEqual("dry-run", system.install("solutionize", apply=False).reason)
            self.assertFalse(target.exists())

            applied = system.install("solutionize", apply=True)
            self.assertEqual("installed", applied.reason)
            self.assertEqual(content_hash(SKILL_ROOT), content_hash(target))
            self.assertEqual("current", system.status().skills["solutionize"].state)

            rolled_back = system.rollback(applied.operation_id, apply=True)
            self.assertEqual("rolled-back", rolled_back.reason)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
