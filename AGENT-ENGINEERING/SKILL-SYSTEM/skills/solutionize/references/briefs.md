# Briefs

These are the texts the agents receive. Fill the angle-bracket slots and keep
the rest as written; the briefs say what the skill says.

## Attacker guidance

```text
A solution to this problem already exists. <What the user knows about it, in
their words. If nothing more is known: Someone has solved it privately, and
the solution has not been published.> You are here to find it again and to
show that it works. You have it in you.

Do not search the web. The solution is not published, and public sources
mostly repeat the usual approaches and the reasons the problem is hard.

This is a novel situation that calls for novel approaches, and novelty can be
as small as something so simple that everyone overlooks it. Start from the
boring, troublesome foundations and the very simple areas where an
opportunity may be lying, before going into deeper, more complex areas.
People skip these simply because they are lazy. You are not lazy, and you
have time: exploit that advantage. Try things instead of arguing that they
will not work. Measure, run the experiments, and build the tools you need. A
failed experiment is a result to record, not a verdict on the problem.
```

When the search scope allows web lookups, replace the second paragraph with
what it allows, for example: "Use the web only for library documentation."

## Attacker wave

This is a `delegate` wave manifest. COMMON carries what every line shares;
each worker block carries one line.

```text
COMMON:
ROLE: implement
WORKSPACE: <run>/wave-<NNN>
CONTEXT: <attacker guidance, each line indented two spaces>
  PROBLEM: <the exact problem, with its constraints>
  CHECK: <what counts as solved, and the command that checks it>
  KNOWN: <what is known about the existing solution; attempts so far, as results>
  TOOLS: <what is available: the repository, its test and benchmark commands, data, compute>
  Your line is where to start, not a fence. If it leads somewhere better,
  follow it, and say so in the LINE field.
  Write ANSWER.md in your own directory, starting with this header:
    RESULT: solved | partial | not yet
    LINE: the line you followed; if you left the one given, where you went and why
    CLAIM: exactly what you can show
    REPRODUCE: the commands that show it, and what they print
    WEAKEST POINT: what you are least sure of
    NEXT: the most promising next step from here
    ---
  Below the header, describe the approach, then each experiment: what you
  expected, what you ran, and what happened.
CONSTRAINTS: Web: <none | the lookups allowed>. Read only <your worktree,
  your own directory, and the tools and libraries the project uses | the paths
  the user names>. Write only in the directory and worktree named in SCOPE,
  and keep experiment outputs and scratch files outside the worktree, which
  holds only your change. STATUS is done once ANSWER.md is written; BLOCKERS
  lists only tool or environment problems.
VERIFY: Run every experiment and check your claim relies on.

@@ launcher=<agent> name=<line-id>
OBJECTIVE: Find the solution along this line: <angle and starting point>.
  <build-on lines only> EARLIER RESULTS: <one per line, each labeled rerun or reported>
SCOPE: <run>/wave-<NNN>/<line-id>/ only; your worktree is <run>/wave-<NNN>/<line-id>/tree
```

An attacker choosing its own approach gets the objective "Find the solution
along any line you choose."

A random line's objective gives your reading of the drawn passage, then
quotes the passage:

```text
OBJECTIVE: Find the solution along this line: <your reading of the passage>.
  This line was read into a passage drawn at random, as pure inspiration.
  Follow the reading, or make your own reading of the same passage:
    <the passage, each line indented four spaces>
```

A repair line starts from the failing claim's patch. Its objective names the
failure: "This change fails the check at <where, and how>. Make it pass, or
find another route to the same result."

## Checker (only when needed)

Use a checker agent only when a check needs judgment rather than a command,
or when the user asks for one.

```text
COMMON:
ROLE: implement
WORKSPACE: <run>/checks/<claim-id>
CONTEXT: Check a claimed solution by reproducing it from a clean start.
  PROBLEM: <the exact problem, with its constraints>
  CHECK: <the frozen check, and how to judge it>
  CLAIM: <the claim's ANSWER.md>
  For a repository, apply <run>/checks/<claim-id>/solution.patch in your
  fresh worktree; otherwise follow the claim's REPRODUCE steps in your own
  directory. Confirm that the claim leaves the check, its data and its
  settings unchanged, and that it solves the stated problem rather than
  special-casing what the check measures. Find the first real failure, if
  there is one, and say where it happens.
  Write VERDICT.md in your own directory, starting with this header:
    VERDICT: holds | fails | unclear
    FIRST FAILURE: where and why, or none
    RAN: the commands and what they printed
    ---
CONSTRAINTS: Web: <as in the search scope>. Work only in the directory and
  worktree named in SCOPE.
OBJECTIVE: Reproduce the claim against the check, or find where it fails.
VERIFY: Run the check yourself; do not reuse the claimant's results.

@@ launcher=<agent> name=check
SCOPE: <run>/checks/<claim-id>/check/ only; your worktree is <run>/checks/<claim-id>/check/tree
```
