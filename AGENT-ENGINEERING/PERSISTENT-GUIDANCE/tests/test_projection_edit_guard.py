from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "projection_edit_guard.py"
_spec = importlib.util.spec_from_file_location("projection_edit_guard", HOOK)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


class ProjectionEditGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.engineering = self.base / "AGENT-ENGINEERING"
        self.guidance = self.engineering / "PERSISTENT-GUIDANCE"
        self.skills = self.engineering / "SKILL-SYSTEM"
        self.home = self.base / "home"
        self.home.mkdir()
        self.guidance.mkdir(parents=True)
        self.script = self.base / "installed-hooks" / HOOK.name
        self.script.parent.mkdir(parents=True)
        self.skills.mkdir()
        shutil.copyfile(HOOK, self.script)
        self.hosts = {
            "projections": [
                {"source": "AGENTS.md", "target": ".claude/CLAUDE.md"},
                {
                    "source_tree": "config/claude/commands",
                    "target_tree": ".claude/commands",
                    "include": ["*.md"],
                },
                {
                    "source_tree": "policy",
                    "target_tree": ".codex/policy",
                    "include": ["manifest.json", "packs/*.md"],
                },
                {
                    "source": "config/codex/config.toml",
                    "target": ".codex/config.toml",
                    "managed_keys": [["personality"]],
                },
                {
                    "source": "config/claude/settings.json",
                    "target": ".claude/settings.json",
                    "host_owned_keys": [],
                },
            ],
            "retirements": [{"target": ".retired/AGENTS.md"}],
            "releases": [{"target": ".released/config.json"}],
        }
        self.registry = {
            "skills": {
                "delegate": {
                    "ownership": "custom",
                    "source": "skills/delegate",
                    "install_targets": ["~/.agents/skills/delegate"],
                },
                "legacy": {
                    "ownership": "legacy-unmanaged",
                    "lifecycle": "retired",
                    "install_targets": ["~/.agents/skills/legacy"],
                },
            }
        }
        self.write_maps()
        (self.guidance / "AGENTS.md").write_text("canonical\n", encoding="utf-8")
        source = self.skills / "skills" / "delegate"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("canonical\n", encoding="utf-8")
        installed = self.home / ".agents" / "skills" / "delegate"
        installed.mkdir(parents=True)
        (installed / "SKILL.md").write_text("installed\n", encoding="utf-8")

    def write_maps(self, enabled_hosts: frozenset[str] | None = None) -> None:
        (self.guidance / "hosts.json").write_text(
            json.dumps(self.hosts), encoding="utf-8"
        )
        (self.skills / "registry.json").write_text(
            json.dumps(self.registry), encoding="utf-8"
        )
        index = guard.build_index(self.guidance, self.home, enabled_hosts)
        path = self.home / guard.INDEX
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(index), encoding="utf-8")

    def run_raw(self, payload: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(self.script)],
            input=payload,
            text=True,
            capture_output=True,
            cwd=self.home,
            env={**os.environ, "HOME": str(self.home)},
            check=False,
        )

    def run_hook(
        self, path: str | Path | None, tool: str = "Edit", cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        field = "notebook_path" if tool == "NotebookEdit" else "file_path"
        return self.run_raw(
            json.dumps(
                {
                    "tool_name": tool,
                    "tool_input": {} if path is None else {field: str(path)},
                    "cwd": str(cwd if cwd is not None else self.base),
                }
            )
        )

    def assert_blocked(
        self, result: subprocess.CompletedProcess[str], canonical: Path, command: str
    ) -> None:
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("installed projection", result.stderr)
        self.assertIn(str(canonical), result.stderr)
        self.assertIn(command, result.stderr)
        self.assertEqual(len(result.stderr.splitlines()), 1)

    def assert_allowed(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def assert_error(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("projection-edit-guard:", result.stderr)
        self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_skill_edit_is_blocked(self) -> None:
        result = self.run_hook("~/.agents/skills/delegate/SKILL.md")
        self.assert_blocked(
            result,
            self.skills / "skills/delegate/SKILL.md",
            f"cd {self.skills} && bin/skill-system refresh --apply",
        )
        self.assertIn(
            str(self.home / ".agents/skills/delegate/SKILL.md"), result.stderr
        )

    def test_skill_edit_through_claude_symlink_is_blocked(self) -> None:
        alias = self.home / ".claude/skills/delegate"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(
            self.home / ".agents/skills/delegate", target_is_directory=True
        )
        self.assert_blocked(
            self.run_hook(alias / "SKILL.md"),
            self.skills / "skills/delegate/SKILL.md",
            "bin/skill-system refresh --apply",
        )

    def test_write_of_new_tree_file_is_blocked(self) -> None:
        target = self.home / ".claude/commands/new.md"
        self.assertFalse(target.exists())
        self.assert_blocked(
            self.run_hook(target, "Write"),
            self.guidance / "config/claude/commands/new.md",
            f"cd {self.guidance} && ./guidance sync",
        )

    def test_guidance_file_projection_is_blocked(self) -> None:
        self.assert_blocked(
            self.run_hook("~/.claude/CLAUDE.md"),
            self.guidance / "AGENTS.md",
            "./guidance sync",
        )

    def test_host_owned_keys_do_not_release_whole_file(self) -> None:
        self.assert_blocked(
            self.run_hook("~/.claude/settings.json"),
            self.guidance / "config/claude/settings.json",
            "./guidance sync",
        )

    def test_selected_settings_are_allowed_even_with_empty_managed_keys(self) -> None:
        for keys in ([["personality"]], []):
            with self.subTest(keys=keys):
                self.hosts["projections"][3]["managed_keys"] = keys
                self.write_maps()
                self.assert_allowed(self.run_hook("~/.codex/config.toml"))

    def test_canonical_and_ordinary_repository_files_are_allowed(self) -> None:
        for path in (
            self.guidance / "AGENTS.md",
            self.skills / "skills/delegate/SKILL.md",
            self.base / "README.md",
        ):
            with self.subTest(path=path):
                self.assert_allowed(self.run_hook(path))

    def test_projection_symlink_into_canonical_tree_is_allowed(self) -> None:
        target = self.home / ".claude/CLAUDE.md"
        target.parent.mkdir()
        target.symlink_to(self.guidance / "AGENTS.md")
        self.assert_allowed(self.run_hook(target))

    def test_new_file_through_canonical_tree_symlink_is_allowed(self) -> None:
        source = self.guidance / "config/claude/commands"
        source.mkdir(parents=True)
        target = self.home / ".claude/commands"
        target.parent.mkdir()
        target.symlink_to(source, target_is_directory=True)
        self.assert_allowed(self.run_hook(target / "new.md", "Write"))

    def test_relative_path_uses_payload_cwd(self) -> None:
        self.assert_blocked(
            self.run_hook("delegate/SKILL.md", cwd=self.home / ".agents/skills"),
            self.skills / "skills/delegate/SKILL.md",
            "bin/skill-system refresh --apply",
        )

    def test_multiedit_and_notebookedit_are_blocked(self) -> None:
        for tool, name in (("MultiEdit", "SKILL.md"), ("NotebookEdit", "demo.ipynb")):
            with self.subTest(tool=tool):
                self.assert_blocked(
                    self.run_hook(f"~/.agents/skills/delegate/{name}", tool),
                    self.skills / "skills/delegate" / name,
                    "bin/skill-system refresh --apply",
                )

    def test_include_patterns_are_relative_to_tree(self) -> None:
        for relative in ("manifest.json", "packs/testing.md"):
            with self.subTest(relative=relative):
                self.assert_blocked(
                    self.run_hook(f"~/.codex/policy/{relative}"),
                    self.guidance / "policy" / relative,
                    "./guidance sync",
                )

    def test_patterns_match_like_sync_and_skills_cover_their_whole_tree(self) -> None:
        # Sync projects `*.md` from the top of the tree only; nested files are not installed.
        self.assert_allowed(self.run_hook(self.home / ".claude/commands/sub/notes.md"))
        self.assert_blocked(
            self.run_hook(self.home / ".agents/skills/delegate/scripts/run.sh", "Write"),
            self.skills / "skills/delegate/scripts/run.sh",
            "bin/skill-system refresh --apply",
        )

    def test_projections_of_disabled_hosts_are_not_guarded(self) -> None:
        self.hosts["projections"][0]["hosts"] = ["claude"]
        self.hosts["projections"][2]["hosts"] = ["codex"]
        self.write_maps(enabled_hosts=frozenset({"codex"}))

        self.assert_allowed(self.run_hook(self.home / ".claude/CLAUDE.md"))
        self.assert_blocked(
            self.run_hook("~/.codex/policy/manifest.json"),
            self.guidance / "policy/manifest.json",
            "./guidance sync",
        )

    def test_sources_elsewhere_in_the_checkout_are_canonical(self) -> None:
        self.hosts["repository_root"] = "../.."
        self.hosts["projections"].append({"source": "../../SHELL/.bashrc", "target": ".bashrc"})
        self.write_maps()
        canonical = self.base / "SHELL/.bashrc"
        canonical.parent.mkdir()
        canonical.write_text("canonical\n", encoding="utf-8")

        self.assert_allowed(self.run_hook(canonical))
        installed = self.home / ".bashrc"
        installed.write_text("installed\n", encoding="utf-8")
        self.assert_blocked(self.run_hook(installed), canonical, "./guidance sync")
        installed.unlink()
        installed.symlink_to(canonical)  # an older setup linked dotfiles into the checkout
        self.assert_allowed(self.run_hook(installed))

    def test_unmanaged_files_and_path_prefix_neighbors_are_allowed(self) -> None:
        for path in (
            "~/.claude/commands/new.txt",
            "~/.claude/commands-extra/new.md",
            "~/.claude/CLAUDE.md.backup",
            "~/.claude/CLAUDE.md/child",
            "~/.agents/skills/delegate-extra/SKILL.md",
            "~/.agents/skills/legacy/SKILL.md",
            "~/.retired/AGENTS.md",
            "~/.released/config.json",
            "~/.codex/policy/other/manifest.json",
            self.base / "AGENT-ENGINEERING-extra/file.md",
        ):
            with self.subTest(path=path):
                self.assert_allowed(self.run_hook(path))

    def test_missing_path_and_unrelated_tools_are_allowed(self) -> None:
        self.assert_allowed(self.run_hook(None))
        self.assert_allowed(self.run_hook("~/.agents/skills/delegate/SKILL.md", "Read"))

    def test_malformed_hook_input_is_a_nonblocking_error(self) -> None:
        for payload in (
            "not JSON",
            "[]",
            json.dumps({"tool_name": "Edit", "tool_input": []}),
            json.dumps({"tool_name": "Edit", "tool_input": {"file_path": 7}}),
        ):
            with self.subTest(payload=payload):
                self.assert_error(self.run_raw(payload))

    def test_host_directory_symlinked_after_sync_is_still_guarded(self) -> None:
        moved = self.base / "dotfiles-claude"
        moved.mkdir()
        (self.home / ".claude").symlink_to(moved, target_is_directory=True)
        self.assert_blocked(
            self.run_hook("~/.claude/CLAUDE.md"),
            self.guidance / "AGENTS.md",
            "./guidance sync",
        )

    def test_guard_reads_only_the_index_not_the_checkout(self) -> None:
        (self.guidance / "hosts.json").unlink()
        (self.skills / "registry.json").unlink()
        self.assert_blocked(
            self.run_hook("~/.claude/CLAUDE.md"),
            self.guidance / "AGENTS.md",
            "./guidance sync",
        )

    def test_missing_or_malformed_index_is_a_nonblocking_error(self) -> None:
        path = self.home / guard.INDEX
        for contents in (None, "not JSON", "{}", "[]", '{"schema_version": 1}'):
            with self.subTest(contents=contents):
                if contents is None:
                    path.unlink()
                else:
                    path.write_text(contents, encoding="utf-8")
                self.assert_error(self.run_hook("~/.claude/CLAUDE.md"))

    def test_index_expands_home_from_its_argument(self) -> None:
        index = guard.build_index(self.guidance, self.home)
        installed = {rule["installed"] for rule in index["rules"]}
        self.assertIn(str(self.home / ".agents/skills/delegate"), installed)
        self.assertEqual(index["exempt"], str(self.engineering))

    def test_missing_or_malformed_maps_stop_the_index(self) -> None:
        for path in (self.guidance / "hosts.json", self.skills / "registry.json"):
            for contents in (None, "not JSON", "{}", "[]"):
                with self.subTest(path=path.name, contents=contents):
                    self.write_maps()
                    if contents is None:
                        path.unlink()
                    else:
                        path.write_text(contents, encoding="utf-8")
                    with self.assertRaises((OSError, ValueError, KeyError, TypeError)):
                        guard.build_index(self.guidance, self.home)

    def test_invalid_later_records_stop_the_index(self) -> None:
        mutations = (
            lambda: self.hosts["projections"].append({"source": "broken"}),
            lambda: self.hosts["projections"].append({"source_tree": "broken"}),
            lambda: self.registry["skills"].update(
                {"broken": {"source": "skills/broken"}}
            ),
            lambda: self.registry["skills"].update({"broken": None}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                original_hosts = json.dumps(self.hosts)
                original_registry = json.dumps(self.registry)
                mutate()
                with self.assertRaises((OSError, ValueError, KeyError, TypeError)):
                    self.write_maps()
                self.hosts = json.loads(original_hosts)
                self.registry = json.loads(original_registry)


if __name__ == "__main__":
    unittest.main()
