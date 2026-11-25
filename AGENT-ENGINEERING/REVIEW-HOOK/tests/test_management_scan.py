from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from runtime.analysis.evidence_package import scan_range
from runtime.analysis.outcomes import (
    OutcomeStore,
    build_auto_outcome,
    delivery_identity,
)
from scripts import review_hook as manager


class ManagementScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.email", "scan@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name", "Scan Test"],
            check=True,
        )
        self.module = self.repo / "module.py"
        self.module.write_text("def choose(items=None):\n    return items\n", encoding="utf-8")
        self._git("add", "module.py")
        self._git("commit", "-qm", "base")
        self.before = self._git("rev-parse", "HEAD")
        self.module.write_text("def choose(items=[]):\n    return items\n", encoding="utf-8")
        self._git("commit", "-am", "change", "-q")
        self.after = self._git("rev-parse", "HEAD")

    def _git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *arguments],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def _run(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["/usr/bin/python3", "-B", str(Path(manager.__file__)), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_full_scan_cli_emits_exact_target_complete_json(self) -> None:
        result = self._run(
            "scan",
            "--repo",
            str(self.repo),
            "--base",
            self.before,
            "--head",
            self.after,
            "--full",
            "--format",
            "json",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(self.before, payload["range"]["before"])
        self.assertEqual(self.after, payload["range"]["after"])
        self.assertEqual("ruff 0.16.5", payload["analysis"]["ruff"])
        self.assertEqual(["B006"], [item["code"] for item in payload["signals"]])
        self.assertEqual(1, payload["decision"]["targets_total"])
        self.assertEqual(
            ["review-scan-suite", "auto-attention-v1"],
            [item["name"] for item in payload["decision"]["policies"]],
        )

    def test_scan_cli_requires_full_flag_and_frozen_object_ids(self) -> None:
        missing_full = self._run(
            "scan",
            "--repo",
            str(self.repo),
            "--base",
            self.before,
            "--head",
            self.after,
        )
        symbolic = self._run(
            "scan",
            "--repo",
            str(self.repo),
            "--base",
            self.before,
            "--head",
            "HEAD",
            "--full",
        )

        self.assertNotEqual(0, missing_full.returncode)
        self.assertIn("--full", missing_full.stderr)
        self.assertNotEqual(0, symbolic.returncode)
        self.assertIn("full lowercase", symbolic.stderr)

    def test_reviewer_command_records_result_and_status_needs_no_user_labels(self) -> None:
        root = Path(self.temporary.name) / "outcomes"
        result = scan_range(self.repo, self.before, self.after)
        event = build_auto_outcome(result, captured_at=100)
        store = OutcomeStore(root)
        store.append(result.repository, event)
        delivery = delivery_identity(event["event_id"], "codex", "session")
        store.record_delivery(
            result.repository,
            event["event_id"],
            delivery,
            "codex",
            delivered_at=110,
        )

        recorded = self._run(
            "record-review-outcome",
            "--root",
            str(root),
            "--repository",
            result.repository.digest,
            "--event",
            event["event_id"],
            "--delivery",
            delivery,
            "--finding-count",
            "1",
        )
        status = self._run("outcome-status", "--root", str(root))

        self.assertEqual(0, recorded.returncode, recorded.stderr)
        self.assertEqual("findings", json.loads(recorded.stdout)["result"])
        self.assertEqual(0, status.returncode, status.stderr)
        summary = json.loads(status.stdout)
        self.assertEqual(1, summary["reviews"]["with_findings"])
        self.assertEqual(0, summary["deliveries"]["awaiting_review"])


if __name__ == "__main__":
    unittest.main()
