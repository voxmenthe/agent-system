---
name: debugging
description: Evidence-first diagnosis of hard bugs, production failures, flakes, and performance regressions. Use when behavior is broken, throwing, failing, or slow, or when asked to debug or find root cause; do not use when cause and deterministic edit are known.
---

# Debugging

One evidence-first workflow for hard bugs, production incidents, flaky behavior, and performance regressions. Skip phases only when explicitly justified.

Pick an authority mode before starting:

- **Diagnose and fix** — a local bug where the request authorizes repair, or it is implicitly expected as part of the plan: run the full loop through Phase 6.
- **Diagnose only** — a production incident, shared environment, or any case where the remedy is not authorized: stay read-only. Phases 0–4 confirm the mechanism; Phase 5 hands the repair off instead of applying it.

When exploring the codebase, read the relevant docs and plans for context, and the code to get a clear mental model of the relevant modules.

## Phase 0 — Pin down the symptom and its evidence

Before building anything:

- Re-read the actual current code, not your memory of it. State the observed symptom, impact, time window, affected scope, and which evidence is trustworthy.
- Label every artifact (log, trace, screenshot, user report) with its environment, version, configuration, time, and source path. Keep verified facts distinct from inferences; do not merge conclusions across provenance until the artifacts are known to describe the same execution path.
- Start from the most conclusive evidence. Enumerate comparable cases instead of generalizing from one instance.
- Treat contradictions as diagnostic signal. Ask why the behavior ever worked, or why the implicated path did not fire before; do not smooth conflicting observations into a convenient narrative.

## Phase 1 — Build a feedback loop

**This is the skill.** Everything else is mechanical. If you have a **tight** pass/fail signal for the bug — one that goes red on _this_ bug — you will find the cause; bisection, hypothesis-testing, and instrumentation all just consume it. If you don't have one, no amount of staring at code will save you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**

### Ways to construct one — try them in roughly this order

1. **Failing test** at whatever seam reaches the bug — unit, integration, e2e.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer) — drives the UI, asserts on DOM/console/network.
5. **Replay a captured trace.** Save a real network request / payload / event log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** Spin up a minimal subset of the system (one service, mocked deps) that exercises the bug code path with a single function call.
7. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
8. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at state X, check, repeat" so you can `git bisect run` it.
9. **Differential loop.** Run the same input through old-version vs new-version (or two configs) and diff outputs.
10. **HITL bash script.** Last resort. If a human must click, drive _them_ with `scripts/hitl-loop.template.sh` so the loop is still structured. Captured output feeds back to you.
11. **Anthing analogous to or inspired by the above 10 starter ideas.**

Build the right feedback loop, and the bug is 90% fixed.

### Tighten the loop

Treat the loop as a product. Once you have _a_ loop, **tighten** it:

- Can I make it faster? (Cache setup, skip unrelated init, narrow the test scope.)
- Can I make the signal sharper? (Assert on the specific symptom, not "didn't crash".)
- Can I make it more deterministic? (Pin time, seed RNG, isolate filesystem, freeze network.)

A 30-second flaky loop is barely better than no loop; a 2-second deterministic one is tight — a debugging superpower.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the trigger 100×, parallelise, add stress, narrow timing windows, inject sleeps. A 50%-flake bug is debuggable; 1% is not — keep raising the rate until it's debuggable.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a) access to whatever environment reproduces it, (b) a captured artifact (HAR file, log dump, core dump, screen recording with timestamps), or (c) permission to add temporary production instrumentation. Do **not** proceed to hypothesise without a loop.

### Completion criterion — a tight loop that goes red

Phase 1 is done when the loop is **tight** and **red-capable**: you can name **one command** — a script path, a test invocation, a curl — that you have **already run at least once** (paste the invocation and its output), and that is:

- [ ] **Red-capable** — it drives the actual bug code path and asserts the **user's exact symptom**, so it can go red on this bug and green once fixed. Not "runs without erroring" — it must be able to _catch this specific bug_.
- [ ] **Deterministic** — same verdict every run (flaky bugs: a pinned, high reproduction rate, per above).
- [ ] **Fast** — seconds, not minutes.
- [ ] **Agent-runnable** — you can run it unattended; a human in the loop only via `scripts/hitl-loop.template.sh`.

If you catch yourself reading code to build a theory before this command exists, **stop — jumping straight to a hypothesis is the exact failure this skill prevents.** No red-capable command, no Phase 2.

