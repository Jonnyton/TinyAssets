## ADDED Requirements

### Requirement: Realtime voice authority is universe-scoped and credential-blind
The voice capability check and session broker SHALL use only a generic HTTP connection and grant explicitly bound to the authenticated owner's universe. The voice route SHALL NOT resolve or receive the long-lived connection credential; credential resolution and request signing remain inside the existing credential-blind broker child. The response to the app SHALL contain only a validated SDP answer and bounded, non-secret session metadata.

#### Scenario: Compatible owner connection exchanges bounded signaling
- **GIVEN** all host gates are enabled and the authenticated owner's universe has a valid voice binding referencing its active HTTP connection and grant
- **WHEN** the owner requests a voice session
- **THEN** the broker sends the provider-neutral session policy and bounded SDP offer through that exact credential-blind connection
- **AND** it returns only a validated, bounded SDP answer and session metadata
- **AND** the response contains no long-lived credential

#### Scenario: Ambient credential is present but an owner connection is absent
- **GIVEN** one or more process-global service credentials exist but the authenticated owner's universe has no valid bound voice connection
- **WHEN** the owner requests a voice session
- **THEN** capability is reported as locked and the broker fails before a network request
- **AND** it does not use an ambient credential, platform connection, or another universe's grant

#### Scenario: Conversation engine authority exists without voice authority
- **GIVEN** a universe has a working assigned writer but no separately bound voice connection
- **WHEN** the app checks Voice capability
- **THEN** Voice is reported as locked while the writer remains available
- **AND** TinyAssets does not request a new credential, substitute platform authority, or disturb writer routing

#### Scenario: Secret-bearing paths are non-observable
- **WHEN** session signaling succeeds or fails
- **THEN** application logs, traces, exceptions, and conversation history contain no long-lived connection credential
- **AND** the HTTP response is marked not cacheable
