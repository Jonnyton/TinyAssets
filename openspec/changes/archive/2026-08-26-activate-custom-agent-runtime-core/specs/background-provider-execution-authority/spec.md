## MODIFIED Requirements

### Requirement: Durable provider work bindings are non-bearer authorization intent
The system SHALL represent authorization for later provider-capable work as a server-owned `ProviderWorkBinding` whose identifier and serialized fields do not themselves authorize provider, credential, outbound-proxy, auth-health, or quota access. For the dark agent runtime, current authenticated owner request middleware SHALL create one inert single-message binding draft for the registered agent-invocation operation before request authority ends; the canonical invocation-admission service SHALL resolve the exact binding/manifest/input target and atomically consume that draft into one `ProviderWorkBinding` linked to one server-authored `AgentInvocationCommand` and one append-only invocation root. Neither the command nor invocation is an independent binding issuance root.

#### Scenario: Queue identity cannot authorize provider work
- **WHEN** a caller presents a run ID, branch-task ID, queue claim, lease, actor string, schedule ID, subscription ID, command ID, invocation ID, receipt ID, or serialized record fields without a current server-issued authority receipt
- **THEN** the system holds before every provider authority sink

#### Scenario: Deferred request records agent intent while request authority is live
- **WHEN** an authenticated owner request authorizes the registered dark agent-invocation operation that will execute after request middleware returns
- **THEN** TinyAssets middleware creates an inert single-message binding draft for the authenticated principal and registered operation after reading the exact current request but before awaiting admission or dispatch augmentation
- **AND** invocation admission resolves the exact agent binding, manifest subject, activation fence, typed-input digest, and budgets and atomically commits one linked provider-work binding, command, and invocation while consuming that draft
- **AND** just-in-time receipt issuance later authorizes the resolved target against current server state without any inherited or snapshotted request bearer

#### Scenario: Exact admission replay uses the existing binding
- **WHEN** the authenticated owner repeats identical canonical admission with the same idempotency key, or recovery observes the already committed aggregate after request authority ended
- **THEN** the service returns or reconciles the same provider-work binding, command, and invocation identities
- **AND** it does not create a new draft, binding, receipt, reservation, or spend

#### Scenario: Deferred work misses the recording boundary
- **WHEN** agent work becomes deferred before the current-message middleware can create and atomically consume the authorized binding draft
- **THEN** the work has no provider issuance root and creates no command, invocation, or provider-work binding
- **AND** stored command-shaped fields, invocation rows, queue possession, or caller data cannot reconstruct one

#### Scenario: Lower-level command cannot create a binding
- **WHEN** a private helper, generic dispatcher, queue worker, or caller-built command/invocation attempts to create or widen a provider-work binding
- **THEN** binding creation fails closed because no live authenticated draft is consumed by the canonical admission service

#### Scenario: Synthetic schedule actor cannot create a binding
- **WHEN** provider-authority V2 applies and a schedule or subscription supplies `owner_actor`, caller kwargs, or another synthetic principal without the server-owned record from `harden-background-branch-execution-authority`
- **THEN** the V2 provider-work binding is not created and the provider-capable execution holds without treating the synthetic principal as authority

#### Scenario: Dark schedules retain shipped behavior
- **WHEN** provider-authority V2 is dark for a schedule or subscription
- **THEN** this binding requirement does not deactivate or otherwise change the shipped trigger

### Requirement: Provider work receipts form a closed bounded union
The system SHALL mint a short-lived `ProviderWorkAuthorityReceipt` for one logical work attempt as exactly one of `universe_work` or `maintainer_maintenance`, with server-owned lifetime, operation, provider-role, invocation, token, and cost ceilings. Every `universe_work` receipt MUST carry exactly one server-classified lineage kind plus one typed immutable execution-subject kind/reference/digest. Existing Branch work MUST retain its exact branch/run/background-attempt lineage and a `branch_version` subject. Agent runtime work MUST use `work_item_kind=agent_invocation`, its exact server-issued invocation command and invocation identity, and an `agent_runtime_manifest` subject without fabricating Branch or background-attempt lineage.

