## Why

The running drain accepted two `BLOCKED` results whose blocker truth existed
only in per-run result files, so current `main` continued to advertise those
targets as claimable. Later workers then spent two additional delivery attempts
repairing and folding back coordination instead of advancing product work.

## What Changes

- Treat a worker's `BLOCKED <target>` marker as a proposed outcome, not durable
  truth.
- Refresh exact current `origin/main` after the marker and accept the blocked
  result only when the canonical claim checker classifies that same target as
  blocked.
- Reject a non-durable blocked result, retain its prepared admission, and send a
  fresh worker back to persist a sanitized STATUS dependency/blocker through
  the normal reviewed PR path.
- Require worker instructions to make blocker truth durable before returning
  `BLOCKED`.
- When current-main pressure still contains candidates but recent-blocker
  filtering leaves no concrete hint, wait the bounded idle interval instead of
  spending a full write-capable worker rediscovering the same blockers.
- Release run-local suppression as soon as current main no longer classifies a
  previously accepted target as blocked, and expose the new transient states
  honestly through watchdog health.
- Persist a bounded set of verified merged-PR receipts, reconstruct it for a
  legacy run on resume, and reject an exact PR replay instead of counting fake
  delivery progress.
- Keep `NO_CANDIDATE`, merge verification, failure budgets, current-main
  refresh, admission, review, and GitHub policy unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: A drain blocker becomes suppressible only
  after its target is durably classified as blocked on current main; transient
  per-run memory cannot substitute for shared coordination truth.

## Impact

The change is limited to the OpenSpec drain supervisor/watchdog, their focused
tests, and the development-coordination runtime delta. It changes no product
runtime, MCP surface, cloud activation, provider authority, or repository
policy. The running tray keeps its current controller until this change is
merged, reviewed, and deployed after its active attempt reaches terminal.
