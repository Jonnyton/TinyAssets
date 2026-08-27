## MODIFIED Requirements

### Requirement: Every role chain terminates at the local model
Every role's configured sequence SHALL terminate with `ollama-local`. Before
dynamic routing, a request/universe call SHALL pass the provider-authority gate
defined by this change. Only providers inside its non-empty
`effective_provider_authority` may enter role-chain filtering.
`ollama-local` is availability fallback, not authority fallback, and MUST NOT
be attempted when outside that set. Roles with no explicit chain SHALL default
to the `writer` chain. The system SHALL only stop for provider unavailability
when the authorized local model itself is also unavailable.
These new authority clauses are subject to the effective V2 gate
defined below; while dark, canonical role chains run unchanged.

After authority succeeds, subscription-only policy, role membership,
`llm_policy`, registration, auth health, cooldown, and quota retain their
canonical behavior. Emptiness caused by these dynamic filters is exhaustion,
not authority hold.

#### Scenario: writer routes to authorized local fallback
- **WHEN** authority includes `ollama-local`
- **AND** every earlier dynamically eligible authorized writer is unavailable
- **THEN** writer attempts `ollama-local`
- **AND** no provider outside authority is attempted

#### Scenario: chains cover the four canonical roles
- **WHEN** role chains are constructed or an unknown role is resolved
- **THEN** `writer`, `judge`, `extract`, and `embed` each end in `ollama-local`
- **AND** an unknown role uses the `writer` chain
- **AND** execution filters the chain through authority before dynamic eligibility

#### Scenario: local fallback cannot widen authority
- **WHEN** no authority-admitted provider remains before dynamic routing
- **THEN** routing raises `ProviderAuthorityHeldError`
- **AND** does not invoke the local model or inspect any provider

### Requirement: Hard writer pin disables fallback and fails loud
When `TINYASSETS_PIN_WRITER` is set, writer SHALL attempt only the pinned
provider after proving it is inside `effective_provider_authority`. A pin
outside authority SHALL fail held before provider lookup. A pin inside
authority that is unavailable or fails SHALL raise
`AllProvidersExhaustedError` without fallback. Non-writer roles remain
unchanged except for their own authority gate. Every pin exhaustion error
SHALL name the pinned provider and explain how to clear the pin.
The new authority check is subject to the effective V2 gate; while dark,
canonical pin behavior remains unchanged.

#### Scenario: pinned writer runs alone
- **WHEN** the pinned writer is authorized and dynamically eligible
- **THEN** writer attempts only that provider

#### Scenario: exhausted authorized pin fails loud
- **WHEN** the pinned writer is authorized but unavailable or fails
- **THEN** routing raises `AllProvidersExhaustedError` naming it
- **AND** does not fall through

#### Scenario: disallowed pin fails held
- **WHEN** the pinned writer is outside provider authority
- **THEN** routing raises `ProviderAuthorityHeldError`
- **AND** performs zero provider, credential, auth-health, or quota access

### Requirement: Per-universe engine preference and privacy allowlist
The router SHALL continue to resolve per-universe configuration from explicit
`universe_context` when supplied and otherwise from process-global universe
configuration only for legacy single-universe, host-local, or local-only
non-request paths. A live request/universe call SHALL NOT use process-global
fallback as authority.

`preferred_writer` and `preferred_judge` SHALL reorder only providers already
inside the authorized and dynamically eligible chain. Migration SHALL add
optional `engine_assignment_state` and `engine_assignment_generation`.
While either is absent or the effective per-universe V2 gate (global or
server-owned canary) is false, runtime
SHALL preserve shipped vault/source/read-failure classification,
`allowed_providers=None` no-op semantics, bare-exhaustion behavior, and
provider routing; it SHALL NOT enforce the target authority gate.

Only after the migration manifest and every surface gate pass under the
bounded canary may the global flag flip. For every effectively gated universe,
runtime, creation, and assignment SHALL persist state, generation, and
`allowed_providers`. It SHALL use `[]` for `unassigned`, `pending`, `held`,
`failed`, and remote-only `remote_ready`; only ordinary `ready` SHALL carry a
non-empty canonical list. `remote_ready` SHALL be valid only with
`engine_source="accepted_market"` and a current successor-issued B2/B13 grant.
An ordinary ready ceiling MUST be role-complete over every role with a live
provider call site: its intersection with each such canonical chain is
non-empty. Startup/CI inventory SHALL enumerate live `role=` call sites and
fail closed if any live role is outside the enforced set. A canonical role
with no live call site (currently `embed`) SHALL NOT block readiness; its first
live caller SHALL hold until its chain is covered.
Every provider in the ceiling SHALL have its own current entry in a non-secret
`provider_authority_bindings` map containing the provider-specific opaque
binding reference/digest and provenance required at the sink. Assignment
replaces rather than unions the prior ceiling and binding map.

Source resolution SHALL be total over shipped and target domains. Target
newborn/setup source `unassigned` SHALL remain `unassigned + []` with no
provider or credential access. Legacy
`byo_api_key` is read/migration-only: new writes are refused and it converts
to target `requester_local` only after
`retire-mcp-provider-secret-deposit` creates an opaque binding and atomically
writes the new source, service, cloud-provider binding entry, and
generation/digest. A cloud binding MUST NOT publish ready authority until its
same assignment transaction has enough separately authorized provider
bindings for every live role. Otherwise it
becomes `failed + []` only during the gated migration, never merely because
optional assignment fields are absent. `requester_local` service `anthropic`
maps writer preference to `claude-code`; service `openai` maps writer
preference to `codex`. Against current live call sites, `claude-code` alone is
not role-complete because it lacks judge/extract, while `codex` covers
writer/judge/extract and may be ready from its own valid cloud binding. The
dormant `embed` chain does not block either assignment until it gains a caller.

