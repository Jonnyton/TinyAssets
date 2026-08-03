## ADDED Requirements

### Requirement: Custody mode remains explicit and replaceable
The system SHALL represent private conversation custody with a versioned open provider identifier, and the first implementation SHALL use `private_universe` only after a trusted current selection resolves the exact registered universe path.

#### Scenario: Authority-resolved private-universe placement
- **WHEN** a valid operation grant resolves an active `private_universe` selection and registered universe path
- **THEN** the provider derives storage only from that registered path and labels records and exports with the selected mode

#### Scenario: Caller-selected or substituted path is refused
- **WHEN** a path is caller-supplied, relative, the platform data root, not the current registered association, nonexistent, symlinked, or a Windows reparse point
- **THEN** the system refuses the operation before opening or writing conversation storage

#### Scenario: Unsupported mode does not fall back
- **WHEN** a grant names a mode for which no provider is installed
- **THEN** the system fails explicitly without writing data or falling back to `private_universe`

### Requirement: Opaque authority is necessary for every operation
The system SHALL require and consume a one-use, unforgeable, action-bound grant from the future authenticated app-conversation authority owner for every create, append, read, export, and delete, and matching identifiers alone SHALL NOT authorize access.

#### Scenario: Valid grant and exact request succeed
- **WHEN** a current grant binds the normalized action digest, owner, universe, agent binding, selected mode/generation, registered path, trusted platform data root, and server-issued idempotency-key digest
- **THEN** the internal facade may perform that one exact operation

#### Scenario: Matching strings without authority fail
- **WHEN** a caller supplies matching owner, universe, binding, interlocutor, participant, or source-event strings without a valid grant
- **THEN** the system returns no private record and writes nothing

#### Scenario: Replayed, expired, revoked, or mismatched grant fails
- **WHEN** a grant has been consumed, expired, its selection or binding is no longer current, or any normalized request field/digest differs
- **THEN** the system fails closed before opening storage and reveals no private state

#### Scenario: Raw transport identity is not authority
- **WHEN** a future app adapter authenticates a provider event
- **THEN** its authority owner mints normalized internal references and a grant; the custody store persists no app credential, installation grant, or raw provider authority object

### Requirement: Threads are immutable and request-bound
The system SHALL create an immutable thread with a server-generated identifier, exact contract/mode, owner, universe, agent binding, normalized interlocutor reference, explicit retention boundary, and RFC 3339 UTC creation time under owner-and-operation-scoped idempotency.

#### Scenario: Concurrent identical create replay
- **WHEN** identical valid create requests with the same server-issued key race or retry before deletion
- **THEN** exactly one thread is created and every request returns that exact thread

#### Scenario: Changed create replay conflicts
- **WHEN** the same owner reuses an active `create_thread` key for different input
- **THEN** the system reports a conflict and preserves the original thread

#### Scenario: Thread has no mutation path
- **WHEN** a thread has been accepted
- **THEN** its identity, scope, interlocutor, custody mode, and retention boundary cannot be updated

### Requirement: Payload canonicalization is portable and bounded
The system SHALL canonicalize message payload mappings with `tinyassets-canonical-json/v1`: only null, booleans, NFC strings, signed-64-bit integers, lists, and string-keyed mappings are accepted; canonical UTF-8 bytes and SHA-256 digests SHALL follow the exact versioned representation.

#### Scenario: Unknown bounded members round-trip
- **WHEN** a payload contains unknown member names but satisfies the canonical type and structural limits
- **THEN** read and export preserve the members and values exactly

#### Scenario: Representation is deterministic
- **WHEN** semantically identical accepted mappings have different insertion order
- **THEN** they produce identical UTF-8 bytes and lowercase `sha256:<64 hex>` digests using code-point key order, compact JSON, NFC text, base-10 integers, and the specified escaping rules

#### Scenario: Ambiguous or pathological input is atomic
- **WHEN** input is raw JSON text, has non-string/duplicate keys, floats, bytes, custom objects, non-NFC text, integers outside signed 64-bit, depth above 16, more than 128 members per mapping, more than 256 list items, more than 4,096 nodes, a key above 256 UTF-8 bytes, a string above 32,768 UTF-8 bytes, or canonical payload size above 65,536 bytes
- **THEN** the system rejects it before grant consumption or storage

### Requirement: Messages are identified, ordered, and append-only
The system SHALL append messages with a globally unique server-generated message ID, contiguous store-assigned ordinal, bounded kind, normalized participant/source-event refs, optional valid reply ID, canonical payload/digest, and creation time, and SHALL expose no accepted-message update operation.

#### Scenario: Concurrent distinct appends are contiguous
- **WHEN** distinct valid messages append concurrently to one thread
- **THEN** each is stored once with a unique ID and contiguous ordinal in transaction order

#### Scenario: Concurrent identical append replay
- **WHEN** identical appends with one server-issued key race or retry before deletion
- **THEN** exactly one message and ordinal are created and every request returns that exact message

#### Scenario: Changed append replay conflicts
- **WHEN** the same owner reuses an active `append_message` key for different input
- **THEN** the append fails with a conflict and consumes no ordinal

