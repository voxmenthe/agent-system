# colgrep for Devin, Command Code, Kimi Code and OpenCode

Gives these four agents [colgrep](https://github.com/lightonai/next-plaid/tree/main/colgrep)
semantic code search and keeps it away from Claude Code and Codex.

```bash
./agents install        # link the skill and write OpenCode's block, then print status
./agents status         # where it is installed; warns if it reached Claude Code or Codex
./agents diff           # our skill text against the installed colgrep's built-in text
./agents uninstall
./reindex               # build or update the indexes of the repos in $COLGREP_REPOS
./reindex --force av    # clear and rebuild named repos under ~/repos
```

Install either this or [`../sgrep`](../sgrep/README.md), not both: each tells
the agents to search with its own tool first.

## Where it goes

| Agent | Target | Loaded |
|---|---|---|
| Devin | `~/.config/devin/skills/colgrep` → `skill/` | when the model picks the skill |
| Command Code | `~/.commandcode/skills/colgrep` → `skill/` | when the model picks the skill |
| Kimi Code | `~/.kimi-code/skills/colgrep` → `skill/` | when the model picks the skill |
| OpenCode | marked block in `~/.config/opencode/AGENTS.md` | every session |

`skill/SKILL.md` is the source of truth. The three links see edits immediately;
OpenCode's block is a copy, so rerun `./agents install` after editing (`status`
reports it as stale until then). The block uses colgrep's own markers, so
`colgrep --uninstall-opencode` removes it too.

Install refuses to replace an existing entry at a link path, and uninstall
removes only links that point here.

## Keeping Claude Code and Codex out

Each target above is read only by its own agent. Do not put this skill in
`~/.agents/skills` or the shared registry: Codex reads that directory and
`skill-system` projects it into `~/.claude/skills`. For the same reason, do not
run colgrep's `--install-claude-code` or `--install-codex`, or `--uninstall`,
which also clears every index. `status` warns if colgrep shows up in any of
those places.

## Skill text

The body is colgrep 1.8.5's built-in instruction text plus an "Agent mode
first" section: for open questions the agent should try `colgrep --agent`
first, while keeping its judgment to use plain `colgrep`, `grep` or `rg` for
names, patterns and exact strings. That sits between colgrep's default
`hybrid` and its `agent` hook modes; `colgrep settings --hook-mode` only changes
colgrep's Claude Code and Codex hooks, so it has no effect here. `colgrep --agent`
needs the local model (`colgrep --install-agent`, 2.5 GB). After a colgrep
upgrade, `./agents diff` shows upstream changes to merge.

The frontmatter description is ours. With upstream's description ("use colgrep
as the primary search tool instead of Grep/Glob"), Devin answered a "where is X
handled" question with `codebase-search-and-understanding-expert`, which
prescribes `rg`, and never ran colgrep. The rewritten description names that
task and that skill.

Kimi's bare launchers (`kimb`, `kimbs`) use their own skill directories and do
not see this skill. Kimi's skill listing truncates descriptions at about 200
characters, so keep the trigger at the front of the description.

## What to expect

Measured 2026-10-13 on five of my repos, with Devin (`dswe`),
Command Code (`poolside/laguna-s-2.1-free`) and OpenCode (`ocsf`):

- Whether colgrep is used depends on the agent. Unprompted "where is X"
  questions led OpenCode to run `colgrep --agent` in 4 of 5 repos (its block
  loads every session), Devin in 1 of 5, and Command Code in none. Command
  Code never loaded the skill, even when told to use colgrep, and its
  `explore` sub-agent has no shell tool, so a search delegated there cannot
  run colgrep.
- One `colgrep --agent` call took 9-70 s on its own and 34-68 s inside agent
  runs; plain `colgrep` took 1-4 s. Command Code's shell tool stops commands
  after 30 s unless the model asks for longer, which cut off 2 of its 5
  required calls, so the skill asks for a 120 s timeout.
- Across 30 runs (3 agents x 5 behaviour questions, once with colgrep
  forbidden and once required), every agent found the right code either way;
  requiring colgrep raised mean run time by 1.5-4x.
- The indexes cover docs as well as code, so plain `colgrep` results in
  the two most documentation-heavy repos were mostly Markdown and JSON.
  `--code-only` filters after retrieval and returned 2 results instead of 10
  in one of them; `colgrep settings --ignore` is the untried fix.

## Indexes

colgrep keeps indexes under `~/Library/Application Support/colgrep/indices`,
outside the repos, and updates a repo's index incrementally on every search.
`reindex` builds them ahead of time with `colgrep init --yes` (no prompt above
10K code units). `--force` runs `colgrep clear` first for a full rebuild.
