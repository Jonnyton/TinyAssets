## Context

TinyAssets can already authenticate a Tier-1 Streamable-HTTP connector caller,
bind that caller to a universe, expose market discovery, and represent a
remote-only engine assignment. Those pieces do not yet form a legal activation
path. A quote or match is economic information, an OAuth token is identity
evidence, and a queue or scheduling claim is work-intake state; none is a
signed distributed-execution grant.

The provider-authority owner defines the only valid target encoding for this
path as:

- `engine_source="accepted_market"`;
- `engine_assignment_state="remote_ready"`; and
- `allowed_providers=[]`.

That state is valid only while a current, non-executable bounded-market
mandate bound to the B13 production composition root exists. The mandate
records the user's total spend ceiling and accepted selection/pricing policy;
it is neither a reservation nor job authority. A B2 grant binds a concrete job
and capsule, so it cannot truthfully be created by an activation request
before the later `converse` message exists. After that message establishes
exact demand and quantity, the paid-market and wallet owners must return a
fresh executable firm quote, capacity consumption, and requester-funded spend
reservation within the mandate. The B13 root must bind those facts into the
exact B2 grant at the per-job dispatch boundary. The ordinary provider router
must never interpret the empty provider list as permission to use a
maintainer, local, BYOC, free, role-default, or environment-selected provider.

The public connector has seven canonical handles. This change must be
completable from a chatbot without adding an eighth handle, using the
deprecated `universe` target, accepting a raw provider secret, or requiring a
desktop or web application. It also must remain separate from
`write_graph(target="request")`, whose owner admits user work into the request
and BranchTask lifecycle.

The old platform-owned cheat/task-automation loop is not part of this design.
Task automations are user-buildable, copyable, remixable graph designs and do
not gain special compute or execution authority from engine activation.

## Goals / Non-Goals

**Goals:**

- Give an authenticated Tier-1 chatbot user one explicit connector action for
  accepting bounded market terms and activating remote compute for an exact
  universe.
- Bind acceptance to a current quote and revalidate every economic and
  identity fact at the server boundary.
- Atomically compose the accepted economic agreement with a current
  B13-bound bounded-market mandate, publish remote-ready engine state only
  after the full composition succeeds, and require fresh quote, capacity,
  requester-funding, and exact B2 authority for each concrete job.
- Dispatch subsequent `converse` work through the accepted-market remote seam
  before the ordinary provider router.
- Fail closed with connector-completable typed refusal or repair results and
  strict idempotency under retry, concurrency, cancellation, expiry, and
  revocation.
- Keep maintainer credentials, quota, wallets, and compute completely outside
  the user path.

**Non-Goals:**

- Adding an MCP handle, a generic engine administration API, or a second
  request/task intake contract.
- Implementing quote discovery, ranking, bid matching, capacity claims,
  payment custody, escrow, settlement, reputation, or B2/B13 grant minting.
- Implementing requester-host, local-model, BYOC credential custody, raw key
  deposit, free-compute fallback, or a desktop-only setup path.
- Treating a quote, match, payment intent, OAuth token, request, scheduling
  claim, provider-attempt receipt, sandbox receipt, or database row as
  execution authority.
- Reintroducing a platform-owned cheat loop or privileged task-automation
  runtime. User automations remain ordinary shareable graph designs subject to
  the same authority boundaries as any other work.
- Authorizing runtime, money, deployment, or production cutover from this
  target-only OpenSpec.

## Decisions

### 1. Activation is an action under the existing `write_graph` handle

The public operation is:

`write_graph(target="engine", action="activate_accepted_market", graph_id=...,
market_acceptance=..., idempotency_key=...)`.

`engine` is a write target because the command changes one universe's engine
assignment. `action` makes the mutation explicit and leaves room for separately
owned engine actions without changing the seven-handle connector catalog. The
server rejects unknown engine actions and unknown fields.

Alternatives considered:

- A new MCP tool was rejected because the canonical seven-handle surface is a
  compatibility and canary invariant.
