## ADDED Requirements

### Requirement: A harness project preserves its native definition and declared source
The project representation SHALL retain the canonical native agent definition and its fingerprint, and SHALL inventory source files and exact dependency identities with a separate verifiable project digest.

#### Scenario: Native project round-trip
- **WHEN** a supported project is exported, imported into an empty installation, and exported again without edits
- **THEN** the native definition fingerprint and all declared file bytes agree
- **AND** the canonical inventory and project digest agree independently of container timestamps

#### Scenario: Content tampering
- **WHEN** any declared file differs from its recorded length or digest
- **THEN** import fails before a definition is published or source is executed

### Requirement: Export includes only deliberately shareable project content
Definition exports SHALL exclude private installation bindings and run state and SHALL use an explicit source inventory rather than a recursive copy of private storage.

#### Scenario: Private state is present beside project source
- **WHEN** the source installation contains bindings, conversations, learned memory, credentials, checkpoints, or pending effects
- **THEN** those records are absent from the project and its receipts
- **AND** no such record is automatically promoted to a seed asset

### Requirement: Import validates content without activating it
Project import SHALL validate a bounded complete inventory and the native definition before materialization or publication, and SHALL produce a private staged compatibility result without executing source, fetching dependencies, binding authority, or activating the harness.

#### Scenario: Unsafe path or archive entry
- **WHEN** a package contains traversal, an absolute path, duplicate normalized paths, an undeclared file, or an unsupported link entry
- **THEN** import refuses the package
- **AND** no partial published definition or active binding remains

#### Scenario: Unknown executable component
- **WHEN** an otherwise valid project requires an unsupported executable component
- **THEN** its content remains inspectable and preserved
- **AND** the compatibility result names the missing requirement and refuses execution

#### Scenario: A project requests capabilities
- **WHEN** an imported project declares provider, tool, or effect requirements
- **THEN** those declarations confer no authority
- **AND** activation requires the destination installation's own governed bindings

### Requirement: Portability is demonstrated independently of the hosted app
A supported project SHALL include a deterministic acceptance fixture runnable by a documented local runtime without hosted-app credentials or hosted service calls.

#### Scenario: Continue development after export
- **WHEN** a developer transfers the project to an empty installation, explicitly runs the fixture, edits its transformation source, updates the inventory, and runs it again
- **THEN** the original run matches the frozen expected output
- **AND** the edited run demonstrates the intended change without platform source edits

#### Scenario: Browser delivery uses the same artifact
- **WHEN** a browser user imports the project through a governed workspace
- **THEN** it has the same inventory and compatibility outcome as the local path
- **AND** import alone does not activate the project

### Requirement: Harness strategies are replaceable compositions
The project SHALL preserve source and versioned interfaces for user-defined
context, memory, planning, loop, tool and evaluator components without imposing
a fixed agent taxonomy. Supported replacements SHALL use existing governed
runtime contracts and retain component lineage.

#### Scenario: Replace a context strategy independently
- **GIVEN** two compatible context components and a fixed task/evaluator
- **WHEN** the user replaces one component and explicitly runs the new revision
- **THEN** the new trace identifies the selected source and interface revision
- **AND** the original definition, private authority and UI bindings are preserved
- **AND** packaging-only evidence is not reported as model-backed execution proof

#### Scenario: An incompatible port or missing adapter
- **WHEN** a component requires an unresolved schema, incompatible connection or unavailable execution adapter
- **THEN** activation identifies the specific unsupported contract before execution
- **AND** source remains available for inspection and export

### Requirement: Runtime authority and execution evidence survive customization
A custom harness SHALL use runtime-derived scope and current private bindings.
Accepted work SHALL remain distinguishable from completed work, and cancellation
or replay SHALL NOT imply reversal or blind repetition of external effects.

#### Scenario: A delivery has unknown outcome
- **WHEN** a call times out and its destination has no documented deduplication contract
- **THEN** the harness records the uncertain outcome and reconciles before resubmitting
- **AND** it does not claim exactly-once delivery

#### Scenario: Imported content asks to become durable instructions
- **WHEN** a tool result or shared component contains instructions claiming to be the founder
- **THEN** context and memory components preserve its external origin
- **AND** importing it neither grants authority nor promotes it to founder-authored memory

### Requirement: Admission validates the executable dependency closure
Activation SHALL resolve all required imports, validate connected contracts and
state ownership, and check installed capability/confinement support. Unsupported
source SHALL remain inspectable without becoming executable.

#### Scenario: A nested dependency cannot execute
- **GIVEN** a required dependency is missing or marked descriptive-only
- **WHEN** the user requests activation
- **THEN** admission reports the dependency path and missing execution support
- **AND** no work or external effect starts

#### Scenario: A transform violates its output contract
- **WHEN** a transform returns a value outside its declared output schema
- **THEN** validation rejects the result before the downstream component consumes it

