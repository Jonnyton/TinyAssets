## MODIFIED Requirements

### Requirement: Every role chain terminates at the local model
The provider router (`tinyassets/providers/router.py`) SHALL define a fallback
chain for each LLM role (`writer`, `judge`, `extract`, `embed`) that ends at the
`ollama-local` provider, so a call with non-empty effective authority can keep
producing output with zero cloud providers reachable when `ollama-local` is
inside that authority. Roles with no explicit chain SHALL default to the
`writer` chain. The system SHALL stop for ordinary provider unavailability only
when the local model itself is also unavailable or excluded by narrower policy.
An empty effective assignment/request authority intersection is not ordinary
provider unavailability and SHALL raise `ProviderAuthorityHeldError` before
local or cloud access.

#### Scenario: writer routes to local when all permitted cloud providers are gone
- **WHEN** a `writer` call has non-empty effective authority containing
  `ollama-local` and every permitted non-local provider is unregistered, in
  cooldown, or filtered out by narrower policy
- **THEN** the router attempts `ollama-local`
- **AND** returns its response instead of raising

#### Scenario: chains cover the four canonical roles
- **WHEN** the router resolves a chain for `writer`, `judge`, `extract`, or
  `embed`
- **THEN** the configured chain ends with `ollama-local`
- **AND** an unknown role name resolves to the `writer` chain

#### Scenario: local fallback cannot widen authority
- **WHEN** `ollama-local` is outside the effective assignment/request
  intersection
- **THEN** local is not attempted even when every cloud provider fails
- **AND** an empty effective intersection raises
  `ProviderAuthorityHeldError`

### Requirement: Hard writer pin disables fallback and fails loud
When `TINYASSETS_PIN_WRITER` is set, the `writer` chain SHALL be narrowed to
that single provider with NO fallback, but the pin MUST NOT add that provider
to either assignment or request authority. If the pin is outside the effective
authority intersection, the router SHALL raise
`ProviderAuthorityHeldError`. If the permitted pinned provider is exhausted,
disabled by subscription-only policy, or has dead subscription login, the
router SHALL raise `AllProvidersExhaustedError`. Neither error may silently
route elsewhere. The error message SHALL name the pinned provider and how to
clear the pin without disclosing authority or credential material.

#### Scenario: pinned writer runs alone
- **WHEN** `TINYASSETS_PIN_WRITER=codex`, Codex is inside effective authority,
  and Codex is healthy
- **THEN** only `codex` is attempted for `writer` calls
- **AND** no fallback provider is attempted

#### Scenario: exhausted permitted pin fails loud
- **WHEN** the pinned writer is inside effective authority but fails or is
  unavailable
- **THEN** the router raises `AllProvidersExhaustedError` naming the pinned
  provider
- **AND** does not fall through to the default chain

#### Scenario: disallowed pin fails held
- **WHEN** the pinned writer is outside the assignment/request authority
  intersection
- **THEN** the router raises `ProviderAuthorityHeldError` with zero provider,
  credential, auth-health, or quota access
- **AND** the pin does not widen either authority set

### Requirement: Per-universe engine preference and privacy allowlist
The router SHALL apply per-universe configuration resolved from an explicit
`universe_context` when supplied, otherwise from the process-global universe
config. `preferred_writer` / `preferred_judge` SHALL reorder the chain so the
preferred provider is tried first (a no-op if absent from the chain). The
`allowed_providers` list SHALL be a replacement-only provider-destination
authority ceiling and SHALL filter every role, policy, pin, ensemble, fallback,
and retry attempt down to permitted canonical providers. `None` is a
pre-cutover legacy encoding only and MUST NOT be accepted by the post-cutover
runtime. `[]` is explicit deny-all, and a non-empty list permits only its
canonical provider identifiers. Every new universe and every `set_engine`
transition MUST publish an explicit ceiling. Scalar, duplicate, mixed-entry,
unknown, or aliased ceilings MUST fail closed before provider, credential,
auth-health, or quota access.

