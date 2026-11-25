from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import unittest.mock

from skill_system import SkillSystem, ValidationError
from skill_system.cli import run
from tests.helpers import make_system


class RelocateTests(unittest.TestCase):
    """A moved checkout: install state and Grok links follow it, nothing else changes."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name).resolve()
        self.old = base / "old" / "SKILL-SYSTEM"
        self.new = base / "new" / "SKILL-SYSTEM"
        self.home = base / "home"
        make_system(self.old, self.home)
        grok = self.old / "grok-skills" / "macro"
        grok.mkdir(parents=True)
        (grok / "SKILL.md").write_text(
            "---\nname: macro\ndescription: Native X research in Grok.\n---\n\n# Macro\n"
        )
        SkillSystem(self.old, self.home).sync(apply=True)
        shutil.copytree(self.old, self.new)
        self.system = SkillSystem(self.new, self.home)
        self.link = self.home / ".grok" / "skills" / "macro"
        self.state = self.home / ".agents" / ".skill-system" / "install-state.json"

    def test_moved_checkout_fails_until_relocated_then_stays_current(self) -> None:
        with self.assertRaisesRegex(ValidationError, "source path disagrees"):
            self.system.status()
        before = self.state.read_bytes()

        alias = self.old.parent.parent / "alias"  # the old checkout reached through a link
        alias.symlink_to(self.old.parent)
        preview = self.system.relocate(alias / "SKILL-SYSTEM")

        self.assertEqual("dry-run", preview.reason)
        self.assertEqual(4, len(preview.changes))  # alpha's state, three Grok links
        self.assertEqual(before, self.state.read_bytes())
        self.assertEqual(self.old / "grok-skills" / "macro", self.link.resolve())

        applied = self.system.relocate(alias / "SKILL-SYSTEM", apply=True)

        self.assertTrue(applied.applied)
        status = self.system.status()
        self.assertEqual("current", status.skills["alpha"].state)
        self.assertEqual({"current"}, {s for a in status.grok.values() for s in a.values()})
        self.assertEqual(self.new / "grok-skills" / "macro", self.link.resolve())
        (backup,) = self.state.parent.glob("install-state.before-relocate-*.json")
        self.assertEqual(before, backup.read_bytes())
        self.link.unlink()  # a stop after the state write: one link still names the old checkout
        self.link.symlink_to(self.old / "grok-skills" / "macro")
        self.assertEqual(1, len(self.system.relocate(self.old, apply=True).changes))
        self.assertEqual(1, len(list(self.state.parent.glob("install-state.before-relocate-*.json"))))
        self.assertEqual("already-current", self.system.relocate(self.old, apply=True).reason)
        self.assertEqual("nothing-to-sync", self.system.sync(apply=True).reason)

    def test_state_naming_a_third_checkout_is_refused_before_any_write(self) -> None:
        state = json.loads(self.state.read_text())
        state["managed"]["alpha"]["source"] = "/elsewhere/SKILL-SYSTEM/skills/alpha"
        self.state.write_text(json.dumps(state))
        before = self.state.read_bytes()

        with self.assertRaisesRegex(ValidationError, "names neither checkout"):
            self.system.relocate(self.old, apply=True)
        self.assertEqual(before, self.state.read_bytes())

        state["managed"]["alpha"]["source"] = str(self.old / "skills" / "alpha")
        state["managed"]["alpha"]["target"] = "/elsewhere/alpha"
        self.state.write_text(json.dumps(state))
        before = self.state.read_bytes()
        with self.assertRaisesRegex(ValidationError, "target path disagrees"):
            self.system.relocate(self.old, apply=True)
        self.assertEqual(before, self.state.read_bytes())
        self.assertEqual(self.old / "grok-skills" / "macro", self.link.resolve())

    def test_cli_relocates_with_apply_only(self) -> None:
        shutil.rmtree(self.old)
        self.old.symlink_to(self.new)  # moved, leaving a link at the old location
        arguments = ["--root", str(self.new), "--home", str(self.home), "relocate", "--from", str(self.old)]
        with unittest.mock.patch("sys.stdout"):
            self.assertEqual(0, run(arguments))
            self.assertEqual(str(self.old / "grok-skills" / "macro"), os.readlink(self.link))
            self.assertEqual(0, run([*arguments, "--apply"]))
        self.assertEqual(str(self.new / "grok-skills" / "macro"), os.readlink(self.link))
        self.assertEqual("current", self.system.status().skills["alpha"].state)


if __name__ == "__main__":
    unittest.main()
