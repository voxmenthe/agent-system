# Examples

Read these to calibrate both tracks:

- how far above and beyond the main work goes while staying the thing that
  was asked;
- what comes alongside it.

Each starts from an ordinary request. In every one, the request is
delivered first and recognizably, and everything bigger comes with it,
never instead of it.

## Gamma levels (task mode)

`$be-ambitious summarize today's gamma levels for ES`

- **Asked:** today's gamma levels for ES, summarized.
- **Intent (inferred):** know how and when prices react to dealer hedging
  exposure, and under what circumstances. The summary is read before
  trading; nobody needs the levels for their own sake.
- **Above and beyond:** the summary, built from open interest by strike
  rather than anyone's published levels. For each level:
  - its exposure sign and size, and the change since yesterday;
  - how price has behaved at comparable levels in the history we have:
    how often it held, how often it broke, and under which conditions
    (time of day, realized volatility, the share of same-day options);
  - a stated probability that it holds today, logged and scored tomorrow.
- **Depth:**
  - rawest material: open interest by strike and futures minute bars, not
    published levels;
  - instruments: an exposure engine, and an event study with a bootstrap
    null;
  - start from the literature on expiration pinning (Ni, Pearson and
    Poteshman, 2005) and on hedging demand and intraday momentum
    (Baltussen, Da, Lammers and Martens, 2021);
  - the belief to challenge: "gamma levels act as support and resistance".
    The event study says when they do, and when they don't.
- **Judges:** the event study against levels placed at random strikes, and
  tomorrow's scoring of today's stated probabilities.
- **Needs:**
  - futures minute bars: there (ChartLab);
  - daily open interest by strike: there (the free Cboe and OCC data the
    SPX report uses);
  - historical option trades with quotes: missing, and some is paid;
  - live option prints: partly there, through IBKR for near-the-money
    strikes.
- **Side project (this session):** the riskiest piece of the bigger
  version. Can dealer positioning be reconstructed from the data we already
  have? Build a crude estimate and check it on one month. Does it reproduce
  the documented effects of dealer hedging: narrower intraday ranges when
  dealers are long gamma, and pinning near large open interest into expiry?
  Bring back the result either way.
- **Bigger version (suggested):** a validated, live read of dealer exposure.
  During the session it says where price is likely to bounce and where it
  is likely to break, and it keeps its own scored track record.
  - *Needs:* dealer positioning reconstructed from option trades,
    over history first, then live:
    1. classify each trade by aggressor side against the quote (Lee–Ready
       style);
    2. track opening positions by strike and expiry;
    3. net them to dealer inventory;
    4. compute gamma, charm and vanna exposure.

    Judge: independent participant data where it can be had (some is
    paid: ask first), and the documented effects reproduced out of sample.
  - *Learned:* when price bounces and when it breaks.
    - An event study of every approach to a level, conditioned on
      exposure, expiry mix, time of day, volatility, approach speed, order
      flow and scheduled events.
    - A walk-forward model of bounce versus break.

    Judge: calibration and discrimination on held-out months against two
    baselines (random levels, and the model without exposure), plus a
    simulation with trading costs.
  - *Working whole:*
    - streaming reconstruction, updating probabilities, and a ChartLab
      panel with alerts;
    - every prediction scored the next morning;
    - walk-forward retraining and drift alarms.

    Judge: eight unattended live weeks matching the backtest's calibration.
  - *Range crew:*
    - an options market maker specifies how a dealer book hedges across
      expiries, and returns the hedging rules the engine implements;
    - a market-microstructure researcher designs the event study and its
      null, and returns bounce and break rates by condition, with
      intervals;
    - a streaming-systems engineer builds the live path, and returns
      end-to-end latency under load;
    - a forecaster scores every live call with proper scoring rules, and
      returns the track record.
  - *Launch:* `$be-ambitious $learning-workspace build a validated, live read of dealer hedging exposure for ES that predicts where price bounces and where it breaks.`
