## Why

TinyAssets conversations are text-only today, which prevents natural hands-free use and makes the mobile shells feel like web wrappers rather than first-class conversational clients. OpenAI's Realtime API can provide low-latency speech input, semantic turn detection, interruption, and speech output, but it is separately metered API compute and must not silently make TinyAssets the model provider or create a second author for the universe.

## What Changes

- Add an authenticated, explicitly enabled voice mode to the shared TinyAssets app surface so the web app and Capacitor mobile shells can support listening, thinking, speaking, interruption, reconnection, and accessible visible status.
- Use browser/mobile WebRTC with a short-lived Realtime client credential minted by the TinyAssets server. The server may mint that credential only from the authenticated owner's per-universe OpenAI API credential and a voice-specific opt-in; it never exposes the long-lived key, falls back to an ambient host key, or spends platform-owned compute.
- Keep the existing assigned-engine `converse` turn as the sole primary writer. Realtime acts as a speech transport and function-call relay: a committed user utterance invokes the existing `converse` path, and the returned universe reply is spoken without replacement by a second model-authored answer.
- Persist the same canonical text exchange already used across app and connector surfaces. Do not persist raw microphone audio. Show a first-use disclosure that audio is sent directly to OpenAI and that OpenAI API retention policies apply.
- Define deterministic interruption, ambiguous-delivery, reconnect, session-expiry, permission-denial, and failure behavior. The first release is foreground-only and does not claim to resume an interrupted audio stream.
- Coordinate later native microphone permission strings and App Store / Play privacy disclosures with the existing mobile release track without taking ownership of signing, enrollment, release metadata, or store publication.
- Land the first reversible slice behind an off-by-default feature flag: the authenticated session policy boundary, client state machine, and deterministic mocks/tests. No deployment, publication, paid API call, or store submission is part of this change.

## Capabilities

### New Capabilities

- `realtime-voice-conversation`: Defines the app voice-session lifecycle, WebRTC media path, semantic turn-taking and barge-in, relay tool contract, reconnect behavior, privacy/cost disclosures, accessibility states, and native-shell requirements.

### Modified Capabilities

- `universe-personification-and-relay`: Requires voice turns to use the existing `converse` writer and to speak that canonical reply rather than independently authoring one.
- `credential-vault`: Allows a voice-session broker to read only the authenticated owner's deposited OpenAI credential under an explicit voice allowance, returning only a short-lived client credential.
- `identity-auth-and-access-control`: Requires the voice-session broker to be authenticated and scoped to the requesting owner and universe.
- `provider-routing`: Distinguishes metered voice transport from the assigned primary writer while preserving the subscription-first, user-owned-compute boundary and prohibiting silent provider fallback.

## Impact

- Shared app: `tinyassets/onboarding/app.html` and its existing deterministic browser harness.
- Server: a small authenticated voice-session policy/broker boundary and route under the app surface; no new public MCP tool handle.
- Credentials and configuration: per-universe OpenAI credential lookup plus a new voice-specific, off-by-default environment allowance; no schema migration.
- Conversation storage: existing canonical `principal:<subject>` text history only; raw audio remains outside TinyAssets persistence.
- Mobile release track: a documented handoff for iOS and Android microphone permissions, privacy labels, foreground behavior, and store review copy. Signing, enrollment, screenshots, publication, and spend remain out of scope.
- Operations: later staged rollout, usage/cost telemetry, kill switch, and rollback evidence are required before enabling the flag in production.
