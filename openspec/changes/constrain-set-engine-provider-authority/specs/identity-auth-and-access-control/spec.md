## ADDED Requirements

### Requirement: Authenticated transport mints one request-scoped provider capability

Authenticated transport middleware SHALL mint one
`ProviderRequestCapability` after a bearer token validates and resolves a
non-anonymous identity for that
request. The capability SHALL bind an opaque request nonce, authenticated
principal ID, mechanism `tinyassets.authenticated-request.v1`, issuer
`tinyassets.auth.middleware`, an unexported identity token, and a
server-owned request-liveness lease. Middleware SHALL register the lease with
the owning transport task/execution-scope identity, mark it active only for
that request, revoke it synchronously before context reset in `finally`, and
make sink liveness checks thread-safe. It SHALL be
non-serializable, non-copyable, non-pickleable, unavailable through API/MCP
schemas or caller-controlled construction, stored in request-local context,
and reset with request identity at request end.

Before request context is reset, the internal `call_provider` bridge SHALL
retrieve the exact object, prove that the server registry still marks its
lease active and that the caller is the owning transport task/execution scope,
mint an internal-only sealed `ProviderAuthorityCarrier`, and pass it into `call_sync`,
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
explicit carrier SHALL grant no provider authority. The sink SHALL recheck
that the server-owned lease is active immediately before invocation minting;
an inherited asyncio Context containing the old identity/capability SHALL NOT
extend the lease or satisfy the owning-execution-scope check.
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

#### Scenario: inherited asyncio context cannot outlive the request
- **WHEN** a child task inherits request ContextVars and runs after middleware revokes the request-liveness lease
- **THEN** bridge and sink checks reject the capability despite the inherited identity and object
- **AND** the child must use a separately owned `ProviderWorkAuthorityReceipt`

#### Scenario: detached child cannot spend while the parent request is active
- **WHEN** an inherited child task calls the bridge before parent middleware returns
- **THEN** its execution-scope identity does not match the lease owner and no carrier is minted
- **AND** only the structured owning request task may propagate request authority

#### Scenario: worker ContextVar absence does not drop explicit authority
- **WHEN** `call_sync` executes in its thread-pool worker without inherited request ContextVars
- **THEN** it uses only the internal capability object captured by the request-side pool closure
- **AND** a missing, mismatched, or caller-constructed carrier holds

#### Scenario: capability is not standalone universe authority
- **WHEN** a valid capability is used with a universe, binding principal, provider, host, or assignment generation that does not match fresh server state
- **THEN** provider routing holds
- **AND** the valid authentication fact does not widen authority
