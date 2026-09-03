## ADDED Requirements

### Requirement: Realtime voice transport cannot alter primary-writer routing
Enabling Realtime voice SHALL NOT enroll, select, replace, or fall back to an OpenAI API model as the universe's primary writer; every spoken turn SHALL continue to use the writer selected by the existing routing equation through `converse`, and any voice resource SHALL remain auxiliary compute bound to that same universe.

#### Scenario: Subscription writer uses metered voice transport
- **GIVEN** a universe whose assigned writer is a subscription CLI and whose owner explicitly enabled user-funded Realtime voice
- **WHEN** the founder completes a spoken turn
- **THEN** `converse` runs the primary turn on the assigned subscription writer
- **AND** Realtime is used only for speech transport and function-call relay

#### Scenario: Subscription writer lacks a compatible voice resource
- **GIVEN** a universe whose assigned writer is a working Codex subscription but whose bound resources contain no documented Realtime-audio authority
- **WHEN** the founder views or starts Voice
- **THEN** the subscription writer remains selected and typed conversation continues
- **AND** Voice is locked without requesting a separate credential or widening to platform compute

#### Scenario: Voice API fails
- **WHEN** Realtime is unavailable, exhausted, or unauthorized
- **THEN** the app reports voice unavailable and preserves typed conversation
- **AND** the router does not substitute an API-key writer or any unselected provider

#### Scenario: General API-key writer allowance remains disabled
- **GIVEN** `TINYASSETS_ALLOW_REALTIME_VOICE_API` is enabled and `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is disabled
- **WHEN** provider routing selects a writer
- **THEN** the voice allowance does not make API-key writer providers eligible
