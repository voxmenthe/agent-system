from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
# A bare `python3 scripts/x.py` only works when the agent's working directory
# is the skill directory, which it never is in a user's project.
UNANCHORED_SCRIPT = re.compile(r"\b(?:python3?|bash|sh|node)\s+scripts/")
# Lines with unanchored invocations that predate this rule. Anchor them
# (`python3 <skill-directory>/scripts/x.py`) and lower the count; never add
# an entry or raise a count.
UNANCHORED_GRANDFATHER = {
    "chats/SKILL.md": 7,
    "gpt-context/SKILL.md": 1,
    "notebooklm/SKILL.md": 2,
    "notebooklm/references/chrome-workflow.md": 1,
    "upcoming/SKILL.md": 1,
}


def unanchored_script_lines(skills_root: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        skill = skill_md.parent
        references = skill / "references"
        documents = [skill_md]
        if references.is_dir():
            documents += sorted(references.rglob("*.md"))
        for document in documents:
            for line in document.read_text().splitlines():
                if UNANCHORED_SCRIPT.search(line):
                    counts[document.relative_to(skills_root).as_posix()] += 1
    return counts


class SkillHygieneTests(unittest.TestCase):
    def test_skill_scripts_are_invoked_from_the_skill_directory(self) -> None:
        self.assertEqual(
            UNANCHORED_GRANDFATHER,
            dict(unanchored_script_lines(ROOT / "skills")),
        )

    def test_unanchored_pattern_separates_bare_and_anchored_invocations(self) -> None:
        flagged = (
            "python3 scripts/check_output.py doc.md",
            "cd skill && bash scripts/run.sh",
            "node scripts/render.mjs",
        )
        anchored = (
            "python3 <skill-directory>/scripts/check_output.py doc.md",
            "python3 ~/.agents/skills/show-code/scripts/render.py x.md",
            "bash /Users/example/.agents/skills/x/scripts/run.sh",
            "edit the files under scripts/ by hand",
        )
        for line in flagged:
            with self.subTest(line=line):
                self.assertRegex(line, UNANCHORED_SCRIPT)
        for line in anchored:
            with self.subTest(line=line):
                self.assertNotRegex(line, UNANCHORED_SCRIPT)


if __name__ == "__main__":
    unittest.main()
