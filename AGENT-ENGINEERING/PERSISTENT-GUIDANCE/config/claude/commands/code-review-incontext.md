---
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(claude -p:*), Bash(gemini -p:*)
description: Review this session's changes as a senior tech lead and write the review to CODE_REVIEW/
---

## Context

All of the changes that we have just implemented in this session.

## Your task

Based on the above changes, create a code review from the perspective of a senior tech lead.
Focus on catching errors or logic inconsistencies, adhering to best practices, and avoiding over-engineering and bloat.
Write your code review to a new file in the `CODE_REVIEW` directory in the project root (create if it does not exist).