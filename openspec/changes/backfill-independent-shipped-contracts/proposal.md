## Why

Nine shipped behavior groups remain materially absent from canonical OpenSpec even though they have no collision with an active implementation change. Until they are backfilled, `openspec/specs/` is truthful but incomplete as an as-built inventory.

## What Changes

- Specify current community-patch PR creation, loop health, nested Patch Packet extraction, and completed-run reuse.
- Specify cumulative multi-shot ASP validation, the installed desktop entrypoint, coordination drift/JSON diagnostics, domain-owned branch and episodic registries, provider bridge retries, Goal compatibility aliases, and wiki maintenance actions.
- Add an `external-effect-adapters` capability for the shipped GitHub PR/merge, Twitter, wiki-writeback, and Windows desktop sinks plus system-owned receipt/quarantine behavior.
- Record only current behavior and its current limitations; no runtime behavior changes.

## Capabilities

### New Capabilities

- `external-effect-adapters`: shipped external-write sink dispatch, authority/consent gates, idempotent receipts, run-snapshot evidence, and forged-evidence quarantine.

### Modified Capabilities

- `community-patch-loop`: add the shipped auto-ship PR, health, nested-packet, and completed-run contracts.
- `constraint-evaluation`: add cumulative incremental multi-shot grounding behavior.
- `desktop-host-runtime`: add the canonical installed GUI entrypoint and distinguish it from the legacy source launcher.
- `development-coordination-runtime`: add required-artifact/skill-mirror drift checks and automation-facing JSON modes.
- `domain-plugin-runtime`: add domain-owned Branch-slug and episodic-coordinate registries.
- `provider-routing`: add the three-attempt exhaustion retry and fallback contract.
- `shared-goals-and-convergence`: add the four shipped ChatGPT compatibility aliases.
- `wiki-commons`: add cosign, guarded delete, consolidation, lint, and project-sync semantics.

## Impact

This is specification-only reconciliation. It updates nine canonical capability owners using evidence from the existing runtime, scripts, and focused tests; it does not change code, storage, public MCP behavior, or deployment state.
