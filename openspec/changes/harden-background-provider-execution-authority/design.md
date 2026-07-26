## Context

`constrain-set-engine-provider-authority` makes live HTTP authority
message-scoped and deliberately non-transferable. That closes stale
FastMCP/ContextVar reuse, but it also means any provider work that outlives
middleware must have a different owner. The same target names this change as
the sole owner of `ProviderWorkAuthorityReceipt` issuance for graph,
run/resume, schedule, daemon, retrieval, reflexion, ingestion, and other
task/thread/process bridges.

Current runtime artifacts identify work but do not authorize provider spend:

- `BranchTask` stores universe, branch, claimed worker, runtime, heartbeat, and
  lease;
- run/checkpoint state stores lineage and resumability;
- schedule/subscription rows store triggers;
- graph nodes and injected `provider_call` functions choose where a call
  occurs; and
- process globals/environment can still identify a daemon or provider.

Treating any of those as authority would make a caller-supplied row, stale
worker, copied task context, or queue replay equivalent to a live
authenticated requester. Conversely, requiring a live requester for every
provider call would break zero-host schedules and autonomous loops. The
missing abstraction is a server-owned durable authorization binding plus a
short-lived execution receipt minted from current state.

The provider-routing target remains the only carrier/sink owner. This change
does not add a second provider entry point; it supplies the exact receipt that
the existing sink validates.

## Goals / Non-Goals

**Goals:**

- Authorize provider work after request middleware returns without ambient
  request, process, environment, queue, or maintainer authority.
- Keep schedules, resumed runs, daemon loops, and post-response work available
  24/7 with no host online.
- Preserve exact principal/actor/universe/branch/run/operation lineage and
  current provider assignment/binding authority at every provider launch.
- Make cross-task/thread/process handoff replay-safe, bounded, revocable, and
  crash-recoverable.
- Bound provider launches and ambiguous retry risk within a receipt.
- Support the one closed universe-less fixed private maintenance completion
  without exposing requester content or quota.
- Keep enforcement dark until the existing provider-authority V2 gate applies
  and provide isolated pre-cutover proof.

**Non-Goals:**

- Request-time `ProviderRequestCapability`, local
  `ProviderHostRequestCapability`, provider assignment, credential custody,
  outbound HTTP grants/proxying, or provider invocation/launch mechanics.
- Branch/run ACL design. Those owners publish the authorization facts this
  owner revalidates.
- New MCP handles/actions, public receipt APIs, caller-minted tokens, raw
  secret deposit, market remote execution, requester-host activation, or
  Agent Village/web UI.
- Exactly-once model completion. An ambiguous launched request is fenced and
  surfaced rather than guessed safe to retry.

## Decisions

### 1. Binding, receipt, claim, and invocation reservation are distinct

| Term | Meaning | Not authority by itself |
|---|---|---|
| `ProviderWorkBinding` | Durable server-owned authorization intent for a named work source and bounded provider-capable operation | schedule row, run ID, branch task, actor string |
| `ProviderWorkAuthorityReceipt` | Short-lived bounded authority for one logical work attempt, derived from one current binding | receipt ID or serialized dict |
| `ProviderWorkExecutionClaim` | One active task/thread/process owner for the receipt generation | worker ID, queue claim, heartbeat, lease |
| `ProviderInvocationReservation` | Atomic ordinal/budget reservation for one provider launch under the active claim | retry counter or provider response |

The binding answers “may this durable work source ask for provider work?” The
receipt answers “may this exact logical attempt do so now?” The execution claim
answers “which currently live execution scope owns it?” The invocation
reservation answers “has this provider launch consumed bounded authority?”

This separation prevents a persistent schedule or queue artifact from becoming
a reusable bearer while allowing zero-host work to obtain fresh authority.
Collapsing these into `BranchTask` was rejected because BranchTask data is
caller-influenced, copied across files/processes, and already has independent
queue lifecycle semantics.

### 2. Receipt variants form one closed discriminated union

`ProviderWorkAuthorityReceipt` has exactly two variants:

