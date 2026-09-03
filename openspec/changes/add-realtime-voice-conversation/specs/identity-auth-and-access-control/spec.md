## ADDED Requirements

### Requirement: Voice-session minting requires the authenticated founder identity
The `GET /mcp/app/voice/status` capability check and `POST /mcp/app/voice/session` broker SHALL require a resolved authenticated subject, SHALL derive the founder home universe from that subject instead of a caller-selected universe id, and SHALL fail closed before credential access or network activity when identity or ownership cannot be proven.

#### Scenario: Anonymous caller requests a voice session
- **WHEN** a request reaches the voice-session broker without a resolved authenticated subject under an OAuth-backed provider
- **THEN** the server returns an authentication challenge or denial
- **AND** it performs no credential lookup and no OpenAI request

#### Scenario: Authenticated founder requests the home voice session
- **WHEN** a founder with a materialized home universe requests a voice session
- **THEN** the broker resolves that home through the authenticated subject
- **AND** it does not accept a body parameter that could select another founder's universe

#### Scenario: Authenticated founder checks Voice capability
- **WHEN** a founder requests Voice status
- **THEN** the server derives that founder's home universe and returns only secret-free readiness metadata
- **AND** readiness cannot be borrowed from another founder, the host environment, or a maintainer account

#### Scenario: Founder home is absent
- **WHEN** an authenticated subject without a materialized founder home requests a voice session
- **THEN** the broker returns an actionable not-ready failure
- **AND** it does not auto-create a universe or access any credential
