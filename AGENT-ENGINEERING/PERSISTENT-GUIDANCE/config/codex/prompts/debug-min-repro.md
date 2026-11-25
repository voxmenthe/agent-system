# Debug: Minimal Reproduction First

Goal: produce a minimal, deterministic reproduction before any fixes.

## Steps
1) **Extract the failing behavior** into the smallest possible script or test. If a test framework exists, write a single, focused test named `test_minimal_repro`.
2) **Freeze the environment**: enumerate OS, runtime, package versions, feature flags, config.
3) **Remove dependencies**: replace external calls with stubs/mocks until the failure disappears; then reintroduce only what's necessary.
4) **Document exact run incantation** (one command).
5) If repro is elusive, **shrink by halves**: binary-search inputs, data volume, concurrency, and feature flags.

## Deliverables
- A self-contained repro snippet/test.
- One command showing red/green status.
- Notes on which removals/injections changed the outcome.

## Additional Context (Optional)
$ARGUMENTS