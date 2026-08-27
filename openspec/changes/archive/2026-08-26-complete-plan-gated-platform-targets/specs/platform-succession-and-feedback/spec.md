## ADDED Requirements

### Requirement: Every production dependency has a recorded successor in a machine-checkable roster

The project SHALL maintain a structured roster enumerating every production dependency whose loss would stop the platform — registrar and domain, DNS and edge configuration, hosting and deployment credentials, data-store ownership, source-repository administration, merge authority, secret custody, treasury signing, moderation authority, and bill payment. Each entry SHALL record its current holders, its named successor, the recovery procedure location, and the date it was last verified. The roster SHALL be machine-readable and SHALL be checked automatically so an entry with no successor, no recovery procedure, or a stale verification date is reported. The check SHALL report rather than block, so a gap is visible without halting unrelated work. The roster, its check, and the succession gates SHALL be repository and CI artifacts; where any of them is surfaced to a caller it SHALL route as an action under an existing canonical handle, and this capability SHALL NOT add an advertised MCP handle for succession, roster, or gate inspection.

#### Scenario: Missing successor is reported

- **WHEN** a roster entry has no named successor or no recovery-procedure location
- **THEN** the automated check reports that entry as incomplete

#### Scenario: Stale verification is reported

- **WHEN** an entry's last-verified date is older than the stated freshness window
- **THEN** the check reports it as stale rather than treating it as verified

#### Scenario: The check informs without blocking

- **WHEN** the roster check reports incomplete or stale entries
- **THEN** the report is surfaced
- **AND** unrelated work is not blocked by the report alone

#### Scenario: Succession surfaces add no handle

- **WHEN** the connector's advertised tool list is inspected after this capability ships
- **THEN** no roster, gate, or succession handle appears
- **AND** any caller-facing surfacing is dispatched as an action under an existing canonical handle

### Requirement: Succession transfers operator authority and grants no access to user content

Succession SHALL transfer authority over platform infrastructure only. Acquiring an operator role SHALL NOT, by itself, grant access to any principal's content under any custody mode, and SHALL NOT grant the ability to decrypt, retrieve, or re-key content whose custody places it outside platform reach. Where an operator legitimately requires access to platform-held user content, that access SHALL flow through the ordinary authenticated and audited authority path with the same records as any other access, and SHALL NOT be an implicit property of the succession event. The succession procedure SHALL be verifiable against this property.

#### Scenario: New operator gains infrastructure, not content

- **WHEN** an operator role is transferred to a successor
- **THEN** the successor gains the named infrastructure authority
- **AND** gains no additional access to any principal's content by virtue of the transfer

#### Scenario: Out-of-reach custody stays out of reach

- **WHEN** a successor assumes every operator role in the roster
- **THEN** content whose custody mode places it outside platform reach remains inaccessible to them

#### Scenario: Legitimate operator access is audited normally

- **WHEN** an operator accesses platform-held user content for a sanctioned purpose
- **THEN** the access is authorized and recorded through the ordinary audited authority path

### Requirement: Bus-factor gates are phase-split and executable

Continuity gates SHALL be split into a launch set and a real-value-cutover set, and each gate SHALL be an executable check producing evidence rather than an asserted claim. The launch set SHALL require the roster to be complete, the runbook to be current, the secret custody location to be recorded with a documented recovery procedure, and at least two principals holding each authority that has a shared-authority requirement. The real-value set SHALL additionally require the named human co-signers, the rehearsed multi-party signing procedure, and the named human successor for registrar authority; these SHALL NOT be satisfiable by an automated or simulated participant. A gate SHALL report which specific condition is unmet rather than a single aggregate failure.

#### Scenario: Launch gate evaluates from evidence

- **WHEN** the launch gate runs
- **THEN** each condition is evaluated against the roster, runbook, and recorded custody state
- **AND** unmet conditions are reported individually

#### Scenario: Real-value gate requires human participants

- **WHEN** the real-value-cutover gate evaluates its co-signer and successor conditions
- **THEN** an automated or simulated participant does not satisfy them
- **AND** the gate reports the condition as unmet until named humans are recorded

#### Scenario: Launch is not blocked by real-value conditions

- **WHEN** the launch gate runs before any real-value cutover
- **THEN** real-value-only conditions are not evaluated as launch blockers

### Requirement: The succession runbook is a live repository artifact whose staleness is detectable

The runbook SHALL live in the repository, SHALL cover the operator roster, secret-custody location and emergency-access procedure, the recurring cost list and payment source, redeployment-from-scratch instructions, the succession initiation procedure, the source-repository continuation procedure, and the feedback response path. It SHALL be updated through the ordinary contribution path. A change to a role grant, a secret-custody location, or a roster entry without a corresponding runbook update SHALL be detectable and reported.

#### Scenario: Role change without runbook update is reported

- **WHEN** a role grant or secret-custody location changes and the runbook is not updated
- **THEN** the staleness check reports the divergence naming the affected entry

#### Scenario: Runbook covers redeployment from nothing

- **WHEN** the runbook is evaluated for completeness
- **THEN** it contains instructions sufficient to redeploy the platform from source and recorded configuration without access to any current operator's personal machine

### Requirement: Feedback is a typed authenticated commons filing with a per-invocation attribution choice

