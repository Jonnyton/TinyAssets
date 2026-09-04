## Context

The shared app at `/mcp/app` is one HTML/JavaScript client used by the browser and the Capacitor Android/iOS shells. Its text composer already calls the canonical `converse` MCP handle, which authorizes the founder, runs one turn on the universe's assigned writer, and appends the founder/universe text exchange to `principal:<authenticated-subject>`. There is no voice transport, microphone permission path, or Realtime credential broker today.

OpenAI recommends WebRTC for browser and mobile Realtime clients and supports server-minted ephemeral client secrets, which keep the long-lived API key on the application server ([WebRTC guide](https://developers.openai.com/api/docs/guides/realtime-webrtc)). Realtime sessions are stateful but have a maximum duration of 60 minutes, and WebRTC sessions automatically truncate unplayed output when the user interrupts ([conversation guide](https://developers.openai.com/api/docs/guides/realtime-conversations)). Semantic VAD is designed to reduce premature turn boundaries and exposes configurable eagerness and interruption behavior ([VAD guide](https://developers.openai.com/api/docs/guides/realtime-vad)).

The initial research used OpenAI Realtime to validate that WebRTC, short-lived media credentials, semantic turn detection, and interruption can form a good implementation. After this branch began, the founder's 2026-09-03 channel-agnostic rule landed on `main`: provider-specific paths may not be added to the user substrate. The implementation therefore exposes a provider-neutral bridge contract. An owner may run or choose any bridge that implements it, including one backed by a local resource. Provider-specific endpoint, model, authentication, retention, and event translation stay behind that owner-controlled bridge.

These constraints create one governing boundary: the universe may use only capabilities its user has bound to it. TinyAssets must remain a relay whose primary writer is the universe's assigned engine. A compatible user-owned voice resource may supply speech transport, but a platform/maintainer credential or another user's resource never may. Jonathan's existing Codex subscription continues to power his writer; because no documented Realtime-audio route exists through that authority, this change does not ask him for a separate key or spend ceiling merely to complete voice work. The mobile release work on `codex/ios-store-release` owns signing and store submission; this change owns the shared voice contract and will hand native permission/privacy requirements to that track.

## Goals / Non-Goals

**Goals:**

- Provide a first-class, foreground voice conversation mode with semantic turn-taking, visible states, barge-in, deterministic recovery, and a continuous canonical text history.
- Keep `converse` as the sole primary writer and preserve its authorization, sandbox, assigned-engine, and transcript behavior.
- Reuse only a compatible voice bridge already bound through the authenticated universe's generic HTTP connection and grant; keep all HTTP credential material inside the credential-blind broker and return only the bridge's bounded SDP answer.
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
- Giving a voice service the remote TinyAssets MCP endpoint would expand the third-party authority surface and place user OAuth material outside the client/server boundary.
- Browser speech recognition/synthesis would avoid API billing but would not deliver a consistent cross-platform Realtime experience.

### 2. The client uses WebRTC and a provider-neutral session bridge

The app first requests the read-only `GET /mcp/app/voice/status` with its existing authenticated session. The server derives the founder home universe and returns only `ready`, `locked`, or `disabled` capability metadata. The client does not show the capture disclosure or request microphone access unless status is `ready`.

For a ready universe, the app creates a bounded WebRTC SDP offer and submits it to `POST /mcp/app/voice/session`. Neither route accepts a caller-selected universe id: the server resolves the same founder home universe used by `converse`. A bounded, non-symlinked `voice-connection.json` file references an existing connection id, grant id, HTTPS session URL, service label, and optional privacy URL. It contains no secret. The server revalidates the grant, connection, owner, universe, revocation state, HTTP type, POST scope, and endpoint allowlist, then calls the session URL through the existing credential-blind outbound proxy. The bridge receives the fixed `tinyassets.voice.v1` policy plus the SDP offer and returns only protocol version, a bounded SDP answer, expiry, and bounded session duration. Responses use `Cache-Control: no-store`; secrets and Authorization headers are excluded from logs and errors.

The browser receives the SDP answer from its same-origin TinyAssets route and applies it to the peer connection. No remote HTTP URL, long-lived credential, or temporary bearer reaches JavaScript, and the app Content Security Policy does not gain a general remote fetch origin. WebRTC media follows the user-selected bridge's SDP while microphone tracks are stopped on leave, error, page hide, sign-out, and unload.

Keeping the server on the bounded signaling path was accepted because it reuses the existing authenticated and credential-blind boundary without putting TinyAssets on the media stream itself. A remote client-side signaling fetch was rejected because a provider-neutral endpoint would require a broad Content Security Policy and expose temporary bearer material to JavaScript. A long-lived key in JavaScript remains prohibited.

### 3. Universe-bound capability, not a host credential, authorizes voice

`TINYASSETS_REALTIME_VOICE_ENABLED` controls whether the UI is available, `TINYASSETS_ALLOW_REALTIME_VOICE_API` is a defense-in-depth session-exchange switch, and `TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED` is the existing generic egress switch. All default false and all must be true. No flag is user spend authority, enables API-key primary writers, weakens `TINYASSETS_ALLOW_API_KEY_PROVIDERS`, or makes a platform credential eligible.

The broker uses only the exact active connection grant named by the requesting universe's binding. Credential resolution and header application remain inside the existing spawned broker worker; voice code never receives either. It SHALL NOT read any process-global service credential, use a platform connection, or fall back to another universe's resource. Missing flags, manifest, connection, grant, owner match, or scope fail before microphone capture and before any network request. The app presents this as a locked capability, not as a demand that Jonathan supply a new key.

The dedicated switch is separate from `TINYASSETS_ALLOW_API_KEY_PROVIDERS` because voice transport is not a routing candidate. Capability authority comes from the universe binding, so a subscription-only writer stays intact whether Voice is ready, locked, or later backed by any user-owned bridge.

### 4. The default session is bounded and interruption-first

The broker pins a versioned bridge protocol and server-owned session instructions; the browser cannot select an arbitrary model or tool. The protocol requests semantic turn detection with medium eagerness and interruption. Tool choice is restricted to `converse`, and output must cite the tool result as its verbatim source. The first slice imposes its own 30-minute maximum regardless of a bridge's larger value and warns at 25 minutes. Reconnection always performs a new authenticated SDP exchange and is bounded to three attempts with jittered backoff.

The client state machine is:

`unavailable -> idle -> requesting_permission -> connecting -> listening -> thinking -> speaking`, with transitions from active states to `reconnecting`, `error`, or `idle`. A `speech_started` event while speaking moves immediately to `listening`; unplayed audio is discarded. Every state has a visible label and an `aria-live` announcement, while the microphone toggle remains keyboard operable.

### 5. Text history is durable; audio-session state is disposable

Each accepted tool call invokes `MCP.converse` exactly once. Its founder message and returned universe reply are the canonical durable history and appear in the same thread as typed turns. Raw audio, bridge audio events, partial transcripts, SDP, and peer-connection diagnostics are not persisted in conversation history.

If the media connection drops while `MCP.converse` is in flight, that request is allowed to finish and its result is shown in text; the app does not resubmit it. If delivery outcome is unknown, the user sees an explicit retry action instead of automatic replay. After reconnect, the app reloads canonical text history but does not replay prior audio or automatically read the last reply.

### 6. Disclosure and usage visibility precede capture

Before the first microphone permission request for a browser profile, the app confirms that the universe still has a compatible bound resource, then names the bound service, explains that any service use belongs to that resource's account, states that TinyAssets never substitutes shared credentials and stores only the canonical text exchange, and links the service's privacy terms when the binding supplies a validated HTTPS URL. Acceptance is stored locally as a disclosure version; it is not authority to spend, and capability is checked again on each start.

Service cost and accounting vary by the bridge the owner chose. The UI may later show bridge-reported session usage as an estimate, clearly labeled non-billing-authoritative. No usage event may contain transcript text or raw audio.

### 7. Native shells remain thin and foreground-only

The shared web app owns the voice UI and protocol. The iOS and Android projects only add the microphone permission declarations and any required WebView media-capture behavior. Store metadata must disclose that audio is sent to the user-selected voice service and canonical text is stored by TinyAssets. The app-store track receives these requirements before it changes signing or submission materials; this branch does not edit its release-owned files without coordination.

## Risks / Trade-offs

- [Spoken output can paraphrase punctuation or wording despite strict instructions] -> Keep displayed/stored text canonical, compare output transcripts, emit mismatch telemetry without content, and user-test before rollout. If unacceptable, replace only the speech-rendering adapter with deterministic TTS.
- [Direct WebRTC hides authoritative service cost from the server] -> Show client-observed usage only as an estimate, cap sessions locally, rate-limit session creation, and require user-owned billing. Do not promise a hard monetary ceiling in the first slice.
- [A bridge could return malicious or oversized signaling data] -> Require the exact protocol version, bound SDP size, valid SDP prefix, no NUL bytes, response-field reduction, and `no-store`; never return the bridge's raw response object.
- [Barge-in can leave durable text that was not fully heard] -> Preserve the full canonical reply in history while truncating only playback; label the transcript as the source of record.
- [Reconnect can duplicate a costly/writing turn] -> Never automatically replay an in-flight or ambiguous `converse` request; require explicit retry.
- [Browser and WebView microphone behavior differs] -> Isolate browser APIs behind an adapter and require deterministic mocks plus one observed browser and one real-device pass before enabling production.
- [CSP or WebView changes can affect the public app] -> Keep the feature off by default, add only the required origin, run focused security tests, the public MCP canary, and a rendered chatbot conversation before rollout.
- [A user may believe their ChatGPT/Codex subscription authorizes Realtime API voice] -> State that the current public API documentation does not expose that route; keep Voice locked unless a compatible user-owned resource is actually bound.

## Migration Plan

1. Land the spec-reviewed broker policy, client state machine, and deterministic tests with all three flags off. No live credential or network call is needed for verification.
2. Add native microphone permissions and store disclosures in coordination with `codex/ios-store-release`; keep release channels unchanged.
3. In a non-production owner-controlled environment that already has a compatible user-bound voice bridge, enable all three gates and run a short browser/device session under that resource's own limits. Do not solicit a separate key or budget merely for this rollout step.
4. Verify turn-taking, interruption, canonical-history continuity, auth isolation, CSP, public canary, and rendered chatbot behavior. Record dated environment and commands.
5. Enable for a small explicit cohort with a kill switch, bounded session duration, failure/latency/usage monitoring, and rollback by disabling either flag.
6. Roll back by turning off `TINYASSETS_REALTIME_VOICE_ENABLED`; existing text conversation and stored history remain usable because no data migration occurs.

## Open Questions

- Bridge ecosystem: which owner-run local speech and remote services should publish reference bridges without adding provider-specific code to the platform substrate?
- Product validation: is generative spoken rendering faithful enough when canonical text is displayed, or must the output adapter change to deterministic TTS before rollout?
- Rollout policy: what initial per-session duration and user-visible spend warning should production use after measured device tests?
- Store review: which final Apple/Google privacy labels and wording are required for the exact shipped SDK-free WebRTC data path?
