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

- Make execution admission backend-neutral, typed, immutable, closed, and derived only by trusted call sites, with owner-specific sealed transport bindings.
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

A trusted execution call site derives one immutable logical value before provider or runner selection:

```text
ExecutionRequirement {
  workload: inference_only | source_exec
  profile: provider_cli | runner_source_exec
  policy_ref + policy_digest
  isolation_requirement_ref + isolation_requirement_digest
  workspace_projection_ref + workspace_projection_digest
  egress_requirement_ref + egress_requirement_digest
  credential_requirement_ref + credential_requirement_digest
  authority_evidence_ref + authority_evidence_digest
}
```

The workload/profile vocabulary is closed. Every reference is opaque and
owner-defined; each digest must match the object resolved at launch.
Credential-vault and outbound-boundary own credential and egress vocabulary
and compatibility, while `authority_evidence_ref` consumes #1784 or B2/B13
evidence without redefining it. The resolved credential requirement must prove
that model-controlled work receives no raw API key, OAuth token, auth-home
projection, or other recoverable credential material.

**Irreducibility finding:** trusted derivation, deny-on-absence, exact
reference/digest binding, and guarantee-set comparison are enforcement
invariants with one useful shape. Each existing owner may seal the same logical
requirement into its own native carrier: ordinary providers use the #1784
invocation, accepted-market uses B2/B13, and runner jobs use a
distributed-execution outer capsule. OS-specific sandbox recipes, backend
implementations, carrier encodings, domain threat-model presets, and privacy
guidance have many valid shapes and remain remixable commons/backend designs.
`ExecutionRequirement` is not a new MCP handle, public action, universal wire
object, or user-facing execution authority.

The only valid workload/profile/policy pairs are:

| Workload | Profile | Exact policy intent | Projection intent | Credential/egress intent |
|---|---|---|---|---|
| `inference_only` | `provider_cli` | tool denied | empty | owner-defined brokered provider transport only |
| `source_exec` | `runner_source_exec` | runner `source_exec` policy | approved source plus declared JSON inputs | owner-defined no-credential and deny-all egress |

The closed base guarantee set for `os_isolated` is:

1. a kernel-enforced principal/process boundary distinct from the daemon;
2. default-deny filesystem projection matching the exact projection digest;
3. default-deny network enforcement matching the exact egress digest;
4. explicit CPU, memory, process, wall-clock, and output bounds;
5. platform secrets and undeclared devices absent;
6. ephemeral cleanup or equivalent bounded lifecycle; and
7. request-bound evidence covering the requirement and actual launch.

`vm_isolated` is admissible as stronger only when it proves every
`os_isolated` guarantee plus a distinct guest-kernel/hypervisor boundary and
default-deny host-device passthrough. Admission compares proved property-set
inclusion first; the tier label is only shorthand after those properties are
verified. A VM with broader mounts, egress, credentials, devices, or missing
evidence is not stronger. Missing or unknown properties deny, and a boolean
such as today's `isolation_enforced` cannot be promoted to either tier.

Admission has two fail-closed phases. Pre-launch admission succeeds only when
the logical requirement is present and trusted; its workload/profile
combination is valid; every resolved
policy/isolation/projection/egress/credential/authority digest matches; the
selected backend supports every required enforcement property; its current
capability/self-test evidence covers the required mechanisms; the exact
planned launch configuration is bound; and the backend protocol commits to
returning request-bound launch evidence. This phase proves capability and
configuration support only. It does not attest the future process or remote
execution, enforcement, cleanup, or result. Missing, stale, mismatched, or
unknown workload, profile, capability, binding, reference, digest,
requirement, planned configuration, or pre-launch evidence denies before
launch.

Post-launch validation then verifies returned evidence bound to the same
requirement/capsule, actual process or remote execution, policy/projection,
egress, resources, cleanup, and result. This phase alone proves the complete
guarantee set for that exact execution. Missing or invalid actual-launch
evidence raises `ExecutionAdmissionError(reason=backend_evidence_invalid)`;
the output cannot become a successful result or trigger fallback.

Alternative rejected: use `sandbox_workspace`, `requires_sandbox`, or a readiness boolean as the requirement. Each is caller-influenced or fungible and cannot express workload/profile compatibility or minimum isolation.

### 2. Tier policy and backend binding have separate owners

This change defines the closed guarantee sets and property-inclusion admission
predicate because provider, graph, and universe callers cannot state a
testable minimum without them. The active `distributed-execution` change
exclusively owns:

- concrete backends and transports;
- the mapping from a backend and its request-bound evidence to a supported profile and proved guarantee set;
- a sealed outer execution capsule keyed to `job_id` that binds the complete logical requirement to dispatch and returned backend evidence;
- runner readiness, policy hashes, images, remote execution, cleanup, and result validation.

The existing `SandboxJobRequest`/`SandboxJobResult` do not bind all required
digests end to end. An additive capability/property report may live in
in-process `RunnerCapabilities`, but no tier or admission field is added to
`SandboxJobRequest`, `EnforcementReceipt`, or `SandboxJobResult` in this lane.
The inner `JOB_REQUEST_SCHEMA_VERSION` remains exactly `runner-job/v1` and
`JOB_RESULT_SCHEMA_VERSION` remains exactly `runner-result/v1`. Source
execution cannot enable until the distributed-execution owner either supplies
the sealed outer capsule or explicitly versions the inner wire in its own
change.

