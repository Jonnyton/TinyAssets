# Selected-model execution and snapshot refresh — independent review

September9,2026. Claude read-only review of exact83b19b49bbc3cdc1f2c031045619ee482a84db14, terminal exit0 after349s, APPROVE. The reviewer reproduced42 tests. This is approval of the bounded local integration, not the unfinished full selector or permission to activate it.

## Disposition

No blocking implementation findings. Retain the recorded live pricing/component, async IO/lock and full-agent readiness gates. Optional observations are not silently treated as completed fixes: observation time before the read, typed SQLite failure wrapping and contract-derived cost estimation remain follow-ups. Keep the conservative full-context input bound until a protocol-specific tokenizer/overhead upper bound is established; a raw byte estimate is not assumed to bound every server-added token. No new review process is active.

## Full reviewer response

Review complete. I read the spec and proof docs, the full canonical diff for all nine source files plus the test file, and the entire `discovery_snapshot.py` coordinator, then traced each check through the router, reservation, and HTTP encoder. I ran only `tests/test_selected_model_authority.py` with the cache provider disabled: 42 passed in 3.29s. No subagents, edits, commits, or live calls.

## Check results

**Untrusted reference/config cannot fabricate membership or broaden authority.** AGREE. The request-local `ModelRef` is only accepted under a validated carrier, and membership is resolved from the signed manifest in `provider_serving_binding.py:843-861`. Cost caps come from `member.access` at `provider_assignment.py:1349`, never from the caller. The router unconditionally overwrites `ModelConfig.selected_model` from the authority at `router.py:614` and rejects provider mismatch. Endpoint, host, and auth are unchanged: the selection only substitutes the body `model` at `api_key_http_provider.py:200`. Owner is rechecked at `model_selection.py:83-85`.

**Independent member after anchor revocation.** AGREE. Both `_current_bound_member_authority` and the new reservation branch at `provider_assignment.py:469-489` validate the member's own binding and grant custody, and `_open_connection_id` resolves the member's definition. The revoked-primary test proves the wire hits only the independent grant.

**Explicit empty allowlist holds.** AGREE. The `allowed_providers is not None` branch at `router.py:147-152` precedes the selected-model branch, and an empty ceiling raises at `router.py:165-167`.

**Source/profile/agent changes at boundaries.** AGREE. After discovery: agent recheck at `provider_assignment.py:1355-1358`, then full chain equality at `:1379-1382` under a fresh transaction. Inside the slot: `before_selected_launch` reruns snapshot freshness and the `_context` digest, which fails on grant revocation, profile change, or view change, plus the agent binding. No SQLite read transaction spans the network IO.

**Request count not consumed before launch.** AGREE. The router calls `before_launch()` inside the slot before `consume_provider_request_invocation`, and the slot-refusal test asserts zero invocations with the reservation released.

**Model/context/cost freshness.** AGREE. Automatic-mode eligibility requires fresh capability and fresh, confirmed pricing at `model_policy.py:199-220`; known context via `min_context=1`; and the 5-minute window with backwards-clock rejection at dispatch in `discovery_snapshot.py:211-224`.

**max_price units and never-round-up.** AGREE. Micros over one million matches both USD-per-million and USD-per-request wire semantics, and `nextafter` toward zero at `discovery_protocols.py:71-73` guarantees a downward-only float.

**High caps respect binding reservation.** AGREE. `affordable_output` bounds output tokens, and the floor `max(legacy, cost_upper_bound)` at `provider_assignment.py:626-630` can never exceed remaining cost because the ceiling-division of the floored token count stays within the integer remainder.

**Unknown actual cost conservative; model receipt not rewritten.** AGREE. `finalize` charges the full reservation on a missing cost at `provider_assignment.py:707-712`. `ProviderResponse.model` is `reported_model(parsed)` and `cost_microunits` stays None at `api_key_http_provider.py:262-270`.

**Legacy behavior preserved.** AGREE. `selected_model` is the last `ModelConfig` field; the legacy reservation branch requires `selected_model is None`; v2 assignments without a selection still hold at `provider_serving_binding.py:819-822`; the projection writer is byte-identical without `candidate_bindings`.

**Wire trace.** AGREE. The openai_chat encoder emits only model, messages, temperature, max_tokens; the constrainer rejects any other key and adds `provider.max_price` plus `require_parameters` at `discovery_protocols.py:50-74`.

**discovery_snapshot.py coordinator.** AGREE on design. `_context` validates definition owner and access method, live grant scoped to owner and universe, connection not revoked with GET in scope, profile present and validated, and auth scheme matching the protocol, all inside one ledger transaction, with the digest covering grant identity, granted_at, view, and profile. `refresh_model_discovery` compares before/after context and enforces the window. The async single-flight is shielded per loop and retrieves exceptions; it is unused by the sync serving path.

**Cost-constraint correctness beyond recorded gates.** No additional flaw found. Decoder components at `catalog_decoders.py:30-35` are exactly the four the encoder can bound, and any unfamiliar pricing key yields missing pricing at `:72-76`, so unbounded components fail closed rather than pass as free.

## Concrete actionable bugs

None blocking.

## Recorded gates and optional hardening

- **Gate, fail-closed:** current OpenRouter catalogues commonly list extra pricing keys such as web_search or internal_reasoning. Under the decoder rule, those rows become ineligible, so live activation may refuse every model. This is the recorded live price-component gate, not a safety flaw.
- **Gate:** discovery runs under the shared admission fence during network IO, so exclusive publishers queue behind broker latency. Recorded async/lock constraint.
- **Hardening:** `observed_at` is stamped after the catalogue read returns in `refresh_model_discovery`, so the freshness window starts after network latency. Stamp it before the read.
- **Hardening:** `_context` does not catch `sqlite3.Error`, so a raw DB error in the pre-launch recheck escapes with a non-provider exception type. Still fail-closed.
- **Hardening:** `SelectedModel.cost_upper_bound` hardcodes OpenRouter component names in a protocol-agnostic module. A second protocol would KeyError, fail-closed, but the bound should derive from the contract.
- **Hardening:** full-context input reservation is very conservative and may make paid large-context selections unaffordable under typical binding ceilings. The byte-length estimate already used for tokens would be a tighter safe bound.

VERDICT: APPROVE

