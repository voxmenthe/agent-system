# Personal Coding Skills User Guide

This guide explains the owner-controlled personal skills as a software
development workflow. It is guidance, not a mandatory pipeline: ask for the
outcome normally, let the agent route only the approved implicit set, and name
any other skill explicitly when you want its particular workflow.

## Availability is binary

A personal skill is either:

- **Live (shared):** its directory exists under `~/.agents/skills`, the runtime can
  discover it, and it may be selected.
- **Retired:** it is absent from the live directory and cannot be selected.

`quarantine` is the maintenance command that implements a reversible
retirement. It moves the exact live directory into recovery storage and records
the move in a journal. The retained copy is a backup, not a third availability
state and not part of the skill library.

Restoring a backup is a separate, explicit reactivation decision. Permanent
deletion of old backups may happen later under a retention policy, but deleting
or retaining a backup does not change whether the skill is live.

Unapproved drafts under `evaluations/candidates/` are neither canonical nor
live.

Grok-only native-X skills are live through links in `~/.grok/skills`,
`~/.grok2/skills` and `~/.grok3/skills`; their [separate catalog](grok-skills/README.md) is not part
of the shared registry or shared quarantine lifecycle.

## Keep personal skills in the managed library

Author personal packages in this repository, not `~/.codex/skills`. When using
the system `skill-creator`, explicitly supply the repository candidate path;
its default output path is not our source-of-truth contract. Follow
[Adding or changing a custom skill](README.md#adding-or-changing-a-custom-skill)
for registration, validation, and one exact managed install.

From `AGENT-ENGINEERING/SKILL-SYSTEM`, use `bin/skill-system audit-codex` to
check for new unmanaged Codex-local declarations. It is read-only; it neither
adopts nor deletes them. Codex's `.system` skills and plugin skills remain
provider-owned, outside this personal-source requirement.

The former `codebase-url`/`codeurl` and `frontend-design` skills and a proposed
narrow PDF form analyzer are candidates only. `plans-context-loader` is archived:
read user-designated plans directly as part of the task, without a separate
bootstrap route. Use `diff-review` instead of `reviewing-commit-risk`, native
Git worktrees instead of the old manager, and available provider PDF tooling for
ordinary PDF work. Simplification reviews stay read-only; actual changes still
require an implementation request.

## Making shared skills visible to Antigravity CLI

After installing `agy`, configure its global discovery once:

```bash
bin/skill-system configure-antigravity
bin/skill-system configure-antigravity --apply
```

The first command is a dry run. The applied command creates only
`~/.gemini/config/skills.json`, pointing it at the existing shared projection.
Later skill installs and refreshes need no Antigravity-specific copy or sync.
An existing different configuration is preserved and reported as a collision.

## Making shared skills visible to Claude Code CLI

Claude Code discovers personal skills from `~/.claude/skills`. Project the
active shared skills and clean up stale/dangling symlinks:

```bash
bin/skill-system configure-claude
bin/skill-system configure-claude --apply
```

The first command is a dry run. The applied command creates symlinks under
`~/.claude/skills` pointing to active shared skills in `~/.agents/skills`, and
safely removes dangling or retired symlinks while preserving unmanaged
Claude-local skills with non-colliding names. A real directory at an active
shared skill's name is a collision, even when its content matches. Preserve
and reconcile that directory before replacing it with a symlink.
`configure-claude --force --apply` moves colliding directories to
`~/.agents/.skill-system/claude-backups/<id>/<name>` (reported as
`quarantine_path`) instead of deleting them; it is still not the shared
installer's journaled adoption path.

## Making shared skills visible to MiMo Desktop

MiMo Desktop discovers skills only from MiMoCode roots. The global write root
is `~/.config/mimocode/skills/<id>/SKILL.md`. Brand roots such as
`~/.agents/skills` and `~/.claude/skills` are not scanned. Project the active
shared skills into that layout:

```bash
bin/skill-system configure-mimo
bin/skill-system configure-mimo --apply
```

The first command is a dry run. The applied command copies each active shared
skill into `~/.config/mimocode/skills/<id>/` (real directories, not symlinks),
writes `locales/en-US.json` and `locales/zh-CN.json` from the skill's
`agents/openai.yaml` display metadata, and records a `.mimo-projection.json`
marker with the projected source hash. Unmanaged local MiMo skills with
non-colliding names are preserved. A real directory at an active shared
skill's name without the marker is a collision; preserve and reconcile it
first, or pass `--force` to move it to
`~/.agents/.skill-system/mimo-backups/<id>/<name>` (reported as
`quarantine_path`) before copying.
`sync --apply` reruns this projection after the shared install stage.

Restart MiMo Desktop or start a new conversation after applying so newly
copied skills are loaded.

## Managing Grok-only skills

Edit `grok-skills/<name>/` here. The six native-X research skills are linked
into both Grok homes, not copied into the shared catalog:

```bash
bin/skill-system validate
bin/skill-system configure-grok
bin/skill-system configure-grok --apply
```

Edits are immediately visible through both links. `status` includes a `grok`
map, and the normal `sync` command also sets up these links. For a reconciled
collision, `configure-grok --force --apply` retains the original exact entries
under the returned `quarantine_path` before linking; no account credentials
or settings are copied. Use this scoped command for Grok adoption, not broad
`sync --force`. Read the [Grok recovery instructions](grok-skills/README.md#collisions-and-recovery)
for partial failures and manual restoration; shared journal rollback does
not apply to these links.

## Keeping managed projections current

From `AGENT-ENGINEERING/SKILL-SYSTEM`, preview all eligible canonical updates:

```bash
bin/skill-system refresh
```

Inspect the JSON `operations` and `excluded` groups, then apply the previewed
class of updates explicitly:

```bash
bin/skill-system refresh --apply
```

Refresh updates only existing installer-managed skills whose canonical source
changed. It does not install absent skills, adopt unmanaged collisions,
overwrite local modifications, or touch retired, reference, legacy, or
external skills. Each updated skill keeps its own transaction and rollback
operation. If a refresh is interrupted, use `status`, recover any named
incomplete operation, and rerun the idempotent command.

## Syncing the full managed set

`sync` is the one command that reconciles every installable `custom` skill
against canonical sources in one pass. It installs `absent` skills and refreshes
`source-updated` ones, then runs the Claude symlink, MiMo Desktop copy, and
Grok-only link projections described above. It does not retire shared skills;
that stays a separate quarantine step.

```bash
bin/skill-system sync
bin/skill-system sync --apply
```

Shared `unmanaged-collision` and `locally-modified` skills are reported as exclusions
(warnings) and left untouched by default. To adopt them — letting canonical
content win while retaining the displaced live content as a rollback-able
preimage — add `--force`:

```bash
bin/skill-system sync --force
bin/skill-system sync --force --apply
```

Each shared install candidate has its own journal, preimage, operation ID, and
rollback path. Claude and MiMo projections are separate: without `--force`, a
colliding directory aborts that stage; with `--force`, it is deleted without a
preimage. Earlier shared installs may already have completed when a later host
projection fails. Grok collisions instead retain exact backups outside
discovery. The combined sync is not an all-or-nothing transaction.

Use `refresh --apply` for existing managed source updates without changing
Claude links or MiMo copies. To resolve a host collision, preserve and
reconcile the exact local directories, then run `configure-claude` or
`configure-mimo` (or `configure-grok` for native-X skills) and its reviewed
apply. Do not use broad `sync --force` merely to resolve a host link: it also
adopts all eligible shared collisions
and local modifications. If an install is interrupted, inspect `status` and
recover any named incomplete operation.

## How to use skills

### Ask normally first

Most of the time, describe the outcome and constraints:

> Add cursor pagination to the audit endpoint without changing the existing
> response shape for clients that omit the cursor.

The agent may automatically select only `agent-browser`, `architecture-plan`,
`codebase-search-and-understanding-expert`, `create-verification-skill`,
`debugging`, `diff-review`, `frame-change`, `learning-workspace`,
`maintain-verification-skill`, `map-change`, `plan-parallel-build`,
`recent-commits-digest`, `simplify-audit`,
`simplify-review`, and `verify-change`. The other managed
custom skills are explicit-only and must be named by the user. Automatic
selection does not expand authority: listing history does not authorize a
pull, and browser use does not authorize unrelated external writes.

Select `map-change` only for uncertain impact of an authorized existing-code
change, and `architecture-plan` only for an unsettled consequential boundary
decision. Reuse current maps and settled designs. Proactive `simplify-audit`
needs a concrete burden in the affected scope, not just a large task or an
architecture keyword. `simplify-review` and `plan-parallel-build` respond to
requests for those outcomes, even without a skill name; they are not automatic
follow-up stages. Name `bro` only when you want its particular writing style.

The verification owners have a moderately high bar: a material missing operating
capability, a materially affected existing recipe, or an important acceptance
question. Routine test commands and adequate existing evidence stay on the direct
path; the three skills are not a mandatory pipeline.

### Name a skill when you want its mode

Explicit selection is useful when the desired mode matters:

- “Use `intent` to help me clarify what outcome I actually want.”
- “Use `$batch-grill` to settle the highest-leverage decisions shaping this plan.”
- “Use `$backwards` to define this project from its imagined finished release and FAQ.”
- “Use `$grilling` to stress-test this decision with three questions at a time.”
- “Use `$research` to investigate this question from primary sources and save a cited Markdown report.”
- “Use `$learning-workspace` to keep this long task resumable from task-local evidence across context loss.”
- “Use `$tdd` to implement this fix one red-green-refactor slice at a time.”
- “Use `$ubiquitous-language` to extract and save the domain glossary from this conversation.”
- “Use `$synthesize-market-state` to produce the recurring market report and safely update the state ledger.”
- “Use `$greenfield` to plan parallel spike work streams that de-risk this new project.”
- “Use `$herenow-deploy` to deploy this exact static bundle to my HereNow account and verify it.”
- “Use `$wsj` to research current or historical WSJ coverage in my authenticated Chrome profile.”
- “Use `$bookmarks` to find my X folder from an approximate name, read all its content, and download linked data or analyze its themes.”
- “Use `$nyt` to survey New York Times coverage, or `$washp` to trace a topic in The Washington Post.”
- “Use `$gpt-context` to seed a new ChatGPT context conversation with these files.”
- “Use `$notebooklm` to turn this paper into a short Audio Overview with PhD-level hosts and save it to TEMP/.”
- “Use `$colab-jobs` to run this script on the cheapest Colab runtime and bring the outputs back.”
- “Use `$delegate` to divide this work among Antigravity, Kimi, Devin, Codex, and Grok in the requested proportions, then integrate and verify it.”
- “Use `$council` with dargh, ocsf and dswe on the panel and ccbx as judge to review this design.”
- “Use `$solutionize` with four caxb and two csbx attackers. Another team serves this query in under 5 ms on the same hardware; we are at 40 ms, and the API is fixed. No web search, and read only services/query/.”
- “`$be-ambitious`, then `$solutionize` with four cax and two ccx attackers: replaying a day of ES ticks through our backtester takes 9 minutes; another team replays a day in under a second on a laptop.”
- “`$council` with cax, ccx and dswe: each panelist reads ~/.agents/skills/be-ambitious/SKILL.md and applies it in prompt mode to "improve the morning market report". Judges rank the plans by how far each goes above and beyond while still delivering the report, with judges that can actually run.”
- “`$be-ambitious $learning-workspace`: sgrep finds the right file in its top five for 60 % of our code questions. Get it to where the best code-search systems are. Hunt with `$solutionize` (four cax, two ccx); when two designs tie on the check, have `$council` choose.” More combinations are in `be-ambitious`'s [examples](skills/be-ambitious/references/examples.md).
- “Use `$explain-code` in codebase mode to make a self-contained HTML onboarding guide.”
- “Use `$show-me-clearly` to explain this unfamiliar subsystem, pinned change, or settled phased plan through one question-led visual walkthrough.”
- “Use `$show-code` to explain this diff in codebase context: trace one input, explain the data contracts, and show why the important lines work.”
- “Use `$eli5` to break this topic down fast in plain language.”
- “Use `$illustrate-cn` to design or generate Xiaohei-style Chinese article illustrations.”
- “Use `$illustrate` for the English Xiaohei illustration workflow.”
- “Use `$scientific-figure-making` to build a publication-ready matplotlib figure with house style and vector export.”
- “Use `$explain-research` in tutorial track to teach me this inspected paper corpus with interspersed rotating quizzes.”
- “Use `map-change`; inspect only and show me the real change surface.”
- “Use `debugging`; diagnose this without implementing a fix.”
- “Use `verify-change` to independently check the implementation.”
- “Commit these exact files and push the branch.”

Naming a skill selects a workflow. It does not grant permissions beyond the
request. In particular, planning does not authorize implementation, and
implementation does not authorize committing, pushing, deploying, deleting
data, or changing external systems.

### Skip ceremony for tiny work

An obvious typo, isolated configuration correction, or local code edit with a
direct verifier should use the repository's normal read-edit-check loop. Do not
force the full workflow onto a tiny change.

## The development workflow

Policy-pack routing is the background guardrail for moderate or complex work;
it lives in the always-on kernel (`### Route instruction packs` and the
generated routing table), not in a selectable skill. The
allowlisted skills may enter when their decision or evidence is
needed. Every remaining managed skill enters only through explicit user
invocation.

| Stage | Question | Route |
| --- | --- | --- |
| Clarify | Is the desired future still materially ambiguous? | [`intent`](skills/intent/SKILL.md) |
| Raise | Did the user explicitly invoke `$be-ambitious` to have a task or prompt done above and beyond, with outside judges? | [`be-ambitious`](skills/be-ambitious/SKILL.md), explicit only |
| Interview | Do several independent, high-leverage plan decisions need to be settled breadth-first? | [`batch-grill`](skills/batch-grill/SKILL.md), explicit only |
| De-risk greenfield | Does a new project need several load-bearing capabilities tested before architecture, scope, or estimates are committed? | [`greenfield`](skills/greenfield/SKILL.md), explicit only |
| Contract | Is this a nontrivial, sufficiently understood change? | [`frame-change`](skills/frame-change/SKILL.md) |
| Continuity | Must this long task survive context compaction or restart without costly rework? | [`learning-workspace`](skills/learning-workspace/SKILL.md); the task's domain workflow remains authoritative |
| Map | Is the impact of this authorized brownfield change still uncertain? | [`map-change`](skills/map-change/SKILL.md), reusing current evidence |
| Investigate | Is there a runtime symptom or hard bug whose cause is unknown? | [`debugging`](skills/debugging/SKILL.md) |
| Design | Does a consequential boundary or ownership decision remain unsettled? | [`architecture-plan`](skills/architecture-plan/SKILL.md), skipping established patterns and settled designs |
| De-risk data | Does it alter persisted data, schemas, events, or compatibility? | `data-safety` policy pack |
| Probe | Would throwaway code answer one unsettled design question cheaply? | Direct bounded implementation under current repository policy; no selectable skill |
| Build | Is one bounded vertical slice settled and authorized? | [`implement-change`](skills/implement-change/SKILL.md), explicit only |
| Delegate | Did the user explicitly request a coordinated wave of external model workers? | [`delegate`](skills/delegate/SKILL.md), explicit only |
| Council | Did the user explicitly ask several external models to attempt the same task, judged blind? | [`council`](skills/council/SKILL.md), explicit only |
| Solutionize | Did the user explicitly invoke `$solutionize` to hunt for a solution known to exist? | [`solutionize`](skills/solutionize/SKILL.md), explicit only |
| Document | Does durable user or maintainer guidance need to change? | Repository documentation policy and normal editing workflow |
| Explain code | Did the user explicitly request a durable HTML guide to a codebase or change? | [`explain-code`](skills/explain-code/SKILL.md), explicit only |
| Explain clearly | Does an early-career engineer need a saved, question-led walkthrough of unfamiliar code, a pinned change, or a settled technical plan? | [`show-me-clearly`](skills/show-me-clearly/SKILL.md), explicit only |
| Explain code in context | Does the reader need the important source lines connected to callers, a concrete runtime trace, data contracts, and consumers? | [`show-code`](skills/show-code/SKILL.md), explicit only |
| Explain simply | Did the user explicitly invoke `/eli5` or `$eli5` for a quick plain-language breakdown of an unfamiliar topic? | [`eli5`](skills/eli5/SKILL.md), explicit only |
| Explain research | Did the user explicitly request a durable HTML synthesis or deep tutorial of an inspected document corpus? | [`explain-research`](skills/explain-research/SKILL.md), explicit only |
| Verify | Does the result satisfy the accepted outcome and invariants? | [`verify-change`](skills/verify-change/SKILL.md), reusing sufficient current evidence |
| Review | Does the patch contain defects, regressions, unsafe scope, or missing tests? | [`diff-review`](skills/diff-review/SKILL.md) |
| Simplify one change | Did the user explicitly ask what retained complexity can be removed from one concrete diff? | [`simplify-review`](skills/simplify-review/SKILL.md) |
| Simplify a repository or plan | Was an audit requested, or does concrete machinery burden the affected feature/plan? | [`simplify-audit`](skills/simplify-audit/SKILL.md), staying inside the declared scope |
| Build minimally | Did the user explicitly request the smallest complete implementation or design for a bounded task? | [`ponytail`](skills/ponytail/SKILL.md), explicit only |
| Publish Git | Did the user explicitly request a commit, push, rebase, or pull request? | Direct Git under the explicit request; no skill route |
| Deploy | Did the user explicitly invoke the HereNow deployment workflow and identify the artifact? | [`herenow-deploy`](skills/herenow-deploy/SKILL.md), explicit only |

This is a decision flow rather than a checklist. A task may enter in the
middle, skip most stages, or stop after diagnosis or planning.

The common paths below show decision order, not automatic skill chaining.
Steps outside the approved implicit allowlist still require the user to name
the skill.

### Common paths

**Feature delivery with Poteto (Codex-first, experimental)**

[`poteto`](skills/poteto/SKILL.md) coordinates assessment, one implementation
writer, fresh non-author review/acceptance, and the authorized PR edge.
[POTETO-USAGE.md](POTETO-USAGE.md) provides the initial explicit-skill request,
bounded objective and resume prompts, explanation settings, and practical
guidance on outcomes and authority. No per-stage forwarding is required for
the supported composition path; no automatic merge/deploy or unattended
restart is implied.

The same guide covers independent use of
[`create-verification-skill`](skills/create-verification-skill/SKILL.md) to
establish a missing affected-surface recipe, or
[`maintain-verification-skill`](skills/maintain-verification-skill/SKILL.md) to
correct and re-drive an existing one. Neither leaf accepts the product or
publishes. Adequate existing instructions are reused; product regressions go
back to implementation. Both leaves may be selected implicitly for their
material-gap triggers and own necessary bounded verification glue without
requiring an additional `implement-change` invocation.

**Small local edit**

```text
inspect -> edit -> focused check
```

**Normal nontrivial change to existing code**

```text
frame-change -> map-change -> implement-change -> verify-change
```

Add `architecture-plan` only when a consequential boundary decision remains
unsettled. Reuse an established design and skip `map-change` when impact is
already understood. These paths show applicable roles, not mandatory stages;
adequate current contracts and evidence are reused. Persistent-data and
compatibility work routes through the mandatory `data-safety` policy pack.
Use `diff-review` before handoff when a separate defect hunt is valuable.

**Long task that must survive context loss**

```text
task-owning workflow -> learning-workspace continuity layer
-> resume from verified task-local evidence
```

`learning-workspace` is an overlay, not a replacement for
teaching, debugging, experiment/optimization, implementation, or cross-task
memory. Use it only with a safe user-authorized local write boundary.

**New project with several load-bearing unknowns**

```text
greenfield -> hand the spike package to an authorized orchestrator
-> aggregate worker verdicts -> revise the project plan
```

`greenfield` owns the planning package. It does not run the worker swarm,
promote spike code into production, or replace the final architecture decision.

**Unknown bug or production symptom**

```text
debugging -> falsifiable mechanism -> frame the confirmed repair
-> implement-change -> verify-change
```

Diagnosis may stop without a fix when that is all the user requested.

**Cross-module or public-interface change**

```text
intent, if requested -> frame-change -> map-change, if impact is uncertain
-> architecture-plan, if a consequential decision remains
-> implement one slice -> verify-change -> diff-review
```

**Persistent-data or compatibility change**

```text
frame-change -> map-change -> data-safety policy pack
-> architecture-plan, if a consequential decision remains -> implement-change
-> verify-change
```

Treat irreversible steps as separate authorization boundaries.

**Documentation-only change**

```text
documentation policy -> edit -> link/content/render checks
```

**Git publication**

```text
verified existing changes -> explicit user publication request -> direct Git
```

Publication is never an automatic final stage.

**HereNow deployment**

```text
exact static artifact -> explicit $herenow-deploy request -> bundle audit
-> publish or exact-target update -> remote and access verification
```

HereNow deployment is an external write. Invocation authorizes only the named
create or update; deletion remains a separate request.

## Core workflow reference

| Skill | Use it when | Do not use it when |
| --- | --- | --- |
| [`intent`](skills/intent/SKILL.md) | You explicitly want to uncover the underlying outcome, priorities, or unacceptable version of success before requirements or design. | The outcome is already clear, or you are ready for specification or implementation. |
| [`batch-grill`](skills/batch-grill/SKILL.md) | You explicitly want a breadth-first interview over the highest-leverage unresolved decisions shaping a consequential plan. | Ordinary discussion, one local clarification, or a fact the agent can inspect is sufficient. |
| [`greenfield`](skills/greenfield/SKILL.md) | A new or in-flight project has several load-bearing capabilities that need self-contained, parallel spike briefs and an aggregation contract. | You need one probe inside an existing codebase, want the swarm executed, or are ready for production implementation. |
| [`frame-change`](skills/frame-change/SKILL.md) | A nontrivial change needs a compact contract: outcome, evidence, boundaries, risk, authority, stop conditions, and recovery. | Intent is unsettled, the edit is tiny, or you need implementation design. |
| [`map-change`](skills/map-change/SKILL.md) | The impact of an authorized existing-code change remains uncertain. | The boundary is already mapped, clearly local, greenfield, or the request only asks how code works. |
| [`architecture-plan`](skills/architecture-plan/SKILL.md) | An unresolved module, API, ownership, or integration decision affects correctness or future change cost. | Established patterns settle the design, the decision is already made, or the fix is local. |
| [`debugging`](skills/debugging/SKILL.md) | A hard bug, runtime failure, or regression needs evidence-first diagnosis: a tight repro loop, provenance, ranked hypotheses, and a falsifiable causal mechanism. | The cause and deterministic repair are already established. |
| [`implement-change`](skills/implement-change/SKILL.md) | One settled, bounded, authorized vertical slice is ready to build and check. | The outcome or interface is unsettled, or the task is review or publication. |
| [`create-verification-skill`](skills/create-verification-skill/SKILL.md) | Nontrivial or high-impact work has a material launch, drive, observation, or proof gap that existing tooling cannot cover. | A normal test command, small probe, or adequate recipe suffices. |
| [`maintain-verification-skill`](skills/maintain-verification-skill/SKILL.md) | An existing recipe's commands, fixtures, interactions, or evidence materially change or demonstrably drift. | The recipe is unaffected, missing, or the failure needs a product fix. |
| [`verify-change`](skills/verify-change/SKILL.md) | A nontrivial or high-impact result needs structured acceptance across important behavior or uncertain evidence. | A tiny low-impact edit has a decisive direct check, or the request merely runs a known test. |
| [`diff-review`](skills/diff-review/SKILL.md) | A working-tree, commit, or pull-request diff needs a defect-focused review. | You only want a summary or still need the patch implemented. |
| [`simplify-review`](skills/simplify-review/SKILL.md) | You explicitly want evidence-backed subtraction advice for one frozen diff. | A general review merely mentions accidental complexity, or the scope is a whole repository. |
| [`simplify-audit`](skills/simplify-audit/SKILL.md) | An audit is requested, or concrete duplicated policy, unjustified stages, or similar burden appears in the affected scope. | A keyword or task size is the only signal, or you need a normal changed-code review or automatic deletion. |
| [`ponytail`](skills/ponytail/SKILL.md) | You explicitly want the smallest complete implementation or design for one bounded task. | You need review, audit, acceptance verification, or Review Scan interpretation. |

Persistent formats, schemas, backfills, events, transactions, and
compatibility removals are governed by the `data-safety` policy pack rather
than a selectable skill.

`verify-change` and `diff-review` are complementary. Verification asks whether
the accepted outcome is proven. Diff review asks what may be wrong with the
patch. Use both when those are meaningfully different questions; reuse
applicable review results instead of repeating the defect hunt. Verification
labels self-checks separately from non-author independent verification, and
does not rerun sufficient current checks simply to assemble another packet.
An explicit independence requirement still needs a non-author reviewer.

## Supporting capabilities

These names include the supporting capabilities from the historical
Release 1 working set, the restored `wsj` capability, the ChatGPT transcript
exporter, two explicit-only HTML explainers, one question-led code explainer,
the explicit-only HereNow deployment workflow, and the paired Ian Xiaohei
illustration skills (Chinese original and English translation), and the
explicit-only publication-figure skill for matplotlib data plots; later per-name
assessment may move them on demand or retire them.

| Skill | Use it for | Important boundary |
| --- | --- | --- |
| [`backwards`](skills/backwards/SKILL.md) | An explicitly requested working-backwards interview and living release narrative, specification, and FAQ. | Explicit-only. It does not activate for ordinary planning, design, research, or implementation requests. |
| [`grilling`](skills/grilling/SKILL.md) | An explicitly requested depth-first stress test of one plan, decision, or idea. | Explicit-only; three questions at a time by default unless otherwise specified. It does not authorize acting on the result. |
| [`arxiv`](skills/arxiv/SKILL.md) | Paper discovery, precise arXiv lookup, full-text evidence, citation graphs, BibTeX, or a paper library. | Explicit-only. arXiv is not complete coverage for every research domain; distinguish discovery from evidence. |
| [`research`](skills/research/SKILL.md) | A primary-source investigation captured as a cited Markdown note in the repository. | Explicit-only. It does not itself authorize product or code changes or mandatory delegation. |
| [`learning-workspace`](skills/learning-workspace/SKILL.md) | Task-local evidence, claims, warnings, procedures, and resume state for a long task across compaction or restart. | Agent-invocable when the user asks for continuity or losing the task's evidence and frontier would force costly rework; long duration alone is not a trigger. Requires a safe local write boundary. The domain workflow retains ownership; this is not teaching, ordinary debugging or optimization, or general memory. |
| [`synthesize-market-state`](skills/synthesize-market-state/SKILL.md) | A recurring participant-native macro/equity synthesis plus a serialized durable market-state update. | Explicit-only. The report is append-only and the current-state edit is single-writer work. |
| [`tdd`](skills/tdd/SKILL.md) | A specifically requested test-first implementation loop over agreed public seams. | Explicit-only. Ordinary implementation or testing does not activate it automatically. |
| [`ubiquitous-language`](skills/ubiquitous-language/SKILL.md) | A canonical domain glossary and ambiguity ledger saved from the current conversation. | Explicit-only. It writes `UBIQUITOUS_LANGUAGE.md` and does not activate from ordinary DDD discussion. |
| [`xgrok`](skills/xgrok/SKILL.md) | X-native posts, threads, replies, practitioner conversations, and targeted receipts unavailable through normal web tools. | X establishes what participants said, not whether their factual claims are true. |
| [`bookmarks`](skills/bookmarks/SKILL.md) | Resolve an approximate X bookmark-folder name, read the entire visible folder, then download linked papers/data or analyze its content. | Explicit-only, read-only on X with authorized local writes. Post dates are not save dates; retain provenance, completeness limits, and existing files. |
| [`wsj`](skills/wsj/SKILL.md) | Current and historical Wall Street Journal research through the owner's authenticated Chrome profile. | Explicit-only and read-only: never handle credentials, inspect cookies, bypass access controls, or treat snippets as sufficient support for nuanced claims. |
| [`nyt`](skills/nyt/SKILL.md) | Current and historical New York Times research at nytimes.com (including nyt.com requests). | Explicit-only; Chrome plugin first, AppleScript fallback when unavailable. Report access and completeness limits. |
| [`washp`](skills/washp/SKILL.md) | Current and historical Washington Post research at washingtonpost.com. | Explicit-only; same browser transport boundary. Search/AI links are discovery evidence; open the reporting. |
| [`explain-code`](skills/explain-code/SKILL.md) | A self-contained HTML onboarding guide, architecture map, runtime trace, or before/after explanation of a code change. | Explicit-only and explanatory, not implementation or review. Modern CSS, shaders, WebGL, or WebGPU are optional progressive enhancements only when they improve understanding; the semantic static explanation must stand on its own. |
| [`show-me-clearly`](skills/show-me-clearly/SKILL.md) | A saved, question-led walkthrough of unfamiliar code, a pinned change, or a settled technical plan for an early-career engineer. | Explicit-only. The Markdown route uses one stable reading spine, color-assisted bounded ASCII orientation, local zooms, and inline source receipts; Mermaid is opt-in. |
| [`show-code`](skills/show-code/SKILL.md) | A code-focused explanation of a diff or mechanism in its existing caller/data/consumer context. | Explicit-only. Combines guided code, a concrete trace, meaningful data contracts, and review questions in one Markdown walkthrough; a bundled Pandoc renderer adds self-contained HTML. Explains code rather than implementing it or issuing a full review verdict. |
| [`explain-research`](skills/explain-research/SKILL.md) | A self-contained HTML evidence synthesis or deep tutorial of papers, reports, specifications, or another document corpus. | Explicit-only. Tutorial checkpoints use a substantial rotating question bank: 70% medium / 30% advanced understanding questions with click-to-reveal explanations, no answer choices or text entry; all claims and visuals remain evidence-bound with a readable static fallback. |
| [`bro`](skills/bro/SKILL.md) | A restatement of the preceding response in the selected bro writing style. | Explicit-only; ordinary requests for a clearer explanation do not select this style. |
| [`fanout`](skills/fanout/SKILL.md) | Parallel divergent ideation: isolated branches under different cognitive frames for open-ended design and naming decisions. | Explicit-only. Fixed multi-agent cost; skip for syntax, lookups, and bugs with a known root cause. |
| [`gpt`](skills/gpt/SKILL.md) | A ChatGPT Pro second opinion through the owner's logged-in Chrome on difficult design, reasoning, or multi-file review work. | Explicit-only; Pro runs take 5-30 minutes. Never for questions answerable with local tools. |
| [`notebooklm`](skills/notebooklm/SKILL.md) | Gemini Notebook (NotebookLM) notebooks from papers, files, or URLs, and Audio Overviews with a chosen format, length, language, and host instructions, downloaded as `.m4a`, through the owner's signed-in Chrome. | Explicit-only external write. Each episode spends up to about 10 % of the daily AI Usage allowance, so generate only what was asked; it never signs in, reads tokens, or deletes. |
| [`colab-jobs`](skills/colab-jobs/SKILL.md) | A Colab runtime on the owner's signed-in personal Google account: create it (CPU by default, the cheapest), copy files, install packages, run scripts or small fine-tuning jobs, bring results back, and release it, through one helper over the official `colab` CLI. | Explicit-only external write that spends compute units. Each session gets a lease that stops it if the agent forgets; it never signs in, reads tokens, mounts Drive, or switches hardware on its own. |
| [`gpt-context`](skills/gpt-context/SKILL.md) | Seed one new ChatGPT conversation in Chat mode, never Work, with 1-10 ordered context files, a fixed no-response prompt, and a title taken from the first filename. | Explicit-only external write. It verifies Chat before upload and each send attempt, leaves the Chat model/effort unchanged, and checks attachments, prompt, and title; it never continues a thread or waits for an answer. |
| [`delegate`](skills/delegate/SKILL.md) | Route bounded tasks across user-selected Antigravity, Kimi Code, Devin, Codex, and Grok workers, then integrate their results. | Explicit-only. Sol launchers use GPT-6.1 Sol; see the skill routing table for the default allocation. Parallel writers still require disjoint ownership. |
| [`council`](skills/council/SKILL.md) | Several independent external-model attempts at one task, ranked by blind external judges, then merged and verified by the parent. | Use only when the user explicitly invokes `$council` to have several independent external models attempt the same task, judged blind before the parent merges them. Do not use to split different work across workers (`delegate`), generate divergent ideas (`fanout`), argue two sides of a tension (`dialectic`), or coordinate native subagents (`orchestrate`). Defaults: panel `cax`, `cdm`, `ccx`, `dswe`, `ommp`; judge `camb` (`ccbm` for a Codex/OpenAI parent); no time limit unless the user names a budget. |
| [`solutionize`](skills/solutionize/SKILL.md) | A hunt for a solution someone has already found but not published: waves of independent experiments, foundations first, with nothing called solved until a clean rerun of the agreed check confirms it. | Use when the user invokes `$solutionize` to hunt for a solution someone has already found but not published. Defaults: no web search; agents read the repository in their worktree, their own directory, and the project's tools and libraries; the host's own subagents when none are named; no time limit unless the user names a budget. |
| [`be-ambitious`](skills/be-ambitious/SKILL.md) | A task or prompt done above and beyond what was asked: the intent inferred from the evidence, the request delivered the way the field's best would with an outside judge, a same-session side project brought back only if its judge passes, and a bigger version planned whole and suggested with a launch prompt. | Use when the user invokes `$be-ambitious` to raise the aim of a task or prompt. The request is always delivered; the bigger version is built only when a multi-session skill (`learning-workspace`, `solutionize` or an evidence loop) is also named. It asks before spending, launching agents nobody named, or irreversible steps. |
| [`catchup`](skills/catchup/SKILL.md) | On return to a long session: what changed since your last message, what needs your decision, and what is still running, read from live sources. | Explicit-only and read-only. It reports and asks; it never acts, relaunches, or decides before you reply. |
| [`skiller`](skills/skiller/SKILL.md) | Which installed skills a task or plan should use, and at which step, chosen from a live catalog of every skill's brief description. | Explicit-only and read-only. It recommends; it never invokes a skill. Useful during `$intent`, `$grilling`, `$batch-grill`, or plan writing. |
| [`create-formal-verification-skill`](skills/create-formal-verification-skill/SKILL.md) | A TLA+ model of the code where a bug costs most and tests reach least, every property shown failing on a broken variant, and a project-local verify skill with a one-command check that reports when the covered code changes. | Explicit-only. Findings stay findings: it reports and replays bugs and offers fixes but does not change product code unless asked. |
| [`orchestrate`](skills/orchestrate/SKILL.md) | Coordinate independent work through the host's native agent tools. | Explicit-only. One writer per file; the parent integrates and verifies. Does not launch external CLI workers. |
| [`dialectic`](skills/dialectic/SKILL.md) | Examine a real tension through two independent committed arguments and parent-led evidence checking and synthesis. | Explicit-only. No forced novelty, fixed multi-round budget, or manufactured balance between unequal evidence. |
| [`agent-browser`](skills/agent-browser/SKILL.md) | Browser interaction through the installed agent-browser CLI. | Agent-invocable when a browser is needed. Use task-owned sessions and version-matched help; external effects remain bounded by the request. |
| [`codebase-search-and-understanding-expert`](skills/codebase-search-and-understanding-expert/SKILL.md) | Questions about existing code: how it works and where, traced through complete units, callers and dependencies; why it is that way and whether planned work shipped, traced through commits, plans and `hist`. | Agent-invocable, read-only; `sgrep` or `rg` first; history only for why, where-from and status questions; `map-change` owns uncertain change impact. |
| [`prepare-context`](skills/prepare-context/SKILL.md) | Build a self-contained local reviewer bundle with source inventories, focused excerpts, and explicit evidence gaps. | Explicit-only. Four component roles, optional native parallel preparation with separate writers and parent assembly, and a relocatable resolver; no external transmission. |
| [`recent-commits-digest`](skills/recent-commits-digest/SKILL.md) | Summarize recent commits, optionally by path, and pull fast-forward-only when requested. | Agent-invocable for history requests. Use `--no-pull` unless pulling is authorized; divergence is an error, never an automatic merge or rebase. |
| [`web-research-then-plan`](skills/web-research-then-plan/SKILL.md) | Research primary sources and write a source-grounded plan in the requested plan family. | Explicit-only. Update an applicable existing index; missing indexes do not block a standalone plan or authorize building the project. |
| [`chats`](skills/chats/SKILL.md) | List recent or date-bounded private ChatGPT conversations and export a selected conversation through the owner's logged-in Chrome. | Explicit-only. Exports include every user-visible branch but not attachment binaries; listing is a best-effort read of the website's private index. Canonical source is prepared but not yet live. |
| [`herenow-deploy`](skills/herenow-deploy/SKILL.md) | Publish or update an exact static artifact bundle on the owner's configured HereNow account, then verify the manifest, URL, and restricted access state. | Explicit-only external write. It does not build the site, guess an update target, expose credentials, or authorize deletion. |
| [`illustrate-cn`](skills/illustrate-cn/SKILL.md) | Chinese original: shot lists and 16:9 white-background hand-drawn Chinese article illustrations using Xiaohei (小黑). | Explicit-only. Not code explanation, Mermaid, HTML, PPT infographics, or commercial illustration. Example images are style calibration, not composition templates. |
| [`illustrate`](skills/illustrate/SKILL.md) | English translation of the same Xiaohei workflow, for English-language use or English source articles. | Explicit-only. Same visual IP and anti-copy rules. Labels follow the article language. Do not use it as a second code-visual route beside `show-me-clearly`. |
| [`scientific-figure-making`](skills/scientific-figure-making/SKILL.md) | Publication-ready matplotlib figures for papers, slides, or reports: bars, trends, heatmaps, radar, concept schematics, and multi-panel layouts with house style and vector export. | Explicit-only. Matplotlib data plots with a publication target only; not interactive dashboards, exploratory plots, or Xiaohei and HTML illustration routes. |

## Choosing between easily confused skills

| If you need... | Choose |
| --- | --- |
| The user's real north star | `intent` |
| A task done above and beyond what was asked, with outside judges and verified suggestions | `$be-ambitious` |
| Several independent plan decisions at the current frontier | `$batch-grill` |
| One depth-first decision stress test, three-question rounds by default | `$grilling` |
| An imagined shipped outcome, release narrative, specification, and FAQ | `$backwards` |
| A parallel evidence campaign for a new project | `greenfield` |
| A bounded contract for a known change | `frame-change` |
| An explanation of how existing code works, or why it is built that way | `codebase-search-and-understanding-expert` |
| The uncertain impact of an authorized existing-code change | `map-change` |
| Resolution of an unsettled consequential boundary or interface decision | `architecture-plan` |
| The cause of an observed runtime problem | `debugging` |
| A safe persistent-data transition | `data-safety` policy pack |
| A primary-source Markdown research artifact | `$research` |
| Task-local continuity for a long task across compaction or restart | `learning-workspace` |
| A recurring participant-native market-state report and ledger update | `$synthesize-market-state` |
| A specifically requested red-green-refactor implementation loop | `$tdd` |
| A saved canonical domain glossary from the conversation | `$ubiquitous-language` |
| Production code for one settled slice | `implement-change` |
| Evidence that the result satisfies the contract | `verify-change` |
| A defect hunt against the patch | `diff-review` |
| Safe simplification advice for one exact diff | `$simplify-review` |
| A repository or plan/design simplification audit | `simplify-audit` |
| The smallest complete bounded implementation or design | `$ponytail` |
| A durable HTML guide to a codebase or code change | `$explain-code` |
| A clear walkthrough of unfamiliar code, a pinned before-and-after change, or a settled phased plan | `$show-me-clearly` |
| A diff explained through actual source, its callers, runtime values, data contracts, and consumers | `$show-code` |
| A fast plain-language breakdown of any unfamiliar topic after naming `/eli5` or `$eli5` | `$eli5` |
| The particular bro style for restating the preceding answer | `$bro`; ordinary clarification needs no style skill |
| Chinese article illustrations in the Xiaohei hand-drawn style | `$illustrate-cn` |
| The same Xiaohei workflow in English | `$illustrate` |
| Publication-ready matplotlib figures for papers, slides, or reports | `$scientific-figure-making` |
| A durable cited HTML synthesis or deep, quiz-interleaved tutorial of a document corpus | `$explain-research` |
| Durable prose in the repository | Normal editing under the documentation policy |
| A commit, push, rebase, or pull request | Direct Git under the user's explicit request |
| A list or complete local transcript of private ChatGPT conversations | `chats` |
| The full contents of a named X bookmark folder, downloaded resources, or a source-grounded analysis of that collection | `bookmarks` |
| A fresh ChatGPT conversation seeded only with uploaded context files | `gpt-context` |
| A NotebookLM Audio Overview of papers or other sources, saved as an audio file | `$notebooklm` |
| Code, installs, or a small training run on a Google Colab runtime, with the results brought back | `$colab-jobs` |
| A user-directed workforce of external coding models | `$delegate` |
| Several external models' independent attempts at one task, judged blind and merged | `$council` |
| A hard problem someone has already solved out of view, hunted by experiment and confirmed by rerunning the check | `$solutionize` |
| What changed in a long session since your last message, and what needs you | `$catchup` |
| Which skills a task or plan should use, and at which step | `$skiller` |
| A model-checked proof of a race, crash window, retry, or state machine, kept rechecked on later changes | `$create-formal-verification-skill` |
| A verified static-site publish or update on HereNow | `$herenow-deploy` |

When no row fits, proceed with the model's general capability rather than
installing or inventing a workflow skill by default.
