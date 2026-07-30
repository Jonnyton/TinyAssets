## ADDED Requirements

### Requirement: Cloud automation is an ordinary user-owned composition
The system SHALL let an ordinary user bind an authorized GitHub repository and their selected delivery spec to a private, versioned Branch composition in their cloud universe using existing Branch, Trigger, Goal, Gate, Run, effect, and cloud-executor primitives, with no privileged drain service, repository-specific product code, or new top-level MCP handle. Jonathan's TinyAssets/OpenSpec drain SHALL be the first production conformance instance of this user-neutral composition.

#### Scenario: Owner binds a repository and spec
- **WHEN** an owner configures the composition with an authorized GitHub repository and a delivery spec
- **THEN** the resulting private Branch uses those owner-selected bindings without new product code

#### Scenario: Owner inspects the automation definition
- **WHEN** the owner inspects the active production loop through the live connector
- **THEN** the response identifies the private universe, Branch, immutable version, Trigger, Goal, gates, effects, cloud executor, repository destination, and delivery spec that compose it

#### Scenario: Privileged drain substrate is absent
- **WHEN** the cloud automation is activated
- **THEN** no drain-specific scheduler, maintainer task loop, or repository-specific GitHub Actions controller is required to continue it

### Requirement: Cloud execution uses only explicit user-owned authority
The cloud executor MUST resolve the owner's bound provider authority and exact owner-selected GitHub repository grant before executing a slice, MUST record the resolved non-secret authority source in run and effect evidence, and MUST fail closed without substituting maintainer, host, market, or ambient credentials.

#### Scenario: Bound provider is available
- **WHEN** a slice starts with a valid owner-bound provider binding and exact repository grant
- **THEN** execution evidence names those authority sources without exposing their secret values

#### Scenario: User-owned provider is unavailable
- **WHEN** the provider binding is missing, revoked, paused, expired, or unusable
- **THEN** the slice records an authority blocker and performs no model or GitHub effect through another authority source

### Requirement: Continuation and admission are durable and single-flight
The automation SHALL persist its activation, Trigger, checkpoint, retry state, and current claim in cloud-owned state, SHALL read exact current `origin/main` before admission, and SHALL allow at most one active slice and one mechanically claimed STATUS/OpenSpec lane for its activation identity across concurrent triggers and worker restarts.

#### Scenario: Concurrent triggers race
- **WHEN** two cloud invocations attempt to start the same automation activation
- **THEN** exactly one invocation acquires the active-slice lease and the other records or observes the existing slice without claiming another lane

#### Scenario: Cloud worker restarts
- **WHEN** the worker stops after a claim and later restarts
- **THEN** it resumes or reconciles the same activation and claim identity before any candidate selection

#### Scenario: Current-main admission finds no admissible work
- **WHEN** the canonical admission policy proves that no claimable, stale, resumable, or safely promotable lane exists
- **THEN** the invocation records an idle terminal receipt and schedules only the next bounded continuation

### Requirement: Each invocation delivers one bounded reviewable slice
The automation SHALL enforce declared time, model, and effect budgets; work within one isolated branch and worktree; publish at most one pull request; require independent opposite-provider review and repository CI; verify GitHub merge state before foldback; and never bypass branch protection or OpenSpec sync/archive policy. When the opposite provider reports a hard account, subscription, spend, or usage limit, the automation MUST persist dated evidence of that limit and use a fresh-context independent reviewer running on separately authorized owner-bound compute; the author MUST NOT review their own slice, and every blocking finding MUST be resolved before delivery advances.

#### Scenario: A candidate is admitted
- **WHEN** one current-main lane is mechanically claimed
- **THEN** the invocation works only that lane and terminates after one bounded reviewable slice, one pull request at most, and one typed terminal result

#### Scenario: Pull request merges
- **WHEN** GitHub reports the exact pull request head merged through normal policy
- **THEN** the automation verifies the merge independently before syncing or archiving the OpenSpec change and retiring the STATUS row

#### Scenario: Budget expires before completion
- **WHEN** a declared time, model, or effect budget is exhausted
- **THEN** the invocation preserves its branch, worktree, claim, evidence, and precise resume state without opening a second lane

#### Scenario: Opposite review provider reaches a hard limit
- **WHEN** the required opposite provider reports a hard account, subscription, spend, or usage limit
- **THEN** the invocation records dated limit evidence and obtains a fresh-context independent review on separately authorized owner-bound compute before delivery advances

### Requirement: GitHub effects are destination-scoped and reconcilable
The automation MUST restrict GitHub writes to the exact owner-authorized repository and declared pull-request purpose and MUST reserve the system-derived tuple `(universe_id, automation_id, claim_id, repository, intended_head_sha, effect_kind)` as the durable effect identity. After an uncertain effect, reconciliation MUST attach and finalize without mutation when the exact remote effect exists; MUST retry at most once under the same reservation only when authoritative destination inspection conclusively proves absence and that reservation is retry-eligible; and MUST record a blocker without mutation when remote state is ambiguous, mismatched, or unavailable.

#### Scenario: Destination does not match the grant
- **WHEN** a Branch packet requests a GitHub write outside the exact granted repository or purpose
- **THEN** the effect fails closed before credential resolution or remote mutation

