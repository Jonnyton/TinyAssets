## Why

Universe-scoped Claude/Codex subprocesses can still inherit maintainer subscription or API authority through partial overlays, helper failures, API-key opt-in, and default CLI homes. This slice closes that subprocess boundary without claiming to fix the separate in-process Gemini/Groq/Grok authority path.

## What Changes

- **BREAKING**: construct a universe CLI child environment from an explicit safe-runtime allowlist instead of copying and subtracting known host credentials.
- Replace every inherited home, profile, XDG, and temporary directory with a private universe-owned provider-child root; pin Claude and Codex auth homes to universe-owned `.credentials` roots.
- Omit ambient proxy/routing authority and copy CA bundle variables only when they identify an absolute existing regular file.
- Apply only the selected provider's recognized universe-vault keys; reject arbitrary helper output rather than widening the child environment.
- Fail explicitly when universe credential resolution fails instead of returning an environment that may retain host authority.
- Preserve host provider variables only for calls with no explicit or environment-bound universe.
- Add red/green and mutation proof for direct tokens, Bedrock/Vertex/cloud activation, API-provider opt-in, default-home discovery, unknown future credentials, safe runtime basics, selected-universe overlay, resolution failure, host-local execution, and packaged-runtime parity.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `credential-vault`: require universe-scoped CLI provider subprocesses to exclude inherited maintainer authority on success and failure paths.

## Impact

- Provider subprocess environment assembly in the canonical runtime and packaged plugin mirror.
- Credential fail-closed tests and canonical `credential-vault` requirements.
- Missing or broken universe CLI credentials will now produce an explicit failure instead of potentially consuming maintainer quota.
- This process-environment boundary does not claim to block provider SDKs from every host network metadata or managed-identity service; it disables AWS EC2 metadata discovery for the child and prevents ambient cloud-route activation, while network egress isolation remains a separate boundary.
- The broader in-process API-provider authority P0 remains open and is not represented as fixed by this change.
