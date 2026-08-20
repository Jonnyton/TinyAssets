# Slice 2 — cross-family review log (Codex)

Reviewer: Codex (opposite family). Read-only, adversarial. Program: serving-reliability.

## Round 1 — build → VERDICT: adapt (4 items)

1. Shutdown drops accepted turns (post-shutdown pool submission / state corruption).
2. Fair ready-key rotation missing (a busy key monopolizes the slot).
3. Overload + escaped worker failures not surfaced to the user.
4. Racy / self-confirming tests (sleep-as-synchronization).

Resolved: OrderedDict + `move_to_end` rotation; a graceful drain; `deliver_app_notice`
for overload + escape surfacing; deterministic barrier/event tests.

## Round 2 — re-review of the adapt fixes → VERDICT: adapt (4 items)

Codex re-verified against the actual tree (ran the suite, hashed the files) and found
the first-cut fixes incomplete:

1. **Critical — drain timeout still stranded accepted work.** A 30s drain deadline set
   `_pool_closed=True` with turns still pending, while `pool.shutdown(wait=True)` kept
   blocking on the running turn — so the deadline bounded nothing and orphaned the
   pending turn permanently. `wait=False` abandoned pending work silently.
2. **Required — saturated-key admission starvation (DoS).** `submit()` bounded on the
   GLOBAL pending count, so one conversation filling the backlog rejected a different
   conversation that could run on an idle worker.
3. **Required — escaped-failure double-post.** `_run_turn` treated any exception from
   `deliver_app_event` as "its notice wasn't delivered", so a post-commit-then-raise
   could produce a second post.
4. **Required — overload notice blocked the loop / exhausted the aux pool.** The 503
   awaited the best-effort Slack post; an unreachable Slack held an AnyIO worker (~15s)
   per rejected request — user-triggerable amplification.

### Resolutions (round 2)

1. Removed the drain deadline. `wait=True` drains FULLY: dispatch stays enabled (guard
   keys off `_pool_closed`, set only after the drain) and `shutdown` blocks on a
   Condition until pending+running reach zero, so every accepted turn runs before the
   pool closes. (A wedged RUNNING turn blocks `pool.shutdown(wait=True)` identically, so
   a deadline could only strand pending turns; each turn self-bounds via Slice-1 caps.)
   `wait=False` abandons pending, logs the count LOUD, and RETURNS it.
2. Per-key admission: a turn that can start now (key idle + free slot) is always
   admitted; otherwise the bound is on THIS key's own deque. One conversation can only
   refuse its own overflow.
3. `deliver_app_event` posts AT MOST ONCE per turn: every `_post` is wrapped so a
   transport fault is logged, not propagated (reply→handled=False, notice→handled=True);
   `_record_universe` is already never-raise. Only PRE-post faults can escape, so
   `_run_turn`'s escape notice cannot double-post.
4. `_fire_best_effort_notice`: a dedicated 2-worker pool with a hard in-flight cap (8)
   that drops+logs past the cap. Overload fires the notice through it and returns the
   503 immediately; the escape notice routes through it too.

New/updated tests: `test_a_saturated_key_does_not_deny_a_key_that_can_run_now`,
`test_graceful_shutdown_drains_accepted_but_pending_work`,
`test_hard_shutdown_reports_the_accepted_turns_it_abandons`,
`test_a_reply_post_that_commits_then_raises_never_double_posts`, overload/escape async
notice waits. Local: ruff clean; 74 passed across the ingress + delivery surface.

## Round 3 — re-review of the round-2 fixes → VERDICT: adapt (3 items)

Codex confirmed the DOUBLE-POST fix is complete (provider reserve/claim/revoke +
memory load happen before posting; all three post paths catch transport ambiguity;
post-delivery recording cannot raise; routing keeps the signed fields). Three
blocking findings remained:

1. **Critical — the drain is never called in production.** `serve_in_background()`
   installs no lifecycle hook calling `shutdown()`; the executor's graceful drain was
   dead code (a "build is not run" gap). Repro: two accepted turns, normal process
   exit, only the running turn executed.
