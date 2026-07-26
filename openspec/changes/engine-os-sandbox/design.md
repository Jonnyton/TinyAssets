## Context

The prior version assumed Bubblewrap availability was authority, bound the complete universe directory read-write, restored the host network namespace, and treated provider-side refusal as terminal. The current code disproves each assumption:

1. `get_sandbox_status()` returns one mutable process-lifetime dictionary (`tinyassets/providers/base.py:891-896`); Codex mode selection and authoring isolation reporting consume it as authority (`tinyassets/providers/codex_provider.py:115-120`, `tinyassets/authoring/sandbox.py:436-464`).
2. The universe root contains `.credential-vault.json`, `.credentials`, and `.runtime/provider-child` (`tinyassets/credential_vault.py:16-17`, `tinyassets/providers/base.py:250,282`). A whole-root projection cannot exclude those descendants.
3. Graph and NodeBid source execute through `exec` with full builtins (`tinyassets/graph_compiler.py:1806-1810`, `tinyassets/executors/node_bid.py:175-177`).
4. `NodeSandbox` launches a same-UID Python child with the host mount and network namespaces and no resource limits (`tinyassets/node_sandbox.py:208,293-303`).
5. Router catches both `ProviderError` and generic exceptions and continues (`tinyassets/providers/router.py:473-493`), so a provider refusal is a fallback hint rather than a route-level denial.
6. The obsolete Bubblewrap policy paired `--unshare-all` with `--share-net`, restoring unrestricted host-network reach.

The trusted graph provider call site also currently omits `UniverseContext`. #1784 owns credential/provider authority and will supply the immutable `ProviderInvocation`/`ProviderExecutor` seam; this change owns only the residual obligation to derive and attach an execution requirement before that seam is invoked.

## Goals / Non-Goals

**Goals:**

- Make execution admission backend-neutral, typed, immutable, closed, and derived only by trusted call sites.
- Deny all prompt-node tools and route all graph/NodeBid source through the existing `source_exec` runner capability.
- Make missing or unsatisfied execution admission terminal and non-fallbackable.
- Keep workspace projections minimal and closed; never expose a complete universe or repository root.
- Remove diagnostic-as-authority in engine/authoring consumers and require the #1784/R2-1a provider owner to remove the Codex dangerous bypass before any execution-admission runtime can be enabled.
- Preserve #1784 provider authority, B2/B13 accepted-market routing, runner wire versions, and the current `JobCapability` vocabulary.

**Non-Goals:**

- Choosing or implementing Bubblewrap, containers, VMs, remote hosts, images, policy hashes, attestations, or any other backend.
- Defining provider credentials, requester authority, provider allowlists, or ambient credential isolation.
- Defining scoped network egress.
- Adding an MCP action, platform capability, `JobCapability`, runner wire field, or public status authority.
- Implementing, building, syncing canonical specs, archiving, deploying, or running live acceptance in this spec-only lane.

## Decisions

### 1. `ExecutionRequirement` is a trusted, immutable admission input

A trusted execution call site derives one immutable value before provider or runner selection:

```text
ExecutionRequirement {
  workload: inference_only | source_exec
  profile: provider_cli | runner_source_exec
  policy_digest: immutable exact-policy digest
  minimum_isolation: os_isolated | vm_isolated
  workspace_projection_ref + workspace_projection_digest
  egress_requirement_ref + egress_requirement_digest
  credential_delivery: none | opaque_brokered
  authority_evidence_ref
}
```

These vocabularies are closed. References are opaque, immutable admission inputs; each required digest must match the object resolved at launch. `authority_evidence_ref` consumes #1784 evidence without redefining it. `opaque_brokered` means the model-controlled child never receives a raw API key, OAuth token, auth-home projection, or other recoverable credential material.

**Irreducibility finding:** trusted derivation, deny-on-absence, exact
policy/projection/egress binding, and minimum-tier comparison are enforcement
boundaries with one useful shape. They therefore belong in this internal
admission carrier. OS-specific sandbox recipes, backend implementations,
domain threat-model presets, and privacy guidance have many valid shapes and
remain remixable commons/backend designs. `ExecutionRequirement` is not a new
MCP handle, public action, or user-facing execution authority.

The only valid workload/profile/policy pairs are:

| Workload | Profile | Exact policy | Minimum tier | Projection |
|---|---|---|---|---|
| `inference_only` | `provider_cli` | `tool_denied` | `os_isolated` | empty |
| `source_exec` | `runner_source_exec` | runner `source_exec` policy | `os_isolated` | approved source plus declared JSON inputs |

