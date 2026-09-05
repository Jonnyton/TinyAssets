## MODIFIED Requirements

### Requirement: Voice-session signaling requires the authenticated founder identity
The provider-capability configuration path, `GET /mcp/app/voice/status` capability check, and `POST /mcp/app/voice/session` broker SHALL require a resolved authenticated subject, SHALL derive the founder home universe and current serving provider through the same canonical home resolver instead of caller-selected authority, and SHALL fail closed before mutation, connection lookup, or network activity when identity or ownership cannot be proven. Capability configuration additionally requires both a current admin ACL and exact connection-grant ownership by the authenticated actor.

#### Scenario: Anonymous caller configures or requests Voice
- **WHEN** a request reaches capability configuration, Voice status, or the voice-session broker without a resolved authenticated subject
- **THEN** the server returns an authentication challenge or denial
- **AND** it performs no capability mutation, connection lookup, or network request

#### Scenario: Authenticated owner configures the current provider capability
- **WHEN** a founder with a current admin ACL who exactly owns the current connection grant declares or revokes realtime capability for their home universe
- **THEN** the server derives the home universe and current provider through that subject
- **AND** the request body cannot select a universe, provider, connection, or grant

#### Scenario: Caller graph disagrees with derived home
- **WHEN** `write_graph` supplies a `graph_id` that does not exactly match the authenticated subject's canonically derived founder home
- **THEN** capability configuration is refused before connection lookup or mutation
- **AND** the caller-selected graph is not ignored or substituted

#### Scenario: Non-owner administrator tries to configure capability
- **WHEN** an administrator who does not own the current connection grant attempts to declare or revoke its capability
- **THEN** the server refuses before mutation
- **AND** the owner's next Voice tap cannot use metadata authored by that administrator

#### Scenario: Authenticated founder requests the home voice session
- **WHEN** a founder with a materialized home universe requests a voice session
- **THEN** the broker resolves that home and current provider through the authenticated subject
- **AND** it does not accept a body parameter that could select another founder's universe, provider, connection, or grant

#### Scenario: Authenticated founder checks Voice capability
- **WHEN** a founder requests Voice status
- **THEN** the server derives that founder's home universe and current serving provider and returns only secret-free readiness metadata
- **AND** readiness requires exact owner, universe, connection, grant, capability, revocation, type, method, and endpoint matches
- **AND** readiness cannot be borrowed from another founder, the host environment, a maintainer account, or another provider

#### Scenario: Founder home is absent
- **WHEN** an authenticated subject without a materialized founder home requests a voice session
- **THEN** the broker returns an actionable not-ready failure
- **AND** it does not auto-create a universe or access any credential
