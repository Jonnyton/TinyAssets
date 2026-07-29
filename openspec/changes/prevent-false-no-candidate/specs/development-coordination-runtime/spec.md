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

#### Scenario: Claimable work exists

- **WHEN** a worker returns `NO_CANDIDATE`
- **AND** `claim_check.py --json` reports one or more claimable rows
- **THEN** the supervisor rejects the result as semantically invalid
- **AND** it dispatches a fresh worker subject to the finite failure budget

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
