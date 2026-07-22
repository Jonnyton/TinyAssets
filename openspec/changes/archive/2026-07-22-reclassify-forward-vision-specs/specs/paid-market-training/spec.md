## REMOVED Requirements

### Requirement: Training reuses the hardened forward properties unchanged
**Reason**: The pure oracle is built, but no training-market transport or persistence invokes it.
**Migration**: Move the oracle contract to `paid-market-economy`; preserve live integration as future work.

### Requirement: Three-tier instrument ladder with a democratization tier that never blocks the base
**Reason**: No F1/F2/F3 instrument or gang/swarm lifecycle exists.
**Migration**: Move F1/F2 to the active future change and keep F3 separately research-gated.

### Requirement: Checkpoint-based settlement (implemented)
**Reason**: Checkpoint math exists, but attestation and streamed payment release do not.
**Migration**: Canonicalize the pure computation under `paid-market-economy`; build transport later.

### Requirement: Verification prices fraud above honest work
**Reason**: No attestation, loss-curve, re-execution, or evaluation-probe layer exists.
**Migration**: Preserve the verification target under the active future change.

### Requirement: Gates are the native training abstraction
**Reason**: Generic goals and gates are not integrated with training instruments or payment.
**Migration**: Build the integration through the active future change.

### Requirement: Capability minting closes the loop with license propagation enforced at mint
**Reason**: Pure license composition exists, but no training completion or mint boundary invokes it.
**Migration**: Keep the pure lattice in `paid-market-economy`; require end-to-end enforcement later.

### Requirement: Data is buyer-supplied in Wave 1 (scoped deliberately)
**Reason**: No training-run transport or URI/hash provenance schema exists.
**Migration**: Preserve the Wave 1 boundary under the active future change.
