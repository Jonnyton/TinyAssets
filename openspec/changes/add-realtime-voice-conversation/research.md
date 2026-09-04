# Voice product and integration comparison

Date checked: 2026-09-03

## Product shape

| Option | Strength | Cost / risk | Fit for TinyAssets |
|---|---|---|---|
| User-bound `tinyassets.voice.v1` bridge | Keeps the platform provider-neutral; owner may choose a remote service, subscription-backed helper, or local resource | Requires a compatible bridge and explicit universe binding | **Selected platform contract** |
| OpenAI `gpt-realtime-2.1` speech-to-speech | Native audio input/output, function calling, semantic VAD, and good interruption/noise behavior | Separately metered API authority; service-specific code would violate the founder's channel-agnostic substrate rule | Suitable behind an owner-supplied bridge, not in platform code |
| Chained transcription → `converse` → deterministic TTS | Clearest author boundary and deterministic synthesis options | More network stages, latency, and separate error/cost surfaces | Suitable bridge implementation |
| Browser/OS speech recognition and synthesis | May use an already-local capability | Inconsistent browser/WebView support, voices, privacy behavior, and turn-taking | Suitable bridge or future client implementation after device proof |

The current-model and capability comparison was grounded in the official
[`gpt-realtime-2.1` model page](https://developers.openai.com/api/docs/models/gpt-realtime-2.1),
while token/context behavior and repeated-context cost risk came from the official
[Realtime cost guide](https://developers.openai.com/api/docs/guides/realtime-costs).
Those findings describe one possible bridge backend, not a TinyAssets platform dependency.

## Connection shape

| Path | Best use | Decision |
|---|---|---|
| Browser/device WebRTC + same-origin SDP exchange through the bridge | Client-side microphone and speaker with low-latency media; HTTP credentials and remote signaling stay behind the owner's generic connection | **Selected** |
| Server WebSocket | Server-side media processing and sideband control | Rejected for the first slice because it makes TinyAssets carry the live media path and bandwidth |
| SIP | Telephone calling | Out of scope |
| Long-lived credential in the client | None | Prohibited |

OpenAI's [WebRTC guide](https://developers.openai.com/api/docs/guides/realtime-webrtc)
was useful evidence for the browser transport and ephemeral-credential pattern. Its provider
event schema is not copied into TinyAssets. Instead, a bridge translates its backend to the
versioned `tinyassets.voice.v1` events consumed by the shared app. The client sends its SDP offer
only to the authenticated same-origin TinyAssets route; the platform exchanges it with the
bridge's allowlisted HTTPS session endpoint through the existing credential-blind, SSRF-hardened
connection proxy and returns only a validated SDP answer.

## Authentication compatibility

As checked on 2026-09-03, the official [Realtime API reference](https://platform.openai.com/docs/api-reference/realtime)
shows Realtime calls authenticated with `Authorization: Bearer $OPENAI_API_KEY`, and the official
[API overview](https://developers.openai.com/api/reference/overview) documents API keys or
workload-identity access tokens as API credentials. These sources do not document a ChatGPT/Codex
subscription session as authorization for Realtime audio. The absence is a product/API limitation
inferred from the documented auth surface, not proof that a private or future route can never exist.

That finding invalidated the original idea of silently reusing the existing subscription token.
The later founder rule also invalidated adding a direct provider-specific API-key adapter to the
platform. The final design does neither: the owner binds a generic HTTP connection and a non-secret
voice manifest; credential resolution and signing remain inside the existing broker child, and the
voice route receives only a sanitized session response.

## Turn-taking and privacy

The generic contract asks the bridge for semantic turn detection, medium eagerness, and immediate
output interruption. The shared app mutes locally on `speech_started`, sends each committed
`tool_call` through canonical `converse`, and accepts speech output only after the corresponding
tool result exists. A bridge may map these semantics onto any backend that can satisfy them.

Retention and training terms belong to the service the owner selected. The first-use disclosure
therefore names that service from the validated binding and links its privacy terms when supplied.
TinyAssets stores canonical text only, never raw audio, provider events, or temporary media bearers.
