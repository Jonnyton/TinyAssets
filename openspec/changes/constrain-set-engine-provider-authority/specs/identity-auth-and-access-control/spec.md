## ADDED Requirements

### Requirement: Provider authority identity clauses share the effective V2 gate

All target clauses in this capability SHALL use the effective default-false
`TINYASSETS_PROVIDER_AUTHORITY_V2` gate defined by `provider-routing`. While
neither the global flag nor the server-owned isolated-canary opt-in applies,
they SHALL remain observational/non-authorizing: shipped stdio/dev transport
behavior and shipped `setup_paths`, including raw `byo_api_key`, remain
unchanged. A server-listed isolated test principal may bootstrap only a new
public/first-contact birth after the server proves it has no existing
home/universe; the generated universe ID is registered before visibility, and
later enforcement keys on that ID rather than principal alone.
The process-global `_DEFAULT_ENGINE_SOURCE` is the sole carve-out: it remains
keyed only on the global flag, while canary universes use their explicit birth
state and the effective per-universe gate.

#### Scenario: dark identity target preserves shipped surfaces
- **WHEN** the global flag is false and a universe is absent from configured/registered server-owned canary state
- **THEN** target request capabilities, holds, and setup filtering grant no authority and change no shipped result
- **AND** stdio/dev provider behavior plus shipped setup paths remain unchanged

#### Scenario: isolated canary uses the complete identity target
- **WHEN** an isolated acceptance-test universe is present in configured/registered server-owned canary state
- **THEN** every target identity capability, hold, and setup clause applies coherently for that universe
- **AND** no request or caller-controlled value can opt another universe in

#### Scenario: canary principal cannot widen existing identity authority
- **WHEN** a server-listed test principal has an existing home or universe
- **THEN** canary birth preflight refuses before registering any ID
- **AND** principal membership alone never enables target enforcement on an existing universe

### Requirement: Authenticated MCP message dispatch mints one message-scoped provider capability

The outer ASGI `AuthContextMiddleware` SHALL retain OAuth challenge,
invalid-token, and anonymous-write pre-dispatch behavior, but its task-local
identity and `finally` lifetime SHALL NOT mint or prove provider authority.
For every non-deferred `tools/call`, a TinyAssets-owned FastMCP
`Middleware.on_call_tool` hook SHALL read the current HTTP message strictly
from `mcp.server.lowlevel.server.request_ctx.get().request`, re-derive its
bearer and non-anonymous principal through the configured TinyAssets auth
provider, and fail closed without minting a reserve when that per-message
request is absent. It SHALL NOT use
`fastmcp.server.dependencies.get_http_request()` because that helper may fall
back to `_current_http_request` or `_task_http_headers`. The hook SHALL NOT
trust those fallback branches, the session initialize request's copied
`ContextVar`, a snapshotted header request, prior message identity, MCP
arguments, client-supplied principal, or ambient session state.

A task-augmented or otherwise deferred `tools/call` SHALL mint no
`ProviderRequestCapability`. Its provider work SHALL hold until
`harden-background-provider-execution-authority` issues and revalidates the
separate durable `ProviderWorkAuthorityReceipt`.

The special anonymous wiki-canary bearer and
`_WikiCanaryExecutionAuthority` SHALL remain canary-only. Provider middleware
SHALL compose with that middleware without treating its token, anonymous
principal, or narrow canary authority as provider identity or capability.

The per-message hook SHALL reserve one opaque, non-serializable dispatch token
before `call_next(context)`. The reserve SHALL bind an opaque message nonce,
authenticated principal ID, current MCP session ID and request ID, exact tool
name, mechanism `tinyassets.authenticated-request.v1`, issuer
`tinyassets.auth.middleware`, an unexported identity token, and the owning
per-message task. The reserve is not provider authority.

