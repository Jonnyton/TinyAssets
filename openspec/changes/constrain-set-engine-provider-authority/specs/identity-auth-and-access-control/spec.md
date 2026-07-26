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
- **AND** only `activate-requester-host-engines` may mint the separate attested `ProviderHostRequestCapability`

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

### Requirement: Attested local transports use a separate host-bound request capability

`activate-requester-host-engines` SHALL own
`ProviderHostRequestCapability` in `identity-auth-and-access-control` as well
as its daemon/desktop/provider-routing deltas. It SHALL mint this capability
for interactive local stdio or local SSE only after verifying either a stable
authenticated account-to-host binding or a same-OS-user local-installation
principal plus attested tray/plugin/runtime identity. Remote or unattested SSE
SHALL mint nothing.

The capability SHALL bind exact local principal, host/installation,
transport-session nonce, target universe, owning execution scope, active
server-liveness lease, permitted host/local assignment generation, mechanism
`tinyassets.attested-host-request.v1`, and issuer
`activate-requester-host-engines`. It
SHALL use the same explicit internal carrier and sink revalidation as
`ProviderRequestCapability`, but the two types SHALL NOT substitute for one
another. It is distinct from the three zero-output
`HostLocalProviderCapability` probes and MAY authorize interactive model work
only against the requester's attested host/local assignment.

Post-cutover release proof SHALL include rendered conversations through the
Tier-2 tray, Tier-3 OSS stdio clone, and mirrored Claude-plugin local runtime.
A fully held installation or a local surface with no minting owner MUST NOT
pass cutover as merely "safe."

#### Scenario: local stdio session receives bounded interactive authority
- **WHEN** an OSS or tray stdio session proves its same-user installation principal and attested local runtime
- **THEN** the host successor mints one session-bound `ProviderHostRequestCapability`
- **AND** routing can use only that principal's attested host/local assignment

#### Scenario: remote or unattested SSE remains held
- **WHEN** SSE lacks authenticated account-to-host or attested same-user installation identity
- **THEN** it receives neither request capability type
- **AND** no local subscription, model, hardware, or maintainer resource is reachable

#### Scenario: host-bound request authority is not a maintenance probe
- **WHEN** interactive local model work is requested
- **THEN** a zero-output `HostLocalProviderCapability` cannot authorize it
- **AND** only the exact live host-request capability may enter the provider carrier

### Requirement: Missing or partial authority holds execution after birth

Universe birth and founder-home binding SHALL complete without provider
authority, but provider-backed execution SHALL NOT begin unless request or
work authority is complete. The universe action layer SHALL catch
`ProviderAuthorityHeldError` from any first-contact or `converse` provider
phase and map it directly to the canonical
`engine_setup_required_payload`. This SHALL NOT require
`AllProvidersExhaustedError`, non-null provider chain state, provider attempt,
or credential lookup.

The payload SHALL preserve completed birth/home binding and contain
`status=held`, `reason=setup_required`, materialized `universe_id`, typed
missing compute/model-access elements, and only setup paths proven live and
completable for that requester's actual surface. It SHALL use
`fulfillment_class=requester_owned|accepted_market`, never overload credential
`authority_class`. Raw `byo_api_key` deposit MUST NOT be advertised.
Accepted-market setup may appear only after paid-market agreement plus
distributed-execution B2/B13 and its connector action path are live;
requester-host/local setup may appear only after its host successor and
surface-specific capability are live.

Before provider-authority enforcement or newborn deny-all can cut over, a
Tier-1 streamable-HTTP chatbot user SHALL be able to complete at least one
advertised path end-to-end through the live connector without a desktop-only
prerequisite. Tier-2 tray, Tier-3 OSS stdio, and Claude-plugin surfaces SHALL
each advertise and complete their own live host/local path. If a surface has
no completable path, cutover SHALL stop rather than render a dead instruction.

`_DEFAULT_ENGINE_SOURCE` SHALL become `unassigned`.
`universe_has_assigned_engine` SHALL derive readiness from
`engine_assignment_state="ready"` plus a non-empty ordinary provider ceiling,
or a separately proven accepted remote execution grant; it MUST NOT infer
assignment from `engine_source != "byo_api_key"`. Legacy
`AllProvidersExhaustedError` for an unassigned universe SHALL still map to the
same setup payload rather than generic prose.

This requirement supersedes the merged-active `universe-creation` requirement
of the same name before that change archives/syncs: its unconditional raw BYOC
and accepted-market setup-path wording becomes the surface-live rule above,
and its receipt naming uses `fulfillment_class` rather than
`authority_class`.

#### Scenario: pre-provider authority hold renders setup
- **WHEN** a newborn or existing universe raises `ProviderAuthorityHeldError` before provider-chain access
- **THEN** the action returns the canonical setup-required payload without requiring chain state
- **AND** `converse` relays that structured hold rather than generic failure prose

#### Scenario: legacy exhaustion still recognizes an unassigned universe
- **WHEN** an unassigned newborn reaches the legacy `AllProvidersExhaustedError` path
- **THEN** `universe_has_assigned_engine` is false and setup-required renders
- **AND** the founder does not receive generic provider-unreachable prose

#### Scenario: connector advertises only a completable first-class path
- **WHEN** a Tier-1 chatbot founder receives setup-required after cutover
- **THEN** at least one advertised accepted-market or previously bound host path is completable through the live connector
- **AND** raw API-key deposit and unavailable desktop-only paths are absent

#### Scenario: unavailable setup route blocks release
- **WHEN** a surface has no setup route that passes its end-to-end acceptance
- **THEN** provider-authority enforcement and newborn deny-all do not cut over on that surface
- **AND** a truthful but dead instruction is not considered product readiness
