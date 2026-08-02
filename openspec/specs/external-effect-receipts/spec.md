# External Effect Receipts

> As-built baseline (2026-07-22, change `reclassify-forward-vision-specs`): describes landed authority, consent, and receipt behavior on `main`, including known limitations. Stronger batch and destination-reconciliation behavior remains in the active `build-forward-platform-capabilities` change.

## Purpose

The shipped per-universe authority, exact destination-consent, and optional caller-hint receipt lifecycle used by current external-write effectors.

## Requirements

### Requirement: Soul effect authority is destination-scoped and transitional
Effectors that use `resolve_soul_effect_authority` SHALL canonicalize authority as the exact stripped `<sink>:<destination>` key and return `authorized`, `denied`, or `undeclared`. A declared non-match or an unexpected soul-read failure SHALL deny the effect; no universe context or no declared grants SHALL return `undeclared`, which currently falls through to legacy capability and consent gates. This transitional fallback is an as-built limitation, not proof of strict soul-only authority.

#### Scenario: a declared non-match fails closed
- **WHEN** a universe soul declares effect grants but not the requested sink and destination
- **THEN** authority resolution returns `denied`

#### Scenario: an undeclared soul preserves the legacy gate path
- **WHEN** no grants are declared for the universe
- **THEN** authority resolution returns `undeclared` rather than authorizing or denying by itself

### Requirement: Effector consent is an exact per-universe destination grant
The consent store SHALL persist one case-sensitive `(sink, destination)` grant per universe with grantor and timestamps, reject empty grant fields, treat empty lookup fields as inactive, revoke by timestamp, and allow a later grant to reactivate the same exact row. It SHALL support no wildcard grants; effectors that use this gate must receive an active exact match before a real write.

#### Scenario: a revoked destination no longer authorizes a write
- **WHEN** an active exact-match consent is revoked
- **THEN** subsequent `is_consent_active` calls return false until that same sink and destination are granted again

#### Scenario: a near-match does not inherit consent
- **WHEN** the requested destination differs in case or text from the stored destination
- **THEN** the consent lookup returns false

### Requirement: External-write receipts atomically reserve one effect per caller hint and sink
Effectors using the receipt store SHALL reserve the per-universe `(idempotency_hint, sink)` row atomically before invoking the external write. A fresh or retry-eligible row SHALL become `pending` for one run; another run SHALL see it as in flight; successful finalization by the owning run SHALL produce a terminal `succeeded` receipt and later calls SHALL deduplicate; failure release by the owning run SHALL mark `failed` and allow retry. A pending row older than 600 seconds MAY be reclaimed, so a crash after the external side effect but before finalization can still produce one duplicate. SQLite lock errors SHALL propagate rather than be treated as receipt misses.

#### Scenario: concurrent reservation has one winner
- **WHEN** multiple runs concurrently reserve the same non-empty hint and sink
- **THEN** exactly one receives a reservable status and the others observe an in-flight or terminal row without firing the effect

#### Scenario: only the reservation owner can finalize or release
- **WHEN** a different run attempts to finalize or release a pending row
- **THEN** the transition is refused and the original reservation remains intact

#### Scenario: failure makes the hint retryable
- **WHEN** the owning run releases a failed external invocation
- **THEN** the row becomes `failed` and a later reservation can acquire it as a retry

### Requirement: Receipt guarantees are per effect and caller-supplied, not batch atomicity
The current receipt layer SHALL treat an empty idempotency hint as opting out of deduplication and SHALL key non-empty hints only with the sink. It provides no deterministic goal/schedule/item hash, destination-native reconciliation guarantee, or whole-batch all-or-nothing journal; callers and individual effectors own those concerns until the active boundary-layer change implements them.

#### Scenario: an omitted hint does not create a dedup claim
- **WHEN** an effector packet supplies an empty idempotency hint
- **THEN** receipt lookup does not report a prior success and the receipt store alone provides no exactly-once guarantee

#### Scenario: one failed item does not roll back sibling effects
- **WHEN** a caller performs multiple separately receipted effects and a later one fails
- **THEN** the receipt layer preserves earlier terminal receipts and does not provide batch rollback