#### Scenario: Reply target is already earlier in the same thread
- **WHEN** a message names a reply target
- **THEN** the target must already be committed in the same thread at a lower ordinal; a missing, cross-thread, same/future, or reply-first concurrent target fails without consuming an ordinal

### Requirement: Exact reads and export fail closed on scope or corruption
The system SHALL serialize exact read/export with writes, require fresh action authority, and reconstruct a complete thread only when canonical envelopes, indexed scope, IDs, digests, reply edges, and contiguous ordinals agree.

#### Scenario: Exact authorized ordered read
- **WHEN** a fresh read grant addresses an intact thread
- **THEN** the system returns its immutable identity and complete messages in ascending ordinal order

#### Scenario: Cross-scope request reveals nothing
- **WHEN** any owner, universe, or agent-binding scope differs
- **THEN** grant validation fails and no private record or existence signal is returned

#### Scenario: Persisted record disagrees
- **WHEN** an indexed column, canonical envelope, digest, message ID, ordinal, or reply edge has been tampered with
- **THEN** the system raises an integrity failure and returns no partial conversation

### Requirement: Private export is deterministic and isolated from the commons
The system SHALL export an exact intact thread as deterministic canonical `conversation-custody/v1` content and SHALL NOT publish it, add it to agent definitions/lineage/bindings, or include credentials, app authority, provider responses, runtime/workflow state, or effects.

#### Scenario: Repeated export is byte-stable
- **WHEN** the same intact thread is exported repeatedly without an intervening append
- **THEN** the canonical bundle bytes and digest are identical with messages ordered by ordinal and no export-time timestamp

#### Scenario: Public and binding data remain conversation-free
- **WHEN** a private thread is created, appended, read, exported, or deleted
- **THEN** no public definition/lineage or private agent-binding configuration is changed

### Requirement: Operations serialize with deletion
The system SHALL use one SQLite `BEGIN IMMEDIATE` order for create, append, exact read, export, and deletion, with commit as the linearization point.

#### Scenario: Append races deletion
- **WHEN** append and deletion overlap
- **THEN** append serialized first is included in the deletion count and removed, while deletion serialized first leaves append failing `conversation_deleted` without a write

#### Scenario: Read or export races deletion
- **WHEN** read/export and deletion overlap
- **THEN** an operation serialized first may return the pre-deletion snapshot, while one serialized after deletion reveals no content; data already returned cannot be revoked

#### Scenario: Corrupt payload remains deletable
- **WHEN** message canonical content is corrupt but authoritative scope columns still match a valid delete grant
- **THEN** deletion removes the thread without reconstructing or disclosing corrupt content; corrupt scope columns fail closed for repair

### Requirement: Deletion removes the active live-store content and records its limits
The system SHALL logically delete a thread and messages atomically, clear all content-derived idempotency state, run secure-delete plus WAL checkpoint/truncation cleanup, and return a receipt only after active-store cleanup succeeds; it SHALL explicitly exclude historical backups, snapshots, media remanence, and already-returned copies.

#### Scenario: Owner-requested deletion completes
- **WHEN** exact owner authority requests deletion with a fresh server-issued key
- **THEN** the logical-delete transaction removes the thread/messages and content-derived ledger state, active SQLite cleanup completes, and one content-free receipt is returned

#### Scenario: Premature retention deletion is refused
- **WHEN** retention-expiry deletion is requested before the stored boundary
- **THEN** the system rejects it and preserves the complete thread

#### Scenario: Cleanup interruption resumes safely
- **WHEN** a crash or busy checkpoint occurs after logical deletion but before cleanup completion
- **THEN** no content is restored or returned, no completion receipt is claimed, and an authorized retry completes the pending content-free intent

#### Scenario: Competing and changed deletion retries are deterministic
- **WHEN** delete requests race or retry
- **THEN** the same key and request returns the exact receipt, another key with the same target/reason links to that receipt, and the same key or target with a changed reason conflicts

#### Scenario: Post-deletion create or append key reuse cannot resurrect content
- **WHEN** a deleted conversation's prior create/append key is reused with identical or changed input
- **THEN** the content-free tombstone returns `conversation_deleted` without distinguishing the input; a fresh create key may create a new thread but no append can target the deleted ID

#### Scenario: Receipt and quiescent live store contain no private residue
- **WHEN** deletion reports success in a quiescent store
- **THEN** the receipt and queryable rows omit payloads, payload digests, active create/append request digests, message/result IDs, interlocutor/participant/source-event refs, reply edges, credentials, and provider IDs, and unique private sentinels are absent from the SQLite primary and sidecars

#### Scenario: Receipt states the deletion scope
- **WHEN** deletion succeeds
- **THEN** the receipt names `active_private_universe_sqlite` and states that historical backups and external copies follow separate retention/deletion policies

### Requirement: The capability remains dark until app authority integration
The system SHALL expose no production grant issuer, constructor, MCP handle, app ingress, delivery effect, provider call, or activation from this change, and future integration MUST independently authenticate organization, interlocutor, binding, custody selection/path, and delivery authority.

#### Scenario: Storage cannot deliver a message
- **WHEN** custody accepts a thread or message in tests or a future authorized caller
- **THEN** no external request, provider invocation, workflow mutation, or outbound reply occurs