Each universe SHALL persist `engine_assignment_state` as exactly `unassigned`,
`pending`, `ready`, `held`, or `failed`. `ready` requires a non-empty canonical
ceiling; every other state requires `[]`. When effective authority is empty,
single-role, policy, and ensemble calls SHALL raise
`ProviderAuthorityHeldError`, which the provider bridge MUST NOT convert to
fallback prose. The ordinary judge-ensemble empty-list result remains reserved
for a non-empty authority set with no healthy registered judge. No role may
leak to a disallowed provider.

`set_engine` SHALL publish the following ceilings:

- BYO `anthropic` SHALL publish `["claude-code"]`.
- BYO `openai` SHALL publish `["codex"]`.
- `self_hosted_endpoint` and `host_daemon` SHALL publish `[]` until a separate
  source-specific activation binds executable authority.
- `market_rented` SHALL remain `[]` in the ordinary provider router even after
  market acceptance; accepted-market work uses only the signed
  paid-market/distributed-execution path.
- Every new/unassigned, in-progress, held, or failed assignment SHALL retain
  `[]`.

For BYO input, an omitted writer SHALL be derived from the exact service
mapping, a matching canonical writer SHALL be accepted, and aliases, unknown
values, or service/writer mismatches SHALL fail before mutation. Assignment
SHALL replace rather than union a prior ceiling. Preference and every other
routing policy may narrow or reorder the ceiling but MUST NOT widen it. This
ceiling proves provider destination only; it MUST NOT be reported as proof of
credential-source isolation.

#### Scenario: allowlist blocks third-party providers
- **WHEN** a universe sets `allowed_providers=["ollama-local"]`
- **THEN** a `writer` call attempts only `ollama-local`
- **AND** `claude-code`, `codex`, and the api-key providers are not attempted

#### Scenario: empty filtered chain hard-fails, no leak
- **WHEN** `allowed_providers` excludes every provider in the resolved chain
- **THEN** single-role, policy, and ensemble calls raise
  `ProviderAuthorityHeldError`
- **AND** no provider is called

#### Scenario: preference reorders without dropping permitted fallback
- **WHEN** a universe sets `preferred_writer` to a provider already in a
  multi-provider ceiling and chain
- **THEN** that provider is attempted first
- **AND** only the remaining providers inside the ceiling stay available

#### Scenario: BYO Anthropic publishes a singleton ceiling
- **WHEN** `set_engine` accepts exact service `anthropic` with an omitted or
  matching `claude-code` writer
- **THEN** the final assignment contains `preferred_writer="claude-code"` and
  `allowed_providers=["claude-code"]`, persists
  `engine_assignment_state="ready"`, and returns `status="engine_set"`
- **AND** a Claude failure does not attempt Codex, an API provider, or a local
  provider

#### Scenario: BYO OpenAI publishes a singleton ceiling
- **WHEN** `set_engine` accepts exact service `openai` with an omitted or
  matching `codex` writer
- **THEN** the final assignment contains `preferred_writer="codex"` and
  `allowed_providers=["codex"]`, persists
  `engine_assignment_state="ready"`, and returns `status="engine_set"`
- **AND** a Codex failure does not attempt Claude, an API provider, or a local
  provider

#### Scenario: mismatched BYO route has zero mutation
- **WHEN** a BYO assignment supplies an alias, unknown service or writer, or a
  writer that does not match the exact service mapping
- **THEN** `set_engine` rejects the request before modifying config or vault
- **AND** no provider, credential, auth-health, or quota path is accessed

#### Scenario: non-executable source is held
- **WHEN** `set_engine` records a self-hosted endpoint, market-rented intent, or
  host-daemon hint without a separately accepted executable binding
- **THEN** the assignment persists `engine_assignment_state="held"` and
  `allowed_providers=[]`
- **AND** `set_engine` returns `status="setup_required"` without claiming
  executable compute
- **AND** every provider role remains held with zero calls until activation

#### Scenario: reassignment replaces authority
- **WHEN** a universe is reassigned from one valid BYO service to the other
- **THEN** the final ceiling contains only the new mapped provider
- **AND** no old provider is retained by union or fallback

#### Scenario: malformed ceiling fails before authority access
- **WHEN** the resolved ceiling is scalar, contains non-string, duplicate,
  unknown, or aliased entries, or cannot be read under its authority lock
