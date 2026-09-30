# One storage pool per account, measured everywhere, enforced where users drive volume

## Why

Founder directive, 2026-09-30: account limits are only **storage GiB** and
**concurrent seats**. Scope is **per account**: one storage pool per person,
shared by all of their universes, and creating universes stays unlimited and
free. At the quota, new user-driven writes are refused visibly. The refusal
message contains a clickable "Upgrade" link. The top tier gets no link, and
reads never break. Free and paid differ only in the numbers, everything works on
free, and there are no rate meters.

`two-dimension-usage-limits` built seats and re-scoped storage out to its own
change (its task 1.4; `REVIEW.md` findings 10-16 and 18). This is that change.
It starts from that review's measured constraints on `origin/main` fb39b118:

- **Two numbers for one fact.** `usage_policy` declares free 2,000 MB and paid
  20,000 MB and enforces neither. `effectors/workspace.py`
  `_universe_quota_kwargs` enforces a flat 16 GiB for every tier, and only
  on `workspaces/`.
- **Free can't hold a workspace.** Workspace admission reserves a fixed 4 GiB
  (`_DEFAULT_MAX_CHECKOUT_BYTES`, used at `workspace.py:875` and `:1206`). The
  pool then checks `used + outstanding + max_bytes > quota`
  (`workspace_pool.py:946`). Under a 2 GiB quota, an empty free universe is
  refused.
- **Some user bytes live outside universe directories.** Run records sit in
  `<base>/.runs.db`, checkpoints in `<base>/.langgraph_runs.db`, uploads in
  `<base>/.run-file-custody`, and branches in the author-server database. Scratch
  is in `<data>/scratch`. A scan of the universe directory alone misses all of
  these.
- **Unadmitted growth.** A permanent generation is published at its
  post-provisioning size. Only the bundle bytes were reconciled, and nothing
  admits that final size (`workspace.py:1006-1017`).
- **Scan races.** A filesystem scan isn't transactional. A reset-on-measure
  ledger can drop a write that lands mid-scan (finding 10).
- **Per-universe keying.** Universes have no owner record, and the tier lives in
  each universe's `.subscription_state.db`. Nothing can sum bytes across one
  person's universes today.
- **The caps are already gone.** `remove-non-usage-limits` 1.3 (#4134, merged
  2026-09-30) deleted the project memory 1 MB cap, the daemon-wiki caps and
  eviction, and the 4 MiB UI-library subquota. Those bytes are unbounded on main
  until this pool enforces them.

## What Changes

1. **One number per tier, per account.** `usage_policy.limits_for(tier).storage_bytes`
   is the only storage quota: free **2 GiB**, paid **20 GiB**, with overrides
   `TINYASSETS_{FREE,PAID}_STORAGE_GIB`. The flat 16 GiB workspace quota and the
   MB variables are deleted.
2. **A universe has exactly one owning account.** The creation transaction
   records it in a `universe_owner` row. The account's tier is read from its
   home universe's subscription record, the one Stripe checkout already writes.
   This is one resolver, shared with the seats lane.
3. **Accounting covers every store** through an explicit store registry. Each
   store has an owner-attribution rule, and a completeness test fails on any
   unregistered top-level entry in the data directory. Live scratch leases stay
   in the shared pool and aren't charged (memory `storage-permanent-vs-scratch`).
4. **The number used is measured bytes plus pending bytes.** Measurements are
   cached per store and per universe. Pending reservations are cleared only by a
   measurement proven to have started after the write committed. Concurrent
   admissions are serialized in one `BEGIN IMMEDIATE` transaction.
5. **Nothing is refused on a stale number.** Before refusing, the gate
   re-measures any of the account's rows older than 60 s. So "delete, then
   retry" always works on the retry.
6. **Workspace reservations fit the quota.** A reservation is
   `min(lease bound, account headroom + the bytes of the generation it
   replaces)`. Before publication, the new generation is measured and must fit
   its reservation. An empty 2 GiB free account can check out any repository
   that fits in 2 GiB.
7. **Enforcement covers only the paths users drive volume through:** files,
   pages, uploads, workspaces, and branch/version writes. That includes project
   memory, the daemon wiki and the UI library, which lose their own caps. The
   credential vault, session and auth stores, chat history, run records and
   checkpoints are counted but never refused.
8. **The refusal is a structured failure** (`storage_quota_exceeded`). It gives
   the numbers, the account's three largest consumers, and
   `usage_policy.upgrade_sentence(tier, what="storage")`. Its link is
   `https://tinyassets.io/app?upgrade=1`, and the top tier gets none. Reads never
   consult the quota.

## Capabilities

### New Capabilities

- `account-storage-quota`: the account owner record, the store registry, the
  measured-plus-pending accounting, the gate and its enforcement points, and the
  visible refusal.

### Modified Capabilities

- `scratch-storage`: permanent workspaces are charged to the owning account's
  tier quota. Reservations fit the quota, and publication measures the
  generation before switching to it. Scratch stays uncharged.

## Impact

- **Storage shape:**
  - `universe_owner` table in the author-server database.
  - `<data>/.storage_accounting.db`, holding measurements, pending reservations
    and a sequence counter.
  - Indexes on `runs(owner_user_id)`, `runs(queue_universe_id)`,
    `branch_versions(publisher)` and `branch_definitions(author)`.
- **Authority:** the tier now gates bytes for real. Owner attribution becomes a
  stored fact rather than something inferred at read time.
- **Behaviour:** workspaces that fit now work on free. User writes past the quota
  are refused with a link. Nothing else is refused.
- **Code:**
  - New: `usage_policy.py`, `universe_owner.py`, `storage_accounting.py`.
  - Modified: `effectors/workspace.py`, `workspace_pool.py`, `universe_tools.py`,
    `api/wiki.py`, `run_file_capture.py`, `daemon_server.py`,
    `branch_versions.py`, `memory/project.py`, `daemon_memory.py`,
    `custom_agents.py` and `api/universe.py`, plus
    `docs/reference/environment-variables.md`.
- **Ordering:** `remove-non-usage-limits` PR 1 (#4134, merged 2026-09-30)
  has **already** removed the project memory, daemon-wiki and UI-library caps.
  Their bytes have no bound on main until this change's gate lands, so task 3.2
  should land first among the enforcement tasks. The seats-per-account lane
  consumes `universe_owner.owner_of` and doesn't define its own.
