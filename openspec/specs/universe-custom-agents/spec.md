# Universe Custom Agents

## Purpose

Public composable agent definitions, private universe bindings, component
provenance, portable interchange, and their authorization and validation
rules.

## Requirements

### Requirement: Public agent definitions are immutable component compositions
The platform SHALL let an authenticated actor publish an immutable public agent definition containing a versioned portable envelope, descriptive metadata, and one or more user-named component objects without imposing a platform-owned agent archetype.

#### Scenario: A user publishes a coding-agent composition
- **WHEN** an authenticated actor publishes a valid definition whose components describe its identity, coding workflow, tools, memory policy, and evaluator references
- **THEN** the platform returns a new stable definition ID, author ID, content fingerprint, and the complete public definition
- **AND** later publication of an evolved configuration creates a new definition rather than mutating the earlier record

#### Scenario: A power user adds an unfamiliar component
- **WHEN** a valid definition contains a component key and kind unknown to the current runtime
- **THEN** the platform preserves and exposes that component for portability and remix
- **AND** preservation does not claim that the current runtime can execute the unknown kind

### Requirement: Agent content is bounded, JSON-compatible, and secret-free
The platform SHALL reject an agent definition or binding payload that exceeds 256 KiB of canonical JSON, contains more than 64 definition components, uses an invalid component key, contains a non-object component, or contains a recursively nested secret-bearing field rather than a governed resource reference.

#### Scenario: A raw credential is rejected
- **WHEN** a definition component or private binding contains a field named `api_key`, `access_token`, `refresh_token`, `client_secret`, `private_key`, `password`, or `credential`
- **THEN** the write fails with a validation error naming the offending JSON path
- **AND** no definition, binding, or lineage row is written

#### Scenario: A governed resource reference is accepted
- **WHEN** a binding names a `resource_binding_id`, `provider_policy_id`, or `adapter_ref` without embedding secret material
- **THEN** validation accepts the reference shape
- **AND** the referenced credential remains outside the agent tables

### Requirement: Component remix preserves bounded multi-parent provenance
The platform SHALL let an authenticated actor publish a remix whose individual child components cite zero or more existing public parent components with finite credit shares in `[0,1]`, SHALL require each child component's shares to total no more than `1.0`, SHALL write definition and provenance atomically, and SHALL reject lineage deeper than 50 generations.

#### Scenario: A user blends components from several agents
- **WHEN** a remix definition cites the identity component of one public agent, the coding workflow of a second, and the memory policy of a third
- **THEN** the child definition contains all selected or authored child components
- **AND** its lineage read reports each verified parent component and credit share

#### Scenario: Invalid lineage leaves no partial definition
- **WHEN** any cited parent definition or component is absent, any share is invalid, the shares exceed `1.0`, or the resulting lineage exceeds 50 generations
- **THEN** the entire remix fails
- **AND** neither the child definition nor any of its lineage rows exists

### Requirement: Universe bindings keep operational configuration private
The platform SHALL let a universe writer bind a public agent definition to that universe with private role, goal, component-configuration, authority, resource, provider, and channel-address references, and SHALL exclude raw credentials, conversations, and effect payloads from the binding.

#### Scenario: A universe owner binds a public agent privately
- **WHEN** an authenticated actor with write or admin access binds a public definition to a universe
- **THEN** the platform returns a private binding with revision `1` and status `configured`
- **AND** anonymous or non-authorized callers cannot discover the binding or its configuration

#### Scenario: A channel reference does not claim a live connection
- **WHEN** a binding stores a Slack or other app adapter/address reference before the outbound boundary runtime is available
- **THEN** the binding remains `configured`
- **AND** the platform does not send, receive, or claim a connected channel

### Requirement: Binding updates are atomic and revision guarded
The platform SHALL update a private agent binding only when the caller has universe write authority and supplies the current expected revision, SHALL increment the revision exactly once, and SHALL allow the update to select a successor public definition.

#### Scenario: Concurrent stale update is refused
- **WHEN** two clients read revision `3`, one update commits revision `4`, and the other submits `expected_revision=3`
- **THEN** the second update fails with a revision-conflict result
- **AND** it does not overwrite revision `4`

### Requirement: Agent definitions support verified portable interchange
The platform SHALL expose a canonical portable definition containing no binding-private data, SHALL verify a supplied content fingerprint during import, SHALL revalidate imported content, and SHALL grant verified lineage credit only for parent components resolvable in the local commons.

#### Scenario: Export excludes universe-private state
- **WHEN** a caller reads the portable form of a public definition that has private universe bindings
- **THEN** the export contains the public components, fingerprint, and public lineage declarations
- **AND** it contains no universe ID, binding ID, role, resource reference, channel address, conversation, credential, or runtime state

#### Scenario: Tampered import is rejected
- **WHEN** an import supplies a fingerprint that does not match its normalized portable content
- **THEN** the import fails validation
- **AND** no local definition or lineage row is written

### Requirement: Definition retries are idempotent per author
The platform SHALL treat a repeated publish, remix, or import carrying the same non-empty idempotency key from the same authenticated author as one logical write and return the original definition without duplicating lineage.

#### Scenario: A chatbot retries after losing the response
- **WHEN** an actor repeats a completed definition write with the same idempotency key
- **THEN** the platform returns the original definition ID and content
- **AND** the definition and component-lineage row counts do not increase
