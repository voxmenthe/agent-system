---
name: catchup
description: On the owner's return to a long session, report from live sources what changed since their last message, what needs their decision, and what is still running. Use only when the user invokes $catchup or /catchup; do not use for ordinary status questions, progress updates, or a summary of one result.
disable-model-invocation: true
---

# Catch up

The owner is back in a session that kept working while they were away. Tell
them what changed, what needs them, and what is still running, from evidence
read now. This is a report: it never acts, launches, retries, or decides.

## Find the boundary

The boundary is the owner's last real message before this invocation.
Everything after it is in scope.

1. `hist read self --kind human --tail 12` lists the recent user messages.
   Walk back from the newest and skip:
   - this invocation (`/catchup`, `$catchup`);
   - host commands, such as `/compact`, `/effort`, `/model` and `/clear`;
   - text the host or another agent wrote: task notifications
     (`<task-notification>`, `[SYSTEM NOTIFICATION`), inter-session messages
     ("Another Claude session sent a message"), and injected context
     (`<system-reminder>`, `<hist>`).

   The first message left is the boundary. Quote its opening words in the
   answer, so the owner sees where you started.
2. `hist read self --after <boundary ref>` gives the session since then. Page
   it with `--tail`. It shows what was done, not that it worked.
3. Workers are separate sessions, and `read --after` leaves them out.
   `hist find "hist-parent" --session self --kind user` lists the workers this
   session started; `hist sessions --workers` gives their times, so keep the
   ones active after the boundary. `hist read <alias> --tail 1 --kind agent`
   is a worker's final answer. Kimi and Grok workers are not indexed: for them,
   and for market runs, read the run's own outputs (`mkt delegates WORKDIR
   --status`, the wave directory), and say that `hist` coverage is incomplete.

## Check the live sources

Read each one now, not from the transcript:

- each wave directory the session used:
  `~/.agents/skills/delegate/scripts/wave-status <jobs-dir>`;
- the active learning workspace's `notes.md`: Current frontier, Resume state
  and live warnings;
- `git status --short` in each repository the session touched, and the commits
  made since the boundary;
- every PR, CI run, or background process the session started, in its current
  state (`gh pr view`, `gh run view`, `ps -p <pid>`).

A source that cannot be read goes under **Not checked**, with the reason.

## Answer in this order

1. **Changed.** A few lines on what was done since the boundary, each with its
   evidence (a test run, a file, a published artifact). Keep verified work
   apart from work that is done but unverified.
2. **Needs you.** Numbered questions that only the owner can answer, each
   readable on its own. Each gives the recommended option first, then the
   others; the reason, and who backs it (you, a reviewer, a worker, a source);
   what stays blocked until they answer; and the reply syntax, for example
   `1 A, 2 done`. If nothing needs them, say so.
3. **Running.** Counts of the workers, waves, and processes still going, then
   each one that is blocked or failed, with its failure class from the fleet
   view.
4. **Not checked.** Each source you could not read, and why.

## Never

- Invent a decision, or present a settled one as open.
- Drop an item to stay short; shorten the items instead.
- Put work you can still do yourself under Needs you. Say it is next instead.
- Act, retry, relaunch, or commit on the strength of this report. Wait for the
  owner's reply.
