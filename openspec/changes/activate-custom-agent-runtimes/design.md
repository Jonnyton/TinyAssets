## Context

The definition/binding slice established an open, immutable `AgentDefinition` and a private, revisioned `AgentBinding`. Interchange made those definitions portable and remixable without a finite starter catalog. Both artifacts are intentionally inert: the current binding status is `configured`, unknown components remain data, and channel references do not claim a connection.

The target runtime must compose existing owners rather than invent a parallel agent stack. PLAN already assigns transactional activation/claiming to the daemon platform, user-owned provider authority to the cloud execution path, workflow semantics to Branch/Run/Gate/Evaluator primitives, credentials and external effects to the connection boundary, and public control to the canonical seven MCP handles. Active authority repairs also own private Branch, Run, evaluation/version, and branch-adjacent access. Several seams are live work owned by other sessions, so this contract-only lane specifies the composition and dependency graph, edits no runtime files, and requires separately admitted delivery successors after exact handoffs.

Slack and Teams also carry organization membership and offboarding semantics. They cannot be treated as a string address plus webhook secret. Their production adapters stay dark until the organization-authority successor binds the external installation, workspace, membership, and group to a TinyAssets principal and universe. The generic connector contract is not Slack-specific and supports future personal or organization apps through the same boundary.

## Goals / Non-Goals

**Goals:**

- Turn one authorized private binding revision into one durable, inspectable runtime activation.
- Preserve the open component envelope while executing only installed, governed adapters.
- Receive authenticated app messages and send replies without putting secrets, conversations, or effect payloads in agent artifacts.
- Let an agent create, dry-test, evaluate, publish, run, observe, repair, and iterate ordinary workflow automations under explicit delegated authority.
- Continue while the user's devices are offline using only user-owned provider/compute authority.
- Give owners phone-chatbot control, deterministic rollback, typed receipts, and useful-progress health through existing MCP handles.

**Non-Goals:**

- Add a privileged OpenClaw, Hermes, coding-agent, Slack-agent, or other platform archetype.
- Execute unknown component semantics or arbitrary tenant code outside the Engine OS confinement owner.
- Copy app, provider, or subscription secrets into definitions, bindings, prompts, graph state, logs, or receipts.
- Make an inbound message itself an authorization grant.
- Clone the Branch/run/evaluation engine, connection ledger, provider router, scheduler, conversation store, or organization policy engine.
- Add an eighth MCP handle, give agents merge/admin authority by default, or retain a host as a simultaneous fallback after cloud cutover.

## Decisions

### 1. Activation freezes a binding snapshot and advances by epoch

`AgentRuntimeActivation` is a typed projection over the canonical server-authoritative automation activation owner, not a second table or transition service. After an exact handoff, that owner must accept a typed immutable activation subject rather than assuming every subject is only a Branch version. For an agent the subject is keyed by `(universe_id, agent_binding_id)` and freezes the exact binding revision, definition ID and fingerprint, and compiled-manifest digest alongside the canonical executor class, monotonically increasing epoch, lease generation, state, budgets, timestamps, and latest health/receipt references. It contains references, not copied component payloads, credentials, messages, or workflow state.

Create, activate, pause, resume, rebind, stop, cutover, and rollback are owner-authorized compare-and-swap transitions. An update to the underlying binding does not mutate a running activation. A new revision takes effect only through explicit rebind, which compiles a new manifest and advances the epoch. Every invocation validates the exact activation epoch, executor class, lease generation, binding revision, definition fingerprint, and compiled-manifest digest before it can spend, mutate graph state, or emit an effect.

Reusing the binding's `status` as runtime state was rejected: binding configuration and process health fail independently, and conflating them would make immutable replay and rollback ambiguous. A separate agent activation ledger was also rejected because the existing epoch/lease owner must remain the sole activation authority across Branch automations and agent runtimes.

### 2. Compilation resolves governed adapters and fails closed as a complete unit

