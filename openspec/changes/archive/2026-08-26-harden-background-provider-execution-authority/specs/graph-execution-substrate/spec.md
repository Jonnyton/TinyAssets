## MODIFIED Requirements

### Requirement: Interrupted runs resume from checkpoint under owner, status, checkpoint, and version guards
`resume_run` SHALL resume a run only from its `SqliteSaver` checkpoint and only when the four canonical guards pass: the caller `actor` owns the run (else `auth_failed`), the run is `interrupted` (a run already `resumed` is idempotently returned; any other status raises `not_interrupted`), a checkpoint exists for the run's `thread_id` (else `no_checkpoint`), and the exact branch version the run used still resolves (else `branch_version_mismatch`). Under the effective provider-authority V2 gate, provider-capable resume adds a fifth authority protocol. Before receipt issuance, the runtime SHALL conditionally claim one durable resume-attempt idempotency record against the expected `interrupted` status. Only the winning attempt may idempotently issue a receipt from the current server-owned run binding; a losing concurrent caller SHALL attach to that same attempt and return its eventual outcome or exact authority hold without issuing or submitting again. The public run remains `interrupted` until the winning attempt links the receipt and conditionally commits `resumed`. `resume_run` SHALL query current ledger truth for the exact work item: an active ledger fence raises `ResumeError` reason `provider_authority_fenced`, while the flat error sentinel alone is diagnostic and cannot block after the ledger fence resolves. Fence resolution SHALL clear or replace the sentinel with the conclusive diagnostic projection. A crash SHALL resume or revoke the exact attempt and SHALL NOT mint a second receipt. Queue/run identity or stored actor strings grant no provider authority. For every V2, dark, provider-capable, and non-provider-capable resume path, the run SHALL be marked `resumed` before background re-invocation with `None` inputs (LangGraph's resume signal).

Under the effective provider-authority V2 gate, the lazy first-use recovery coordinator and its `recover_in_flight_runs` call SHALL sweep a provider-capable `queued` or `running` row to `interrupted` only after authority reconciliation proves no reservation exists or every reservation is durably conclusive as `cancelled_before_launch`, `succeeded`, or `failed`; succeeded/failed slots and budgets remain consumed while cancelled-before-launch authority is released. Recovery SHALL prove the old process owner dead or atomically invalidate and advance its execution-claim generation before cancellation or sweep. A dead/invalidated-owner `reserved` reservation SHALL first be atomically cancelled before launch. An unclosed `launch_started`, `indeterminate`, or unreadable reservation SHALL fence its receipt and update the public run to `interrupted` with the stable `provider_authority_fenced` sentinel in the existing flat diagnostic error text, so no run is falsely reported in flight after a restart while remaining non-runnable. The shipped process-global boolean SHALL become a synchronized per-universe recovery state machine: each universe becomes done only after its applicable reconciliation and sweep succeed; an effective-V2 universe failure remains retryable and fails closed only provider-capable run operations for that universe; dark/unlisted universes complete the shipped sweep and stay live independently unless a row already has an authority-ledger record, which remains subject to reconciliation and fencing regardless of gate state. As-built limitations: the `recover_in_flight_runs` docstring still incorrectly says both that `interrupted` is terminal and that mid-run resume via checkpoint is unavailable, and dark-mode `resume_run` retains the shipped non-CAS read/write race that can submit two concurrent resumes.

#### Scenario: a non-owner cannot resume
- **WHEN** an actor who does not own the run calls `resume_run`
- **THEN** `ResumeError` with reason `auth_failed` is raised and no resume occurs

#### Scenario: only interrupted runs resume
- **WHEN** `resume_run` is called on a run whose status is not `interrupted` and not `resumed`
- **THEN** `ResumeError` with reason `not_interrupted` is raised carrying the current status

#### Scenario: a second resume is idempotent
- **WHEN** `resume_run` is called on a run already marked `resumed`
- **THEN** it returns the same run outcome without launching a second resume

#### Scenario: every resume commits status before invocation
- **WHEN** any dark, V2, provider-capable, or non-provider-capable resume passes its applicable guards
- **THEN** the run is marked `resumed` before background re-invocation with `None` inputs

