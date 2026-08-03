## ADDED Requirements

### Requirement: Custody mode remains explicit and replaceable
The system SHALL represent private conversation custody with a versioned contract and explicit provider mode, and the first implementation SHALL store `private_universe` data only inside the selected universe directory without making that mode a closed list or universal default.

#### Scenario: Private-universe placement
- **WHEN** the `private_universe` provider is constructed for a selected universe
- **THEN** it stores conversation state in that universe directory and refuses a context naming another universe

#### Scenario: Future custody mode is not silently selected
- **WHEN** a caller requests an unsupported custody mode
- **THEN** the system fails explicitly without writing data or falling back to `private_universe`

### Requirement: Authenticated internal context scopes every operation
The system SHALL require one bounded internal context containing the authenticated owner, universe, and agent-binding identifiers for every thread creation, append, read, export, and deletion operation, and SHALL NOT treat raw app-provider identifiers as authority.

#### Scenario: Exact context succeeds
- **WHEN** a caller uses the same owner, universe, and agent-binding context that created a thread
- **THEN** the caller can address that exact thread through the internal custody contract

#### Scenario: Cross-scope access is indistinguishable from absence
- **WHEN** any owner, universe, or agent-binding identifier differs from the stored context
- **THEN** read and export return no private record and append or deletion writes nothing

#### Scenario: Raw transport identity is not stored as authority
- **WHEN** an upstream app adapter supplies a message after authentication
- **THEN** the custody record contains only bounded normalized internal participant and source-event references, not an app credential, installation grant, or raw provider authority object

### Requirement: Threads are immutable and idempotent
The system SHALL create an immutable conversation thread with a server-generated identifier, exact custody contract/mode, owner, universe, agent binding, normalized interlocutor reference, explicit retention boundary, and creation time under owner-scoped request-bound idempotency.

#### Scenario: Identical create replay
- **WHEN** the same owner retries a thread creation with the same idempotency key and identical input
- **THEN** the system returns the exact existing thread and creates no additional row

#### Scenario: Changed create replay conflicts
- **WHEN** the same owner reuses a thread-creation idempotency key with different input
- **THEN** the system reports a conflict and preserves the original thread unchanged

#### Scenario: Thread has no mutation path
- **WHEN** a thread has been accepted
- **THEN** its identity, scope, interlocutor, custody mode, and retention boundary cannot be updated

### Requirement: Messages are bounded, canonical, ordered, and append-only
The system SHALL append messages as canonical JSON envelopes with a store-assigned contiguous ordinal, bounded message kind, normalized participant and source-event references, optional same-thread reply reference, bounded arbitrary JSON payload, payload digest, and creation time, and SHALL expose no accepted-message update operation.

#### Scenario: Append preserves portable payload
- **WHEN** a valid message contains an unknown but JSON-compatible payload member within all bounds
- **THEN** the system preserves that member exactly in subsequent reads and export

#### Scenario: Concurrent distinct appends are contiguous
- **WHEN** distinct valid messages append concurrently to one thread
- **THEN** each message is stored once with a unique contiguous ordinal and deterministic ordinal ordering

#### Scenario: Identical append replay
- **WHEN** the same owner retries an append with the same idempotency key and identical input
- **THEN** the exact existing message is returned without allocating another ordinal

#### Scenario: Changed append replay conflicts
- **WHEN** the same owner reuses a message idempotency key with different input
- **THEN** the append fails with a conflict and the existing message remains unchanged

#### Scenario: Invalid or oversized payload is atomic
- **WHEN** a payload is non-canonical, exceeds 64 KiB, exceeds structural bounds, or contains a reply reference outside the thread
- **THEN** the system rejects it without writing a message or consuming an ordinal

### Requirement: Exact reads and export fail closed on corruption
The system SHALL reconstruct threads and messages only when canonical envelopes, indexed identity columns, digests, reply lineage, and ordinals agree, and SHALL fail closed rather than return partial private history when persisted state is corrupt.

#### Scenario: Exact ordered read
- **WHEN** the authenticated context reads an intact thread
- **THEN** the system returns its immutable identity and all messages in ascending contiguous ordinal order

#### Scenario: Persisted record disagrees
- **WHEN** an indexed column, canonical envelope, digest, or ordinal has been tampered with
- **THEN** the system raises an integrity failure and returns no partial conversation

### Requirement: Private export is deterministic and isolated from the commons
The system SHALL export an exact thread as a deterministic `conversation-custody/v1` JSON-compatible private bundle and SHALL NOT publish it, add it to agent definitions or component lineage, or include credentials, app-installation authority, provider responses, runtime state, workflow state, or effect records.

#### Scenario: Repeated export is deterministic
- **WHEN** the same intact thread is exported repeatedly without intervening appends
- **THEN** each export has identical canonical content with messages ordered by ordinal

#### Scenario: Public agent data remains conversation-free
- **WHEN** a private thread is created, appended, read, or exported
- **THEN** no public agent definition, public remix lineage, or private agent-binding configuration is changed

### Requirement: Deletion removes private content and retains a minimal receipt
The system SHALL delete a thread and all message content atomically on an authenticated owner request or after its retention boundary, then retain only an immutable idempotent receipt containing scope identifiers, deletion reason and time, and deleted-message count without content-derived or transport-derived private material.

#### Scenario: Owner-requested deletion
- **WHEN** the exact authenticated owner requests deletion with a fresh idempotency key
- **THEN** the thread and every message become unreadable and unexportable in the same transaction and one receipt is returned

#### Scenario: Premature retention deletion is refused
- **WHEN** retention-expiry deletion is requested before the stored boundary
- **THEN** the system rejects the request and preserves the complete thread

#### Scenario: Exact deletion replay
- **WHEN** the owner retries the same deletion request with the same idempotency key and target
- **THEN** the exact existing receipt is returned without creating another receipt

#### Scenario: Deletion receipt contains no private residue
- **WHEN** deletion completes
- **THEN** the receipt omits payloads, payload digests, source-event references, interlocutor references, reply lineage, credentials, and provider identifiers

### Requirement: The capability remains dark until app authority integration
The system SHALL expose no MCP handle, app ingress, delivery effect, provider call, or production activation from this change, and a future app-conversation integration MUST provide independently authenticated organization, interlocutor, binding, and delivery authority before using custody records.

#### Scenario: Storage owner cannot deliver a message
- **WHEN** conversation custody accepts a thread or message
- **THEN** no external request, provider invocation, workflow mutation, or outbound reply occurs
