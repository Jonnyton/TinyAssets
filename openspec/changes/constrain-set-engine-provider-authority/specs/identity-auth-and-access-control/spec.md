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

Before request context is reset, the internal `call_provider` bridge SHALL
retrieve the exact object and pass it through an internal-only typed
`ProviderAuthorityCarrier` argument into `call_sync`,
`call_with_policy_sync`, retry/policy/judge branches, the router thread-pool
closure, and `ProviderInvocation`. This explicit propagation SHALL NOT depend
on `ContextVar` propagation into `ProviderRouter`'s class-level
`ThreadPoolExecutor`, which is intentionally absent. Startup/CI inventory
SHALL prove that every request thread/task bridge either carries the exact
object or holds before provider work.

Provider sinks SHALL obtain the exact carried capability rather than accept
one from action arguments or ambient worker context. A missing bearer,
anonymous identity, invalid token, mismatched current identity, wrong
mechanism/issuer, copied or serialized value, stale prior-request capability,
lookalike object, capability presented outside its request, or missing
explicit carrier SHALL grant no provider authority.
The capability alone SHALL NOT authorize a universe, provider, credential,
host, assignment generation, market agreement, background run, or spend; the
provider-routing sink SHALL bind those dimensions from fresh server state.

#### Scenario: authenticated request receives an unforgeable capability
- **WHEN** transport validates a bearer and resolves a non-anonymous identity
- **THEN** middleware installs one request capability bound to that principal and request nonce
- **AND** the internal bridge explicitly carries the same object through the router pool only for that request

#### Scenario: anonymous or invalid request receives no capability
- **WHEN** credentials are absent, invalid, or resolve anonymous
- **THEN** no provider request capability is minted
- **AND** caller data cannot substitute one

#### Scenario: unauthenticated stdio and SSE transports mint no request capability
- **WHEN** a stdio or SSE server shell runs without `AuthContextMiddleware` or another reviewed authenticated transport identity
- **THEN** it mints no `ProviderRequestCapability` and request provider work holds
- **AND** only a future stable account-to-host route may supply its separate explicit authority

#### Scenario: prior-request replay fails
- **WHEN** a capability from request A is copied, retained, or presented during request B
- **THEN** identity-token/current-context validation rejects it
- **AND** no provider or credential is accessed

#### Scenario: worker ContextVar absence does not drop explicit authority
- **WHEN** `call_sync` executes in its thread-pool worker without inherited request ContextVars
- **THEN** it uses only the internal capability object captured by the request-side pool closure
- **AND** a missing, mismatched, or caller-constructed carrier holds

#### Scenario: capability is not standalone universe authority
- **WHEN** a valid capability is used with a universe, binding principal, provider, host, or assignment generation that does not match fresh server state
- **THEN** provider routing holds
- **AND** the valid authentication fact does not widen authority