#### Scenario: Worker loses the local success result
- **WHEN** GitHub may have accepted a branch or pull-request mutation but local finalization is absent
- **THEN** the next invocation attaches and finalizes an exact remote match, retries once under the same reservation after conclusive absence, or blocks without mutation when reconciliation is ambiguous or fails

### Requirement: The owner can inspect and control the loop from a phone chatbot
The authenticated live connector SHALL let the owner inspect the active version, current claim, last useful progress, terminal receipts, authority source, budgets, next retry, and blocking reason, and SHALL let the owner pause, resume, or stop future slices through existing canonical handles without a desktop, filesystem, CLI, host login, or local credential broker. Runtime implementation SHALL remain gated while a successful connector authorization or reconnect does not continue into authenticated calls for the same owner and universe.

#### Scenario: Connector identity continuity is unavailable
- **WHEN** authorization or reconnect completes but a subsequent authenticated connector call fails
- **THEN** the cloud production loop remains blocked from runtime activation
- **AND** direct MCP probes or local CLI access do not clear the implementation gate

#### Scenario: Owner pauses future work
- **WHEN** the owner pauses the automation through a phone chatbot
- **THEN** no new slice starts after the pause is durably recorded, while any already committed external effect is reported rather than represented as cancelled

#### Scenario: Non-owner attempts control
- **WHEN** another principal attempts to pause, resume, stop, or inspect private automation state
- **THEN** the canonical owner-authorization boundary denies the request without disclosing private state

### Requirement: The owner can repair and evolve immutable automation versions
The authenticated live connector SHALL let the owner edit the ordinary Branch definition and its repository/spec bindings, inspect the complete diff, dry-test it without external writes, publish a new immutable version, bind that version for future slices, and roll back by rebinding a prior immutable version.

#### Scenario: Owner publishes an update
- **WHEN** the owner accepts a reviewed definition diff after a successful dry test
- **THEN** the system publishes a new immutable Branch version and changes activation only after an explicit owner-authorized bind

#### Scenario: Owner rolls back
- **WHEN** the owner selects a previously published version
- **THEN** future slices bind to that immutable version without altering either version's history

### Requirement: Tray-to-cloud cutover is single-active
The system MUST store one server-authoritative activation record keyed by `(universe_id, automation_id)` with a monotonically increasing epoch, active executor class, immutable Branch version, lease identity, and state. Activation, version rebind, stop, cutover, and rollback MUST use compare-and-swap transitions, and every claim MUST validate the exact current epoch, executor class, and version. The system MUST require the tray drain to stop before cloud acceptance and cloud automation to stop before rollback reactivates the tray; competing cloud versions, alternate activation identities, and stale or partitioned tray attempts MUST fail closed rather than claim.

#### Scenario: Tray is still active at cloud activation
- **WHEN** cloud activation observes that the tray drain can still claim work
- **THEN** cloud activation fails closed and neither executor is accepted as the sole active drain

#### Scenario: Rollback restores the tray
- **WHEN** the owner rolls back from cloud execution to the temporary tray bridge
- **THEN** the cloud activation is durably stopped before the tray is allowed to claim

#### Scenario: Stale executor retains cached activation state
- **WHEN** a tray or cloud worker presents an old epoch, executor class, version, or lease after another activation transition
- **THEN** claim validation fails without queue or STATUS mutation

#### Scenario: Competing cloud versions race
- **WHEN** two immutable Branch versions attempt to activate or claim concurrently under distinct local identities
- **THEN** at most one compare-and-swap transition owns the current epoch and only that exact epoch and version can claim

### Requirement: Health distinguishes liveness from useful progress
The automation SHALL persist typed receipts and checkpoints that report last useful progress, current claim, authority source, budget state, retry state, blocker, and applied continuation policy, and SHALL raise a no-progress alarm when retries or process liveness continue without a useful delivery transition.

#### Scenario: Worker is live but repeatedly retries
- **WHEN** heartbeats continue but no claim, pull-request, merge, foldback, or explicit durable blocker transition occurs within the configured bound
- **THEN** health reports no useful progress and raises the configured alarm

#### Scenario: A slice terminates
- **WHEN** a slice reaches merged, partial, blocked, failed, or idle termination
- **THEN** one typed terminal receipt records the claim, immutable Branch version, authority source, budgets, evidence handles, and next action

### Requirement: Acceptance proves PC-off continuity and owner operability
Final acceptance MUST keep every personal computer used by the first conformance owner off for at least 24 continuous hours, MUST include cloud-worker restart recovery and collision checks, and MUST use rendered phone-chatbot conversations through the authenticated live connector to prove inspection, control, repair, immutable-version activation, and rollback.

#### Scenario: Twenty-four-hour cloud proof passes
- **WHEN** the cloud automation completes its acceptance window
- **THEN** evidence shows at least 24 hours of useful cloud progress, recovery from a worker restart, no duplicate claims, only owner-bound provider authority, and no tray activity

#### Scenario: Phone-only evolution proof passes
- **WHEN** the owner uses a rendered phone-chatbot session with every personal computer offline
- **THEN** the owner can inspect, pause, resume, edit repository/spec bindings, diff, dry-test, publish, activate, and roll back the automation without maintainer intervention
