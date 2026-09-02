# A run releases its workspace locks against the wrong database

**Filed:** 2026-09-01, read straight out of the production databases while
the founder's universe could not check anything out.
**Severity:** P1 — every workspace run, failed or succeeded, leaves its
universe lock and its host slot held. The second job of any universe is
refused as `workspace_busy` until something else releases them.

## The finding

Two homes for one run's state:

* the workspace effector keeps **locks, leases and the outbox in the
  universe's runs database** — `effectors/workspace.py` passes
  `base_path=universe_dir` into `_create` / `_discard`;
* the run's row and its terminal status are written to the **root** runs
  database, and the terminal enqueue runs there too —
  `runs.py` `update_run_status` calls `_enqueue_workspace_terminal(conn,
  base_path, run_id)` with the root as `base_path`.

So at termination the enqueue looks for the run's locks in a database that
holds none, writes nothing, and the locks stay. The sweep joined against the
local `runs` table, whose rows are at the root, and could not see them either.

## Live evidence (2026-09-01, `docker exec tinyassets-daemon python -`)

```
/data/.runs.db                              runs: 2486   workspace_locks: 0
  runs row 8f30bb9abf2b492f: status=failed
/data/u-01kxm1vszd8hwp7em418asq8h9/.runs.db  runs: 0      workspace_locks: 2
  universe u-01kx…  held by 8f30bb9abf2b492f  age 26.9 h
  host     slot-0   held by 8f30bb9abf2b492f  age 26.9 h
  outbox: one row, wipe_scratch, release_universe_lock=0, release_host_lock=0, done
```

The only outbox entry the run ever produced was the checkout failure's own
scratch wipe, written with `release_locks=False`. The terminal release that
would have carried both flags was never written, because it was attempted in
the other file.

## What shipped as a backstop

The sweep now consults the root for locks whose run it does not know locally:
terminal there → released at once, live there → kept however old, known
nowhere → released past a one-hour age bound. That makes back-to-back jobs
work and stops the leak from being permanent. It does not make the terminal
path correct.

## The structural fix

One database for a run and its workspace state. Either the terminal enqueue
runs against the run's universe database (the run's universe is known: the
actor is `universe:<id>`), or workspace state moves to the root beside the
runs. This is a storage-shape decision, so it takes an OpenSpec change; the
first option is the smaller diff and keeps the per-universe containment the
effector was built for.

Related: `_TERMINAL_STATUSES` is defined twice in `runs.py` (two definitions of
one fact); both agree today.