Runner result statuses remain exactly `succeeded`, `failed`, and `cancelled`.
Graph run statuses remain exactly `queued`, `running`, `completed`, `failed`,
`cancelled`, `interrupted`, and `resumed`. Admission adds no success or run
state.

Alternative rejected: add a distributed-execution delta here. That active
change owns the backend contract; a second unarchived delta would create two
owners for backend-to-profile/guarantee binding and the outer capsule.

### 3. Prompt work is tool-denied provider inference, never a runner capability

Universe reply/learning turns and graph prompt nodes derive
`workload=inference_only`, `profile=provider_cli`, exact tool-denied policy,
and the full `os_isolated` guarantee set. They expose no Bash, filesystem,
WebFetch, scheduling, messaging, MCP, or future unenumerated tool. Trusted code
assembles the prompt from admitted inputs before launch; the digested execution
projection resolves to empty.

`provider_cli` is an execution profile, not a workload. Provider inference retains the provider executor’s native completion/streaming interface and is not forced into one-shot `SandboxJobRequest` JSON. `inference_only` is not a `JobCapability`, wire capability, action, or synonym for an existing runner capability. The existing `JobCapability` values remain exactly `source_exec`, `repo_read`, `repo_exec`, and `coding`, with their current immutable action mapping.

Alternative rejected: retain WebFetch as the sole allowed tool. Provider inference and outbound network fetch are different workloads; scoped egress is owned by `outbound-boundary-layer`, and an unenumerated CLI tool would reopen the original escape.

### 4. Source execution uses the existing `source_exec` seam

Graph `source_code` nodes and NodeBid source execution retain their trusted
approval and source-hash eligibility checks, then derive
`workload=source_exec`, `profile=runner_source_exec`, the exact runner source
policy, and the full `os_isolated` guarantee set. The
distributed-execution-owned outer capsule binds that logical requirement to
the inner `SandboxJobRequest` using existing `JobCapability.SOURCE_EXEC` and
the same `job_id`. Approval, hash matching, input-shape validation, and pattern
checks may refuse authoring or submission, but none attest isolation or
authorize in-process `exec`.

The closed `source_exec` projection contains only the approved source bytes and declared JSON-object inputs. It is created after identifiers and paths resolve in trusted code and contains no caller-selected host path. A whole universe root, repository root, current working directory, home, auth home, credential/vault path, or ambient data root is never projected.

Alternative rejected: repair `NodeSandbox` and keep direct graph/NodeBid execution. It is a same-UID crash/timeout boundary, not an OS containment backend, and would duplicate distributed execution.

### 5. Admission failure has one shared terminal taxonomy

This admission contract owns the shared semantic type
`ExecutionAdmissionError` and these closed reason codes:

- `requirement_missing`
- `requirement_untrusted`
- `requirement_malformed`
- `binding_mismatch`
- `profile_unsupported`
- `isolation_unsatisfied`
- `backend_unavailable`
- `backend_protocol_mismatch`
- `backend_evidence_invalid`

The type remains distinct from `ProviderAuthorityHeldError`, `ProviderError`,
`AllProvidersExhaustedError`, cooldown input, provider-attempt evidence,
runner transport exceptions, and backend execution results. Each consuming
owner maps its native pre-launch failures into this taxonomy: graph/NodeBid
normalize runner preflight and protocol refusals; universe/provider paths
preserve it; accepted-market admission maps B2/B13 capsule refusal. Backend
failure after a successful dispatch remains a backend result rather than an
admission error.

Pre-launch refusal and post-launch evidence rejection use the same terminal
type, but only the latter may use `backend_evidence_invalid` for evidence that
could not exist before launch.

The #1784/R2-1a provider lane owns updating router handlers that currently
catch `ProviderError` or `Exception` so they re-raise
`ExecutionAdmissionError` before cooldown, continue, retry, alternate
provider, local fallback, explicit fallback, mock output, degraded sentinel,
or fallback prose. Graph and universe boundaries preserve the error and map it
to terminal `failed` state. Until each owner implements its mapping and catch
ordering, runtime cutover remains held. The shape follows #1784's
non-fallbackable authority-hold precedent without duplicating authority
requirements or claiming either type is currently shipped.

Provider and backend failures after successful admission retain their
separately owned behavior.

Alternative rejected: subclass `ProviderError`. The current router catches
that family and continues, which would make the control structurally
non-terminal.

### 6. Each execution owner seals the same logical requirement natively

For ordinary provider-backed work, the #1784/R2-1a provider owner attaches the
trusted logical `ExecutionRequirement` by value or immutable reference to its
router-minted `ProviderInvocation`, and `ProviderExecutor.start()` consumes it
at the same launch-freeze boundary. For accepted-market work,
`activate-connector-requester-authority` and distributed execution bind the
same logical requirement into the B2/B13 sealed execution capsule before
pre-routing; that path never creates an ordinary `ProviderInvocation` or enters
`ProviderExecutor`. For runner-backed graph/NodeBid work, the
distributed-execution outer capsule binds the requirement to the frozen inner
job by `job_id`.

