## MODIFIED Requirements

### Requirement: Voice mode is explicit, foreground-only, and accessible
The shared TinyAssets app SHALL expose one Voice control beside the message composer. It SHALL use an authorized current-provider realtime bridge when present, and otherwise SHALL use supported browser/device speech recognition and synthesis around the same canonical `converse` operation when typed conversation works. It SHALL require an explicit user start action and transport-specific disclosure, and SHALL stop recognition, microphone capture, and speech output when the user leaves voice mode, hides or unloads the app, signs out, or reaches an unrecoverable error.

#### Scenario: Realtime bridge transport is unavailable
- **WHEN** generic outbound HTTP transport is disabled
- **THEN** the app does not request a realtime voice session
- **AND** supported browser/device speech may still wrap canonical typed conversation without using outbound HTTP

#### Scenario: Legacy Voice host flags are absent
- **GIVEN** generic outbound HTTP transport is enabled
- **AND** the current provider exposes an authorized `tinyassets.voice.v1` capability
- **WHEN** the Voice-specific legacy host flags are unset or false
- **THEN** the app still reports Voice ready and proceeds directly from the composer control
- **AND** readiness comes only from the user's exact current-provider capability, never platform authority

#### Scenario: Current provider is Voice-ready
- **WHEN** the signed-in founder taps the composer Voice control and the current provider exposes an authorized `tinyassets.voice.v1` capability
- **THEN** the app proceeds directly to the current disclosure when required and otherwise starts Voice immediately
- **AND** it does not show a provider picker or credential setup flow

#### Scenario: Universe is not powered
- **WHEN** the founder taps Voice and no provider currently serves the universe
- **THEN** the app opens or focuses the existing unpowered-universe provider request
- **AND** it makes no microphone request, bridge request, or Voice-specific credential request

#### Scenario: Current provider cannot supply a realtime bridge
- **WHEN** the current provider can power typed conversation but has no compatible realtime capability
- **AND** browser speech recognition and synthesis are available
- **THEN** the Voice control offers browser/device speech around the existing canonical conversation
- **AND** it does not open provider setup, request another credential, switch writers, or call `/voice/session`

#### Scenario: Browser speech input is unavailable
- **WHEN** typed conversation works, no compatible realtime bridge exists, and the browser exposes no supported speech-recognition interface
- **THEN** the app names the browser/device limitation and keeps typed conversation available
- **AND** it does not ask the user to reconnect the provider or imply that their ChatGPT subscription grants external Realtime API access

#### Scenario: Conversation authority status cannot be confirmed
- **WHEN** the authenticated Voice status request fails or times out
- **THEN** the app does not infer that browser speech may bypass the unknown unpowered state
- **AND** it starts no recognition, microphone capture, or provider setup

#### Scenario: Every active state is perceivable
- **WHEN** voice moves among requesting permission, connecting, listening, thinking, speaking, reconnecting, or error
- **THEN** the app displays the current state and announces it through an accessible live region
- **AND** the start/stop control remains keyboard operable

#### Scenario: Leaving voice stops capture
- **WHEN** the user stops voice, signs out, hides the app, unloads the page, or the periodic authority check loses readiness
- **THEN** all local microphone tracks and recognition stop, queued speech synthesis is cancelled, and the client returns to a non-capturing state

#### Scenario: Browser speech synthesis does not settle
- **WHEN** the browser fires neither completion nor error for a requested utterance
- **THEN** the client cancels synthesis after a bounded local deadline and enters an actionable error state
- **AND** the canonical text reply remains visible in history

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
The app SHALL disclose the selected speech transport before its first microphone permission request. For a bridge it SHALL name the current user-owned connection capability and link validated privacy terms when supplied. For browser speech it SHALL explain that the browser/device speech service performs recognition and synthesis, may process audio remotely depending on the browser, and is separate from the universe's connected writer. Both disclosures SHALL state that TinyAssets submits and stores the canonical text exchange but not raw audio and never substitutes shared provider authority.

#### Scenario: Browser speech relays one canonical turn
- **WHEN** browser recognition returns a final non-empty utterance
- **THEN** the app submits that exact text once through authenticated `converse`
- **AND** renders the exact canonical reply before passing that same text to speech synthesis
- **AND** sends no raw audio to a TinyAssets route

#### Scenario: First voice start requires current disclosure
- **WHEN** the browser profile has not accepted the current disclosure version and identity for the selected bridge or browser speech transport
- **THEN** the app first confirms an available speech transport and presents its disclosure before requesting microphone permission or a voice session
- **AND** declining leaves typed conversation available and sends no audio

#### Scenario: Voice resource or bridge descriptor changes
- **WHEN** a browser profile accepted the disclosure for an earlier connection, protocol, session URL, service name, privacy URL, or disclosure version
- **THEN** the app requires fresh disclosure acceptance before requesting microphone permission or a voice session
- **AND** the server exposes only an opaque, non-secret disclosure identifier rather than a connection credential

#### Scenario: Raw audio is excluded from TinyAssets persistence
- **WHEN** a voice turn completes, is interrupted, or fails
- **THEN** TinyAssets does not write microphone bytes, bridge audio events, or partial audio buffers to conversation history or application logs
