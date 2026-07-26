## MODIFIED Requirements

### Requirement: Interrupted runs resume from checkpoint under owner, status, checkpoint, and version guards
`resume_run` SHALL resume a run only from its `SqliteSaver` checkpoint and only when the four canonical guards pass: the caller `actor` owns the run (else `auth_failed`), the run is `interrupted` (a run already `resumed` is idempotently returned; any other status raises `not_interrupted`), a checkpoint exists for the run's `thread_id` (else `no_checkpoint`), and the exact branch version the run used still resolves (else `branch_version_mismatch`). The header remains unchanged for delta identity; under the effective provider-authority V2 gate, provider-capable resume adds a fifth authority protocol. Before receipt issuance, the runtime SHALL conditionally claim one durable resume-attempt idempotency record against the expected `interrupted` status. Only the winning attempt may idempotently issue a receipt from the current server-owned run binding; the public run remains `interrupted` until that same attempt links the receipt and conditionally commits `resumed`. A crash SHALL resume or revoke the exact attempt and SHALL NOT mint a second receipt. Queue/run identity or stored actor strings grant no provider authority. Once committed, background re-invocation uses `None` inputs (LangGraph's resume signal).

Under the effective provider-authority V2 gate, the lazy first-use `_ensure_runs_recovery` guard and its `recover_in_flight_runs` call SHALL sweep a provider-capable `queued` or `running` row to `interrupted` only after authority reconciliation proves no reservation exists or every reservation is durably conclusive as `cancelled_before_launch`, `succeeded`, or `failed`; consumed terminal slots and budgets remain consumed. A dead-owner `reserved`, unclosed `launch_started`, `indeterminate`, or unreadable reservation SHALL preserve the row as a non-runnable authority hold and fence its receipt. Non-provider-capable rows retain the shipped first-use sweep under V2. While V2 is dark, first-use recovery retains the shipped unconditional sweep. As-built limitation: the `recover_in_flight_runs` docstring still states that `interrupted` is terminal and that mid-run resume via checkpoint is "not available today" — that docstring is stale, because `resume_run` implements exactly that checkpoint-based resume.

#### Scenario: a non-owner cannot resume
- **WHEN** an actor who does not own the run calls `resume_run`
- **THEN** `ResumeError` with reason `auth_failed` is raised and no resume occurs

#### Scenario: only interrupted runs resume
- **WHEN** `resume_run` is called on a run whose status is not `interrupted` and not `resumed`
- **THEN** `ResumeError` with reason `not_interrupted` is raised carrying the current status

#### Scenario: a second resume is idempotent
- **WHEN** `resume_run` is called on a run already marked `resumed`
- **THEN** it returns the same run outcome without launching a second resume

#### Scenario: concurrent resume callers share one attempt
- **WHEN** two callers concurrently resume the same provider-capable `interrupted` run under V2
- **THEN** exactly one conditional resume-attempt claim succeeds
- **AND** only that attempt may idempotently issue and link one background receipt

#### Scenario: provider authority failure preserves resumability
- **WHEN** the winning resume attempt cannot issue or link a valid background provider receipt
- **THEN** no provider-capable invocation starts
- **AND** reconciliation revokes or safely retries that exact idempotent attempt while the public run remains `interrupted`

#### Scenario: first-use recovery interrupts work with conclusive authority
- **WHEN** `_ensure_runs_recovery` first invokes `recover_in_flight_runs` under V2 for provider-capable rows whose authority records have no reservation or only reservations durably `cancelled_before_launch`, `succeeded`, or `failed`
- **THEN** those rows are updated to `interrupted` with a restart message and the count is returned
- **AND** consumed terminal reservation budgets remain consumed

#### Scenario: first-use recovery fences ambiguous provider work
- **WHEN** first-use recovery finds a provider-capable run with a dead-owner `reserved`, unclosed `launch_started`, `indeterminate`, or unreadable reservation
- **THEN** the run remains non-runnable and its receipt becomes `fenced_indeterminate`
- **AND** it is not automatically resumed or swept to ordinary `interrupted`

#### Scenario: non-provider runs retain the first-use sweep under V2
- **WHEN** first-use recovery under V2 finds a non-provider-capable row left `queued` or `running`
- **THEN** the row is updated to `interrupted` with the shipped restart message and counted

#### Scenario: dark mode retains the shipped first-use sweep
- **WHEN** provider-authority V2 is dark and `recover_in_flight_runs` finds rows left `queued` or `running` by a crash
- **THEN** those rows are updated to `interrupted` with the shipped restart message and the count is returned

## ADDED Requirements

### Requirement: Provider-capable graph execution propagates the exact receipt
The graph execution substrate SHALL propagate the exact non-serializable provider-work receipt through provider-capable nodes and every task or thread bridge, and SHALL use an atomic opaque handoff claim for every process bridge. This requirement is subject to the effective provider-authority V2 gate; while dark it SHALL preserve shipped graph execution without a new receipt precondition.

#### Scenario: Threaded provider node retains one claim
- **WHEN** a compiled provider-capable node executes in a thread pool
- **THEN** the node receives the same claimed receipt object and cannot reconstruct authority from graph state, config, actor identity, or queue metadata

#### Scenario: Process worker claims opaque handoff
- **WHEN** graph work crosses a process boundary
- **THEN** the intended worker atomically claims the one-use opaque handoff from the authority store before it can invoke the provider bridge

#### Scenario: Receipt missing at injected provider bridge
- **WHEN** a production `provider_call` or equivalent injected callable is invoked without the exact permitted receipt
- **THEN** the bridge holds before provider, credential, transport, auth-health, or quota authority

#### Scenario: Dark mode preserves graph bridges
- **WHEN** the effective provider-authority V2 gate is dark
- **THEN** direct, task, thread, and process graph bridges retain shipped behavior without a new receipt hold

### Requirement: Graph descendants preserve authority lineage and ceilings
The graph execution substrate SHALL derive child, retry, fallback, retrieval, reflexion, ingestion, evaluation, and router work only within the receipt's current lineage, operation, provider-role, depth, lifetime, cancellation, and budget ceilings. This requirement is subject to the effective provider-authority V2 gate; while dark it SHALL preserve shipped descendant, retry, fallback, and router behavior.

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

#### Scenario: Dark mode preserves graph descendants
- **WHEN** the effective provider-authority V2 gate is dark
- **THEN** child, retry, fallback, retrieval, reflexion, ingestion, evaluation, and router paths retain shipped behavior without new receipt-derived ceilings
