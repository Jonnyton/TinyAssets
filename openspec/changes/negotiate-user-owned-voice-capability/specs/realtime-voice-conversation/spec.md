## MODIFIED Requirements

### Requirement: Voice mode is explicit, foreground-only, and accessible
The shared TinyAssets app SHALL expose one Voice control beside the message composer, SHALL start immediately from that control when the authenticated universe's current provider has a compatible user-authorized capability, SHALL reuse the existing provider connection/request path otherwise, SHALL require an explicit user start action, and SHALL stop every microphone track when the user leaves voice mode, hides or unloads the app, signs out, or reaches an unrecoverable error.

#### Scenario: Voice is unavailable by default
- **WHEN** any required voice or outbound allowance is disabled
- **THEN** the app does not start microphone capture or request a voice session
- **AND** it presents a concise unavailable reason without disabling typed conversation

#### Scenario: Current provider is Voice-ready
- **WHEN** the signed-in founder taps the composer Voice control and the current provider exposes an authorized `tinyassets.voice.v1` capability
- **THEN** the app proceeds directly to the current disclosure when required and otherwise starts Voice immediately
- **AND** it does not show a provider picker or credential setup flow

#### Scenario: Universe is not powered
- **WHEN** the founder taps Voice and no provider currently serves the universe
- **THEN** the app opens or focuses the existing unpowered-universe provider request
- **AND** it makes no microphone request, bridge request, or Voice-specific credential request

#### Scenario: Current provider cannot supply realtime Voice
- **WHEN** the current provider can power typed conversation but has no compatible realtime capability
- **THEN** the app identifies Voice as unavailable for that provider and keeps typed conversation available
- **AND** it offers the existing user-authorized connection/request path only when status returns `remediation: existing_connection_surface`
- **AND** status returns `remediation: none` otherwise and the app remains unavailable without a separate Voice credential flow
- **AND** the affordance never pre-fills or auto-submits an endpoint extension from capability metadata

#### Scenario: Every active state is perceivable
- **WHEN** voice moves among requesting permission, connecting, listening, thinking, speaking, reconnecting, or error
- **THEN** the app displays the current state and announces it through an accessible live region
- **AND** the start/stop control remains keyboard operable

#### Scenario: Leaving voice stops capture
- **WHEN** the user stops voice, signs out, hides the app, unloads the page, or the periodic authority check loses readiness
- **THEN** all local microphone tracks stop and the client returns to a non-capturing state

#### Scenario: Authority is revoked during an active session
- **GIVEN** Voice is actively capturing
- **WHEN** the capability or grant is revoked, the connection is removed, the provider is rebound, credential custody rotates, the ACL is lost, or the status check fails
- **THEN** the client stops all microphone tracks and closes the peer connection within ten seconds
- **AND** typed conversation remains available

### Requirement: Realtime transport uses WebRTC with a provider-neutral bridge contract
The voice client SHALL use a WebRTC session configured through the versioned `tinyassets.voice.v1` capability declared on the current user-owned provider connection, with semantic voice activity detection, automatic turn creation, and response interruption enabled; it SHALL NOT contain a provider-specific endpoint, model, credential name, or event vocabulary, and SHALL NOT place any long-lived credential in client code or storage.

#### Scenario: Current provider capability starts a media session
- **GIVEN** the authenticated owner's current provider resolves to an active HTTP connection and universe grant with a valid `tinyassets.voice.v1` capability
- **WHEN** the owner starts Voice
- **THEN** the browser sends a bounded SDP offer only to its authenticated same-origin route
- **AND** the server sends its fixed session policy and offer through the credential-blind proxy
- **AND** only a validated, bounded SDP answer and non-secret session metadata return to JavaScript

#### Scenario: Capability or bridge response is malformed
- **WHEN** capability metadata is malformed, cross-owner, cross-universe, revoked, missing `POST` scope, outside the connection allowlist, or the bridge response has the wrong protocol or invalid SDP
- **THEN** Voice fails closed with a secret-free error before sending microphone audio

#### Scenario: User interrupts spoken output
- **WHEN** bridge `speech_started` evidence arrives while the universe reply is playing
- **THEN** unplayed output is cancelled or truncated and the client transitions to listening
- **AND** the complete canonical text reply remains visible in history

#### Scenario: Microphone permission is denied
- **WHEN** the platform rejects microphone permission
- **THEN** the client enters an actionable error state without creating an audio session
- **AND** typed conversation remains available

### Requirement: Audio privacy and resource use are disclosed before capture
The app SHALL confirm capability and then disclose before its first microphone permission request that audio is sent to the service named by the current user-owned connection capability, any service use belongs to that resource, TinyAssets never substitutes shared authority, TinyAssets stores the canonical text exchange but not raw audio, and the service's privacy terms apply. The disclosure SHALL link those terms when the capability supplies a validated HTTPS privacy URL. Its opaque disclosure identity SHALL be derived from the connection id and complete canonical descriptor, including protocol, session URL, service name, and privacy URL.

#### Scenario: First voice start requires current disclosure
- **WHEN** the browser profile has not accepted the current disclosure version and identity for the current connection capability
- **THEN** the app first confirms a compatible resource and presents the disclosure before requesting microphone permission or a voice session
- **AND** declining leaves typed conversation available and sends no audio

#### Scenario: Voice resource or bridge descriptor changes
- **WHEN** a browser profile accepted the disclosure for an earlier connection, protocol, session URL, service name, privacy URL, or disclosure version
- **THEN** the app requires fresh disclosure acceptance before requesting microphone permission or a voice session
- **AND** the server exposes only an opaque, non-secret disclosure identifier rather than a connection credential

#### Scenario: Raw audio is excluded from TinyAssets persistence
- **WHEN** a voice turn completes, is interrupted, or fails
- **THEN** TinyAssets does not write microphone bytes, bridge audio events, or partial audio buffers to conversation history or application logs
