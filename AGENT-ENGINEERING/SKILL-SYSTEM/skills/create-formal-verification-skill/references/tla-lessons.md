# Modelling lessons for TLA+ and TLC

Each rule comes from building and fixing four verifications: a shell
supervisor that launches, reaps and stops worker process groups; a journaled
install/rollback transaction system; and a TypeScript alert pipeline and its
cross-process owner lock. The last three found seven real bugs; the first
found none and re-caught a recently fixed one.

## Fidelity

- **Cite lines from a numbered listing.** Take every citation from `nl -ba
  <file>` at the sync commit and spot-check each before handoff. Citations
  written from memory or an unnumbered read drifted by one to four lines.
- **Argue atomicity in the model's header.** A step may group what nothing
  else can observe in between: a command holding an exclusive lock, one loop
  iteration that reads only its own worker's state, or one atomic write or
  same-filesystem rename. Every other boundary is a separate step.
- **Make the environment adversarial.** Processes exit at any moment, signals
  arrive at any time, timers elapse anywhere, writes fail, and a command may
  stop between any two of its writes. Bound how many failures a behavior gets
  (one I/O failure per run was enough) rather than leaving them out.
- **Start crash windows where the tests inject, then widen.** Tests usually
  fail a command only right after a journal write. Model that window first,
  then the window between an effect and the journal write that records it,
  then a stop inside recovery itself. The last two windows held three of the
  four bugs; the fourth needed no crash, only an operation order the docs
  allow.
- **State invariants over every record the code keeps.** A property limited
  to the current definition's records passed while an edit that replaced the
  detector broke the same promise for an older record.
- **Cite line numbers only in the model.** Use function or unit names in the
  notes, the manifest's `what` fields and the skills: a 46-line product
  change shifted more than 100 citations across six files. Apply this to new
  and touched work.

## State space

- **Budget a new config before trusting it.** Run it with a time limit and
  watch TLC's progress lines. When it passes the stated budget, stop and drop
  one dimension (a mode, a crash window, a process) rather than waiting. A
  config with every mode, one edit and one crash passed 50M states and was
  still growing; with two modes and no crash it finished at 25.6M states in
  73 s.
- **Fire environment events only where the code reads them.** An event that
  changes only what step k reads gives the same outcomes moved to just before
  step k, because nothing in between observes it. Restricting events to those
  read points and saying so in the header, together with the next two rules,
  cut one model from 53.7M to 4.2M states with no loss of behaviors.
- **Reset what the code never reads again.** Once a timer or flag cannot
  influence a later step, set it to a canonical value.
- **Abstract counts to what is read.** If the code only asks "is anything
  still alive", a boolean beats a set of processes. Reduce trees and files to
  content hashes or versions.
- **Make bounds and options constants.** Put choices such as `--jobs` or
  `--timeout` in constant sets, so a config can split one large run into
  several and the quick tier can pick small ones.
- **Expect liveness to stop at tiny bounds.** TLC's liveness checking did not
  finish for two workers in 400 s while safety finished in seconds. Check
  termination in its own config at the smallest bound, with weak fairness on
  the code and strong fairness on the events that must eventually happen,
  and say in the notes where it stops.

## Configs and properties

- **One target property per mutation or finding config.** The runner then
  requires that exact property to be the one violated, so a different failure
  cannot pass as a catch.
- **One `PROPERTY` per temporal config.** TLC reports "Temporal properties
  were violated" without a name; the runner uses the config's only property.
- **Use action properties for promises about steps.** "A rollback that
  finishes restores its own tree" is `[][...]_vars` over the step, not an
  invariant over states.
- **Disable deadlock checking for systems that can sit idle.** When a command
  may stop and nothing else is enabled, write `CHECK_DEADLOCK FALSE`, or TLC
  reports a deadlock instead of the property you are checking.
- **Bound quantifiers in `Next` by constants.** `\E i \in 1..Len(ops)` makes
  TLC label every such step `Next` in counterexamples; `\E i \in 1..MaxOps`
  with the guard inside the action restores the action's name. Splitting an
  action with a check that may refuse into `StartX` and `RefuseX` names the
  refusal too. A guard conjoined outside the action disjunction
  (`\E p : alive[p] /\ (A(p) \/ B(p))`) hides the names the same way; put it
  inside the actions that need it.
- **"Successor state is not completely specified"** often means a misaligned
  `/\` list, not a missing assignment.
- **Expect counterexample state counts to vary.** With `-workers auto`, TLC's
  workers stop at different points, so a violation's state count changes
  between runs; a pass's count does not.

## Bug or model error

- **A model error can look exactly like a bug.** A classification that
  forgot one phase produced a false refusal. Replay every violation against
  the real code before reporting it, with a test that drives the public API
  in a temporary home and injects the stop by raising from the function that
  writes the next phase. Write it with the suite's own fixtures, so it
  becomes the fix's regression test.
- **Replay a race with real processes.** Pause one contender inside the
  window by wrapping the system call it makes there, in its own process, and
  run the others as real detached processes. Reap or double-fork the
  children: `kill(pid, 0)` reports an unreaped zombie as alive.
- **A mutation that is not caught can expose a missing property.** Dropping a
  "no mutation while an operation is incomplete" check went uncaught because
  no property said every incomplete operation stays recoverable. Rule out a
  bound that never reaches the step and a mutation that changes nothing
  observable first (see "Show that every property can fail" in `SKILL.md`),
  then record such a gap in the notes.
- **When the main configs constrain an order the code allows, say so.** The
  main configs rolled back newest first; the order the docs allowed is a
  separate finding config, and it found a bug.
- **A fix can change which property catches its pre-fix mutation.** Putting
  back the code behind a silent bad rollback was caught as a refused rollback
  instead, because the fix also added an occupied-target check. Target the
  property the mutation breaks, and say in its config which guard catches it.

## Runs

- Measure each config once and put it in the quick or full tier by time. The
  supervisor's full tier took about 21 minutes (three workers at each
  `--jobs` value, up to 479M distinct states); its quick tier takes about 40 s.
- TLC uses every core with `-workers auto`; running two large checks at once
  slows both.
