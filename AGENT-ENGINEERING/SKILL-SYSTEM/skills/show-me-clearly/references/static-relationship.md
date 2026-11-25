# Subject: static relationship or interface

Read this before writing an explanation of ownership, registration, resolution,
containment, or a call relationship. It assumes the spine, prose rules, and
visual limits in `SKILL.md`.

## Qualify every edge

Show one concrete relation per edge: who owns, registers, resolves, contains,
or calls what. Qualify the scope — process-global, profile-scoped, optional, or
session-local. A filesystem tree shows containment only, never runtime order.

## Annotate nodes with their owning file or module

A bare name in a tree gives the reader no way to find the thing. When a tree
node names a file-backed thing, put its owning file, package, or module in
parentheses after it:

```text
<SessionPage> (apps/web/src/routes/session.tsx)
  useSessionEvents()
  <SessionToolbar> (packages/ui)
```

Annotate only nodes whose location the reader cannot guess. Keep the annotation
short enough that the line stays inside 88 columns — a package or directory is
usually enough. The annotation orients; it does not replace the receipt, which
still carries the exact line range.
