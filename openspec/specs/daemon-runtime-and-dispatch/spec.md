# Daemon Runtime and Dispatch

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

The 24/7 uptime engine: stateless dispatcher selection, file-locked lease claims, supervisor with backoff and healthcheck, host singleton lock, persisted scheduler, fleet idle-cycle single-flight, and the durable work-target registry.
## Requirements
### Requirement: Dispatcher selection is a stateless deterministic function invoked at cycle boundaries
The branch-task dispatcher (`tinyassets.dispatcher`) SHALL select the next task with a pure, stateless function that reads the persisted queue, keeps only `pending` tasks whose trigger-source tier is enabled, scores each by a deterministic `tier_weight + recency_decay + user_boost` formula, and returns the single highest-scoring task (ties broken by oldest `queued_at`) or `None` when nothing is eligible. It SHALL be invoked exactly at graph-cycle boundaries — once at daemon startup and once between cycle-wrapper returns — and SHALL NOT run its own timer or continuous polling loop. The selector SHALL only read the queue and SHALL never claim or mutate it, and deferred market and goal-affinity terms SHALL contribute zero until their coefficients are configured, without re-shaping the score.

#### Scenario: highest-scoring eligible task wins
- **WHEN** `select_next_task` runs over a queue containing pending and non-pending tasks
- **THEN** it returns the single pending, tier-enabled task with the highest score
- **AND** ties on score are broken by the oldest `queued_at`

#### Scenario: no eligible task yields None
- **WHEN** the queue is empty or every pending task's tier is disabled
- **THEN** `select_next_task` returns `None`

#### Scenario: selection never mutates the queue
- **WHEN** `select_next_task` chooses a task
- **THEN** the returned task is still `pending` on disk and no row is claimed or rewritten by the selector

### Requirement: Queue-state mutations are file-locked, single-winner, and terminally idempotent
All branch-task queue mutations (`tinyassets.branch_tasks`) SHALL execute under an exclusive per-universe file lock so concurrent workers sharing the queue file cannot race. `claim_task` SHALL transition a task to `running` only if it is still `pending`, returning `None` otherwise, so any given task is claimed by at most one worker. `mark_status` SHALL raise on an invalid non-terminal transition, but SHALL treat a duplicate finalize of an already-terminal task as an idempotent no-op that keeps the first result and never crashes the daemon (first-writer-wins).

#### Scenario: only one worker claims a pending task
- **WHEN** two workers call `claim_task` for the same pending task
- **THEN** exactly one receives the claimed task transitioned to `running`
- **AND** the other receives `None`

#### Scenario: duplicate finalize on a terminal task is a no-op
- **WHEN** `mark_status` is called on a task that is already in a terminal state
- **THEN** the call returns without raising and without changing the existing terminal result

#### Scenario: an invalid non-terminal transition raises
- **WHEN** `mark_status` requests a transition that is not permitted from the current non-terminal state
- **THEN** it raises rather than corrupting the row

### Requirement: Startup recovery is lease-aware and worker-scoped, never a blanket reset
At daemon startup the runtime (`fantasy_daemon.__main__` dispatcher-startup hook) SHALL recover orphaned `running` rows with lease-aware reclaim, NOT a blanket reset of every `running` row. It SHALL reclaim only rows whose `executor_worker_id` equals this worker's own uniquely-assigned id (a provably-dead prior incarnation, via `reclaim_predecessor_tasks`) plus rows whose lease has expired or is absent (`reclaim_expired_leases` with leaseless reclaim enabled), so a live peer holding a fresh lease is never reclaimed. Predecessor reclaim SHALL be a no-op when the worker id is blank or the shared host default, because a non-unique id could belong to a live twin. As-built limitation: this is the cure half of the 2026-06-25 double-claim wedge, where the retired blanket `recover_claimed_tasks` reset stole live peers' tasks on every restart.

#### Scenario: an expired-lease orphan is reclaimed
- **WHEN** startup recovery runs and finds a `running` row whose lease has expired
- **THEN** the row is reset to `pending` with its claim and lease metadata cleared

#### Scenario: a healthy peer's fresh-lease task is untouched
- **WHEN** startup recovery runs while another worker holds a `running` task with a fresh lease
- **THEN** that task is left `running` and unclaimed by recovery

#### Scenario: a non-unique worker id skips predecessor reclaim
- **WHEN** the worker id is blank or equal to the shared host default
- **THEN** `reclaim_predecessor_tasks` reclaims nothing and the lease TTL remains the only fallback

