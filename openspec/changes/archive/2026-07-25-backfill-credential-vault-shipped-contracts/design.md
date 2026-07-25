## Context

The combined direct-owner backfill was independently source-reviewed. Its
credential remainder was split out because draft PR #1606 was assumed to own
the canonical file, but that assumption conflated an unlanded future change
with the already-shipped behavior this backfill specifies.

## Decision

Retain the two reviewed credential requirements in a dedicated active change.
Verify them against the current `origin/main` runtime and canonical requirement
set, remove any duplicate or inaccurate clauses, rerun focused credential
evidence, and sync without waiting for draft PR #1606.

This change does not repair the missing cross-process lock or alter credential
selection. Canonical as-built truth must preserve both limitations until the
runtime changes.

## Risks

- A future provider-routing change, including draft PR #1606, may supersede
  part of this as-built truth when it lands. That future change must modify the
  canonical requirement then; its draft state is not a backfill dependency.
- Draft PR #1549 touches the same canonical file but a separate provider-auth
  overlay requirement. Append these requirements without rewriting that area.
- A later credential fix may add serialization. If so, replace the limitation
  with the newly verified behavior rather than syncing historical truth.

## Migration Plan

1. Verify the branch is based on current `origin/main`.
2. Rerun focused credential tests and source review against current source.
3. Sync and strict-validate; archive and land only after cross-family review.
