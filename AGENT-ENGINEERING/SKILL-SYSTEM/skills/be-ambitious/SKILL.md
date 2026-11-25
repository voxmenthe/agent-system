---
name: be-ambitious
description: "Do what a task or prompt asks, above and beyond, with Felix Rieseberg's types of ambition: Altitude infers the intent behind the request, Depth works like the field's best from the raw material, and Range brings in other fields doing what their experts do, with an outside judge for the result. Always delivers the request itself; may add a short, verified side project, and suggests a bigger version, building it only when a multi-session skill is also named. Use when the user invokes $be-ambitious; do not use it unasked."
disable-model-invocation: true
---

# Be ambitious

Most tasks are done at the size they were typed. Models are "astounding in
some directions, while inadequate in others" (Terence Tao), and the way to
find the astounding parts is to aim higher than feels reasonable. Do what
was asked the way the field's best would, given what it is for. Let
something other than you check it. Then bring back the better version you
saw along the way.

The method is Felix Rieseberg's, from [How to be more ambitious: a tutorial
for humans with models](https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/)
(13 Oct 2026); see [NOTICE](NOTICE.md). Worked examples, and prompts that
combine this skill with others, are in [examples](references/examples.md).

> Use when the user invokes `$be-ambitious` to raise the aim of a task or
> prompt.

## The rule

**Do what was asked, above and beyond, and let an outside judge show it.
Anything past the request comes alongside it, never in its place.**

- **The request is the main work.** Deliver it recognizably: the same
  deliverable, at no less than the same scope, so anyone can point at the
  result and see it was done. If you think it is the wrong thing, still do
  it, and say why in the report.
- **Above and beyond, inside the request.** Let what the request is for
  decide how well it is done: the field's methods, the raw material,
  targets near the limit. Better, not bigger: every addition serves the
  request.
- **Infer the intent; don't interrogate.** Work it out from the evidence,
  state it in one line as an assumption, and go on. Never hold up the
  request to ask about it.
- **Past the request: alongside, never instead.** A better version you can
  build and check this session is a side project. Anything bigger is a
  suggestion, built only when the user's invocation sets up a long run.
- **Methods, not voices.** Bringing in a field means using its methods and
  instruments. New vocabulary on the old method is role play: the
  transcript gets stranger and the result stays the same.
- **An outside judge.** For the delivered work, the side project and every
  part of a bigger version, something other than you or the user shows the
  result is right: a test, a benchmark, a reproduction, held-out data, a
  measurement, or fresh judges when only judgment can decide. Prefer a
  measurement when one exists. Never grade your own work.
- **Aim hard; never fake.** Specific hard targets beat "do your best";
  assume they can be met, and report a miss in real numbers. A
  reconstruction checked against outside evidence is an instrument; an
  invented source, tool or result is not.
- **The standard rises; the permissions don't.** Invoking this skill
  authorizes a higher standard, not new kinds of action. Ask before a step
  that spends money, launches agents the user did not name, or can't be
  undone.

## Input

The task is whatever follows `$be-ambitious`. With nothing after it, use
the user's most recent request; with no request either, ask for the task
in one line and stop.

Then decide what you were handed:

- **A task to do** (fix, build, analyse, write): do the main work, then any
  side project. Build a bigger version only if the invocation sets up a
  long run.
