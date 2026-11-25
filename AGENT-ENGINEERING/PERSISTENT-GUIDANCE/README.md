# Persistent guidance

This directory is the owner-controlled source of truth for global agent guidance **and explicitly managed CLI settings**. `AGENTS.md`, `policy/manifest.json`, `policy/packs/`, and `config/` are canonical. Most targets are whole-file projections; Codex configs and shared MCP entries in mixed-state JSON files manage only selected settings and leave the rest to their host.

`policy/packs/memory.md` embeds the blocks that `memory instructions` and `hist instructions` print, between `OMEM INSTRUCTIONS` and `HIST INSTRUCTIONS` markers; `./guidance build` (and `sync`) refreshes them from the installed OMem CLIs, so edit those blocks in the OMem repository, not here.

This is one of four projection managers; [../README.md](../README.md) indexes all of their sync procedures side by side.

## One-step propagation

From this directory:

```bash
./guidance sync
```

The command rebuilds generated policy artifacts, validates the catalog and host manifest, preflights every destination, and then updates the projections. Existing known legacy files are copied to `~/.local/state/persistent-guidance/backups/` before replacement or retirement. After writing, declared shared-consumer probes run automatically; a failed probe rolls back that file-changing transaction.

`guidance` uses `uv` and declares its Python and TOML-editing dependency inline. The first run prepares a cached environment; it does not install this repository's unrelated project dependencies.