### Requirement: The supervisor keeps one daemon subprocess alive with backoff, producer restart, auth quarantine, and graceful drain
The cloud-worker supervisor (`tinyassets.cloud_worker` run-supervisor loop) SHALL spawn the daemon subprocess, wait for its exit, and respawn it with exponential backoff — a shorter idle backoff after clean (no-work) exits and a longer crash backoff after non-zero exits — until a SIGTERM/SIGINT stop is requested. While a subprocess runs it SHALL poll for newly-queued branch tasks and restart the child so pending work is picked up, SHALL write a phase-tagged heartbeat file, and SHALL quarantine itself (skip the spawn, beat, back off, re-check) when the writer provider is unauthenticated so a dead-auth worker never claims-and-fails tasks. On a stop signal, once the child's death is CONFIRMED, it SHALL release that worker's own orphaned leases so a live peer can pick the work up immediately rather than waiting out the lease TTL.

#### Scenario: backoff differs by exit kind
- **WHEN** the subprocess exits cleanly versus crashing
- **THEN** the supervisor sleeps an idle backoff after the clean exit and a crash backoff after the crash
- **AND** consecutive exits of the same kind grow the backoff up to its ceiling

#### Scenario: newly queued work restarts the child
- **WHEN** a pending branch task appears while the subprocess is running and no branch task is already running
- **THEN** the supervisor restarts the subprocess so the pending task is claimed on the next spawn

#### Scenario: an unauthenticated writer quarantines the worker
- **WHEN** the writer provider reports `not_logged_in` before a spawn
- **THEN** the supervisor skips the spawn, writes an `auth_quarantined` heartbeat, and backs off without claiming any task

#### Scenario: confirmed child death releases its leases
- **WHEN** a stop signal terminates the child and its exit is confirmed
- **THEN** the supervisor releases that worker's own orphaned leases during graceful drain

### Requirement: The container healthcheck asserts liveness, not mere process existence
The container healthcheck (`tinyassets.cloud_worker_healthcheck`) SHALL report healthy only when the supervisor heartbeat file exists, is parseable, and is fresh relative to the supervisor's own declared backoff sleep bounded by a hard staleness floor, AND no pickable branch task has been waiting past the pickable-staleness bound. It SHALL exit 0 when healthy and exit 1 with a one-line reason otherwise, so a wedged-but-running worker (a stale heartbeat or pickable work stuck unpicked) is reported unhealthy and self-heals via container restart rather than passing a naive process-alive check.

#### Scenario: a missing or stale heartbeat is unhealthy
- **WHEN** the supervisor heartbeat file is absent, unreadable, or older than its allowed staleness
- **THEN** the healthcheck reports unhealthy and exits 1 with a one-line reason

#### Scenario: stuck pickable work is unhealthy
- **WHEN** a pickable branch task has been waiting past the pickable-staleness bound while the heartbeat is stale
- **THEN** the healthcheck reports unhealthy

#### Scenario: a beating supervisor with no stuck work is healthy
- **WHEN** the heartbeat is fresh and no pickable work is waiting past the bound
- **THEN** the healthcheck reports healthy and exits 0

### Requirement: Host-singleton and fleet idle-cycle coordination fail safe
Two file-lock coordination primitives SHALL keep the runtime safe under concurrency. `tinyassets.singleton_lock` SHALL enforce a single host daemon instance via an OS-exclusive file lock that is the ground truth, with a PID sidecar as a human-readable breadcrumb; a PID sidecar without a held OS lock SHALL be treated as stale and overwritten on acquisition. `tinyassets.idle_cycle` SHALL dedupe the no-work heartbeat cycle across a fleet with a run lock plus a freshness stamp, skipping when another worker is mid-cycle or has a fresh stamp, and SHALL fail OPEN — degrading to a possibly-duplicate cycle, never a stalled heartbeat — when its lock or stamp I/O fails.

#### Scenario: a second host instance cannot acquire the lock
- **WHEN** a second process attempts to acquire the singleton lock while another live process holds it
- **THEN** acquisition fails and reports the holding PID from the sidecar

#### Scenario: a stale PID sidecar is overwritten
- **WHEN** a PID sidecar exists but no process holds the paired OS lock
- **THEN** acquisition succeeds and the sidecar is overwritten with the new PID

#### Scenario: a fresh foreign idle-cycle stamp is skipped
- **WHEN** a worker attempts the idle cycle while a different worker's stamp is within the freshness window
- **THEN** it declines the slot and does not run a duplicate no-work cycle

