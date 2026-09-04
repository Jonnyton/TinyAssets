## MODIFIED Requirements

### Requirement: Realtime voice transport cannot alter primary-writer routing
Enabling Realtime voice SHALL NOT enroll, select, replace, or fall back to any provider as the universe's primary writer; capability discovery SHALL inspect only the provider already selected by the existing routing equation, every spoken turn SHALL continue to use that writer through `converse`, and the voice bridge SHALL remain auxiliary transport on that provider's existing user-owned connection.

#### Scenario: Current provider advertises realtime transport
- **GIVEN** a universe with an assigned writer whose exact user-owned connection declares authorized `tinyassets.voice.v1` support
- **WHEN** the founder completes a spoken turn
- **THEN** `converse` runs the primary turn on the assigned writer
- **AND** the same provider connection's voice bridge is used only for speech transport and function-call relay

#### Scenario: Assigned writer lacks a compatible voice capability
- **GIVEN** a universe whose assigned writer works but whose current provider exposes no compatible realtime capability
- **WHEN** the founder starts Voice
- **THEN** the writer remains selected and typed conversation continues
- **AND** the same control opens the existing provider connection or capability-request path and explains that compatible user-owned authority is required
- **AND** TinyAssets does not request a separate Voice-only credential or widen to platform compute

#### Scenario: Generic outbound transport is disabled while provider setup remains actionable
- **GIVEN** generic outbound HTTP transport is disabled
- **WHEN** the founder starts Voice without compatible current-provider authority
- **THEN** TinyAssets discovers the current provider's capability state and opens the existing provider connection or capability-request path when remediation is available
- **AND** no microphone permission or Voice session request occurs

#### Scenario: Another provider has realtime capability
- **WHEN** another connection or provider could supply realtime Voice but is not the current serving provider
- **THEN** capability discovery does not select or call it
- **AND** only an explicit user change through the existing provider-authority path can make it eligible

#### Scenario: Voice bridge fails
- **WHEN** the current provider's bridge is unavailable, exhausted, or unauthorized
- **THEN** the app reports Voice unavailable and preserves typed conversation
- **AND** the router does not substitute an API-key writer or any unselected provider

#### Scenario: General API-key writer allowance remains disabled
- **GIVEN** an exact user-owned Voice capability is ready and `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is disabled
- **WHEN** provider routing selects a writer
- **THEN** the voice allowance does not make API-key writer providers eligible