Submitting feedback SHALL create a typed filing through the existing typed-filing contract owned by `wiki-commons`, extended by this change's MODIFIED delta against that capability rather than by a second filing mechanism. This capability SHALL NOT define a parallel identifier allocator, duplicate check, or filing schema; `wiki-commons` remains the sole owner of typed-filing identity, per-kind ID allocation, and deduplication. A feedback filing SHALL carry a feedback category, a title, a description, optional caller-supplied context, and the submitter's per-invocation choice of attributed or pseudonymous presentation. Filing SHALL require authentication like any other write; the attribution choice SHALL control presentation only and SHALL NOT remove the authenticated binding used for abuse control. Deduplication SHALL use the `wiki-commons` per-kind duplicate check so a resubmission of the same report does not mint a second identifier. This capability SHALL NOT add an advertised MCP handle for feedback; the filing routes as an action under `write_page` per the cross-capability handle invariant.

#### Scenario: Filing lands as a typed commons page

- **WHEN** an authenticated principal submits feedback with a category and description
- **THEN** a typed filing is created through the `wiki-commons` typed-filing contract with a per-kind identifier
- **AND** no second filing mechanism, identifier allocator, or duplicate check is introduced by this capability

#### Scenario: Pseudonymous presentation keeps the authenticated binding

- **WHEN** a submitter chooses pseudonymous presentation
- **THEN** the filing presents without their identity
- **AND** the authenticated binding remains available to abuse control

#### Scenario: Resubmission does not mint a second filing

- **WHEN** the same report is submitted again
- **THEN** the existing filing is returned or updated
- **AND** no second identifier is minted

#### Scenario: No feedback handle is advertised

- **WHEN** the connector's advertised tool list is inspected
- **THEN** no feedback-specific handle appears

### Requirement: Feedback context is bounded by enforcement while guidance lives in the commons

The platform SHALL apply the same visibility predicate used for reads to every **structured** element of a filing — artifact, page, node, and principal references; attachments; and any platform-derived context or summary — and SHALL refuse a filing that carries a structured element the submitter is not authorized to publish, naming the offending element rather than silently stripping it. This enforcement boundary is scoped to structured and platform-derived elements because they are the elements a read predicate can resolve. Caller-authored free-text prose SHALL NOT be subjected to content classification: the platform SHALL NOT claim to detect private material inside arbitrary pasted prose. Instead, prose SHALL pass through an explicit publication confirmation that states the filing will be publicly readable before it is created, and SHALL remain subject to post-hoc moderation and takedown on the same path as any other public commons content. Guidance about what makes a useful filing, what to redact, and which categories fit which situations SHALL be seeded remixable commons content that a user can replace or extend without platform involvement, and SHALL NOT be implemented as platform-authored policy code or as a classification gate.

#### Scenario: Unpublishable structured element is refused explicitly

- **WHEN** an attachment or a structured reference in a filing resolves to content the submitter cannot publish
- **THEN** the filing is refused with the offending element named
- **AND** the element is not silently included or silently removed

#### Scenario: Prose is confirmed for publication, not classified

- **WHEN** a submitter's free-text description is submitted
- **THEN** the platform states before creation that the filing will be publicly readable and requires explicit confirmation
- **AND** the platform does not assert that the prose has been checked for private content
- **AND** the filing remains subject to post-hoc moderation and takedown

#### Scenario: Guidance is replaceable commons content

- **WHEN** a user replaces or extends the seeded feedback guidance
- **THEN** their version is usable without platform changes
- **AND** the enforcement boundary on unpublishable content is unaffected by the replacement

### Requirement: The external tracker stays the canonical feedback queue and the commons filing is its durable staging record

The canonical feedback queue SHALL remain the external issue tracker named by the landed architecture, which states that all channels route into it and that it remains the canonical queue. A filing created through the platform SHALL be projected into that canonical queue as an outbound external effect under the platform's effect authority and receipt contract, SHALL be idempotent so retries do not create duplicates, and SHALL record its receipt and the resulting external identifier against the filing. The commons filing SHALL be a durable staging and provenance record of the submission: a projection failure SHALL NOT lose, block, or invalidate it, and it SHALL remain readable and retryable. The commons filing SHALL NOT be presented as the canonical queue, and a filing whose projection has not succeeded SHALL be reported as pending projection rather than as queued. Whether the commons filing should ever replace the external tracker as the canonical record is **not decided by this change**; it is recorded as an open question requiring a host decision, and no implementing lane may adopt the reversal without it. Inbound feedback arriving through an external channel without an authenticated submitter SHALL reach the same canonical queue, SHALL be marked lower-trust, and SHALL NOT thereby acquire the authority of an authenticated filing.

#### Scenario: Projection failure does not lose the filing

- **WHEN** projection to the canonical external queue fails
- **THEN** the staging filing is retained and readable with its projection recorded as failed
- **AND** the failure is retryable without duplicating the external record

#### Scenario: The canonical record is the external queue entry

- **WHEN** a filing's projection succeeds
- **THEN** the external queue entry is the canonical record and its identifier is resolvable from the filing
- **AND** a filing with no successful projection is reported as pending projection rather than as queued

#### Scenario: Retried projection does not duplicate

- **WHEN** a projection is retried after an uncertain outcome
- **THEN** at most one external record exists for the filing
- **AND** its receipt is recorded against the filing

#### Scenario: Unauthenticated inbound feedback is admitted but not elevated

- **WHEN** feedback arrives from an external channel with no authenticated submitter
- **THEN** it reaches the same canonical queue marked lower-trust
- **AND** it does not gain the authority of an authenticated filing