The closed tier order is `os_isolated < vm_isolated`. Admission succeeds only when the requirement is present and trusted; its workload/profile/policy combination is valid; every resolved policy, projection, and egress digest matches; credential delivery is closed and compatible; #1784 authority evidence is current; the selected backend explicitly supports that profile; and the backend’s bound tier is greater than or equal to the required tier. Missing, stale, mismatched, or unknown workload, profile, policy, tier, binding, projection, egress, credential-delivery class, authority reference, or requirement denies. A boolean such as today’s `isolation_enforced` cannot be promoted to either tier by default.

Alternative rejected: use `sandbox_workspace`, `requires_sandbox`, or a readiness boolean as the requirement. Each is caller-influenced or fungible and cannot express workload/profile compatibility or minimum isolation.

### 2. Tier policy and backend binding have separate owners

This change defines the closed tier ordering and admission predicate because provider, graph, and universe callers cannot state a testable minimum without them. The active `distributed-execution` change exclusively owns:

- concrete backends and transports;
- the mapping from a backend and its evidence to a supported profile and isolation tier;
- runner readiness, policy hashes, images, remote execution, cleanup, and result validation.

An additive `isolation_tier` may live on the in-process `RunnerCapabilities` report when the distributed-execution owner implements the binding. It must not be added to `SandboxJobRequest`, `EnforcementReceipt`, or `SandboxJobResult`. `JOB_REQUEST_SCHEMA_VERSION` remains exactly `runner-job/v1`; `JOB_RESULT_SCHEMA_VERSION` remains exactly `runner-result/v1`.

Alternative rejected: add a distributed-execution delta here. That active change owns the backend contract; a second unarchived delta would create two owners for backend-to-tier binding.

### 3. Prompt work is tool-denied provider inference, never a runner capability

Universe reply/learning turns and graph prompt nodes derive `workload=inference_only`, `profile=provider_cli`, exact `tool_policy=tool_denied`, and `minimum_isolation=os_isolated`. They expose no Bash, filesystem, WebFetch, scheduling, messaging, MCP, or future unenumerated tool. Trusted code assembles the prompt from admitted inputs before launch; the digested execution projection resolves to empty.

`provider_cli` is an execution profile, not a workload. Provider inference retains the provider executor’s native completion/streaming interface and is not forced into one-shot `SandboxJobRequest` JSON. `inference_only` is not a `JobCapability`, wire capability, action, or synonym for an existing runner capability. The existing `JobCapability` values remain exactly `source_exec`, `repo_read`, `repo_exec`, and `coding`, with their current immutable action mapping.

Alternative rejected: retain WebFetch as the sole allowed tool. Provider inference and outbound network fetch are different workloads; scoped egress is owned by `outbound-boundary-layer`, and an unenumerated CLI tool would reopen the original escape.

### 4. Source execution uses the existing `source_exec` seam

Graph `source_code` nodes and NodeBid source execution retain their trusted approval and source-hash eligibility checks, then derive `workload=source_exec`, `profile=runner_source_exec`, the exact runner source policy digest, and create a `SandboxJobRequest` using existing `JobCapability.SOURCE_EXEC`. Approval, hash matching, input-shape validation, and pattern checks may refuse authoring or submission, but none attest isolation or authorize in-process `exec`.

The closed `source_exec` projection contains only the approved source bytes and declared JSON-object inputs. It is created after identifiers and paths resolve in trusted code and contains no caller-selected host path. A whole universe root, repository root, current working directory, home, auth home, credential/vault path, or ambient data root is never projected.

Alternative rejected: repair `NodeSandbox` and keep direct graph/NodeBid execution. It is a same-UID crash/timeout boundary, not an OS containment backend, and would duplicate distributed execution.

### 5. Admission failure consumes a provider-owned terminal exception contract

The provider owner must supply one closed route-level exception shape for a missing, malformed, untrusted, or unsatisfied execution requirement. It must remain distinct from `ProviderError`, provider exhaustion, cooldown input, provider attempt, or a backend execution result.

The #1784/R2-1a provider lane owns updating router handlers that currently catch `ProviderError` or `Exception` so they re-raise the execution-admission exception before cooldown, continue, retry, alternate provider, local fallback, explicit fallback, mock output, degraded sentinel, or fallback prose. This change consumes that contract: graph and universe boundaries preserve the exception unchanged and map it to terminal `failed` state. Until the provider owner lands the exception and catch ordering, this lane remains held. The shape follows #1784’s non-fallbackable `ProviderAuthorityHeldError` precedent without duplicating authority requirements or assuming that spec-only class already exists in runtime.

