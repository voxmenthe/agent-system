---
name: greenfield
description: De-risk an upcoming or in-progress greenfield project by organizing its load-bearing capabilities into parallelizable spike work streams — small runnable demos, minimal feasibility studies, and when interaction risk demands it a mini-MVP — packaged as self-contained briefs for handoff to an orchestrator that executes them with a swarm of agents. Use when planning a new project whose key pieces of functionality need quick empirical validation before committing to architecture, scope, or estimates. Do not use to answer a single design question inside an existing codebase, to execute the spikes yourself, to build the production implementation, or for brownfield changes.
disable-model-invocation: true
---

# Greenfield

Turn a greenfield or in-flight plan's risky assumptions into a set of independent, parallelizable **spike work streams**, packaged for handoff to an
orchestrator that runs a swarm of agents to execute them concurrently. A
**spike** is the smallest runnable demonstration of one capability the full
system will need.

This skill plans the campaign and produces the handoff package. The
orchestrator executes it. The deliverables are the package before execution
and the verdict map after it.

## Keep the boundary narrow

- The input is a project plan or feature list concrete enough to enumerate
  capabilities. If it is too vague for that, stop for upstream planning; do
  not invent scope and then spike it.
- This is a planning mode. Do not build the spikes yourself; produce the
  work-stream package and hand it off. A single open design question in an
  existing codebase is a different task — use a single throwaway prototype
  for that.
- Never production: no hardening, no auth, no deployment, no mutation of
  shared state, and no paid or irreversible external calls without explicit
  approval. Bake these limits into every brief.
- The spike suite is throwaway exploration code, clearly marked, and kept out
  of every production path. The mini-MVP is not the seed of the real
  codebase; do not let it silently become one.

## Size and split work streams

Treat a spike work stream as one independently answerable feasibility
question, not a list of files or generic tasks. It is well bounded when one
agent can:

- run one minimal probe without another same-wave spike's unreturned verdict;
- own its directory plus any scratch resource or external quota exclusively;
- return evidence and a verdict useful even if peer spikes fail; and
- name the later planning decision that consumes the verdict.

Test any long, complex, or critical-path spike for a further split. Split when:

- it bundles questions whose verdicts can change the plan independently;
- child probes can meet through a fixed input, fixture, or prior verdict rather
  than shared mutable work;
- distinct resources or failure modes support separate owners; or
- it is expected to dominate completion time and child questions would let
  additional agents make useful progress concurrently.

Apply these tests recursively. Stop splitting when child probes would share
write targets, scratch resources, or quotas; depend on unresolved same-wave
findings; add setup, glue, or coordination larger than the probe; or fail to
yield independently useful verdicts. If no safe evidence seam exists, keep the
spike whole, mark it as a critical-path constraint, and explain why. Do not
manufacture parallelism by splitting files or implementation steps.

Use the question, verdict, and ownership boundary as the sizing rule. Do not
invent a universal duration, point, or worker-count threshold; time-box each
coherent spike separately.

## Workflow

1. **Capability inventory.** From the plan, list the functional capabilities
   the full implementation will depend on. Split each into
   known-straightforward or unknown/risky. Do not spike the straightforward —
   a demo of ordinary CRUD teaches nothing.
2. **Prioritize.** Rank the risky capabilities by
   `ignorance × plan risk × cost of a wrong assumption`. Choose the smallest
   spike set that retires the most plan risk, and state what was deliberately
   left unspiked.
