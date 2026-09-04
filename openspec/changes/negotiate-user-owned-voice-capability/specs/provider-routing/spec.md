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
- **WHEN** the founder views or starts Voice
- **THEN** the writer remains selected and typed conversation continues
- **AND** Voice is unavailable without requesting a second credential or widening to platform compute

#### Scenario: Another provider has realtime capability
- **WHEN** another connection or provider could supply realtime Voice but is not the current serving provider
- **THEN** capability discovery does not select or call it
- **AND** only an explicit user change through the existing provider-authority path can make it eligible

#### Scenario: Voice bridge fails
- **WHEN** the current provider's bridge is unavailable, exhausted, or unauthorized
- **THEN** the app reports Voice unavailable and preserves typed conversation
- **AND** the router does not substitute an API-key writer or any unselected provider

#### Scenario: General API-key writer allowance remains disabled
- **GIVEN** the voice session switch is enabled and `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is disabled
- **WHEN** provider routing selects a writer
- **THEN** the voice allowance does not make API-key writer providers eligible

