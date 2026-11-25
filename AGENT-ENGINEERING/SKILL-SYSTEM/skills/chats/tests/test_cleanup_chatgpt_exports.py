from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cleanup_chatgpt_exports as cleaner


class CleanupChatGPTExportsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conv_id = "6a9f5195-b428-83e8-b7ee-45a2f92d488a"
        self.raw_transcript = {
            "schema_version": 1,
            "exported_at": "2026-09-08T00:00:00Z",
            "source": {
                "service": "chatgpt",
                "conversation_id": self.conv_id,
                "conversation_url": f"https://chatgpt.com/c/{self.conv_id}",
                "title": "Research MAI 1 Paper",
            },
            "counts": {"active_messages": 1, "visible_messages": 1},
            "messages": [{"id": "msg-1", "parts": ["hello"]}],
        }

    def test_clean_export_directory_renames_uuid_dir_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            exports_dir = Path(temporary)
            uuid_dir = exports_dir / self.conv_id
            uuid_dir.mkdir()

            md_file = uuid_dir / f"{self.conv_id}.md"
            md_file.write_text("# Old Title\nHello world\n", encoding="utf-8")

            json_file = uuid_dir / f"{self.conv_id}.json"
            json_file.write_text(json.dumps(self.raw_transcript), encoding="utf-8")

            manifest_file = uuid_dir / f"{self.conv_id}.manifest.json"
            manifest_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "complete",
                        "conversation_id": self.conv_id,
                        "files": {},
                    }
                ),
                encoding="utf-8",
            )

            # Dry run test first
            info = cleaner.inspect_export_directory(uuid_dir)
            dry_res = cleaner.clean_export_directory(info, None, dry_run=True)
            self.assertEqual("modified", dry_res["status"])
            self.assertTrue(uuid_dir.exists())

            # Real run
            real_res = cleaner.clean_export_directory(info, None, dry_run=False)
            self.assertEqual("modified", real_res["status"])

            expected_dir = exports_dir / "research-mai-1-paper"
            self.assertTrue(expected_dir.is_dir())
            self.assertFalse(uuid_dir.exists())

            expected_md = expected_dir / "research-mai-1-paper.md"
            expected_json = expected_dir / "research-mai-1-paper.json"
            expected_manifest = expected_dir / "research-mai-1-paper.manifest.json"

            self.assertTrue(expected_md.is_file())
            self.assertTrue(expected_json.is_file())
            self.assertTrue(expected_manifest.is_file())

            # Validate manifest content
            manifest = json.loads(expected_manifest.read_text(encoding="utf-8"))
            self.assertEqual("research-mai-1-paper", manifest["slug"])
            self.assertIn("research-mai-1-paper.md", manifest["files"])
            self.assertIn("research-mai-1-paper.json", manifest["files"])

            md_sha = hashlib.sha256(expected_md.read_bytes()).hexdigest()
            json_sha = hashlib.sha256(expected_json.read_bytes()).hexdigest()
            self.assertEqual(md_sha, manifest["files"]["research-mai-1-paper.md"]["sha256"])
            self.assertEqual(json_sha, manifest["files"]["research-mai-1-paper.json"]["sha256"])

            # Test idempotence on cleaned folder
            info2 = cleaner.inspect_export_directory(expected_dir)
            idempotent_res = cleaner.clean_export_directory(info2, None, dry_run=False)
            self.assertEqual("already_clean", idempotent_res["status"])

    def test_cleanup_all_with_multiple_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            exports_dir = Path(temporary)

            # Folder 1: UUID with version suffix
            dir1 = exports_dir / f"{self.conv_id}-v2"
            dir1.mkdir()
            (dir1 / "conversation.md").write_text("# Hello", encoding="utf-8")
            (dir1 / "conversation.json").write_text(json.dumps(self.raw_transcript), encoding="utf-8")

            summary = cleaner.cleanup_all(exports_dir, dry_run=False)
            self.assertEqual("ok", summary["status"])
            self.assertEqual(1, summary["total_count"])
            self.assertEqual(1, summary["modified_count"])

            expected_dir = exports_dir / "research-mai-1-paper-v2"
            self.assertTrue(expected_dir.is_dir())
            self.assertTrue((expected_dir / "research-mai-1-paper-v2.md").is_file())
            self.assertTrue((expected_dir / "research-mai-1-paper-v2.json").is_file())
            self.assertTrue((expected_dir / "research-mai-1-paper-v2.manifest.json").is_file())

            # Second pass: zero modified
            summary2 = cleaner.cleanup_all(exports_dir, dry_run=False)
            self.assertEqual(0, summary2["modified_count"])


if __name__ == "__main__":
    unittest.main()
