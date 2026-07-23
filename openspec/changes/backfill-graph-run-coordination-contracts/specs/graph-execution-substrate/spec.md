## ADDED Requirements

### Requirement: Run evidence receipts are typed, bounded, and non-authoritative
The run substrate SHALL accept only `source_acquisition_receipt`, `claim_lineage_receipt`, and `revision_receipt` payloads, normalize each type's known fields, preserve unknown JSON keys, reject invalid or contradictory known fields, and enforce the positive byte cap selected by `TINYASSETS_RECEIPT_PAYLOAD_MAX_BYTES` (default 65,536 bytes). These receipts MUST remain caller-supplied evidence records: unknown keys and `extensions` round-trip without validation, signature, truth rank, certification, or external-effect authority.

#### Scenario: Source acquisition aliases and flags normalize
- **WHEN** a source receipt supplies its subject through `source_ref`, `source`, `file_ref`, or `corpus_ref`
- **THEN** the first non-empty value becomes the trimmed `source_ref` and `subject_id`, missing timestamps/string fields and six boolean acquisition flags receive their defaults, and every supplied flag must be a JSON boolean

#### Scenario: Contradictory source states are rejected
- **WHEN** `not_searched` is combined with `fetched`, `viewed`, `verified`, `snapshotted`, or `unavailable`, or `unavailable` is combined with an acquired flag
- **THEN** receipt validation fails before persistence

#### Scenario: Claim lineage and revision lists are normalized
- **WHEN** a claim-lineage receipt names a non-empty `claim_id`, or a revision receipt names at least one of `old_run_id` and `old_claim_id`
- **THEN** the corresponding evidence, changed-claim, affected-output, and rerun fields are normalized as trimmed string lists and the claim or prior-run identifier becomes the receipt subject

#### Scenario: Extensions survive without gaining authority
- **WHEN** a valid receipt includes unknown top-level keys or an `extensions` object
- **THEN** those values round-trip unchanged but the run substrate assigns them no schema validity, truth rank, or authority

#### Scenario: Serialized payload cap is enforced
- **WHEN** the normalized UTF-8 JSON payload exceeds the configured positive byte cap, or the cap is non-integer or non-positive
- **THEN** recording fails with a validation error and no receipt is inserted

### Requirement: Run receipt persistence and public actions preserve run visibility
The run substrate SHALL append a receipt only for an existing run, generating a receipt ID and created time when the caller does not supply them, and SHALL list receipts newest-first with optional exact run, receipt-type, and subject filters and a limit clamped from 1 through 1,000. The public `record_run_receipt` action MUST apply the run's current write authorization before insertion, and `list_run_receipts` MUST apply current read authorization both for one-run queries and to every row returned by unscoped enumeration.

#### Scenario: Missing run cannot receive a receipt
- **WHEN** a caller records an otherwise valid receipt for a run ID absent from the current data-root runs database
- **THEN** insertion fails even though the declared SQLite foreign key is not currently enforced

#### Scenario: Receipt filtering is bounded and newest-first
- **WHEN** receipts are listed with any combination of run ID, valid receipt type, subject ID, and limit
- **THEN** matching rows are returned by descending creation time with the limit clamped to at least 1 and at most 1,000

#### Scenario: Private run write is filtered before recording
- **WHEN** the public record action resolves an existing run that the current caller may not write
- **THEN** it returns the canonical run-write denial and does not insert a receipt

#### Scenario: Enumeration cannot leak private-run receipts
- **WHEN** the public list action is called with or without a run ID
- **THEN** a receipt is returned only when the current caller may read its owning run, with repeated receipts for one run sharing the per-request visibility result

#### Scenario: Persistence does not claim caller idempotency
- **WHEN** a caller records the same logical payload repeatedly without reusing a colliding explicit receipt ID
- **THEN** the store may append multiple receipts because it provides no caller idempotency or semantic deduplication guarantee

### Requirement: Installation-local teammate mailbox persists send, receive, and acknowledgement
The run substrate SHALL persist teammate messages with a generated message ID, existing non-empty source run, non-empty destination node, JSON-serializable body, optional reply ID, UTC sent time, and exactly one of `request`, `response`, `broadcast`, `plan_approval_request`, `plan_approval_response`, `shutdown_request`, or `shutdown_response`. It SHALL provide non-destructive receive and idempotent acknowledgement actions over the installation's shared `TINYASSETS_DATA_DIR` runs database while retaining the as-built identity, isolation, and graph-wiring limitations below.

#### Scenario: Send validates the stored message envelope
- **WHEN** a caller sends a message with an existing source run, non-empty destination, allowed type, and JSON body
- **THEN** the mailbox stores it unacknowledged and the public action returns its message ID and sent time

#### Scenario: Invalid source, type, or body is rejected
- **WHEN** the source run is absent, the message type is outside the seven-value set, or the body is not JSON-serializable
- **THEN** no teammate message is inserted

#### Scenario: Receive filters destination and broadcasts
- **WHEN** a non-empty node receives messages
- **THEN** it sees rows addressed to that node plus `*` broadcasts, optionally filtered by inclusive `since` and supplied message types, ordered from earliest sent time, and clamped to 1 through 1,000 rows

#### Scenario: Empty-node receive enumerates the data-root mailbox
- **WHEN** receive is called with an empty node ID
- **THEN** it enumerates otherwise-filtered rows in the shared data-root database rather than applying a recipient predicate

#### Scenario: Addressee or broadcast acknowledgement is idempotent
- **WHEN** the caller-supplied node ID matches the stored destination or the destination is `*`
- **THEN** acknowledgement sets the message's single global `acked` flag to true and repeated acknowledgement remains successful

#### Scenario: Wrong node cannot acknowledge a directed message
- **WHEN** the caller-supplied node ID differs from a directed message's destination
- **THEN** acknowledgement fails without changing the stored flag

#### Scenario: Current mailbox identity and reference limitations remain visible
- **WHEN** send, receive, or acknowledge is used through the public actions
- **THEN** the handlers perform no run read/write or universe-access check, the store validates no destination-node or reply-message existence, independently authenticates no sender or caller node identity beyond the surrounding tool context, stores no acknowledgement timestamp, and treats one broadcast acknowledgement as global

#### Scenario: Graph message primitives remain unwired
- **WHEN** a BranchDefinition contains `send_message_spec` or `receive_messages_spec`
- **THEN** callable helper and recipient-validation code does not make the primitive part of the compile/execution path, and its focused graph-compiler tests remain strict expected failures
