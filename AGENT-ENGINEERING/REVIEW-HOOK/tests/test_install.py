from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from scripts import review_hook as manager
from runtime.review_core import EXPECTED_DIFF_REVIEW

REAL_HOST_CLI_VERSION = manager._host_cli_version


class ReviewHookInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.codex_home = self.root / "codex-home"
        self.kimi_home = self.root / "kimi-home"
        self.antigravity_home = self.root / "antigravity-config"
        version_patch = mock.patch.object(
            manager,
            "_host_cli_version",
            side_effect=lambda host: manager.SUPPORTED_HOST_CLI[host][1],
        )
        version_patch.start()
        self.addCleanup(version_patch.stop)

    def _expected(self, host: str = "codex") -> dict:
        return manager.expected_manifest(host)

    def _install(self, host: str = "codex", home: Path | None = None) -> dict:
        defaults = {
            "codex": self.codex_home,
            "kimi": self.kimi_home,
            "antigravity": self.antigravity_home,
        }
        selected_home = home or defaults[host]
        return manager.install([host], {host: selected_home}, True)

    def _kimi_config_fixture(self) -> tuple[Path, bytes, Path]:
        canonical = self.kimi_home / "config.toml"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        base = b'default_model = "fixture"\n'
        canonical.write_bytes(base)
        desired = self.root / "desired-kimi-config.toml"
        desired.write_bytes(
            base
            + b"\n[[hooks]]\n"
            + b'event = "PreToolUse"\n'
            + b'matcher = "^Bash$"\n'
            + b"command = 'exec /usr/bin/python3 -B \"$KIMI_CODE_HOME/hooks/"
            + b"review-after-commit/hosts/kimi/adapter.py\"'\n"
            + b"timeout = 30\n"
            + b"\n[[hooks]]\n"
            + b'event = "Stop"\n'
            + b"command = 'exec /usr/bin/python3 -B \"$KIMI_CODE_HOME/hooks/"
            + b"review-after-commit/hosts/kimi/adapter.py\"'\n"
            + b"timeout = 30\n"
        )
        return canonical, base, desired

    def test_validate_builds_allowlisted_bundles_with_expected_modes(self) -> None:
        validation = manager.validate_sources(["codex", "kimi", "antigravity"])

        self.assertEqual(32, validation["codex"]["files"])
        self.assertEqual(29, validation["kimi"]["files"])
        self.assertEqual(31, validation["antigravity"]["files"])
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            bundle = Path(temporary) / "bundle"
            expected = self._expected("codex")
            manager.build_bundle("codex", bundle, expected)
            manager.validate_bundle(bundle, expected)
            self.assertEqual(
                0o755,
                stat.S_IMODE(
                    (bundle / "hosts/codex/adapter.py").stat().st_mode
                ),
            )
            self.assertEqual(
                0o755,
                stat.S_IMODE((bundle / "assets/ruff").stat().st_mode),
            )
            self.assertEqual(
                manager.RUFF_ASSET_SHA256,
                manager._sha256(bundle / "assets/ruff"),
            )
            version = subprocess.run(
                [str(bundle / "assets/ruff"), "--version"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, version.returncode, version.stderr)
            self.assertEqual(manager.RUFF_VERSION, version.stdout.strip())
            self.assertNotIn(
                "trusted_hash",
                (bundle / "profile.config.toml").read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "REVIEW_AFTER_COMMIT_MODE=",
                (bundle / "profile.config.toml").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                (manager.SOURCE_ROOT / "shell/review-after-commit.bash").read_bytes(),
                (bundle / "shell/review-after-commit.bash").read_bytes(),
            )
            self.assertFalse(any(path.name == "__pycache__" for path in bundle.rglob("*")))

    def test_source_validation_rejects_ruff_or_auto_policy_drift(self) -> None:
        with mock.patch.object(manager, "RUFF_ASSET_SHA256", "0" * 64):
            with self.assertRaisesRegex(manager.ManagementError, "pinned digest"):
                manager._validate_review_scan_sources()

        original = manager._load_json_object

        def disable_auto(path):
            value = original(path)
            if path.name == "auto-attention-v1.json":
                value["automatic_delivery"] = False
            return value

        with mock.patch.object(manager, "_load_json_object", side_effect=disable_auto):
            with self.assertRaisesRegex(manager.ManagementError, "active for dogfooding"):
                manager._validate_review_scan_sources()

    def test_built_bundle_runs_review_scan_with_its_offline_ruff_asset(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            temporary_root = Path(temporary)
            bundle = temporary_root / "bundle"
            manager.build_bundle("codex", bundle, self._expected("codex"))
            repo = temporary_root / "repo"
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email", "bundle@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.name", "Bundle Test"],
                check=True,
            )
            module = repo / "module.py"
            module.write_text("def choose(items=None):\n    return items\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "module.py"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
            before = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            module.write_text("def choose(items=[]):\n    return items\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "commit", "-am", "change", "-q"], check=True)
            after = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            script = (
                "import json,sys;"
                "sys.path.insert(0,sys.argv[1]);"
                "from runtime.analysis.evidence_package import scan_range;"
                "r=scan_range(__import__('pathlib').Path(sys.argv[2]),sys.argv[3],sys.argv[4]);"
                "print(json.dumps({'ruff':r.evidence.ruff_version,'codes':[s.code for s in r.evidence.signals]}))"
            )
            environment = os.environ.copy()
            environment.pop("REVIEW_HOOK_RUFF", None)
            environment["PATH"] = "/usr/bin:/bin"

            result = subprocess.run(
                ["/usr/bin/python3", "-B", "-c", script, str(bundle), str(repo), before, after],
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(manager.RUFF_VERSION, payload["ruff"])
        self.assertEqual(["B006"], payload["codes"])

    def test_dry_run_writes_nothing_and_lists_exact_destination(self) -> None:
        plan = manager.install(
            ["codex"], {"codex": self.codex_home}, apply=False
        )

        self.assertFalse(self.codex_home.exists())
        self.assertEqual("absent", plan["operations"][0]["before"])
        self.assertEqual(
            str(self.codex_home / "hooks/review-after-commit"),
            plan["operations"][0]["destination"],
        )
        self.assertEqual([], plan["results"])

    def test_clean_install_is_current_idempotent_and_receipted(self) -> None:
        first = self._install()
        destination = manager.destination_for("codex", self.codex_home)
        expected = self._expected()

        self.assertTrue(destination.is_symlink())
        self.assertEqual("current", manager.classify("codex", self.codex_home, expected)["status"])
        receipt_path = Path(first["results"][0]["receipt"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual("active", receipt["phase"])
        self.assertEqual(expected["bundle_digest"], receipt["bundle_digest"])
        self.assertEqual(
            {
                "schema",
                "transaction",
                "phase",
                "host",
                "destination",
                "had_previous",
                "backup",
                "release",
                "bundle_digest",
                "before_status",
                "prepared_at",
                "installed_at",
            },
            set(receipt),
        )
        manifest = json.loads(
            (destination.resolve() / manager.MANIFEST_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(expected["files"], manifest["files"])
        self.assertEqual(expected["policy_hashes"], manifest["policy_hashes"])
        self.assertEqual(manager.RUFF_VERSION, manifest["ruff_version"])
        self.assertEqual(asdict(EXPECTED_DIFF_REVIEW), manifest["expected_skill"])
        receipts_before = sorted(receipt_path.parent.glob("*.json"))

        second = self._install()

        self.assertEqual("already-current", second["results"][0]["status"])
        self.assertEqual(receipts_before, sorted(receipt_path.parent.glob("*.json")))

    def test_install_and_rollback_to_absent_are_recoverable(self) -> None:
        self._install()
        dry_run = manager.rollback("codex", self.codex_home, False)
        self.assertTrue(manager.destination_for("codex", self.codex_home).is_symlink())

        applied = manager.rollback("codex", self.codex_home, True)

        self.assertEqual("absent", dry_run["restore"])
        self.assertIn("rollback_receipt", applied)
        self.assertEqual(
            "absent",
            manager.classify("codex", self.codex_home, self._expected())["status"],
        )
        replaced = json.loads(
            Path(applied["rollback_receipt"]).read_text(encoding="utf-8")
        )["replaced_bundle"]
        self.assertTrue(Path(replaced).is_symlink())

    def test_known_legacy_link_is_backed_up_and_restored(self) -> None:
        legacy = self.root / "legacy-source"
        legacy.mkdir()
        core_file = legacy / "review_after_commit_core.py"
        core_file.write_text("legacy core\n", encoding="utf-8")
        legacy_digest = hashlib.sha256(core_file.read_bytes()).hexdigest()
        destination = manager.destination_for("codex", self.codex_home)
        destination.parent.mkdir(parents=True)
        destination.symlink_to(legacy)

        with mock.patch.object(manager, "LEGACY_CORE_SHA256", legacy_digest):
            self.assertEqual(
                "legacy-symlink",
                manager.classify("codex", self.codex_home, self._expected())["status"],
            )
            installed = self._install()
            receipt = json.loads(
                Path(installed["results"][0]["receipt"]).read_text(encoding="utf-8")
            )
            self.assertTrue(Path(receipt["backup"]).is_symlink())
            manager.rollback("codex", self.codex_home, True)

        self.assertTrue(destination.is_symlink())
        self.assertEqual(legacy.resolve(), destination.resolve())

    def test_unknown_broken_and_real_destinations_are_refused_unchanged(self) -> None:
        unknown_target = self.root / "unknown-target"
        unknown_target.mkdir()
        cases = (
            ("unrecognized", unknown_target),
            ("broken", self.root / "missing-target"),
            ("unrecognized", None),
        )

        # Exercise the three shapes independently so each refusal starts from
        # a fresh home and cannot be confused with a prior case.
        for index, (expected_status, link_target) in enumerate(cases):
            home = self.root / "refusal-{}".format(index)
            target = manager.destination_for("codex", home)
            target.parent.mkdir(parents=True)
            if link_target is not None:
                target.symlink_to(link_target)
            else:
                target.mkdir()
                (target / "owner.txt").write_text("unowned\n", encoding="utf-8")
            before_link = os.readlink(target) if target.is_symlink() else None
            with self.assertRaisesRegex(manager.ManagementError, "refusing"):
                self._install(home=home)
            self.assertEqual(
                expected_status,
                manager.classify("codex", home, self._expected())["status"],
            )
            if before_link is not None:
                self.assertEqual(before_link, os.readlink(target))
            else:
                self.assertEqual("unowned\n", (target / "owner.txt").read_text())

    def _fake_host_cli_path(self, executable: str, script_body: str) -> str:
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        script = bin_dir / executable
        script.write_text("#!/bin/sh\n" + script_body + "\n", encoding="utf-8")
        script.chmod(0o755)
        return str(bin_dir)

    def test_host_cli_newer_than_captured_version_installs_and_is_reported(self) -> None:
        fake_path = self._fake_host_cli_path("codex", "echo 'codex-cli 9.9.9'")
        expected = self._expected()

        with mock.patch.object(
            manager, "_host_cli_version", REAL_HOST_CLI_VERSION
        ), mock.patch.dict(os.environ, {"PATH": fake_path}):
            self._install()
            status = manager.inspect_status("codex", self.codex_home)

        self.assertEqual("current", status["status"])
        self.assertEqual(
            {
                "status": "available",
                "captured_cli": manager.SUPPORTED_HOST_CLI["codex"][1],
                "actual_cli": "codex-cli 9.9.9",
            },
            status["host_contract"],
        )
        self.assertEqual(expected["bundle_digest"], status["installed_bundle_digest"])

    def test_host_cli_that_cannot_report_a_version_is_rejected(self) -> None:
        cases = {
            "missing": None,
            "failing": "echo 'boom' >&2; exit 1",
            "silent": "exit 0",
        }
        for name, script_body in cases.items():
            with self.subTest(name):
                fake_path = str(self.root / name)
                if script_body is not None:
                    fake_path = self._fake_host_cli_path("kimi", script_body)
                with mock.patch.dict(os.environ, {"PATH": fake_path}):
                    with self.assertRaisesRegex(manager.ManagementError, "kimi CLI"):
                        REAL_HOST_CLI_VERSION("kimi")

    def test_status_reports_unavailable_host_cli_without_hiding_destination(self) -> None:
        expected = self._expected()
        self._install()

        with mock.patch.object(
            manager,
            "_host_cli_version",
            side_effect=manager.ManagementError("fixture host missing"),
        ):
            status = manager.inspect_status("codex", self.codex_home)

        self.assertEqual("current", status["status"])
        self.assertEqual("unavailable", status["host_contract"]["status"])
        self.assertEqual(
            manager.SUPPORTED_HOST_CLI["codex"][1],
            status["host_contract"]["captured_cli"],
        )
        self.assertEqual(expected["bundle_digest"], status["installed_bundle_digest"])
        self.assertEqual(expected["bundle_digest"], status["source_contract"]["bundle_digest"])
        self.assertEqual(manager.RUFF_VERSION, status["source_contract"]["ruff_version"])
        self.assertEqual(0, status["runtime"]["events"]["count"])

    def test_unavailable_host_cli_blocks_install_before_fake_home_mutation(self) -> None:
        with mock.patch.object(
            manager,
            "_host_cli_version",
            side_effect=manager.ManagementError("fixture host missing"),
        ):
            with self.assertRaisesRegex(manager.ManagementError, "fixture host missing"):
                self._install()

        self.assertFalse(self.codex_home.exists())

    def test_local_modification_is_reported_and_never_overwritten(self) -> None:
        self._install()
        destination = manager.destination_for("codex", self.codex_home)
        changed = destination.resolve() / "runtime/review_core.py"
        original = changed.read_text(encoding="utf-8")
        changed.write_text(original + "# local owner change\n", encoding="utf-8")

        status = manager.classify("codex", self.codex_home, self._expected())
        self.assertEqual("locally-modified", status["status"])
        with self.assertRaisesRegex(manager.ManagementError, "locally-modified"):
            self._install()
        self.assertTrue(changed.read_text(encoding="utf-8").endswith("owner change\n"))

    def test_stale_unmodified_release_upgrades_and_can_restore_previous(self) -> None:
        self._install()
        destination = manager.destination_for("codex", self.codex_home)
        release = destination.resolve()
        old_release = release.parent / "old-release"
        release.rename(old_release)
        destination.unlink()
        destination.symlink_to(old_release)
        manifest_path = old_release / manager.MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["bundle_digest"] = "sha256:" + "0" * 64
        manifest_path.write_bytes(manager._json_bytes(manifest))
        os.chmod(manifest_path, 0o644)
        self.assertEqual(
            "stale",
            manager.classify("codex", self.codex_home, self._expected())["status"],
        )

        self._install()
        self.assertEqual(
            "current",
            manager.classify("codex", self.codex_home, self._expected())["status"],
        )
        manager.rollback("codex", self.codex_home, True)
        self.assertEqual(old_release.resolve(), destination.resolve())

    def test_all_hosts_are_preflighted_before_first_mutation(self) -> None:
        kimi_destination = manager.destination_for("kimi", self.kimi_home)
        kimi_destination.parent.mkdir(parents=True)
        kimi_destination.mkdir()
        (kimi_destination / "owner.txt").write_text("unowned\n", encoding="utf-8")

        with self.assertRaisesRegex(manager.ManagementError, "refusing kimi"):
            manager.install(
                ["codex", "kimi"],
                {"codex": self.codex_home, "kimi": self.kimi_home},
                True,
            )

        self.assertFalse(self.codex_home.exists())
        self.assertEqual("unowned\n", (kimi_destination / "owner.txt").read_text())

    def test_later_host_failure_reports_partial_completion(self) -> None:
        original = manager._install_one

        def fail_kimi(host, home, expected, before_status):
            if host == "kimi":
                raise RuntimeError("injected later-host failure")
            return original(host, home, expected, before_status)

        with mock.patch.object(manager, "_install_one", side_effect=fail_kimi):
            with self.assertRaisesRegex(manager.ManagementError, "completed host transaction"):
                manager.install(
                    ["codex", "kimi"],
                    {"codex": self.codex_home, "kimi": self.kimi_home},
                    True,
                )

        self.assertEqual(
            "current",
            manager.classify("codex", self.codex_home, self._expected("codex"))["status"],
        )
        self.assertEqual(
            "absent",
            manager.classify("kimi", self.kimi_home, self._expected("kimi"))["status"],
        )

    def test_post_activation_failure_restores_old_or_absent_pointer(self) -> None:
        original_write = manager._write_json_atomic

        def fail_active_receipt(path, value):
            if isinstance(value, dict) and value.get("phase") == "active":
                raise OSError("injected receipt finalization failure")
            return original_write(path, value)

        with mock.patch.object(manager, "_write_json_atomic", side_effect=fail_active_receipt):
            with self.assertRaisesRegex(manager.ManagementError, "install failed"):
                self._install()

        destination = manager.destination_for("codex", self.codex_home)
        self.assertFalse(os.path.lexists(destination))
        failed_new = list(
            (manager.control_root(self.codex_home) / "backups").glob("*/failed-new")
        )
        self.assertEqual(1, len(failed_new))
        self.assertTrue(failed_new[0].is_symlink())

    def test_selected_profile_is_local_and_preserves_trust_suffix(self) -> None:
        self._install()
        selected = self.root / "selected-codex-home"
        dry = manager.materialize_codex_profile(
            self.codex_home, selected, apply=False
        )
        self.assertEqual("materialize", dry["action"])
        self.assertNotIn("template_digest", dry)
        self.assertFalse(selected.exists())

        manager.materialize_codex_profile(self.codex_home, selected, apply=True)
        profile = selected / "review-after-commit.config.toml"
        profile_receipt = json.loads(
            (selected / "review-after-commit.profile-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("review-hook-profile-receipt/v1", profile_receipt["schema"])
        self.assertEqual(
            {"schema", "profile", "static_digest", "preimage", "materialized_at"},
            set(profile_receipt),
        )
        self.assertTrue(profile.is_file())
        self.assertFalse(profile.is_symlink())
        self.assertEqual(0o600, stat.S_IMODE(profile.stat().st_mode))
        with profile.open("a", encoding="utf-8") as stream:
            stream.write(
                '\n[hooks.state."fixture:pre_tool_use:0:0"]\n'
                'trusted_hash = "sha256:fixture"\n'
            )
        trusted = profile.read_bytes()

        result = manager.materialize_codex_profile(
            self.codex_home, selected, apply=True
        )

        self.assertEqual("none", result["action"])
        self.assertTrue(result["trust_suffix_preserved"])
        self.assertEqual(trusted, profile.read_bytes())

    def test_selected_profile_static_modification_is_refused(self) -> None:
        self._install()
        selected = self.root / "selected-codex-home"
        manager.materialize_codex_profile(self.codex_home, selected, apply=True)
        profile = selected / "review-after-commit.config.toml"
        profile.write_text(
            profile.read_text(encoding="utf-8").replace(
                'service_tier = "default"', 'service_tier = "fast"'
            ),
            encoding="utf-8",
        )
        changed = profile.read_bytes()

        with self.assertRaisesRegex(manager.ManagementError, "modified locally"):
            manager.materialize_codex_profile(
                self.codex_home, selected, apply=True
            )
        self.assertEqual(changed, profile.read_bytes())

    def test_exact_legacy_profile_symlink_migrates_and_rolls_back(self) -> None:
        self._install()
        selected = self.root / "selected-codex-home"
        selected.mkdir()
        template = (
            manager.destination_for("codex", self.codex_home)
            / "profile.config.toml"
        )
        profile = selected / "review-after-commit.config.toml"
        profile.symlink_to(template)

        dry = manager.materialize_codex_profile(
            self.codex_home, selected, apply=False
        )

        self.assertEqual("migrate-legacy-symlink", dry["action"])
        self.assertTrue(profile.is_symlink())
        manager.materialize_codex_profile(self.codex_home, selected, apply=True)
        self.assertTrue(profile.is_file())
        self.assertFalse(profile.is_symlink())
        with profile.open("a", encoding="utf-8") as stream:
            stream.write(
                '\n[hooks.state."fixture:pre_tool_use:0:0"]\n'
                'trusted_hash = "sha256:fixture"\n'
            )

        rollback = manager.rollback_codex_profile(selected, apply=True)

        self.assertTrue(profile.is_symlink())
        self.assertEqual(str(template), os.readlink(profile))
        self.assertFalse(
            (selected / "review-after-commit.profile-receipt.json").exists()
        )
        backup = Path(rollback["backup_profile"])
        self.assertTrue(backup.is_file())
        self.assertIn("trusted_hash", backup.read_text(encoding="utf-8"))

    def test_unknown_profile_symlink_is_refused_unchanged(self) -> None:
        self._install()
        selected = self.root / "selected-codex-home"
        selected.mkdir()
        unknown = self.root / "unowned-profile.toml"
        unknown.write_text("unowned = true\n", encoding="utf-8")
        profile = selected / "review-after-commit.config.toml"
        profile.symlink_to(unknown)

        with self.assertRaisesRegex(manager.ManagementError, "unknown profile symlink"):
            manager.materialize_codex_profile(
                self.codex_home, selected, apply=True
            )

        self.assertTrue(profile.is_symlink())
        self.assertEqual(str(unknown), os.readlink(profile))

    def test_profile_receipt_failure_restores_exact_legacy_symlink(self) -> None:
        self._install()
        selected = self.root / "selected-codex-home"
        selected.mkdir()
        template = (
            manager.destination_for("codex", self.codex_home)
            / "profile.config.toml"
        )
        profile = selected / "review-after-commit.config.toml"
        profile.symlink_to(template)

        with mock.patch.object(
            manager,
            "_write_json_atomic",
            side_effect=OSError("injected profile receipt failure"),
        ):
            with self.assertRaisesRegex(OSError, "injected profile receipt failure"):
                manager.materialize_codex_profile(
                    self.codex_home, selected, apply=True
                )

        self.assertTrue(profile.is_symlink())
        self.assertEqual(str(template), os.readlink(profile))
        self.assertFalse(
            (selected / "review-after-commit.profile-receipt.json").exists()
        )

    def test_new_profile_rolls_back_to_absent_without_losing_local_copy(self) -> None:
        self._install()
        selected = self.root / "selected-codex-home"
        manager.materialize_codex_profile(self.codex_home, selected, apply=True)
        profile = selected / "review-after-commit.config.toml"
        original = profile.read_bytes()

        dry = manager.rollback_codex_profile(selected, apply=False)
        applied = manager.rollback_codex_profile(selected, apply=True)

        self.assertEqual("absent", dry["restore"])
        self.assertFalse(profile.exists())
        self.assertFalse(
            (selected / "review-after-commit.profile-receipt.json").exists()
        )
        self.assertEqual(original, Path(applied["backup_profile"]).read_bytes())

    def test_installed_bundle_can_materialize_and_roll_back_profile(self) -> None:
        self._install()
        bundle = manager.destination_for("codex", self.codex_home)
        installed_manager = bundle / "scripts/review_hook.py"
        selected = self.root / "selected-codex-home"

        materialized = subprocess.run(
            [
                "/usr/bin/python3",
                "-B",
                str(installed_manager),
                "materialize-profile",
                "--canonical-home",
                str(self.codex_home),
                "--selected-home",
                str(selected),
                "--apply",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        rolled_back = subprocess.run(
            [
                "/usr/bin/python3",
                "-B",
                str(installed_manager),
                "rollback-profile",
                "--selected-home",
                str(selected),
                "--apply",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, materialized.returncode, materialized.stderr)
        self.assertEqual("materialize", json.loads(materialized.stdout)["action"])
        self.assertEqual(0, rolled_back.returncode, rolled_back.stderr)
        self.assertEqual("absent", json.loads(rolled_back.stdout)["restore"])
        self.assertFalse(
            (selected / "review-after-commit.config.toml").exists()
        )

    def test_kimi_stale_legacy_config_migrates_and_rolls_back_exactly(self) -> None:
        self._install("kimi")
        canonical, base, desired = self._kimi_config_fixture()
        selected = self.root / "selected-kimi-home"
        selected.mkdir()
        config = selected / "config.toml"
        legacy = (
            base
            + b"\n[[hooks]]\n"
            + b'event = "PreToolUse"\n'
            + b"command = 'exec /usr/bin/python3 \"$KIMI_CODE_HOME/hooks/"
            + b"review-after-commit/kimi_hook.py\"'\n"
            + b"timeout = 30\n"
        )
        config.write_bytes(legacy)
        os.chmod(config, 0o640)
        canonical_marker = selected / ".canonical-config.sha256"
        generated_marker = selected / ".generated-config.sha256"
        canonical_marker.write_text(
            "0" * 64 + "\n", encoding="utf-8"
        )
        generated_marker.write_text(
            hashlib.sha256(legacy).hexdigest() + "\n", encoding="utf-8"
        )
        preimages = {
            path.name: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
            for path in (config, canonical_marker, generated_marker)
        }

        dry = manager.materialize_kimi_config(
            canonical, selected, desired, apply=False
        )
        manager.materialize_kimi_config(canonical, selected, desired, apply=True)

        self.assertEqual("migrate-legacy-config", dry["action"])
        self.assertEqual(desired.read_bytes(), config.read_bytes())
        receipt_path = selected / "review-after-commit.kimi-config-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "schema",
                "selected_home",
                "config",
                "current_digest",
                "canonical_digest",
                "preimage",
                "materialized_at",
            },
            set(receipt),
        )
        rolled_back = manager.rollback_kimi_config(selected, apply=True)
        for path in (config, canonical_marker, generated_marker):
            payload, mode = preimages[path.name]
            self.assertEqual(payload, path.read_bytes())
            self.assertEqual(mode, stat.S_IMODE(path.stat().st_mode))
        self.assertFalse(
            (selected / "review-after-commit.kimi-config-receipt.json").exists()
        )
        self.assertTrue(Path(rolled_back["backup_config"]).is_file())

    def test_kimi_unreceipted_unknown_config_is_refused_unchanged(self) -> None:
        self._install("kimi")
        canonical, _, desired = self._kimi_config_fixture()
        selected = self.root / "selected-kimi-home"
        selected.mkdir()
        config = selected / "config.toml"
        config.write_text("unowned = true\n", encoding="utf-8")

        with self.assertRaisesRegex(manager.ManagementError, "unrecognized Kimi"):
            manager.materialize_kimi_config(
                canonical, selected, desired, apply=True
            )

        self.assertEqual("unowned = true\n", config.read_text(encoding="utf-8"))

    def test_kimi_legacy_config_requires_ascii_checksum_markers(self) -> None:
        self._install("kimi")
        canonical, base, desired = self._kimi_config_fixture()
        selected = self.root / "selected-kimi-home"
        selected.mkdir()
        legacy = base + b"\ncommand = 'kimi_hook.py'\n"
        (selected / "config.toml").write_bytes(legacy)
        (selected / ".canonical-config.sha256").write_bytes(
            hashlib.sha256(base).hexdigest().encode("ascii") + b"\xc3\xa9\n"
        )
        (selected / ".generated-config.sha256").write_text(
            hashlib.sha256(legacy).hexdigest() + "\n", encoding="ascii"
        )

        with self.assertRaisesRegex(manager.ManagementError, "unrecognized Kimi"):
            manager.materialize_kimi_config(
                canonical, selected, desired, apply=True
            )

        self.assertEqual(legacy, (selected / "config.toml").read_bytes())

    def test_kimi_config_receipt_failure_restores_absent_preimage(self) -> None:
        self._install("kimi")
        canonical, _, desired = self._kimi_config_fixture()
        selected = self.root / "selected-kimi-home"

        with mock.patch.object(
            manager,
            "_write_json_atomic",
            side_effect=OSError("injected Kimi config receipt failure"),
        ):
            with self.assertRaisesRegex(
                OSError, "injected Kimi config receipt failure"
            ):
                manager.materialize_kimi_config(
                    canonical, selected, desired, apply=True
                )

        for name in (
            "config.toml",
            ".canonical-config.sha256",
            ".generated-config.sha256",
            "review-after-commit.kimi-config-receipt.json",
        ):
            self.assertFalse((selected / name).exists())

    def test_installed_kimi_manager_owns_config_apply_and_rollback(self) -> None:
        self._install("kimi")
        canonical, _, desired = self._kimi_config_fixture()
        selected = self.root / "selected-kimi-home"
        installed_manager = (
            manager.destination_for("kimi", self.kimi_home)
            / "scripts/review_hook.py"
        )

        applied = subprocess.run(
            [
                "/usr/bin/python3",
                "-B",
                str(installed_manager),
                "materialize-kimi-config",
                "--canonical-config",
                str(canonical),
                "--selected-home",
                str(selected),
                "--desired-config",
                str(desired),
                "--apply",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        rolled_back = subprocess.run(
            [
                "/usr/bin/python3",
                "-B",
                str(installed_manager),
                "rollback-kimi-config",
                "--selected-home",
                str(selected),
                "--apply",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, applied.returncode, applied.stderr)
        self.assertEqual("materialize", json.loads(applied.stdout)["action"])
        self.assertEqual(0, rolled_back.returncode, rolled_back.stderr)
        self.assertEqual("absent", json.loads(rolled_back.stdout)["restore"])
        self.assertFalse((selected / "config.toml").exists())

    def test_antigravity_install_is_disabled_and_preserves_shared_registry(self) -> None:
        self.antigravity_home.mkdir(parents=True)
        config_path = self.antigravity_home / "config.json"
        imports_path = self.antigravity_home / "import_manifest.json"
        config_path.write_text(
            json.dumps(
                {
                    "theme": "fixture",
                    "plugins": {"other-plugin": {"enabled": True}},
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        imports_path.write_text(
            json.dumps(
                {
                    "imports": [
                        {
                            "name": "other-plugin",
                            "source": "antigravity",
                            "components": ["skills"],
                            "importedAt": "2026-01-01T00:00:00Z",
                        }
                    ]
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        result = self._install("antigravity")
        destination = manager.destination_for(
            "antigravity", self.antigravity_home
        )
        status = manager.inspect_status("antigravity", self.antigravity_home)

        self.assertTrue(destination.is_symlink())
        self.assertEqual("installed-disabled", status["status"])
        self.assertFalse(status["plugin"]["enabled"])
        self.assertTrue(status["plugin"]["registered"])
        self.assertTrue(status["plugin"]["dormant_without_selection"])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual("fixture", config["theme"])
        self.assertTrue(config["plugins"]["other-plugin"]["enabled"])
        self.assertFalse(config["plugins"]["review-after-commit"]["enabled"])
        imports = json.loads(imports_path.read_text(encoding="utf-8"))["imports"]
        self.assertEqual("other-plugin", imports[0]["name"])
        self.assertEqual("review-after-commit", imports[1]["name"])
        receipt = json.loads(
            Path(result["results"][0]["receipt"]).read_text(encoding="utf-8")
        )
        self.assertFalse(receipt["antigravity_registry"]["enabled_after"])

    def test_antigravity_enablement_is_separate_reversible_and_idempotent(self) -> None:
        self._install("antigravity")
        dry = manager.set_antigravity_enabled(
            self.antigravity_home, True, apply=False
        )
        self.assertEqual("enable", dry["action"])
        self.assertEqual(
            "installed-disabled",
            manager.inspect_status("antigravity", self.antigravity_home)["status"],
        )

        enabled = manager.set_antigravity_enabled(
            self.antigravity_home, True, apply=True
        )
        self.assertIn("receipt", enabled)
        self.assertEqual(
            "current",
            manager.inspect_status("antigravity", self.antigravity_home)["status"],
        )
        repeated = manager.set_antigravity_enabled(
            self.antigravity_home, True, apply=True
        )
        self.assertEqual("none", repeated["action"])

        disabled = manager.set_antigravity_enabled(
            self.antigravity_home, False, apply=True
        )
        self.assertIn("receipt", disabled)
        self.assertEqual(
            "installed-disabled",
            manager.inspect_status("antigravity", self.antigravity_home)["status"],
        )

    def test_antigravity_rollback_restores_exact_shared_files(self) -> None:
        self.antigravity_home.mkdir(parents=True)
        config_path = self.antigravity_home / "config.json"
        imports_path = self.antigravity_home / "import_manifest.json"
        original_config = b'{"unrelated":true}\n'
        original_imports = b'{"imports":[]}\n'
        config_path.write_bytes(original_config)
        imports_path.write_bytes(original_imports)
        self._install("antigravity")

        manager.rollback("antigravity", self.antigravity_home, True)

        self.assertEqual(original_config, config_path.read_bytes())
        self.assertEqual(original_imports, imports_path.read_bytes())
        self.assertEqual(
            "absent",
            manager.classify(
                "antigravity",
                self.antigravity_home,
                self._expected("antigravity"),
            )["status"],
        )

    def test_antigravity_partial_registry_install_is_recovered_exactly(self) -> None:
        self.antigravity_home.mkdir(parents=True)
        config_path = self.antigravity_home / "config.json"
        imports_path = self.antigravity_home / "import_manifest.json"
        original_config = b'{"unrelated":true}\n'
        original_imports = b'{"imports":[]}\n'
        config_path.write_bytes(original_config)
        imports_path.write_bytes(original_imports)
        original_write = manager._write_json_atomic

        def fail_import_write(path, value):
            if path == imports_path:
                raise OSError("injected import registry failure")
            return original_write(path, value)

        with mock.patch.object(
            manager, "_write_json_atomic", side_effect=fail_import_write
        ):
            with self.assertRaisesRegex(manager.ManagementError, "install failed"):
                self._install("antigravity")

        self.assertEqual(original_config, config_path.read_bytes())
        self.assertEqual(original_imports, imports_path.read_bytes())
        self.assertFalse(
            os.path.lexists(
                manager.destination_for("antigravity", self.antigravity_home)
            )
        )

    def test_antigravity_partial_registry_rollback_is_recovered_exactly(self) -> None:
        self._install("antigravity")
        config_path = self.antigravity_home / "config.json"
        imports_path = self.antigravity_home / "import_manifest.json"
        installed_config = config_path.read_bytes()
        installed_imports = imports_path.read_bytes()
        original_restore = manager._restore_file
        injected = False

        def fail_first_import_restore(path, payload):
            nonlocal injected
            if path == imports_path and not injected:
                injected = True
                raise OSError("injected rollback registry failure")
            return original_restore(path, payload)

        with mock.patch.object(
            manager, "_restore_file", side_effect=fail_first_import_restore
        ):
            with self.assertRaisesRegex(OSError, "injected rollback registry failure"):
                manager.rollback("antigravity", self.antigravity_home, True)

        self.assertEqual(installed_config, config_path.read_bytes())
        self.assertEqual(installed_imports, imports_path.read_bytes())
        self.assertEqual(
            "installed-disabled",
            manager.classify(
                "antigravity",
                self.antigravity_home,
                self._expected("antigravity"),
            )["status"],
        )

    def test_antigravity_malformed_registry_is_refused_before_mutation(self) -> None:
        self.antigravity_home.mkdir(parents=True)
        config = self.antigravity_home / "config.json"
        config.write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(manager.ManagementError, "config.json"):
            self._install("antigravity")
        self.assertEqual("not json", config.read_text(encoding="utf-8"))
        self.assertFalse(
            os.path.lexists(
                manager.destination_for("antigravity", self.antigravity_home)
            )
        )

    def test_cli_apply_status_and_rollback_use_only_the_fake_home(self) -> None:
        home = self.root / "cli-codex-home"
        home_option = "codex={}".format(home)

        def run(*arguments: str) -> dict:
            result = subprocess.run(
                ["/usr/bin/python3", "-B", str(Path(manager.__file__)), *arguments],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            return json.loads(result.stdout)

        dry = run("install", "--host", "codex", "--home", home_option)
        self.assertFalse(home.exists())
        self.assertFalse(dry["apply"])

        run("install", "--host", "codex", "--home", home_option, "--apply")
        status = run("status", "--host", "codex", "--home", home_option)
        self.assertEqual("current", status["statuses"][0]["status"])
        run("rollback", "--host", "codex", "--home", home_option, "--apply")
        final_status = run("status", "--host", "codex", "--home", home_option)
        self.assertEqual("absent", final_status["statuses"][0]["status"])


if __name__ == "__main__":
    unittest.main()
