## ADDED Requirements

### Requirement: Voice mode is explicit, foreground-only, and accessible
The shared TinyAssets app SHALL show Voice as ready only when the authenticated universe has a compatible user-bound resource, SHALL show it as an unlockable capability otherwise, SHALL require an explicit user start action, and SHALL stop every microphone track when the user leaves voice mode, hides or unloads the app, signs out, or reaches an unrecoverable error.

#### Scenario: Voice is unavailable by default
- **WHEN** either required voice allowance is disabled
- **THEN** the app does not start microphone capture or request a Realtime client credential
- **AND** it presents a concise unavailable reason without disabling typed conversation

#### Scenario: Host supports Voice but the universe lacks a compatible resource
- **WHEN** the signed-in app checks Voice capability and no compatible resource is bound to that universe
- **THEN** Voice is visibly locked with an explanation that a compatible user-owned resource can unlock it
- **AND** the app makes no microphone request, Realtime request, platform-credential lookup, or change to typed conversation

#### Scenario: Every active state is perceivable
- **WHEN** voice moves among requesting permission, connecting, listening, thinking, speaking, reconnecting, or error
- **THEN** the app displays the current state and announces it through an accessible live region
- **AND** the start/stop control remains keyboard operable

#### Scenario: Leaving voice stops capture
- **WHEN** the user stops voice, signs out, hides the app, or unloads the page
- **THEN** all local microphone tracks stop and the client returns to a non-capturing state

### Requirement: Realtime transport uses WebRTC with semantic turn-taking and barge-in
The voice client SHALL use a WebRTC Realtime session configured by the server with semantic voice activity detection, automatic turn creation, and response interruption enabled; it SHALL NOT place a long-lived OpenAI credential in client code or storage.

#### Scenario: User interrupts spoken output
- **WHEN** provider speech-started evidence arrives while the universe reply is playing
- **THEN** unplayed output is cancelled or truncated and the client transitions to listening
- **AND** the complete canonical text reply remains visible in history

#### Scenario: Microphone permission is denied
- **WHEN** the platform rejects microphone permission
- **THEN** the client enters an actionable error state without creating an audio session
- **AND** typed conversation remains available

### Requirement: Voice turns relay through the canonical converse operation exactly once
For every committed spoken user turn, the client SHALL invoke the existing authenticated `converse` operation exactly once, SHALL render its returned universe text as the canonical assistant reply, and SHALL restrict Realtime to speech transport and the narrow `converse(message)` function-call contract.

#### Scenario: Spoken turn enters the shared thread
- **WHEN** semantic turn detection commits a user utterance and Realtime emits a valid `converse` function call
- **THEN** the client calls `MCP.converse` once with the committed message
- **AND** the founder message and exact returned reply appear in the same history used by typed turns

#### Scenario: Realtime attempts an untooled answer
- **WHEN** Realtime produces assistant content without the required `converse` tool result
- **THEN** the client refuses to store or render that content as the universe's canonical reply
- **AND** the turn fails visibly rather than inventing a fallback response

### Requirement: Disconnect and expiry recovery never silently duplicate a turn
The voice client SHALL treat media-session state as disposable, SHALL obtain a new short-lived credential for reconnection, and SHALL NOT automatically replay a `converse` call whose delivery is in flight or ambiguous.

#### Scenario: Media disconnect occurs during a converse call
- **WHEN** WebRTC disconnects after `MCP.converse` has started
- **THEN** the existing call may finish and its canonical text result is rendered once
- **AND** reconnect does not submit the founder message again

#### Scenario: Session reconnect succeeds
- **WHEN** a bounded reconnect attempt establishes a new Realtime session
- **THEN** the app reloads canonical text history and resumes in listening state
- **AND** it does not replay prior audio or automatically speak the prior reply

#### Scenario: Delivery remains ambiguous
- **WHEN** the client cannot determine whether a founder turn reached `converse`
- **THEN** it presents an explicit retry action
- **AND** it does not retry without user intent

### Requirement: Audio privacy and resource use are disclosed before capture
The app SHALL confirm capability and then disclose before its first microphone permission request that audio is sent to the selected voice provider, any provider use belongs to the universe's bound resource, TinyAssets never substitutes shared authority, TinyAssets stores the canonical text exchange but not raw audio, and provider retention controls apply.

#### Scenario: First voice start requires current disclosure
- **WHEN** the browser profile has not accepted the current disclosure version
- **THEN** the app first confirms a compatible resource and presents the disclosure before requesting microphone permission or a client credential
- **AND** declining leaves typed conversation available and sends no audio

#### Scenario: Raw audio is excluded from TinyAssets persistence
- **WHEN** a voice turn completes, is interrupted, or fails
- **THEN** TinyAssets does not write microphone bytes, provider audio events, or partial audio buffers to conversation history or application logs

### Requirement: Voice sessions are bounded and fail visibly
The client SHALL enforce a session-duration cap below the provider maximum, SHALL bound reconnection attempts, and SHALL expose provider-reported usage only as a non-authoritative estimate rather than a billing guarantee.

#### Scenario: Local session cap is reached
- **WHEN** an active voice session reaches the configured local duration cap
- **THEN** the client stops capture and returns to idle with an explanation
- **AND** it does not silently mint a replacement credential

#### Scenario: Reconnect budget is exhausted
- **WHEN** the bounded reconnect attempts all fail
- **THEN** the client enters an actionable error state and stops capture
- **AND** typed conversation and existing history remain available
