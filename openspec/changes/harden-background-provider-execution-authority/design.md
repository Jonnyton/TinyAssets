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
   - exact provider and operation;
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

- **Deferred/task-augmented request:** while the current authenticated message
  and target authorization are still live, the server records the durable
  binding transactionally with the deferred work item. The later worker mints
  no request capability.
- **Schedule/subscription:** authorized creation records principal, target,
  operation, and limits. Each trigger revalidates the binding; the schedule
  row or trigger event alone is not authority.
- **Run/resume/daemon activation:** an authorized run or daemon activation
  records its durable binding. Resume/cycle issuance revalidates ownership,
  target visibility/authorization, non-cancelled state, and current daemon
  eligibility.
- **Child/background work:** an active parent receipt may ask the server to
  create a child binding only when the child remains within the parent’s
  universe/branch lineage, allowed operation set, depth, lifetime, and
  remaining budget. Child authority is replacement/narrowing, never union.
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
MCP payload, environment, or provider config. The current implementation uses
the platform transactional store with atomic transactions/CAS and a stable
interface; workers never open or mutate the ledger directly.

For task/thread handoff, code carries a non-serializable receipt object only
inside the claimed execution scope. For process handoff, the server emits an
internal envelope containing an opaque receipt ID, one-use claim nonce,
intended runtime/worker audience, and expiry. The receiving worker must
atomically claim that exact envelope against current server state. The ID,
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

If a worker is provably dead and no invocation reservation reached
`launch_started`, the server may expire the claim and issue a new claim
generation for the same logical receipt. Every stale object/envelope from the
old generation then fails.

If any reservation may have launched but lacks a terminal result, the receipt
becomes `fenced_indeterminate`. It cannot be reclaimed or retried
automatically. Operator/reconciliation evidence must resolve or replace the
work. This follows the provider target’s durable launch-fence rule and avoids
duplicate cost/effects disguised as recovery.

### 7. Provider launches consume atomic receipt reservations

Immediately before the provider sink mints `ProviderInvocation`, the authority
service atomically reserves the next invocation ordinal under the active
claim. It verifies remaining invocation/token/cost/time budget, operation and
role membership, current claim/receipt/binding state, and the fresh provider
assignment tuple. Dynamic provider routing may narrow afterward but cannot
refund or widen authority.

Reservation states are `reserved`, `launch_started`, `succeeded`, `failed`,
`cancelled_before_launch`, and `indeterminate`. A reservation cancelled before
launch may be released according to the fixed budget policy. Once
`launch_started`, it remains consumed regardless of provider outcome. Provider
fallback/retry creates another reservation and must fit the same receipt
limits.

This is not billing or requester quota. It is an authority ceiling. Existing
quota and outbound-grant owners apply their own narrower checks afterward.

### 8. Receipt lifecycle is explicit and monotonic

Bindings are `active`, `revoked`, `expired`, or `superseded`.
Receipts are `issued`, `claimed`, `completed`, `failed`, `cancelled`,
`expired`, or `fenced_indeterminate`. Transitions are monotonic and
first-terminal-writer-wins. Terminal work cancellation revokes the active
claim before downstream cleanup; stale task/run finalizers cannot reopen it.

Startup reconciliation:

- expires elapsed unclaimed receipts;
- preserves valid active claims whose owner/lease remains live;
- reclaims only pre-launch claims with provably dead owners;
- fences any claim with ambiguous launch state;
- revokes receipts whose binding/target/assignment is provably stale; and
- preserves plus holds on unreadable authority/lineage stores rather than
  inferring absence or freshness.

Ledger events contain secret-free IDs/digests, generations, state, reason,
timestamps, and bounded classifications. They exclude prompts, model output,
credentials, bearer tokens, claim nonces, and recoverable secret material.

### 9. Maintenance completion is a separate closed route

The shipped `_AUTH_PROBE_PROMPT` completion never enters `call_provider`,
universe role/policy routing, request authority, or requester quota. Its owner
validates the `maintainer_maintenance` receipt and separate maintenance
binding/budget, reserves its one bounded invocation, and passes the exact
receipt to the provider sink’s closed maintenance route.

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
Unlisted universes preserve shipped behavior byte-for-byte.

Universe-less maintenance enforcement applies when global V2 is true or when
a server-owned default-empty maintenance-canary set contains the exact fixed
operation. Caller input, environment-derived request data, or receipt payload
cannot populate the set. The canary uses an isolated maintenance budget and
cleans up its receipt/binding records. Global cutover requires the universe
and maintenance paths to pass together.

### 11. Call-site closure is a build and CI gate

Inventory classifies every live provider bridge, including:

- `universe_intelligence` live converse/intelligence calls;
- compiled provider nodes and router thread-pool closure;
- branch run/resume/version/child execution;
- schedules, subscriptions, daemon cycles, selectors, and cloud workers;
- editorial evaluation and ingestion extraction/synthesis;
- RAPTOR, agentic retrieval, reflexion, and other memory/retrieval work;
- `_AUTH_PROBE_PROMPT` maintenance; and
- the mirrored Claude-plugin provider/runtime copies.

Each bridge is exactly one of: live request-carried, attested host-request
carried, background-receipted, closed maintenance, remote accepted-market, or
proven non-provider/mock. Unclassified bridges and direct provider
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
- **[Crash recovery duplicates provider spend]** → Reclaim only when no
  irreversible launch occurred; ambiguous launches fence.
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
2. Inventory/classify every provider bridge and choose exact store/lock
   integration points without broadening claimed runtime files.
3. Add the binding/receipt/claim/reservation ledger and non-authorizing dark
   diagnostics; preserve shipped behavior with both gates dark.
4. Add RED tests for issuance roots, forgery/replay, stale lineage,
   cancellation, concurrency, budget, crash, ambiguous launch, maintenance,
   and mirrored runtime.
5. Implement server issuance/claim/reconciliation, then thread the exact
   receipt through background call sites into the existing provider carrier.
6. Exercise isolated universe and maintenance canaries, including real
   cross-process worker and §14 concurrent claim/launch proof.
7. Land dependent run/background owners, prove every 24/7 loop stays live or
   intentionally held, and only then permit provider-authority global cutover.
8. Sync/archive after implementation and rendered connector acceptance.
   Rollback disables the effective gates and preserves the receipt ledger for
   diagnosis; it never widens authority or deletes ambiguous evidence.

## Open Questions

- Which current transactional store/lock implementation best hosts the
  authority ledger without coupling it to BranchTask JSON? Resolve during
  inventory before implementation; the interface and invariants above do not
  vary by backend.
- Which exact provider-capable call sites are live-request paths versus
  background paths today? Task 3 inventory must classify every production
  caller, including injected callables and the packaged mirror.
- What fixed default invocation/token/cost ceilings apply per operation?
  Runtime implementation must choose conservative server-owned values and
  make widening an operator configuration change, never caller input.