Activation compilation walks every definition component and its private configuration. A registry resolves each executable `kind` plus optional `adapter_ref` to an installed adapter contract with a stable version/digest, declared input/output artifact types, required governed resources, permitted capability verbs, confinement class, and budget dimensions. The compiled manifest freezes those resolutions and produces exhaustive `ready`, `descriptive_only`, `unsupported`, or `blocked` diagnostics per component.

An explicitly descriptive component may remain non-executable. Any component that requests execution but has no installed adapter, unresolved resource, incompatible artifact type, or unavailable confinement blocks the entire activation. Unknown components remain fully portable and remixable; they are never silently ignored, interpreted as prompts, or passed to a generic code evaluator. Arbitrary code adapters require the Engine OS production confinement contract before they can report ready.

A platform-owned component enum was rejected because it would reintroduce the power-user ceiling. Best-effort partial activation was rejected because it changes agent semantics without the author knowing.

### 3. Runtime authority is a narrow delegated principal, not the binding owner

The runtime acts as a server-derived agent principal bound to the owning subject, universe, binding, activation epoch, and invocation. The binding references explicit capability grants for graph reads/writes, workflow execution, provider use, resources, and external destinations. Admission checks the live grant on every privileged transition; cached grants and user-authored actor fields are not authority.

Provider invocation resolves only requester-owned authority selected by the binding/provider policy. Missing, paused, revoked, expired, or unusable authority blocks without maintainer, host, market, or ambient fallback. The first safe implementation may execute only already-admitted declarative nodes and deterministic evaluators. Tenant code, repository commands, or tools that need isolation remain blocked until the Engine OS owner supplies production confinement.

Giving the runtime the owner's bearer identity was rejected because a prompt injection or compromised app sender would inherit every owner capability.

### 4. App ingress is authenticated, tenant-bound, replay-safe, and non-authorizing

The canonical boundary-layer ingress owner verifies provider signatures/tokens before constructing a canonical inbound envelope; the custom-agent runtime creates no second inbox, replay ledger, or webhook verifier. The envelope includes the connection grant, external installation/tenant, channel or conversation, provider message/event ID, verified sender mapping, event timestamp, normalized content reference/digest, and bounded attachments. Raw request authentication material never crosses from the trusted boundary into agent adapter code or agent context.

The connection ledger maps that envelope to exactly one authorized universe and binding. Slack/Teams additionally require the organization-authority owner to resolve current installation, workspace, membership/group, offboarding, and role state; an absent or ambiguous mapping fails closed. Message text, mentions, channel names, and caller-supplied IDs never select the TinyAssets principal, universe, binding, or role. The app route also consumes the canonical interlocutor authorization floor: non-founder senders remain refused until its owner ships a reviewed non-founder path, even if the app provider authenticated them.

Inbox admission reserves a system-derived replay identity before dispatch. Duplicate deliveries observe the same event/invocation record. Events outside timestamp, size, rate, abuse, attachment, or grant policy receive a typed refusal/hold and do not wake the runtime. An admitted message supplies input, not permission: the agent still needs a separate capability for every graph mutation, provider call, or reply.

Direct webhook code inside an `AgentDefinition` or a custom-agent-owned inbound ledger was rejected because either would fork identity, replay, moderation, and secret custody per agent.

### 5. Replies use the outbound boundary and one system-derived effect identity

An agent reply is a typed external effect routed through the same live connection grant. The trusted proxy resolves credentials, applies destination and action caps, redacts logs, and records reservation, attempt, reconciliation, and terminal receipts. Adapter code remains credential-blind.

The reply effect identity is derived from `(universe_id, activation_id, activation_epoch, inbound_event_id, reply_ordinal, connection_grant_id, destination, effect_kind)`. Recovery attaches an exact remote match where the destination can reconcile it; conclusively absent retry remains bounded under the same reservation; ambiguity blocks without another send. Pause or stop prevents future replies but does not represent an already accepted external message as cancelled.

Slack is one adapter over this contract, not a special execution path. Adding provider-specific send logic to the custom-agent service was rejected because it would bypass revocation, caps, and effect receipts.

### 6. Conversation state is private runtime data and the speaker is explicit

