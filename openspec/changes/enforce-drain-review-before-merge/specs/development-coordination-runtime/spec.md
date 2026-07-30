## MODIFIED Requirements

### Requirement: Drain Workers Preserve Delivery Governance

Every generated drain-worker brief SHALL require current-main orientation, a
clean purpose-named worktree, exact STATUS collision/admission checks, one
concrete acceptance contract, tests and required independent review, at most one
PR, verified merge, spec sync/archive when complete, and STATUS foldback. It
MUST forbid umbrella conversion, silent claim theft, primary-checkout edits, and
mechanical legacy-change fan-out. A legacy oversized change MAY be attempted
only as one concrete recovery slice containing at most 12 unchecked tasks and
SHOULD prefer materially fewer tasks within the finite worker timeout. The brief
MUST state that local peer workers are write-capable without a reliable OS
sandbox on the supported Windows host, so worktree/claim/review/CI/budget
controls are the safety boundary.

For every controller-admitted `drain/*` branch, the brief MUST require a draft
pull request, independent approval of the exact current head, and a durable
machine-readable approval receipt before the pull request becomes ready. The
trusted repository auto-enrollment workflow SHALL keep a drain pull request out
of auto-merge unless exactly one approval verdict, reviewed head, and review
artifact marker are present and the reviewed head equals the current pull
request head. It MUST disable an existing drain auto-merge request when the
receipt is missing, malformed, ambiguous, or stale. Non-drain pull requests
MUST retain their existing enrollment behavior.

The repository's already-required `policy` check SHALL evaluate the same receipt
against every current drain head from trusted base-branch code and MUST fail
closed when the receipt is missing, malformed, ambiguous, or stale. The policy
check MUST remain pending or red for an unapproved current head so branch
protection prevents merge while enrollment cancellation is still running.

#### Scenario: No safe candidate exists

- **WHEN** every candidate is live-claimed, host-owned, blocked, or lacks a
  concrete bounded acceptance contract
- **THEN** the worker returns `NO_CANDIDATE` or `BLOCKED`
- **AND** it does not invent a new change merely to stay busy

#### Scenario: Global worktree inspection exceeds its drain-worker cap

- **WHEN** `worktree_status.py` does not complete within 90 seconds for a
  controller-launched worker
- **THEN** the worker records the timeout and may continue only after creating a
  clean current-main worktree with `_PURPOSE.md`
- **AND** it still runs exact claim/collision and provider-context checks before
  editing

#### Scenario: Legacy change is selected

- **WHEN** the worker selects a grandfathered oversized active change
- **THEN** it limits the delivery attempt to at most 12 unchecked tasks and one
  PR
- **AND** it does not mechanically create child changes for the remaining work

#### Scenario: Drain pull request lacks exact-head approval

- **WHEN** a pull request from a `drain/*` branch is non-draft or already
  enrolled for auto-merge
- **AND** its durable review receipt is missing, malformed, ambiguous, or names
  a head other than the current pull-request head
- **THEN** the trusted repository workflow does not enable auto-merge and
  disables any existing auto-merge request
- **AND** the required current-head policy check fails so branch protection
  prevents merge before or during cancellation

#### Scenario: Drain pull request has exact-head approval

- **WHEN** a pull request from a `drain/*` branch contains exactly one durable
  `APPROVE` verdict, current 40-character lowercase head SHA, and review artifact
  marker
- **THEN** the trusted repository workflow may idempotently enable auto-merge
  under the ordinary required CI and branch-protection gates
- **AND** the required policy check may pass that head through to the existing
  writer/checker family policy

#### Scenario: Reviewed drain head changes

- **WHEN** a drain pull request was eligible for auto-merge
- **AND** a subsequent commit changes its current head without a new matching
  independent-review receipt
- **THEN** the trusted repository workflow disables the stale auto-merge request
- **AND** a fresh exact-head review is required before re-enrollment

#### Scenario: Ordinary pull request is evaluated

- **WHEN** a same-repository non-draft pull request targets `main` from a branch
  outside the `drain/*` namespace
- **THEN** the trusted workflow preserves its existing idempotent auto-enrollment
  behavior without requiring a drain review receipt
