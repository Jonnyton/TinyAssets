## ADDED Requirements

### Requirement: Assigned queue execution is dark by default
The daemon SHALL NOT scan, claim, heartbeat, or execute assigned queue work unless `TINYASSETS_ASSIGNED_QUEUE_CONSUMER` is explicitly truthy.

#### Scenario: Flag absent
- **WHEN** the daemon starts without the assigned queue consumer flag
- **THEN** it creates no consumer and performs zero queue claims

### Requirement: Assigned queue claims are exact and single-winner
The consumer MUST claim only a pending epoch-2 task whose current activation epoch, immutable subject reference and digest, background attempt, universe, and boot-unique consumer lease all validate in the claim transaction.

#### Scenario: Two consumers race
- **WHEN** two live consumers race to claim the same task
- **THEN** exactly one claim CAS succeeds and at most one run reservation is created

#### Scenario: Activation rotates during claim
- **WHEN** the automation epoch or immutable version changes before the claim commits
- **THEN** the claim fails without changing the task

### Requirement: Consumer failures cannot terminate the daemon
The consumer SHALL bound global and per-universe concurrency, SHALL be stoppable, and MUST contain task exceptions inside its worker future.

#### Scenario: Task raises
- **WHEN** a claimed task raises an unexpected exception
- **THEN** the HTTP/daemon coordinator remains alive and continues bounded polling

#### Scenario: Consumer restarts
- **WHEN** a consumer process exits before launch and its task lease expires
- **THEN** recovery can return the same task and attempt budget to retryable work without a permanent reservation
