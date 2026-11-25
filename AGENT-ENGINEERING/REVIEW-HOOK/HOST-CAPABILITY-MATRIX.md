# Host capability matrix

## Host version policy — 2026-10-05

Captured CLI versions are recorded in bundle manifests and `status` but no
longer gate `validate`, `install` or activation; only a missing CLI or one that
cannot report its version blocks. Kimi Code `2.1.1` and Antigravity `1.2.17`
were installed on that basis: Antigravity's `plugin validate` accepted the
bundle and ordinary launches of both still work. Review-mode delivery on these
binaries is not re-proven. Bundles differ from the proven Codex bundle below
only in `scripts/review_hook.py`.

## Current selected route — 2026-10-03

Codex CLI **0.160.0** is the currently recertified route. A current-binary hook
capture supplied the checked-in sanitized Pre/PostToolUse fixtures. The existing
`Bash`/`tool_input.command` parsing and `additionalContext` emission still work;
no speculative host adapter rewrite was necessary.

The canonical reviewer digest now has one runtime owner; the install manifest
derives it, and the Skill System's regression checks it against the actual
canonical package. The reviewed skill and evaluated candidate were not changed.

| Boundary | Current evidence |
|---|---|
| Actual commit observation and delivery | Current Codex executed a staged commit in an owned repository; lifecycle instructions arrived automatically, without a manually manufactured request |
| Reviewer and result | Canonical `diff-review` reproduced the deliberately seeded mutable-default regression and executed the delivered private result command |
| Private isolation | One scan, one Codex delivery, one review, one finding; zero awaiting results; ordinary outcome aggregate unchanged |
| Replay/concurrency | Duplicate and simultaneous PostToolUse callbacks emit once; counters and private event history are stable; retry behavior for other hosts is retained |
| Selected bundle/projection | `sha256:7d49e9e3e7877ed0bbb4fd8e50f5b9bbe9f2817ebe2d8816c4b3272ec153bba2`; exact live Codex installation reports `current` |
| Focused regression checks | 88 tests across the core, three adapters, installer, management scan and outcomes pass |
| Kimi Code / Antigravity | Not recertified or installed; current binaries `2.1.1` / `1.2.16` differ from captured `0.39.1` / `1.1.22`; old managed bundles are stale |

See the milestones 4–6 run record
for immutable ranges, capture/projection receipts and before/after regressions.
The headless live probe used an owned home and explicit hook-trust flag. It
does not establish every launcher/trust combination, native UI delivery,
all-host compatibility or natural-review yield. Codex's once-only consumption
does not guarantee delivery after a crash between consumption and stdout.

## Historical all-host matrix — 2026-08-30

The following records repository tests, disposable-home tests, installed-bundle
tests and non-interactive live launcher probes at that date. Disposable Git
repositories kept the workspace and existing host sessions unchanged. These
are historical observations, not current installation claims.

| Capability | Codex command-line agent | Kimi Code | Antigravity |
| --- | --- | --- | --- |
| Normal launch stays unhooked | Parser and adapter negatives pass | Parser and adapter negatives pass | Enabled plugin returns immediately when review mode is not selected |
| Scheduled mode | Shared counter, exact-range, duplicate, and host-delivery tests pass | Shared behavior plus stop and next-command delivery tests pass | Shared behavior plus deferred-delivery and replay tests pass |
| Automatic scan and selection | Installed adapter selected a known Python correctness problem in an isolated repository | Installed adapter selected the same problem in an isolated repository | Installed plugin selected the same problem in an isolated repository |
| Automatic delivery | Installed adapter emitted immediate read-only review context and recorded Codex delivery | Installed adapter emitted the proven stop-boundary denial and recorded Kimi Code delivery | Installed plugin deferred to the next invocation and recorded Antigravity delivery only when emitted |
| Silent automatic event | Python nonmatch, non-Python range, and scan-failure tests emit no invented review while retaining private scan status | Uses the same shared core and installed policy | Uses the same shared core and installed policy |
| Reviewer result capture | Delivered request includes the private result command; management tests cover findings and no findings | Same shared command and canonical review skill | Same shared command and canonical review skill |
| Automatic outcome summary | Installed management command runs against the live private state root | Installed management command returns the same summary | Installed management command returns the same summary |
| Folder trust | Selected Codex profile preservation tests pass | Wrappers trust the current folder; repeated high-to-maximum effort switches preserve a valid generated configuration and receipt | Existing Antigravity trust behavior is unchanged |
| Launcher probe | `cdx --review-mode auto --version` returned Codex `0.151.0` | `kimh` and `kimm` automatic-mode version probes returned Kimi Code `0.39.1` | `agg --review-mode auto --version` returned Antigravity `1.1.22` |
| Live managed state | Current | Current | Current, registered, enabled, and marked dormant without selection |

The complete repository check passed 167 Python tests plus both shell test
scripts. The Skill System validation and audit passed, and the live
`diff-review` projection matches its canonical source.

### Historical evidence boundary

The installed automatic adapters, selection policy, delivery paths, and
private outcome commands are verified. Earlier end-to-end host tests also
proved real commit observation and review delivery for all three hosts.

At the August check no naturally occurring automatic-mode review had happened,
so the outcome summary contained zero scans and zero reviews. That was expected
before normal dogfooding began; it was not evidence
that user behavior was simulated. Real scan, delivery, finding, and no-finding
outcomes will be captured automatically during ordinary automatic-mode use.
