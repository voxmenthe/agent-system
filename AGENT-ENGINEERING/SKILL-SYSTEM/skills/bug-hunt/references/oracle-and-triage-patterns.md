# Oracle and triage patterns

Load this when designing oracles (Phase 2), calibrating (Phase 3), or
triaging and reporting (Phase 5). The blueprints come from published
property-based bug hunts on parsers, SDKs, a Git implementation, and a
database API.

## Blueprints

### Parser, printer, serializer

- Round trip over generated structures: `parse(print(x)) == x`. Also
  `print(parse(print(x))) == print(x)` when printing normalizes.
- Separation: `parse(a + SEP + b) == parse(a) + parse(b)`, so one item never
  swallows the next.
- Invariance: comments, blank lines, whitespace, keyword case, and line
  endings (LF vs CRLF) that the docs call insignificant must not change the
  parse.
- Error path: on arbitrary text, `parse` raises only its documented error
  type, never a crash or a different exception.
- Generator: build structures from the grammar with colliding name pools,
  and put every character that matters to the format into value alphabets:
  quotes, backslash, comment markers, separators, `=`, whitespace at both
  ends, newline, tab, and non-ASCII text.

### Streaming or adapter dual path

- Send the same payload through the batch and the streaming path (or sync and
  async, or two API bridges) and compare field by field, one signature per
  field (`stream__usage__provider`).
- Fragment the stream at every position, including inside multi-byte UTF-8
  and inside tokens; allow empty fragments.
- Compare both paths to the generated ground truth too, so a bug present in
  both paths is still caught.

### Stateful API interleaving

- Generate sequences over 2-5 handles (statements, cursors, sessions) on 1-2
  connections, with some suspended while another runs writes, schema
  changes, or transactions.
- Check in lockstep against a reference model or reference engine after
  every step, then close and reopen, ideally reading the result with an
  independent reader.
- Keep earlier generator versions runnable as coverage baselines when you
  evolve the generator.
- Counted harness classes are not verdicts: documented-unsupported (skip),
  undefined by the spec (unspecified), already filed (known), and minor
  documented differences (tolerated). Count each and report the counts.

### Typed-wrapper differential (URLs, auth, paths)

- Call the same function with the raw string and with the parsed type
  (`check(uri_str)` vs `check(Url(uri_str))`); any disagreement is a
  candidate finding.
- Alphabet: backslash, percent-encoded host characters, trailing space and
  C0 controls, IPv4 shorthand (`127.1`), IDNA hosts, empty authority
  (`app://`), repeated query parameters.

### Direct vs composed (mounted, proxied, cached)

- Run identical client actions against a component directly and through
  the composition (mounted under a parent, behind a proxy or middleware,
  with a cache) and compare results, logs, and levels.
- Cache laws: a hit equals the miss it replaced, a write invalidates, sync
  and async caches agree, costs stay finite and non-negative.

### Reference implementation with two tiers

- Generate small worlds where names collide (a branch and a tag with the
  same name, hex-like names, skewed timestamps) and resolve each query in
  both implementations.
- Use a fast batch oracle for throughput and re-decide every disagreement
  with the authoritative command before it counts.

## Signatures

Name each check `area__kind__detail`, for example
`roundtrip__value_changed__quoted` or `crash__exception__loads`. Engines tell
failures apart by where they are raised (Hypothesis: exception type and the
raising line; Ephyra: panic location or `signature(...)`). A shared helper
that raises from one line merges every signature, so in Python give each
signature its own exception class:

```python
_KINDS: dict[str, type[AssertionError]] = {}


def fail(signature: str, detail: str) -> None:
    """Raise a failure that shrinks and reports apart from every other signature."""
    kind = _KINDS.setdefault(signature, type(signature, (AssertionError,), {}))
    raise kind(f"{signature}: {detail}")
```

## Counted masks

Mask a confirmed bug only when it fires so often that it hides others, and
only narrowly:

```python
import os
from collections import Counter

MASKED: Counter[str] = Counter()
MASKS_ON = os.environ.get("NO_MASK") != "1"


def masked(name: str, applies: bool) -> bool:
    """True when an already-confirmed bug explains this case; counted, never silent."""
    if MASKS_ON and applies:
        MASKED[name] += 1
        return True
    return False
```

Report every mask with its count and share of cases; a mask that covers a
large share is hiding search space. Run once with `NO_MASK=1` before the
final report to confirm the masked bugs still reproduce.

## Seeded-mutant calibration

1. Pick one to three small realistic mutants on the surface under test: a
   dropped escape, an off-by-one bound, a swapped comparison, a missing
   branch for an edge value, or a known historical bug.
2. Apply each outside the target tree: `unittest.mock.patch.object` inside a
   calibration test, a scratch copy with a one-line patch, or a mutant patch
   file applied in a scratch worktree.
3. Run the harness at smoke budget. Record mutant, catching property,
   signature, time to kill, and shrunk input. A mutant that survives means
   the oracle or generator is too weak: fix that before hunting.
4. Confirm the target is unchanged (`git diff --exit-code`, or checksums).

## Flake check

Replay each failure three times with the same seed in a fresh process. If
the outcome varies, look for time, randomness outside the engine, state kept
between cases, threads, the filesystem, or the network. Report a flake with
its rate and suspected source. It is a product bug only when the
nondeterminism itself breaks a documented guarantee.

## Triage questions, in order

1. Is the input inside the documented domain (types, preconditions,
   grammar)? No: **generator invalid-input bug**.
2. Does the failure reproduce on a clean environment with pinned versions?
   No: **oracle / environment bug**.
3. Does a quotable source state the expected result? Yes, and the oracle
   reads it correctly: **real product bug**. The source documents the
   observed behaviour, or the oracle misses a legitimate equivalence:
   **oracle / environment bug**.
4. Sources silent or contradictory: **spec / contract ambiguity**.

Dedupe before reporting: one root cause with several manifestations (a wrong
value for one input, an exception for another) is one bug listing both
signatures. Check the project's issues, tests, and recent commits, and
reproduce on the latest revision.

## Bug report template

```markdown
## One-line summary of the wrong behaviour

- Version tested: package version or commit, runtime, OS
- Expected: what the source says, quoting "the sentence" from its doc path
- Actual: the exact observed output

### Reproducer (no property-testing dependency)

Ten to thirty lines, plus the exact command that runs them.

### Regression test

Path in the target's own suite, the command, and its failing output on
unmodified code.

Found by: property name, oracle rung, signature, seed.
```

If the user authorizes filing upstream, follow the project's contribution
guide, issue template, and any AI-use policy; send anything that may be a
security problem through its private channel.

## Hunt report template

| Property | Oracle rung | Source | Cases | Coverage before, after | Failures |
|---|---|---|---|---|---|

Then: calibration kills (mutant, property, signature, time, shrunk input);
the bug ledger; spec questions; flakes; masks with counts; generator
self-check results after the last evolution; cleanup (state directories
removed, workers and servers stopped, target status clean); and the next
surface or oracle worth trying.
