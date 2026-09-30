# Design: account storage quota

## D0. Why spec-first

This change touches storage shape (two new stores plus indexes), authority (who
owns a universe's bytes, and whose tier applies), and money (the tier gates
something real). Those are the categories AGENTS.md says to specify first.
`two-dimension-usage-limits` D5 is the target model this refines. Its review
(`REVIEW.md`, findings 10-16 and 18) is where this design starts.

## D1. The numbers: one per tier, per account

| tier | storage | seats (seats lane) |
|---|---|---|
| free | **2 GiB** | 3 |
| paid | **20 GiB** | 8 |

- **The only definition** is `usage_policy.limits_for(tier).storage_bytes`.
  Overrides are `TINYASSETS_FREE_STORAGE_GIB` and `TINYASSETS_PAID_STORAGE_GIB`.
  The `_MB` variables are unset in every deploy file (checked:
  `deploy/`, `.github/`, `environment-variables.md`). So the unit changes
  without a shim.
- **Deleted:** `effectors/workspace.py` `_universe_quota_kwargs` (the flat
  16 GiB) and `workspace_pool.admit`'s own universe-quota predicate. There is
  one quota and one place that checks it (D6).
- **Why 2 / 20.** They are the declared values already reviewed, rounded to the
  GiB unit the founder uses. 2 GiB holds a provisioned checkout of a repository
  this size: 29 MiB pack, 13 MB tree, 5,545 files, measured on this repo today.
  It also leaves room for years of chat, pages and run history. 20 GiB is 10x
  that. The seats design had floated 50 GiB for paid. That is larger than the
  production droplet's whole disk (a $12 droplet has 50 GB), so a single paid
  account could fill the box. Task 1 measures what the two test accounts
  actually hold before enforcement ships. If either is above 1 GiB, the number
  goes back to the founder rather than being enforced.

## D2. The account: a stored owner, never an inferred one

- **`universe_owner(universe_id PK, account_id, bound_at)`** lives in the
  author-server database, beside `universe_acl`. It is written in the same
  transaction as the creator's admin grant in `_action_create_universe`, and by
  `claim_founder_home` / `ensure_founder_home`. Those are the only two birth
  paths. A shared universe's other admins are never charged.
- **`accounts.owner_of(universe_id) -> account_id | None`** and
  **`accounts.tier_of(account_id)`** are the one resolver pair. The tier is read
  from the account's home universe's `.subscription_state.db`, which is where
  Stripe checkout writes it today. `universe_server._universe_birth_refusal`
  already reads it that way. The seats-per-account lane must call these rather
  than define a second pair (memory `two-definitions-of-one-fact`).
- **Backfill, from stored bindings only.** The first source is `founder_home`,
  an explicit identity binding and not a correlation. The second is the
  creation grant: a universe with exactly one admin row where
  `actor_id = granted_by`, the row `_action_create_universe` writes. Anything
  else stays unbound. Its bytes appear on a host-only "unattributed" line and
  its writes aren't gated, since there is no account to refuse against. This is
  open question Q2. The second source is a judgement call against memory
  `never-infer-identity-from-adjacent-tables`, and the founder may prefer
  `founder_home` only.

## D3. Every store, registered

Accounting enumerates stores from one registry, `storage_accounting.STORES`.
The table lists each store, where its bytes live, what attributes them, how it
is measured, and whether writes to it are gated.

| store | where | attributed by | measured how | gated |
|---|---|---|---|---|
| `universe_files` | `<data>/<uid>/**` except `.runtime/` and `workspaces/` | `owner_of(uid)` | no-follow walk, logical `st_size`, hard links counted once | files, project memory, UI library, daemon wiki |
| `workspaces` | `<uid>/workspaces/<repo>/<gen>` (published and outstanding) | `owner_of(uid)` | measured at publication and at lease release (D6) | yes |
| `run_records` | `<base>/.runs.db`: `runs`, `run_events`, `run_receipts`, … | `runs.owner_user_id`, falling back to `owner_of(queue_universe_id)` | `SUM(length(payload columns))` on indexed owner | no |
| `checkpoints` | `<base>/.langgraph_runs.db` | `thread_id → runs.thread_id → owner` | `SUM(length(checkpoint)+length(metadata))`, writes table likewise | no |
| `uploads` | `<base>/.run-file-custody` | `run_file_objects.owner_id` (already stored) | `SUM(size_bytes) WHERE state='ready'` | yes |
| `branches` | author-server `branch_definitions`, `.runs.db` `branch_versions` | `author`, `publisher` (user ids) | `SUM(length(graph_json, snapshot_json, …))` | yes |
| `commons_pages` | `<data>/wiki` | writer, recorded at write (Q3) | per-row size | yes |
| scratch | `<data>/scratch` | none (shared pool) | pool ledger, host line only | pool bounds (unchanged) |

