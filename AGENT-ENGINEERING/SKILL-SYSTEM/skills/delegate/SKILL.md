---
name: delegate
description: "Coordinate bounded work across external model workers through the owner's shell launchers. Use only when the user explicitly invokes $delegate to assign work to Antigravity, Kimi Code, Devin, Codex, Claude, Grok, OpenCode, Command Code, or Pi. Do not use automatically, for trivial work, or merely to maximize model diversity."
disable-model-invocation: true
---

# Delegate

Turn an explicitly requested model mix into bounded worker assignments, let
authorized workers perform real work, and integrate their results into one
verified outcome. Diversity is a routing input, not a quota or a substitute for
judgment.

## Honor the invocation and authority

- Run this workflow only after the user explicitly names `$delegate` or asks to
  use the `delegate` skill. Never self-invoke it.
- Treat the user's requested models, wrappers, and rough proportions as the
  governing allocation. Proportions guide assignment of meaningful work units;
  they are not token quotas and do not justify artificial task splitting.
- After compaction or a restart, when the task's learning workspace records the
  owner's choices for it (launchers, second opinions, tracking), apply them
  without waiting for the owner to restate them. They bind that task only.
- If the user invokes the skill without a model mix, route tightly scoped
  through moderately-complex coding work (low, normal, and moderately
  complex) to Devin SWE-2 at `max` effort with `dswe`.
  Route ordinary exploration and summary work to `dswe`
  as well, except tasks needing a visual component or long
  context, which go to `aggb`. Reserve `cax` or `caxb` for highly complex
  coding tasks and difficult debugging. Use `cam` or `camb` (GPT-6 Astra
  at `max` effort) as an oracle-style consultant for second opinions and
  especially tricky debugging, rather than as a routine implementation worker.
  Claude Opus at `xhigh` (`ccx`/`ccbx`) and Claude Fable at `high`
  (`ccfh`/`ccbfh`) are expensive oracle-like alternatives. Call them sparingly
  for bounded, high-value questions, not routine implementation or broad fan-out.
- Do not add Kimi, Devin, Grok, OpenCode, or any other family merely to make the roster
  look diverse. Use them when the user requests them or gives routing guidance
  that includes them.
- Invocation does not broaden the original request. An analysis request keeps
  every worker read-only. An implementation request may authorize bounded
  edits, but not commits, pushes, branch changes, deployments, destructive
  operations, or unrelated external writes.

When the requested proportion cannot be represented by the available safe work
units, preserve the substantive priority and report the deviation. Do not
manufacture unsafe parallelism to satisfy a percentage exactly.

## Route by work, then by model

First identify work units with their own objective and evidence boundary. Only
then assign launchers.

