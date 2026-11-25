# Role packs and lanes

Ported from the council CLI's `ROLE_PACKS` and `ROLE_LIBRARY`
(`ztools/src/council/council_quality.py`, 2026-10-15). This file is now the
skill's own copy; the CLI is not consulted at run time.

## Using lanes

- Roles are off unless the invocation names a pack (`use the "code" roles`)
  or a member's lane (`dargh as skeptic`). A named member lane is used
  exactly. A lane may come from any pack, or from the extra lanes below.
- Candidates are the panelists plus the sealed parent; each gets one lane.
- When a pack has more lanes than candidates, choose the lanes that best fit
  this task, not the first N. When it has fewer, reuse the lanes that matter
  most for this task.
- At least one candidate must hold a complete-answer lane (kind `A`). Give
  the sealed parent one when you can.
- State each chosen lane and why in the bill, then proceed without asking.
- Record every candidate's lane in `lanes.tsv`:
  `LETTER<TAB>lane<TAB>complete-answer|contributing`.
- In the wave, `OBJECTIVE` moves out of `COMMON` into each worker block and
  carries the lane text (see [procedure](procedure.md#roles-on)).

Kinds: `A` = complete-answer (answers the whole task through its lens; may be
BASE). `C` = contributing (one lens: findings, checks, critique; supplies
DELTAS, never BASE).

## Packs

| Pack | Lanes |
| --- | --- |
| general | primary-worker, planner, alternate-worker, skeptic, evidence-worker, simplifier |
| code | architect, implementer, test-designer, regression-reviewer, interface-reviewer, perf-security-reviewer |
| code-rle | primary-worker, planner, alternate-worker, skeptic, evidence-worker, simplifier, architect, implementer, load-bearing-designer, data-modeler, blast-radius-mapper, complexity-budget-keeper, altitude-thinker, elegance-seeker, ideal-result-worker, readability-steward, reviewer-advocate |
| research | faithful-extractor, method-results-extractor, citation-skeptic, idea-generator, feasibility-reviewer |
| plan | strategist, implementation-slicer, risk-reviewer, evaluation-designer, simplifier |
| review | correctness-reviewer, regression-reviewer, test-coverage-reviewer, behavior-reviewer, severity-triager |
| idea | ideator, grounder, high-level-sanity-check, skeptic, simplifier |
| rl-env-design | research-grounder, task-ideator, grader-architect, variant-architect, reward-hack-redteam, pitch-reviewer, high-level-sanity-check, rl-training-manager |
| design-perspectives | grounder, high-level-sanity-check, ideator, primary-worker, planner, alternate-worker, skeptic, evidence-worker, simplifier, load-bearing-designer, data-modeler, blast-radius-mapper, complexity-budget-keeper, altitude-thinker, elegance-seeker, ideal-result-worker |

Council's `rl-env-design` pack names `high-level-sanity-check`, not the
`high-level-sanity-check-rl` lane; it is ported as is. An unknown pack name
stops the run before any call: list these packs and ask.

## Lanes

| Lane | Kind | Lane text |
| --- | --- | --- |
| primary-worker | A | Solve DIRECTLY and completely; optimize for a correct, concrete, shippable answer. |
| planner | A | Lead with DECOMPOSITION: break the problem into sub-parts and solve each; expose the structure. |
| alternate-worker | A | Take an ALTERNATIVE paradigm/approach from the obvious one; argue why it may be better. |
| skeptic | A | RED-TEAM: surface the assumptions, failure modes, and edge cases others miss; then solve. |
| evidence-worker | A | Check sources/tests/repo facts/citations/commands; ground every claim in inspected evidence. |
| simplifier | A | Find the SIMPLEST thing that fully works; minimize moving parts; justify every cut. |
| architect | A | Design the STRUCTURE first: modules, interfaces, data flow, the seams; implement against it. |
| implementer | A | Write the COMPLETE working implementation; handle the real edge cases and error paths, not a sketch. |
| load-bearing-designer | A | Design the LOAD BEARING components first: the key elements that make this codebase work, the critical paths, etc.; then design the rest around them. |
| test-designer | C | Lead with TESTS: enumerate happy/edge/failure cases and write runnable checks; make correctness observable. |
| regression-reviewer | C | Hunt REGRESSIONS: what existing behavior could this break? Preserve invariants; name what you verified. |
| interface-reviewer | C | Scrutinize the INTERFACES/APIs/signatures/naming/contracts for clarity and misuse-resistance. |
| perf-security-reviewer | C | Probe PERFORMANCE and SECURITY: complexity, hot paths, untrusted input, injection, resource limits. |
| data-modeler | A | Worry about DATA STRUCTURES, not code: pick the representation that makes the logic obvious and the special cases vanish; reshape the model before writing procedures. |
| blast-radius-mapper | C | Map the BLAST RADIUS: if this breaks, what stops working; if it changes, how far does the ripple spread? Guard the load-bearing and irreversible paths; treat true edges lightly. |
| complexity-budget-keeper | C | Guard the COMPLEXITY BUDGET: every interface/abstraction must pay for itself; reject speculative flags, shims, and hooks (YAGNI); generalize only when 3 concrete cases collapse into one. |
| altitude-thinker | C | Climb to ALTITUDE: drop the line-level details and ask what problem this really solves, whether the framing is right, and which single reframing or insight would make most of the work disappear. |
| elegance-seeker | A | Seek the ELEGANT shape, not merely the small one: orthogonal, composable building blocks and the one clean idea that makes the solution feel inevitable — true simplicity, never the naive kind that just defers the mess. |
| ideal-result-worker | A | Start from the IDEAL final result — what this would look like if the problem solved itself — then work backward to the minimum mechanism that reaches it; treat everything beyond that minimum as a cost to justify. |
| readability-steward | A | Write for the NEXT READER: names that document themselves, control flow obvious at a glance, intent legible in one pass; if a comment must explain WHAT the code does (not why), the code isn't clear enough yet. |
| reviewer-advocate | A | Optimize for the REVIEWER: the smallest diff that does the job, mechanical renames split from semantic edits, one idea per change, nothing surprising smuggled into a move — make the change easy to say yes to. |
| faithful-extractor | A | Extract FAITHFULLY what the source actually says; quote precisely; do not infer beyond the text. |
| method-results-extractor | A | Pull the METHOD and RESULTS exactly: setup, metrics, numbers, ablations, conditions; keep the figures. |
| citation-skeptic | C | Verify CITATIONS and claims against the evidence; flag unsupported, overstated, or mis-attributed assertions. |
| idea-generator | C | Generate NEW ideas/extensions/connections the source enables; be inventive but grounded. |
| feasibility-reviewer | C | Assess FEASIBILITY and limitations: what could fail, what is assumed, what would be hard to reproduce. |
| strategist | A | Set the STRATEGY: the objective, the order of operations, the highest-leverage path to done. |
| implementation-slicer | A | Slice into SHIPPABLE increments, each independently testable, with clear acceptance per slice. |
| risk-reviewer | C | Map the RISKS and mitigations: blast radius, failure modes, rollbacks, what could go wrong. |
| evaluation-designer | C | Design how success is MEASURED: metrics, checks, acceptance gates, what evidence proves done. |
| correctness-reviewer | A | Find CORRECTNESS bugs: logic errors, wrong assumptions, off-by-ones, mishandled states; prove each. |
| test-coverage-reviewer | C | Assess TEST COVERAGE: untested paths, missing edge cases, weak assertions; name the gaps. |
| behavior-reviewer | A | Check BEHAVIOR against intent: does it actually do what was asked, including the implicit requirements? |
| severity-triager | A | TRIAGE findings by severity and likelihood; separate must-fix from nits; recommend what to act on. |
| ideator | A | Brainstorm MANY distinct approaches and concepts. Prize ideas with simple and elegant approaches driven by deep insight into the problem. Be inventive but buildable and grounded. |
| grounder | A | GROUND every idea in the source and the goal: what do the source documents and code indicate, and what are the high-impact changes and implementation details. |
| high-level-sanity-check | A | Step back and see the forest not the trees. Do a high-level sanity check. What is the best high-level approach? What are the core insights that determine it? |
| research-grounder | C | GROUND every idea in the source and the research goal: what the paper/seed actually establishes, and the high-impact interp/alignment step a real agent would use this task for. |
| task-ideator | A | Brainstorm MANY distinct task concepts the source enables; prize ideas whose hard part differs across them; be inventive but buildable and gradable. |
| grader-architect | C | Design the GROUND TRUTH first: reference solution, do-it-ourselves, or easy-verify/hard-solve (P!=NP); a continuous score (1 pass, 0 fail, partial between) calibratable to ~10% frontier pass. |
| variant-architect | C | Maximize VARIETY without monoculture: harness natural data diversity so each variant forces different problem-solving steps; reject axes whose variants share one solution. |
| reward-hack-redteam | C | RED-TEAM the grader: name the shortcut that scores without doing the work (flat surface, topic-summary, lookup table, saturating recipe); then add the contrastive/sibling gate that kills it. |
| pitch-reviewer | C | Pressure-test as a skeptical PITCH reviewer: is the difficulty real (not just withheld weights), is it ONE unified task, buildable and gradable, with rollout evidence (score spread, signal fraction, strategy diversity) to earn a KEEP? |
| rl-training-manager | C | What would make this a valuable addition to our portfolio of RL environments used to train frontier models such as Claude Mythos and GPT 6? How should it be structured and designed to teach the agent something meaningful? |

### Extra lanes (in no pack; name them per member)

| Lane | Kind | Lane text |
| --- | --- | --- |
| special-case-eliminator | A | Eliminate SPECIAL CASES — first/last/empty/null branches, if/else ladders — by folding them into one unified path with dispatch tables, sentinels, and sane defaults. |
| deletionist | A | DELETE first: the best code is no code. Strip dead paths, middlemen, single-use helpers, and speculative surface until only what fully works is left standing. |
| friction-listener | A | Treat RESISTANCE as signal: where the code fights — awkward data flow, defensive 'just in case', reaching into other modules — name the architectural mismatch and redesign so it flows. |
| cost-honesty-reviewer | C | Expose HIDDEN COSTS and lying abstractions: no expensive work behind an innocent accessor; put the cost in the name (fetch_*/save_*); flag surprise I/O and hidden O(n^2). |
| brownfield-archaeologist | C | DON'T BREAK USERSPACE: first learn why the code exists, the invariants it holds, and who depends on it; preserve the contracts callers rely on before changing anything. |
| fail-loud-reviewer | C | FAIL LOUDLY: crash on unexpected state, refuse silent .get(default) for required fields, ban broad except; let a clean error point straight at the bug. |
| core-edge-separator | A | Separate pure CORE from effectful EDGE: keep core logic referentially transparent and blind to UI/DB/network; push side effects to adapters behind a narrow, stable waist. |
| least-power-advocate | A | Reach for the LEAST POWERFUL tool: data over code, config over branching, schema over hand-written validation; make the correct path easiest and destructive ops opt-in. |
| high-level-sanity-check-rl | C | Step back and see the forest not the trees: what are the core insights that could make this an interesting and viable RL environment task? |
| hardest-thing-first | A | Attack the HARDEST 2-3 parts first and sketch how the design absorbs each; if a hard part needs special-casing or boundary leaks, the architecture is wrong — find where it flows. |
