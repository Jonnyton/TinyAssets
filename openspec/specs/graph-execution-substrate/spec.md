# Graph Execution Substrate

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

The domain-agnostic engine that turns a user-authored branch into a runnable, checkpointed, resumable LangGraph execution: BranchDefinition/NodeDefinition model, graph compiler (reducers, conditional edges), runs engine with failure taxonomy and resume.
## Requirements
### Requirement: Branch and node definitions are validated dataclasses with lossless JSON round-trip
Community-designed graph topologies SHALL be represented by two `@dataclass` types in `tinyassets.branches` — `NodeDefinition` (one node) and `BranchDefinition` (a full topology of nodes, edges, conditional edges, entry point, and state schema) — each serializable to and from a plain JSON-compatible dict via `to_dict` / `from_dict` (BranchDefinition also exposes `to_json`). A BranchDefinition SHALL store its graph as a single embedded JSON blob so fork, clone, and export stay atomic (one row equals one complete topology). NodeDefinition construction SHALL fail loudly per Hard Rule #8 when a persisted row supplies a non-list value for `input_keys`, `output_keys`, `tools_allowed`, or `effects`, or a non-string element inside one, rather than silently accepting a bare string that would later be iterated character-by-character.

#### Scenario: a node round-trips through its dict form
- **WHEN** a NodeDefinition is serialized with `to_dict` and reconstructed with `from_dict`
- **THEN** the reconstructed node preserves its declared fields (`input_keys`, `output_keys`, `source_code` or `prompt_template`, dependencies, and execution policy)
- **AND** unknown keys in the input dict are ignored rather than raising

#### Scenario: a malformed key list is rejected at construction
- **WHEN** a NodeDefinition is constructed with `input_keys` set to a bare string instead of a list (for example from a pre-fix write path)
- **THEN** construction raises `NodeDefinitionValidationError` naming the offending field
- **AND** the branch fails to load rather than corrupting sandbox and state handling downstream

#### Scenario: an invalid phase is rejected
- **WHEN** a NodeDefinition is constructed with a `phase` outside the valid phase vocabulary
- **THEN** construction raises `ValueError` listing the acceptable phases

### Requirement: Branch validation is the compile gate
`BranchDefinition.validate()` SHALL return the list of structural errors that make a topology unrunnable — missing name, no nodes, missing or dangling entry point, duplicate node IDs, edge or conditional-edge endpoints that are not defined nodes, graph nodes unreachable from the entry point (orphans), cycles with no path to `END`, duplicate or node-colliding state-field names, and undeclared prompt-template placeholders. `compile_branch` SHALL call `validate()` first and SHALL raise `CompilerError` listing those errors instead of producing a `StateGraph` when any are present, so an invalid branch can never compile.

#### Scenario: an orphan node fails validation
- **WHEN** a branch contains a graph node with no path from the entry point (or `START`)
- **THEN** `validate()` returns an error naming the unreachable node
- **AND** `compile_branch` raises `CompilerError` rather than returning a compiled graph

#### Scenario: a cycle with no exit fails validation
- **WHEN** a branch contains a cycle whose nodes cannot reach `END`
- **THEN** `validate()` returns an error naming the nodes in the exitless cycle

#### Scenario: a valid topology compiles
- **WHEN** a branch with a reachable entry point, resolvable edges, and a terminating path is compiled
- **THEN** `validate()` returns an empty list and `compile_branch` returns a `CompiledBranch` carrying the uncompiled `StateGraph` and the synthesized state TypedDict

### Requirement: State fields accumulate per their declared reducer
The compiler SHALL synthesize the run's state type as a `TypedDict` (Hard Rule #5) whose per-field merge behavior follows each `state_schema` field's declared `reducer`: `append` maps to `Annotated[list, operator.add]`, `merge` maps to `Annotated[dict, <shallow merger>]` under a single-writer contract, and any other value (including unset) is last-write-wins overwrite. For every merge-reduced field, compilation SHALL reject a graph with more than one node that declares the field through `output_keys` or `output_mapping`, and node execution SHALL fail closed if a node writes that field without declaring it. With exactly one declared writer, the merger SHALL remain a shallow, right-biased `dict.update`: right-hand top-level keys overwrite matching left-hand keys, left-only keys remain, and nested values are replaced wholesale rather than deep-merged.

#### Scenario: an append field concatenates contributions
- **WHEN** two nodes each write a list to a state field declared `reducer="append"`
- **THEN** the field's value is the concatenation of both contributions via `operator.add`

#### Scenario: an unreduced field is overwritten
- **WHEN** a field has no recognized reducer and two nodes write it
- **THEN** the last write wins and the earlier value is discarded

#### Scenario: multiple declared merge writers fail compilation
- **WHEN** more than one graph node declares the same `reducer="merge"` field in `output_keys` or `output_mapping`
- **THEN** `compile_branch` raises `CompilerError` because a merge-reduced field requires a single writer

#### Scenario: an undeclared merge write fails closed at runtime
- **WHEN** a compiled node returns a value for a `reducer="merge"` field absent from that node's `output_keys` and `output_mapping`
- **THEN** node execution raises `CompilerError` instead of applying the undeclared write