2. **Required — the starvation fix removed the global bound.** Per-key-only admission
   let 1,000 distinct keys all queue (unbounded memory).
3. **Required — the notifier leaks a permit + can raise on scheduling failure.**
   `_NOTIFIER_INFLIGHT` incremented before an unguarded `pool.submit`; a rejecting
   pool leaked the permit and 500'd the request.

### Resolutions (round 3)

1. `shutdown_ingress_executor()` helper + wired into `universe_server` create_streamable_
   http_app **lifespan finally** (the main-thread uvicorn's signal-driven shutdown runs
   it; the ingress listener is a daemon thread that never sees the signal). New test
   drives the REAL lifespan and asserts the drain runs (mutation-catching).
2. Restored a GLOBAL pending cap (`max_total_pending`, default 512, env
   `TINYASSETS_INGRESS_MAX_TOTAL_PENDING`) enforced for a turn that must wait,
   ALONGSIDE the per-key cap; the immediate-start exception is preserved. New test:
   20 distinct keys under a global cap of 5 → only 5 admitted.
3. `_fire_best_effort_notice` wraps `pool.submit`; on failure it releases the permit
   and returns False (never raises). New tests: saturation→drop→recover, and a
   rejecting pool stays leak-free across 20 attempts.

Test-gap fixes Codex named: drain test now proves shutdown is BLOCKED mid-drain
before releasing; the 503 test now BLOCKS the notice and proves the response returns
before it finishes (real decoupling proof, not an instant spy).

Local: ruff clean; ingress + workers + http + directory-app lifecycle tests green.

## Round 4 — re-review of the round-3 fixes → VERDICT: adapt (2 items)

Codex confirmed the lifecycle drain (runtime-probed: 1 `wait=True` call at teardown,
SIGTERM forwarded by tini/exec), the global+per-key bound (100-round/100-submitter
stress: exactly 5 admitted, no bypass/off-by-one), and the mutation-catching
lifecycle test are all fixed. Two remaining, both the SAME CPython edge — `pool.submit`
enqueues the work item BEFORE starting a worker thread, so a thread-creation failure
both raises AND may later run the queued item:

1. **Notifier double-release.** The queued `_wrapped` finally AND the except path both
   decrement the permit → `_NOTIFIER_INFLIGHT == -1`, defeating the cap.
2. **Dispatch wedge.** `_pool.submit` failing after the slot is claimed left a phantom
   `_running`/active key → a same-key turn could never dispatch and `shutdown(wait=True)`
   hung forever.

### Resolutions (round 4)

1. A shared lock-guarded latch (`released=[False]` + `_release()`) makes the permit
   release EXACTLY ONCE regardless of which path(s) fire. New test drives a pool that
   runs `_wrapped` then raises, asserting the counter stays 0 (never -1) over 20 iters.
2. `_dispatch_locked` wraps `_pool.submit`; on failure it rolls back
   (`_active.discard` + `_running -= 1`), logs loud, and returns (no busy-spin). The
   turn is dropped (can't run it, can't notify over a thread-starved process). New test
   injects a failing pool and asserts no phantom `_running`, key re-dispatchable, and
   `shutdown(wait=True)` returns.

Both tests are mutation-catching. Local: ruff clean; workers+http 46 passed.

## Round 5 — narrow re-review of the two round-4 fixes → VERDICT: adapt (Fix 2 only)

Fix 1 (notifier idempotent release) CONFIRMED correct (500-iter concurrent probe →
`_NOTIFIER_INFLIGHT == 0`; regression test fails on reversion). Fix 2 (dispatch rollback)
still had the partial-enqueue hazard: CPython enqueues the work item BEFORE starting a
thread, so when a worker already existed the queued `_run` still ran and its finally
double-decremented (`_running == -1`), plus a return-after-failure could strand other
eligible keys and hang `shutdown(wait=True)`.

### Resolution (round 5) — ROOT-CAUSE fix, not another rollback patch

