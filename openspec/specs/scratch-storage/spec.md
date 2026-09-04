# Scratch Storage

> As-built (2026-08-30, change `workspace-node`): the two storage classes a
> workspace can live in — the universe's permanent space, and a shared pool of
> per-job scratch leases — and the transaction and outbox that hand them out and
> take them back. Implemented in `tinyassets/workspace_pool.py` and
> `tinyassets/workspace_fs.py`. Design rationale in the change's `design.md` (D0).

## Purpose

A universe never needs to be bigger than the codebase it works on. Permanent
storage is the space a universe owns and is charged for; the disk a single job
borrows to check out, build and test a repository is not that, and charging it
to the universe would make working with a large repository indistinguishable
from keeping it. This capability separates the two: permanent workspaces are
immutable-by-host generations under the universe's own directory and count
against its quota, while scratch is a shared pool of opaque per-job leases that
are reserved in one transaction, released only through a persisted outbox, and
never recycled in place — so the next user's run cannot see the previous one's
bytes, and a crash in any window is repaired rather than leaked.

## Requirements

### Requirement: Scratch storage is leased per job in a shared pool and never charged to a universe's permanent space

The platform SHALL keep two storage classes — the universe's permanent space under its own directory, bounded by its tier quota, and a shared scratch pool of per-job leases under `<data>/scratch/` — and SHALL never charge a scratch lease to a universe's permanent quota.
A lease SHALL be a random opaque id bound server-side to `(universe,
connection, canonical repo, generation)`, SHALL live in a freshly created
directory under a parent resolved without following links (an opened
directory handle held for every later host-side access), and SHALL be
bounded per lease (default 4 GiB) and by the pool (default 20 GiB). Disk
bounds are enforced best-effort in this change (repository size from the
API before cloning, a watcher that kills at the bound); a kernel quota (a
dedicated scratch filesystem with project quotas) is the named follow-up.

#### Scenario: a large checkout does not enlarge the universe
- **WHEN** a universe checks out a 3 GiB repository as scratch
- **THEN** the universe's permanent usage is unchanged and the pool's reserved bytes rise by the lease's bound until release

### Requirement: Workspace admission is one transaction and release follows a persisted outbox that reconciles every crash window

The runtime SHALL perform the storage reservation (lease bound or universe quota), the pool-total check, the job-lock acquisition, the byte-ledger reservation of the operation's maximum charge and the `ACTIVE` transition in one `BEGIN IMMEDIATE` transaction in the workspace-owning runs database, and SHALL release storage and locks only through a persisted `workspace_outbox` entry. When the canonical run row and workspace state share one database, terminal status and outbox entries SHALL be one transaction. When the run row lives at the data root and workspace state lives in the universe database, the terminal path SHALL commit the root status, immediately select the exact universe from server-written execution context, enqueue release in that universe database, and kick that universe's sweep; it SHALL never derive a path from a noncanonical universe id or create an absent universe database. The universe's periodic sweep SHALL treat a terminal status in the root database as recovery evidence and enqueue the same release after a crash between the two database writes.
An outbox entry SHALL carry one action — `wipe_scratch(lease, generation)`,
`discard_permanent_generation(repo_key, generation)` or
`release_lock_only` — and the universe and host locks to release. A single
in-process processor SHALL claim entries at-least-once with a claim token
and `claimed_at`, SHALL perform the filesystem steps against a
deterministic quarantine name derived from the lease (or repo key) and
generation, SHALL reconcile every combination on retry (source present and
quarantine absent → rename; source absent and quarantine present →
delete; both absent → done; both present → delete the quarantine, then
rename), SHALL delete without following links, and in one final
transaction SHALL mark the lease `AVAILABLE` or `LOST` (bytes stay charged
and it is reported), release both locks and acknowledge the entry by
claim-token compare. This protocol SHALL replace both the direct terminal
write and the startup bulk rewrite of in-flight runs, so startup recovery
enqueues each interrupted run's entries in the transaction that rewrites
it. A startup sweeper SHALL run to completion before any new workspace job
is admitted, and a periodic sweeper SHALL reclaim entries whose claim
expired. A directory SHALL never be recycled in place, and there SHALL be
no grace-window reuse.

#### Scenario: two admissions cannot oversubscribe the pool
- **WHEN** two checkouts are admitted concurrently with 5 GiB of pool capacity left and 4 GiB leases
- **THEN** exactly one acquires a reservation and the other is refused as `workspace_pool_busy`

#### Scenario: a root-owned terminal run releases universe-owned locks immediately
- **WHEN** a run row at the data root becomes terminal while its lease and locks live in the exact universe database named by its server-written execution context
- **THEN** the terminal path enqueues release in that universe database and kicks its sweep without waiting for the periodic repair pass

#### Scenario: a crash between the two terminal writes is repaired
- **WHEN** the root terminal status committed but the daemon stopped before the universe outbox entry committed
- **THEN** the next universe sweep reads the terminal root status, enqueues the release, and processes it through the same idempotent outbox protocol

#### Scenario: the next user's run never sees the previous lease's bytes
- **WHEN** a lease is released and a different universe's run is granted a lease
- **THEN** the new lease is a new random directory created after the old one's deletion verified; no object, ref or file of the old lease exists under the pool

#### Scenario: a crash after the rename but before its commit is repaired
- **WHEN** the processor renamed a lease into quarantine and the daemon died before committing, and the entry is claimed again after restart
- **THEN** the processor finds the source absent and the deterministic quarantine present, deletes it, and completes the entry; no new workspace job is admitted until every old entry reached `AVAILABLE` or `LOST`

#### Scenario: a failed wipe keeps its bytes charged and still releases the locks
- **WHEN** deletion of a quarantined lease fails permanently
- **THEN** the lease is marked `LOST`, its bytes remain charged against the pool, both locks are released, and the loss is reported

### Requirement: Permanent workspaces are immutable-by-host generations chosen at checkout

A checkout with `storage: "universe"` SHALL build a new opaque generation from staging's bundle beneath a no-follow universe directory handle, SHALL count it against the universe's quota, SHALL be refused as `workspace_quota_exceeded` before any bytes move when it would exceed that quota — leaving the existing generation unchanged — and SHALL publish it only by atomically switching the repository key's authoritative generation, enqueuing the previous generation for `discard_permanent_generation`.
There is no `pin`, no `reuse` and no refresh in place: host git SHALL
never open a previous generation. A permanent workspace is removed only
by `discard` (an outbox transition that immediately revokes any
capability over it), never by age.

#### Scenario: a second permanent checkout never opens the first generation
- **WHEN** a universe checks out the same repository twice with `storage: "universe"`
- **THEN** the second checkout populates a new generation from a fresh bundle, switches the authoritative generation atomically, and the first generation is quarantined and deleted through the outbox without any host git process opening it

#### Scenario: a quota refusal destroys nothing
- **WHEN** a permanent checkout would exceed the universe's quota
- **THEN** it is refused as `workspace_quota_exceeded` and the existing generation, if any, is untouched