#### Scenario: one declared merge writer shallow-merges right-biased
- **WHEN** the sole declared writer updates a merge-reduced dict containing overlapping top-level keys, left-only keys, and a nested value
- **THEN** the resulting dict preserves left-only keys and uses the writer's values for overlapping keys
- **AND** the writer's nested value replaces the prior nested value wholesale rather than being deep-merged

### Requirement: Conditional edges route by path_map label, not target node id
A conditional-edge router built by the compiler SHALL return a key into LangGraph's `path_map` (a declared condition label), not a target node id — matching the `add_conditional_edges(source, router, path_map=conditions)` contract where LangGraph resolves the target from the returned label. The router SHALL read the source node's first `output_key` from state and return that value verbatim when it is a declared label, and SHALL fall back to the first declared label (or `END` when none) when the output key is absent, empty, or not a valid label, so the graph advances rather than raising `KeyError`. This is the as-built fix for the BUG-019/021/022 routing failure where returning `conditions[value]` (a target) was always looked up as a path_map key and always raised.

#### Scenario: a matching label routes to its branch
- **WHEN** the source node writes an output value equal to a declared condition label
- **THEN** the router returns that label and LangGraph advances to the mapped target node

#### Scenario: a missing or unknown output falls back to the first label
- **WHEN** the source node's output key is absent, non-string, or not among the declared labels
- **THEN** the router returns the first declared label so the graph advances instead of hanging or `KeyError`-ing

### Requirement: source_code nodes execute in-process behind a fail-closed approval gate
A `source_code` node SHALL execute only after `_validate_source_code` passes a fail-closed gate: the node must be `approved`, must carry a non-empty `approved_source_hash` equal to `sha256` of its effective source, and must contain none of the disallowed dangerous patterns; an empty or mismatched hash SHALL raise `UnapprovedNodeError` (an empty hash is treated as forged or carried-from-elsewhere, never as trusted). Approved source SHALL then run in-process via `exec` into a single namespace and expose a `run(state)` callable. As-built limitation (security-load-bearing): this execution path has no OS-level isolation — it runs with full `__builtins__` in the daemon process, protected only by the approval-hash gate plus a substring pattern scan. A stronger subprocess sandbox (`NodeSandbox` in `tinyassets.node_sandbox`, which filters state to declared keys, enforces an import allowlist, and kills on timeout) exists but is NOT wired into `compile_branch`, and it hardcodes a POSIX `HOME=/tmp` in the child environment, so it is not portable to Windows hosts as written.

#### Scenario: an unapproved or hash-mismatched node is refused
- **WHEN** a source_code node is run without `approved=True`, or with a missing/stale/forged `approved_source_hash`
- **THEN** `UnapprovedNodeError` is raised and the node does not execute

#### Scenario: a disallowed pattern is refused
- **WHEN** an approved source_code node's body contains a disallowed dangerous pattern
- **THEN** `CompilerError` is raised before execution

#### Scenario: the standalone sandbox isolates but is not the compile path (as-built limitation)
- **WHEN** `NodeSandbox.execute` runs a node in its own subprocess
- **THEN** state is filtered to the node's declared input keys, non-allowlisted imports fail, and an infinite loop is killed at the timeout
- **AND** this sandbox is not invoked by `compile_branch`, whose source_code nodes run in-process instead

