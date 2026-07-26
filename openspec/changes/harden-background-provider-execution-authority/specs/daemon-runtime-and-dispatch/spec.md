## MODIFIED Requirements

### Requirement: Queue-state mutations are file-locked, single-winner, and terminally idempotent
All branch-task queue mutations (`tinyassets.branch_tasks`) SHALL execute under an exclusive per-universe file lock so concurrent workers sharing the queue file cannot race. Internal BranchTask state SHALL carry a monotonic `lease_generation`; `claim_task`, lease release, and reclaim SHALL increment it whenever they change claim/lease ownership or validity. `claim_task` SHALL transition a task to `running` only if it is still `pending`, returning `None` otherwise, so any given task is claimed by at most one worker. `mark_status` SHALL raise on an invalid non-terminal transition, but SHALL treat a duplicate finalize of an already-terminal task as an idempotent no-op that keeps the first result and never crashes the daemon (first-writer-wins).

#### Scenario: only one worker claims a pending task
- **WHEN** two workers call `claim_task` for the same pending task
- **THEN** exactly one receives the claimed task transitioned to `running` with an incremented lease generation
- **AND** the other receives `None`

#### Scenario: duplicate finalize on a terminal task is a no-op
- **WHEN** `mark_status` is called on a task that is already in a terminal state
- **THEN** the call returns without raising and without changing the existing terminal result

#### Scenario: an invalid non-terminal transition raises
- **WHEN** `mark_status` requests a transition that is not permitted from the current non-terminal state
- **THEN** it raises rather than corrupting the row

### Requirement: Startup recovery is lease-aware and worker-scoped, never a blanket reset
At daemon startup the runtime (`fantasy_daemon.__main__` dispatcher-startup hook) SHALL recover orphaned `running` rows with lease-aware reclaim, NOT a blanket reset of every `running` row. Startup SHALL consider rows whose `executor_worker_id` equals this worker's own uniquely-assigned id (a provably-dead prior incarnation, via `reclaim_predecessor_tasks`) plus rows whose lease has expired or is absent (`reclaim_expired_leases` with leaseless reclaim enabled). `reclaim_predecessor_tasks` SHALL no-op on a blank worker id; every caller SHALL pass only a uniquely-assigned id and SHALL skip the shared host default. Before every dispatcher claim/pick, the hot sweep SHALL call only `reclaim_expired_leases` with leaseless reclaim disabled and SHALL NOT perform predecessor reclaim. Under the effective provider-authority V2 gate, every startup reclaim path and every hot-pick expired-lease reset SHALL apply the same provider-authority guard: lease expiry alone SHALL NOT prove owner death; `ProviderWorkAuthorityStore` SHALL either prove the owner dead or atomically invalidate and advance the old execution-claim generation. Reservation creation SHALL validate that exact active generation. The store SHALL then prove that the prior receipt has no reservation or every reservation is durably conclusive as `cancelled_before_launch`, `succeeded`, or `failed`; a dead/invalidated-owner `reserved` reservation SHALL first be atomically cancelled before launch, while an unclosed `launch_started`, `indeterminate`, or unreadable reservation SHALL hold the row non-claimable and fence the receipt. The authority proof SHALL bind the exact task, advanced authority/claim generation, claim owner, and monotonic lease generation, and the file-locked queue reset SHALL compare-and-swap that unchanged tuple; timestamps are observability only, and concurrent heartbeat, renewal, or authority change forces fresh reconciliation. Non-provider-capable rows retain the respective shipped startup or hot-pick lease rule under V2, and dark provider behavior retains the same shipped rules only for work with no authority-ledger record; any existing authority-ledger record remains subject to reconciliation and fencing regardless of gate state. As-built limitation: this is the cure half of the 2026-06-25 double-claim wedge, where the retired blanket `recover_claimed_tasks` reset stole live peers' tasks on every restart.

