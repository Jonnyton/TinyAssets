## Why

A Tier-1 user arriving through the live chatbot connector can create a universe but cannot currently authorize accepted-market compute for it. The shipped path either reaches the ordinary provider router, advertises raw BYO-key setup, or records legacy `market_rented` metadata that grants no execution authority; none of those paths may spend maintainer quota or satisfy the zero-host-online product contract.

## What Changes

- Add one named, connector-completable `action="activate_accepted_market"` under the existing `write_graph` handle with `target="engine"`. No eighth MCP handle, reuse of the live `target="universe"` birth path, legacy `universe` handle, raw secret deposit, desktop prerequisite, or free-form text authority is introduced. Engine activation remains separate from the closed operator-request contract, which creates a Request plus epoch-2 BranchTask for work intake.
- Require an explicit, typed acceptance of a current market request, quote, and micros-denominated budget/spend terms. The server derives the authenticated actor and tenant, rehydrates the full canonical request context, revalidates universe authority, quote identity/version/digest/expiry, capacity and economic limits, and refuses caller-supplied provider, host, credential, actor, tenant, or execution-grant authority.
- Compose the accepted economic agreement with a provisional, non-executable B13-bound bounded-market mandate at the provider-routing assignment owner's named atomic commit. The mandate reference becomes current and the universe becomes `engine_source="accepted_market"` and `engine_assignment_state="remote_ready"` with `allowed_providers=[]` only if that full commit succeeds; otherwise no activation state or current mandate is published.
- Route every later `converse` through the B13 sole production composition root before the ordinary provider router. After the concrete message determines demand and quantity, B13 coordinates—but does not impersonate—the live-price/transport owner for the exact request-bound quote/bid/match/paid-claim/slot and selected host, the domain owner for fenced capacity, `paid-market-economy` for logical budget reservation/accounting intent, and the architecture §18.6 wallet/chain-effect successor for requester real-fund authority. B13 binds those owner-native results and S14/B36 settlement identity into the sealed capsule and per-job B2 grant. Missing, expired, revoked, fenced, overspent, or inconsistent allocation, economic, capacity, funding, or per-job authority returns a typed repair state and never falls through to maintainer, local, BYOC, free, or role-based provider chains.
- Keep quote/ranking, request/bid/match/claim, escrow/settlement, execution-grant minting, sandbox admission, and requester-host/BYOC custody with their existing owners. This change consumes those outputs; it does not redefine or bypass them.
- Require strict idempotency, same-key/different-body conflict handling, concurrent activation/cancel/expiry/revocation proof, public canaries, and a rendered chatbot conversation through `https://tinyassets.io/mcp` before cutover.

## Capabilities

### New Capabilities

None. This change composes four existing capability owners and adds no new top-level platform primitive.

### Modified Capabilities

- `identity-auth-and-access-control`: Binds activation to the current OAuth subject, tenant, exact universe, request/session/tool context, and one-shot non-replayable authority without environment or maintainer fallback.
- `live-mcp-connector-surface`: Adds the accepted-market activation request to the existing canonical `write_graph` handle and renders typed success, refusal, and repair results without exposing authority carriers or secrets.
- `paid-market-economy`: Defines the accepted-agreement producer and per-job logical budget reservation/accounting intent, while preserving the rule that submission, ranking, matching, claiming, database accounting, or provider evidence grants no domain capacity, real-fund, wallet/chain, host, or execution authority.
- `distributed-execution`: Makes B13 the cross-owner per-job composition coordinator and requires each concrete `converse` job to bind its exact demand, quantity, request/bid/match/claim/slot, selected host, firm quote, domain-fenced capacity, logical accounting intent, §18.6 real-fund result, S14/B36 settlement identity, and spend ceiling into the sealed capsule and B2 grant without promoting any one input into execution authority.

## Impact

The eventual implementation will touch the canonical `write_graph` router, connector metadata/results, request-local identity, paid-market workflow/quote validation, universe engine-assignment state, the pre-router `converse` dispatch seam, distributed-execution grant consumption, storage transaction boundaries, and focused concurrency/security tests. It explicitly depends on `paid-market-track-e-wave-2-transport`, the merged provider-authority/assignment owner (#1784), paid-market owners (#1786/#1798), every applicable domain capacity owner, branch access (#1797), execution admission (#1573), distributed-execution S14/B36 in `docs/exec-plans/active/2026-07-18-distributed-execution-platform.md`, and the reviewed wallet/chain-effect successor required by `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6. It deliberately does not modify or reuse `operator-request-trigger-contract`. This proposal grants target authority only; it does not authorize runtime, payment, deployment, or production mutation.
