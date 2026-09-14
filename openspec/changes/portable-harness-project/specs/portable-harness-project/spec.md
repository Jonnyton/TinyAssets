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