#### Scenario: idle-cycle coordination I/O failure fails open
- **WHEN** the idle-cycle run lock or stamp I/O errors
- **THEN** the slot is granted (fail open) so the heartbeat cannot stall

### Requirement: Scheduled and event-triggered invocation is persisted and restart-recoverable
Scheduled and event-triggered branch invocation (`tinyassets.scheduler`) SHALL persist cron and interval schedules and event subscriptions in the universe's runs SQLite database so they survive daemon restart, with the tick loop reading the database each tick and firing due schedules. It SHALL deliver each event at most once per subscription through a persisted `scheduler_delivered_events` idempotency table, SHALL rate-limit active schedules and subscriptions per owner, and SHALL gate schedule removal to the owner or an admin. As-built limitation: on restart an interval schedule catches up a single missed fire on the first tick (its interval has already elapsed), but a cron schedule fires only the current due minute and does NOT backfill cron ticks missed while the daemon was down.

#### Scenario: schedules survive a restart and fire when due
- **WHEN** the scheduler starts and reads a persisted schedule whose next fire is due
- **THEN** it fires the schedule's branch and records `last_fired_at`

#### Scenario: an event is delivered exactly once per subscription
- **WHEN** the same `event_id` is emitted more than once to a subscription already recorded in `scheduler_delivered_events`
- **THEN** the subscription fires only once and the redelivery is a no-op

#### Scenario: per-owner rate limit and owner-gated removal are enforced
- **WHEN** an owner exceeds the per-owner active-schedule limit, or a non-owner non-admin requests removal
- **THEN** the registration is rejected for exceeding the limit and the removal is refused for lacking ownership

### Requirement: The work-target registry has an explicit lifecycle
Every durable `WorkTarget` record SHALL carry a `lifecycle` field.
`WorkTarget.from_dict` SHALL coerce that field to a string; `create_target`
SHALL accept the caller-supplied lifecycle without closed-enum validation. For
string inputs, arbitrary values SHALL round-trip. The module publishes the
conventional values `active`, `paused`, `dormant`, `complete`, `superseded`,
`marked_for_discard`, and `discarded`; transition helpers use the values
applicable to their operation. `mark_target_for_discard` SHALL set
`marked_for_discard` and record the review cycle. `discard_target` SHALL leave
the target marked until the configured review delay has elapsed, then set
`discarded`, retain the registry row, write the archival JSON copy, and record
the recoverability deadline.

#### Scenario: a target carries an explicit lifecycle state
- **WHEN** a target is created with the default lifecycle, a transition helper changes it, or generic construction/deserialization receives another string
- **THEN** the supplied lifecycle string is persisted and round-trips
- **AND** transition helpers use conventional named values, but the generic boundary does not enforce a closed enum

#### Scenario: discard is a delayed two-step, not immediate deletion
- **WHEN** a target is marked for discard and `discard_target` is called before the review delay has elapsed
- **THEN** the target stays `marked_for_discard`
- **AND** only after the delay does finalization set `discarded`, write the archival copy, and retain a recoverability deadline

### Requirement: Soul guidance is a bounded advisory input to deterministic dispatch
The dispatcher SHALL apply soul guidance only after the ordinary pending-status, enabled-tier, required-LLM-type, and preferred-request-type filters, and SHALL use it only to reject work explicitly directed to another bound daemon or to add a non-negative capped affinity term to the existing deterministic queue score. `soul_guided_dispatch_read` MUST remain read-only: it derives affinity from token overlap with the active daemon's domain claims and soul plus the importance of at most three open mini-brain hints, but it neither claims nor mutates a task. This shipped path does not ask a model to choose among souls or candidates and does not persist a soul-choice receipt.

#### Scenario: default configuration leaves soul guidance inert
- **WHEN** selection runs with the default empty `active_daemon_id` and zero `soul_affinity_coefficient`
- **THEN** every otherwise eligible task receives a zero soul adjustment, a task's `directed_daemon_id` is not enforced without an active daemon binding, and ordinary deterministic queue policy decides the winner

#### Scenario: a bound daemon enforces requester direction
- **WHEN** `active_daemon_id` is non-empty and an otherwise eligible task has a different non-empty `directed_daemon_id`
- **THEN** soul guidance marks that task ineligible before scoring it, while an undirected task or a task directed to the active daemon remains eligible