- **Rewritten prompt:**

  ```text
  Summarize today's gamma levels for ES. Build them from open interest by
  strike, not published levels. For each level give its exposure sign and
  size, the change since yesterday, how often comparable levels have held
  or broken in our history and under which conditions, and a probability
  that it holds today. Log the probabilities.
  Pass = the event study beats levels at random strikes, and tomorrow's
  scoring of today's probabilities is recorded.
  ```

- **Next:** the summary.

With a long run set up, `$be-ambitious $learning-workspace summarize
today's gamma levels for ES` delivers the same summary and side project.
It then goes on to build the bigger version across sessions:

1. a crude reconstruction, a simple event study and a basic live panel,
   end to end;
2. then the reconstruction, deepened.

Buying data still waits for the user.

## An RL environment (task mode)

`$be-ambitious generate more variants for the boundary-edit task`

- **Asked:** more variants of the boundary-edit task.
- **Intent (inferred):** an environment where reward comes from the agent
  actually accomplishing interesting tasks, working the way a true
  researcher does. The user has set the bar for variants before: likely
  to survive confirmation as KEEP.
- **Above and beyond:** at least as many variants as asked, each built so
  reward hacking and brute force pay as little as the current task allows:
  - every variant survives the task's own confirmation as KEEP;
  - before delivery, a red-team agent tries to earn reward on each variant
    without solving it, and a brute-force agent tries to enumerate it
    within the budget. Variants either agent beats are fixed or dropped;
  - each variant needs investigation, something that can only be found by
    experiment, where the task allows it;
  - difficulty spreads across the frontier: solve rates for a strong and a
    weaker model.
- **Judges:** confirmation as KEEP; each probe's result per variant; the
  spread of solve rates.
- **Range crew:**
  - a security red-teamer attacks the grader and the sandbox, and returns
    the exploits found per variant;
  - an experimental scientist designs what must be found by experiment,
    and returns the experiment cost model;
  - a psychometrician fits difficulty and discrimination across models,
    and returns each variant's place on the frontier.
- **Needs:** the task source, its grader and its confirmation step are
  there. The red-team and brute-force agents are missing and get built;
  they are the main work's judges, so they belong to it.
- **Side project (this session):** a changed boundary-edit task, still
  recognizably the same task, where hacking and brute force can't pay by
  construction. For example: cases generated at grading time, a grader the
  agent cannot reach, and experiments that cost budget. Judge: the same
  red-team and brute-force agents beat the original on some variants but
  fail on the changed task, while strong models still solve it. If that
  holds, bring back the comparison and suggest the change.
- **Bigger version (suggested):** an environment where honest research is
  the only profitable strategy, by construction, with a measured result
  that training in it makes models better researchers. The spec, each
  property with its judge:
  1. reward only from real accomplishment (a grader audit);
  2. hacking unprofitable (a red team with a large budget fails to beat
     honest failure on every released task);
  3. brute force unprofitable (a brute-force agent with the same budget
     scores near zero);
  4. research-shaped: solving needs hypotheses, experiments and updates
     (blind reads of successful transcripts find them);
  5. interesting: worth a strong researcher's afternoon, with difficulty at
     the frontier (pass rates across checkpoints, and an expert's blind
     rating).

  Around the spec:
  - an instance generator;
  - a red-team gate on every release;
  - a transfer test: at equal compute, does training on it improve
    held-out research tasks more than training on the current environment?
    Training compute needs the user's go-ahead.

  A mechanism designer would own the reward rule and the argument that no
  exploit pays.
- **Next:** the variants, with both probes.

## A clock bug (task mode)

`$be-ambitious fix the test that started failing when the clocks changed`

- **Asked:** the failing test fixed.
- **Intent (inferred):** trust that a green suite means correct code. This
  failure says it didn't.
