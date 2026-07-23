## ADDED Requirements

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