| Family | Supported launcher names | Default role |
| --- | --- | --- |
| Antigravity | `agg`, `aggbs`, `aggb`, `aggbbs`; user-selected `agom` (Opus 5.5 medium), `argh` (Gemini 4 Argon high) | Primary choice (`aggb`) for exploration and summary tasks that need a visual component or long context; other exploration/summary work goes to `dswe`. Also basic implementation, mechanical changes, and other well-bounded work. Good as a quick parser of visual elements. Use `agom` and `argh` only when the user names them, for example as an independent panel or review voice. A plain name runs on whichever of the two accounts has more of its model's quota left; its `2` twin (`agg2`, `aggb2`, `agom2`, …) pins the second account, on the user's direction. |
| Kimi Code — K3.1 Pro | `kimm`, `kimb`, `kimbs` | User-requested implementation, analysis, or an independent approach. The runner removes prompt-mode trace and session output. Latency on the long side, so might take a while to respond. |
| Devin | `dswe` (primary), `dglm`, `dargh`, `dopmm`, `doph`, `dopx`, `dopm` | `dswe` (SWE-2 at `max` effort) is the primary choice for tightly scoped through normal and moderately-complex coding tasks, and for exploration and summary work that needs no visual component or long context. Keep concurrent `dswe` workers under 8 (10 is the hard ceiling). The other launchers (`dargh` is Gemini 4 Argon high) are user-selected Devin models for bounded implementation or review assignments. |
| Grok | `grokxh`, `grok` (primary) / `grok2xh`, `grok2` (secondary) / `grok3xh`, `grok3` (third) | User-requested implementation, adversarial review, or independent analysis. If directed to do so, route to the secondary or third account using its wrappers (`grok2xh`, `grok2` or `grok3xh`, `grok3`). The runner removes intermediate commentary and reasoning fields. |
| Codex — GPT-6 Luna `max` | `clm`, `clmb` | Basic work and clear-cut code implementations that benefit from a lightweight Codex worker. The runner maps `clm` and `clmb` to clean final-message modes. |
| Codex — GPT-6.1 Sol `xhigh` | `cdx`, `cdxb` | Complex reasoning, cross-file changes, integration, or critical review when a second Codex family is wanted. The runner maps `cdx` and `cdxb` to clean final-message modes. |
| Claude — Sonnet 5.5 | `csx`, `csbx` (xhigh); also `csmm`/`csbmm` (medium), `cshh`/`csbh` (high), `csm`/`csbm` (max), `csu`/`csbu` (ultracode) | Same capability tier as GPT-6.1 Sol (`cdx`): complex reasoning, cross-file changes, integration, or critical review, especially when a non-Codex family is wanted at that tier. Default to `csx`/`csbx`. The `csb*` variants use Claude Code safe mode (no inherited CLAUDE.md, hooks, plugins, MCP, or skills). The runner returns only Claude's final JSON `result`. |
| Claude — Haiku 5.5 | `chx`, `chbx` (xhigh); also `chmm`/`chbmm` (medium), `chh`/`chbh` (high), `chm`/`chbm` (max), `chu`/`chbu` (ultracode) | Roughly the GPT-6 Luna (`clm`) class: basic work and clear-cut code implementations that benefit from a lightweight worker — but better at visual design and weaker on very long contexts, so keep task context small-to-medium. Default to `chx`/`chbx`. The `chb*` variants use Claude Code safe mode, same as `csb*`. The runner returns only Claude's final JSON `result`. |
| Claude — Opus `xhigh` | `ccx`, `ccbx` (safe mode) | Expensive oracle-like consultant for high-value second opinions and especially tricky diagnosis. Call sparingly, not as a routine implementation worker. |
| Claude — Fable `high` | `ccfh`, `ccbfh` (safe mode) | Expensive oracle-like consultant with the same sparing consultation role as Opus. |
| Codex — GPT-6 Astra `medium` | `camm`, `cammb`| Moderately complex agentic work, reasoning, and cross-file changes, difficult diagnosis, integration, or critical review. |
| Codex — GPT-6 Astra `xhigh` | `cax`, `caxb`| Preferred choice for highly complex coding tasks and difficult debugging; also deep reasoning, integration, or critical review requiring judgement. Latency on the long side, so might take a while to respond. |
| Codex — GPT-6 Astra `max` | `cam`, `camb` | Oracle-style consultant for second opinions and especially tricky debugging. Give it a bounded question, relevant evidence, and prior attempts; ask for supported conclusions, competing hypotheses, and discriminating next checks. Default to read-only consultation, with the parent owning implementation and verification. |

For Claude oracle consultations, provide one unresolved question, relevant
evidence, and prior attempts; request supported conclusions, competing
hypotheses, and discriminating next checks. Default to read-only consultation,
with the parent owning implementation and verification. The `ccbx`/`ccbfh`
variants use the same Claude Code safe mode as the `csb*` launchers above.
Brief any oracle with [references/oracle-briefing.md](references/oracle-briefing.md).

Use a normal/scoped launcher when inherited user or project customization is
part of the intended context. Use a bare launcher when the task packet is
self-contained and independence from those customizations is valuable. Never
choose a bare mode that removes instructions or skills the worker actually
needs.

Do not claim a provider-specific strength that has not been established by the
task or the user's guidance. The table is a routing default, not a benchmark.

