# Serve an open compute provider (the compute-agnostic last mile)

## Why

`compute-agnostic-provider-set` built + landed (PR #2486) everything up to the
authority core: the open provider registry (`connect_compute`), the executors
(`ApiKeyHttpProvider` over the credential-blind proxy), the resolver, the router
bridge, and the non-authority routing building blocks — ~90 tests, full suite green.
But a universe's served/automation turns route the provider through an AUTHORITY
grant that is CLI-subscription-shaped and cannot represent an open provider:

- `authorize_served_provider_call` (provider_assignment.py:1033) requires a
  `provider_binding` in the work-authority store, a subscription **custody** record
  matched by reference-id/generation/digest, `service ∈ {codex, claude-code}`, and a
  subscription **credential snapshot** (line 1172).
- `reserve_served_provider_budget` (line 306) re-checks the subscription custody.
- `ServedProviderAuthority` carries a required `credential_snapshot_dir: Path`.
- `bind_serving_provider` (provider_serving_binding.py:209) accepts only
  codex/claude-code.

An `api_key_http` provider has NONE of these — its credential lives in the connection
grant, resolved at call time by `ApiKeyHttpProvider` via `universe_dir`. So without a
parallel authority path, a user can register + select an open provider but it can
never actually serve.

## What changes

A PARALLEL authority path for open (`api_key_http`) providers, alongside (never
replacing) the subscription-CLI path:

1. **`ServedProviderAuthority.credential_snapshot_dir` becomes `Path | None`** —
   None for an open provider (no subscription snapshot); the CLI path is unchanged.
2. **`authorize_served_provider_call` open-provider branch:** when the serving
   binding's provider is an open provider name (`api_key_http:<def-id>`), validate the
   agent-binding serving/owner/revision facts as today, resolve the ProviderDefinition
   + its connection grant, and require the grant to be **bound to this universe + owned
   by the caller + not revoked** (the isolation gate — belt; `ApiKeyHttpProvider`
   re-checks per call). Build the authority with no snapshot/custody: connection-grant
   identity in the credential_reference_* fields, `credential_service="http"`,
   `credential_snapshot_dir=None`, a bounded default budget. NO subscription snapshot,
   NO custody lookup. The grant IS the authorization — no held-by-default gate (it is
   the user's own compute).
3. **`reserve_served_provider_budget` open-provider branch:** skip the subscription
   custody re-check; reserve against a bounded default open-provider budget keyed by
   the definition id (runaway protection — the user pays their own API bill, so the
   ceiling is generous but present).
4. **`bind_serving_provider` accepts an open-provider def-id:** validate the
   definition exists in the universe + is owned; wire the agent binding's provider_ref
   to the open provider name. No `TINYASSETS_ALLOW_CLAUDE_SERVING`-style hold (that is
   a Claude-subscription safeguard; open providers are grant-authorized).

## Boundaries (defer, do not duplicate)

- `allowed_providers` ceiling / assignment CAS / launch barrier →
  `constrain-set-engine-provider-authority` (consume; the open branch adds no competing
  writer of allowed_providers).
- Credential custody for the deposited api key → the browser-form path
  (`retire-mcp-provider-secret-deposit`); this change resolves the credential ONLY
  through the existing connection grant + credential-blind proxy, never a new secret path.
- **The interactive TOOL-USING agent on an open provider needs the agentic-over-API
  harness (separate follow-up).** THIS change covers the single-completion converse
  turn + automation nodes on an open provider — the router calls `.complete()` once;
  `ApiKeyHttpProvider` does one API call. Multi-tool-call agent loops on an arbitrary
  API are out of scope here.

## Security invariants (must hold)

- Universe isolation: the connection grant must be bound to the RUNNING universe
  (validated here AND per-call by `ApiKeyHttpProvider`); no cross-universe serve.
- Credential-blindness: the api key is applied only inside the broker worker; no
  snapshot, no plaintext in the authority/control plane.
- No ambient fallback: an open provider with an absent/revoked grant fails closed
  (`ProviderAuthorityHeldError`), never borrowing a host credential.
- The subscription-CLI path is byte-for-byte unchanged (differential + full-suite).

## Gate

Authority/credential-sensitive → Codex SHAPE review of THIS design before build, then
exact-diff review before merge; full provider/routing/serving suite zero-new-failures.
Then dogfood: register OpenAI via connect_compute, `set_engine open_provider`, run.