- **A prompt to improve** (a rewrite request, or a task meant for another
  agent, a worker packet or another skill's brief): stop after the
  rewritten prompt.

If you can't tell which, treat it as a prompt.

## Infer the intent

Work out what the request is for before starting it. Read the evidence
first: the conversation, the repository with its plans, notes and results,
and past sessions when a history tool exists. Write the intent in one line,
mark it as your inference, and go on.

Reach for what the user actually cares about, often a step or two above the
request: a question answered for good, a capability, an outcome that stays
true. Two examples:

- "Summarize today's gamma levels" serves knowing how and when prices react
  to dealer hedging exposure, and under what circumstances.
- More variants for an RL task serve an environment where reward comes only
  from genuine research.

An intent you can't tie to the evidence stays modest, and you say so.

The intent then does three jobs:

- it decides how well the request is done: the gamma summary says which
  levels have held, which have broken, and when;
- it points to a side project: a better version of the thing itself;
- it frames the bigger version, if there is one.

Ask about the intent only when the uncertainty is extreme and a long build
depends on it; then ask in one line, before that build. Creative work often
has no intent beyond itself; then raise its standard and its perspectives
instead.

## Do the request, above and beyond

This is the main work, and it comes first. Deliver the request itself, and
make it the version the field's best would be proud of:

- shaped by the intent;
- worked like an expert, from the raw material (Depth);
- through other fields where the request needs them (Range);
- aimed near the limit, as a floor with a quality bar: "50 new variants,
  each surviving confirmation and a red-team probe", not "up to 50";
- checked by an outside judge.

Stay inside the request: a reviewer should see every addition as part of
doing it well. Sometimes something you need doesn't exist, such as data or
a tool:

- if a validated approximation fits the session, build it;
- otherwise, do the best the existing material allows, and name what is
  missing and what it would unlock.

Building the missing piece itself belongs to a side project or the bigger
version.

Speed, the same work in less time, is how most people already use models;
skip it.

### Depth: work like the field's best

Go one level below the request, to its raw data, tools and problems, and
keep going until the field's best could learn something from the work.

- **Use the expert's instruments.** Where you'd reach for a markdown table,
  a top data scientist reaches for a database and a statistical model. The
  user needn't know what experts use; you usually do.
- **Aim near the limit, and treat it as reasonable.** Ask what the
  hardware, the data or the field's best could reach, and aim there:
  usually an order of magnitude past the ask, not a percentage. The page
  takes 10 seconds and the user asked for 5: aim for 200 milliseconds.
- **Challenge what everyone believes.** Take the raw data and try to
  reproduce the belief: "We believe churn is an onboarding problem. Try to
  reproduce that from the raw data."
- **Produce new knowledge.** Once deep in the data, look for what nobody
  knows yet, and show it holds on data it has not seen.

Run every Depth pass through Felix's prompt:

> I want a deeper version of this task, not a bigger one. Before rewriting
> it: (1) say what a top professional in this field would do here that I'm
> not asking for; (2) name the rawest material they would start from
> instead of what has already been digested for me; (3) name the specific
> methods and tools they would use; (4) say what, other than you or me,
> would show the result is right. Then rewrite my prompt to ask for exactly
> that.

Leave the choices that are the user's to make open rather than deciding
them.

### Range: bring in other fields

Look at the work through more fields than used to be affordable.

- **Replace the nouns with verbs** (Kelley and Littman, *The Art of
  Innovation*). A quarterly review isn't "a deck"; it is getting busy
  people to believe a story about cause and effect, and to decide under
  uncertainty, in 30 minutes. The verbs show which fields can help.
- **Assemble the crew.** Raise the stakes until you'd send the best: for
  quality, an analyst, a journalist and an editor; to present it, a motion
  designer; as a red team, a short seller and a forensic accountant.
- **Borrow their tools.** A field brings its software, not only its ideas:
  a 3D tool to render an interior, a statistics package for an analysis.
- **Do, don't play.** Don't write like a short seller; do what a short
  seller does to research a position. Give each field a job, the method or
  tool it uses, and the output it hands back.

## Go beyond, alongside

Two things can come with the main work, never in its place.

**A side project** (optional; your call). It is one of two things:

- a better but still recognizable version of the thing itself, better by
  construction rather than bigger;
- the riskiest first step of the bigger version.

Take it on only if it can be finished and checked this session:

- after the request is delivered, or beside it without delaying it;
- kept apart from the delivered work, in its own worktree or folder;
- with its own outside judge, comparing it with the original.

If the judge passes, bring it back as a suggestion with its results. If it
doesn't, or it won't fit the session, say in one line what you tried or
would try, and what would settle it.

For example, asked for more variants of an RL task:

1. Deliver the variants, each built so reward hacking and brute force pay
   as little as the task allows.
2. On the side, change the task so that neither can pay, by construction.
3. Show that a red-team agent beats the original but not the change.
4. Suggest the change.

**The bigger version.** This is what would serve the intent completely,
further than the user pictured. Its end state does at least one of these:

- takes the person out of the loop: a system that keeps the intent served
  without being asked (Felix went from fixing single crashes to keeping his
  apps crash-free);
- makes the class of problem impossible, by construction;
- runs beside the ritual the request belongs to until it is shown to work
  better. For Felix's quarterly deck: design a better way to catch problems
  early, show from history it would have caught them sooner, and run it
  beside the deck for a quarter;
- produces knowledge nobody has, shown to hold on data it has not seen.

Plan it as a whole, each part with its judge:

1. **Must be.** The properties that would make the intent true, written as
   a spec.
2. **Needs.** What doesn't exist yet (data, instruments, a design), and how
   it gets built or reconstructed and validated, live if the intent is
   live. Before Claude could keep Felix's apps crash-free, it needed the
   crash reports, a map from app versions to commits, and machines to
   reproduce and verify fixes on every platform. A missing input is part of
   the plan, never a reason to aim lower.
3. **Learned.** What must be found out, and under which conditions, not on
   average.
4. **Working whole.** The complete thing that keeps serving the intent.

A part with no judge yet stays in the plan, marked with what its judge
would need. Know the ceiling: "go make money" is still too high for most
businesses.

Suggest it with a rewritten prompt that launches it. Build it yourself only
when the user's invocation also names a multi-session skill
(`learning-workspace`, `solutionize` or one of the evidence loops). Even
then, build it only after the request is delivered, under that skill's
rules: its thinnest end-to-end version first, then one part at a time.

## Check the aim

Before starting, test the plan in both directions.

The aim is too low if:

- a competent professional would have done the request this way anyway,
  unprompted;
- the intent only restates the request;
- a missing input made you settle without saying what it would unlock;
- a target is a percentage rather than a step toward the limit;
- a bigger version you name ends in a report, not something that keeps
  working or is right by construction.

It has gone too far if:

- the request isn't recognizably delivered: a different deliverable, a
  narrower one, or one deferred behind other work;
- part of the main work doesn't serve the request;
- a side project can't finish this session, or touches the delivered work;
- a long build is about to start that the invocation didn't set up.

Fix whichever holds, and keep every judge.

## Output

Size it to the task. For a one-line prompt, a few lines of plan: the
rewrite is the product. In this order:

1. **Asked**, as given, and the **intent**, in one line marked as your
   inference.
2. **Above and beyond**: how the request will be done:
   - for Depth, the four answers and a target near the limit;
   - the Range crew as field, job, method or tool, and output;
   - the judge.
3. **Needs**: data, tools and access, each marked there or missing. For
   each missing one, how it is approximated now, or what it would unlock.
4. **Alongside**:
   - the side project, if any, with its judge;
   - the bigger version, if any: its end state, its parts and their
     judges, and whether it will be suggested or built.
5. **Rewritten prompt**, in one fenced block the user can copy, written the
   way they would type it. It keeps the original ask intact, asks for it
   above and beyond, and ends with the judges and what counts as a pass.
   For another agent, it may add the side project as an optional, bounded
   section.
6. **Next**: the main work, and the skill that should run it when another
   fits (see "With other skills"). For a prompt, stop here.

## Finish a task

Report in this order, so both halves are visible:

1. **Asked → delivered**: the request, and the judge's evidence that it is
   done.
2. **Above and beyond**: what the work did past a competent version, each
   judge's result in real numbers, and what was missed, by how much.
3. **Side project**: its judge's result and the suggestion, or one line on
   why there isn't one.
4. **Bigger version**: suggested, with its plan and launch prompt; or, if
   you are building it, where it stopped and what the next step needs.

Before reporting a hit, check that the result does not special-case what
the judge measures. Hard targets make that tempting.

## With other skills

The rewritten prompt is a contract another skill can run: the request,
above and beyond, with its judges and a pass condition.

- Name the skill that fits in **Next** and in the rewrite.
- Run an explicit-only skill only when the user's invocation named it.
- Skills that may load on their own follow their own rules.

Prompts that combine skills are in [examples](references/examples.md).

| When | Skill | What it takes from the plan |
| --- | --- | --- |
| The work will outlive this session | `learning-workspace` | The request and intent in `Task contract`, with the judge of the part being worked as the terminal condition; challenged beliefs and reconstructions as hypothesis claims with grounding checks; the side project and bigger version in the frontier, and suggestions in owed decisions; `be-ambitious` among the skills to reread |
| A target is known to have been reached elsewhere | `solutionize` | The target as the problem, its judge as the frozen check, what is known about who reached it |
| Several models should each attempt the work | `council` | The rewrite as its task |
| One model's reading may be too narrow, and the stakes justify several | `council` | A task telling each panelist to read this skill and apply it in prompt mode. The plans are judged on how far each goes above and beyond while still delivering the request, with judges that can actually run |
| The bigger version is a new system whose key parts may not be feasible | `greenfield` | Each uncertain part as a feasibility question with its verdict |
| A part is an improvement campaign with a measured judge | `evidence-driven-loop-minimal` for a short loop, `evidence-driven-loop-guided` for a campaign, `evidence-driven-loop-instrumented` for a long, auditable one | The target as the outcome, the judge as the evaluator, a baseline to measure first |
| Only judgment can say whether a part is better | `evidence-driven-loop-judged` | The part as the task, and the criteria the judges compare on |
| A part is an open design question | `fanout` | The question, or Range's verbs |
| The crew or the spikes need separate workers | `orchestrate` (native) or `delegate` (external) | One packet per field or spike: its job, its method or tool, and its output |
| A judge doesn't exist yet | `create-verification-skill` | What must be launched, driven and observed |
| A part is a nontrivial code change | `frame-change` | The part as the outcome, its judge as acceptance evidence |

## Why this works

People do more when they believe the hard thing is possible. George
Dantzig solved two open statistics problems in 1939 because he took them
for homework, and the four-minute mile fell again 46 days after Bannister
ran it. The same holds for the model: say the hard thing is possible, and
permit failure against an honest judge.
