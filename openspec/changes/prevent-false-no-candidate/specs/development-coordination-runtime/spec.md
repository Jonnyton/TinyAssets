## ADDED Requirements

### Requirement: OpenSpec Drain Proves Work Exhaustion Before Idling

The OpenSpec drain supervisor SHALL accept `NO_CANDIDATE` only when the
canonical claim checker reports zero claimable rows, zero policy-qualified
stale-claim candidates, and zero in-flight rows owned by the drain's exact
identity. Every drain-worker brief MUST require the worker to resume its own
claim, select claimable finish-first work, reap policy-qualified stale claims,
freshness-check blocker labels, and consider safe cross-cutting promotion in
that order before reporting no candidate. Live foreign claims, host-owned
actions, unresolved decisions, and overlapping write sets MUST remain excluded.
Immediately before dispatch, the supervisor SHALL provide a bounded ordered
snapshot of exact-identity-owned, claimable, and policy-qualified stale rows.
The controller MUST revalidate that snapshot on current main and durably claim
the first still-valid row before dispatch; the worker MUST verify and reuse the
prepared claim before beginning a broad backlog audit.
Codex drain dispatches SHALL use a balanced reasoning effort suitable for the
preselected single-slice contract rather than inherit a higher interactive
session effort setting.
When the first ordered candidate is claimable or policy-qualified stale, the
supervisor SHALL create a clean current-main worktree, write its purpose
metadata, commit the exact STATUS claim, persist the admission record, and
launch the worker from that prepared worktree. The worker MUST reuse that lane
and MUST NOT repeat selection or create a second worktree.

#### Scenario: Claimable work exists

- **WHEN** the pre-dispatch claim check reports one or more claimable rows
- **THEN** the supervisor injects their ordered labels and bounded file scope
- **AND** the worker revalidates and durably claims the first still-admissible
  row before a broad audit
- **AND** a later `NO_CANDIDATE` is rejected while any claimable row remains

#### Scenario: Codex worker is dispatched

- **WHEN** the supervisor launches a disposable Codex drain worker
- **THEN** the peer command carries balanced `medium` reasoning effort
- **AND** tests, independent review, CI, and finite worker budgets remain the
  quality boundary

#### Scenario: First claimable candidate is admitted

- **WHEN** the canonical pre-dispatch snapshot has a claimable first row
- **THEN** the controller runs the bounded claim-phase context feed
- **AND** creates a clean branch/worktree from current `origin/main`
- **AND** commits `claimed:<exact-drain-identity> ACTIVE <date>` before dispatch
- **AND** launches the worker with that worktree as its cwd

#### Scenario: First stale candidate is admitted

- **WHEN** no claimable row precedes a policy-qualified stale first row
- **THEN** the controller commits the policy reaping status before the claim
- **AND** commits the exact drain claim in the same prepared worktree

#### Scenario: Admission target collides

- **WHEN** the deterministic worktree path or branch already exists
- **THEN** the controller refuses to overwrite or delete it
- **AND** records a bounded visible admission failure

#### Scenario: Admitted target is blocked

- **WHEN** the worker returns `BLOCKED` for its exact assigned target
- **THEN** the controller preserves the worktree and records the recent blocker
- **AND** releases active admission so the next snapshot can select a different
  non-blocked candidate

#### Scenario: Admission operation fails

- **WHEN** fetch, context feed, claim check, worktree I/O, or git admission
  times out or errors
- **THEN** the controller records a bounded `admission-failed` result
- **AND** it does not remain falsely `running` or dispatch an unclaimed worker

#### Scenario: Worker reports a different target

- **WHEN** an admitted worker's terminal marker names a target other than its
  assigned target
- **THEN** the controller rejects the result and retains admission for recovery

#### Scenario: Admitted target needs foldback

- **WHEN** a verified merged implementation returns `PARTIAL`
- **THEN** replacement-worker instructions require current-main restacking
  before any foldback PR is published

#### Scenario: Policy-qualified stale claim exists

- **WHEN** a worker returns `NO_CANDIDATE`
- **AND** `claim_check.py --json` reports one or more stale-claim candidates
- **THEN** the supervisor rejects the result
- **AND** the next worker brief requires policy-compliant reaping before idle

#### Scenario: Drain identity already owns work

- **WHEN** a worker returns `NO_CANDIDATE`
- **AND** an in-flight row is claimed by the drain's exact identity
- **THEN** the supervisor rejects the result
- **AND** the next worker must resume that owned row before selecting new work

#### Scenario: Coordination state is genuinely exhausted

- **WHEN** claimable and stale counts are both zero
- **AND** the worker has revalidated blockers and found no safe cross-cutting
  recovery task to promote
- **THEN** the supervisor may accept `NO_CANDIDATE`
- **AND** it waits the configured idle interval without consuming a failure
  strike

#### Scenario: A foreign claim is live

- **WHEN** a row has a current heartbeat or otherwise fails the stale-claim
  policy
- **THEN** the drain MUST NOT reap or overwrite that claim
- **AND** it selects non-overlapping work or remains idle
