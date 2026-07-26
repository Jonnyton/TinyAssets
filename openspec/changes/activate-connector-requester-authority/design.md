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
exact demand and quantity, the live-price/transport owner must return the
request-bound quote/bid/match/paid-claim/slot and selected host, the domain
owner must return fenced capacity, `paid-market-economy` must return logical
budget/accounting intent, and the architecture §18.6 successor must return
requester real-fund authority. The B13 root coordinates and binds those
owner-native facts plus the S14/B36 settlement identity into the exact B2 grant
at the per-job dispatch boundary. The ordinary provider router must never
interpret the empty provider list as permission to use a
maintainer, local, BYOC, free, role-default, or environment-selected provider.

The public connector has seven canonical handles. This change must be
completable from a chatbot without adding an eighth handle, reusing the live
`target="universe"` birth path or legacy `universe` handle,
accepting a raw provider secret, or requiring a
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
- `target="universe"` was rejected because it is the live opt-in universe-birth
  path and must not be overloaded with compute authority.
- `target="request"` was rejected because engine activation is durable
  universe configuration, not admission of a Request or BranchTask.
- Free-form `text` was rejected because authoritative acceptance must be
  machine-validated and cannot depend on prompt interpretation.

### 2. The public acceptance object is closed, bounded, and non-authoritative

`market_acceptance` is a strict object with these fields:

| Field | Meaning |
|---|---|
| `schema_version` | Exact value `accepted-market-activation/v1` |
| `request_id` | Immutable canonical paid-market request identifier |
| `request_version` | Positive immutable request version |
| `request_digest` | Digest of the canonical request and its authority-neutral workload terms |
| `selection_receipt_id` | Immutable server-issued route-selection receipt |
| `selection_receipt_digest` | Digest of the accepted route evaluation |
| `quote_id` | Immutable server-issued quote identifier |
| `quote_version` | Positive immutable quote version |
| `quote_digest` | Digest of the canonical quoted terms |
| `fulfillment_descriptor_id` | Selected compute/model fulfillment descriptor |
| `fulfillment_descriptor_version` | Immutable descriptor version |
| `fulfillment_descriptor_digest` | Digest of the canonical descriptor |
| `currency` | Current `ValidatedQuote.settlement_currency`; `MarketRequest` has no currency field |
| `budget_micros` | Positive mandate-wide budget in integer micros |
| `spend_cap_micros` | Positive maximum spend per job in integer micros, not exceeding the budget |
| `fee_schedule_version` | Accepted immutable fee schedule version |
| `demand_commitment_digest` | Digest of the quoted workload/demand envelope |
| `acceptance_policy_digest` | Digest of the matching/acceptance policy |
| `settlement_policy_version` | Accepted immutable settlement-policy version |
| `deadline` | Positive epoch-seconds deadline copied from the canonical request |
| `quote_expires_at` | Deterministic RFC 3339 `Z` rendering of current integer `ValidatedQuote.expires_at` |

The object identifies the terms the user is confirming; it does not carry
positive authority. Actor, tenant, universe access, provider, host, credential,
wallet, payment authority, B2/B13 grant, lease, generation, fence, and
execution capability are server-derived or owned elsewhere and are forbidden
as caller fields.

`budget_micros` is the mandate-wide spend ceiling and `spend_cap_micros` is
the per-job ceiling; neither promises that one quote covers future work.
`acceptance_policy_digest` binds the canonical server-held route-selection
policy, per-job price/service constraints, reservation/retry/refund rules, and
any stricter per-job cap. A later job whose exact demand, quantity, landed
total, fee version, deadline, settlement policy, or service terms fall outside
that policy requires a new explicit acceptance.

The server re-resolves the canonical request, selection receipt, quote, and
descriptor and compares their current canonical versions and digests. From the
request it rehydrates and verifies the requester, tenant, capability digest,
payload digest, budget, spend cap, bid-window close, deadline, acceptance
policy, settlement policy, visibility, and fanout rather than trusting
caller-authored copies. The canonical `MarketRequest` has no universe field:
the agreement binds the exact target universe separately from the
server-derived current activation authority and never infers universe scope
from request contents. It verifies that the selected route is still the
explicitly accepted paid lane, that the quote is unexpired, uncancelled,
available to the actor/tenant and exact authorized target universe, within the
stated micros-denominated bounds, and backed by a still-acceptable market
state. Copying a deadline or expiry into the request cannot extend the
canonical value. Unknown fields and numeric coercion fail closed.

