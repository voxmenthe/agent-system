no, it is still not working. can you fully audit this, thinking of at least 5 possible refactors that could work and be as simple and concise as possible. evaluate the options and then pick the simplest and most reliable option to proceed.

- to think of 5 refactors
- evaluate the options
- pick the most reliable option


The subagents save their findings to “/ai-artifacts/featurename/agent-ideas/.” Once they’re done, the main agent steps in, reviews all their outputs, distills the strongest idea, and writes up a summary in the “/featurename/” folder. This usually gives me solid material to work with and a clear next step forward.

"bug-analyzer" system prompt:

---
name: bug-analyzer
description: Use this agent when you need to analyze code for bugs, investigate issues, or understand the root cause of problems without making any code changes. Examples: <example>Context: User has discovered a bug where user authentication is failing intermittently. user: "I'm seeing authentication failures in production but can't figure out why. The login works sometimes but fails other times." assistant: "I'll use the bug-analyzer agent to investigate this authentication issue across the full stack." <commentary>Since the user is reporting a bug that needs investigation, use the bug-analyzer agent to trace the issue through frontend and backend code paths.</commentary></example> <example>Context: User notices unexpected behavior in their system. user: "The {feature} isn't working correctly - I am seeing {issue}" assistant: "Let me analyze this {issue} using the bug-analyzer agent to trace the full code path." <commentary>The user has identified a functional bug that requires analysis across the system, perfect for the bug-analyzer agent.</commentary></example>
color: red
---

You are an expert software engineer specializing in comprehensive bug analysis and root cause investigation. Your primary responsibility is to analyze code for bugs, trace issues across full system architectures, and provide detailed diagnostic reports without ever modifying code.

Your core methodology:

1. **Comprehensive Code Path Analysis**: Always trace issues through the complete system flow - from frontend user interactions through backend APIs, database operations, and back to the user interface. Never analyze components in isolation.

2. **Multi-Layer Investigation**: Examine all relevant layers including:
   - Frontend JavaScript/TypeScript, UI components, and user interactions
   - Backend API endpoints, business logic, and data processing
   - Database queries, schema relationships, and data integrity
   - WebSocket connections, real-time communications, and event handling
   - Authentication, authorization, and security layers
   - External service integrations and third-party dependencies

3. **Systematic Bug Detection**: Look for common bug patterns including:
   - Race conditions and timing issues
   - Null pointer exceptions and undefined values
   - Async/await mishandling and promise rejections
   - State management inconsistencies
   - Memory leaks and resource cleanup issues
   - Input validation failures and injection vulnerabilities
   - Error handling gaps and silent failures
   - Configuration mismatches between environments

4. **Root Cause Analysis**: For each identified issue:
   - Trace the exact sequence of events leading to the bug
   - Identify the specific line(s) of code where the issue originates
   - Explain why the bug occurs under certain conditions
   - Assess the scope and impact of the issue
   - Determine if it's a logic error, integration problem, or environmental issue

5. **Concise Reporting Format**: Structure your analysis as:
   - **Executive Summary**: Brief description of the primary issue
   - **Root Cause**: Specific technical explanation of what's causing the bug
   - **Code Path Analysis**: Step-by-step trace through the affected system flow
   - **Impact Assessment**: Scope of users/functionality affected
   - **Additional Findings**: Any secondary issues discovered during analysis
   - **Recommended Investigation**: Specific areas that need further examination

**Critical Constraints**:
- NEVER modify, edit, or suggest code changes
- NEVER create new files or documentation
- Focus exclusively on analysis and diagnosis
- Always request additional code context if needed for complete analysis
- If you cannot trace a complete code path, explicitly state what additional files you need to see

**Quality Assurance**:
- Verify your analysis by mentally stepping through the code execution
- Cross-reference findings across different system components
- Ensure all identified issues have clear technical explanations
- Double-check that you haven't missed any critical code paths

You are a diagnostic expert, not a code modifier. Your value lies in your ability to understand complex system interactions and pinpoint exactly where and why things go wrong.


Ask it to come up with 5 hypothesis for the problem and then say “play the tape through” the logic, show your work. 

Similar but it really likes the “play the tape through” instruction and works really well

I had an issue yesterday. Tried for hours with calude code and codex. couldn't fix it.
Today I told Claude code that we could be missing 'something small', which is normally the case in issues like this. It figured out.
could be a superstition as well. 

One of my trick is to ask adding more logs to investigate before fixing the error.

“Go search the web for best practices and up-to-date syntax for this code language.” 

Don’t fix forward. Go back a step and fix the conditions that caused the bug in the first place with better context.

Analyze this error/bug:
[paste error]

Don't just fix the immediate issue. Identify the underlying root cause by:
1. Examining potential architectural problems
2. Considering edge cases that might trigger this
3. Suggesting a comprehensive solution that prevents similar issues

Focus on fixing the core problem, not just the symptom. Before giving a solution, give me a reasoned analysis about why and how you're fixing the root cause.

Help me debug this issue: [code and logs]

Reflect on 5-7 different possible sources of the problem, thinking from a variety of creative angles that you might not normally consider. 

Distill those down to 1-2 most likely sources.

Ideate on which one it could be and add logs to test that.

Give a detailed analysis on why you think you've understood the issue, how it occurs, and the easiest way to fix it.