### Requirement: Runs are checkpointed LangGraph executions with a fixed terminal status set
The runs engine (`tinyassets.runs`) SHALL execute a compiled branch as a checkpointed LangGraph run using a synchronous `SqliteSaver` (never `AsyncSqliteSaver`, per Hard Rule #1) persisted at `.langgraph_runs.db`, with the LangGraph `thread_id` equal to the `run_id`. A run's lifecycle status SHALL be one of `queued`, `running`, `completed`, `failed`, `cancelled`, `interrupted`, or `resumed`. The graph SHALL be invoked with a recursion ceiling defaulting to `DEFAULT_RECURSION_LIMIT = 100` (raised from LangGraph's stock 25 to accommodate multi-iteration gate loops), overridable per call within validated bounds.

#### Scenario: run state persists to disk under its thread id
- **WHEN** a run executes with a file-backed `SqliteSaver` at `.langgraph_runs.db`
- **THEN** its checkpoint is written keyed by `thread_id == run_id` and survives across checkpointer instances
- **AND** distinct runs (distinct thread ids) do not read each other's checkpoints

#### Scenario: the default recursion limit is 100
- **WHEN** a run is invoked without a recursion override
- **THEN** the applied recursion limit is 100, above LangGraph's stock 25
- **AND** an explicit override outside the accepted min/max range is rejected

### Requirement: Run failures map to a terminal status taxonomy
The executor SHALL translate every terminating condition into a terminal run status with a diagnostic error message rather than leaving a run wedged or crashing the daemon: cancellation (including LangGraph-wrapped cancellation) maps to `cancelled`; a LangGraph interrupt or a child-invocation receipt-timeout maps to `interrupted` (the latter carrying a `child_invocation_receipt_gate` marker so it can be reclaimed); and `GraphRecursionError`, node timeout, empty-LLM-response, and propagated child-run failure each map to `failed` with a reason-specific message. A separate presentation helper (`_classify_failure`) SHALL fold a stored run record into a short failure-class label (for example `cancelled`, `interrupted`, `child_receipt_waiting`, `empty_llm_response`, `timeout`, `provider_exhausted`, `sandbox_unavailable`) for run-history surfaces.

#### Scenario: an empty LLM response terminates the run as failed
- **WHEN** a node's provider returns an empty response that surfaces as an empty-response error
- **THEN** the run status becomes `failed` with a message identifying the empty response and the responsible node

#### Scenario: exceeding the recursion limit terminates the run as failed
- **WHEN** a run trips the applied recursion limit
- **THEN** the run status becomes `failed` with a `GraphRecursionError` message naming the applied limit and how to raise it

#### Scenario: a cancelled run reports cancelled, not failed
- **WHEN** a run is cancelled between nodes
- **THEN** the run status becomes `cancelled` with a cancellation message, distinct from a crash

### Requirement: Interrupted runs resume from checkpoint under owner, status, checkpoint, and version guards
`resume_run` SHALL resume a run only from its `SqliteSaver` checkpoint and only when four guards pass: the caller `actor` owns the run (else `auth_failed`), the run is `interrupted` (a run already `resumed` is idempotently returned; any other status raises `not_interrupted`), a checkpoint exists for the run's `thread_id` (else `no_checkpoint`), and the exact branch version the run used still resolves (else `branch_version_mismatch`). On resume the run SHALL be marked `resumed` before background re-invocation with `None` inputs (LangGraph's resume signal). At server startup `recover_in_flight_runs` SHALL sweep any `queued` or `running` rows to `interrupted` so no run is falsely reported in flight after a restart. As-built limitation: the `recover_in_flight_runs` docstring still states that `interrupted` is terminal and that mid-run resume via checkpoint is "not available today" — that docstring is stale, because `resume_run` implements exactly that checkpoint-based resume.

#### Scenario: a non-owner cannot resume
- **WHEN** an actor who does not own the run calls `resume_run`
- **THEN** `ResumeError` with reason `auth_failed` is raised and no resume occurs

#### Scenario: only interrupted runs resume
- **WHEN** `resume_run` is called on a run whose status is not `interrupted` and not `resumed`
- **THEN** `ResumeError` with reason `not_interrupted` is raised carrying the current status

#### Scenario: a second resume is idempotent
- **WHEN** `resume_run` is called on a run already marked `resumed`
- **THEN** it returns the same run outcome without launching a second resume

#### Scenario: startup sweeps in-flight runs to interrupted
- **WHEN** `recover_in_flight_runs` runs at startup with rows left `queued` or `running` by a crash
- **THEN** those rows are updated to `interrupted` with a restart message and the count is returned

### Requirement: Child-Branch node shapes are validated before execution

Branch validation SHALL require a live `branch_def_id`, frozen
`branch_version_id`, or await `run_id_field` for its corresponding node shape;
it MUST reject unsupported wait modes, mixed prompt/source bodies,
simultaneous live and frozen invocation specs, and live/frozen mapped parent
output keys absent from a non-empty parent state schema. Frozen-version
validation MUST also reject unsupported failure modes. Await output mappings
currently are not checked against the parent schema. Runtime compilation MUST
enforce the configured child-invocation depth cap.

#### Scenario: Mutually exclusive child definitions fail validation

- **WHEN** one node declares both `invoke_branch_spec` and `invoke_branch_version_spec`
- **THEN** Branch validation reports the node as invalid before execution

#### Scenario: Output mapping respects the parent schema

- **WHEN** a live or frozen invocation maps output to a key absent from a non-empty parent state schema
- **THEN** Branch validation rejects the mapping

#### Scenario: Await output mapping is not schema-validated

- **WHEN** an await spec maps output to a key absent from a non-empty parent state schema
- **THEN** current Branch validation does not report that mapping error

#### Scenario: Nested invocation stops at the runtime depth cap

- **WHEN** compilation reaches the configured child-invocation depth ceiling
- **THEN** the compiler raises an invocation-depth error rather than spawning another child

### Requirement: Live child invocation maps state and supports blocking or async execution

A live child-invocation node SHALL resolve the current Branch definition, map
declared parent keys into child input keys, and use an explicit child actor or
otherwise inherit the parent run actor, falling back to `anonymous`. Blocking
mode MUST invoke the child synchronously without a child-poll timeout and map
declared child outputs on success. A non-completed terminal child SHALL apply
`propagate`, `default`, or `retry`; node-local `retry_budget=N` permits up to N
retries after the initial attempt, with zero coerced to the default of one.
The thread-local aggregate counter is reset by synchronous child execution and
therefore does not reliably cap live nested retries beyond the local budget.
Live validation does not reject an unknown failure-mode value, which reaches
runtime and follows the propagate path on child failure. Async mode MUST return
immediately, place the child run ID in the first declared parent output key,
and SHALL NOT apply blocking failure policy.

