---
name: sgrep
description: Find code, or the plans and notes behind it, by describing it, with the local sgrep CLI. Use when you need where or how something is implemented, or why it was planned that way, and don't know the exact names. Do not use for known names, strings, or regexes; use rg for those, and grep only if rg is missing.
---

# sgrep: find code and docs by what they say

`sgrep` is a local CLI (nothing leaves the machine) that ranks code and docs by
meaning as well as words. Use sgrep to locate behaviour or reasoning, rg for
exact names and every occurrence, and grep only if rg is missing.

## Commands

```bash
sgrep "where a failed upload is retried with backoff" src         # implementation: the code folder
sgrep "why uploads retry instead of failing fast" PLANS           # plans, decisions, motivation
sgrep "how the client library paginates results" REFERENCE        # external manuals, mirrored docs
sgrep "where a failed upload is retried with backoff" src -n 10   # 10 results instead of 5
sgrep "where a failed upload is retried with backoff"             # whole repo: location unknown
rg --json -C 3 -g '*.py' 'retry|backoff' | sgrep "where a failed upload is retried" --stdin
```

The last form ranks rg's matches by intent. Use it to filter by file type or
to sort a long list of rg hits.

## Workflow

1. Aim PATH at what you're looking for. For an implementation, use the folder
   that holds the code (`src`, `lib`, `apps/<name>`, `packages/<name>`); run
   `ls` first if you don't know the layout. For past plans, decisions, or
   motivation, search `PLANS`, which holds most of them, then `docs`. For how
   an external tool or library works, search `REFERENCE`, which holds manuals
   and mirrored docs. Repos without these folders usually use `docs`. Search
   the repo root only when you don't know where it lives: a large repo is
   mostly docs and data, so its index is slow to rebuild and prose crowds out
   code.
2. Describe it in words the source would use: the code's or comments' terms
   for code ("truncate long command output to the token budget"), the plan's
   terms for docs.
3. Each result is `path:start-end` followed by the passage. Paths are
   relative to the PATH you passed: `sgrep "q" src` prints `api/x.py:10-30`
   for `src/api/x.py`.
4. As soon as a result names a function, type, constant, or config key, switch
   to rg for its definition, callers, and tests. Read the file before
   answering or editing: sgrep always returns something, even when nothing
   matches, so a result is a lead, not proof.
5. If the results miss, rephrase once. If a scoped search still misses, widen
   PATH to the parent or the repo root before concluding it isn't there, since
   the wrong folder hides the answer. Then fall back to rg with likely names.

## Rules

- One query and at most one PATH. `sgrep "q" dirA dirB` fails; search their
  parent or run sgrep twice.
- `-n N` sets the result count (default 5). There is no `--n`, `--glob`, `-g`,
  or `-t`; filter file types with the rg pipe above.
- Every result prints its whole passage (up to about 2,000 characters), so
  start with the default 5.
- The first search of a folder, or the first after any file in it changes,
  builds that folder's index: a few seconds for a code folder, up to about 40
  seconds for a whole large repo. Later searches take 0.2-5 seconds. Run it in
  the foreground with a timeout of at least 120 seconds, and don't pass
  `--refresh-cache` or `--no-cache`.
- When you hand a search to a sub-agent, tell it to use sgrep, then rg.
