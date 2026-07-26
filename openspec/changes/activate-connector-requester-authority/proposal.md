## Why

A Tier-1 user arriving through the live chatbot connector can create a universe but cannot currently authorize accepted-market compute for it. The shipped path either reaches the ordinary provider router, advertises raw BYO-key setup, or records legacy `market_rented` metadata that grants no execution authority; none of those paths may spend maintainer quota or satisfy the zero-host-online product contract.

## What Changes

- Add one named, connector-completable `action="activate_accepted_market"` under the existing `write_graph` handle with `target="engine"`. No eighth MCP handle, deprecated `universe` target, raw secret deposit, desktop prerequisite, or free-form text authority is introduced. Engine activation remains separate from the closed operator-request contract, which creates a Request plus epoch-2 BranchTask for work intake.
- Require an explicit, typed acceptance of a current market quote and bounded spend terms. The server derives the authenticated actor and tenant, revalidates universe authority, quote identity/version/digest/expiry, capacity and economic limits, and refuses caller-supplied provider, host, credential, actor, tenant, or execution-grant authority.
- Compose the accepted economic agreement with a current, non-executable B13-bound bounded-market mandate at one named atomic boundary. The universe becomes `engine_source="accepted_market"` and `engine_assignment_state="remote_ready"` with `allowed_providers=[]` only if that full composition commits; otherwise no activation state is published.
- Route every later `converse` through the accepted-market B13 composition root before the ordinary provider router. After the concrete message determines demand and quantity, the market owner must supply a fresh executable firm quote, capacity consumption, and requester-funded spend reservation within the accepted mandate; B13 then binds those exact owner-native references/digests into the sealed capsule and per-job B2 grant. Missing, expired, revoked, fenced, overspent, or inconsistent activation, economic, capacity, funding, or per-job authority returns a typed, connector-completable repair state and never falls through to maintainer, local, BYOC, free, or role-based provider chains.
- Keep quote/ranking, request/bid/match/claim, escrow/settlement, execution-grant minting, sandbox admission, and requester-host/BYOC custody with their existing owners. This change consumes those outputs; it does not redefine or bypass them.
- Require strict idempotency, same-key/different-body conflict handling, concurrent activation/cancel/expiry/revocation proof, public canaries, and a rendered chatbot conversation through `https://tinyassets.io/mcp` before cutover.

## Capabilities

### New Capabilities

None. This change composes four existing capability owners and adds no new top-level platform primitive.

### Modified Capabilities

- `identity-auth-and-access-control`: Binds activation to the current OAuth subject, tenant, exact universe, request/session/tool context, and one-shot non-replayable authority without environment or maintainer fallback.
- `live-mcp-connector-surface`: Adds the accepted-market activation request to the existing canonical `write_graph` handle and renders typed success, refusal, and repair results without exposing authority carriers or secrets.
- `paid-market-economy`: Defines the explicit bounded mandate that activation may consume and the fresh per-job executable quote, capacity-consumption, funding-reservation, retry/release, and settlement outputs required before dispatch, while preserving the rule that ranking, matches, and claims alone grant no money, provider, or execution authority.
- `distributed-execution`: Requires activation to consume a non-executable B13-bound mandate and each concrete `converse` job to bind its exact demand, quantity, firm quote, capacity consumption, funding reservation, and spend ceiling into the sealed capsule and B2 grant, without promoting queue, request, market, provider-attempt, or admission receipts into execution authority.

## Impact

The eventual implementation will touch the canonical `write_graph` router, connector metadata/results, request-local identity, paid-market workflow/quote validation, universe engine-assignment state, the pre-router `converse` dispatch seam, distributed-execution grant consumption, storage transaction boundaries, and focused concurrency/security tests. It explicitly depends on `paid-market-track-e-wave-2-transport`, the merged provider-authority owner (#1784), paid-market owners (#1786/#1798), branch access (#1797), and execution admission (#1573). It deliberately does not modify or reuse `operator-request-trigger-contract`. This proposal grants target authority only; it does not authorize runtime, payment, deployment, or production mutation.
