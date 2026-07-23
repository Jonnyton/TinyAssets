## Why

Four groups of shipped behavior still lack complete canonical OpenSpec
ownership after the 2026-07-22 full-coverage audit. This change records those
current contracts without redesigning them or importing target behavior from
the active credential, connector, identity/universe, or release changes.

## What Changes

- Specify the current credential alias/secret-selection quirks and fixed
  temporary-file replacement boundary.
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
- Keep the change draft-only until each active dependency owner clears; do not
  sync its deltas into canonical specs while overlapping owners are in flight.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `credential-vault`: Add exact alias/first-record secret selection and the
  fixed-temp-file replacement limitation not already owned canonically.
- `live-mcp-connector-surface`: Add the shipped prompt catalog and
  tool/prompt metadata invariants.
- `identity-auth-and-access-control`: Add the exact identity-bearing status
  response variants.
- `universe-lifecycle-and-soul`: Add the public switch gates and distinguish
  reachable authenticated selection from the helper-only anonymous branch.
- `uptime-and-alarms`: Add shipped DNS, LLM-binding, release reconciliation,
  and disk-pressure behavior.

## Impact

The eventual canonical owners are the five capabilities above. Current source,
workflow, and focused tests are read-only evidence in this change. Active
dependency changes retain authority over future credential, connector,
identity/universe, and release behavior; this change may be rebased or split
before canonical sync if those owners alter the shipped boundaries.
