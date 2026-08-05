# The worker fleet serves a universe no authenticated user can repoint

`current: 2026-08-05`. Measured against deployed sha `bb5b3cf5`
(deploy run `30989259215`). Cross-family review: Codex `adapt` — it confirmed
the diagnosis and **refuted the first proposed fix**; see *Rejected fix* below.

## Symptom

`get_status` on the founder home `u-01kxm1vszd8hwp7em418asq8h9`:

```
depth = 4, pending = 4, valid_pending_count = 4, eligible_pending_count = 0
awaiting_compatible_capacity = 4   reason: no_live_compatible_worker
compatible_worker_count = 0        consumer_ready = true
operational_oldest_age_s = 47284   (~13.1 h)
quarantined = 0, invalid_operator_admission = 0
open_brain.runtime_instance_count = 4
```

Four slices are structurally valid, and nothing will ever claim them.

## Root cause

The worker fleet resolves the universe it serves from a **host-global marker**,
while the queued work lives in a **per-user universe**.

1. `cloud_worker._resolve_universe()` falls through to
   `storage.active_universe_id()`, which reads `/data/.active_universe`.
   In production that marker holds `concordance` — the legacy story universe.
   Every supervisor beat is therefore written under `concordance/`.
2. `api.universe._worker_liveness(udir)` globs beat files **inside `udir`**
   (`universe.py:1204-1214`). For `udir = u-01kxm1…` the glob returns nothing,
   so `_compatible_epoch2_workers` returns `[]` and
   `compatible_worker_count = 0` (`universe.py:1485`) — *before* any descriptor
   is validated. Every pending row then classifies
   `awaiting_compatible_capacity` / `no_live_compatible_worker`
   (`branch_tasks_v2.py:604-610`).
3. Independently, the beat pairs the supervisor's universe (`concordance`) with
   `TINYASSETS_RUNTIME_INSTANCE_ID`, which `_pump_cloud_automation_triggers`
   last set for a runtime registered against the *pumped* universe and never
   restored (`cloud_worker.py:1005`). `daemon_registry.py:469-470` compares
   exactly those two values and raises `queue_universe_id_mismatch` — on every
   beat, which is why the worker logs repeat it. This is why
   `runtime_instance_count = 4` in `u-01kxm1…` while its beats are absent: the
   worker's runtime is registered in one universe and its liveness advertised
   in another.

## Why no user can fix it

This is the load-bearing part, and it is a *design* gap rather than a leak:

- An **authenticated** founder's `switch_universe` is request-scoped **by
  design** and deliberately does not touch the marker — "Explicit universe
  selection is not global… must NOT mutate the host-global `.active_universe`
  marker that other users resolve through" (`api/universe.py:5562-5578`).
- Only an **anonymous / dev single-tenant** call writes the marker
  (`api/universe.py:5580-5586`).
- `TINYASSETS_UNIVERSE` cannot be used to pin a worker: `deploy-prod.yml:1415`
  fails the deploy if a worker inherits it, because it "can bind a worker to a
  different universe than the public MCP default".

The multi-tenant fix correctly froze the marker; the worker fleet was never
migrated off it. So the fleet is pinned to whatever universe the marker held
when anonymous writes were still possible, and **no authenticated user —
including the founder — can repoint it through any advertised handle.**

## Rejected fix (recorded so it is not re-attempted)

*Proposal:* have the automation pump record the `(universe, runtime, worker
slot)` triple it binds, and have the liveness beat advertise capacity into each
served universe from that triple.

*Why it is wrong:* the beat asserts a live **consumer** (`subprocess_alive`),
but the pump's runtime binding is a **producer** audience. Cross-universe
pumping happens after the supervised child has exited, and that child was
spawned against `concordance`. Advertising from the pump triple would either
report `subprocess_alive=false` or falsely advertise the next `concordance`
child as a consumer for the target universe. The rows would leave
`awaiting_compatible_capacity` and become claimable by a worker that will never
work them — replacing a visible stall with an invisible one.

## Correct shape

One **real supervised execution context per advertised universe**: a supervisor
whose resolved universe, spawned child, registered runtime, descriptor, and
beat directory all agree. Keep the atomic-record idea, but bind it to spawned
consumers, not to producer-pump audiences.

This is also what the platform model requires — a universe is a user's account,
and many users each run their own. A single host-global marker choosing which
universe the whole fleet serves cannot survive a second user.

## Smallest unblock (host decision)

Repoint `/data/.active_universe` at `u-01kxm1vszd8hwp7em418asq8h9`. Spawn
registration, child universe, descriptor, and beat directory then align, and
the four pending slices become claimable.

Tradeoff: the marker is fleet-global, so this moves **every** worker off
`concordance`. Note `concordance` is currently being worked by the
`fantasy_daemon` route and has been producing 0 words across 98 chapters, so
the practical cost looks low — but that is an observation, not a verified
finding, and the call is the host's.
