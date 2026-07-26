## Why

The Layer-1 wiki canary is false-red in production: anonymous `write_page`
correctly receives the canonical pre-dispatch HTTP 401 OAuth challenge, while
the canary still expects the retired tool-JSON rejection envelope. This hides a
healthy authentication boundary behind a P0 incident signal.

## What Changes

- Treat only an HTTP 401 response with a non-empty `WWW-Authenticate` challenge
  to the anonymous `write_page` call as successful write-gate evidence.
- Keep all dispatched JSON tool results, including the former
  `status=rejected, auth_required=true` envelope, red because a challenged
  write must be refused pre-dispatch.
- Preserve the anonymous persisted `read_page` draft proof after a valid
  challenge and surface the wiki-canary diagnostic through the uptime workflow.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `uptime-and-alarms`: Define the wiki sub-probe's valid OAuth-challenge
  evidence and its diagnostic propagation. The connector protocol boundary
  remains owned by `live-mcp-connector-surface`.

## Impact

Updates `scripts/wiki_canary.py`, its focused tests, and the uptime-canary
workflow/test. The public connector's HTTP 401 + `WWW-Authenticate`
requirement is unchanged and is cross-referenced rather than duplicated.
