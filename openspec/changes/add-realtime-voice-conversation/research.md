# Voice product and integration comparison

Date checked: 2026-09-03

## Product shape

| Option | Strength | Cost / risk | Fit for TinyAssets |
|---|---|---|---|
| OpenAI `gpt-realtime-2.1` speech-to-speech | Current Realtime model; native audio input/output, function calling, semantic VAD, and improved interruption/noise behavior | Separately metered API compute; generative speech can diverge from canonical punctuation or wording; provider retention applies | **Selected transport**, with `converse` as the only author and muted output until its canonical reply exists |
| Earlier `gpt-realtime-2` / `gpt-realtime` | Similar Realtime integration surface | Older behavior; no advantage for a new pinned rollout | Not selected; keep the model allowlist server-owned and re-evaluate deliberately |
| Chained transcription → `converse` → deterministic TTS | Clearest author boundary and deterministic synthesis options | More network stages, more latency, separate error/cost surfaces, and manual turn orchestration | Primary fallback if measured spoken-output fidelity is unacceptable |
| Browser/OS speech recognition and synthesis | Can avoid a dedicated Realtime session in some environments | Inconsistent browser/WebView support, voices, privacy behavior, and turn-taking | Not a first-class cross-platform product path |

The current-model and capability choice is grounded in the official
[`gpt-realtime-2.1` model page](https://developers.openai.com/api/docs/models/gpt-realtime-2.1),
while token/context behavior and repeated-context cost risk come from the official
[Realtime cost guide](https://developers.openai.com/api/docs/guides/realtime-costs).

## Connection shape

| Path | Best use | Decision |
|---|---|---|
| Browser/device WebRTC + server-minted client secret | Client-side microphone and speaker with low-latency media; long-lived key remains server-side | **Selected** |
| Server WebSocket | Server-side media processing and sideband control | Rejected for the first slice because it makes TinyAssets carry the live media path and bandwidth |
| SIP | Telephone calling | Out of scope |
| Long-lived API key in the client | None | Prohibited |

OpenAI's [WebRTC guide](https://developers.openai.com/api/docs/guides/realtime-webrtc)
recommends WebRTC for browser/mobile clients and documents the ephemeral-secret exchange. The
[client-secret reference](https://developers.openai.com/api/reference/python/resources/realtime/subresources/client_secrets/methods/create)
also makes an important limitation explicit: attached session configuration can be overridden by
the client connection. TinyAssets therefore treats the first-party app, CSP, narrow tool adapter,
muted-output gate, and canonical `converse` result as layered controls; the ephemeral secret is a
credential-custody boundary, not a cryptographic guarantee that an altered client cannot choose a
different Realtime configuration against its owner's own API account.

The official client-secret schema does not expose a `safety_identifier` field, and the official
API documentation does not define an `OpenAI-Safety-Identifier` request header. TinyAssets does
not invent that header: the stable signed-in identity remains the local mint-rate-limit key, and a
provider safety identifier will be added only if OpenAI documents a Realtime-supported field.

## Authentication compatibility

As checked on 2026-09-03, the official [Realtime API reference](https://platform.openai.com/docs/api-reference/realtime)
shows Realtime calls authenticated with `Authorization: Bearer $OPENAI_API_KEY`, and the official
[API overview](https://developers.openai.com/api/reference/overview) documents API keys or
workload-identity access tokens as API credentials. The official [API quickstart](https://developers.openai.com/api/docs/quickstart)
also separates API-key setup and API billing from product subscription sign-in. These sources do
not document a ChatGPT/Codex subscription session as authorization for Realtime audio. The absence
is a product/API limitation inferred from the documented auth surface, not proof that a private or
future route can never exist.

Therefore TinyAssets does not send the Codex subscription token to Realtime and does not ask for a
replacement key merely to finish this feature. The OpenAI adapter is ready only when an owner has
already bound a compatible API-project credential to that universe. Otherwise Voice stays visible
as locked. Future per-user adapters may use a documented subscription voice entitlement, local
speech resources, or another provider's user-bound speech capability after their authority,
privacy, and canonical-author contracts are specified; none may use maintainer or platform quota.

## Turn-taking and privacy

Semantic VAD with medium eagerness is selected because it waits for semantic completion more
naturally than fixed silence alone. `interrupt_response=true` owns provider-side cancellation;
the client immediately mutes playback on `speech_started` rather than issuing a duplicate cancel.
See the official [VAD guide](https://developers.openai.com/api/docs/guides/realtime-vad).

The API is not used for model training by default, but default abuse-monitoring logs can be
retained for up to 30 days unless an eligible organization configures different data controls.
TinyAssets therefore discloses the provider path before capture and stores only canonical text,
not raw audio. See [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data).
