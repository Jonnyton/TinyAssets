# Tier-1 Connector Accepted-Market Authority Audit

**Date:** 2026-07-26

**Audited base:** `origin/main` `cf30da16e020db19d8374e6568c9d4eeb2689bc8`

**Change:** `activate-connector-requester-authority`

**Authority:** target OpenSpec and audit only. This artifact grants no API,
runtime, router, provider invocation, market acceptance, payment, migration,
deployment, or production authority.

## Finding

The live connector has no complete path by which an authenticated Tier-1
chatbot user can explicitly accept market-priced compute for a universe and
then use that compute without reaching an ordinary provider chain. The exact
successor assigned by #1784 is therefore necessary, but it must remain a
composition of four existing capability owners rather than a new top-level
primitive.

The clean public action is:

```text
write_graph(
  target="engine",
  action="activate_accepted_market",
  graph_id=<target universe>,
  idempotency_key=<body-bound key>,
  market_acceptance=<strict typed acceptance>
)
```

This uses one of the seven canonical handles, does not revive the deprecated
`universe` handle, and keeps engine authority out of the operator Request plus
epoch-2 BranchTask intake contract.

## Current Runtime Trace

### Connector admission

- `tinyassets/universe_server.py:525` owns `write_graph`. Its current targets
  are goal, request, branch, and universe; it has no engine activation target.
- Request intake delegates to `tinyassets/api/universe.py:2012`
  (`admit_request_v2`) and `_action_admit_request_v2` near line 1840.
- `_REQUEST_TYPES` near line 1793 is closed to
  `scene_direction|revision|canon_change|branch_proposal|general`.
- `_request_body_digest` near line 1813 binds the exact closed request body.
  Reusing this contract for engine activation would either smuggle economic
  authority through free text or force a competing Request/BranchTask
  workflow. Neither shape is accepted.

### Request identity

- HTTP bearer authentication enters a request-local `ContextVar` through
  `tinyassets/auth/middleware.py`; WorkOS JWT validation and subject/org
  derivation live in `tinyassets/auth/workos_provider.py`.
- `tinyassets/api/permissions.py` derives operator request actor and tenant
  server-side and checks exact universe access.
- `tinyassets/api/engine_helpers.py:_current_actor` still has an ambient
  `UNIVERSE_SERVER_USER` fallback. The accepted-market action must never call
  this helper or infer authority from process environment.

### Converse routing and setup

- `tinyassets/universe_server.py:985` authenticates `converse` and delegates to
  `tinyassets/universe_intelligence.py:478`.
- The intelligence path currently calls `tinyassets/providers/call.py:213`
  unconditionally, then enters the ordinary `ProviderRouter`, preferred
  writer, allowed-provider, API-key, quota, and fallback chains.
- There is no pre-router accepted-market execution path.
- `tinyassets/api/universe.py:5809` builds engine setup output only from
  provider-chain exhaustion plus no assigned engine. Its only historical setup
  path is raw BYO API key, while legacy `market_rented` metadata can suppress
  setup without authorizing execution.
- No runtime symbol for `accepted_market`, `remote_ready`, or the required
  durable accepted-market activation currently exists.

### Market and execution authority

- `tinyassets/payments/market_workflow.py` has a tenant-scoped workflow,
  verified requester authority, body-bound idempotency, budget/spend bounds,
  deadlines, and acceptance policy. It is not connected to a canonical MCP
  handle.
- `tinyassets/paid_market/quotes.py` and routing helpers validate and rank
  quotes. Ranking deliberately grants no reservation, money, provider, host,
  or execution authority.
- `tinyassets/execution_authority/records.py:179` defines the B2
  `ExecutionGrantV1`, binding owner, daemon, job, capsule, lease,
  generation/fence, capability ceiling, expiry, and idempotency.
- Distributed-execution tests prove that queue claims, admissions, and
  provider receipts cannot be promoted to B2 authority. Nothing in
  `converse` consumes the B2/B13 production route today.

## Owner Map

