## Why

TinyAssets requires §14 concurrency/load proof for every uptime-track capability, but current changes independently restate evidence fields while the only cross-platform harness plan is a stale April pre-draft. Without one shared evidence contract, unavailable substrates can be mistaken for green proof, reported percentiles cannot be independently recomputed, and capability-specific load results cannot be compared or rolled up honestly.

## What Changes

- Add a shared, versioned production-load evidence contract for immutable run manifests, environment fingerprints, raw metrics and traces, invariant-oracle results, fault timelines, reconciliation, and baseline comparisons.
- Standardize terminal verdicts as `passed`, `failed`, or `not_run`, with failure-first rollup over required and applicable scenarios and machine-readable blocking-substrate reasons for `not_run`.
- Separate protocol conformance from scenario outcomes so the evidence machinery can be proven while scenarios lacking declared real substrates or real-equivalent isolated environments remain visibly `not_run`.
- Keep workload definitions, thresholds, adapters, faults, and invariant predicates with their capability owners; the shared contract owns only how evidence is recorded and evaluated.
- Explicitly prohibit mock or shaped execution from being reported as passed production evidence.
- Supersede the April Track J pre-draft as implementation authority while retaining it as historical scenario research.

## Capabilities

### New Capabilities

- `production-load-evidence`: Defines the cross-capability §14 scenario registry and evidence protocol, terminal verdict algebra, substrate honesty rules, and independently recomputable run artifacts.

### Modified Capabilities

None. Capability owners will adopt the shared schema in later, separately claimed changes without moving their workload mixes or thresholds into this change.

## Impact

This proposal adds target-only OpenSpec artifacts and supersedes one legacy planning document. A later implementation change will own the protocol code under `tests/load/_protocol/` after the current `tests/load/` claim releases. This change does not implement scenario adapters, change public MCP behavior, modify deployment, or grant production-readiness authority. The connector conversation remains the first-class product surface; Agent Village is outside this capability except for a possible future operator-observability scenario after the platform primitives mature.