When more than one launcher would serve an assignment, let quota choose:
`scripts/pick-launcher RANK...` prints the one to run. Each argument is a
rank, best first, and commas join equals: `pick-launcher dopm,cmnh` lets quota
alone decide, and `pick-launcher cdm cdm2 argh` keeps that order. It covers
the Antigravity, Claude Code, Codex, Command Code, Devin, Grok, OpenCode and Pi
wrappers in `~/.bash_agents` (Pi's Go launchers spend the OpenCode Go quota).
A launcher qualifies when every quota window
that applies to it has at least 10% left (`--floor PERCENT`). The first rank
with a qualifying launcher wins. Within that rank it spends the subscription
credit that expires soonest, then free models, then pay-per-use launchers.
It never falls through to pay-per-use past a launcher whose quota it could not
read. Exit 1 means none qualifies; each candidate's reading and verdict go to
stderr. The pick is a snapshot. A plain Antigravity name it returns may still
move to its `2` twin at launch (see the adapter notes below).

### Explicit-user routes

These launchers are supported **only when the user explicitly requests them**.
Do not select or recommend them from skill guidance, including as automatic
fallbacks. Their presence in an allowlist is not a routing recommendation.

| Family / mode | Explicit-user launcher names | Contract |
| --- | --- | --- |
| Antigravity | `argm` (Gemini 4 Argon medium), `agoh` (Opus 5.5 high), `aghh`/`aghhb` (Gemini 4 Hydrogen high, normal/bare), `aghx`/`aghxb` (Gemini 4 Hydrogen xhigh, normal/bare), `agcm`/`agcmb` (Gemini 4 Carbon medium, normal/bare), `agch`/`agchb` (Gemini 4 Carbon high, normal/bare), `agnm`/`agnmb` (Gemini 4 Neon medium, normal/bare), `agnh`/`agnhb` (Gemini 4 Neon high, normal/bare), `agnx`/`agnxb` (Gemini 4 Neon xhigh, normal/bare); second account `argm2`, `agoh2`, `aghh2`/`aghhb2`, `aghx2`/`aghxb2`, `agcm2`/`agcmb2`, `agch2`/`agchb2`, `agnm2`/`agnmb2`, `agnh2`/`agnhb2`, `agnx2`/`agnxb2` | Same final-only headless boundary and account pick as the other Antigravity launchers. |
| Codex — GPT-6.1 Terra | `ctx`/`ctxb` (`xhigh`), `ctm`/`ctmb` (`max`); secondary account `ctx2`/`ctxb2`, `ctm2`/`ctmb2` | Scoped/bare variants using the final-only `-p` path, preserving the requested model, effort, and account. |
| Codex — GPT-6.1 Sol `max` | `cdm`, `cdmb`; secondary account `cdm2`, `cdmb2` | Scoped/bare variants; mapped to their matching final-only `*e` wrappers, preserving the requested account. |
| Codex — GPT-6 Astra `high` | `cah`, `cahb`; secondary account `cah2`, `cahb2` | Scoped/bare variants using the final-only `-p` path. |
| Codex — secondary account (`codex2`) | `clm2`/`clmb2` (Luna `max`), `cdx2`/`cdxb2` (Sol `xhigh`), `camm2`/`cammb2` (Astra `medium`), `cax2`/`caxb2` (Astra `xhigh`), `cam2`/`camb2` (Astra `max`) | Secondary-account (`~/.codex2`) twins of the default Codex routes; Luna/Sol map to `*e2` and Astra uses `-p` final-only capture. |
| Claude — Opus `max` | `ccm`, `ccbm` (safe mode) | JSON final-result extraction. |
| Claude — Opus `medium` | `ccmm` | JSON final-result extraction. |
| Claude — Fable `xhigh` | `ccfx`, `ccbfx` (safe mode) | JSON final-result extraction. |
| Claude subagent boost | `ccmM`, `ccxX` | Opus max/xhigh with built-in subagent boost; same JSON final-result extraction. |
| Claude — API key (`cck*`) | `cck` (default), Opus `cckm`/`cckbm` (`max`), `ccku`/`cckbu` (`ultracode`), `cckx`/`cckbx` (`xhigh`), `cckh`/`cckbh` (`high`), `cckmm`/`cckbmm` (`medium`); Fable `cckfm`/`cckbfm` (`max`), `cckfu`/`cckbfu` (`ultracode`), `cckfx`/`cckbfx` (`xhigh`), `cckfh`/`cckbfh` (`high`), `cckfmm`/`cckbfmm` (`medium`) | Explicit API-key auth (`ANTHROPIC_API_KEY` from `~/.env`; `cckb*` uses `--bare`); JSON final-result extraction. |
| Codex subagent boost | `cdmM`, `cdxX`, `camM`, `caxX`; secondary account `cdmM2`, `cdxX2`, `camM2`, `caxX2` | Sol/Astra max/xhigh with built-in subagent boost; `-p` preserves boost settings and account while returning only final text. |
| OpenCode — Muse Spark 1.3 Contributor `xhigh` | `ocs` (`opencode-go/muse-spark-1.3-contributor`, paid) | JSON final-message extraction; no automatic fallback to this model. |
| OpenCode | `ommp` (`opencode-go/mimo-v2.6-pro`) | JSON final-message extraction; no automatic fallback to this model. |
| OpenCode — Gemini 4 Argon `high` | `ocargh` (`opencode-go/gemini-4-argon`) | JSON final-message extraction; no automatic fallback to or from this model. |
| OpenCode — Go paid models | `ochy` (`opencode-go/hy4`, `high`), `ocq4h`/`ocq4x` (`opencode-go/qwen4-max`, `high`/`xhigh`) | JSON final-message extraction; spends OpenCode Go quota. No automatic fallback. |
| OpenCode — MiMo-V2.6-Flash Free | `ocmm26` (`opencode/mimo-v2.6-flash-free`, Zen) | JSON final-message extraction; the catalog exposes no adjustable reasoning level, so no effort variant is passed. No automatic fallback. |
| OpenCode — Go free / low-cost models | `ochy4flash` (`opencode-go/hy4-flash-free`, `high`, its highest effort; candidate cheap backup for `dswe` in market workflows), `oclongcat` (`opencode-go/longcat-2.5`; OpenCode Go deprecated `-free`), `ociceman` (`opencode-go/iceman-contributor-free`) | JSON final-message extraction; LongCat and Iceman expose no selectable variant, so none is passed. No automatic fallback. |
| Pi — Go free / low-cost models | `pihy4flash` (`opencode-go/hy4-flash-free`, `high`), `pilongcat` (`opencode-go/longcat-2.5`), `piiceman` (`opencode-go/iceman-contributor-free`) | Pi's text print mode returns only the final assistant text; no permission prompts by design. LongCat and Iceman pin no thinking level. They spend the OpenCode Go quota. No automatic fallback. |
| Command Code | `cmg` (GLM-5.3, max effort), `cmds` (DeepSeek V4.1 Flash, max effort), `cmm26p` (MiMo-V2.6-Pro, `xiaomi/mimo-v2.6-pro`, no adjustable effort), `cmqh`/`cmqx` (Qwen4 Max, `Qwen/Qwen4-Max`, `high`/`xhigh`), `cms` (Muse Spark 1.3 Contributor, `meta/muse-spark-1.3-contributor`, no adjustable effort), `cmhy` (Tencent Hy4, `tencent/hy4`, `high`) | JSON terminal-result extraction; YOLO wrappers with no permission prompts, for bounded tasks only. |
| Command Code — free models | `cmdglyph` (Glyph Cluster, `stealth/glyph-cluster:free`, `xhigh`, its highest effort — **reasoning-only, no web access**), `cmdflint` (Flint v1.0, `recursive/flint-v1.0:free`, no adjustable effort) | Same terminal-result extraction and YOLO boundary as the other Command Code wrappers. Do not route web-lookup tasks to `cmdglyph`. |
| Command Code — an exact model | `cmd:<native-id>`, for a model the user named that `am cmd` lists (for example `cmd:deepseek/deepseek-v4.1-flash`) | `am` resolves and revalidates it before launch, at the model's default effort; a model no longer listed fails with `am: no matching live models` and never becomes another model. Same terminal-result extraction; prefer a named wrapper when one exists. |

`cmm26p`, `cms`, and `cmdflint` omit `--effort`: their models expose no selectable reasoning levels.

Choosing a boost wrapper explicitly permits its built-in fan-out within the
assigned scope, not unrelated delegation. The parent still owns scope,
integration and verification; `--jobs` counts outer workers, not their internal
subagents. Do not select boost wrappers merely because a task is difficult.
Launcher names are case-sensitive. Only the Codex and Antigravity routes above
have `2` twins; do not invent Claude secondary-account names.
Interactive resume (`cdxr`/`cdxr2`) and Antigravity Teamwork Preview
(`aggtp`/`aggbtp`) remain outside the adapter.

## Establish ownership before launching

Inspect the current workspace and version-control state. Preserve all
pre-existing changes, including untracked files.

For each assignment, record:

- the launcher and approximate share it serves;
- `read`, `write`, or `verify` authority;
- the exact owned files or another concrete scope boundary;
- dependencies on other assignments;
- the expected evidence and return contract.

Parallel readers are safe when they are independent. Parallel writers are safe
only when their owned paths and generated artifacts are disjoint and neither
depends on unreturned work. Treat shared configuration, manifests, schemas,
lockfiles, generated outputs, migrations, and broad formatting as overlapping
ownership even when the nominal source files differ.

Maintain one active writer per owned file. While a worker owns a write scope,
the parent and other workers must not edit it. Serialize overlapping work, or
make one assignment read-only. Do not let a reviewer inspect a half-written
state when its verdict depends on the completed implementation.

## Write self-contained task packets

Give each worker only the context needed for its assignment:

```text
ROLE: implement | analyze | review | verify
OBJECTIVE: one observable outcome
WORKSPACE: absolute project path
SCOPE: exact owned files, symbols, or read-only surface
CONTEXT: relevant facts, errors, decisions, and dependencies
CONSTRAINTS: preserved behavior, explicit non-goals, and authority limits
VERIFY: exact checks or evidence expected
RETURN: required status and evidence fields
```

For a writer, require these return fields:

```text
STATUS: done | blocked
CHANGED: files changed and why
VERIFICATION: commands and results
BLOCKERS: unresolved issues or none
```

For a reader or verifier, require `STATUS`, `FINDINGS`, `EVIDENCE`, and
`BLOCKERS` instead.

Every packet must tell the worker to preserve unrelated changes and not to
commit, push, switch branches, alter workspace configuration, or delegate
again unless the user explicitly authorized that action. Do not forward the
whole conversation, secrets, credentials, or unrelated private context.

When `CONTEXT` would need long earlier discussion or output, pass `hist`
references (for example `myrepo:12345`) and tell the worker to run
`hist zoom <ref>`, instead of pasting the text.

When research feeds a later decision, keep the desired change out of the
researcher's packet: ask neutral questions about the current state, with exact
pointers (paths, symbols, `hist` refs), so the findings are not bent toward it.

## Run workers through the adapter

Use `scripts/run-worker.sh` from this skill rather than calling a prompt-mode
wrapper directly. It sources `${BASH_AGENTS_FILE:-$HOME/.bash_agents}` and
accepts the task on standard input or through `--task-file`. Run from a Codex
or Claude Code session, it ends each task with a
`[hist-parent <host>:<session id>]` line, so `hist` links the worker to that
session on every host.

```bash
DELEGATE_RUNNER="$HOME/.agents/skills/delegate/scripts/run-worker.sh"
"$DELEGATE_RUNNER" aggb <<'DELEGATE_TASK'
ROLE: implement
OBJECTIVE: Add the agreed parser boundary.
WORKSPACE: /absolute/path/to/project
SCOPE: src/parser.py and tests/test_parser.py only
CONTEXT: The accepted contract and relevant failure evidence go here.
CONSTRAINTS: Preserve unrelated changes. Do not commit, push, or edit other files.
VERIFY: Run the focused parser tests.
RETURN: STATUS, CHANGED, VERIFICATION, BLOCKERS.
DELEGATE_TASK
```

The adapter deliberately allowlists known launchers. For successful calls it
prints only the worker's final response:

- Kimi runs in `stream-json` mode and returns the last non-empty assistant
  content, excluding tool calls, reasoning traces, version text, and resume
  hints.
- Grok runs in JSON mode and returns only its `text` field, excluding `thought`
  and usage metadata.
- OpenCode (`ocs`, `ommp`, `ocargh`, `ochy`, `ocq4h`, `ocq4x`, `ocmm26`, `ochy4flash`, `oclongcat`, `ociceman`) runs in JSON
  mode (`run --format json`) and returns the final assistant message content,
  excluding intermediate tool calls and step commentary. Missing wrappers and
  failed runs fail without switching models or providers.
- Pi (`pihy4flash`, `pilongcat`, `piiceman`) runs with `-p`; its text print mode
  writes only the last assistant message's text, which the adapter passes
  through after an empty-response check. Pi has no permission prompts by design.
- Command Code (`cmg`, `cmds`, `cmm26p`, `cmqh`, `cmqx`, `cms`, `cmhy`, `cmdglyph`, `cmdflint`, and `cmd:<native-id>` through `am`) runs with `--no-auto-update --output-format json -p`.
  Only a terminal `type: result`, `subtype: success` record with nonempty
  `finalText` is returned; event commentary, tool output, errors, turn-limit
  results and malformed streams cannot become successful stdout. The installed
  Command Code 1.84.0 contract was verified with a real tool-using headless run;
  this is not an unverified plain-text passthrough. The adapter ends every
  Command Code task with "Delivery: never send a progress note as a message;
  your final message holds the complete answer.", since a run that ends on a
  narration message returns no answer.
- `cdx`, `cdxb`, `cdm`, and `cdmb` are translated to `cdxe`, `cdxbe`, `cdme`, and
  `cdmbe`, respectively, so the caller receives Codex's final message rather than
  its event stream.
- `cdx2`, `cdxb2`, `cdm2`, and `cdmb2` map to `cdxe2`, `cdxbe2`, `cdme2`, and
  `cdmbe2`, respectively, preserving the secondary account; these final aliases are
  also accepted directly.
- `clm` and `clmb` (and secondary-account `clm2` and `clmb2`) are translated to
  `clme` and `clmbe` (`clme2` and `clmbe2`), respectively, keeping GPT-6 Luna at
  `max` effort while returning only its final message; these final aliases are also
  accepted directly.
- Terra launchers (`ctx`/`ctxb` at `xhigh`, `ctm`/`ctmb` at `max`) and their
  secondary-account `2` twins use their stream wrappers' `-p` headless path,
  keeping GPT-6.1 Terra and the requested effort, home mode, and account.
- Astra launchers (`cam`, `camb`, `cax`, `caxb`, `camm`, `cammb`, `cah`, `cahb`,
  and their secondary-account `2` twins `cam2`, `camb2`, `cax2`, `caxb2`, `camm2`,
  `cammb2`, `cah2`, `cahb2`) and Codex boost launchers use their stream wrappers' `-p`
  headless path, which reroutes to the same cdxe-style final-only capture without
  dropping model, account or boost options.
- Claude Sonnet (`cs*`), Haiku (`ch*`), and the listed Opus/Fable launchers
  (including the explicit-user effort, boost, and `cck*` API-key variants) run with
  `--output-format json` and return only the
  final `result` text; a result marked `is_error` fails with diagnostics on
  stderr.
- Antigravity (`agg`/`aggbs`/`aggb`/`aggbbs`/`agom`/`agoh`/`argm`/`argh`/`aghh`/`aghhb`/`aghx`/`aghxb`/`agcm`/`agcmb`/`agch`/`agchb`/`agnm`/`agnmb`/`agnh`/`agnhb`/`agnx`/`agnxb`) uses the launchers' final-only headless path in
  `~/.bash_agents`, backed by `scripts/agy-final-output.py` (Python 3 required).
  Native AGY text **and JSON `response`** concatenate intermediate commentary
  with the final answer; neither is a final-message boundary. The helper requests
  `stream-json`, reconstructs the terminal completed `agent_response` step from
  its text deltas, and returns it only after a successful result and process exit.
  Tool events, earlier responses and partial answers are discarded. Malformed,
  incomplete or unrecognized streams fail with stderr diagnostics, never a raw
  transcript fallback. The adapter also suppresses AGY stdout on failure.
  This applies to `-p`, `--print`, `--prompt`, their `=value` and single-dash
  long-option forms, and `--input-format stream-json`. Default output is final
  text; explicit `json` keeps the result object with its response replaced; explicit
  `stream-json` emits only final result events. Interactive launcher arguments
  pass through unchanged. Keep the helper installed with the shell definitions.
- A plain Antigravity name runs on whichever signed-in account has more of its
  model group's quota left (`scripts/agy-account.py`, from AGY's `/usage`; a
  reading serves launches for 3 minutes, so a wave pays the ~4 s check once).
  The `2` twins (`agg2`/`aggbs2`/`aggb2`/`aggbbs2`/`agom2`/`agoh2`/`argm2`/`argh2`/`aghh2`/`aghhb2`/`aghx2`/`aghxb2`/`agcm2`/`agcmb2`/`agch2`/`agchb2`/`agnm2`/`agnmb2`/`agnh2`/`agnhb2`/`agnx2`/`agnxb2`)
  pin the second account (`~/.agy2`). A picked run that fails while a fresh
  reading shows its account's group spent moves once to the other account; with
  the group spent on every account it fails `rate-limited`, which bars only its
  launcher because AGY meters each model group apart.
