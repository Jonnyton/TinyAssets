> Sync-order note. `demand-side-signals` also modifies the scheduler
> requirement below to add IANA timezone, DST, missed-tick policy, and
> period-identity behavior. This block includes that complete post-change
> contract plus background target authority. `demand-side-signals` MUST sync
> first and this change MUST sync second; reversing or independently syncing
> either delta would delete one side of the merged requirement.
> `harden-background-provider-execution-authority` also modifies startup
> recovery and supervisor graceful drain below. That provider change MUST sync
> first; this change's complete merged blocks MUST sync second.

## MODIFIED Requirements

### Requirement: Startup recovery is lease-aware and worker-scoped, never a blanket reset
At daemon startup the runtime (`fantasy_daemon.__main__` dispatcher-startup hook) SHALL recover orphaned `running` rows with lease-aware reclaim, NOT a blanket reset of every `running` row. Startup SHALL consider rows whose `executor_worker_id` equals this worker's own uniquely-assigned ID (a provably-dead prior incarnation, via `reclaim_predecessor_tasks`) plus rows whose lease has expired or is absent (`reclaim_expired_leases` with leaseless reclaim enabled). `reclaim_predecessor_tasks` SHALL no-op on a blank worker ID; every caller SHALL pass only a uniquely-assigned ID and SHALL skip the shared host default. Before every dispatcher claim/pick, the hot sweep SHALL call only `reclaim_expired_leases` with leaseless reclaim disabled and SHALL NOT perform predecessor reclaim.

Under the effective provider-authority V2 gate, every startup reclaim path and hot-pick expired-lease reset SHALL apply the same provider-authority guard. Lease expiry alone MUST NOT prove owner death; `ProviderWorkAuthorityStore` MUST prove the owner dead or atomically invalidate/advance the old execution-claim generation, and reservation creation MUST validate that exact current generation. The store MUST prove the prior receipt has no reservation or every reservation is durably conclusive as `cancelled_before_launch`, `succeeded`, or `failed`; a dead/invalidated-owner `reserved` reservation MUST first be atomically cancelled before launch, while unclosed `launch_started`, `indeterminate`, or unreadable state holds the row non-claimable and fences the receipt.

Under the effective background-target gate, every target-bound row SHALL additionally prove the prior attempt-claim owner dead or atomically invalidate/advance that claim generation and prove that the target attempt never crossed an irreversible boundary or is durably conclusive. Conclusive recovery SHALL reclaim the same target attempt and reset the task to `pending`, including a generation-checked recovery-proven `target_authority_held` to `pending` transition, without rotating the binding or requiring a user. An indeterminate target boundary SHALL remain `target_authority_held`. The authority proofs MUST bind the exact task, provider/target claim generations, claim owner, and monotonic lease generation; timestamps are observability only and MUST NOT serve as compare-and-swap identity. Queue reset MUST compare-and-swap the unchanged authoritative tuple, and any concurrent heartbeat, renewal, or authority change forces fresh reconciliation. Epoch-2 `Epoch2BranchTaskAdapter.recover_expired` MUST apply the same applicable authority proof/fence contract as the epoch-1 startup and hot sweeps.

Non-provider-capable rows retain their provider-independent recovery rule. Dark provider/target behavior retains shipped lease recovery only for work with no corresponding authority-ledger record; any existing provider or target record remains subject to reconciliation and fencing regardless of gate state. As-built limitation: this is the cure half of the 2026-06-25 double-claim wedge, where the retired blanket `recover_claimed_tasks` reset stole live peers' tasks on every restart. Background-target recovery clauses introduced by this change MUST remain non-authorizing until the live-activation requirement and store-owner decision are satisfied.

#### Scenario: an expired-lease orphan with conclusive authority is reclaimed
- **WHEN** startup recovery finds an expired target/provider-capable row, proves its owner dead or invalidates the old claim generations, and finds every provider reservation and target irreversible boundary durably conclusive
- **THEN** the same task/target attempt is reset to `pending` with claim and lease metadata cleared
- **AND** provider budgets retain the sibling capability's settlement behavior while no new target binding or lineage unit is created
- **AND** reset compares the exact unchanged task, claim owner, lease generation, and authority proofs

#### Scenario: dispatcher pick sweep applies the same authority guards
- **WHEN** `reclaim_expired_leases` runs immediately before a dispatcher claim/pick
- **THEN** it applies the same owner invalidation, provider-reservation, target-boundary, generation, and queue compare-and-swap requirements
- **AND** it does not reclaim leaseless rows or invoke predecessor reclaim

