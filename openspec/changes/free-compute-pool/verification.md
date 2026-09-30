## Verified provider data (2026-09-30)

All four cards use the owner's key, bearer authentication, `api_key_http` and `openai_chat`. The card fetches the granted `/models` endpoint and intersects its IDs with installed, documented chat/tool models before asking the owner to accept that explicit model list. It does not invent pricing for catalogues that do not publish it. The existing declared-model consent explains that provider billing settings must remain free/trial; TinyAssets cannot impose a zero-dollar request ceiling on these APIs.

| Source | OpenAI-compatible base URL | Current free/trial offer | Primary documentation |
|---|---|---|---|
| Google AI Studio | `https://generativelanguage.googleapis.com/v1beta/openai` | Eligible Gemini models have a free tier. Per-project/model limits; daily requests reset at midnight Pacific. Exact active limits are in AI Studio. | [Endpoint and models](https://ai.google.dev/gemini-api/docs/openai), [pricing](https://ai.google.dev/gemini-api/docs/pricing), [limits](https://ai.google.dev/gemini-api/docs/rate-limits), [key setup](https://ai.google.dev/gemini-api/docs/api-key) |
| Groq | `https://api.groq.com/openai/v1` | Free plan; gpt-oss-120b/20b currently list 30 RPM, 1,000 RPD, 8K TPM and 200K TPD. Payment method needed to upgrade to Developer. | [Endpoint](https://console.groq.com/docs/openai), [limits](https://console.groq.com/docs/rate-limits), [billing](https://console.groq.com/docs/billing-faqs), [key setup](https://console.groq.com/docs/quickstart) |
| Cerebras | `https://api.cerebras.ai/v1` | **Not recurring free:** $5 trial credit, 30 days, verified payment method required. Trial lists 5 RPM and 1M TPD; model/account exceptions apply. | [Endpoint](https://inference-docs.cerebras.ai/resources/openai), [models](https://inference-docs.cerebras.ai/api-reference/models/list-models), [trial and limits](https://inference-docs.cerebras.ai/support/rate-limits) |
| Mistral | `https://api.mistral.ai/v1` | Free mode needs no card; included monthly usage and model rate limits are shown in the account. Current docs give about five minutes for signup/key setup. | [Setup and endpoint](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key), [models](https://docs.mistral.ai/api/endpoint/models), [limits](https://docs.mistral.ai/admin/billing-usage/usage-limits) |

Fastest likely new-user path: **Groq**, from its short account-to-Keys flow and no payment setup for Free. This is an inference from the documented flow, not a measured signup benchmark; a user already signed into Google may find AI Studio faster.

## Quota evidence

OpenRouter's `free-models-per-day` names and epoch-millisecond `metadata.headers.X-RateLimit-Reset`, Gemini's QuotaFailure `PerDay` IDs, Groq's RPD/TPD messages and declared RPD headers, and Cerebras's explicit `*-day` remaining/reset headers are recognized. A generic 429/RESOURCE_EXHAUSTED is insufficient. Mistral does **not** document a daily-specific code: `1300`/`rate_limited` without daily words stays unknown, and the notice no longer promises minutes. The Mistral explicit daily-word fixture tests the generic envelope extension, not a claim that 1300 alone means daily.

Generic short Retry-After hints never override daily evidence. Known provider reset timestamps or declared reset semantics supply the deadline. Without either, a conservative one-day cooldown is used and the notice says the provider supplied no reset time. A later source cleanup cannot shorten a known daily cooldown.

## Verification

- 615 targeted tests passed across quota/capacity, real chat/workflow pooling, model access, connect ingress/controllers, notices and onboarding, including affected heavy `test_provider_retry.py` and `test_provider_work_authority.py`.
- Additional card-controller/ingress tests exercise one password field, clearing before submit, preserving typing over rail refreshes and exact same-origin rejection.
- Final focused regression after mutation restoration: 82 passed. Plugin rebuilt with a successful import probe; all 519 canonical mirrored files match. Strict OpenSpec validation passes.
- Pooling tests use real stores, consent, `prepare_owned_model_plan`, chat coordinator, router, workflow compiler and HTTP adapter. Only remote HTTP responses (including engine tool-list HTTP) are synthetic. The second source is connected through the new card composition and explicitly accepted; the unrelated owner's healthy wire records zero discovery/inference requests.
- Mutation checks, each restored byte-for-byte: disabling daily detection fails both pooling tests; rejecting daily safe-transition evidence fails both; removing the pre-discovery owner/home check fails the foreign-owner card test.
- Ruff passes all changed Python files. A broad `ruff check tinyassets` also encountered existing violations in untouched files; those are outside this lane.
- No live credentials were used and no provider signup speed was measured. Deployment SHA assertion and real-user app proof remain post-merge work; this delivery opens a PR without auto-merge.
- One cross-family Claude review approved the implementation with no correctness blockers. Whole-source cooling follows the requested policy even for model-specific daily limits; failed discovery leaves an inert owned key available for reconnect. The PR is draft because repository automation otherwise re-enables auto-merge on updates.
- After integrating main's patch-intake and timezone work: 314 tests passed across both upstream features, onboarding and this source-pooling change. Changed-file Ruff and strict OpenSpec validation pass; rebuilt runtime import probe passes and all 522 canonical files mirror-match.
