## Context

`subprocess_env_for_provider` currently copies the host environment, applies a
universe vault overlay, and removes host subscription variables only if all
three values remain unchanged. This creates two leaks: one changed variable
suppresses removal of every unchanged host value, and a swallowed unexpected
helper exception bypasses removal entirely.

The ordinary missing-vault path is already protected, API-key stripping remains
owned by the subscription-only policy, and host-local calls legitimately need
their host subscription. The fix therefore needs an explicit universe-scope
decision before any fallible vault helper runs.

## Goals / Non-Goals

**Goals:**

- Make host-subscription isolation fail closed for explicit and environment-
  bound universe calls.
- Let a universe vault add back only that universe's provider credential values.
- Surface unexpected universe vault-helper failures at the provider boundary.
- Preserve host-local behavior and malformed-vault validation behavior.

**Non-Goals:**

- Change API-key opt-in policy, vault storage, encryption, provider selection,
  credential deposit, or public status payloads.
- Remove host subscription credentials from calls with no universe scope.
- Add fallback shims or silently reinterpret invalid universe bindings.

## Decisions

### 1. Determine scope from intent before calling vault helpers

A call is universe-scoped when `universe_dir` is supplied or the copied
environment contains a non-empty `TINYASSETS_UNIVERSE`. The builder strips
`CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, and `CODEX_HOME` immediately for
that scope, before importing, resolving, or applying vault helpers.

Alternative considered: retain the after-overlay equality comparison and make
it per-key. That fixes partial overlays but still leaks when an earlier helper
raises, and it makes provenance depend on comparing secret values rather than
on an explicit trust boundary.

### 2. Apply the vault only after inherited host auth is gone

The existing overlay then adds any supported credential values from the chosen
universe. A partial overlay is safe because omitted variables remain absent,
while a complete overlay behaves as before using universe-owned values.

Alternative considered: snapshot each original value and remove unchanged keys
after overlay. Pre-stripping is smaller, auditable, and secure even when the
overlay mutates the environment before failing.

### 3. Raise on unexpected helper failures for universe-scoped calls

Malformed-vault `ValueError` continues to propagate. Any other exception during
vault import, application, or resolution for a universe-scoped call becomes a
`ProviderUnavailableError` with no secret material in its message. The router
can then apply ordinary provider failure/fallback behavior. A host-local call
retains the existing best-effort behavior because it has no cross-universe
credential boundary to protect.

Alternative considered: swallow the exception after pre-stripping. That is
secret-safe but violates the project's fail-loud rule and hides why the selected
provider lost authentication.

## Risks / Trade-offs

- [Risk] A malformed environment binding strips host auth from a call that was
  intended to be local. → Mitigation: a non-empty universe binding is explicit
  universe intent and must fail closed; clear the binding for host-local work.
- [Risk] New `ProviderUnavailableError` changes the immediate exception type. →
  Mitigation: provider routing already handles that type and can fall back with
  structured diagnostics.
- [Risk] Error text leaks credentials. → Mitigation: name only the provider and
  failed overlay stage; never include environment values or vault records.
- [Trade-off] Universe-scoped calls may fail sooner during helper faults. This is
  required to prevent invisible host-credential use.

## Migration Plan

1. Add red tests reproducing partial-overlay and unexpected-error leakage.
2. Pre-strip host subscription variables for detected universe scope and make
   unexpected scoped helper failures explicit.
3. Run the focused provider/credential suite, independent security review, and
   strict OpenSpec validation.
4. Sync and archive the delta with the implementation, then land through PR.

Rollback restores the prior leakage behavior and is therefore allowed only as
an emergency code revert with the STATUS security row reopened.

## Open Questions

Implementation requires host approval because it changes authentication logic.
