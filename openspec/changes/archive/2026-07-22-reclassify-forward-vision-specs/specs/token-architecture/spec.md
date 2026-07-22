## REMOVED Requirements

### Requirement: The wall — TINY never appears in any settlement path
**Reason**: Current settlement defaults to internal `MicroToken`, and importing `tinyassets.paid_market` imports the fund module, contradicting the stated module wall.
**Migration**: Describe current internal arithmetic under `paid-market-economy`; define any future stablecoin/TINY boundary explicitly.

### Requirement: Fund discipline — mint/redeem at NAV only, rounding favors the fund (implemented)
**Reason**: Safe pure NAV math exists, but the requirement incorrectly permits first-mint pricing of a pre-seeded treasury that hardened code refuses.
**Migration**: Canonicalize the explicit refusal and exact arithmetic in `paid-market-economy`.

### Requirement: Conservative valuation — realized cash flow only, never mark-to-model
**Reason**: The fund accepts caller-computed AUM and has no valuation ledger or reporting job.
**Migration**: Move auditable valuation to the counsel-gated active future change.

### Requirement: Mixed-asset current-state binding rules
**Reason**: Fee and capacity helpers exist, but live pricing, personal liquidity, treasury seeding, and founder-token restrictions do not.
**Migration**: Keep pure fee/capacity math canonical; preserve product policy as future work.
