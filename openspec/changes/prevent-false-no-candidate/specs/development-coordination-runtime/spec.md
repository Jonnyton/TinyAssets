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
The worker MUST revalidate that snapshot and durably claim the first still-valid
row before beginning a broad backlog audit.

#### Scenario: Claimable work exists

- **WHEN** the pre-dispatch claim check reports one or more claimable rows
- **THEN** the supervisor injects their ordered labels and bounded file scope
- **AND** the worker revalidates and durably claims the first still-admissible
  row before a broad audit
- **AND** a later `NO_CANDIDATE` is rejected while any claimable row remains

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