- **Counted but excluded from the account:** `.runtime/`, the platform's own
  provider runtime. `usage_policy`'s earlier note found it to be about 99% of
  the raw footprint, and the user didn't put it there.
- **Counted and never gated:** the credential vault, session and auth stores,
  subscription state, chat history, run records and checkpoints. These bytes
  are inside `universe_files` or the shared stores above, so they show in the
  owner's number, but no write to them is refused. Refusing a vault or session
  write would lock the owner out of fixing the problem. Refusing a run's own
  record would lose work that has already been admitted.
- **Completeness guard (test).** The test drives every registered writer into a
  temporary data directory, then lists every top-level entry of `<data>` and of
  each universe directory. Each entry must be registered or on a short,
  commented `PLATFORM_OWNED` list: seat and admission ledgers, `.universe-tool-slots`,
  and transient `.workspace-staging`. A new store that nobody registered fails
  CI, because it would otherwise be an uncounted place to put bytes.

## D4. Accounting = measured + pending, with a sequence, not a reset

All of this is in `<data>/.storage_accounting.db`, resolved through
`storage.data_dir()` with the same symlink refusal `universe_seats` uses.

```
measurements(scope, store, bytes, start_seq, measured_at, PRIMARY KEY(scope, store))
    -- scope = universe_id for per-universe stores, account_id for account-keyed ones
pending(id, account_id, universe_id, store, bytes, state, lease_id,
        commit_seq, created_at)          -- state: reserved | committed
counter(seq)                             -- monotone, bumped in every commit/measure txn
```

- **Admit** (one `BEGIN IMMEDIATE`):
  `used = Σ measurements(owned scopes) + Σ pending(account)`. If `used + n ≤
  quota`, insert `pending(reserved, n)` and return the reservation. All
  admissions on the host serialize here, so two concurrent writes can't both
  see the same headroom.
- **Commit:** the writer reports the actual bytes it wrote. The state becomes
  `committed`, with `commit_seq = ++seq`. Actual bytes above the reservation are
  a bug and fail loudly; they are never clamped silently, the check
  `storage/run_files.py:272` already makes. **Release** deletes the row when the
  write didn't happen.
- **Measure** `(scope, store)`:
  1. Read `start_seq = seq`.
  2. Scan, outside any transaction.
  3. In one transaction, write the row and delete `committed` pending rows for
     that scope and store with `commit_seq < start_seq`.

  A write committed before the scan started was on disk before it started, so
  the scan saw it. A write committed later, or still `reserved`, stays in
  pending. The worst case is a transient over-count, which the next
  measurement clears. An under-count can't happen. This closes finding 10
  without a clock, the same "retain until measurement provably covers it" rule
  `workspace_pool._universe_outstanding_bytes` uses.
- **Never measured, or the measurement fails** (finding 15): the gate still
  admits while `Σ pending + n ≤ quota`. The allowance is bounded, never
  unlimited. Past that point it refuses as `storage_accounting_unavailable`
  (`actionable_by: host`), a failure class distinct from
  `storage_quota_exceeded`. It is loud in the log and on status.

### Aggregation cost

- **Gate read.** It sums at most `(#owned universes × 3) + 3` measurement rows
  plus the account's pending rows. That is microseconds, with no filesystem or
  cross-database access inside the transaction.
- **Measurement.** Only `universe_files` walks the filesystem, at O(files), and
  workspaces are excluded from that walk. A 2 GiB free account walks in well
  under a second. The shared stores cost one indexed `SUM` each. That needs two
  new indexes on `runs` and one each on `branch_versions` and
  `branch_definitions`, which are created idempotently.
- **When it runs.** A single-flight background sweep, one at a time and off the
  request path, re-measures rows that are marked dirty or older than 15 min for
  accounts active in the last day. Idle accounts cost nothing.