**Pre-warm the pool** (`_prewarm_pool()` in `__init__`): submit `max_concurrency` barrier
tasks so every worker thread spawns at construction. After that `len(pool._threads) ==
max_concurrency`, so a runtime `submit` never creates a thread and cannot raise-after-
enqueue — the only remaining `submit` raise is the pre-enqueue pool/interpreter-shutdown
check, where `_run` never runs (rollback safe). Fails LOUD at construction if a thread
can't start. Defense-in-depth in the dispatch except (pre-warm-unreachable worker-died
case): `pool._threads` non-empty → turn enqueued, leave the slot claimed and let `_run`
clean up (no double-count); no worker → abandon current + all pending (undeliverable) and
`notify_all` so a drain can't hang. New tests: pre-warm thread count; live-worker no-
double-count; no-worker non-wedge. All mutation-catching. Local: ruff clean; workers 16 +
http/app_ingress 59 passed.

## Round 6 — narrow re-review of the pre-warm root fix → VERDICT: adapt (2 residuals)

Codex CONFIRMED pre-warm is correct across CPython 3.11/3.12/3.14, and that the
true-partial-enqueue-with-live-worker path retains `_active`/`_running` until `_run`
cleans up (no overlap/double-count), and drains reach idle. Two residuals:

1. `_threads` non-empty does NOT prove the work was enqueued: a PRE-enqueue reject
   (pool/interpreter shutting down) leaves threads intact, so it was misclassified as
   "enqueued" → slot stranded → `shutdown` wedged.
2. A failed pre-warm left a half-built executor (leaked threads).

### Resolution (round 6)

1. `_on_dispatch_submit_failed(key)` detects a pre-enqueue reject EXPLICITLY —
   `pool._shutdown` / `pool._broken` / `concurrent.futures.thread._shutdown` — and rolls
   back in that case (and when no worker exists), only leaving the slot claimed for a
   genuine partial enqueue (non-shutdown failure with a live worker). No worker → abandon
   all pending + notify.
2. `_prewarm_pool` wraps the barrier submits: on failure `barrier.abort()` +
   `pool.shutdown(wait=False)` + re-raise (fail loud, no leak).

New tests: pre-enqueue-reject-with-live-threads rolls back + shutdown returns; pre-warm
failure tears down the pool + raises. Both mutation-catching. Local: ruff clean; workers
18 + http/app_ingress 59 passed; full affected suite 146 passed (pre-fix).

## Round 7 — confirm of the round-6 fixes → VERDICT: adapt (make ownership definitive)

Codex's decisive critique: inferring enqueue ownership from mutable shutdown flags /
thread-set truthiness is fundamentally racy (a flag can flip after the raise; an
allocation error is not a shutdown; a thread in `_threads` may be dead). Reproduced:
non-shutdown pre-enqueue (allocation) with threads → `running=1`; flag-flip → `-1`;
prewarm `shutdown(wait=False)` shadowed the original error.

### Resolution (round 7) — capacity-based, flag-free classification

`_on_dispatch_submit_failed` now decides ownership from WORKER CAPACITY, grounded in
CPython: `submit` can only raise AFTER enqueue inside `_adjust_thread_count`, which
starts a thread solely when `len(_threads) < max_workers`; `_threads` grows
monotonically to max and never shrinks. So `0 < len(_threads) < max_concurrency`
(below capacity + worker) = a genuine post-enqueue raise → leave the slot claimed
(`_run` owns cleanup); otherwise (at capacity → any raise is pre-enqueue; or no worker)
→ roll back (+ abandon all if no worker). No shutdown flags are sampled, so the flip
race is gone; after pre-warm `len(_threads) == max` stably, so production always takes
the at-capacity roll-back path. `_prewarm_pool` cleanup is wrapped so it re-raises the
ORIGINAL construction error. New tests: at-capacity rolls back a non-shutdown
MemoryError; below-capacity+worker no double-count; no-worker abandon; prewarm failure
preserves the original error. All mutation-catching. Local: ruff clean; workers 18 +
full affected suite green.

