---
argument-hint: <what parts of the repo to focus on, what feedback/recommendations we want>
description: Build a dense context bundle under PLANS/PREPARED_CONTEXT/ for a remote model or reviewer without repo access
allowed-tools: Bash, Read, Write, Glob, Grep, Task
---

Read and follow the full orchestration instructions in:
`~/.claude/skills/prepare-context/SKILL.md`

First, choose a short descriptive title for this context bundle based on the user's request
(e.g. "auth-refactor-review" or "api-design-feedback"). Then resolve the request:

```bash
python3 ~/.claude/skills/prepare-context/scripts/resolve_prepare_context.py --create-output-dir --title "<descriptive-title>" "<full free-form input text>"
```

The entire input is a free-form focus/feedback request describing what parts of the repo
to analyze and what feedback is needed. The resolver defaults to the current repo root.

Use the generated manifest as the workflow seam for:
- the canonical output directory under `PLANS/PREPARED_CONTEXT/{timestamp}-{title}-{id}/`
- the request summary path plus one component file path per sub-agent
- repo structure summary (directory tree, file stats, key files)
- search roots, ignore rules, and starter file candidates for task overview, plan context, commit context, and code context
- an `always_consider` block covering recent plans and commit narratives (when available)
- recommended tools for deeper repo exploration (coderank, kit, search_estimate)
- the final bundle assembly order

The workflow should spawn one `context-preparer` sub-agent per component file, give each
agent the manifest's starter files as anchors rather than ground truth, let the agents use
their own search judgment (including the recommended tools) inside the provided roots, and
only then concatenate the components into the final `*_prepared_context.md` bundle.
