## Context

PR #2080 established a contract-only coordination root and required the runtime core to land before app conversations, workflow evolution, or public control. Current main already has immutable public agent definitions, private revisioned bindings, a dark canonical `AutomationActivationStore`, Branch-only background binding/attempt authority, provider-work reservations, and Branch-pinned cloud-continuation records. PR #2077 made the Branch claim-to-provider handoff transactionally safe but explicitly left provider launch and cutover dark. The active cloud-drain lane still owns the authority files this successor must eventually consume.

The current activation, provider-work receipt, and cloud-continuation records assume an immutable Branch version. An arbitrary agent is not reducible to one Branch: its public components may describe identity, reasoning, tools, memory, workflows, evaluators, or user-invented kinds. Those owners therefore need one shared typed immutable execution-subject contract that can identify either an ordinary Branch version or a compiled agent manifest without running parallel epoch/lease/provider/continuation state machines. The background Branch binding/attempt authority remains Branch-specific and is not an agent invocation carrier. Generalization must be made by, or with an exact handoff from, the active owner while the cloud path is still dark.

The component envelope intentionally has no platform taxonomy or execution order. Runtime compilation must not guess that a component named `identity` is a prompt or that object insertion order is an orchestration plan. The private binding supplies a `runtime` envelope with an explicit governed plan-adapter reference and per-component runtime mode/adapter reference; the plan adapter declares topology and entry semantics, while component adapters declare typed component behavior. Existing `component_configuration` remains component-private configuration rather than hidden orchestration metadata.

## Goals / Non-Goals

**Goals:**

- Freeze a definition/binding revision into one immutable, content-addressed agent runtime manifest.
- Reuse the canonical activation epoch, executor, lease, transition, claim, and recovery authority.
- Compile all requested executable components through installed governed component and plan adapters without imposing a platform-wide topology or entry model.
- Derive and enforce a narrow agent runtime principal with current delegated grants.
- Execute a bounded typed invocation using only requester-owned provider/compute authority and durable cloud continuation.
- Keep health, recovery, and rollback inspectable through private internal projections.

**Non-Goals:**

- App/webhook/email ingress, outbound replies, conversation storage, Slack, or Teams.
- Branch creation/patching/runs/evaluation/workflow iteration or arbitrary external effects.
- Public MCP targets or operations, connector prose, rendered chatbot acceptance, or an eighth handle.
- Arbitrary tenant code, repository commands, shell access, or user-supplied adapter execution.
- A platform-owned agent archetype, fixed component enum, starter catalog, or guessed component semantics.
- A second activation, attempt, provider-work, continuation, or health state machine.

## Decisions

### 1. A compiled manifest is one shared typed execution subject

`AgentRuntimeManifest` is an immutable record identified by `agent_manifest_<ULID>` and a SHA-256 digest over canonical content. It pins the universe, binding ID/revision, definition ID/fingerprint, every component runtime mode, every resolved component and plan adapter identity/version/digest, the plan adapter's canonical typed execution plan, referenced capability/resource/provider-policy IDs, declared budget envelope, and compiler-contract version. It stores no raw credential, conversation, effect payload, provider response, or mutable execution state.

The canonical activation, provider-work, and cloud-continuation owners share one `ExecutionSubject` contract such as `(subject_kind, subject_ref, subject_digest)`. `branch_version` remains a valid kind; `agent_runtime_manifest` is added as another. Exactly one typed subject tuple participates in every activation compare-and-swap/claim, provider receipt/claim, and continuation prepare/resume validation. Existing Branch flows keep the same subject facts and safety behavior. The agent projection references those canonical owners; it does not persist their transitions itself.

For an agent binding, the activation service derives one reserved `automation_id` deterministically from the typed owner key `("agent_binding", agent_binding_id)` and never accepts an agent automation ID from a caller. The existing `(universe_id, automation_id)` primary key therefore becomes the uniqueness fence for `(universe_id, agent_binding_id)`: every manifest rebind advances the same record, and concurrent activation through alternate local IDs cannot create a second epoch or lease.

Storing the binding ID directly in the activation was rejected because a binding is mutable. Copying any canonical ledger was rejected because two epochs, provider claims, or continuations could both claim authority. Forcing an agent invocation through `BackgroundBranchAttempt` was rejected because its Branch definition/version and run-operation invariants are real authority, not generic labels.

### 2. Binding runtime metadata is explicit, private, and plan-adapter owned

The binding's private `runtime` envelope has `plan_adapter_ref`, optional plan-adapter configuration, `components`, and `budgets`. `runtime.components` is keyed by the same user-named keys as the public definition and supplies only runtime mode and optional governed component `adapter_ref`; existing `component_configuration` supplies private configuration consumed under each resolved descriptor's schema. Every component receives a runtime mode: omitted mode defaults to `execute` and therefore requires a governed component adapter; `descriptive_only` preserves the component and its allowed private configuration as typed immutable data but grants it no execution, tool, provider, resource, or effect behavior.

