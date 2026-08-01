## ADDED Requirements

### Requirement: An immutable manifest pins the complete agent runtime subject
The system SHALL compile one exact private binding revision and public definition fingerprint into an immutable content-addressed agent runtime manifest that pins the universe, binding, definition, every component runtime mode, resolved component and plan adapter versions/digests, the plan adapter's canonical typed execution plan, requested governed-reference IDs, budgets, and compiler-contract version while excluding credentials, conversations, provider outputs, effect payloads, and mutable execution state.

#### Scenario: Binding changes after compilation
- **WHEN** a binding revision, selected definition, component configuration, adapter digest, governed reference, or budget input changes after a manifest was compiled
- **THEN** the existing manifest remains immutable and a later compile produces a distinct manifest/digest
- **AND** no running activation changes until an explicit canonical rebind selects the successor manifest

#### Scenario: Compile fails atomically
- **WHEN** any pinned input changes concurrently or complete validation finds an invalid, secret-bearing, oversized, unresolved, or incompatible value
- **THEN** compilation fails without writing a partial manifest or changing activation state

### Requirement: Canonical runtime owners share one typed execution subject
The system MUST activate, assign provider work for, and continue an agent manifest only through one identical typed immutable execution-subject kind/reference/digest carried by the canonical automation-activation, provider-work, and cloud-continuation owners, MUST include that exact tuple in every transition and claim validation, and MUST create no agent-only activation, provider-work, continuation, epoch, lease, transition, or fallback authority.

#### Scenario: Branch and agent subjects share one owner contract
- **WHEN** canonical activation, provider-work, and continuation records carry ordinary Branch-version or agent-manifest work
- **THEN** each related record has exactly one matching typed immutable subject tuple and preserves its existing transition, budget, revocation, epoch/executor/lease, and concurrency guards
- **AND** an agent subject cannot claim through Branch fields or a second local identity

#### Scenario: One binding cannot acquire two activation rows
- **WHEN** concurrent callers attempt to activate different manifests or supply alternate local automation identities for the same `(universe_id, agent_binding_id)`
- **THEN** the server ignores caller automation identities and derives one reserved automation key from the typed binding owner
- **AND** the canonical activation primary key and compare-and-swap transition admit at most one current epoch, subject, executor, and lease

#### Scenario: Stale agent executor presents cached state
- **WHEN** an executor presents an old subject digest, epoch, executor class, or lease after stop, rebind, cutover, or recovery advanced the canonical record
- **THEN** claim validation fails before invocation, provider reservation, spend, or output

#### Scenario: Agent invocation is not a background Branch attempt
- **WHEN** an agent-manifest invocation requests provider work or continuation without executing a Branch
- **THEN** it uses a server-classified agent-invocation identity and the shared execution subject
- **AND** it neither fabricates Branch definition/version fields nor creates, reads, or mutates a `BackgroundBranchAttempt`

### Requirement: Runtime metadata selects explicit component and plan semantics
The system SHALL require the private binding's `runtime` envelope to select one governed `plan_adapter_ref`, SHALL read per-component mode and optional governed component adapter reference from `runtime.components` keyed by public component key while keeping private values in `component_configuration`, SHALL default an omitted mode to `execute`, and SHALL allow `descriptive_only` only as non-executable typed configuration that grants no tool, provider, resource, capability, graph, or effect behavior.

#### Scenario: Plan semantics are absent or guessed
- **WHEN** a binding omits its governed plan adapter or relies on component names, object order, or a platform default to imply topology or entry semantics
- **THEN** compilation fails with an explicit plan diagnostic and does not guess a platform archetype

#### Scenario: Unknown component is explicitly descriptive
- **WHEN** an unfamiliar component is marked `descriptive_only`
- **THEN** its canonical content can be pinned in the manifest for a descriptor-declared typed input
- **AND** it is never invoked or interpreted as prompt text or code by default

### Requirement: Governed adapters compile one exhaustive adapter-declared plan
The system MUST resolve every `execute` component through an installed governed component descriptor that freezes its kind/reference/version/digest, configuration schema, typed inputs/outputs, required capability/resource/provider classes, confinement class, and budget dimensions; MUST resolve the selected governed plan descriptor that declares its plan class, topology and entry schema, compatible component contracts, complete-component coverage rule, confinement class, and canonical compiler; and MUST reject unresolved descriptors, incompatible artifacts, omitted executable components, invalid descriptor-declared topology, or unavailable confinement as a complete activation failure.