- **THEN** routing fails closed with zero provider attempts
- **AND** credential, auth-health, and quota state are not accessed

#### Scenario: new universe starts deny-all
- **WHEN** a universe is created before any engine assignment
- **THEN** it persists `engine_assignment_state="unassigned"` and
  `allowed_providers=[]`
- **AND** universe-originated provider work is held with zero calls

#### Scenario: assignment failure is durable and recoverable
- **WHEN** an assignment fails after durable `pending + []` quarantine
- **THEN** recovery publishes `engine_assignment_state="failed"` with `[]` and
  retains a secret-free transaction journal until reconciliation completes
- **AND** retry or migration validates the journal under the exclusive
  assignment lock, preserves unrelated vault records, and never trusts a
  partial assignment as ready

### Requirement: Judge ensemble fans out to all healthy judges in parallel
`call_judge_ensemble` SHALL call every registered, non-cooldown judge provider
inside the non-empty effective assignment/request authority intersection once,
in parallel, and SHALL never call the same provider twice. Subscription-only
and auth-health filters SHALL apply after authority. It SHALL return 1-N
responses depending on how many authorized judges are healthy and SHALL return
an empty list when effective authority is non-empty but no authorized judge is
available. An empty effective authority intersection SHALL raise
`ProviderAuthorityHeldError` for both ensemble and single-judge calls.
Separately, a single `call()` with role `judge` SHALL return a degraded sentinel
only when its non-empty authorized chain is ordinarily exhausted.

#### Scenario: fan-out returns one response per healthy authorized judge
- **WHEN** the ensemble runs with several healthy judge providers inside
  effective authority
- **THEN** each is called exactly once in parallel
- **AND** the result list contains one response per provider that responded

#### Scenario: empty authorized ensemble returns an empty list
- **WHEN** effective authority is non-empty but registration, cooldown,
  subscription, or auth-health filters remove every authorized judge
- **THEN** `call_judge_ensemble` returns an empty list

#### Scenario: exhausted authorized single judge returns a degraded sentinel
- **WHEN** a `call()` with role `judge` ordinarily exhausts its non-empty
  authorized chain
- **THEN** it returns the degraded judge response
- **AND** does not raise `AllProvidersExhaustedError`

#### Scenario: empty judge authority fails held
- **WHEN** the assignment/request authority intersection is empty
- **THEN** ensemble and single-judge calls raise
  `ProviderAuthorityHeldError`
- **AND** no provider, credential, auth-health, or quota path is accessed

### Requirement: Provider calls use one explicit immutable contract
The provider layer SHALL represent per-call routing with an immutable
`UniverseContext`, immutable request provider authority, immutable
`ModelConfig`, immutable `ResolvedProviderAuthority`, immutable
`ProviderInvocation`, `ProviderLaunchHandle`, and immutable `ProviderResponse`.
Without a compatibility shim, every `BaseProvider` implementation MUST replace
one-phase `complete(...)` with async
`start(invocation: ProviderInvocation) -> ProviderLaunchHandle`; the handle
MUST expose async `result() -> ProviderResponse`.

`ProviderInvocation` SHALL contain the fully materialized prompt, system,
model, universe, endpoint, credential/auth provenance and material, plus an
identity-validated, router-minted launch token. It MUST be non-serializable and
MUST NOT be constructible from public request data. `UniverseContext` carries
optional non-authorizing preferences.
Every universe-originated call MUST carry a typed provider-destination call scope
whose universe variant contains the already-authorized universe directory and
a reference/view derived from the accepted immutable request-authority
contract. If `RequestExecutionAuthority` is retained by its owning change, the
provider layer MUST consume that exact contract and MUST NOT define a second
request-eligibility type. The universe scope exposes its immutable eligible
provider set to the provider layer without allowing that layer to mint, widen,
or replace requester authority.

