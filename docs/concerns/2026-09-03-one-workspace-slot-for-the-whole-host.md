# There is no host-wide workspace bound at all

**Filed 2026-09-03. Corrected the same day**, after a cross-family review
refuted the first version of this file. The original claim — that one workspace
slot serialised every user on the host — was **wrong**, and the correction runs
the opposite way.

## What I claimed, and why it was wrong

`tinyassets/workspace_pool.py` has two locks, and the second is named `host`:

```python
HOST_SLOT = "slot-0"
_acquire_lock(conn, scope=SCOPE_HOST, key=host_slot, ...)
```

I read that as a global mutex and filed it as a P1 cross-user defect: any
user's workspace job refusing every other user's. Codex refuted it with the one
fact I never checked — **which database that row lives in**:

```python
def _pool_db(base_path: Path) -> Path:
    return runs.runs_db_path(base_path)      # <base_path>/.runs.db
```

and `base_path` is the **universe directory**, which the module itself proves
two hundred lines earlier:

```python
def _universe_id(base_path: str | Path | None) -> str:
    return Path(base_path).name.strip()      # the dir name IS the universe id
```

So every universe has its own `.runs.db`, and every universe has its own
`slot-0`. Two users scan different files and both acquire a slot. **The lock
named `host` has never crossed tenants**, and the cross-user defect I filed
does not exist.

## What is actually true

**1. Tiny's `workspace_busy` was the per-universe lock, working.** The refusal
it hit on 2026-09-01 was its own universe's second job meeting the mutex that
exists to stop one universe splitting a job across parallel branches. That is
the intended behaviour, and it is the half of the refusal message that applies:
*"Another workspace job of this universe (or the host's single slot)"*.

**2. There is no host-wide capacity bound.** This is the real finding, and it
is the inverse of the one I filed. Nothing stops N universes from running
workspace jobs at once: no shared table, no host lock file, no admission
counter above the universe. On a 1 vCPU / 2 GB box (see
`capacity-is-memory-not-cpu`) concurrent checkouts of large repos are the
plausible way to exhaust it, and the code that looks like it bounds this does
not.

**3. `wait_s` does not govern the wait.** `_connect` sets
`PRAGMA busy_timeout = 30000`, so `BEGIN IMMEDIATE` can block for thirty
seconds regardless of `wait_s`, and the retry loop catches only
`WorkspacePoolRefused` — an expired busy timeout raises
`sqlite3.OperationalError` and escapes as `workspace_checkout_failed`. So
`wait_s=0` can block for thirty seconds, and `wait_s > 30` can fail early with
the wrong error. Separate bug, same file.

## Why the fix is not "more slots"

Adding N slots to a per-universe database bounds nothing: each universe still
gets its own N. The first version of this branch did exactly that, passed its
tests because the tests shared one database unlike production, and would have
shipped a no-op wearing the name of a fix. It is reverted.

A real host bound needs a store above the universe — the platform root's
database, or a lock file under the data root — and that is a storage-shape
decision, not a constant to raise.

## What the misleading name should become

`SCOPE_HOST` and `HOST_SLOT` describe a scope the row does not have. Whatever
bound gets built, those names should stop claiming host scope while living in a
per-universe file; that naming is what made the misreading easy, and it will do
it again.