Legacy `host_daemon` migrates only through
`activate-requester-host-engines` to `founder_hosted_daemon`.
`self_hosted_endpoint`, `host_daemon`, `local_model`, and
`founder_hosted_daemon` remain held/deny-all until that successor proves the
endpoint/daemon/local model, requester authorization, and stable
authenticated account-to-host principal. The successor is the sole ready
writer for target `local_model`/`ollama`, which maps to
`ollama-local`/`["ollama-local"]`, and `founder_hosted_daemon`.
It may also publish an attested requester-owned `ollama-local` binding as the
role supplement for a requester-local cloud assignment through the same
`ProviderAssignmentAdmission`; the atomic compositor then publishes
`["claude-code", "ollama-local"]` only when every provider has its own valid
binding and every live role remains reachable. The local binding SHALL carry
its attested requester-host endpoint and execution-host identity.
`ProviderExecutor.start()` SHALL construct/select local transport solely from
that endpoint inside the matching requester-host execution scope. A
process-registered default, ambient `OLLAMA_HOST`, or loopback endpoint without
proof that the executor is the attested requester host SHALL fail held.
Maintainer-owned local compute is never a supplement.
`market_rented` remains held/deny-all in the ordinary router for its entire
lifecycle.

Target source `accepted_market` is remote-dispatch-only. It stores a separately
proven B2/B13 grant, publishes `engine_assignment_state="remote_ready"` with
`allowed_providers=[]`, and has no ordinary provider ceiling. Ordinary role
chains MUST NOT be consulted for it.
`activate-connector-requester-authority` SHALL own the pre-routing dispatch
seam that converts the grant into remote execution for `converse`; provider
routing holds when that seam or grant is absent, expired, revoked, or
inconsistent. Such a hold SHALL map to the successor's accepted-market
repair/renewal path. `universe_has_assigned_engine` SHALL remain fail-safe true
rather than classify the universe as engine-less, even before the owner
atomically downgrades stale `remote_ready` state to `held + []`.

Omitted writer is derived. Unknown/aliased/mismatched service or writer,
missing binding/host reference, and unsupported assignment fields fail before
mutation. This capability does not define raw-secret ingress; custody owns its
refusal and requester-local writer.

`effective_provider_authority` SHALL mean only the fresh ordinary assignment ceiling
after the exact live request capability or owner-defined background receipt
and binding tuple pass. Dynamic routing filters are not part of this term.
Accepted-market remote dispatch occurs before and outside this ordinary term.
An empty authority set raises `ProviderAuthorityHeldError`; dynamic exhaustion
after a non-empty authority set retains canonical
`AllProvidersExhaustedError`, chain-drain, retry, explicit fallback,
policy-fallback, and judge behavior.

#### Scenario: allowlist blocks third-party providers
- **WHEN** a ready assignment and valid request capability admit only `ollama-local`
- **THEN** writer attempts only `ollama-local`
- **AND** other providers are neither inspected nor attempted

#### Scenario: authority-derived emptiness holds
- **WHEN** assignment/capability/receipt/binding validation yields no authorized provider
- **THEN** routing raises `ProviderAuthorityHeldError`
- **AND** performs zero provider, credential, auth-health, or quota access

#### Scenario: subscription policy emptiness is exhaustion
- **WHEN** provider authority is non-empty but subscription-only policy removes every provider
- **THEN** routing retains canonical `AllProvidersExhaustedError`
- **AND** does not misclassify the result as an authority hold

#### Scenario: preferred writer and judge reorder without widening
- **WHEN** `preferred_writer` or `preferred_judge` is inside the authorized dynamic chain
- **THEN** it is attempted first for its role
- **AND** only remaining providers in the same authorized chain may follow

#### Scenario: cloud-only requester-local assignment stays held
- **WHEN** an authenticated requester assigns canonical `anthropic` with only its valid cloud binding
- **THEN** the cloud binding and writer preference may persist, but state remains `held` with `allowed_providers=[]`
- **AND** the assignment cannot become ready while any live role has no bound authorized destination

#### Scenario: OpenAI cloud binding covers current live roles
- **WHEN** an authenticated requester assigns canonical `openai` with a current valid Codex binding
- **THEN** it may become ready because Codex covers current live writer, judge, and extract call sites
- **AND** dormant embed does not block readiness but its first live caller holds until covered

#### Scenario: requester-owned role supplement makes cloud assignment ready
- **WHEN** the same universe has a valid cloud binding plus an attested requester-owned `ollama-local` binding
- **THEN** one atomic assignment publishes the matching cloud-plus-local ceiling and per-provider binding map
- **AND** every live role retains at least one bound authorized destination

#### Scenario: process-default local provider cannot supplement
- **WHEN** a proposed local binding lacks a requester endpoint or matching attested executor-host identity
- **THEN** assignment remains `held` with `allowed_providers=[]`
- **AND** process-default localhost, ambient `OLLAMA_HOST`, and maintainer compute are not invoked

#### Scenario: ceiling without complete provider bindings stays held
- **WHEN** a proposed ceiling contains any provider without its own current matching binding entry
- **THEN** assignment remains `held` with `allowed_providers=[]`
- **AND** no other provider's binding or maintainer resource substitutes

#### Scenario: attested local model makes canonical zero-cloud fallback reachable
- **WHEN** the host successor validates target `local_model` service `ollama` and its stable account-to-host binding
- **THEN** state is `ready` with `allowed_providers=["ollama-local"]`
- **AND** canonical role chains can terminate at the authorized local model

#### Scenario: accepted market dispatch bypasses ordinary chains
- **WHEN** a Tier-1 connector universe has a valid accepted-market B2/B13 grant
- **THEN** assignment is `remote_ready + []` and the successor-owned pre-routing seam dispatches `converse` remotely without an ordinary ceiling
- **AND** missing seam/grant holds rather than falling through to maintainer or desktop resources

#### Scenario: revoked accepted market grant is not engine-less
- **WHEN** `accepted_market` state has an absent, expired, revoked, or inconsistent B2/B13 grant
- **THEN** remote dispatch holds, the setup mapper offers accepted-market repair/renewal, and the owner downgrades it to `held + []`
- **AND** the fail-safe assigned-engine classifier stays true and no ordinary provider or generic engine-less path is used

#### Scenario: every shipped source has an explicit migration or hold
- **WHEN** source is `byo_api_key`, `self_hosted_endpoint`, `market_rented`, or `host_daemon`
- **THEN** routing follows its named conversion/activation owner or publishes held/failed deny-all
- **AND** no shipped value falls through to an implicit ready state

#### Scenario: invalid route has zero mutation
- **WHEN** assignment uses an unknown/aliased/mismatched route, lacks an opaque binding reference, or supplies unsupported assignment fields
- **THEN** it fails before journal, config, credential, ledger, or provider mutation