## Round 8 — confirm of the capacity-based fix → VERDICT: adapt (capture capacity BEFORE submit)

Codex's decisive refinement: sampling `_threads` AFTER a submit failure is still not
definitive — `_adjust_thread_count` can grow `_threads` to max and THEN raise (e.g. a
MemoryError registering the new thread), so post-failure `len == max` does not prove
the pre-submit state. The definitive signal is capacity CAPTURED BEFORE submit; and
since ownership is ambiguous below capacity, do not submit there at all (the pre-warm
invariant guarantees we are always at capacity, so below-capacity is a broken
invariant).

### Resolution (round 8) — capture-before-submit, never-submit-below-capacity

`_dispatch_locked` now checks `len(_threads) >= max_concurrency` BEFORE calling
`submit`. At capacity → submit; a raise is then DEFINITIVELY pre-enqueue (`_adjust_
thread_count` is a no-op) → roll back. Below capacity → `_on_prewarm_invariant_broken`
rolls back WITHOUT submitting (no ambiguity), abandoning all pending + waking any drain
if the pool is empty. There is no longer any "leave the slot claimed" path — every
failure rolls back, because we only submit where a raise is unambiguously pre-enqueue.
This is correct by construction, not by edge-patching. New/updated tests: at-capacity
non-shutdown (MemoryError) rolls back; below-capacity never submits and abandons
pending + wakes a REAL waiting drain (mutation-complete: removing the abandon OR the
notify deadlocks it); no-worker no-wedge; prewarm failure preserves the original error.

Also fixed a TEST-only hang the pre-warm introduced: the lifespan drain test was
draining the module-singleton left by other modules; it now resets to a fresh clean
executor (tests the wiring, not accumulated global state).

Local: ruff clean; workers 18 passed; full affected suite green.

## Round 9 — confirm of capture-before-submit → VERDICT: adapt (use an ownership handshake)

Codex found the last hole: even AT capacity, `_adjust_thread_count` allocates the
thread's weakref callback BEFORE checking `len(_threads)`, so a MemoryError there raises
AFTER enqueue — capacity is not a definitive pre/post-enqueue proxy. Its prescribed
robust fix: an explicit ownership handshake, not thread-count inference.

### Resolution (round 9) — the ownership handshake (correct by lock serialization)

Each dispatch hands `_run` a per-turn `slot={"cancelled":False}`. `_dispatch_locked`
holds `self._lock` across the `submit` call AND its except; `_run` takes the lock before
reading `slot["cancelled"]`. So `_run` cannot have started when the except runs — on ANY
submit failure (pre- or post-enqueue) we set `cancelled`, latch `_broken` (future
`submit` returns False), roll back, and abandon pending; an enqueued `_run` later takes
the lock, sees `cancelled`, and bails. No `_threads`/flag inference; no double-count; no
overlap. The capacity check and `_on_prewarm_invariant_broken` are removed. The abandon
path carries no notify (redundant — the enclosing `_run` finally always notifies after,
and the submit path has no waiter during shutdown). New tests: submit-failure
cancels+rolls-back+latches-broken; enqueue-then-raise bails the wrapper (fn never runs,
`_running==0` not -1, awaited via the real Future); submit-failure abandons pending so a
real drain returns.

## Round 10 — confirm of the handshake → VERDICT: implementation CORRECT (one test strengthened)

Codex: "The implementation is correct." Confirmed airtight lock serialization (never
releases the lock or runs `_run` inline between submit and except), no false
cancellation on success, consistent `_broken` latch + abandonment, safe omission of the
abandon-path notify, and mutation-catching latch/rollback/clear assertions. The sole ask
was to make `test_enqueue_then_raise` deterministically kill a no-lock mutant: the fake
now pauses after enqueuing so the worker reaches `_run`'s cancellation check before the
except sets `cancelled` — with the lock `_run` is blocked (dispatch holds it) and cannot
run fn; without it the mutant runs fn and the test fails.

**Final:** ruff clean; workers 18 passed; full affected suite 148 passed (no hang);
mirror parity. Slice 2 LANDING.
