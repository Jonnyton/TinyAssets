## REMOVED Requirements

### Requirement: Money movement goes through market.apply_tx() and nothing else (HARD RULE)
**Reason**: `market.apply_tx` exists only in prototype SQL while current callable actions directly use SQLite payment helpers, contradicting this rule.
**Migration**: Keep current default-off transport truth in `paid-market-economy`; require an explicit future cutover and differential proof.

### Requirement: Token-normalized settlement (Wave 3a)
**Reason**: Prototype columns exist, but completion-token enforcement and dispute handling do not.
**Migration**: Move the full transport requirement to the active future change.

### Requirement: Composite spot quote never fabricates liveness
**Reason**: A pure quote oracle exists, but feed acquisition, per-field freshness, stale fallback, and publication are absent.
**Migration**: Specify the actual oracle in `paid-market-economy`; build liveness behavior later.

### Requirement: Spot/forward quote surface is unauthenticated, cached, and MCP text-block safe
**Reason**: No price HTTP or MCP surface is shipped.
**Migration**: Move the surface to the active future change and require public-surface acceptance.

### Requirement: Thin-market manipulation posture on the index
**Reason**: The implementation caps direction-insensitive counterparty pairs, not users, so the stated per-user rule is contradicted.
**Migration**: Canonicalize pair-capped behavior; change to a per-user rule only through a future behavior change.

### Requirement: Standardized capacity forwards
**Reason**: Pure bucket and state helpers exist, but no posting, purchase, book, or published best ask exists.
**Migration**: Keep pure validation canonical; move the order lifecycle to the active future change.

### Requirement: Forward settlement is demand-relative, pro-rata, and conservation-exact
**Reason**: The pure oracle is built, but the capability file presents it as part of an unbuilt live forward market.
**Migration**: Move the full pure contract to `paid-market-economy`; retain transport integration as future work.

### Requirement: Uniform buyer caps with machine-readable rejection
**Reason**: No price-cap or spend-cap request path exists.
**Migration**: Move the target to the active future change.

### Requirement: Forwards require collateral by construction; spot posture unchanged
**Reason**: Collateral arithmetic exists, but no post-and-lock lifecycle exists.
**Migration**: Keep the arithmetic canonical and build lock-on-post later.

### Requirement: Demand-forecast signal is privacy-gated off by default
**Reason**: No demand-signal flag or surface exists.
**Migration**: Preserve it as future privacy-gated behavior.

### Requirement: Cash-settled and secondary instruments are out of scope
**Reason**: The pure state machine lacks those transitions, but there is no callable boundary that refuses such requests.
**Migration**: Require explicit refusal in the future transport change.