#### Scenario: non-executable source is held
- **WHEN** self-hosted, host-daemon, or market-rented intent lacks its owning activation proof
- **THEN** assignment is `held` with `allowed_providers=[]`
- **AND** endpoint, daemon, market, provider, or writer hints authorize nothing

#### Scenario: reassignment replaces authority
- **WHEN** a ready universe receives another valid assignment
- **THEN** new state/binding-map/preference/generation/ceiling replace the old transaction atomically
- **AND** stale contexts cannot retain the removed provider

#### Scenario: malformed assignment fails held
- **WHEN** state, generation, ceiling, per-provider binding map/digest, transaction identity, journal, or admission lock is inconsistent or unreadable
- **THEN** routing holds before credential or provider access

#### Scenario: explicit context remains the configuration source
- **WHEN** an authorized call supplies explicit `UniverseContext` with resolved configuration
- **THEN** that context wins over process-global configuration
- **AND** authority is still derived from fresh server state rather than the context

#### Scenario: absent context preserves only non-request legacy behavior
- **WHEN** an enumerated host-local or local-only non-request operation supplies no explicit universe context
- **THEN** canonical process-global/default configuration fallback remains available
- **AND** a live request/universe operation with absent context holds instead

### Requirement: Auth-health quarantine of dead-login subscription providers
When an auth-health probe is injected, the router SHALL drop a provider whose
subscription login is definitively `not_logged_in` from fallback chains,
policy attempt orders, and judge ensemble only after the non-empty provider
authority ceiling is established. The gate SHALL remain conservative:
`unknown` and `ok` stay and a probe exception means keep. When no probe is
injected, the gate SHALL remain an as-built no-op that quarantines nothing.
Authority intersection is subject to the effective V2 gate; while dark, the
canonical auth-health gate runs without target authority.

An authorized pinned writer with dead login SHALL fail loud rather than route
elsewhere. An authorized chain MAY fall through to `ollama-local` only when
`ollama-local` is inside the same effective authority ceiling with its own
valid binding. A chain with no remaining authorized writer SHALL exhaust
without using an unauthorized local provider.

#### Scenario: dead-auth writer is skipped only inside authority
- **WHEN** the probe reports an authorized `claude-code` as `not_logged_in` and another authorized writer remains
- **THEN** routing goes to that next authorized healthy provider
- **AND** no provider outside authority is inspected or attempted

#### Scenario: authorized unknown and local providers are never stranded
- **WHEN** authorized subscription writers report `not_logged_in` and authorized `ollama-local` reports `unknown`
- **THEN** routing falls through to `ollama-local`
- **AND** returns its response

#### Scenario: unauthorized local fallback cannot rescue dead auth
- **WHEN** the only authorized writer reports `not_logged_in` and `ollama-local` is outside authority
- **THEN** routing raises canonical dynamic exhaustion for that authorized provider
- **AND** does not attempt the local model

#### Scenario: pinned dead-auth writer fails loud
- **WHEN** an authorized pinned writer reports `not_logged_in`
- **THEN** routing raises `AllProvidersExhaustedError` referencing subscription login
- **AND** no other provider is called

### Requirement: Per-node policy routing honors llm_policy overrides
`call_with_policy` SHALL honor an explicit `llm_policy` dict by building an
attempt order from `difficulty_override` matched against the call difficulty,
then `preferred`, then `fallback_chain`, de-duplicated in that order. Before
subscription-only, allowlist, auth-health, registration, cooldown, or quota
filters, policy routing SHALL intersect that order with the same non-empty
`effective_provider_authority` as role routing.

A policy that names no authorized provider SHALL raise
`ProviderAuthorityHeldError` and MUST NOT fall through to a wider role chain.
After a non-empty authority intersection, an empty policy or dynamically
exhausted policy SHALL retain canonical fall-through to role-based `call()`,
which re-applies the same authority and dynamic gates. The method SHALL retain
its canonical `(response_text, provider_name_used, call_meta)` result.
The authority intersection/hold clauses are subject to the effective V2 gate;
while dark, canonical policy fall-through remains unchanged.

#### Scenario: preferred policy provider is tried first
- **WHEN** policy names an authorized, healthy preferred provider
- **THEN** it is attempted before authorized policy fallbacks
- **AND** the returned tuple reports it as provider used

#### Scenario: policy respects the privacy allowlist and authority ceiling
- **WHEN** policy names providers outside `allowed_providers`
- **THEN** they are not inspected or attempted
- **AND** routing continues only with authorized policy providers

#### Scenario: exhausted authorized policy falls through without widening
- **WHEN** policy has a non-empty authority intersection but its dynamic candidates exhaust
- **THEN** role-based `call()` runs under the same authority ceiling
- **AND** no provider outside that ceiling becomes eligible

#### Scenario: policy with no authorized destination holds
- **WHEN** policy contains no provider inside effective authority
- **THEN** routing raises `ProviderAuthorityHeldError`
- **AND** does not fall through to role routing

#### Scenario: policy routing returns response telemetry
- **WHEN** `call_with_policy` completes through a policy provider or authorized role fallback
- **THEN** it returns response text, provider used, and call metadata with model, family, latency, degraded state, and attempt count

### Requirement: Judge ensemble fans out to all healthy judges in parallel
The judge ensemble SHALL fan out concurrently only to registered, healthy
judges inside a non-empty provider-authority set. It SHALL call every such
registered, non-cooldown judge provider once, SHALL never call the same
provider twice, and SHALL return one response per provider that responds. A
non-empty authorized set with no healthy registered judge retains canonical
empty/degraded behavior. Authority-derived emptiness raises
`ProviderAuthorityHeldError`.
Authority intersection/hold clauses are subject to the effective V2 gate;
while dark, canonical judge behavior remains unchanged.

#### Scenario: fan-out returns authorized responses
- **WHEN** multiple healthy registered judges are authorized
- **THEN** each is called exactly once concurrently
- **AND** one response returns per successful authorized judge

#### Scenario: non-empty authorized ensemble retains empty behavior
- **WHEN** authority is non-empty but no included judge is healthy and registered
- **THEN** canonical empty-ensemble behavior remains

