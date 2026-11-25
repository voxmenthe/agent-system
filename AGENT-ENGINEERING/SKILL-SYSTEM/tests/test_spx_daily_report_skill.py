from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from skill_system import SkillSystem, content_hash
from skill_system.model import validate_skill_tree

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "spx-daily-report"


class SPXSkillPackageTests(unittest.TestCase):
    def test_registered_tree_and_runtime_assets(self) -> None:
        validate_skill_tree(SKILL, "spx-daily-report")
        record = json.loads((ROOT / "registry.json").read_text())["skills"][
            "spx-daily-report"
        ]
        self.assertEqual(record["source"], "skills/spx-daily-report")
        self.assertEqual(record["effect_ceiling"], "local-write")
        for path in [
            "scripts/spx-daily-report",
            "scripts/spx_report.py",
            "scripts/spx_sources.py",
            "scripts/spx_analytics.py",
            "scripts/spx_render.py",
            "tests/fixtures/marks.csv",
            "tests/fixtures/occ.txt",
            "references/operations.md",
            "references/methodology.md",
        ]:
            self.assertTrue((SKILL / path).is_file())
        self.assertTrue((SKILL / "scripts/spx-daily-report").stat().st_mode & 0o111)

    def test_isolated_install_is_idempotent_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            system = SkillSystem(ROOT, home)
            target = home / ".agents/skills/spx-daily-report"
            self.assertEqual(
                system.install("spx-daily-report", apply=False).reason, "dry-run"
            )
            self.assertFalse(target.exists())
            result = system.install("spx-daily-report", apply=True)
            self.assertEqual(content_hash(SKILL), content_hash(target))
            self.assertEqual(
                system.install("spx-daily-report", apply=True).reason, "already-current"
            )
            system.rollback(result.operation_id, apply=True)
            self.assertFalse(target.exists())
            self.assertEqual(system.status().incomplete_operations, ())


if __name__ == "__main__":
    unittest.main()
