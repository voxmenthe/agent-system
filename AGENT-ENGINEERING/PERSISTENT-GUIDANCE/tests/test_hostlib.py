from __future__ import annotations

import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

GUIDANCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = GUIDANCE_ROOT / "policy" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import hostlib
from hostlib import (
    GuidanceError,
    adopt,
    format_plan,
    load_host_manifest,
    plan_sync,
    rollback,
    summarize_plan,
    sync,
    verify_shared_consumers,
)
from mcpconfig import expected_mcp_outputs


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_guidance_cli():
    loader = importlib.machinery.SourceFileLoader(
        "persistent_guidance_cli", str(GUIDANCE_ROOT / "guidance")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("could not load guidance CLI for testing")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class GuidanceFixture:
    def __init__(self, base: Path) -> None:
        self.root = base / "source"
        self.home = base / "home"
        self.root.mkdir()
        self.home.mkdir()
        (self.root / "candidate-guidance").mkdir()
        (self.root / "policy" / "packs").mkdir(parents=True)
        (self.root / "policy" / "generated").mkdir()
        (self.root / "AGENTS.md").write_bytes(b"canonical-v1\n")
        (self.root / "policy" / "manifest.json").write_text("{}\n", encoding="utf-8")
        (self.root / "policy" / "packs" / "one.md").write_text(
            "# One\n", encoding="utf-8"
        )
        (self.root / "policy" / "generated" / "routing-table.md").write_text(
            "# Table\n", encoding="utf-8"
        )
        self.legacy = b"legacy\n"
        self.manifest = {
            "schema_version": 1,
            "manager_id": "test/persistent-guidance/v1",
            "state_dir": ".local/state/persistent-guidance",
            "required_hosts": ["alpha"],
            "protected_source_paths": ["candidate-guidance"],
            "projections": [
                {
                    "id": "kernel",
                    "source": "AGENTS.md",
                    "target": ".alpha/AGENTS.md",
                    "hosts": ["alpha"],
                    "adopt_sha256": [digest(self.legacy)],
                },
                {
                    "id": "policy-tree",
                    "source_tree": "policy",
                    "target_tree": ".alpha/policy",
                    "include": ["manifest.json", "generated/*.md", "packs/*.md"],
                    "hosts": ["alpha"],
                },
                {
                    "id": "new-copy",
                    "source": "AGENTS.md",
                    "target": ".new/AGENTS.md",
                    "hosts": ["alpha"],
                },
            ],
            "retirements": [
                {
                    "id": "old-copy",
                    "target": ".old/AGENTS.md",
                    "hosts": ["alpha"],
                    "adopt_sha256": [digest(self.legacy)],
                    "reason": "legacy duplicate",
                }
            ],
            "releases": [],
            "shared_consumers": [],
        }
        self.write_manifest()

    def write_manifest(self) -> None:
        (self.root / "hosts.json").write_text(
            json.dumps(self.manifest, indent=2) + "\n",
            encoding="utf-8",
        )

    def add_config(
        self,
        name: str,
        data: bytes,
        host_owned_keys: list[list[str]] | None = None,
        managed_keys: list[list[str]] | None = None,
    ) -> tuple[Path, Path]:
        """Add an independent one-to-one config projection; returns (source, target)."""
        source = self.root / "config" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(data)
        projection = {
            "id": f"{name}-config",
            "source": f"config/{name}",
            "target": f".alpha/{name}",
            "hosts": ["alpha"],
            "independent": True,
        }
        if host_owned_keys is not None:
            projection["host_owned_keys"] = host_owned_keys
        if managed_keys is not None:
            projection["managed_keys"] = managed_keys
        self.manifest["projections"].append(projection)
        self.write_manifest()
        return source, self.home / ".alpha" / name

    def add_tree(self, name: str, source_tree: str, include: list[str]) -> None:
        """Add an independent tree projection into ~/.alpha/<name>."""
        self.manifest["projections"].append(
            {
                "id": name,
                "source_tree": source_tree,
                "target_tree": f".alpha/{name}",
                "include": include,
                "hosts": ["alpha"],
                "independent": True,
            }
        )
        self.write_manifest()

    def write_home(self, relative: str, data: bytes) -> Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


def state_of(plan, operation_id: str) -> str:
    return next(
        status.state
        for status in plan.statuses
        if status.operation.operation_id == operation_id
    )


class HostManifestTests(unittest.TestCase):
    def test_codex_ownership_excludes_wrapper_choices_but_includes_subagents(
        self,
    ) -> None:
        manifest = load_host_manifest(GUIDANCE_ROOT)
        for projection in manifest["projections"]:
            if projection["id"] not in {"codex-config", "codex2-config"}:
                continue
            with self.subTest(projection=projection["id"]):
                paths = projection["managed_keys"]
                source = tomllib.loads(
                    (GUIDANCE_ROOT / projection["source"]).read_text()
                )
                self.assertIn(["agents"], paths)
                self.assertIn(["features", "multi_agent"], paths)
                self.assertIn(["features", "multi_agent_v2"], paths)
                self.assertIn(["model_verbosity"], paths)
                self.assertNotIn(["model"], paths)
                self.assertNotIn(["model_reasoning_effort"], paths)
                self.assertNotIn("model", source)
                self.assertNotIn("model_reasoning_effort", source)
                self.assertNotIn("host_owned_keys", projection)
                if projection["id"] == "codex-config":
                    self.assertIn("default_subagent_model", source["agents"])
                    self.assertIn("default_subagent_reasoning_effort", source["agents"])

    def test_grok_accounts_share_one_config(self) -> None:
        """Each Grok home has its own source; only Grok's own [privacy] stamp may differ."""
        manifest = load_host_manifest(GUIDANCE_ROOT)
        configs = {
            projection["target"]: tomllib.loads(
                (GUIDANCE_ROOT / projection["source"]).read_text()
            )
            for projection in manifest["projections"]
            if projection["hosts"][0] in {"grok", "grok2", "grok3"}
        }
        self.assertEqual(
            {".grok/config.toml", ".grok2/config.toml", ".grok3/config.toml"},
            set(configs),
        )
        for config in configs.values():
            config.pop("privacy", None)
        primary = configs.pop(".grok/config.toml")
        for target, config in configs.items():
            with self.subTest(target=target):
                self.assertEqual(primary, config)

    def test_antigravity_accounts_share_one_cli_config(self) -> None:
        """Each Antigravity CLI home has its own source; only its model, trust, and allow lists may differ."""
        manifest = load_host_manifest(GUIDANCE_ROOT)
        configs = {
            projection["target"]: json.loads(
                (GUIDANCE_ROOT / projection["source"]).read_text()
            )
            for projection in manifest["projections"]
            if projection["hosts"][0] in {"antigravity", "antigravity2"}
            and projection["target"].endswith(".gemini/antigravity-cli/settings.json")
        }
        self.assertEqual(
            {
                ".gemini/antigravity-cli/settings.json",
                ".agy2/.gemini/antigravity-cli/settings.json",
            },
            set(configs),
        )
        # Their models, trust lists and allowed commands are host-owned, so not here.
        self.assertEqual(
            configs[".gemini/antigravity-cli/settings.json"],
            configs[".agy2/.gemini/antigravity-cli/settings.json"],
        )

    def test_every_agent_host_receives_the_policy_packs_its_kernel_names(self) -> None:
        manifest = load_host_manifest(GUIDANCE_ROOT)
        kernel = (GUIDANCE_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("~/.codex/policy/packs", kernel)
        tree = next(p for p in manifest["projections"] if p["id"] == "codex-policy-tree")
        self.assertEqual(tree["target_tree"], ".codex/policy")
        self.assertEqual(
            set(manifest["required_hosts"]) - {"hist", "memory", "shell"}, set(tree["hosts"])
        )

    def test_projected_sources_hold_no_machine_paths(self) -> None:
        """Every machine gets these bytes; its own paths come from @HOME@ or shell.local.sh."""
        manifest = load_host_manifest(GUIDANCE_ROOT)
        offenders = []
        for operation in hostlib.expand_operations(GUIDANCE_ROOT, manifest, Path("/home")):
            if operation.source_relative is None:
                continue
            source = GUIDANCE_ROOT / operation.source_relative
            for number, line in enumerate(source.read_bytes().splitlines(), 1):
                if b"/Users/" in line or b"/Volumes/" in line:
                    offenders.append(f"{operation.source_relative.as_posix()}:{number}")
        self.assertEqual([], offenders)

    def test_shared_consumer_must_be_a_host_of_what_it_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GuidanceFixture(Path(temporary))
            fixture.manifest["required_hosts"].append("beta")
            fixture.manifest["shared_consumers"].append(
                {
                    "host": "beta",
                    "projection": "kernel",
                    "mechanism": "reads alpha's file",
                    "verification": {"command": ["true"], "stdout_regex": [], "stdout_not_regex": []},
                }
            )
            fixture.write_manifest()
            with self.assertRaisesRegex(GuidanceError, "beta reads kernel"):
                plan_sync(fixture.root, fixture.home)
            fixture.manifest["projections"][0]["hosts"].append("beta")
            fixture.write_manifest()
            plan_sync(fixture.root, fixture.home)

    def test_real_manifest_covers_every_requested_host(self) -> None:
        manifest = load_host_manifest(GUIDANCE_ROOT)
        self.assertEqual(
            set(manifest["required_hosts"]),
            {
                "codex",
                "codex2",
                "claude",
                "devin",
                "cursor",
                "antigravity",
                "antigravity2",
                "grok",
                "grok2",
                "grok3",
                "command-code",
                "pi",
                "amp",
                "kimi",
                "hist",
                "memory",
                "shell",
            },
        )
        kimi = next(
            projection
            for projection in manifest["projections"]
            if projection["hosts"] == ["kimi"]
        )
        self.assertEqual(kimi["source"], "AGENTS.md")
        self.assertEqual(kimi["target"], ".kimi-code/AGENTS.md")

    def test_protected_source_cannot_be_projected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GuidanceFixture(Path(temporary))
            candidate = fixture.root / "candidate-guidance" / "draft.md"
            candidate.write_text("draft\n", encoding="utf-8")
            fixture.manifest["projections"][0]["source"] = "candidate-guidance/draft.md"
            fixture.write_manifest()
            with self.assertRaisesRegex(GuidanceError, "protected source path"):
                load_host_manifest(fixture.root)

    def test_host_owned_keys_require_an_independent_parseable_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GuidanceFixture(Path(temporary))
            fixture.add_config("settings.json", b"{}\n", host_owned_keys=[])
            fixture.manifest["projections"][-1]["independent"] = False
            fixture.write_manifest()
            with self.assertRaisesRegex(GuidanceError, "requires independent"):
                load_host_manifest(fixture.root)

            fixture.manifest["projections"][-1]["independent"] = True
            fixture.write_manifest()
            (fixture.root / "config" / "settings.json").write_bytes(b"{not json")
            with self.assertRaisesRegex(GuidanceError, "does not parse"):
                load_host_manifest(fixture.root)

    def test_independent_projection_cannot_share_its_source(self) -> None:
        """Independence means one-to-one: a shared source would fan out an adoption."""
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GuidanceFixture(Path(temporary))
            fixture.manifest["projections"][0]["independent"] = True
            fixture.write_manifest()
            with self.assertRaisesRegex(GuidanceError, "shares its source"):
                load_host_manifest(fixture.root)

            fixture.manifest["projections"][0]["independent"] = False
            fixture.add_tree("packs", "policy", ["packs/*.md"])
            with self.assertRaisesRegex(GuidanceError, "shares its source"):
                load_host_manifest(fixture.root)

    def test_shared_consumer_verification_is_executable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = GuidanceFixture(Path(temporary))
            fixture.manifest["required_hosts"].append("beta")
            fixture.manifest["projections"][0]["hosts"].append("beta")
            fixture.manifest["shared_consumers"] = [
                {
                    "host": "beta",
                    "projection": "kernel",
                    "mechanism": "test compatibility",
                    "verification": {
                        "command": [
                            sys.executable,
                            "-c",
                            "print('compatibility-active')",
                        ],
                        "stdout_regex": ["compatibility-active"],
                        "stdout_not_regex": ["duplicate-active"],
                    },
                }
            ]
            fixture.write_manifest()

            results = verify_shared_consumers(fixture.root, fixture.home)

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].ok)


