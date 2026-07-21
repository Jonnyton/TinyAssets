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
The compiler SHALL synthesize the run's state type as a `TypedDict` (Hard Rule #5) whose per-field merge behavior follows each `state_schema` field's declared `reducer`: `append` maps to `Annotated[list, operator.add]`, `merge` maps to `Annotated[dict, <shallow merger>]`, and any other value (including unset) is last-write-wins overwrite. As-built limitation: the `merge` reducer (`_dict_merge` in `graph_compiler`) is a shallow, right-biased `dict.update` — nested keys are replaced wholesale, not deep-merged, and because the result depends on which side is applied last it is non-convergent under concurrent fan-in and is only safe for single-writer fields (tracked as the "L4 reducer law" work item).

#### Scenario: an append field concatenates contributions
- **WHEN** two nodes each write a list to a state field declared `reducer="append"`
- **THEN** the field's value is the concatenation of both contributions via `operator.add`

#### Scenario: an unreduced field is overwritten
- **WHEN** a field has no recognized reducer and two nodes write it
- **THEN** the last write wins and the earlier value is discarded

#### Scenario: a merge field is shallow and order-sensitive (as-built limitation)
- **WHEN** two nodes write overlapping-key dicts to a field declared `reducer="merge"`
- **THEN** the surviving value is a shallow right-biased union in which the later-applied dict's keys overwrite the earlier's
- **AND** nested structures are replaced, not deep-merged, so concurrent fan-in into a merge field is not convergent

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
