## ADDED Requirements

### Requirement: Stale retired-fleet reconciliation is dry-run first
The system SHALL expose an on-demand stale-fleet reconciliation command whose default mode performs no writes and reports the cutoff, sorted selected task and runtime entries, exact counts, and a stable SHA-256 digest over the cutoff and sorted selected IDs.

#### Scenario: Default invocation is read only
- **WHEN** an operator invokes `python -m tinyassets.runtime_reconcile stale-fleet` without `--apply`
- **THEN** the command prints the reconciliation plan and digest without creating, migrating, updating, cancelling, retiring, compacting, or deleting storage records

#### Scenario: Explicit dry-run remains read only
- **WHEN** an operator invokes the command with `--dry-run`
- **THEN** its behavior is identical to the default dry-run mode

### Requirement: Apply is bound to the reviewed plan
The system SHALL require an expected plan digest and exact expected task and runtime counts for apply, SHALL recompute the plan before any mutation, and MUST exit nonzero without writes when any guard differs or is missing.

#### Scenario: Digest mismatch aborts the entire apply
- **WHEN** the recomputed digest differs from `--expected-plan-digest`
- **THEN** no task cancellation or runtime retirement lifecycle is invoked

#### Scenario: Either count mismatch aborts the entire apply
- **WHEN** either recomputed count differs from its expected exact count
- **THEN** no task cancellation or runtime retirement lifecycle is invoked

### Requirement: Only stale retired-cloud-capacity tasks are cancelled
The system SHALL select only enabled pending epoch-2 tasks at or older than the cutoff that pass current admission/task integrity, are policy-enabled, classify as `awaiting_compatible_capacity` under the current legacy matcher, and carry the retired `cloud` executor class. Apply SHALL recheck status, queued timestamp, grant generation, body/integrity digest evidence under `BEGIN IMMEDIATE` and then reuse the request-v2 cancellation lifecycle with reason `stale_awaiting_compatible_capacity_retired_fleet`.

#### Scenario: Qualifying task is cancelled with history and payload retained
- **WHEN** a planned task still matches every CAS field during apply
- **THEN** its task and request status become `cancelled`, admission/request/task event state is updated, the cancellation event records the retirement reason, and its task/admission/request payload rows remain present

#### Scenario: Fresh, foreign, runnable, invalid, or non-cloud task is untouched
- **WHEN** a task is newer than the cutoff, not pending, disabled, fails integrity, has compatible capacity, is policy-parked, or has an executor class other than `cloud`
- **THEN** it is absent from the plan and apply does not mutate it

### Requirement: Only stale unowned cloud-worker runtimes are retired
The system SHALL select only provisioned runtime instances with exact `metadata.runtime_registration=cloud_worker`, a dead heartbeat at or older than the cutoff, no current claim or unexpired lease, and valid digest/`updated_at` evidence. Apply SHALL recheck those conditions under `BEGIN IMMEDIATE` and reuse the runtime retirement lifecycle to set status `retired`.

#### Scenario: Qualifying runtime is retired without destructive cleanup
- **WHEN** a planned cloud-worker runtime still matches its digest, `updated_at`, heartbeat, claim, and lease CAS evidence
- **THEN** its status becomes `retired` while daemon definitions, runtime history, attribution, and task records remain present

#### Scenario: Fresh, foreign, non-cloud, active, claimed, or leased runtime is untouched
- **WHEN** a runtime is fresh, not provisioned, lacks exact cloud-worker registration, has a live heartbeat, owns a current claim, or owns an unexpired lease
- **THEN** it is absent from the plan and apply does not mutate it
