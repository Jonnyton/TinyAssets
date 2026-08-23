# Tasks — compute-agnostic-provider-set (≤12; narrow delta)

Owns: provider descriptor/executor registry + capability observations + atomic
migration. Selection/toggle (`user-assigned-llm-policy`), API-key custody
(`retire-mcp-provider-secret-deposit`), connect UX (`byo-llm-connect-flow`) are
sibling umbrella lanes that consume this — NOT built here.

## 0. Pre-req — SALVAGE fleet-removal, do NOT hand-merge it (revised 2026-08-22)
Verification verdict: `retire-cloud-worker-fleet` (branch `claude/fleet-removal-complete`)
is clean/tested/in-scope but 65 commits behind, and its `router.py`/`base.py`/
`provider_assignment.py` conflicts are ALL the dangerous pattern — a large stale-base
DELETION vs main's NEWER additive security/budget work (`_SERVED_PER_CALL_MAX_TOKENS`
served-budget fix, `ProviderInvocationCarrier` authority, connect_http #2485). A
hand-merge risks silently dropping main's work — and slice-1 REWRITES those same files
anyway. So do NOT land the branch as-is.
- [ ] 0.1 **Salvage the clean-merging modules** (additive, no conflict): cherry-pick /
      copy `tinyassets/assigned_credential_execution.py` (+382) + `tests/test_assigned_credential_execution.py`
      (+490) + the archived OpenSpec change onto current `origin/main`.
- [ ] 0.2 **Fold the fleet-removal INTENT into slice-1's router rewrite** (§3 here):
      queued execution resolves each workflow's assigned serving credential; fail closed
      `no_requester_owned_executor`; remove provider-fallback chains / free-provider
      chaining / writer pins / ambient host-credential borrow — but PRESERVE main's
      served-budget decouple, `ProviderInvocationCarrier`, and connect_http substrate.
      This replaces a risky hand-merge of a file we rewrite anyway.