#### Scenario: Blocking live invocation returns mapped child output

- **WHEN** a live child Branch completes in blocking mode
- **THEN** each declared parent output key receives the corresponding child output value

#### Scenario: Async live invocation returns its run identity

- **WHEN** a live child Branch is started in async mode with an output mapping
- **THEN** the first parent output key receives the child run ID and the parent node does not wait for completion

#### Scenario: Live blocking retry is locally bounded

- **WHEN** a live blocking child repeatedly ends non-completed with `on_child_fail=retry`
- **THEN** the node stops after its local retry budget and propagates, while the thread-local aggregate is not a reliable additional bound for synchronous nested runs

### Requirement: Frozen child invocation binds a version and applies blocking failure policy

A frozen child-invocation node SHALL execute the exact stored
`branch_version_id` snapshot with the same input, actor, depth, and output
mapping semantics as live invocation. Frozen blocking SHALL queue the child and
poll it with a 300-second default timeout rather than invoke synchronously; a
poll timeout MUST follow the parent receipt-wait interruption path before any
failure policy is applied. A non-completed terminal child MUST use `propagate`,
`default`, or `retry` behavior. `retry_budget=N` permits up to N retries after
the initial attempt, with zero coerced to the default of one, and each retry
MUST also consume the thread-local per-parent-run aggregate configured by
`TINYASSETS_MAX_CHILD_RETRIES_TOTAL`; this counter is not process-wide. Frozen
async mode SHALL return the child run ID without applying blocking failure
policy.

#### Scenario: Later live edits do not change a frozen child

- **WHEN** a child is invoked by stored version after its live definition changes
- **THEN** execution reconstructs and runs the frozen version snapshot

#### Scenario: Default policy returns declared fallback outputs

- **WHEN** a blocking child ends non-completed with `on_child_fail=default`
- **THEN** the node returns its declared default outputs through the parent mapping instead of failing the parent

#### Scenario: Retry policy is bounded

- **WHEN** a blocking child continues failing under `on_child_fail=retry`
- **THEN** retries stop at the first exhausted node-local or thread-local parent budget and the failure then propagates

#### Scenario: Frozen blocking timeout precedes failure policy

- **WHEN** a frozen blocking child remains non-terminal for the polling timeout
- **THEN** the parent is interrupted into receipt-waiting rather than applying `on_child_fail`

### Requirement: Await nodes map terminal output but make timeout receipt-recoverable

An await node SHALL read a child run ID from its configured parent-state field,
poll until any terminal child status, and map the stored child output without
interpreting the child terminal status. If the timeout expires while the child
is still non-terminal, the parent run MUST become `interrupted` with structured
`receipt_waiting` output naming the child, timeout, and
`attach_existing_child_run` reclaim action.

#### Scenario: Terminal child output is mapped

- **WHEN** an awaited child reaches any terminal status before timeout
- **THEN** the await node maps the declared fields from its stored output and does not apply blocking invocation failure policy

#### Scenario: Non-terminal timeout preserves a reclaim path

- **WHEN** an awaited child remains non-terminal through the timeout
- **THEN** the parent is interrupted with receipt-wait evidence and the completed child may later be attached rather than rerun

### Requirement: Existing-child attachment is validated, one-shot, and evidenced

The run store SHALL attach only an existing completed child with non-empty
output to a parent already in receipt-waiting state. It MUST validate the
expected, supplied, and actual child Branch identities and any supplied output
digest and reject conflicting prior digests. A successful attachment SHALL
store at most one row for the parent-child pair and update the parent out of
receipt-waiting; a sequential replay, including an identical replay, MUST be
rejected as `parent_not_receipt_waiting`. The same unchanged child MAY attach
to a different receipt-waiting parent, but a changed computed digest MUST be
rejected against its prior attachment.

#### Scenario: Wrong or unfinished child cannot be attached

- **WHEN** the supplied child has the wrong Branch identity, is non-completed, or has no output
- **THEN** attachment fails without updating the parent receipt state

#### Scenario: Matching completed child attaches with stable evidence

- **WHEN** a matching completed child with non-empty output is attached to a receipt-waiting parent
- **THEN** the parent records the child output, digest, receipt, and stable evidence handle

#### Scenario: Sequential replay is rejected

- **WHEN** the same parent-child pair is attached again with the same computed digest
- **THEN** attachment is rejected because the successful first call moved the parent out of receipt-waiting

#### Scenario: Unchanged child can evidence another waiting parent

- **WHEN** the same completed child is attached to a different receipt-waiting parent with the same computed digest
- **THEN** a separate parent-child attachment is permitted while a conflicting computed digest is refused

### Requirement: A terminal run can seed a distinct same-Branch run with explicit lineage

The `run_branch resume_from` input SHALL trim surrounding whitespace and then
accept a normalized source run ID containing no whitespace only when that run
exists, is owned by the current Branch-run actor, belongs
to the requested Branch definition, and is `completed`, `failed`, `cancelled`,
or `interrupted`. It MUST start a new run rather than resume the source
checkpoint, merge source inputs with explicitly supplied inputs taking
precedence, and record the chosen source as the new run's lineage parent using
the requested Branch's current version.