Conversation turns, attachment content, summaries, and model context live in the universe's private conversation/runtime store under retention and deletion policy; they never enter a public definition, portable export, binding record, lineage edge, or public receipt. Read paths enforce universe and interlocutor authorization before context assembly.

An app conversation explicitly names the bound agent as speaker and assembles its pinned identity/persona components as a named projection of only the universe whole-mind context allowed to that interlocutor and activation. The agent does not claim to be the entire universe or manufacture founder/private knowledge. The existing `converse` surface remains the universe's direct whole-mind personification; the personification-relay owner must reconcile the first outbound agent surface before rollout.

Treating the external sender as the binding owner, or making every custom agent a second universe identity, was rejected. The agent is an explicitly bound actor whose voice and authority are inspectable.

### 7. Workflow iteration composes the existing graph lifecycle

The runtime does not own a workflow format. A workflow-oriented component resolves to ordinary Branch definitions and immutable versions. Under explicit grants, an invocation may propose or patch a Branch, inspect the complete diff, compile/dry-test without external effects, create a bounded Run, evaluate it through frozen evaluator/gate versions, publish a successor Branch version, and explicitly bind or roll back an activation. Failed evaluation produces bounded repair context for a new iteration; it never self-certifies success or grants effect, merge, or deployment authority.

Every step records the activation/invocation, authenticated requester or external interlocutor, delegated agent principal, source Branch/version, evaluator versions, budgets, outputs, and next action. Concurrent iterations use revision/epoch guards and one active claim per workflow identity. Generated workflows remain ordinary user-owned artifacts that can be exported, published, and remixed independently of the agent.

Creating an agent-specific workflow engine was rejected because it would strand agent-authored automations outside the commons and existing evaluation evidence.

### 8. Existing handles expose coarse control and complete diagnostics

The canonical surface remains `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`. `write_graph target=agent_binding` gains coarse owner operations such as compile/activate/pause/resume/rebind/stop; `read_graph` and `get_status` expose the private activation projection; `run_graph` invokes an admitted agent/workflow operation where appropriate. Exact operation names are frozen test-first during the router slice after the cohit check and owner handoffs.

Responses distinguish `configured`, `blocked`, `activating`, `active`, `paused`, and `stopped`; name every unsupported component or missing authority; and never claim an app is connected until authenticated ingress and outbound grant checks pass. Private state retains not-found-equivalent authorization behavior.

A new `agents` MCP tool was rejected because it would violate the exact-seven contract and add selection burden without adding a primitive.

### 9. Health measures useful progress and recovery is single-active

Activation, invocation, inbox event, workflow claim, provider attempt, evaluation, and outbound effect retain separate durable identities and owners. Cloud continuation resumes or reconciles the same identities after worker death. Epoch and lease checks fence stale cloud workers and stopped host executors. A cloud activation is not accepted until any host activation is stopped; the host is not kept as a simultaneous fallback.

Health reports last useful progress, current invocation/claim, resolved authority classes, budget state, next retry, blocker, connection state, and terminal receipts. Repeated heartbeat or retries without a conversation response, workflow/evaluation transition, or explicit durable blocker is unhealthy and alarms. Owner pause, stop, rebind, and rollback remain operable from a phone chatbot with the user's computers offline.

### 10. Delivery is split into bounded successors and independently proven

This change is contract-only and owns no runtime implementation. Delivery is split into separate OpenSpec changes, STATUS claims, branches, reviews, and PRs:

1. `activate-custom-agent-runtime-core` composes the sole activation owner, exhaustive component compiler, delegated principal, user-owned provider/cloud continuation, recovery, and health; it exposes no app ingress and performs no workflow authoring.
2. `connect-custom-agent-app-conversations` consumes the landed core plus the sole boundary ingress/effect owner, private conversation custody, organization authority, canonical interlocutor floor, and personification reconciliation; it owns no workflow mutation lifecycle.
3. `enable-custom-agent-workflow-iteration` consumes the landed core plus `harden-branch-access-authority`, `harden-run-branch-access-authority`, `harden-branch-evaluation-access-authority`, and `harden-branch-adjacent-access-authority`; tenant-code operations additionally wait for Engine OS confinement.
4. `expose-custom-agent-runtime-control` adds coarse canonical-handle operations and packaged mirror only after the underlying transitions are live; it adds no eighth handle and no new lifecycle owner.
5. `prove-custom-agent-runtime-live` integrates the landed slices and owns deployment, canary, load, rendered app/connector, PC-off, cross-user remix, and organic-use proof without adding product semantics.