#### Scenario: a dead-owner reserved provider attempt is cancelled before reclaim
- **WHEN** recovery proves the owner dead or invalidates its claim generation and finds a durable provider `reserved` reservation
- **THEN** it atomically changes that reservation to `cancelled_before_launch`, releases its provider authority, obtains fresh proofs, and only then attempts queue reset

#### Scenario: a fresh-lease predecessor orphan receives both authority guards
- **WHEN** startup predecessor reclaim finds a target/provider-capable row owned by a provably-dead prior worker incarnation even though its lease has not expired
- **THEN** recovery applies both authority-domain reconciliation/fencing contracts before resetting the row

#### Scenario: an ambiguous provider or target boundary is held
- **WHEN** recovery finds an unclosed provider `launch_started`/`indeterminate` reservation or an indeterminate target irreversible boundary
- **THEN** the row is not reset to pending and remains non-claimable under its domain-specific fence
- **AND** an ambiguous provider receipt is specifically `fenced_indeterminate` without automatic retry

#### Scenario: a healthy peer's fresh-lease task is untouched
- **WHEN** startup recovery runs while another worker holds a running task with a fresh lease
- **THEN** that task is left running and unclaimed by recovery

#### Scenario: a non-unique worker ID skips predecessor reclaim
- **WHEN** the worker ID is blank or equal to the shared host default
- **THEN** the helper no-ops on blank and callers skip the shared default, leaving lease TTL as the only fallback

#### Scenario: lease renewal defeats stale recovery proof
- **WHEN** a worker heartbeat or lease renewal changes the queue row after authority proof but before reset
- **THEN** queue compare-and-swap fails and recovery obtains fresh authority and queue evidence before retrying

#### Scenario: expired lease invalidates stale claims
- **WHEN** lease expiry makes a target/provider-capable row eligible but worker death cannot be proved
- **THEN** recovery atomically advances the applicable old execution-claim generations before issuing reconciliation proofs
- **AND** later attempts from the stale worker fail generation validation

#### Scenario: dark rows with no ledger retain shipped recovery
- **WHEN** the effective authority gates are dark and an eligible row has no provider or target ledger record
- **THEN** startup recovery retains canonical shipped lease-aware behavior
- **AND** any existing authority record remains subject to reconciliation and fencing

#### Scenario: work outside an authority domain retains its recovery rule
- **WHEN** an eligible row is non-provider-capable or has no background target domain under the effective live gates
- **THEN** that inapplicable domain adds no new recovery precondition while every applicable domain still reconciles

### Requirement: The supervisor keeps one daemon subprocess alive with backoff, producer restart, auth quarantine, and graceful drain
The cloud-worker supervisor (`tinyassets.cloud_worker` run-supervisor loop) SHALL spawn the daemon subprocess, wait for its exit, and respawn it with exponential backoff — a shorter idle backoff after clean (no-work) exits and a longer crash backoff after non-zero exits — until a SIGTERM/SIGINT stop is requested. While a subprocess runs it SHALL poll for newly queued branch tasks and restart the child so pending work is picked up, SHALL write a phase-tagged heartbeat file, and SHALL quarantine itself (skip spawn, beat, back off, re-check) when the writer provider is unauthenticated so a dead-auth worker never claims-and-fails tasks. Under the effective provider-authority V2 gate it SHALL also quarantine before spawn or claim when maintenance authority is unavailable and records `auth_unknown`; while dark, it SHALL retain the shipped rule that quarantines only on `not_logged_in`.

On a stop signal, once child death is CONFIRMED, graceful drain SHALL release that worker's orphaned leases only after every applicable authority domain passes the same proof, reconciliation, fence, monotonic generation, and queue compare-and-swap rules as startup recovery. A provider-capable orphan MUST pass dead-or-invalidated-owner and reservation reconciliation; an unclosed `launch_started`, `indeterminate`, or unreadable reservation remains fenced/non-claimable. A target-bound orphan MUST pass dead-or-invalidated-owner and irreversible-boundary reconciliation; conclusive state advances/reclaims the same target-attempt generation for a peer, while an indeterminate boundary moves/remains `target_authority_held`. Non-provider/non-target rows retain shipped graceful-drain release. Dark behavior retains shipped release only for rows with no applicable authority record; every existing record reconciles regardless of gate state. Background-target drain clauses MUST remain dark until live-activation prerequisites pass.

