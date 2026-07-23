## Why

The full-coverage audit found shipped credential alias, first-record selection,
and vault replacement behavior that lacks canonical ownership. Its canonical
file is actively owned by PR #1606, so this remainder is isolated from the
dependency-cleared direct-owner foldback.

## What Changes

- Specify the exact provider aliases and first-record secret-selection behavior
  already shipped by the credential vault.
- Specify the fixed temporary-file replacement boundary and its absent
  cross-process serialization guarantee.
- Keep the delta active until PR #1606 settles, then rebase it onto the final
  credential contract before canonical sync.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `credential-vault`: Add shipped secret-selection and replacement behavior
  absent from the current canonical requirement set.

## Impact

This change owns specification only. Runtime and tests remain read-only
evidence. PR #1606 retains write authority over the canonical credential spec
until its provider-authorization change settles.
