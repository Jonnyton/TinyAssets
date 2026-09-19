## ADDED Requirements

### Requirement: Cross-user delivery enters a receiver-authorized node
The engine SHALL deliver only to a receiver-owned exposed node whose current
policy permits the authenticated sending principal, and SHALL run the pinned
receiver graph from that node with receiver authority and resource admission.

#### Scenario: Receiver chooses an internal node
- **WHEN** the receiver exposes an internal node and all required ingress inputs are provided
- **THEN** delivery starts at that node and follows its receiver-defined downstream graph
- **AND** predecessor-only nodes and their effects do not execute or get edited

#### Scenario: Exposure would lose a required workspace ancestor
- **WHEN** an exposure projection removes a checkout required by its entry or downstream node
- **THEN** exposure creation fails with an actionable diagnostic before a sender can connect

#### Scenario: Sender claims someone else's identity
- **WHEN** a request or payload names a permitted user but authentication identifies a different user
- **THEN** intake rejects before copying data or enqueueing work

#### Scenario: Public foreign graph is not a receiving grant
- **WHEN** a sender can read or reuse a public workflow without a permitted exposure
- **THEN** the sender cannot cause it to execute in the foreign owner's universe

#### Scenario: Receiver authority is unavailable
- **WHEN** the receiver's required authority is absent or revoked
- **THEN** the delivery returns a defined refusal or receiver-owned pending state
- **AND** neither sender nor host credentials substitute for receiver authority

### Requirement: Delivery contracts preserve scoped exact artifacts
The engine SHALL validate receiver-defined input contracts and preserve exact
structured values and file bytes through explicit cross-owner artifact transfer,
without granting foreign session, path, credential or unrelated run access.

#### Scenario: Binary file remains usable after sender handle expires
- **WHEN** an authorized binary file is accepted and the original sender handle later expires
- **THEN** the receiving node can consume the exact accepted bytes under its own run scope
- **AND** a third user cannot read them using the delivery ID or content hash

#### Scenario: Invalid input or foreign source artifact
- **WHEN** inputs violate the advertised contract or reference an artifact the sender cannot read
- **THEN** acceptance fails explicitly without a receiver run or leaked artifact

#### Scenario: Payload contains control-looking text
- **WHEN** an accepted object contains ordinary fields named key or token, or text asking for broader authority
- **THEN** its data is preserved and remains untrusted input
- **AND** it cannot overwrite trusted sender, receiver, provider or tool authority

### Requirement: Cross-user occurrences have durable two-party outcomes
The engine SHALL associate each accepted occurrence with durable delivery intent,
at most one receiver run per numbered execution attempt and a bounded two-party
receipt, preserving identity across concurrent retries and restarts without
exposing private receiver execution details to the sender.

#### Scenario: Concurrent retry and crash recovery
- **WHEN** concurrent submissions or post-crash retries use the same link and occurrence with identical content
- **THEN** they resolve to the same accepted delivery and receiver run
- **AND** a crash between acceptance and worker execution does not create a second run

#### Scenario: Worker never started before restart
- **WHEN** recovery proves an accepted delivery's attempt never started
- **THEN** reconciliation schedules that attempt through the existing executor
- **AND** competing reconcilers cannot execute it twice or silently leave it stranded

#### Scenario: Prior execution is interrupted or ambiguous
- **WHEN** recovery cannot prove a prior attempt was never executed
- **THEN** the receipt reports interruption or ambiguity instead of successful processing
- **AND** only an explicit receiver retry creates a new numbered attempt

#### Scenario: User-authored loop sends repeated deliverables
- **WHEN** a user's node calls the delivery RPC with distinct stable occurrence IDs on successive loop iterations
- **THEN** each intended send is independent, while a retry of one occurrence is deduplicated
- **AND** existing once-per-node-per-run declared-effect semantics remain unchanged

#### Scenario: In-node delivery authority comes from the parent
- **WHEN** a node declares and calls `deliver_output` with `link_id`, `occurrence_id` and `outputs`
- **THEN** the trusted parent binds sender authority to the persisted run owner, current universe ownership, compiled branch and actual node placement
- **AND** payload-supplied identity or additional authority selectors are rejected
- **AND** cancellation is rechecked inside the handler before acceptance

#### Scenario: Accepted transfer survives later source failure
- **WHEN** a node's transfer commits and its source run later fails or is cancelled
- **THEN** the accepted transfer and truthful receiver outcome remain inspectable
- **AND** the source write settlement cannot be downgraded by later read settlement

#### Scenario: Direct-send legacy identity is not relabeled
- **WHEN** a direct send uses a key equal to an in-node derived occurrence identity
- **THEN** differing source-run provenance returns occurrence conflict instead of reusing or relabeling the original delivery
- **AND** existing direct keys and receipt fields remain compatible

#### Scenario: Owned private composition does not borrow co-admin authority
- **WHEN** an owned definition invokes its owner's private child
- **THEN** the parent and child definition authors must both equal the frozen persisted owner, who still administers that universe, and the persisted parent row must match context and be running
- **AND** foreign/public provenance or a different co-admin's parent cannot acquire private-child access through the runner's identity
- **AND** nested delivery uses the child's own run and actual placement

#### Scenario: Intentional identical sends and changed replay
- **WHEN** identical content is sent using two distinct occurrence IDs
- **THEN** two deliveries can be accepted
- **AND** reusing either ID with different content returns occurrence_conflict

#### Scenario: Link or receiver revoked
- **WHEN** a sender disconnects or a receiver revokes before a new occurrence is accepted
- **THEN** no new receiver run is created for that occurrence
- **AND** prior accepted transfers remain inspectable by their authorized parties

#### Scenario: Processing fails after acceptance
- **WHEN** an accepted receiver run fails
- **THEN** the receipt distinguishes failure from successful processing and supplies a safe reason
- **AND** sender inspection cannot reveal receiver credentials, private outputs or raw logs
- **AND** sender responses and ledger entries identify the delivery, not the private receiver run
