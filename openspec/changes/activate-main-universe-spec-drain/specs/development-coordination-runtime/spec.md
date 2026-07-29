## ADDED Requirements

### Requirement: The cloud OpenSpec drain preserves fresh mechanical admission
The cloud drain SHALL fetch and inspect exact current `origin/main` coordination state before every selection, rank only currently admissible STATUS/OpenSpec lanes, and atomically claim one selected lane before build work. A refresh, classification, collision, or claim failure MUST fail closed or select another independently admissible lane; cached controller state, a stale checkout, and Branch-authored target text SHALL NOT grant admission.

#### Scenario: Former candidate retired on main
- **WHEN** a cached prior run names a candidate whose STATUS row was removed or completed on current `origin/main`
- **THEN** the cloud drain does not dispatch that candidate and refreshes selection from current state

#### Scenario: Candidate collides during admission
- **WHEN** another provider claims an overlapping write set after selection but before the cloud claim commits
- **THEN** the cloud attempt records the collision and performs no build mutation for that candidate

### Requirement: Each cloud drain invocation delivers one governed bounded slice
Each admitted cloud invocation SHALL implement or fold back no more than one reviewable slice under explicit time, token/spend, retry, and file-boundary limits. It SHALL preserve OpenSpec apply requirements, focused verification, independent opposite-provider review, ordinary GitHub pull-request and branch-protection policy, and sync/archive foldback. It MUST persist a typed terminal receipt before another invocation is eligible.

#### Scenario: Slice is mergeable
- **WHEN** one bounded slice passes its required checks and independent review
- **THEN** the drain publishes or updates its isolated pull request through the scoped GitHub effect and records the exact branch, head, checks, review, and next foldback state

#### Scenario: Slice discovers broader architecture work
- **WHEN** the admitted slice cannot finish without expanding beyond its claimed files or delivery-size ceiling
- **THEN** it records a concrete blocked/dependency result and does not silently enlarge the slice

### Requirement: Cloud drain selection follows live uptime priority without starving completable work
The cloud drain SHALL choose among admissible lanes using the live coordination policy: unblock the largest currently broken complete-system uptime surface, break ties by shared dependency impact and then shortest verified recovery, and prefer finish-first foldback when it can retire active WIP. Subordinated work SHALL remain eligible only when it does not displace admissible uptime progress.

#### Scenario: BYOC and market work are both admissible
- **WHEN** requester-owned compute and market-compute lanes are both admissible and neither has a stronger shared-dependency tie
- **THEN** the drain selects the requester-owned compute lane because the approved cloud-drain proof excludes a market-compute dependency

#### Scenario: Small foldback retires active WIP
- **WHEN** a nearly complete change can be verified, synced, and archived before a larger equally impactful slice
- **THEN** finish-first ranking may select the foldback and records why it reduces active delivery WIP

### Requirement: Cloud execution uses isolated repository lanes and durable receipts
The cloud drain SHALL perform repository mutations in an isolated Git branch tied to the admitted STATUS write boundary and SHALL integrate only through the normal pull-request path. Cloud-local checkout or workspace state MUST NOT be treated as durable coordination or health; every resumable claim, effect, verification, review, and terminal outcome SHALL be recoverable from repository/control-plane records and typed receipts.

#### Scenario: Cloud worker filesystem disappears
- **WHEN** an ephemeral worker is destroyed after committing or publishing a slice
- **THEN** a replacement reconstructs the lane and exact next action from durable branch, pull-request, STATUS, OpenSpec, activation, and receipt state

#### Scenario: Worker cannot publish
- **WHEN** local verification passes but the scoped GitHub effect is unavailable or refused
- **THEN** the result is a delivery failure with preserved local commit evidence, not a claim that the task is durably blocked or complete
