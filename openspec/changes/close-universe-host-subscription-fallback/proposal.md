## Why

Universe-scoped provider subprocesses can still inherit the maintainer's Claude or Codex subscription when a vault overlay is partial or credential resolution fails unexpectedly. That violates TinyAssets' execution-authority boundary: users must bring or accept their own compute and model access, and maintainer quota must never become a fallback.

## What Changes

- **BREAKING**: strip all inherited host-subscription authority before applying a universe's credential overlay.
- Fail explicitly when universe credential resolution fails instead of returning an environment that may retain host authority.
- Preserve host subscription variables only for calls that are genuinely host-local and resolve no universe.
- Add red/green and mutation proof for no credential, partial overlay, resolution failure, and host-local execution.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `credential-vault`: require universe-scoped provider subprocesses to exclude inherited maintainer subscription authority on every success and failure path.

## Impact

- Provider subprocess environment assembly in the canonical runtime and packaged plugin mirror.
- Credential fail-closed tests and canonical `credential-vault` requirements.
- Missing or broken universe credentials will now produce an explicit failure instead of potentially consuming maintainer quota.
