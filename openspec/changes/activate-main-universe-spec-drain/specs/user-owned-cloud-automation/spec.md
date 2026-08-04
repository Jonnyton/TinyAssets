## ADDED Requirements

### Requirement: Cloud automation is an ordinary user-owned composition
The system SHALL represent a requester-owned repository-to-accepted-spec production loop as a private, versioned Branch composition in the requester's universe using existing Branch, Trigger, Goal, Gate, Run, evaluator, effect, and cloud-executor primitives, with principal, universe, repository, accepted spec, immutable Branch version, evaluator policy, provider route, and destination supplied as authorized data-bound inputs and with no privileged drain service or new top-level MCP handle. Jonathan's main-universe OpenSpec drain SHALL be the first acceptance fixture, not a privileged runtime mode.

#### Scenario: Owner inspects the automation definition
- **WHEN** an owner inspects their active repository-to-spec automation through the live connector
- **THEN** the response identifies the private universe, repository, accepted spec, Branch, immutable version, Trigger, Goal, evaluator, effects, provider route, and cloud executor that compose it

#### Scenario: Privileged drain substrate is absent
- **WHEN** the cloud automation is activated
- **THEN** no drain-specific scheduler, maintainer task loop, or repository-specific GitHub Actions controller is required to continue it

### Requirement: Definition and operational state retain separate owners
The system MUST store only immutable user-authored work-definition references in the published Branch version and MUST derive its user-facing operational projection read-only from the server-authoritative activation, epoch-2 task, background Branch attempt, provider invocation, frozen evaluation, outbound effect, and GitHub/OpenSpec records. The definition or projection MUST NOT independently mint authority, own mutable attempt state, or advance the composite lifecycle.

#### Scenario: Projection observes independently owned state
- **WHEN** activation, attempt, provider, evaluation, or effect state changes under its owning authority
- **THEN** the next projection reflects that record and its generation without copying it into a second writable packet state

#### Scenario: Definition attempts to carry runtime authority
- **WHEN** a published definition supplies an activation epoch, lease generation, provider reservation, evaluation result, effect reservation, or terminal state as user-authored authority
- **THEN** admission fails closed without activating, claiming, invoking a provider, or performing an external effect

### Requirement: Cloud execution uses only explicit user-owned authority
The cloud executor MUST resolve the requester's bound provider authority and exact destination repository grant before executing a slice, MUST record the resolved non-secret authority source in run and effect evidence, and MUST fail closed without substituting maintainer, host, market, or ambient credentials.

#### Scenario: Bound provider is available
- **WHEN** a slice starts with a valid requester-owned provider binding and exact repository grant
- **THEN** execution evidence names those authority sources without exposing their secret values

#### Scenario: User-owned provider is unavailable
- **WHEN** the provider binding is missing, revoked, paused, expired, or unusable
- **THEN** the slice records an authority blocker and performs no model or GitHub effect through another authority source

### Requirement: Baseline evaluation is typed and tenant-code-free
Before provider spend, the automation MUST freeze an existing `AcceptanceScenario` identity and version, evaluator chain, input artifact digests, privacy scope, expected evidence, and budgets. The first slice MUST execute only typed deterministic evaluators that run no tenant repository code; shell, repository commands, CI emulation, and external tools MUST fail closed with `sandbox_unavailable` until the distributed-execution owner supplies production confinement with platform secrets absent, exact source staging, bounded resources, cleanup proof, and signed or fenced terminal evidence. Evaluation success MUST NOT grant provider, GitHub, merge, or foldback authority.

#### Scenario: Typed deterministic baseline is admitted
- **WHEN** the frozen acceptance scenario uses only admitted deterministic evaluators and its immutable inputs are available
- **THEN** the evaluator records an immutable receipt bound to the scenario version and input digests before provider execution is considered

#### Scenario: Definition requests repository code execution
- **WHEN** the baseline or evaluator requests a shell command, repository test command, CI emulation, or external tool without the production confinement backend
- **THEN** admission records `sandbox_unavailable` and performs no tenant code, provider invocation, or external effect

