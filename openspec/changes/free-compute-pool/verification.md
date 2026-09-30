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

## PR #4137 CI repair (2026-09-30)

- Merged current main, retaining both append-only activity histories; regenerated the plugin with `python packaging/claude-plugin/build_plugin.py`.
- Regenerated `WebSite/brand/generated-assets.json` with the canonical brand renderer after the app HTML changed.
- Moved source URLs, help/billing links, model IDs, wire names and quota message/header shapes into installed JSON data. Generic readers use those declarations; the channel-specific baseline is unchanged. A synthetic shape test proves new fields and headers work through data and unconfigured fields do not count as daily evidence.
- Preserved protocol-decoded 402 capacity signals, including Retry-After; undeclared decoders use the generic Retry-After parser. Daily exhaustion still takes precedence for 429.
- Restored the original two-argument cooldown call for native auth notices; daily detail is passed only for daily cooldowns. Existing retry and side-effect fences are unchanged.
- Restored actionable ?send again when capacity is available? wording for generic rate limits without inventing a minutes-long window.
- Main did not fix the authority check/use exception contract: the inner evidence store rejects a swapped database before the outer test composition root checks its pinned descriptor. The root now enforces that check even when construction raises, preserving its configuration-error contract while retaining unrelated schema errors. The regression additionally proves no schema or initialization marker was created.
- Final reported-failure files plus new pooling/quota/cards: **149 passed, 3 skipped** on Windows. All `test_provider*.py` suites plus HTTP/capacity suites (including both affected heavy provider files): **842 passed, 21 skipped**. Authority/evidence and failure-reader suites: **112 passed, 3 skipped**. Notice/history suites: **39 passed**. Counts overlap.
- Linux oracle on an external snapshot of all Git-tracked and unignored working files: **170 passed, 1 skipped** across authority/evidence, real-router HTTP, served routing, pooling/quota and notices. The database-swap regression executed and passed. The sole skip requires explicitly configured live Codex credentials/snapshot; it is not claimed as a pass. Snapshotting excluded ignored dependency trees that made the initial oracle copy unnecessarily slow.
- Preview trust-boundary `npm test`: **233 passed, 4 skipped** after `npm ci`. Pre-commit invariants, changed-file Ruff and strict OpenSpec validation pass. Brand and ratchet checks pass without threshold or assertion weakening; new JSON files are included in the regenerated plugin.
- Bounded Claude cross-family repair review via `peer-agents`: **AGREE / APPROVE**, no floor or correctness findings. The pinned-file check preserves cleanup and does not blanket-normalize store errors; the 402 retry evidence and native retry fences remain intact.
- Delivery remains PR only: fast-forward push, mark ready as requested, no auto-merge. Diff-scope receipts or labels are left to the owner; deployment and the real-user app pass remain post-merge.
