---
name: batch-grill
description: Conduct a breadth-first decision interview that finds and settles the smallest set of high-leverage unresolved choices shaping a consequential plan, design, specification, or strategy. Use when the user explicitly invokes $batch-grill or asks to resolve a decision frontier. Do not use for routine clarification, initial intent discovery, single-issue depth-first probing, or facts the agent can inspect.
disable-model-invocation: true
---

# Batch Grill

Turn a consequential but partly specified idea into a decision-ready direction.
Conduct a breadth-first interview: form a top-down model of the choices that
shape the result, ask the highest-leverage independent choices that can be
settled now in one numbered round, then use the answers to expose the next
frontier.

The goal is not comprehensive requirements gathering. Find the smallest set of
answers that prevents a major wrong direction, costly rework, or a silent
assumption about scope, authority, risk, or success.

## Keep the boundary narrow

- Use ordinary discussion for one or two local questions. Use a depth-first
  grilling workflow when one answer must be explored before any other useful
  question can be asked.
- Inspect available files, tools, prior decisions, and runtime evidence before
  asking the user for a fact. Ask the user for judgments, preferences,
  priorities, and authority that only they can supply.
- Do not require delegation. Use another agent or tool only when it is actually
  available and materially useful.
- This is an interview and decision-summary workflow. Do not edit files,
  publish artifacts, create tickets, or implement the resulting plan unless
  the user separately authorizes that action.

## Find the real frontier

Start by forming a private current theory of the decision target, plausible
directions, hard constraints, major failure modes, and established decisions.
Use outcome, scope, authority, risk, compatibility, transition, and evidence as
diagnostic lenses, not as questionnaire headings. Do not ask a question merely
to fill one of those categories.

Generate candidate decisions from the top down. The **frontier** is not every
unanswered question whose prerequisites happen to be settled. It is the
highest-leverage unresolved decision on each independent branch whose
prerequisites are settled. A child decision does not join the frontier while
an unresolved parent could eliminate it, reframe it, or determine a safe
default for it.

Before retaining a candidate question, privately complete this sentence:

> If the answer were A rather than B, we would change ______.

Reject the question when the blank is vague or changes only naming, tuning,
layout, wording, or another local implementation detail. Ask only when all of
these are true:

1. At least two materially different answers remain plausible.
2. The answers would change the solution family, scope, success criterion,
   authority boundary, risk posture, compatibility strategy, or several
   important downstream choices; alternatively, the answer would prevent one
   costly or hard-to-reverse failure.
3. Available context and evidence do not already answer it, and no safe,
   inexpensive, reversible default makes the question unnecessary now.
4. The user is uniquely positioned to supply the judgment or authority.
5. No unresolved higher-level decision on the same branch could make the
   question disappear or substantially change its meaning.

Prefer questions with the greatest:

`downstream reach × uncertainty × cost of a wrong assumption × separation between plausible answers ÷ user effort`

Do not calculate a score mechanically. Use the expression to reject low-yield
questions and to order the remaining frontier.

Lift premature implementation questions to the governing decision they stand
in for:

| Premature detail | Governing decision |
| --- | --- |
| “Which database?” | What durability, concurrency, recovery, and operating constraints select a storage family? |
| “How many retries?” | Which failures are safe to repeat, and what side effects must be idempotent? |
| “Which UI control?” | What authority or review boundary must the interaction enforce? |

Ask an implementation choice directly only when its governing constraints are
settled and the choice is itself costly to reverse or needed immediately.

Merge decision-equivalent questions and discard speculative branches. Resolve
accessible facts yourself. An unresolved fact blocks only the decisions that
depend on it; continue with independent frontier decisions. Keep the internal
graph only as detailed as needed to choose the next round, and do not expose a
large speculative tree as ceremony.

## Ask frontier rounds

For each round:

1. Ask as few questions as earn their place, often two to five and never more
   than eight. If one hinge decision dominates, ask only that one. If more than
   eight qualify, ask the subset with the greatest branch-elimination power or
   irreversible risk and state that lower-leverage decisions remain.
2. Do not place two questions in the same round when one answer could change
   the other question or its useful options.
3. Ask one decision per number. Include the current recommendation or
   provisional read and one short consequence statement naming what would
   change if the user chose differently. Add options only when they clarify a
   real fork.
4. Let the user answer tersely by number, accept a stated default, or mark an
   item unknown or deferred. Do not infer more commitment than the response
   supports.
5. Reconcile the answers with prior decisions, surface any real contradiction,
   and recompute the frontier. Do not reopen a settled decision without new
   evidence or a downstream conflict.

If no frontier-level decision exists, do not manufacture questions.

## Stop deliberately

Stop when any of these conditions holds:

- no unresolved frontier-level decision blocks a usable result;
- remaining items are reversible implementation details or are explicitly
  deferred with a known consequence; or
- the user asks to stop or summarize.

Do not try to visit every imaginable branch. After three substantive rounds,
summarize progress, identify the remaining hinge decisions, and ask whether
another round is worth the added effort.

## Return a decision map

At the stopping point, provide a compact decision map containing:

- the objective and load-bearing constraints;
- settled decisions with brief rationale;
- unresolved or deferred decisions and what they block;
- assumptions, evidence gaps, and material risks; and
- the next authorized decision or action, if one is clear.

Distinguish what the user decided from facts observed and conclusions inferred.
Do not present a deferred choice as settled.
