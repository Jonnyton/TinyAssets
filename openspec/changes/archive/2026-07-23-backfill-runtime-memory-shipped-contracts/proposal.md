## Why

Four shipped runtime and memory behavior groups remain incompletely covered by canonical OpenSpec even though their current owners do not overlap any active delta destination. Backfilling them now closes half of the remaining reverse-coverage gap without importing future distributed-execution or OKF-store guarantees.

## What Changes

- Specify explicitly flagged latest-loop-soul selection, bounded/versioned behavior updates, and the current REST host-pool registration, pricing/capacity, heartbeat, deregistration, and callback-isolation behavior. Soul-wiki scaffolding remains owned by the existing `knowledge-retrieval-and-memory` requirement.
- Specify claimed-task heartbeat ownership, cooperative queue cancellation, terminal queue archival, and the callable-but-unwired blanket recovery helper.
- Specify live and frozen-version child-Branch invocation, mapping, depth, wait/failure behavior, receipt-wait interruption, validated one-shot attachment of an already-completed child run, and the separate `run_branch resume_from` new-run lineage contract.
- Specify the current read-only-to-source OKF v0.1 export, curated source set, privacy exclusions, metadata/link conversion, reserved bundle files, and conformance report.
- Preserve the separation from active `distributed-execution` accepted-result authority and `brain-okf-canonical-store` write-through migration targets.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `daemon-identity-and-host-pool`: add shipped daemon-selection/update and REST host-pool lifecycle contracts.
- `daemon-runtime-and-dispatch`: add shipped lease-heartbeat, cooperative-cancel, terminal-GC, and legacy recovery-helper contracts.
- `graph-execution-substrate`: add shipped child-Branch invocation, await/receipt-wait, existing-child attachment, and terminal-run-seeded new-run contracts.
- `knowledge-retrieval-and-memory`: add the shipped curated OKF v0.1 export contract.

## Impact

This is current-behavior reconciliation. It changes canonical requirements and may maintain focused assertions, but does not change product runtime, storage schemas, public MCP behavior, or deployment state. Primary evidence is in `tinyassets/daemon_registry.py`, `tinyassets/host_pool/`, `tinyassets/branch_tasks.py`, `fantasy_daemon/__main__.py`, `tinyassets/branches.py`, `tinyassets/graph_compiler.py`, `tinyassets/runs.py`, `tinyassets/api/runs.py`, `tinyassets/wiki/okf_export.py`, and their focused tests.