- [ ] 0.3 Delete the cloud-worker fleet files fleet-removal removed (cloud_worker.py,
      host_pool/*, idle_cycle.py, healthcheck, fleet-only tests) as a scoped removal on
      current main + reference-repair. Decide `slack_agent_worker.py` keep-vs-delete
      (main already deleted it; adopt that deletion unless a live surface needs it).

## 1. Registry (owns: provider definition → candidate) — DONE
- [x] 1.1 `ProviderDefinition` immutable descriptor (deterministic server-issued id,
      `access_method` ∈ {`subscription_cli`,`api_key_http`}, `protocol`, model, `ref`
      indirection [provider name | connection_id, never a secret], visibility) +
      per-universe JSON store. Registration creates ONLY a candidate — no
      enroll/authorize/select/route; test asserts the registry store is the sole
      artifact written. Owner-conflict refused; access-method/protocol coherence
      enforced. `tinyassets/providers/definition.py` + 19 tests.
      NOTE: the endpoint + credential + assignment-gen binding lives on the
      referenced `ConnectionLedger` connection (api_key_http reuses connect_http),
      not duplicated in the descriptor — the descriptor holds only the `ref`.
- [x] 1.2 Commons visibility: `list_commons_definitions` returns SHAPE-only public
      views (no owner, no ref); `remix_definition` requires the remixer's own new
      ref and refuses a full-definition dict, so the original owner's ref/credential
      is NEVER carried across a remix.

## 2. Executors (owns: frozen invocation dispatch)
Executors are `BaseProvider` subclasses, so the existing node-execution + serving
machinery consumes them unchanged (agent = node, host decision 2026-08-22).
Compute authorization = the connection GRANT alone (no effector consent / no
outbound-effects flag); SSRF + credential-blindness still apply.
- [ ] 2.1 `provider_for_definition(definition) -> BaseProvider` resolver; selects the
      executor deterministically by `access_method`; NO cross-method ambient fallback.
- [ ] 2.2 `subscription_cli` executor = existing `CodexProvider` behind the resolver,
      verbatim behavior (codex exec, sealed CODEX_HOME, sandbox, auth-health, budget,
      telemetry, `codex` identity). Differential-test vs current `CodexProvider`.
- [x] 2.3a `api_key_http` protocol ENCODERS (not vendor SDKs): `openai_chat` +
      `anthropic_messages` — credential-free request body/path build + fail-loud
      response decode. `tinyassets/providers/protocol_encoders.py` + 18 tests.
- [ ] 2.3b `ApiKeyHttpProvider(BaseProvider)` — composes the encoder + dispatch via
      `ConnectionLedger.resolve_exact_scoped_proxy(universe_id, grant_id, connection_id)`
      then `proxy.request(verb, request)` (the credential-blind broker worker; grant
      gates it, NO effector-consent/flag per the compute-authorization decision) +
      decode into a `ProviderResponse`. Universe-isolation gate: grant.universe_id must
      match. Test wire-request assembly + response parse via the injected in-process
      driver seam (the spawned worker re-imports production SSRF, so a monkeypatch
      cannot cross it — use the loopback-broker seam for assertions).

## 3. Open router
- [ ] 3.1 Implement the routing equation (selected ∩ allowed_providers ∩ enrollment ∩
      capability); replace static role chains (`router.py:180`). Router filters within
      the selected ordered set, never synthesizes a candidate. Empty set → fail closed
      naming the emptying input.
- [ ] 3.2 Preserve fail-loud, bounded cooldown, hard-writer-pin, per-universe privacy
      allowlist; privacy ceiling DOMINATES capability. Assert with mutation-probe tests.

## 4. Capability + advisories (non-authority)
- [ ] 4.1 Capability observations: user-declared (validated on use) + passive
      health/rate from real calls + ONE optional bounded same-origin `/models` probe
      (TTL, per-owner rate/concurrency/cost limit, cache keyed by connection gen).
- [ ] 4.2 Compliance advisories: freshness-stamped, provenance-carrying records
      (seed: the Anthropic third-party-OAuth prohibition, verified 2026-08-22). Assert
      neither observation nor advisory can grant/widen/veto authority — only narrow.

## 5. Migration + prune (atomic)
- [ ] 5.1 Collapse `gemini/groq/grok/ollama` providers into `api_key_http` definitions;
      route `call.py:166` construction and `provider_serving_binding.py:209` through the
      registry; keep `codex`/`claude-code` binding ids stable. `_SUPPORTED_SERVICES`
      retirement is deferred to the custody owner (do not generalize it here).

## 6. Verification + rollout
- [ ] 6.1 Security tests: SSRF reuse on user `base_url`, credential-ref endpoint binding
      (changed base_url can't redirect a key), remix-carries-no-credential, probe
      rate/cost limits, `allowed_providers`-resolves-server-ids, privacy-dominates.
- [ ] 6.2 Guard test: NO LLM reachable without a universe-authorized, requester-owned
      provider (fail-closed everywhere, no ambient/host fallback). Full provider/routing/
      serving suite zero-new-failures vs origin/main; ruff clean; mirror rebuilt.
- [ ] 6.3 Codex exact-diff review (approve/adapt) before merge. Then dogfood:
      **OpenAI-subscription via the browser chatbot connector** (`ui-test`). Queue the
      **API-key dogfood (Claude-API, OpenRouter) behind the custody lane landing.**

## Follow-ups (sibling umbrella lanes, not this change)
Selection surface + toggle (default OpenAI) → `user-assigned-llm-policy` over the open
set. API-key custody (direct-to-executor/native store, opaque tuple-bound ref) →
`retire-mcp-provider-secret-deposit`. Connect UX + Claude-premise correction →
`byo-llm-connect-flow`. Additional protocol encoders beyond openai_chat/anthropic_messages.
