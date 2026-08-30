## ADDED Requirements

### Requirement: Scratch storage is leased per job in a shared pool and never charged to a universe's permanent space

The platform SHALL keep two storage classes — the universe's permanent space under its own directory, bounded by its tier quota, and a shared scratch pool of per-job leases under `<data>/scratch/` — and SHALL never charge a scratch lease to a universe's permanent quota.
A lease SHALL be a random opaque id bound server-side to `(universe,
connection, canonical repo, storage class, generation)`, SHALL live in a
freshly created directory under a parent resolved without following links
(an opened directory handle held for every later host-side access), and
SHALL be bounded per lease (default 4 GiB) and by the pool (default 20 GiB).
Disk bounds are enforced best-effort in this change (repository size from
the API before cloning, `--depth`, a watcher that kills at the bound); a
kernel quota (a dedicated scratch filesystem with project quotas) is the
named follow-up.

#### Scenario: a large checkout does not enlarge the universe
- **WHEN** a universe checks out a 3 GiB repository as scratch
- **THEN** the universe's permanent usage is unchanged and the pool's reserved bytes rise by the lease's bound until release

### Requirement: Lease admission is one transaction and release follows a persisted state machine

The runtime SHALL perform reservation, the pool-total check, the job-lock acquisition and the `ACTIVE` transition of a lease in one `BEGIN IMMEDIATE` transaction in the runs database, SHALL write the run's terminal status and the lease's release entry in one transaction into a `lease_outbox` table, and SHALL release only through that outbox.
The state machine is `RESERVED → ACTIVE(run, universe, generation) →
QUARANTINED(path) → WIPING → AVAILABLE`, with `LOST` for a wipe that
failed (its bytes stay charged against the pool and it is reported). A
single in-process processor SHALL claim outbox entries at-least-once
(`claimed_by`, `claimed_at`, generation) after commit and SHALL perform
atomic rename into quarantine, deletion without following links,
verification, and only then `AVAILABLE`; a startup sweeper SHALL run before
any new lease is admitted, and a periodic sweeper SHALL reclaim entries
whose claimant is dead. Startup recovery that rewrites in-flight runs to
`interrupted` SHALL enqueue their leases' release. A directory SHALL never
be recycled in place, and there SHALL be no grace-window reuse.

#### Scenario: two admissions cannot oversubscribe the pool
- **WHEN** two checkouts are admitted concurrently with 5 GiB of pool capacity left and 4 GiB leases
- **THEN** exactly one acquires a reservation and the other is refused as `workspace_pool_busy`

#### Scenario: the next user's run never sees the previous lease's bytes
- **WHEN** a lease is released and a different universe's run is granted a lease
- **THEN** the new lease is a new random directory created after the old one's deletion verified; no object, ref or file of the old lease exists under the pool

#### Scenario: a crash between terminal status and release is repaired before new work
- **WHEN** the daemon restarts after a run's terminal status and outbox entry committed but before the entry was processed
- **THEN** the startup sweeper processes the entry and no new lease is admitted until it has

### Requirement: Permanent workspaces are chosen at checkout and removed only on request

A checkout with `storage: "universe"` SHALL place the workspace under the universe's permanent space, SHALL count it against the universe's quota, and SHALL be refused as `workspace_quota_exceeded` before any bytes move when it would exceed that quota.
There is no separate pin operation; a permanent workspace is reopened only
through a fresh authority-checked `checkout` with `storage: "universe"`
and is removed only by `discard`, never by age.

#### Scenario: keeping a workspace across turns is a permanent checkout
- **WHEN** a universe checks out the same repository twice with `storage: "universe"`
- **THEN** the second checkout fetches and resets the existing permanent workspace (or keeps local work when the packet says `reuse: true`) and no scratch lease is created
