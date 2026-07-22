## REMOVED Requirements

### Requirement: MCP both directions; connections live in the resource ledger
**Reason**: Only inbound MCP is shipped; outbound connection binding and a resource ledger are future behavior.
**Migration**: Inbound MCP remains owned by `live-mcp-connector-surface`; the target moves to `build-forward-platform-capabilities`.

### Requirement: Action caps are the second autonomy column
**Reason**: Current consent and authority gates do not implement numeric per-action caps.
**Migration**: Preserve current gates under `external-effect-receipts`; add caps only through the active future change.

### Requirement: Exactly-once effects (HARD RULE — Opus must not improvise)
**Reason**: Selected effectors have per-sink receipts, but the specified deterministic key, generic journal, and whole-batch hold do not exist.
**Migration**: The shipped narrower lifecycle moves to `external-effect-receipts`; the stronger contract remains active future work.

### Requirement: Human-as-sensor goal inbox and timezone-aware scheduling
**Reason**: Durable schedules exist, but goal inbox ingestion and per-goal timezone scheduling do not.
**Migration**: Existing schedules remain in `daemon-runtime-and-dispatch`; inbox and timezone behavior moves to the active future change.

### Requirement: HARD RULE — adapters never see credentials
**Reason**: The proposed commons adapter proxy is not implemented; current trusted effectors resolve credentials daemon-side.
**Migration**: Future adapters must implement this boundary in `build-forward-platform-capabilities`.

### Requirement: Non-MCP APIs are covered by commons adapters
**Reason**: No OpenAPI-to-MCP adapter generator, registry, or runtime is shipped.
**Migration**: Reintroduce only through the active future change.

### Requirement: Addressable inboxes and typed artifact flows fail loud at design time
**Reason**: The content-addressed typed flow is absent, and current unknown graph types fall back to `Any` rather than failing.
**Migration**: Current graph behavior remains owned by `graph-execution-substrate`; the stricter target moves to the active future change.
