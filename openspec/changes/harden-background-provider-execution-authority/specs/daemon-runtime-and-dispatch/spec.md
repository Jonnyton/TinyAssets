## MODIFIED Requirements

### Requirement: Startup recovery is lease-aware and worker-scoped, never a blanket reset
At daemon startup the runtime (`fantasy_daemon.__main__` dispatcher-startup hook) SHALL recover orphaned `running` rows with lease-aware reclaim, NOT a blanket reset of every `running` row. It SHALL consider only rows whose `executor_worker_id` equals this worker's own uniquely-assigned id (a provably-dead prior incarnation, via `reclaim_predecessor_tasks`) plus rows whose lease has expired or is absent (`reclaim_expired_leases` with leaseless reclaim enabled), so a live peer holding a fresh lease is never reclaimed merely because another worker restarted. The dispatcher SHALL skip predecessor reclaim when the worker id is blank or the shared host default, because a non-unique id could belong to a live twin. Under the effective provider-authority V2 gate, lease expiry alone SHALL NOT prove owner death: before a provider-capable eligible row can reset, `ProviderWorkAuthorityStore` SHALL either prove the owner dead or atomically invalidate and advance the old execution-claim generation. Reservation creation SHALL validate that exact active generation, so an invalidated live-but-wedged worker can reserve nothing. The store SHALL then prove that the prior receipt has no reservation or every reservation is durably conclusive as `cancelled_before_launch`, `succeeded`, or `failed`; a dead/invalidated-owner `reserved` reservation SHALL first be atomically cancelled before launch, while an unclosed `launch_started`, `indeterminate`, or unreadable reservation SHALL hold the row non-claimable and fence the receipt. The authority proof SHALL bind the exact task, advanced authority/claim generation, claim owner, and lease generation, and the file-locked queue reset SHALL compare-and-swap that unchanged tuple; a concurrent heartbeat, renewal, or authority change makes reset fail and forces fresh reconciliation. Non-provider-capable rows retain the lease-aware reclaim rule under V2, and dark provider behavior retains the same shipped rule. As-built limitation: this is the cure half of the 2026-06-25 double-claim wedge, where the retired blanket `recover_claimed_tasks` reset stole live peers' tasks on every restart.

#### Scenario: an expired-lease orphan with conclusive authority is reclaimed
- **WHEN** startup recovery finds an expired provider-capable row, proves its owner dead or atomically invalidates the old claim generation, and finds no reservation or only reservations durably `cancelled_before_launch`, `succeeded`, or `failed`
- **THEN** the row is reset to `pending` with its claim and lease metadata cleared
- **AND** succeeded/failed budgets remain consumed while cancelled-before-launch authority is released
- **AND** reset uses a compare-and-swap on the exact unchanged task, claim owner, lease generation, and authority proof

#### Scenario: a dead-owner reserved attempt is cancelled before reclaim
- **WHEN** startup recovery proves the owner dead or invalidates its claim generation and finds a durable `reserved` reservation
- **THEN** it atomically changes the reservation to `cancelled_before_launch`, releases its full authority, obtains a fresh reconciliation proof, and only then attempts the queue compare-and-swap

#### Scenario: an expired lease with ambiguous provider launch is held
- **WHEN** startup recovery finds an expired provider-capable row with an unclosed `launch_started`, `indeterminate`, or unreadable reservation
- **THEN** the row is not reset to `pending`
- **AND** its provider receipt is held as `fenced_indeterminate` without automatic retry

#### Scenario: a healthy peer's fresh-lease task is untouched
- **WHEN** startup recovery runs while another worker holds a `running` task with a fresh lease
- **THEN** that task is left `running` and unclaimed by recovery

#### Scenario: a non-unique worker id skips predecessor reclaim
- **WHEN** the worker id is blank or equal to the shared host default
- **THEN** the dispatcher skips predecessor reclaim and the lease TTL remains the only fallback

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
The daemon and dispatch system SHALL reconcile execution claims and provider invocation reservations before redispatching provider-capable work after worker death, restart, lease loss, or ambiguous transport outcome. This requirement is subject to the effective provider-authority V2 gate; while dark it SHALL preserve shipped recovery behavior.

#### Scenario: Dead worker before launch can be redispatched
- **WHEN** the authority store proves the old worker is dead and the receipt has no reservation or only reservations durably `cancelled_before_launch`, `succeeded`, or `failed`
- **THEN** the daemon may redispatch under a freshly claimed no-broader receipt

#### Scenario: Dead worker reserved before arming is cancelled
- **WHEN** the old worker is provably dead with a durable `reserved` reservation
- **THEN** recovery atomically cancels it before launch, releases its full authority, and may then redispatch under a no-broader receipt

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
