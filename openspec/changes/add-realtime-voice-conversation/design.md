## Context

The shared app at `/mcp/app` is one HTML/JavaScript client used by the browser and the Capacitor Android/iOS shells. Its text composer already calls the canonical `converse` MCP handle, which authorizes the founder, runs one turn on the universe's assigned writer, and appends the founder/universe text exchange to `principal:<authenticated-subject>`. There is no voice transport, microphone permission path, or Realtime credential broker today.

OpenAI recommends WebRTC for browser and mobile Realtime clients and supports server-minted ephemeral client secrets, which keep the long-lived API key on the application server ([WebRTC guide](https://developers.openai.com/api/docs/guides/realtime-webrtc)). Realtime sessions are stateful but have a maximum duration of 60 minutes, and WebRTC sessions automatically truncate unplayed output when the user interrupts ([conversation guide](https://developers.openai.com/api/docs/guides/realtime-conversations)). Semantic VAD is designed to reduce premature turn boundaries and exposes configurable eagerness and interruption behavior ([VAD guide](https://developers.openai.com/api/docs/guides/realtime-vad)).

The current generally documented model is `gpt-realtime-2.1`, an update to `gpt-realtime-2` with improved silence/noise handling and interruption behavior ([model page](https://developers.openai.com/api/docs/models/gpt-realtime-2.1)). As checked on 2026-09-03, OpenAI's public Realtime call reference requires `Authorization: Bearer $OPENAI_API_KEY`, while the API overview documents API keys or workload-identity access tokens as API credentials ([Realtime reference](https://platform.openai.com/docs/api-reference/realtime), [API overview](https://developers.openai.com/api/reference/overview)). The public documentation does not identify a ChatGPT/Codex subscription session as Realtime API authority. Treating the existing subscription token as such would therefore be an unsupported inference. API data is not used for training by default, but abuse-monitoring logs may be retained for up to 30 days unless a different eligible data-control arrangement applies ([data controls](https://developers.openai.com/api/docs/guides/your-data)).

These constraints create one governing boundary: the universe may use only capabilities its user has bound to it. TinyAssets must remain a relay whose primary writer is the universe's assigned engine. A compatible user-owned voice resource may supply speech transport, but a platform/maintainer credential or another user's resource never may. Jonathan's existing Codex subscription continues to power his writer; because no documented Realtime-audio route exists through that authority, this change does not ask him for a separate key or spend ceiling merely to complete voice work. The mobile release work on `codex/ios-store-release` owns signing and store submission; this change owns the shared voice contract and will hand native permission/privacy requirements to that track.

## Goals / Non-Goals

**Goals:**

- Provide a first-class, foreground voice conversation mode with semantic turn-taking, visible states, barge-in, deterministic recovery, and a continuous canonical text history.
- Keep `converse` as the sole primary writer and preserve its authorization, sandbox, assigned-engine, and transcript behavior.
- Reuse only a compatible voice resource already bound to the authenticated universe; keep any long-lived credential server-side and return only short-lived client authority.
- Show Voice as locked before microphone capture when the universe lacks such a resource, with no platform-key, ambient-key, or cross-user fallback.
- Make the first implementation slice testable without a microphone, paid API call, network access, deployment, or store submission.

**Non-Goals:**

- Background listening, wake words, phone-call integration, audio recording, audio-history playback, or raw-audio persistence.
- A new public MCP handle, a new conversation store, or a second Realtime-authored universe persona.
- Platform-funded voice, bundled API credits, automatic billing, or silently converting subscription users to API usage.
- Shipping, signing, publishing, enabling production traffic, or changing the existing app-store branch's release artifacts in this slice.
- Perfect continuation of an interrupted waveform or hidden automatic replay of an ambiguously delivered user turn.

## Decisions

### 1. Realtime is the media and turn-taking plane; `converse` remains the author

The Realtime session SHALL expose one narrow client-executed function tool, `converse(message)`, and require that tool for a committed speech turn. The client executes the function by calling its existing authenticated `MCP.converse(message)` path. The exact returned universe text is appended and rendered by the existing canonical conversation flow, then supplied back to Realtime for speech rendering. The visible assistant bubble is always the canonical `converse` result, never a Realtime-generated transcript.

The session instructions and tool choice will prohibit a free-standing Realtime answer. Output-audio transcript events will be compared with normalized canonical text for observability; a mismatch marks the spoken rendering as non-canonical without overwriting stored text. A mismatch emits the existing identity-scoped `/mcp/app/trace` event `voice_output_mismatch` with counts and state only—never either text body, audio, a credential, or tool arguments—so operators have a bounded structured signal rather than an unspecified log sink. This is a guardrail, not a mathematical guarantee that a generative voice renderer will pronounce every character identically.

Alternatives rejected:

- Making Realtime the primary writer would bypass the assigned engine and turn a voice preference into a provider/billing change.
- Giving OpenAI the remote TinyAssets MCP endpoint would expand the third-party authority surface and place user OAuth material outside the client/server boundary.
- Browser speech recognition/synthesis would avoid API billing but would not deliver a consistent cross-platform Realtime experience.

### 2. The client uses WebRTC and a server-minted ephemeral secret

The app first requests the read-only `GET /mcp/app/voice/status` with its existing authenticated session. The server derives the founder home universe and returns only `ready`, `locked`, or `disabled` capability metadata. The client does not show the capture disclosure or request microphone access unless status is `ready`.

For the initial OpenAI adapter, a ready app requests `POST /mcp/app/voice/session`. Neither route accepts a caller-selected universe id: the server resolves the same founder home universe used by `converse`. The server validates both host-side adapter gates, resolves only that universe owner's deposited OpenAI API credential, calls OpenAI's `/v1/realtime/client_secrets` endpoint without an OpenAI SDK, and returns the short-lived secret plus non-secret expiry/model metadata. Responses use `Cache-Control: no-store`; secrets and Authorization headers are excluded from logs and errors.

The client sends the SDP directly to OpenAI over WebRTC. The app Content Security Policy gains only the minimum OpenAI connection origin while voice is enabled. Microphone tracks are stopped on leave, error, page hide, sign-out, and unload.

The unified server SDP proxy was rejected because it puts TinyAssets on the media-session setup path and increases bandwidth and uptime responsibility. A long-lived key in JavaScript was rejected because it violates credential custody.

### 3. Universe-bound capability, not a host credential, authorizes voice

`TINYASSETS_REALTIME_VOICE_ENABLED` controls whether the UI adapter is available, and `TINYASSETS_ALLOW_REALTIME_VOICE_API` is a defense-in-depth host kill switch for the initial OpenAI API adapter. Both default false and both must be true. Neither flag is user spend authority, enables API-key primary writers, weakens `TINYASSETS_ALLOW_API_KEY_PROVIDERS`, or makes a platform credential eligible.

The broker uses only a compatible resource deposited under the requesting universe owner's contract. The initial adapter recognizes a deposited per-universe OpenAI API credential. It SHALL NOT reinterpret the existing Codex subscription session as Realtime authority, read a process-global `OPENAI_API_KEY`, use a platform credential, or fall back to another universe's resource. Missing flags or compatible resources fail before any OpenAI request. The app presents the latter as a locked capability, not as a demand that Jonathan supply a new key.

This dedicated kill switch was chosen over reusing `TINYASSETS_ALLOW_API_KEY_PROVIDERS` because voice transport is not a routing candidate. Capability authority comes from the universe binding, so a subscription-only writer stays intact whether Voice is ready, locked, or later backed by a different user-owned adapter.

### 4. The default session is bounded and interruption-first

The broker pins an allowlisted model (initially `gpt-realtime-2.1`) and server-owned session instructions; the browser cannot select an arbitrary model or tool. Input uses semantic VAD with `interrupt_response=true`, a medium eagerness default, and automatic response creation. Tool choice is restricted to `converse`. A local session timer stops the microphone before the provider's 60-minute maximum; the first slice uses a 30-minute cap and warns at 25 minutes. Reconnection always mints a new secret and is bounded to three attempts with jittered backoff.

The client state machine is:

`unavailable -> idle -> requesting_permission -> connecting -> listening -> thinking -> speaking`, with transitions from active states to `reconnecting`, `error`, or `idle`. A `speech_started` event while speaking moves immediately to `listening`; unplayed audio is discarded. Every state has a visible label and an `aria-live` announcement, while the microphone toggle remains keyboard operable.

### 5. Text history is durable; audio-session state is disposable

Each accepted tool call invokes `MCP.converse` exactly once. Its founder message and returned universe reply are the canonical durable history and appear in the same thread as typed turns. Raw audio, provider audio events, partial transcripts, ephemeral secrets, and peer-connection diagnostics are not persisted in conversation history.

If the media connection drops while `MCP.converse` is in flight, that request is allowed to finish and its result is shown in text; the app does not resubmit it. If delivery outcome is unknown, the user sees an explicit retry action instead of automatic replay. After reconnect, the app reloads canonical text history but does not replay prior audio or automatically read the last reply.

### 6. Disclosure and usage visibility precede capture

Before the first microphone permission request for a browser profile, the app confirms that the universe still has a compatible bound resource, then discloses the exact provider path, that any provider use belongs to that resource's account, that TinyAssets never substitutes shared credentials, that TinyAssets stores only the canonical text exchange, and that provider retention controls apply. Acceptance is stored locally as a disclosure version; it is not authority to spend, and capability is checked again on each start.

Realtime cost grows with both audio tokens and repeated conversation context ([cost guide](https://developers.openai.com/api/docs/guides/realtime-costs)). The UI may show provider-reported session usage as an estimate, clearly labeled non-billing-authoritative. No usage event may contain transcript text or raw audio.

### 7. Native shells remain thin and foreground-only

The shared web app owns the voice UI and protocol. The iOS and Android projects only add the microphone permission declarations and any required WebView media-capture behavior. Store metadata must disclose audio sent to OpenAI and canonical text stored by TinyAssets. The app-store track receives these requirements before it changes signing or submission materials; this branch does not edit its release-owned files without coordination.

## Risks / Trade-offs

- [Spoken output can paraphrase punctuation or wording despite strict instructions] -> Keep displayed/stored text canonical, compare output transcripts, emit mismatch telemetry without content, and user-test before rollout. If unacceptable, replace only the speech-rendering adapter with deterministic TTS.
- [Direct WebRTC hides authoritative provider cost from the server] -> Show client-observed usage only as an estimate, cap sessions locally, rate-limit secret minting, and require user-owned billing. Do not promise a hard monetary ceiling in the first slice.
- [An ephemeral secret is still a temporary bearer credential] -> Authenticate the broker, scope session configuration server-side, return no-store responses, redact it everywhere, and use the shortest provider-supported expiry.
- [Barge-in can leave durable text that was not fully heard] -> Preserve the full canonical reply in history while truncating only playback; label the transcript as the source of record.
- [Reconnect can duplicate a costly/writing turn] -> Never automatically replay an in-flight or ambiguous `converse` request; require explicit retry.
- [Browser and WebView microphone behavior differs] -> Isolate browser APIs behind an adapter and require deterministic mocks plus one observed browser and one real-device pass before enabling production.
- [CSP or WebView changes can affect the public app] -> Keep the feature off by default, add only the required origin, run focused security tests, the public MCP canary, and a rendered chatbot conversation before rollout.
- [A user may believe their ChatGPT/Codex subscription authorizes Realtime API voice] -> State that the current public API documentation does not expose that route; keep Voice locked unless a compatible user-owned resource is actually bound.

## Migration Plan

1. Land the spec-reviewed broker policy, client state machine, and deterministic tests with both flags off. No live credential or network call is needed for verification.
2. Add native microphone permissions and store disclosures in coordination with `codex/ios-store-release`; keep release channels unchanged.
3. In a non-production owner-controlled environment that already has a compatible user-bound voice resource, enable both adapter gates and run a short browser/device session under that resource's own limits. Do not solicit a separate key or budget merely for this rollout step.
4. Verify turn-taking, interruption, canonical-history continuity, auth isolation, CSP, public canary, and rendered chatbot behavior. Record dated environment and commands.
5. Enable for a small explicit cohort with a kill switch, bounded session duration, failure/latency/usage monitoring, and rollback by disabling either flag.
6. Roll back by turning off `TINYASSETS_REALTIME_VOICE_ENABLED`; existing text conversation and stored history remain usable because no data migration occurs.

## Open Questions

- Product/API watch: does OpenAI later document Realtime audio through the existing ChatGPT/Codex subscription-authenticated route? If so, add that as a compatible per-universe adapter after review; until then it is unavailable, not emulated with a shared key.
- Capability adapters: which user-bound local speech or other provider subscription resources can satisfy the voice contract without weakening canonical `converse` authorship?
- Product validation: is generative spoken rendering faithful enough when canonical text is displayed, or must the output adapter change to deterministic TTS before rollout?
- Rollout policy: what initial per-session duration and user-visible spend warning should production use after measured device tests?
- Store review: which final Apple/Google privacy labels and wording are required for the exact shipped SDK-free WebRTC data path?
