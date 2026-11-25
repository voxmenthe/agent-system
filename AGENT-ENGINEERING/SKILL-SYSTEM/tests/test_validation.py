from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skill_system import SkillSystem, ValidationError
from tests.helpers import custom_record, make_system, write_json, write_skill


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "source"
        self.home = base / "home"
        make_system(self.root, self.home, ("alpha", "beta"))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def system(self) -> SkillSystem:
        return SkillSystem(self.root, self.home)

    def test_valid_canonical_tree_does_not_read_live_skill_content(self) -> None:
        live = self.home / ".agents" / "skills" / "alpha"
        live.mkdir(parents=True)
        (live / "SKILL.md").write_text("broken live content")

        report = self.system().validate()

        self.assertTrue(report.ok)
        self.assertEqual(report.custom_skills, ("alpha", "beta"))

    def test_invalid_frontmatter_and_name_mismatch_fail(self) -> None:
        (self.root / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: other\ndescription: Use when testing.\nextra: forbidden\n---\n"
        )

        with self.assertRaisesRegex(ValidationError, "frontmatter|registry key"):
            self.system().validate()

    def test_disable_model_invocation_frontmatter_key_is_strictly_optional(self) -> None:
        skill_md = self.root / "skills" / "alpha" / "SKILL.md"
        openai_yaml = self.root / "skills" / "alpha" / "agents" / "openai.yaml"
        skill_md.write_text(
            "---\nname: alpha\ndescription: Use when testing. Do not use otherwise.\n"
            "disable-model-invocation: true\n---\n"
        )
        openai_yaml.write_text(
            openai_yaml.read_text()
            + "policy:\n  allow_implicit_invocation: false\n"
        )
        self.assertTrue(self.system().validate().ok)

        skill_md.write_text(
            "---\nname: alpha\ndescription: Use when testing. Do not use otherwise.\n"
            "disable-model-invocation: yes\n---\n"
        )
        with self.assertRaisesRegex(ValidationError, "disable-model-invocation"):
            self.system().validate()

    def test_yaml_ambiguous_plain_frontmatter_scalar_requires_quotes(self) -> None:
        skill_md = self.root / "skills" / "alpha" / "SKILL.md"
        skill_md.write_text(
            "---\n"
            "name: alpha\n"
            "description: Use when mapping topology: ownership. "
            "Do not use otherwise.\n"
            "---\n"
        )
        with self.assertRaisesRegex(ValidationError, "quoted YAML scalar"):
            self.system().validate()

        skill_md.write_text(
            "---\n"
            "name: alpha\n"
            'description: "Use when mapping topology: ownership. '
            'Do not use otherwise."\n'
            "---\n"
        )
        self.assertTrue(self.system().validate().ok)

        skill_md.write_text(
            "---\n"
            "name: alpha\n"
            'description: "Use when mapping topology. Do not use otherwise.\n'
            "---\n"
        )
        with self.assertRaisesRegex(ValidationError, "quoted YAML scalar"):
            self.system().validate()

    def test_invocation_policies_must_match_across_hosts(self) -> None:
        skill_md = self.root / "skills" / "alpha" / "SKILL.md"
        openai_yaml = self.root / "skills" / "alpha" / "agents" / "openai.yaml"
        skill_md.write_text(
            "---\nname: alpha\ndescription: Use when testing. Do not use otherwise.\n"
            "disable-model-invocation: true\n---\n"
        )
        with self.assertRaisesRegex(ValidationError, "invocation policy mismatch"):
            self.system().validate()

        write_skill(self.root, "alpha")
        openai_yaml.write_text(
            openai_yaml.read_text()
            + "policy:\n  allow_implicit_invocation: false\n"
        )
        with self.assertRaisesRegex(ValidationError, "invocation policy mismatch"):
            self.system().validate()

    def test_missing_or_invalid_runtime_metadata_fails(self) -> None:
        (self.root / "skills" / "alpha" / "agents" / "openai.yaml").unlink()
        with self.assertRaisesRegex(ValidationError, "openai.yaml"):
            self.system().validate()

        write_skill(self.root, "alpha")
        (self.root / "skills" / "alpha" / "agents" / "openai.yaml").write_text(
            "interface:\n  display_name: unquoted\n"
        )
        with self.assertRaisesRegex(ValidationError, "quoted|short_description"):
            self.system().validate()

    def test_broken_local_markdown_reference_fails(self) -> None:
        skill_md = self.root / "skills" / "alpha" / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text() + "\nRead [the missing guide](references/missing.md).\n"
        )

        with self.assertRaisesRegex(ValidationError, "missing.md"):
            self.system().validate()

    def test_unknown_dependency_cycle_and_retired_dependency_fail(self) -> None:
        registry = json.loads((self.root / "registry.json").read_text())
        registry["skills"]["alpha"]["dependencies"] = ["missing"]
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "undeclared dependency"):
            self.system().validate()

        registry["skills"]["alpha"]["dependencies"] = ["beta"]
        registry["skills"]["beta"]["dependencies"] = ["alpha"]
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "cycle"):
            self.system().validate()

        registry["skills"]["beta"]["dependencies"] = []
        registry["skills"]["beta"]["lifecycle"] = "retired"
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "retired"):
            self.system().validate()

    def test_duplicate_target_and_path_escape_fail(self) -> None:
        registry = json.loads((self.root / "registry.json").read_text())
        registry["skills"]["beta"]["install_targets"] = [
            "~/.agents/skills/alpha"
        ]
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "duplicate install target"):
            self.system().validate()

        registry["skills"]["beta"]["install_targets"] = [
            "~/.agents/skills/beta"
        ]
        registry["skills"]["alpha"]["source"] = "../escape"
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "escapes"):
            self.system().validate()

    def test_unknown_schema_lifecycle_effect_and_fields_fail_loudly(self) -> None:
        registry = json.loads((self.root / "registry.json").read_text())
        registry["schema_version"] = 2
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "schema_version"):
            self.system().validate()

        registry["schema_version"] = 1
        registry["skills"]["alpha"]["lifecycle"] = "almost-stable"
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "lifecycle"):
            self.system().validate()

        registry["skills"]["alpha"]["lifecycle"] = "experimental"
        registry["skills"]["alpha"]["effect_ceiling"] = "root"
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "effect_ceiling"):
            self.system().validate()

        registry["skills"]["alpha"]["effect_ceiling"] = "local-write"
        registry["surprise"] = True
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "unknown field"):
            self.system().validate()

    def test_provenance_optional_fields_and_exit_phase_are_strict(self) -> None:
        registry = json.loads((self.root / "registry.json").read_text())
        registry["skills"]["alpha"]["provenance"]["notes"] = 42
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "provenance.notes"):
            self.system().validate()

        del registry["skills"]["alpha"]["provenance"]["notes"]
        legacy = {
            "lifecycle": "deprecated",
            "ownership": "legacy-unmanaged",
            "install_targets": ["~/.agents/skills/legacy"],
            "dependencies": [],
            "effect_ceiling": "local-write",
            "provenance": {
                "origin": "snapshot",
                "revision": "fixture",
                "license": "MIT",
                "observed_hash": "sha256:" + "0" * 64,
                "disposition": "probation",
                "exit_phase": True,
            },
            "evaluation_profile": "manual-probation",
        }
        registry["skills"]["legacy"] = legacy
        write_json(self.root / "registry.json", registry)
        with self.assertRaisesRegex(ValidationError, "exit_phase"):
            self.system().validate()

    def test_symlink_and_special_file_are_rejected(self) -> None:
        target = self.root / "skills" / "alpha" / "linked"
        target.symlink_to("SKILL.md")
        with self.assertRaisesRegex(ValidationError, "symlink"):
            self.system().validate()

    def test_hidden_framework_assumption_is_rejected(self) -> None:
        skill_md = self.root / "skills" / "alpha" / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text()
            + "\nRun `/setup` and update the progress tracker before continuing.\n"
        )

        with self.assertRaisesRegex(ValidationError, "hidden framework assumption"):
            self.system().validate()

    def test_legacy_and_external_records_are_audit_only(self) -> None:
        registry = json.loads((self.root / "registry.json").read_text())
        registry["skills"]["legacy"] = {
            "lifecycle": "deprecated",
            "ownership": "legacy-unmanaged",
            "install_targets": ["~/.agents/skills/legacy"],
            "dependencies": [],
            "effect_ceiling": "local-write",
            "provenance": {
                "origin": "mattpocock/skills",
                "revision": "fixture",
                "license": "MIT",
                "observed_hash": "sha256:" + "0" * 64,
                "disposition": "probation",
                "exit_phase": 7,
            },
            "evaluation_profile": "manual-probation",
        }
        registry["skills"]["external"] = {
            "ownership": "external",
            "install_targets": ["~/.agents/skills/external"],
            "dependencies": [],
            "effect_ceiling": "external-write",
            "provenance": {
                "origin": "vercel-labs/skills",
                "revision": "fixture",
                "license": "MIT",
                "manager": "skills-cli",
            },
            "evaluation_profile": "external",
        }
        write_json(self.root / "registry.json", registry)

        report = self.system().validate()
        self.assertEqual(report.legacy_skills, ("legacy",))
        self.assertEqual(report.external_skills, ("external",))
        with self.assertRaisesRegex(ValidationError, "not custom"):
            self.system().install("legacy", apply=False)

    def test_bytecode_cache_files_are_ignored_in_hash_status_and_install(self) -> None:
        from skill_system import configure_mimo, content_hash

        alpha_src = self.root / "skills" / "alpha"
        helper = alpha_src / "scripts" / "helper.py"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text("print('ok')\n")
        baseline_hash = content_hash(alpha_src)

        pycache_src = alpha_src / "scripts" / "__pycache__"
        pycache_src.mkdir(parents=True, exist_ok=True)
        (pycache_src / "helper.cpython-314.pyc").write_bytes(b"bytecode")
        (alpha_src / "stray.pyo").write_bytes(b"optimized")

        self.assertEqual(baseline_hash, content_hash(alpha_src))
        self.system().install("alpha", apply=True)

        alpha_target = self.home / ".agents" / "skills" / "alpha"
        self.assertFalse((alpha_target / "scripts" / "__pycache__").exists())
        self.assertFalse((alpha_target / "stray.pyo").exists())
        self.assertEqual("current", self.system().status().skills["alpha"].state)

        target_pycache = alpha_target / "scripts" / "__pycache__"
        target_pycache.mkdir(parents=True, exist_ok=True)
        (target_pycache / "runtime.cpython-314.pyc").write_bytes(b"live-bytecode")
        self.assertEqual("current", self.system().status().skills["alpha"].state)

        configure_mimo(self.root, self.home, apply=True)
        mimo_alpha = self.home / ".config" / "mimocode" / "skills" / "alpha"
        self.assertFalse((mimo_alpha / "scripts" / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