For the canonical synchronous-tool path, the TinyAssets-owned wrapper created
by `_register_structured_tool` SHALL atomically claim that reserve on worker
entry, after AnyIO has selected the actual worker, and bind the server-owned
request-liveness lease to the claiming thread plus the exact message/tool
tuple. For an async registered tool, the per-message task SHALL claim the same
reserve immediately before handler entry. Exactly one execution scope MAY
claim it. The resulting `ProviderRequestCapability` and lease SHALL remain
active only while the per-message middleware structurally awaits that exact
handler and SHALL be revoked in the wrapper and middleware `finally` paths
before the result is released. Reserve/capability lookalikes, copied
`ContextVar` values, arbitrary child tasks/threads, nested workers, stale
messages, and caller-controlled execution identifiers SHALL NOT claim,
transfer, or extend the lease.

The capability SHALL be non-serializable, non-copyable, non-pickleable,
unavailable through API/MCP schemas or caller-controlled construction, and
usable only by the registered message task or claimed worker. Before provider
work, the internal `call_provider` bridge SHALL retrieve the exact object,
prove the server registry still marks its message lease and execution claim
active, mint an internal-only sealed `ProviderAuthorityCarrier`, and pass it
into `call_sync`, `call_with_policy_sync`, retry/policy/judge branches, the
router thread-pool closure, and `ProviderInvocation`. This explicit
propagation SHALL NOT depend on `ContextVar` propagation into
`ProviderRouter`'s class-level `ThreadPoolExecutor`, which is intentionally
absent. Startup/CI inventory SHALL prove that every message-to-worker and
router-pool bridge either carries the exact server-issued object or holds
before provider work.

Provider sinks SHALL obtain the exact carried capability rather than accept
one from action arguments or ambient worker/session context. A missing bearer,
anonymous identity, invalid token, mismatched current identity, wrong
mechanism/issuer, copied or serialized value, stale prior-request capability,
lookalike object, capability presented outside its request, or missing
explicit carrier SHALL grant no provider authority. The sink SHALL recheck
that the server-owned lease is active immediately before invocation minting;
an inherited asyncio Context containing an initialize/prior-message
identity/capability SHALL NOT extend the lease or satisfy the current
message/execution-claim check.
The capability alone SHALL NOT authorize a universe, provider, credential,
host, assignment generation, market agreement, background run, or spend; the
provider-routing sink SHALL bind those dimensions from fresh server state.

#### Scenario: authenticated message receives an unforgeable capability
- **WHEN** per-message FastMCP middleware resolves a current bearer to a non-anonymous principal for one `tools/call`
- **THEN** it reserves one dispatch token bound to that principal, session, MCP request, and tool
- **AND** only the exact registered handler execution may claim the message capability and carry it through the router pool

#### Scenario: anonymous or invalid request receives no capability
- **WHEN** current-message credentials are absent, invalid, or resolve anonymous
- **THEN** no provider request capability is minted
- **AND** caller data cannot substitute one

#### Scenario: inherited or snapshotted request fallback is not current-message authority
- **WHEN** per-message `request_ctx` has no current HTTP request but an inherited `_current_http_request` or snapshotted `_task_http_headers` source contains a valid bearer
- **THEN** the hook fails closed and mints no reserve or provider request capability
- **AND** the FastMCP fallback helper and its synthetic request are not consulted

#### Scenario: deferred tool call cannot reuse request authority
- **WHEN** a task-augmented or otherwise deferred tool call would execute after the message middleware returns
- **THEN** it mints no `ProviderRequestCapability` and provider work holds
- **AND** only the background owner's separately issued durable receipt may authorize that work

#### Scenario: wiki canary authority never becomes provider authority
- **WHEN** the special anonymous wiki-canary bearer authorizes its narrow canary operation on the shared FastMCP app
- **THEN** provider middleware mints no reserve, provider request capability, or carrier
- **AND** it preserves the canary middleware's independent narrow behavior without widening it

#### Scenario: unauthenticated stdio and SSE transports mint no request capability
- **WHEN** a stdio or SSE server shell lacks a reviewed authenticated per-message transport identity
- **THEN** it mints no `ProviderRequestCapability` and request provider work holds
- **AND** only `activate-requester-host-engines` may mint the separate attested `ProviderHostRequestCapability`

#### Scenario: stateful session re-derives every message
- **WHEN** a stateful streamable-HTTP session handles initialize and later tool-call messages with the same or refreshed bearer
- **THEN** each tool call derives fresh current-request identity and a distinct message reserve
- **AND** the initialize request's copied identity, token, or revoked lease authorizes nothing