1. `universe_work`
   - binding ID/digest and receipt generation;
   - authenticated principal and executing actor/daemon;
   - universe, branch, run, and exact operation;
   - current provider-assignment generation/digest;
   - allowed operation/role set;
   - bounded lifetime and invocation/token/cost ceilings;
   - issuer, opaque receipt ID, and revocation generation.
2. `maintainer_maintenance`
   - host/operator principal;
   - exact provider, operation, invoking runtime/daemon identity, and
     executor/transport identity;
   - opaque credential reference plus current credential-record digest;
   - fixed private prompt digest;
   - separate maintenance binding/budget;
   - bounded lifetime and exactly bounded invocation count;
   - no universe, branch, run, requester identity, requester content, or
     requester quota.

Unknown variants and optional lineage in place of the closed union grant
nothing. A generic “system” or “background” variant was rejected because it
would erase who authorized the work and what it may spend.

### 3. Durable bindings have explicit issuance roots

The owner creates or refreshes a `ProviderWorkBinding` only at one of these
server-owned transitions:

- **Deferred/task-augmented request:** TinyAssets-owned
  `Middleware.on_call_tool` creates an inert, single-message binding draft
  after it reads `request_ctx.get().request` and re-derives bearer identity,
  but before it structurally awaits `call_next` or any dispatch augmentation.
  The draft binds only principal, message, and registered operation; it is not
  target authority. The tool resolves the exact target and consumes the draft
  transactionally with its deferred work item. Just-in-time receipt issuance
  performs target authorization against that resolved server record. The
  later worker mints no request capability. Work that becomes deferred before
  this boundary has no issuance root and holds.
- **Schedule/subscription:** the background-branch authority owner records the
  authenticated principal, target authorization, operation, and limits at
  authorized creation. This change consumes that server-owned record; it does
  not read `owner_actor`, caller kwargs, or another synthetic actor. Until
  `harden-background-branch-execution-authority` lands that record, this
  issuance root remains inactive. Each trigger revalidates the binding; the
  schedule row or trigger event alone is not authority.
- **Run/resume/daemon activation:** an authorized run or daemon activation
  records its durable binding. Resume/cycle issuance revalidates ownership,
  target visibility/authorization, non-cancelled state, and current daemon
  eligibility. Concurrent resume first claims one durable resume-attempt
  idempotency record by conditional transition from `interrupted`; only that
  attempt may issue the receipt. The run remains publicly `interrupted` until
  the same attempt links its receipt and commits `resumed`. Crash recovery
  resumes or revokes that exact attempt and never creates a second receipt.
- **Child/background work:** an active parent receipt may ask the server to
  create a child binding only when the child remains within the parent’s
  universe/branch lineage, allowed operation set, depth, lifetime, and
  remaining budget. The store atomically transfers invocation/token/cost
  authority from parent to child, debiting the parent before making the child
  claimable; concurrent children can never receive more in aggregate than the
  parent's remaining ceiling. Child authority is replacement/narrowing, never
  union, and returned unused authority follows one explicit settlement rule.
- **Maintainer maintenance:** local operator configuration creates a separate
  host/operator-owned binding for the one fixed private viability operation.

Every root uses the authenticated-subject/daemon/runtime owners’ canonical
read interfaces; this change does not invent ACL truth. Queue claims,
admission/replay verdicts, request receipts/results/events, priority grants,
environment actors, and worker identity cannot create a binding.

### 4. Receipts are minted just in time from fresh state

Before issuing `universe_work`, the authority service revalidates:

- binding active/not expired/not revoked and digest exact;
- principal and actor/daemon still permitted for the named target/operation;
- universe/branch/run lineage exact, readable, and not cancelled/tombstoned;
- claimed work item matches its physical universe and binding reference;
- provider assignment state, generation, ceiling, and per-provider binding
  digest are current;
- remaining receipt/work budget is non-zero; and
- runtime/worker identity is eligible for the target execution class.

Failure creates no receipt and performs no provider, credential,
outbound-proxy, auth-health, or quota access. A previously issued receipt is
invalid immediately when its binding, assignment generation, target
authorization, cancellation, or revocation generation changes.

