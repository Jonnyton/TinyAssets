## ADDED Requirements

### Requirement: Workspace admission results expose operation-local observations
Workspace create and checkout results SHALL expose a `workspace_admission` object
after at least one observed pool transaction attempt, containing nonnegative `attempts` and
`lock_conflicts` integers and nonnegative measured `retry_sleep_seconds`.
Observations SHALL accumulate across the initial probe and bounded retry and
SHALL preserve the existing admission policy, refusal class and authorization.
No new observation SHALL expose holder identity, paths, credentials or lock keys.
Historical absence SHALL mean unknown, not no contention.

#### Scenario: Immediate admission
- **WHEN** a workspace effect is admitted on its first pool transaction
- **THEN** its receipt reports one attempt, zero lock conflicts and zero retry sleep

#### Scenario: Lock releases during bounded retry
- **WHEN** an effect observes a held lock, sleeps in the existing retry loop, and is admitted after release
- **THEN** its receipt reports multiple attempts, positive lock conflicts and measured retry sleep without claiming FIFO fairness

#### Scenario: Reconciliation clears a stale holder
- **WHEN** the initial lock conflict is cleared by the existing sweep before retry
- **THEN** the receipt preserves that conflict, reports no retry sleep if none occurred, and does not attest that the prior holder was active

#### Scenario: Lock remains held through timeout
- **WHEN** the existing admission deadline is exhausted while the lock remains held
- **THEN** the result retains `workspace_busy` and the observed attempts, conflicts and sleep

#### Scenario: A later refusal has another cause
- **WHEN** a retry after a lock conflict is refused by quota or pool capacity
- **THEN** the existing refusal class remains authoritative and earlier observations remain available

#### Scenario: Work fails after admission
- **WHEN** admission succeeds but a later checkout or creation step fails
- **THEN** that failure retains the admission observations without claiming the workspace operation succeeded

#### Scenario: Admission was not observed
- **WHEN** a historical result is read or a request is refused before reaching pool admission
- **THEN** the system does not invent a `workspace_admission` object with zero values