### Requirement: Continuation and admission are durable and single-flight
The owning activation, Trigger, epoch-2 task, background attempt, and provider/effect authorities SHALL persist their respective checkpoint, retry, lease, claim, and reservation state, SHALL read exact current repository head before admission, and SHALL allow at most one active slice and one mechanically claimed STATUS/OpenSpec lane for the activation identity across concurrent triggers and worker restarts. A continuously heartbeating epoch-2 task MUST explicitly renew its exact same-audience background-attempt lease before another provider launch; the inert provider receipt identity and conserved total budgets MAY survive rotating derived leases only while every launch transaction revalidates the current task, worker, activation, binding, attempt, and provider authority and proves the task and attempt lease expiries remain equal. Generic provider claim, reservation, and launch APIs MUST reject cloud background-attempt receipts; only the current-authority cloud service path may claim or launch them. An expired provider execution claim MAY advance only through a one-use service grant whose exact current roots are revalidated inside the same provider-ledger write transaction, MUST retain the same receipt and nonce-bound worker/runtime intent, MUST advance its generation without resetting prior reservations or aggregate budgets, and MUST refuse renewal while any launch remains merely reserved. Public claim replay remains stale after expiry. Before its first claim or reservation only, a legacy short-lived cloud receipt MAY migrate to the exact current provider-binding expiry by atomically advancing its receipt generation; any consumed or authority-different receipt MUST fail closed instead. A task heartbeat after expiry, newer task claim, alternate audience, stopped activation, stale binding, or forged renewal grant MUST NOT renew derived authority.

#### Scenario: Concurrent triggers race
- **WHEN** two cloud invocations attempt to start the same automation activation
- **THEN** exactly one invocation acquires the active-slice lease and the other records or observes the existing slice without claiming another lane

#### Scenario: Cloud worker restarts
- **WHEN** the worker stops after a claim and later restarts
- **THEN** it resumes or reconciles the same activation and claim identity before any candidate selection

#### Scenario: A long provider node crosses the original derived lease
- **WHEN** the same live worker has continuously renewed the epoch-2 task before expiry and requests another governed provider node after the original background-attempt lease
- **THEN** the runtime renews that exact attempt to the current task lease before transactionally arming the next carrier
- **AND** if the provider claim expired, it advances that exact nonce-bound claim generation through a one-use current-authority grant
- **AND** it preserves the receipt's original aggregate invocation, token, cost, and prior-reservation ceilings rather than minting new budgets

#### Scenario: Current-main admission finds no admissible work
- **WHEN** the canonical admission policy proves that no claimable, stale, resumable, or safely promotable lane exists
- **THEN** the invocation records an idle terminal receipt and schedules only the next bounded continuation

### Requirement: Each invocation delivers one bounded reviewable slice
The automation SHALL enforce declared time, model, and effect budgets; work within one isolated branch and task workspace; publish at most one pull request; require independent opposite-provider review and repository CI; verify GitHub merge state before foldback; and never bypass branch protection or OpenSpec sync/archive policy. The immutable definition MUST declare target-attempt/retry count separately from provider-invocation count so an ordinary user-authored Branch MAY contain multiple governed provider nodes without multiplying retry authority. Its total token and cost budgets MUST allocate at least one positive unit to every permitted provider invocation, and the runtime MUST distribute those totals without loss while refusing any zero-budget carrier before provider access. The cloud receipt MUST freeze the exact non-empty role set from the requester-owned provider binding, including `writer` for repository delivery, and each user-authored provider node MAY select any role in that set while undeclared roles fail before reservation or provider access. Provider-node ordinal, identity, and budget allocation MUST be derived from durable reservations under the same write transaction so worker reconstruction cannot repeat remainder shares or lose invocation capacity. Every marked provider node MUST revalidate the current activation, queue custody, background attempt, provider binding, role membership, and budget in the same durable transaction that arms its one-use provider carrier. A failed evaluation MAY retry once in the same preserved task workspace under the same logical definition and system-derived effect identity, but MUST use fresh target-attempt and provider-invocation generations and fresh bounded budgets. When the opposite provider reports a hard account, subscription, spend, or usage limit, the automation MUST persist dated evidence of that limit and use a fresh-context independent reviewer running on separately authorized requester-owned compute; the author MUST NOT review their own slice, and every blocking finding MUST be resolved before delivery advances.

#### Scenario: A candidate is admitted
- **WHEN** one current-main lane is mechanically claimed
- **THEN** the invocation works only that lane and terminates after one bounded reviewable slice, one pull request at most, and one typed terminal result

#### Scenario: A user-authored Branch uses multiple declared provider roles
- **WHEN** provider nodes select `writer`, `judge`, or another role frozen in the requester-owned binding
- **THEN** every node uses the same conserved receipt budget and exact role-specific carrier without escaping to a shared or ambient provider route
- **AND** a node selecting a role absent from that binding is rejected before a reservation is persisted

