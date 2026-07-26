## Why

Three dependency-cleared groups of shipped behavior still lack complete
canonical OpenSpec ownership after the 2026-07-22 full-coverage audit. This
change records those current contracts without redesigning them or importing
target behavior from active connector, identity/universe, or release changes.
The overlapping credential-vault remainder is isolated in
`backfill-credential-vault-shipped-contracts`.

## What Changes

- Specify the shipped prompt catalog and metadata plus the exact
  early/config-error/full status response variants.
- Specify public universe-switch authorization, authenticated request scope,
  and the directly invoked helper's otherwise-unreachable anonymous host
  scope.
- Specify the shipped DNS and LLM-binding canaries, release reconciler, and
  disk-pressure alert/rotation/auto-prune controller.
- Preserve every observed limitation explicitly, including absent
  cross-process credential-file locking and omitted `session_boundary` fields
  in early status responses.
- Sync these requirement-level independent deltas while keeping future target
  changes responsible for modifying the resulting as-built owners.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `live-mcp-connector-surface`: Add the shipped prompt catalog and
  tool/prompt metadata invariants.
- `identity-auth-and-access-control`: Add the exact identity-bearing status
  response variants.
- `universe-lifecycle-and-soul`: Add the public switch gates and distinguish
  reachable authenticated selection from the helper-only anonymous branch.
- `uptime-and-alarms`: Add shipped DNS, LLM-binding, release reconciliation,
  and disk-pressure behavior.

## Impact

The eventual canonical owners are the four capabilities above. Current source,
workflow, and focused tests are read-only evidence in this change. Active
target changes retain authority over future connector, identity/universe, and
release behavior and must modify these as-built owners when their runtime
changes land.