This change SHALL NOT define, construct, resolve, persist, or widen a second
request authority, execution grant, market agreement, delegation,
credential-vault contract, secret-custody contract, or receipt. The provider
layer consumes only the immutable already-resolved universe authority
view/reference. It MUST NOT rediscover grants, credentials, market offers,
budgets, or ambient host resources.
An `OperatorRequestAdmissionVerdict`, priority grant, admission receipt,
`BranchTask`, or scheduling claim MUST NOT populate the typed request
eligible-provider set and MUST NOT authorize provider access, credentials,
compute, market purchase, execution lease, settlement, or spending.
Every provider attempt MUST obtain fresh persistent assignment and journal
state under shared-reader/exclusive-writer admission and compute:

`fresh assignment ceiling INTERSECT request_allowed_providers INTERSECT narrower policy`.

Neither authority set may replace or widen the other. Missing universe scope,
request eligibility, unreadable state, contended admission, or an active
journal that does not match the final config's transaction identity and
`commit_ready` non-secret digests MUST fail held before authority resolution.
Atomic final-config publication is the assignment commit point; a matching
leftover `commit_ready` journal is cleanup evidence and does not block
admission.

While holding the shared reader, routing MUST resolve an immutable
`ResolvedProviderAuthority` containing the admitted provider, exact
credential/auth provenance and material reference, mint
`ProviderInvocation`, and await `BaseProvider.start(invocation)`.
`start()` MUST return only after a CLI/local child is spawned with fully
materialized env/stdin/cwd/endpoint inputs, or after an HTTP/in-process
transport has copied fully materialized endpoint/headers/body/client
inputs into a scheduled request. The reader is released only after that launch
barrier, and network completion then proceeds through
`ProviderLaunchHandle.result()`.

Launch SHALL use a monotonic `launch_timeout_seconds`, separate from model
completion timeout, defaulting to 5 seconds and bounded to 1 through 30
seconds. Before any partial child/request creation, each provider MUST install
a cleanup guard and durably fsync a secret-free `provider_launch_pending`
record containing a unique launch id before external creation. The
child process group or transport idempotency key MUST carry that launch id.
After start and handle registration, the record MUST atomically become
`provider_launch_active`; terminal finalization MUST durably record its
transport outcome before clearing it. Launch deadline, exception, or
cancellation MUST abort/kill and reap the partial transport. The cleanup guard
MUST prove terminal cleanup before the reader unlocks. Successful cleanup
permits a waiting assignment writer to proceed. If terminal cleanup cannot be
proven within the bounded cleanup deadline, routing MUST install a durable
per-universe
`provider_launch_cleanup_failed` fence before releasing the reader; subsequent
routing and assignment MUST fail loud until operator recovery.

After `start()` returns, provider and handle MUST NOT re-read authority from
universe files, vault, process environment, auth homes, or config. A provider
invocation without the exact router-minted launch-token
identity MUST fail held. The router MUST register every handle before unlock
and own it through structured cleanup; callers MUST NOT receive an unowned
handle. `result()` and `close()` SHALL share one atomic terminal state machine.
Exactly one transition MUST own transport completion or reaping across success,
ordinary provider error, model timeout, caller cancellation, explicit close,
and concurrent `result()`/`close()` calls; all other callers MUST await and
receive the cached terminal outcome. Secret material MUST NOT enter the
journal, diagnostics, or logs.

Startup and assignment MUST reconcile every leftover
`provider_launch_pending` or `provider_launch_active` record before routing or
authority mutation. Reconciliation SHALL locate/abort/reap a tagged child,
query a transport idempotency key where supported, and finalize the durable
transport outcome exactly once. If terminal state cannot be proven,
reconciliation MUST retain
`provider_launch_cleanup_failed`.

`market_rented` SHALL remain `allowed_providers=[]` in this router. An accepted
market agreement, remote executor, market lease, settlement, or economic
accounting MUST NOT enter `ResolvedProviderAuthority`,
`ProviderInvocation`, `ProviderLaunchHandle`, or this launch journal.
Accepted-market work SHALL use only the paid-market/distributed-execution
owner's signed remote-executor path.

