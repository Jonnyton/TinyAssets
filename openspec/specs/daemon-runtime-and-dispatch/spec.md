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
The durable work-target registry (`tinyassets.work_targets`) SHALL model each target with an explicit lifecycle state drawn from a fixed set — `active`, `paused`, `dormant`, `complete`, `superseded`, `marked_for_discard`, `discarded` — persisted in inspectable JSON in the universe directory, so the daemon schedules over durable targets rather than a transient task queue. Discard SHALL be a reversible two-step transition: `mark_target_for_discard` moves a target to `marked_for_discard` and records the review cycle, and `discard_target` moves it to `discarded` only after the configured review delay has elapsed, rather than an immediate deletion.

#### Scenario: a target carries an explicit lifecycle state
- **WHEN** a work target is created and later paused, completed, or superseded
- **THEN** its lifecycle field reflects the corresponding state from the fixed lifecycle set and is persisted to JSON

#### Scenario: discard is a delayed two-step, not immediate deletion
- **WHEN** a target is marked for discard and `discard_target` is called before the review delay has elapsed
- **THEN** the target stays `marked_for_discard` and is only moved to `discarded` once the review delay has passed