#### Scenario: authorized single judge may degrade
- **WHEN** exactly one authorized judge follows the canonical exhausted single-judge path
- **THEN** canonical degraded-sentinel behavior remains

#### Scenario: empty judge authority holds
- **WHEN** provider authority contains no judge
- **THEN** judge routing raises `ProviderAuthorityHeldError`
- **AND** returns neither ordinary empty ensemble nor degraded sentinel

### Requirement: Provider calls use one explicit immutable contract
The provider layer SHALL retain immutable `UniverseContext`, `ModelConfig`,
and `ProviderResponse`. `UniverseContext` SHALL retain optional universe
directory and resolved configuration. `ModelConfig` SHALL retain timeout,
token cap, temperature, reasoning effort, workspace-sandbox, allowed-tool, and
disallowed-tool settings. `ProviderResponse` SHALL retain text, provider,
model, family, latency, and degraded flag, and add exact call-local credential
fields `credential_kind` and `authority_class`.

Every `BaseProvider` implementation SHALL retain canonical async
`complete(prompt, system, config, *, universe_dir=None) -> ProviderResponse`.
The provider layer SHALL add immutable non-serializable
`ProviderAuthorityCarrier`, `ProviderInvocation`, and
`ProviderLaunchHandle`, plus an executor-local `ProviderExecutor`.

For a live non-deferred HTTP request, the TinyAssets-owned FastMCP
`Middleware.on_call_tool` hook SHALL read the current message strictly from
`mcp.server.lowlevel.server.request_ctx.get().request`, re-derive its bearer
identity, reserve one opaque dispatch token bound to the authenticated
principal, MCP session/request/tool, and owning message task, and structurally
await `call_next`. It SHALL fail closed when that per-message request is
absent and SHALL NOT use `get_http_request()` because its inherited
`_current_http_request` and snapshotted `_task_http_headers` fallbacks do not
prove current-message authority. The outer ASGI middleware's task-local
Context and the stateful session initialize Context MUST NOT mint or prove
provider authority. A task-augmented or otherwise deferred tool call SHALL
mint no request capability and SHALL hold until the background owner issues a
durable receipt.

The special anonymous wiki-canary bearer and
`_WikiCanaryExecutionAuthority` SHALL compose on the same FastMCP app without
minting provider request authority. Their anonymous principal, canary token,
and narrow operation SHALL NOT satisfy provider identity or carrier checks.

The TinyAssets wrapper created by `_register_structured_tool` SHALL claim the
reserve atomically on synchronous worker entry, after AnyIO selects the actual
thread, and bind one active message lease to that worker and exact invocation.
An async registered handler SHALL claim it in the owning message task before
handler entry. The reserve is non-authorizing, one-shot, and
non-serializable. Copied Context, stale session/message state, detached or
nested execution, and caller-supplied identities cannot claim or extend it.
Wrapper and per-message middleware `finally` paths SHALL revoke the claim
before releasing the result.

For provider work, `call_provider` SHALL retrieve the exact current
`ProviderRequestCapability` or successor-owned
`ProviderHostRequestCapability`, prove its server-owned message lease and
registered execution claim remain active, mint a sealed internal carrier, and
explicitly pass it
through internal-only arguments to `call_sync`, `call_with_policy_sync`,
retry/policy/judge branches, the router `ThreadPoolExecutor` closure, and
invocation minting. This SHALL NOT depend on a copied ContextVar alone or on
ContextVar propagation into the router pool worker. Inherited asyncio
ContextVars SHALL NOT extend the lease or pass the message/claim check.
API/MCP schemas, caller kwargs, request/universe
payloads, serialized state, and ambient worker context MUST NOT construct or
populate the carrier.

For remote HTTP providers, a provider binding SHALL NOT substitute for or
duplicate outbound authority. `ProviderExecutor.start()` SHALL also consume
the current user-owned, per-universe connection grant and credential-blind
daemon-side proxy owned by `outbound-boundary-layer`. Missing, expired,
revoked, or ambiguous outbound authority SHALL hold before provider or
credential access without host, maintainer, or ambient fallback.

Background, resumed, scheduled, daemon, RAPTOR, reflexion, retrieval, and
post-response graph work SHALL supply a server-owned
`ProviderWorkAuthorityReceipt` defined by
`harden-background-provider-execution-authority`. That owner SHALL define two
closed receipt variants. Universe work binds
principal/actor/run/branch/universe/operation, generation/digest, and bounded
lifetime across thread/task/process bridges. Universe-less maintainer
maintenance binds host/operator principal, exact operation, fixed private
prompt digest, and bounded lifetime; it carries no universe, run, branch,
requester identity, requester quota, or requester content. Before that owner
lands, those paths SHALL hold. This change remains the sole provider-layer
carrier/sink owner.

All target carrier/sink enforcement SHALL remain dark while the effective V2
gate (global flag or server-owned isolated-canary listing) does not apply to
the routed universe. Dark-mode code MAY mint, validate, inventory, and emit
non-authorizing diagnostics, but MUST preserve every shipped provider call,
helper, default, exception, and fallback result.

Before each attempt, the router SHALL:

1. acquire shared `ProviderAssignmentAdmission`;
2. validate assignment journal/fence, generation, ceiling, and binding digest;
3. require the exact explicitly carried request capability with mechanism
   `tinyassets.authenticated-request.v1`, issuer
   `tinyassets.auth.middleware`, principal matching the authenticated
   transport identity captured by the carrier, and target universe matching
   the routed universe; recheck its server-owned liveness lease immediately
   before minting invocation; or validate the exact attested host-request
   capability with mechanism `tinyassets.attested-host-request.v1`, issuer
   `activate-requester-host-engines`, and its local
   principal/host/session/universe/generation tuple; or validate the exact
   background receipt from its owner;
4. select the admitted provider's binding-map entry and validate its
   principal/universe/provider/host/generation/digest plus non-empty,
   unexpired, non-tombstoned, non-revoked state; and
5. mint a router-token-bound `ProviderInvocation`.

Universe-less maintainer maintenance is a closed exception to the
universe-assignment fields in steps 1, 2, and 4, not to sink validation. It
MUST NOT enter `call_provider`, policy routing, role chains, or a universe
assignment. Its owner SHALL instead revalidate the receipt against a separate
host/operator-owned maintenance binding for the exact provider, operation,
private-prompt digest, and maintenance budget immediately before minting the
invocation. Missing or stale receipt/binding holds before auth access or
completion.

