## REMOVED Requirements

### Requirement: The math that must not drift (implemented)
**Reason**: Pure ordered-input and apportionment math is built, but persisted arrival order and pool lifecycle are absent.
**Migration**: Move the pure contract to `paid-market-economy`; preserve persistence as future work.

### Requirement: Attribution splits pay the lineage first and jointly conserve
**Reason**: A caller-supplied single-event split is built, but frozen lineage tables and recursive revenue events are absent.
**Migration**: Keep pure distribution canonical; build persisted lineage later.

### Requirement: Ownership is deliberately minimal in v1 — no secondary share transfer
**Reason**: No ownership record or callable transfer/refusal surface exists.
**Migration**: Preserve non-transferability as a legal and future acceptance gate.

### Requirement: Risk is stated on the tin
**Reason**: Refund math exists, but no pool-terms surface or terminal-run integration exists.
**Migration**: Build terms and terminal settlement through the active future change.
