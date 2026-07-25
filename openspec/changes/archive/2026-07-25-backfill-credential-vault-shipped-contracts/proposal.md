## Why

The full-coverage audit found shipped credential alias, first-record selection,
and vault replacement behavior that lacks canonical ownership. This remainder
was initially held behind draft PR #1606, but that draft proposes unlanded
provider-routing behavior and does not own the already-shipped contract on
`main`.

## What Changes

- Specify the exact provider aliases and first-record secret-selection behavior
  already shipped by the credential vault.
- Specify the fixed temporary-file replacement boundary and its absent
  cross-process serialization guarantee.
- Verify the delta directly against the current `origin/main` runtime and
  canonical spec before sync, independent of unlanded draft behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `credential-vault`: Add shipped secret-selection and replacement behavior
  absent from the current canonical requirement set.

## Impact

This change owns specification only. Runtime and tests remain read-only
evidence. Draft PR #1549 also edits the canonical credential spec, but only its
separate provider-auth overlay requirement; this backfill appends disjoint
as-built requirements.
