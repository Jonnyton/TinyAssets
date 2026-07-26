> Sync-order note. `demand-side-signals` also modifies the scheduler
> requirement below to add IANA timezone, DST, missed-tick policy, and
> period-identity behavior. This block includes that complete post-change
> contract plus background target authority. `demand-side-signals` MUST sync
> first and this change MUST sync second; reversing or independently syncing
> either delta would delete one side of the merged requirement.

## MODIFIED Requirements

### Requirement: Scheduled and event-triggered invocation is persisted and restart-recoverable
Scheduled and event-triggered branch invocation (`tinyassets.scheduler`) SHALL persist cron and interval schedules and event subscriptions in the universe's as-built runs SQLite database so they survive daemon restart, with the tick loop reading durable state each tick and processing due schedules. Every persisted cron-class schedule MUST record a resolvable IANA timezone, and registration without one MUST fail rather than use the daemon's local zone. Each schedule MUST declare `skip`, `fire_once`, or `backfill_bounded(n)` missed-tick policy and persist the applied policy plus skipped/replayed counts after downtime. `skip` SHALL create no period identity or attempt; `fire_once` SHALL use exactly the most recent missed period's identity; and bounded backfill SHALL process the most recent `n` identities in chronological order and record discarded periods. A nonexistent DST local time MUST fire once at the next valid instant with its nominal identity; an ambiguous local time MUST fire once on the first UTC occurrence with one identity.

Authenticated creation MUST derive the canonical request principal, authorize the exact universe/branch operation, and atomically or recoverably pair the source with a `BackgroundBranchBinding`; `owner_actor` MUST NOT grant authority. Every due schedule-period identity or event MUST resolve one deterministic logical key and obtain one freshly revalidated `BackgroundBranchAttempt` before dispatch. Event delivery SHALL remain at most once per subscription through the persisted `scheduler_delivered_events` idempotency table linked to that attempt or an explicit denial/hold. The system SHALL rate-limit active sources per canonical principal and SHALL gate list, pause, unpause, removal, and unsubscribe to the principal or a current universe admin without transferring authorship or exposing unauthorized existence.

#### Scenario: schedules survive a restart and fire when due
- **WHEN** the scheduler starts and reads a persisted schedule whose next period is due and whose current binding revalidates
- **THEN** it creates or follows exactly one attempt for that period identity, dispatches its pinned target, and records `last_fired_at`

#### Scenario: an event is delivered exactly once per subscription
- **WHEN** the same `event_id` is emitted more than once to one subscription generation
- **THEN** all deliveries resolve to one attempt or one explicit denial/hold record and no second branch run starts

#### Scenario: per-principal rate limit and principal-gated control are enforced
- **WHEN** an authenticated principal exceeds the active-source limit, or a non-owner non-admin requests list/control/removal
- **THEN** registration is rejected for exceeding the limit and unauthorized access is refused without disclosing whether the source exists

#### Scenario: stale creation identity does not survive until fire
- **WHEN** a principal was authorized at schedule creation but loses required target access before a later due instant
- **THEN** that due instant enters a target-authority hold and no branch or provider execution begins

#### Scenario: a missed cron window resolves by declared policy and period identity
- **WHEN** the daemon returns after downtime that spanned one or more due cron periods
- **THEN** the schedule applies its declared missed-tick policy and records the skipped/replayed/discarded counts
- **AND** every admitted replay reuses its own missed period identity as the background-attempt logical key
- **AND** `skip` mints neither a period identity nor a target attempt

#### Scenario: DST gaps and overlaps issue one target attempt
- **WHEN** a schedule's local fire time falls in a spring-forward gap
- **THEN** it fires once at the next valid local instant under the nominal period identity and at most one target attempt
- **AND** a fall-back overlap fires only on the first UTC occurrence with one identity and one attempt

#### Scenario: a schedule without an IANA timezone is rejected at registration
- **WHEN** a cron-class schedule has no timezone or an unresolvable timezone
- **THEN** registration fails before a schedule or background binding is persisted

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
- **THEN** the task enters `target_authority_held` before branch resolution or run creation

## ADDED Requirements

### Requirement: Request and producer task admission commits target authority
The daemon task-ingress layer SHALL commit one background target binding with every authenticated protocol-v2 Request/admission/task aggregate and every producer task derived from a current authenticated goal subscription or accepted paid-market contract. The binding reference/digest MUST be present before a task becomes pickable. The existing epoch-2 claim remains only a scheduling reservation; the selected worker MUST claim the exact `BackgroundBranchAttempt` before branch resolution, and the B2 handoff required by `operator-request-trigger-contract` remains an additional independent gate.

#### Scenario: Protocol request is all or nothing
- **WHEN** authenticated Request admission resolves an exact branch target
- **THEN** the Request, admission, task, committed event, and target binding all commit or none commit

#### Scenario: Producer cannot authorize from content
- **WHEN** a goal-pool or paid-market producer emits a task whose source lacks a current authenticated subscription/contract target delegation
- **THEN** no pickable task or target binding is created even if pool YAML, `posted_by`, or producer identity looks authorized

#### Scenario: Target attempt precedes B2
- **WHEN** an epoch-2 worker wins the scheduling claim
- **THEN** it must claim the exact target attempt before branch resolution and separately satisfy B2 before distributed execution

### Requirement: Interrupted-run resume uses exact durable target authority
Run resume SHALL derive the canonical resume principal and revalidate run ownership, universe/branch access, cancellation, exact stored branch version, checkpoint, and durable run-binding generation. One conditional resume generation MUST create or follow one exact `BackgroundBranchAttempt`; startup `recover_in_flight_runs`, the stored run actor, and process environment MUST NOT mint resume authority. A resumed graph MUST receive child delegation from that attempt rather than reconstructing it from stored actor text.

#### Scenario: Concurrent resume has one target attempt
- **WHEN** two authenticated callers race to resume the same interrupted checkpoint generation
- **THEN** exactly one conditional resume and target attempt wins and both callers observe its outcome

#### Scenario: Startup recovery cannot resume by itself
- **WHEN** startup converts an in-flight run to interrupted
- **THEN** it fences stale execution but creates no target attempt until an authorized resume transition occurs

### Requirement: Soul-loop dispatch requires a pinned current target binding
The daemon SHALL dispatch a universe soul loop only when the current pinned `soul.md` version/content digest and normalized loop branch match one active `BackgroundBranchBinding`. Every cycle MUST claim one unique current `BackgroundBranchAttempt` bound to the eligible daemon/runtime. Missing or mismatched authority MUST hold the loop and MUST NOT fall back to `PROGRAM.md`, `UNIVERSE_SERVER_USER`, a previous soul generation, or daemon ownership as target authority.

#### Scenario: Governed target edit fences the old loop
- **WHEN** a governed soul edit changes the declared loop branch or pinned soul digest
- **THEN** an old loop attempt cannot start and dispatch waits for the exact new binding generation

#### Scenario: Legacy program fallback cannot run unattended
- **WHEN** a universe has only a legacy `PROGRAM.md` loop and no provable current binding
- **THEN** the daemon reports `reauthorization_required` without executing that loop
