## ADDED Requirements

### Requirement: OpenSpec drain blockers become suppressible only after durable current-main classification
The OpenSpec drain supervisor SHALL treat a worker `BLOCKED` marker as valid only when a fresh exact `origin/main` claim-check snapshot classifies the same canonical target as blocked. Claim-check snapshots MUST preserve the complete normalized task label, and the supervisor's bounded target identity MUST remain distinct for labels that share a long prefix. The worker MUST first land a sanitized STATUS dependency or blocker through normal repository review. A target that remains claimable or stale, disappears without explicit blocked classification, or cannot be checked because current-main refresh fails SHALL NOT enter the recent-blocked set. The supervisor MUST retain any prepared admission, record a bounded invalid-blocked failure, and send a fresh worker back to the same lane within the existing failure budget.

#### Scenario: Worker reports a blocker that exists only in its result file
- **WHEN** an admitted worker returns `BLOCKED` but current main still classifies the target claimable
- **THEN** the supervisor rejects the result as `INVALID_BLOCKED_RESULT`
- **AND** retains the admission without adding the target to recent blockers

#### Scenario: Worker lands sanitized blocker truth
- **WHEN** an admitted worker returns `BLOCKED` and fresh current main classifies the same canonical target blocked
- **THEN** the supervisor accepts the blocked result, releases active admission, and may select different work

#### Scenario: Blocker verification cannot refresh current main
- **WHEN** origin refresh or current-main claim classification fails after a `BLOCKED` marker
- **THEN** the supervisor rejects the marker and preserves the admission rather than trusting stale or private evidence

#### Scenario: Worker deletes the target instead of recording a blocker
- **WHEN** a `BLOCKED` marker names a target absent from the fresh current-main blocked collection
- **THEN** the supervisor rejects the result and does not treat disappearance as blocker proof

#### Scenario: Distinct labels share a long prefix
- **WHEN** a blocked row and a claimable row have task labels that differ only after a long common prefix
- **THEN** claim-check preserves both complete labels and the supervisor derives distinct bounded target identities
- **AND** the blocked row cannot authorize or cool down the claimable row

#### Scenario: Pre-hash run resumes with a long-label admission
- **WHEN** persisted state predates collision-resistant target identity
- **THEN** the supervisor rekeys the admission and resume target from its complete task label
- **AND** releases legacy recent-blocked slugs that cannot be translated safely

#### Scenario: Recent blockers consume every concrete candidate hint
- **WHEN** current-main pressure still reports claimable or stale rows, no owned or prepared admission exists, and filtering this run's recent blockers leaves no concrete hint
- **THEN** the supervisor records a bounded blocked cooldown and waits before refreshing
- **AND** it does not launch a full write-capable no-hint worker

#### Scenario: A different candidate remains after filtering
- **WHEN** recent blockers are filtered and another concrete claimable or stale candidate remains
- **THEN** the controller admits and dispatches that candidate under the existing current-main contract

#### Scenario: A durable blocker clears
- **WHEN** a target in the run's recent-blocked set is no longer classified blocked by fresh current main
- **THEN** the controller removes its run-local suppression before candidate filtering
- **AND** may admit that target again under the ordinary candidate contract

#### Scenario: Blocker retry and cooldown remain observable
- **WHEN** a live controller is cooling down or retrying an invalid private blocker
- **THEN** watchdog health reports waiting rather than ordinary running
- **AND** an ended invalid-blocker diagnostic reports failure

### Requirement: Verified merge receipts are idempotent per run
The OpenSpec drain supervisor SHALL advance completed-slice progress at most once for a canonical verified merged pull-request identity. Owner and repository casing plus numeric formatting of the pull-request number MUST NOT create a distinct identity. It MUST persist every successful receipt for the bounded run and reconstruct canonical verified receipts only for legacy result artifacts whose supervisor audit records successful merge consumption. Result text or current merge state alone MUST NOT turn a previously failed verification into a consumed receipt. `PARTIAL` SHALL NOT consume the merge receipt because later foldback may legitimately return `MERGED` for the same pull request.

#### Scenario: Worker replays an already consumed merged PR
- **WHEN** a worker returns `MERGED` with a canonical PR identity already present in the run's verified merge receipts
- **THEN** the controller records `INVALID_DUPLICATE_MERGE`
- **AND** does not advance completed slices or release a prepared admission

#### Scenario: Legacy run resumes after merged work
- **WHEN** run state predates the merge-receipt field
- **THEN** the controller reconstructs the complete run-bounded unique canonical receipt set from successfully consumed result artifacts and their supervisor audit records
- **AND** trusts only PRs that still pass controller merge verification

#### Scenario: Previously failed merge verification later becomes merged
- **WHEN** a consumed legacy result reported `MERGED` but its supervisor audit records `merge-verification-failed`
- **THEN** receipt reconstruction does not consume that PR
- **AND** a later verified `MERGED` retry may advance one slice

#### Scenario: Partial foldback later completes
- **WHEN** a verified `PARTIAL` result is followed by `MERGED` for the same PR after foldback
- **THEN** the `MERGED` result may advance one slice because `PARTIAL` did not consume its receipt
