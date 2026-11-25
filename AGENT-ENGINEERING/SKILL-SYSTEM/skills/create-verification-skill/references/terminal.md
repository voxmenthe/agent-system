# Drive the terminal contract

Use this when terminal behavior is part of the claim: prompt transitions,
keyboard navigation, resizing, interruption or recovery. An ordinary CLI with
structured output usually needs only a subprocess. A component renderer can
check frames, but cannot establish controlling-terminal or real input behavior.

## Select the smallest real driver

Reuse the target's existing terminal harness. Otherwise use an available PTY,
Expect or an owned tmux session. Programs that open `/dev/tty` need a controlling
terminal, not merely a pipe whose output resembles a screen. Bind the terminal
to the intended command, working directory and disposable state; record the
actual executable and target source identity.

Pin only conditions relevant to the claim: terminal dimensions, `TERM`, locale,
input data and optional pager/editor configuration. Clear inherited selection
or preview commands when they would change the fixture. Do not copy a personal
session, use a fixed shared tmux name or kill an existing session to make room.

## Operate one observable transition at a time

1. Start the real command and capture its initial screen/prompt.
2. Wait for an expected state with a deadline, retaining partial output on
   timeout. A sleep is not evidence that the application reached that state.
3. Send literal input separately from key sequences. Capture the next state
   and check the selected value or public result, not just the echoed input.
4. Exercise the terminal-specific edge that matters: resize and redraw,
   Escape/back navigation, Ctrl-C, EOF or restarting after interruption.
   Observe both the interrupted result and a working fresh invocation.
5. Check the promised side effects or absence of them. For a read-only Git
   browser, compare index/worktree state as well as the displayed selection.

A terminal transcript contains cursor motion and overwritten text. Match an
actual rendered frame when layout matters; raw substring matching can accept
text left from a previous screen. Keep before/after frames or raw recordings
with clearly identified boundaries. Text capture does not certify color,
contrast or visual fidelity.

## Close the owned session

Keep the child/session handle and its process-group ownership. Attempt normal
exit first; bound shutdown, escalate only against that owned group if needed,
then reap it and close PTY descriptors. Verify no owned child or tmux session
remains. A surviving child invalidates cleanup even if the wrapper exited.
Retain recordings and failures outside temporary state before removing it.

Report an unavailable executable, missing controlling terminal or unsupported
key encoding as a prerequisite/driver gap, not as a passing CLI test. A fake
picker can validate argument handling but is not real interactive acceptance.

Source ideas: Cursor Team Kit's control-cli and Gloomberb's distinction among
CLI, component-renderer and full-terminal tests. Their application commands,
fixed sleeps and shared session names are not portable requirements.
