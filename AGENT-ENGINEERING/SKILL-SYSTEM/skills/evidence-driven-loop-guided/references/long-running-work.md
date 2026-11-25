# Long-Running Work

Externalize the small amount of state needed to resume correctly. Do not turn
the campaign into a permanent service merely because conversation context can
compact.

## Keep an authoritative evidence trail

Preserve raw task output outside the conversation when it is too large or too
important to summarize. Inspect it with targeted queries, parsers, diffs, and
small derived reports. Record paths and commands needed to reproduce a
conclusion; do not copy entire logs into context.

Use existing repository conventions first. If none exist, a task-local note is
often enough. It should make the following recoverable without imposing a
machine schema:

- objective, hard gates, primary measure, budget, and authority boundary;
- exact baseline and current-best comparison protocol;
- confirmed findings, tentative hypotheses, and ruled-out explanations;
- last prediction, action, exact observation, and interpretation;
- material artifacts or helper scripts and how to reproduce them; and
- next predicted action and why it has information value.

Update the note after evidence changes the task model, not after every trivial
command. Raw logs remain authoritative; the note is an index and current
theory.

## Resume from evidence, not narrative momentum

At the start of a new session or handoff:

1. read the current task contract and the format of stored evidence;
2. verify that the named baseline, current best, artifacts, evaluator, and
   environment still exist;
3. inspect the last decisive raw observation;
4. restate the current model and predict the next result; and
5. run a cheap orientation check before spending a large remaining budget.

Do not continue an old plan merely because it was written down. Invalidate it
when code, data, dependencies, evaluator behavior, user priorities, or the
available environment have changed.

## Make expensive work resumable only when it earns the cost

For training, search, compilation, or large benchmarks, checkpoint at natural
transaction boundaries. Record enough configuration and provenance to decide
whether a checkpoint is comparable and safe to resume. Test recovery early if
losing the run would be material.

Do not add a queue, daemon, database, lease protocol, or distributed scheduler
unless the task already requires one or repeated campaigns demonstrate a
stable operational seam. A local process and a durable note are usually the
right first implementation.

## Handoff state precisely

State what is observed, inferred, and still unknown. Include budget consumed,
running or external processes, partial side effects, cleanup obligations, and
the exact stop or authority condition. Never imply that a process is still
being monitored after the agent has yielded unless an actual monitoring
mechanism owns it.
