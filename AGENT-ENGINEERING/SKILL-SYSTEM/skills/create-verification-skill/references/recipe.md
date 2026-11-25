# One affected-surface recipe

This is a shape example, not a tested command for the reader's project. Keep
the target's existing format when adequate. A small CLI needs one recipe, not
a generated feature directory for every flag.

## Example: inspect an offline capture

- **Owner:** `docs/verification/capture.md` and its checked-in synthetic fixture.
  Production parsing remains owned by the product module.
- **User path:** inspect capture coverage before producing the normal archive.
  Requires a readable capture; no account or network access for this path.
- **Launch:** from the exact candidate checkout, invoke the documented Python
  interpreter and the script by resolved path. This is a short-lived command,
  not a server to keep alive.
- **Doctor:** resolve checkout/head and script path/hash; run its help command.
  Confirm the documented flag exists and the fixture belongs to this run.
- **Drive:** invoke the real CLI with that fixture and capture stdout, stderr,
  and exit status. Check root/selected IDs and counts, then drive the preserved
  archive workflow. Exercise malformed input without output-file creation.
- **Identity:** retain the resolved script path/hash alongside the exact
  invocation. Running an installed copy elsewhere does not test this checkout.
- **Evidence:** save invocations/results and artifact hashes in the task's
  evidence directory, outside its disposable output directory.
- **Cleanup:** delete only the run-created output directory; verify that proof
  remains readable. There are no persistent processes or ports in this path.

The real recipe supplies runnable commands, actual fixture paths, observations,
and expected values. It marks planned but unbuilt behavior separately. A UI or
service recipe additionally names readiness, stable navigation, process and
port ownership, data/profile isolation, and teardown.
