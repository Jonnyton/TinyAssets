# Pricing applicability independent implementation review

September9,2026 UTC. Review14602 completed421s, VERDICT ADAPT,268 focused
passes independently reproduced. Reviewed working tree over558b94a3.
Required cache-write correction applied afterward: input_cache_write bounded
by input cap, regression flipped and cap-fit test extended. Also corrected the
author-reproduced generic advisory extra-fee omission and documented free-only
wire enforcement dependency. No further review round dispatched; corrected
head is not independently reapproved. Full final tests recorded in pricing-proof.

Reviewer's Gemini example mixed implicit and explicit caching subsections: the
current guide says implicit caching has no write/storage cost, whereas the
write/storage formula belongs to explicitly enabled caching. The OpenAI automatic
write surcharge independently establishes the blocking finding, so accept the
required general correction without repeating the inaccurate Gemini premise.

Docker oracle bootstrap changes558b94a3 independently accepted. Optional
image-token ambiguity and endpoint-level pricing/reasoning count coverage remain
integration notes, not claims of live paid safety or full-agent completion.

## Verbatim review

I've finished gathering evidence and am now writing up the verdict.

## Verdict: ADAPT (one concrete change), everything else approved

Focused tests I ran in the frozen worktree: 268 passed across the pricing, decoder, policy, snapshot, authority and market-surface files. The packaging copies of the four core modules are byte-identical to the core tree.

### DISAGREE_EVIDENCE: cache-write exclusion is not justified by the encoder shape

The shape review excluded `input_cache_write` because the plain-string encoder cannot emit `cache_control`. The current OpenRouter prompt-caching guide contradicts that premise for automatic-caching providers:

- OpenAI: "Prompt caching with OpenAI is automated and does not require any additional configuration" and, for GPT-5.6 and later, "Cache writes: charged at 1.25x the price of the original input pricing, even with automatic caching."
- Gemini 2.5+ implicit caching: no `cache_control` required, and "Cache write cost = Input token price + (Cache storage price × (5 minutes / 60 minutes))."
- DeepSeek: automated, writes "charged at the same price as the original input pricing."
- Anthropic is the only listed provider that needs a client-sent `cache_control`, and the 1-hour TTL needs an explicit `ttl` field. The 1h exclusion is therefore sound. The 5-minute write exclusion is not.

The provider-selection guide documents `max_price` only for prompt, completion, request and image. It says nothing about the prompt bound covering cache-write pricing. So a plain-string request to a GPT-5.6-class or Gemini endpoint can be charged a cache-write rate above the accepted input cap with no client opt-in, and `SelectedModel.cost_upper_bound` reserves only context tokens times the input cap. That widens the reservation, which the patch's own test brief says must never happen. Under today's free-only caps the magnitude is zero for real rows, since 1.25 times a zero prompt price is zero, but the test at `tests/test_model_price_applicability.py:66` explicitly asserts that a nonzero advertised cache-write price is accepted on a zero-prompt row, which locks in the wrong rule.

Required change, minimal and inside the existing seam:

- In `tinyassets/providers/discovery_protocols.py:103`, remove `input_cache_write_million_tokens_usd` from `excluded_components` and add `("input_cache_write_million_tokens_usd", "input_million_tokens_usd")` to `extra_price_bounds`. Keep the 1h component excluded.
- Flip the `("input_cache_write", "0.000002", True)` parametrize row to `False`, and add `input_cache_write` to the cap-fit parametrize at line 79.
- Mirror to the packaging copy. The cost is that Anthropic rows priced at exactly a paid cap would be rejected because their 1.25x write price exceeds it. That is conservative, not a capability loss, and free-only rows are unaffected.

### AGREE, with evidence

- **Cache reads bounded by the input cap.** The caching guide lists reads at 0.1x to 0.5x of input for every provider, and the policy additionally rejects any advertised read price above the input cap at `model_policy.py:263`. Endpoint-level read prices that differ from the model-level advertisement remain a deferred integration requirement, not a concrete escape.
- **Reasoning bounded by the completion cap.** The reasoning guide states "Reasoning tokens are considered output tokens and charged accordingly." The price bound is correct. Deferred, not gating: some models carry `default_enabled: true`, and the docs do not state that `max_tokens` bounds reasoning tokens for every provider. That affects the token-count half of the reservation, which this patch leaves unchanged from base.
- **Mandatory evidence versus optional wire ceilings.** Missing prompt or completion becomes an unknown component and rejects. Missing request or image proceeds only when a confirmed accepted cap exists, and `_validate_snapshot` always supplies all four caps, with zeros for free-only. The constrained body is applied at the real dispatch site in `api_key_http_provider.py:205`. The only caller of `order_models` is `_validate_snapshot`, so no public selector or UI is activated.
- **Maximum across overrides.** The SDK `PricingOverride` type contains only price fields plus `minPromptTokens`, `utcDays`, `utcStart`, `utcEnd`. The decoder's condition set matches exactly, any other key rejects, and `discount` is ignored so it can never lower a bound.
- **Unknown or malformed extras.** Known charges are retained alongside `unknown_components`, a malformed known component is dropped from charges and recorded as unknown, and the updated decoder test asserts four charges survive next to one unknown.
- **Exact decimal strings.** The formatter is correct for zero, whole, and sub-micro values, and rejects above 10^18 micros. The SDK `MaxPrice` type declares every field as a string. The public guide's example uses bare numbers, so string acceptance is a live-gate item. If the server rejects strings the request fails closed with no charge.
- **Plain-string guards.** The real encoder emits exactly role and content strings, so the shape guard matches production. The body key whitelist blocks plugins, tools, modalities, reasoning, provider, models and route. The `@preset/` and `:online` guards match the documented indirections.
- **Output media.** Image generation requires an explicit modalities selection per the image-generation guide, and the policy still demands an advertised zero image or audio output price before accepting such a model. Video or other output modalities reject.
- **Text-only rules stay on the text interaction.** They live only on `text_interaction`. A future tools interaction must declare its own bounds, and tool-enabled dispatch is still refused before encoding.
- **Caps, manifest, reservation unchanged.** `provider_assignment.py`, `SelectedModel`, and the manifest are untouched.

### Docker oracle repairs at base 558b94a3

Sound. Dockerfile escape processing does not apply inside RUN except at line end, so the `'\n'` reaches Python intact. The `test -s` guard fails the build on an empty requirements file, the regression test executes the exact Dockerfile payload rather than a copy, and `--no-same-owner` keeps the extracted tree owned by the container user so the fresh `git init` is not flagged as dubious ownership.

### Minor, non-gating

- `image_token` is excluded as input-image pricing, but the SDK comment only says "Price in USD per image token." Since image output already requires an explicit zero `image_output` and generation needs a blocked `modalities` field, there is no concrete escape. Requiring a zero `image_token` whenever image output is advertised would close the ambiguity cheaply.
- The advisory free-only path at `model_policy.py:220` lets a missing request price through with a comment that the wire ceiling is enforced, but nothing in that branch verifies it. It is safe only because the sole caller always passes explicit caps. A one-line comment stating that dependency would prevent a future caller from relying on it.
