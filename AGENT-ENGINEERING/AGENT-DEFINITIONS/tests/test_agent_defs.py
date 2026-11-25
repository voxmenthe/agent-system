from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    loader = importlib.machinery.SourceFileLoader(
        "agent_defs", str(ROOT / "agent-defs")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution so @dataclass can resolve the module globals.
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


agent_defs = _load_module()


DEFINITION = """---
name: {name}
description: A bounded role used by the tests.
model: {model}
---

Body text.
"""


class PolicyTests(unittest.TestCase):
    def test_accepts_stable_model_tokens(self):
        for model in sorted(agent_defs.ALLOWED_MODELS):
            definitions = {
                "probe.md": DEFINITION.format(name="probe", model=model).encode()
            }
            self.assertEqual(agent_defs.policy_errors(definitions), [], model)

    def test_rejects_full_model_id(self):
        # The defect this manager exists to prevent: a pinned version that dies
        # with the next model release.
        definitions = {
            "probe.md": DEFINITION.format(
                name="probe", model="claude-opus-4-6"
            ).encode()
        }
        errors = agent_defs.policy_errors(definitions)
        self.assertEqual(len(errors), 1)
        self.assertIn("not a stable token", errors[0])

    def test_rejects_name_that_does_not_match_filename(self):
        definitions = {
            "probe.md": DEFINITION.format(name="other", model="inherit").encode()
        }
        errors = agent_defs.policy_errors(definitions)
        self.assertEqual(len(errors), 1)
        self.assertIn("must match the filename stem", errors[0])

    def test_rejects_underscore_in_name(self):
        definitions = {
            "a_b.md": DEFINITION.format(name="a_b", model="inherit").encode()
        }
        self.assertIn(
            "lowercase words joined by hyphens",
            agent_defs.policy_errors(definitions)[0],
        )

    def test_rejects_missing_frontmatter(self):
        definitions = {"probe.md": b"no frontmatter here\n"}
        self.assertIn("missing a leading", agent_defs.policy_errors(definitions)[0])

    def test_rejects_non_markdown_extension(self):
        definitions = {
            "probe.m": DEFINITION.format(name="probe", model="inherit").encode()
        }
        self.assertIn(".md extension", agent_defs.policy_errors(definitions)[0])

    def test_shipped_definitions_satisfy_policy(self):
        self.assertEqual(agent_defs.policy_errors(agent_defs.read_definitions()), [])


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.library = self.tmp / "library"
        self.library.mkdir()
        self.home = self.tmp / "home"
        (self.home / ".claude" / "agents").mkdir(parents=True)
        original = agent_defs.CANONICAL_DIR
        agent_defs.CANONICAL_DIR = self.library
        self.addCleanup(setattr, agent_defs, "CANONICAL_DIR", original)

    def _write_library(self, name: str, body: str = "Body text.\n"):
        text = f"---\nname: {name}\ndescription: d\nmodel: inherit\n---\n\n{body}"
        (self.library / f"{name}.md").write_text(text)
        return text

    @property
    def target_dir(self) -> Path:
        return self.home / ".claude" / "agents"

    def _loaded(self) -> list[str]:
        return sorted(p.name for p in self.target_dir.iterdir())

    # --- the core contract: the library is not projected wholesale -----------

    def test_library_is_not_projected_by_default(self):
        self._write_library("alpha")
        self._write_library("beta")
        plan = agent_defs.plan_sync(self.home)
        self.assertEqual(plan.operations, ())
        agent_defs.apply_plan(self.home, plan)
        self.assertEqual(self._loaded(), [])

    def test_load_projects_only_the_named_agent(self):
        canonical = self._write_library("alpha")
        self._write_library("beta")
        plan = agent_defs.plan_sync(self.home, load=("alpha",))
        self.assertEqual(
            [(op.kind, op.filename) for op in plan.operations], [("create", "alpha.md")]
        )
        agent_defs.apply_plan(self.home, plan)
        self.assertEqual(self._loaded(), ["alpha.md"])
        self.assertEqual((self.target_dir / "alpha.md").read_text(), canonical)

    def test_sync_refreshes_loaded_agents_without_adding_others(self):
        self._write_library("alpha")
        self._write_library("beta")
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, load=("alpha",))
        )
        revised = self._write_library("alpha", body="Revised body.\n")

        plan = agent_defs.plan_sync(self.home)
        self.assertEqual(
            [(op.kind, op.filename) for op in plan.operations], [("update", "alpha.md")]
        )
        agent_defs.apply_plan(self.home, plan)
        self.assertEqual((self.target_dir / "alpha.md").read_text(), revised)
        self.assertEqual(self._loaded(), ["alpha.md"])

    def test_unload_removes_only_the_named_agent(self):
        self._write_library("alpha")
        self._write_library("beta")
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, load=("alpha", "beta"))
        )
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, unload=("alpha",))
        )
        self.assertEqual(self._loaded(), ["beta.md"])

    def test_unload_all_empties_the_target(self):
        self._write_library("alpha")
        self._write_library("beta")
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, load=("alpha", "beta"))
        )
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, unload_all=True)
        )
        self.assertEqual(self._loaded(), [])
        self.assertEqual(agent_defs.load_state(self.home)["projected"], {})

    def test_loading_an_unknown_agent_fails_loudly(self):
        self._write_library("alpha")
        with self.assertRaises(agent_defs.AgentDefsError) as caught:
            agent_defs.plan_sync(self.home, load=("nope",))
        self.assertIn("not an agent in the library", str(caught.exception))

    def test_unloading_an_agent_that_is_not_loaded_fails_loudly(self):
        self._write_library("alpha")
        with self.assertRaises(agent_defs.AgentDefsError) as caught:
            agent_defs.plan_sync(self.home, unload=("alpha",))
        self.assertIn("not loaded", str(caught.exception))

    def test_retiring_a_loaded_definition_withdraws_it(self):
        self._write_library("alpha")
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, load=("alpha",))
        )
        (self.library / "alpha.md").unlink()
        self._write_library("beta")

        plan = agent_defs.plan_sync(self.home)
        self.assertEqual(
            [(op.kind, op.filename) for op in plan.changes], [("remove", "alpha.md")]
        )
        agent_defs.apply_plan(self.home, plan)
        self.assertEqual(self._loaded(), [])

    # --- ownership -----------------------------------------------------------

    def test_unmanaged_target_file_blocks_sync(self):
        self._write_library("alpha")
        (self.target_dir / "alpha.md").write_text("hand written\n")
        plan = agent_defs.plan_sync(self.home)
        self.assertEqual([op.kind for op in plan.operations], ["conflict"])
        with self.assertRaises(agent_defs.SyncConflict):
            agent_defs.apply_plan(self.home, plan)
        self.assertEqual((self.target_dir / "alpha.md").read_text(), "hand written\n")

    def test_take_ownership_overwrites_and_backs_up(self):
        canonical = self._write_library("alpha")
        (self.target_dir / "alpha.md").write_text("hand written\n")
        plan = agent_defs.plan_sync(self.home, take_ownership=True)
        agent_defs.apply_plan(self.home, plan)
        self.assertEqual((self.target_dir / "alpha.md").read_text(), canonical)
        backups = list(
            (self.home / ".local/state/agent-definitions/backups").rglob("alpha.md")
        )
        self.assertEqual([p.read_text() for p in backups], ["hand written\n"])

    def test_edit_in_place_after_loading_is_a_conflict(self):
        self._write_library("alpha")
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, load=("alpha",))
        )
        (self.target_dir / "alpha.md").write_text("locally tweaked\n")
        plan = agent_defs.plan_sync(self.home)
        self.assertEqual([op.kind for op in plan.operations], ["conflict"])
        self.assertIn("edited in place", plan.operations[0].detail)

    def test_target_already_matching_canonical_is_recorded_as_owned(self):
        # A file the sync had no work to do on is still ours. Leaving it out of
        # the state record made the next canonical edit look like a conflict.
        canonical = self._write_library("alpha")
        (self.target_dir / "alpha.md").write_text(canonical)
        plan = agent_defs.plan_sync(self.home)
        self.assertEqual([op.kind for op in plan.operations], ["current"])
        agent_defs.apply_plan(self.home, plan)
        self.assertIn("alpha.md", agent_defs.load_state(self.home)["projected"])

        self._write_library("alpha", body="Revised body.\n")
        self.assertEqual(
            [op.kind for op in agent_defs.plan_sync(self.home).operations], ["update"]
        )

    # --- recovery ------------------------------------------------------------

    def test_rollback_restores_a_load(self):
        self._write_library("alpha")
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, load=("alpha",))
        )
        self.assertEqual(self._loaded(), ["alpha.md"])
        agent_defs.rollback(self.home)
        self.assertEqual(self._loaded(), [])

    def test_rollback_restores_an_unload(self):
        canonical = self._write_library("alpha")
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, load=("alpha",))
        )
        agent_defs.apply_plan(
            self.home, agent_defs.plan_sync(self.home, unload_all=True)
        )
        agent_defs.rollback(self.home)
        self.assertEqual((self.target_dir / "alpha.md").read_text(), canonical)

    def test_rollback_without_a_transaction_fails_loudly(self):
        self._write_library("alpha")
        with self.assertRaises(agent_defs.AgentDefsError):
            agent_defs.rollback(self.home)

    def test_empty_library_fails_loudly(self):
        with self.assertRaises(agent_defs.AgentDefsError):
            agent_defs.plan_sync(self.home)

    def test_state_from_another_manager_is_rejected(self):
        self._write_library("alpha")
        agent_defs.save_state(
            self.home, {"manager_id": "someone-else", "projected": {}}
        )
        with self.assertRaises(agent_defs.AgentDefsError):
            agent_defs.plan_sync(self.home)


if __name__ == "__main__":
    unittest.main()