Trusted host-local work MUST carry `HostLocalProviderCapability`, a
process-internal, non-serializable, identity-validated token minted only by
trusted daemon bootstrap after local operator configuration. It MUST be
bound to an enumerated non-request-reachable host operation, mutually exclusive
with universe authority, and absent from every MCP/API schema,
JSON/environment request field, node state, universe config, user-controlled
constructor, and user/request/universe lineage. A boolean, string, enum,
serialized token, or caller-created lookalike MUST fail held. Omitted scope is
never permission. A `None` scope, ambient `TINYASSETS_UNIVERSE`, legacy global
fallback, environment-derived universe selection, or internally supplied
host-local capability on universe/user/request lineage MUST NOT authorize
provider access. A
ceiling from an older immutable context MUST NOT widen fresh authority. Model
config carries timeout, token cap, temperature, reasoning effort,
workspace-sandbox, allowed-tool, and disallowed-tool settings. Provider response
carries text, provider, model, family, latency, and degraded state.

#### Scenario: explicit context isolates interleaved universes
- **WHEN** synchronous calls for two universes are interleaved through the
  router's thread pool and each supplies a `UniverseContext` with its own
  directory and resolved configuration
- **THEN** each call applies that universe's current provider ceiling and its
  context's remaining preferences
- **AND** each selected provider receives only that universe's directory

#### Scenario: absent universe authority fails held
- **WHEN** universe-originated work supplies no authoritative universe
  directory or no typed request eligible set
- **THEN** routing raises `ProviderAuthorityHeldError` with zero provider calls
- **AND** a host-local capability can authorize only its enumerated
  non-request-reachable host operation, never this universe work

#### Scenario: request admission and scheduling artifacts grant no provider authority
- **WHEN** a caller supplies only an `OperatorRequestAdmissionVerdict`,
  priority grant, admission receipt, `BranchTask`, or scheduling claim
- **THEN** routing raises `ProviderAuthorityHeldError` before reading provider,
  credential, auth-health, quota, market, lease, settlement, or spending state
- **AND** none of those artifacts populates the typed request
  eligible-provider set or authorizes provider access, credentials, compute,
  market purchase, execution lease, settlement, or spending

#### Scenario: ambient state cannot become host-local authority
- **WHEN** a provider call omits its typed provider-destination call scope while
  process state,
  `TINYASSETS_UNIVERSE`, a legacy global router, or an optional
  `UniverseContext` happens to identify a universe or host configuration
- **THEN** routing raises `ProviderAuthorityHeldError` before reading provider,
  credential, auth-health, quota, market, or lease state
- **AND** the caller must receive either the approved universe authority view
  or the genuine bootstrap-minted `HostLocalProviderCapability` explicitly

#### Scenario: public callers cannot forge host-local authority
- **WHEN** MCP, API, JSON, environment-derived request data, node state,
  universe config, or a caller-created lookalike supplies a host-local boolean,
  string, enum, or serialized token
- **THEN** identity validation rejects it with
  `ProviderAuthorityHeldError`
- **AND** no provider, credential, auth-health, quota, or lease path is accessed

#### Scenario: host-local and universe authority are exclusive
- **WHEN** a call supplies both the accepted universe
  provider-destination call scope and the genuine
  `HostLocalProviderCapability`
- **THEN** routing rejects the ambiguous scope before authority resolution
- **AND** approved host-local callers remain limited to the reviewed bootstrap
  inventory

#### Scenario: host-local capability cannot rescue universe work
- **WHEN** an internal caller supplies a genuine bootstrap-minted
  `HostLocalProviderCapability` for a graph, run, resume, version, policy,
  judge, extract, embed, first-contact, or any other user/request/universe
  lineage
- **THEN** routing rejects the operation with `ProviderAuthorityHeldError`
- **AND** no maintainer credential, quota, account, local model, or local
  hardware is accessed

#### Scenario: accepted market work bypasses the ordinary provider router
- **WHEN** a universe has accepted a paid-market agreement while its persistent
  ordinary provider ceiling remains `[]`
- **THEN** this router makes zero provider calls and does not construct a market
  invocation, lease, settlement, or accounting record
- **AND** only the paid-market/distributed-execution signed remote-executor
  path may consume that accepted agreement

#### Scenario: provider response carries model evidence
- **WHEN** a provider completes a model call
- **THEN** it returns text together with provider name, model name, model
  family, latency in milliseconds, and whether the response is degraded