#### Scenario: affinity is advisory and bounded
- **WHEN** a bound daemon has domain-claim, soul-token, or open mini-brain matches for an eligible task and the configured coefficient is positive
- **THEN** the dispatcher adds `min(max(0, coefficient) * raw_affinity, max(0, term_cap))` to the ordinary score and does not let the affinity term bypass any ordinary eligibility filter

#### Scenario: unavailable soul or brain data fails open
- **WHEN** active-daemon lookup fails, or the optional mini-brain hint read fails
- **THEN** the dispatcher logs the advisory-read failure and retains ordinary task eligibility, using zero adjustment when the daemon itself is unavailable and any remaining soul or claim evidence when only brain hints are unavailable

#### Scenario: selection produces no model choice receipt
- **WHEN** soul-guided selection chooses a task
- **THEN** the result is still the deterministic top `BranchTask` from the in-memory score ordering, with no model invocation, autonomous soul choice, or persisted soul-selection receipt

### Requirement: Generic work targets persist records and expose guarded helper transitions
The generic work-target layer SHALL persist a `WorkTarget` record keyed by `target_id` with title, home link, role, publish stage, lifecycle, intent, tags, artifact/note/target/timeline/lineage references, selection reason, metadata, timestamps, and producer origin. It MUST support load, replace, lookup, and upsert through the daemon storage server with JSON fallback; active-only selection with an optional role filter; create, provisional-create, role reclassification, publish commit, discard, and review/execution artifact helpers. The exported role, publish-stage, lifecycle, and origin literals are conventions used by these helpers, not validated enums: `from_dict`, `create_target`, and producer origin stamping currently permit arbitrary strings to persist. The JSON fallback path SHALL NOT be represented as sharing the branch-task queue's file-locking guarantee; its read/replace/upsert operations are not protected by that queue lock.

#### Scenario: a generic target round-trips through storage
- **WHEN** a caller creates or upserts a target and later loads or looks it up by `target_id`
- **THEN** the record fields and references round-trip through the daemon storage server, or through `work_targets.json` when that server operation raises, and the upsert refreshes `updated_at`

#### Scenario: selectable registry reads exclude non-active records
- **WHEN** `list_selectable_targets` reads records with active and non-active lifecycle values and an optional role filter
- **THEN** it returns only records whose lifecycle string is exactly `active` and, when supplied, whose role string exactly matches the requested role

#### Scenario: helper transitions guard publish state
- **WHEN** a notes target is reclassified as publishable and then committed
- **THEN** reclassification first sets `publish_stage` to `provisional`, commit changes it to `committed`, and reclassification back to notes resets it to `none` and can emit a reconciliation note

#### Scenario: enum-like fields remain permissive
- **WHEN** stored input or a helper caller supplies an unrecognized role, publish-stage, lifecycle, or origin string
- **THEN** the generic record layer persists that string rather than rejecting it as outside a closed enum, although built-in filters and transitions only recognize their named constants

#### Scenario: discard is delayed and recoverable
- **WHEN** a target is marked for discard at review cycle N
- **THEN** it remains `marked_for_discard` until at least 20 review cycles have elapsed, after which finalization sets it to `discarded`, writes an archival JSON copy, and records a 30-day recoverability deadline instead of deleting the registry row

#### Scenario: review and execution artifacts are durable but not a complete public snapshot
- **WHEN** a review stage or execution handoff writes its payload
- **THEN** the helper stores a uniquely named JSON artifact under `artifacts/reviews` or an execution-ID-named JSON artifact under `artifacts/executions`, while the current read tools expose `work_targets.json` and `status.json` separately and do not provide one complete public snapshot joining targets, hard priorities, review artifacts, and execution artifacts

### Requirement: Fantasy foundation review gates authorial work on current hard priorities
The fantasy-domain universe graph SHALL enter `foundation_priority_review` before authorial selection, finalize eligible delayed discards, synchronize source-synthesis priorities, collect soft conflicts, and persist a foundation review artifact. It MUST treat only active records with `hard_block=true` as blockers and currently creates such blockers for fantasy source-upload synthesis; this review topology is fantasy-specific and is not a generic daemon-engine review protocol.

#### Scenario: an unsynthesized source upload hard-blocks authorial work
- **WHEN** synchronized source state yields one or more active hard priorities
- **THEN** foundation review selects the first hard priority's target, sets intent to `synthesize source upload`, routes `current_task` and `task_queue` to `worldbuild`, reports stage `foundation`, and records the priorities and synthesis signals in a review artifact

#### Scenario: soft conflicts remain visible without blocking
- **WHEN** undismissed notes categorized as `concern` or `error` exist but no active hard priority exists
- **THEN** foundation review includes them as soft conflicts, reports stage `authorial`, leaves the selected target and current task empty, and allows the graph to continue to authorial review