#### Scenario: backoff differs by exit kind
- **WHEN** the subprocess exits cleanly versus crashing
- **THEN** the supervisor sleeps an idle backoff after the clean exit and a crash backoff after the crash
- **AND** consecutive exits of the same kind grow up to the configured ceiling

#### Scenario: newly queued work restarts the child
- **WHEN** a pending branch task appears while the subprocess is running and no branch task is already running
- **THEN** the supervisor restarts the subprocess so the pending task is claimed on the next spawn

#### Scenario: an unauthenticated writer quarantines the worker
- **WHEN** the writer provider reports `not_logged_in` before a spawn
- **THEN** the supervisor skips spawn, writes an `auth_quarantined` heartbeat, and backs off without claiming a task

#### Scenario: unavailable V2 maintenance authority quarantines provider work
- **WHEN** the effective worker/provider V2 gate is active and maintenance authority lacks fresh conclusive health evidence
- **THEN** the supervisor records `auth_unknown`, skips spawn, and backs off without claiming provider-capable work
- **AND** ordinary router unknown health is not reinterpreted as `not_logged_in`

#### Scenario: confirmed child death reconciles every authority domain
- **WHEN** a stop signal terminates the child and its exit is confirmed
- **THEN** graceful drain releases only leases whose provider reservations and target irreversible boundaries are conclusive under exact generation proofs
- **AND** ambiguous provider state remains fenced and ambiguous target state remains `target_authority_held` without peer execution

### Requirement: Scheduled and event-triggered invocation is persisted and restart-recoverable
Scheduled and event-triggered branch invocation (`tinyassets.scheduler`) SHALL persist cron and interval schedules and event subscriptions in the universe's as-built runs SQLite database so they survive daemon restart, with the tick loop reading durable state each tick and processing due schedules. Every persisted cron-class schedule MUST record a resolvable IANA timezone, and registration without one MUST fail rather than use the daemon's local zone. Each schedule MUST declare `skip`, `fire_once`, or `backfill_bounded(n)` missed-tick policy and persist the applied policy plus skipped/replayed counts after downtime. `skip` SHALL create no period identity or attempt; `fire_once` SHALL use exactly the most recent missed period's identity; and bounded backfill SHALL process the most recent `n` identities in chronological order and record discarded periods. A nonexistent DST local time MUST fire once at the next valid instant with its nominal identity; an ambiguous local time MUST fire once on the first UTC occurrence with one identity.

Authenticated creation MUST derive the canonical request principal, authorize the exact universe/branch operation, and atomically or recoverably pair the source with a `BackgroundBranchBinding`; `owner_actor` MUST NOT grant authority. Every due schedule-period identity or event MUST resolve one deterministic logical key and obtain one freshly revalidated `BackgroundBranchAttempt` before dispatch. Event delivery SHALL remain at most once per subscription through the persisted `scheduler_delivered_events` idempotency table linked to that attempt or an explicit denial/hold. The system SHALL rate-limit active sources per canonical principal and SHALL gate list, pause, unpause, removal, and unsubscribe to the principal or a current universe admin without transferring authorship or exposing unauthorized existence.
Background-target clauses introduced by this change MUST remain dark/non-authorizing until the live-activation requirement, dependency sync order, and store-owner decision are satisfied; demand-side timing behavior may activate under its own owner.

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
The epoch-1 dispatcher SHALL derive the trusted enqueue universe from the canonical physical universe directory whose queue supplied the claimed row; an epoch-2 dispatcher SHALL derive the equivalent canonical physical tenant/universe namespace from its transactional queue owner without imposing a filesystem directory. Before branch execution each MUST compare that value with the row's persisted `universe_id` and fail without starting a run when they differ. After a match, only that physical universe/tenant binding SHALL be passed into graph enqueue context; mutable task metadata MUST NOT redirect descendant writes. The worker MUST verify its queue lease generation, resolve and atomically claim the row's exact committed `BackgroundBranchAttempt` for the task/source generation and daemon/runtime/worker audience, then reverify the unchanged lease before branch resolution. A queue claim, actor string, public target, or binding reference without that attempt MUST NOT authorize branch resolution, run creation, or downstream authority. A provably dead/invalidated predecessor with a conclusive pre-execution boundary MUST permit autonomous same-attempt claim-generation recovery; only missing/revoked/unauthorized/indeterminate target authority enters `target_authority_held`. If post-claim lease revalidation fails before an irreversible boundary, the target claim MUST be released or fenced automatically. Background-target clauses introduced by this change MUST remain dark/non-authorizing until the live-activation requirement and store-owner decision are satisfied.

