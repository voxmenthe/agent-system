# Concurrency and flow control

## Applies when

Load this pack before changing async tasks, threads, processes, locks, queues, workers, schedulers, parallel execution, cancellation, retries interacting with shared state, distributed coordination, or resource lifetimes that cross task boundaries.

## Does not apply when

Do not load it for purely sequential code or independent batch operations with no shared resources, ordering, cancellation, or capacity behavior. Load it when hidden concurrency may exist in a framework or callback.

## Non-negotiable rules

- Use structured concurrency: child work belongs to a scope, completes before scope exit, propagates errors upward, receives cancellation, and cannot become an orphan.
- Define ownership of mutable state and resources. Shared mutable state without a clear synchronization or single-owner model is a defect.
- Consumers control production rate. Bound queues and concurrency; expose demand/capacity signals and fail explicitly rather than degrading silently.
- Cancellation is a normal control path. It must release resources, stop child work, and avoid committing partial state unless the operation is explicitly resumable or transactional.
- Prefer coordination-free and monotonic designs: idempotent handlers, commutative updates, deduplication keys, immutable messages, and explicit coordination only around non-monotonic decisions.
- Never add retry loops on a hunch. Define retryable errors, backoff, limits, idempotence, and the effect of cancellation.

## Procedure

1. Draw the task and resource hierarchy: parents, children, shared state, locks, queues, files/sockets, transactions, and shutdown owners.
2. State required ordering, at-most/at-least/exactly-once expectations, duplicate behavior, and which invariants must be atomic.
3. Choose the simplest ownership model: immutable data, actor/single-owner state, message passing, or a narrowly scoped lock. Avoid mixing several models without necessity.
4. Bound concurrency and queues from expected capacity. Define overload behavior, fairness, starvation risk, timeouts, and how backpressure reaches producers.
5. Make cancellation and shutdown explicit. Test cancellation at waits, during partial work, and while resources are held. Ensure cleanup runs once.
6. Keep lock scope minimal and document lock ordering when more than one lock can be held. Never perform unbounded or remote work while holding a lock unless the invariant demands it and the risk is explicit.
7. Treat external side effects as retry-sensitive. Use idempotency keys, transactional outboxes, deduplication, or reconciliation where duplicate execution is possible.
8. For load-bearing worker, queue, or distributed systems, add observability for the relevant capacity and failure signals: queue depth, active workers, latency, saturation, retries, cancellations, dead-letter paths, or stuck work.
9. Test races deterministically where possible using barriers, fake clocks, controlled executors, and property/invariant checks rather than sleeps.
10. For cross-process or distributed flows, analyze partial failure and state what happens when a worker dies after each externally visible step. Where recovery depends on which step ran last, keep that state explicit and each step that must be atomic identifiable as one function or delimited region. When the orders, stop points, or retries that matter outnumber what tests can inject, suggest `$create-formal-verification-skill`; when a project `verify-*` skill covers code you changed, run its check.

## Done criteria

- Task, resource, and mutable-state ownership are explicit.
- Concurrency and queues are bounded; overload and backpressure behavior are deliberate.
- Errors and cancellation propagate correctly; no orphan tasks or leaked resources remain.
- Atomicity, ordering, duplicate handling, and retry semantics are stated and tested.
- Race tests rely on controllable synchronization rather than timing luck.
- Relevant saturation, stuck-work, retry, and cancellation signals are observable for load-bearing worker, queue, or distributed systems.