#### Scenario: Pull request merges
- **WHEN** GitHub reports the exact pull request head merged through normal policy
- **THEN** the automation verifies the merge independently before syncing or archiving the OpenSpec change and retiring the STATUS row

#### Scenario: Budget expires before completion
- **WHEN** a declared time, model, or effect budget is exhausted
- **THEN** the invocation preserves its branch, worktree, claim, evidence, and precise resume state without opening a second lane

#### Scenario: Opposite review provider reaches a hard limit
- **WHEN** the required opposite provider reports a hard account, subscription, spend, or usage limit
- **THEN** the invocation records dated limit evidence and obtains a fresh-context independent review on separately authorized requester-owned compute before delivery advances

### Requirement: GitHub effects are destination-scoped and reconcilable
The outbound-boundary owner MUST restrict GitHub writes to the exact granted repository and declared pull-request purpose and MUST reserve the system-derived tuple `(universe_id, automation_id, claim_id, repository, intended_head_sha, effect_kind)` as the durable effect identity. Before that exact identity exists, the owner MAY create unreachable content-addressed Git objects only under a separate journal keyed by the server-owned claim/repository/effect slot; that journal MUST freeze the first complete effect-intent digest, reuse its prepared commit across restart or replay, and MUST NOT publish a branch ref or pull request. The branch ref and pull request MAY become visible only after the prepared commit SHA has been folded into the exact effect identity and its journal is reserved. After an uncertain effect, that owner MUST attach and finalize without mutation when the exact remote effect exists; MUST retry at most once under the same reservation only when authoritative destination inspection conclusively proves absence and that reservation is retry-eligible; and MUST record a blocker without mutation when remote state is ambiguous, mismatched, or unavailable. This automation MUST NOT add a target-local receipt store, effect identity, or reconciliation loop and MUST remain inactive until the outbound owner ships this behavior or explicitly delegates a narrow reviewed GitHub adapter within that owner.

#### Scenario: Destination does not match the grant
- **WHEN** a Branch definition requests a GitHub write outside the exact granted repository or purpose
- **THEN** the effect fails closed before credential resolution or remote mutation

#### Scenario: Worker loses the local success result
- **WHEN** GitHub may have accepted a branch or pull-request mutation but local finalization is absent
- **THEN** the next invocation attaches and finalizes an exact remote match, retries once under the same reservation after conclusive absence, or blocks without mutation when reconciliation is ambiguous or fails

### Requirement: The owner can inspect and control the loop from a phone chatbot
The live connector SHALL let the authenticated owner inspect the active version, current claim, last useful progress, terminal receipts, authority source, budgets, next retry, and blocking reason, and SHALL let the owner pause, resume, or stop future slices through existing canonical `read_graph`, `write_graph`, `run_graph`, and `get_status` handles without a desktop, filesystem, CLI, or host login. Reprioritization is outside this first slice.

#### Scenario: Owner pauses future work
- **WHEN** the owner pauses the automation through a phone chatbot
- **THEN** no new slice starts after the pause is durably recorded, while any already committed external effect is reported rather than represented as cancelled

#### Scenario: Non-owner attempts control
- **WHEN** another principal attempts to pause, resume, stop, or inspect private automation state
- **THEN** the canonical owner-authorization boundary denies the request without disclosing private state

### Requirement: The owner can repair and evolve immutable automation versions
The live connector SHALL let the authenticated owner edit the ordinary Branch definition, inspect its complete diff, dry-test it without external writes or tenant code, publish a new immutable version, bind that version for future slices, and roll back by rebinding a prior immutable version through existing canonical handles.

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
- **WHEN** Jonathan rolls back from cloud execution to the temporary tray bridge
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
Final acceptance MUST keep Jonathan's computer off for at least 24 continuous hours, MUST include cloud-worker restart recovery and collision checks, and MUST use rendered phone-chatbot conversations through the live connector to prove inspection, control, repair, immutable-version activation, and rollback.

#### Scenario: Twenty-four-hour cloud proof passes
- **WHEN** the cloud automation completes its acceptance window
- **THEN** evidence shows at least 24 hours of useful cloud progress, recovery from a worker restart, no duplicate claims, only Jonathan-owned provider authority, and no tray activity

#### Scenario: Phone-only evolution proof passes
- **WHEN** Jonathan uses a rendered phone-chatbot session with every computer offline
- **THEN** he can inspect, pause, resume, edit, diff, dry-test, publish, activate, and roll back the automation without maintainer intervention