This metadata is validated only when compiling an activation, so authoring and remix remain daemon-free and can preserve unfamiliar kinds. The public definition is never mutated to fit one installation's adapter registry.

Guessing topology or entry semantics from names, component order, or a platform enum was rejected because it creates hidden archetypes and non-portable behavior. Treating unknown components as descriptive by default was rejected because it silently drops requested semantics.

### 3. Governed adapters compile one exhaustive adapter-declared plan

An installed `AgentComponentAdapterDescriptor` binds an exact component `kind` plus optional governed adapter reference to a stable adapter version/digest, configuration schema, typed inputs/outputs, required capability/resource/provider classes, confinement class, and budget dimensions. Compilation resolves every `execute` component and emits an exhaustive typed component set or deterministic diagnostics.

An installed `AgentPlanAdapterDescriptor` owns one stable plan class, its topology and entry schema, compatible component input/output contracts, complete-component coverage rule, confinement class, and canonical plan compiler. It receives the resolved typed component set and must either include every `execute` component under its declared semantics or reject compilation; the platform never assumes that an agent is single-entry, acyclic, connected, or even graph-shaped. A single-entry DAG is one admissible plan class, while recurrent, multi-entry, event-driven, state-machine, or future shapes require their own governed descriptors. Descriptive components can be consumed only where an applicable descriptor declares their canonical configuration as typed input. The compiler never interprets unknown JSON as a prompt or code.

The first production-safe plan/component pair may be a generic bounded provider-turn primitive that transforms declared typed context/input into typed output without graph mutation or external effects. That is one supported descriptor, not the platform-wide agent archetype. Unsupported requested plan semantics fail closed without blocking import, export, or remix. User-supplied executable adapters remain blocked until a separately reviewed Engine OS/confinement successor admits them.

### 4. Compilation is deterministic, atomic, and separate from activation

Compilation reads one exact binding revision and definition fingerprint, resolves the current installed adapter set and governed references, validates the complete plan, then writes one manifest atomically. Any concurrent binding change, missing adapter/resource, digest mismatch, unsupported confinement, invalid dependency, secret-bearing material, or size/budget violation leaves no manifest.

Recompiling identical canonical inputs returns the existing manifest under a caller-supplied idempotency key and content digest. A changed adapter version/digest or binding revision creates a new manifest; it never changes one already activated. Compilation confers no execution authority and does not activate automatically.

### 5. The runtime principal is server-derived and narrower than the owner

`AgentRuntimePrincipal` is derived from the authenticated owner, universe, binding, manifest, activation epoch, executor/lease, and invocation. It is not accepted from component or binding JSON. The manifest lists capability/resource/provider references as requests; the runtime resolves and live-checks their current grants before every privileged transition.

The principal cannot inherit the owner's bearer token, caller-selected actor, maintainer permissions, or environment credentials. Revocation after compilation or activation blocks the next invocation/resume/provider reservation. Grant evidence records stable non-secret identifiers and generations without copying secret values.

### 6. Server-authored admission precedes provider execution

A private caller cannot create spend-causing work by constructing an invocation row or calling a generic dispatcher. While current authenticated owner intent is still live, the existing request boundary creates one inert single-message provider-work binding draft for the registered dark agent-invocation operation. The canonical agent-invocation admission service resolves the exact agent target and atomically consumes that draft into one non-bearer `ProviderWorkBinding` linked with one server-authored `AgentInvocationCommand` and append-only `AgentInvocation` lifecycle root. Future admission roots require their own approved successor delta.

The server-authored command binds the authorizing principal and grant generation, universe, binding revision, manifest execution subject, activation epoch/executor/lease, typed-input digest, stable invocation identity, budget envelope, provider-work binding identity/generation/digest, and idempotency key. Exact retries replay the same three linked identities, changed-input key reuse conflicts, and concurrent duplicates have one winner. If the authenticated recording boundary or atomic aggregate is absent, no command, invocation, or provider-work binding can be reconstructed after the request ends.

The durable command and provider-work binding store authority provenance, not the owner's bearer. Recovery can resume the same invocation after the request ends, but it must revalidate the command, binding, current activation, grants, subject, lease, and budgets. Private helpers, queue possession, generic dispatch, persisted actor labels, raw command fields, and raw `AgentInvocation` fields cannot mint or widen either record.

After admission, the invocation asks the canonical provider-work owner for requester-owned authority under server-classified `work_item_kind=agent_invocation` and the same subject tuple. The provider child receives only the universe-scoped credential route selected by that owner.