**Redact secrets everywhere you show or send them.** Replace every secret (API key, token, password, cookie, credentialed URL) with `<REDACTED>` in the commands, output and artifacts you paste, and in any packet you send to a delegate or external model; storage-side redaction comes too late for what a model or delegate has already seen. Build the loop to read secrets from environment variables, never inline. If redaction would hide the signal (the bug is in the secret's format), say so and describe the property that matters, such as its length, prefix or encoding, instead of the value.

## Phase 2 — Reproduce + minimise

Run the loop. Watch it go red — the bug appears.

Confirm:

- [ ] The loop produces the failure mode the **user** described — not a different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, reproducible at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix actually addresses it.

### Minimise

Once it's red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut — keep only what's load-bearing for the failure.

Why bother: a minimal repro shrinks the hypothesis space in Phase 3 (fewer moving parts left to suspect) and becomes the clean regression test in Phase 5.

Done when **every remaining element is load-bearing** — removing any one of them makes the loop go green.

Do not proceed until you have reproduced **and** minimised.

## Phase 3 — Hypothesise

Generate **3–5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors on the first plausible idea. Preserve low-probability, high-impact possibilities in the list — don't prune them just because they're unlikely.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe — discard or sharpen it.

For each hypothesis, identify the **cheapest discriminating observation** — the probe that confirms or kills it fastest. That ordering, not plausibility alone, sets the test order.

While ranking, trace the critical path: ownership, boundaries, retries, fallbacks, and recent changes. Distinguish the defect from the event that triggered it, and root-cause repair from symptom suppression.

**Show the ranked list to the user before testing.** They often have domain knowledge that re-ranks instantly ("we just deployed a change to #3"), or know hypotheses they've already ruled out. Cheap checkpoint, big time saver. Don't block on it — proceed with your ranking if the user is AFK.

## Phase 4 — Instrument

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the env supports it. One breakpoint beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Cleanup at the end becomes a single grep. Untagged logs survive; tagged logs die.

**Perf branch.** For performance regressions, logs are usually wrong. Instead: establish a baseline measurement (timing harness, `performance.now()`, profiler, query plan), then bisect. Measure first, fix second.

## Phase 5 — Confirm the mechanism, then repair or hand off

**Gate:** before recommending or applying any remedy, state the observed mechanism in **one falsifiable sentence** tied to the evidence. If that is not possible, the result is still a hypothesis — report it as one, with your confidence and what remains unverified. Then say, in one more sentence, why the same path worked before or what changed to trigger it now (an API value, a credential, a deploy, another consumer of the same input); if you have not established that, say so in the report.

The remedy — whoever applies it — is the **smallest change that maps directly to the mechanism**. Avoid speculative retries, broad catches, silent defaults, or security/performance machinery without a confirmed failure mode.

### Diagnose-only mode — hand off

Stop here and hand the confirmed mechanism to whoever owns the repair. The handoff must:

- name the reproduction or regression check that must **fail before the fix**;
- enumerate behavior-changing axes such as configuration, environment, and concurrency;
- require exhaustive old-versus-new cases when replacing load-bearing logic; and
- report the conclusion, evidence, confidence, and what remains unverified.

### Diagnose-and-fix mode — regression test + fix

Write the regression test **before the fix** — but only if there is a **correct seam** for it.

A correct seam is one where the test exercises the **real bug pattern** as it occurs at the call site. If the only available seam is too shallow (single-caller test when the bug needs multiple callers, unit test that can't replicate the chain that triggered the bug), a regression test there gives false confidence.

**If no correct seam exists, that itself is the finding.** Note it. The codebase architecture is preventing the bug from being locked down. Flag it in the post-mortem.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 feedback loop against the original (un-minimised) scenario.

If you check a test by forcing a mutation (reverting the fix, injecting a fault), first prove the mutation landed in the code the test actually runs (the installed copy, build, or import path), or its result proves nothing.

**Two failed fixes on one premise: test the premise, not a third fix.** When two fixes that share one premise fail the same check, write the premise in one sentence (for example, "the handler runs in the request process") and test it with an observation that would differ if it were false, before writing a third fix. A false premise sends you back to Phase 3 with the hypothesis list it invalidated.

## Phase 6 — Cleanup + post-mortem

Required before declaring done:

- [ ] Original repro no longer reproduces (re-run the Phase 1 loop)
- [ ] Regression test passes (or absence of seam is documented)
- [ ] All `[DEBUG-...]` instrumentation removed (`grep` the prefix)
- [ ] Throwaway prototypes deleted (or moved to a clearly-marked debug location)
- [ ] The hypothesis that turned out correct is stated in the commit / PR message — so the next debugger learns

**Then ask: what would have prevented this bug?** If the answer involves architectural change (no good test seam, tangled callers, hidden coupling), recommend it as a follow-up with the specifics. Make the recommendation **after** the fix is in, not before — you have more information now than when you started.

**After a deep dig, also ask what would have shown the deciding fact at first look.** Propose the cheap, always-on signal (a log line, an assertion, a status field, a line in an existing report) that would make the next occurrence a glance instead of a dig.
