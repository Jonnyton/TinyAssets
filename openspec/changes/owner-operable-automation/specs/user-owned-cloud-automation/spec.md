# user-owned-cloud-automation — owner-operable repair

## ADDED Requirements

### Requirement: The owner SHALL be able to make their own automation do work now

An authenticated owner SHALL have a way, through canonical chatbot handles
alone, to cause their own automation's pinned Branch version to execute without
waiting for scheduled convergence, and without desktop, filesystem, or CLI
access. The chosen shape SHALL state whether the run consumes the provider
binding's invocations and the destination grant's action cap, and whether it
emits a terminal receipt.

#### Scenario: An automation that never converged can still be made to run

- **GIVEN** an automation whose `desired_state` is `active`
- **AND** whose `activation.state` has remained `stopped` with zero terminal
  receipts
- **WHEN** its owner asks their chatbot to run it now
- **THEN** the pinned Branch version executes
- **AND** the owner can observe that it ran

#### Scenario: The repair is owner-scoped

- **GIVEN** a caller who is not the automation's principal
- **WHEN** they attempt the same repair
- **THEN** it is refused non-oracularly, exactly as `get` and `pause` are today

### Requirement: `next_action` SHALL name an operation the surface accepts

Every value `next_action` can emit SHALL be an operation this surface accepts
for that target, enforced by a test that fails when the emitted set and the
accepted set diverge. An empty `next_action` is preferable to a name the handler
will reject.

#### Scenario: A label that names no real operation fails the build

- **GIVEN** health can emit some value V for `next_action`
- **WHEN** V is not an operation the handler accepts
- **THEN** the test suite fails

#### Scenario: Regression — the observed hallucination

- **GIVEN** an automation wedged before its first slice
- **WHEN** health reports its blocker and next action
- **THEN** the next action is one the owner can actually invoke
- **AND** an assistant reading it cannot infer a queued job that does not exist

> Live 2026-08-05: health emitted `next_action: "run_once"` with no such
> operation. An assistant reported to the owner that a `run_once` had been queued
> and was awaiting a worker. Nothing had been queued.

### Requirement: A control that changes nothing SHALL NOT report success

A control that cannot affect the state the owner is asking about SHALL say so in
typed form rather than return an unqualified success. This applies notably to
`resume` on an automation whose `desired_state` is already `active`, where the
write is a no-op.

#### Scenario: Resume on an already-active automation

- **GIVEN** an automation with `desired_state: active` and a non-converged
  activation
- **WHEN** the owner resumes it
- **THEN** the result distinguishes "already in this desired state, nothing
  changed" from "the requested change was applied"

> Live 2026-08-05: the owner's assistant resumed a wedged automation, received
> success, and had to tell the owner it could not distinguish that from a no-op
> because `activation.state` and `updated_at` were both unchanged.
