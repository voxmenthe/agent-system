---
name: codebase-search-and-understanding-expert
description: Answer questions about existing code, including why it is built that way and whether planned work shipped. Use when the user or the task needs to know how code works, where something happens, why it is this way, where a value came from, or how far a plan got. Do not use for change-impact planning, reviews, or as a routine first step before an edit.
---

# Codebase Search and Understanding

Answer each part of the question from where its answer lives. What the code does now lives in the code: read it, and run it when the answer depends on runtime. Why it is that way, and whether planned work shipped, live in history: commits, plans, and past agent sessions. Many questions need both; say which part came from where.

`map-change` owns the impact of an authorized change. Reuse tracing already done for either; do not run both over the same evidence.

## Trace the code

1. Locate named paths, repository instructions, entrypoints, and nearby tests with `rg --files` and path/type filters.
2. Search the likely owning directory: `sgrep "<behaviour in plain words>" <dir>` when you don't know the names (see the `sgrep` skill), `rg -n` when you do. Then read the complete relevant behavioral unit. Search hits locate evidence; they do not establish behavior alone.
3. Trace callers, dependencies, configuration, tests, and error paths until the question's boundary is understood. Expand when evidence reveals coupling, not to inventory everything.
4. When the answer depends on runtime (is this folder needed, which branch runs), prefer an existing test or a cheap read-only probe over inference, and say which you did.

## Trace the history

Most "how" and "where" questions need none of this. Reach for it when the question is why, where from, whether, or "did we":

| Question | Where the answer usually is | First moves |
| --- | --- | --- |
| Why is it built this way? Where does this value come from? | The commit that introduced it, the plan behind it, the session that wrote it | `git log -S'<symbol>' --format='%h %cI %s'`; `sgrep "<the reason, in the plan's words>" PLANS`; then `hist` below |
| Has this plan been implemented? Where do we stand? | Code and tests against the plan's milestones; the sessions that worked on it | Check each milestone in code, tests, and `git log`; `hist find "<plan file name>" --all` |
| Did we try this before? Has this failed before? | Past sessions | `hist find "<exact error or phrase>" --all` |

`hist` holds what commits and plans leave out: what the user asked for, what was considered, what the tools printed. Ways in from code:

- **The edit that introduced a symbol.** `hist find "<symbol>" --all --kind tool --until <commit time from git log>`. Hits come newest first; follow `more:` to the last page, where the oldest hit is usually the edit itself, then `hist zoom` the outline ref under it to read the discussion around it. Commits often land in a batch after the work, so the commit time is only an upper bound.
- **The conversation behind a commit.** `hist find "<short hash>" --all`, including commits made from another repository.
- **What the user wanted when it was built.** `hist find "<feature words>" --all --kind human`.

Search for a name, file name, or error text alone; a code line with its value mostly finds earlier searches for that line. `--after` is a paging cursor; bound time with `--since` and `--until`. These are starting points, not a checklist: when you suspect an earlier session already holds the answer, such as a worker that traced this subsystem, the removal of a function, or a decision argued out in another repository, look.

History says what was. Confirm behavior against the current code. "No recorded reason" is a valid answer and better than an invented one. When history changes the answer, say so in a line.

## Answer

Give exact file:line evidence and execution paths. Keep apart what the code does now, what history says (with its commit, plan, or `hist` reference), and what you inferred. For plan status, report implemented work, remaining milestones, and how current the plan document is, separately. Label unverified runtime behavior.

## Bounded search

Narrow by directory and glob before searching common terms. `rg -m 20` limits matches per file, not total output. Use `rg -l` for filenames alone. Empty results may reflect ignored files: use `--hidden` or explicit paths deliberately, without searching `.git` contents. Use NUL-delimited filename lists when passing paths between commands.

Use an already available language server or AST search when text cannot distinguish syntax. Imports, co-changes, and ranking scores are navigation hints, not proof of call relationships. Do not modify the repository or install tooling merely to explore it.