Provider failures after successful admission remain provider failures and retain their separately owned retry/fallback policy.

Alternative rejected: subclass `ProviderError`. The current router catches that family and continues, which would make the control structurally non-terminal.

### 6. Requirements attach to, but do not redefine, #1784 invocation authority

The #1784/R2-1a provider owner must attach the trusted `ExecutionRequirement` by value or immutable reference to its router-minted immutable `ProviderInvocation`, and `ProviderExecutor.start()` must consume it at the same launch-freeze boundary. This change requires and consumes that attachment but does not modify provider routing itself. Callers cannot supply or lower it through prompts, node definitions, `llm_policy`, `requires_sandbox`, request payloads, or environment.

This change does not restate requester/market/host authority, `allowed_providers`, authority bindings, credential dereference, or `ProviderAuthorityHeldError`. Those remain wholly owned by #1784 and its credential/outbound successors. A route with valid provider authority but no valid execution requirement is nevertheless inadmissible; the two errors remain distinct.

Accepted-market work remains outside ordinary role/policy routing. `activate-connector-requester-authority` dispatches it through the paid-market agreement plus distributed-execution B2 signed-remote protocol and B13 anti-loss composition root. This lane neither sends it through ordinary provider fallback nor mints market authority.

### 7. Cached sandbox status is diagnostic only; provider target repair is a blocking handoff

`get_sandbox_status` may preserve its current cached, mutable compatibility shape for observation, but no provider mode, runner readiness, graph validity, authoring attestation, requirement derivation, tier binding, or execution admission may consume it as authority.

The active #1784 change already modifies the exact canonical Bubblewrap requirement heading and retains the dangerous bypass. Therefore this change must not create a competing `provider-routing` delta. The #1784/R2-1a owner must remove `--dangerously-bypass-approvals-and-sandbox`, make failed admission terminate before subprocess creation, and make router catch ordering preserve that exception. Runtime implementation and cutover hold until that provider target exists; this spec-only target may be reviewed and merged without reinterpreting a successful Bubblewrap probe as confinement.

### 8. A0 stops authoring false attestation before backend work

`authoring.sandbox.require_isolation` must not report `os_isolated` from installed-Bubblewrap diagnostics. Until the distributed-execution owner supplies a backend binding whose admitted tier satisfies the draft’s requirement, `requires_os_isolation=True` is refused. Existing authoring source checks remain eligibility controls and never produce an isolation claim.

This A0 correction is a dependency/handoff to the active node-authoring owner, not a fourth delta spec in this lane.

## Risks / Trade-offs

- **[Risk] No backend may initially satisfy `os_isolated`.** → Fail closed and expose a typed admission refusal; do not restore in-process or dangerous-mode fallback.
- **[Risk] Tier names drift from backend evidence.** → Keep the vocabulary closed here and require distributed-execution to own each backend binding explicitly; absent/unknown binding denies.
- **[Risk] `ExecutionRequirement` is confused with provider authority.** → Keep separate types and errors; carry only the #1784-owned evidence reference and consume its immutable carrier without restating authority clauses.
- **[Risk] A closed projection omits a legitimate input.** → Add that input explicitly at the trusted call site; never broaden to a whole root.
- **[Risk] Existing status consumers assume availability means enforcement.** → Retain diagnostic visibility but forbid authority consumption and add false-attestation regression coverage in the implementation lane.
- **[Risk] Two active changes touch runner concepts.** → This lane owns caller requirement/admission semantics only; distributed-execution owns backend implementation and bindings.

## Migration Plan

This artifact is a spec-only supersession of the obsolete Bubblewrap design. Implementation must proceed in separately claimed runtime/test lanes after #1784/R2-1a removes the dangerous bypass, supplies the terminal exception/catch ordering, and attaches the requirement to the carrier/executor seam, and after distributed-execution backend binding is available. A0 false-authority removal precedes A1 admission enforcement; A2 graph/NodeBid cutover occurs only when `source_exec` is admitted. No compatibility downgrade is permitted between waves.

Canonical spec sync and archive happen only with the implementation landing. Deployment, canary, rendered-chatbot proof, and post-fix clean-use evidence are later shipping gates, not claims of this change.

## Open Questions

None for this contract. Concrete backend-to-tier bindings, rollout sequencing, and backend evidence are intentionally deferred to their named owners.
