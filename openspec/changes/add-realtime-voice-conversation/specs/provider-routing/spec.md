## ADDED Requirements

### Requirement: Realtime voice transport cannot alter primary-writer routing
Enabling Realtime voice SHALL NOT enroll, select, replace, or fall back to any voice service as the universe's primary writer; every spoken turn SHALL continue to use the writer selected by the existing routing equation through `converse`, and any voice connection SHALL remain auxiliary transport bound to that same universe.

#### Scenario: Assigned writer uses separate voice transport
- **GIVEN** a universe with an assigned writer and an explicitly bound user-owned voice connection
- **WHEN** the founder completes a spoken turn
- **THEN** `converse` runs the primary turn on the assigned writer
- **AND** the voice bridge is used only for speech transport and function-call relay

#### Scenario: Assigned writer lacks a compatible voice resource
- **GIVEN** a universe whose assigned writer works but whose bound resources contain no compatible voice bridge
- **WHEN** the founder views or starts Voice
- **THEN** the writer remains selected and typed conversation continues
- **AND** Voice is locked without requesting a separate credential or widening to platform compute

#### Scenario: Voice bridge fails
- **WHEN** the bridge is unavailable, exhausted, or unauthorized
- **THEN** the app reports voice unavailable and preserves typed conversation
- **AND** the router does not substitute an API-key writer or any unselected provider

#### Scenario: General API-key writer allowance remains disabled
- **GIVEN** the voice session switch is enabled and `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is disabled
- **WHEN** provider routing selects a writer
- **THEN** the voice allowance does not make API-key writer providers eligible
