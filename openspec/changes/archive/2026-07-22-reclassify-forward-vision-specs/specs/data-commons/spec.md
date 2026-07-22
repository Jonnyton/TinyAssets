## REMOVED Requirements

### Requirement: The dataset asset is content-addressed and reference-only
**Reason**: No dataset asset registry or reference-only manifest transport is implemented.
**Migration**: Move the target to `build-forward-platform-capabilities`.

### Requirement: License propagation is fail-closed (implemented)
**Reason**: A pure license lattice exists, but no training admission or mint boundary invokes it.
**Migration**: Specify the pure helper under `paid-market-economy`; keep end-to-end enforcement active and unbuilt.

### Requirement: Data pricing is not compute pricing
**Reason**: Dataset pricing modes and `data_ppm` settlement are not implemented.
**Migration**: Generic exact apportionment remains in `paid-market-economy`; dataset pricing moves to the active future change.

### Requirement: Contamination and quality checks gate gate-meaning (transport, named)
**Reason**: No dataset contamination or quality admission gate is shipped.
**Migration**: Move the target to the active future change.

### Requirement: Contributor attribution reuses exact apportionment
**Reason**: Exact apportionment exists, but dataset contributor records and payout integration do not.
**Migration**: Keep the pure apportionment contract under `paid-market-economy`; build dataset attribution later.

### Requirement: Dataset Forge is a commons workflow, not a platform service (design law)
**Reason**: No Dataset Forge or example-level provenance-manifest workflow is shipped.
**Migration**: Preserve the workflow target under the active future change.
