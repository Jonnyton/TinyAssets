# Tasks — serve-open-compute-provider (build to the Codex-reviewed shape in proposal.md)

Authority/credential-critical. Build order minimizes blast radius; each step keeps the
subscription-CLI path byte-for-byte unchanged (differential + full suite between steps).
Do NOT start the live-authority steps (3–6) without the shape in proposal.md open.

## 0. Hard prerequisite (Codex finding #2)
- [ ] 0.1 `allowed_providers` intersection at the served-authority chain. The served
      router replaces the ceiling with `[served_authority.provider]` (router.py:591), so
      any minted authority bypasses `allowed_providers`. Either land the read-side
      intersection there, or declare an `applyRequires` dep on
      `constrain-set-engine-provider-authority` and land that first. Open serving MUST NOT
      ship until this holds. Mutation-probe: a served authority outside the allowlist is refused.

## 1. Authority shape (Codex findings #1, #3)
- [ ] 1.1 `ServedProviderAuthority`: add `authority_kind: str` ("subscription_snapshot" |
      "connection_grant"); make `credential_snapshot_dir: Path | None`. Update the ONE
      subscription construction site (provider_assignment.py:1176) to pass
      `authority_kind="subscription_snapshot"`. `None` is NEVER the discriminator — an
      absent CLI snapshot must fail closed (assert with a test).
- [ ] 1.2 The open provider gets a REAL `ProviderAssignment` + provider-work binding via
      the SAME CAS/generation machinery (no parallel system). `provider_ref` STAYS the
      work-binding id (== assignment.binding_id at 1120); the open name goes in
      `ProviderAssignment.provider`. Budget scope = binding id + generation.
      SOLVED custody approach (credential_vault.py — follow `adopt_llm_subscription_custody`
      / `current_llm_subscription_custody`'s exact pattern): add `adopt_connection_grant_custody`
      / `current_connection_grant_custody` that REUSE the `llm_credential_custody` table +
      `_custody_reference_digest`, with `service = f"connection:{connection_id}"` and a
      SECRET-FREE grant-identity `record_digest = _canonical_digest({grant_id, connection_id,
      credential_ref, owner_user_id, universe_id, schema_version:1})` (NOT the credential
      material — the secret stays credential-blind; the digest rotates if the grant changes).
      This yields a valid `LLMCredentialCustodyReference` (reference_id/generation/reference_digest/
      _record_digest) that `_assignment` + the work-binding seed consume UNCHANGED — so bind /
      authorize / reserve reuse the same integrity + CAS with only a custody-source branch.
      Owner gate: the caller already validated the connection grant is owned + bound; the
      custody table's UNIQUE(owner,universe,service) + the grant-ownership check are the gate.

## 2. Bind + serving fence (Codex findings #5, #8)
- [ ] 2.1 `bind_serving_provider` accepts an open-provider def-id: validate the definition
      exists + is owned AND its current connection grant is bound-to-universe + owned +
      not-revoked; no claude-style host-opt-in hold (grant is the authorization). Create
      the connection_grant-kind assignment/work binding.
- [ ] 2.2 Extend `_current_serving_authority` (provider_serving_binding.py:509, indexes the
      subscription-only service map) + `set_serving` + serving-universe discovery with the
      connection_grant variant, or open bind succeeds while set_serving fails.

## 3. Authorize + reserve (Codex findings #4, #7)
- [ ] 3.1 `authorize_served_provider_call` connection_grant branch: canonicalize
      `universe_dir` (base_path/universe_id, not basename at 1059); revalidate the EXACT
      tuple (principal + canonical universe + definition id/digest + access_method +
      definition.ref/grant id + grant owner + grant universe + grant connection +
      non-revoked + assignment/work-binding reference equality). NO snapshot, NO custody.
      Authorization is the PRIMARY owner gate.
- [ ] 3.2 `reserve_served_provider_budget` connection_grant branch: skip subscription
      custody; enforce paid-API budget — finite per-call output cap passed to the API,
      atomic rolling invocation cap, rolling CUMULATIVE token/spend across settled calls,
      binding-id/generation scope, NO dollar-cost ceiling unless real pricing exists.

## 4. Launch guard + charging (Codex findings #5-substitution, #6)
- [ ] 4.1 Substitution guard at router.py:702 — the selected `ApiKeyHttpProvider` instance's
      definition id/ref/digest MUST match the served authority before reservation + dispatch.
- [ ] 4.2 Conservative charging: after a possibly-dispatched request, CONSUME (not release)
      the reservation (router.py:767 currently releases on the executor's post-dispatch
      raise → billed-but-free). A malformed/failed response after dispatch still consumes.

## 5. Scope (Codex finding #9)
- [ ] 5.1 converse/writer authority only (authorization/routing reject other operations).
      "automation nodes" run inside that authority or are separately specified — not implied.

## 6. Verify + rollout
- [ ] 6.1 Tests: open-provider serve happy path (single-completion converse via injected
      proxy); cross-universe/owner/revoked grant refused; allowlist intersection enforced;
      substitution guard; conservative charging (billed request consumes); subscription-CLI
      path differential-unchanged; set_serving open variant. FULL provider/routing/serving
      suite zero-new-failures; ruff; mirror.
- [ ] 6.2 Codex exact-diff review (approve/adapt) before merge. Then merge #2486-lineage,
      deploy (confirm prod git_sha), and dogfood: connect_compute registers OpenAI (key
      supplied by the founder out of band), `set_engine open_provider`, run a converse turn
      + an automation. `ui-test` for the chatbot surface.
