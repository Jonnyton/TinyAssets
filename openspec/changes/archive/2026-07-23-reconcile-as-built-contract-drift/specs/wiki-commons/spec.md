## ADDED Requirements

### Requirement: Trigger receipts use one mutable per-attempt row attempted before enqueue
Before dispatcher enqueue, each filed-page auto-trigger handler SHALL attempt
to insert one SQLite row in `pending`. If receipt creation raises, the handler
SHALL log the failure and continue enqueue without a receipt so bug filing
survives the receipt-store outage. When a receipt exists, `mark_queued`,
`mark_failed`, and `mark_skipped` SHALL update that row by
`trigger_attempt_id`. These helpers
SHALL NOT condition the update on the previous status or reject a zero affected
row count, so a later terminal helper can overwrite an earlier terminal status.
The orphan query SHALL continue to return `pending` or `queued` attempts older
than the configured cutoff.

#### Scenario: successful pending receipt precedes enqueue
- **WHEN** pending receipt creation succeeds for a filed-page auto-trigger
- **THEN** a `pending` receipt row is written before enqueue is attempted

#### Scenario: receipt-store failure does not prevent enqueue
- **WHEN** pending receipt creation raises
- **THEN** the handler logs the receipt-store failure
- **AND** continues the investigation enqueue without a receipt

#### Scenario: a later terminal update can overwrite an earlier terminal status
- **WHEN** terminal-marking helpers are invoked more than once for the same attempt
- **THEN** each helper updates by `trigger_attempt_id` without checking the prior status
- **AND** the last update can replace an earlier `queued`, `failed`, or `skipped` value

#### Scenario: stale attempts are detectable as orphans
- **WHEN** a receipt remains in `pending` or `queued` past the staleness cutoff
- **THEN** the orphan query returns it for health checks

## REMOVED Requirements

### Requirement: Trigger receipts are append-only and recorded before enqueue
**Reason**: Pending receipt creation is attempted before enqueue but can fail open; when a row exists, it remains one mutable row and terminal helpers perform unrestricted updates rather than append-only or compare-and-swap transitions.
**Migration**: Use the mutable-row requirement above; the separate hardening lane owns guarded single-terminal updates or an append-only event model.
