## Why

The completed full-coverage audit found five PARTIAL and two CONTRADICTED
canonical requirements. Each overclaims an absolute guarantee that current
code does not enforce: a closed work-target lifecycle enum, universal integer
money, race-atomic settlement creation, mandatory Goal attribution, fully
transactional founder creation, deterministically grounded learning, and
single-terminal append-only trigger receipts. Canonical OpenSpec is as-built
truth, so these statements must describe the shipped limitations now rather
than wait for a future hardening release.

## What Changes

- Correct two still-accurately-named requirements in place: work-target
  lifecycle and authenticated founder creation.
- Remove and replace five requirements whose headings themselves assert false
  absolutes: integer-only money, immutable/write-once settlement, mandatory
  Goal-ledger append, fail-closed grounded learning, and append-only
  single-terminal trigger receipts.
- Preserve the stronger desired guarantees in the separately owned
  `harden-canonical-absolute-guarantees` lane; this change does not normalize
  them as the target design.
- Coordinate with the active paid-market, universe-creation, and
  personification deltas without syncing any of their future behavior.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: distinguish conventional lifecycle helper
  values from the permissive generic record boundary.
- `paid-market-economy`: record payment-core integer conversion, permissive
  legacy bid scalars, v1 float settlement serialization, and sequential-only
  settlement overwrite protection.
- `shared-goals-and-convergence`: record provider-mode authorization, the
  unknown-action boundary, and best-effort contribution attribution after a
  successful Goal write.
- `universe-lifecycle-and-soul`: record best-effort index registration and the
  attempted-but-fallible directory cleanup boundary around founder creation.
- `universe-personification-and-relay`: record tolerant model extraction and
  field-specific filtering instead of claiming complete fact grounding.
- `wiki-commons`: record fail-open pending-row creation, the mutable
  per-attempt receipt row, unguarded terminal updates, and orphan queries.

## Impact

- Spec truth only under the six capabilities above.
- No runtime, API, storage, authorization, money movement, or deployment
  behavior changes.
- The hardening lane remains responsible for strict money parsing, atomic
  settlement creation, durable Goal attribution, transactional founder birth,
  deterministic learning evidence, and guarded receipt terminality.