- **Above and beyond:**
  - the root cause fixed in the code, not in the test's expectation;
  - a regression test that fails before the fix and passes after;
  - a property-based sweep of that code path over ten years of time zones
    and transitions, including every DST change and leap day;
  - any other instance of the same bug in that code path, fixed or listed.
- **Judges:** the regression test, before and after; the sweep; and the
  module's mutation score, which shows whether its tests would catch the
  bug.
- **Side project (this session):** make the bug class impossible by
  construction:
  - all time goes through one injected clock;
  - a lint rule fails CI on any other clock read;
  - the work lives in its own worktree.

  Judge: a planted `datetime.now()` fails CI, and the lint reports zero on
  the branch. If both hold, suggest it.
- **Bigger version (suggested):** a repository that retires each bug class
  it meets. Mine every bug-fix commit for its class. After each fix, an
  agent writes the guard for the class: a property test or a lint rule.
  Judge: replay last year's bug-fix commits and measure what share a guard
  would have caught before merge.
- **Next:** the fix and its regression test.

## Papers on agent memory (task mode)

`$be-ambitious summarize these 12 papers on agent memory`

- **Asked:** a summary of the 12 papers.
- **Intent (inferred):** agents that remember what matters, so the user
  never has to repeat themselves. We run our own memory system, so the
  summary should help improve it.
- **Above and beyond:** the summary, organized around claims we could test:
  - for each paper, its central claim, the evidence for it (benchmarks,
    ablations, code), and how strong that evidence is;
  - one table comparing all twelve on the same axes;
  - where they disagree, and what would settle it;
  - what each implies for our memory system.
- **Judges:** every quoted claim checked against the paper's own text; and
  a fresh agent given only the summary answers 20 questions drawn from the
  papers about as well as one given the papers.
- **Side project (this session):** test the strongest claim on our own
  history. Mine 50 moments in the `hist` archive where the user had to
  repeat a correction. Check whether the best method would have surfaced
  the note that was needed, and bring back the count.
- **Bigger version (suggested):** a memory system with a measured effect on
  agent behaviour, which turns recurring lessons into skills by itself.
  Its parts:
  - a benchmark built from `hist`, with pooled relevance judgments (as
    TREC does);
  - the strongest methods reproduced, with results broken down by task
    type and horizon;
  - a live A/B test;
  - lessons promoted into skills, each validated on held-out tasks.

  Judge: the rate of repeated user corrections, before and after.
- **Next:** the summary.

## A worker packet (prompt mode)

`$be-ambitious rewrite this before I send it to cax: "Summarize the reference repo be-ambitious."`

- **Asked:** a prompt that gets a summary of the reference repository.
- **Intent (inferred):** decide what our skill system should take from it.
- **Above and beyond:** the summary still comes first. After it comes what
  a reviewer needs to act on it: each reusable pattern, the skill it would
  change, and the evidence for it.
- **Rewritten prompt:**

  ```text
  Summarize REFERENCE-REPOS/be-ambitious at commit dc116a3: what it does,
  how, and where its ideas come from. Then list each pattern that our
  skills under AGENT-ENGINEERING/SKILL-SYSTEM/skills could reuse, with the
  source line it comes from, the skill it would change, and the change.
  Optional, if it fits your session: write the patch for the strongest
  pattern in a scratch copy of that skill, and a three-task trial (tasks
  from hist, run with and without the patch, judged blind). Report it as a
  suggestion.
  Pass = the summary covers every file; every pattern cites its source
  line; any patch passes validate_skill_tree.
  ```

- **Bigger version (suggested to the user):** a standing pipeline. On every
  upstream update of a tracked reference repository, patterns are
  extracted and trialled, and only the winners reach the user, as
  patches.
- **Next:** send the prompt. This was a prompt, so stop here.

## With other skills

Short prompts that combine `be-ambitious` with other skills, each followed by
what was asked, how the main work goes above and beyond, and what comes
alongside. The numbers in the prompts are illustrative.

**With `learning-workspace`**