#### Scenario: policy routing returns response telemetry
- **WHEN** `call_with_policy` completes through a policy provider or the role
  fallback chain
- **THEN** it returns response text, the provider used, and call metadata
  containing model, family, latency, degraded state, and attempt count

#### Scenario: provider launch freezes authority before unlock
- **WHEN** the router admits an attempt under the shared reader
- **THEN** it fully materializes `ProviderInvocation` and awaits the provider's
  launch barrier before releasing the reader
- **AND** `ProviderLaunchHandle.result()` may await network completion outside
  the lock without any authority re-resolution

#### Scenario: subprocess launch uses only captured authority
- **WHEN** a CLI or local provider starts
- **THEN** its child is spawned under the reader with env, stdin, cwd, endpoint,
  and credential material derived only from `ProviderInvocation`
- **AND** later vault, environment, config, or auth-home mutation cannot change
  the launched attempt

#### Scenario: in-process launch uses only captured authority
- **WHEN** an HTTP or in-process provider starts
- **THEN** its transport copies endpoint, headers, body, and client from
  `ProviderInvocation` into a scheduled request under the reader
- **AND** later vault, environment, or config mutation cannot change
  the launched attempt

#### Scenario: direct provider bypass fails held
- **WHEN** code calls a provider with a caller-created invocation, invokes the
  removed `complete(...)` path, or omits the router-minted launch-token identity
- **THEN** the provider rejects the call with `ProviderAuthorityHeldError`
- **AND** it does not resolve credentials, auth, quota, or network state

#### Scenario: hung launch cleans up before assignment proceeds
- **WHEN** provider launch exceeds its bounded launch deadline after partially
  creating a child or request
- **THEN** the provider aborts/kills and reaps the partial transport and
  proves terminal cleanup before the reader unlocks
- **AND** after verified cleanup a waiting assignment writer may proceed

#### Scenario: unprovable launch cleanup fences the universe
- **WHEN** partial-launch cleanup cannot prove the child/request terminal within
  the bounded cleanup deadline
- **THEN** routing durably installs
  `provider_launch_cleanup_failed` before releasing the reader
- **AND** routing and assignment fail loud until operator recovery

#### Scenario: completion cancellation reaps exactly once
- **WHEN** model completion times out, its caller is cancelled, or the router
  closes the launch handle
- **THEN** cancellation reaches the transport, the child/request is
  aborted/reaped, and one terminal transition owns cleanup
- **AND** repeated `close()` or `result()` observes the same cached terminal
  outcome without repeated external effects

#### Scenario: success and provider error finalize transport once
- **WHEN** a launched provider succeeds or returns an ordinary provider error
- **THEN** one terminal transition owns completion or reaps transport resources
- **AND** later result or close calls return the cached outcome without
  repeating transport effects

#### Scenario: concurrent result and close have one terminal owner
- **WHEN** concurrent `result()`/`result()` or `result()`/`close()` calls race
- **THEN** one atomic transition owns completion or abort, resource reaping,
  and terminal outcome publication
- **AND** every other caller awaits and observes the same cached terminal
  outcome

#### Scenario: launch journal survives creation crash windows
- **WHEN** the daemon crashes before resource creation, after resource creation
  before handle registration, or after registration before reader unlock
- **THEN** startup/assignment finds the durable pending or active launch id,
  locates and aborts/reaps the tagged resource or reconciles its transport
  idempotency key, and finalizes the transport outcome exactly once
- **AND** routing and assignment remain held until reconciliation proves a
  terminal state

#### Scenario: completion crash reconciles durable transport outcome
- **WHEN** the daemon crashes after provider completion but before terminal
  journal finalization
- **THEN** startup/assignment uses the durable launch id and provider transport
  evidence to record success, failure, unknown, or retain the cleanup-failed
  fence
- **AND** it never finalizes the same transport launch twice

#### Scenario: router never abandons an unawaited handle
- **WHEN** `start()` returns a `ProviderLaunchHandle`
- **THEN** the router registers it before unlocking and owns it in structured
  cleanup through result or close
- **AND** no public caller can receive or abandon an unowned live handle

