## MODIFIED Requirements

### Requirement: Every role chain terminates at the local model
Every role's configured sequence SHALL terminate with `ollama-local`. Before
dynamic routing, a request/universe call SHALL pass the provider-authority gate
defined by this change. Only providers inside its non-empty
`effective_provider_authority` may enter role-chain filtering.
`ollama-local` is availability fallback, not authority fallback, and MUST NOT
be attempted when outside that set.

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
- **WHEN** role chains are constructed
- **THEN** `writer`, `judge`, `extract`, and `embed` each end in `ollama-local`
- **AND** execution filters each chain through authority before dynamic eligibility

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
unchanged except for their own authority gate.

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
inside the authorized and dynamically eligible chain. Every universe SHALL
persist `engine_assignment_state`, `engine_assignment_generation`, and
`allowed_providers`. `None` SHALL be accepted only by an offline pre-cutover
reader. Runtime, creation, and assignment SHALL use `[]` for `unassigned`,
`pending`, `held`, and `failed`, and a non-empty canonical list only for
`ready`. Assignment replaces rather than unions the prior ceiling.

Target `engine_source=requester_local` SHALL accept only an already-created
opaque credential binding reference. Service `anthropic` maps to
`claude-code`/`["claude-code"]`; service `openai` maps to
`codex`/`["codex"]`. Omitted writer is derived. Unknown/aliased/mismatched
service or writer, missing binding reference, and unsupported assignment
fields fail before mutation. This capability does not define raw-secret
ingress; `retire-mcp-provider-secret-deposit` owns its refusal.

`self_hosted_endpoint` and `host_daemon` remain held/deny-all until
`activate-requester-host-engines` proves endpoint or daemon, authenticated
account-to-host principal, and requester authority. `market_rented` remains
held/deny-all in the ordinary router for its entire lifecycle.

`effective_provider_authority` SHALL mean only the fresh assignment ceiling
after the exact live request capability or owner-defined background receipt
and binding tuple pass. Dynamic routing filters are not part of this term.
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

#### Scenario: requester-local assignments are singleton
- **WHEN** an authenticated requester assigns canonical `anthropic` or `openai` with a valid opaque binding reference
- **THEN** state is `ready`, generation increments once, and preference/ceiling equal the canonical singleton mapping

#### Scenario: invalid route has zero mutation
- **WHEN** assignment uses an unknown/aliased/mismatched route, lacks an opaque binding reference, or supplies unsupported assignment fields
- **THEN** it fails before journal, config, credential, ledger, or provider mutation

#### Scenario: non-executable source is held
- **WHEN** self-hosted, host-daemon, or market-rented intent lacks its owning activation proof
- **THEN** assignment is `held` with `allowed_providers=[]`
- **AND** endpoint, daemon, market, provider, or writer hints authorize nothing

#### Scenario: reassignment replaces authority
- **WHEN** a ready universe receives another valid assignment
- **THEN** new state/reference/preference/generation/ceiling replace the old transaction atomically
- **AND** stale contexts cannot retain the removed provider

#### Scenario: malformed assignment fails held
- **WHEN** state, generation, ceiling, binding reference/digest, transaction identity, journal, or admission lock is inconsistent or unreadable
- **THEN** routing holds before credential or provider access

#### Scenario: explicit context remains the configuration source
- **WHEN** an authorized call supplies explicit `UniverseContext` with resolved configuration
- **THEN** that context wins over process-global configuration
- **AND** authority is still derived from fresh server state rather than the context

#### Scenario: absent context preserves only non-request legacy behavior
- **WHEN** an enumerated host-local or local-only non-request operation supplies no explicit universe context
- **THEN** canonical process-global/default configuration fallback remains available
- **AND** a live request/universe operation with absent context holds instead

### Requirement: Judge ensemble fans out to all healthy judges in parallel
The judge ensemble SHALL fan out concurrently only to registered, healthy
judges inside a non-empty provider-authority set. A non-empty authorized set
with no healthy registered judge retains canonical empty/degraded behavior.
Authority-derived emptiness raises `ProviderAuthorityHeldError`.

#### Scenario: fan-out returns authorized responses
- **WHEN** multiple healthy registered judges are authorized
- **THEN** they run concurrently
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
kind and credential-authority class.

The provider layer SHALL add immutable non-serializable
`ProviderInvocation` and `ProviderLaunchHandle`. Every live-request call site
shall retain the exact current `ProviderRequestCapability`; background work
shall supply its owning server receipt. This change is the sole provider-layer
propagation owner.

Before each attempt, the router SHALL:

1. acquire shared `ProviderAssignmentAdmission`;
2. validate assignment journal/fence, generation, ceiling, and binding digest;
3. require the exact current request capability with mechanism
   `tinyassets.authenticated-request.v1`, issuer
   `tinyassets.auth.middleware`, principal matching current identity, and
   target universe matching the routed universe;
4. validate binding principal/universe/provider/host/generation/digest and
   non-empty, unexpired, non-tombstoned, non-revoked state; and
5. mint a router-token-bound `ProviderInvocation`.

