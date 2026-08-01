## ADDED Requirements

### Requirement: Activation freezes one authorized binding snapshot
The system SHALL let a universe owner compile and activate one private `AgentBinding` revision through the canonical server-authoritative automation activation owner as a runtime snapshot containing the exact definition ID and fingerprint, binding revision, compiled-manifest digest, executor class, monotonically increasing activation epoch, lease generation, budgets, and state, while creating no agent-only activation ledger and storing no copied credential, conversation, effect payload, or mutable workflow state in that snapshot.

#### Scenario: Binding update does not mutate a running agent
- **WHEN** an owner updates the binding after revision `4` was activated
- **THEN** the active runtime remains pinned to revision `4` and its definition fingerprint
- **AND** the successor revision takes effect only after an explicit owner-authorized rebind advances the activation epoch

#### Scenario: Concurrent activation transitions race
- **WHEN** two callers submit pause, rebind, resume, stop, or activation transitions from the same expected epoch
- **THEN** at most one compare-and-swap transition commits
- **AND** the stale transition performs no invocation, provider spend, graph mutation, or external effect

### Requirement: Component compilation is exhaustive and fail-closed
The system MUST resolve every executable definition component and private component configuration through an installed governed adapter with a frozen version/digest, declared artifact types, required resources, permitted capabilities, confinement class, and budget dimensions, and MUST return exhaustive per-component diagnostics without executing a partial agent whose requested semantics are unresolved.

#### Scenario: Unfamiliar component remains portable but blocks requested execution
- **WHEN** a definition contains an unfamiliar component marked for execution and no governed adapter resolves it
- **THEN** compilation reports that exact component as `unsupported` and the activation remains `blocked`
- **AND** the original component remains unchanged in definition reads, exports, and remixes

#### Scenario: Descriptive component needs no runtime adapter
- **WHEN** a component is explicitly descriptive-only and requests no executable behavior
- **THEN** compilation may classify it `descriptive_only` without blocking otherwise complete semantics
- **AND** it gains no tool, provider, resource, or effect authority

#### Scenario: Tenant code lacks production confinement
- **WHEN** an adapter requests source code, repository commands, shell access, or another tenant-code execution class before Engine OS confinement is available
- **THEN** activation reports `sandbox_unavailable` and performs no code execution, provider invocation, graph mutation, or external effect

### Requirement: Runtime authority is delegated, scoped, and live-checked
The system MUST derive an agent runtime principal from the authenticated owner, universe, binding, activation epoch, and invocation, MUST authorize every graph read/write, provider invocation, governed-resource use, workflow action, and external effect against a current explicit capability grant, and MUST never substitute the owner's bearer identity or maintainer, host, market, or ambient authority.

#### Scenario: Message asks the agent to exceed its grant
- **WHEN** an authenticated or unauthenticated interlocutor asks an agent with read-only Branch authority to patch or run a Branch
- **THEN** the mutation or run is refused under the agent principal
- **AND** neither message content nor the owner's broader authority widens the grant

#### Scenario: User-owned provider becomes unavailable
- **WHEN** the bound provider authority is missing, paused, revoked, expired, or unusable at invocation time
- **THEN** the invocation records a typed authority blocker
- **AND** no maintainer, host, market, or ambient provider route is attempted

### Requirement: App ingress is authenticated, tenant-bound, and replay-safe
The system SHALL accept an external app event only through the canonical boundary-layer ingress owner after it verifies provider authentication, maps the installation/tenant and sender through current authority to exactly one universe and binding, enforces timestamp, size, rate, abuse, attachment, interlocutor, and grant policy, and durably reserves replay identity `(provider, external_installation_or_tenant_id, provider_event_or_message_id)` plus the normalized body digest before agent dispatch; the agent runtime MUST create no second inbox, webhook verifier, or replay ledger.

#### Scenario: Duplicate app delivery wakes one logical invocation
- **WHEN** an app retries the same provider event or message ID concurrently or after worker restart
- **THEN** every delivery resolves to the same durable inbound event and logical invocation
- **AND** the runtime does not repeat workflow mutations or replies merely because delivery was retried