#### Scenario: prior-message replay fails
- **WHEN** a reserve or capability from message A is copied, retained, or presented during message B
- **THEN** current session/request/tool and server-claim validation rejects it
- **AND** no provider or credential is accessed

#### Scenario: inherited asyncio context cannot outlive the request
- **WHEN** a child task inherits message ContextVars and runs after middleware revokes the message lease
- **THEN** bridge and sink checks reject the capability despite the inherited identity and object
- **AND** the child must use a separately owned `ProviderWorkAuthorityReceipt`

#### Scenario: detached child cannot spend while the message is active
- **WHEN** an inherited child task/thread calls the bridge before per-message middleware returns
- **THEN** its execution identity does not match the registered message task or claimed wrapper worker
- **AND** no carrier is minted

#### Scenario: structured synchronous MCP dispatch retains request authority
- **WHEN** per-message middleware reserves a token and FastMCP submits the TinyAssets registered synchronous wrapper through AnyIO
- **THEN** the wrapper atomically claims the reserve against its actual worker identity on entry
- **AND** that worker may use the message capability only until wrapper or middleware `finally` revokes it before result release

#### Scenario: worker claim cannot detach or multiply
- **WHEN** a worker-spawned task/thread, copied reserve, stale worker, second claimant, or caller-supplied identifier attempts to claim or present authority
- **THEN** the server registry rejects it because the reserve is one-shot or the execution identity differs
- **AND** copied Context alone never proves provider authority

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

### Requirement: Connector requester authority has a named activation owner

`activate-connector-requester-authority` SHALL own the Tier-1
streamable-HTTP path across `identity-auth-and-access-control`,
`paid-market-economy`, `distributed-execution`, and
`live-mcp-connector-surface`. It SHALL compose the authenticated requester,
accepted paid-market agreement, a revocable non-executable B13 activation
mandate, bounded spend, and target universe into one connector-completable
accepted-market assignment. It SHALL NOT create or store a B2 before the
later concrete job and capsule exist; only the B13 production composition
root may create that job's exact B2 after every named owner-native result is
current. Its own OpenSpec SHALL name an action
carried by one of the seven canonical live connector handles before its
`applyRequires` gate clears; it MUST NOT use the deprecated `universe` handle,
reintroduce raw secret deposit, or require a desktop/web-app prerequisite.

The successor SHALL own the connector-visible setup step, typed result,
authorization/visibility, idempotency, and rendered acceptance. Until its
change is implemented and the end-to-end path passes, Tier-1 provider-
authority enforcement and newborn deny-all cutover SHALL remain blocked.

#### Scenario: chatbot founder completes accepted market setup
- **WHEN** an authenticated Tier-1 founder accepts a valid market offer through the live connector
- **THEN** the named successor atomically commits the accepted agreement plus current non-executable B13 activation-mandate reference and publishes `engine_source="accepted_market"`, `engine_assignment_state="remote_ready"`, and `allowed_providers=[]`
- **AND** the next `converse` executes only after B13 composes fresh per-job market, capacity, funding, settlement, execution-admission, capsule, and exact B2 authority through the successor's pre-routing remote-execution seam, not the ordinary provider ceiling, without maintainer or desktop resources

#### Scenario: invalid accepted-market mandate maps to repair, not engine-less
- **WHEN** an accepted agreement or activation mandate is absent, expired, revoked, cancelled, fenced, or inconsistent
- **THEN** `universe_has_assigned_engine` remains fail-safe true while execution holds and the successor-owned setup mapper offers accepted-market repair or renewal
- **AND** no ordinary provider, maintainer resource, desktop prerequisite, or generic engine-less envelope substitutes

#### Scenario: absent connector activation owner blocks cutover
- **WHEN** paid-market, the B13 activation/per-job composition path, per-job B2, or the connector-visible setup step is unavailable
- **THEN** no accepted-market path is advertised as completable
- **AND** Tier-1 deny-all enforcement does not cut over

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
distributed-execution B2/B13 and
`activate-connector-requester-authority` are live;
requester-host/local setup may appear only after its host successor and
surface-specific capability are live.

