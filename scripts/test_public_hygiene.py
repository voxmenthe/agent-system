#!/usr/bin/env python3
"""Unit tests for scripts/check_public_hygiene.py."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_public_hygiene as hygiene  # noqa: E402


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=check,
    )


class PublicHygieneTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        (self.repo / "README.md").write_text("# Clean public repo\n", encoding="utf-8")
        _git(self.repo, "add", "README.md")
        _git(self.repo, "commit", "-m", "initial clean commit")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_and_stage(self, rel: str, content: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        _git(self.repo, "add", rel)

    def test_real_repo_head_passes_generic_hygiene(self) -> None:
        empty_dl = Path(self._tmp.name) / "nonexistent-denylist.txt"
        findings = hygiene.check_all(REPO_ROOT, [], use_gitleaks=False)
        self.assertEqual([], [f.format() for f in findings])
        # Also verify CLI returns 0 with --no-gitleaks and missing optional denylist.
        rc = hygiene.main(["--repo", str(REPO_ROOT), "--all", "--denylist", str(empty_dl), "--no-gitleaks"])
        self.assertEqual(0, rc)

    def test_secret_patterns_caught_and_test_sentinels_allowed(self) -> None:
        # Construct tokens dynamically so this test file itself stays hygiene-clean.
        bad_lines = "\n".join(
            [
                "live_sk = '" + "sk-" + "liveAbCdEf1234567890" + "'",
                "gh = '" + "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2" + "'",
                "slack = '" + "xox" + "b-1234567890-abcdef" + "'",
                "aws = '" + "AKIA" + "IOSFODNN7EXAMPLE" + "'",
                "-----BEGIN " + "RSA PRIVATE KEY-----",
                "auth = 'Bearer " + "ZXhhbXBsZV9yZWFsX2xvb2tpbmdfdG9rZW4" + "'",
                "OPENAI_" + "API_KEY=" + "realvalue1234567890abcd",
            ]
        )
        findings = hygiene.scan_text(bad_lines, rel_path="scripts/app.py", denylist=[])
        self.assertEqual(7, len(findings), [f.format() for f in findings])
        self.assertTrue(all(f.rule == "secret-pattern" for f in findings))

        # Synthetic test sentinels inside tests/ are allowed.
        test_lines = "\n".join(
            [
                'key = "sk-test-not-real"',
                'hdr = "Authorization: Bearer fake-claude-oauth-token"',
                'OPENAI_API_KEY="ambient-openai-key"',
            ]
        )
        test_findings = hygiene.scan_text(test_lines, rel_path="SHELL/tests/test_sample.py", denylist=[])
        self.assertEqual([], test_findings)

    def test_machine_paths_caught_and_portable_placeholders_allowed(self) -> None:
        bad = "\n".join(
            [
                "home = '" + "/Users/" + "alice_real/repos/x'",
                "disk = '" + "/Volumes/" + "cdrive/repos/x'",
                "tmp = '" + "/private/var/" + "folders/ab/cd/T/foo'",
            ]
        )
        findings = hygiene.scan_text(bad, rel_path="docs/note.md", denylist=[])
        self.assertEqual(3, len(findings), [f.format() for f in findings])
        self.assertTrue(all(f.rule == "machine-path" for f in findings))

        good = "\n".join(
            [
                "home = '/Users/me/repos/x'",
                "disk = '/Volumes/External/uv_cache'",
                "tpl = '@HOME@/repos/x'",
            ]
        )
        self.assertEqual([], hygiene.scan_text(good, rel_path="docs/note.md", denylist=[]))

    def test_emails_caught_and_example_or_license_allowed(self) -> None:
        bad_email = "contact: person@" + "private-domain.org"
        findings = hygiene.scan_text(bad_email, rel_path="docs/note.md", denylist=[])
        self.assertEqual(1, len(findings))
        self.assertEqual("email", findings[0].rule)

        # Example domains and upstream licenses are allowed.
        self.assertEqual([], hygiene.scan_text("you@example.com\nhook@example.invalid", rel_path="docs/note.md", denylist=[]))
        self.assertEqual([], hygiene.scan_text(bad_email, rel_path="AGENT-ENGINEERING/REVIEW-HOOK/assets/ruff.LICENSE", denylist=[]))

    def test_stale_monorepo_paths_caught(self) -> None:
        bad = "\n".join(
            [
                "source " + "M3" + "-BASH/.bash_agents",
                "source " + "M4" + "-BASH/.bashrc",
                "see " + "PROM" + "PTS/foo.md",
                "see " + "REFER" + "ENCE/guide.md",
                "run scripts/" + "grok-" + "X-adhoc/mkt",
                "saved in " + ".learning-" + "workspace/foo/bar.md",
            ]
        )
        findings = hygiene.scan_text(bad, rel_path="SHELL/tests/test_launcher.py", denylist=[])
        self.assertEqual(6, len(findings), [f.format() for f in findings])
        self.assertTrue(all(f.rule == "stale-monorepo-path" for f in findings))

    def test_host_owned_keys_checked_dynamically_for_json_and_toml(self) -> None:
        hosts_doc = {
            "projections": [
                {
                    "id": "claude-config",
                    "source": "config/claude/settings.json",
                    "host_owned_keys": [["model"], ["effortLevel"]],
                },
                {
                    "id": "antigravity-cli-config",
                    "source": "config/antigravity/antigravity-cli/settings.json",
                    "host_owned_keys": [["trustedWorkspaces"], ["permissions", "allow"]],
                },
                {
                    "id": "kimi-config",
                    "source": "config/kimi/config.toml",
                    "host_owned_keys": [["default_model"], ["models"]],
                },
            ]
        }
        self._write_and_stage(
            "AGENT-ENGINEERING/PERSISTENT-GUIDANCE/hosts.json",
            json.dumps(hosts_doc, indent=2),
        )
        self._write_and_stage(
            "AGENT-ENGINEERING/PERSISTENT-GUIDANCE/config/claude/settings.json",
            json.dumps({"model": "opus", "env": {}}),
        )
        self._write_and_stage(
            "AGENT-ENGINEERING/PERSISTENT-GUIDANCE/config/antigravity/antigravity-cli/settings.json",
            json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}),
        )
        self._write_and_stage(
            "AGENT-ENGINEERING/PERSISTENT-GUIDANCE/config/kimi/config.toml",
            'default_model = "k2"\n[models.k2]\nprovider = "moonshot"\n',
        )

        findings = hygiene.check_staged(self.repo, [], use_gitleaks=False)
        hok = [f for f in findings if f.rule == "host-owned-key"]
        self.assertEqual(4, len(hok), [f.format() for f in hok])
        details = " ".join(f.detail for f in hok)
        self.assertIn("model", details)
        self.assertIn("permissions.allow", details)
        self.assertIn("default_model", details)
        self.assertIn("models", details)

    def test_private_denylist_rules_allow_globs_and_require_flag(self) -> None:
        dl = Path(self._tmp.name) / "hygiene-denylist.txt"
        dl.write_text(
            "# private terms\n"
            "secretcodename\n"
            "re:private-proj-[0-9]+\n"
            "legacy-id  @allow:allowed/file.json\n",
            encoding="utf-8",
        )
        rules, errs = hygiene.load_denylist(dl, required=True)
        self.assertEqual([], errs)
        self.assertEqual(3, len(rules))

        # Matched terms must be flagged without echoing the raw term in output.
        f1 = hygiene.scan_text("uses SecretCodeName here", rel_path="a.md", denylist=rules)
        self.assertEqual(1, len(f1))
        self.assertEqual("private-denylist", f1[0].rule)
        self.assertNotIn("secretcodename", f1[0].detail.lower())

        f2 = hygiene.scan_text("repo private-proj-42", rel_path="b.md", denylist=rules)
        self.assertEqual(1, len(f2))

        # @allow skips only the allowlisted path.
        self.assertEqual([], hygiene.scan_text("id = legacy-id", rel_path="allowed/file.json", denylist=rules))
        self.assertEqual(1, len(hygiene.scan_text("id = legacy-id", rel_path="other/file.json", denylist=rules)))

        # Missing required denylist fails loudly.
        missing = Path(self._tmp.name) / "missing.txt"
        _, req_errs = hygiene.load_denylist(missing, required=True)
        self.assertEqual(1, len(req_errs))
        self.assertEqual("denylist-missing", req_errs[0].rule)

    def test_staged_mode_scans_index_not_unstaged_worktree(self) -> None:
        self._write_and_stage("clean.txt", "nothing private\n")
        # Write an unstaged violation to disk without staging it.
        (self.repo / "clean.txt").write_text("path=" + "/Users/" + "someone/x\n", encoding="utf-8")
        self.assertEqual([], hygiene.check_staged(self.repo, [], use_gitleaks=False))

        # Now stage the violation and verify --staged catches it.
        _git(self.repo, "add", "clean.txt")
        findings = hygiene.check_staged(self.repo, [], use_gitleaks=False)
        self.assertEqual(1, len(findings))
        self.assertEqual("machine-path", findings[0].rule)

    def test_commits_mode_checks_diffs_and_commit_messages(self) -> None:
        base = _git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self._write_and_stage("note.md", "clean body\n")
        _git(self.repo, "commit", "-m", "port from " + "M3" + "-BASH wrapper")
        findings = hygiene.check_commits(self.repo, f"{base}..HEAD", [], use_gitleaks=False)
        self.assertEqual(1, len(findings), [f.format() for f in findings])
        self.assertEqual("stale-monorepo-path", findings[0].rule)
        self.assertIn("message", findings[0].location)

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks not installed")
    def test_gitleaks_integration_catches_staged_token(self) -> None:
        self._write_and_stage("leak.txt", "token = " + "ghp_" + "9z8y7x6w5v4u3t2s1r0q9p8o7n6m5l4k3j2i" + "\n")
        findings = hygiene.run_gitleaks(self.repo, mode="staged")
        self.assertEqual(1, len(findings))
        self.assertEqual("gitleaks", findings[0].rule)


if __name__ == "__main__":
    unittest.main()
