## ADDED Requirements

### Requirement: Community flagging is authenticated, bounded, and duplicate-safe
The system SHALL let an authenticated account flag a public commons artifact or outcome claim with a reason and optional detail. It SHALL accept at most one open flag from the same actor for the same artifact, SHALL apply configured account-age or completed-interaction eligibility before a flag contributes to automated thresholds, and SHALL enforce a per-account flag rate limit. A rejected, duplicate, or rate-limited flag SHALL NOT increment the artifact's distinct-flagger count.

#### Scenario: Eligible account files its first flag
- **WHEN** an authenticated eligible account flags a supported public artifact within its rate limit
- **THEN** one open flag is recorded with actor, artifact, reason, detail, and timestamp
- **AND** the distinct-flagger count increases by one

#### Scenario: Duplicate flag does not amplify one actor
- **WHEN** the same actor files another open flag against the same artifact
- **THEN** the request is rejected or returns the existing flag idempotently
- **AND** the distinct-flagger count remains unchanged

#### Scenario: Ineligible or rate-limited flag has no threshold effect
- **WHEN** an account fails the configured age/interaction gate or exceeds its flag bucket
- **THEN** the system returns a bounded refusal with retry or eligibility evidence
- **AND** no contributing flag is written

### Requirement: Distinct community flags cause reversible soft-hide, not deletion
The system SHALL compare eligible open flags from distinct actors with a configurable soft-hide threshold. Crossing the threshold SHALL move the artifact to an `under_review` or equivalent non-discoverable state atomically with the threshold-crossing flag. Soft-hidden content SHALL remain visible to its owner and authorized reviewers, SHALL preserve its content and provenance, and SHALL NOT be hard-deleted merely because a threshold was crossed.

#### Scenario: Threshold crossing soft-hides once
- **WHEN** concurrent eligible flags make the distinct-flagger count cross the configured threshold
- **THEN** exactly one visible-to-under-review transition is recorded
- **AND** the artifact disappears from ordinary discovery without being deleted

#### Scenario: A single report cannot hide content
- **WHEN** the number of distinct eligible flaggers remains below threshold
- **THEN** the artifact remains ordinarily discoverable

#### Scenario: Owner can inspect a soft-hidden artifact
- **WHEN** an artifact is under review
- **THEN** its owner and authorized reviewers can read the artifact, flag count, and review status
- **AND** unrelated users cannot discover it through ordinary public listing

### Requirement: Review authority is explicit, renewable, and conflict-free
The system SHALL grant review authority only to authenticated actors satisfying a configured contributor or earned-reliability policy and accepting the current community-owned moderation rubric version. Review authority SHALL expire or require re-acceptance when policy says so, SHALL be revocable, and SHALL NOT be inferred from a username, host environment variable, daemon ownership, or self-asserted tier. A reviewer SHALL NOT decide a flag or appeal involving an artifact they own or a decision they authored.

#### Scenario: Eligible reviewer accepts the current rubric
- **WHEN** an authenticated actor satisfies the configured eligibility rule and explicitly accepts the current rubric version
- **THEN** review authority is granted with actor, rubric version, grant source, and expiry or renewal evidence

#### Scenario: Stale rubric acceptance cannot authorize review
- **WHEN** a reviewer has not accepted the currently required rubric version
- **THEN** a decision attempt fails closed without changing flag or artifact state

#### Scenario: Reviewer recuses from own artifact
- **WHEN** a reviewer attempts to resolve a flag on an artifact they own
- **THEN** the system refuses the decision and records no moderation transition

### Requirement: Review decisions preserve rationale, independence, and reversible state
The system SHALL support dismissal, continued soft-hide, escalation, and proposed hard-delete decisions with a non-empty rationale and immutable reviewer attribution. A dismissal SHALL close the applicable open flags and restore ordinary discovery when no other active moderation hold remains. Hard-delete SHALL require concurrence by at least two distinct authorized reviewers; the first concurrence SHALL retain the artifact in reversible hidden state. Conflicting reviewer decisions SHALL escalate rather than select a winner by arrival order.

#### Scenario: Dismissal restores discovery
- **WHEN** an authorized independent reviewer dismisses the flags that caused soft-hide and no other hold remains
- **THEN** the flags close, the artifact returns to ordinary discovery, and the rationale remains auditable

#### Scenario: One reviewer cannot hard-delete
- **WHEN** one authorized reviewer proposes hard-delete
- **THEN** the artifact remains recoverably hidden pending a second independent concurrence

#### Scenario: Second distinct reviewer concurs
- **WHEN** a second eligible reviewer who is neither the owner nor the first reviewer independently concurs
- **THEN** the artifact leaves public and owner-editable surfaces under the configured recoverable-delete policy
- **AND** an immutable decision/audit record survives

#### Scenario: Reviewers disagree
- **WHEN** independent reviewers produce conflicting terminal recommendations
- **THEN** the case enters the council/escalation queue without deleting the artifact

### Requirement: Artifact owners have a durable independent appeal path
The system SHALL let an artifact owner appeal any hide or delete decision once per decision revision with a message. An appeal SHALL be reviewed by an authorized actor who did not author the appealed decision and, for a terminal deletion, by the configured moderator council/quorum. Appeal resolution SHALL record rationale and SHALL be able to restore a recoverable artifact without erasing the original decision history.

