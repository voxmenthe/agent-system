---
argument-hint: [path ...] [push]
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Bash(git ls-files:*), Bash(find:*)
description: Commit outstanding work as logically grouped commits with informative messages
---

## Context

- Branch: !`git branch --show-current`
- Status, untracked files included: !`git status --short --untracked-files=all`
- Already staged: !`git diff --cached --stat`
- Recent commits, for message style: !`git log --oneline -10`

Arguments: `$ARGUMENTS`

## Your task

Commit the outstanding work as a set of logically grouped commits.

1. **Scope.** If the arguments name paths, everything outstanding under them is in
   scope, tracked and untracked. With no paths, the scope is the changes this session
   made. Everything else is unowned: leave it exactly as it is, staged or not, and list it
   at the end.
2. **Group** in-scope files by the reason they changed: one coherent reason per commit,
   and each file in exactly one commit. Do not split a file's hunks across commits.
3. **Large files.** Do not commit any file of 100 MB or more
   (`find <paths> -type f -size +100M`). Report each one, and suggest a `.gitignore` entry
   for it.
4. **Commit each group** by staging its paths explicitly (`git add -- <paths>`) and
   committing only those paths (`git commit -m "<message>" -- <paths>`), so that anything
   staged before you started stays staged and out of your commits. Never use `git add -A`,
   `git add .` or `git commit -a`.
5. **Messages.** Use `<area>: <verb-phrase>`, lowercase, no final period, matching the
   recent commits. Add a short body only when the subject cannot carry the reason: what
   changed and how it works, not the blow-by-blow. Never mention Claude or any other AI
   tool, and add no co-author trailer.
6. **Push** only if the arguments include `push`. Otherwise, do not push.

For anything not covered here, follow the git policy pack. Finish with one line per
commit (short hash and subject), then any unowned or large files you left alone.
