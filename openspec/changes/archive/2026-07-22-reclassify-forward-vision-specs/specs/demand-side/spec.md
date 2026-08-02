## REMOVED Requirements

### Requirement: The standing goal is the native demand unit
**Reason**: Shared Goal subscriptions and scheduling exist, but no standing-goal demand model or absent-user execution exists.
**Migration**: Existing shared goals remain in their canonical owners; standing goals move to the active future change.

### Requirement: Product rules (binding)
**Reason**: Archetype goal counts, week-one outcomes, terminal onboarding state, and per-universe metrics are not implemented.
**Migration**: Preserve these product outcomes under the active future change.

### Requirement: Goal bounties make demand transferable
**Reason**: Passive bounty metadata and escrow primitives do not compose into a claimable bounty lifecycle.
**Migration**: Keep the primitives under their existing owners and build bounties through the active future change.

### Requirement: Composition rules (pinned — Opus must not improvise these)
**Reason**: The six rules are not enforced by a bounty post, claim, gate, tranche, arbitration, expiry, or settlement surface.
**Migration**: Preserve the rules as future acceptance requirements.

### Requirement: Universe-to-universe services are deferred behind bounties
**Reason**: Services are absent, but there is no executable bounty-volume gate; absence alone is not an implemented capability.
**Migration**: Keep the defer rule as an active design and launch gate until it is measurable.