Invocation SHALL contain exactly one HTTP request capability, attested
host-request capability, or owner-defined background receipt; authenticated
principal and admitted provider;
target universe and assignment generation for universe/host work, or neither
field for the closed universe-less maintenance variant; opaque binding
reference/digest, credential/auth
provenance, `credential_kind`, `authority_class`, immutable call inputs, and
router-only launch token. It MUST NOT contain native or recoverable
secret material.

Credential kinds SHALL be `llm_subscription`, `llm_api_key`, `local`, `none`,
or `unknown`. `authority_class` SHALL be `universe`, `host`, `local`, `none`,
or `unknown`.
`unknown` grants nothing; universe remote success cannot report host. These
values are captured at the exact execution boundary for the same call.

`ProviderExecutor.start(invocation) -> ProviderLaunchHandle`; the handle SHALL
expose `result() -> ProviderResponse` and idempotent close.
`ProviderExecutor.start()` SHALL be the sole provider-layer validator of the
complete binding tuple and the sole coordinator that invokes the selected
provider's canonical `complete(...)`. For CLI, local, and in-process
transports, only executor-local `start()` MAY dereference the opaque binding,
materializing native secret only in provider child/request memory. For remote
HTTP, it SHALL NOT dereference or perform network I/O; it SHALL obtain a
non-serializable handle bound to the current outbound grant and credential
reference, bind that handle to an executor-scoped provider instance, and call
canonical `complete(...)` with redacted request data. The outbound proxy alone
SHALL resolve the credential and perform the HTTP request. `start()` SHALL
return after the selected transport owns a registered irreversible copy of
launch inputs. Provider and handle code thereafter MUST NOT reread config,
vault, ambient environment, or auth homes.

Launch timeout SHALL be distinct from model completion. Partial creation,
cancellation, timeout, result/close races, and crash recovery SHALL have one
terminal owner and secret-free launch ID. Unprovable cleanup SHALL install a
durable universe fence. Shared admission remains held through `start()` and
releases while result completion continues.

`HostLocalProviderCapability` MAY authorize only
`subscription_auth_probe`, `local_model_readiness_probe`, or
`sandbox_readiness_probe`. Those operations accept no user prompt, mutate no
universe/branch, invoke no model completion, spend no quota, and cannot mint a
`ProviderInvocation`. `subscription_auth_probe` covers only non-completion
credential inspection.

The shipped completion-based refresh-viability probe using
`_AUTH_PROBE_PROMPT` is not host-local. It SHALL hold until
`harden-background-provider-execution-authority` issues a bounded maintenance
`ProviderWorkAuthorityReceipt` bound to the host/operator principal, exact
operation, fixed private prompt digest, and bounded lifetime, or it is
replaced by a proven zero-output probe. The receipt SHALL contain no universe,
run, branch, requester identity, requester quota, or requester content. The
probe MUST NOT run on ambient maintainer authentication outside that receipt.
The host-local capability is bootstrap-minted, identity-validated,
non-serializable, mutually exclusive with request/work authority, and
unavailable through API/MCP, config/state, environment-derived request input,
or caller construction. Startup/CI closure SHALL fail if any other host-local
operation exists.

#### Scenario: interleaved universes remain isolated
- **WHEN** A and B interleave provider calls
- **THEN** each launch uses its own current capability, principal, universe, generation, provider, binding, provenance, and inputs
- **AND** neither can inherit the other's authority

#### Scenario: authentic A capability cannot spend B binding
- **WHEN** a valid request capability for principal/universe A is presented on routed universe B with the same provider
- **THEN** sink subject/binding checks raise `ProviderAuthorityHeldError`
- **AND** B's credential is not dereferenced

#### Scenario: authentic principal cannot cross assignment generation
- **WHEN** the same principal presents authority captured before a new assignment generation
- **THEN** the fresh generation/digest check holds before dereference

#### Scenario: absent request capability holds
- **WHEN** live request/universe work lacks the exact current capability
- **THEN** no global universe, actor, process identity, or environment value substitutes

#### Scenario: request authority crosses the router pool explicitly
- **WHEN** `call_sync` submits provider routing to its class-level thread pool
- **THEN** its closure carries the exact internal capability object retrieved by `call_provider`
- **AND** an unset worker ContextVar neither widens authority nor causes a valid request to lose its carrier

#### Scenario: stateful HTTP session derives current message authority
- **WHEN** a streamable-HTTP session processes initialize and later tool calls in its long-lived server task
- **THEN** each non-deferred `tools/call` re-derives identity strictly from its per-message `request_ctx` HTTP request and receives a distinct session/request/tool-bound reserve
- **AND** the initialize or prior-message Context snapshot and revoked lease authorize nothing

#### Scenario: request fallback and deferred dispatch hold
- **WHEN** per-message request context is absent, inherited/snapshotted headers remain, or tool execution is task-augmented/deferred
- **THEN** no request capability or carrier is minted
- **AND** provider work holds unless the background owner separately issues and revalidates its durable receipt

#### Scenario: synchronous MCP tool dispatch claims on worker entry
- **WHEN** per-message middleware reserves authority and FastMCP invokes the TinyAssets registered wrapper through AnyIO
- **THEN** the wrapper claims the one-shot reserve against its actual worker identity on entry while the message task awaits `call_next`
- **AND** a detached child, copied reserve, second claimant, stale worker, or caller-supplied identity cannot mint a carrier

#### Scenario: attested local request uses the same sealed carrier boundary
- **WHEN** local stdio/SSE supplies a live `ProviderHostRequestCapability`
- **THEN** the carrier and sink bind its exact installation principal, host, session, universe, and assignment generation
- **AND** it cannot substitute for HTTP request or background authority

#### Scenario: inherited child context is not request liveness
- **WHEN** an asyncio child inherits identity/capability ContextVars from the request
- **THEN** it cannot mint a carrier because its execution scope is not the registered owner
- **AND** after request completion the revoked server lease also fails at the sink

