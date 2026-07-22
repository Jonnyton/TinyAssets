## Context

`subprocess_env_for_provider` currently copies the host environment, applies a universe vault overlay, and strips host subscription variables only when every tracked value is unchanged. A partial overlay therefore preserves unrelated host authority, while a broad exception handler returns the inherited environment after unexpected vault failures. Production mounts maintainer Claude and Codex auth homes, so both paths can spend maintainer quota for a user universe.

The function also serves host-local daemon and development calls. Those calls must keep their own subscription authority when no explicit or environment-bound universe exists.

## Goals / Non-Goals

**Goals:**

- Establish universe scope before credential work begins.
- Remove all inherited host subscription variables before applying any universe overlay.
- Fail explicitly if universe credential resolution cannot complete.
- Preserve host-local behavior and keep the canonical runtime and packaged mirror identical.

**Non-Goals:**

- Provider allowlist enforcement, provider/credential receipts, or market matching.
- Adding credentials, compute, or fallback capacity supplied by TinyAssets.
- Changing API-key opt-in policy or credential-vault storage.

## Decisions

### Determine authority scope before applying credentials

The provider environment builder will derive universe scope from the explicit `universe_dir` first and otherwise from the copied `TINYASSETS_UNIVERSE` binding. When neither exists, it will return the normal host-local environment. This avoids depending on a vault helper to decide whether it is safe to retain host credentials.

Alternative considered: infer scope after the overlay by comparing values. Rejected because a legitimate partial overlay makes value comparison unable to distinguish universe authority from inherited host authority.

### Strip first, then overlay only universe-owned values

For a universe-scoped call, all entries in `HOST_SUBSCRIPTION_ENV_VARS` will be removed before `apply_provider_auth_env` runs. The vault may then add only credentials resolved for that universe. This makes the safe state structural rather than conditional on which values changed.

Alternative considered: strip only provider-relevant variables. Rejected because routing and provider selection remain separate work; an unchosen provider credential must not survive in a universe child environment.

### Convert unexpected universe credential failures into an explicit provider failure

`ValueError` remains fail-loud for malformed vaults. Any other exception during a universe-scoped overlay will be wrapped in `ProviderUnavailableError` without credential values. Host-local calls do not need the vault import or overlay and retain their existing environment.

Alternative considered: swallow failures after stripping host auth. Rejected because silent absence obscures a broken authority path and conflicts with the project's fail-loud rule.

## Risks / Trade-offs

- **Previously working but unauthorized calls will fail** → This is the intended breaking security correction; the error directs operators to configure universe-owned or accepted-market authority.
- **A vault helper regression can stop universe inference** → Scope is established without the helper, and focused tests cover explicit and environment-bound universe calls.
- **Runtime and packaged plugin can drift** → Make the same minimal edit in both files and run the repository mirror/parity checks.

## Migration Plan

1. Add failing regression tests for partial overlay and unexpected overlay failure.
2. Implement strip-before-overlay and explicit failure in the canonical runtime.
3. Apply the identical implementation to the packaged runtime mirror.
4. Run focused and surrounding provider tests, strict OpenSpec validation, and mirror parity checks.
5. Sync the proven requirement into canonical `credential-vault` and archive this change in the same lane.

Rollback is a normal revert, but it reopens a maintainer-credential leak and must restore the P0 concern immediately.

## Open Questions

None for this slice. Provider selection and audit receipts remain in STATUS R2-1a/R2-1b.

