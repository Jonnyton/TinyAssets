## ADDED Requirements

### Requirement: Assigned serving credential is the sole universe execution authority
For a universe-scoped workflow execution, the vault SHALL expose credential material only through the exact current serving assignment selected for that universe. The daemon SHALL resolve the serving agent row, assignment, provider-work binding, custody reference, and binding budgets inside one transaction while holding shared provider-assignment admission for the complete run; it SHALL snapshot that assigned credential for the run and clean the snapshot afterward, including when authority construction or the provider body fails. A concurrent disable, revision change, rebind, or custody rotation SHALL wait for the active run or cause the next resolution to hold. A missing, malformed, stale, revoked, exhausted, or unavailable assignment SHALL produce the typed hold `no_requester_owned_executor` without attaching the underlying credential exception chain; the vault/provider boundary SHALL NOT copy ambient host credential variables, search for another credential record, or fall back to another provider.

#### Scenario: Exact assigned credential is snapshotted
- **WHEN** a workflow's current serving assignment and vault custody reference agree
- **THEN** the daemon receives a launch-scoped snapshot for only that assigned credential
- **AND** the snapshot is removed after the run

#### Scenario: Assignment mutation cannot race an active snapshot
- **WHEN** a provider assignment writer attempts to disable, revise, rebind, or rotate the credential while a run holds assigned credential authority
- **THEN** the mutation waits for the run's shared admission fence
- **AND** no stale serving identity can be launched after the mutation commits

#### Scenario: Missing assigned credential cannot inherit host auth
- **WHEN** the host process has valid provider auth but the task universe has no usable assigned credential
- **THEN** execution holds with `no_requester_owned_executor`
- **AND** no host auth home, token, API key, endpoint, or provider route enters the child

#### Scenario: Another vault credential is not an implicit fallback
- **WHEN** the assigned credential is unavailable and the same vault contains another provider credential
- **THEN** the other credential remains unused unless the user explicitly rebinds the workflow