#### Scenario: stale context cannot widen a quarantined assignment
- **WHEN** a call holds an older broader ceiling in `UniverseContext` and
  assignment publishes deny-all quarantine before the call's next provider
  admission
- **THEN** that attempt observes the fresh `[]` ceiling and makes zero provider
  calls
- **AND** retries, policy fallback, pins, and judge ensemble remain deny-all

#### Scenario: concurrent assignments publish one coherent authority
- **WHEN** two assignments overlap for the same universe while routing is
  active
- **THEN** one per-universe cross-process assignment discipline serializes
  quarantine, source or vault update, and final config publication
- **AND** the final source, vault service, preference, and ceiling describe one
  complete assignment while no route observes unrestricted authority

#### Scenario: assignment and request authority intersect
- **WHEN** the fresh assignment ceiling contains providers A and B while the
  immutable request eligible set contains B and C
- **THEN** only provider B is eligible before narrower policy is applied
- **AND** neither set is persisted over or used to widen the other

#### Scenario: reader admission linearizes concurrent authority
- **WHEN** two readers and one assignment writer overlap for one universe
- **THEN** shared readers may concurrently validate assignment/journal state,
  capture immutable provider/auth/credential authority, and launch
- **AND** an attempt launched before the writer publishes `pending` may finish
  with its captured authority, while attempts reaching admission during or
  after quarantine fail held with zero provider access
- **AND** the exclusive writer waits for authority capture and launch but not
  for provider network completion

#### Scenario: writer cannot mix old admission with new credentials
- **WHEN** an assignment writer starts after a reader admits a provider but
  before that attempt resolves auth or launches
- **THEN** the writer waits while the reader captures the exact immutable
  credential/auth provenance and material reference and launches
- **AND** the attempt cannot combine the old provider ceiling with new or
  partial assignment credentials

#### Scenario: final config publication commits the transaction
- **WHEN** the process crashes after atomic ready/held config publication but
  before matching journal cleanup
- **THEN** admission accepts the final state only when transaction identity and
  non-secret digests match the `commit_ready` journal
- **AND** any pre-publication, mismatched, or uncommitted journal fails held
  until recovery

### Requirement: The provider call bridge retries only transient full-chain exhaustion
The shared provider call bridge SHALL retry `AllProvidersExhaustedError` up to
three total router attempts with exponential waits bounded from two through
eight seconds. It SHALL NOT retry unrelated exceptions.
`ProviderAuthorityHeldError` SHALL be re-raised immediately and MUST NOT be
converted to caller fallback prose. After ordinary provider failure or when no
router exists, the bridge SHALL return the caller-supplied fallback response
when present and otherwise re-raise the original unrelated error, or raise
`AllProvidersExhaustedError` for exhaustion or a missing router, rather than
synthesize empty prose.

#### Scenario: Transient exhaustion clears
- **WHEN** the first router attempt raises `AllProvidersExhaustedError` and the
  second succeeds
- **THEN** the bridge returns the successful provider text after two attempts

#### Scenario: Three exhaustion attempts use the explicit fallback
- **WHEN** all three router attempts raise `AllProvidersExhaustedError` and
  `fallback_response` is supplied
- **THEN** the bridge returns that fallback response

#### Scenario: Exhaustion without fallback fails loudly
- **WHEN** all router attempts exhaust and no fallback response is supplied
- **THEN** the final `AllProvidersExhaustedError` is raised

#### Scenario: Unrelated exception is not retried
- **WHEN** the router raises an exception other than
  `AllProvidersExhaustedError` or `ProviderAuthorityHeldError`
- **THEN** the bridge performs one router attempt and then returns the supplied
  fallback or re-raises that exception

#### Scenario: Held authority never becomes fallback prose
- **WHEN** the router raises `ProviderAuthorityHeldError` and
  `fallback_response` is supplied
- **THEN** the bridge re-raises `ProviderAuthorityHeldError` after one attempt
- **AND** it does not return or synthesize fallback prose

#### Scenario: No router preserves fallback semantics
- **WHEN** no router is installed
- **THEN** the bridge returns a supplied fallback immediately or raises
  `AllProvidersExhaustedError` when no fallback exists