### 5. The durable ledger is server-owned; cross-process envelopes are claims

The authoritative binding/receipt/claim/reservation ledger lives behind one
control-plane `ProviderWorkAuthorityStore`, not in BranchTask JSON, run input,
MCP payload, environment, or provider config. Implementation must select an
existing platform transactional store and expose atomic transactions/CAS
through this one stable interface; workers never open or mutate the ledger
directly.

Authority-store transactions are short and complete before either
`ProviderAssignmentAdmission` or the branch-task queue file lock. Provider
launch order is authority store, release, assignment admission, then
credential index/keyring. Recovery order is authority store, release, then
queue file lock. Queue and assignment locks never nest. No authority-store
transaction may be acquired while queue, assignment-admission, or credential
locks are held; reverse acquisition and untracked reentrancy fail loud. Result
settlement occurs only after assignment admission is released.

Cross-store recovery uses a short-lived non-authorizing reconciliation proof
bound to the exact authority generation, queue task, claim owner, and lease
generation. Queue reset then performs a file-locked compare-and-swap against
that exact task/claim/lease tuple. A concurrent heartbeat or lease renewal
changes the tuple and makes the reset fail; recovery must restart from a fresh
authority proof. The proof alone grants no provider or queue authority.
Lease expiry alone never proves death. Before proof issuance, recovery must
either prove the old owner dead or atomically invalidate the old execution
claim generation under the authority store. Claim invalidation serializes
with reservation creation: whichever commits first forces reconciliation of
the new state, and an invalidated stale worker can reserve nothing.

For task/thread handoff, code carries a non-serializable receipt object only
inside the claimed execution scope. Queue records created before worker
selection carry only a non-authorizing binding reference. After the queue
owner atomically selects a worker, the server emits an internal process
envelope containing an opaque receipt ID, one-use claim nonce, that exact
runtime/worker audience, and expiry. The receiving worker must atomically
claim that exact envelope against current server state. The ID,
nonce, worker ID, signature/MAC, or envelope alone cannot authorize a provider
call after claim, expiry, revocation, or audience mismatch; the provider
carrier contains the reconstructed non-serializable receipt plus active claim
generation.

Public API/MCP schemas, branch inputs/state, queue payloads, caller kwargs,
logs, receipts/results, and serialized universe state cannot construct,
inspect, or populate the authority object.

### 6. One active execution claim; reclaim only before an irreversible launch

A receipt has at most one active `ProviderWorkExecutionClaim`. Claim binds
receipt generation, runtime instance, worker, process/task identity, work
item, and lease. Heartbeat may extend the claim only for that exact owner and
never extends the receipt’s absolute lifetime or budget.

If a worker is provably dead and the receipt has no reservation, or every
reservation has a durable conclusive state (`cancelled_before_launch`,
`succeeded`, or `failed`), the server may expire the claim and issue a new
claim generation for the remaining authorized work. Consumed terminal slots
and budgets remain consumed only for launched `succeeded` or `failed`
reservations; `cancelled_before_launch` releases its full reserved authority.
A dead-owner `reserved` reservation is provably pre-arm under the durable
ordering below, so reconciliation atomically cancels it before launch and may
then reclaim. An unclosed `launch_started` or `indeterminate` reservation is
ambiguous and fences. Every stale object/envelope from the old generation
then fails.

If any reservation may have launched but lacks a conclusive result, the
receipt becomes `fenced_indeterminate`. It cannot be reclaimed or retried
automatically. An autonomous reconciler first consumes provider launch-handle,
attempt-receipt, outbound-proxy, child-process, and durable result evidence to
resolve proven absence, success, or failure. If evidence remains ambiguous
after the bounded reconciliation window, the work stays non-runnable and
emits the smallest explicit `manual_resolution_required` operator action;
global cutover is prohibited for a transport that cannot surface that state.
This follows the provider target’s durable launch-fence rule and avoids
duplicate cost/effects disguised as recovery.