#### Scenario: clearly wrong remains soft at the foundation gate
- **WHEN** a collected concern or error carries `clearly_wrong=true` but has no corresponding active hard-priority record
- **THEN** foundation review reports the flag in `soft_conflicts` and does not promote it into a hard blocker

#### Scenario: foundation review finalizes eligible discards
- **WHEN** a target has remained marked for discard for the configured 20-cycle delay when foundation review runs
- **THEN** the review finalizes that target, includes its ID in `finalized_discards`, and persists the result in the foundation review artifact

#### Scenario: missing universe context cannot produce a foundation snapshot
- **WHEN** foundation review receives neither `_universe_path` nor `universe_path`
- **THEN** it returns an authorial-stage no-op with empty soft conflicts and a diagnostic trace, without writing the normal review artifact

### Requirement: Fantasy authorial review ranks producer candidates and hands one target to execution
The fantasy-domain authorial path SHALL materialize and rank work-target candidates, choose at most one selected target plus at most two alternates, persist an authorial review artifact, and pass the selected target and intent to `dispatch_execution`. With the producer interface enabled by default, it MUST run registered producers in registration order, stamp every emitted target with the producer's origin, skip and log a failing producer, and merge duplicate `target_id` values last-write-wins; the shipped fantasy registration order is `seed`, `fantasy_authorial`, then `user_request`. This selection and execution topology, including book/chapter/scene scope inference, is fantasy-only rather than a generic engine scheduler.

#### Scenario: producer candidates are merged before ranking
- **WHEN** the producer interface is enabled for an authorial review cycle
- **THEN** the phase runs all registered producers, merges their emitted targets by `target_id` with the later producer winning, and passes that merged list as the complete `candidate_override` to authorial ranking

#### Scenario: producer failure does not abort the cycle
- **WHEN** one registered producer raises while a later producer emits a target
- **THEN** the failure is logged, the later producer still runs, and its origin-stamped target remains available for ranking

#### Scenario: producer overrides can retain paused or discarded candidates
- **WHEN** any registered producer emits a target whose lifecycle is `paused`, `discarded`, or another non-active string
- **THEN** merge and `candidate_override` ranking do not universally filter it out, so it can survive into the ranked candidate set with a lower lifecycle score and can be selected if higher-ranked alternatives do not displace it

#### Scenario: a pending request is materialized but not guaranteed selection
- **WHEN** the user-request producer reads a valid `requests.json` entry with `status=pending`
- **THEN** it idempotently upserts an active notes target keyed from the request ID, marks the request `seen` with timestamp and target reference, and includes the target among the cycle's candidates without guaranteeing that it becomes the selected target

#### Scenario: deterministic authorial heuristics select one target
- **WHEN** authorial review receives ranked candidates
- **THEN** it prefers the first notes target for explicit `reflect` or `worldbuild`, otherwise preserves a previously selected target when present, otherwise takes the top-ranked candidate; it derives intent from the workflow hint or target intent and records no more than two remaining candidate IDs as alternates

#### Scenario: no candidate yields idle
- **WHEN** authorial ranking returns no candidates
- **THEN** review selects no target, persists the authorial review artifact, and hands off `current_task=idle` with an `idle` task queue

#### Scenario: execution routing honors request type before heuristics
- **WHEN** `dispatch_execution` receives a selected target and intent
- **THEN** it maps request types `scene_direction` and `revision` to `run_book` and `canon_change` and `branch_proposal` to `worldbuild` before considering intent keywords, then falls back to `reflect`, worldbuild/reconcile/synthesis/compare intent, notes-role worldbuild, or publishable `run_book`, with missing target and intent yielding `idle`

#### Scenario: execution handoff persists fantasy scope and review linkage
- **WHEN** execution routing determines the concrete task
- **THEN** it creates a unique execution ID, infers the fantasy book/chapter/scene-or-notes scope from the selected target, writes an execution artifact containing the selected target, intent, task, scope, prior review reference, and alternates, and returns the corresponding legacy task queue

### Requirement: Claimed-task heartbeats refresh only the current running lease

The branch-task queue SHALL refresh heartbeat and lease timestamps only for a
`running` task under the queue file lock. When both a supplied worker owner and
an existing owner are non-empty, an owner mismatch MUST return no update; a
heartbeat refresh MUST NOT reclaim or transition the task.

#### Scenario: Current owner refreshes a running task