This change requires these owner-native bindings but does not define their
carrier encoding. Callers cannot supply or lower the logical requirement
through prompts, node definitions, `llm_policy`, `requires_sandbox`, request
payloads, or environment.

This change does not restate requester/market/host authority, `allowed_providers`, authority bindings, credential dereference, or `ProviderAuthorityHeldError`. Those remain wholly owned by #1784 and its credential/outbound successors. A route with valid provider authority but no valid execution requirement is nevertheless inadmissible; the two errors remain distinct.

Accepted-market work remains outside ordinary role/policy routing.
`activate-connector-requester-authority` dispatches it through the paid-market
agreement plus distributed-execution B2 signed-remote protocol and B13
anti-loss composition root. This lane neither sends it through ordinary
provider fallback nor mints market authority.

### 7. Cached sandbox status is diagnostic only; provider target repair is a blocking handoff

`get_sandbox_status` may preserve its current cached, mutable compatibility
shape for observation, but no provider mode, runner readiness, graph validity,
authoring attestation, requirement derivation, profile/guarantee binding, or
execution admission may consume it as authority.

The active #1784 change already modifies the exact canonical Bubblewrap
requirement heading and retains the dangerous bypass. Therefore this change
must not create a competing `provider-routing` delta. The #1784/R2-1a owner
must remove `--dangerously-bypass-approvals-and-sandbox`, make failed admission
terminate before subprocess creation, and make router catch ordering preserve
the shared `ExecutionAdmissionError`. Runtime implementation and cutover hold
until that provider target exists; this spec-only target may be reviewed and
merged without reinterpreting a successful Bubblewrap probe as confinement.

### 8. A0 stops authoring false attestation before backend work

`authoring.sandbox.require_isolation` must not report `os_isolated` from installed-Bubblewrap diagnostics. Until the distributed-execution owner supplies a backend binding whose admitted tier satisfies the draft’s requirement, `requires_os_isolation=True` is refused. Existing authoring source checks remain eligibility controls and never produce an isolation claim.

This A0 correction is a dependency/handoff to the active node-authoring owner, not a fourth delta spec in this lane.

## Risks / Trade-offs

- **[Risk] No backend may initially satisfy `os_isolated`.** → Fail closed and expose a typed admission refusal; do not restore in-process or dangerous-mode fallback.
- **[Risk] Tier labels conceal weaker property sets.** → Admit on proved guarantee-set inclusion, treat labels as shorthand only, and require distributed execution to bind each backend explicitly; absent/unknown properties deny.
- **[Risk] `ExecutionRequirement` is confused with provider authority.** → Keep separate types and errors; carry only the #1784-owned evidence reference and consume its immutable carrier without restating authority clauses.
- **[Risk] A closed projection omits a legitimate input.** → Add that input explicitly at the trusted call site; never broaden to a whole root.
- **[Risk] Existing status consumers assume availability means enforcement.** → Retain diagnostic visibility but forbid authority consumption and add false-attestation regression coverage in the implementation lane.
- **[Risk] Two active changes touch runner concepts.** → This lane owns caller requirement/admission semantics only; distributed-execution owns backend implementation and bindings.
- **[Risk] Frozen inner runner wire cannot bind complete admission evidence.** → Keep source execution disabled until distributed execution supplies a sealed outer capsule or versions its own wire.
- **[Risk] Credential/egress compatibility is underspecified.** → Consume only opaque owner-defined references and digests; no profile is enabled until both owners publish an exact compatible requirement.

## Migration Plan

This artifact is a spec-only supersession of the obsolete Bubblewrap design.
Implementation must proceed in separately claimed runtime/test lanes after
#1784/R2-1a removes the dangerous bypass and preserves the shared terminal
error; ordinary provider, accepted-market, and runner owners seal the logical
requirement into their native carriers; credential/egress owners publish
compatible references; and distributed-execution backend binding plus outer
capsule evidence is available. A0 false-authority removal precedes A1
admission enforcement; A2 graph/NodeBid cutover occurs only when
`source_exec` is admitted. No compatibility downgrade is permitted between
waves.

Canonical spec sync and archive happen only with the implementation landing. Deployment, canary, rendered-chatbot proof, and post-fix clean-use evidence are later shipping gates, not claims of this change.

## Remaining Owner Questions

The logical admission invariants are closed here. The outer-capsule handoff is
also resolved: `distributed-execution` owns the purpose-separated M1-signed
`ExecutionAdmissionCapsuleV1`, the M1-signed `BackendBindingV1`, and the
reviewed-verifier `BackendLaunchEvidenceV1` contract, bound outside the frozen
inner `runner/v1` wire by `job_id`. These owner-native integrations remain
open and blocking:

1. Which credential-vault and outbound-boundary reference/digest pairs are
   compatible with each execution profile?
2. Which concrete backends prove each required guarantee set?

Those owners must answer in their own OpenSpec changes before runtime
implementation or cutover; this lane must not choose for them.