#### Scenario: External identifiers cannot alias across tenants or changed bodies
- **WHEN** two installations or tenants use the same provider event/message ID, or one installation repeats that ID with a different normalized body digest
- **THEN** different installation/tenant tuples remain distinct events while the changed-body reuse of one exact tuple records a conflict/hold
- **AND** the conflicting payload is not dispatched, merged into prior context, or allowed to replace the reserved digest

#### Scenario: Message content attempts to choose identity or tenancy
- **WHEN** an event body, mention, channel name, or caller-supplied field names another actor, universe, binding, role, or organization
- **THEN** routing and interlocutor tier remain derived only from the verified connection and identity mappings
- **AND** an absent, revoked, stale, or ambiguous mapping fails closed without waking an agent

#### Scenario: Slack or Teams organization mapping is unavailable
- **WHEN** a Slack or Teams event arrives before current installation, workspace, membership/group, offboarding, and role state can be resolved by the organization-authority owner
- **THEN** the adapter remains inactive or records a typed refusal
- **AND** no string address or webhook secret substitutes for organization authority

#### Scenario: Authenticated app sender remains below the conversation floor
- **WHEN** an app provider authenticates a sender whose mapped TinyAssets interlocutor is not permitted by the canonical conversation authority
- **THEN** the event is refused before agent context assembly or provider invocation
- **AND** the custom-agent route does not create a second non-founder authorization path

#### Scenario: Membership is revoked after durable admission
- **WHEN** an admitted event resumes after a worker delay or restart and the sender's connection, organization membership/group, offboarding, role, or interlocutor authority is no longer current
- **THEN** the system revalidates those authorities before private context assembly, graph mutation, provider invocation, and reply reservation and records a terminal authorization blocker
- **AND** it exposes no new private context, performs no mutation or spend, and sends no reply under the stale admission

### Requirement: App replies use one governed outbound effect identity
The system MUST send every app reply through a current per-universe connection grant and credential-blind trusted proxy using a system-derived effect identity bound to the activation epoch, inbound event, reply ordinal, connection grant, destination, and effect kind, with caps, redaction, reconciliation, and terminal receipts enforced by the outbound-boundary owner.

#### Scenario: Reply result is lost after the destination accepted it
- **WHEN** a worker restarts after an app may have accepted the reply but before local finalization
- **THEN** recovery attaches and finalizes an exact remote match when supported, retries only after conclusive absence under the same bounded reservation, or blocks on ambiguity
- **AND** it never creates a fresh effect identity to send the same logical reply again

#### Scenario: Connection grant is revoked
- **WHEN** the destination connection grant is absent, expired, revoked, over cap, or does not cover the exact destination and effect kind
- **THEN** the reply is held or refused before credential resolution or remote mutation
- **AND** the runtime does not fall back to an ambient app credential

### Requirement: Conversations remain private and speaker identity is explicit
The system SHALL keep external message content, attachments, conversation turns, summaries, and model context in universe-private runtime/conversation custody under authorization, retention, export, and deletion policy, SHALL exclude them from public definitions, portable exports, binding records, lineage, and public receipts, and SHALL identify the bound agent rather than impersonating the whole universe.

#### Scenario: Public definition is exported after app use
- **WHEN** an agent with app conversations is exported or remixed
- **THEN** the portable definition contains only public definition content and public lineage
- **AND** it contains no installation, channel, sender, message, conversation, attachment, credential, activation, or effect data

#### Scenario: Agent assembles a reply
- **WHEN** an admitted interlocutor talks to a bound agent
- **THEN** response context contains only that agent's pinned identity/persona components as a named projection of universe whole-mind information authorized for the interlocutor and activation
- **AND** the response neither claims to be the entire universe nor fabricates founder/private knowledge

### Requirement: Agents iterate ordinary workflows through existing primitives
The system SHALL let an activated agent with explicit grants create or patch an ordinary Branch, inspect its complete diff, compile and dry-test without external effects, run it within declared budgets, evaluate it against frozen evaluator and Gate versions, publish a successor immutable version, and explicitly activate or roll back that version, while keeping every generated workflow independently exportable, publishable, and remixable.