#### Scenario: Universe work receipt is fully bound
- **WHEN** the system mints a `universe_work` receipt
- **THEN** it binds the receipt to the current binding and generation, authorized principal and actor or daemon, universe, exact server-classified lineage and execution subject, assignment generation and digest, provider binding digest, allowed operation and provider-role set, ceilings, issuer, receipt identity, and revocation generation
- **AND** Branch work retains its branch, run, operation, and applicable background-attempt fields while agent work retains its invocation command and invocation fields

#### Scenario: Unknown receipt variant or lineage is rejected
- **WHEN** a provider-capable path receives a receipt whose variant, work-item kind, lineage shape, or execution-subject kind is absent from the closed server-owned union
- **THEN** the system rejects it before any authority sink

#### Scenario: Receipt scope cannot widen
- **WHEN** work retries, falls back, or creates child work
- **THEN** each resulting attempt uses a fresh receipt or reservation whose operation, provider roles, lineage, execution subject, depth, lifetime, and budgets are no broader than its authorized parent and current binding

#### Scenario: Concurrent children conserve parent authority
- **WHEN** one parent creates one or more provider-capable child bindings
- **THEN** the authority store atomically transfers invocation, token, and cost ceilings from the parent's remaining authority before each child becomes claimable
- **AND** concurrent children cannot receive more aggregate authority than the parent's prior remaining ceiling

#### Scenario: Unused child authority returns exactly once
- **WHEN** a child closes conclusively with proven unused authority
- **THEN** the store returns that authority exactly once only if the same parent receipt and generation remain active
- **AND** otherwise the unused authority expires without crediting any parent

### Requirement: Fresh issuance revalidates durable authority
The system SHALL mint each provider-work receipt just in time from a current binding only after atomically revalidating binding state and digest, principal and actor authority, server-classified work lineage, physical work location, exact execution subject, provider assignment, revocation state, remaining budget, and eligible runtime.

#### Scenario: Stale assignment blocks issuance
- **WHEN** the current assignment generation, ceiling, provider binding, or assignment digest differs from the binding
- **THEN** receipt issuance fails closed
- **AND** no stale receipt is reconstructed or refreshed

#### Scenario: Cancelled, moved, or rebound work blocks issuance
- **WHEN** the universe, Branch/run/background attempt, agent invocation command/invocation, operation, or execution subject is cancelled, unauthorized, stale, or physically inconsistent with the claimed work
- **THEN** receipt issuance fails before provider authority becomes available

#### Scenario: Binding revocation blocks future attempts
- **WHEN** a binding is revoked, expired, or superseded
- **THEN** the system mints no new receipts from it even if an older task, lease, command, or process later resumes

#### Scenario: Existing fence blocks fresh issuance for the work item
- **WHEN** any prior receipt for the exact physical work-item key is `fenced_indeterminate` or contains a `reserved`, unclosed `launch_started`, or `indeterminate` reservation
- **THEN** the authority store issues no fresh receipt for that work item regardless of binding state, queue/run/invocation status, projected error text, or current rollout gate
- **AND** issuance becomes eligible only after ledger reconciliation makes every prior reservation conclusive

## ADDED Requirements

### Requirement: Agent invocation is a closed provider-authority classification
The background provider execution authority owner SHALL add `agent_invocation` to its mechanically checked whole-runtime inventory only for the canonical agent-invocation admission and execution path. Enqueue, admission, issuance, recovery, canonical runtime, and packaged mirrors MUST agree on that server-owned classification, and missing or unknown classification MUST fail closed before provider authority.

#### Scenario: Agent helper bypasses the admitted carrier
- **WHEN** a private helper, generic dispatcher, queue row, or caller-built invocation attempts provider execution without the exact server-issued invocation command, invocation identity, and `agent_runtime_manifest` subject
- **THEN** the call-site closure gate or runtime authority gate fails before provider launch

#### Scenario: Existing Branch classification is unchanged
- **WHEN** ordinary Branch provider work is classified, issued, claimed, launched, or reconciled
- **THEN** it retains its current branch/run/background-attempt lineage and `branch_version` subject checks without accepting agent invocation fields as substitutes
