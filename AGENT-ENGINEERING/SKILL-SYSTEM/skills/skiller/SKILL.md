---
name: skiller
description: "Recommend which installed skills a task, plan, or implementation should use, and at which step, from a live catalog of every skill's brief description. Use only when the user invokes $skiller or /skiller, often during intent, grilling, or plan creation, to choose the skills to name in the plan; do not use to run the recommended skills, review a skill, or find external skills to install."
disable-model-invocation: true
---

# Skiller

Recommend the few installed skills that would change how this work gets done,
and the step where each belongs, so they can be named in the plan before
implementation starts. This is advice: it never invokes, launches, or edits a
skill.

## Read the work

Work from what the conversation has settled: the request, an Intent Brief, the
decisions from a grilling round, a plan and its steps. Read the plan file when
one exists. Ask one question only if the work itself is unknown.

When invoked inside another skill's session (`intent`, `grilling`,
`batch-grill`, plan writing), give the recommendation, then resume that session
where it left off; do not end the interview. Mark a recommendation that depends
on a decision still open as conditional on it.

## Read the catalog

Run `~/.agents/skills/skiller/scripts/catalog`. It prints one line per installed
skill, read live: name, `explicit` or `auto`, and the skill's brief
description. Read every line. Do not choose from memory or from your own skill
list: hosts leave explicit-only skills out of it, and most of the library is
explicit-only.

1. Shortlist the skills whose brief description fits a step of the work.
2. Run `catalog <name>...` on the shortlist to read each one's full
   description. Drop any whose trigger is not met or whose "do not use" clause
   matches.
3. Read a shortlisted skill's `SKILL.md` only when its description leaves its
   fit, or its order relative to another skill, unclear.

`catalog --full` prints every full description (about 25 KB); use it only when
the brief lines are too thin to shortlist from.

## Choose few

- Recommend a skill only where it changes what is done at that step: a
  contract, a check, an artifact, or a gate the step would otherwise lack. A
  skill that would only restate what the step already does gets no row.
- When two skills overlap, pick one and give the reason in a line.
- Keep the order the descriptions imply, such as `frame-change` before
  `architecture-plan` and `verify-change` after implementation.
- Recommend only skills the catalog lists. When a need has no skill, say so;
  propose a new skill only if asked.

## Answer

**Recommended skills**, one row per skill, in the order the work reaches them:

| Step | Skill | Mode | Why here |
| --- | --- | --- | --- |

- **Step:** the plan step or phase, or the moment: before design, during
  implementation, before calling it done.
- **Mode:** an `auto` skill loads itself when the step matches; naming it in the
  plan makes that certain. An `explicit` skill runs only when invoked by name,
  so give the invocation for the user to type at that step: `$name` in Codex,
  `/name` in Claude Code.
- **Why here:** what it adds at that step, in one line.

Write each row so it can be pasted into the plan step it names. Then, only when
they apply:

- **Close calls:** up to three skills left out where the choice is not obvious,
  each with its reason.
- **Gaps:** a need that no installed skill covers.

Give the answer in the conversation. Add it to a plan document only when the
user asks or the surrounding workflow is already writing that document.