| Capability | This successor owns | It must not steal |
|---|---|---|
| `identity-auth-and-access-control` | #1784 TinyAssets current-message reserve, actual handler claim/liveness, OAuth requester, tenant, exact universe, message/session/tool/action binding, revocation before result | Outer ContextVar/FastMCP snapshot/prior-message/copied-worker authority, caller actor/tenant, `ProviderRequestCapability` substitution, durable replay |
| `paid-market-economy` | Explicit accepted-agreement producer over the canonical request and quote, bounded mandate, logical budget reservation/accounting intent, tenant workflow, domain-separated body-bound idempotency | Treating submission/match/claim as acceptance; creating domain capacity, real-fund/wallet/chain authority, selected-host authority, settlement finality, or execution authority |
| `distributed-execution` | B13 provisional non-executable mandate and sole cross-owner per-job composition of allocation/claim, domain capacity, logical accounting, §18.6 real-fund, S14/B36, and exact B2 plus Engine OS admission | Writing another owner's records, pre-minting future-job B2, or promoting request/match/claim/row/receipt/reservation evidence |
| `live-mcp-connector-surface` | Exact action/input/result, rendered confirmation, refusal, repair, and renewal | New MCP handle, raw grant/secret/payment carrier, deprecated handle, or desktop prerequisite |
| `provider-routing` (#1784) | Existing assignment/activation-transaction owner: agreement/mandate references, `accepted_market + remote_ready + []`, pre-router seam, ordinary-chain bypass, held state | No delta in this successor |
| live price / Wave 2 | Exact request-bound quote→bid→deterministic-match→atomic paid-claim/slot, selected host, versions/digests/fences, delivery lifecycle | No price-index or operator-request delta in this successor |
| domain capacity owners | Domain-native capacity grant/lease/work order and semantic acceptance | No generic market or connector replacement |
| architecture §18.6 successor | Sole requester real-fund/wallet/chain-effect authority and verified receipts | No PostgreSQL logical reservation promoted to custody |

BYOC, local-model, stdio, tray, and plugin activation belong exclusively to
`activate-requester-host-engines`.

## Required Acceptance Boundary

The connector supplies only server-verifiable references and explicit user
limits: canonical request identity/version/digest, selection/evaluation
receipt identity and digest, firm quote identity/version/digest, accepted
integer-micros budget and per-job spend cap, settlement currency,
fee-schedule and settlement-policy versions, deadline, and acceptance policy.

The server derives or reloads the actor, tenant, universe, canonical request's
capability/payload/bid-window/policy/visibility/fanout fields, descriptor,
demand commitment, quote contents, issuer/capacity evidence, host,
domain-capacity result, wallet/chain receipt, and B13 market-mandate authority. Caller-supplied
versions of those authority objects are rejected. The mandate is ongoing but
bounded by the accepted budget, per-job spend cap, and selection policy; it is
neither a reservation nor job authority. Because B2 binds a concrete
job/capsule, it is not created during activation. After the later message and
job exist, B13 coordinates the live-price/transport owner's exact
request/quote/bid/match/paid-claim/slot and selected host, the domain owner's
fenced capacity, paid-market's logical budget reservation/accounting intent,
the architecture §18.6 successor's requester real-fund result, and
distributed-execution S14/B36. Only then may it produce the exact B2.

One production composition boundary must atomically establish the accepted
agreement, current settlement prerequisites, the non-executable B13-bound
bounded-market mandate, and exclusive universe assignment:

```text
engine_source="accepted_market"
engine_assignment_state="remote_ready"
allowed_providers=[]
```

Any failure leaves no `remote_ready` mutation and authorizes no execution or
maintainer spend. Same-key/same-body replay returns the original typed result;
same-key/different-body reuse conflicts after current actor and universe
authorization is rechecked. The activation idempotency namespace is
domain-separated from request admission and every other target/action. A
provisional B13 mandate becomes current only through the committed activation
reference; failed commits revoke or expire it idempotently, and retries cannot
accumulate mandate authority.

Each later `converse` authenticates its own message and revalidates the
durable bounded-market mandate. B13 coordinates owner-native idempotent
prepare/commit/cancel results and seals the exact request, bid, match, claim,
slot, selected host, quote-to-bid link, logical budget reservation, domain
capacity fence, §18.6 real-fund receipt, fee/spend ledger, S14/B36
`job_id:lease_fence:accepted_result_sha256`, demand, quantity, daemon/host,
capsule, and lease identities into B2. The daemon/host must equal the current
paid claimant. Each owner serializes its own resource; B13 writes none of
them. One fenced CAS chooses `dispatch_committed` or
`cancelled_and_released`. The cancel winner prevents/revokes B2 and releases
once; the dispatch winner forbids pre-dispatch release. Settlement/refund
requires current platform-signed B2 terminal evidence plus domain acceptance,
never host self-attestation.
An activation, quote, reservation, or mutable database row is never itself
executable authority. Missing, expired, revoked, fenced, overspent, consumed,
or inconsistent state maps to held repair/renewal and never to maintainer,
local, BYOC, free, or ordinary provider fallback.

## Open Implementation Dependencies

- #1784 accepted-market assignment, fail-safe hold, and pre-routing tasks.
- `paid-market-live-price-discovery` executable firm quote, secure connector
  read/handoff, load, and rendered-proof tasks.
- `paid-market-track-e-wave-2-transport` production baseline/migrations,
  canonical router delegation, delivery/fence integration, and concurrency
  evidence.
- A paid-market accepted-agreement producer distinct from request submission,
  bidding, matching, claiming, and delivery.
- Distributed-execution B13 production composition, trust/custody, per-job
  cross-owner composition, S14/B36 fenced terminal settlement identity, and
  live B2 proof.
- Every applicable domain-native capacity/acceptance owner.
- The reviewed wallet/chain-effect successor required by
  `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6.
- Engine OS execution admission (#1573 target; reconciled implementation
  successor).
- A single transactional persistence boundary for activation plus an atomic
  per-job budget/capacity/funding boundary. Independent best-effort writes to
  current request, market, wallet, capacity, or universe stores cannot satisfy
  either invariant.

No runtime implementation may start through this target lane. Each dependency
must land under its own claim, or the implementation successor must record an
exact dependency and refuse partial activation.

## Fresh Verification

On 2026-07-26 in the Windows worktree, the current relevant baseline passed:

```text
python -m pytest -q \
  tests/test_request_admission_surface.py \
  tests/test_converse_handle.py \
  tests/test_current_actor_auth_context.py \
  tests/test_paid_market_routing.py \
  tests/test_paid_market_workflow.py \
  tests/test_distributed_execution_authority.py
```

Result: **73 passed in 14.81 seconds**. This proves the current seams are
internally consistent; it does not prove accepted-market activation, which
does not exist.

Before cutover the implementation successor must add focused authorization,
schema bounds/coercion/idempotency/non-enumeration/current-replay truth,
quote/bid/match/claim/slot/selected-host binding, owner-isolated
budget/capacity/funding oversubscription, dispatch-vs-cancel CAS,
signed-terminal/domain-acceptance settlement, retry/release/refund, B2/B13,
expiry/revocation/fence, pre-router refusal, and
no-maintainer-fallback tests; run the full-platform architecture §14
concurrent load proof; pass public canaries; complete a rendered chatbot
conversation through
`https://tinyassets.io/mcp`; and record post-fix clean-user evidence or a
dated watch item.