- **WHEN** the claiming worker refreshes a running task heartbeat
- **THEN** the task remains running and receives new `heartbeat_at` and `lease_expires_at` values

#### Scenario: A stale worker cannot overwrite another owner lease

- **WHEN** a worker owner different from the stored owner attempts a heartbeat refresh
- **THEN** the helper returns no task and leaves the stored lease unchanged

#### Scenario: Heartbeat is inert for a non-running task

- **WHEN** heartbeat refresh targets a pending or terminal task
- **THEN** the helper returns no task without changing its status or lease fields

### Requirement: Branch-task cancellation distinguishes observed pending and running work

The queue-cancel action SHALL mark a task observed as pending terminally
`cancelled` through a later locked mutation. For a task observed as `running`,
it MUST require either the claiming daemon identity or the
`cancel_branch_task` capability and set an idempotent cooperative-cancel flag
under the queue lock. The legacy wrapper graph stream SHALL poll that flag at
inter-node events and finalize an observed cancellation as `cancelled`, not
`failed`. Current direct BranchTask and NodeBid execution paths do not poll the
BranchTask flag and therefore do not guarantee cooperative cancellation. The
initial status read and later cancellation mutation are separate locked
operations, so a concurrent pending-to-running claim can enter the immediate
cancel path without the running-task authorization check.

#### Scenario: Work observed pending is cancelled immediately

- **WHEN** queue cancellation targets a pending branch task
- **THEN** the task is marked `cancelled` without entering cooperative running-task cancellation

#### Scenario: Unauthorized running-task cancellation is refused

- **WHEN** an actor is neither the claiming daemon nor authorized with `cancel_branch_task`
- **THEN** queue cancellation returns `cancel_not_authorized` and does not set the cancel flag

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

The branch-task garbage collector SHALL, under the queue file lock, move only
terminal tasks whose string-valued `queued_at` parses before the configured
cutoff into the archive. It MUST retain pending, running, recent terminal,
missing/empty-date, and terminal rows whose string date raises `ValueError` in
`datetime.fromisoformat`; a truthy non-string date currently raises `TypeError`
and aborts collection. It SHALL replace the archive atomically before rewriting
the live queue. Because archived origin rows remain authoritative input to
lifetime lineage admission, an existing blank, whitespace-only, unreadable,
invalid-JSON, or non-list archive MUST fail collection without replacing the
archive or rewriting the live queue. A missing archive SHALL mean empty
history. A repeated collection after an archive-first/live-second interruption
SHALL not duplicate an identified task already present in the archive.

#### Scenario: Active and recent tasks survive collection

- **WHEN** garbage collection sees old pending or running tasks and a recent terminal task
- **THEN** all of those rows remain in the live queue

#### Scenario: Old terminal work moves to the archive

- **WHEN** a terminal task has a parseable `queued_at` before the cutoff
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

### Requirement: Blanket running-task recovery remains a callable unsafe helper

The current `recover_claimed_tasks` helper SHALL remain callable and, under the
queue file lock, reset every `running` task to `pending` while clearing claim,
worker-owner, heartbeat, and lease fields. It SHALL retain executor-worker,
executor-runtime, progress, and cancel-request fields. The helper currently has no production
call site; startup behavior remains owned by the existing canonical lease-aware
and worker-scoped recovery requirement.

#### Scenario: Direct blanket recovery clears every running claim

- **WHEN** a caller explicitly invokes `recover_claimed_tasks` on a queue with running tasks
- **THEN** every running row becomes pending with `claimed_by`, `worker_owner_id`, `heartbeat_at`, and `lease_expires_at` cleared while executor identity, progress, and `cancel_requested` are retained

### Requirement: Claimed-task execution binds enqueue authority to the physical queue universe
The epoch-1 dispatcher SHALL derive the trusted enqueue universe from the canonical physical universe directory whose queue supplied the claimed row. Before branch execution it MUST compare that value with the row's persisted `universe_id` and fail without starting a run when they differ. After a match, only the physical queue universe SHALL be passed into graph enqueue context; mutable task metadata MUST NOT redirect descendant writes.

#### Scenario: Mismatched persisted universe fails before execution
- **WHEN** a task stored in universe A's queue declares universe B in its persisted row
- **THEN** direct branch execution is refused before a run starts and no descendant is appended to either universe

#### Scenario: Matching row uses the physical universe
- **WHEN** a claimed row's persisted universe matches the physical queue directory
- **THEN** graph execution receives that physical universe as its trusted enqueue context