### 7. Provider launches consume atomic receipt reservations

Before acquiring `ProviderAssignmentAdmission`, the authority service
atomically reserves the next invocation ordinal under the active claim. It
verifies remaining invocation/token/cost/time budget, operation and role
membership, current claim/receipt/binding state, and an expected provider
assignment tuple. The authority transaction then durably transitions the
reservation to `launch_started` and closes before assignment admission is
acquired. `launch_started` means the irreversible launch fence is armed, not
that transport is known to have started. The carrier then freezes the receipt
generation, claim generation, reservation ordinal/digest, expected assignment
tuple, and revocation/cancellation generation. The parent provider-routing
sequence validates that carried frozen tuple under assignment admission
without rereading the authority store before minting `ProviderInvocation`. A
revocation or cancellation committed before arming wins and prevents the
attempt; once arming commits, that single attempt owns the launch race and may
proceed if parent admission still validates, while the revocation prevents
every later reservation. A later admission or launch failure consumes the
armed slot conservatively; no authority-store lock is reacquired under
admission. Dynamic provider routing may narrow afterward but cannot refund or
widen authority.

Reservation states are `reserved`, `launch_started`, `succeeded`, `failed`,
`cancelled_before_launch`, and `indeterminate`. `indeterminate` is a fenced
non-conclusive state entered when an armed attempt lacks proof of success,
failure, or non-launch; authoritative reconciliation may advance it once to
`cancelled_before_launch`, `succeeded`, or `failed`. An admission or launch
failure with conclusive no-transport or failure evidence becomes `failed`;
ambiguous transport becomes `indeterminate`. A reservation cancelled before
the launch fence is armed releases its full invocation, token, and cost
reservation. Once `launch_started`, the invocation slot remains consumed
regardless of provider outcome. Token and cost authority reserve the
server-owned worst case derived from the resolved provider/model price
ceiling and `ModelConfig` token cap. If `max_tokens` is `None`, the adapter
must substitute a finite conservative server-owned ceiling for the exact
provider/model/role or hold. Subscription CLI providers reserve one
server-defined subscription-invocation cost unit rather than fabricated
per-token currency. An authoritative terminal usage record
may refund only the proven unused portion after admission release; absent or
ambiguous usage retains the full reservation. Provider fallback/retry creates
another reservation and must fit the same receipt limits.

Judge-ensemble fan-out resolves its exact N providers/configs and atomically
reserves all N ordinals plus their worst-case budgets before any member
launches. If the receipt cannot fund the complete ensemble, the whole
ensemble holds; partial fan-out is forbidden. Each member arms its own launch
fence and enters the parent `ProviderInvocation`/`ProviderExecutor` sink;
direct bare `BaseProvider.complete(...)` remains a CI failure.

This is not billing or requester quota. It is an authority ceiling. Existing
quota and outbound-grant owners apply their own narrower checks afterward.

### 8. Receipt lifecycle is explicit and monotonic

Bindings are `active`, `revoked`, `expired`, or `superseded`.
Receipts are `issued`, `claimed`, `completed`, `failed`, `cancelled`,
`expired`, or `fenced_indeterminate`. Transitions are monotonic.
`fenced_indeterminate` is non-runnable but may advance only from authoritative
evidence to the matching conclusive terminal; the first conclusive terminal
wins. Terminal work cancellation revokes the active claim before downstream
cleanup; stale task/run finalizers cannot reopen it.

Daemon-start and lazy first-use run reconciliation:

- expires elapsed unclaimed receipts;
- preserves valid active claims whose owner/lease remains live;
- reclaims only after proving the owner dead or atomically invalidating its
  claim generation, with no reservation or only durably conclusive
  `cancelled_before_launch`, `succeeded`, or `failed` reservations;
- atomically cancels dead/invalidated-owner `reserved` before launch and
  releases its full authority;
- fences unclosed `launch_started` or `indeterminate` reservations because
  outcome is not provable;
- fences any claim with ambiguous launch state;
- revokes receipts whose binding/target/assignment is provably stale; and
- preserves plus holds on unreadable authority/lineage stores rather than
  inferring absence or freshness.

