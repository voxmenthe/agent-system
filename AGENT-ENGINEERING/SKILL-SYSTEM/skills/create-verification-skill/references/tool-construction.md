# Build a tool from a real operation

Use this when the missing capability is repeatable interaction, extraction,
or checking. Reuse an existing adequate driver first. A tool is justified by
the material evidence gap it closes, not by a quota of scripts or test cases.

## Observe one operation before encoding it

Perform the smallest authorized public operation with the target's existing
tools. Record its inputs, response or terminal state, relevant side effects,
and failure signal. For an unbuilt feature, establish a preserved path and
leave the proposed operation unexercised. Do not reverse-engineer a new client
when a documented command already provides the needed observation.

Choose the least sufficient helper:

| Repeated difficulty | Useful helper | Boundary to preserve |
| --- | --- | --- |
| An awkward public interaction | Small driver or existing tool invocation | Use the real public path, not internal setters |
| Large logs or API output | Parser/query over retained raw observations | Keep source IDs and point to the evidence being summarized |
| Multi-step behavior | Recorded action sequence and result checks | Stop when an unexpected transition invalidates later actions |
| Repeated service calls | Narrow client using the supported interface | UI/API equivalence is limited to the compared operation |

An authorized browser capture can help explain an otherwise opaque operation,
but does not grant endpoint-write or session-copying authority. API replay can
check backend behavior without proving the browser interaction.

## Keep the command inspectable

Use the project's language and dependencies. Give the helper explicit inputs,
the smallest useful command/flag surface, actionable errors, and a nonzero exit
for a failed or incomplete check. When another tool consumes output, keep data
structured and diagnostics separate. Stable IDs and saved artifact paths are
more useful than a giant transcript. Do not add a generic filtering language,
service framework, or global installation to operate one target.

Separate the input state from the evidence destination. Bind the run to the
actual source/build and owned process or module; retain invocation, inputs,
observations, and check outcomes. Existing test output is often sufficient.
If an old success report could survive a failed rerun, use a fresh output
location or write an explicit failed disposition before it can be mistaken
for this run's result.

## Prove the helper itself

Run it on the operation you observed and compare the actual result. Vary one
meaningful input; exercise invalid input or an unavailable prerequisite. At a
load-bearing oracle, use a known-wrong result that should fail the intended
assertion, not a launcher error. Do not accept a phrase anywhere in noisy
stdout when only a specific product field establishes the claim.

Choose the known-wrong result to defeat the comparator's weakest shortcut. A
comparator that checks totals passes a result whose rows swapped values: an
allocation of 30% to A and 70% to B still sums to 100% when written as 70% to
A and 30% to B. Compare per key, and keep that swap as the known-wrong case
that must fail while the correct ordering passes.

Exercise it from the documented entry and a fresh shell. Test another working
directory only if that portability is claimed. Release owned resources on
success and failure, then read the proof after teardown. Keep the helper with
the target; promote a generic executable into this package only after real
uses establish reusable value.

Finalize success after required cleanup. A rejected close must not leave a
passing report or cause state to be deleted beneath a possibly active resource;
retain the failed disposition and the exact owned state needing recovery.

Source ideas: pstack's build-the-lever method and OpenAI's agent-facing CLI
patterns. This is an owner-authored adaptation, not a shipped upstream client.