#### Scenario: an expired-lease orphan with conclusive authority is reclaimed
- **WHEN** startup recovery finds an expired provider-capable row, proves its owner dead or atomically invalidates the old claim generation, and finds no reservation or only reservations durably `cancelled_before_launch`, `succeeded`, or `failed`
- **THEN** the row is reset to `pending` with its claim and lease metadata cleared
- **AND** succeeded/failed budgets remain consumed while cancelled-before-launch authority is released
- **AND** reset uses a compare-and-swap on the exact unchanged task, claim owner, lease generation, and authority proof

#### Scenario: dispatcher pick sweep applies the same authority guard
- **WHEN** `reclaim_expired_leases` runs immediately before a dispatcher claim/pick
- **THEN** it applies the same owner invalidation, reservation reconciliation, monotonic lease-generation, and queue compare-and-swap requirements as startup recovery
- **AND** it does not reclaim leaseless rows or invoke predecessor reclaim

#### Scenario: a dead-owner reserved attempt is cancelled before reclaim
- **WHEN** startup recovery proves the owner dead or invalidates its claim generation and finds a durable `reserved` reservation
- **THEN** it atomically changes the reservation to `cancelled_before_launch`, releases its full authority, obtains a fresh reconciliation proof, and only then attempts the queue compare-and-swap

#### Scenario: a fresh-lease predecessor orphan receives the authority guard
- **WHEN** startup predecessor reclaim finds a provider-capable row owned by a provably-dead prior worker incarnation even though its lease has not expired
- **THEN** recovery applies the same owner invalidation, reservation reconciliation, monotonic lease-generation, and queue compare-and-swap requirements before resetting the row

#### Scenario: an expired lease with ambiguous provider launch is held
- **WHEN** startup recovery finds an expired provider-capable row with an unclosed `launch_started`, `indeterminate`, or unreadable reservation
- **THEN** the row is not reset to `pending`
- **AND** its provider receipt is held as `fenced_indeterminate` without automatic retry

#### Scenario: a healthy peer's fresh-lease task is untouched
- **WHEN** startup recovery runs while another worker holds a `running` task with a fresh lease
- **THEN** that task is left `running` and unclaimed by recovery

#### Scenario: a non-unique worker id skips predecessor reclaim
- **WHEN** the worker id is blank or equal to the shared host default
- **THEN** the helper no-ops on blank and every caller skips the shared host default, leaving the lease TTL as the only fallback

#### Scenario: lease renewal defeats stale recovery proof
- **WHEN** a worker heartbeat or lease renewal changes the queue row after authority proof but before reset
- **THEN** the compare-and-swap fails without resetting the live row
- **AND** recovery must obtain fresh authority and queue evidence before retrying

#### Scenario: expired lease does not leave a live claim valid
- **WHEN** lease expiry makes a provider-capable row eligible but worker death cannot be proved
- **THEN** recovery atomically advances the old execution-claim generation before issuing its reconciliation proof
- **AND** every later reservation attempt from the old worker fails generation validation

#### Scenario: dark mode preserves shipped lease recovery
- **WHEN** the effective provider-authority V2 gate is dark and an eligible row has no authority-ledger record
- **THEN** startup recovery retains the canonical shipped lease-aware behavior without a new provider-authority precondition
- **AND** any existing authority-ledger record remains subject to reconciliation and fencing regardless of gate state

#### Scenario: non-provider work retains lease recovery under V2
- **WHEN** startup recovery under V2 finds an eligible non-provider-capable row with an expired lease
- **THEN** the row is reset to `pending` with its claim and lease metadata cleared