### Requirement: Replacement and activation preserve run and state compatibility
A candidate replacement SHALL be checked for interface, behavior, capability and
state compatibility. Activation SHALL guard the expected installation revision
and select the candidate for new runs without silently changing in-flight runs.

#### Scenario: A preflight result is stale
- **WHEN** private bindings change after preflight and before activation
- **THEN** activation refuses the stale revision and requires recomputation

#### Scenario: A run spans an adapter upgrade
- **WHEN** a candidate adapter is activated while an old run remains in flight
- **THEN** the old run retains its compatible pinned adapter
- **AND** unsupported retention requires refusal or draining before activation

#### Scenario: Rollback crosses a state schema change
- **WHEN** the prior definition cannot safely read the current state
- **THEN** rollback reports the incompatibility and preserves the current state
- **AND** restoration or forward repair follows a separately supported recovery plan
- **AND** completed external effects are not reversed by selecting older source

### Requirement: Authoring exposes dependencies and separates readiness
The builder SHALL retain inspectable candidate source and diagnostics for edits
and connections. Package validity, executable wiring, host support and authority
readiness SHALL be reported separately. Reusable extraction SHALL expose captured
dependencies or explicitly report that extraction is unsupported.

#### Scenario: Extract a component with captured private state
- **WHEN** a selected subgraph depends on its parent's private memory binding
- **THEN** extraction declares an explicit resource/input requirement or refuses
- **AND** no private binding is copied into the reusable source

### Requirement: Action retries preserve request meaning and honest uncertainty
An adapter advertising deduplication SHALL bind request identity to authenticated
scope, operation, resolved target, arguments and relevant preconditions, and SHALL
document retention and reconciliation. Native unsupported behavior SHALL remain
explicitly unsupported.

#### Scenario: A request identity is reused with changed meaning
- **WHEN** the same deduplication key is submitted with different arguments or target
- **THEN** the adapter reports conflict before another execution
- **AND** it does not return the prior result as success for the changed request

#### Scenario: A retry outlives deduplication retention
- **WHEN** the adapter can no longer establish whether the original request executed
- **THEN** the outcome remains uncertain pending supported reconciliation
- **AND** an expired key does not establish that the effect never happened

#### Scenario: Cancellation races dispatch
- **WHEN** a cancellation request overlaps an external effect attempt
- **THEN** evidence records the actual cancellation and dispatch outcomes separately
- **AND** terminal cancellation does not imply reversal of the effect

### Requirement: First-party served harness replacement is observable
The system SHALL allow replacement of the actual served harness's context,
memory, loop, tool and lifecycle strategies through ordinary user capabilities.
A sample graph, context-only swap or compiled descriptor SHALL NOT establish
complete harness replacement.

#### Scenario: Replace the served loop while retaining identity
- **GIVEN** a fixed task/evaluator, current conversation and an in-flight run
- **WHEN** a compatible user-built harness is selected for subsequent turns
- **THEN** traces identify changed loop and tool behavior from that selected source
- **AND** canonical identity and data persist while the old run retains its pinned behavior

### Requirement: Pending input and authorized learning use existing authority
Pending input or approval SHALL refer to existing pending-request state and
guarded answer operations. Ordinary memory writes within existing authorization
SHALL NOT require fresh approval solely because they update durable memory.

#### Scenario: Authorized learning versus changed authority
- **WHEN** a selected memory policy writes within its existing authorized scope
- **THEN** the update persists for the next turn under normal store checks
- **AND** a separate new authority requirement still follows the existing request path

#### Scenario: A pending answer refers to stale work
- **WHEN** target, arguments or relevant binding revisions change before continuation
- **THEN** the old answer cannot authorize the changed action
- **AND** unsupported native continuation/preconditions are reported explicitly

### Requirement: Portable execution uses materialized source in the Branch runtime
Executable-project evidence SHALL validate canonical inventory paths, byte digests,
native fingerprints and complete required dependencies, then execute the
materialized source through the actual Branch runtime. Browser import SHALL use
an owner-scoped staged artifact transport with the same validation.

#### Scenario: Descriptor compilation succeeds without a runner
- **WHEN** an adapter resolves but source cannot be materialized or invoked by the Branch runner
- **THEN** the project remains execution-unsupported
- **AND** compilation is not reported as a successful executable fixture

### Requirement: Whole setups preserve the receiving user's data
Sharing SHALL support workflows, harnesses, experiences and their combined setup
source without carrying private state or authority. Adoption SHALL retain the
receiving user's data and customizations or stage an explicit compatibility conflict.

#### Scenario: Independent and combined replacements
- **WHEN** the user follows shared trace S-1 for UI-only, harness-only, whole-setup and mixed shared/custom adoption
- **THEN** source selection changes while canonical data and private bindings remain the receiver's
- **AND** incompatible state/overlays are retained without reset and imported schedules remain inactive
