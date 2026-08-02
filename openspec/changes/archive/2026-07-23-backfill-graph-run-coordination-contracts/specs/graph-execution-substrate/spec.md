## ADDED Requirements

### Requirement: Run evidence receipts are typed, bounded, and non-authoritative
The run substrate SHALL accept only `source_acquisition_receipt`, `claim_lineage_receipt`, and `revision_receipt` payloads; normalize their type-specific known fields; reject missing required subject identifiers, non-list or non-string list values, non-boolean source flags, and the defined source-state contradictions; and preserve unknown keys and JSON-compatible values. Values supplied directly that are not JSON-compatible MAY be stringified during sizing and persistence and therefore have no byte-for-byte round-trip guarantee. The substrate SHALL enforce the positive cap selected by `TINYASSETS_RECEIPT_PAYLOAD_MAX_BYTES` (default 65,536 bytes) against its compact, sorted UTF-8 JSON size-check encoding. These receipts MUST remain caller-supplied evidence records: unknown keys and `extensions` gain no validation, signature, truth rank, certification, or external-effect authority.

#### Scenario: Source acquisition aliases and flags normalize
- **WHEN** a source receipt supplies its subject through `source_ref`, `source`, `file_ref`, or `corpus_ref`
- **THEN** the first truthy value in precedence order `source_ref`, `source`, `file_ref`, `corpus_ref` is stringified and trimmed; if that selected value trims empty, validation fails without consulting later aliases; otherwise it becomes `source_ref` and `subject_id`, missing timestamps/string fields and six boolean acquisition flags receive their defaults, and every supplied flag must be a JSON boolean

#### Scenario: Contradictory source states are rejected
- **WHEN** `not_searched` is combined with `fetched`, `viewed`, `verified`, `snapshotted`, or `unavailable`, or `unavailable` is combined with an acquired flag
- **THEN** receipt validation fails before persistence

#### Scenario: Claim lineage and revision lists are normalized
- **WHEN** a claim-lineage receipt names a non-empty `claim_id`, or a revision receipt names at least one of `old_run_id` and `old_claim_id`
- **THEN** claim lineage trims `claim_id`, normalizes `evidence_refs`, `imported_prior_run_claims`, `counter_evidence_refs`, and `changed_claims`, and uses `claim_id` as `subject_id`; revision trims `old_run_id` and `old_claim_id`, normalizes `new_evidence_refs`, `affected_outputs`, and `recommended_reruns`, and uses non-empty `old_claim_id` as `subject_id` before falling back to `old_run_id`

#### Scenario: Extensions survive without gaining authority
- **WHEN** a valid receipt includes unknown top-level keys or an `extensions` object
- **THEN** JSON-compatible values round-trip unchanged and receive no schema validity, truth rank, or authority, while a directly supplied non-JSON-compatible value may be stringified

#### Scenario: Compact size-check payload cap is enforced
- **WHEN** the compact sorted UTF-8 JSON encoding used by the size checker exceeds the configured positive byte cap, or the cap is non-integer or non-positive
- **THEN** recording fails with a validation error and no receipt is inserted, without claiming that the separately encoded on-disk `payload_json` blob is bounded to the same byte count

### Requirement: Run receipt persistence and public actions preserve run visibility
The run substrate SHALL append a receipt only for an existing run, generating a receipt ID when none is supplied and always assigning the current creation time, and SHALL list receipts newest-first with optional exact run, receipt-type, and subject filters and a limit clamped from 1 through 1,000. For a run whose actor begins `universe:` and has a non-empty trimmed suffix, the public `record_run_receipt` action MUST derive that universe and apply its current write authorization before insertion, and `list_run_receipts` MUST apply its current read authorization both for one-run queries and to every resolvable row during unscoped enumeration. As-built limitations: a non-universe actor string or `universe:` with an empty suffix currently passes these helpers without a general run-owner ACL check, and because the foreign key is unenforced, a receipt whose run record later disappears passes the current `rec is None or _run_read_allowed(rec)` visibility predicate.

#### Scenario: Missing run cannot receive a receipt
- **WHEN** a caller records an otherwise valid receipt for a run ID absent from the current data-root runs database
- **THEN** insertion fails even though the declared SQLite foreign key is not currently enforced

#### Scenario: Receipt filtering is bounded and newest-first
- **WHEN** receipts are listed with any combination of run ID, valid receipt type, subject ID, and limit
- **THEN** matching rows are returned by descending creation time with the limit defaulting to 100 and clamped to at least 1 and at most 1,000

#### Scenario: Public receipt list normalizes invalid limits
- **WHEN** the public list action receives a missing or falsey limit, or a value that `int()` cannot convert
- **THEN** it uses the default limit of 100 before the storage-layer clamp