1. `$be-ambitious $learning-workspace ChartLab's collector sometimes misses bars; fix it.`

   - **Asked:** the missing bars fixed.
   - **Above and beyond:** the root cause found and fixed with a
     regression test, every past gap backfilled, and the last month
     reconciled bar by bar against a second source.
   - **Judge:** a planted outage is caught and backfilled, and the
     reconciliation finds zero missing bars.
   - **Bigger version:** `learning-workspace` is named, so the agent may go
     on to build a data layer that proves its own completeness every
     session. Its judge: 30 sessions reconcile with zero missing bars.
   - The workspace holds "gaps cluster at reconnects" as `K-1`, with its
     grounding check.

**With `solutionize`**

2. `$be-ambitious, then $solutionize with four cax and two ccx attackers: replaying a day of ES ticks through our backtester takes 9 minutes; another team replays a day in under a second on a laptop.`

   - **Asked:** a faster replay.
   - **Above and beyond:** under one second per day, with results
     bit-identical to the current engine on 20 recorded days.
     `solutionize` takes that target as its problem, and the timing plus
     the identity check as its frozen check.
   - **Bigger version:** once the target is met, the backtester can become
     an interactive research instrument, where a year-long parameter sweep
     runs in minutes.

**With `council`**

3. `$be-ambitious, then $council it: design an evaluation for our skill system.`

   - **Asked:** an evaluation design.
   - **Above and beyond:** paired runs with and without each skill on
     tasks mined from `hist`, judged blind, with a power estimate per skill
     and the cost of a full run.
   - **How it runs:** the rewrite becomes council's task. The panel
     designs, the judges rank blind, and the parent merges.
   - **Suggested alongside:** a system that measures every skill
     continuously and flags the ones to retire.

4. `$council with cax, ccx and dswe: each panelist reads ~/.agents/skills/be-ambitious/SKILL.md and applies it in prompt mode to "improve the morning market report". Judges rank the plans by how far each goes above and beyond while still delivering the report, with judges that can actually run.`

   Council as an ambition panel:
   - One model's reading, and its ambition, stop where its priors stop.
     Three decorrelated plans, ranked blind, raise the ceiling.
   - The merged plan keeps the boldest version that still delivers the
     report and still has real judges.
   - Council's read-only panel matches prompt mode.
   - The panelists read the skill file directly, so this works with any
     launcher.

**With two of them**

5. `$be-ambitious $learning-workspace, then $solutionize with the host's subagents: design a boundary-edit task where a red team can't beat honest failure and a brute-force agent scores near zero; a lab we talked to runs environments like that.`

   - **Asked:** the design. Here the request itself is the redesign.
   - **Above and beyond:**
     - a five-property spec: reward from real accomplishment; hacking
       unprofitable; brute force unprofitable; research-shaped;
       interesting;
     - a judge for each property;
     - an audit of the current task against the spec.
   - **How it runs:** `solutionize`'s frozen check is the red-team and
     brute-force gates, plus a solve-rate band for strong models. The
     workspace holds the spec, the audit's claims and the waves across
     sessions.

6. `$be-ambitious $learning-workspace: our weekly market-state ledger should catch turning points sooner. Take each design fork to $council.`

   - **Asked:** the ledger itself catches turning points sooner.
   - **Above and beyond:**
     - the ledger's entries carry early flags drawn from raw prices,
       positioning and participant language;
     - a backtest on last year's ledger shows the flags would have caught
       the turns earlier;
     - a month of live entries confirms it.
   - **How it runs:** each design fork goes to a council round, and the
     workspace records each round's conclusion as a claim.

7. `$be-ambitious, then $solutionize with five cax attackers, using $council to choose each wave's lines: get our 3B model to match the 30B on our grader tasks; another team did it with distillation and data curation.`

   - **Asked:** the 3B matching the 30B.
   - **Above and beyond:** at least the 30B's score on held-out grader
     tasks, at a tenth of the inference cost. That is the frozen check.
   - **How it runs:** `solutionize` runs the waves. `council` chooses lines
     when the choice is a judgment call, which `solutionize` already
     allows.

