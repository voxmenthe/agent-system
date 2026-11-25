# Implementation discipline

## Applies when

Load this pack before editing production code, configuration that changes runtime behavior, build/dependency files, scripts, or executable tooling. It also applies when reviewing implementation shape or correcting a bug.

## Does not apply when

Do not load it for pure prose work with no executable or behavioral consequence. For generated files, follow the generator and source-of-truth instructions rather than hand-editing output.

## Non-negotiable rules

- Implement exactly the requested behavior. Do not bundle “while here” cleanup, speculative flags, shims, hooks, extension points, or unrelated refactors.
- Default to deletion. Remove unused helpers and redundant checks when they are part of the requested change, but do not broaden scope merely to tidy nearby code.
- Validate at boundaries, then trust real internal invariants. Required fields and configuration fail loudly; do not hide them behind `.get(..., default)`, broad fallbacks, or speculative defensive code.
- Never use broad `except Exception` in normal code. Catch only errors whose meaning and recovery are understood. Library code raises domain errors; thin CLI/UI edges translate them for users.
- Keep expensive work and side effects honest in names and interfaces. Do not hide network, filesystem, database, model, or repeated linear work in property-like accessors.
- Make the smallest reviewable diff. Separate mechanical movement or renaming from semantic change when both are necessary.
- Deepen one component at a time and keep the system runnable end to end between steps. Never leave the path broken while working elsewhere, and never build a component in isolation to wire up later: wire it into the running path now, against stubs if necessary.
- Do not reintroduce temporary code that ships, dead disabled-feature scaffolding, preflight checks for failures never observed, retry wrappers added on a hunch, defensive security machinery without a concrete threat model, or repository pollution that merely works around a downstream tool defect.

## Procedure

1. **Form hypotheses before editing.** For bugs, rank one to three plausible causes. Test the most likely while preserving low-probability, high-impact possibilities. Update the hypotheses when evidence changes.
2. **Choose the least-powerful sufficient mechanism.** Prefer data over code, schemas over validation code, configuration over branching, built-ins over libraries, libraries over frameworks, and functions over classes unless functions are insufficient.
3. **Shape control flow for verification.** Use early returns. Do not split a cohesive function to meet a length or branch count. A single-use helper of four lines or fewer normally stays inline unless its name captures a caller-visible concept. Delete a helper that has one caller after refactoring unless it preserves a real boundary.
4. **Extract only shared rules.** Two similar bodies often stay duplicated when they represent different reasons and may drift independently. Extract when the same rule exists for the same reason and changing one almost always requires changing the other. Three repeated shapes are evidence worth investigating.
5. **Push domain rules downward.** When CLI/web, train/eval, or other surfaces implement the same rule, move it into the domain model rather than adding a sideways shared helper.
6. **Use honest naming in the domain's vocabulary.** When the person describing the work names a domain concept, use that word in identifiers, types, and tests rather than a synonym. Commands are verbs. Cheap pure queries may be nouns when context is clear. Expensive reads use `fetch_*`; writes use `save_*` or `write_*`. Variables are explicit nouns. Avoid vague core names such as `Manager`, `Handler`, `Processor`, `Util`, `Helper`, or an unqualified `Service`; name the actual role or split it.
7. **Keep files cohesive.** Aim near 400 lines and avoid exceeding 700: file size raises an agent's cost to load and check a module. Propose relocation before broad splitting; line count is a signal, not a substitute for cohesion. Function length and branch count are not problems by themselves; branches are paths that tests must tell apart.
8. **Handle cleanup once.** Wrap only the call that can raise in `try/except`; use `try/finally` or structured resource management rather than duplicating cleanup at every return.
9. **Make fallbacks deliberate.** Investigate root cause first. A necessary fallback must constrain blast radius, emit structured context describing the error and fallback, and have a test. Graceful degradation belongs at edges; invariant violations in dense core logic should fail fast.
10. **Consider performance where load-bearing.** State or infer expected input size. Avoid repeated filesystem, database, model, or network calls in loops unless the bound is tiny and obvious. Add a benchmark only for a measured bottleneck, a load-bearing change, or an asymptotic improvement needing evidence. When measurement shows a load-bearing gain, take the faster shape even at a readability cost; keep the interface and domain names, and guard the change with a test against the plain version or the behavior it must keep.
11. **Use current sources.** Inspect the repository before assuming its stack. For APIs or versions that may have changed, prefer current official documentation. For Python projects, use `uv` when the repository does not specify otherwise; for a new React/TypeScript frontend with no contrary constraint, prefer a modern TypeScript and Vite setup.
12. **Recover deliberately from tool failures.** Retry transient tool or workflow errors two or three times with changed parameters or a better hypothesis, not blind repetition. After that, state what failed and what evidence would unblock progress. Never turn a transient investigation tactic into committed retry machinery without a concrete failure contract.
13. **Fix self-introduced mechanics without ceremony.** Correct syntax, formatting, compile errors, and typos introduced by the current change and keep the fix inside scope. Report only consequences material to the result, validation, or the user's next action.

Useful search defaults: `sgrep` to find code by behaviour, `fd` for files, `rg` for text, `ast-grep` for structure, `jq` for JSON, and `yq` for YAML/XML. Use structural search when syntax matters. Batch independent reads and searches; do not hide long-running work in committed retry machinery.

## Done criteria

- The change addresses the root cause and no unrelated behavior.
- Names use the domain's terms, and changed behavior can be run and checked on its own.
- Required configuration and invariants fail clearly; error handling is specific.
- No speculative widening, hidden expensive work, accidental quadratic behavior, or unbounded repeated I/O was introduced.
- The diff is focused, generated sources are respected, and obsolete artifacts made irrelevant by this change are handled safely.
- Validation described in the testing pack has been performed and reported accurately.
