## RENAMED Requirements

- FROM: `External-write receipts atomically reserve one effect per caller hint and sink`
- TO: `External-write receipts atomically reserve one effect per derived identity and sink`
- FROM: `Receipt guarantees are per effect and caller-supplied, not batch atomicity`
- TO: `Receipt identity is system-derived and batch outcomes are explicit`

## MODIFIED Requirements

### Requirement: External-write receipts atomically reserve one effect per derived identity and sink
Effectors using the receipt store SHALL reserve the per-universe `(effect_identity, sink)` row atomically before invoking the external write, where `effect_identity` is derived by the system from durable goal, schedule-period, and item-fingerprint inputs. A fresh or retry-eligible row SHALL become `pending` for one run; another run SHALL see it as in flight; successful finalization by the owning run SHALL produce a terminal `succeeded` receipt and later calls SHALL deduplicate; failure release by the owning run SHALL mark `failed` and allow retry. A pending row SHALL NOT be reclaimed on elapsed time alone: reclamation SHALL first reconcile with the destination where the destination exposes a reconciliation interface, and where it does not, the row SHALL be held for operator remediation rather than silently reclaimed into a possible duplicate. SQLite lock errors SHALL propagate rather than be treated as receipt misses.

#### Scenario: concurrent reservation has one winner
- **WHEN** multiple runs concurrently reserve the same derived identity and sink
- **THEN** exactly one receives a reservable status and the others observe an in-flight or terminal row without firing the effect

#### Scenario: only the reservation owner can finalize or release
- **WHEN** a different run attempts to finalize or release a pending row
- **THEN** the transition is refused and the original reservation remains intact

#### Scenario: failure makes the identity retryable
- **WHEN** the owning run releases a failed external invocation
- **THEN** the row becomes `failed` and a later reservation can acquire it as a retry

#### Scenario: a stale pending row reconciles before it is reclaimed
- **WHEN** a run crashes after the external effect but before finalization and the row ages past its reclamation threshold
- **THEN** reclamation consults the destination and records the existing outcome, or holds the row for remediation when the destination cannot be reconciled, rather than reclaiming it into a second effect

### Requirement: Receipt identity is system-derived and batch outcomes are explicit
The receipt layer SHALL derive deduplication identity from durable goal, schedule-period, and item-fingerprint inputs rather than accepting a caller-supplied hint, and an effect whose identity cannot be derived SHALL fail closed instead of proceeding unreceipted. The layer SHALL journal intent before the external call, consult the journal on every replay, and persist a terminal result in every case. For a declared batch, any item that cannot be admitted, effected, or reconciled SHALL hold the batch as a whole: no further item SHALL fire, and every item and reason SHALL be visible. Whole-batch hold is explicitly not rollback — an already-terminal external effect may be irreversible at its destination, so the guarantee is that failures are reported and nothing further fires, never that completed effects were reversed.

#### Scenario: an omitted caller hint no longer opts out of deduplication
- **WHEN** an effector packet supplies no idempotency hint
- **THEN** the system derives the effect identity and receipts the effect, and an effect with no derivable identity is refused rather than fired unreceipted

#### Scenario: a failed item holds the batch without claiming reversal
- **WHEN** a later item in a batch fails after earlier items reached terminal success
- **THEN** the batch reports every item and reason, fires no further effect, and preserves the earlier terminal receipts without claiming the completed effects were rolled back
