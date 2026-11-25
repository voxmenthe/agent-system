# Shell layer

Edit bash/git helper sources here. Normal shells do **not** load this tree
directly — they load the home projection under `~`.

## Why two locations

| Role | Path |
|---|---|
| Source of truth (edit here) | `SHELL/` |
| Home projection (runtime) | `~/.git-helpers/`, `~/.bash_git_helpers`, and the other `~/.bash*` files |
| Loader | `~/.bashrc` sources `~/.bash_git_helpers` |

`~/.bash_git_helpers` prefers a repo-local `git-helpers/` next to itself, and
otherwise falls back to `~/.git-helpers`. Interactive shells therefore use the
home copy unless you are inside a checkout that still has the sibling tree.

Edits under `SHELL/` do **not** take effect until `guidance sync` projects
them home. The shell layer is the `shell` host of the
[guidance manager](../AGENT-ENGINEERING/PERSISTENT-GUIDANCE/README.md): the six
dotfiles, `git-helpers/` (without its tests) into `~/.git-helpers/`, and five
helpers into `~/.local/bin`, which are installed executable when their source is.
They form one sync group, so they always change together, with backups and
`./guidance rollback`. A projected file you edit in place, or an installer
appends to, blocks that group until you resolve it (see below).

Nothing machine-specific belongs in these files. `~/.bash_profile` sources
`~/.config/agent-system/shell.local.sh` before its defaults; put cache
locations, extra PATH entries and `TRAVEL_MODE_SH` there
([example](shell.local.example.sh)). `@HOME@` in a source becomes the home
directory on sync, which keeps installer-written lines such as
`export PATH="@HOME@/.kimi-code/bin:$PATH"` byte-identical to what the
installer looks for.

When an installer appends a PATH line to a projected dotfile, sync reports a
conflict for that file. Either adopt it (`./guidance adopt --only shell-bashrc`,
which writes `@HOME@` for the home path; then commit), or move the line into
`shell.local.sh`, delete the dotfile, and run `./guidance sync` to restore it.

## Live agent model picker: `am`

```bash
am                         # Live free/deal/new/stealth shortlist → choose → native CLI
am cmd --kind deal --list   # Full descriptions, prices, conditions and other metadata
am oc --all                # Browse Zen and Go, never OpenRouter or other BYOK providers
am devin gemini --list      # Search the full scoped catalog, not just the shortlist
am --all --json             # Catalog plus source status; no session or inference
am 'cmd:stealth/cat-jam:free' -- -p 'Explain this function'
```

Exact keys are `cmd:native-id`, `oc:provider/model`, or `devin:model_uid`.
IDs shown here are examples, not maintained defaults. Search text always opens
a chooser; only an exact key skips selection. `--kind free|deal|stealth|new|all`
sets an explicit constraint, including on exact keys. `--all` means all model
categories within the supported CLI/provider scope, never all OpenCode providers.

`--list` prints complete detail blocks without width-based truncation: native
descriptions, exact IDs, prices/cache/context tiers, context/output limits,
efforts, modalities, plan requirements, capacity notices, offer conditions and
newness evidence where published. `fzf` uses top-aligned columns for CLI, model,
badges and price/offer, with a sectioned detail preview. `ZEN` and `GO` distinguish
the OpenCode routes. Narrow terminals put the preview below the list. **Tab**
toggles it, **Ctrl-F** expands/restores it, and **Shift-Up/Down** scrolls it.
Descriptions and exact keys remain searchable. `NO_COLOR` disables color;
`--list` is always plain text, and `--json` retains the complete structured data.
Without `fzf`, a numbered terminal chooser is used. Both preserve piped stdin for
the agent. Escape/Ctrl-C cancels without launching.

`--effort VALUE` pins only an advertised Command Code effort or OpenCode variant;
omitting it leaves the native default unpinned. Devin effort is part of its exact
UID. Native launch arguments follow `--`. Model/effort overrides, resume/session,
remote/cloud and alternate-config switches are rejected: this is a new-session,
current-directory picker. Existing wrappers and native CLIs remain available.
For Command Code/Devin prompts beginning with a flag, use `--print=--literal`;
their optional `-p` prompt must not hide a subsequent native option.

