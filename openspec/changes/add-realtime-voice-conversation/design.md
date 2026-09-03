## Context

The shared app at `/mcp/app` is one HTML/JavaScript client used by the browser and the Capacitor Android/iOS shells. Its text composer already calls the canonical `converse` MCP handle, which authorizes the founder, runs one turn on the universe's assigned writer, and appends the founder/universe text exchange to `principal:<authenticated-subject>`. There is no voice transport, microphone permission path, or Realtime credential broker today.

OpenAI recommends WebRTC for browser and mobile Realtime clients and supports server-minted ephemeral client secrets, which keep the long-lived API key on the application server ([WebRTC guide](https://developers.openai.com/api/docs/guides/realtime-webrtc)). Realtime sessions are stateful but have a maximum duration of 60 minutes, and WebRTC sessions automatically truncate unplayed output when the user interrupts ([conversation guide](https://developers.openai.com/api/docs/guides/realtime-conversations)). Semantic VAD is designed to reduce premature turn boundaries and exposes configurable eagerness and interruption behavior ([VAD guide](https://developers.openai.com/api/docs/guides/realtime-vad)).

The current generally documented model is `gpt-realtime-2.1`, an update to `gpt-realtime-2` with improved silence/noise handling and interruption behavior ([model page](https://developers.openai.com/api/docs/models/gpt-realtime-2.1)). It is API-metered compute and is not covered by a ChatGPT or Codex subscription. API data is not used for training by default, but abuse-monitoring logs may be retained for up to 30 days unless a different eligible data-control arrangement applies ([data controls](https://developers.openai.com/api/docs/guides/your-data)).

These constraints create two authority boundaries. TinyAssets must remain a relay whose primary writer is the universe's assigned subscription/owner-provided engine, and Realtime spend must be explicitly authorized against the user's own API credential. The mobile release work on `codex/ios-store-release` owns signing and store submission; this change owns the shared voice contract and will hand native permission/privacy requirements to that track.

## Goals / Non-Goals

**Goals:**

- Provide a first-class, foreground voice conversation mode with semantic turn-taking, visible states, barge-in, deterministic recovery, and a continuous canonical text history.
- Keep `converse` as the sole primary writer and preserve its authorization, sandbox, assigned-engine, and transcript behavior.
- Keep long-lived API credentials server-side and return only short-lived Realtime client credentials to an authenticated owner.
- Make metered API use a separate, explicit, off-by-default choice with no platform-key or ambient-key fallback.
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

The app requests `POST /mcp/app/voice/session` with its existing authenticated session. The request has no caller-selected universe id in the first slice: the server resolves the same founder home universe used by `converse`. The server validates both voice flags, resolves only that universe owner's deposited OpenAI credential, calls OpenAI's `/v1/realtime/client_secrets` endpoint without an OpenAI SDK, and returns the short-lived secret plus non-secret expiry/model metadata. Responses use `Cache-Control: no-store`; secrets and Authorization headers are excluded from logs and errors.

The client sends the SDP directly to OpenAI over WebRTC. The app Content Security Policy gains only the minimum OpenAI connection origin while voice is enabled. Microphone tracks are stopped on leave, error, page hide, sign-out, and unload.

The unified server SDP proxy was rejected because it puts TinyAssets on the media-session setup path and increases bandwidth and uptime responsibility. A long-lived key in JavaScript was rejected because it violates credential custody.

### 3. Voice has a dedicated, additive allowance

`TINYASSETS_REALTIME_VOICE_ENABLED` controls whether the UI and broker are available, and `TINYASSETS_ALLOW_REALTIME_VOICE_API` separately authorizes metered Realtime API use. Both default false and both must be true. The latter does not enable API-key primary writers and does not weaken `TINYASSETS_ALLOW_API_KEY_PROVIDERS`.

The broker uses only a per-universe credential deposited under the custody owner's contract. It SHALL NOT read a process-global `OPENAI_API_KEY`, use a platform credential, or fall back to another universe's credential. Missing flags or credentials fail before any OpenAI request with a typed, user-actionable response.

This dedicated gate was chosen over reusing `TINYASSETS_ALLOW_API_KEY_PROVIDERS` because voice transport is not a routing candidate and users must be able to retain a subscription-only writer while separately deciding whether to pay for audio transport.

### 4. The default session is bounded and interruption-first

The broker pins an allowlisted model (initially `gpt-realtime-2.1`) and server-owned session instructions; the browser cannot select an arbitrary model or tool. Input uses semantic VAD with `interrupt_response=true`, a medium eagerness default, and automatic response creation. Tool choice is restricted to `converse`. A local session timer stops the microphone before the provider's 60-minute maximum; the first slice uses a 30-minute cap and warns at 25 minutes. Reconnection always mints a new secret and is bounded to three attempts with jittered backoff.

The client state machine is:

`unavailable -> idle -> requesting_permission -> connecting -> listening -> thinking -> speaking`, with transitions from active states to `reconnecting`, `error`, or `idle`. A `speech_started` event while speaking moves immediately to `listening`; unplayed audio is discarded. Every state has a visible label and an `aria-live` announcement, while the microphone toggle remains keyboard operable.

### 5. Text history is durable; audio-session state is disposable

Each accepted tool call invokes `MCP.converse` exactly once. Its founder message and returned universe reply are the canonical durable history and appear in the same thread as typed turns. Raw audio, provider audio events, partial transcripts, ephemeral secrets, and peer-connection diagnostics are not persisted in conversation history.

If the media connection drops while `MCP.converse` is in flight, that request is allowed to finish and its result is shown in text; the app does not resubmit it. If delivery outcome is unknown, the user sees an explicit retry action instead of automatic replay. After reconnect, the app reloads canonical text history but does not replay prior audio or automatically read the last reply.

### 6. Disclosure and usage visibility precede capture

Before the first microphone permission request for a browser profile, the app discloses that audio is sent directly to OpenAI, TinyAssets stores only the canonical text exchange, OpenAI API charges apply to the user's credential, and provider retention controls apply. Acceptance is stored locally as a disclosure version, not as authority to spend; the two server-side flags and credential remain mandatory.

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
- [A user may believe their ChatGPT/Codex subscription covers voice] -> State explicitly in setup and first-use disclosure that Realtime API billing is separate.

## Migration Plan

1. Land the spec-reviewed broker policy, client state machine, and deterministic tests with both flags off. No live credential or network call is needed for verification.
2. Add native microphone permissions and store disclosures in coordination with `codex/ios-store-release`; keep release channels unchanged.
3. In a non-production owner-controlled environment, deposit a user-owned OpenAI key, enable both flags, and run a short metered browser/device session with a pre-agreed spend ceiling.
4. Verify turn-taking, interruption, canonical-history continuity, auth isolation, CSP, public canary, and rendered chatbot behavior. Record dated environment and commands.
5. Enable for a small explicit cohort with a kill switch, bounded session duration, failure/latency/usage monitoring, and rollback by disabling either flag.
6. Roll back by turning off `TINYASSETS_REALTIME_VOICE_ENABLED`; existing text conversation and stored history remain usable because no data migration occurs.

## Open Questions

- Founder decision: approve user-owned per-universe OpenAI API credentials as the only initial funding model, or intentionally change `PLAN.md` and billing architecture for platform-funded voice. The design recommends user-owned only.
- Product validation: is generative spoken rendering faithful enough when canonical text is displayed, or must the output adapter change to deterministic TTS before rollout?
- Rollout policy: what initial per-session duration and user-visible spend warning should production use after measured device tests?
- Store review: which final Apple/Google privacy labels and wording are required for the exact shipped SDK-free WebRTC data path?