The shipped process-global boolean becomes a synchronized per-universe
recovery state machine. It marks each universe done only after its applicable
authority reconciliation and run sweep both commit. A V2-universe failure
remains retryable and fails closed only provider-capable run operations for
that universe; dark/unlisted universes complete the shipped sweep and remain
live independently. A fenced run is reported publicly as `interrupted` with
`error.reason = provider_authority_fenced`, never as indefinitely `queued` or
`running`; `resume_run` raises that exact reason until reconciliation resolves
it.

Ledger events contain secret-free IDs/digests, generations, state, reason,
timestamps, and bounded classifications. They exclude prompts, model output,
credentials, bearer tokens, claim nonces, and recoverable secret material.

### 9. Maintenance completion is a separate closed target route

Today ordinary provider routing can synchronously launch
`_AUTH_PROBE_PROMPT` through `subscription_auth_health` and resolve
`CODEX_HOME` plus the CLI from ambient process state. Dark mode preserves that
shipped behavior. Under an effective V2 gate, ordinary universe/request
routing retains the parent's shipped non-completion subscription-auth ladder
exactly. Codex quarantines when `auth.json` is missing, but an existing empty,
corrupt, stale, or cache-miss file with probing disabled remains eligible with
presence/inconclusive evidence. Claude-code quarantines an absent, empty, or
unreadable config directory. The viability-probe kill switch preserves the
shipped unconditional eligible verdict. Router `unknown`/inconclusive results
remain eligible; only each provider's shipped positive dead signature
quarantines. Ordinary routing MUST NOT launch the
`_AUTH_PROBE_PROMPT` completion, borrow its universe receipt for that
completion, dereference maintainer credentials, or start the maintainer CLI.

The target probe owner instead validates the `maintainer_maintenance` receipt
and separate maintenance binding/budget, reserves its one bounded invocation,
and passes the exact receipt to `ProviderExecutor`'s closed maintenance
entrypoint. That entrypoint bypasses `call_provider`, universe role/policy
routing, request authority, and requester quota, but retains the parent's
single provider sink, opaque-binding dereference, executable/transport
validation, launch handle, and no-ambient-reread rules. The maintenance
binding's opaque credential reference/digest, provider, executor/transport,
runtime/daemon, and operation must all remain current.

The prompt is compiled from a fixed private constant and compared by digest;
request/universe/branch content cannot influence it. The result may update
host subscription-auth viability only. It cannot mutate a universe, create
work, produce user output, or mint child authority. `get_status` remains
read-only and never launches the completion.

A proven zero-output replacement may retire this variant through a future
OpenSpec change. Until then, classifying the completion as a zero-output
`HostLocalProviderCapability` is forbidden.

### 10. Enforcement composes with the existing V2 gate

The owner may create, validate, inventory, and emit non-authorizing
diagnostics while provider-authority V2 is dark, but universe receipt
enforcement applies only when the exact universe’s effective V2 gate applies.
That gate cannot become effective for a worker/provider until its maintenance
canary has produced current conclusive viability evidence and the supervisor
has proven both authenticated spawn and unauthenticated/unknown quarantine.
Missing maintenance authority keeps V2 dark for that worker/provider rather
than inventing a health state. Unlisted universes preserve shipped behavior
byte-for-byte.

Universe-less maintenance enforcement applies when global V2 is true or when
a server-owned default-empty maintenance-canary set contains the exact fixed
operation plus invoking runtime/daemon identity. Caller input,
environment-derived request data, or receipt payload cannot populate the set.
The canary runtime uses an isolated credential binding and maintenance budget
and cleans up its receipt/binding records; enabling it does not affect other
production probe callers. Global cutover requires the universe and maintenance
paths to pass together.

### 11. Call-site closure is a build and CI gate

Inventory classifies every live provider bridge, including:

- `universe_intelligence` live converse/intelligence calls;
- compiled provider nodes, router thread-pool closure, and the async
  judge-ensemble `gather` plus its direct `provider.complete(...)` members;
