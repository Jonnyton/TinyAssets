## ADDED Requirements

### Requirement: Realtime voice transport cannot alter primary-writer routing
Enabling Realtime voice SHALL NOT enroll, select, replace, or fall back to an OpenAI API model as the universe's primary writer; every spoken turn SHALL continue to use the writer selected by the existing routing equation through `converse`, and the voice API credential SHALL remain auxiliary user-owned transport compute.

#### Scenario: Subscription writer uses metered voice transport
- **GIVEN** a universe whose assigned writer is a subscription CLI and whose owner explicitly enabled user-funded Realtime voice
- **WHEN** the founder completes a spoken turn
- **THEN** `converse` runs the primary turn on the assigned subscription writer
- **AND** Realtime is used only for speech transport and function-call relay

#### Scenario: Voice API fails
- **WHEN** Realtime is unavailable, exhausted, or unauthorized
- **THEN** the app reports voice unavailable and preserves typed conversation
- **AND** the router does not substitute an API-key writer or any unselected provider

#### Scenario: General API-key writer allowance remains disabled
- **GIVEN** `TINYASSETS_ALLOW_REALTIME_VOICE_API` is enabled and `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is disabled
- **WHEN** provider routing selects a writer
- **THEN** the voice allowance does not make API-key writer providers eligible
