# Subject: representative runtime path

Read this before writing an explanation of one trigger-to-result path. It
assumes the spine, prose rules, and visual limits in `SKILL.md`.

## One path, named at both ends

Use one trigger-to-result path. Name its trigger and its caller-visible result
in Scope. Do not silently merge alternative paths; if the reader needs a second
path, say why and keep it a named aside.

## Show a boundary only when it is material

Show process, event-loop, transport, side effect, failure, cleanup, and return
boundaries only when they change the answer. A boundary is material when
crossing it changes what can fail, what persists, what the caller observes, or
who owns the state. Drawing an immaterial boundary spends one of the seven
elements and buys nothing.

Do not turn routing or subprocess use into an isolation or security guarantee.
A separate process is a separate process; say what it actually enforces.

## Prefer an indented call tree

Runtime control flow reads fastest as an indented call tree. Reserve drawn
connectors for the relations indentation cannot express: a branch that rejoins,
a failure edge leaving the main path, a retry that returns to an earlier state.
