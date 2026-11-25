---
argument-hint: <what to assess> [partners: <launchers>] [summarizers: <launchers>]
description: Assess a subject with named agents as design partners and summarizers, tracked in a learning workspace, and write the result to PLANS/
---

Assess: $ARGUMENTS

How to run it:

- **Agents.** Use the agents named after "partners" as design partners: second opinions,
  a sounding board, and checks on your reasoning. Use the agents named after
  "summarizers" for lower-level searches and summaries, as many as needed. Use only the
  agents named here, and if none are named, do the work yourself. Launch them through the
  delegate adapter and read `~/.agents/skills/delegate/SKILL.md` before the first launch.
  Give each agent the context and guidance it needs to understand the nuance of what you
  need, passing `hist` refs rather than pasted transcript. Treat what they return as
  evidence to verify, not as conclusions.
- **Your role.** You are not merely an orchestrator. You are principally responsible for
  understanding my intent, integrating the partners' advice, pushing back on calls for
  overengineering, and making the final recommendation the highest quality it can be.
- **Tracking.** Use the learning-workspace skill to track insights and investigative work,
  and to coordinate with the agents.
- **Output.** Put the assessment, recommendations and plan in a new document in the
  `PLANS` folder (a subfolder with an index when there are several documents).
- **Scope.** Unless the request above asks for changes, this is analysis: change nothing
  except the `PLANS` document and the workspace.