**With all three**

8. `$be-ambitious $learning-workspace: sgrep finds the right file in its top five for 60 % of our code questions. Get it to where the best code-search systems are. Hunt with $solutionize (four cax, two ccx); when two designs tie on the check, have $council choose.`

   - **Asked:** sgrep at the level of the best code-search systems.
   - **Intent (inferred):** agents find the right code on the first try,
     and keep finding it as the repository changes.
   - **Above and beyond:** recall@5 of at least 0.9 on held-out real
     questions, under 100 ms per query, with an index build under a
     minute. Challenge the belief that the embedding model is the
     bottleneck.
   - **Needs:** the held-out question set doesn't exist, so building it is
     part of the main work: questions agents actually asked, mined from
     `hist`, with the files they ended up opening, checked by pooled
     relevance judgments (TREC-style).
   - **How it runs:**
     - `learning-workspace` holds the request, the intent and the targets
       in `Task contract`, with the recall target as the terminal
       condition; "the embedding model is the bottleneck" becomes
       `K-1 [hypothesis]`, grounded by recall with a stronger embedder on
       the same index;
     - `solutionize` takes the targets as its problem and the held-out
       recall@5, rerun from a clean worktree, as its frozen check; its
       first wave measures, reads the misses and runs the naive fixes;
     - `council` runs only when two confirmed candidates both pass the
       check, choosing on maintenance cost and failure modes.
   - **Bigger version:** search that turns every real miss into a test and
     improves from it, with no one curating. Its judge: recall on next
     month's fresh misses. Long-run skills are named, so it may be built
     once the main targets are met.

**With other skills**

9. `$be-ambitious $learning-workspace $evidence-driven-loop-instrumented: each RL training experiment takes 30 hours.`

   - **Asked:** faster experiments.
   - **Above and beyond:** the full run itself cut from 30 hours, by
     removing the measured time that isn't training (data loading,
     evaluation cadence, checkpointing). Final metrics must stay within
     seed noise of the original on two configurations.
   - **Bigger version:** long-run skills are named, so the agent may then
     build a 30-minute proxy run that ranks configurations the way the
     full run does. Its judge: a rank correlation of at least 0.9 on
     held-out configurations.
   - **How it runs:** the instrumented loop keeps receipts for every run.

10. `$be-ambitious $evidence-driven-loop-judged: make the skill-system user guide great.`

    - **Asked:** a great user guide.
    - **Above and beyond:** "great" becomes measurable. The hard gate:
      fresh agents given only the guide pick the right skill on the first
      try for at least 95 % of 40 held-out tasks mined from `hist`.
    - **How it runs:** the judged loop handles what only judgment can
      settle, such as clarity and tone.

11. `$be-ambitious, then $fanout the bigger version: the weekly skill-system status doc.`

    - **Asked:** this week's status doc.
    - **Above and beyond:** the doc is written, with its numbers drawn from
      evidence of each skill's use and outcomes mined from `hist`. Skills
      that look ready to retire are flagged.
    - **Judge:** would the flags have caught `route-policy`, retired on 23
      October, before the user did?
    - **Alongside:** `fanout` then widens "what would show a skill's value
      better than a status doc?" to feed the suggestion.

12. `$be-ambitious $greenfield, then $delegate the spikes, one cax each: build a live read of dealer hedging exposure for ES.`

    - **Asked:** the gamma example's bigger version (above), as the request
      itself.
    - **Above and beyond:** its needs become `greenfield` spikes, each a
      feasibility question with its verdict:
      - can aggressor-side classification of option trades reconstruct
        opening positions well enough to pass the validation checks?
      - can near-the-money option prints be streamed within budget?
      - does a crude exposure estimate already predict intraday range?
    - **How it runs:** `delegate` runs one spike per worker, and the
      verdicts decide what gets built first.