- branch run/resume/version/child execution;
- schedules, subscriptions, daemon cycles, selectors, and cloud workers;
- editorial evaluation and ingestion extraction/synthesis;
- RAPTOR, agentic retrieval, reflexion, and other memory/retrieval work;
- `_AUTH_PROBE_PROMPT` maintenance; and
- the mirrored Claude-plugin provider/runtime copies.

Each bridge is exactly one of: live request-carried, attested host-request
carried, background-receipted, closed maintenance, remote accepted-market, or
proven non-provider/mock. Attested host-request and remote accepted-market
remain empty fail-closed classifications until
`activate-requester-host-engines` and
`activate-connector-requester-authority` respectively land their owners.
Unclassified bridges and direct provider
`complete(...)` bypasses fail CI. A function that accepts injected
`provider_call` is classified by every production caller, not assumed safe
from its signature.

## Risks / Trade-offs

- **[Receipt complexity becomes a second scheduler]** → Keep work lifecycle in
  existing task/run/schedule owners; this ledger owns only provider authority,
  claims, and invocation reservations.
- **[Long receipts become durable bearer tokens]** → Server-side state,
  bounded lifetime/budget, one active claim, current-state revalidation, and
  non-authorizing IDs/envelopes.
- **[Crash recovery duplicates provider spend]** → Arm the durable launch
  fence before assignment admission or transport; dead/invalidated-owner
  `reserved` cancels and releases authority, while unclosed armed or
  indeterminate attempts fence.
- **[Authorization revocation races an in-flight launch]** → Revalidate under
  atomic reservation immediately before invocation; launch thereafter uses
  the frozen tuple and cannot reread ambient state.
- **[A schedule loses 24/7 availability]** → Durable binding survives request
  loss; each trigger mints fresh bounded authority without a live requester.
- **[Maintenance borrows requester or maintainer quota invisibly]** → Separate
  host/operator binding and maintenance budget, fixed prompt, no requester
  fields, explicit diagnostics.
- **[Mirrored plugin drifts]** → Inventory and mirror-parity gate cover both
  canonical and packaged provider bridges.
- **[V2 rollout partially changes legacy behavior]** → Existing effective
  universe gate plus default-empty maintenance canary; no caller opt-in.

## Migration Plan

1. Land this target spec active/unsynced and publish one-way handoffs to the
   run/background authority owners. Keep runtime unchanged.
2. Inventory/classify every provider bridge, choose the existing store behind
   the interface, and verify the authority-store-before-assignment global lock
   order without broadening claimed runtime files.
3. Add the binding/receipt/claim/reservation ledger and non-authorizing dark
   diagnostics; preserve shipped behavior with both gates dark.
4. Add RED tests for issuance roots, forgery/replay, stale lineage,
   cancellation, concurrency, budget, crash, ambiguous launch, maintenance,
   and mirrored runtime.
5. Land or consume the background-branch principal/target owner, implement
   server issuance/claim/reconciliation, then thread the exact receipt through
   background call sites into the existing provider carrier.
6. Exercise isolated universe and maintenance canaries, including real
   cross-process worker and §14 concurrent claim/launch proof.
7. Land dependent run/background owners, prove every 24/7 loop stays live or
   intentionally held, and only then permit provider-authority global cutover.
8. Sync/archive after implementation and rendered connector acceptance.
   Rollback disables the effective gates and preserves the receipt ledger for
   diagnosis; it never widens authority or deletes ambiguous evidence.

## Open Questions

- Which existing transactional backend best hosts the authority ledger
  without coupling it to BranchTask JSON? Resolve during inventory; every
  candidate must preserve the fixed authority-store-before-assignment order
  and must not nest authority transactions under admission.
- Which exact provider-capable call sites are live-request paths versus
  background paths today? Tasks 1.1 and 5.5 must classify every production
  caller, including injected callables and the packaged mirror.
- What conservative fixed default invocation/token/cost ceilings apply per
  operation? Runtime implementation must select server-owned defaults before
  build; widening is an operator configuration change, never caller input.
