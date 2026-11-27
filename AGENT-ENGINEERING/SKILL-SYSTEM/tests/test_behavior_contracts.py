from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from skill_system import content_hash


ROOT = Path(__file__).resolve().parents[1]


class BehaviorContractTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (ROOT / "skills" / name / "SKILL.md").read_text()

    def test_managed_skills_use_the_approved_implicit_invocation_allowlist(
        self,
    ) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        expected = {
            "agent-browser",
            "architecture-plan",
            "codebase-search-and-understanding-expert",
            "create-verification-skill",
            "debugging",
            "diff-review",
            "frame-change",
            "learning-workspace",
            "maintain-verification-skill",
            "map-change",
            "plan-parallel-build",
            "recent-commits-digest",
            "sgrep",
            "simplify-audit",
            "simplify-review",
            "verify-change",
        }
        observed: set[str] = set()

        for name, record in registry.items():
            if record["ownership"] != "custom":
                continue
            content = self.read(name)
            frontmatter = content.split("---", 2)[1]
            metadata = (
                ROOT / "skills" / name / "agents" / "openai.yaml"
            ).read_text()
            model_invocation_disabled = (
                "disable-model-invocation: true" in frontmatter
            )
            implicit_invocation_allowed = (
                "allow_implicit_invocation: false" not in metadata
            )

            with self.subTest(name=name):
                self.assertEqual(
                    model_invocation_disabled,
                    not implicit_invocation_allowed,
                )
            if implicit_invocation_allowed:
                observed.add(name)

        self.assertEqual(expected, observed)

    def test_tiny_change_is_explicitly_outside_four_skill_pipeline(self) -> None:
        for name in (
            "frame-change",
            "map-change",
            "implement-change",
            "verify-change",
        ):
            with self.subTest(name=name):
                self.assertRegex(self.read(name), r"(?i)do not use|skip")
                self.assertRegex(self.read(name), r"(?i)trivial|tiny|obvious")

    def test_intent_and_frame_change_own_distinct_decisions(self) -> None:
        intent = self.read("intent")
        frame = self.read("frame-change")
        self.assertIn("Do not plan, design, or implement", intent)
        self.assertRegex(frame, r"(?i)confirmed intent|settled outcome")
        self.assertRegex(frame, r"(?i)do not replace.*intent|unsettled")

    def test_intent_handles_directional_forks_without_expanding_by_default(
        self,
    ) -> None:
        intent = self.read("intent")
        self.assertRegex(intent, r"(?i)directional fork")
        self.assertRegex(
            intent,
            r"(?is)inextricably tied to the intent.*macro direction-setter",
        )
        self.assertRegex(
            intent,
            r"(?is)user-facing.*how humans will actually use.*UI designs",
        )
        self.assertRegex(
            intent,
            r"(?is)local, reversible, low-impact, and detailed implementation.*choices for later",
        )
        self.assertRegex(
            intent,
            r"(?is)deeper technical exploration or multi-round design.*option.*default",
        )
        self.assertIn("**High-level direction**", intent)
        self.assertIn("**Open hinges**", intent)

    def test_map_is_read_only_and_cites_repository_evidence(self) -> None:
        content = self.read("map-change")
        self.assertRegex(content, r"(?i)read-only")
        self.assertRegex(content, r"(?i)paths? and symbols?")
        self.assertRegex(content, r"(?i)do not modify")

    def test_implementation_is_one_slice_and_has_stop_conditions(self) -> None:
        content = self.read("implement-change")
        self.assertRegex(content, r"(?i)one.*slice")
        self.assertRegex(content, r"(?i)stop condition")
        self.assertRegex(content, r"(?i)do not.*commit|must not.*commit")

    def test_verify_is_independent_and_does_not_trust_builder_summary(self) -> None:
        content = self.read("verify-change")
        self.assertRegex(content, r"(?i)independent|fresh")
        self.assertRegex(content, r"(?i)builder.*summary|self.report")
        self.assertRegex(content, r"(?i)accept|revise|return to design|restart")

    def test_diff_review_consumes_evidence_without_treating_it_as_authority(self) -> None:
        content = self.read("diff-review")
        self.assertRegex(content, r"(?i)evidence\s+packet")
        self.assertRegex(content, r"(?i)independent")
        self.assertRegex(content, r"(?i)(?:not|never)\s+as\s+authority|do not trust")

    def test_evaluated_review_portfolio_is_canonical_and_legacy_routes_retired(
        self,
    ) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        accepted = {
            "diff-review": "sha256:a8d8e31f6bb1af642db81e91f345cd095c973a5b98c2b506264d8338fd8f4fd0",
            "simplify-review": "sha256:f3c67a9b2077a1c090e25756c34f65cbed677102675b370b919333af9134ca17",
            "simplify-audit": "sha256:6fd9c0b44f0cff22f5ef6a2277bfe32d93ef487bf0649c45a87553e5f9a04f9a",
            "ponytail": "sha256:52b66c9d774af3286cbf21b90ff510186c76fb2896089d9342dd671a4037af7f",
        }

        for name, accepted_hash in accepted.items():
            with self.subTest(name=name):
                record = registry[name]
                canonical = ROOT / "skills" / name
                self.assertEqual("custom", record["ownership"])
                self.assertEqual("experimental", record["lifecycle"])
                self.assertEqual(f"skills/{name}", record["source"])
                self.assertEqual(
                    [f"~/.agents/skills/{name}"], record["install_targets"]
                )
                self.assertEqual([], record["dependencies"])
                self.assertEqual("read-only", record["effect_ceiling"])
                self.assertEqual(accepted_hash, record["provenance"]["revision"])
                self.assertEqual(accepted_hash, content_hash(canonical))
                if name == "diff-review":
                    runtime_digest = subprocess.check_output(
                        [
                            sys.executable, "-B", "-c",
                            "from runtime.review_core import EXPECTED_DIFF_REVIEW; "
                            "print(EXPECTED_DIFF_REVIEW.digest)",
                        ],
                        cwd=ROOT.parent / "REVIEW-HOOK",
                        text=True,
                        timeout=10,
                    ).strip()
                    self.assertEqual(content_hash(canonical), runtime_digest)

        for name in ("diff-review", "simplify-review", "simplify-audit"):
            metadata = (ROOT / "skills" / name / "agents" / "openai.yaml").read_text()
            self.assertIn("allow_implicit_invocation: true", metadata)

        simplify_audit = self.read("simplify-audit")
        self.assertNotIn("disable-model-invocation", simplify_audit)

        ponytail = self.read("ponytail")
        ponytail_metadata = (
            ROOT / "skills" / "ponytail" / "agents" / "openai.yaml"
        ).read_text()
        self.assertIn("disable-model-invocation: true", ponytail)
        self.assertIn("allow_implicit_invocation: false", ponytail_metadata)

        retired_hashes = {
            "ponytail-review": "sha256:09c282244217b59913607585372c694cf0d2b429559c4183f54415eb43666e10",
            "ponytail-audit": "sha256:fa492b5f36d0d7687d35c282065b76ba26c6f0bbe662e06e415860075b7fa3ea",
        }
        for name, observed_hash in retired_hashes.items():
            with self.subTest(name=name):
                record = registry[name]
                self.assertEqual("legacy-unmanaged", record["ownership"])
                self.assertEqual("retired", record["lifecycle"])
                self.assertNotIn("source", record)
                self.assertEqual(
                    "quarantined-after-owner-approval",
                    record["provenance"]["disposition"],
                )
                self.assertNotIn("notes", record["provenance"])
                self.assertEqual(observed_hash, record["provenance"]["observed_hash"])
                self.assertFalse((ROOT / "skills" / name).exists())

    def test_simplify_audit_defaults_to_the_minimum_direct_path(self) -> None:
        content = self.read("simplify-audit")

        self.assertRegex(content, r"(?i)repository-owned\s+plan\s+or\s+design")
        self.assertRegex(content, r"(?is)smallest credible direct path.*baseline")
        self.assertRegex(
            content,
            r"(?is)lifecycle stage.*gate.*artifact.*handoff.*burden\s+of\s+proof",
        )
        self.assertRegex(
            content,
            r"(?is)validation.*rollback.*observability.*dogfooding",
        )
        self.assertRegex(content, r"(?is)experimental lane.*promotion stage")
        self.assertRegex(
            content,
            r"(?is)credible irreversible failure.*data-integrity.*mixed-version",
        )

    def test_batch_grill_asks_only_frontier_level_decisions(self) -> None:
        content = self.read("batch-grill")
        self.assertRegex(content, r"(?i)highest-leverage unresolved decision")
        self.assertRegex(content, r"(?is)child decision.*unresolved parent")
        self.assertIn("If the answer were A rather than B", content)
        self.assertRegex(content, r"(?i)do not edit files")

    def test_xgrok_is_explicit_only_and_has_a_native_grok_path(self) -> None:
        content = self.read("xgrok")
        metadata = (
            ROOT / "skills" / "xgrok" / "agents" / "openai.yaml"
        ).read_text()
        host_boundary = content.split("## Respect the host boundary", 1)[1].split(
            "## Choose the retrieval mode", 1
        )[0]

        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("allow_implicit_invocation: false", metadata)
        for marker in (
            "Grok Build",
            "`grok` CLI",
            "`/xgrok`",
            "`scripts/xgrok`",
            "`references/worker-protocol.md`",
            "native X",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, host_boundary)

    def test_debugging_requires_diagnosis_before_remedy(self) -> None:
        content = self.read("debugging")
        self.assertRegex(content, r"(?i)observed mechanism")
        self.assertRegex(content, r"(?i)falsifiable sentence")
        self.assertRegex(content, r"(?i)defect.*trigger|trigger.*defect")
        self.assertRegex(content, r"(?i)provenance")
        self.assertRegex(content, r"(?i)contradiction")
        self.assertRegex(content, r"(?i)do not implement|read-only")

    def test_greenfield_plans_spikes_without_executing_the_swarm(self) -> None:
        content = self.read("greenfield")
        self.assertRegex(content, r"(?i)planning mode")
        self.assertRegex(content, r"(?i)each work stream owns exactly one")
        self.assertRegex(content, r"(?is)dominate completion time.*additional agents")
        self.assertRegex(content, r"(?i)apply these tests recursively")
        self.assertRegex(content, r"(?is)no safe evidence seam.*critical-path")
        self.assertRegex(content, r"(?i)do not\s+manufacture parallelism")
        self.assertRegex(content, r"(?is)same wave only when.*unreturned verdict")
        self.assertRegex(content, r"(?is)do not\s+invent a universal duration")
        self.assertRegex(content, r"(?i)do not run the swarm")
        self.assertRegex(content, r"(?i)never production")

    def test_plan_parallel_build_uses_real_parallel_implementation_boundaries(
        self,
    ) -> None:
        content = self.read("plan-parallel-build")
        metadata = (
            ROOT / "skills" / "plan-parallel-build" / "agents" / "openai.yaml"
        ).read_text()
        record = json.loads((ROOT / "registry.json").read_text())["skills"][
            "plan-parallel-build"
        ]

        self.assertEqual("custom", record["ownership"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual("skills/plan-parallel-build", record["source"])
        self.assertEqual(
            ["~/.agents/skills/plan-parallel-build"], record["install_targets"]
        )
        self.assertEqual([], record["dependencies"])
        self.assertEqual("local-write", record["effect_ceiling"])
        self.assertEqual("parallel-build-planning", record["evaluation_profile"])
        self.assertNotIn("disable-model-invocation", content)
        self.assertNotIn("allow_implicit_invocation", metadata)
        self.assertIn("$plan-parallel-build", metadata)
        self.assertRegex(content, r"(?i)direct implementation")
        self.assertRegex(content, r"(?i)deliverable is one Markdown plan")
        self.assertRegex(content, r"(?i)do not assign point scores")
        self.assertRegex(content, r"(?is)split a long.*stable seam")
        self.assertRegex(content, r"(?i)manufacturing parallelism")
        self.assertRegex(content, r"(?is)No same-wave dependency.*TBD")
        self.assertRegex(content, r"(?i)extensive hardening")
        self.assertRegex(content, r"(?is)do not run.*workstreams")

    def test_herenow_deploy_is_explicit_and_bounded(self) -> None:
        content = self.read("herenow-deploy")
        metadata = (
            ROOT / "skills" / "herenow-deploy" / "agents" / "openai.yaml"
        ).read_text()
        record = json.loads((ROOT / "registry.json").read_text())["skills"][
            "herenow-deploy"
        ]

        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertEqual("external-write", record["effect_ceiling"])
        self.assertEqual(
            ["~/.agents/skills/herenow-deploy"], record["install_targets"]
        )
        self.assertIn("herenow publish", content)
        self.assertIn("--url", content)
        self.assertRegex(content, r"(?is)do not invoke\s+`herenow delete`")
        self.assertRegex(content, r"(?i)purpose-built directory")
        self.assertRegex(content, r"(?i)verify")

    def test_chats_is_explicit_user_only(self) -> None:
        content = self.read("chats")
        metadata = (
            ROOT / "skills" / "chats" / "agents" / "openai.yaml"
        ).read_text()

        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("Prefer the authenticated Chrome connector", content)
        self.assertIn(
            "Do not read Chrome's `Local State` on the connector route", content
        )

    def test_gpt_context_declares_its_helper_and_explicit_write_boundary(self) -> None:
        content = self.read("gpt-context")
        metadata = (
            ROOT / "skills" / "gpt-context" / "agents" / "openai.yaml"
        ).read_text()
        script = (
            ROOT
            / "skills"
            / "gpt-context"
            / "scripts"
            / "start_context_chat.py"
        ).read_text()
        record = json.loads((ROOT / "registry.json").read_text())["skills"][
            "gpt-context"
        ]

        self.assertEqual(["gpt"], record["dependencies"])
        self.assertEqual("external-write", record["effect_ceiling"])
        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("Don't respond, this is just for context.", content)
        self.assertIn("scripts/start_context_chat.py", content)
        self.assertTrue(script)
        self.assertRegex(content, r"(?is)inspect.*before retrying")

    def test_arxiv_x_list_feed_is_explicit_and_source_bounded(self) -> None:
        content = self.read("arxiv")
        reference = (
            ROOT
            / "skills"
            / "arxiv"
            / "references"
            / "x-list-paper-feeds.md"
        ).read_text()

        self.assertIn("references/x-list-paper-feeds.md", content)
        self.assertRegex(content, r"(?is)X list.*only when.*explicitly asks")
        self.assertIn("authenticated Chrome", reference)
        self.assertIn("`list:{LIST_ID}`", reference)
        self.assertRegex(reference, r"(?i)bounded.*backfill")
        self.assertRegex(reference, r"(?i)best-effort|not exhaustive")
        self.assertRegex(reference, r"(?is)deduplicate.*arXiv ID")
        self.assertIn("canonical arXiv metadata", reference)
        self.assertIn("[X] · [abstract] · [PDF]", reference)
        self.assertRegex(reference, r"(?is)do not\s+download.*unless")

    def test_recent_skills_are_normally_installable_custom_records(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        expected_effects = {
            "code-like-luke": "local-write",
            "teach": "local-write",
            "to-tickets": "external-write",
        }

        for name, effect_ceiling in expected_effects.items():
            with self.subTest(name=name):
                record = registry[name]
                content = self.read(name)
                metadata = (
                    ROOT / "skills" / name / "agents" / "openai.yaml"
                ).read_text()
                self.assertEqual("custom", record["ownership"])
                self.assertEqual("experimental", record["lifecycle"])
                self.assertEqual(f"skills/{name}", record["source"])
                self.assertEqual(
                    [f"~/.agents/skills/{name}"], record["install_targets"]
                )
                self.assertEqual([], record["dependencies"])
                self.assertEqual(effect_ceiling, record["effect_ceiling"])
                self.assertIn("disable-model-invocation: true", content)
                self.assertIn("allow_implicit_invocation: false", metadata)

    def test_backwards_is_managed_and_explicit_invocation_only(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        record = registry["backwards"]
        content = self.read("backwards")
        metadata = (
            ROOT / "skills" / "backwards" / "agents" / "openai.yaml"
        ).read_text()

        self.assertEqual("custom", record["ownership"])
        self.assertEqual("skills/backwards", record["source"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertRegex(content, r"(?i)only when explicitly invoked")

    def test_migrated_skills_are_managed_and_explicit_invocation_only(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        expected = {
            "grilling": ("read-only", []),
            "research": ("local-write", []),
            "synthesize-market-state": ("local-write", ["wsj", "xgrok"]),
            "tdd": ("local-write", []),
            "ubiquitous-language": ("local-write", []),
        }

        for name, (effect_ceiling, dependencies) in expected.items():
            with self.subTest(name=name):
                record = registry[name]
                content = self.read(name)
                metadata = (
                    ROOT / "skills" / name / "agents" / "openai.yaml"
                ).read_text()
                self.assertEqual("custom", record["ownership"])
                self.assertEqual("experimental", record["lifecycle"])
                self.assertEqual(f"skills/{name}", record["source"])
                self.assertEqual(
                    [f"~/.agents/skills/{name}"], record["install_targets"]
                )
                self.assertEqual(effect_ceiling, record["effect_ceiling"])
                self.assertEqual(dependencies, record["dependencies"])
                self.assertIn("disable-model-invocation: true", content)
                self.assertIn("allow_implicit_invocation: false", metadata)
                for stale_key in ("disposition", "exit_phase", "observed_hash"):
                    self.assertNotIn(stale_key, record["provenance"])

        research_root = ROOT / "skills" / "research"
        self.assertEqual(
            [research_root / "SKILL.md"],
            sorted(research_root.rglob("SKILL.md")),
        )
        self.assertNotIn("Spin up a **background agent**", self.read("research"))
        self.assertNotIn("code-review", self.read("tdd"))
        self.assertRegex(
            self.read("synthesize-market-state"),
            r"(?is)single-writer.*do not.*simultaneous",
        )

    def test_evidence_loop_variants_are_explicit_and_materially_distinct(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        expected_assets = {
            "evidence-driven-loop-minimal": {
                "references": set(),
                "scripts": set(),
            },
            "evidence-driven-loop-guided": {
                "references": {
                    "domain-patterns.md",
                    "evaluation-design.md",
                    "experiment-strategy.md",
                    "long-running-work.md",
                },
                "scripts": set(),
            },
            "evidence-driven-loop-instrumented": {
                "references": {
                    "campaign-protocol.md",
                    "capture-run.md",
                    "selection-and-confirmation.md",
                },
                "scripts": {"capture_run.py"},
            },
            "evidence-driven-loop-judged": {
                "references": {"comparative-judgment.md"},
                "scripts": set(),
            },
        }

        for name, assets in expected_assets.items():
            with self.subTest(name=name):
                root = ROOT / "skills" / name
                record = registry[name]
                content = (root / "SKILL.md").read_text()
                metadata = (root / "agents" / "openai.yaml").read_text()
                references = root / "references"
                scripts = root / "scripts"

                self.assertEqual("custom", record["ownership"])
                self.assertEqual("experimental", record["lifecycle"])
                self.assertEqual(f"skills/{name}", record["source"])
                self.assertEqual(
                    [f"~/.agents/skills/{name}"], record["install_targets"]
                )
                self.assertEqual(
                    ["orchestrate"] if name == "evidence-driven-loop-judged" else [],
                    record["dependencies"],
                )
                self.assertEqual("local-write", record["effect_ceiling"])
                self.assertIn("disable-model-invocation: true", content)
                self.assertIn("allow_implicit_invocation: false", metadata)
                self.assertEqual(
                    assets["references"],
                    {path.name for path in references.glob("*.md")}
                    if references.exists()
                    else set(),
                )
                self.assertEqual(
                    assets["scripts"],
                    {path.name for path in scripts.glob("*") if path.is_file()}
                    if scripts.exists()
                    else set(),
                )

        instrumented_tests = (
            ROOT / "skills" / "evidence-driven-loop-instrumented" / "tests"
        )
        self.assertTrue((instrumented_tests / "test_capture_run.py").is_file())

        judged_content = (
            ROOT / "skills" / "evidence-driven-loop-judged" / "SKILL.md"
        ).read_text()
        self.assertIn("use at least one fresh subagent", judged_content.lower())
        launch_owner = ROOT / registry["orchestrate"]["source"] / "SKILL.md"
        launch_content = launch_owner.read_text()
        launch_pairs = {
            role.strip(): (model, effort)
            for role, model, effort in re.findall(
                r"^\| ([^|]+) \| `([^`]+)` \| `([^`]+)` \|$",
                launch_content,
                flags=re.MULTILINE,
            )
        }
        self.assertEqual(
            {
                "Ordinary bounded worker": ("gpt-6-astra", "low"),
                "Explorer": ("gpt-5.6-sol", "medium"),
                "Independent reviewer (`commit-diff-risk-reviewer`)": (
                    "gpt-6-astra", "high"
                ),
                "Independent LLM judge deciding whether to accept an improvement": (
                    "gpt-6-astra", "high"
                ),
            },
            launch_pairs,
        )
        self.assertIn("human judge", judged_content.lower())

    def test_specialized_compact_visual_skills_are_retired_into_show_me(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        retired = {
            "show-code-structure",
            "show-code-flow",
            "show-code-change",
        }

        for name in retired:
            with self.subTest(name=name):
                record = registry[name]
                self.assertEqual("legacy-unmanaged", record["ownership"])
                self.assertEqual("retired", record["lifecycle"])
                self.assertNotIn("source", record)
                self.assertEqual(
                    [f"~/.agents/skills/{name}"], record["install_targets"]
                )
                self.assertEqual([], record["dependencies"])
                self.assertEqual("local-write", record["effect_ceiling"])
                self.assertEqual(
                    "retired-superseded-by-show-me",
                    record["evaluation_profile"],
                )
                self.assertEqual(
                    "quarantined-after-owner-approval",
                    record["provenance"]["disposition"],
                )
                self.assertFalse((ROOT / "skills" / name).exists())

    def test_show_me_and_show_me_clearly_coexist_as_custom_skills(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        show_me_record = registry["show-me"]
        self.assertEqual("custom", show_me_record["ownership"])
        self.assertEqual("experimental", show_me_record["lifecycle"])
        self.assertEqual("skills/show-me", show_me_record["source"])
        self.assertEqual(
            ["~/.agents/skills/show-me"], show_me_record["install_targets"]
        )
        self.assertEqual([], show_me_record["dependencies"])
        self.assertEqual("local-write", show_me_record["effect_ceiling"])
        show_me_source = ROOT / "skills" / "show-me"
        self.assertTrue((show_me_source / "SKILL.md").is_file())
        self.assertTrue((show_me_source / "agents" / "openai.yaml").is_file())
        self.assertIn("disable-model-invocation: true", self.read("show-me"))
        self.assertIn(
            "allow_implicit_invocation: false",
            (show_me_source / "agents" / "openai.yaml").read_text(),
        )

        source = ROOT / "skills" / "show-me-clearly"
        record = registry["show-me-clearly"]

        self.assertEqual("custom", record["ownership"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual("skills/show-me-clearly", record["source"])
        self.assertEqual(
            ["~/.agents/skills/show-me-clearly"], record["install_targets"]
        )
        self.assertEqual([], record["dependencies"])
        self.assertEqual("local-write", record["effect_ceiling"])
        self.assertEqual(
            "question-led-ascii-code-explanation",
            record["evaluation_profile"],
        )
        for path in (source / "SKILL.md", source / "agents" / "openai.yaml"):
            with self.subTest(path=path):
                self.assertTrue(path.is_file())
                self.assertTrue(path.read_text().strip())

    def test_html_explainers_are_consolidated_explicit_and_progressive(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        code = self.read("explain-code")
        code_metadata = (
            ROOT / "skills" / "explain-code" / "agents" / "openai.yaml"
        ).read_text()
        codebase_mode = (
            ROOT / "skills" / "explain-code" / "references" / "codebase.md"
        ).read_text()
        change_mode = (
            ROOT / "skills" / "explain-code" / "references" / "change.md"
        ).read_text()
        research = self.read("explain-research")
        research_metadata = (
            ROOT / "skills" / "explain-research" / "agents" / "openai.yaml"
        ).read_text()
        tutorial_track = (
            ROOT
            / "skills"
            / "explain-research"
            / "references"
            / "tutorial-track.md"
        ).read_text()

        for name, content, metadata in (
            ("explain-code", code, code_metadata),
            ("explain-research", research, research_metadata),
        ):
            with self.subTest(name=name):
                self.assertEqual("custom", registry[name]["ownership"])
                self.assertEqual("experimental", registry[name]["lifecycle"])
                self.assertEqual(f"skills/{name}", registry[name]["source"])
                self.assertEqual(
                    [f"~/.agents/skills/{name}"], registry[name]["install_targets"]
                )
                self.assertIn("disable-model-invocation: true", content)
                self.assertIn("allow_implicit_invocation: false", metadata)
                self.assertIn("Effects are optional", content)
                self.assertIn("WebGL2", content)
                self.assertIn("WebGPU", content)
                self.assertIn("prefers-reduced-motion", content)
                self.assertRegex(content, r"(?i)static .*fallback")

        self.assertIn("references/codebase.md", code)
        self.assertIn("references/change.md", code)
        self.assertIn("representative user or system action", codebase_mode)
        self.assertIn("present-day verdict", change_mode)
        self.assertIn("stop-here test", change_mode)
        self.assertIn("Never invent missing values", research)
        self.assertRegex(research, r"(?i)never draw.*quantitative chart")
        self.assertIn("references/tutorial-track.md", research)
        self.assertRegex(research, r"(?i)synthesis track")
        self.assertRegex(research, r"(?i)tutorial track")
        self.assertRegex(research_metadata, r"(?i)tutorial")
        self.assertRegex(tutorial_track, r"(?i)at least 36 distinct questions")
        self.assertRegex(
            tutorial_track,
            r"(?i)checkpoint after every major learning module",
        )
        self.assertRegex(tutorial_track, r"(?i)never defer all questions to the end")
        self.assertRegex(tutorial_track, r"(?i)do not lead with a literature overview")
        self.assertRegex(tutorial_track, r"(?i)new questions")
        self.assertRegex(
            tutorial_track,
            r"(?is)do not render.*entire question bank.*up front",
        )
        self.assertRegex(
            tutorial_track,
            r"(?is)do not repeat.*pool.*exhausted",
        )
        self.assertIn("aria-live", tutorial_track)

        for retired_name in ("explain-codebase", "explain-diff", "explain-progress"):
            with self.subTest(retired_name=retired_name):
                self.assertEqual("legacy-unmanaged", registry[retired_name]["ownership"])
                self.assertEqual("retired", registry[retired_name]["lifecycle"])

    def test_illustrate_cn_is_a_bounded_chinese_article_image_skill(self) -> None:
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        root = ROOT / "skills" / "illustrate-cn"
        content = self.read("illustrate-cn")
        metadata = (root / "agents" / "openai.yaml").read_text()
        record = registry["illustrate-cn"]
        examples = root / "assets" / "examples"

        self.assertEqual("custom", record["ownership"])
        self.assertEqual("experimental", record["lifecycle"])
        self.assertEqual("skills/illustrate-cn", record["source"])
        self.assertEqual(
            ["~/.agents/skills/illustrate-cn"],
            record["install_targets"],
        )
        self.assertEqual([], record["dependencies"])
        self.assertEqual("local-write", record["effect_ceiling"])
        self.assertEqual(
            "explicit-only-xiaohei-illustrate-cn",
            record["evaluation_profile"],
        )
        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("$illustrate-cn", metadata)
        self.assertIn("只在用户用名称或斜杠命令显式调用", content)
        self.assertTrue((root / "LICENSE").is_file())
        self.assertTrue((root / "NOTICE.md").is_file())
        self.assertEqual(
            {
                "composition-patterns.md",
                "prompt-template.md",
                "qa-checklist.md",
                "style-dna.md",
                "xiaohei-ip.md",
            },
            {path.name for path in (root / "references").glob("*.md")},
        )
        self.assertEqual(14, len(list(examples.glob("*.png"))))
        self.assertIn("小黑", content)
        self.assertIn("16:9", content)
        self.assertIn("`image_gen`", content)
        self.assertIn("`image_edit`", content)
        self.assertIn("imagegen", content)
        self.assertRegex(content, r"(?i)do not use for commercial")
        self.assertIn("不要复刻过往案例", content)
        self.assertIn("assets/<article-slug>-illustrations/", content)
        self.assertIn("这是中文原版", content)
        self.assertIn("$illustrate", content)

    def test_illustrate_text_files_exist_and_are_nonempty(self) -> None:
        root = ROOT / "skills" / "illustrate"
        text_files = (
            root / "SKILL.md",
            root / "NOTICE.md",
            root / "agents" / "openai.yaml",
            root / "references" / "composition-patterns.md",
            root / "references" / "prompt-template.md",
            root / "references" / "qa-checklist.md",
            root / "references" / "style-dna.md",
            root / "references" / "xiaohei-ip.md",
        )

        for path in text_files:
            with self.subTest(path=path):
                self.assertTrue(path.is_file())
                self.assertTrue(path.read_text().strip())


if __name__ == "__main__":
    unittest.main()
