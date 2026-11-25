# Agent engineering

Four independent managers project owner-controlled sources in this repository into the CLI configuration directories under `$HOME`. This page is the index of their sync procedures. Each subsystem's own README or usage guide remains the authority on its behavior; what follows is the part you need to run them and the part that only makes sense when you look at all four together.

Every manager follows the same shape:

- A canonical source lives in this repository. Managed files or settings under `$HOME` are **projections**; edit their source here. Unmanaged Codex settings remain host-owned.
- Whole-file ownership is tracked by content hash. A target the manager did not write, or one edited in place since the last sync, is a **conflict** that blocks the sync before any write. PERSISTENT-GUIDANCE narrows this: a conflict blocks only its sync group, each user-level config is its own group, and some host-only config rewrites are adopted automatically. Codex configs and selected shared MCP entries compare only explicitly managed values; other host changes are silent and left alone.
- A preimage of everything changed is retained, and the last transaction can be rolled back.

Three of them project their entire canonical set. AGENT-DEFINITIONS is the exception: its sources are a *library*, and only the agents you explicitly load are projected — see [Loading agents on demand](#loading-agents-on-demand).

## The four managers

| Subsystem | Owns | Projects into | Primary command |
|---|---|---|---|
| [PERSISTENT-GUIDANCE](PERSISTENT-GUIDANCE/README.md) | `AGENTS.md`, policy packs, CLI config and prompt files; selected settings for Codex and mixed-state MCP configs | 11 hosts: `~/.claude/`, `~/.codex/`, `~/.codex2/`, `~/.gemini/`, `~/.kimi-code/`, `~/.grok/`, `~/.cursor/`, `~/.commandcode/`, `~/.pi/`, `~/.config/amp/`, `~/.devin/` | `./guidance sync` |
| [AGENT-DEFINITIONS](AGENT-DEFINITIONS/README.md) | A library of Claude Code subagent definitions | `~/.claude/agents/`, on demand only | `./agent-defs load <name>` |
| [SKILL-SYSTEM](SKILL-SYSTEM/README.md) | Canonical custom skills | `~/.agents/skills/`, then `~/.claude/skills/`, `~/.config/mimocode/skills/` | `bin/skill-system sync --apply` |
| [REVIEW-HOOK](REVIEW-HOOK/USAGE.md) | The post-commit review system | Per-host installer trees for Codex, Kimi Code, Antigravity | `scripts/review_hook.py install --host <h> --apply` |

All four are run from their own directory, and none of them touch the others' targets.

## Mutation defaults are not the same

This is the one thing worth memorizing, because getting it wrong is how you write when you meant to preview:

- **`./guidance sync` writes immediately.** Pass `--dry-run` to preview.
- **`skill-system` and `review_hook.py` preview by default.** They are dry runs until you add `--apply`.
- **`agent-defs` is split.** `load` and `unload` write immediately, because each one names exactly the agents it touches. `sync` previews until `--apply`, because it acts on whatever happens to be loaded.

`./guidance status`, `agent-defs status`, `skill-system status`, and `review_hook.py status --all-hosts` are always read-only.

## Loading agents on demand

Claude Code reads every file in `~/.claude/agents/` at startup and puts each `description` into the context window. It offers no way to mark a subagent user-invocable only — `permissions.deny` hides an agent from the model but also makes it unavailable to you — so an agent parked in that directory costs tokens in every session whether or not you use it.

The library therefore stays in the repository, and you load what a task actually needs:

```bash
cd AGENT-DEFINITIONS
./agent-defs status              # what is loaded, and what is available
./agent-defs load tech-lead      # or several: load tech-lead torvalds
./agent-defs unload --all        # back to an empty target
```

Claude Code notices the change within a few seconds without a restart, so an agent loaded mid-session is usable in that session. The steady state is zero loaded.

`./agent-defs sync --apply` is maintenance, not loading: it re-projects already-loaded agents whose library source changed and withdraws ones whose source left the library. It never loads a new agent. Adding, editing, and retiring definitions is covered in [AGENT-DEFINITIONS/README.md](AGENT-DEFINITIONS/README.md).

## Routine sync

There is no required ordering between the managers; they own disjoint targets. This sequence is just a convenient sweep, preview first:

```bash
cd PERSISTENT-GUIDANCE && ./guidance status                  # exit 1 = changes, 2 = conflicts
cd ../AGENT-DEFINITIONS && ./agent-defs status               # loaded agents only; the library is not a target
cd ../SKILL-SYSTEM      && bin/skill-system status
cd ../REVIEW-HOOK       && /usr/bin/python3 -B scripts/review_hook.py status --all-hosts
```

Then apply whichever reported work:

```bash
cd PERSISTENT-GUIDANCE && ./guidance sync
cd ../AGENT-DEFINITIONS && ./agent-defs sync --apply         # no-op when nothing is loaded
cd ../SKILL-SYSTEM      && bin/skill-system sync --apply
cd ../REVIEW-HOOK       && /usr/bin/python3 -B scripts/review_hook.py install --host codex --apply
```

`guidance sync` runs the shared-consumer probes (`devin rules list`, `grok inspect --json`) afterwards and rolls its own transaction back if one fails.

## Resolving a conflict

All four refuse to overwrite a file they do not own, but they resolve that refusal in **opposite directions**. Pick by asking which copy you want to keep:

| Situation | Command | Direction |
|---|---|---|
| The host rewrote its own config and you want to keep that change | `./guidance adopt` | host file → canonical source |
| The repository is right and the target is stale or unowned | `./agent-defs sync --apply --take-ownership` | canonical source → host file |
| A skill target collides or was edited locally | `bin/skill-system sync --apply --force` | canonical source → host file |

`guidance adopt` is the odd one out, and deliberately so. For whole-file projections, adopting turns host-written drift into an ordinary repository diff you review with `git diff config/` before syncing. For the two Codex configs, ordinary host updates are unmanaged and need no reconciliation; adoption copies only conflicting managed settings. See [Codex selected settings](PERSISTENT-GUIDANCE/README.md#codex-selected-settings-not-whole-file-synchronization) and [Reconciling host-written drift](PERSISTENT-GUIDANCE/README.md#reconciling-host-written-drift).

Use `--dry-run` on `adopt` first, and `--only <projection-id>` to take one file at a time. `AGENTS.md` projects to ten hosts, so adopting drift on one of them rewrites the shared kernel for all ten.

## Recovery material

| Subsystem | State and backups |
|---|---|
| PERSISTENT-GUIDANCE | `~/.local/state/persistent-guidance/` |
| AGENT-DEFINITIONS | `~/.local/state/agent-definitions/` |
| SKILL-SYSTEM | `~/.agents/.skill-system/` |
| REVIEW-HOOK | `<canonical-host-home>/.review-after-commit-installer/` |

To undo the most recent file-changing sync, provided none of its outputs have been edited since:

```bash
./guidance rollback
./agent-defs rollback
bin/skill-system rollback <operation_id> --apply
/usr/bin/python3 -B scripts/review_hook.py rollback --host <host> --apply
```

Review-hook rollback has a required order when selected Codex or Kimi Code homes are involved; follow the receipts in [USAGE.md](REVIEW-HOOK/USAGE.md#roll-back) rather than deleting by hand.

## Where the managers meet

They own disjoint files, but two relationships are worth knowing:

- **Review-hook reads the live host config.** `materialize-profile` and `materialize-kimi-config` derive a *selected* host home from the canonical home, reading `~/.codex/config.toml` and `~/.kimi-code/config.toml`. Kimi's config is a whole-file projection; Codex combines managed preferences with host-owned state. Review-hook keeps consuming the full live config, not Codex's small repository fragment.
- **Three managers write under `~/.claude/`, but never the same file.** Skill-system projects `~/.claude/skills/` and edits the `skills.json` lock; guidance owns `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/.claude/commands/`, and selected MCP definitions in `~/.claude.json`; agent-defs owns `~/.claude/agents/`. Guidance owns the `permissions` block in `settings.json`, so a `deny` rule naming an agent is a guidance change, not an agent-defs one.

Credential stores (`auth.json`, `credentials/`, `oauth/`) and `~/.cursor/mcp.json` stay outside every projection set. Guidance manages only selected MCP definitions inside the mixed-state `~/.claude.json`; its account/session values stay host-owned and never enter canonical fragments. Shared HTTP server URLs live in [PERSISTENT-GUIDANCE/config/mcp/servers.json](PERSISTENT-GUIDANCE/config/mcp/servers.json) and use the existing `./guidance sync` path.
