## REMOVED Requirements

### Requirement: The accessible ladder, with an honesty clause binding on all copy
**Reason**: Pure shuttle math does not enforce an FPGA-before-shuttle ladder, and the current allocator accepts no gate proof.
**Migration**: Preserve the ladder under the active future change; retain only arithmetic in `paid-market-economy`.

### Requirement: Shuttle economics — knowable price, isolated failure (implemented)
**Reason**: Allocation and break-even math are built, but the claimed survivor-price isolation is contradicted by largest-remainder rounding, and gate-driven removal, persistence, and fab-failure orchestration are absent.
**Migration**: Extract the pure arithmetic to `paid-market-economy`; move the lifecycle target to the active future change.

### Requirement: Verification chain mints a hardware capability
**Reason**: No bring-up-to-capability mint integration exists.
**Migration**: Move the target to the active future change.

### Requirement: Physical fabrication reuses commons + gates + exact quoting (implemented)
**Reason**: Pure quotation, ranking, and settlement are built, but commons artifacts, paid requests, and QA gates are absent.
**Migration**: Extract pure behavior to `paid-market-economy`; keep integration active and unbuilt.

### Requirement: Mechanical designs are parametric programs, not meshes (binding)
**Reason**: No code-CAD admission or build-output enforcement is shipped.
**Migration**: Move the target to the active future change.

### Requirement: Pricing-as-query returns three un-conflated stages with a pinned break-even
**Reason**: A break-even helper exists, but no three-stage read surface or cross-surface payload does.
**Migration**: Keep pure break-even math canonical; build the query surface later.

### Requirement: Garage silicon is a device market and a learning ladder, not a compute market
**Reason**: No enforceable product or copy surface exists.
**Migration**: Preserve the honesty requirement under the active future change.

### Requirement: Garage-fab listings carry a fail-closed safety-documentation gate (REQUIRED)
**Reason**: No listing validator or process-chemistry safety schema is shipped.
**Migration**: Preserve the safety gate under the active future change.