#### Scenario: Owner appeals a hide
- **WHEN** an artifact owner submits the first appeal for the current decision revision
- **THEN** the system records the appeal, links it to the decision, and places it in an independent review queue

#### Scenario: Original reviewer cannot resolve the appeal
- **WHEN** the reviewer who authored the appealed decision attempts to resolve it
- **THEN** authorization fails closed and the appeal remains pending

#### Scenario: Appeal overturns a recoverable deletion
- **WHEN** the authorized appeal quorum overturns a deletion before retention expires
- **THEN** the artifact is restored with its identity and provenance
- **AND** the decision and appeal histories remain visible to authorized readers

### Requirement: Terminal powers have a multi-operator recovery boundary
Hard-delete, account suspension/ban, moderator-role grant/revocation, and appeal override SHALL require a configured council or equivalent multi-operator authorization boundary rather than a host-only production button. The production readiness gate SHALL require at least two independently authenticated operators with equivalent emergency authority and a tested rotation/recovery procedure. Bootstrap identities SHALL be deployment data, not hardcoded user names.

#### Scenario: One operator attempts a terminal override
- **WHEN** council policy requires quorum and only one operator authorizes a terminal action
- **THEN** the action remains pending or is refused without changing terminal state

#### Scenario: Operator credential is rotated
- **WHEN** one council credential is revoked and a replacement is enrolled through the authorized process
- **THEN** the old credential immediately loses authority and quorum operation continues without a host-only fallback

### Requirement: Abuse controls bound high-leverage writes without becoming content classifiers
The system SHALL enforce configurable per-account limits for public artifact creation/update, paid-request posting, and other high-leverage commons writes at the authoritative mutation boundary. It SHALL support account-age or completed-interaction gates for high-leverage actions and emit bounded anomaly signals for human review, including young-account high-volume activity. It SHALL NOT automatically classify or remove legal content based on an opaque model score; automated behavior is limited to structural limits, reversible soft-hide thresholds, and review-queue signals.

#### Scenario: High-volume writer exceeds its bucket
- **WHEN** an account exceeds a configured authoritative write bucket
- **THEN** the next write is rejected with a retry boundary and no partial artifact mutation

#### Scenario: Anomaly signal does not become a takedown
- **WHEN** a young account triggers the configured high-volume anomaly rule
- **THEN** a review signal is recorded
- **AND** no content is deleted or banned solely from that signal

#### Scenario: Paid request lacks reserved authority
- **WHEN** a paid request requires reserved settlement authority and reservation fails
- **THEN** the request is not published as payable work
- **AND** moderation does not invent a separate settlement path

### Requirement: Moderator quality controls are evidence-based and non-punitive by default
The system SHALL maintain reviewer/flagger quality evidence from resolved cases without exposing secret or private artifact content. A configured sustained low-accuracy threshold MAY revoke volunteer review authority or de-prioritize future flags, but SHALL NOT silently ban the account, rewrite prior decisions, or remove the user's ordinary right to appeal. Any automated role change SHALL be notified and auditable.

#### Scenario: Sustained low flag accuracy crosses the configured boundary
- **WHEN** a volunteer meets the configured minimum resolved-case sample and falls below the configured accuracy threshold
- **THEN** volunteer review authority is revoked or suspended with an auditable reason and notification
- **AND** the account retains ordinary authenticated user rights

#### Scenario: Insufficient sample does not demote
- **WHEN** the resolved-case sample is below the configured minimum
- **THEN** no automated role demotion occurs from the incomplete metric

### Requirement: Moderation evidence and state changes are observable across affected surfaces
The system SHALL expose bounded moderation status to the artifact owner, authorized reviewers, and public discovery as appropriate without exposing reporter secrets or private content. Every flag transition, review decision, appeal, role change, and terminal action SHALL carry an immutable actor/time/reason audit event. Public audit views MAY redact reporter identity and sensitive evidence while preserving decision accountability.

#### Scenario: Public user sees an under-review marker
- **WHEN** a previously discoverable artifact is soft-hidden
- **THEN** a direct public reference returns an `under_review` or equivalent bounded status rather than silently pretending the artifact never existed

#### Scenario: Authorized audit reconstructs a case
- **WHEN** an authorized reviewer reads a completed case
- **THEN** the ordered flag, decision, appeal, role, and artifact-state events reconstruct the transition history without relying on mutable current rows alone

### Requirement: Moderation completion includes concurrent and degraded-mode proof
The capability SHALL NOT be considered implemented until automated proof exercises concurrent distinct flags at the soft-hide boundary, competing reviewer decisions, two-reviewer hard-delete, simultaneous appeal/decision activity, rate-limit races, queue growth, and storage or notification failures. The proof SHALL show no lost flag, duplicate terminal transition, single-reviewer delete, cross-tenant disclosure, or fail-open authorization, and SHALL record bounded queue latency and recovery behavior at the declared target load.

#### Scenario: Concurrent threshold and review traffic
- **WHEN** the declared §14 load sends flags and review decisions against hot and unrelated artifacts concurrently
- **THEN** each artifact reaches a serializable policy-valid state
- **AND** unrelated artifacts and tenants do not block or leak into one another beyond the declared bounds

#### Scenario: Notification delivery fails
- **WHEN** a moderation state transition commits but owner notification fails
- **THEN** authoritative moderation state remains committed, the notification failure is observable/retryable, and the system does not roll back or duplicate the decision