Each successor has one sentence of intent, at most 12 session-sized tasks, an exact Files boundary, and an independent review. No successor may be claimed by the same provider while another delivery change is active; this coordination root moves to monitoring after publication so one successor at a time can be admitted normally.

No successor claims `active` or `connected` before all of its prerequisites are live. Final acceptance includes security/fault tests, §14 concurrency/load proof, packaged mirror parity, deployment/canary evidence, a rendered live connector control conversation, a rendered Slack conversation with duplicate-delivery/reply proof, 24 hours of PC-off useful progress including worker recovery, a real other-creator remix activation, and post-fix organic use.

### 11. The first V1 proof is one remix-to-running experience, not a starter archetype

The host-approved first V1 golden path begins with a browser-only user and real
public definitions authored by other users. The user selects components from
at least two creators, replaces/removes/adds components through the existing
graph surface, and produces one child with verified component-level lineage.
The user then chooses the private cloud-universe custody mode for this
experience and binds their own supported provider authority, goals, governed
resources, Slack connection, budgets, and runtime policy. No private binding,
credential, conversation, goal, or runtime field enters the public definition,
portable lineage, or commons export.

Through a rendered Slack conversation, the user asks the bound agent to create
a recurring intelligence workflow. The agent composes an ordinary Branch,
dry-tests without external effects, runs it within a declared budget, evaluates
against frozen criteria, presents one evidence-backed revision, and requests
explicit activation. After approval, a genuine scheduled run posts a cited
result during a continuous PC-off cloud window that includes worker recovery.
The same agent is exported and re-imported canonically; when its definition is
published, a second account remixes it without receiving any first-account
private state.

“Intelligence agent” is deliberately fixture content rather than a component
kind, runtime mode, enum, built-in configuration, ranking preference, or
platform-maintained starter. It was selected because a read-heavy,
source-verifiable workflow keeps remix, evaluation, app conversation, and
offline execution visible without making repository-write confinement the
center of the first demonstration. Coding agents, OpenClaw-like operators,
Hermes-like assistants, and foreign imports remain later community
compositions over exactly the same pipeline.

## Current-main owner audit

Re-audited 2026-08-01 against base `11657461`. “Missing” means no admitted
OpenSpec delivery owner or production API exists; this coordination root does
not silently claim that surface.