Before provider-authority enforcement or newborn deny-all can cut over, a
Tier-1 streamable-HTTP chatbot user SHALL be able to complete at least one
advertised path end-to-end through the live connector without a desktop-only
prerequisite. Tier-2 tray, Tier-3 OSS stdio, and Claude-plugin surfaces SHALL
each advertise and complete their own live host/local path under the
server-owned isolated-universe canary while the global flag remains false. If
a surface has no completable path, cutover SHALL stop rather than render a
dead instruction.

Migration SHALL add optional assignment state/generation fields without
changing legacy classification. While
`TINYASSETS_PROVIDER_AUTHORITY_V2` is false,
`_DEFAULT_ENGINE_SOURCE` SHALL remain `byo_api_key`. While the gate is false
for a universe (neither global nor canary) or either optional assignment field
is absent,
`universe_has_assigned_engine` SHALL preserve every shipped fail-safe:
unreadable/unparseable vault or config returns true; any LLM credential
returns true; an explicit non-default legacy source returns true; only a
readable default source with no LLM credential returns false.

Only after the migration manifest proves every universe classified and all
surface gates pass may the deployment flip
`TINYASSETS_PROVIDER_AUTHORITY_V2`, set
`_DEFAULT_ENGINE_SOURCE=unassigned` for new births, and use assignment state
globally outside the server-owned canary.
For migrated state, unreadable evidence remains true/fail-safe;
`unassigned + []` is false; `ready + nonempty ceiling` or a separately proven
accepted remote grant is true; and pending/held/failed/inconsistent state is
true for the legacy exhaustion classifier so a real fault is not retold as
"no engine." Typed `ProviderAuthorityHeldError` still maps directly to the
precise setup envelope.

The legacy `AllProvidersExhaustedError` path SHALL retain its non-null
`chain_state` requirement and call the migration-aware helper. A bare
policy/pin/no-router exhaustion SHALL return no setup envelope and preserve its
own error. New deny-all uses `ProviderAuthorityHeldError`; it MUST NOT broaden
the legacy exhaustion mapper.

This requirement supersedes the merged-active `universe-creation` requirement
of the same name before that change archives/syncs: its unconditional raw BYOC
and accepted-market setup-path wording becomes the surface-live rule above,
and its receipt naming uses `fulfillment_class` rather than
`authority_class`.

#### Scenario: pre-provider authority hold renders setup
- **WHEN** a newborn or existing universe raises `ProviderAuthorityHeldError` before provider-chain access
- **THEN** the action returns the canonical setup-required payload without requiring chain state
- **AND** `converse` relays that structured hold rather than generic failure prose

#### Scenario: unmigrated credentialed universe preserves its real fault
- **WHEN** assignment fields are absent and a readable vault contains an LLM credential or an explicit non-default legacy source
- **THEN** `universe_has_assigned_engine` remains true
- **AND** exhaustion is not retold as no-engine onboarding

#### Scenario: unreadable legacy state stays fail-safe
- **WHEN** an unmigrated or migrated vault/config is unreadable or unparseable
- **THEN** the helper returns true and logs the read failure
- **AND** setup instructions do not hide corrupt state

#### Scenario: bare exhaustion remains a hard failure
- **WHEN** `AllProvidersExhaustedError` has no `chain_state` because of policy, pin, or missing router
- **THEN** the setup mapper returns no payload
- **AND** the original error message remains visible

#### Scenario: migrated unassigned authority uses the typed hold path
- **WHEN** a migrated newborn has `unassigned + []`
- **THEN** provider routing raises `ProviderAuthorityHeldError`
- **AND** the typed mapper renders setup without widening bare exhaustion

#### Scenario: connector advertises only a completable first-class path
- **WHEN** a Tier-1 chatbot founder receives setup-required after cutover
- **THEN** at least one advertised accepted-market or previously bound host path is completable through the live connector
- **AND** raw API-key deposit and unavailable desktop-only paths are absent

#### Scenario: unavailable setup route blocks release
- **WHEN** a surface has no setup route that passes its end-to-end acceptance
- **THEN** provider-authority enforcement and newborn deny-all do not cut over on that surface
- **AND** a truthful but dead instruction is not considered product readiness