#### Scenario: post-response work requires its durable owner receipt
- **WHEN** graph, resume, schedule, daemon, retrieval, or other background work reaches routing after request middleware returned
- **THEN** routing requires a fresh `ProviderWorkAuthorityReceipt` from its named owner
- **AND** missing, caller-supplied, expired, stale-generation, or wrong-lineage receipts hold

#### Scenario: scheduling artifacts grant no provider authority
- **WHEN** a caller supplies admission/replay verdict, request receipt/result/event, priority grant, branch-task row, or queue claim/lease without the required capability/receipt
- **THEN** routing holds before provider or credential access

#### Scenario: host-local forgery fails
- **WHEN** request lineage supplies a boolean, string, enum, serialized token, lookalike, or genuine host token
- **THEN** routing holds without accessing maintainer resources

#### Scenario: host-local operation set is closed and zero-output
- **WHEN** host-local maintenance is requested
- **THEN** it is one of the three named probe operations and cannot invoke completion or consume quota
- **AND** inventory fails for any additional operation

#### Scenario: completion-based auth viability is background maintenance
- **WHEN** the shipped `_AUTH_PROBE_PROMPT` refresh-viability completion is requested
- **THEN** a host-local capability cannot run it
- **AND** it requires the background owner's exact universe-less host/operator, operation, private-prompt-digest, and lifetime-bound maintenance receipt or a zero-output replacement

#### Scenario: invocation is reference-only
- **WHEN** requester-local authority succeeds
- **THEN** invocation contains opaque reference/digest and provenance
- **AND** contains no native/recoverable credential

#### Scenario: executor owns validation and transport selection
- **WHEN** a requester-local provider starts
- **THEN** only `ProviderExecutor.start()` validates the complete binding tuple and coordinates canonical provider invocation
- **AND** CLI/local/in-process transports dereference only in executor child/request memory, while remote HTTP uses only the outbound owner's grant-bound credential-blind proxy handle

#### Scenario: remote HTTP secret and network ownership is singular
- **WHEN** an authorized remote HTTP provider is selected
- **THEN** the executor-scoped provider sends a redacted request through the outbound proxy handle
- **AND** only the outbound proxy resolves the credential reference and performs network I/O

#### Scenario: direct provider bypass holds
- **WHEN** provider code is invoked without router launch token
- **THEN** it holds before credential or transport work

#### Scenario: stale context cannot widen quarantine
- **WHEN** an older context reaches admission after state/generation/ceiling narrows
- **THEN** fresh state holds or uses only the newer authority

#### Scenario: launch freezes authority
- **WHEN** `start()` returns a registered handle
- **THEN** transport owns every required input and no later authority reread occurs

#### Scenario: failed cleanup fences
- **WHEN** launch cleanup cannot be proven after timeout/cancellation/crash
- **THEN** a durable fence blocks routing and assignment until recovery

#### Scenario: result and close have one terminal owner
- **WHEN** completion, timeout, cancellation, close, or recovery race
- **THEN** exactly one terminal transition owns transport cleanup/outcome
- **AND** others receive the cached outcome

#### Scenario: response preserves original evidence plus classifications
- **WHEN** a provider completes
- **THEN** response carries canonical text/provider/model/family/latency/degraded fields and same-call classifications
- **AND** process-global last-provider state cannot attribute them

#### Scenario: absent context preserves single-universe non-request behavior
- **WHEN** an enumerated non-request operation supplies no explicit context
- **THEN** canonical single-universe/default configuration fallback remains
- **AND** it does not mint request authority

### Requirement: The provider call bridge retries only transient full-chain exhaustion
The bridge SHALL retry only transient `AllProvidersExhaustedError` up to three
total router attempts with exponential waits bounded from two through eight
seconds. `ProviderAuthorityHeldError` SHALL be re-raised after one authority
check and MUST NOT become retry, alternate provider, local fallback, forced
mock, judge sentinel, or fallback prose. The bridge SHALL NOT retry unrelated
exceptions. After failure or when no router exists, it SHALL return the
caller-supplied fallback response when present and otherwise re-raise the
original unrelated error, or raise `AllProvidersExhaustedError` for exhaustion
or a missing router, rather than synthesize empty prose.
`ProviderAuthorityHeldError` handling is subject to the effective V2 gate;
while dark, the canonical bridge never receives that new authority error.

#### Scenario: transient exhaustion clears
- **WHEN** an authorized dynamic chain exhausts and later succeeds within the bounded policy
- **THEN** the bridge returns the provider response within three total attempts

#### Scenario: bounded exhaustion uses explicit fallback
- **WHEN** all three authorized dynamic attempts exhaust and explicit fallback exists
- **THEN** canonical fallback behavior remains

#### Scenario: exhaustion without fallback fails loudly
- **WHEN** all bounded authorized dynamic attempts exhaust without fallback
- **THEN** `AllProvidersExhaustedError` is raised

#### Scenario: unrelated exception is not retried
- **WHEN** routing raises an exception other than transient exhaustion
- **THEN** its type and canonical retry behavior are preserved

#### Scenario: authority hold never becomes provider fallback
- **WHEN** routing raises `ProviderAuthorityHeldError`
- **THEN** the bridge re-raises it without retry or provider/fallback text

#### Scenario: no router preserves canonical non-authority behavior
- **WHEN** no router exists on an enumerated non-request path
- **THEN** the bridge returns supplied fallback immediately or raises `AllProvidersExhaustedError`

### Requirement: Bubblewrap readiness is a cached two-stage provider probe that selects ordinary Codex mode
`tinyassets.providers.base.probe_sandbox_available` SHALL return a dictionary
with `bwrap_available` and `reason`. It SHALL report unavailable immediately on
win32, when `bwrap` is absent from `PATH`, when `bwrap --version` exits
nonzero, when a minimal `bwrap --ro-bind / / /bin/sh -c true` launch exits
nonzero, or when either subprocess attempt raises; each subprocess SHALL have
a five-second timeout. It SHALL report available with a null reason only when
both subprocesses exit zero.

`get_sandbox_status` SHALL lazily cache and return the first probe dictionary
for the remainder of the process. It returns that same mutable dictionary,
does not refresh it, and does not copy it.