Catalogs and official offer pages are fetched on demand and the selected route
is checked again before launch. No alternative model/provider is substituted.
Listings may return valid partial data with exit status 1 when a source is
unavailable or reduced. JSON always uses a `schema_version`, `sources`,
`local_new_status`, and `models` envelope; diagnostics do not contaminate it.
Catalog presence is not proof of account entitlement. Go is subscription-backed,
not a free offer merely because a marginal rate is zero. Advertised discounts and
usage boosts retain their conditions; they are not an account billing estimate.
Devin retains native free/new labels and current account price summaries. Its
native cost tier is a secondary category, not a statement about discounts.
Promotion annotations come from the versioned
[`agent_model_offers.json`](agent_model_offers.json) fallback described below;
they are manually reviewed, not automatically discovered or account-verified.
Missing annotations do not mean that no promotion exists.

The only runtime-written picker data is a disposable, locked/atomic first-seen baseline
at `${XDG_STATE_HOME:-~/.local/state}/agent-models/first-seen.json`, scoped by
CLI/profile paths and project. It holds identities/timestamps, not prices,
quotas, credentials or prompts. The first catalog establishes a baseline rather
than labeling everything new. Local observations and provider release/new flags
are distinguished; the recent window is seven days. Corruption disables only
local-new evidence and is reported; deleting the baseline rebuilds it.

### Maintaining promotion annotations

For Devin, update `agent_model_offers.json` and install it beside the helper.
No model-specific wrapper or Python change is needed. Each version-1 record has:

| Field | Meaning |
|---|---|
| `id` | Unique promotion identifier, not a model ID. |
| `models` | Exact case-sensitive `CLI:native-id` keys. Only existing live models can be annotated. |
| `discounts` | Map of eligible billing-plan labels to advertised percentages; never an account billing quote. |
| `starts`, `through` | Inclusive UTC calendar dates (`YYYY-MM-DD`). Expired/future records do not qualify; overlapping active records for a key are rejected. |
| `source`, `checked_at` | Official HTTPS evidence link and the date a maintainer reviewed it, not a live promotion check. |
| `condition` | Eligibility, exclusions and other important provider terms. |

The bundled records cover the Argon launch/introductory transition, the SWE-2
ACU discount, and the Gemini 3.7/3.8 Flash introductory pricing. Dates are evaluated
on every fetch, including immediately before launch. An end date is not proof of
the provider's exact cutoff time; live native rates remain authoritative.
Annotations never change those rates, native free evidence, model availability,
provider selection or launch arguments. Unknown IDs are not added to the catalog.
The picker shows native prices first, with plan-dependent discounts alongside;
the preview retains the eligible plans, source, review date and exclusions.

Missing/malformed files make promotion coverage explicitly unavailable while
preserving the live catalog. `--kind deal` cannot launch without valid current
evidence. An empty valid file means manual coverage, not exhaustive discovery.
Command Code and OpenCode continue using their existing live offer adapters.

### Install or update

Requires Python **3.12+**, Bash, `jq`, and the native CLIs you use; `fzf` is optional.
From `SHELL/`, project the helpers and `.bash_agents`, then reload:

```bash
cd ../AGENT-ENGINEERING/PERSISTENT-GUIDANCE
./guidance sync --dry-run   # preview
./guidance sync
```

Then `source ~/.bash_agents`.

Ensure `~/.local/bin` is on PATH and `python3 --version` is 3.12 or newer.
`AGENT_MODELS_HELPER` can select a different helper copy. Both companion modules
and the offers JSON file must remain beside it. Neither discovery nor the new OpenCode launch path pins
shared model defaults: headless launches pass an explicit model, and the full
TUI opens an explicitly created, model-bound session. Native CLIs may still
maintain their own recent-model/session bookkeeping.

Focused offline checks, from the repository root:

```bash
uv run --no-project python -m unittest discover -s SHELL/tests -p test_agent_models.py -v
uv run --no-project python -m unittest discover -s SHELL/tests -p test_final_output.py -v
uv run --no-project python -m unittest discover -s SHELL/tests -p test_agents.py -v
```

The design and implementation evidence
records the source contracts and live checks.

## Propagate after changing helpers

From this folder:

```bash
cd ../AGENT-ENGINEERING/PERSISTENT-GUIDANCE
./guidance sync --dry-run   # preview
./guidance sync
```

Then open a new shell (or `source ~/.bashrc`) so the functions reload.

## Claude subscription wrappers

`claude` uses the native Anthropic login. The old Kimi aliases and profile
injection are commented out. The Kimi profile is retained as commented JSON in
`~/.claude/kimi-oauth-settings.disabled.jsonc`; `kimi-oauth-settings.json` is an
empty object so old launch commands cannot accidentally reactivate it.