#### Scenario: Explicit source wins over recency

- **WHEN** `resume_from` names an owned terminal run that is not the latest run of the requested Branch
- **THEN** the system seeds a new run from that exact source and returns and records its ID as the lineage parent

#### Scenario: Explicit inputs override source inputs

- **WHEN** the source run and new request both provide the same input key
- **THEN** the newly supplied value is used while source-only inputs are retained

#### Scenario: Invalid source is classified before execution

- **WHEN** the normalized source ID contains internal whitespace, is missing, is owned by another Branch-run actor, belongs to another Branch, or is non-terminal
- **THEN** `run_branch` returns the corresponding `resume_from_invalid`, `resume_from_not_found`, `resume_from_forbidden`, `resume_from_branch_mismatch`, or `resume_from_invalid_state` failure without starting the seeded run

#### Scenario: Seeded execution is not checkpoint resume

- **WHEN** `run_branch resume_from` accepts a terminal source
- **THEN** it launches a distinct run of the requested current Branch and does not invoke the interrupted-run `resume_run` checkpoint path

### Requirement: Compiled provider nodes preserve the production sandbox error without generic wrapping

The direct provider bridge and policy-routed provider paths SHALL preserve
sandbox-specific failures. In `compile_branch` they SHALL re-raise
`tinyassets.providers.base.SandboxUnavailableError` before their generic
provider-error wrapping. After a provider returns nonempty text, the graph
path SHALL defensively pass that response through the production
`check_bwrap_failure` recognizer before propagating the text into state.
Recognized response text SHALL therefore raise the provider-layer sandbox error;
normal text SHALL proceed unchanged.

This contract covers only the provider-layer exception class and its
platform-gated signature recognizer. The distinct
`tinyassets.sandbox.detect.SandboxUnavailableError` is not interoperable with
this path. Non-sandbox exceptions raised while importing or invoking the
defensive response checker are swallowed, and win32 recognition remains a
no-op.

#### Scenario: A provider-layer sandbox error crosses the graph boundary unchanged

- **WHEN** an injected or policy-routed provider raises `tinyassets.providers.base.SandboxUnavailableError`
- **THEN** the compiled node re-raises that same sandbox-specific exception
- **AND** generic provider-error wrapping does not replace it

#### Scenario: Leaked sandbox text is rejected before state propagation

- **WHEN** a nonempty provider response contains a recognized Bubblewrap failure signature on a checked platform
- **THEN** the response checker raises the provider-layer sandbox error
- **AND** the text is not returned as successful node output

#### Scenario: Normal provider text proceeds

- **WHEN** a nonempty provider response contains no recognized sandbox signature
- **THEN** the graph node returns the normal provider text

### Requirement: Branch sandbox demand is advisory metadata and never an execution gate

`NodeDefinition.requires_sandbox` SHALL default to false, serialize, and
round-trip. For rows admitted by the ordinary branch visibility and scope
rules, branch listing SHALL report `has_sandbox_nodes`. The
`requires_sandbox` filter SHALL be stripped and lowercased; `none` returns only
branches without marked nodes, `any` returns only branches with at least one
marked node, and an empty or any other value applies no sandbox-demand filter.

Branch validation SHALL best-effort read the cached production sandbox status.
When it is falsey and the branch contains marked nodes, validation SHALL add
one non-fatal warning that lists the sorted marked node IDs, the probe reason,
and remediation. It SHALL not warn for an available probe or an unmarked
branch; an exception while obtaining status SHALL suppress this advisory.

The metadata SHALL NOT affect structural validity or `runnable`, and neither
`compile_branch` nor provider selection consumes it as an admission or
execution gate. The current warning's statement that marked nodes will fail at
runtime is advisory wording, not an enforced or universal outcome.

#### Scenario: An unavailable host discloses marked nodes without blocking the branch

- **WHEN** validation sees a falsey cached probe and a branch with multiple `requires_sandbox=true` nodes
- **THEN** it returns one warning containing the sorted marked node IDs, probe reason, and remediation
- **AND** sandbox availability alone does not change `valid` or `runnable`

#### Scenario: Available and unmarked branches have no sandbox warning

- **WHEN** the cached probe is available or the branch contains no marked node
- **THEN** branch validation emits no sandbox-compatibility warning

#### Scenario: A probe exception suppresses only the advisory

- **WHEN** reading cached sandbox status raises during branch validation
- **THEN** validation continues without the sandbox warning
- **AND** its ordinary structural and approval results remain authoritative

#### Scenario: Branch listing filters declared demand after ordinary scope admission

- **WHEN** scope-eligible branches are listed with `requires_sandbox=none` or `requires_sandbox=any`
- **THEN** it returns respectively only unmarked branches or only branches with at least one marked node
- **AND** each returned row reports its `has_sandbox_nodes` value

#### Scenario: Empty and unknown filters preserve all otherwise-admitted rows

