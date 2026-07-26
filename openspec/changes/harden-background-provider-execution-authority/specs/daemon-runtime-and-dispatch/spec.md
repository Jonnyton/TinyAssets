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
- **WHEN** the authority store proves the old worker is dead and every reservation remained before `launch_started`
- **THEN** the daemon may redispatch under a freshly claimed no-broader receipt

#### Scenario: Ambiguous launch prevents automatic redispatch
- **WHEN** the authority store cannot prove that the old attempt remained pre-launch
- **THEN** the daemon leaves the work held as `fenced_indeterminate`
- **AND** it does not automatically retry, fall back, or renew authority

### Requirement: Daemon maintenance probes use dedicated authority
The daemon SHALL run `_AUTH_PROBE_PROMPT` only as the exact authorized maintainer-maintenance operation and SHALL keep it outside ordinary universe work, requester quota, and public status reads.

#### Scenario: Periodic auth health probe is authorized
- **WHEN** the daemon's server-owned maintenance schedule invokes the fixed private probe
- **THEN** it obtains a bounded maintenance receipt from the separate maintenance binding and budget before provider launch

#### Scenario: Probe authority unavailable
- **WHEN** the maintenance binding is absent, revoked, exhausted, or outside its effective gate
- **THEN** the daemon records a held or unavailable auth-health state without borrowing a universe or requester receipt
