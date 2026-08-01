## ADDED Requirements

### Requirement: Foreign imports are privately staged before publication
The platform SHALL process a bounded foreign source into an authenticated actor-owned sanitized import stage and SHALL require separate explicit operations to publish its candidate definition and bind the published definition to a universe.

#### Scenario: Successful conversion does not publish or bind
- **WHEN** an authenticated actor imports a valid foreign agent source
- **THEN** the platform returns a private stage containing a sanitized canonical candidate, report, and receipt
- **AND** no public definition, verified lineage edge, universe binding, or runtime activation is created

#### Scenario: Another actor cannot inspect a stage
- **WHEN** an actor reads an import stage owned by a different actor
- **THEN** the platform returns the same not-found result as an absent stage

#### Scenario: Publish-stage commits as one transaction
- **WHEN** an actor explicitly publishes a valid unexpired stage
- **THEN** stage status, public definition, local verified lineage projections, durable receipt linkage, and resulting definition ID commit in one transaction
- **AND** any failure leaves all of those records in their prior state

#### Scenario: Unpublished stage expires
- **WHEN** 24 hours pass without explicit publication
- **THEN** the sanitized candidate, actor-private report, and raw-source commitment become unavailable
- **AND** no published definition or binding is deleted

### Requirement: Conversion reports account for preservation and loss
The platform SHALL independently enumerate every scalar leaf and empty container of a JSON source or canonical JSON target as canonical RFC 6901 paths, SHALL require the adapter report to cover that inventory exactly once with one terminal classification from `preserved`, `normalized`, `unsupported`, `omitted_secret`, `requires_private_binding`, or `requires_runtime`, and SHALL mark opaque-format inventories without an independent verifier as `unverified`, non-exhaustive, and never lossless.

#### Scenario: Less-capable export reports every loss
- **WHEN** an actor exports a canonical definition through a target adapter that cannot represent one component and requires private setup for another
- **THEN** the report classifies the first item as `unsupported` and the second as `requires_private_binding`
- **AND** the response declares the conversion non-lossless rather than silently omitting either item

#### Scenario: Adapter claim cannot manufacture lossless status
- **WHEN** an adapter reports `lossless=true` but normalized source and output fingerprints do not prove equality
- **THEN** the platform rejects the adapter output and writes no successful conversion receipt

#### Scenario: Adapter omits one JSON source item
- **WHEN** the trusted runner enumerates a JSON source path that is absent from the adapter inventory or report
- **THEN** the platform rejects the conversion as incomplete
- **AND** no stage, receipt, definition, binding, or lineage projection is written

#### Scenario: Opaque inventory is visibly unverified
- **WHEN** an opaque source has no independent admitted inventory verifier
- **THEN** its report sets `inventory_verification=unverified`, `exhaustive=false`, and `lossless=false`
- **AND** the response does not claim that unknown source content was preserved

### Requirement: Interchange documents have one bounded canonical wire shape
The platform SHALL enforce UTF-8 canonical JSON with sorted keys, compact separators, finite numbers, no duplicate object keys, nesting depth at most 32, raw or decoded foreign source/output size at most 1 MiB, RFC 4648 padded base64 size at most 1,398,104 characters, canonical candidate size at most 256 KiB and 64 components, complete adapter response size at most 2 MiB, report size at most 4,096 unique inventory items, JSON Pointer paths at most 512 characters, safe details at most 256 characters, declarative mappings at most 128 KiB and 512 rules, and lowercase 64-hex SHA-256 or HMAC digests with explicit algorithm fields.

#### Scenario: Over-limit or ambiguous document fails before persistence
- **WHEN** a request, adapter mapping, candidate, inventory, report, path, detail, digest, number, nesting level, or duplicate-key object violates the canonical bounds
- **THEN** validation fails before adapter execution or persistence
- **AND** the response returns a bounded safe terminal error without reflecting secret-bearing input