| Concern | Current owner / API | Current handoff state |
|---|---|---|
| Definition, N-parent remix, private binding | `universe-custom-agents`; `tinyassets/custom_agents.py`; `tinyassets/api/custom_agents.py` | Domain/API landed; final public, rendered, cross-user, and organic evidence remains. |
| Canonical interchange/export | `agent-interchange-pipeline`; `tinyassets/agent_interchange.py` | Core and live single-user proof landed; real other-creator blend and organic evidence remain. |
| Runtime manifest, component/plan compilation, grants, principal | `activate-custom-agent-runtime-core`; `tinyassets/agent_runtime.py`, `agent_runtime_compiler.py`, `agent_runtime_plan_compiler.py`, `agent_runtime_grants.py`, `agent_runtime_principal.py` | Immutable dark seams landed; delegated invocation, recovery, health, load, review, and foldback remain under the active cloud owner. |
| Activation, continuation, provider authority | `activate-main-universe-spec-drain`, `harden-background-provider-execution-authority`, and runtime-core; `tinyassets/user_owned_cloud_automation.py`, `cloud_automation_continuation.py`, `provider_work_authority.py` plus their storage modules | Actively owned by `codex-gpt5-desktop-cloud`; no app/workflow successor may overlap or infer completion. |
| Outbound connection/effect authority | `outbound-boundary-layer`; `ConnectionLedger` / `ScopedConnectionProxy` in `tinyassets/storage/outbound_connections.py`; `execute_replay_safe_effect` in `tinyassets/effectors/outbound_boundary.py` | Connection grants, caps, and replay-safe non-value effects are built dark; final verification/foldback remains. |
| Authenticated app ingress/inbox | `outbound-boundary-layer` tasks 4.1-4.2 are the nearest declared owner | Durable generic webhook/email inbox admission is unbuilt; no Slack signature verifier, app-event envelope, or connected claim may be inferred. |
| Slack organization/install/member mapping | **Missing owner and API** | Admit a narrow organization-authority change and exact handoff before `connect-custom-agent-app-conversations`. |
| Interlocutor authorization and voice | `reconcile-universe-personification-relay`; `tinyassets/api/interlocutor.py` | Tier binding and pre-assembly filtering exist, but production conversation is founder-only and outbound speaking tasks 6.4/6.5/6.9 remain open. |
| Private conversation custody | **Missing owner and store** | Select a user-chosen custody mode, retention/deletion contract, and narrow delivery owner before app conversation implementation. |
| Workflow mutation/evaluation authority | `harden-branch-access-authority`; future run/evaluation/adjacent successors; `engine-os-sandbox` for tenant code | Branch repairs are incomplete; run/evaluation/adjacent successors are not admitted; tenant code remains blocked. |
| Canonical control and integrated live proof | Future `expose-custom-agent-runtime-control` and `prove-custom-agent-runtime-live` | Not admitted until the underlying behavior slices land; they add no product semantics. |

## Risks / Trade-offs

- **[A broad agent can become an authority amplifier]** → Derive a narrow runtime principal and re-check live grants at every privileged transition.
- **[Unknown components create surprising partial behavior]** → Compile exhaustively and block the whole activation when requested semantics cannot execute.
- **[App retries can duplicate work or speech]** → Reserve system-derived ingress and effect identities before dispatch and reconcile under the same identities.
- **[Slack/Teams identity can drift after offboarding]** → Require live organization/install membership resolution and fail closed on stale or ambiguous state.
- **[24/7 execution can spend indefinitely]** → Freeze per-invocation and rolling budgets, expose holds, and measure useful progress rather than process liveness.
- **[An agent can optimize its own tests]** → Freeze evaluator/gate versions outside the candidate mutation and keep evaluation non-authoritative.
- **[Cross-owner composition can produce a second state machine]** → Store only references/projections and leave activation, provider, workflow, conversation, and effect lifecycle writes with their canonical owners.
- **[The full vertical slice is dependency-heavy]** → Land dark seams independently, preserve `configured`, and refuse `active`/`connected` claims until end-to-end proof passes.

## Migration Plan

1. Land and independently review this contract-only change; keep all bindings inert and move its STATUS row to monitoring.
2. Admit and deliver `activate-custom-agent-runtime-core` after the activation/provider owner handoffs.
3. Admit and deliver `connect-custom-agent-app-conversations` after boundary, organization, interlocutor, conversation-custody, and personification handoffs.
4. Admit and deliver `enable-custom-agent-workflow-iteration` after all Branch/Run/evaluation authority repairs and Engine OS gates that its exact slice needs.
5. Admit and deliver `expose-custom-agent-runtime-control` behind the exact seven handles.
6. Admit and deliver `prove-custom-agent-runtime-live`, then sync the as-built capability and archive this coordination root only after every required proof exists.

Rollback stops admission, advances the activation epoch to `stopped`, revokes future invocation/effect reservations, and leaves immutable definitions, bindings, workflow versions, receipts, and already-terminal external effects intact. Rollback never rewrites public lineage or claims that an irreversible external effect was undone.

## Open Questions

- Which organization-authority change will own the canonical Slack workspace/member/group mapping, and what exact handoff artifact will this change consume?
- Which production app adapter should prove the generic contract before or alongside Slack if organization authority is not yet live?
- Which private conversation store and retention/deletion owner will supply the first runtime implementation without duplicating custody?
- What default rolling budget and no-useful-progress window should the first bounded cohort use? These are rollout policy, not agent-definition schema.
