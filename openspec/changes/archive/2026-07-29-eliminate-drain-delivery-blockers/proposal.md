## Why

The first overnight OpenSpec drain recovered correctly across an abrupt host
shutdown and produced three verified work packages, but it landed zero pull
requests. Two operational defects caused that result: Windows exposed a
console whose closure terminated the tray host, and Codex workers in linked
worktrees could not write the external Git metadata needed to commit and
publish their completed work.

## What Changes

- Launch the sign-in tray host and every provider subprocess without a visible
  Windows console.
- Grant a write-capable Codex worker the linked worktree's resolved Git common
  directory in addition to its worktree.
- Require workers to use the repository's shell Git/GitHub publication route.
- Distinguish a durable task blocker from a retryable delivery-infrastructure
  failure so verified work is resumed immediately instead of parked as
  `BLOCKED`.
- Preserve the existing one-worker-at-a-time, finite-budget, abrupt-shutdown
  recovery model.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: make drain startup consoleless and make
  verified local work retryable through commit/push/PR delivery.

## Impact

The change affects the peer subprocess launcher, drain worker brief and result
contract, Windows autostart task, focused regression tests, and the operator
runbook. It changes no product API or end-user data shape.