When `ProviderExecutor.start()` selects an ordinary `CodexProvider.complete`
call, `bwrap_available` truthy SHALL select `--full-auto`, while falsey SHALL
select `--dangerously-bypass-approvals-and-sandbox`; both modes also include
`--skip-git-repo-check` and `--ephemeral`. An invocation whose canonical
`ModelConfig` has `sandbox_workspace=True` SHALL refuse before probing or
selecting either mode. This probe is a CLI-readiness heuristic, not an OS
backend or proof that the subsequent workload is confined. In particular, an
unavailable ordinary call bypasses Codex approvals and sandboxing rather than
failing closed.

#### Scenario: successful version and functional probes select full-auto
- **WHEN** `bwrap` is found and its version and minimal launch subprocesses both exit zero
- **THEN** the first cached result is `{"bwrap_available": true, "reason": null}`
- **AND** an ordinary Codex call includes `--full-auto` and omits `--dangerously-bypass-approvals-and-sandbox`

#### Scenario: an unavailable probe selects the dangerous bypass
- **WHEN** the cached probe is false because of win32, a missing executable, a nonzero version or launch result, or a probe exception
- **THEN** an ordinary Codex call includes `--dangerously-bypass-approvals-and-sandbox` and omits `--full-auto`
- **AND** the result carries a reason for the unavailable classification

#### Scenario: repeated status reads retain the first mutable result
- **WHEN** `get_sandbox_status` is called repeatedly and a caller mutates the returned dictionary
- **THEN** the underlying probe is invoked once
- **AND** every read returns the same cached dictionary, including the mutation

#### Scenario: founder-facing sandbox configuration refuses before mode selection
- **WHEN** a Codex invocation has `sandbox_workspace=True`
- **THEN** it raises `ProviderError` before consulting Bubblewrap readiness
- **AND** no Codex subprocess is started

### Requirement: Recognized provider CLI sandbox failures are loud only after earlier quick-exit classification
On non-win32 paths, `tinyassets.providers.base.check_bwrap_failure` SHALL
case-insensitively recognize `bwrap: No permissions to create a new
namespace`, `bwrap: No permissions to create new namespace`, `bwrap: No such
file or directory`, and `sandbox initialization failed`. A match SHALL raise
the provider-layer `SandboxUnavailableError` with at most the first 400 stderr
characters and three remediation options. Empty or unmatched text SHALL pass.
On win32 the helper SHALL be a no-op.

When `ProviderExecutor.start()` selects Claude text completion, Claude JSON
completion, or Codex completion, the selected canonical `complete()` path
SHALL pass stderr through this helper when control reaches its
post-communicate sandbox check, including an exit-zero invocation that emitted
a recognized failure. The check does not dominate every error path: each CLI
provider's quick return-code-1 classification at elapsed time under five
seconds occurs first and raises `ProviderUnavailableError`, so such a
Bubblewrap failure is not guaranteed to retain the sandbox-specific type.

#### Scenario: a recognized exit-zero stderr failure raises the provider sandbox error
- **WHEN** a provider invocation reaches the sandbox check with any recognized signature in mixed-case stderr
- **THEN** it raises `tinyassets.providers.base.SandboxUnavailableError`
- **AND** the error carries a bounded stderr excerpt and remediation guidance

#### Scenario: normal output and win32 do not trigger the recognizer
- **WHEN** stderr is empty or unmatched, or the process platform is win32
- **THEN** `check_bwrap_failure` returns without raising a sandbox error

#### Scenario: a return-code-1 failure under five seconds is classified before sandbox recognition
- **WHEN** a CLI invocation exits one under five seconds with text that also matches a sandbox signature
- **THEN** the earlier quick-exit path raises `ProviderUnavailableError`
- **AND** the sandbox recognizer does not retroactively replace that type

## ADDED Requirements

### Requirement: Target provider authority enforcement has one global dark gate
`TINYASSETS_PROVIDER_AUTHORITY_V2` SHALL default false. A server-owned
`TINYASSETS_PROVIDER_AUTHORITY_V2_CANARY_UNIVERSES` set SHALL default empty
and SHALL contain only isolated acceptance-test universe IDs with a complete
migration manifest and ready surface path. A separate server-owned
`TINYASSETS_PROVIDER_AUTHORITY_V2_CANARY_PRINCIPALS` set SHALL default empty
and contain only isolated test principals proven to have no existing home or
universe. When such a principal performs public/first-contact birth, the
server SHALL register the generated canonical universe ID in a private canary
registry durably before target birth initialization or visibility. The
secret-free registry SHALL reload across process restart. After birth,
enforcement keys only on the registered universe ID, not on principal alone.
A registration whose birth transaction does not commit SHALL be removed
durably before the failure returns. Startup reconciliation SHALL remove a
registered ID only when the corresponding universe is provably absent. An
unreadable or unavailable universe store SHALL preserve the entry, hold
routing, and emit an operator diagnostic rather than infer absence.

Target enforcement is active for a universe only when the global flag is true
or its canonical ID is in configured/registered server-owned canary state.
Request, actor, universe config, MCP input, or other caller data MUST NOT
populate or widen either canary set or the private registry.

While neither gate applies to a universe, every new
authority, carrier, assignment-state, hold, retry, pin, policy, judge,
auth-health, launch, birth, and setup clause in this change SHALL remain
observational/non-authorizing and preserve shipped runtime behavior.
Requirements in this delta MUST NOT be read independently as enabling target
enforcement while the global gate is dark.

The flag SHALL flip only after the complete legacy manifest, all three named
successors, every provider-bridge classification, and Tier-1/Tier-2/Tier-3/
plugin acceptance gates pass under the bounded canary. Flip, post-cutover
defaults, newborn deny-all, and target enforcement SHALL deploy atomically
with a rollback receipt. Canary cleanup SHALL remove the isolated test
universes, principal entries, and registered IDs; it MUST NOT migrate an
existing user universe merely to obtain pre-flip proof.

#### Scenario: dark target preserves existing calls and births
- **WHEN** `TINYASSETS_PROVIDER_AUTHORITY_V2=false` and the universe is absent from configured/registered server-owned canary state
- **THEN** existing provider calls, defaults, births, helpers, exceptions, retries, fallbacks, pins, policy, judges, and auth health retain shipped results
- **AND** target carrier/assignment diagnostics grant no authority

