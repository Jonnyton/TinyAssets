## MODIFIED Requirements

### Requirement: OpenSpec drain refines visible backlog before idle
When owned, claimable, and policy-qualified stale STATUS candidates are absent, the drain supervisor SHALL inspect exact-current-main OpenSpec flow and SHALL provide one bounded existing-change refinery target before accepting candidate exhaustion. Refinery admission MUST exclude live-owned, host-owned, and invalid-artifact changes, MUST authorize coordination reconciliation only, and MUST NOT authorize product implementation before a normal current-main claim exists. The refinery SHALL model the exact next delivery slice rather than whole-change completion: its `Depends` cell MUST contain only unresolved prerequisites that must land before that slice can begin, while later testing, review, deployment, rendered acceptance, and organic-use gates remain in the slice acceptance text or OpenSpec tasks. Before returning `BLOCKED`, the refinery MUST inspect unchecked tasks for a bounded executable slice and then the shortest concrete autonomous prerequisite-removal slice. A verified `PARTIAL` refinery result SHALL be accepted as a continuation only when fresh current main exposes a claimable row overlapping the assigned change boundary.

#### Scenario: STATUS is blocked while untracked changes remain
- **WHEN** claim pressure is zero and exact current main contains an incomplete untracked OpenSpec change
- **THEN** the next worker brief names that change as a refinery target
- **AND** `NO_CANDIDATE` is rejected while that target remains refinable

#### Scenario: Active status omits a provider identity
- **WHEN** an otherwise refinery-eligible change has a matching bare `in-flight` STATUS row
- **THEN** the supervisor excludes that change from refinery admission even though no named owner can be extracted

#### Scenario: Refinery promotes bounded implementation work
- **WHEN** the refinery worker proves one existing change has a safe bounded acceptance contract
- **THEN** it lands one exact pending STATUS row whose `Depends` names only prerequisites required before that slice can start
- **AND** downstream verification and release gates do not make that earlier slice non-claimable
- **AND** a fresh worker performs ordinary collision checking and claim admission before product edits

#### Scenario: Direct slice is blocked but an autonomous prerequisite is available
- **WHEN** the selected implementation slice cannot start yet
- **AND** a bounded non-overlapping prerequisite-removal slice can run without host-only authority or a live foreign claim
- **THEN** the refinery promotes that prerequisite-removal slice as the next claimable row
- **AND** it does not record the whole legacy change as globally blocked

#### Scenario: Refinery proves a durable blocker
- **WHEN** no bounded unchecked-task slice and no concrete autonomous prerequisite-removal slice can begin because of a current host, dependency, policy, review, or live-claim gate
- **THEN** the worker lands that immediate blocker on the exact STATUS row before returning `BLOCKED`
- **AND** recent-block suppression prevents immediate repetitive triage of the same target

#### Scenario: Refinery continuation does not expose delivery
- **WHEN** a refinery reports `PARTIAL` and its coordination PR is verified merged
- **AND** fresh current main contains no claimable row overlapping the assigned change boundary
- **THEN** the supervisor rejects the continuation as non-delivery coordination churn
- **AND** it does not treat the refinery pseudo-target as implementation admission

#### Scenario: Refinery handoff and implementation both make bounded progress
- **WHEN** an accepted refinery `PARTIAL` exposes a claimable target
- **AND** the next ordinary worker merges a bounded `PARTIAL` slice for that same target
- **THEN** the refinery handoff does not count as the first repeated implementation partial
- **AND** the supervisor immediately resumes the preserved target without consuming a failure strike or entering the idle wait

#### Scenario: Coordination is genuinely exhausted
- **WHEN** claimable, stale, owned, and refinable counts are all zero after exact-current-main inspection
- **THEN** the supervisor may accept `NO_CANDIDATE` and wait without consuming a failure strike

### Requirement: Drain Watchdog Preserves Identity Across Abrupt Shutdown
The drain watchdog SHALL attach to a live unfinished drain, SHALL resume an unfinished drain whose recorded controller is dead using the same run directory and exact identity, and SHALL start a fresh bounded run only when no unfinished run exists or an explicit restart targets an already-terminal fatal or failure-budget run. An explicit restart of a live supervisor that exits through orderly `stop-requested` SHALL resume that same run directory and identity with stale-lock and stop-marker recovery.

#### Scenario: Explicit restart gracefully stops a live supervisor
- **WHEN** an explicit restart is requested while a supervisor is live
- **AND** that supervisor exits through orderly `stop-requested`
- **THEN** the watchdog resumes the same run directory and exact drain identity
- **AND** the preserved admission and resume target remain available to the next worker

#### Scenario: Explicit restart follows an already-terminal failure
- **WHEN** an explicit restart targets a supervisor already ended at a fatal or failure-budget terminal outcome
- **THEN** the watchdog preserves the authorized fresh-run decision
- **AND** it starts exactly one fresh bounded supervisor run