#### Scenario: Executable component has no adapter
- **WHEN** an unfamiliar or unavailable component defaults to or explicitly requests `execute`
- **THEN** exhaustive diagnostics report that exact component as unsupported and no manifest or activation is created
- **AND** the public definition remains unchanged and portable for export/remix

#### Scenario: Plan shape is adapter-declared
- **WHEN** a governed plan adapter declares single-entry DAG, recurrent, multi-entry, event-driven, state-machine, or another topology and entry contract
- **THEN** the compiler validates that declared contract and includes every `execute` component under its coverage rule
- **AND** the platform does not impose universal single-entry, acyclic, connected, or graph-shaped semantics

#### Scenario: Requested plan class is unavailable
- **WHEN** an imported or remixed agent requests plan semantics for which no installed governed plan adapter exists
- **THEN** activation fails with exhaustive diagnostics without altering or rejecting the portable definition, binding, import, export, or remix artifact

#### Scenario: Tenant-code adapter lacks confinement
- **WHEN** a descriptor requires source code, repository commands, shell access, or another tenant-code confinement class not supplied by the approved Engine OS owner
- **THEN** compilation reports `sandbox_unavailable` and performs no code, provider, graph, or effect operation

### Requirement: Compile retries are deterministic and idempotent
The system SHALL canonicalize compiler inputs, write a manifest atomically, and return the same manifest for a repeated compile by the same authorized owner with the same non-empty idempotency key and identical input digest while rejecting reuse of that key with changed inputs.

#### Scenario: Compile response is lost
- **WHEN** the owner repeats an identical completed compile with the same idempotency key
- **THEN** the original manifest ID/digest and diagnostics are returned and no duplicate manifest is written

#### Scenario: Idempotency key is reused for changed inputs
- **WHEN** the same owner reuses a compile idempotency key after any canonical input differs
- **THEN** compilation returns a conflict and neither the old manifest nor activation is mutated

### Requirement: Runtime authority is delegated and live-checked
The system MUST derive each agent runtime principal server-side from the authenticated owner, universe, binding, manifest, activation subject/epoch/executor/lease, and invocation, MUST treat manifest capability/resource/provider references only as requests, and MUST revalidate current explicit grants before every privileged transition without accepting caller-authored actors or inheriting the owner's bearer, maintainer, host, market, or ambient authority.

#### Scenario: Grant is revoked after activation
- **WHEN** a requested capability, resource, or provider grant is revoked, paused, expired, or changed after manifest compilation or activation
- **THEN** the next invocation or resumed transition records a typed authority blocker before provider reservation or spend
- **AND** cached manifest data does not preserve the old authority

#### Scenario: Component claims a broader actor
- **WHEN** component or binding JSON names an owner, administrator, maintainer, or alternate universe as its actor
- **THEN** the runtime principal remains server-derived and the claimed identity grants no authority

### Requirement: Spend-causing invocation has one replay-safe admission owner
The system MUST atomically create and link one non-bearer `ProviderWorkBinding`, one `AgentInvocationCommand`, and its append-only `AgentInvocation` lifecycle root through one server-owned admission service only while processing current authenticated owner intent and consuming the exact inert single-message provider-work binding draft from that live request boundary, or a future explicitly admitted successor root. The command MUST bind the authorizing principal and grant generation, universe, binding revision, manifest execution subject, activation epoch/executor/lease, typed-input digest, stable invocation identity, budget envelope, provider-work binding identity/generation/digest, and idempotency key, and MUST never accept caller-authored command or binding authority fields.

#### Scenario: Exact invocation request is replayed
- **WHEN** the same authorized owner intent repeats with the same idempotency key and identical canonical command inputs
- **THEN** admission returns the original provider-work binding, command, and invocation identities without reserving or spending again

#### Scenario: Invocation key is reused with changed input
- **WHEN** the same idempotency key is presented with a different typed-input digest, subject, activation fence, principal, or budget
- **THEN** admission conflicts before a provider-work binding, invocation, provider receipt, continuation, or spend is created

#### Scenario: Lower-level path attempts to bypass admission
- **WHEN** a private helper, generic dispatcher, queue claimant, persisted actor label, caller-built command, or caller-built invocation record requests provider-capable work without the exact atomically linked provider-work binding and server-issued command
- **THEN** execution fails closed before provider authority, credentials, continuation, or spend