The v1 schema fixes its wire bounds rather than relying on language coercion:
all IDs inside `market_acceptance` are 1-128 ASCII characters matching
`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`; the top-level idempotency key retains
`write_graph`'s 16-128 ASCII-character bound and matches
`[A-Za-z0-9][A-Za-z0-9._:-]{15,127}`; every digest is exactly 64 lowercase hex
characters. Currency comes only from the rehydrated current
`ValidatedQuote.settlement_currency` without case normalization and matches
`[A-Za-z0-9][A-Za-z0-9._:-]{0,15}`; `MarketRequest` has no currency field.
`fee_schedule_version` and
`settlement_policy_version` are owner-native ASCII strings of 1-128 characters
matching `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`. Only `request_version`,
`quote_version`, `fulfillment_descriptor_version`, `deadline`,
`budget_micros`, and `spend_cap_micros` are strict JSON integers (Boolean,
float, decimal string, overflow, zero where positive is required, and negative
values are rejected) not exceeding signed 64-bit range. The paid-market
agreement owner's published `canonical_market_max_micros` is positive and no
greater than that range, and the invariant is
`0 < spend_cap_micros <= budget_micros <= canonical_market_max_micros`.
`quote_expires_at` is deterministically rendered from the current
`ValidatedQuote.expires_at` integer Unix epoch seconds as whole-second UTC
RFC 3339 `YYYY-MM-DDTHH:MM:SSZ`. The server parses it back to integer epoch
seconds and requires exact equality with the raw owner value; fractional
seconds, non-`Z` offsets, normalization, or caller formatting are never owner
truth. Deadline and raw quote expiry must equal their owner records, remain
future-valid, and fit the owner-defined maximum horizon. The exact schema is
versioned before any grammar, maximum, unit, or time encoding changes.

Alternatives considered:

- Sending only `quote_id` was rejected because an old UI could unknowingly
  confirm changed economic terms.
- Sending the complete provider offer was rejected because it invites callers
  to assert host, capacity, price, or authority facts.
- A generic JSON string was rejected because parsing ambiguity defeats closed
  schema validation and idempotency hashing.

### 3. Request-local identity authorizes the command; B2/B13 authorizes work

The identity owner derives the current authenticated OAuth subject and tenant
only through #1784's TinyAssets-owned per-message FastMCP reserve, actual
registered-handler claim, and live server registry entry. It mints a distinct
one-shot activation capability bound to the exact current message, claimed
execution, session, `write_graph` tool, `engine` target, action, principal,
tenant, and universe, then revokes it before result release. Outer ASGI
`ContextVar` identity alone, FastMCP inherited or snapshotted request fallback,
initialize/prior-message headers, and copied worker/task context are not
current-message authority. The capability is distinct from
`ProviderRequestCapability`, durable market authority, and B2; it is
non-serializable, non-delegable, non-replayable outside that invocation, and
cannot be minted for unauthenticated, background, scheduled, deferred, stdio,
or SSE work.

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

### 4. One transaction publishes agreement, mandate binding, and engine state

Activation uses the provider-routing assignment owner's single idempotent
storage transaction. Inside its coordinator, the server:

1. verifies request-local actor, tenant, universe write authority, action, and
   idempotency scope;
2. revalidates the canonical paid request, quote, descriptor, budget, spend
   cap, fee schedule, demand commitment, acceptance/settlement policy,
   deadline, expiry, cancellation, and capacity;
3. asks the paid-market owner's explicit accepted-agreement producer to
   invoke the internal tenant-scoped `paid_market.accept_agreement_v1`
   interface over the current canonical request, quote, and explicit
   confirmation without resubmitting or mutating the original market request;
4. asks the distributed-execution B13 root for a bounded, revocable,
   non-executable provisional mandate bound to that agreement, target
   universe, accepted selection/pricing policy, budget and per-job spend
   ceilings, expiry, revocation generation, and idempotency digest; and
5. asks the provider-routing assignment owner to atomically persist the
   agreement/mandate references, make the provisional reference current, and
   publish
   `accepted_market + remote_ready + []`.

If any step fails, none of those activation mutations commits. Payment and
settlement owners may have their own independently valid pre-existing records,
but this command must not leave a partial accepted agreement presented as an
active engine assignment. A provisional mandate becomes current and
discoverable only through the committed activation reference. If step 5 fails,
the composition owner idempotently revokes or allows expiry of that
non-executable provisional mandate; same-body retry finds the same provisional
identity and can never accumulate active mandates.

The idempotency identity is domain-separated by the canonical tool, target,
and action, then binds the authenticated actor, tenant, universe, and
`idempotency_key`: `write_graph/engine/activate_accepted_market`. It cannot
collide with request admission or another `write_graph` action. Independently,
the owner computes `activation_body_digest` as lowercase SHA-256 over
`UTF8("tinyassets/connector-market-activation/v1\0")` followed by the RFC 8785
JSON Canonicalization Scheme bytes for exactly
`{"target":"engine","action":"activate_accepted_market","graph_id":graph_id,
"market_acceptance":market_acceptance}`. `market_acceptance` contains exactly
the closed v1 field set; the top-level idempotency key is excluded because it
is bound separately in the identity. Transport envelopes, authorization
headers, renderings, omitted/defaulted fields, and unknown fields never enter
the projection. Any projection, algorithm, or domain change requires a new
activation schema version. A replay with the same digest returns the original
typed result. Reusing the key within that namespace with a different digest is
a conflict. Concurrent first activations have one winner; losers observe that
winner or a typed conflict. Cancellation, quote expiry, capacity loss, or
mandate revocation that wins before commit prevents activation.