The provider-work owner replaces its Branch-only receipt identity with the shared typed subject while preserving every binding, revocation, operation/role, budget, expiry, claim, and concurrency guard for existing Branch work. The cloud-continuation owner likewise carries the same typed subject for agent invocation recovery. Neither change weakens or aliases Branch fields, and the Branch-only background-attempt ledger is not edited or queried for agent invocations.

Missing, paused, revoked, expired, over-budget, or unusable provider authority terminates with a typed blocker. There is no maintainer, host, market, ambient, or alternate-provider fallback unless the user's bound provider policy explicitly and validly names that route. A provider result is typed data, not authority to mutate graphs or create external effects.

The core supports no public invocation surface. Its internal service exists only for focused integration and successor composition; later app/control successors must add their own authenticated admission roots before routing into it.

### 7. Recovery retains separate identities and useful-progress health

Activation, agent invocation, provider reservation/attempt, and cloud continuation remain separate durable records owned by their canonical modules. Recovery resumes or reconciles the same identities after worker death and revalidates the shared execution subject, activation epoch, executor, lease, binding/manifest pins, grants, provider authority, and budgets before continuing. Branch work continues to use its separate background binding/attempt record without aliasing an agent invocation.

Stale or alternate executors fail closed. Host-to-cloud cutover remains single-active. Health is a private projection over owner records and distinguishes useful transitions—manifest compiled, invocation admitted, provider result recorded, typed terminal output/blocker—from heartbeat or retry churn. Repeated retries without a useful transition alarm and do not mint a new invocation automatically.

### 8. The core lands dark and hands off immutable seams

Runtime implementation begins only after an exact current-main audit and explicit handoff from the active activation/provider/cloud-continuation owner. The first implementation claim lists exact canonical files plus new core modules/tests and their packaged mirrors. Tests prove no app route, graph mutation, external effect, or public MCP operation becomes reachable.

The slice passes focused unit/integration/security tests, cross-process compile/idempotency/epoch/lease/provider races, restart fault injection, §14 production-shaped load, type/lint checks, mirror parity, and independent exact-head review. It may deploy dark for structural/runtime health proof, but it does not require or claim rendered app/chatbot or organic-use evidence because it exposes no user surface.

## Risks / Trade-offs

- **[Generalizing typed subject identity can disrupt three active owners]** → Require their exact handoff, one shared tuple with no dual identity, and existing Branch activation/provider/continuation regression and concurrency proof.
- **[Adapters recreate a fixed taxonomy or topology]** → Key component and plan adapters by extensible governed references, and let each plan descriptor declare its own entry/topology semantics.
- **[A compiler silently omits unfamiliar semantics]** → Default every component to `execute`, require explicit `descriptive_only`, and require plan-adapter proof that every executable component is covered.
- **[Two IDs activate one binding]** → Derive one reserved automation key from the binding ID and prove the existing primary key fences concurrent aliases.
- **[A helper mints spend without user intent]** → Require an atomic server-authored invocation command and prove all lower-level paths fail closed.
- **[A manifest freezes stale authority]** → Freeze only requested references; revalidate live grants/provider authority at every invocation/resume.
- **[Provider output becomes ambient authority]** → Treat it as typed data and expose no graph/effect operations in this slice.
- **[A dark core is mistaken for a usable agent]** → Preserve binding `configured`, expose no public operations, and report readiness only in private internal diagnostics.

## Migration Plan

1. Land and independently review this spec with no runtime file claim.
2. Wait for the activation/provider/cloud owner to land or grant an exact handoff; rebase and audit current main.
3. Test-first, generalize the shared activation/provider-work/continuation subject, enforce the derived binding activation key, and add immutable manifests plus component/plan compilation behind dark internal APIs while leaving Branch-attempt authority unchanged.
4. Add the delegated principal and server-authored invocation-command lifecycle, then compose provider/cloud continuation without public/app/workflow routes.
5. Prove recovery, races, load, mirror parity, and existing Branch activation regression; deploy dark only if every gate passes.
6. Sync/archive this core after dark runtime proof, then let separately admitted app, workflow, and control successors consume its immutable seams.

Rollback disables new agent-manifest admission, advances any dark agent activation to stopped through the canonical owner, and leaves immutable definitions, bindings, manifests, receipts, and Branch activations intact. It never deletes or rewrites public agent content.

## Open Questions

- What exact typed-subject field names will the active activation owner approve at handoff while its store is still dark?
- Which current grant resolver becomes the single runtime capability check, given the active authority hardening lanes?
- Which generic provider-turn descriptor is sufficiently useful for dark proof without becoming a privileged agent archetype?
