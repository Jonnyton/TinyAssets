## MODIFIED Requirements

### Requirement: Tray-to-cloud cutover is single-active
The system MUST store one server-authoritative activation record keyed by `(universe_id, automation_id)` with a monotonically increasing epoch, active executor class, exactly one typed immutable execution subject, lease identity, and state. Ordinary Branch automation MUST retain its existing server-owned automation identity and `branch_version` subject. Agent runtime activation MUST derive its reserved automation identity only from `("agent_binding", agent_binding_id)`, so the existing primary key is also the uniqueness fence for `(universe_id, agent_binding_id)` and no caller-selected alias can activate a second manifest. Activation, subject rebind, stop, cutover, and rollback MUST use compare-and-swap transitions, and every claim MUST validate the exact current epoch, executor class, execution-subject kind/reference/digest, and lease. The system MUST require the tray drain to stop before cloud acceptance and cloud automation to stop before rollback reactivates the tray; competing subjects, alternate activation identities, and stale or partitioned attempts MUST fail closed rather than claim.

#### Scenario: Tray is still active at cloud activation
- **WHEN** cloud activation observes that the tray drain can still claim work
- **THEN** cloud activation fails closed and neither executor is accepted as the sole active drain

#### Scenario: Rollback restores the tray
- **WHEN** Jonathan rolls back from cloud execution to the temporary tray bridge
- **THEN** the cloud activation is durably stopped before the tray is allowed to claim

#### Scenario: Stale executor retains cached activation state
- **WHEN** a tray or cloud worker presents an old epoch, executor class, subject digest, or lease after another activation transition
- **THEN** claim validation fails without queue or STATUS mutation

#### Scenario: Competing Branch versions race
- **WHEN** two immutable Branch versions attempt to activate or claim concurrently under distinct local identities
- **THEN** at most one compare-and-swap transition owns the current epoch and only that exact epoch and `branch_version` subject can claim

#### Scenario: Competing agent manifests race through aliases
- **WHEN** concurrent callers request different local automation IDs or manifests for the same `(universe_id, agent_binding_id)`
- **THEN** the server derives one reserved automation key and at most one compare-and-swap winner owns the current epoch, `agent_runtime_manifest` subject, executor, and lease

## ADDED Requirements

### Requirement: Cloud continuation preserves the exact execution subject
The canonical cloud-continuation owner SHALL carry exactly one typed immutable execution-subject kind/reference/digest and SHALL validate that same tuple with the activation epoch, executor, lease, admission identity, grants, and budgets on prepare, claim, resume, and reconciliation. A Branch continuation SHALL retain its exact Branch attempt and lineage requirements. An agent invocation continuation SHALL retain its exact server-issued invocation command and invocation identity and MUST NOT fabricate, create, read, or mutate a `BackgroundBranchAttempt`.

#### Scenario: Agent worker restarts after admission
- **WHEN** an agent invocation worker stops after durable admission or provider reservation
- **THEN** continuation recovery reconciles the same command, invocation, activation, subject, provider reservation, and continuation identities before any retry
- **AND** no replacement invocation or Branch attempt is minted

#### Scenario: Continuation subject differs from activation
- **WHEN** a continuation presents a different subject kind, reference, or digest than the exact current activation
- **THEN** preparation, claim, or resume fails before provider authority, spend, or output finalization