### Requirement: The supervisor keeps one daemon subprocess alive with backoff, producer restart, auth quarantine, and graceful drain
The cloud-worker supervisor (`tinyassets.cloud_worker` run-supervisor loop) SHALL spawn the daemon subprocess, wait for its exit, and respawn it with exponential backoff — a shorter idle backoff after clean (no-work) exits and a longer crash backoff after non-zero exits — until a SIGTERM/SIGINT stop is requested. While a subprocess runs it SHALL poll for newly-queued branch tasks and restart the child so pending work is picked up, SHALL write a phase-tagged heartbeat file, and SHALL quarantine itself (skip the spawn, beat, back off, re-check) when the writer provider is unauthenticated so a dead-auth worker never claims-and-fails tasks. Under the effective provider-authority V2 gate it SHALL also quarantine before spawn or claim when maintenance authority is unavailable and records `auth_unknown`; while dark, the worker SHALL retain the shipped rule that quarantines only on `not_logged_in`. On a stop signal, once the child's death is CONFIRMED, it SHALL release that worker's own orphaned leases so a live peer can pick the work up immediately rather than waiting out the lease TTL. Under the effective provider-authority V2 gate, every provider-capable orphan SHALL first pass the same dead-or-invalidated-owner proof, reservation reconciliation, fence, and queue compare-and-swap requirements as startup recovery; an ambiguous launch remains fenced and non-claimable rather than being released. Non-provider-capable rows retain the shipped graceful-drain release under V2, and dark provider behavior retains that shipped rule for rows with no authority-ledger record; any existing authority-ledger record remains subject to reconciliation and fencing regardless of gate state.

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

#### Scenario: unavailable V2 maintenance authority quarantines provider work
- **WHEN** the effective worker/provider V2 gate is active and maintenance authority cannot produce fresh conclusive health evidence
- **THEN** the supervisor records `auth_unknown`, skips the spawn, and backs off without claiming provider-capable work
- **AND** ordinary router unknown or inconclusive health remains eligible and is not reinterpreted as `not_logged_in`

#### Scenario: confirmed child death reconciles before releasing its leases
- **WHEN** a stop signal terminates the child and its exit is confirmed
- **THEN** the supervisor reconciles provider authority and releases only conclusively safe orphaned leases during graceful drain
- **AND** an unclosed `launch_started`, `indeterminate`, or unreadable reservation remains fenced and non-claimable

### Requirement: Claimed-task heartbeats refresh only the current running lease

The branch-task queue SHALL refresh heartbeat and lease timestamps only for a
`running` task under the queue file lock and SHALL increment the task's
monotonic `lease_generation` in that same locked mutation. When both a
supplied worker owner and an existing owner are non-empty, an owner mismatch
MUST return no update; a heartbeat refresh MUST NOT reclaim or transition the
task.

#### Scenario: Current owner refreshes a running task

- **WHEN** the claiming worker refreshes a running task heartbeat
- **THEN** the task remains running, receives new `heartbeat_at` and `lease_expires_at` values, and increments `lease_generation`

#### Scenario: A stale worker cannot overwrite another owner lease

- **WHEN** a worker owner different from the stored owner attempts a heartbeat refresh
- **THEN** the helper returns no task and leaves the stored lease and generation unchanged

#### Scenario: Heartbeat is inert for a non-running task

- **WHEN** heartbeat refresh targets a pending or terminal task
- **THEN** the helper returns no task without changing its status, lease fields, or generation

## ADDED Requirements

### Requirement: Background dispatch obtains authority independently of work identity
The daemon and dispatch system SHALL obtain a fresh server-issued provider-work receipt before any claimed, scheduled, resumed, subscription-triggered, or autonomous work reaches provider, credential, outbound-proxy, auth-health, or quota authority, independently of queue identity and lease state. This requirement is subject to the effective provider-authority V2 gate; while dark it SHALL preserve shipped dispatch behavior without a new receipt precondition.

#### Scenario: Claimed branch task needs separate provider authority
- **WHEN** a worker validly claims or renews a branch-task lease whose execution can reach a provider
- **THEN** the claim or lease grants no provider authority
- **AND** the worker must separately claim a receipt derived from the current work binding

#### Scenario: Schedule trigger mints per-attempt authority
- **WHEN** an authorized schedule or subscription creates a provider-capable execution attempt
- **THEN** the daemon revalidates its binding and mints a fresh bounded receipt for that trigger

#### Scenario: Run or daemon cycle resumes after request context ended
- **WHEN** a run, resume, selector, cloud worker, or autonomous daemon cycle reaches provider-capable work without a current live request
- **THEN** it uses background provider authority tied to the exact work attempt
- **AND** it does not inherit, snapshot, or synthesize request authority

#### Scenario: Missing or stale authority holds work
- **WHEN** a background dispatcher cannot obtain or claim a current receipt
- **THEN** it holds or fails the provider-capable step explicitly before any provider authority sink
- **AND** it preserves enough non-secret state for safe retry after authorization is restored