- **WHEN** scope-eligible rows are listed with an empty or unrecognized `requires_sandbox` value
- **THEN** every otherwise-admitted row remains
- **AND** each row still reports `has_sandbox_nodes`

#### Scenario: Runtime ignores the advisory flag

- **WHEN** a structurally runnable branch contains a node marked `requires_sandbox=true`
- **THEN** the flag itself neither blocks compilation nor selects a sandbox-capable provider

### Requirement: Run evidence receipts are typed, bounded, and non-authoritative
The run substrate SHALL accept only `source_acquisition_receipt`, `claim_lineage_receipt`, and `revision_receipt` payloads; normalize their type-specific known fields; reject missing required subject identifiers, non-list or non-string list values, non-boolean source flags, and the defined source-state contradictions; and preserve unknown keys and JSON-compatible values. Values supplied directly that are not JSON-compatible MAY be stringified during sizing and persistence and therefore have no byte-for-byte round-trip guarantee. The substrate SHALL enforce the positive cap selected by `TINYASSETS_RECEIPT_PAYLOAD_MAX_BYTES` (default 65,536 bytes) against its compact, sorted UTF-8 JSON size-check encoding. These receipts MUST remain caller-supplied evidence records: unknown keys and `extensions` gain no validation, signature, truth rank, certification, or external-effect authority.

#### Scenario: Source acquisition aliases and flags normalize
- **WHEN** a source receipt supplies its subject through `source_ref`, `source`, `file_ref`, or `corpus_ref`
- **THEN** the first truthy value in precedence order `source_ref`, `source`, `file_ref`, `corpus_ref` is stringified and trimmed; if that selected value trims empty, validation fails without consulting later aliases; otherwise it becomes `source_ref` and `subject_id`, missing timestamps/string fields and six boolean acquisition flags receive their defaults, and every supplied flag must be a JSON boolean

#### Scenario: Contradictory source states are rejected
- **WHEN** `not_searched` is combined with `fetched`, `viewed`, `verified`, `snapshotted`, or `unavailable`, or `unavailable` is combined with an acquired flag
- **THEN** receipt validation fails before persistence

#### Scenario: Claim lineage and revision lists are normalized
- **WHEN** a claim-lineage receipt names a non-empty `claim_id`, or a revision receipt names at least one of `old_run_id` and `old_claim_id`
- **THEN** claim lineage trims `claim_id`, normalizes `evidence_refs`, `imported_prior_run_claims`, `counter_evidence_refs`, and `changed_claims`, and uses `claim_id` as `subject_id`; revision trims `old_run_id` and `old_claim_id`, normalizes `new_evidence_refs`, `affected_outputs`, and `recommended_reruns`, and uses non-empty `old_claim_id` as `subject_id` before falling back to `old_run_id`

#### Scenario: Extensions survive without gaining authority
- **WHEN** a valid receipt includes unknown top-level keys or an `extensions` object
- **THEN** JSON-compatible values round-trip unchanged and receive no schema validity, truth rank, or authority, while a directly supplied non-JSON-compatible value may be stringified

#### Scenario: Compact size-check payload cap is enforced
- **WHEN** the compact sorted UTF-8 JSON encoding used by the size checker exceeds the configured positive byte cap, or the cap is non-integer or non-positive
- **THEN** recording fails with a validation error and no receipt is inserted, without claiming that the separately encoded on-disk `payload_json` blob is bounded to the same byte count

### Requirement: Run receipt persistence and public actions preserve run visibility
The run substrate SHALL append a receipt only for an existing run, generating a receipt ID when none is supplied and always assigning the current creation time, and SHALL list receipts newest-first with optional exact run, receipt-type, and subject filters and a limit clamped from 1 through 1,000. For a run whose actor begins `universe:` and has a non-empty trimmed suffix, the public `record_run_receipt` action MUST derive that universe and apply its current write authorization before insertion, and `list_run_receipts` MUST apply its current read authorization both for one-run queries and to every resolvable row during unscoped enumeration. As-built limitations: a non-universe actor string or `universe:` with an empty suffix currently passes these helpers without a general run-owner ACL check, and because the foreign key is unenforced, a receipt whose run record later disappears passes the current `rec is None or _run_read_allowed(rec)` visibility predicate.

#### Scenario: Missing run cannot receive a receipt
- **WHEN** a caller records an otherwise valid receipt for a run ID absent from the current data-root runs database
- **THEN** insertion fails even though the declared SQLite foreign key is not currently enforced

#### Scenario: Receipt filtering is bounded and newest-first
- **WHEN** receipts are listed with any combination of run ID, valid receipt type, subject ID, and limit
- **THEN** matching rows are returned by descending creation time with the limit defaulting to 100 and clamped to at least 1 and at most 1,000

#### Scenario: Public receipt list normalizes invalid limits
- **WHEN** the public list action receives a missing or falsey limit, or a value that `int()` cannot convert
- **THEN** it uses the default limit of 100 before the storage-layer clamp

