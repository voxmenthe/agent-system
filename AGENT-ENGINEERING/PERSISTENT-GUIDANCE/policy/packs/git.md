# Git, coordination, and diff hygiene

## Applies when

Load this pack before committing, rebasing, resetting, restoring, checking out over work, cleaning, deleting, moving large amounts of code, pushing, cherry-picking, merging, changing history, preparing a pull request, or reviewing/staging a diff. Also load it when multiple people or agents may be editing the same worktree.

## Does not apply when

It is optional for read-only repository inspection such as `git log`, `git show`, or `git diff`, unless those commands are part of a publication or recovery workflow.

## Non-negotiable rules

- Never discard, overwrite, restore, or delete changes you did not author or that the user did not explicitly ask to remove.
- Never run destructive operations such as `git reset --hard`, `git clean`, restoring unknown files, checking out an older state over work, amending shared commits, force-pushing, or history rewriting without explicit written authorization.
- Before deleting a file to resolve a local failure, stop and verify ownership and intent. Another person or agent may be editing nearby files.
- High-risk operations require a safer alternative: backup branch/tag, dry run, worktree, patch export, shadow copy, or an explicit recovery path.
- Commit only the intended files. Do not stage the entire worktree by default.
- In a worktree other sessions may share, never run `git stash` without a pathspec limited to your own files, and never pop, apply, drop or clear a stash entry you did not create: every worktree of a repository shares one stash list. Save your own work as a commit or a patch instead.
- Before `git worktree remove`, forced or not, check the worktree for commits no branch holds (`git -C <tree> log --oneline HEAD --not --branches --remotes`) and ignored files worth keeping (`git -C <tree> status --short --ignored`). Save them, or confirm they are disposable output of your own run; removal takes both.

## Procedure

1. Inspect `git status --short`, the relevant diff, and repository instructions before any mutation.
2. Separate behavioral edits from mechanical movement, formatting, generated output, or broad renaming. When both are necessary, prefer distinct commits or clearly separable patches.
3. Coordinate when overlapping work is possible. Do not “fix” failures by removing another actor’s in-progress changes.
4. Stage paths explicitly and quote paths containing brackets, parentheses, spaces, or shell metacharacters.
5. Keep commits atomic. A commit should represent one coherent reason for change and include only its touched files.
6. Use subjects shaped as `<area>: <verb-phrase>`, lowercase, with no terminal period. A body is optional for trivial work. When needed, open with what the old behavior got wrong and close with the new shape; keep it to a few paragraphs and link longer design material.
7. For non-interactive rebases, set `GIT_EDITOR=:` and `GIT_SEQUENCE_EDITOR=:` only after confirming the intended sequence and safety.
8. Before publishing, review the diff as an external reviewer: accidental churn, unrelated files, secret/config leakage, generated files, unsupported claims, and missing validation.
9. After a failed Git operation, diagnose before retrying. Do not use increasingly destructive commands to force progress.

## Done criteria

- The working tree and index contain only intended changes; unowned work is untouched.
- The diff is reviewable and does not mix unrelated mechanical and semantic edits.
- Any destructive or history-changing operation was explicitly authorized and has a recovery path.
- Commits are coherent, paths were staged explicitly, and messages describe the actual change.
- Publication notes state validation and material risks accurately.
