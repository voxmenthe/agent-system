---
name: research
description: Use when explicitly invoked as `$research` to investigate a question against high-trust primary sources and save a cited Markdown report in the repository. Do not use for ordinary fact lookup, implementation, or uncited brainstorming.
disable-model-invocation: true
---

# Research

Investigate the requested question directly and preserve the result as a
source-grounded repository artifact.

## Workflow

1. State the exact question, source boundary, and intended output path before
   deep retrieval. Follow an existing repository convention for research notes;
   if none exists, choose a narrow sensible location and report it.
2. Prefer primary sources: official documentation, source code, specifications,
   first-party APIs, original papers, and other material owned by the relevant
   authority. Use secondary sources only for discovery or clearly labeled
   context.
3. Trace every load-bearing claim to the source that supports it. Include direct
   links or precise local paths close to the claims they support.
4. Distinguish sourced fact, inference, conflicting evidence, and unknowns. Do
   not silently fill evidence gaps from memory.
5. Write one coherent Markdown report. Include the question, findings, evidence
   boundary, unresolved issues, and the exact sources used.
6. Reread the saved report and verify that each material claim is supported and
   that the file exists at the reported path.

Delegation is optional and requires separate authorization from the user or the
active agent policy. When it is authorized, the coordinating agent still owns
source verification, synthesis, and the final artifact.