#### Scenario: Mismatched persisted universe fails before execution
- **WHEN** a task stored in universe A's queue declares universe B in its persisted row
- **THEN** direct branch execution is refused before a run starts and no descendant is appended to either universe

#### Scenario: Matching row uses the physical universe
- **WHEN** a claimed row's persisted universe and current attempt both match the physical queue directory
- **THEN** graph execution receives that physical universe as its trusted enqueue context

#### Scenario: Lease ownership is not target authority
- **WHEN** a worker owns the queue lease but the task's attempt is absent, stale, revoked, or bound to another execution audience
- **THEN** it cannot resolve or execute the branch
- **AND** a provably dead predecessor with a conclusive boundary is autonomously reclaimed, while missing/revoked/unauthorized/indeterminate target authority enters `target_authority_held`

### Requirement: Branch-task cancellation distinguishes observed pending and running work
The queue-cancel action SHALL mark a task observed as pending terminally `cancelled` through a later locked mutation. A task observed as `target_authority_held` MUST require the canonical authorizing principal or current universe admin, atomically revoke/fence its binding and attempt generations, and mark that same row terminally `cancelled`; actor strings and queue possession grant nothing. For a task observed as `running`, cancellation MUST require either the claiming daemon identity or the `cancel_branch_task` capability and set an idempotent cooperative-cancel flag under the queue lock. The legacy wrapper graph stream SHALL poll that flag at inter-node events and finalize an observed cancellation as `cancelled`, not `failed`. Current direct BranchTask and NodeBid execution paths do not poll the BranchTask flag and therefore do not guarantee cooperative cancellation. The initial status read and later mutation remain separate locked operations, so a concurrent pending-to-running claim can enter the immediate cancel path without the running-task authorization check. Held-status clauses introduced by this change MUST remain dark until target-authority activation prerequisites pass.

#### Scenario: Work observed pending is cancelled immediately
- **WHEN** queue cancellation targets a pending branch task
- **THEN** the task is marked `cancelled` without entering cooperative running-task cancellation

#### Scenario: Authorized held work is cancelled and fenced
- **WHEN** the canonical authorizing principal or current universe admin cancels a `target_authority_held` task
- **THEN** its binding/attempt generations are revoked or fenced and that same row becomes terminally `cancelled`

#### Scenario: Unauthorized held or running cancellation is refused
- **WHEN** a caller lacks the canonical held-task principal/admin authority and the running-task daemon/capability authority
- **THEN** cancellation returns `cancel_not_authorized` without changing the row or its authority

#### Scenario: Legacy wrapper cancellation is cooperative and idempotent
- **WHEN** an authorized actor requests cancellation one or more times for a running task executing through the legacy wrapper stream
- **THEN** the cancel flag remains set, that stream observes it between node events, and finalizes the task as `cancelled`

#### Scenario: Direct execution can finish after a cancellation request
- **WHEN** cancellation is requested during direct BranchTask or NodeBid execution
- **THEN** the flag is retained, but the current executor may still finalize the task from its execution outcome

#### Scenario: Pending classification has a claim race
- **WHEN** a task is claimed after queue-cancel observes it as pending but before the immediate status mutation
- **THEN** the running task can be marked cancelled without passing the running-task authorization branch

### Requirement: Queue garbage collection archives only old terminal tasks
The branch-task garbage collector SHALL, under the queue file lock, move only terminal tasks whose string-valued `queued_at` parses before the configured cutoff into the archive. It MUST retain pending, running, `target_authority_held`, recent terminal, missing/empty-date, and terminal rows whose string date raises `ValueError` in `datetime.fromisoformat`; a truthy non-string date currently raises `TypeError` and aborts collection. A held row becomes archive-eligible only after authorized cancellation or another valid terminal transition. The collector SHALL replace the archive atomically before rewriting the live queue. Because archived origin rows remain authoritative input to lifetime lineage admission, an existing blank, whitespace-only, unreadable, invalid-JSON, or non-list archive MUST fail collection without replacing the archive or rewriting the live queue. A missing archive SHALL mean empty history. A repeated collection after an archive-first/live-second interruption SHALL not duplicate an identified task already present in the archive. Held-status clauses introduced by this change MUST remain dark until target-authority activation prerequisites pass.

#### Scenario: Active, held, and recent tasks survive collection
- **WHEN** garbage collection sees old pending, running, or `target_authority_held` tasks and a recent terminal task
- **THEN** all of those rows remain in the live queue