#### Scenario: Dark mode preserves background dispatch
- **WHEN** the effective provider-authority V2 gate is dark and work has no authority-ledger record
- **THEN** claimed, scheduled, resumed, subscription-triggered, and autonomous dispatch retain shipped behavior without a new receipt hold
- **AND** existing authority-ledger records cannot be discarded or bypassed

### Requirement: Daemon recovery respects receipt launch fences
The daemon and dispatch system SHALL reconcile execution claims and provider invocation reservations before redispatching provider-capable work after worker death, restart, lease loss, graceful-drain release of the worker's own orphaned leases, or ambiguous transport outcome. Graceful drain SHALL apply the same owner invalidation, reservation reconciliation, fence, monotonic lease-generation, and queue compare-and-swap guard before resetting any provider-capable row. This requirement is subject to the effective provider-authority V2 gate; while dark it SHALL preserve shipped recovery behavior for work with no authority-ledger record.

#### Scenario: Dead worker before launch can be redispatched
- **WHEN** the authority store proves the old worker dead or atomically invalidates its claim generation, and the receipt has no reservation or only reservations durably `cancelled_before_launch`, `succeeded`, or `failed`
- **THEN** the daemon may redispatch under a freshly claimed no-broader receipt

#### Scenario: Dead worker reserved before arming is cancelled
- **WHEN** the old worker is provably dead or its claim generation was atomically invalidated, with a durable `reserved` reservation
- **THEN** recovery atomically cancels it before launch, releases its full authority, and may then redispatch under a no-broader receipt

#### Scenario: Graceful drain reconciles before releasing an orphaned lease
- **WHEN** the supervisor confirms child death and releases its own orphaned provider-capable task lease
- **THEN** it applies the same authority reconciliation and queue compare-and-swap as startup recovery before resetting the row
- **AND** an unclosed armed or indeterminate reservation remains fenced and non-claimable

#### Scenario: Ambiguous launch prevents automatic redispatch
- **WHEN** the authority store cannot prove that the old attempt remained pre-launch
- **THEN** the daemon leaves the work held as `fenced_indeterminate`
- **AND** it does not automatically retry, fall back, or renew authority

#### Scenario: Dark mode preserves daemon recovery
- **WHEN** the effective provider-authority V2 gate is dark and work has no authority-ledger record
- **THEN** daemon recovery retains shipped redispatch behavior without a new authority-fence precondition
- **AND** existing authority-ledger records remain subject to reconciliation and fencing

### Requirement: Daemon maintenance probes use dedicated authority
The daemon SHALL run `_AUTH_PROBE_PROMPT` under V2 only as the exact authorized maintainer-maintenance operation bound to its invoking runtime or daemon and current opaque credential record, and SHALL keep it outside ordinary universe work, requester quota, and public status reads. This requirement is subject to the effective provider-authority V2 gate; while dark it SHALL preserve the shipped probe path.

#### Scenario: Periodic auth health probe is authorized
- **WHEN** the daemon's server-owned maintenance schedule invokes the fixed private probe
- **THEN** it obtains a bounded maintenance receipt from the separate runtime-bound credential binding and budget before provider launch

#### Scenario: Probe authority unavailable
- **WHEN** effective V2 maintenance authority becomes revoked, exhausted, or otherwise unavailable after cutover
- **THEN** the daemon records `auth_unknown` and the supervisor quarantines without spawning or claiming provider-capable work until fresh conclusive health evidence exists
- **AND** it does not borrow a universe or requester receipt

#### Scenario: Maintenance readiness failure keeps V2 dark
- **WHEN** a maintenance canary lacks its binding or cannot prove authenticated spawn and unauthenticated/unknown quarantine
- **THEN** provider-authority V2 does not become effective for that worker/provider
- **AND** the still-dark worker retains the shipped probe path

#### Scenario: Dark mode preserves the shipped probe
- **WHEN** the effective provider-authority V2 gate is dark
- **THEN** the daemon retains the shipped `_AUTH_PROBE_PROMPT` behavior without a maintenance-receipt precondition
