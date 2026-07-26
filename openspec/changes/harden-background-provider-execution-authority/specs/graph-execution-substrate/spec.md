## MODIFIED Requirements

### Requirement: Interrupted runs resume from checkpoint under owner, status, checkpoint, and version guards
`resume_run` SHALL resume a run only from its `SqliteSaver` checkpoint and only when five guards pass: the caller `actor` owns the run (else `auth_failed`), the run is `interrupted` (a run already `resumed` is idempotently returned; any other status raises `not_interrupted`), a checkpoint exists for the run's `thread_id` (else `no_checkpoint`), the exact branch version the run used still resolves (else `branch_version_mismatch`), and provider-capable resume work obtains a fresh background receipt from the current server-owned run binding (else it remains interrupted with an explicit authority hold). The background receipt SHALL be obtained before the run is marked `resumed`; queue/run identity or stored actor strings grant no provider authority. On resume the run SHALL be marked `resumed` before background re-invocation with `None` inputs (LangGraph's resume signal). Under the effective provider-authority V2 gate, startup `recover_in_flight_runs` SHALL sweep a `queued` or `running` row to `interrupted` only after authority reconciliation proves no reservation exists or only reservations durably `cancelled_before_launch`; a dead-owner `reserved`, possibly launched, or unreadable reservation SHALL preserve the row as a non-runnable authority hold and fence its receipt. While V2 is dark, startup retains the shipped unconditional sweep. As-built limitation: the `recover_in_flight_runs` docstring still states that `interrupted` is terminal and that mid-run resume via checkpoint is "not available today" — that docstring is stale, because `resume_run` implements exactly that checkpoint-based resume.

#### Scenario: a non-owner cannot resume
- **WHEN** an actor who does not own the run calls `resume_run`
- **THEN** `ResumeError` with reason `auth_failed` is raised and no resume occurs

#### Scenario: only interrupted runs resume
- **WHEN** `resume_run` is called on a run whose status is not `interrupted` and not `resumed`
- **THEN** `ResumeError` with reason `not_interrupted` is raised carrying the current status

#### Scenario: a second resume is idempotent
- **WHEN** `resume_run` is called on a run already marked `resumed`
- **THEN** it returns the same run outcome without launching a second resume

#### Scenario: provider-capable resume requires a fresh receipt
- **WHEN** all four canonical resume guards pass but the current run binding cannot issue a valid background provider receipt
- **THEN** the run remains `interrupted` with an explicit authority hold
- **AND** no provider-capable background invocation starts

#### Scenario: startup interrupts only work with proven launch absence
- **WHEN** `recover_in_flight_runs` runs under V2 with `queued` or `running` rows whose authority records have no reservation or only reservations durably `cancelled_before_launch`
- **THEN** those rows are updated to `interrupted` with a restart message and the count is returned

#### Scenario: startup fences ambiguous in-flight provider work
- **WHEN** startup finds a provider-capable run with a dead-owner `reserved`, possibly launched, or unreadable reservation
- **THEN** the run remains non-runnable and its receipt becomes `fenced_indeterminate`
- **AND** it is not automatically resumed or swept to ordinary `interrupted`

#### Scenario: dark mode retains the shipped startup sweep
- **WHEN** provider-authority V2 is dark and `recover_in_flight_runs` finds rows left `queued` or `running` by a crash
- **THEN** those rows are updated to `interrupted` with the shipped restart message and the count is returned

## ADDED Requirements

### Requirement: Provider-capable graph execution propagates the exact receipt
The graph execution substrate SHALL propagate the exact non-serializable provider-work receipt through provider-capable nodes and every task or thread bridge, and SHALL use an atomic opaque handoff claim for every process bridge.

#### Scenario: Threaded provider node retains one claim
- **WHEN** a compiled provider-capable node executes in a thread pool
- **THEN** the node receives the same claimed receipt object and cannot reconstruct authority from graph state, config, actor identity, or queue metadata

#### Scenario: Process worker claims opaque handoff
- **WHEN** graph work crosses a process boundary
- **THEN** the intended worker atomically claims the one-use opaque handoff from the authority store before it can invoke the provider bridge

#### Scenario: Receipt missing at injected provider bridge
- **WHEN** a production `provider_call` or equivalent injected callable is invoked without the exact permitted receipt
- **THEN** the bridge holds before provider, credential, transport, auth-health, or quota authority

### Requirement: Graph descendants preserve authority lineage and ceilings
The graph execution substrate SHALL derive child, retry, fallback, retrieval, reflexion, ingestion, evaluation, and router work only within the receipt's current lineage, operation, provider-role, depth, lifetime, cancellation, and budget ceilings.

#### Scenario: Child work narrows authority
- **WHEN** a node creates provider-capable child work
- **THEN** the child obtains a fresh receipt bound to its exact child lineage with no wider operations, roles, depth, lifetime, invocation, token, or cost ceilings

#### Scenario: Cancellation reaches pending graph calls
- **WHEN** receipt, run, branch, or universe cancellation becomes effective
- **THEN** pending graph nodes cannot reserve new provider invocations
- **AND** already launched reservations remain consumed and reconcile to an explicit terminal or indeterminate state

#### Scenario: Fallback requires another reservation
- **WHEN** a router or node attempts a second provider after a launched call fails
- **THEN** it must atomically reserve another permitted invocation and cannot reuse the launched reservation

### Requirement: Every provider-capable graph call site has one authority classification
The graph execution substrate SHALL maintain a mechanically checked inventory in which every production provider-capable caller, injected callable, and packaged runtime mirror has exactly one authority classification.

#### Scenario: Call-site inventory is complete
- **WHEN** CI scans universe intelligence, compiled nodes and routers, the async judge-ensemble `gather` and direct `provider.complete(...)` members, run and child bridges, editorial and ingestion paths, retrieval and RAPTOR paths, reflexion, entity extraction, community evaluation, and the mirrored Claude plugin
- **THEN** each provider-capable call site is classified as live-request authority, host authority, background receipt authority, maintenance authority, accepted-market remote dispatch, or proven non-provider or mock-only

#### Scenario: Successor-owned classifications remain empty
- **WHEN** `activate-requester-host-engines` or `activate-connector-requester-authority` has not landed its authority owner
- **THEN** attested host-request and accepted-market remote classifications respectively contain no production call site
- **AND** any attempted use fails the call-site closure gate

#### Scenario: Unclassified provider call fails the gate
- **WHEN** a new or changed production call site can reach provider execution without one exact classification and carrier path
- **THEN** the call-site closure check fails before the change can land

#### Scenario: Mirrored runtime remains equivalent
- **WHEN** authority-carrier behavior changes in the canonical runtime
- **THEN** the packaged Claude-plugin mirror exposes the same background receipt enforcement or is proven not to contain the affected provider path
