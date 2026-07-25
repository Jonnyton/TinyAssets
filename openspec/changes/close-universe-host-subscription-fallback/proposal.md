## Why

Universe-scoped Claude/Codex subprocesses can still inherit maintainer subscription or API authority through partial overlays, helper failures, API-key opt-in, and default CLI homes. This slice closes that subprocess boundary without claiming to fix the separate in-process Gemini/Groq/Grok authority path.

## What Changes

- **BREAKING**: construct a universe CLI child environment from an explicit safe-runtime allowlist instead of copying and subtracting known host credentials.
- Replace every inherited home, profile, XDG, and temporary directory with a private universe-owned provider-child root; pin empty Claude and Codex auth homes to a distinct runtime-only `auth-empty` root.
- Omit ambient proxy/routing authority and copy CA bundle variables only when they identify an absolute existing regular file.
- Support only canonical `claude-code` and `codex` universe subprocesses; apply only the selected provider's recognized universe-vault keys and reject arbitrary helper output rather than widening the child environment.
- Resolve and physically contain runtime and credential paths beneath the canonical universe root before any child-directory creation or credential-helper side effect; revalidate path overlays after the helper returns.
- Reject a symlinked, junction/reparse-linked, hardlinked/multi-link, non-file, or physically outside `.credential-vault.json` before any public vault resolver reads it.
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
- A universe with no CLI credential receives isolated empty runtime auth homes and fails authentication at provider-call time without consuming maintainer quota. Broken, unrecognized, malformed, or physically out-of-universe credential resolution fails explicitly before provider launch.
- **BREAKING**: existing universe vault records whose Claude or Codex auth path physically resolves outside that universe are refused, including paths that escape through a symlink, junction, or reparse component. Operators must move that auth material beneath the universe before retrying.
- **BREAKING**: a linked, multi-link, non-file, or physically outside `.credential-vault.json` is refused. Operators must replace it with a private single-link regular file directly beneath the universe; linked-source compatibility would reopen cross-universe credential authority.
- Host tooling that inherits a non-empty `TINYASSETS_UNIVERSE` is intentionally treated as universe-scoped; unset the binding for ordinary host-local provider execution.
- This process-environment boundary does not claim to block provider SDKs from every host network metadata or managed-identity service; it disables AWS EC2 metadata discovery for the child and prevents ambient cloud-route activation, while network egress isolation remains a separate boundary.
- The broader in-process API-provider authority P0 remains open and is not represented as fixed by this change.
