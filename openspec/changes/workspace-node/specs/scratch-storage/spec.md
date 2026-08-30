## ADDED Requirements

### Requirement: Scratch storage is leased per job in a shared pool and never charged to a universe's permanent space

The platform SHALL keep two storage classes: the universe's permanent
space under its own directory, bounded by its tier quota, and a shared
scratch pool of leases under `<data>/scratch/`. A lease SHALL be a random
opaque id bound server-side to `(universe, connection, canonical repo,
storage class, generation)`, SHALL live in a freshly created directory
under a parent validated without following links (an opened directory
handle held across bind setup), SHALL be bounded per lease (default 4 GiB)
and by the pool (default 20 GiB, admission refuses a new lease when the
pool's reserved bytes would exceed it — `workspace_pool_busy`), and SHALL
NOT count against the universe's permanent quota. Disk bounds are enforced
best-effort in this change (API repository size before cloning, `--depth`,
a watcher that kills at the bound) and the spec records that a kernel
quota (a dedicated scratch filesystem with project quotas) is the named
follow-up.

#### Scenario: a large checkout does not enlarge the universe
- **WHEN** a universe checks out a 3 GiB repository as scratch
- **THEN** the universe's permanent usage is unchanged and the pool's reserved bytes rise by the lease's bound until release

### Requirement: Leases follow a persisted state machine and are released after the terminal commit

A lease SHALL be `ACTIVE(run, universe, generation)` while its run lives.
The run's terminal-status transaction SHALL write an idempotent release
entry to an outbox processed after commit — never inside the status write
itself; a startup sweeper and a periodic sweeper SHALL reconcile leases
whose owning run is dead. Release SHALL move the lease to `QUARANTINED` by
atomic rename, then `WIPING` (deletion without following links), then
`AVAILABLE` only after the deletion verified; a directory SHALL never be
recycled in place, and a failed wipe SHALL permanently reduce the pool's
available bytes and be reported. There SHALL be no grace-window reuse: a
later run pins explicitly or checks out fresh.

#### Scenario: the next user's run never sees the previous lease's bytes
- **WHEN** a lease is released and a different universe's run is granted a lease
- **THEN** the new lease is a new random directory created after the old one's deletion verified; no object, ref or file of the old lease exists under the pool

#### Scenario: a crash between terminal status and release is repaired
- **WHEN** the daemon restarts after a run's terminal status committed but before its outbox entry was processed
- **THEN** the startup sweeper processes the entry and the lease is wiped before any new lease is granted

### Requirement: Pinned workspaces are permanent until discarded

A workspace pinned into the universe's permanent space SHALL count against
the universe's quota, SHALL be reopened only through a fresh
authority-checked `checkout` effect with `storage: "universe"`, and SHALL
NOT be removed by age — only by an explicit `discard` or a quota refusal at
pin time.

#### Scenario: pinning is a quota decision, not a silent copy
- **WHEN** a `checkout` with `storage: "universe"` would exceed the universe's quota
- **THEN** it is refused as `workspace_quota_exceeded` before any bytes move
