## ADDED Requirements

### Requirement: Assigned serving credential is the sole universe execution authority
For a universe-scoped workflow execution, the vault SHALL expose credential material only through the exact current serving assignment selected for that universe. The daemon SHALL snapshot that assigned credential for one run and clean the snapshot afterward. A missing, malformed, stale, revoked, exhausted, or unavailable assignment SHALL produce the typed hold `no_requester_owned_executor`; the vault/provider boundary SHALL NOT copy ambient host credential variables, search for another credential record, or fall back to another provider.

#### Scenario: Exact assigned credential is snapshotted
- **WHEN** a workflow's current serving assignment and vault custody reference agree
- **THEN** the daemon receives a launch-scoped snapshot for only that assigned credential
- **AND** the snapshot is removed after the run

#### Scenario: Missing assigned credential cannot inherit host auth
- **WHEN** the host process has valid provider auth but the task universe has no usable assigned credential
- **THEN** execution holds with `no_requester_owned_executor`
- **AND** no host auth home, token, API key, endpoint, or provider route enters the child

#### Scenario: Another vault credential is not an implicit fallback
- **WHEN** the assigned credential is unavailable and the same vault contains another provider credential
- **THEN** the other credential remains unused unless the user explicitly rebinds the workflow