#### Scenario: dark legacy engine assignment gains no new auth precondition
- **WHEN** the effective V2 gate is dark and any production-authenticated or development-mode caller passes the shipped `set_engine` dispatch gate and universe write ACL as enforced by that configured auth mode
- **THEN** every accepted legacy source/service retains its shipped mutation and readiness behavior
- **AND** this change adds no independent authentication, founder-only, or destination-ceiling precondition

#### Scenario: full enforcement cannot partially flip
- **WHEN** any migration, successor, bridge inventory, or surface acceptance gate is incomplete
- **THEN** the flag remains false and target defaults/enforcement remain dark
- **AND** no individual requirement enables a partial cutover outside configured/registered isolated-canary state

#### Scenario: bounded canary proves post-flip behavior
- **WHEN** a canonical isolated test universe with a complete manifest and ready path is listed by server-owned canary configuration
- **THEN** every target clause applies coherently to that universe as it would after the global flip
- **AND** unlisted universes retain shipped behavior and cannot opt themselves in

#### Scenario: isolated principal bootstraps generated-ID birth proof
- **WHEN** a preflight-clean isolated test principal with no home or universe performs public or first-contact birth
- **THEN** the server registers the generated ID before target initialization and visibility
- **AND** the principal cannot opt an existing or caller-selected universe into canary enforcement

### Requirement: Provider assignment admission is one exported cross-capability primitive
Provider routing SHALL export one `ProviderAssignmentAdmission` keyed by
canonical universe identity. It SHALL provide shared launch readers and
exclusive assignment/custody writers; callers MUST NOT choose lock paths.
This requirement is subject to the effective V2 gate. While dark, admission
may inventory/advisory-check only and MUST preserve shipped call, assignment,
custody, and lock results without introducing a new refusal.
Global acquisition order SHALL be assignment admission before credential
index/keyring locks. Reverse acquisition and untracked reentrancy SHALL fail
loud. Exclusive custody operations SHALL verify expected assignment generation
and credential-record digest. Shared launch admission SHALL verify the same
generation/digest and remain held through executor-local `start()`.

#### Scenario: custody compare-delete serializes with launch
- **WHEN** legacy retirement obtains exclusive assignment admission
- **THEN** it verifies expected generation/digest before narrower custody locks
- **AND** no launch reader can dereference the retiring binding concurrently

#### Scenario: launch reader freezes the same binding
- **WHEN** launch obtains shared admission
- **THEN** it validates current generation/digest and crosses `start()` before release
- **AND** a waiting assignment/custody writer cannot mix new authority into that launch

#### Scenario: reverse lock order is rejected
- **WHEN** code holding a custody index/keyring lock attempts to acquire assignment admission
- **THEN** acquisition fails loud before waiting or mutating

### Requirement: Provider authority holds are distinct execution evidence
The provider boundary SHALL classify an authority denial as
`outcome=authority_held` and `route_condition=authority_held`. It MUST NOT
classify `ProviderAuthorityHeldError` as provider `error`,
`provider_error`, exhaustion, fallback, mock, or degraded sentinel. The
separate provider-attempt receipt owner SHALL consume this exact typed
classification and extend its closed enums when it aggregates immutable
attempts/results. `identity-auth-and-access-control` SHALL own the canonical
authority/setup contract for `engine_setup_required_payload`;
`universe-creation` SHALL implement its action-layer rendering. Provider
routing does not define a second user-facing envelope.

On merge, this requirement supersedes the merged active
`universe-creation` clause that admits a caller-built eligible-provider bundle
and its same-capability `Missing or partial authority holds execution after
birth` clause that unconditionally advertises raw BYOC/accepted-market paths
and names fulfillment as receipt `authority_class`,
and the merged active `provider-attempt-receipts` closed enums that omit
`authority_held`. The receipt clause that maps otherwise-unrelated exceptions
to `outcome=error` / `route_condition=provider_error` SHALL explicitly exclude
`ProviderAuthorityHeldError`. Those sibling changes MUST adapt before
archive/sync into `openspec/specs/`, regardless of archive order.

#### Scenario: held authority is not provider fault
- **WHEN** authority-derived emptiness or binding mismatch raises `ProviderAuthorityHeldError`
- **THEN** same-call evidence reports `authority_held/authority_held`
- **AND** no provider attempt is attributed

### Requirement: Remote and requester-host activation stay outside ordinary routing
Accepted-market execution SHALL require the paid-market-economy accepted
agreement plus the distributed-execution signed-remote protocol defined by
design Decision B2 and the sole production composition root required by
anti-loss task B13 (`5.13`).
Distributed-execution V6 SHALL remain scoped to deterministic market selection,
escrow, verification, settlement, and reputation. Dark D0 records/seals SHALL
remain fake/test-only.

Self-hosted/host-daemon/local-model activation SHALL require
`activate-requester-host-engines` across `daemon-identity-and-host-pool`,
`desktop-host-runtime`, `identity-auth-and-access-control`, and
source-specific provider routing. That successor SHALL mint the separate
attested `ProviderHostRequestCapability` for interactive local stdio/SSE.
No live cutover or legacy conversion may begin until a Tier-1 chatbot user can
complete an advertised accepted-market path through
`activate-connector-requester-authority`; Tier-2
tray, Tier-3 OSS stdio, and Claude-plugin users can mint local host-request
authority and complete host/local execution; the typed held payload advertises
only surface-live paths; and every background/run/scheduled/daemon provider
bridge carries a valid receipt. A fully held local surface MUST NOT count as
safe cutover.

#### Scenario: market selection cannot mint execution authority
- **WHEN** V6 selects an accepted market host
- **THEN** only B2 plus the B13 production composition root may authorize execution
- **AND** ordinary provider routing remains deny-all

#### Scenario: existing founder home blocks unsafe cutover
- **WHEN** the live founder home has only raw-key or otherwise non-ready legacy state and no replacement ready path passes acceptance
- **THEN** deployment stops before quiescing legacy writers or enforcing the cutover
- **AND** no raw key is reclassified as an opaque reference

#### Scenario: held local install blocks cutover
- **WHEN** tray, OSS stdio, or Claude-plugin local runtime cannot mint its attested host-request capability
- **THEN** post-cutover readiness fails for that surface
- **AND** deny-all safety is not misreported as a working local product
