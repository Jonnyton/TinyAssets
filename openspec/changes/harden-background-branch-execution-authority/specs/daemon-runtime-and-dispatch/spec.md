## MODIFIED Requirements

### Requirement: Scheduled and event-triggered invocation is persisted and restart-recoverable
Scheduled and event-triggered branch invocation (`tinyassets.scheduler`) SHALL persist cron and interval schedules and event subscriptions in the universe's runs database so they survive daemon restart, with the tick loop reading durable state each tick and processing due schedules. Authenticated creation MUST derive the canonical request principal, authorize the exact universe/branch operation, and atomically or recoverably pair the source with a `BackgroundBranchBinding`; `owner_actor` MUST NOT grant authority. Every due instant or event MUST resolve one deterministic logical key and obtain one freshly revalidated `BackgroundBranchAttempt` before dispatch. Event delivery SHALL remain at most once per subscription through durable idempotency linked to that attempt or an explicit denial/hold. The system SHALL rate-limit active sources per canonical principal and SHALL gate list, pause, unpause, removal, and unsubscribe to the principal or a current universe admin without transferring authorship or exposing unauthorized existence. As-built timing semantics remain: on restart an interval schedule catches up a single missed fire on the first tick, while a cron schedule fires only the current due minute and does NOT backfill missed cron ticks.

#### Scenario: schedules survive a restart and fire when due
- **WHEN** the scheduler starts and reads a persisted schedule whose next fire is due and whose current binding revalidates
- **THEN** it creates or follows exactly one attempt for that due instant, dispatches its pinned target, and records `last_fired_at`

#### Scenario: an event is delivered exactly once per subscription
- **WHEN** the same `event_id` is emitted more than once to one subscription generation
- **THEN** all deliveries resolve to one attempt or one explicit denial/hold record and no second branch run starts

#### Scenario: per-principal rate limit and principal-gated control are enforced
- **WHEN** an authenticated principal exceeds the active-source limit, or a non-owner non-admin requests list/control/removal
- **THEN** registration is rejected for exceeding the limit and unauthorized access is refused without disclosing whether the source exists

#### Scenario: stale creation identity does not survive until fire
- **WHEN** a principal was authorized at schedule creation but loses required target access before a later due instant
- **THEN** that due instant enters an authority hold and no branch or provider execution begins

### Requirement: Claimed-task execution binds enqueue authority to the physical queue universe
The dispatcher SHALL derive the trusted enqueue universe from the canonical physical universe directory whose queue supplied the claimed row. Before branch execution it MUST compare that value with the row's persisted `universe_id` and fail without starting a run when they differ. After a match, only the physical queue universe SHALL be passed into graph enqueue context; mutable task metadata MUST NOT redirect descendant writes. The worker MUST also resolve and atomically claim the row's exact committed `BackgroundBranchAttempt` for the task generation, physical universe, daemon/runtime/worker audience, and lease generation. A queue claim, actor string, public target, or binding reference without that attempt MUST NOT authorize branch resolution, run creation, or downstream authority.

#### Scenario: Mismatched persisted universe fails before execution
- **WHEN** a task stored in universe A's queue declares universe B in its persisted row
- **THEN** direct branch execution is refused before a run starts and no descendant is appended to either universe

#### Scenario: Matching row uses the physical universe
- **WHEN** a claimed row's persisted universe and current attempt both match the physical queue directory
- **THEN** graph execution receives that physical universe as its trusted enqueue context

#### Scenario: Lease ownership is not target authority
- **WHEN** a worker owns the queue lease but the task's attempt is absent, stale, revoked, or bound to another execution audience
- **THEN** the task enters an authority hold before branch resolution or run creation

## ADDED Requirements

### Requirement: Soul-loop dispatch requires a pinned current target binding
The daemon SHALL dispatch a universe soul loop only when the current pinned `soul.md` version/content digest and normalized loop branch match one active `BackgroundBranchBinding`. Every cycle MUST claim one unique current `BackgroundBranchAttempt` bound to the eligible daemon/runtime. Missing or mismatched authority MUST hold the loop and MUST NOT fall back to `PROGRAM.md`, `UNIVERSE_SERVER_USER`, a previous soul generation, or daemon ownership as target authority.

#### Scenario: Governed target edit fences the old loop
- **WHEN** a governed soul edit changes the declared loop branch or pinned soul digest
- **THEN** an old loop attempt cannot start and dispatch waits for the exact new binding generation

#### Scenario: Legacy program fallback cannot run unattended
- **WHEN** a universe has only a legacy `PROGRAM.md` loop and no provable current binding
- **THEN** the daemon reports `reauthorization_required` without executing that loop