#### Scenario: Authenticated recording boundary is missed
- **WHEN** invocation admission runs after the live request boundary ended without atomically consuming its exact inert provider-work binding draft
- **THEN** it creates no command, invocation, or provider-work binding and cannot reconstruct authority from request data, stored actors, or caller fields

#### Scenario: Recovery occurs after request authority ends
- **WHEN** a worker restarts after durable admission and the live owner bearer is no longer present
- **THEN** it may resume only the same provider-work binding, command, and invocation after revalidating current activation, grants, subject, lease, and budgets
- **AND** durable provenance never reconstructs or substitutes for the owner's bearer

### Requirement: Provider execution uses only requester-owned background authority
The system SHALL execute a bounded private typed invocation only after its exact server-issued invocation command, append-only agent-invocation record, and the canonical provider-work owner resolve the requester's explicitly bound provider/compute authority and budgets for the exact runtime principal, activation, and shared execution subject, SHALL persist non-secret authority evidence and provider attempt identity, and SHALL treat provider output as non-authoritative typed data with no graph or external-effect capability.

#### Scenario: Bound provider authority is unavailable
- **WHEN** the selected requester-owned provider route is missing, paused, revoked, expired, over budget, or unusable
- **THEN** the invocation terminates or blocks without maintainer, host, market, ambient, or unselected-provider substitution

#### Scenario: Provider returns a mutation instruction
- **WHEN** provider output requests a graph write, workflow run, external effect, app reply, credential access, or public control operation
- **THEN** the core records only bounded typed output or a validation failure and performs none of those operations

### Requirement: Recovery is single-active and health measures useful progress
The system MUST persist separate canonical activation, agent-invocation, provider-work, and cloud-continuation identities, MUST resume or reconcile the same identities after worker loss while revalidating the identical shared subject plus all epoch/lease/authority/budget pins, MUST leave Branch-only background attempts outside agent invocation, and MUST report private useful-progress health without minting replacement identities or treating heartbeat churn as success.

#### Scenario: Worker restarts after provider reservation
- **WHEN** a cloud worker stops after durable admission or provider reservation and another worker resumes
- **THEN** recovery reconciles the same activation, agent-invocation, provider-work, and continuation identities before any retry
- **AND** a stale or alternate executor cannot spend or finalize output under an invalid epoch or lease

#### Scenario: Runtime retries without progress
- **WHEN** heartbeats or retries continue without a manifest, admitted invocation, provider result, terminal typed output, or explicit durable blocker transition within the configured bound
- **THEN** private health reports no useful progress and raises the configured alarm

### Requirement: The runtime core remains dark and non-mutating outside its authority
The system MUST expose no app ingress/reply, conversation custody, Branch/run/evaluation/workflow mutation, external effect, public MCP target/operation, or tenant-code path from this core and MUST keep bindings user-visible as `configured` rather than claiming a usable, connected, or publicly controllable agent.

#### Scenario: Core deploys before successors
- **WHEN** the runtime core and its private internal diagnostics are deployed without app, workflow, or control successors
- **THEN** the canonical advertised MCP handle set and operations remain unchanged
- **AND** no external caller can activate or invoke the dark core through a newly reachable route

### Requirement: Core completion requires authority, recovery, and load proof
The system MUST NOT declare the runtime core complete until focused/regression/security/fault suites, cross-process manifest/idempotency/epoch/lease/provider races, worker-restart recovery, §14 production-shaped load, existing Branch activation regressions, type/lint checks, packaged mirror parity, dark deployment health, and independent exact-head review all pass with freshness-stamped evidence.

#### Scenario: Unit tests pass but owner handoff or runtime proof is absent
- **WHEN** local tests pass without the exact activation/provider owner handoff, concurrency/load evidence, restart recovery, mirror parity, or dark deployment proof
- **THEN** the change remains incomplete and no as-built spec is synced

#### Scenario: Dark core acceptance passes
- **WHEN** every structural and runtime gate passes on exact versions using only requester-owned authority and no public/app/workflow surface
- **THEN** `custom-agent-runtime-core` may sync and archive after independent review
- **AND** later successors consume its immutable manifest, principal, activation, invocation, and health seams without replacing their owners