- **The number the owner sees** comes from `accounts.usage(account)`: the total,
  the quota, and a per-universe and per-store breakdown with `measured_at`. The
  status fields that display it belong to the seats lane (1.5) and
  limits-cleanup (3.1). This change supplies the function.

## D5. How a delete frees space

- **No negative credits.** A "freed" credit for bytes that didn't actually
  leave disk (hard links, content-addressed custody, a failed unlink) would be
  an evasion. Space is freed only when a measurement stops seeing the bytes.
- **Delete paths call `storage_accounting.touch(scope, store)`**, which marks
  the row dirty so the sweep and the status read pick it up soon. It is a
  latency aid only. Correctness doesn't depend on it.
- **The guarantee is on the refusal path.** Before returning
  `storage_quota_exceeded`, the gate re-measures every row for the account whose
  `measured_at` is older than 60 s, then admits once more. A refusal is always
  based on a fresh measurement. "Delete, then retry" therefore succeeds on the
  retry whether or not the delete path remembered to `touch`, and the
  re-measurement cost is paid only by writes that are near the quota.
- **Workspaces:** a discard completing in the outbox marks the `workspaces` row
  dirty. A replaced generation is credited at replacement time (D6), because
  `_publish` enqueues its discard in the same transaction.

## D6. Workspaces: a reservation that fits the quota

This replaces the fixed 4 GiB reservation and the pool's own quota check
(findings 13, 14 and 16).

1. **Admit in accounting first.** For a checkout:
   `headroom = quota - used(account) + bytes(the published generation this
   repo_key would replace)`. The added term is the replaced generation because
   its discard is owed atomically at publication, and the transient overlap on
   disk is the platform's to absorb.
   `reservation = min(LEASE_BOUND 4 GiB, headroom)`. If `reservation <
   MIN_WORKSPACE (64 MiB)`, refuse `storage_quota_exceeded` before any lease or
   bytes exist.
2. **`workspace_pool.admit(max_bytes=reservation)`** with no
   `universe_quota_bytes`. The pool keeps its locks, its scratch pool bound and
   its outbox. It no longer holds a second copy of the quota.
3. **Transfer** is bounded by `max_bytes` exactly as today: repository size is
   checked from the API before cloning, and a watcher kills at the bound.
4. **Before `_publish`**, measure the new generation directory after
   provisioning. If it is larger than the reservation, refuse
   `storage_quota_exceeded` and enqueue the new generation's discard. The
   published generation is untouched. Otherwise commit the reservation with the
   measured bytes. `publish_generation` takes the reservation id and refuses
   without one, so no path (a future pin included) can move bytes into
   permanent space unadmitted.
5. **Crash windows:** the pool database and the accounting database are
   separate, and each pending row carries `lease_id`. The sweep resolves a
   reservation whose lease is published, which becomes committed at the
   measured size, or released or discarded, which is deleted. Until then it
   stays counted. That errs toward over-counting, not under-counting.