An unknown file or local edit blocks only its **sync group**, before any file in that group changes, and sync exits 2 after applying everything else. Projections marked `"independent": true` in `hosts.json` (every user-level config and the Claude command directory) are each their own group; a directory projection is one group as a whole. Projections that name the same `"sync_group"` (the shell dotfiles and helpers) form one group of their own and apply together. Everything else (the kernel fan-out, both Codex homes' policy trees and prompt directories, the Cursor adapter, and retirements) shares one group, so hosts never run different policy generations.

A file that this manager never wrote and whose hash is not listed as known (a hand-copied dotfile on a machine set up before this repository, for example) is a conflict. `./guidance sync --replace-unowned` replaces such files instead; each old file stays in that sync's backup, so `rollback` restores it. Selected-settings and host-owned configs keep their unmanaged and host-written values; one that does not parse into the expected shape is still a conflict, because its values could not be kept. A file with a managed record and local edits, or a symlink, is still a conflict. The backups directory is private (`0700`). Sync rechecks each target just before writing it and rolls the whole transaction back on an error or Ctrl-C, but it cannot see an edit that lands between that recheck and its write, so do not edit these files while it runs.

Sources are paths under this folder, or under the checkout when they start with `..` (`"repository_root": "../.."` in `hosts.json` allows it; nothing outside the checkout). A source with its owner execute bit set is installed executable: sync adds execute bits wherever the target has read bits, and never removes them.

Useful read-only commands:

```bash
./guidance status
./guidance status --brief   # one line only when something needs attention
./guidance validate
./guidance verify
./guidance sync --dry-run
```

`~/.bash_agents` (managed in `SHELL`) runs `status --brief` in interactive shells at most hourly, so drift shows up when it happens instead of at the next sync. It finds this checkout through `~/.config/agent-system/machine.json`; `PERSISTENT_GUIDANCE_DIR` overrides that.

To undo the most recent sync, provided none of its outputs have been edited:

```bash
./guidance rollback
```

Rollback restores everything that transaction wrote, including files of hosts the machine file has since disabled.

## User-level configuration

`config/<host>/` holds the canonical configuration or selected-settings fragment, plus the prompt files those settings or the CLI load. Edit managed settings here, run `./guidance sync`, and the host picks them up. Sources are one-to-one with their targets; shared MCP values are the explicit exception, rendered from one registry into the opted-in native sources.

| Host | Canonical source | Managed target |
|---|---|---|
| Claude Code | `config/claude/settings.json`, `config/claude/commands/*.md` | `~/.claude/settings.json`, `~/.claude/commands/` |
| Codex | `config/codex/config.toml`, `config/codex/prompts/*.md` | `~/.codex/config.toml`, `~/.codex/prompts/` |
| Codex, secondary account | `config/codex2/config.toml`, `config/codex/prompts/*.md` | `~/.codex2/config.toml`, `~/.codex2/prompts/` |
| Grok | `config/grok/config.toml` | `~/.grok/config.toml` |
| Grok, second and third accounts | `config/grok2/config.toml`, `config/grok3/config.toml` | `~/.grok2/config.toml`, `~/.grok3/config.toml` |
| Kimi Code | `config/kimi/{config,tui}.toml`, `config/kimi/mcp.json` | `~/.kimi-code/` |
| Antigravity | `config/antigravity/settings.json`, `config/antigravity/antigravity-cli/settings.json` | `~/.gemini/settings.json`, `~/.gemini/antigravity-cli/settings.json` |
| Antigravity CLI, second account | `config/antigravity2/antigravity-cli/settings.json`, kept equal to the primary's (a test checks) | `~/.agy2/.gemini/antigravity-cli/settings.json` |
| Amp | `config/amp/settings.json` | `~/.config/amp/settings.json` |
| Cursor | `config/cursor/{cli-config,hooks}.json` | `~/.cursor/` |
| Command Code | `config/command-code/{settings,mcp}.json` | `~/.commandcode/` |
| Pi | `config/pi/models.json` | `~/.pi/agent/models.json` |
| Devin | `config/devin/argv.json` | `~/.devin/argv.json` |
| `hist` (OMem session history) | `config/hist/config.toml`; `view.inject`, the repositories shown the history view, is set per machine in the live file | `~/.hist/config.toml` |
| `memory` (OMem) | `config/memory/config.toml`: consolidation trust and catalog policy | `~/.memory-v0/config.toml` |

### One canonical source, many machines

- **Enabled hosts.** `~/.config/agent-system/machine.json` (`{"schema_version": 1, "checkout": "<path>", "hosts": [...]}`) lists the hosts this machine uses; `bootstrap` at the repository root writes it. Projections for other hosts report `disabled`: sync never writes, removes or probes them, and files they already have stay in place. Without the file every host in `required_hosts` is enabled.
- **Home directory.** Canonical files write `@HOME@` where the home directory goes. Sync renders it to the target home, and `adopt` turns that home path back into `@HOME@` wherever it ends at a path boundary (`/Users/a/x`, not `/Users/ab`). Rendering refuses a home path with characters other than letters, digits and `. _ - /`, because the value lands unescaped in JSON, TOML and shell strings.
- **Host-written values** stay in each machine's live files; see [Reconciling host-written drift](#reconciling-host-written-drift).

### Shared MCP servers

[`config/mcp/servers.json`](config/mcp/servers.json) owns shared HTTP server URLs. Each opted-in projection's `shared_mcp` in `hosts.json` names its native format and selected servers. `./guidance build` renders those entries into the existing native config sources; `./guidance sync` builds, validates and projects them with the normal conflict checks and recovery transaction. Do not hand-edit generated server entries in `config/<host>/`.

Lovable is configured for Claude Code, both Codex accounts, Antigravity, Kimi Code and Devin:

| Client | Canonical native fragment | Live target | Ownership |
|---|---|---|---|
| Claude Code | `config/claude/mcp.json` | `~/.claude.json` | Only `mcpServers.lovable` |
| Codex | `config/{codex,codex2}/config.toml` | `~/.{codex,codex2}/config.toml` | `mcp_servers.lovable`, alongside the existing selected settings |
| Antigravity | `config/antigravity/mcp.json` | `~/.gemini/config/mcp_config.json` | Only `mcpServers.lovable`; the second account already shares this config directory |
| Kimi Code | `config/kimi/mcp.json` | `~/.kimi-code/mcp.json` | Existing whole-file projection; other servers are retained in its source |
| Devin | `config/devin/mcp.json` | `~/.config/devin/mcp_config.json` | `mcpServers.lovable` and `mcpServers.claude_in_chrome`; other entries remain host-owned |

Selected JSON sync preserves all unowned parsed values, including other MCP servers and Claude's account/project state; JSON formatting may change when a managed value changes. First registration can add selected keys only when they are all absent; a differing existing entry is a conflict, not permission to overwrite it. Malformed JSON remains a conflict. An empty Antigravity config encountered during setup was initialized using `agy mcp add` before sync took ownership.

The registry currently supports HTTP URLs only, with entries shaped as `"lovable": {"url": "https://mcp.lovable.dev"}`. To add another shared server, add its registry entry and opt each desired projection into its name; selected-settings projections also need that server's exact key path in `managed_keys`. To remove a server, set its registry value to `null`, keep its projection references and ownership paths, then sync: the managed entry is removed without touching siblings. Do not simply delete a referenced registry key; that fails validation.

Claude in Chrome is a machine-local stdio exception to the shared HTTP registry. The native entries in Codex, Kimi Code, Devin and Command Code launch `claude --claude-in-chrome-mcp`; Devin and Command Code manage only `mcpServers.claude_in_chrome`, while Kimi Code retains its whole-file projection. These entries require a local Claude Code installation and a connected local browser; they cannot give cloud Devin sessions access to the Mac's browser.

OAuth tokens and client-generated credentials stay local and are never rendered from the registry. Sync installs configuration, not an OAuth grant. Client-native login and a read-only connection check are separate steps.

### Host-specific config notes

The prompt directories are projected as whole directories: every `*.md` in `config/claude/commands/` is installed into `~/.claude/commands/`, and every `*.md` in `config/codex/prompts/` into both Codex homes. That includes `compact.md`, which `experimental_compact_prompt_file` in each Codex config points at, each at its own home's copy. Add a prompt here, not in `$HOME`; a file created directly in the target directory is not tracked. Deleting one here needs a `retirements` or `releases` entry, because sync refuses to forget a target it owns. Codex 0.164 no longer offers files in `prompts/` as slash commands (`/debu` finds nothing), so only `compact.md` is still read there.

The three Grok homes run identical settings. Each has its own source because sync copies a host's `[privacy]` stamp back into the source, and a shared source would spread one account's stamp to the others. Edit all three files together; `tests/test_hostlib.py` fails when they differ outside `[privacy]`.

`config/claude/settings.json` turns on Code Mode (`CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`) and deliberately leaves `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` unset: Code Mode refuses to start while agent teams is on. Record a setting that is off on purpose here, never as a `//` line in the JSON. JSON has no comments, so the source stops parsing, `./guidance status` fails, and sync refuses to touch the unparseable installed copy.

### Projection edit guard (Claude Code)

`config/claude/settings.json` runs [`hooks/projection_edit_guard.py`](hooks/projection_edit_guard.py) before every Edit, Write, MultiEdit and NotebookEdit. When the target resolves (through symlinks) to an installed projection, the hook blocks the call and names the canonical file and the command that projects it. Selected-settings targets (Codex configs and mixed-state MCP JSON files) are not guarded, because hosts own most of those files. Shell writes are not intercepted.

Sync projects both Claude hooks to `~/.claude/hooks/persistent-guidance/`, and `settings.json` calls them there, so nothing Claude runs reads this checkout. The guard reads its rules from `~/.local/state/persistent-guidance/edit-guard.json`, which every `sync` derives from `projections` in `hosts.json` and `install_targets` in `../SKILL-SYSTEM/registry.json` (`hosts.json` names the guard under `edit_guard`). A new projection needs no hook change, but a registry change takes effect at the next guidance sync. A map that does not parse stops sync before any write; a missing or unreadable index is a non-blocking hook error, never a block.

### Piped-status warning (Claude Code)

Before every Bash call, [`hooks/piped_status_warning.py`](hooks/piped_status_warning.py) looks for a check piped through a filter whose `$?` is read next, as in `tsc --noEmit | tail -3; echo tsc=$?`, where `$?` is `tail`'s status. It never blocks: the agent gets a warning naming `${PIPESTATUS[0]}` as context and the command runs. It skips commands that use `PIPESTATUS` or `pipefail`, heredoc bodies and single-quoted text, which the shell does not run. It uses the patterns of the October 26 RX-2 helper (`.learning-workspace/reference-readacross/helpers/piped_status_misreads.py`) and was added when that check found five misreads after the testing-pack rule.

### Codex: selected settings, not whole-file synchronization

`codex-config` and `codex2-config` declare `managed_keys` in `hosts.json`. Their canonical TOML files contain only:

- The entire `[agents]` table, `features.multi_agent`, and `[features.multi_agent_v2]`. This includes subagent model/effort defaults when present; each account keeps its own limits and values.
- `[features.context_management]`, `model_context_window`, `model_auto_compact_token_limit`, `model_auto_compact_token_limit_scope`, `tool_output_token_limit`, and `experimental_compact_prompt_file`.
- `plan_mode_reasoning_effort`, `model_reasoning_summary`, `model_verbosity`, and `personality`.
- `memories.extract_model` and `memories.consolidation_model`, both under `[memories]`; other memory settings remain host-owned.
- The `[mcp_servers.claude_in_chrome]` table, which gives Codex the Claude in Chrome browser tools, and `[mcp_servers.lovable]`, rendered from the shared MCP registry. Other MCP entries remain host-owned.
- The OMem and `hist` hook arrays `hooks.UserPromptSubmit`, `hooks.SessionStart` and `hooks.SubagentStart`, and for the primary account `shell_environment_policy.set.OMEM_HOST`. Codex records which hooks you trusted under `[hooks.state]`, which stays host-owned, so on a new machine open `/hooks` in a fresh Codex session and trust them once.

Top-level **`model` and `model_reasoning_effort` are deliberately unmanaged**: launch wrappers select them. Projects, plugins, generated MCP entries, other hook registrations, hook trust hashes, notices, service tier, and all other unselected settings remain host-owned. They cause no warning, require no adoption/sync, and are never imported into these canonical fragments.

Status compares parsed values only at managed paths. A selected table owns its whole subtree. Sync merges canonical changes into the live TOML while preserving unrelated values and text; it rejects malformed content or a changed managed value instead of overwriting it. Atomic writes, mutation-time hash checks, backups, and rollback remain in effect. Rollback refuses a later edit to the live file, even when that edit affects only unmanaged settings, so recovery cannot erase newer host state.

Changing a managed value locally still reports a conflict. `./guidance adopt --dry-run --only codex-config` shows only the managed differences; adoption copies only those values into the canonical fragment. To manage a new setting, add its key path to `managed_keys` and its desired value to the fragment. To remove a managed value, omit it from the fragment but keep its path; to release it without changing the live value, remove both. Empty or overlapping paths, non-JSON/TOML sources, and unmanaged values in a canonical fragment fail validation. `managed_keys` and `host_owned_keys` are mutually exclusive.

Credential and session stores (`auth.json`, `credentials/`, `oauth/`) and `~/.cursor/mcp.json` stay out of the projection set. The mixed-state `~/.claude.json` is the narrow exception: only its declared shared MCP entries are managed, and its account/session values never enter canonical fragments. Recovery backups remain private under the manager's state directory. The approval lists hosts append to, `~/.codex/rules/default.rules` and `~/.claude/settings.local.json`, are host state and also stay out.

Files that a CLI rewrites with its own state are listed under `releases` in `hosts.json` instead of being managed: currently `~/.commandcode/config.json` and `~/.pi/agent/settings.json`. Sync forgets a released target's ownership record and never touches the file. A release entry is inert once a sync has run, so it can be deleted after that.

### Reconciling host-written drift

Unlike `AGENTS.md`, several CLIs rewrite their own configuration file. Routine Codex changes are outside its selected-settings contract above. Other whole-file projections still reconcile host-written state: Claude Code writes `/config`, `model`, `effortLevel` and `modelSettings` choices back to `settings.json`, Antigravity sets `ide.hasSeenNudge`, the Antigravity CLI records `model`, `trustedWorkspaces` and always-allowed commands, Grok stamps `privacy_banner_acked` and strips comments when it rewrites `config.toml`, and Kimi Code rewrites its service's model list (the `[models]` tables in `config.toml`) whenever that list changes and records your model choices in `default_model` and `[secondary_model]`. Every other Kimi setting stays canonical.

A config projection's `host_owned_keys` lists the key paths its host writes (an empty list still opts into comparing parsed JSON/TOML). Those values belong to each machine, so the canonical source never holds them; validation rejects a source that carries one. Sync compares only the remaining keys: a live file that differs in host-owned keys, formatting, or comments stays `current` and is never rewritten. When a canonical key changes, sync writes the canonical text with the live file's host-owned values merged in. A live change to a canonical key is a `conflict` that blocks only that config. A canonical comment does not survive a host that strips comments, so put explanations in this README instead.

`adopt` is the manual reconciliation step: it copies the host's current managed content back into its canonical source, turning the conflict into an ordinary repository diff. Whole-file projections copy the whole file; selected-settings projections copy only managed values.

```bash
./guidance adopt --dry-run          # show what the host and canonical each changed, write nothing
./guidance adopt                    # pull every drifted target back
./guidance adopt --only codex-config
```

Sync keeps content-addressed copies of its last-synced canonical content under `~/.local/state/persistent-guidance/installed/`: whole files for whole-file projections, managed-value fragments for selected settings. That lets `adopt --dry-run` show two diffs: installed → live (what the host changed) and, when canonical also moved, installed → canonical (your unsynced edit). Selected-settings diffs exclude unmanaged values. Values on lines that look like keys, tokens, secrets, or passwords are redacted. If both sides changed, adoption can revert your unsynced managed edit, so adopt and then reapply that hunk from `git diff`.

Review the result with `git diff config/`, keep or revert each hunk, then run `./guidance sync`. Adoption only considers `conflict` targets, and it leaves host-owned keys out of what it copies. It ignores `legacy` targets, since those are the known old files that sync is supposed to overwrite, never touches a retirement target, and never adopts a `managed-stale` target: that target still matches what sync installed apart from host-owned values, so there is no host edit left to recover and adopting it would revert a canonical edit you have not synced yet.

Because `AGENTS.md` projects to ten hosts, adopting drift on one of them rewrites the shared kernel for all ten. Inspect that diff carefully; `--only` exists for this reason.

## Verification

From this directory:

```bash
uv run --no-project --with tomlkit==0.13.3 python -m unittest discover -s tests
./guidance validate
./guidance sync --dry-run
```

## Host delivery

| Host | Managed delivery |
|---|---|
| Codex | `~/.codex/AGENTS.md` plus `~/.codex/policy/` |
| Codex, secondary account (`codex2`) | `~/.codex2/AGENTS.md` plus `~/.codex2/policy/`; the `2`-suffixed Codex wrappers (`cdx2` and the rest) set `CODEX_HOME=~/.codex2` |
| Claude Code | `~/.claude/CLAUDE.md` |
| Devin | Claude compatibility, runtime-checked by `guidance verify`; the redundant `~/.devin/AGENTS.md` is retired |
| Cursor | Always-on user rule in `~/.cursor/rules/persistent-guidance.mdc` |
| Antigravity | `~/.gemini/GEMINI.md` and the active desktop/IDE profile files |
| Antigravity CLI, second account (`agy2`) | `~/.agy2/.gemini/GEMINI.md`; the `2`-suffixed Antigravity wrappers (`agg2` and the rest) run `agy` with `HOME=~/.agy2` |
| Grok | Claude compatibility, runtime-checked by `guidance verify`; the redundant `~/.grok/AGENTS.md` is retired |
| Command Code | `~/.commandcode/AGENTS.md` |
| Pi | `~/.pi/agent/AGENTS.md` |
| Amp | `~/.config/amp/AGENTS.md`; the generic duplicate is retired |
| Kimi Code | `~/.kimi-code/AGENTS.md`; policy packs use the shared `~/.codex/policy/` tree |
| Shell layer (`shell`) | The `~/.bash*` dotfiles, `~/.git-helpers/` and five `~/.local/bin` helpers, from `SHELL/` (one sync group; see [SHELL](../../SHELL/README.md)) |

The exact targets, known legacy hashes, shared-consumer relationships, and protected source paths are declared in `hosts.json`, alongside the user-level configuration projections described above. A host-specific adapter may change presentation or discovery mechanics, but not the policy semantics.

Kimi Code loads global instructions from `$KIMI_CODE_HOME/AGENTS.md` (default `~/.kimi-code/AGENTS.md`; see [Kimi instruction-file discovery](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/agents)). The managed file replaces the known legacy instructions, with a backup on first adoption. Normal `kimm`/`kimh`/`kiml` launchers use this canonical home; review-enabled variants link its `AGENTS.md` into their selected home. Bare `kimb`/`kimbs` launchers intentionally omit it. Do not project guidance to `~/.agents/AGENTS.md`, which those bare launchers cannot exclude. An independently configured `KIMI_CODE_HOME` is not automatically managed.
