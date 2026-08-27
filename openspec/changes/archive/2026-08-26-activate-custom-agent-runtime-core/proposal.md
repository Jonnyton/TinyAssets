## Why

The merged custom-agent runtime contract separates delivery into bounded successors. The first necessary slice is the inert runtime core: a private `AgentBinding` must compile into an immutable governed manifest and bind to the platform's sole activation epoch before app transport, workflow authoring, or connector controls can safely exist.

## What Changes

- Extend and consume the canonical automation-activation owner with a typed agent-manifest subject; create no agent-only activation ledger or transition service.
- Compile every executable component in the pinned definition/binding snapshot through installed governed component adapters plus a governed plan adapter whose declared plan class owns topology and entry semantics; block the whole activation when requested semantics, resources, artifact types, plan semantics, or confinement cannot resolve.
- Derive a narrow agent runtime principal and live-check its explicit grants instead of running with the binding owner's bearer authority.
- Admit spend-causing work only by atomically consuming the live authenticated request's inert provider-work binding draft into one linked binding, replay-safe server-authored invocation command, and invocation root; then invoke only the requester's explicitly bound provider/compute authority through the canonical provider-work and cloud-continuation owners using the same typed execution subject, with frozen budgets, receipts, epoch/lease fencing, restart recovery, and useful-progress health; do not coerce an agent invocation into the Branch-only background-attempt ledger.
- Keep the slice dark and private: no app ingress/replies, conversation custody, workflow creation/iteration, public MCP operations, tenant-code execution, or live rollout is included.
- Defer runtime file claims until the active cloud-drain/provider owner grants an exact handoff; this proposal initially owns only its OpenSpec directory and `STATUS.md`.

## Capabilities

### New Capabilities

- `custom-agent-runtime-core`: Immutable agent activation manifests, exhaustive governed component compilation, delegated runtime authority, requester-owned provider execution, and single-active durable recovery without public/app/workflow surfaces.

### Modified Capabilities

- `user-owned-cloud-automation`: Generalize the canonical single-active activation and cloud-continuation contracts to one typed immutable execution subject while preserving Branch behavior and deriving the unique agent activation key from `(universe_id, agent_binding_id)`.
- `background-provider-execution-authority`: Admit a server-classified agent-invocation lineage into the existing bounded universe-work receipt/claim authority without weakening Branch lineage, call-site closure, budgets, or launch fencing.

## Impact

After owner handoff, the implementation will touch the canonical typed execution-subject contract across activation/provider-work/cloud continuation, a new custom-agent manifest/compiler/invocation adapter, delegated principal and invocation-command admission, private projections, packaged mirrors for changed runtime files, and focused security/concurrency/load tests. It leaves the Branch-only background-attempt ledger unchanged and adds no database or queue that competes with the canonical activation, provider-work, or continuation ledgers.
