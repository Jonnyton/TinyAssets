## MODIFIED Requirements

### Requirement: source_code nodes execute in an OS-isolated subprocess with data and no credentials

A `source_code` node SHALL execute in a child process launched through the
host's OS sandbox (bubblewrap on Linux: no network, no data directory, no
universe root, no credential mounts, cleared environment, private `/tmp`,
`--die-with-parent`), with address-space, CPU, file-size and descriptor
limits set first thing in the child. The child SHALL receive only the node's
declared `input_keys` (plus schema-defaulted keys) as `state` and the
`{status, body}` of its graph ancestors' authenticated calls as `effects` —
never response headers — and SHALL return a dict, which passes through to
state exactly as an in-process node's return did (the single-merge-writer
guard sees it unfiltered; undeclared keys are named in the node's event).
Calls to `invoke_mcp_action` inside the child SHALL be answered synchronously
by the parent over the sandbox's pipes, through the run's invoker with the
run's authority (at most 32 per run, replies bounded); the child SHALL never
hold the invoker. The in-process `exec` path SHALL NOT exist. A host without the OS
sandbox SHALL fail the run loudly as `sandbox_unavailable`; no environment
variable SHALL select an unsandboxed launcher (test doubles are injected).
Source SHALL still be refused for a disallowed pattern, a size over 50 KB or
a syntax error.

Execution authority SHALL be authorship: a `source_code` node runs only when
the run's `caller_provenance` is `own` (the branch was authored by the actor
the run executes as). A public foreign branch run directly SHALL refuse at
compile with a message naming the remedy (remix into the caller's universe),
classified `node_not_accepted`. `approved` / `approved_source_hash` SHALL be
provenance only and SHALL NOT gate execution.

#### Scenario: an owner-authored code node runs without approval
- **WHEN** a branch authored by the run's actor contains a `source_code` node with `approved=False`
- **THEN** the node executes in the sandbox and its declared outputs land in state

#### Scenario: a foreign branch's code refuses
- **WHEN** a run executes a public branch authored by someone else and it contains a `source_code` node
- **THEN** compilation raises before any node runs, the run fails as `node_not_accepted`, and the message says to remix the branch

#### Scenario: the child sees ancestors' bodies and no headers
- **WHEN** a code node's ancestor fetched a document with a `Set-Cookie` header
- **THEN** `effects[<ancestor>]` carries `status` and the full `body` and no `headers` key

#### Scenario: a print flood cannot exhaust the daemon
- **WHEN** code prints past the output cap
- **THEN** the child is killed at the cap and the node fails with "output too large"

### Requirement: Run failures map to a terminal status taxonomy
The executor SHALL additionally classify a sandboxed code node's failure as
`code_node_failed` (actionable by the chatbot: the message carries the
child's stderr tail), a refused foreign code node as `node_not_accepted`
(chatbot: remix), and an effect failure raised at node time by its
`external write failed - <node>/<sink>: <error> [<kind>]` message (the
existing `external_write_failed` / `external_write_refused` classes). All
other clauses of this requirement are unchanged.

#### Scenario: a code node that raises fails the run with its stderr
- **WHEN** `run()` raises inside the sandbox
- **THEN** the run status is `failed`, the class is `code_node_failed`, and the error contains the exception text from the child's stderr

### Requirement: Owner-authored source nodes enqueue paced same-universe BranchTasks under trusted bounded context
When the node-enqueue capability is enabled and an owner-authored
`source_code` node calls `invoke_mcp_action('enqueue_branch_run', …)`, the
parent SHALL perform the enqueue with the run's authority and answer the
child with its result; the enqueue SHALL append one epoch-1 `BranchTask` and
SHALL NOT start a run synchronously. All other clauses (trusted context,
target authority, capacity) are unchanged; "approved" in this requirement
reads "owner-authored".

## ADDED Requirements

### Requirement: Effects fire at node time in graph order

When a node's function returns, the runtime SHALL immediately dispatch the
node's declared `effects` against the state merged with that node's delta
(reducers applied), record the full result on a run-scoped effect chain and
bounded evidence for persistence, and continue to the next node. A node's
effects SHALL fire at most once per run; a revisit (cycle) SHALL fail the
node with kind `effect_already_fired`. A reference to an earlier effect —
`$ta.effect`, a code node's `effects` — SHALL resolve only to the node's
graph ancestors. A packet refused before the wire, a crashed adapter, a dead
sink, or a delivered call answered ≥ 400 whose status the packet did not
declare in `accept_statuses` SHALL fail the node and end the run `failed`;
later nodes SHALL NOT run. Evidence SHALL persist on every terminal status,
and a run that fired a delivered effect before failing SHALL carry
`failed_after_effects` naming those nodes. After an interrupt, a resumed run
SHALL refuse a reference to an effect fired before the interrupt rather than
resolve it from persisted bounded evidence.

#### Scenario: a refused write stops the chain
- **WHEN** `write_readme`'s packet is refused (`invalid_body_transform`) and `open_pr` follows it
- **THEN** the run fails at `write_readme` with `external write failed - write_readme/…`, `open_pr` never fires, and the evidence of `create_branch` is persisted with `failed_after_effects: ["create_branch"]`

#### Scenario: a probe's 404 is data when declared
- **WHEN** a GET packet declares `"accept_statuses": [404]` and the far side answers 404
- **THEN** the node succeeds and a later code node reads `effects["probe"]["status"] == 404`

#### Scenario: a cycle cannot refire an effect
- **WHEN** a conditional edge routes back to a node whose effects already fired in this run
- **THEN** the second visit fails the node with kind `effect_already_fired`
