# Review Scan evidence

Review Scan is deterministic attention evidence, not a verdict, refactoring
request, or quality score.

## Validate the package first

Require:

- `review-evidence/v2` and a stable event ID;
- complete base/head Git object IDs and exact commit count;
- typed analysis status, policy/tool versions, and Python-target provenance;
- a complete target manifest with every signal reference resolvable;
- `truncated: false` for an attention package; and
- no source body, transcript, credentials, author identity, or environment
  dump.

An invalid, stale, incomplete, or contract-incompatible package is a
capability gap. Do not fill missing identities from guesswork. A scope-overflow
request must name every affected file explicitly.

## Review behavior

1. Freeze the exact range and inspect its whole net diff independently before
   following highlighted targets.
2. Account for every target and relationship signal in the manifest.
3. Classify observations as actionable correctness risk, accidental retained
   structure, justified structure, contextual evidence, or noise.
4. Check unhighlighted changed paths for more serious risks.
5. Preserve diagnostic messages for correctness signals and interpret metric
   deltas in context; improvement in a metric is not proof of quality.
6. Record package health and coverage in the receipt.

For an explicit full scan, use the repository-owned read-only scan command only
when it is installed and validated. Resolve moving refs once, pass full object
IDs, and fail visibly if the shared operation is unavailable. Never checkout,
stash, reset, stage, commit, alter refs, or scan the mutable worktree as a
substitute for immutable Git objects.

In automatic mode, treat the package only as selection context. Independently
review the full exact range, then run the hook-supplied private outcome command
with the number of findings you will report. The command does not authorize a
target-repository write, and the user does not prepare labels or notes.
