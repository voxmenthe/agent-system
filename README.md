# agent-system

The guidance, skills, hooks, launch wrappers and shell setup shared by every
coding agent on my Macs, with the commands that install them into `$HOME`.

This is my personal setup, published for reference. It is built around the
tools and accounts I use, so expect to fork it and adapt it rather than run it
as-is.

Each Mac gets the same files from this checkout. What differs per machine
lives outside it: `~/.config/agent-system/machine.json` (which hosts this
machine runs) and `~/.config/agent-system/shell.local.sh` (cache locations,
extra PATH entries, the Chrome profile the browser skills use).

## Set up a Mac

Needs macOS and [Homebrew](https://brew.sh).

```bash
git clone https://github.com/voxmenthe/agent-system.git ~/repos/agent-system
cd ~/repos/agent-system
./bootstrap --dry-run     # preview; writes nothing
./bootstrap               # install; asks before writing
```

The preview stops early on a Mac that still needs some of the Homebrew
formulas, since the later stages run them; it also skips the guidance and
skill previews until OMem and the machine file are in place.

`bootstrap` installs `bash`, `git`, `jq`, `ripgrep` and `uv` with Homebrew, writes the
machine file, installs OMem (`memory`, `hist`) at the version pinned in
`dependencies.json`, projects guidance and the shell layer, syncs the skills,
installs the review hook, and ends with `./doctor`. It is safe to rerun.

By default it enables the agent CLIs it finds on `PATH` (a second account
only when its home, such as `~/.codex2`, already exists), plus `hist`,
`memory` and `shell`. Choose explicitly with `--hosts claude,codex,hist,memory,shell`;
the list is kept in the machine file for later runs. `bootstrap` does not
install the agent CLIs themselves; the `mup` shell function does, once the
shell layer is in place.

`SHELL/Brewfile` is my main Mac's full toolset, dumped with `brew bundle dump`.
`brew bundle --file SHELL/Brewfile` installs it on another Mac, but some of
its `uv` and `npm` entries are editable installs from sibling checkouts on
that Mac, so elsewhere they fail or install a different package. `bootstrap`
installs only the formulas it needs.

On a machine that already has some of these files (hand-copied dotfiles, a
`~/.claude/settings.json`), `bootstrap` lists the ones it did not write and asks
before replacing them. Each replaced file stays in that sync's backup, and
`cd AGENT-ENGINEERING/PERSISTENT-GUIDANCE && ./guidance rollback` restores the
whole sync. On a Mac whose skills were installed from another checkout (the
old monorepo), it also asks before moving the skill manager's state to this
checkout. `--yes` accepts every question.

`./doctor` is read-only. It checks tools, OMem, each enabled host, guidance,
skills, the review hook and the memory hooks, then lists what no command can do:
logging in to each CLI, trusting the Codex hooks in `/hooks`, creating
`~/.api_keys`, signing in to Chrome profiles, making Homebrew bash the login
shell, and installing the optional `sgrep` and `colgrep`. It does not import
session history: run `hist sync --all` once if you want this machine's old
transcripts searchable (it can take half an hour).

## Update

```bash
git pull --ff-only && ./bootstrap --yes
```

## Layout

| Path | What it is | Installed by |
|---|---|---|
| `AGENT-ENGINEERING/PERSISTENT-GUIDANCE` | Global agent instructions, policy packs, per-host configs, Claude hooks; also projects the shell layer | `./guidance sync` |
| `AGENT-ENGINEERING/SKILL-SYSTEM` | Skills and the manager that installs them per host | `bin/skill-system sync --apply` |
| `AGENT-ENGINEERING/REVIEW-HOOK` | Post-commit review hook for Codex, Kimi and Antigravity | `scripts/review_hook.py install --host <h> --apply` |
| `AGENT-ENGINEERING/AGENT-DEFINITIONS` | Claude Code subagents, none loaded by default | on demand: `./agent-defs load <name>` |
| `SHELL` | Dotfiles, `git-helpers`, launch wrappers (`.bash_agents`) and helpers | guidance (`shell` host) |
| `scripts/openrouter.py` | `or`: OpenRouter's model catalog, newest first, and the money left on a key | by hand: `install -m 755 scripts/openrouter.py ~/.local/bin/or` |
| `dependencies.json` | Pinned OMem ref, required Homebrew formulas, how `doctor` detects each host | read by `bootstrap` and `doctor` |

Edit the sources here, never the installed copies: a Claude Code hook blocks
edits to installed projections and names the source to edit instead. Each
component's README has its own details and tests.

`PLANS/` (design notes) and `AGENT-ENGINEERING/SKILL-SYSTEM/evaluations/`
(skill evaluation records) are gitignored: they stay on the working machine
and are not published.

## License

[MIT](LICENSE), except for the adapted skills and bundled files listed in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), which keep their upstream
terms.
