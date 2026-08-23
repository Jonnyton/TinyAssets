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

## 1. Registry (owns: provider definition → candidate)
- [ ] 1.1 `ProviderDefinition` immutable descriptor (server-issued id, `access_method`
      ∈ {`subscription_cli`,`api_key_http`}, `protocol`, normalized endpoint, model,
      opaque `credential_ref` tuple-bound to endpoint+assignment-gen, visibility) +
      storage. Registration creates ONLY a candidate — no enroll/authorize/select/route.
- [ ] 1.2 Commons visibility: a `commons` definition is a descriptor-only remix source;
      remix NEVER auto-binds the original owner's credential.

## 2. Executors (owns: frozen invocation dispatch)
- [ ] 2.1 `Executor.execute(invocation, credential_ref)` interface; select
      deterministically by `access_method`; NO cross-method ambient fallback.
- [ ] 2.2 `subscription_cli` executor = existing `CodexProvider` behind the interface,
      verbatim behavior (codex exec, sealed CODEX_HOME, sandbox, auth-health, budget,
      telemetry, `codex` identity). Differential-test vs current `CodexProvider`.
- [ ] 2.3 `api_key_http` executor = `openai_chat` + `anthropic_messages` protocol
      ENCODERS (not vendor SDKs) that emit through the SSRF-hardened outbound proxy
      (`ConnectionLedger` + credential-blind proxy). Differential-test the openai_chat
      encoder against the current grok/groq/ollama providers' request/response handling.

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