#### Scenario: Agent repairs a failing workflow
- **WHEN** a frozen evaluator rejects a candidate workflow run
- **THEN** the failure produces bounded repair context for a new candidate version and invocation
- **AND** the candidate cannot alter the frozen evaluator, self-certify success, or acquire effect, merge, deployment, or broader graph authority from the result

#### Scenario: Concurrent iterations target one workflow
- **WHEN** two invocations attempt to evolve the same Branch or activation from one base revision
- **THEN** revision, claim, and activation-epoch guards allow at most one successor transition
- **AND** the loser preserves evidence without overwriting or silently merging the winner

### Requirement: Activation survives offline users and worker recovery with one executor
The system MUST persist activation, invocation, inbox, workflow-claim, provider-attempt, evaluation, and outbound-effect identities so a cloud worker can resume or reconcile them after restart, MUST fence stale epochs and leases, and MUST require a host activation to stop before cloud acceptance rather than retaining simultaneous host fallback.

#### Scenario: Cloud worker restarts mid-invocation
- **WHEN** the active cloud worker stops after any durable reservation and a replacement starts
- **THEN** the replacement resumes or reconciles the same activation, invocation, claims, provider attempts, and effects before doing new work
- **AND** no stale or alternate executor can continue after its epoch or lease is fenced

#### Scenario: User computers remain offline
- **WHEN** a cloud activation has been accepted and every user device and tray is offline
- **THEN** admitted conversations and scheduled workflow iterations continue through the user's cloud universe and explicitly bound provider/compute authority
- **AND** device shutdown does not erase, silently pause, or transfer authority for the activation

### Requirement: Owners control and inspect agents through the canonical seven handles
The system SHALL expose private compile, activate, pause, resume, rebind, stop, run, and status behavior as coarse targets or operations behind the existing canonical `read_graph`, `write_graph`, `run_graph`, and `get_status` handles, SHALL preserve not-found-equivalent authorization for private state, and SHALL keep the advertised public MCP set at exactly seven handles.

#### Scenario: Owner controls an agent from a phone chatbot
- **WHEN** the authenticated owner inspects or changes an activation with no desktop, CLI, filesystem, or host login
- **THEN** the private owner projection reports the pinned definition/binding, component diagnostics, state, epoch, current invocation, authority classes, budgets, connection state, last useful progress, receipts, next retry, and blocker
- **AND** an owner-authorized pause, resume, rebind, stop, or rollback applies through compare-and-swap control

#### Scenario: Configured channel is not connected
- **WHEN** a binding names an app adapter or address but ingress authentication, organization mapping, connection grant, or outbound readiness is incomplete
- **THEN** the private owner projection remains `configured` or `blocked` and names the missing prerequisite
- **AND** it does not claim `active`, `connected`, or successful delivery

### Requirement: Completion requires concurrency, live app, and organic proof
The system MUST NOT declare custom-agent runtime activation complete until it passes security and fault-injection tests, §14 production-shaped concurrency/load proof, packaged-runtime parity, deployment and canonical canaries, rendered live connector control, rendered Slack ingress/reply with duplicate-delivery recovery, a continuous 24-hour PC-off window including worker restart, activation of a real other-creator remix, and distinguishable post-fix organic use.

#### Scenario: Structural tests pass without live evidence
- **WHEN** unit, integration, security, concurrency, load, and canary checks pass but rendered app, PC-off, cross-user, or organic evidence is absent
- **THEN** the change remains incomplete with the missing evidence named in `STATUS.md`
- **AND** no spec is synced or archived as fully built

#### Scenario: End-to-end acceptance passes
- **WHEN** one production activation satisfies every required structural and live proof using only requester-owned authority
- **THEN** evidence records exact versions, environments, timestamps, load shape, recovery events, rendered conversations, effect receipts, and privacy-safe organic-use source
- **AND** the capability may sync to as-built specs and archive after independent exact-head review
