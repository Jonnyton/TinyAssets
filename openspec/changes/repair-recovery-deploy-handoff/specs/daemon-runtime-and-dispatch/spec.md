## ADDED Requirements

### Requirement: Finalized Recovery Hands Off Only Its Exact Fleet To Canonical Deploy

The transitional production deploy fence SHALL permit a normal deployment to
retire a finalized emergency-recovery container generation only when durable
recovery provenance and the current preflight independently prove the same
exact five stopped, restart-fenced container identities and Docker Compose
project. The handoff MUST preserve the production data volume, unrelated
containers, queue safety, and the unchanged receipt snapshot, and MUST record
removal intent before container mutation.

#### Scenario: Exact finalized recovery generation hands off

- **WHEN** a finalized recovery fleet is the exact running predecessor observed
  by normal preflight and the same exact five IDs and recovery project labels
  remain stopped with `restart=no` at target preparation
- **THEN** the fence records removal intent, removes only those exact container
  IDs without removing the data volume, proves the fleet inventory empty, and
  then permits the canonical service to start

#### Scenario: Ordinary canonical predecessor keeps its normal lifecycle

- **WHEN** normal preflight observes a predecessor with no durable finalized
  recovery handoff record
- **THEN** target preparation does not remove that predecessor through the
  recovery handoff path

#### Scenario: Unproved recovery ownership fails without removal

- **WHEN** the candidate fleet is partial, extra, running, restart-enabled,
  identity-changed, foreign-project, or inconsistent with durable recovery
  provenance
- **THEN** the fence fails before `docker rm` and keeps the canonical service
  from starting

#### Scenario: Removal-intent replay completes only the exact remaining subset

- **WHEN** the process restarts after durable exact-fleet removal intent and
  `docker rm` already removed zero or more of the recorded containers
- **THEN** the fence proves every missing recorded ID absent, proves every
  survivor has its original ID, recovery project label, stopped state, and
  `restart=no`, removes only those exact survivors, and records completion only
  after the production-volume inventory is empty
- **AND** any pre-intent partial fleet, extra writer, substituted identity,
  running survivor, restart-enabled survivor, or foreign-project survivor
  fails closed

#### Scenario: Unsafe recovery replaces a proved partial canonical target

- **WHEN** a failed normal start leaves a strict subset of expected container
  names on the production volume
- **AND** every survivor has the exact recorded target image and revision,
  canonical Compose project label, stopped state, and `restart=no`
- **AND** every missing expected canonical name is absent in every container
  state
- **THEN** recovery records the exact survivor IDs before mutation, removes
  only those IDs without `-v`, proves the volume inventory empty, and may start
  the admitted recovery image
- **AND** interruption may replay only the exact remaining recorded subset
- **AND** any extra, substituted, foreign, running, restart-enabled, or
  same-name off-volume container fails before removal

### Requirement: Failed Candidate Startup Evidence Precedes Rollback

The deploy workflow SHALL preserve bounded candidate startup evidence before
rollback can replace or remove a normal production candidate that fails before
health convergence. The evidence MUST exclude production environment values
and MUST expire automatically.

#### Scenario: Failed candidate is captured without environment disclosure

- **WHEN** the candidate daemon does not reach the public health gate
- **THEN** the workflow captures Compose container status, daemon runtime
  state, and at most the final 128 KiB of the last 200 daemon log lines
- **AND** uploads that evidence as a private workflow artifact before rollback
- **AND** does not inspect or serialize container environment values
- **AND** retains the artifact for no more than seven days
