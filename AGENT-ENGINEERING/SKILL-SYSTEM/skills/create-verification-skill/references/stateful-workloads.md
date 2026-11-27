# Exercise state transitions and replay the inputs

Use this when a meaningful claim depends on a sequence of operations, retries,
rejections or recovery. Start with a bounded local workload over the real
public interface. A service's existing HTTP tests may already provide the
necessary operating path; extend their inputs/evidence before adding a runner.

## Define the state question before the operation list

Write down the initial state, legal operations and a small input-derived model
or invariant. For inventory reservations, successful unique orders consume
stock once; a duplicate returns the same order; a rejected reservation does
not consume stock. Do not derive every expectation from the server's response.

Choose operations that actually reach the risky transitions: a last available
unit, reuse of a key after exhaustion, conflicting reuse, rejection followed
by a valid request, or restart with acknowledged state. Check at those
transitions, not only after the sequence; later operations can hide an earlier
error. Assert that the important states were reached on a correct system.

Keep attempted calls, acknowledged results and distinct logical operations
separate. Follow the target's retry/idempotency contract. An interrupted call
may have committed: when the outcome is uncertain, retain that uncertainty
and use permissible bounds or a public reconciliation query instead of
inventing a rejection or blindly retrying with a new identity.

## Make the local run repeatable

- Record the operation/configuration input before execution, then append actual
  outcomes and intermediate observations. Keep the replay input separate from
  the result report and validate it before starting resources.
- Replaying means executing those inputs against a fresh declared initial
  state, not re-reading an old report. Preserve source/runtime identity and
  any prerequisite data that changes the operation meaning.
- Add seeded generation only when varied sequences close a real coverage gap.
  Record the concrete generated operations too; a seed alone can change meaning
  after the generator changes.
- If concurrency belongs to the contract, record operation groups and allowed
  outcomes. Replaying the group does not reproduce the scheduler. Use existing
  controlled-interleaving tests for causal race claims rather than promise
  deterministic scheduling from a seed.
- Where safety rests on a lock, look for preconditions read before it is
  taken (a path, link, copy, claim or balance) and confirm each is verified
  again under the lock. Aim a controlled interleaving at the gap between the
  check and the lock; a sequential workload never opens it.
- Bound operations, response waits and total run time. Close the exact owned
  service/state and retain the input, observations and failure point after
  cleanup. A graceful restart does not establish crash or power-loss recovery.

## Distinguish a broken system from a broken experiment

Reject malformed inputs as workload errors; unavailable binaries or failed
startup are environment failures. An invariant mismatch is a system candidate
finding only after checking the oracle and target identity. Never count a
launcher exception as evidence that a known-bad implementation was detected.

Run the healthy case first, and require every safety invariant to pass before
designing or running a controlled wrong implementation, mutation or planted
fault: against a baseline that already fails, a violation cannot be credited
to the plant. Then run one relevant wrong case and a fresh replay. Check that
the wrong case fails at the intended invariant while a
valid rejection/minimal case still passes. Repair the owning harness or
product boundary; do not loosen the expectation to accommodate the defect.

Source ideas: Antithesis's locally runnable self-driving workloads, property
versus reach assertions, run-level input variation and green baseline before
mutation, and pragmatic-agent-skills' lock re-check. No hosted campaign,
SDK, container publication or universal property framework is implied.