class GuidanceCliTests(unittest.TestCase):
    def test_failed_post_sync_probe_rolls_back_file_changes(self) -> None:
        cli = load_guidance_cli()
        plan = SimpleNamespace(changes=(), conflicts=())
        outcome = SimpleNamespace(plan=plan, transaction_id="transaction-1")
        failed_probe = SimpleNamespace(host="grok", ok=False, detail="probe failed")
        home = Path("/tmp/guidance-cli-test-home")

        with (
            mock.patch.object(sys, "argv", ["guidance", "--home", str(home), "sync"]),
            mock.patch.object(cli, "build"),
            mock.patch.object(cli, "validation_errors", return_value=[]),
            mock.patch.object(cli, "sync", return_value=outcome),
            mock.patch.object(cli, "format_plan", return_value="plan"),
            mock.patch.object(
                cli, "verify_shared_consumers", return_value=(failed_probe,)
            ),
            mock.patch.object(
                cli, "rollback", return_value="transaction-1"
            ) as rollback_mock,
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            result = cli.main()

        self.assertEqual(result, 2)
        rollback_mock.assert_called_once_with(cli.ROOT, home)


class SyncLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = GuidanceFixture(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_sync_adopts_retires_backs_up_and_rolls_back(self) -> None:
        kernel = self.fixture.write_home(".alpha/AGENTS.md", self.fixture.legacy)
        retired = self.fixture.write_home(".old/AGENTS.md", self.fixture.legacy)

        before = plan_sync(self.fixture.root, self.fixture.home)
        states = {
            status.operation.operation_id: status.state for status in before.statuses
        }
        self.assertEqual(states["kernel"], "legacy")
        self.assertEqual(states["new-copy"], "missing")
        self.assertEqual(states["old-copy"], "retirement-needed")

        outcome = sync(self.fixture.root, self.fixture.home)
        transaction_id = outcome.transaction_id
        self.assertIsNotNone(transaction_id)
        self.assertFalse(outcome.plan.changes)
        self.assertEqual(kernel.read_bytes(), b"canonical-v1\n")
        self.assertFalse(retired.exists())
        self.assertEqual(
            (self.fixture.home / ".new/AGENTS.md").read_bytes(), b"canonical-v1\n"
        )
        backup_root = (
            self.fixture.home
            / ".local/state/persistent-guidance/backups"
            / str(transaction_id)
            / "files"
        )
        self.assertEqual(
            (backup_root / ".alpha/AGENTS.md").read_bytes(), self.fixture.legacy
        )
        self.assertEqual(
            (backup_root / ".old/AGENTS.md").read_bytes(), self.fixture.legacy
        )

        rolled_back = rollback(self.fixture.root, self.fixture.home)
        self.assertEqual(rolled_back, transaction_id)
        self.assertEqual(kernel.read_bytes(), self.fixture.legacy)
        self.assertEqual(retired.read_bytes(), self.fixture.legacy)
        self.assertFalse((self.fixture.home / ".new/AGENTS.md").exists())
        self.assertFalse(
            (self.fixture.home / ".local/state/persistent-guidance/state.json").exists()
        )

    def test_managed_stale_output_updates(self) -> None:
        sync(self.fixture.root, self.fixture.home)
        (self.fixture.root / "AGENTS.md").write_bytes(b"canonical-v2\n")
        plan = plan_sync(self.fixture.root, self.fixture.home)
        kernel = next(
            status
            for status in plan.statuses
            if status.operation.operation_id == "kernel"
        )
        self.assertEqual(kernel.state, "managed-stale")

        current = sync(self.fixture.root, self.fixture.home).plan
        self.assertFalse(current.changes)
        self.assertEqual(
            (self.fixture.home / ".alpha/AGENTS.md").read_bytes(),
            b"canonical-v2\n",
        )

    def test_local_drift_blocks_its_whole_sync_group(self) -> None:
        sync(self.fixture.root, self.fixture.home)
        drifted = self.fixture.home / ".alpha/AGENTS.md"
        drifted.write_bytes(b"local edit\n")
        (self.fixture.root / "AGENTS.md").write_bytes(b"canonical-v2\n")
        untouched = self.fixture.home / ".new/AGENTS.md"
        old_untouched = untouched.read_bytes()

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertIsNone(outcome.transaction_id)
        self.assertTrue(outcome.plan.conflicts)
        self.assertEqual(drifted.read_bytes(), b"local edit\n")
        self.assertEqual(untouched.read_bytes(), old_untouched)

    def test_config_conflict_does_not_block_the_kernel(self) -> None:
        """Regression: one host-edited config used to stop every projection."""
        source, target = self.fixture.add_config("settings.json", b'{"a": 1}\n')
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(b'{"a": 2}\n')
        (self.fixture.root / "AGENTS.md").write_bytes(b"canonical-v2\n")

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertIsNotNone(outcome.transaction_id)
        self.assertEqual(
            [status.operation.operation_id for status in outcome.plan.conflicts],
            ["settings.json-config"],
        )
        self.assertEqual(
            (self.fixture.home / ".alpha/AGENTS.md").read_bytes(), b"canonical-v2\n"
        )
        self.assertEqual(target.read_bytes(), b'{"a": 2}\n')
        # The blocked target keeps its old ownership record, so the host edit is
        # still recognized as drift and adoptable rather than silently owned.
        adoptions = adopt(self.fixture.root, self.fixture.home)
        self.assertEqual([a.operation_id for a in adoptions], ["settings.json-config"])
        self.assertEqual(source.read_bytes(), b'{"a": 2}\n')

    def test_kernel_conflict_does_not_block_an_independent_config(self) -> None:
        source, target = self.fixture.add_config("settings.json", b'{"a": 1}\n')
        sync(self.fixture.root, self.fixture.home)
        (self.fixture.home / ".alpha/AGENTS.md").write_bytes(b"local edit\n")
        source.write_bytes(b'{"a": 3}\n')

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertEqual(target.read_bytes(), b'{"a": 3}\n')
        self.assertEqual(state_of(outcome.plan, "kernel"), "conflict")
        self.assertEqual(state_of(outcome.plan, "new-copy"), "current")
        self.assertEqual(
            (self.fixture.home / ".alpha/AGENTS.md").read_bytes(), b"local edit\n"
        )

    def test_independent_tree_conflict_blocks_only_its_own_tree(self) -> None:
        prompts = self.fixture.root / "config" / "prompts"
        prompts.mkdir(parents=True)
        (prompts / "a.md").write_bytes(b"a-v1\n")
        (prompts / "b.md").write_bytes(b"b-v1\n")
        self.fixture.add_tree("prompts", "config/prompts", ["*.md"])
        sync(self.fixture.root, self.fixture.home)
        edited = self.fixture.home / ".alpha/prompts/a.md"
        edited.write_bytes(b"local edit\n")
        (prompts / "b.md").write_bytes(b"b-v2\n")
        (self.fixture.root / "AGENTS.md").write_bytes(b"canonical-v2\n")

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertEqual(
            [status.operation.operation_id for status in outcome.plan.conflicts],
            ["prompts:a.md"],
        )
        self.assertEqual(
            (self.fixture.home / ".alpha/AGENTS.md").read_bytes(), b"canonical-v2\n"
        )
        self.assertEqual(edited.read_bytes(), b"local edit\n")
        self.assertEqual(
            (self.fixture.home / ".alpha/prompts/b.md").read_bytes(), b"b-v1\n"
        )

    def test_rollback_refuses_drift_before_restoring_any_file(self) -> None:
        kernel = self.fixture.write_home(".alpha/AGENTS.md", self.fixture.legacy)
        retired = self.fixture.write_home(".old/AGENTS.md", self.fixture.legacy)
        sync(self.fixture.root, self.fixture.home)
        drifted = self.fixture.home / ".new/AGENTS.md"
        drifted.write_bytes(b"local edit\n")

        with self.assertRaisesRegex(GuidanceError, "local drift"):
            rollback(self.fixture.root, self.fixture.home)

        self.assertEqual(kernel.read_bytes(), b"canonical-v1\n")
        self.assertFalse(retired.exists())
        self.assertEqual(drifted.read_bytes(), b"local edit\n")

    def test_previously_retired_file_reappearing_is_a_conflict(self) -> None:
        sync(self.fixture.root, self.fixture.home)
        self.fixture.write_home(".old/AGENTS.md", self.fixture.legacy)

        plan = plan_sync(self.fixture.root, self.fixture.home)
        retired = next(
            status
            for status in plan.statuses
            if status.operation.operation_id == "old-copy"
        )

        self.assertEqual(retired.state, "conflict")
        self.assertIn("reappeared", retired.detail)

    def test_removed_projection_requires_explicit_retirement(self) -> None:
        sync(self.fixture.root, self.fixture.home)
        self.fixture.manifest["projections"] = [
            projection
            for projection in self.fixture.manifest["projections"]
            if projection["id"] != "new-copy"
        ]
        self.fixture.write_manifest()

        with self.assertRaisesRegex(GuidanceError, "add explicit retirements"):
            plan_sync(self.fixture.root, self.fixture.home)

    def test_released_target_is_forgotten_but_left_in_place(self) -> None:
        sync(self.fixture.root, self.fixture.home)
        released = self.fixture.home / ".new/AGENTS.md"
        released.write_bytes(b"host keeps editing this\n")
        self.fixture.manifest["projections"] = [
            projection
            for projection in self.fixture.manifest["projections"]
            if projection["id"] != "new-copy"
        ]
        self.fixture.manifest["releases"] = [
            {"target": ".new/AGENTS.md", "reason": "host-owned state"}
        ]
        self.fixture.write_manifest()

        sync(self.fixture.root, self.fixture.home)

        self.assertEqual(released.read_bytes(), b"host keeps editing this\n")
        state = json.loads(
            (
                self.fixture.home / ".local/state/persistent-guidance/state.json"
            ).read_text(encoding="utf-8")
        )
        self.assertNotIn(".new/AGENTS.md", state["targets"])
        self.fixture.manifest["releases"] = []
        self.fixture.write_manifest()
        self.assertFalse(plan_sync(self.fixture.root, self.fixture.home).conflicts)

    def test_unknown_first_run_file_blocks_without_creating_other_targets(self) -> None:
        self.fixture.write_home(".alpha/AGENTS.md", b"unowned\n")
        new_target = self.fixture.home / ".new/AGENTS.md"

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertTrue(outcome.plan.conflicts)
        self.assertFalse(new_target.exists())
        self.assertFalse(
            (self.fixture.home / ".local/state/persistent-guidance/state.json").exists()
        )

    def test_symlinked_target_parent_blocks_without_writing_through_it(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (self.fixture.home / ".alpha").symlink_to(outside, target_is_directory=True)

        self.assertTrue(sync(self.fixture.root, self.fixture.home).plan.conflicts)

        self.assertFalse((outside / "AGENTS.md").exists())
        self.assertFalse((self.fixture.home / ".new/AGENTS.md").exists())
        self.assertFalse(
            (self.fixture.home / ".local/state/persistent-guidance/state.json").exists()
        )

    def test_dry_run_does_not_create_state_or_targets(self) -> None:
        outcome = sync(self.fixture.root, self.fixture.home, dry_run=True)
        self.assertIsNone(outcome.transaction_id)
        self.assertTrue(outcome.plan.changes)
        self.assertFalse((self.fixture.home / ".new/AGENTS.md").exists())
        self.assertFalse((self.fixture.home / ".local/state").exists())

    def test_brief_summary_is_silent_only_when_everything_is_current(self) -> None:
        summary = summarize_plan(plan_sync(self.fixture.root, self.fixture.home))
        self.assertIsNotNone(summary)
        self.assertIn("pending", str(summary))
        sync(self.fixture.root, self.fixture.home)
        self.assertIsNone(
            summarize_plan(plan_sync(self.fixture.root, self.fixture.home))
        )
        (self.fixture.home / ".new/AGENTS.md").write_bytes(b"local edit\n")
        self.assertIn(
            "1 conflict(s): new-copy",
            str(summarize_plan(plan_sync(self.fixture.root, self.fixture.home))),
        )


class MachineFileTests(unittest.TestCase):
    """The machine file enables a subset of hosts; the rest are left alone."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = GuidanceFixture(Path(self.temporary.name))
        manifest = self.fixture.manifest
        manifest["required_hosts"].append("beta")
        manifest["projections"].append(
            {
                "id": "beta-kernel",
                "source": "AGENTS.md",
                "target": ".beta/AGENTS.md",
                "hosts": ["beta"],
            }
        )
        manifest["shared_consumers"].append(
            {
                "host": "beta",
                "projection": "beta-kernel",
                "mechanism": "probe that would fail",
                "verification": {
                    "command": ["false"],
                    "stdout_regex": [],
                    "stdout_not_regex": [],
                },
            }
        )
        self.fixture.write_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_machine(self, hosts: list[str]) -> None:
        self.fixture.write_home(
            ".config/agent-system/machine.json",
            json.dumps({"schema_version": 1, "hosts": hosts}).encode(),
        )

    def test_disabled_host_is_neither_written_nor_probed(self) -> None:
        self.write_machine(["alpha", "mimo"])
        plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertEqual(state_of(plan, "beta-kernel"), "disabled")
        self.assertEqual(state_of(plan, "kernel"), "missing")

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertFalse(outcome.plan.changes)
        self.assertTrue((self.fixture.home / ".alpha/AGENTS.md").exists())
        self.assertFalse((self.fixture.home / ".beta").exists())
        self.assertEqual(verify_shared_consumers(self.fixture.root, self.fixture.home), ())
        self.assertIn("disabled ", format_plan(outcome.plan))
        self.assertIsNone(summarize_plan(outcome.plan))

    def test_disabling_a_synced_host_leaves_its_files_in_place(self) -> None:
        sync(self.fixture.root, self.fixture.home)
        beta = self.fixture.home / ".beta/AGENTS.md"
        self.write_machine(["alpha"])
        (self.fixture.root / "AGENTS.md").write_bytes(b"canonical-v2\n")

        sync(self.fixture.root, self.fixture.home)

        self.assertEqual(beta.read_bytes(), b"canonical-v1\n")
        self.assertEqual(
            (self.fixture.home / ".alpha/AGENTS.md").read_bytes(), b"canonical-v2\n"
        )

    def test_without_a_machine_file_every_host_is_enabled(self) -> None:
        plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertEqual(state_of(plan, "beta-kernel"), "missing")
        results = verify_shared_consumers(self.fixture.root, self.fixture.home)
        self.assertEqual([(r.host, r.ok) for r in results], [("beta", False)])

    def test_release_clears_ownership_even_with_every_host_disabled(self) -> None:
        sync(self.fixture.root, self.fixture.home)
        manifest = self.fixture.manifest
        manifest["projections"] = [p for p in manifest["projections"] if p["id"] != "new-copy"]
        manifest["releases"].append({"target": ".new/AGENTS.md", "reason": "host owns it now"})
        self.fixture.write_manifest()
        self.write_machine([])

        sync(self.fixture.root, self.fixture.home)

        state = json.loads(
            (self.fixture.home / ".local/state/persistent-guidance/state.json").read_bytes()
        )
        self.assertNotIn(".new/AGENTS.md", state["targets"])
        self.assertTrue((self.fixture.home / ".new/AGENTS.md").exists())

    def test_malformed_machine_file_stops_before_any_write(self) -> None:
        self.fixture.write_home(".config/agent-system/machine.json", b"{\"hosts\": 1}")
        with self.assertRaises(GuidanceError):
            sync(self.fixture.root, self.fixture.home)
        self.assertFalse((self.fixture.home / ".alpha").exists())


class ManagedConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = GuidanceFixture(Path(self.temporary.name))
        self.owned = (
            b'model_verbosity = "low"\n\n'
            b"[agents]\nmax_depth = 1\n\n"
            b"[features]\nmulti_agent = true\n"
        )
        self.paths = [["model_verbosity"], ["agents"], ["features", "multi_agent"]]

    def add_config(self) -> tuple[Path, Path]:
        return self.fixture.add_config(
            "config.toml", self.owned, managed_keys=self.paths
        )

    def test_json_mcp_projection_preserves_host_state_and_rolls_back(self) -> None:
        owned = {
            "mcpServers": {
                "lovable": {"type": "http", "url": "https://example.com/mcp"}
            }
        }
        source, target = self.fixture.add_config(
            "mcp.json",
            json.dumps(owned).encode(),
            managed_keys=[["mcpServers", "lovable"]],
        )
        runtime = {
            "oauthAccount": {"id": "local-account"},
            "projects": {"/work": {}},
            "mcpServers": {"other": {"command": "local-tool"}},
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        before = json.dumps(runtime).encode()
        target.write_bytes(before)

        preview = sync(self.fixture.root, self.fixture.home, dry_run=True)
        self.assertFalse(preview.plan.conflicts)
        self.assertEqual(target.read_bytes(), before)
        outcome = sync(self.fixture.root, self.fixture.home)
        self.assertFalse(outcome.plan.conflicts)
        expected = json.loads(before)
        expected["mcpServers"].update(owned["mcpServers"])
        self.assertEqual(json.loads(target.read_bytes()), expected)
        self.assertIsNone(sync(self.fixture.root, self.fixture.home).transaction_id)
        self.assertEqual(json.loads(source.read_bytes()), owned)
        rollback(self.fixture.root, self.fixture.home)
        self.assertEqual(target.read_bytes(), before)

    def test_json_owned_drift_adopts_only_selected_values(self) -> None:
        owned = {"mcpServers": {"lovable": {"url": "https://example.com/mcp"}}}
        source, target = self.fixture.add_config(
            "mcp.json",
            json.dumps(owned).encode(),
            managed_keys=[["mcpServers", "lovable"]],
        )
        sync(self.fixture.root, self.fixture.home)
        live = {
            "secret": "host-only",
            "mcpServers": {
                "other": {},
                "lovable": {"url": "https://changed.example/mcp"},
            },
        }
        target.write_text(json.dumps(live))
        self.assertTrue(sync(self.fixture.root, self.fixture.home).plan.conflicts)
        (preview,) = adopt(self.fixture.root, self.fixture.home, dry_run=True)
        self.assertNotIn("host-only", preview.evidence)
        adopt(self.fixture.root, self.fixture.home)
        self.assertEqual(
            json.loads(source.read_bytes()),
            {"mcpServers": {"lovable": live["mcpServers"]["lovable"]}},
        )
        self.assertFalse(sync(self.fixture.root, self.fixture.home).plan.conflicts)
        self.assertEqual(json.loads(target.read_bytes()), live)
        source.write_text("{}")
        sync(self.fixture.root, self.fixture.home)
        del live["mcpServers"]["lovable"]
        self.assertEqual(json.loads(target.read_bytes()), live)

    def test_json_malformed_or_conflicting_host_state_is_never_overwritten(
        self,
    ) -> None:
        _, target = self.fixture.add_config(
            "mcp.json",
            b'{"mcpServers":{"lovable":{"url":"https://example.com"}}}',
            managed_keys=[["mcpServers", "lovable"]],
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        for live in (
            b"{broken",
            b"[]",
            '{"hostState":"keep"}'.encode("utf-16"),
            b'{"mcpServers":false}',
            b'{"mcpServers":{"lovable":{"url":"https://other.example"}}}',
        ):
            with self.subTest(live=live):
                target.write_bytes(live)
                self.assertTrue(
                    sync(self.fixture.root, self.fixture.home).plan.conflicts
                )
                self.assertEqual(target.read_bytes(), live)

    def test_unmanaged_changes_are_silent_and_never_adopted(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        live = (
            b'# Codex controls these selections.\nmodel = "wrapper-model"\n'
            b'model_reasoning_effort = "xhigh"\nservice_tier = "fast"\n\n'
            + self.owned
            + b'\n[plugins."unified-computer-use@openai-bundled"]\nenabled = true\n'
            + b'\n[mcp_servers.node_repl]\nargs = ["app", "updated"]\n'
            + b'\n[hooks.state."new-project"]\ntrusted_hash = "new-hash"\n'
        )
        target.write_bytes(live)

        plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertEqual(state_of(plan, "config.toml-config"), "current")
        self.assertIsNone(summarize_plan(plan))
        self.assertEqual(adopt(self.fixture.root, self.fixture.home), ())
        outcome = sync(self.fixture.root, self.fixture.home)
        self.assertIsNone(outcome.transaction_id)
        self.assertEqual(source.read_bytes(), self.owned)
        self.assertEqual(target.read_bytes(), live)

    def test_existing_whole_file_state_transitions_without_rewriting_live(self) -> None:
        original = b'model = "old-model"\n\n' + self.owned
        source, target = self.fixture.add_config("config.toml", original)
        sync(self.fixture.root, self.fixture.home)
        live = b'model = "new-model"\nmodel_reasoning_effort = "max"\n\n' + self.owned
        target.write_bytes(live)
        source.write_bytes(self.owned)
        self.fixture.manifest["projections"][-1]["managed_keys"] = self.paths
        self.fixture.write_manifest()

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertFalse(outcome.plan.conflicts)
        self.assertIsNone(outcome.transaction_id)
        self.assertIsNone(summarize_plan(outcome.plan))
        self.assertEqual(target.read_bytes(), live)
        self.assertEqual(source.read_bytes(), self.owned)

    def test_canonical_changes_preserve_runtime_text_and_roll_back(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        runtime = (
            b'# Leave this comment and spacing intact.\nmodel  = "selected-model" # UI\n'
            b'model_reasoning_effort = "max"\n\n'
        )
        runtime_tail = (
            b"\n[features]\nmulti_agent = true\napps = true # not managed\n"
            b'\n[mcp_servers."custom.server"]\n'
            b'args = ["one", "two"]\nenv = { NAME = "value" }\n'
            b'description = """A multiline\nvalue stays intact."""\n'
            b'\n[projects."/new/project"]\ntrust_level = "trusted"\n'
        )
        live = runtime + self.owned.split(b"[features]")[0] + runtime_tail
        target.write_bytes(live)
        source.write_bytes(self.owned.replace(b"max_depth = 1", b"max_depth = 2"))

        self.assertEqual(
            state_of(
                plan_sync(self.fixture.root, self.fixture.home), "config.toml-config"
            ),
            "managed-stale",
        )
        preview = sync(self.fixture.root, self.fixture.home, dry_run=True)
        self.assertFalse(preview.plan.conflicts)
        self.assertEqual(target.read_bytes(), live)
        outcome = sync(self.fixture.root, self.fixture.home)
        self.assertIsNotNone(outcome.transaction_id)
        self.assertFalse(outcome.plan.conflicts)
        updated = target.read_bytes()
        self.assertEqual(
            tomllib.loads(updated.decode()),
            tomllib.loads(live.replace(b"max_depth = 1", b"max_depth = 2").decode()),
        )
        self.assertTrue(updated.startswith(runtime))
        self.assertTrue(updated.endswith(runtime_tail))
        self.assertEqual(
            sync(self.fixture.root, self.fixture.home).transaction_id, None
        )
        rollback(self.fixture.root, self.fixture.home)
        self.assertEqual(target.read_bytes(), live)

    def test_owned_drift_is_reviewed_without_importing_runtime_values(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        live = b'model = "selected-model"\n\n' + self.owned.replace(b'"low"', b'"high"')
        target.write_bytes(live)
        plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertEqual(state_of(plan, "config.toml-config"), "conflict")
        self.assertIn("config.toml-config", str(summarize_plan(plan)))
        self.assertTrue(sync(self.fixture.root, self.fixture.home).plan.conflicts)
        self.assertEqual(target.read_bytes(), live)
        (preview,) = adopt(self.fixture.root, self.fixture.home, dry_run=True)
        self.assertIn('model_verbosity = "high"', preview.evidence)
        self.assertNotIn("selected-model", preview.evidence)
        adopt(self.fixture.root, self.fixture.home)
        self.assertEqual(source.read_bytes(), self.owned.replace(b'"low"', b'"high"'))
        self.assertFalse(sync(self.fixture.root, self.fixture.home).plan.conflicts)
        self.assertEqual(target.read_bytes(), live)

    def test_removing_a_managed_value_preserves_unmanaged_siblings(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        live = self.owned.replace(
            b"multi_agent = true", b"multi_agent = true\napps = true"
        )
        target.write_bytes(live)
        source.write_bytes(self.owned.replace(b"multi_agent = true\n", b""))

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertFalse(outcome.plan.conflicts)
        parsed = tomllib.loads(target.read_text())
        self.assertNotIn("multi_agent", parsed["features"])
        self.assertTrue(parsed["features"]["apps"])
        self.assertEqual(parsed["agents"]["max_depth"], 1)

    def test_malformed_runtime_config_is_not_overwritten_or_adopted(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        broken = b'model = "unterminated\n' + self.owned
        target.write_bytes(broken)

        self.assertEqual(
            state_of(
                plan_sync(self.fixture.root, self.fixture.home), "config.toml-config"
            ),
            "conflict",
        )
        self.assertTrue(sync(self.fixture.root, self.fixture.home).plan.conflicts)
        with self.assertRaises(GuidanceError):
            adopt(self.fixture.root, self.fixture.home)
        self.assertEqual(source.read_bytes(), self.owned)
        self.assertEqual(target.read_bytes(), broken)

    def test_managed_source_rejects_unowned_keys_and_overlapping_paths(self) -> None:
        source, _ = self.add_config()
        source.write_bytes(b'model = "unowned"\n\n' + self.owned)
        with self.assertRaisesRegex(GuidanceError, "unmanaged"):
            load_host_manifest(self.fixture.root)
        source.write_bytes(self.owned)
        self.fixture.manifest["projections"][-1]["managed_keys"].append(
            ["agents", "max_depth"]
        )
        self.fixture.write_manifest()
        with self.assertRaisesRegex(GuidanceError, "overlap"):
            load_host_manifest(self.fixture.root)

    def test_managed_values_compare_toml_types_not_python_coercions(self) -> None:
        _, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        for replacement in (b"true", b"1.0"):
            with self.subTest(replacement=replacement):
                target.write_bytes(
                    self.owned.replace(b"max_depth = 1", b"max_depth = " + replacement)
                )
                self.assertEqual(
                    state_of(
                        plan_sync(self.fixture.root, self.fixture.home),
                        "config.toml-config",
                    ),
                    "conflict",
                )

    def test_unmanaged_special_values_survive_managed_changes(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        runtime = b"host_nan = nan\nhost_date = 2026-10-06T12:00:00-07:00\n\n"
        target.write_bytes(runtime + self.owned)
        source.write_bytes(self.owned.replace(b"max_depth = 1", b"max_depth = 2"))

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertFalse(outcome.plan.conflicts)
        self.assertTrue(target.read_bytes().startswith(runtime))
        self.assertEqual(tomllib.loads(target.read_text())["agents"]["max_depth"], 2)

    def test_rollback_refuses_to_erase_later_unmanaged_host_updates(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        source.write_bytes(self.owned.replace(b"max_depth = 1", b"max_depth = 2"))
        sync(self.fixture.root, self.fixture.home)
        live = b'model = "new-host-selection"\n\n' + target.read_bytes()
        target.write_bytes(live)

        self.assertIsNone(
            summarize_plan(plan_sync(self.fixture.root, self.fixture.home))
        )
        with self.assertRaisesRegex(GuidanceError, "local drift"):
            rollback(self.fixture.root, self.fixture.home)
        self.assertEqual(target.read_bytes(), live)

    def test_releasing_a_setting_leaves_its_live_value_alone(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        live = target.read_bytes()
        source.write_bytes(self.owned.replace(b'model_verbosity = "low"\n\n', b""))
        self.fixture.manifest["projections"][-1]["managed_keys"].remove(
            ["model_verbosity"]
        )
        self.fixture.write_manifest()

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertIsNone(outcome.transaction_id)
        self.assertIsNone(summarize_plan(outcome.plan))
        self.assertEqual(target.read_bytes(), live)

    def test_non_table_parent_is_not_clobbered(self) -> None:
        source, target = self.add_config()
        sync(self.fixture.root, self.fixture.home)
        live = b"features = false\n\n" + self.owned.split(b"[features]")[0]
        target.write_bytes(live)

        self.assertTrue(sync(self.fixture.root, self.fixture.home).plan.conflicts)
        with self.assertRaisesRegex(GuidanceError, "non-table parent"):
            adopt(self.fixture.root, self.fixture.home)
        self.assertEqual(source.read_bytes(), self.owned)
        self.assertEqual(target.read_bytes(), live)


class SharedMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = GuidanceFixture(Path(self.temporary.name))
        self.registry = self.fixture.root / "config/mcp/servers.json"
        self.registry.parent.mkdir(parents=True)
        self.write_registry({"url": "https://example.com/mcp"})
        self.targets = {}
        for dialect in ("claude", "codex", "antigravity", "kimi", "devin"):
            section = "mcp_servers" if dialect == "codex" else "mcpServers"
            suffix = "toml" if dialect == "codex" else "json"
            source, target = self.fixture.add_config(
                f"{dialect}.{suffix}",
                b"" if suffix == "toml" else b"{}",
                managed_keys=[[section, "lovable"]],
            )
            self.fixture.manifest["projections"][-1]["shared_mcp"] = {
                "format": dialect,
                "servers": ["lovable"],
            }
            self.targets[dialect] = (source, target)
        self.fixture.write_manifest()

    def write_registry(self, server: dict[str, str] | None) -> None:
        self.registry.write_text(
            json.dumps({"schema_version": 1, "servers": {"lovable": server}})
        )

    def build_and_sync(self):
        for path, text in expected_mcp_outputs(self.fixture.root).items():
            path.write_text(text)
        return sync(self.fixture.root, self.fixture.home)

    def test_one_registry_flows_through_each_native_config_and_live_merge(self) -> None:
        self.assertFalse(self.build_and_sync().plan.conflicts)
        for dialect, (_, target) in self.targets.items():
            if dialect == "codex":
                target.write_text('model = "host-choice"\n\n' + target.read_text())
            else:
                live = json.loads(target.read_bytes())
                live["hostState"] = {"keep": True}
                live["mcpServers"]["other"] = {"command": "keep-me"}
                target.write_text(json.dumps(live))
        self.write_registry({"url": "https://updated.example/mcp"})
        self.assertFalse(self.build_and_sync().plan.conflicts)
        for dialect, (_, target) in self.targets.items():
            with self.subTest(dialect=dialect):
                if dialect == "codex":
                    parsed = tomllib.loads(target.read_text())
                    server = parsed["mcp_servers"]["lovable"]
                    self.assertEqual(parsed["model"], "host-choice")
                else:
                    parsed = json.loads(target.read_bytes())
                    self.assertTrue(parsed["hostState"]["keep"])
                    self.assertEqual(
                        parsed["mcpServers"]["other"]["command"], "keep-me"
                    )
                    server = parsed["mcpServers"]["lovable"]
                url_key = "serverUrl" if dialect == "antigravity" else "url"
                self.assertEqual(server[url_key], "https://updated.example/mcp")
                if dialect == "claude":
                    self.assertEqual(server["type"], "http")
                if dialect == "devin":
                    self.assertEqual(server["transport"], "http")
        self.assertIsNone(self.build_and_sync().transaction_id)
        self.write_registry(None)
        self.assertFalse(self.build_and_sync().plan.conflicts)
        for dialect, (_, target) in self.targets.items():
            parsed = (
                tomllib.loads(target.read_text())
                if dialect == "codex"
                else json.loads(target.read_bytes())
            )
            self.assertNotIn(
                "lovable",
                parsed.get("mcp_servers" if dialect == "codex" else "mcpServers", {}),
            )

    def test_invalid_registry_or_unowned_entry_stops_before_writes(self) -> None:
        for server in (
            {"url": "invalid"},
            {"url": "https://[invalid"},
            {"url": "https://user:secret@example.com"},
            {"url": "https://example.com", "token": "forbidden"},
        ):
            with self.subTest(server=server):
                self.write_registry(server)
                with self.assertRaises(GuidanceError):
                    expected_mcp_outputs(self.fixture.root)
                self.assertFalse(
                    any(target.exists() for _, target in self.targets.values())
                )
        self.write_registry({"url": "https://example.com"})
        self.fixture.manifest["projections"][-1]["shared_mcp"]["servers"] = ["other"]
        self.fixture.write_manifest()
        with self.assertRaises(GuidanceError):
            expected_mcp_outputs(self.fixture.root)


class HostOwnedKeyTests(unittest.TestCase):
    """Host-written keys stay on each machine; canonical never holds them."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = GuidanceFixture(Path(self.temporary.name))

    def test_host_key_and_reformat_stay_on_the_host(self) -> None:
        cases = (
            (
                "settings.json",
                b'{\n  "model": "opus",\n  "seen": {"keep": 1}\n}\n',
                [["seen", "nudge"]],
                b'{"seen": {"keep": 1, "nudge": true}, "model": "opus"}',
            ),
            (
                "config.toml",
                b'# why the proxy exists\n[endpoints]\nurl = "http://x"\n',
                [["privacy"]],
                b'[endpoints]\nurl = "http://x"\n\n[privacy]\nacked = "2026-10-01"\n',
            ),
        )
        for name, canonical, keys, host_written in cases:
            with self.subTest(name=name):
                source, target = self.fixture.add_config(
                    name, canonical, host_owned_keys=keys
                )
                sync(self.fixture.root, self.fixture.home)
                target.write_bytes(host_written)
                operation_id = f"{name}-config"
                self.assertEqual(
                    state_of(plan_sync(self.fixture.root, self.fixture.home), operation_id),
                    "current",
                )

                outcome = sync(self.fixture.root, self.fixture.home)

                self.assertIsNone(outcome.transaction_id)
                self.assertEqual(source.read_bytes(), canonical)
                self.assertEqual(target.read_bytes(), host_written)

    def test_preexisting_host_file_is_replaced_only_when_known(self) -> None:
        """A host's first-run file: listed hash -> canonical plus its own keys."""
        canonical = b'{"effort": "high"}\n'
        first_run = b'{"effort": "low", "seen": true}\n'
        source, target = self.fixture.add_config(
            "settings.json", canonical, host_owned_keys=[["seen"]]
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(first_run)
        self.assertEqual(
            state_of(plan_sync(self.fixture.root, self.fixture.home), "settings.json-config"),
            "conflict",
        )

        self.fixture.manifest["projections"][-1]["adopt_sha256"] = [digest(first_run)]
        self.fixture.write_manifest()
        self.assertEqual(
            state_of(plan_sync(self.fixture.root, self.fixture.home), "settings.json-config"),
            "legacy",
        )
        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertIsNotNone(outcome.transaction_id)
        self.assertEqual(state_of(outcome.plan, "settings.json-config"), "current")
        self.assertEqual(json.loads(target.read_bytes()), {"effort": "high", "seen": True})
        self.assertEqual(source.read_bytes(), canonical)

    def test_host_write_between_hash_and_read_is_never_overwritten(self) -> None:
        source, target = self.fixture.add_config(
            "settings.json", b'{"effort": "high"}\n', host_owned_keys=[["model"]]
        )
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(b'{"effort": "high", "model": "first"}\n')
        source.write_bytes(b'{"effort": "xhigh"}\n')
        real_sha256_file = hostlib.sha256_file
        injected = []

        def hash_then_host_writes(path: Path) -> str:
            digest_value = real_sha256_file(path)
            if path == target.resolve() and not injected:
                injected.append(True)
                target.write_bytes(b'{"effort": "high", "model": "second"}\n')
            return digest_value

        with mock.patch.object(hostlib, "sha256_file", hash_then_host_writes):
            plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertEqual(state_of(plan, "settings.json-config"), "conflict")
        self.assertEqual(json.loads(target.read_bytes())["model"], "second")

    def test_exact_hashes_prove_ownership_without_parsing_or_a_copy(self) -> None:
        legacy = b"not json at all\n"
        source, target = self.fixture.add_config("mcp.json", b'{"a": 1}\n', host_owned_keys=[])
        self.fixture.manifest["projections"][-1]["adopt_sha256"] = [digest(legacy)]
        self.fixture.write_manifest()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(legacy)
        self.assertEqual(state_of(plan_sync(self.fixture.root, self.fixture.home), "mcp.json-config"), "legacy")
        sync(self.fixture.root, self.fixture.home)
        self.assertEqual(target.read_bytes(), b'{"a": 1}\n')

        # The live file is exactly what sync installed, but its copy is gone.
        shutil.rmtree(self.fixture.home / ".local/state/persistent-guidance/installed")
        source.write_bytes(b'{"a": 2}\n')
        self.assertEqual(
            state_of(plan_sync(self.fixture.root, self.fixture.home), "mcp.json-config"),
            "managed-stale",
        )
        sync(self.fixture.root, self.fixture.home)
        self.assertEqual(json.loads(target.read_bytes()), {"a": 2})

    def test_first_run_file_with_only_host_owned_keys_is_merged(self) -> None:
        source, target = self.fixture.add_config(
            "settings.json",
            b'{"hooks": {"Stop": []}}\n',
            host_owned_keys=[["model"], ["effortLevel"]],
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'{"model": "sonnet", "effortLevel": "high"}\n')

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertIsNotNone(outcome.transaction_id)
        self.assertEqual(
            json.loads(target.read_bytes()),
            {"hooks": {"Stop": []}, "model": "sonnet", "effortLevel": "high"},
        )
        # Any canonical-owned value makes it someone else's file again.
        other = self.fixture.home / ".alpha" / "other.json"
        self.fixture.add_config("other.json", b'{"a": 1}\n', host_owned_keys=[["model"]])
        other.write_bytes(b'{"a": 0, "model": "x"}\n')
        self.assertEqual(
            state_of(plan_sync(self.fixture.root, self.fixture.home), "other.json-config"),
            "conflict",
        )

    def test_ambiguous_host_owned_declarations_fail_validation(self) -> None:
        cases = (
            (b'{"ide": {}}\n', [["ide", "seen"]], "empty parents of host-owned keys"),
            (b'{"a": 1}\n', [["permissions", "allow"], ["permissions"]], "overlapping"),
        )
        for data, keys, message in cases:
            with self.subTest(message=message):
                self.fixture.manifest["projections"] = self.fixture.manifest["projections"][:3]
                self.fixture.add_config("settings.json", data, host_owned_keys=keys)
                with self.assertRaisesRegex(GuidanceError, message):
                    plan_sync(self.fixture.root, self.fixture.home)

    def test_adopt_preview_ignores_host_owned_values_in_older_copies(self) -> None:
        source, target = self.fixture.add_config(
            "settings.json", b'{"a": 1, "trusted": ["/only-on-that-mac"]}\n'
        )
        sync(self.fixture.root, self.fixture.home)
        self.fixture.manifest["projections"][-1]["host_owned_keys"] = [["trusted"]]
        self.fixture.write_manifest()
        source.write_bytes(b'{"a": 1}\n')
        target.write_bytes(b'{"a": 2, "trusted": ["/only-on-that-mac"]}\n')

        (adoption,) = adopt(self.fixture.root, self.fixture.home, dry_run=True)

        self.assertNotIn("only-on-that-mac", adoption.evidence)
        self.assertNotIn("canonical also changed", adoption.evidence)
        self.assertIn('"a": 2', adoption.evidence)

    def test_canonical_source_may_not_carry_a_host_owned_key(self) -> None:
        self.fixture.add_config(
            "settings.json", b'{"model": "opus", "seen": true}\n', host_owned_keys=[["seen"]]
        )
        with self.assertRaisesRegex(GuidanceError, "carries host-owned keys"):
            plan_sync(self.fixture.root, self.fixture.home)

    def test_change_to_a_canonical_key_stays_a_reviewed_conflict(self) -> None:
        source, target = self.fixture.add_config(
            "settings.json", b'{"effort": "high"}\n', host_owned_keys=[["seen"]]
        )
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(b'{"effort": "xhigh", "seen": true}\n')

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertEqual(state_of(outcome.plan, "settings.json-config"), "conflict")
        self.assertEqual(source.read_bytes(), b'{"effort": "high"}\n')
        self.assertEqual(target.read_bytes(), b'{"effort": "xhigh", "seen": true}\n')

    def test_canonical_edit_keeps_the_hosts_values_and_canonical_text(self) -> None:
        """Regression: a CLI-toggled key plus an unsynced canonical edit conflicted."""
        source, target = self.fixture.add_config(
            "config.toml",
            b'# keep this note\nmodel = "a"\n[other]\nkeep = true\n',
            host_owned_keys=[["service_tier"], ["privacy"]],
        )
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(
            b'service_tier = """fast\nvalue"""\n# keep this note\nmodel = "a"\n'
            b'[other]\nkeep = true\n\n[privacy]\nacked = "new"\n'
        )
        source.write_bytes(b'# keep this note\nmodel = "b"\n[other]\nkeep = true\n')

        preview = sync(self.fixture.root, self.fixture.home, dry_run=True)
        self.assertFalse(preview.plan.conflicts)
        self.assertEqual(state_of(preview.plan, "config.toml-config"), "managed-stale")

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertFalse(outcome.plan.conflicts)
        self.assertEqual(
            source.read_bytes(), b'# keep this note\nmodel = "b"\n[other]\nkeep = true\n'
        )
        written = target.read_bytes()
        self.assertTrue(written.startswith(b'# keep this note\nmodel = "b"\n'))
        self.assertEqual(
            tomllib.loads(written.decode()),
            {
                "model": "b",
                "service_tier": "fast\nvalue",
                "other": {"keep": True},
                "privacy": {"acked": "new"},
            },
        )
        repeated = sync(self.fixture.root, self.fixture.home)
        self.assertIsNone(repeated.transaction_id)

    def test_host_removing_its_own_key_during_a_canonical_edit(self) -> None:
        source, target = self.fixture.add_config(
            "settings.json", b'{"model": "a"}\n', host_owned_keys=[["seen"]]
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(b'{"model": "a", "seen": true}\n')
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(b'{"model": "a"}\n')
        source.write_bytes(b'{"model": "b"}\n')

        sync(self.fixture.root, self.fixture.home)

        self.assertEqual(json.loads(target.read_bytes()), {"model": "b"})

    def test_adopt_takes_canonical_changes_but_not_host_owned_keys(self) -> None:
        source, target = self.fixture.add_config(
            "config.toml", b'model = "a"\n', host_owned_keys=[["privacy"]]
        )
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(b'model = "z"\n\n[privacy]\nacked = "today"\n')

        (adoption,) = adopt(self.fixture.root, self.fixture.home)

        self.assertEqual(adoption.operation_id, "config.toml-config")
        self.assertEqual(tomllib.loads(source.read_text()), {"model": "z"})
        self.assertEqual(
            state_of(plan_sync(self.fixture.root, self.fixture.home), "config.toml-config"),
            "current",
        )

    def test_unparseable_host_write_is_a_conflict(self) -> None:
        _, target = self.fixture.add_config(
            "settings.json", b"{}\n", host_owned_keys=[]
        )
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(b"{truncated")

        plan = plan_sync(self.fixture.root, self.fixture.home)

        status = next(
            s
            for s in plan.statuses
            if s.operation.operation_id == "settings.json-config"
        )
        self.assertEqual(status.state, "conflict")
        self.assertIn("unparseable", status.detail)

    def test_adopt_evidence_separates_host_and_canonical_changes(self) -> None:
        source, target = self.fixture.add_config(
            "settings.json",
            b'{\n  "effort": "high",\n  "theme": "dark",\n  "api_key": "old"\n}\n',
        )
        sync(self.fixture.root, self.fixture.home)
        target.write_bytes(
            b'{\n  "effort": "xhigh",\n  "theme": "dark",\n  "api_key": "sk-live-secret"\n}\n'
        )
        source.write_bytes(
            b'{\n  "effort": "high",\n  "theme": "light",\n  "api_key": "old"\n}\n'
        )

        (adoption,) = adopt(self.fixture.root, self.fixture.home, dry_run=True)

        host_part, canonical_part = adoption.evidence.split("canonical also changed")
        self.assertIn('+  "effort": "xhigh"', host_part)
        self.assertNotIn('"theme": "light"', host_part)
        self.assertIn('+  "theme": "light"', canonical_part)
        self.assertNotIn("sk-live-secret", adoption.evidence)
        self.assertIn('"api_key": <redacted>', adoption.evidence)


class HomeTokenTests(unittest.TestCase):
    """config/ says @HOME@; each machine's files hold its own home path."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = GuidanceFixture(Path(self.temporary.name))
        self.home = str(self.fixture.home.resolve())

    def test_sync_renders_and_adopt_restores_only_this_home(self) -> None:
        canonical = b'{"command": "@HOME@/.local/bin/uvx"}\n'
        source, target = self.fixture.add_config("mcp.json", canonical)
        sync(self.fixture.root, self.fixture.home)
        self.assertEqual(
            target.read_bytes(), canonical.replace(b"@HOME@", self.home.encode())
        )

        # The host edits the path and adds a sibling of the home directory.
        live = (
            f'{{"command": "{self.home}/.local/bin/uvx2", "other": "{self.home}2/x", '
            f'"backup": "/Volumes/b{self.home}/x", "self": "{self.home}"}}\n'
        )
        target.write_text(live, encoding="utf-8")
        adopt(self.fixture.root, self.fixture.home)

        self.assertEqual(
            source.read_text(encoding="utf-8"),
            f'{{"command": "@HOME@/.local/bin/uvx2", "other": "{self.home}2/x", '
            f'"backup": "/Volumes/b{self.home}/x", "self": "@HOME@"}}\n',
        )
        self.assertIsNone(sync(self.fixture.root, self.fixture.home).transaction_id)
        self.assertEqual(target.read_text(encoding="utf-8"), live)

    def test_managed_and_host_owned_configs_render_the_token(self) -> None:
        managed_source, managed_target = self.fixture.add_config(
            "config.toml", b'prompt = "@HOME@/a.md"\n', managed_keys=[["prompt"]]
        )
        managed_target.parent.mkdir(parents=True, exist_ok=True)
        managed_target.write_bytes(b'model = "host"\n')
        owned_source, owned_target = self.fixture.add_config(
            "settings.json", b'{"hook": "@HOME@/h.py"}\n', host_owned_keys=[["seen"]]
        )
        sync(self.fixture.root, self.fixture.home)
        owned_target.write_bytes(owned_target.read_bytes()[:-2] + b', "seen": true}\n')
        owned_source.write_bytes(b'{"hook": "@HOME@/h2.py"}\n')

        sync(self.fixture.root, self.fixture.home)

        self.assertEqual(
            tomllib.loads(managed_target.read_text(encoding="utf-8")),
            {"model": "host", "prompt": f"{self.home}/a.md"},
        )
        self.assertEqual(
            json.loads(owned_target.read_bytes()),
            {"hook": f"{self.home}/h2.py", "seen": True},
        )

        managed_target.write_text(
            f'model = "host"\nprompt = "{self.home}/b.md"\n', encoding="utf-8"
        )
        adopt(self.fixture.root, self.fixture.home, operation_ids=frozenset({"config.toml-config"}))
        self.assertEqual(managed_source.read_bytes(), b'prompt = "@HOME@/b.md"\n')

    def test_home_that_cannot_be_written_into_config_stops_before_any_write(self) -> None:
        odd_home = Path(self.temporary.name) / "odd home"
        odd_home.mkdir()
        _, target = self.fixture.add_config("mcp.json", b'{"command": "@HOME@/x"}\n')

        with self.assertRaisesRegex(GuidanceError, "cannot render @HOME@"):
            sync(self.fixture.root, odd_home)
        self.assertFalse((odd_home / target.relative_to(self.fixture.home)).exists())

        # Sources without the token stay installable there.
        self.fixture.manifest["projections"].pop()
        self.fixture.write_manifest()
        self.assertIsNotNone(sync(self.fixture.root, odd_home).transaction_id)


class EditGuardIndexTests(unittest.TestCase):
    """Sync writes the rules the installed guard reads instead of the checkout."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.fixture = GuidanceFixture(base)
        (self.fixture.root / "hooks").mkdir()
        (self.fixture.root / "hooks" / "projection_edit_guard.py").write_bytes(
            (GUIDANCE_ROOT / "hooks" / "projection_edit_guard.py").read_bytes()
        )
        self.registry = base / "SKILL-SYSTEM" / "registry.json"
        self.registry.parent.mkdir()
        self.registry.write_text('{"skills": {}}\n', encoding="utf-8")
        self.fixture.manifest["edit_guard"] = "hooks/projection_edit_guard.py"
        self.fixture.write_manifest()
        self.index = self.fixture.home / ".local/state/persistent-guidance/edit-guard.json"

    def test_sync_writes_the_index(self) -> None:
        sync(self.fixture.root, self.fixture.home)

        rules = json.loads(self.index.read_bytes())["rules"]
        kernel = next(rule for rule in rules if rule["installed"].endswith(".alpha/AGENTS.md"))
        self.assertEqual(kernel["source"], str((self.fixture.root / "AGENTS.md").resolve()))

    def test_malformed_registry_stops_sync_before_any_write(self) -> None:
        self.registry.write_text("[]\n", encoding="utf-8")
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                with self.assertRaisesRegex(GuidanceError, "edit-guard index"):
                    sync(self.fixture.root, self.fixture.home, dry_run=dry_run)
        self.assertFalse((self.fixture.home / ".alpha").exists())
        self.assertFalse(self.index.exists())

    def test_missing_guard_script_fails_validation(self) -> None:
        self.fixture.manifest["edit_guard"] = "hooks/absent.py"
        self.fixture.write_manifest()
        with self.assertRaisesRegex(GuidanceError, "edit_guard does not exist"):
            plan_sync(self.fixture.root, self.fixture.home)


class AdoptTests(unittest.TestCase):
    """A host that rewrites its own configuration file must be reconcilable."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = GuidanceFixture(Path(self.temporary.name))
        self.fixture.write_home(".old/AGENTS.md", self.fixture.legacy)
        sync(self.fixture.root, self.fixture.home)
        self.kernel = self.fixture.home / ".alpha/AGENTS.md"

    def test_host_written_drift_is_pulled_back_into_the_canonical_source(self) -> None:
        self.kernel.write_bytes(b"canonical-v1\nhost-appended\n")

        adoptions = adopt(self.fixture.root, self.fixture.home)

        self.assertEqual([adoption.operation_id for adoption in adoptions], ["kernel"])
        self.assertEqual(
            (self.fixture.root / "AGENTS.md").read_bytes(),
            b"canonical-v1\nhost-appended\n",
        )

        # The conflict is gone, and because this source also feeds .new/AGENTS.md
        # the adopted content is now pending propagation to that sibling target.
        plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertFalse(plan.conflicts)
        self.assertEqual(
            [status.operation.operation_id for status in plan.changes], ["new-copy"]
        )

        sync(self.fixture.root, self.fixture.home)
        self.assertEqual(
            (self.fixture.home / ".new/AGENTS.md").read_bytes(),
            b"canonical-v1\nhost-appended\n",
        )
        self.assertFalse(plan_sync(self.fixture.root, self.fixture.home).changes)

    def test_dry_run_reports_without_touching_the_source(self) -> None:
        self.kernel.write_bytes(b"drifted\n")

        adoptions = adopt(self.fixture.root, self.fixture.home, dry_run=True)

        self.assertEqual(len(adoptions), 1)
        self.assertEqual(
            (self.fixture.root / "AGENTS.md").read_bytes(), b"canonical-v1\n"
        )

    def test_selection_leaves_other_drifted_targets_alone(self) -> None:
        self.kernel.write_bytes(b"drifted-kernel\n")
        (self.fixture.home / ".new/AGENTS.md").write_bytes(b"drifted-copy\n")

        adoptions = adopt(
            self.fixture.root, self.fixture.home, operation_ids=frozenset({"kernel"})
        )

        self.assertEqual([adoption.operation_id for adoption in adoptions], ["kernel"])
        self.assertEqual(
            (self.fixture.root / "AGENTS.md").read_bytes(), b"drifted-kernel\n"
        )

    def test_unknown_operation_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(GuidanceError, "unknown operation ids"):
            adopt(
                self.fixture.root,
                self.fixture.home,
                operation_ids=frozenset({"not-a-projection"}),
            )

    def test_legacy_content_is_not_adopted(self) -> None:
        """`legacy` means sync should overwrite the host file, not learn from it."""
        self.kernel.write_bytes(self.fixture.legacy)

        self.assertEqual(adopt(self.fixture.root, self.fixture.home), ())
        self.assertEqual(
            (self.fixture.root / "AGENTS.md").read_bytes(), b"canonical-v1\n"
        )

    def test_retirement_target_is_never_adopted(self) -> None:
        self.fixture.write_home(".old/AGENTS.md", self.fixture.legacy)

        self.assertEqual(adopt(self.fixture.root, self.fixture.home), ())

    def test_pending_canonical_edit_is_not_adopted_back_over_itself(self) -> None:
        """`managed-stale` carries this manager's own output, not host drift.

        The host file still matches what sync installed, so there is nothing to
        learn from it. Adopting it would overwrite an unsynced canonical edit
        with the previous generation of that same file.
        """
        (self.fixture.root / "AGENTS.md").write_bytes(b"canonical-v2\n")
        plan = plan_sync(self.fixture.root, self.fixture.home)
        kernel = next(
            status
            for status in plan.statuses
            if status.operation.operation_id == "kernel"
        )
        self.assertEqual(kernel.state, "managed-stale")

        self.assertEqual(adopt(self.fixture.root, self.fixture.home), ())
        self.assertEqual(
            (self.fixture.root / "AGENTS.md").read_bytes(), b"canonical-v2\n"
        )



class RepositorySourceTests(unittest.TestCase):
    """The shell layer: sources elsewhere in the checkout, grouped, some executable."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Nested, so the test's own `outside` sibling stays inside the temp dir.
        self.base = Path(self.temporary.name).resolve() / "checkout"
        self.base.mkdir()
        self.fixture = GuidanceFixture(self.base)
        shell = self.base / "shell"
        shell.mkdir()
        (shell / "bashrc").write_bytes(b"rc-v1\n")
        (shell / "profile").write_bytes(b"profile-v1\n")
        (shell / "tool.py").write_bytes(b"#!/usr/bin/env python3\n")
        (shell / "tool.py").chmod(0o755)
        self.fixture.manifest["repository_root"] = ".."

    def add_shell(self, source: str, target: str, **extra) -> Path:
        self.fixture.manifest["projections"].append(
            {
                "id": target,
                "source": source,
                "target": target,
                "hosts": ["alpha"],
                **({"independent": True} if not extra else extra),
            }
        )
        self.fixture.write_manifest()
        return self.fixture.home / target

    def test_sources_may_reach_the_repository_root_and_no_further(self) -> None:
        target = self.add_shell("../shell/bashrc", ".bashrc")
        sync(self.fixture.root, self.fixture.home)
        self.assertEqual(target.read_bytes(), b"rc-v1\n")

        del self.fixture.manifest["repository_root"]
        self.fixture.write_manifest()
        with self.assertRaisesRegex(GuidanceError, "must stay within its declared root"):
            load_host_manifest(self.fixture.root)

        self.fixture.manifest["repository_root"] = ".."
        (self.base.parent / "outside").write_bytes(b"x\n")
        self.addCleanup((self.base.parent / "outside").unlink)
        for source, error in (
            ("../../outside", "escapes the repository root"),
            ("../shell/../shell/bashrc", "must stay within its declared root"),
            ("../source/candidate-guidance/draft.md", "protected source path"),
        ):
            with self.subTest(source=source):
                (self.fixture.root / "candidate-guidance" / "draft.md").write_bytes(b"d\n")
                self.fixture.manifest["projections"][-1]["source"] = source
                self.fixture.write_manifest()
                with self.assertRaisesRegex(GuidanceError, error):
                    load_host_manifest(self.fixture.root)

        self.fixture.manifest["projections"][-1]["source"] = "../shell/bashrc"
        for root in ("shell", "../x", ""):
            with self.subTest(repository_root=root):
                self.fixture.manifest["repository_root"] = root
                self.fixture.write_manifest()
                with self.assertRaisesRegex(GuidanceError, "repository_root must be"):
                    load_host_manifest(self.fixture.root)

    def test_named_group_applies_together_and_blocks_only_itself(self) -> None:
        rc = self.add_shell("../shell/bashrc", ".bashrc", sync_group="shell")
        profile = self.add_shell("../shell/profile", ".bash_profile", sync_group="shell")
        self.fixture.write_home(".bashrc", b"hand-copied\n")
        (self.fixture.root / "AGENTS.md").write_bytes(b"canonical-v2\n")

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertEqual(
            [status.operation.operation_id for status in outcome.plan.conflicts],
            [".bashrc"],
        )
        self.assertFalse(profile.exists())
        self.assertEqual(rc.read_bytes(), b"hand-copied\n")
        self.assertEqual(
            (self.fixture.home / ".alpha/AGENTS.md").read_bytes(), b"canonical-v2\n"
        )

        for value, error in (
            ("Shell Files", "must be a lowercase name"),
            (True, "must be a lowercase name"),
        ):
            with self.subTest(sync_group=value):
                self.fixture.manifest["projections"][-1]["sync_group"] = value
                self.fixture.write_manifest()
                with self.assertRaisesRegex(GuidanceError, error):
                    load_host_manifest(self.fixture.root)
        self.fixture.manifest["projections"][-1]["sync_group"] = "shell"
        self.fixture.manifest["projections"][-1]["independent"] = True
        self.fixture.write_manifest()
        with self.assertRaisesRegex(GuidanceError, "exclusive"):
            load_host_manifest(self.fixture.root)

        del self.fixture.manifest["projections"][-1]["independent"]
        self.add_shell("../shell/bashrc", ".bashrc-copy", hosts=["alpha"])
        with self.assertRaisesRegex(GuidanceError, "shares its source"):
            load_host_manifest(self.fixture.root)

    def test_one_file_named_two_ways_is_one_source(self) -> None:
        # The kernel projections read AGENTS.md; this names it through the root.
        self.add_shell("../source/AGENTS.md", ".alias/AGENTS.md", sync_group="shell")
        with self.assertRaisesRegex(GuidanceError, "shares its source"):
            load_host_manifest(self.fixture.root)

    def test_execute_bits_follow_the_source_and_are_only_added(self) -> None:
        tool = self.add_shell("../shell/tool.py", ".local/bin/tool")
        rc = self.add_shell("../shell/bashrc", ".bashrc")
        sync(self.fixture.root, self.fixture.home)
        self.assertEqual(tool.stat().st_mode & 0o777, 0o755)
        self.assertEqual(rc.stat().st_mode & 0o777, 0o644)

        tool.chmod(0o600)
        rc.chmod(0o750)
        plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertEqual(state_of(plan, ".local/bin/tool"), "managed-stale")
        self.assertEqual(state_of(plan, ".bashrc"), "current")

        outcome = sync(self.fixture.root, self.fixture.home)

        self.assertIsNotNone(outcome.transaction_id)
        self.assertEqual(state_of(outcome.plan, ".local/bin/tool"), "current")
        self.assertEqual(tool.stat().st_mode & 0o777, 0o700)
        self.assertEqual(rc.stat().st_mode & 0o777, 0o750)
        rollback(self.fixture.root, self.fixture.home)
        self.assertEqual(tool.stat().st_mode & 0o777, 0o600)

        tool.chmod(0o744)  # owner can run it, but group and others can read and not run
        plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertEqual(state_of(plan, ".local/bin/tool"), "managed-stale")
        sync(self.fixture.root, self.fixture.home)
        self.assertEqual(tool.stat().st_mode & 0o777, 0o755)


class ReplaceUnownedTests(unittest.TestCase):
    """`sync --replace-unowned`: a file this manager never wrote is backed up and replaced."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = GuidanceFixture(Path(self.temporary.name))

    def test_unowned_file_is_replaced_with_a_backup_and_rolls_back(self) -> None:
        kernel = self.fixture.write_home(".alpha/AGENTS.md", b"hand-copied\n")
        self.assertEqual(
            state_of(plan_sync(self.fixture.root, self.fixture.home), "kernel"), "conflict"
        )
        preview = sync(self.fixture.root, self.fixture.home, dry_run=True, replace_unowned=True)
        self.assertEqual(state_of(preview.plan, "kernel"), "replace-unowned")
        self.assertEqual(kernel.read_bytes(), b"hand-copied\n")

        outcome = sync(self.fixture.root, self.fixture.home, replace_unowned=True)

        self.assertFalse(outcome.plan.conflicts)
        self.assertEqual(kernel.read_bytes(), b"canonical-v1\n")
        state = json.loads(
            (self.fixture.home / ".local/state/persistent-guidance/state.json").read_bytes()
        )
        backup = state["targets"][".alpha/AGENTS.md"]["backups"][0]
        self.assertEqual(
            (self.fixture.home / ".local/state/persistent-guidance" / backup).read_bytes(),
            b"hand-copied\n",
        )
        rollback(self.fixture.root, self.fixture.home)
        self.assertEqual(kernel.read_bytes(), b"hand-copied\n")

    def test_drift_from_a_managed_write_is_never_replaced(self) -> None:
        sync(self.fixture.root, self.fixture.home)
        kernel = self.fixture.write_home(".alpha/AGENTS.md", b"local edit\n")
        link = self.fixture.home / ".new/AGENTS.md"
        link.unlink()
        link.symlink_to(kernel)

        outcome = sync(self.fixture.root, self.fixture.home, replace_unowned=True)

        self.assertEqual(
            sorted(status.operation.operation_id for status in outcome.plan.conflicts),
            ["kernel", "new-copy"],
        )
        self.assertEqual(kernel.read_bytes(), b"local edit\n")

    def test_unowned_configs_keep_the_values_canonical_does_not_own(self) -> None:
        _, settings = self.fixture.add_config(
            "settings.json", b'{"effort": "high"}\n', host_owned_keys=[["seen"]]
        )
        _, config = self.fixture.add_config(
            "config.toml", b'model = "a"\n', managed_keys=[["model"]]
        )
        self.fixture.write_home(".alpha/settings.json", b'{"effort": "low", "seen": true}\n')
        self.fixture.write_home(".alpha/config.toml", b'model = "b"\ntheme = "dark"\n')
        plan = plan_sync(self.fixture.root, self.fixture.home)
        self.assertEqual(state_of(plan, "settings.json-config"), "conflict")
        self.assertEqual(state_of(plan, "config.toml-config"), "conflict")
        for status in plan.conflicts:
            self.assertTrue(status.detail.startswith(hostlib.UNOWNED_CONFLICT), status.detail)

        outcome = sync(self.fixture.root, self.fixture.home, replace_unowned=True)

        self.assertFalse(outcome.plan.conflicts)
        self.assertEqual(json.loads(settings.read_bytes()), {"effort": "high", "seen": True})
        self.assertEqual(
            tomllib.loads(config.read_text(encoding="utf-8")), {"model": "a", "theme": "dark"}
        )

    def test_backups_are_private_whatever_the_umask(self) -> None:
        self.fixture.write_home(".alpha/AGENTS.md", b"hand-copied\n")
        self.addCleanup(os.umask, os.umask(0o022))

        outcome = sync(self.fixture.root, self.fixture.home, replace_unowned=True)

        backups = self.fixture.home / ".local/state/persistent-guidance/backups"
        self.assertEqual(stat.S_IMODE(backups.stat().st_mode), 0o700)
        transaction = backups / outcome.transaction_id
        self.assertEqual(stat.S_IMODE(transaction.stat().st_mode), 0o700)

    def test_host_config_that_cannot_be_read_back_is_not_replaced(self) -> None:
        self.fixture.add_config(
            "settings.json", b'{"effort": "high"}\n', host_owned_keys=[["permissions", "allow"]]
        )
        old = b'{"permissions": "old-format", "model": "x"}\n'
        settings = self.fixture.write_home(".alpha/settings.json", old)

        outcome = sync(self.fixture.root, self.fixture.home, replace_unowned=True)

        self.assertEqual(state_of(outcome.plan, "settings.json-config"), "conflict")
        self.assertEqual(settings.read_bytes(), old)

    def test_interrupt_during_sync_restores_what_it_had_written(self) -> None:
        kernel = self.fixture.write_home(".alpha/AGENTS.md", b"hand-copied\n")
        real_write = hostlib._atomic_write
        written: list[Path] = []

        def interrupt_second_target(path: Path, data: bytes, mode: int) -> None:
            # One Ctrl-C, at the second target; the rollback's own writes go through.
            if len(written) == 1 and not Path(path).is_relative_to(self.fixture.home / ".local"):
                written.append(Path(path))
                raise KeyboardInterrupt
            if not Path(path).is_relative_to(self.fixture.home / ".local"):
                written.append(Path(path))
            return real_write(path, data, mode)

        with mock.patch.object(hostlib, "_atomic_write", interrupt_second_target):
            with self.assertRaises(KeyboardInterrupt):
                sync(self.fixture.root, self.fixture.home, replace_unowned=True)

        self.assertGreaterEqual(len(written), 2)
        self.assertEqual(kernel.read_bytes(), b"hand-copied\n")
        self.assertFalse((self.fixture.home / ".new/AGENTS.md").exists())
        self.assertFalse(
            (self.fixture.home / ".local/state/persistent-guidance/state.json").exists()
        )

    def test_target_that_becomes_a_symlink_after_preflight_is_left_alone(self) -> None:
        kernel = self.fixture.home / ".alpha/AGENTS.md"
        real_classify = hostlib._classify
        calls: list[str] = []

        def link_after_recheck(operation, *args, **kwargs):
            status = real_classify(operation, *args, **kwargs)
            calls.append(operation.operation_id)
            if operation.operation_id == "kernel" and calls.count("kernel") == 2:
                kernel.parent.mkdir(parents=True, exist_ok=True)
                kernel.symlink_to(self.fixture.home / "nowhere")
            return status

        with mock.patch.object(hostlib, "_classify", link_after_recheck):
            with self.assertRaisesRegex(GuidanceError, "became a symlink"):
                sync(self.fixture.root, self.fixture.home)

        self.assertTrue(kernel.is_symlink())


if __name__ == "__main__":
    unittest.main()
