# Cross-family review: gpt-6-astra, round 1, 2026-09-30

`codex exec -m gpt-6-astra -s read-only` on the design at `68b96ca2`, from the PR
worktree. Asked to refute, with structured disagreement
(`AGREE` / `DISAGREE_EVIDENCE` / `DISAGREE_CONCERN`) and code citations.

**Verdict: ADAPT.** 19 findings: 0 P0, 16 P1, 3 P2. Its summary line is the useful
one: *"The two-number model is sound. The design does not yet make either number
authoritative."*

That split is what this document acts on. Seats are fixable in place and were
fixed. Storage was not sound enough to build, and is re-scoped out.

## Fixed in this change

| # | Finding | Fix | Test |
|---|---|---|---|
| 1 | Expiry reclaimed a seat unconditionally, so killing the refresher while the provider ran admitted a second holder. `automations._lease_blocks` already refuses this. | `_reap` reclaims only when the holder is not provably alive, reusing the OS-lock liveness proof `automations` maintains. | `test_a_live_holder_keeps_an_expired_seat` |
| 4 | Reference-counted re-entry let a blocked parent lend one seat to N parallel child agent nodes — N model calls on one seat. | Re-entry is an exclusive transfer: `depth = 1` predicate, so a seat is lent to one nested call at a time and a parallel sibling pays its own. | `test_a_seat_is_lent_to_one_nested_call_at_a_time` |
| 6 | The admission predicate compared TOTAL live against `seats - reserve` for background work: 3 seats, 1 reserved, 2 interactive holders refused background while a seat sat free and no background work ran. | `_admits` applies two predicates — `total < seats` always, `background < seats - reserve` for background only. A reserve bounds the class it constrains. | `test_a_reserve_bounds_background_not_the_total` |
| 2 | A seat around an enqueuing handler releases too early: `start_run` returns `queued`, and `graph_compiler` leaves a started worker running past a node timeout. | Module contract now states the seat belongs to the EXECUTING code, never the enqueuer. Placement rule, enforced at the call sites in the build. | contract; call-site tests with the sites |
| 3 | A waiter row was described as durable queued work; it is a queue position and carries no payload. | Split stated explicitly: background work is already durable in its own tables, so waiting only delays it. A synchronous `converse` turn is TOLD it is waiting and retried — the module no longer claims to replay it. | `test_an_expired_waiter_loses_only_its_position` |
| 5 | `ProviderInvocationCarrier` is immutable, non-serializable and process-bound, so it cannot carry a seat id; and a by-version invoke defaults to blocking, so depth answers the wrong question. | `parent_seat_id` is an explicit in-process parameter. A cross-process nested call takes its own seat. Inheritance keys on actual suspension, not depth. | contract; `test_another_universe_cannot_ride_a_seat_by_naming_it` |
| 7 | "Fairness" read as a promise of eventual background service, which absolute interactive priority cannot give. | Stated as a non-promise: the guarantee is one-directional (the owner's chat never waits on their automations), there is no aging, and background progress is conditional on interactive demand subsiding. | contract |
| 19 | "3 free seats is the minimum needed to demonstrate queueing" is false — 2 seats with 1 reserved gives 1 running and 3 waiting, which is a queue. | Kept 3 as a product choice and deleted the necessity argument. An argument that does not hold is worse than none. | n/a (comment) |

Findings 8 and 9 partly conceded: cross-universe *correctness* holds (separate
`universe_id` columns avoid the old `U::B` composite collision, and astra confirms
this), but it is right that a caller must not be able to *choose* its universe, and
that global ticket values leak other universes' enqueue activity. The authority
binding lands with the call sites, where the authenticated universe is available;
the ticket becomes a universe-local position on the owner-facing surface.

## Re-scoped out: storage

Eight findings (10-16, 18) are storage soundness, and one is a hard blocker:

> **16 — the proposed free quota refuses existing permanent workspace admission.**
> Workspace creation reserves a fixed 4 GiB (`effectors/workspace.py:94`, `:875`)
> and admission checks requested bytes against quota (`workspace_pool.py:946`).
> Even an empty 2 GiB free universe fails.

That directly violates the directive's own floor — *"everything we are testing
should work so neither of our users should need to upgrade"*. Shipping the quota as
designed would break permanent workspaces on free, which is worse than not shipping
it.

### Production is NOT affected today (measured 2026-09-30)

Asked before carrying on, because the finding reads like a live outage and is not.
Driving the real `workspace_pool.admit` with today's live parameters
(`max_bytes = _DEFAULT_MAX_CHECKOUT_BYTES` = 4 GiB,
`universe_quota_bytes = _DEFAULT_MAX_CHECKOUT_BYTES * 4` = 16 GiB):

| Free quota | Empty universe, one permanent workspace |
|---|---|
| **16 GiB (today's live value)** | **ADMITTED** |
| 8 GiB | ADMITTED |
| 5 GiB | ADMITTED |
| 4 GiB | ADMITTED (exactly at the boundary) |
| 2 GiB (the proposed value) | REFUSED `workspace_quota_exceeded` |

And the quota does bind correctly when a universe is genuinely full: at 13 GiB used
against the 16 GiB quota, a 4 GiB request is refused with
`workspace_quota_exceeded: 13958643712 used + 0 reserved + 4294967296 requested`.

So finding 16 is **prospective, not live**. It describes what the 2 GiB free quota
would have done had it shipped. The minimum viable free quota is
`_DEFAULT_MAX_CHECKOUT_BYTES` (4 GiB) while the reservation stays a flat 4 GiB;
anything below it refuses a permanent workspace on an empty universe.

### Two live gaps this measurement exposed, which are the storage change's real brief

1. **The quota is not tier-aware at all.** `_universe_quota_kwargs` returns a flat
   `_DEFAULT_MAX_CHECKOUT_BYTES * 4` for every universe. So *"free users have less
   cloud storage space"* is currently **not true** — free and paid have identical
   storage limits, 16 GiB each. The directive's second number is not implemented,
   rather than implemented wrongly.
2. **There are already two storage numbers for one fact.** 16 GiB hardcoded in
   `effectors/workspace.py` and enforced for workspaces only, versus
   `usage_policy`'s `_DEFAULT_FREE_STORAGE_MB = 2000` / `_PAID_STORAGE_MB = 20000`,
   declared per tier and enforced nowhere. They disagree by 8x on free. The storage
   change must collapse them, not add a third.

The fix for finding 16 is therefore not "raise the free quota to 4 GiB" — that
would make free and paid nearly equal again. It is to make the RESERVATION
incremental or quota-fitted, so a 2 GiB universe can hold a small workspace,
which is astra's own suggested remedy.

The rest are the same class: the accounting is not authoritative yet.

- **11, 12** the directory boundary is wrong. Run databases live at
  `<base>/.runs.db` and `<base>/.langgraph_runs.db`, custody at a separate
  `.run-file-custody` store — beside universe directories, not inside them. A
  universe-directory scan cannot reconcile bytes it cannot see.
- **13** scratch lives at `<data>/scratch`, BESIDE universe directories. Subtracting
  its aggregate from a universe-only scan removes bytes never included, so a large
  scratch lease masks permanent usage. And `publish_generation()` moves scratch to
  permanent without quota admission (`workspace_pool.py:1313`).
- **10** transactional reset does not make a filesystem scan transactional: reserve
  100 bytes, scan before the write lands, commit `measured=0, pending=0`, write
  lands — the bytes vanish from accounting. `workspace_pool.py:478` already retains
  reservations until measurement provably covers them, which is the pattern to copy.
- **14** "bytes admitted" has no enforced relation to bytes retained: no
  `used + growth <= quota`, no bound on actual growth, no reconciliation of failed
  writes. `storage/run_files.py:272` already checks committed size against reserved.
- **15** first-measurement failure admits writes with no bound at all, and logging
  does not bound them. Needs `storage_accounting_unavailable` distinguished from
  `storage_quota_exceeded`, and a bounded allocation rather than an unlimited path.
- **18** another per-universe hourly meter survives that the deletion scope missed:
  `workspace_pool.py:916` refuses on a rolling-hour byte sum against
  `bytes_per_hour`. Added to deletion scope.

A reserve/publish/reconcile lifecycle across four physical stores is its own change
with its own storage-shape review. It is not a task inside a seats change.

## Corrected, not fixed: the egress claim

> **17 — D7's egress premise is false.** Source-code nodes are distinct from model
> nodes (`graph_compiler.py:3804`) and effect dispatch happens after node execution
> (`graph_compiler.py:3625`), so a model-call seat does not imply every dispatch
> holds one. Concurrency times per-run bytes gives no cumulative egress bound.

Conceded. D7 claimed "nothing dispatches without holding a seat"; that is not true,
and the claim is withdrawn. The directive's deletion of the per-hour account meters
still stands — it is a directive — but the justification cannot be "seats cover it".
What covers it is a host-level bound on dispatch, which does not exist yet and is
named as an open item rather than assumed. Its absence is now a known gap with a
home, not a sentence in a design that reads as if it were handled.

This also weakens D8: "the cross-user floor is what seats enforce" is true for model
concurrency and not for bandwidth, queues, CPU or disk. Stated as such.

## Finding 1's fix was itself broken, and the test hid it

Caught by the jail-fix lane (run-owner-proof), 2026-09-30, after the fix landed.

The holder token was `f"{os.getpid()}:{_BOOT}"`. `automations._HOLDER_RE` is
`^[A-Za-z0-9_-]{1,128}$`, so the **colon** meant `holder_liveness_path` returned
`None`, every probe answered `"unknown"`, and `holder_is_provably_alive` could
never return `True`. The liveness guard in `_reap` was dead code and reaping was
timeout-only — finding 1 was not closed, only decorated.

The test did not catch it because it monkeypatched `_holder_is_alive`, the
predicate under test. That is the failure mode in memory
`my-tests-lose-to-runtime-substitution` and `silent-failure-dispatch-and-tests`:
a green test that never drives the real call.

Fixed in place (option (a)) rather than left as a seam, because it was small:

- the token is `seat<pid>_<hex>`, which the existing regex accepts;
- `_register_liveness` takes the real OS lock on the acquisition path, lazily —
  a module import must not create files;
- the liveness proof is read from **the seat store's own directory**, not
  `data_dir()`. The proof has to live beside the ledger it vouches for; reading it
  from the global root would consult the wrong process's evidence and make every
  test with an explicit `db` silently unable to see a live holder;
- the test drives a real `hold_process_liveness` lock and then **closes the fd**
  to prove the dead case, with no mock anywhere.

Three mutations, three killed — including one that only fell after a second test
was added. Removing `_register_liveness` initially left every test green, because
they all took the lock themselves: the reap predicate was proven, but nothing
proved a real seat-holder *publishes* the proof that keeps its seat.
`test_taking_a_seat_registers_this_process_as_provably_alive` closes that, and it
exists only because the mutation survived.

When jail-fix lands `process_liveness.owner_token()` / `owner_state()`, this
becomes a two-line swap at `_holder()` and `_holder_is_alive` — the seam the lead
offered as option (b) exists anyway, it just is not load-bearing in the meantime.

## Rounds

Round 1 of at most 3. Round 2 goes to the seats implementation once the call sites
land — not to the design again, which this round already moved.
