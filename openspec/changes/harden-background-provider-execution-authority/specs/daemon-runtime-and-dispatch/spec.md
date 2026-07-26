## MODIFIED Requirements

### Requirement: Startup recovery is lease-aware and worker-scoped, never a blanket reset
At daemon startup the runtime (`fantasy_daemon.__main__` dispatcher-startup hook) SHALL recover orphaned `running` rows with lease-aware reclaim, NOT a blanket reset of every `running` row. It SHALL consider only rows whose `executor_worker_id` equals this worker's own uniquely-assigned id (a provably-dead prior incarnation, via `reclaim_predecessor_tasks`) plus rows whose lease has expired or is absent (`reclaim_expired_leases` with leaseless reclaim enabled), so a live peer holding a fresh lease is never reclaimed. Predecessor reclaim SHALL be a no-op when the worker id is blank or the shared host default, because a non-unique id could belong to a live twin. For provider-capable work, an eligible row SHALL be reset to `pending` only after `ProviderWorkAuthorityStore` proves that the prior receipt has no reservation or only reservations durably `cancelled_before_launch`; a dead-owner `reserved` reservation, unreadable evidence, or any possibly launched reservation SHALL hold the row non-claimable and fence the receipt instead of resetting it. As-built limitation: this replaces the cure half of the 2026-06-25 double-claim wedge only under the effective provider-authority V2 gate; while dark, shipped lease recovery remains unchanged.

#### Scenario: an expired-lease orphan with proven launch absence is reclaimed
- **WHEN** startup recovery runs and finds a provider-capable `running` row whose lease has expired and whose receipt has no reservation or only reservations durably `cancelled_before_launch`
- **THEN** the row is reset to `pending` with its claim and lease metadata cleared

#### Scenario: an expired lease with ambiguous provider launch is held
- **WHEN** startup recovery finds an expired provider-capable row with a dead-owner `reserved` reservation, unreadable authority evidence, or a reservation that may have launched
- **THEN** the row is not reset to `pending`
- **AND** its provider receipt is held as `fenced_indeterminate` without automatic retry

#### Scenario: a healthy peer's fresh-lease task is untouched
- **WHEN** startup recovery runs while another worker holds a `running` task with a fresh lease
- **THEN** that task is left `running` and unclaimed by recovery

#### Scenario: a non-unique worker id skips predecessor reclaim
- **WHEN** the worker id is blank or equal to the shared host default
- **THEN** `reclaim_predecessor_tasks` reclaims nothing and the lease TTL remains the only queue-level fallback

#### Scenario: dark mode preserves shipped lease recovery
- **WHEN** the effective provider-authority V2 gate is dark
- **THEN** startup recovery retains the canonical shipped lease-aware behavior without a new provider-authority precondition

## ADDED Requirements

### Requirement: Background dispatch obtains authority independently of work identity
The daemon and dispatch system SHALL obtain a fresh server-issued provider-work receipt before any claimed, scheduled, resumed, subscription-triggered, or autonomous work reaches provider, credential, outbound-proxy, auth-health, or quota authority, independently of queue identity and lease state.

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

### Requirement: Daemon recovery respects receipt launch fences
The daemon and dispatch system SHALL reconcile execution claims and provider invocation reservations before redispatching provider-capable work after worker death, restart, lease loss, or ambiguous transport outcome.

#### Scenario: Dead worker before launch can be redispatched
- **WHEN** the authority store proves the old worker is dead and the receipt has no reservation or only reservations durably `cancelled_before_launch`
- **THEN** the daemon may redispatch under a freshly claimed no-broader receipt

#### Scenario: Ambiguous launch prevents automatic redispatch
- **WHEN** the authority store cannot prove that the old attempt remained pre-launch
- **THEN** the daemon leaves the work held as `fenced_indeterminate`
- **AND** it does not automatically retry, fall back, or renew authority

### Requirement: Daemon maintenance probes use dedicated authority
The daemon SHALL run `_AUTH_PROBE_PROMPT` under V2 only as the exact authorized maintainer-maintenance operation bound to its invoking runtime or daemon and current opaque credential record, and SHALL keep it outside ordinary universe work, requester quota, and public status reads.

#### Scenario: Periodic auth health probe is authorized
- **WHEN** the daemon's server-owned maintenance schedule invokes the fixed private probe
- **THEN** it obtains a bounded maintenance receipt from the separate runtime-bound credential binding and budget before provider launch

#### Scenario: Probe authority unavailable
- **WHEN** the maintenance binding is absent, revoked, exhausted, or outside its effective gate
- **THEN** the daemon records a held or unavailable auth-health state without borrowing a universe or requester receipt