#### Scenario: Private universe-bound run write is filtered before recording
- **WHEN** the public record action resolves an existing `universe:<uid>` run whose universe the current caller may not write
- **THEN** it returns the canonical run-write denial and does not insert a receipt

#### Scenario: Enumeration filters private universe-bound receipts
- **WHEN** the public list action is called with or without a run ID
- **THEN** a receipt whose run still resolves to a `universe:<uid>` actor is returned only when the current caller may read that universe, with repeated receipts for one run sharing the per-request visibility result

#### Scenario: Non-universe run actors bypass resource ACL derivation
- **WHEN** a receipt's resolvable run actor does not begin `universe:` or its suffix trims empty
- **THEN** the current receipt access helpers treat the row as allowed without deriving a universe or checking a general run-owner ACL

#### Scenario: Orphan receipt visibility is not fail-closed
- **WHEN** an unenforced or externally altered data-root leaves a receipt whose referenced run row no longer resolves
- **THEN** the current public list predicate treats that orphan receipt as visible rather than failing closed

#### Scenario: Persistence does not claim caller idempotency
- **WHEN** a caller records the same logical payload repeatedly without reusing a colliding explicit receipt ID
- **THEN** the store may append multiple receipts because it provides no caller idempotency or semantic deduplication guarantee

### Requirement: Installation-local teammate mailbox persists send, receive, and acknowledgement
The run substrate SHALL persist teammate messages with a generated message ID, existing non-empty source run, non-empty destination node, JSON-serializable body, optional reply ID, UTC sent time, and exactly one of `request`, `response`, `broadcast`, `plan_approval_request`, `plan_approval_response`, `shutdown_request`, or `shutdown_response`. It SHALL provide non-destructive receive and idempotent acknowledgement actions over the installation's shared `TINYASSETS_DATA_DIR` runs database while retaining the as-built identity, isolation, and graph-wiring limitations below.

#### Scenario: Send validates the stored message envelope
- **WHEN** a caller sends a message with an existing source run, non-empty destination, allowed type, and JSON body
- **THEN** the mailbox stores it unacknowledged and the public action returns `message_id` plus `delivered_at` equal to the stored `sent_at`

#### Scenario: Invalid source, destination, type, or body is rejected
- **WHEN** the source run is absent, the source or destination ID is empty, the message type is outside the seven-value set, or the body is not JSON-serializable
- **THEN** no teammate message is inserted

#### Scenario: Receive filters destination and broadcasts
- **WHEN** a non-empty node receives messages
- **THEN** it sees rows addressed to that node plus `*` broadcasts, optionally filtered by inclusive `since` and supplied message types, ordered from earliest sent time, with a default limit of 50 clamped to 1 through 1,000 rows

#### Scenario: Unconvertible public mailbox limit can escape the handler
- **WHEN** the public receive action receives a limit value that `int()` cannot convert
- **THEN** its eager conversion may raise before the handler's JSON error wrapper rather than returning a normalized error envelope, while integer-convertible values are coerced successfully

#### Scenario: Empty-node receive enumerates the data-root mailbox
- **WHEN** receive is called with an empty node ID
- **THEN** it enumerates otherwise-filtered rows in the shared data-root database rather than applying a recipient predicate

#### Scenario: Addressee or broadcast acknowledgement is idempotent
- **WHEN** the caller-supplied node ID matches the stored destination or the destination is `*`
- **THEN** acknowledgement sets the message's single global `acked` flag to true and repeated acknowledgement remains successful

#### Scenario: Wrong node cannot acknowledge a directed message
- **WHEN** the caller-supplied node ID differs from a directed message's destination
- **THEN** acknowledgement fails without changing the stored flag

#### Scenario: Public acknowledgement validates required identifiers
- **WHEN** the public acknowledgement action receives an empty message ID or node ID, or the message ID does not exist
- **THEN** it returns an error and does not modify a mailbox row

#### Scenario: Current mailbox identity and reference limitations remain visible
- **WHEN** send, receive, or acknowledge is used through the public actions
- **THEN** the handlers perform no run read/write or universe-access check, the store validates no destination-node or reply-message existence, independently authenticates no sender or caller node identity beyond the surrounding tool context, stores no acknowledgement timestamp, and treats one broadcast acknowledgement as global

#### Scenario: Graph message helpers are callable but detached from Branch execution
- **WHEN** the send, receive, or recipient-validation helper is called directly
- **THEN** its focused helper behavior is available
- **AND** current `NodeDefinition` and `BranchDefinition` shapes expose no message-spec field and `compile_branch` never invokes these helpers, so compiled graph execution is not wired

### Requirement: Approved source nodes enqueue paced same-universe BranchTasks under trusted bounded context
When the node-enqueue capability is enabled and an approved `source_code` node declares the enqueue tool, `enqueue_branch_run` SHALL append one epoch-1 `BranchTask` and SHALL NOT start a run synchronously. The task SHALL target the trusted physical queue universe; use forced `trigger_source=owner_queued` and `request_type=branch_run`; copy only object inputs; use server-derived parent/origin lineage and parent depth plus one; and target an existing public branch. Epoch-1 enqueue MUST reject every private target because it carries no request-scoped authenticated actor evidence. Every trusted root run SHALL derive one stable origin shared by all sibling enqueues. One atomic successful-enqueue budget SHALL be shared across every source node in the compiled run. Missing trusted/run context, a foreign universe, mismatched persisted universe metadata, a missing or private target, invalid inputs, depth or run-wide budget exhaustion, or a shared-cap refusal SHALL fail before append or surface the atomic refusal as `CompilerError`.