- Devin print mode concatenates progress and final text. After a zero exit,
  `scripts/devin-final-output.py` reads the new local session's committed
  `main_chain_id` head from `~/.local/share/devin/cli/sessions.db` (read-only),
  matched by launch clock, physical working directory and exact task. The
  adapter appends a unique `Delegate task id:` line to each Devin task, so
  concurrent workers with the same task (waves, judges) stay distinct. Only a
  nonempty terminal assistant message matching stdout's suffix is returned;
  earlier narration stays on stderr. Missing/ambiguous sessions, schema drift,
  nonterminal heads and mismatched output fail closed. This is the verified
  local Devin boundary, not an OpenCode event parser or cloud-output adapter.

Do not bypass the adapter because a direct probe happened to look clean; tool-
using turns can emit intermediate commentary that simple turns do not.

When a launched run fails, the adapter's last stderr line is its failure class:
`delegate worker: failure class: rate-limited: <reason>` (a rate limit or
quota), `quarantined: <reason>` (an expired key, a missing credential, a
signed-out CLI, an ended plan, a retired model or another non-retryable refusal)
or `unclassified`, which may be the task's own failure. Only the CLI's own error
records count: an empty answer whose transcript merely quotes a quota message
stays `unclassified`, and a record only one harness writes counts only from that
harness's launchers. A rate-limited or quarantined launcher is unavailable for
the rest of the pass (see [stop conditions](#stop-conditions)). A
`rate-limited: account quota exhausted on <harness>` failure makes every
launcher on that account unavailable (one row of `scripts/launcher-routes.tsv`;
a secondary account such as `codex2` is a separate row).

After a launcher or configuration change, `scripts/probe-launcher NAME` runs one
read-only task through this adapter that a worker can answer only with a real
tool call, and reports the launch, the failure class, the extracted final
message, any model the CLI's JSON names and the `hist` parent link. Run it by
hand on the changed route; it gates no wave.

Regression checks for the Antigravity output contract (synthetic event streams,
launcher dispatch and adapter failure handling; no model calls):

```bash
python3 -B -m unittest discover -s "$HOME/.agents/skills/delegate/tests" -v
```

**Optional wave runner:** When a shared-context wave is specifically called for,
read [references/wave-runner.md](references/wave-runner.md) before preparing or
running it. Ordinary single-worker or separately supervised adapter calls need
only the instructions here. Existing authority, ownership, and integration
rules still apply.

## Execute and supervise the wave

Launch independent assignments concurrently only when the host can supervise
each process and the ownership test above passes. Otherwise run them in
dependency order. The user asked for useful delegation, not maximum process
count. Keep concurrent `dswe` workers under 8 — never 10 or more — even when
the wave job cap would allow a larger batch.

For each completed or failed call:

1. Record its exit status and final response.
2. Inspect the actual workspace state; a summary is not proof of what changed.
3. On timeout or transport failure, assume the worker may have started writing.
   Check the process and workspace before retrying or reassigning its scope.
4. Do not automatically continue an incomplete response with an open-ended
   prompt. Issue a narrow follow-up only when a specific missing fact blocks
   integration.
5. If a worker reports `blocked`, preserve its evidence and re-route only after
   resolving the cause or deliberately changing the assignment.

Worker outputs are evidence, not authority. Resolve disagreements against the
accepted task, repository state, tests, and primary sources. Reject or repair a
worker's contribution when the evidence does not support it.

## Integrate and verify

After all writer scopes settle:

1. Compare the complete version-control state with the preflight state.
2. Inspect every changed file and confirm ownership boundaries were respected.
3. Reconcile interfaces and assumptions across worker contributions.
4. Run focused checks for each assignment, then one appropriate integrated
   check over the combined result.
5. Account for every worker that finished: used (where), excluded (why), or
   still pending. A result that arrives late, even past its time cap, is still
   considered.
6. Verify independently rather than trusting worker-reported success.
   `hist sessions --workers` lists the workers, and `hist read <alias> --tail 20`
   shows the end of the transcript behind a final report; Kimi and Grok workers
   are not recorded yet. To check a consequential claim, search the worker's
   session in the words its tools print, not the words of its report
   (`hist find "pass" --session <alias> --kind result`). Read a transcript once
   the worker has finished; polling a running worker through `hist` spends
   context and shows little.

When the user authorizes repeated review → fix → re-review rounds, read
[references/review-correction-loop.md](references/review-correction-loop.md)
before the first round.

Give each review worker exactly one outcome:

- `folded`: its review was read into yours. This says nothing about its
  advice; record what was done with each of its findings separately.
- `not-run`: positive evidence that it never started (not launched, or refused
  before any work, such as a quota refusal).
- `failed`: it started and ended without a result (a non-zero exit, a timeout).
- `no-usable-output`: it finished, but its output was empty, off target, or
  unverifiable.

For each review that did not fold, say whether you covered its lane yourself
(`in-process-fallback`) or the lane stays uncovered. When a review's coverage
receipt leaves changed paths unreviewed, the follow-up reviews only those
paths, bound to the same base and head object IDs and the same review
configuration. Re-resolve the target first; if any of them changed, refuse the
follow-up and say the new target needs a full review.

Report the model allocation actually used, the meaningful work each worker
owned, any requested-proportion deviation, the integrated result, verification
evidence, and remaining risk. Keep launcher traces and private task packets out
of the user-facing answer unless they explain a failure.

## Stop conditions

Stop and return control rather than guessing when:

- the requested launcher or its underlying CLI is unavailable or unauthenticated;
- safe ownership boundaries cannot be formed for requested parallel writers;
- the user-requested allocation conflicts with a higher-priority authority or
  safety constraint;
- a worker may still be running after a timeout;
- integration requires an action outside the user's original authorization.