| Model | Effort | Normal | Bare subscription |
|---|---|---|---|
| Opus | high | `cch` | `ccbh` |
| Opus | xhigh | `ccx` | `ccbx` |
| Opus | max | `ccm` | `ccbm` |
| Fable | medium | `ccfmm` | `ccbfmm` |
| Fable | high | `ccfh` | `ccbfh` |
| Fable | xhigh | `ccfx` | `ccbfx` |
| Fable | max | `ccfm` | `ccbfm` |
| Sonnet | medium | `csmm` | `csbmm` |
| Sonnet | high | `cshh` | `csbh` |
| Sonnet | xhigh | `csx` | `csbx` |
| Sonnet | max | `csm` | `csbm` |

`ccxX` and `ccmM` add a per-launch parallel boost to `ccx` and `ccm`: 16
concurrent subagents, maximum depth 2, tool-use concurrency 16, and workflow
agent concurrency 18. They pass a `--settings` JSON overlay, leaving the managed
settings file and ordinary wrappers unchanged. Subagents inherit the session's
`xhigh` or `max` effort unless their definition overrides it. These names are
case-sensitive and have no additional bare variants.

Sonnet high is `cshh` because `csh` is the system C shell (`/bin/csh`).
`csu`/`csbu` run Sonnet at ultracode.
Sonnet wrappers pin `claude-sonnet-5-5[1m]`. `~/.claude/settings.json` sends
subagents to Opus through `CLAUDE_CODE_SUBAGENT_MODEL`, and an explicit `sonnet`
request still reaches Sonnet.

Subscription wrappers use the current `opus[1m]` and `fable[1m]` model aliases
for the 1M context window and the existing `--dangerously-skip-permissions`
behavior. They clear inherited Kimi
endpoint/model overrides and let `--effort` select the requested reasoning level.
Bare subscription wrappers use `--safe-mode`, which disables customizations
while retaining subscription login. Native `--bare` skips OAuth/keychain auth.
Existing `cck*` wrappers still explicitly select API-key authentication, and
passing `--api-key` or `-ak` switches any Claude wrapper (including Sonnet,
Haiku, and `ccxX`/`ccmM`) to API-key auth. `_cc_launch` reads
`ANTHROPIC_API_KEY` from `~/.env` (`CLAUDE_ENV_FILE` overrides) via an inline
`apiKeyHelper` (keeping `ANTHROPIC_API_KEY` unset in Claude's process
environment and out of CLI `argv`), fails with exit `2` if no key is found,
merges any `--settings` overlays via `jq`, and upgrades `--safe-mode` to
`--bare`.

Passing `--code-mode` before `--` opts any subscription wrapper (including
`ccxX`/`ccmM` and `--safe-mode` bare variants) into a Chrome-less Code Mode
session: `_cc_launch` passes `--no-chrome`, swaps
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` for `DISABLE_AUTOUPDATER=1`,
`DISABLE_ERROR_REPORTING=1`, and `DISABLE_FEEDBACK_COMMAND=1`, sets
`CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1`, and overrides
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` to `""` in a merged `--settings`
overlay. `--code-mode` rejects `--api-key`/`-ak` (`cck*`) and `--chrome`.
For a one-off advisor model without modifying managed settings, pass
`--advisor <model>` at launch rather than `/advisor` inside a session.

After copying `.bash_agents` and `.bash_aliases` home, reload both:

```bash
source ~/.bash_aliases
source ~/.bash_agents
```

## Kimi Code wrappers

The wrappers inherit the K3.1 Pro model default from the managed
[Kimi config](../AGENT-ENGINEERING/PERSISTENT-GUIDANCE/config/kimi/config.toml).
`kimm`, `kimb`, and `kimbs` select max effort; `kimh` selects high and `kiml`
selects low. The bare variants retain that model default while omitting user
customizations. Normal launchers still accept native `-m`/`--model` overrides.
Start a new session to use the corrected default; existing sessions retain
their selected model.

## Antigravity second account