- `target="universe"` was rejected because that target is deprecated and
  conflates universe birth with compute authority.
- `target="request"` was rejected because engine activation is durable
  universe configuration, not admission of a Request or BranchTask.
- Free-form `text` was rejected because authoritative acceptance must be
  machine-validated and cannot depend on prompt interpretation.

### 2. The public acceptance object is closed, bounded, and non-authoritative

`market_acceptance` is a strict object with these fields:

| Field | Meaning |
|---|---|
| `schema_version` | Exact value `accepted-market-activation/v1` |
| `selection_receipt_id` | Immutable server-issued route-selection receipt |
| `selection_receipt_digest` | Digest of the accepted route evaluation |
| `quote_id` | Immutable server-issued quote identifier |
| `quote_version` | Positive immutable quote version |
| `quote_digest` | Digest of the canonical quoted terms |
| `fulfillment_descriptor_id` | Selected compute/model fulfillment descriptor |
| `fulfillment_descriptor_version` | Immutable descriptor version |
| `fulfillment_descriptor_digest` | Digest of the canonical descriptor |
| `currency` | Currency code of the accepted cap |
| `max_total_minor` | Positive maximum total spend in minor units |
| `fee_schedule_version` | Accepted immutable fee schedule version |
| `demand_commitment_digest` | Digest of the quoted workload/demand envelope |
| `acceptance_policy_digest` | Digest of the matching/acceptance policy |
| `quote_expires_at` | Aware timestamp copied from the quote |

The object identifies the terms the user is confirming; it does not carry
positive authority. Actor, tenant, universe access, provider, host, credential,
wallet, payment authority, B2/B13 grant, lease, generation, fence, and
execution capability are server-derived or owned elsewhere and are forbidden
as caller fields.

`max_total_minor` is the mandate-wide spend ceiling, not a promise that one
quote covers future work. `acceptance_policy_digest` binds the canonical
server-held route-selection policy, per-job price/service constraints,
reservation/retry/refund rules, and any per-job cap. A later job whose exact
demand, quantity, landed total, fee version, or service terms fall outside that
policy requires a new explicit acceptance.

The server re-resolves the selection receipt, quote, and descriptor and
compares their current canonical versions and digests. It verifies that the
selected route is still the explicitly accepted paid lane, that the quote is
unexpired, uncancelled, available to the actor/tenant/universe, within the
stated spend cap, and backed by a still-acceptable market state. Copying an
expiry into the request cannot extend it. Unknown fields and numeric coercion
fail closed.

Alternatives considered:

- Sending only `quote_id` was rejected because an old UI could unknowingly
  confirm changed economic terms.
- Sending the complete provider offer was rejected because it invites callers
  to assert host, capacity, price, or authority facts.
- A generic JSON string was rejected because parsing ambiguity defeats closed
  schema validation and idempotency hashing.

### 3. Request-local identity authorizes the command; B2/B13 authorizes work

The connector transport supplies the current authenticated OAuth subject and
tenant. The identity owner binds a one-shot activation capability to the exact
request, session, `write_graph` tool, `engine` target, action, principal, and
universe. The capability is non-serializable, non-delegable, non-replayable
outside that invocation, and cannot be minted for unauthenticated,
background, scheduled, deferred, stdio, or SSE work.

Identity permits the actor to request the mutation; it does not permit remote
execution. The durable mandate is also non-executable: it records only the
bounded agreement-to-B13 composition and remaining spend-policy envelope.
Positive work authority comes from current per-job market/funding/capacity
results plus a B2 signed grant issued through the B13 production composition
root after a concrete job and capsule exist.

Alternatives considered:

- Reusing the OAuth bearer token as execution authority was rejected because
  authentication and execution are separate authority domains.
- Persisting the request capability for the next `converse` was rejected
  because request-local capabilities cannot escape their originating call.

### 4. One transaction publishes agreement, grant binding, and engine state

Activation uses a single idempotent composition boundary. Inside it, the
server:

1. verifies request-local actor, tenant, universe write authority, action, and
   idempotency scope;
2. revalidates the quote, descriptor, spend cap, fee schedule, demand
   commitment, policy, expiry, cancellation, and capacity;
3. asks the paid-market owner for the exact accepted-agreement result;
4. asks the distributed-execution B13 root for a bounded, revocable,
   non-executable mandate bound to that agreement, target universe, accepted
   selection/pricing policy, total spend ceiling, expiry, revocation
   generation, and idempotency digest; and
5. atomically persists the agreement/mandate references and publishes
   `accepted_market + remote_ready + []`.

If any step fails, none of those activation mutations commits. Payment and
settlement owners may have their own independently valid pre-existing records,
but this command must not leave a partial accepted agreement presented as an
active engine assignment.

The idempotency identity is the authenticated actor, tenant, universe,
`activate_accepted_market` action, and `idempotency_key`. A replay with the
same canonical body returns the original typed result. Reusing the key with a
different body is a conflict. Concurrent first activations have one winner;
losers observe that winner or a typed conflict. Cancellation, quote expiry,
capacity loss, or grant revocation that wins before commit prevents activation.

Alternatives considered:

- Publishing `accepted_market` before grant construction was rejected because
  it creates a phantom ready state.
- Eventual reconciliation was rejected because `converse` could run in the
  gap and reach an ambient fallback.

### 5. Accepted-market `converse` dispatch is pre-routing and fail-closed

For an accepted-market universe, `converse` first re-derives the persisted
agreement and B13-bound bounded-market mandate. After compiling the concrete
message into exact job demand, quantity, and capsule input, it must:

1. obtain a fresh executable firm quote for that exact demand/quantity under
   the accepted selection policy;
2. revalidate quote, fee, currency, service terms, expiry, capacity fence, and
   remaining mandate budget;
3. atomically consume/reserve the exact capacity and requester-owned or
   delegated funding/spend ceiling under a job idempotency identity;
4. seal the agreement, mandate, quote, demand, quantity, capacity-consumption,
   funding-reservation, fee, and spend-ledger references/digests into the
   capsule; and
5. ask B13 for the B2 grant bound to that sealed capsule plus the selected
   daemon/host, job, lease, generation/fence, capability ceiling, expiry, and
   idempotency identity.

Only that exact B2 grant may enter the distributed-execution seam. Concurrent
jobs serialize against remaining budget and conserved capacity; a loser holds
before dispatch. Same-job retries reuse the same reservation/consumption and
B2 result. Cancellation or pre-dispatch failure releases both reservations
exactly once. Post-dispatch settlement applies actual verified use and releases
or refunds unused reserved value through the owning market/wallet contracts;
the connector never invents those effects.

The ordinary provider router is never consulted for this source. If authority
is absent, expired, revoked, fenced, cancelled, inconsistent, or cannot be
re-derived, dispatch holds. The assignment owner atomically downgrades stale
`remote_ready` to `held + []`, and the connector maps the condition to an
accepted-market repair or renewal action. It never falls through to
maintainer, requester-host, local, BYOC, free, or role-default provider chains.

Neither an accepted-market agreement nor its mandate bypasses the independent
execution-admission and sandbox evidence required for the concrete job. Queue,
market, funding, capacity, or admission artifacts may narrow or reject B2
authority but cannot promote themselves into it.

### 6. Connector results disclose status, not authority carriers

Success returns a typed result containing the universe identifier, action,
`engine_source`, assignment state, fulfillment class, accepted quote identity
and version, bounded spend/currency summary, idempotency outcome, and a safe
next step. It contains no secret, signature, raw grant, lease capability,
credential, host address, wallet token, actor/tenant override, or internal
authority carrier.

Refusal and repair use stable typed codes. Refusal covers malformed or stale
acceptance, authorization failure, budget conflict, quote/fee/policy drift,
cancellation, unavailable capacity or requester funding, concurrent
oversubscription, and same-key/different-body conflict. Repair covers a
formerly valid assignment whose B13-bound mandate, per-job quote/capacity/
funding path, or B2 production path is now absent, expired, revoked, fenced,
consumed, or inconsistent. A path is advertised as completable only when all
required owners are live on the connector surface.

