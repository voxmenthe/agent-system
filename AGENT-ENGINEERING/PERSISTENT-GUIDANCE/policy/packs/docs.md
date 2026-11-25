# Documentation and prose

## Applies when

Load this pack before changing Markdown, README files, setup/run instructions, architecture or process docs, comments, docstrings, CLI help, durable review notes, or other user- or maintainer-facing prose.

## Does not apply when

Do not load it for ephemeral chat explanation that will not become repository content, unless the task is specifically to design documentation policy.

## Non-negotiable rules

- Source code should explain what through names and structure; do not trade verification or measured performance for linear reading. Comments explain only non-obvious why, constraints, invariants an optimization relies on, stratification, or workarounds.
- Default to no comment. When needed, prefer one short line. Multi-paragraph history belongs in Markdown or design records, not source.
- Do not put dates, ticket IDs, commit narratives, or incident walls of text in source comments.
- Docstrings exist only for caller-visible contracts that change how callers use the code; skip them when the name and types already say enough.
- Setup instructions must work from a fresh clone. Do not depend on undeclared laptop state, absolute paths outside the repository, or an environment that the setup command never creates.
- Maintain one authoritative source for each policy or workflow. Mirrors must link to or explicitly summarize the authority and be updated together.

## Procedure

1. Identify the audience and the decision or action the document must support. Delete content that does not change understanding or action.
2. Keep explanation local to what it governs, but move extensive rationale into a nearby `CHOICES.md`, `PROCESS.md`, architecture decision record, or focused design document.
3. For setup, target a simple `make setup` and `make run` experience when appropriate. More than two essential commands needs a reason. If `.venv` or equivalent is expected, setup creates it reproducibly.
4. Give long docs progressive detail: roughly 3 lines to run it, 20 lines to understand development setup, and 50 lines to start changing it. Prefer one end-to-end workflow over an inventory of every flag.
5. Use environment variables or flags with sane documented defaults; never instruct users to edit `.env`. Provide a commented `.env.example` without secrets. If the normal command needs many required arguments, decide which are policy/defaults rather than documenting accidental complexity; usually only the target and authentication remain truly required.
6. Write current-state documentation. Put historical alternatives in an explicit “Alternatives considered” section or version control, not mixed into operating instructions.
7. Apply the deletion test to prose. Remove throat-clearing, fossil phrases, duplicated code descriptions, and weaker restatements. Preserve evidence, constraints, tradeoffs, uncertainty, and exact identifiers that affect decisions.
8. Use established domain terminology when it is precise and define it briefly when the audience may not know it. For a non-obvious module or workflow, point to the existing command that runs or probes it and the result to expect.
9. Verify every command, path, configuration key, API name, and version-sensitive claim against the current repository or official source.

## Done criteria

- A fresh reader can perform the documented workflow without hidden state or unexplained paths.
- Comments and docstrings add caller-relevant rationale rather than narrating code.
- The document has an explicit source of truth and no conflicting duplicate instructions.
- Commands and technical claims were verified; uncertainty is labeled rather than papered over.
- Prose is concise without deleting distinctions that affect implementation or decisions.
