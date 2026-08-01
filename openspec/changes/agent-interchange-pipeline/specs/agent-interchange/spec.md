## ADDED Requirements

### Requirement: Canonical definitions round-trip without semantic loss
The platform SHALL export and import `agent-definition/v1` as one normalized portable definition whose public content and content fingerprint are identical after an export-import-export round-trip.

#### Scenario: Native definition round-trips exactly
- **WHEN** an actor exports a public definition and imports the unchanged canonical document
- **THEN** the imported portable content normalizes to the same content fingerprint
- **AND** a second export contains the same components, public metadata, and origin declarations

#### Scenario: Private and runtime state never enters canonical interchange
- **WHEN** a public definition has one or more private universe bindings and runtime activity
- **THEN** its canonical export contains no binding ID, universe ID, credential, resource or channel address, conversation, effect payload, execution record, or runtime state

### Requirement: Foreign imports are privately staged before publication
The platform SHALL process a bounded foreign source into an authenticated actor-owned sanitized import stage and SHALL require separate explicit operations to publish its candidate definition and bind the published definition to a universe.

#### Scenario: Successful conversion does not publish or bind
- **WHEN** an authenticated actor imports a valid foreign agent source
- **THEN** the platform returns a private stage containing a sanitized canonical candidate, report, and receipt
- **AND** no public definition, verified lineage edge, universe binding, or runtime activation is created

#### Scenario: Another actor cannot inspect a stage
- **WHEN** an actor reads an import stage owned by a different actor
- **THEN** the platform returns the same not-found result as an absent stage

### Requirement: Conversion reports account for preservation and loss
The platform SHALL return a bounded structured `ConversionReport` that assigns every relevant source or target item exactly one terminal classification from `preserved`, `normalized`, `unsupported`, `omitted_secret`, `requires_private_binding`, or `requires_runtime` and SHALL never claim losslessness unless verifier-proven native equality holds.

#### Scenario: Less-capable export reports every loss
- **WHEN** an actor exports a canonical definition through a target adapter that cannot represent one component and requires private setup for another
- **THEN** the report classifies the first item as `unsupported` and the second as `requires_private_binding`
- **AND** the response declares the conversion non-lossless rather than silently omitting either item

#### Scenario: Adapter claim cannot manufacture lossless status
- **WHEN** an adapter reports `lossless=true` but normalized source and output fingerprints do not prove equality
- **THEN** the platform rejects the adapter output and writes no successful conversion receipt

### Requirement: Unknown content is preserved safely and secret material is omitted
The platform SHALL preserve safe unknown agent data in bounded namespaced extensions and SHALL omit suspected credentials, authority-bearing values, conversations, effect payloads, and runtime state from canonical candidates, public definitions, foreign exports, reports, receipts, errors, and logs.

#### Scenario: Unfamiliar component survives conversion
- **WHEN** a bounded source contains an unfamiliar component or field that is safe to publish but not understood by the current runtime
- **THEN** the sanitized canonical candidate preserves it under a stable namespaced key
- **AND** the report classifies it as `preserved` or `requires_runtime` without claiming it is executable

#### Scenario: Credential-like source data cannot become public evidence
- **WHEN** a malicious source contains API keys, access or refresh tokens, passwords, private keys, channel secrets, or credential-bearing nested fields
- **THEN** their values are absent from durable stage content, the public candidate, reports, receipts, errors, exports, and logs
- **AND** safe report entries classify the affected paths as `omitted_secret` or `requires_private_binding`

### Requirement: Conversion receipts bind exact provenance
The platform SHALL create an immutable conversion receipt whose digest binds the source digest, direction, adapter identity, adapter semantic version, immutable adapter digest, output fingerprint or digest, and conversion-report digest.

#### Scenario: Adapter revision has distinct provenance
- **WHEN** the same source is converted by two adapter versions or immutable adapter digests
- **THEN** the platform returns distinct conversion receipts even if their normalized outputs match

#### Scenario: Receipt tampering is detected
- **WHEN** any receipt-bound source, adapter, output, or report field is altered
- **THEN** receipt verification fails
- **AND** the altered receipt cannot authorize publication or be presented as valid conversion evidence

### Requirement: Foreign adapters are versioned untrusted commons artifacts
The platform SHALL accept foreign conversion only from an immutable adapter conforming to `agent-interchange-adapter/v1`, SHALL validate its output independently, and SHALL execute adapter code only through governed Engine OS admission without ambient credentials, universe authority, network entitlement, provider access, or an in-process fallback.

#### Scenario: Runtime-required adapter is unavailable
- **WHEN** a requested adapter requires executable code but no governed Engine OS admission is available
- **THEN** the conversion remains unexecuted and reports `requires_runtime`
- **AND** the platform does not run the adapter in the API or daemon process

#### Scenario: Invalid adapter output cannot bypass canonical validation
- **WHEN** an adapter returns oversized, malformed, secret-bearing, or fingerprint-inconsistent canonical output
- **THEN** the platform rejects the conversion atomically
- **AND** no successful stage, receipt, definition, binding, or lineage edge is written

### Requirement: Any users' public agents can be remixed together
The platform SHALL let an authenticated actor publish one child definition selecting components from any number of public parent definitions regardless of parent authorship, while preserving server-verified component lineage, bounded credit shares, and residual child-author credit.

#### Scenario: Child blends three other users' agents
- **WHEN** one actor selects components from public definitions authored by three different other actors and adds a new component
- **THEN** the child publishes atomically with verified lineage to all selected parent components
- **AND** the newly authored residual content remains attributable to the child author

#### Scenario: Imported provenance remains informational until resolved
- **WHEN** a staged or imported definition declares an external parent that the local commons cannot resolve by immutable definition and component fingerprint
- **THEN** the platform may preserve the declaration as informational origin metadata
- **AND** it writes no verified lineage edge or verified credit for that source

### Requirement: Interchange writes are idempotent and concurrency safe
The platform SHALL treat a repeated conversion or publish-stage request with the same actor-scoped idempotency identity and identical bound inputs as one logical operation and SHALL reject reuse of that identity with different source, adapter, direction, or candidate content.

#### Scenario: Concurrent identical import creates one stage
- **WHEN** concurrent requests submit the same source, adapter digest, direction, actor, and idempotency key
- **THEN** all successful responses identify the same stage and receipt
- **AND** storage contains one logical stage and one logical receipt

#### Scenario: Conflicting retry is refused
- **WHEN** an actor reuses an interchange idempotency key with different bound input
- **THEN** the platform returns a conflict
- **AND** the original stage, receipt, definition, binding, and lineage remain unchanged

### Requirement: Interchange remains on canonical graph handles
The platform SHALL expose agent staging, inspection, remix, publication, binding, and export operations only through targets and operations of the existing canonical graph handles and SHALL preserve the exact seven-handle public manifest.

#### Scenario: Rendered chatbot completes the interchange flow
- **WHEN** a connector user imports a foreign source, inspects its report, blends components from other users' public agents, explicitly publishes, binds privately, and exports the result
- **THEN** the flow completes through `read_graph` and `write_graph` agent targets with authorization enforced at every private boundary
- **AND** the advertised tool set remains `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}`
