Independent Claude review, September 9,2026. Exact head4e21c3d5; terminal exit0 after358s. Internal implementation APPROVE, metadata shape ADAPT. Corrections are incorporated in discovery-profile.md before publication code.

**Scope inspected:** head 4e21c3d5 verified, tree clean before and after. I read both new modules, the model_policy diff, both test files, both proof docs, the profile, and the existing storage/API capability code. I ran only the discovery transport tests with cache disabled.

```
python -m pytest -q -p no:cacheprovider tests/test_discovery_http.py
63 passed in 1.49s
```

The runtime mirror copies of both modules are byte-identical to the source copies.

## Part 1: implementation at 50192fd7 and 4e21c3d5

**AGREE, no actionable defects.** Each claimed property is backed by the code I read.

- **Exact pricing.** Prices are string-only Decimals scaled to integer micros with a non-integral remainder refused, so a sub-micro nonzero price never rounds to free (`tinyassets/providers/catalog_decoders.py:47-69`). An unfamiliar charge key collapses the whole pricing to unknown rather than being dropped (`catalog_decoders.py:73-76`). Both are regression-tested.
- **Scores.** Indices are exact millionths from int, float, or string; bool is refused. Duplicate per-model records are unranked, and one source only (`catalog_decoders.py:179-193`).
- **Opaque joins.** Score join is by exact id or the catalogue's own `canonical_slug`; the decoder does no stripping or guessing (`catalog_decoders.py:135-137`). Duplicate or malformed ids reject the whole catalogue.
- **Partial data.** Mismatched count, a `links.next`, HTTP 206, redirects, duplicate JSON keys, and non-finite constants all fail loudly (`catalog_decoders.py:85-97`, `discovery_http.py:112-135`).
- **Freshness.** Connection freshness comes from the caller's context and is copied unchanged; benchmark freshness derives from `as_of` against the caller's clock, never from fetch time. Remote top-level flags cannot flip owner_filtered, executor_tools, or account id; that is tested directly.
- **Isolation.** Five layers agree before any socket: definition, grant, connection view, the exact resolver with principal recheck (`storage/outbound_connections.py:3633-3654`), then the broker's live re-read of the grant row (`outbound_connections.py:736-745`). The lambda principal verifier is the established pattern used by the HTTP executor (`providers/api_key_http_provider.py:137`), voice (`onboarding/realtime_voice.py:325`), and external calls, so this is consistent, not a shortcut.
- **Broker reuse and cleanup.** One proxy per read, closed in a finally block, and a failed close discards the result rather than returning it (`discovery_http.py:98-110`). Tests count starts and closes on every path.
- **No leaks or expansion.** All raised messages are fixed strings with `from None`; the broker separately refuses any response containing the credential. Port 443 only, existing allowlist enforced before the proxy and again at dispatch, and full-channel grants keep only their declared hosts. No new endpoint, scope, header override, or retry exists.
- **Output modality addition.** Additive with a text default, so existing constructions are unchanged, and the check is a subset test like input modalities (`providers/model_policy.py:192-193`).

**DISAGREE_CONCERN, non-blocking, integration not yet implemented.** The decoder's closed component set is prompt, completion, request, image. The real OpenRouter pricing object as I know it also carries web_search, internal_reasoning, and cache read/write keys, which this decoder treats as unfamiliar. With that shape every live row decodes to unknown pricing and nothing is ever automatically eligible. That is the safe direction and the proof doc says so, but the passing fixtures do not resemble a real response, so they do not prove automatic eligibility works. Confirm against a real account response before any automatic-selection claim.

**Optional hardening.** A row with no architecture block reports `capability_unsupported` rather than `capability_unknown`; conservative but semantically loose. Each read spawns a fresh proxy process; single-flight and caching are already on the acceptance list.

**Implementation disposition: APPROVE** as an internal, unactivated slice.

## Part 2: profile shape, pre-build

**AGREE** on the home: the existing capabilities table plus the existing configure operation, no identity or grant change, no second registry, no LLM dependency. **DISAGREE_EVIDENCE** on three points where the profile understates what the existing code forces.

1. **Storage is single-kind by construction, not by table.** The kind set is a one-element frozenset (`outbound_connections.py:1796`). The value type is voice-shaped (`outbound_connections.py:226-246`). The validator pins the voice protocol and fields (`outbound_connections.py:1822-1856`). Configure requires POST scope and allowlists `session_url` for POST (`outbound_connections.py:3308-3378`). Read re-validates through the same voice validator (`outbound_connections.py:3380-3398`). The profile must state that all four sites dispatch on kind through one in-module spec table mapping kind to value type, validator, verb, and URL fields, with GET for model_discovery. That is the bounded extension; anything else is either a second registry or a broken read path.

2. **The existing API handler has the LLM dependency the profile forbids.** It resolves the connection from the current serving provider, which requires one serving binding and a resolved assignment (`api/provider_capability.py:74-90`). The definition_id branch is the right fix, but the profile must say explicitly that this kind bypasses that resolver entirely, loads the definition through the store's verified lookup, which checks the content address and universe bucket (`providers/definition.py:272-294`), then applies the same grant and resource gate as compute registration (`api/compute_connection.py:74-120`). The closed payload field set (`provider_capability.py:63-72`) admits `definition_id` for this kind only, and the voice-specific error name is not reused. The server branch at `universe_server.py:1173` needs no change.

3. **Account-filtered semantics: pin the path in the adapter, never carry a flag.** This is the smallest correction. The adapter `openrouter_user_models_v1` declares `account_filtered=True` and one fixed catalogue path. Publication rejects any `catalogue_url` whose canonical path differs from that constant or carries a query; the host stays the owner's choice bounded by the connection allowlist. At refresh, the adapter alone computes `owner_filtered` as: adapter is account-filtered, the fetched URL equals the pinned URL, and HTTP 200 returned through this grant's credentialed proxy. It is never stored in the descriptor, never a parameter to the decoder or ordering call from outside the adapter, and never read from the body. A same-schema global list lives at a different path, so it cannot be configured under this adapter at all; a future global adapter carries `account_filtered=False` and the existing `privacy_unverified` gate keeps it out of automatic selection. Keep `authenticated_account_id` None so capacity identity stays per connection. Do not add an unauthenticated negative probe; that would be endpoint expansion. The trust here is in the owner's declared host and chosen adapter, the same trust already placed in executing against it, not in remote metadata.

**Also state in the profile.** The row is keyed by connection, so every definition sharing a grant shares the profile, and removal through any one removes it for all. Revocation leaves the row in place; every reader must gate on the live view as voice does (`realtime_voice.py:127-140`) and as the transport already does.

**Profile-shape disposition: ADAPT** with the three corrections above before publication implementation. None weakens the prior gates: owner subscription and local defaults still rank first, catalogue evidence still cannot make the text-only executor tool-capable, and explicit choices and empty fallback lists keep their meaning.

VERDICT: ADAPT
