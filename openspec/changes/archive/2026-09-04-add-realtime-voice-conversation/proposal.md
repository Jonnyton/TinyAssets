## Why

TinyAssets conversations are text-only today, which prevents natural hands-free use and makes the mobile shells feel like web wrappers rather than first-class conversational clients. Low-latency speech needs media transport, turn detection, interruption, and speech output, but no particular provider or credential may become a platform assumption. Voice must therefore be capability-gated per universe and must not silently make TinyAssets the provider, payer, or second author.

## What Changes

- Add an authenticated, explicitly enabled voice mode to the shared TinyAssets app surface so the web app and Capacitor mobile shells can support listening, thinking, speaking, interruption, reconnection, and accessible visible status.
- Reuse a compatible voice resource already bound to the authenticated universe. The platform speaks a provider-neutral `tinyassets.voice.v1` bridge contract over the existing credential-blind HTTP connection and grant; service-specific endpoints, models, credentials, and event translation live behind the user's bridge rather than in TinyAssets.
- Report capability readiness before requesting microphone access. A universe without a compatible user-owned subscription, credential, or local resource sees Voice as locked with an honest unlock explanation; typed conversation remains available and no provider or microphone request occurs.
- Keep the existing assigned-engine `converse` turn as the sole primary writer. Realtime acts as a speech transport and function-call relay: a committed user utterance invokes the existing `converse` path, and the returned universe reply is spoken without replacement by a second model-authored answer.
- Persist the same canonical text exchange already used across app and connector surfaces. Do not persist raw microphone audio. Show a first-use disclosure naming the bound voice service, its privacy link when supplied, and that audio is sent directly to that service.
- Define deterministic interruption, ambiguous-delivery, reconnect, session-expiry, permission-denial, and failure behavior. The first release is foreground-only and does not claim to resume an interrupted audio stream.
- Coordinate later native microphone permission strings and App Store / Play privacy disclosures with the existing mobile release track without taking ownership of signing, enrollment, release metadata, or store publication.
- Land the first reversible slice behind an off-by-default feature flag: the authenticated session policy boundary, client state machine, and deterministic mocks/tests. No deployment, publication, paid API call, or store submission is part of this change.

## Capabilities

### New Capabilities

- `realtime-voice-conversation`: Defines the app voice-session lifecycle, WebRTC media path, semantic turn-taking and barge-in, relay tool contract, reconnect behavior, privacy/cost disclosures, accessibility states, and native-shell requirements.

### Modified Capabilities

- `universe-personification-and-relay`: Requires voice turns to use the existing `converse` writer and to speak that canonical reply rather than independently authoring one.
- `credential-vault`: Requires the voice-session broker to reuse the existing credential-blind connection boundary; neither the route nor voice code may resolve or receive the long-lived credential.
- `identity-auth-and-access-control`: Requires the voice-session broker to be authenticated and scoped to the requesting owner and universe.
- `provider-routing`: Distinguishes metered voice transport from the assigned primary writer while preserving the subscription-first, user-owned-compute boundary and prohibiting silent provider fallback.

## Impact

- Shared app: `tinyassets/onboarding/app.html` and its existing deterministic browser harness.
- Server: a small authenticated voice-session policy/broker boundary and route under the app surface; no new public MCP tool handle.
- Credentials and configuration: a per-universe `voice-connection.json` binding references an existing generic HTTP connection/grant, plus off-by-default adapter and outbound kill switches; no secret or provider identifier is stored in the binding.
- Conversation storage: existing canonical `principal:<subject>` text history only; raw audio remains outside TinyAssets persistence.
- Mobile release track: a documented handoff for iOS and Android microphone permissions, privacy labels, foreground behavior, and store review copy. Signing, enrollment, screenshots, publication, and spend remain out of scope.
- Operations: later staged rollout, usage/cost telemetry, kill switch, and rollback evidence are required before enabling the flag in production.
