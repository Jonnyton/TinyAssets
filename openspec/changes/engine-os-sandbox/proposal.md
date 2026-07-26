## Why

The current “sandbox” signals are not execution authority. A process-lifetime mutable diagnostic selects Codex’s dangerous bypass (`tinyassets/providers/base.py:891-896`, `tinyassets/providers/codex_provider.py:115-120`) and can positively attest authoring isolation that is never applied (`tinyassets/authoring/sandbox.py:436-464`); the proposed whole-universe mount would also include the credential paths it claimed to exclude (`tinyassets/credential_vault.py:16-17`, `tinyassets/providers/base.py:250,282`).

Untrusted source still executes with full builtins in-process in graph and NodeBid paths (`tinyassets/graph_compiler.py:1806-1810`, `tinyassets/executors/node_bid.py:175-177`) or in a same-UID child without an OS boundary (`tinyassets/node_sandbox.py:208,293-303`). Provider-side refusals are then caught and continued as fallback (`tinyassets/providers/router.py:473-493`), while the obsolete Bubblewrap design deliberately restores the full host network namespace. These six contradictions require a backend-neutral execution-admission contract, not a Bubblewrap wrapper.

## What Changes

- **BREAKING — A0, remove false authority:** `get_sandbox_status` remains a cached diagnostic only and no longer proves isolation or admits authoring. Authoring that requests OS isolation is refused unless a real admitted backend supplies it. The #1784/R2-1a provider owner must separately remove the Codex `--dangerously-bypass-approvals-and-sandbox` target before any execution-admission runtime can be enabled.
- **BREAKING — A1, require trusted admission:** each trusted graph, universe, or NodeBid call site derives an immutable `ExecutionRequirement` from closed workload, profile, and minimum-isolation vocabularies. A missing, unknown, caller-authored, or unsatisfied requirement terminates execution with the non-fallbackable admission exception supplied by the provider owner, distinct from provider failure.
- Prompt-only work uses `workload=inference_only`, the `provider_cli` execution profile, an exact `tool_denied` policy digest, and an empty workspace projection. `provider_cli` is a profile, not a workload; `inference_only` is admission vocabulary only and never becomes a `JobCapability`.
- **BREAKING — A2, route source execution through the runner:** graph `source_code` nodes and NodeBid source run as existing `JobCapability.SOURCE_EXEC` work through `SandboxRunner`; approval and source-hash checks remain authoring admission and never attest containment. Closed projections contain only the approved source and declared JSON inputs, never a repository root, universe root, credential path, auth home, or vault path.
- Preserve `JOB_REQUEST_SCHEMA_VERSION="runner-job/v1"`, `JOB_RESULT_SCHEMA_VERSION="runner-result/v1"`, and the existing closed `JobCapability` values and action mapping.
- Bind every requirement to digested policy, projection, and egress references, a closed `none|opaque_brokered` credential-delivery class, and the #1784 authority-evidence reference without exposing raw credentials to model-controlled work.
- Define the closed isolation-tier ordering and admission predicate here, but hand backend-to-tier/profile binding, runner backend implementation, backend evidence, and dispatch transport to the active `distributed-execution` change.
- Preserve accepted-market execution as the paid-market/distributed-execution B2/B13 pre-routing path. It does not enter ordinary provider fallback.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: replace in-process source execution and advisory-only sandbox demand with typed admission and runner-backed `source_exec`.
- `universe-personification-and-relay`: replace the Bubblewrap/whole-universe design with tool-denied inference, closed projections, and terminal admission semantics.

## Impact

The eventual implementation will affect trusted graph, universe, NodeBid, and authoring call sites plus the per-job runner seam. This change adds no MCP action, capability, top-level primitive, `JobCapability`, wire field, backend, build, rollout, or deployment.

This lane consumes, but does not redefine, #1784 `constrain-set-engine-provider-authority`: provider authority, the exact Bubblewrap-heading delta, immutable `ProviderInvocation`/`ProviderExecutor`, Codex mode selection, and router exception handling remain owned by #1784/R2-1a. This change has no `provider-routing` delta; runtime implementation and cutover hold until that owner attaches the requirement, removes the dangerous bypass, and supplies the non-fallbackable admission exception contract. It also depends on `credential-vault` for ambient-secret isolation, `outbound-boundary-layer` for scoped egress, and `distributed-execution` for backend implementation and backend-to-tier/profile binding. Provider-authority ready paths remain owned by `activate-requester-host-engines`, `harden-background-provider-execution-authority`, and `activate-connector-requester-authority`; the last preserves accepted-market B2/B13 dispatch before ordinary routing.
