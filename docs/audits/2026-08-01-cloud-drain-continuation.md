# Cloud-drain prepared continuation proof

Date: 2026-07-31 America/Los_Angeles / 2026-08-01 UTC
Environment: Windows development worktree `wf-cloud-drain-continuation`

## Verdict

This slice persists one restart-safe, non-authorizing cloud continuation for
an inactive repository-to-spec automation. It is a dark prerequisite, not a
cloud-drain activation. The local tray drain remains the only live executor,
and the epoch-2 cloud consumer remains disabled.

The record binds the immutable work-definition digest and Branch version to
the exact stopped activation epoch, active background Branch binding,
requester-owned provider binding, and exact GitHub destination grant. It holds
only IDs, generations, and content digests. It contains no credential, token,
provider invocation, effect authority, task claim, or background attempt.

## Authority and transaction boundary

Preparation reads each canonical owner and fails closed when the activation is
missing or active; the background binding is inactive, expired, foreign,
wrong-version, non-cloud, exhausted, or broader than the accepted definition;
the provider binding is unavailable; or the repository grant is unavailable.

The continuation insert and exact stopped-activation comparison occur in one
`BEGIN IMMEDIATE` transaction in the shared TinyAssets control-plane database.
Concurrent callers therefore create exactly one record. An identical later
call, including one after restart at a different wall-clock time, replays the
original record. A different immutable definition conflicts instead of
silently replacing it.

Provider, background, and outbound-grant owners are intentionally separate
authority aggregates. Their preflight reads cannot form one cross-store
snapshot. The continuation records their exact generations and digests, and a
later activation/attempt/effect slice must revalidate every owner just in time.
Because preparation grants no execution or effect authority, revocation after
preparation leaves only an unusable stale snapshot; it cannot launch work.

## Negative proof

After successful preparation:

- the automation activation remains `stopped` at the same epoch;
- no epoch-2 task table or row is created by this path;
- no background attempt exists;
- no provider invocation or credential resolution occurs; and
- no outbound effect or receipt is created.

The continuation reader verifies strict schema, row-to-record identity, and a
canonical content digest. Tampered persisted JSON fails closed on restart.

## Fresh verification

Verified 2026-07-31 America/Los_Angeles:

- `python -m pytest tests/test_cloud_automation_continuation.py -q` — 15 passed.
- Related activation, epoch-2 admission, background authority, provider
  authority, user-owned automation, and outbound-ledger suite — 445 passed;
  one pre-existing dependency deprecation warning.
- Ruff on the two implementation modules and focused test — clean.

## Remaining gate

OpenSpec task 1.2 remains unchecked. This slice does not create an epoch-2
admission, issue a background attempt, reserve provider work, or authorize a
GitHub effect. The next slice must compose those existing owners with fresh
generation checks and single-flight identity. Task 4.1 must still stop and
fence the tray before enabling any cloud consumer, so this change cannot cause
tray/cloud overlap.