#### Scenario: Private universe-bound run write is filtered before recording
- **WHEN** the public record action resolves an existing `universe:<uid>` run whose universe the current caller may not write
- **THEN** it returns the canonical run-write denial and does not insert a receipt

#### Scenario: Enumeration filters private universe-bound receipts
- **WHEN** the public list action is called with or without a run ID
- **THEN** a receipt whose run still resolves to a `universe:<uid>` actor is returned only when the current caller may read that universe, with repeated receipts for one run sharing the per-request visibility result

#### Scenario: Non-universe run actors bypass resource ACL derivation
- **WHEN** a receipt's resolvable run actor does not begin `universe:` or its suffix trims empty
- **THEN** the current receipt access helpers treat the row as allowed without deriving a universe or checking a general run-owner ACL

#### Scenario: Orphan receipt visibility is not fail-closed
- **WHEN** an unenforced or externally altered data-root leaves a receipt whose referenced run row no longer resolves
- **THEN** the current public list predicate treats that orphan receipt as visible rather than failing closed

#### Scenario: Persistence does not claim caller idempotency
- **WHEN** a caller records the same logical payload repeatedly without reusing a colliding explicit receipt ID
- **THEN** the store may append multiple receipts because it provides no caller idempotency or semantic deduplication guarantee

### Requirement: Installation-local teammate mailbox persists send, receive, and acknowledgement
The run substrate SHALL persist teammate messages with a generated message ID, existing non-empty source run, non-empty destination node, JSON-serializable body, optional reply ID, UTC sent time, and exactly one of `request`, `response`, `broadcast`, `plan_approval_request`, `plan_approval_response`, `shutdown_request`, or `shutdown_response`. It SHALL provide non-destructive receive and idempotent acknowledgement actions over the installation's shared `TINYASSETS_DATA_DIR` runs database while retaining the as-built identity, isolation, and graph-wiring limitations below.

#### Scenario: Send validates the stored message envelope
- **WHEN** a caller sends a message with an existing source run, non-empty destination, allowed type, and JSON body
- **THEN** the mailbox stores it unacknowledged and the public action returns `message_id` plus `delivered_at` equal to the stored `sent_at`

#### Scenario: Invalid source, destination, type, or body is rejected
- **WHEN** the source run is absent, the source or destination ID is empty, the message type is outside the seven-value set, or the body is not JSON-serializable
- **THEN** no teammate message is inserted

#### Scenario: Receive filters destination and broadcasts
- **WHEN** a non-empty node receives messages
- **THEN** it sees rows addressed to that node plus `*` broadcasts, optionally filtered by inclusive `since` and supplied message types, ordered from earliest sent time, with a default limit of 50 clamped to 1 through 1,000 rows

#### Scenario: Unconvertible public mailbox limit can escape the handler
- **WHEN** the public receive action receives a limit value that `int()` cannot convert
- **THEN** its eager conversion may raise before the handler's JSON error wrapper rather than returning a normalized error envelope, while integer-convertible values are coerced successfully

#### Scenario: Empty-node receive enumerates the data-root mailbox
- **WHEN** receive is called with an empty node ID
- **THEN** it enumerates otherwise-filtered rows in the shared data-root database rather than applying a recipient predicate

#### Scenario: Addressee or broadcast acknowledgement is idempotent
- **WHEN** the caller-supplied node ID matches the stored destination or the destination is `*`
- **THEN** acknowledgement sets the message's single global `acked` flag to true and repeated acknowledgement remains successful

#### Scenario: Wrong node cannot acknowledge a directed message
- **WHEN** the caller-supplied node ID differs from a directed message's destination
- **THEN** acknowledgement fails without changing the stored flag

#### Scenario: Public acknowledgement validates required identifiers
- **WHEN** the public acknowledgement action receives an empty message ID or node ID, or the message ID does not exist
- **THEN** it returns an error and does not modify a mailbox row

#### Scenario: Current mailbox identity and reference limitations remain visible
- **WHEN** send, receive, or acknowledge is used through the public actions
- **THEN** the handlers perform no run read/write or universe-access check, the store validates no destination-node or reply-message existence, independently authenticates no sender or caller node identity beyond the surrounding tool context, stores no acknowledgement timestamp, and treats one broadcast acknowledgement as global

#### Scenario: Graph message helpers are callable but detached from Branch execution
- **WHEN** the send, receive, or recipient-validation helper is called directly
- **THEN** its focused helper behavior is available
- **AND** current `NodeDefinition` and `BranchDefinition` shapes expose no message-spec field and `compile_branch` never invokes these helpers, so compiled graph execution is not wired
