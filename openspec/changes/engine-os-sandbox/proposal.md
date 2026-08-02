## Why

The current “sandbox” signals are not execution authority. A process-lifetime mutable diagnostic selects Codex’s dangerous bypass (`tinyassets/providers/base.py:891-896`, `tinyassets/providers/codex_provider.py:115-120`) and can positively attest authoring isolation that is never applied (`tinyassets/authoring/sandbox.py:436-464`); the proposed whole-universe mount would also include the credential paths it claimed to exclude (`tinyassets/credential_vault.py:16-17`, `tinyassets/providers/base.py:250,282`).

Untrusted source still executes with full builtins in-process in graph and NodeBid paths (`tinyassets/graph_compiler.py:1806-1810`, `tinyassets/executors/node_bid.py:175-177`) or in a same-UID child without an OS boundary (`tinyassets/node_sandbox.py:208,293-303`). Provider-side refusals are then caught and continued as fallback (`tinyassets/providers/router.py:473-493`), while the obsolete Bubblewrap design deliberately restores the full host network namespace. These six contradictions require a backend-neutral execution-admission contract, not a Bubblewrap wrapper.

## What Changes

- **BREAKING — A0, remove false authority:** `get_sandbox_status` remains a cached diagnostic only and no longer proves isolation or admits authoring. Authoring that requests OS isolation is refused unless a real admitted backend supplies it. The #1784/R2-1a provider owner must separately remove the Codex `--dangerously-bypass-approvals-and-sandbox` target before any execution-admission runtime can be enabled.
- **BREAKING — A1, require trusted admission:** each trusted graph, universe, or NodeBid call site derives an immutable logical `ExecutionRequirement` from closed workload/profile vocabulary and enforceable isolation guarantees. A missing, unknown, caller-authored, or unsatisfied requirement terminates execution with a shared `ExecutionAdmissionError`, distinct from authority, provider, exhaustion, runner-transport, and backend-result failures.
- Prompt-only work uses `workload=inference_only`, the `provider_cli` execution profile, an exact `tool_denied` policy digest, and an empty workspace projection. `provider_cli` is a profile, not a workload; `inference_only` is admission vocabulary only and never becomes a `JobCapability`.
- **BREAKING — A2, route source execution through the runner:** graph `source_code` nodes and NodeBid source run as existing `JobCapability.SOURCE_EXEC` work through `SandboxRunner`; approval and source-hash checks remain authoring admission and never attest containment. Closed projections contain only the approved source and declared JSON inputs, never a repository root, universe root, credential path, auth home, or vault path.
- Preserve the inner `runner/v1`, `JOB_REQUEST_SCHEMA_VERSION="runner-job/v1"`, `JOB_RESULT_SCHEMA_VERSION="runner-result/v1"`, existing closed `JobCapability` values/action mapping, runner result statuses, and graph run statuses. Runtime remains held until the distributed-execution owner supplies a sealed outer capsule keyed to `job_id` that binds the complete requirement and backend evidence, or explicitly versions its wire in its own change.
- Bind every logical requirement to opaque owner-defined policy, projection, egress, credential, and authority references plus digests. This lane defines no credential-delivery or egress taxonomy and exposes no raw credential to model-controlled work.
- Define the closed isolation guarantee sets and property-inclusion admission predicate here, but hand backend-to-profile/guarantee binding, runner backend implementation, backend evidence, outer capsule, and dispatch transport to the active `distributed-execution` change.
- Preserve accepted-market execution as the paid-market/distributed-execution B2/B13 pre-routing path. Ordinary provider-backed turns bind the logical requirement into #1784's immutable invocation; accepted-market turns bind it into the B2/B13 sealed execution capsule and never enter ordinary provider routing or `ProviderExecutor`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: replace in-process source execution with runner-backed `source_exec` while preserving advisory metadata behavior and making trusted admission independent of that metadata.
- `universe-personification-and-relay`: replace the Bubblewrap/whole-universe design with tool-denied inference, closed projections, and terminal admission semantics.

## Impact

The eventual implementation will affect trusted graph, universe, NodeBid, and authoring call sites plus the per-job runner seam. This change adds no MCP action, capability, top-level primitive, `JobCapability`, wire field, backend, build, rollout, or deployment.

This lane consumes, but does not redefine, #1784 `constrain-set-engine-provider-authority`: provider authority, the exact Bubblewrap-heading delta, immutable `ProviderInvocation`/`ProviderExecutor`, Codex mode selection, and router catch ordering remain owned by #1784/R2-1a. This change has no `provider-routing` delta; runtime implementation and cutover hold until that owner removes the dangerous bypass, binds ordinary provider invocations to the logical requirement, and preserves the shared admission error before broad fallback handlers. It also depends on `credential-vault` and `outbound-boundary-layer` for opaque owner-defined credential/egress requirements, and on `distributed-execution` for backend implementation, property-set binding, sealed outer capsules, and backend evidence. Provider-authority ready paths remain owned by `activate-requester-host-engines`, `harden-background-provider-execution-authority`, and `activate-connector-requester-authority`; the last binds accepted-market requirements into B2/B13 before ordinary routing.
