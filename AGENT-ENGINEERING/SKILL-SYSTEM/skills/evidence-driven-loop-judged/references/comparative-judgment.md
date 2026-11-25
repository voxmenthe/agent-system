# Comparative Judgment Protocol

Load this reference when designing or running the judged evaluation. Adapt its
artifacts to the task; it is a reasoning protocol, not a universal schema.

## Build the evaluation packet

Give every judge the same minimum sufficient packet:

- the task or user need;
- the frozen criteria and any priority among them;
- hard gates already checked;
- representative inputs or cases;
- blinded candidate artifacts produced under comparable conditions;
- explicit output choices and tie semantics; and
- known evaluation limits the judge should not silently fill with assumptions.

Do not include candidate names, chronology, author, optimizer prediction,
intended winner, or another judge's reasoning unless the role explicitly
requires adjudication. Normalize incidental differences such as filenames,
verbosity outside the artifact under review, or metadata that reveals lineage.
Do not normalize away real product costs or behavior.

Keep the packet and every full response in task-local evidence. A concise index
may point to those files and summarize outcomes, but it must not replace them.

## Assign roles with ordinary subagents

The default harness subagent is normally enough. Define specialization through
the assignment rather than relying on named provider-specific agent classes.
Keep every judge read-only and in a fresh context.

Use only roles that help the current decision:

| Role | Question | When useful |
| --- | --- | --- |
| Criteria judge | Which candidate better satisfies each stated criterion? | Normal comparison |
| Preference judge | Which artifact is better as a whole for the stated user and why? | Criteria omit an important gestalt |
| Coverage or attack reviewer | What was sacrificed, gamed, or left unevaluated? | Before promotion or after suspicious wins |
| Adjudicator | What explains preserved disagreement, and what narrower decision is supported? | Conflicting independent verdicts |

An adjudicator receives the original packet plus the separate verdicts. Ask it
to preserve genuine tradeoffs, not merely choose a majority winner. It must not
rewrite the earlier records.

If the harness supports only sequential subagent calls, run fresh calls one at
a time. Different model families can add diversity when available, but are not
required. A predeclared panel with fixed roles, models, and order assignments is
one evaluation-epoch configuration; changing its composition after evaluation
begins starts a new epoch. Several copies of one model are not independent if
they share the optimizer's context, each other's answers, or the same anchoring
explanation.

## Use a concrete judge assignment

A task-specific assignment can follow this shape:

```text
Act only as an independent, read-only judge. Do not edit the candidates or
evaluation. Compare blinded artifacts A and B for the supplied task and cases.
Apply the frozen criteria as written; identify missing evidence rather than
inventing it. Return A, B, tie, or insufficient. For each criterion, cite the
specific artifact or case evidence that controls your decision. Then list
possible evaluation blind spots. Do not infer candidate lineage or optimize a
new answer.
```

Add domain context and criterion definitions only as needed. Avoid asking for a
generic Likert score: subjective judges often compress absolute ratings and
produce weaker search signal than direct comparison.

## Counterbalance consequential comparisons

For a consequential selection between incumbent `I` and candidate `C`:

1. create a common packet, then one presentation with `I=A, C=B`;
2. create a second presentation with `C=A, I=B`, changing only artifact order
   and the labels needed to follow that swap;
3. inspect an exact diff or preserve task-appropriate hashes to verify no other
   context changed; otherwise mark the comparison unusable;
4. send the presentations to separate fresh judge contexts;
5. map the blinded verdicts back to candidate identity; and
6. retain both rationales before aggregating.

Interpret the pair conservatively:

- both mapped verdicts prefer `C`: candidate win;
- both prefer `I`: incumbent win;
- each presentation chooses its first or second position: order-sensitive tie;
- one or both say tie or insufficient: unresolved unless the declared policy
  and supporting evidence justify a narrower conclusion;
- rationales materially conflict despite matching labels: investigate rather
  than treating the labels as independent confirmation.

One exploratory order can guide the next cheap probe or a low-risk reversible
decision under an explicit single-order limitation, but it cannot support
consequential promotion by itself.

## Preserve partial orders and cycles

Treat pairwise results as direct edges, not absolute quality scores. Do not infer
`A > C` only because `A > B` and `B > C`. If direct comparisons produce
`A > B > C > A`, mark the set non-orderable under the current evaluation.

Respond to a consequential cycle by doing one or more of the following:

- inspect which cases or criteria produce the tradeoff;
- add a targeted case if it represents a real requirement;
- narrow the improvement claim;
- retain the incumbent;
- start a new evaluation epoch if the evaluator was defective; or
- escalate the tradeoff to a human.

Do not manufacture a total ranking through arbitrary point totals or silent
tie-breaking.

## Freeze and version evaluation epochs

The following changes alter what a verdict means:

- criteria, priorities, or rubric wording;
- judge prompt, role, model, or relevant tool access;
- case set, context, or artifact presentation;
- blinding or normalization;
- order policy, aggregation, or tie handling; and
- hard gates or protected-capability checks.

When one changes, explain the discovered flaw, retain old results under the old
epoch, rerun the incumbent and finalist under the new epoch, and avoid mixing
preferences across epochs. Keep confirmation cases or reviewers outside the
adaptive search loop when feasible.

## Track coverage and reward-hacking risk

Maintain a small task-native coverage view rather than pretending the rubric is
complete:

- required capability or use-case families;
- representative and boundary cases;
- known failure modes;
- protected properties and hard gates;
- search-visible versus confirmation-only evidence; and
- explicitly uncovered areas.

Untested capabilities are unknown, not passing. If a candidate removes,
simplifies, or weakens behavior outside the cases, use a coverage or attack
reviewer and inspect the exact diff or artifact change. Keep the incumbent when
the evaluation cannot establish that the sacrifice is acceptable.

For a consequential promotion, the optimizer may not perform its own decisive
coverage review. Assign it to a fresh read-only subagent. One of the
counterbalanced judges may cover this role only when the role and questions
were declared in the frozen packet before seeing candidate results; otherwise
use a separate reviewer.

## Prepare human adjudication

Use a human for authority and product judgment, not as a ceremonial final stamp.
Escalate when:

- counterbalanced judges remain materially inconsistent;
- a preference cycle affects selection;
- the criteria must encode a new value tradeoff;
- important capabilities lack defensible coverage;
- judge leakage, co-adaptation, or reward hacking is plausible;
- rebaselining after an evaluator change is infeasible; or
- the decision is consequential or difficult to reverse.

Give the human a compact packet containing:

- the decision and promotion rule;
- incumbent and candidate artifacts, blinded when useful;
- frozen criteria, cases, and coverage gaps;
- hard-gate results;
- each judge verdict and its controlling evidence;
- order effects, disagreements, cycles, and unmeasured risks; and
- the primary agent's reversible recommendation.

Ask for the smallest decision only the human can make: choose a candidate,
clarify a tradeoff, change the criteria, authorize a risk, or stop. After a
criterion change, begin a new evaluation epoch rather than relabeling old
results.

## Control cost without laundering uncertainty

Use staged judging:

1. hard gates and cheap artifact checks;
2. one independent comparison to discriminate an early hypothesis;
3. counterbalanced comparison for a consequential finalist;
4. coverage or attack review when the candidate could sacrifice unmeasured
   behavior;
5. human adjudication only at an actual authority or ambiguity boundary.

Stop adding judges when the evaluation frame, not sample count, explains the
disagreement. More correlated verdicts do not turn preference into truth.
