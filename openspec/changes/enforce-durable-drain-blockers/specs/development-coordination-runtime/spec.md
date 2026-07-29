## ADDED Requirements

### Requirement: OpenSpec drain blockers become suppressible only after durable current-main classification
The OpenSpec drain supervisor SHALL treat a worker `BLOCKED` marker as valid only when a fresh exact `origin/main` claim-check snapshot classifies the same canonical target as blocked. The worker MUST first land a sanitized STATUS dependency or blocker through normal repository review. A target that remains claimable or stale, disappears without explicit blocked classification, or cannot be checked because current-main refresh fails SHALL NOT enter the recent-blocked set. The supervisor MUST retain any prepared admission, record a bounded invalid-blocked failure, and send a fresh worker back to the same lane within the existing failure budget.

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

#### Scenario: Recent blockers consume every concrete candidate hint
- **WHEN** current-main pressure still reports claimable or stale rows, no owned or prepared admission exists, and filtering this run's recent blockers leaves no concrete hint
- **THEN** the supervisor records a bounded blocked cooldown and waits before refreshing
- **AND** it does not launch a full write-capable no-hint worker

#### Scenario: A different candidate remains after filtering
- **WHEN** recent blockers are filtered and another concrete claimable or stale candidate remains
- **THEN** the controller admits and dispatches that candidate under the existing current-main contract