6. **In-run growth is a stated non-guarantee.** A permanent workspace mounted
   read-write into a run can grow through the jail. It is measured at lease
   release. Overshoot is bounded by what one run writes under the existing jail
   limits (`ToolLimits.file_bytes` per file, and the call's wall clock). A new
   workspace job, or any gated write, on an account at or over its quota is
   refused. A kernel project quota on the data volume is the follow-up already
   named in `scratch-storage`, and is not built here.
7. **Scratch doesn't change:** it is never charged, with a 4 GiB lease bound
   and a 20 GiB pool. The per-hour `bytes_per_hour` meter (finding 18) is
   deleted by the seats lane's PR 2 (its task 2.2), not here.

## D7. Enforcement points, named exactly

The gate is `storage_accounting.reserve(account, universe, store, n)`, followed
by `commit(actual)` or `release()`, on these paths and no others.

| founder word | call site | `n` |
|---|---|---|
| files | `universe_tools.write_file` / `edit_file` (engine `write`/`edit`, agent nodes) | payload bytes |
| files | write-capable jail calls (`bash`, code-node sandbox) | 0 (refused only when at or over quota); `universe_files` marked dirty after |
| files | `memory/project.py` set, `custom_agents` UI-library save | serialized bytes |
| pages | `write_page` / `api/wiki.py` writes, universe scope, commons scope (Q3), and `daemon_memory` wiki writes | page bytes |
| uploads | `run_file_capture.capture_authoring_files` and cross-owner delivery into the **receiver's** custody (Q4) | file bytes |
| workspaces | checkout/create admission and `_publish` (D6) | fitted reservation |
| branch/version writes | `save_branch_definition`, `create_branch_definition_once`, `publish_branch_version` | serialized bytes |

- **Not gated:** everything else, listed in D3. The `bash` row is deliberately
  a check at or over the quota, not a reservation. A shell's output size can't
  be known in advance, and pretending otherwise would produce reservations that
  mean nothing.
- **Reads, lists, deletes and status never call the gate.**

## D8. The refusal

```json
{"error": "<message>", "failure_class": "storage_quota_exceeded",
 "actionable_by": "user", "used_bytes": ..., "quota_bytes": ..., "requested_bytes": ...,
 "tier": "free", "largest": [{"universe_id": ..., "store": "workspaces", "bytes": ...}, ...]}
```

The message is built by one function, with `usage_policy.upgrade_sentence`
appended:

> Your account is using 1.9 GiB of its 2 GiB of cloud storage across 3
> universes, and this write needs 150 MiB. Delete files, pages, run outputs or
> workspaces to free space, or [Upgrade](https://tinyassets.io/app?upgrade=1)
> for more storage.

- **Top tier:** `upgrade_url` returns `None`, so the sentence is empty and the
  fact stands alone.
- **`largest`** lists only the refused account's own universes. It is never
  shown to another user, including the sender of a cross-owner delivery (Q4).
- The same record surfaces in the chatbot tool result, in the universe agent's
  tool result (so it can tell the owner) and in the app. No banner, no modal.

## D9. Rejected

- **Per-writer byte counters.** More than 40 writers, and every one that is
  missed is silent. Measuring plus a completeness test fails loudly instead.
- **Resetting pending on measure.** It drops writes that land mid-scan
  (finding 10).
- **Raising free to 4 GiB so the fixed reservation fits.** That would erase the
  free/paid difference. Fitting the reservation instead fixes the actual defect.
- **Charging live scratch.** It contradicts `storage-permanent-vs-scratch`.
- **Refusing when accounting is unmeasurable.** That breaks working accounts.
  Instead the allowance is bounded, never unlimited (D4).
- **Gating the vault, sessions or chat.** That would lock the owner out of
  fixing the problem.
- **Kernel filesystem quotas now.** The droplet has no project-quota filesystem
  yet. It stays the named follow-up.

## D10. Order against other lanes

- **`remove-non-usage-limits` 1.3 already landed** (#4134, merged
  2026-09-30 07:53Z). The project memory, daemon-wiki and UI-library caps are
  gone on main now, so those write paths have no byte bound until task 3.2
  ships. That makes 3.2 the first enforcement slice to land. It is a live gap,
  not a future ordering.
- **`two-dimension-usage-limits` / seats-per-account** consume
  `accounts.owner_of` / `tier_of`. Whichever change lands first creates
  `accounts.py`, and the other rebases onto it.
- **`observe-attributable-storage`** remains the admin observation surface.
  `accounts.usage` becomes the owner-facing authority, and the observation
  helper keeps reporting its own partial, bounded view without claiming quota
  authority.

## Open questions (at the design point)

- **Q1. Numbers.** Free 2 GiB and paid 20 GiB, as proposed, or something else?
  Task 1 measures the two test accounts first.
- **Q2. Legacy owner backfill.** `founder_home` plus the sole self-granted admin
  row, as proposed, or `founder_home` only, which leaves more universes
  unattributed and ungated?
- **Q3. Commons pages.** Charge the writer, as proposed, which needs a small
  writer-attribution row per commons page because pages don't record authors
  today? Or treat the commons as platform-held and uncharged, which leaves an
  unbounded public write path?
- **Q4. Delivering a file to a full receiver.** Proposed: refuse the delivery
  against the **receiver's** quota. The sender sees "the recipient's storage is
  full" and no numbers. The receiver sees the full refusal with its link.
- **Q5. Overshoot during a run.** Is growth bounded by one run's writes (D6.6)
  acceptable for the MVP, with kernel quotas deferred?
