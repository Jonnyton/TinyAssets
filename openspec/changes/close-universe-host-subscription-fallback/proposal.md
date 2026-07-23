## Why

Universe-scoped Claude/Codex subprocesses can still inherit maintainer subscription or API authority through partial overlays, helper failures, API-key opt-in, and default CLI homes. This slice closes that subprocess boundary without claiming to fix the separate in-process Gemini/Groq/Grok authority path.

## What Changes

- **BREAKING**: strip inherited provider tokens/API variables from a universe CLI child and pin its auth homes to universe-owned `.credentials` roots before applying the universe overlay.
- Fail explicitly when universe credential resolution fails instead of returning an environment that may retain host authority.
- Preserve host provider variables only for calls with no explicit or environment-bound universe.
- Add red/green and mutation proof for no credential, partial overlay, API-provider opt-in, default-home discovery, resolution failure, and host-local execution.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `credential-vault`: require universe-scoped CLI provider subprocesses to exclude inherited maintainer authority on success and failure paths.

## Impact

- Provider subprocess environment assembly in the canonical runtime and packaged plugin mirror.
- Credential fail-closed tests and canonical `credential-vault` requirements.
- Missing or broken universe CLI credentials will now produce an explicit failure instead of potentially consuming maintainer quota.
- The broader in-process API-provider authority P0 remains open and is not represented as fixed by this change.
