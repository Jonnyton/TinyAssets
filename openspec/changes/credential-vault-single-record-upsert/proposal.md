## Why

The credential-vault write boundary now preserves unrelated credentials during
single-record deposits, so its arity-dependent behavior must be recorded as
as-built requirement truth. Review also found collision cases where an upsert
could retain a shadowing token, erase subscription sibling fields, or leave
same-slot duplicates.

## What Changes

- Mark the reviewed single-record upsert behavior as built.
- Define logical-slot matching from the fields consumed by current resolvers.
- Make overlapping VCS purpose selectors rotate one slot instead of appending a
  shadowed token.
- Preserve sibling fields when merging `llm_subscription` records.
- Collapse every matching duplicate during one-record upserts.
- Retain exact bulk replacement, empty clearing, fail-loud malformed-vault
  handling, and the existing cross-process race disclaimer.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `credential-vault`: Specify the as-built single-record upsert contract and
  distinguish it from bulk replacement and empty clearing.

## Impact

The canonical and packaged runtime copies of `tinyassets/credential_vault.py`,
credential-vault regression tests, and the existing `credential-vault`
capability spec are affected. No API signature or dependency changes.
