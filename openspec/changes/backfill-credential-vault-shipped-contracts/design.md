## Context

The combined direct-owner backfill was independently source-reviewed, but its
credential owner overlaps the actively claimed provider-authorization lane.
The other shipped backfills have no requirement-level collision and can fold
back independently.

## Decision

Retain the two reviewed credential requirements in a dedicated active change.
After PR #1606 settles, re-read the resulting canonical requirement, remove any
duplicate clauses, rerun the focused credential evidence, and only then sync
and archive this remainder.

This change does not repair the missing cross-process lock or alter credential
selection. Canonical as-built truth must preserve both limitations until the
runtime changes.

## Risks

- PR #1606 may change the credential environment boundary. Rebase against its
  landed source and spec rather than preserving stale wording.
- A later credential fix may add serialization. If so, replace the limitation
  with the newly verified behavior rather than syncing historical truth.

## Migration Plan

1. Wait for PR #1606 or its successor to settle.
2. Rebase and rerun focused credential tests and source review.
3. Sync, strict-validate, archive, and land through review.
