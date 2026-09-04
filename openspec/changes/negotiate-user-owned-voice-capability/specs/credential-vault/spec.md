## MODIFIED Requirements

### Requirement: Realtime voice authority is universe-scoped and credential-blind
The voice capability declaration, capability check, and session broker SHALL use only the current provider's existing generic HTTP connection and grant bound to the authenticated owner's universe. Capability metadata SHALL NOT grant or widen credential authority. The voice route SHALL NOT resolve or receive the long-lived connection credential; credential resolution and request signing remain inside the existing credential-blind broker child. The response to the app SHALL contain only a validated SDP answer and bounded, non-secret session metadata.

Capability metadata SHALL be stored in a `connection_capabilities` table keyed by `(connection_id, capability_kind)` and linked to the owning connection. Connection deletion SHALL remove its capability rows in the same transaction before the deterministic connection id can be reused.

#### Scenario: Compatible current provider exchanges bounded signaling
- **GIVEN** generic outbound HTTP transport is enabled and the authenticated owner's current provider has a valid realtime capability on its active HTTP connection and grant
- **WHEN** the owner requests a voice session
- **THEN** the broker sends the provider-neutral session policy and bounded SDP offer through that exact credential-blind connection
- **AND** it returns only a validated, bounded SDP answer and session metadata
- **AND** the response contains no long-lived credential

#### Scenario: Capability declaration cannot widen a grant
- **WHEN** the owner declares realtime capability metadata for an existing provider connection
- **THEN** TinyAssets requires the session endpoint and `POST` method to be present in the connection's existing allowlist and scopes
- **AND** it does not mutate credential custody, endpoint authority, the universe grant, or serving selection

#### Scenario: Credential custody rotates without a new declaration
- **WHEN** the current connection or grant no longer passes the canonical serving-authority credential digest check
- **THEN** Voice status and session creation fail closed
- **AND** a stale capability row cannot authorize signaling with the rotated credential

#### Scenario: Ambient credential is present but current provider capability is absent
- **GIVEN** one or more process-global service credentials exist but the current provider has no valid realtime capability
- **WHEN** the owner requests a voice session
- **THEN** capability is reported as unavailable and the broker fails before a network request
- **AND** it does not use an ambient credential, platform connection, another universe's grant, or another provider

#### Scenario: Conversation engine authority exists without voice authority
- **GIVEN** a universe has a working assigned writer whose current provider exposes no compatible realtime capability
- **WHEN** the app checks Voice capability
- **THEN** Voice is reported as unavailable while the writer remains available
- **AND** TinyAssets does not request a second credential, substitute platform authority, or disturb writer routing

#### Scenario: Secret-bearing paths are non-observable
- **WHEN** capability configuration or session signaling succeeds or fails
- **THEN** application logs, traces, exceptions, capability rows, and conversation history contain no long-lived connection credential
- **AND** the HTTP response is marked not cacheable