#### Scenario: Enabled enqueue appends but does not execute
- **WHEN** an approved source node enqueues an existing public branch with valid trusted context and remaining capacity
- **THEN** exactly one forced `owner_queued` `branch_run` task is appended to that trusted universe
- **AND** the target run is left for paced daemon dispatch rather than started synchronously

#### Scenario: Trusted context and target authority fail closed
- **WHEN** enqueue lacks trusted universe or run context, names a foreign universe, or targets a missing or private branch
- **THEN** it raises `CompilerError` without appending a task

#### Scenario: Branch-authored routing metadata cannot escalate
- **WHEN** source-authored arguments attempt to control the universe, request type, trigger source, parent, origin, or depth
- **THEN** the trusted server context and forced routing fields remain authoritative and no privileged scheduler class can be selected

#### Scenario: Root siblings share one stable origin
- **WHEN** one trusted root run with no supplied parent or origin enqueues multiple children
- **THEN** every child receives the same server-derived run origin and competes for one lineage budget

#### Scenario: Source nodes share one run-wide enqueue budget
- **WHEN** multiple source nodes in one compiled run attempt more successful enqueues than `TINYASSETS_NODE_ENQUEUE_MAX_PER_RUN`
- **THEN** the run appends exactly the shared budget across all nodes and every excess attempt is refused

#### Scenario: Process identity cannot authorize a private target
- **WHEN** epoch-1 enqueue targets a private branch and the process or context actor string equals its author
- **THEN** enqueue still fails because no durable request-scoped actor authority is present

### Requirement: Shared in-node enqueue growth caps are atomic under concurrent producers
The in-node enqueue append SHALL read required history, count, and append under the same exclusive per-universe cross-process queue lock. The global cap SHALL count live `pending` and `running` rows. The lineage cap SHALL count unique non-empty `branch_task_id` values across live and archived rows carrying the same trusted `origin_branch_task_id`, plus every matching row without an ID conservatively. Concurrent contenders SHALL admit no more than remaining capacity, preserve every admitted row exactly once in readable queue JSON, and reject every excess contender without append. A missing queue or archive SHALL represent empty history, but an existing blank, whitespace-only, unreadable, invalid-JSON, or non-list required history file SHALL fail closed.

#### Scenario: Concurrent distinct-origin writers stop exactly at global capacity
- **WHEN** more distinct-origin producers contend concurrently than the global active queue has remaining capacity
- **THEN** exactly the remaining number are appended and every excess producer receives a cap refusal
- **AND** the queue contains no duplicate, lost, or corrupt admitted row

#### Scenario: Concurrent same-origin writers stop exactly at lineage capacity
- **WHEN** more producers with one trusted origin contend concurrently than that lineage has remaining lifetime capacity
- **THEN** exactly the remaining number are appended and every excess producer receives a cap refusal
- **AND** unrelated origins remain admissible while global capacity remains

#### Scenario: Archived descendants still consume lineage capacity
- **WHEN** terminal descendants of an origin have moved from the live queue to the archive
- **THEN** those archived rows still count toward later lineage admission

#### Scenario: Crash-window overlap counts one identified descendant
- **WHEN** one identified task row exists in both the archive and live queue after an interrupted archive-first collection
- **THEN** lineage admission counts that `branch_task_id` once rather than falsely exhausting two slots

#### Scenario: Corrupt lineage history refuses admission
- **WHEN** a lineage-capped enqueue requires an archive that cannot be read or decoded
- **THEN** admission fails without appending or resetting lineage history

#### Scenario: Blank persisted history refuses admission
- **WHEN** a required live queue or archive exists but contains zero bytes or only whitespace
- **THEN** admission fails without appending or treating that file as empty history

### Requirement: In-node enqueue remains epoch-1 until transactional v2 preserves its guards
The production in-node enqueue primitive SHALL emit only the epoch-1 file-backed task shape. It MUST NOT emit epoch-2 tasks until the transactional v2 path provides a stable server-owned root origin, one atomic run-wide budget, physical tenant/universe binding, atomic global-active and lifetime-lineage count/check/insert, and fail-closed integrity semantics equivalent to this capability.

#### Scenario: Current enqueue emits epoch-1 work
- **WHEN** a valid in-node enqueue is admitted by the current runtime
- **THEN** it writes the existing file-backed `owner_queued` `branch_run` task and does not select the v2 transport

#### Scenario: V2 migration is guard-complete
- **WHEN** a future change routes in-node enqueue through transactional v2 storage
- **THEN** that change must prove every stable-origin, run-budget, scope-binding, shared-cap, and integrity invariant before enabling the route
