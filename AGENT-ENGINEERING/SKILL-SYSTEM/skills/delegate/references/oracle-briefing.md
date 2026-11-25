# Oracle briefing

Use this for an oracle-style consultation (`cam`, `ccx`, `ccfh` and their
variants): one hard question to a strong model that does not share your
context. Quote evidence verbatim and summarize only narrative. Leave out
secrets and unrelated private context.

```text
QUESTION: one unresolved question, and why it is being asked now
REQUEST: the user's request, verbatim, then each later correction or
  constraint, verbatim and in order
TRIED: what was investigated, decided, tried and rejected, each with its reason
EVIDENCE: hist refs (`hist zoom <ref>`) and paths for the raw evidence: errors,
  test output, the relevant diff hunks. Paste only short excerpts.
STATE: what is done, what is half-done, and what is still running
RETURN: supported conclusions, competing hypotheses, and the discriminating
  next checks; or, for a decision, a verdict and the single best next step
```

For a decision, add the options with their tradeoffs and your current leaning.
When stuck, add what you expected, what you observed, and the hypotheses already
ruled out. Before completion, add what you verified and how, and what you did
not verify.

Afterwards, record one line on what was done with the advice: adopted, adopted
in part, or rejected, with the reason. Put it where the task keeps its notes,
or in the final report.
