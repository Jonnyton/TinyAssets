## Why

PROBE-003 lost its persisted write proof when anonymous MCP writes were correctly
closed by #1441. Restore end-to-end wiki write/read coverage without weakening
the anonymous-write gate or granting the canary a reusable OAuth identity.

## What Changes

- Add an opt-in, non-OAuth bearer credential that can authorize only the
  reserved `drafts/notes/uptime-probe.md` write through `write_page`.
- Keep the feature entirely disabled when the server credential is absent or
  shorter than 32 bytes, compare bearer material in constant time, and leave
  every other authentication and authorization check unchanged.
- Make PROBE-003 perform a credentialed write-then-read roundtrip when its CI
  secret is present, while retaining the anonymous gate-plus-read probe when it
  is absent.
- Wire and document the CI secret and its rotation inventory entry.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `identity-auth-and-access-control`: Define the fail-closed, single-page
  service-token exception without creating an authenticated identity.
- `wiki-commons`: Reserve one exact draft path for service-token canary writes.
- `uptime-and-alarms`: Upgrade PROBE-003 to credentialed write/read evidence
  with a missing-secret-safe anonymous fallback.

## Impact

Affected surfaces are the MCP auth middleware and `write_page` handler, wiki
storage helper, PROBE-003 script and tests, the uptime GitHub Actions workflow,
the secret-key catalog, and the acceptance-probe catalog. No OAuth scopes,
founder identities, public tool names, or dependencies change.
