# Angles

**Inspiration only: angles to build on, not to follow, and not meant to be
exhaustive.** Open this file only when the run has stalled: waves have
stopped adding anything new, changing the frame has run dry, and no line in
view seems worth running. If the run has not stalled, close it and go back
to the problem. Lines come from the problem itself, and this list would only
narrow them.

This is not a menu, a checklist or a complete list, and the best line is
often one that is not here. Each angle is a seed. Turn one into a bet about
this problem in its own terms, combine two, invert one, or follow whatever
better idea it brings to mind. Do not work through the list or try to cover
it, and never take its end for the end of the hunt. To keep habit out of the
choice, let chance pick: draw a few lines from this file with the
random-line command in [running](running.md), and draw again when the
passage holds no angle.

The list grows as the skill is used, but never during a run. When an angle
that is not here breaks a stall, name it in the final report, so the owner
can add it under "Added from runs" with the run it came from.

## Use the premise

- Assume the fix is small and overlooked: what would a five-line change look like?
- Reason backwards from what the existing solution visibly does: its outputs, timings and limits.
- Ask what whoever solved it had that you lack: data, hardware, a library, a dropped constraint.
- Ask what someone with years inside this codebase or field would know that a newcomer would not.
- Suppose they found it by accident: what accident would have shown it to them?
- Find the limit everyone accepts, and test whether it is real.

## Look again

- Reproduce it from scratch in a clean environment, and note every difference.
- Measure it with a different instrument: a profiler, a tracer, counters, logs.
- Find where the time, memory or errors actually go; it is rarely where everyone assumes.
- Diff a working case against a failing one, line by line and setting by setting.
- Watch it run: step through it, or trace one request from end to end.
- Change one thing in the environment at a time: machine, version, input size, load.
- Check the defaults: settings nobody chose, inherited from a template, a library or an old decision.
- Read the warnings everyone ignores: compiler, linter, runtime, deprecation.
- Check units, precision, rounding and overflow.
- Look at the data itself: outliers, duplicates, encodings, distributions.
- Read the check line by line: what exactly counts as passing?
- Reread the problem statement for what it does not say.

## Change the problem

- Shrink it until it yields, then grow it back one step at a time.
- Solve one special case completely, then lift the method.
- Generalize: solve a bigger problem that is easier to state.
- Drop a constraint, solve, then repair the solution.
- Add a constraint that makes it easier, then relax it step by step.
- Solve the inverse, dual or complementary problem.
- Work backwards from the goal: what must be true just before it?
- Split it into parts that can be solved separately, or merge two parts into one.
- Bound the answer from both sides, then close the gap.
- Approximate first, then refine.

## Change the form

- Change the data layout: columns instead of rows, sorted, indexed, packed, compressed.
- Change the encoding, units, coordinates or basis.
- Precompute, cache or memoize, or recompute instead of storing.
- Move work from run time to build time, or the reverse.
- Batch it, stream it, or make it incremental.
- Make it lazy, or make it eager.
- Replace a general mechanism with a special-purpose one, or the reverse.
- Ask what the hardware is good at, and reshape the work to fit it.
- Restate it as something else: a graph, a matrix, a probability, a game, a grammar.

## Exploit structure

- Look for a symmetry, and solve one case from each class.
- Find an invariant, and see what it rules out.
- Look for something monotonic, and search it by bisection.
- Look for sparsity or locality: most of the work may touch few of the cases.
- Design for the inputs that actually occur, not the worst case.

## Search by machine

- Enumerate every case on small inputs, then look for the pattern.
- Sweep two parameters together, not one at a time; the answer may sit in an interaction.
- Encode it for a solver: SMT, SAT, integer or constraint programming.
- Fit exact formulas to measurements, then test them on new inputs.
- Search at random, then search locally around the best points.
- Fit a cheap model of an expensive check, search on the model, and confirm on the check.
- Fuzz it with random and adversarial inputs.
- Evolve programs or settings automatically, and test the winners on inputs the search never saw.
- Compare it with another implementation on many inputs.

## Borrow

- Transplant a mechanism from another field: biology, economics, physics, logistics.
- Ask how a database, compiler, kernel, game-engine or GPU programmer would do it.
- Find the nearest problem with a known solution, and adapt that solution.
- Search this codebase for a place where a similar problem is already solved.
- Dig through the history: what did older versions, branches and abandoned attempts do?
- Read the source of the dependencies; the trick may live in a library.
- Ask how it was done before computers, or by hand.

## Build a tool

- Build a purpose-built solver, simulator, minimizer or profiler.
- Visualize it: plot the data, draw the state, animate the process.
- Write a harness that runs thousands of variants unattended.
- Automate the tedious comparison everyone has avoided.
- Build a model of the system, and check it against measurements.

## Question the frame

- Ask what would make the problem easy, then try to make that true.
- Look for the boring explanation: a typo, a setting, an off-by-one, a stale cache.
- Ask what the system really optimizes, and whether that is the goal.
- Look for a constraint that is not real: inherited, historical or misread.
- Look in another layer: hardware, operating system, network, compiler, data, process.
- Suppose the hard part is somewhere else, and look there.

## Provoke

- Invert it: how would you make it worse? Then do the opposite.
- Remove a part, and see what still works.
- Push one parameter to an absurd extreme, and watch what changes.
- Try the laziest thing that could possibly work.
- Give a deliberately strange idea a small, fixed budget.
- Combine two approaches that failed on their own.

## Change how you work

- Explain the problem plainly to someone outside it.
- Start again from a blank page, ignoring every earlier attempt.
- Work a tiny case by hand.
- Ask what a beginner, a specialist from another field, or someone with no budget would try.
- Do the opposite of what the last wave did.

## Added from runs