Every Antigravity wrapper has a `2` twin (`agg2`, `aggbs2`, `aggtp2`, `aggb2`,
`aggbbs2`, `aggbtp2`, `agom2`, `agoh2`, `argm2`, `argh2`, `aghh2`, `aghhb2`,
`aghx2`, `aghxb2`, `agcm2`, `agcmb2`, `agch2`, `agchb2`, `agnm2`, `agnmb2`,
`agnh2`, `agnhb2`, `agnx2`, `agnxb2`) that runs `agy` with `HOME=~/.agy2` (`AGY2_HOME` overrides). `agy` has no home variable: its login
lives in the macOS login keychain and `~/.gemini/antigravity-cli`, and another
HOME hides the keychain, so the second login is stored under
`~/.agy2/.gemini/antigravity-cli`. Every second-account run (the twins, `usage`
and the delegate's account picker) also sets a stand-in `SSH_CONNECTION` unless
a real one exists: in an SSH session `agy` keeps its tokens in that file without
trying the keychain, which would otherwise raise macOS's "Keychain Not Found"
dialog at each hourly token refresh. Run `agg2` once in a terminal to log in;
until then headless twins refuse to start rather than open a browser login.

Configuration is shared: `~/.agy2/.gemini/config` links to `~/.gemini/config`,
and PERSISTENT-GUIDANCE projects `GEMINI.md` and `antigravity-cli/settings.json`
for both accounts, leaving each its own trust list and permission allowlist.
Commands the agent runs get the real HOME back through
`~/.agy2/.zdotdir/.zshenv`, so git, `gh` and skills behave as on the primary
account. At the terminal a plain name is always the primary account; the
delegate runner (`mkt delegate`, delegate waves) picks whichever account has
more of the model's quota left.

## Antigravity API-key fallback (`GEMINI_API_KEY`)

Use `agk` (prefix or standalone; defaults to `aghh`) or pass `--api-key` /
`-ak` to any Gemini wrapper to run `agy` against the Gemini Developer API via
`--settings '{"modelProvider":"gemini"}'` and `GEMINI_API_KEY`:

```bash
agk                       # Same as `agk aghh` (gemini-4-hydrogen-high)
agk -p "fix the tests"    # Headless final-only on GEMINI_API_KEY
agk aghxb -p "audit diff" # Prefix any Gemini wrapper (including bare/boost/tp)
aghx --api-key -p "task"  # Composable flag anywhere before `--`
argm -ak                  # Short flag
```

If `GEMINI_API_KEY` is unset (for example, in non-login shells that never sourced
`~/.bash_profile`), `_agy_launch` falls back to reading `GEMINI_API_KEY` from
`~/.env` (`AGY_ENV_FILE` overrides) in an isolated subshell without leaking
other variables, and fails loudly if no key is found. Caller `--settings`
overlays are merged via `jq` so `modelProvider: "gemini"` is preserved,
`GOOGLE_GEMINI_BASE_URL` is cleared unless `AGY_KEEP_BASE_URL=1`, and `agom`,
`agoh`, and `*2` twins are rejected with exit `2`.

## Final-only headless output

Plain-text headless runs buffer stdout and print only the final answer:

| Wrappers | Headless invocation | Native structured-output opt-out |
|---|---|---|
| All Antigravity wrappers, including `agoh` | `-p "task"` | JSON modes are also filtered to final results |
| `kimm`, `kimh`, `kiml`, `kimb`, `kimbs` | `-p "task"` | `--output-format stream-json` |
| `grokxh`, `grok2`, `grok2xh`, `grok3`, `grok3xh` | `-p "task"` or `--single "task"` | `--output-format json` or a streaming format |
| All OpenCode wrappers | `-p "task"` or `run "task"` | `--format json` |

Interactive launches are unchanged. Kimi, Grok, and OpenCode filtering requires
`jq`; diagnostics stay on stderr, and failed or unparseable runs return nonzero
without replaying partial stdout. Explicit structured formats stay native for
consumers such as `delegate`. Plain `grok` is still the raw CLI, not a wrapper.
Devin remains native; reliable final extraction needs session-database lookup.
If OpenCode omits its terminal event, plain output requires a successful native
session-completion readback as well as completed text; raw JSON is unchanged.
Codex's existing final-only capture and the Claude, Command Code, and Pi wrappers
are unchanged.

## Usage dashboard

Run `usage` to query all providers concurrently, or select harnesses with `-a`:

```bash
usage -a claude
usage -a claude, codex, devin
```

The comma-separated list does not need quotes; compact and quoted lists also
work. Filtering happens **before** workers launch: only selected harnesses are
queried and shown, including in the expiration and banked-reset summaries.
Duplicate names run once; unknown or empty names are rejected before any query.
Names: `claude`, `codex`, `antigravity`, `devin`, `grok`, `kimi`, `cmd`, `amp`,
`opencode`, `typesafe`. `cmd` means Command Code, and `opencode` means
OpenCode Go. Codex selections include both configured accounts; Grok selections
include `~/.grok` plus `~/.grok2` and `~/.grok3` once each holds a login;
Antigravity selections add `~/.agy2` once it holds a login, both queried at once.

For Command Code, `cmd whoami` checks the key online; `cmd status` can report a
saved key as authenticated even when the API rejects it. After an HTTP 401,
run `cmd logout` then `cmd login`, and verify `cmd whoami` and `usage -a cmd`.
If `COMMAND_CODE_API_KEY` is set, update or unset it instead: it overrides the
saved login.

OpenCode Go uses `OPENCODE_API_KEY` when set, matching native Console auth;
otherwise it uses the active account returned by `opencode auth export opencode-go`
(OpenCode v2), not the legacy `auth.json` migration file. The background server
can retain an environment key absent from the current shell, so working model
requests do not prove the saved key is valid. Reuse a valid existing key before
creating another. Install it through `/connect` or
`opencode auth login opencode-go --method key`, then verify both a native model
request and `usage -a opencode`.

Each completed provider
section prints immediately; section order depends on response times. The ranked
expiration summary prints last, after all providers finish, so the slowest
provider sets the total runtime. A failed provider still gets a section and
makes the final exit status nonzero.

Every run queries the selected providers for current usage. Quota percentages,
banked resets, pacing, and rankings never come from a previous run's snapshot.
If a refresh fails, times out, or is blocked by a provider cooldown, that
provider shows **unavailable** instead of old numbers. Upstream reporting can
still lag actual consumption.

The summary ranks included windows by reset time, shortest first: Claude's and
both Codex accounts' five-hour windows and Devin's daily windows therefore lead
the weekly and monthly ones. Codex Spark's separate pool stays in the provider
section only.
A provider that ranks some windows can still report a gap, such as a weekly
window with no scheduled reset, under "Windows without expiration data".

"Banked resets (manual use)" lists each account with unused reset credits,
their count, and the soonest upcoming credit expiry in Pacific time, with an
hours-and-minutes countdown. These are separate from automatic quota resets;
`usage` never redeems them. Missing credit expiry details are marked unavailable.
Claude's grant lookup uses the installed CLI's read-only usage endpoint with
`cedar_ember=1&skip_spend=1` and its user-agent; this is not a documented public
API. Only grants returned by the current request appear in the summary.

`usage -a claude` also reads **Console API promotional credits**, separately
from subscription limits and banked resets. Each active API-eligible grant
shows its remaining/original dollar amount, Pacific expiration date, and time
left in the summary. Expired grants are excluded; exhausted grants show $0.
Purchased credits are not included. Product restrictions are respected; model
restrictions, if any, can be checked on the Console Billing page. Missing or
unreadable data is marked unavailable, never inferred from the plan price.

The Console requires its own login, not Claude Code's subscription OAuth token.
To connect it once:

1. Open [Console Billing](https://platform.claude.com/settings/billing) and
   select the organization receiving your monthly credits.
2. In browser DevTools → Network, reload, select the request ending in
   `/prepaid/credits`, and copy its **Cookie request header value**.
3. Run `claude-console-login` in a terminal (reads the clipboard), then
   `usage -a claude`. For piped input, the command accepts either the raw value
   or a `Cookie:` header line. Do not paste the session into chat or a command
   argument.

The imported cookie jar is private (mode 600), stored at
`${XDG_CACHE_HOME:-~/.cache}/agent-usage/claude-console-cookies.txt`, or
`$CLAUDE_CONSOLE_COOKIE_JAR` when set. Rerun the import if the session expires
or you switch organizations. The lookup uses the Console's undocumented,
read-only `/api/organizations/<organization>/prepaid/credits` endpoint and its
`promo_tranches` data. Every run queries the balance anew; failed requests
never reuse old balances. No credits are claimed, purchased, or consumed.
Monthly credits do not roll over; see
[Anthropic's monthly API credit terms](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-and-team-plans).

Claude shows the five-hour and weekly subscription limits, including separate
model limits such as Fable, with reset times and pacing. Claude's five-hour and
weekly limits both appear in the ranked expiration summary. It reads the default macOS
Keychain login or `.credentials.json` under `${CLAUDE_CONFIG_DIR:-~/.claude}`
and makes at most one read-only subscription-usage request per run, plus the
Console credit lookup when configured; credentials are never
passed in command arguments. It does not make model requests. HTTP 401 (token
rejected) and 403 (access denied) are reported separately.

Claude Code renews its access token only while it runs, so usage was
unreadable whenever Claude Code had been idle for longer than the token's
eight-hour life. When, and only when, the stored token is already past its
expiry, `usage` renews it itself with the stored refresh token, against
`https://platform.claude.com/v1/oauth/token` as Claude Code's own OAuth client.
That renewal is not metered: no model request is made. A live token is never
rotated, so a working login is never disturbed; `USAGE_CLAUDE_RENEW=0` disables
renewal entirely and restores the previous report-only behavior.

Renewal rotates the refresh token, so the new credential is written straight
back to the store it came from (Keychain, else `.credentials.json`), with the
value passed on standard input rather than in command arguments. Claude Code's
own `.storage-write.lock` is held across read, renew, and write, and a
credential renewed by Claude Code in the meantime is used as-is instead of
being rotated again. If the write fails, the renewed credential is saved to
`claude-renewed-credentials.json` (mode 600) in the cache directory and the
path is reported, because a rotated refresh token that is not stored anywhere
ends the login. A refused renewal changes nothing and is reported with its
HTTP status.

A long-lived token from `claude setup-token` is not an alternative here: those
tokens carry inference scope only and the usage endpoint rejects them with 403.

A 429 immediately starts a cooldown using `Retry-After` (seconds or an HTTP
date), with no immediate retry. If that header is missing, invalid, or already
elapsed, the fallback cooldown is 15 minutes. Later runs explicitly say when
they skip the request because of a locally cached cooldown.

Claude and Antigravity no longer read or write usage snapshots; existing
snapshot files and the old `USAGE_CLAUDE_CACHE_TTL` and
`USAGE_ANTIGRAVITY_CACHE_TTL` overrides are ignored. Claude's authentication
renewal and HTTP 429 cooldown are unchanged.

Antigravity runs `agy --print /usage --output-format json` on each invocation.
Starting the CLI costs seconds, so it can dominate dashboard runtime.
Antigravity's active five-hour buckets appear in the **5-hour limits** summary,
sorted by reset time alongside the other providers' five-hour windows. A
disabled five-hour bucket is shown as **disabled**, without inventing a reset
time or reporting its residual percentage; weekly exhaustion is still shown
and ranked as 100% used. `agy` treats its own `--print-timeout` as a turn budget
rather than a wall clock (a 5s budget was observed returning after 20s), so a
watchdog caps the query at `USAGE_ANTIGRAVITY_TIMEOUT` seconds (25 by default).
Failed, invalid, or timed-out responses show no quota stats and return nonzero.

Kimi reports `limit` and `remaining` per window and no longer sends the `used`
field it once did; the used percentage is derived from whichever pair is
present. Kimi access tokens last about fifteen minutes, so an expired one is
refreshed and written back before the usage query.

TypeSafe's public API has no usage or balance endpoint, so `usage` reads the
console (`console.typesafe.ai`): the billing overview for credit balance,
per-grant remaining amounts and expiries, and cycle spend, and `/api/usage` for
requests and tokens over the last 24 hours and 7 days per API key, with spend
estimated at the documented $0.042 per million input tokens (output is free).
`TYPESAFE_API_KEY` is rejected there; the console authenticates with Stytch
login cookies.

Seed that login once with `typesafe-login`: copy the `Cookie` request header
from any logged-in console request (DevTools, Network, pick a request, Copy
value) and run it with nothing else copied in between. It also reads the header
from standard input. The cookies are written to
`~/.cache/agent-usage/typesafe-cookies.txt` (mode 600, `TYPESAFE_COOKIE_JAR`
overrides) and are never passed in command arguments.

The console's `session` cookie is a JWT that lives only five minutes, but the
server re-mints it from the durable `session_id` cookie whenever both are sent,
so `usage` refreshes the jar on every run and the login survives unattended.
Requests run against a copy of the jar and the copy is promoted only when the
session survives, because a rejected request makes the console blank the
session cookie and writing that back would destroy a working login. The
underlying Stytch session is fixed at fourteen days from the browser login
rather than sliding, so the section prints when it ends and `typesafe-login`
has to be rerun.

The credit balance comes from a Next.js server action whose id is rebuilt on
every console deploy. The id is cached in
`~/.cache/agent-usage/typesafe-billing-action`; when the console answers that
the action is gone, `usage` rediscovers it from the billing page's own chunks
and retries once. Discovery costs about three seconds and only happens after a
deploy. Grants that live a month or less (the free tier credit) are paced and
ranked; longer purchased credits are listed with their expiry only.

Focused regression checks (no network or real accounts):

```bash
uv run --no-project python -m unittest discover -s SHELL/tests -p test_usage.py -v
```

## Codex launch speed

```bash
cdx                        # Standard
cdx -f                     # Fast, same model and reasoning effort
cdx -uf                    # Ultrafast, where available
cam -f -p "review the diff" # Fast in a headless run
```

Main-account launchers default to Standard without rewriting the saved Codex
configuration. `-f` and `-uf` apply only to that launch and are not supported on
the secondary account or in API-key mode. Existing Fast aliases such as `cdxf`
keep their Fast setting. Explicit `-c service_tier=…` overrides the wrapper
setting. Availability of each tier depends on the model and account.

## Codex parallel boost wrappers

```bash
cdxX                     # Sol 6.2/xhigh primary and subagents
cdmM                     # Sol 6.2/max primary and subagents
caxX                     # Astra 6.2/xhigh primary and subagents
camM                     # Astra 6.2/max primary and subagents
cdxX2                    # Same Sol xhigh boost on the secondary Codex account
cdmM2                    # Same Sol max boost on the secondary Codex account
caxX2                    # Same xhigh boost on the secondary Codex account
camM2                    # Same max boost on the secondary Codex account
cax                      # Ordinary subagent defaults again
```

`cdxX`/`cdmM` and `caxX`/`camM` temporarily enable agents with 16 concurrent
subagents (17 slots including the primary) and maximum depth 2. The `cd*` pair
uses `gpt-6.2-sol` for both primary and subagents; the `ca*` pair uses
`gpt-6.2-astra`. Each pair pins `xhigh` or `max` effort, respectively, for both.
They inherit the normal launchers' repository-scoped home, review hooks, and
interactive/headless
behavior; for example, `caxX -p "your task"`. Explicit trailing `-c` overrides
still win.

Names are case-sensitive: `cdmM` and `camM` are distinct from the existing
medium-effort `cdmm` and `camm`. Their `2`-suffixed variants use the secondary
account's separate configuration and state roots. There are no additional bare
variants. They never edit `config.toml`; ordinary `cdx`, `cdm`, `cax`, and `cam`
launches retain the managed defaults. New shells pick them up after propagation;
reload an existing shell with `source ~/.bash_agents`.

## Codex API-key fallback

To use OpenAI API-key billing when ChatGPT subscription quota is exhausted without
disturbing `~/.codex` or `~/.codex2`, provision a separate canonical home in
`~/.codex-api` (symlinking `AGENTS.md`, `config.toml`, `prompts`, `rules`, `skills`,
and `hooks` from `~/.codex`), then authenticate once:

```bash
printenv OPENAI_API_KEY | CODEX_HOME="$HOME/.codex-api" codex login --with-api-key
```

Launch any Codex wrapper against `~/.codex-api` (`~/.codex-state-api`) either
with the `cdxk` prefix or with `--api-key` / `-ak`:

```bash
cdxk                     # Same as `cdxk cdx` (gpt-6.2-sol/xhigh, API-key home)
cdxk -p "fix the tests"  # Headless final-only on ~/.codex-api
cdxk cam -p "audit diff" # Prefix any Codex wrapper (model, bare, boost, final)
cdxb --api-key           # Bare mode on ~/.codex-api
cam -ak -p "fix tests"   # Short flag anywhere before `--`
```

Wrapper runs clear inherited `OPENAI_API_KEY`, `CODEX_API_KEY`, and
`CODEX_ACCESS_TOKEN` so subscription wrappers never silently bill `CODEX_API_KEY`
under `codex exec` and API-key runs use `~/.codex-api/auth.json` uniformly across
TUI, `app-server`, and `exec`. When `OPENAI_API_KEY` is set in your shell, `cdxk`
and `--api-key` automatically sync it into `~/.codex-api/auth.json` before
clearing the env var (refusing to overwrite ChatGPT OAuth or symlinked `auth.json`
files). `cdxk` rejects secondary `*2` wrappers (`cdxk cdx2`).

## Codex bare launches and resume

Bare wrappers (`cdxb`, `camb`, their `2` variants, etc.) reuse a minimal home
per project/worktree and account. Saved conversations stay available without
being injected into new chats. Plain and review-hook launches have separate
homes. Automatic project instructions, skill inventories, plugins and memories
remain disabled; explicit skill mentions still work. Tools are cut to the core
coding loop (shell, patch, web search, subagents) plus external-Chrome browser
use and the arXiv MCP; goals, image generation, computer use, the in-app browser,
skill search, and tool suggestions are off. Browser use copies the ChatGPT
app's `node_repl` server from the account's `config.toml`; without it the
launcher warns and continues. Unexpected home-level
`AGENTS.md` or `AGENTS.override.md` files cause a clear error, not deletion.

`guidance sync` installs the resume helper as `~/.local/bin/codex-sessions`
with the wrappers (Python 3.11+; `fzf` is optional):

```bash
cdxr                     # Current directory, both accounts; searchable picker
cdxr --all               # All directories, both accounts, bare and normal
cdxr --last              # Latest matching session
cdxr SESSION_ID          # Exact session from any directory
cdxr2 --all              # Account 2 only
cdxr --all --list         # Read-only inventory
cdxr SESSION_ID --dry-run # Show account, original home and native command
cdxr SESSION_ID -m gpt-5.6-sol --ctx-mgmt
```

`cdxr` searches the two global homes and their repository, branch, fresh,
new persistent bare, and old timestamped bare stores. It reads SQLite metadata
read-only, including paginated sessions, and discovers unindexed rollout files.
It resumes **in the original home with that home's account**; it does not switch
a thread to another account, copy credentials, merge stores, or move writer locks.
Inherited API credentials and SQLite-location overrides are cleared for resume.
Existing homes and conversations are not migrated. `--home PATH` disambiguates
copies of the same session ID in different stores.

Headless sessions are included. Add `--include-subagents` for internal child
sessions, or `--include-archived` for archived sessions. Choosing an archived
session runs native `codex unarchive` in its original home before resuming.
Very old files without native session metadata are listed with a conversion
warning: Codex 0.154 cannot resume that format, and this helper never rewrites it.
Records without a known directory appear under `--all`.

`-m`, `-c`, `-C`, `-a`, `-s`, `--profile`, and context-manager options are
supported; put other native options or a continuation prompt after `--`.
Remote attachment and explicit SQLite redirection belong to native `codex`,
not this local-home picker. Native Codex still enforces active-writer exclusion.

Existing `~/.codex/resume.conf` (or `CODEX_RESUME_CONFIG`) defaults for `any`,
`last`, `dir`, `limit`, and `effort` are retained. Discovery is always live.
The picker searches every matching session; a configured `limit` caps printed
lists only. An explicit `--limit N` can also cap the picker.
The obsolete `full_auto` setting is not forwarded: the selected home's approval
and sandbox settings apply, with explicit `-a`/`-s` overrides available.
The old `~/.codex/bin/codex_resume` script is left untouched, but no longer used
by default. `CODEX_SESSION_HELPER` selects another copy of the new helper;
`CODEX_RESUME_LAUNCHER` remains an explicit launcher override.

Custom `CODEX_CANONICAL_HOME`, `CODEX_STATE_ROOT`, `CODEX2_HOME`,
`CODEX2_STATE_ROOT`, `CODEX_BARE_STATE_ROOT`, and `CODEX_FRESH_STATE_ROOT`
locations are honored. Absolute `sqlite_home` configuration is supported;
unrecorded per-invocation SQLite environment routing cannot be inferred.

Focused tests, from the repository root:

```bash
uv run --no-project python -m unittest discover -s SHELL/tests -v
CODEX_NATIVE_TESTS=1 uv run --no-project python -m unittest discover -s SHELL/tests -v
```

Native checks use disposable homes and synthetic history with no model calls.
They verify low-context startup, history resume, and same-thread writer exclusion.

## Tests

Run tests from the source tree, not from `~/.git-helpers` (tests are not
installed there):

```bash
cd SHELL/git-helpers
python3 -m unittest tests.test_navigation -v
```

## Related docs

Picker keys and usage for `g peek` live in
`REFERENCE/CODEBASE-NAVIGATION/GIT-FN-USAGE.md`.