#### Scenario: concurrent resume callers share one attempt
- **WHEN** two callers concurrently resume the same provider-capable `interrupted` run under V2
- **THEN** exactly one conditional resume-attempt claim succeeds
- **AND** only that attempt may idempotently issue and link one background receipt
- **AND** the loser follows the same attempt and returns its eventual outcome or exact authority hold without a second submission

#### Scenario: provider authority failure preserves resumability
- **WHEN** the winning resume attempt cannot issue or link a valid background provider receipt
- **THEN** no provider-capable invocation starts
- **AND** reconciliation revokes or safely retries that exact idempotent attempt while the public run remains `interrupted`

#### Scenario: first-use recovery interrupts work with conclusive authority
- **WHEN** `_ensure_runs_recovery` first invokes `recover_in_flight_runs` under V2 for provider-capable rows whose authority records have no reservation or only reservations durably `cancelled_before_launch`, `succeeded`, or `failed`
- **THEN** those rows are updated to `interrupted` with a restart message and the count is returned
- **AND** succeeded/failed reservation budgets remain consumed while cancelled-before-launch authority is released

#### Scenario: first-use recovery cancels a dead-owner reservation
- **WHEN** first-use recovery proves the owner dead or atomically invalidates its claim generation and finds a durable `reserved` reservation
- **THEN** it atomically transitions the reservation to `cancelled_before_launch`, releases its full authority, and then performs the ordinary interrupted sweep

#### Scenario: unprovable run owner is invalidated before sweep
- **WHEN** first-use recovery cannot prove the old run worker dead
- **THEN** the authority store atomically advances the old execution-claim generation before cancellation or sweep
- **AND** every reservation attempt from that stale process fails generation validation

#### Scenario: first-use recovery fences ambiguous provider work
- **WHEN** first-use recovery finds a provider-capable run with an unclosed `launch_started`, `indeterminate`, or unreadable reservation
- **THEN** the receipt becomes `fenced_indeterminate` and the public run becomes `interrupted` with diagnostic error reason `provider_authority_fenced`
- **AND** it remains non-runnable and `resume_run` raises that exact reason until authoritative reconciliation resolves the fence

#### Scenario: resolved fence updates the diagnostic projection
- **WHEN** ledger reconciliation makes every prior reservation conclusive and clears the work-item fence
- **THEN** the run remains or becomes `interrupted` with the fence sentinel cleared or replaced by a conclusive diagnostic
- **AND** `resume_run` consults the ledger and may claim its single attempt instead of being blocked by stale error text

#### Scenario: failed first-use reconciliation is isolated and retryable
- **WHEN** authority reconciliation or the run sweep raises for one effective-V2 universe
- **THEN** the coordinator does not mark that universe done and a later use retries it
- **AND** provider-capable run operations fail closed only for that universe while dark/unlisted universes complete their shipped sweep and remain live

#### Scenario: non-provider runs retain the first-use sweep under V2
- **WHEN** first-use recovery under V2 finds a non-provider-capable row left `queued` or `running`
- **THEN** the row is updated to `interrupted` with the shipped restart message and counted

#### Scenario: dark mode retains the shipped first-use sweep
- **WHEN** provider-authority V2 is dark and `recover_in_flight_runs` finds rows with no authority-ledger record left `queued` or `running` by a crash
- **THEN** those rows are updated to `interrupted` with the shipped restart message and the count is returned
- **AND** any existing authority-ledger record is reconciled and fenced regardless of gate state

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
- **WHEN** the effective provider-authority V2 gate is dark and graph work has no authority-ledger record
- **THEN** direct, task, thread, and process graph bridges retain shipped behavior without a new receipt hold
- **AND** any existing authority-ledger record remains subject to its carrier, reconciliation, and fence

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
- **WHEN** the effective provider-authority V2 gate is dark and graph work has no authority-ledger record
- **THEN** child, retry, fallback, retrieval, reflexion, ingestion, evaluation, and router paths retain shipped behavior without new receipt-derived ceilings
- **AND** any existing authority-ledger record remains subject to its lineage, budget, and fence