#### Scenario: Converted response has exactly one bounded output
- **WHEN** an adapter returns `status=converted`
- **THEN** `schema_version` equals `agent-interchange-adapter/v1`, adapter digest fields are explicit, exactly one of bounded `candidate_json` or canonical `output_base64` is present, and `error_code` is absent
- **AND** the receipt explicitly binds sanitized-source, adapter, output, report, and receipt digests with `sha256` algorithm fields

#### Scenario: Non-converted response cannot smuggle output
- **WHEN** an adapter returns `requires_runtime`, `unsupported`, or `invalid`
- **THEN** it supplies a safe terminal `error_code` and contains neither `candidate_json` nor `output_base64`
- **AND** no successful conversion receipt is written

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
The platform SHALL create an immutable conversion receipt whose digest binds a digest of sanitized source content, direction, adapter identity, adapter semantic version, immutable adapter digest, output fingerprint or digest, and conversion-report digest, while any exact raw-input commitment remains actor-private, purpose-keyed, and time-bounded.

#### Scenario: Adapter revision has distinct provenance
- **WHEN** the same source is converted by two adapter versions or immutable adapter digests
- **THEN** the platform returns distinct conversion receipts even if their normalized outputs match

#### Scenario: Published import exports its safe conversion origin
- **WHEN** an actor publishes a staged foreign import and later exports that public definition
- **THEN** its immutable `external_origins` includes the sanitized-source digest and algorithm plus the adapter reference, semantic version, immutable digest, and digest algorithm bound by the conversion receipt
- **AND** the public definition and export contain neither the private raw-source commitment nor raw source content
- **AND** publication clears the stage's private raw-source commitment in the same transaction while retaining its durable receipt linkage

#### Scenario: Rolling upgrade closes pre-fix provenance and commitment gaps
- **WHEN** an upgraded process opens storage containing a pre-fix published stage with a retained private commitment
- **THEN** schema initialization idempotently clears that commitment without changing its immutable public definition or receipt linkage
- **AND WHEN** an unexpired pre-fix private stage without the safe public origin is published after upgrade
- **THEN** publication reconstructs the origin from stored receipt-bound sanitized metadata and atomically replaces the candidate and receipt before publishing
- **AND** it rejects publication if the stored receipt does not match the staged candidate, report, sanitized-source digest, or adapter metadata
- **AND** if adding the required origin would exceed the canonical candidate bound, publication returns bounded `restage_required` without changing the stage, receipt, definition, lineage, or commitment
- **AND WHEN** a pre-fix already-published stage is retried with its original idempotency key
- **THEN** the stored legacy request digest returns the existing immutable definition rather than conflicting with the new origin shape

#### Scenario: Receipt tampering is detected
- **WHEN** any receipt-bound source, adapter, output, or report field is altered
- **THEN** receipt verification fails
- **AND** the altered receipt cannot authorize publication or be presented as valid conversion evidence

#### Scenario: Raw source cannot be guessed from public evidence
- **WHEN** a foreign source contains a low-entropy credential or consists only of secret-bearing content
- **THEN** no public receipt or report contains an unkeyed digest of the raw source or secret value
- **AND** the private raw-input commitment is unavailable after the stage retention deadline

#### Scenario: Production deploy installs the private commitment key safely
- **WHEN** a deployment can expose agent staging on a public connector
- **THEN** it requires a dedicated, canonical single-line base64 secret decoding to at least 32 random bytes before any deployment mutation
- **AND** malformed, multiline, non-canonical, missing, or short key material fails before the first remote mutation
- **AND** it transfers the secret through standard input into an atomic protected daemon-only environment file without printing the value
- **AND** tunnel, logging, and worker processes do not receive the dedicated secret
- **AND** a self-host template declares the required empty secret placeholder without embedding a default or shared key
- **AND** clean-host bootstrap installs that protected placeholder, repairs its owner/mode on rerun, and the service refuses startup unless it is readable as `root:tinyassets` mode `0640`
- **AND** rotation replaces the repository secret and deploys forward without resurrecting a rotated-away key during image rollback
- **AND** deleting the repository secret blocks deployment but is not represented as runtime revocation

