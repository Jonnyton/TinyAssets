## ADDED Requirements

### Requirement: Authenticated transport mints one request-scoped provider capability

Authenticated transport middleware SHALL mint one
`ProviderRequestCapability` after a bearer token validates and resolves a
non-anonymous identity for that
request. The capability SHALL bind an opaque request nonce, authenticated
principal ID, mechanism `tinyassets.authenticated-request.v1`, issuer
`tinyassets.auth.middleware`, and an unexported identity token. It SHALL be
non-serializable, non-copyable, non-pickleable, unavailable through API/MCP
schemas or caller-controlled construction, stored in request-local context,
and reset with request identity at request end.

Provider sinks SHALL obtain the exact current capability rather than accept
one from action arguments. A missing bearer, anonymous identity, invalid
token, mismatched current identity, wrong mechanism/issuer, copied or
serialized value, stale prior-request capability, lookalike object, or
capability presented outside its request SHALL grant no provider authority.
The capability alone SHALL NOT authorize a universe, provider, credential,
host, assignment generation, market agreement, background run, or spend; the
provider-routing sink SHALL bind those dimensions from fresh server state.

#### Scenario: authenticated request receives an unforgeable capability
- **WHEN** transport validates a bearer and resolves a non-anonymous identity
- **THEN** middleware installs one request capability bound to that principal and request nonce
- **AND** provider routing can retrieve the same object only within that request

#### Scenario: anonymous or invalid request receives no capability
- **WHEN** credentials are absent, invalid, or resolve anonymous
- **THEN** no provider request capability is minted
- **AND** caller data cannot substitute one

#### Scenario: prior-request replay fails
- **WHEN** a capability from request A is copied, retained, or presented during request B
- **THEN** identity-token/current-context validation rejects it
- **AND** no provider or credential is accessed

#### Scenario: capability is not standalone universe authority
- **WHEN** a valid capability is used with a universe, binding principal, provider, host, or assignment generation that does not match fresh server state
- **THEN** provider routing holds
- **AND** the valid authentication fact does not widen authority
