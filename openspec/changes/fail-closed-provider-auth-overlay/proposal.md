## Why

The provider/credential reconciliation proved that universe-scoped subprocesses
can retain host subscription credentials when a vault supplies only a partial
overlay or when a non-validation vault helper error is swallowed. That can run
a founder's work on host credentials across the intended universe boundary.

## What Changes

- Strip every inherited host-subscription variable before attempting any
  universe-scoped vault overlay, including when scope comes from
  `TINYASSETS_UNIVERSE`.
- Preserve only values supplied after that strip by the resolved universe's
  vault, so partial overlays cannot retain unrelated host credentials.
- Fail a universe-scoped provider environment build loudly when vault import,
  application, or resolution raises an unexpected error; keep malformed-vault
  `ValueError` behavior unchanged.
- Preserve host credentials for genuinely host-local calls with no explicit or
  environment-bound universe.
- Add mutation-capable regression tests for partial overlays, unexpected helper
  failure, malformed vaults, and the host-local counter-case.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `credential-vault`: replace the documented partial/error-path leakage
  limitations with a fail-closed universe subprocess environment contract.

## Impact

- `tinyassets/providers/base.py` environment construction and
  `tests/test_credential_fail_closed.py` security regressions.
- Canonical `credential-vault` behavior after implementation, review, sync, and
  archive.
- No vault storage shape, credential record, public MCP surface, or deployment
  configuration change.