### 7. Cutover requires structural, concurrency, and rendered evidence

Implementation remains dark until the provider-authority owner, paid-market
transport, B2/B13 production root, execution admission, and connector action
are integrated. Verification must cover strict schemas, authority mutation
tests, atomicity, idempotency, cancellation/expiry/revocation races, and the
full-platform architecture's section 14 concurrency/load obligations.

Public cutover additionally requires canonical-handle canaries and a rendered
chatbot conversation through `https://tinyassets.io/mcp` in which a newborn
Tier-1 user sees current terms, explicitly accepts them, activates the exact
universe, and completes a remote `converse` without maintainer quota or a
desktop. Post-fix clean-use evidence remains a separate release gate.

## Risks / Trade-offs

- **[Risk: the public acceptance object duplicates immutable quote facts]** →
  Treat caller values only as confirmation commitments and compare every field
  with canonical server records before accepting.
- **[Risk: cross-owner transaction composition is operationally difficult]** →
  Define one named composition boundary and publish no ready state until every
  owner returns verifiable success; retries use the same idempotency identity.
- **[Risk: quote or capacity expires during activation]** → Serialize the
  final revalidation and commit against owner-defined cancellation, expiry, and
  capacity fences; the losing operation returns a typed refusal.
- **[Risk: activation is mistaken for a pre-minted per-job B2 grant]** →
  Make the durable mandate explicitly non-executable and require fresh
  per-job quote, capacity, requester-funding, and B2 authority only after each
  concrete job/capsule exists.
- **[Risk: concurrent jobs oversubscribe budget or conserved capacity]** →
  Reserve both under one job-idempotency identity before B2 creation; serialize
  competing commits and release/refund exactly once through owning contracts.
- **[Risk: a stored mandate becomes stale after activation]** →
  Re-derive authority at every execution decision, downgrade to held, and
  expose only repair/renewal.
- **[Risk: an empty provider list is mistaken for permission to fall back]** →
  Dispatch accepted-market before ordinary routing and mutation-test that the
  ordinary router is never called.
- **[Risk: task/request primitives blur with engine activation]** → Keep the
  engine action separate from Request/BranchTask admission and grant no special
  authority to user-authored automation graphs.
- **[Trade-off: no BYOC escape hatch in Tier-1 activation]** → Preserve the
  clean authority boundary; requester-host and secure custody remain separate
  successor paths.

## Migration Plan

1. Land and archive this target contract without enabling runtime behavior.
2. Reconcile the exact action schema with the canonical connector router while
   preserving the seven-handle catalog and the independent request-target
   contract.
3. Integrate the paid-market accepted-agreement owner and current transport.
4. Integrate the B2 signed protocol and B13 sole production composition root,
   plus execution-admission and sandbox enforcement.
5. Add the dark activation transaction, pre-routing dispatch, typed connector
   mapper, and focused security/concurrency/load tests.
6. Enable only server-owned, default-empty test principals/universes after all
   dependencies are live; run public canaries and rendered connector proof.
7. Obtain explicit rollout approval and post-fix clean-use evidence before
   global Tier-1 cutover.

Rollback stops new activations and remote dispatch while preserving signed
evidence, monotonic fences, accepted financial records, and existing held
assignments. It must never reinterpret a quote, request, legacy
`market_rented` row, or mutable database state as positive authority.

## Open Questions

No host design question remains in this target. Runtime starts only after the
paid-market owner exposes stable quote/selection identifiers plus per-job
capacity and requester-funding reservation/settlement interfaces, the B13 owner
exposes the non-executable mandate and per-job B2 composition interfaces, and
one storage owner can prove each required atomic commit. The implementation
successor advertises only the repair actions it proves live and records its
numerical section-14 load envelope before executing the gate.
