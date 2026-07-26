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
- **WHEN** CI scans universe intelligence, compiled nodes and routers, run and child bridges, editorial and ingestion paths, retrieval and RAPTOR paths, reflexion, entity extraction, community evaluation, and the mirrored Claude plugin
- **THEN** each provider-capable call site is classified as live-request authority, host authority, background receipt authority, maintenance authority, accepted-market remote dispatch, or proven non-provider or mock-only

#### Scenario: Unclassified provider call fails the gate
- **WHEN** a new or changed production call site can reach provider execution without one exact classification and carrier path
- **THEN** the call-site closure check fails before the change can land

#### Scenario: Mirrored runtime remains equivalent
- **WHEN** authority-carrier behavior changes in the canonical runtime
- **THEN** the packaged Claude-plugin mirror exposes the same background receipt enforcement or is proven not to contain the affected provider path