### Requirement: Foreign adapters are versioned untrusted commons artifacts
The platform SHALL accept foreign conversion only from an immutable adapter conforming to `agent-interchange-adapter/v1`, SHALL validate its output independently, SHALL permit in-process interpretation only for bounded non-executable declarative JSON mappings, and SHALL execute adapter code only through governed Engine OS admission without ambient credentials, universe authority, network entitlement, provider access, or an in-process code fallback.

#### Scenario: Runtime-required adapter is unavailable
- **WHEN** a requested adapter requires executable code but no governed Engine OS admission is available
- **THEN** the conversion remains unexecuted and reports `requires_runtime`
- **AND** the platform does not run the adapter in the API or daemon process

#### Scenario: Declarative proof adapter uses the same protocol
- **WHEN** an immutable adapter contains only bounded JSON-pointer copy, rename, constant, namespace-preserve, and classification rules with no expressions, code, network, or secret access
- **THEN** the platform may interpret it in-process through `agent-interchange-adapter/v1`
- **AND** its output, report, receipt, and canonical candidate pass the same validation as every other adapter

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
The platform SHALL make `(actor, operation, idempotency_key)` unique, store a canonical digest of the bound request, treat an identical retry as one logical operation, and reject reuse of that identity with different source, adapter, direction, or candidate content.

#### Scenario: Concurrent identical import creates one stage
- **WHEN** concurrent requests submit the same source, adapter digest, direction, actor, and idempotency key
- **THEN** all successful responses identify the same stage and receipt
- **AND** storage contains one logical stage and one logical receipt

#### Scenario: Conflicting retry is refused
- **WHEN** an actor reuses an interchange idempotency key with different bound input
- **THEN** the platform returns a conflict
- **AND** the original stage, receipt, definition, binding, and lineage remain unchanged

### Requirement: Interchange sustains deployment-shaped concurrent use
The platform SHALL satisfy the §14 interchange load envelope with no partial writes, duplicate logical stages, secret leakage, or unhandled storage-contention failures.

#### Scenario: Mixed maximum-payload load stays within thresholds
- **WHEN** 200 concurrent actors across eight processes issue 1,000 mixed stage, import, remix, and export requests in five minutes, including 256-KiB definitions, 64-component definitions, identical retries, and conflicting retries
- **THEN** throughput is at least 3.33 requests per second, p95 latency is below 2 seconds, p99 latency is below 3 seconds, and unexpected errors remain below 1 percent
- **AND** there are zero unhandled busy errors, partial stage/definition/lineage writes, duplicate logical stages, or secret-bearing report/receipt/log values
- **AND** expected idempotency conflicts are counted separately from unexpected errors

### Requirement: Interchange remains on canonical graph handles
The platform SHALL expose agent staging, inspection, remix, publication, binding, and export operations only through targets and operations of the existing canonical graph handles and SHALL preserve the exact seven-handle public manifest.

#### Scenario: Rendered chatbot completes the interchange flow
- **WHEN** a connector user imports a foreign source, inspects its report, blends components from other users' public agents, explicitly publishes, binds privately, and exports the result
- **THEN** the flow completes through `read_graph` and `write_graph` agent targets with authorization enforced at every private boundary
- **AND** the advertised tool set remains `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}`

#### Scenario: A rendered client can construct a declarative import from the tool contract
- **WHEN** a connector client receives an arbitrary JSON agent manifest and selects `write_graph` with `target=agent` and `operation=stage_import`
- **THEN** the advertised `payload_json` description identifies `source_json` and `adapter` as sibling top-level keys and never instructs the client to nest the source inside the adapter
- **AND** it identifies the `agent-interchange-adapter/v1` version, adapter identity fields, the closed rule operations, their required path/classification fields, and exact source-inventory coverage
- **AND** a client can construct the private staging request without relying on a maintained catalog of agent-specific configurations or hidden documentation