Invocation SHALL contain request capability or owner-defined background
receipt, target universe, authenticated principal, admitted provider,
assignment generation, opaque binding reference/digest, credential/auth
provenance, credential kind, credential-authority class, immutable call
inputs, and router-only launch token. It MUST NOT contain native or recoverable
secret material.

Credential kinds SHALL be `llm_subscription`, `llm_api_key`, `local`, `none`,
or `unknown`. Credential-authority classes (the receipt field currently named
`authority_class`) SHALL be `universe`, `host`, `local`, `none`, or `unknown`.
`unknown` grants nothing; universe remote success cannot report host. These
values are captured at the exact execution boundary for the same call.

Every provider SHALL expose
`start(invocation) -> ProviderLaunchHandle`; the handle SHALL expose
`result() -> ProviderResponse` and idempotent close. Only executor-local
`start()` may revalidate and dereference the opaque binding, materializing
native secret only in provider child/request memory. It SHALL return after
transport owns a registered irreversible copy of launch inputs. Provider and
handle code thereafter MUST NOT reread config, vault, ambient environment, or
auth homes.

Launch timeout SHALL be distinct from model completion. Partial creation,
cancellation, timeout, result/close races, and crash recovery SHALL have one
terminal owner and secret-free launch ID. Unprovable cleanup SHALL install a
durable universe fence. Shared admission remains held through `start()` and
releases while result completion continues.

`HostLocalProviderCapability` MAY authorize only enumerated non-request
maintenance. It is bootstrap-minted, identity-validated, non-serializable,
mutually exclusive with request authority, and unavailable through API/MCP,
config/state, environment-derived request input, or caller construction.

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

#### Scenario: scheduling artifacts grant no provider authority
- **WHEN** a caller supplies admission/replay verdict, request receipt/result/event, priority grant, branch-task row, or queue claim/lease without the required capability/receipt
- **THEN** routing holds before provider or credential access

#### Scenario: host-local forgery fails
- **WHEN** request lineage supplies a boolean, string, enum, serialized token, lookalike, or genuine host token
- **THEN** routing holds without accessing maintainer resources

#### Scenario: invocation is reference-only
- **WHEN** requester-local authority succeeds
- **THEN** invocation contains opaque reference/digest and provenance
- **AND** contains no native/recoverable credential

#### Scenario: executor-local start owns dereference
- **WHEN** requester-local provider starts
- **THEN** only selected executor-local `start()` validates the complete binding tuple and dereferences
- **AND** native material exists only inside provider child/request memory

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
The bridge SHALL retry only transient `AllProvidersExhaustedError` under its
canonical bounded policy. `ProviderAuthorityHeldError` SHALL be re-raised
after one authority check and MUST NOT become retry, alternate provider, local
fallback, forced mock, judge sentinel, or fallback prose. Dynamic exhaustion,
unrelated exception identity, and missing-router behavior remain canonical.

#### Scenario: transient exhaustion clears
- **WHEN** an authorized dynamic chain exhausts and later succeeds within the bounded policy
- **THEN** the bridge returns the provider response

#### Scenario: bounded exhaustion uses explicit fallback
- **WHEN** all bounded authorized dynamic attempts exhaust and explicit fallback exists
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
- **THEN** canonical fallback/error behavior remains

## ADDED Requirements

### Requirement: Provider assignment admission is one exported cross-capability primitive
Provider routing SHALL export one `ProviderAssignmentAdmission` keyed by
canonical universe identity. It SHALL provide shared launch readers and
exclusive assignment/custody writers; callers MUST NOT choose lock paths.
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
classification when it aggregates immutable attempts/results.

#### Scenario: held authority is not provider fault
- **WHEN** authority-derived emptiness or binding mismatch raises `ProviderAuthorityHeldError`
- **THEN** same-call evidence reports `authority_held/authority_held`
- **AND** no provider attempt is attributed

### Requirement: Remote and requester-host activation stay outside ordinary routing
Accepted-market execution SHALL require the paid-market-economy accepted
agreement plus the distributed-execution B2 signed-remote protocol and the
sole production composition root required by anti-loss task B13 (`5.13`).
Distributed-execution V6 SHALL remain scoped to deterministic market selection,
escrow, verification, settlement, and reputation. Dark D0 records/seals SHALL
remain fake/test-only.

Self-hosted/host-daemon activation SHALL require
`activate-requester-host-engines` across `daemon-identity-and-host-pool`,
`desktop-host-runtime`, and source-specific provider routing. No live cutover
or legacy conversion may begin until requester-local opaque custody or that
requester-host route passes rendered end-to-end acceptance.

#### Scenario: market selection cannot mint execution authority
- **WHEN** V6 selects an accepted market host
- **THEN** only B2 plus the B13 production composition root may authorize execution
- **AND** ordinary provider routing remains deny-all

#### Scenario: existing founder home blocks unsafe cutover
- **WHEN** the live founder home has only raw-key or otherwise non-ready legacy state and no replacement ready path passes acceptance
- **THEN** deployment stops before quiescing legacy writers or enforcing the cutover
- **AND** no raw key is reclassified as an opaque reference
