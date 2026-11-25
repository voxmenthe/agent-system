# Agent definitions

Owner-controlled source of truth for Claude Code subagent definitions. `agents/` is the **library**; `~/.claude/agents/` holds only what is currently loaded and must not be edited directly.

Nothing is loaded by default. Claude Code reads every file in `~/.claude/agents/` at startup and puts each `description` into the context window — and it offers no way to make an agent user-invocable only, so an agent parked there costs tokens in every session whether or not you use it. Keeping the library here and loading on demand makes that cost opt-in.

## Loading and unloading

```bash
./agent-defs status                   # what is loaded, and what is available
./agent-defs load researcher          # make one available to Claude Code
./agent-defs load tech-lead torvalds  # or several
./agent-defs unload researcher
./agent-defs unload --all             # back to an empty target
```

`load` and `unload` apply immediately: they name exactly what they touch, and both are reversible. Claude Code watches `~/.claude/agents/` and picks up a change within a few seconds with no restart, so an agent loaded mid-session is usable in that session.

`sync` is gated behind `--apply` because it acts on an implicit set rather than on named agents:

```bash
./agent-defs sync            # dry run: refresh loaded agents against the library
./agent-defs sync --apply
```

`sync` never loads anything new. It re-projects loaded agents whose library source changed, and withdraws loaded agents whose source has left the library.

To undo the most recent `load`, `unload`, or `sync`:

```bash
./agent-defs rollback
```

Every command that writes retains a preimage of what it changed under `~/.local/state/agent-definitions/backups/`.

## Adding, changing, and retiring an agent

The directory *is* the manifest — there is no separate list to keep in step.

| Goal | Action |
|---|---|
| Add an agent | Write `agents/<name>.md`; it becomes loadable |
| Change an agent | Edit `agents/<name>.md`; `sync --apply` refreshes it if loaded |
| Retire an agent | `git rm agents/<name>.md`; `sync --apply` withdraws it if loaded |
| Restore a retired agent | Restore `agents/<name>.md` from Git history |

## Definition contract

Beyond [Claude Code's own frontmatter rules](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields), `validate` enforces three things:

- **`name` matches the filename stem.** Claude Code does not require this, but the projector keys ownership off the filename, so the two must agree.
- **`.md` extension.** A truncated extension is silently undiscoverable at runtime.
- **`model` is a stable token** — `inherit`, `opus`, `sonnet`, `haiku`, or `fable`. A full model ID such as `claude-opus-4-6` is rejected.

That last rule is the point of the whole directory. Every definition imported here carried a pinned model version, and pinned versions are what rotted: a released-and-superseded ID keeps working just long enough that nobody notices, and a malformed one (`claude-opus-4-6[1m]`) never worked at all. Family aliases and `inherit` name no version, so a model release cannot strand a definition.

Use `inherit` unless a role should deliberately run cheaper than the session — `bounded-command-runner` and `commit-message-author` pin `sonnet` for that reason.

Frontmatter YAML is parsed by `claude plugin validate --strict`, not by this tool, so the runtime's parser is the authority on whether a definition loads. The `claude` executable must be on `PATH`.

## Ownership and conflicts

Every write records the sha256 of the file in `~/.local/state/agent-definitions/state.json`. A target file whose content matches that record is owned by this manager and may be overwritten or removed. Anything else — a file that was never loaded through this tool, or one edited in place afterwards — is a **conflict** that blocks the whole command before any write.

`sync --take-ownership` resolves a conflict by overwriting or deleting the target anyway, after backing it up. Note that it runs the opposite direction from `guidance adopt` in [PERSISTENT-GUIDANCE](../PERSISTENT-GUIDANCE/README.md), which pulls host drift *back* into canonical sources; the names differ deliberately.

Directories and dotfiles inside the target are ignored, never read or removed.

## Scope

Claude Code is the only managed host. It is the only CLI in use here with file-based subagent discovery: Codex 0.155 spawns subagents with a configured default model but has no persona-file registry, and `~/.cursor/agents` is unused. Project-level `.claude/agents/` directories inside other repositories are out of scope and untouched.

## Alternatives considered

**Entries in `PERSISTENT-GUIDANCE/hosts.json`.** That manager already projects host files with preflight, backup, and rollback, so agents could have been ~13 more `source`/`target` pairs. Rejected because adding or retiring an agent would mean hand-editing a manifest, which is the same manual bookkeeping that let the old definitions rot — and because guidance projects its whole set unconditionally, which is exactly what agents must not do.

**`permissions.deny: ["Agent(name)"]` instead of unloading.** A denied agent does disappear from the list the model sees, but it disappears for you too: asking for it by name in a session where it is denied returns *"No <name> subagent is available in this session."* That is an off switch, not on-demand availability. Claude Code has no subagent equivalent of a skill's `disable-model-invocation: true`.

**A `registry.json` in the style of [SKILL-SYSTEM](../SKILL-SYSTEM/).** Rejected as disproportionate. Skills are multi-file, third-party-sourced, and executable, which is why they carry lifecycle, provenance, and quarantine. These are single-file prompts written by the owner.

**Symlinks into this repository instead of copies.** Rejected because this repository lives on an external volume; an unmounted volume would silently empty the agent directory. Copies also make backup and rollback meaningful.
