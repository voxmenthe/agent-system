# Shared-context wave runner

Use this optional helper script for independently runnable assignments with a
shared context. After authoring one `wave.txt`, launch all workers with one command:

```bash
DELEGATE_WAVE="$HOME/.agents/skills/delegate/scripts/run-wave.sh"
"$DELEGATE_WAVE" --wave wave.txt --jobs-dir out/wave-001
```

`out/` must exist; `wave-001` must not exist. Add `--dry-run` to inspect composed
packets without launching workers; use a **new** directory for execution after
preview. `--jobs N` bounds concurrency (default 4, capped by worker count).
`--timeout SECS` (whole seconds, 1 to 9999999) stops any worker still running
SECS seconds after its launch (see [cancellation](#cancellation-and-recovery));
there is no default timeout.
`--help` shows usage. Input and artifact paths resolve against the caller's
working directory, not the manifest's location. Adapters start in `WORKSPACE`.

Before launching, `~/.agents/skills/delegate/scripts/wave-usage wave.txt` prints
one line per quota window above 80% used, or unreadable, on a harness the wave
uses, naming the wave's launchers there; it prints nothing when every window is
fine. It is a warning, not a gate: re-routing stays your decision. Launchers
share a quota account as listed in `scripts/launcher-routes.tsv`, one row per
account; the runner reads the same table.

This is a path within [delegate](../SKILL.md), not a new delegation authority.
Read its [invocation rules](../SKILL.md#honor-the-invocation-and-authority),
[ownership discipline](../SKILL.md#establish-ownership-before-launching), and
[integration requirements](../SKILL.md#integrate-and-verify). Launcher examples
illustrate syntax, not permission to change the user's requested model mix.
Ordinary adapter calls do not need this reference.

## Two manifest shapes

Varied independent implementation assignments, with settled interfaces and
separate tests (substitute an existing absolute workspace):

```text
COMMON:
ROLE: implement
WORKSPACE: /absolute/path/to/project
CONTEXT: Parser and serializer interfaces and fixtures are already agreed.
  Each assignment below can be implemented and tested without the other's output.
CONSTRAINTS: <shared non-goals — written once>

@@ launcher=aggb name=parser
OBJECTIVE: Add the agreed parser boundary.
SCOPE: src/parser.py and tests/test_parser.py only
VERIFY: Run the focused parser tests.

@@ launcher=cdx name=serializer
OBJECTIVE: Implement the agreed serializer interface.
SCOPE: src/serializer.py and tests/test_serializer.py only
VERIFY: Run the focused serializer tests against the agreed fixtures.
```

Same-prompt **read-only** fan-out; the complete task is written once:

```text
COMMON:
ROLE: review
OBJECTIVE: Identify correctness defects in the parser and serializer contract.
WORKSPACE: /absolute/path/to/project
SCOPE: Read src/parser.py, src/serializer.py, and their focused tests; edit nothing.
CONTEXT: Both implementations are complete and no writer is active on these files.
CONSTRAINTS: Keep this review independent and read-only; do not delegate further.
VERIFY: Trace each suspected defect to a concrete input and source location.

@@ launcher=clm name=review-a
@@ launcher=clmb name=review-b
@@ launcher=cdx name=review-c
```

Before launching writers, review paths, generated artifacts, shared configuration,
and dependencies. Keep the manifest and jobs directory outside every worker's
write scope. Shared context does not prove independent ownership: each assignment
must run and verify against the starting workspace. Same-prompt writers in one
workspace are unsafe; use disjoint assignments or separately prepared workspaces
through the single-worker adapter. Dependent work belongs in later waves, even
with `--jobs 1`. No token-overlap detector is used; parser success and dry run do
not certify scope independence.

## Manifest v1 contract

- First nonblank line: exactly `COMMON:`, once. At least one worker follows,
  each beginning exactly `@@ launcher=<known> name=<id>` with no extra attributes.
  Invalid input reports manifest line numbers and launches nothing, including
  when a later block is invalid.
- Headers and field labels start at column zero. Continuations are indented;
  blank lines are allowed. Indent reserved markers inside quoted context.
  LF, CRLF, and missing final newline are accepted. Field text is preserved
  (line endings normalize to LF); shell metacharacters remain literal data.
  The manifest is never sourced, evaluated, expanded, or executed.
- COMMON requires nonempty `ROLE`, `WORKSPACE`, `CONTEXT`, and `CONSTRAINTS`.
  `ROLE` is `implement`, `analyze`, `review`, or `verify`; the last three are
  read-only, including their checks. `WORKSPACE` is one existing absolute
  directory. ROLE and WORKSPACE have single-line values.
- Every final packet requires exactly one nonempty `OBJECTIVE`, `SCOPE`, and
  `VERIFY`, each supplied either in COMMON or the worker block, never both.
  Worker blocks may supply only those three fields. Duplicates, unknown labels,
  and user-authored `RETURN` are rejected. There are **no overrides**, even for
  VERIFY: supply common checks for everyone or each worker's complete checks.
- Empty worker bodies are valid when COMMON supplies every required field.
  Names match `[A-Za-z0-9][A-Za-z0-9_-]*` and must be distinct after ASCII case
  folding. Duplicate launchers are allowed.
- Eligible launchers (case-sensitive): `agg aggbs aggb aggbbs agom agoh argm argh aghh aghhb aghx aghxb agcm agcmb agch agchb agnm agnmb agnh agnhb agnx agnxb
  agg2 aggbs2 aggb2 aggbbs2 agom2 agoh2 argm2 argh2 aghh2 aghhb2 aghx2 aghxb2 agcm2 agcmb2 agch2 agchb2 agnm2 agnmb2 agnh2 agnhb2 agnx2 agnxb2
  kimm kimb kimbs dglm dswe dargh dopmm doph dopx dopm grok grokxh grok2 grok2xh grok3 grok3xh
  clm clmb clme clmbe clm2 clmb2 clme2 clmbe2 ctx ctxb ctx2 ctxb2 ctm ctmb ctm2 ctmb2
  cdx cdxb cdxe cdxbe cdx2 cdxb2 cdxe2 cdxbe2 cdm cdmb cdme cdmbe cdm2 cdmb2 cdme2 cdmbe2
  cam camb cax caxb camm cammb cah cahb cam2 camb2 cax2 caxb2 camm2 cammb2 cah2 cahb2
  cdmM cdxX camM caxX cdmM2 cdxX2 camM2 caxX2 ocs ommp ocargh ochy ocq4h ocq4x ocmm26 ochy4flash oclongcat ociceman
  cmg cmds cmm26p cmqh cmqx cms cmhy cmdglyph cmdflint pihy4flash pilongcat piiceman
  csm csu csx cshh csmm csbm csbu csbx csbh csbmm chm chu chx chh chmm
  chbm chbu chbx chbh chbmm ccx ccbx ccm ccbm ccmm ccfh ccbfh ccfx ccbfx ccmM ccxX
  cck cckm ccku cckx cckh cckmm cckbm cckbu cckbx cckbh cckbmm
  cckfm cckfu cckfx cckfh cckfmm cckbfm cckbfu cckbfx cckbfh cckbfmm`.
  The Kimi Code launchers inherit managed K3.1 Pro through the sibling adapter.
  Opus (`ccx`/`ccbx`, `xhigh`) and Fable (`ccfh`/`ccbfh`, `high`) are expensive
  oracle-like consultants; use sparingly for bounded, high-value questions.
  Eligibility is not a routing recommendation: honor the
  [explicit-user routes](../SKILL.md#explicit-user-routes), including the effort,
  account, API-key and boost opt-ins. Boost subagents are not counted by `--jobs` and
  must stay within their outer worker's assigned scope.
  The sibling `run-worker.sh` alone owns remapping, wrapper availability,
  failure suppression, and final-output extraction.
- `launcher=cmd:<native-id>` names an exact Command Code model, for a model the
  user named only ([explicit-user routes](../SKILL.md#explicit-user-routes)). The
  adapter passes it to `am`, which resolves and revalidates it before launch; a
  model that is no longer listed fails with `am: no matching live models` and
  never becomes another model. Native IDs use `[A-Za-z0-9._/:+-]`.
- `launcher=cdxk` defaults to `cdxk:cdx`. `launcher=cdxk:<launcher>` prefixes
  any eligible primary Codex launcher (for example `cdxk:cdm`, `cdxk:cam`, or
  `cdxk:cdmM`) with `cdxk`, using the OpenAI API-key account. The equivalent
  single-worker forms are `run-worker.sh cdxk cdm` and `run-worker.sh cdxk:cdm`.
  Use these only when the user explicitly requests Codex API-key agents.
  Secondary-account, non-Codex, and unknown targets fail before task writing.
- `launcher=agk` defaults to `agk:aghh`. `launcher=agk:<launcher>` prefixes
  any eligible primary Gemini Antigravity launcher (for example `agk:agnx`,
  `agk:agch`, or `agk:agnhb`) with `agk`, using `GEMINI_API_KEY` mode. The
  equivalent single-worker forms are `run-worker.sh agk agnx` and
  `run-worker.sh agk:agnx`. Use these only when the user explicitly requests
  Antigravity API-key agents. Secondary-account, non-Gemini (`agom`/`agoh`),
  non-Antigravity, and unknown targets fail before task writing.
- Any new launch path must append the same `[hist-parent]` line that
  `run-worker.sh` adds to the task, so `hist` links the worker to its parent.

Packets concatenate COMMON, a blank line, the worker body (if any), and one
generated footer. The footer summarizes the skill's preserve-unrelated-changes
and authority limits, retaining **unless the user explicitly authorized** the
action. Execution itself adds no authority; task text does not authorize
redelegation. The generated return contract is:

- Implement: `RETURN: STATUS, CHANGED, VERIFICATION, BLOCKERS`.
- Analyze/review/verify: `RETURN: STATUS, FINDINGS, EVIDENCE, BLOCKERS`.

The [task-packet contract](../SKILL.md#write-self-contained-task-packets) remains
authoritative; review it, the footer, and this reference together when changing
these semantics.

## Execution and evidence

The entire manifest is validated before exclusively creating a private jobs
directory (`umask 077`). Existing directories, files, and symlinks are refused;
there is no overwrite, resume, or replay flag. All tasks are written before any
launch. Prelaunch I/O failure leaves diagnostic evidence and launches nothing.
Dry run creates only `.task` files and prints named packet boundaries; it does
not source wrappers, probe authentication, or validate providers or ownership.

Adapters launch in manifest order with closed stdin, at most N at once. Capacity
refills as any worker finishes, not in batches or only when the oldest finishes.
N counts adapters: a returned worker's leftovers that are still being stopped do
not hold a slot, so keep assignments disjoint even under `--jobs 1`.
An ordinary worker failure does not cancel independent peers or trigger retries.
A failure whose class (below) is `rate-limited` or `quarantined` bars its
launcher for the rest of the wave: its queued workers become `not-started
(<kind> on <launcher>)`, stderr says so, and the rest of the wave keeps
dispatching. A failure whose class is `rate-limited: account quota exhausted on
<harness>`, naming the launcher's own harness, bars every launcher on its
account instead: their queued workers become `not-started (rate-limited on
account <account>)`, where `<account>` is the harness, or `harness:account` for
a secondary account such as `codex:codex2`. A secondary account is its own row,
so the primary's exhaustion leaves it eligible, and the reverse. Workers already
running continue. Re-routing is the parent's choice.

| Artifact | Meaning |
| --- | --- |
| `<name>.task` | Fully composed packet. |
| `<name>.out` | Adapter stdout, verbatim; never reconstructed from stderr. |
| `<name>.stderr` | Adapter stderr, verbatim. A failed run that reached its launcher ends with its failure class. |
| `<name>.status` | Reaped numeric exit status plus newline, `timeout`, `not-started (<kind> on <launcher>)`, `not-started (rate-limited on account <account>)`, or cancellation state below. |
| `WAVE.tsv` | `name`, `launcher`; written before the first launch, so a running wave can be read. |
| `SUMMARY.tsv` | `name`, `launcher`, `exit` (the `.status` value), `out-bytes`; tab-separated, manifest order. |

The failure class is the last stderr line, `delegate worker: failure class:`
followed by `rate-limited: <reason>` (a rate limit or quota), `quarantined:
<reason>` (an expired key, a missing credential, a signed-out CLI, an ended free
window or plan, a model the provider no longer routes, or another non-retryable
refusal) or `unclassified`. `scripts/refusals.py` reads
it from the last 8 KiB of the launcher's output; the market pool loads the same
table from the installed skill. An unclassified failure may be the task's own.
A rate limit counts only on a line the CLI writes as its own error record (a
plain-text `Error:`, a JSON error object or event, an HTTP status line, or the
adapter's own line); a worker's transcript that quotes one is not a refusal.
Only a recorded plan-wide quota message reads `account quota exhausted on
<harness>`: Codex's "You've hit your usage limit.", Devin's weekly quota and
OpenCode Go's "Go usage limit exceeded", each opening a line as the CLI's own
error record. A bare 429 or one model's limit stays `rate limit or quota`,
which bars only the launcher. The adapter names the failed launcher
(`refusals.py --launcher`), so a record only one harness writes (those three
quota messages, OpenCode's no-route error, Command Code's sign-out, Codex's
startup `Error loading config.toml`, the second Antigravity account's sign-in
line) counts only from that harness's launchers: another harness's transcript
may print it verbatim.

The parent alone writes the summary. Byte counts measure `.out` bytes, not
characters; absent output counts as 0. Launcher is the **requested alias**, not
an inferred effective provider. Fallback diagnostics stay downstream.

| Wave exit | Meaning |
| --- | --- |
| 0 | Every adapter exited 0; not proof of accepted work. |
| 1 | Worker or runner failure. |
| 2 | Invalid input or preflight failure. |
| 130 / 143 | SIGINT / SIGTERM, after handled cleanup. |

A zero exit or `STATUS: done` is not proof of correctness; `STATUS: blocked` can
arrive with exit 0. Inspect every returned status and actual workspace, resolve
blockers, and verify independently before starting dependent waves. The runner
does not parse responses or merge results.

For the fleet view, during or after a wave, run
`~/.agents/skills/delegate/scripts/wave-status <jobs-dir>`. It is read-only and
prints one line of counts (returned, blocked, failed by class, unsettled, not
started), then every failure and blocker, then at most 20 other rows (`--all`
prints all), each with the path of its full output. An unsettled worker reads
`output opened, no status` once the runner has opened its output, which it does
just before spawning the adapter, and `no status` before that. A `returned` row
is not accepted work.

## Cancellation and recovery

SIGINT/SIGTERM or internal supervision/artifact-write failure stops dispatch and
terminates owned local process groups, including wrapper and CLI descendants.
Cleanup waits up to five seconds before escalating remaining groups to SIGKILL,
then briefly checks termination and reaps direct children. It never intentionally
signals the caller's group or unrelated processes. Completed statuses survive;
queued jobs become `not-started`. Jobs whose termination cannot be confirmed
become `unconfirmed`, with outstanding PID/process-group identities on stderr.
Their scopes are **not released**.

An adapter that returns while its process group still has live processes (for
example an MCP server its CLI left behind) keeps its own exit status; the runner
reports the group on stderr and stops those leftovers with SIGTERM, then SIGKILL
after five seconds, while peers keep running. Leftovers are treated as
disposable, including an implement worker's backgrounded writer. With
`--timeout SECS`, a worker still running SECS seconds after launch is stopped
the same way; its status is `timeout` and the wave exits 1. A group still alive
two seconds after SIGKILL fails the runner into the cleanup above; if cleanup
cannot end it either, that worker becomes `unconfirmed`. These intervals use Bash's whole-second wall
clock: each can end up to one second early, and time the host spends asleep
counts, so a host that sleeps through a deadline stops the worker on waking.

Handled interruption produces status files and a summary when storage permits.
Storage failure is reported on stderr and returns nonzero; a partial summary
is not complete evidence. SIGKILL or host loss can leave missing files: missing
status/summary means **unknown**, never success. Inspect processes and workspace
before a fresh invocation. Local process groups cannot prove cancellation of
detached or remote provider work, and termination does not undo edits. Follow
[stop conditions](../SKILL.md#stop-conditions) before reassigning uncertain scopes.

## Focused validation (no model calls)

The runner needs Bash 3.2+, standard macOS/Linux utilities, its executable
sibling adapter, which retains its own dependencies, and the sibling
`launcher-routes.tsv`; without the table, or a row for a manifest's launcher,
it launches nothing. It adds no Python or jq runtime dependency. Tests need
Python 3; real-adapter fixtures also need jq.
From the repository root:

```bash
python3 -B -m unittest discover -s AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/tests -v
python3 -B -m unittest discover -s AGENT-ENGINEERING/SKILL-SYSTEM/tests -p 'test_delegate_skill.py' -v
bash -n AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/run-wave.sh
shellcheck AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/run-wave.sh
```

Wave tests run against both `/bin/bash` and the normally selected Bash, using a
fake sibling adapter for process control and fake `BASH_AGENTS_FILE` wrappers
for adapter compatibility. The AGY output suite separately requires local
`${BASH_AGENTS_FILE:-$HOME/.bash_agents}` for its synthetic wrapper-dispatch test.
No live workers or credentials are required for wave validation.
