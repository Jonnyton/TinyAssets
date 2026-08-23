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

## Codex shape review — 2026-08-23: VERDICT adapt (folded — corrected shape)

Credential-blindness + no-fallback pinning approved. Required shape changes before build:

1. **One authority, two DISCRIMINATED variants — reuse the SAME path.** Add an explicit
   `authority_kind` to `ServedProviderAuthority`: `subscription_snapshot` (current custody
   tuple + required snapshot path) | `connection_grant` (exact definition + grant identity,
   no snapshot). NEVER infer open authority from a missing snapshot, and never insert
   placeholder generation/digest. Keep ONE shared assignment / work-binding / CAS path — do
   NOT add an open-provider custody, snapshot, host gate, or a second assignment system.
   `credential_snapshot_dir: Path | None` is allowed but `None` is NOT the discriminator.
2. **`allowed_providers` is a HARD prerequisite, not deferred.** The served router replaces
   the ceiling with `[served_authority.provider]` (router.py:591), so any minted served
   authority bypasses `allowed_providers`. Either make the ceiling change an `applyRequires`
   dependency (constrain-set-engine-provider-authority) or enforce the read-side
   intersection before open serving ships.
3. **`provider_ref` correction.** The canonical open-provider name goes in
   `ProviderAssignment.provider` + the work binding — NOT `agent.configuration.provider_ref`,
   which is the provider-work binding ID that authorization requires to equal
   `assignment.binding_id` (provider_assignment.py:1120). Changing its meaning breaks the
   chain. So an open provider gets a real assignment + work binding (reusing the CAS/
   generation machinery), budget scoped by binding ID/generation.
4. **Exact-identity revalidation + canonical universe.** `authorize_served_provider_call`
   (1033) + `reserve_served_provider_budget` (306) must canonicalize `universe_dir`
   (base_path/universe_id, not just basename at 1059) and revalidate the exact tuple:
   principal + canonical universe + definition id/digest + access_method + definition.ref/
   grant id + grant owner + grant universe + grant connection + non-revoked + assignment/
   work-binding reference equality. Authorization is the PRIMARY owner gate (the executor's
   read of owner from the grant is consistency, not an independent caller check).
5. **Substitution guard at launch.** At router.py:702, verify the selected
   `ApiKeyHttpProvider` instance's definition id/ref/digest matches the served authority
   BEFORE reservation + dispatch (the one-element chain stops name-fallback but not
   same-name registry substitution).
6. **Conservative charging.** The executor raises after `proxy.request` for malformed
   responses (api_key_http_provider.py:175) while the router RELEASES the reservation
   (router.py:767) — a billed request could erase budget. After any possibly-dispatched
   request, CONSUME (not release) the reservation.
7. **Paid-API budget semantics** (not "generous"): a finite hard per-call output-token
   ceiling passed to the API; an atomic rolling invocation ceiling; a rolling CUMULATIVE
   token/spend proxy across settled calls (not just in-flight); isolation by owner/universe/
   binding-id+generation; NO dollar-cost ceiling unless real provider pricing exists
   (ApiKeyHttpProvider reports tokens, no cost_microunits today).
8. **`_current_serving_authority` (provider_serving_binding.py:509)** indexes the
   subscription-only service map unconditionally — extend the current-serving fence (469)
   with the connection_grant variant so bind replay, `set_serving`, and serving-universe
   discovery validate open authority (else open binding succeeds but set_serving fails).
9. **Scope: converse/writer only.** Authorization/routing reject every operation but
   `converse`; "automation nodes" must run inside that converse/writer authority or be
   separately specified — not implied.

This makes the last mile a well-defined, reviewed change reusing the unified authority
model (not a parallel one). Build to this shape, then Codex exact-diff review + full suite.