#### Scenario: Cancelled held work moves to the archive
- **WHEN** a formerly held task is terminally cancelled and has a parseable `queued_at` before the cutoff
- **THEN** it is appended to the archive and removed from the live queue while retaining one lifetime-lineage charge

#### Scenario: Old ordinary terminal work moves to the archive
- **WHEN** any succeeded, failed, or cancelled task has a parseable `queued_at` before the cutoff
- **THEN** it is appended to the archive and removed from the live queue

#### Scenario: Interrupted collection converges without archive duplication
- **WHEN** an identified terminal task is already archived but remains in the live queue after an interrupted collection
- **THEN** a later collection removes the live copy without appending a second archived copy

#### Scenario: Corrupt prior archive blocks collection instead of erasing lineage truth
- **WHEN** old terminal rows are eligible for collection while the existing archive cannot be read as a JSON list
- **THEN** collection raises without replacing the archive or removing rows from the live queue

#### Scenario: Blank prior archive is corrupt history
- **WHEN** old terminal rows are eligible for collection while the existing archive is empty or whitespace-only
- **THEN** collection raises without treating that file as a missing empty archive

## ADDED Requirements

### Requirement: Request, producer, and wiki forward-trigger task admission commits target authority
The daemon task-ingress layer SHALL commit one background target binding with every authenticated protocol-v2 Request/admission/task aggregate, every producer task derived from a current authenticated goal subscription or landed accepted paid-market execution contract, and every authenticated wiki `file_bug` investigation forward-trigger. Market producer output MUST remain held/non-pickable until `paid-market-track-e-wave-2-transport` supplies that accepted contract generation. The binding reference/digest MUST be present before a task becomes pickable. The existing epoch-2 claim remains only a scheduling reservation; the selected worker MUST claim the exact `BackgroundBranchAttempt` before branch resolution, and the B2 handoff required by `operator-request-trigger-contract` remains an additional independent gate. Target-authority clauses MUST remain dark until the live-activation requirement and all named owners have landed.

#### Scenario: Protocol request is all or nothing
- **WHEN** authenticated Request admission resolves an exact branch target
- **THEN** the Request, admission, task, committed event, and target binding all commit or none commit

#### Scenario: Producer cannot authorize from content
- **WHEN** a goal-pool or paid-market producer emits a task whose source lacks a current authenticated subscription/contract target delegation
- **THEN** no pickable task or target binding is created even if pool YAML, `posted_by`, or producer identity looks authorized

#### Scenario: Wiki bug forwarding is authenticated and atomic
- **WHEN** an authenticated wiki write commits a `file_bug` revision that requests investigation
- **THEN** the filing revision, exact investigation binding, and task commit as one transaction or recoverable pair
- **AND** no bare `bug_investigation.append_task` row becomes pickable

#### Scenario: Target attempt precedes B2
- **WHEN** an epoch-2 worker wins the scheduling claim
- **THEN** it must claim the exact target attempt before branch resolution and separately satisfy B2 before distributed execution

### Requirement: Soul-loop dispatch requires a pinned current target binding
The daemon SHALL dispatch a universe soul loop only when the current pinned `soul.md` version/content digest and normalized `loop_branch_def_id`/`Loop branch` declaration match one active `BackgroundBranchBinding`. Every cycle MUST claim one unique current `BackgroundBranchAttempt` bound to the eligible daemon/runtime. The production-default compiled `branches/universe_cycle.yaml` stream MUST be retired as an execution bypass and may continue only after registration as an ordinary Branch version plus authenticated creation or provable founder/admin migration into governed soul authority. Missing or mismatched authority MUST hold the loop and MUST NOT fall back to the built-in stream, `PROGRAM.md`, `UNIVERSE_SERVER_USER`, a previous soul generation, or daemon ownership as target authority. These enforcement clauses MUST remain dark until live-activation prerequisites pass.

#### Scenario: Governed target edit fences the old loop
- **WHEN** a governed soul edit changes the declared loop branch or pinned soul digest
- **THEN** an old loop attempt cannot start and dispatch waits for the exact new binding generation

#### Scenario: Legacy program fallback cannot run unattended
- **WHEN** a universe has only a legacy `PROGRAM.md` loop and no provable current binding
- **THEN** the daemon reports `reauthorization_required` without executing that loop

#### Scenario: Built-in cycle is converted before enforcement
- **WHEN** a legacy universe previously ran the compiled default universe cycle
- **THEN** it continues only after that cycle is a registered Branch version declared in governed soul state with a valid binding
- **AND** ambiguous universes hold for connector reauthorization instead of streaming the built-in graph directly