3. **One question per spike, one spike per work stream.** Give each spike a
   named question it must settle ("Can library X stream Y at the needed
   rate?", "Does the API support partial updates?") and define the smallest
   demo that settles it: one command to run, hardcoded inputs, no
   abstractions, output that prints the evidence.
4. **Make the streams independent.** Each work stream owns exactly one
   directory, `spikes/<id>/`, and writes nowhere else. Shared files — the
   plan index and the final report — belong to the aggregator, never to
   workers. If two candidate spikes would need the same file, scratch
   resource, or external quota, merge them or sequence them; that coupling is
   itself plan information worth recording.
5. **Draw the dependency edges.** Put streams in the same wave only when
   neither needs another's unreturned verdict, their owned paths and scratch
   resources do not conflict, and each can run against fixed inputs or
   independently prepared fixtures. Most streams should satisfy those rules
   and form a single wave. A spike gated on another's feasibility verdict,
   and the mini-MVP, go in later waves that consume those verdicts. Build the
   mini-MVP only for interaction risk — when the open question is whether
   capabilities compose end to end — as the smallest integration of a subset
   demonstrating one thread.
6. **Write self-contained briefs.** Each executing agent starts with zero
   context. The brief must stand alone: the question, the constraints, the
   owned paths, the expected run command, the time-box, the verdict format,
   and the evidence to print. A brief a fresh agent could misread gets
   rewritten — ambiguity in a parallel worker multiplies.
7. **Package the handoff.** Assemble the plan index, the briefs, the wave
   schedule, and the aggregation contract, plus a short orchestrator summary
   covering waves, parallelism limits, and the per-worker effect ceiling.
8. **Aggregate after execution.** Collect the returned verdicts into the
   spike report. Every verdict must change something in the plan: scope, an
   architecture choice, sequencing, estimates, or a killed direction. A spike
   that changes nothing was the wrong spike.

## Work-stream brief format

One brief per stream, with exactly these fields:

- **id** — kebab-case, matching its owned directory `spikes/<id>/`.
- **capability and question** — what the full system needs and the named
  question this spike settles.
- **task** — the smallest demo to build, the expected run command, and the
  evidence it must print.
- **owned paths** — `spikes/<id>/` only; writing elsewhere is a contract
  violation.
- **constraints** — time-box; throwaway code; no tests beyond runnability; no
  persistence unless persistence is the question, and then a scratch store
  marked disposable; no external mutation, paid calls, or network writes.
- **dependencies** — `none`, or the spike ids whose verdicts this stream
  consumes.
- **verdict** — one of `FEASIBLE`, `FEASIBLE WITH CONSTRAINTS`,
  `INFEASIBLE`, `UNRESOLVED`, plus the numbers or constraints behind it,
  reported back in the format the aggregation contract defines.

## Handoff package layout

```text
spikes/
├── SPIKE-PLAN.md      # capability inventory, skipped items, waves, aggregation contract
├── briefs/
│   ├── <id>.md        # one self-contained work-stream brief per stream
│   └── ...
└── <id>/              # worker-owned output directories, created by the workers
```

`SPIKE-PLAN.md` is the orchestrator's entry point: it lists every stream,
its wave, and its brief path, and defines how verdicts are reported back so
aggregation is mechanical.

## Output: spike report

After the orchestrator returns, produce the verdict map, in conversation or
as `SPIKES.md` beside the suite:

- the capability inventory, including what was skipped and why;
- per spike: question, run command, verdict, and the key numbers or
  constraints discovered;
- the mini-MVP result if one was built: what the end-to-end thread
  demonstrated and what it did not;
- plan implications: decisions now backed by evidence, assumptions killed,
  new risks found, and revised sequencing or estimates.

## Rules

- Prefer more independently verdictable spikes over one large spike, but split
  only at evidence seams. A quick-script scope is a warning to retest the
  boundary, not permission to divide one inseparable question arbitrarily.
- No spike without a question. A demo that settles nothing is waste.
- Skip the polish, in the briefs and in the demos: no tests beyond
  runnability, no error handling past the happy path.
- Time-box each spike. A worker that cannot reach an answer reports
  `UNRESOLVED` with what was learned and stops; it does not rabbit-hole.
- Never give two workers the same write target. The plan index and the report
  are aggregator-owned files.
- Do not run the swarm from this skill. Hand the package to the orchestrator
  and let it own scheduling, parallelism, and worker supervision.

## Stop conditions

- A load-bearing premise proves infeasible: stop and report; do not patch
  around it to keep the plan alive.
- The plan shifts materially mid-exploration: re-derive the capability
  inventory and re-issue affected briefs before more workers start.
- The capabilities cannot be decoupled into independent streams: do not force
  parallelism — plan a short sequential campaign and say why.
- A brief starts needing production concerns such as auth, real persistence,
  or scale: that is the implementation talking. Stop and hand the finding
  back to planning.
