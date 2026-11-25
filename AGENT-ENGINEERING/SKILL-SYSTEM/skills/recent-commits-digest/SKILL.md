---
name: recent-commits-digest
description: Return recent one-line commit summaries with optional path filters. Use when asked to pull and catch up or list recent history; do not use for diff review or resolving diverged branches.
---

# Recent Commits Digest

Use the [digest helper script](scripts/recent_commits_digest.py) from the target repository. Set `skill_dir` to the directory containing this loaded `SKILL.md`.

```bash
uv run --no-project python "$skill_dir/scripts/recent_commits_digest.py" -n 5 --path src
```

Default count is five. Omit `--path` for all commits; repeat it for multiple paths. Use `--no-pull` for history-only requests or when the requested pull already completed. Listing history alone does not authorize pulling.

When pulling was requested, the helper runs `git pull --ff-only` against the current branch's configured upstream. It reports whether HEAD advanced and lists recent commits; the list is not limited to newly pulled commits. On failure, stop and report the actual error. Do not merge, rebase, reset, stash, or change upstream configuration to force progress.

Return pull status and compact bullets of `<sha> <title>`. Retain path/count filters. Do not read diffs, add author/date columns, or expand into recommendations unless requested.