Current authenticated subject, tenant, exact-universe write/admin authority,
current-message claim, and liveness are rechecked before every idempotency
lookup. Loss of any authority returns the same non-enumerating denial whether
or not the key or historical result exists. A same-body historical success is
side-effect stable but never reactivates expired/revoked authority: the replay
result identifies the historical commit and separately reports the
re-derived current assignment. If the mandate is now held, the connector
renders current held/repair state rather than stale `remote_ready` success.

Alternatives considered:

- Publishing `accepted_market` before the atomic accepted-agreement plus
  non-executable-mandate reference commit was rejected because it creates a
  phantom ready state. The later per-job B2 is intentionally absent here.
- Eventual reconciliation was rejected because `converse` could run in the
  gap and reach an ambient fallback.

### 5. Accepted-market `converse` dispatch is pre-routing and fail-closed

For an accepted-market universe, `converse` first re-derives the persisted
agreement and current B13-bound bounded-market mandate. After compiling the
concrete message into exact job demand, quantity, and capsule input, the B13
sole production composition root coordinates these owner-native operations:

1. the live-price/transport owner obtains a fresh executable firm quote and
   exact request-bound bid, deterministic match, atomic paid claim/fan-out
   slot, selected host/owner, versions, digests, and current fences;
2. the domain owner creates or consumes the exact fenced capacity
   grant/lease/work order for that demand and quantity;
3. `paid-market-economy` revalidates quote, fee, currency, service terms,
   expiry, and remaining mandate budget and records only the logical budget
   reservation/accounting intent;
4. the separately reviewed wallet/chain-effect successor required by the
   full-platform architecture §18.6 returns the requester-owned or explicitly
   delegated real-fund reservation/receipt;
5. B13 verifies the exact quote-to-bid link, current claim/slot, selected
   host, capacity fence, and that the B2 daemon/host equals the current paid
   claimant, then seals every owner-native identity/version/digest plus
   `job_id:lease_fence:accepted_result_sha256`, fee, and spend-ledger identity
   into the capsule; and
6. B13 issues the B2 grant bound to that sealed capsule, selected daemon/host,
   job, lease, generation/fence, capability ceiling, expiry, and idempotency
   identity.

B13 coordinates but cannot write another owner's records. Each owner exposes
body-bound idempotent prepare/commit/cancel operations. No B2 becomes
observable until every required result is current; failure before that point
releases or cancels each prepared owner result exactly once.

Only that exact B2 grant may enter the distributed-execution seam. Concurrent
jobs serialize independently at the claim slot, logical budget, domain
capacity, and real-fund owners; a loser holds before B2. Same-job retries reuse
the same owner-native results and B2. The B13 production composition root owns
the one global dispatch/cancel CAS/fence that chooses
`reserved -> dispatch_committed` or
`reserved -> cancelled_and_released`. If cancellation wins, B2 is absent or
revoked and every reservation releases once. If dispatch wins, pre-dispatch
release is forbidden. Later settlement/refund consumes the current
platform-signed `ExecutionTerminalV1`, its current generation/fence and
distributed-execution owner-CAS completion proof, plus domain acceptance
bound to `job_id:lease_fence:accepted_result_sha256`. Settlement requires
`terminal.job_id == job_id`, `terminal.fence == lease_fence`, and
`terminal.accepted_result_digest == accepted_result_sha256`; host
self-attestation or generic "accepted use" is insufficient. The connector
never invents those effects.

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
- **[Risk: cross-owner composition is operationally difficult]** → The
  provider-routing assignment owner coordinates the activation storage
  transaction. B13 coordinates the per-job owner-native prepare/commit/cancel
  protocol, publishes no B2 until every result is current, and compensates
  failed prepares idempotently without taking another owner's authority.
- **[Risk: quote or capacity expires during activation]** → Serialize the
  final revalidation and commit against owner-defined cancellation, expiry, and
  capacity fences; the losing operation returns a typed refusal.
- **[Risk: activation is mistaken for a pre-minted per-job B2 grant]** →
  Make the durable mandate explicitly non-executable and require fresh
  per-job quote, capacity, requester-funding, and B2 authority only after each
  concrete job/capsule exists.
- **[Risk: concurrent jobs oversubscribe claim slots, budget, capacity, or
  funds]** → Each owning contract serializes its own resource under one
  cross-owner job identity before B2 creation; B13 checks all current fences
  and release/refund remains exactly-once through owning contracts.
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
3. Land and integrate the paid-market accepted-agreement producer and current
   transport as internal `paid_market.accept_agreement_v1`; do not reinterpret
   request submission or matching as agreement acceptance.
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

No host design question remains in this target. Runtime starts only after
#1784's provider-routing assignment owner exposes the activation transaction;
the live-price/transport owner exposes request-bound bid/match/claim/slot and
selected-host results; applicable domain owners expose fenced capacity;
`paid-market-economy` exposes the accepted agreement plus logical reservation;
the reviewed full-platform architecture §18.6 successor exposes real-fund
authority; distributed-execution S14/B36 exposes fenced terminal settlement
identity; and B13 exposes provisional mandate plus cross-owner per-job B2
composition. The implementation successor advertises only repair actions it
proves live and records its numerical section-14 load envelope before the
gate.
