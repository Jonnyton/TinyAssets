## Context

`subprocess_env_for_provider` currently copies the host environment, applies a universe vault overlay, and strips host subscription variables only when every tracked value is unchanged. A partial overlay therefore preserves unrelated host authority, while a broad exception handler returns the inherited environment after unexpected vault failures. When `TINYASSETS_ALLOW_API_KEY_PROVIDERS=1`, process-global API-provider variables also remain. Production mounts maintainer Claude and Codex auth homes, so these paths can spend maintainer quota for a user universe.

The function also serves host-local daemon and development calls. Those calls must keep their own subscription authority when no explicit or environment-bound universe exists.

## Goals / Non-Goals

**Goals:**

- Establish universe scope before credential work begins.
- Remove inherited provider tokens/API variables and pin CLI auth homes away from host defaults before applying any universe overlay, even when host API-key providers are opted in.
- Fail explicitly if universe credential resolution cannot complete.
- Preserve host-local behavior and keep the canonical runtime and packaged mirror identical.

**Non-Goals:**

- Provider allowlist enforcement, provider/credential receipts, or market matching.
- In-process Gemini, Groq, or Grok client credential resolution; those providers still require a separate fail-closed change before the platform-wide P0 can close.
- Adding credentials, compute, or fallback capacity supplied by TinyAssets.
- Changing API-key opt-in policy or credential-vault storage.

## Decisions

### Determine authority scope before applying credentials

The provider environment builder will treat any non-empty explicit `universe_dir` or copied `TINYASSETS_UNIVERSE` binding as universe scope without requiring that path to exist or validate first. When neither binding is present, it will return the normal host-local environment without importing or invoking a vault helper. This prevents a missing/malformed universe path or helper failure from reclassifying a user call as host-local.

Alternative considered: infer scope after the overlay by comparing values. Rejected because a legitimate partial overlay makes value comparison unable to distinguish universe authority from inherited host authority.

### Strip first, then overlay only universe-owned values

For a universe-scoped call, inherited OAuth/API variables will be removed and CLI auth homes will be replaced with that universe's `.credentials/codex` and `.credentials/claude` paths before `apply_provider_auth_env` runs. Pinning both homes is necessary because merely deleting `CODEX_HOME` or `CLAUDE_CONFIG_DIR` lets the CLIs rediscover maintainer auth under `HOME`. The vault may then replace those safe defaults or add only values resolved for that universe. This makes the safe state structural rather than conditional on which values changed, whether host API-key providers are opted in, or whether explicit auth-home variables were originally set.

Alternative considered: delete every auth-home variable. Rejected because both CLIs then fall back to maintainer auth under the inherited home directory. Alternative considered: strip only variables for the selected CLI. Rejected because API-key opt-in otherwise leaves process-global provider authority in the child environment. In-process SDK providers are deliberately excluded rather than falsely covered by an environment-only fix.

### Convert unexpected universe credential failures into an explicit provider failure

`ValueError` remains fail-loud for malformed vaults. Any other exception during a universe-scoped overlay will be wrapped in a sanitized `ProviderUnavailableError` without underlying exception text or credential values. Host-local calls do not import or invoke the vault overlay and retain their existing environment under the normal API-key opt-in policy.

Alternative considered: swallow failures after stripping host auth. Rejected because silent absence obscures a broken authority path and conflicts with the project's fail-loud rule.

## Risks / Trade-offs

- **Previously working but unauthorized calls will fail** → This is the intended breaking security correction; operators must configure universe-owned authority. Market authority remains separate and unbuilt in this slice.
- **A vault helper regression can stop universe inference** → Scope is established without the helper, and focused tests cover explicit and environment-bound universe calls.
- **Runtime and packaged plugin can drift** → Make the same minimal edit in both files and run the repository mirror/parity checks.

## Migration Plan

1. Add failing regression tests for partial overlay, host API-key opt-in, default-home discovery, and unexpected overlay failure.
2. Implement strip-before-overlay and explicit failure in the canonical runtime.
3. Apply the identical implementation to the packaged runtime mirror.
4. Run focused and surrounding provider tests, strict OpenSpec validation, and mirror parity checks.
5. Sync the proven requirement into canonical `credential-vault` and archive this change in the same lane.

Rollback is a normal revert, but it reopens a maintainer-credential leak and must restore the P0 concern immediately.

## Open Questions

None for this slice. Provider selection and audit receipts remain in STATUS R2-1a/R2-1b.
