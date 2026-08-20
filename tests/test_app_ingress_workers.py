"""Tests for the per-conversation bounded FIFO ingress executor (Slice 2).

Concurrency is driven deterministically with ``threading.Event`` barriers — never
``sleep`` as a synchronization primitive — so the FIFO / concurrency-bound / no-
starvation guarantees are actually asserted, not merely observed by luck.
"""

from __future__ import annotations

import threading
import time

import pytest

from tinyassets.app_ingress_workers import ConversationExecutor


def _wait(pred, timeout=5.0):
    """Spin until pred() is true (bounded), returning its final value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.005)
    return pred()


def test_same_key_runs_strictly_in_order_without_overlap():
    # Deterministic (no sleep-as-sync): turn 0 HOLDS the key open on a gate, and
    # we assert turn 1 has NOT started. With max_concurrency=4 a free slot always
    # exists, so the ONLY thing that can hold turn 1 back is the same-key serial
    # rule — making the negative assertion a real proof, not a timing accident.
    ex = ConversationExecutor(max_concurrency=4, max_queue=64)
    order: list[str] = []
    lock = threading.Lock()
    gate0 = threading.Event()
    started1 = threading.Event()

    def fn0():
        with lock:
            order.append("start0")
        gate0.wait(5)  # hold the key open until the test releases it
        with lock:
            order.append("end0")

    def fn1():
        started1.set()
        with lock:
            order.append("run1")

    assert ex.submit("A", fn0) is True
    assert ex.submit("A", fn1) is True
    assert _wait(lambda: "start0" in order)  # turn 0 is running and holds key A
    # Turn 1 cannot have started: it is pending behind turn 0 on the SAME key,
    # even though 3 slots are free. (Dispatch happens under the lock at submit
    # time, so an eligible turn 1 would already be on the pool — it is not.)
    assert not started1.is_set()
    gate0.set()  # let turn 0 finish; turn 1 becomes eligible
    assert _wait(started1.is_set)
    ex.shutdown(wait=True)
    assert order == ["start0", "end0", "run1"]


def test_ready_keys_rotate_fairly_across_a_single_slot():
    # Proves the fair-rotation (Codex adapt #2): with one slot and two keys each
    # holding a backlog, dispatch INTERLEAVES the keys (a1,b1,a2,b2) instead of
    # draining one key fully first (a1,a2,b1,b2). Deterministic: a gate turn holds
    # the only slot while both backlogs are queued, so rotation — not submit
    # timing — decides the order.
    ex = ConversationExecutor(max_concurrency=1, max_queue=64)
    order: list[str] = []
    lock = threading.Lock()
    gate = threading.Event()

    def gate_turn():
        gate.wait(5)

    def make(label):
        def fn():
            with lock:
                order.append(label)
        return fn

    assert ex.submit("GATE", gate_turn) is True  # occupies the single slot
    # Queue both backlogs while the slot is held, so nothing dispatches yet.
    assert ex.submit("A", make("a1")) is True
    assert ex.submit("A", make("a2")) is True
    assert ex.submit("B", make("b1")) is True
    assert ex.submit("B", make("b2")) is True
    gate.set()  # release the slot; the 4 queued turns now drain one at a time
    assert _wait(lambda: len(order) == 4)
    ex.shutdown(wait=True)
    assert order == ["a1", "b1", "a2", "b2"]


def test_different_keys_run_concurrently():
    ex = ConversationExecutor(max_concurrency=4, max_queue=64)
    a_started = threading.Event()
    a_release = threading.Event()
    b_done = threading.Event()

    def a():
        a_started.set()
        a_release.wait(5)

    def b():
        b_done.set()

    ex.submit("A", a)
    assert _wait(a_started.is_set)      # A is running (and blocked)
    ex.submit("B", b)
    assert _wait(b_done.is_set)         # B completed WHILE A is still blocked
    assert not a_release.is_set()
    a_release.set()
    ex.shutdown(wait=True)


def test_global_concurrency_bound_holds():
    ex = ConversationExecutor(max_concurrency=2, max_queue=64)
    running = 0
    max_running = 0
    lock = threading.Lock()
    release = threading.Event()
    later_started = threading.Event()

    def holder():
        nonlocal running, max_running
        with lock:
            running += 1
            max_running = max(max_running, running)
        release.wait(5)
        with lock:
            running -= 1

    def later():
        later_started.set()

    ex.submit("k0", holder)
    ex.submit("k1", holder)
    ex.submit("k2", later)  # distinct keys, but the 2 slots are taken
    ex.submit("k3", later)
    assert _wait(lambda: running == 2)   # exactly 2 hold the 2 slots
    # No sleep-then-peek: the later turns cannot have started, because a turn that
    # would exceed the bound is never handed to the pool (dispatch is gated under
    # the lock at submit time). With both slots held, this is a real invariant.
    assert not later_started.is_set()
    release.set()
    assert _wait(later_started.is_set)   # freeing a slot lets a later turn run
    assert _wait(lambda: running == 0)
    ex.shutdown(wait=True)
    assert max_running == 2


def test_a_single_conversation_backlog_is_bounded_per_key_not_globally():
    ex = ConversationExecutor(max_concurrency=1, max_queue=2)
    release = threading.Event()
    started = threading.Event()

    def blocker():
        started.set()
        release.wait(5)

    assert ex.submit("A", blocker) is True        # A running, holds the 1 slot
    assert _wait(started.is_set)
    assert ex.submit("A", lambda: None) is True    # A backlog = 1
    assert ex.submit("A", lambda: None) is True    # A backlog = 2 (== max_queue)
    assert ex.submit("A", lambda: None) is False   # A's OWN overflow is refused
    # A different conversation is NOT penalized by A's saturated backlog.
    assert ex.submit("B", lambda: None) is True
    release.set()
    ex.shutdown(wait=True)


def test_a_saturated_key_does_not_deny_a_key_that_can_run_now():
    # Codex #2 reproduction: max_concurrency=2, one conversation saturates its
    # backlog, but a worker is idle — a different conversation that could run
    # immediately must still be admitted (the pre-fix global-count check refused
    # it, a user-triggerable denial of service).
    ex = ConversationExecutor(max_concurrency=2, max_queue=2)
    a1_started = threading.Event()
    a1_release = threading.Event()
    b_ran = threading.Event()

    def a1():
        a1_started.set()
        a1_release.wait(5)

    assert ex.submit("A", a1) is True              # A1 running (1 of 2 slots)
    assert _wait(a1_started.is_set)
    assert ex.submit("A", lambda: None) is True    # A2 pending (A backlog 1)
    assert ex.submit("A", lambda: None) is True    # A3 pending (A backlog 2 == max)
    assert ex.submit("A", lambda: None) is False   # A's own overflow refused
    # One worker is still idle; B can run NOW and must be admitted despite A's
    # saturated backlog.
    assert ex.submit("B", lambda: b_ran.set()) is True
    assert _wait(b_ran.is_set)                     # B actually ran on the idle slot
    a1_release.set()
    ex.shutdown(wait=True)


def test_a_busy_key_does_not_starve_another_key():
    ex = ConversationExecutor(max_concurrency=2, max_queue=64)
    a_release = threading.Event()
    a_first_started = threading.Event()
    b_done = threading.Event()

    def a_blocking():
        a_first_started.set()
        a_release.wait(5)

    # A big backlog on key A: the first blocks, the rest are queued behind it.
    ex.submit("A", a_blocking)
    for _ in range(5):
        ex.submit("A", lambda: None)
    assert _wait(a_first_started.is_set)
    # B must still get the OTHER slot despite A's backlog (A uses 1 slot at a time).
    ex.submit("B", lambda: b_done.set())
    assert _wait(b_done.is_set)
    a_release.set()
    ex.shutdown(wait=True)


def test_a_raising_turn_does_not_wedge_the_executor():
    ex = ConversationExecutor(max_concurrency=2, max_queue=64)
    second_ran = threading.Event()

    def boom():
        raise RuntimeError("turn blew up")

    ex.submit("A", boom)
    # Same key: the next turn must still run (key released despite the exception).
    ex.submit("A", lambda: second_ran.set())
    assert _wait(second_ran.is_set)
    ex.shutdown(wait=True)


def test_the_pool_is_prewarmed_so_dispatch_never_creates_a_thread():
    # The root fix for the partial-enqueue hazard (Codex round-5): all worker
    # threads exist BEFORE any turn is dispatched, so a runtime `submit` only ever
    # enqueues (never creates a thread) and thus cannot raise-after-enqueue.
    ex = ConversationExecutor(max_concurrency=3, max_queue=8)
    try:
        assert len(ex._pool._threads) == 3   # all workers spawned at construction
    finally:
        ex.shutdown(wait=True)


def test_submit_failure_cancels_rolls_back_and_latches_broken():
    # Codex round-9: on ANY `_pool.submit` failure (pre- OR post-enqueue, for any
    # reason) the ownership handshake cancels the turn and rolls the slot back — no
    # phantom running, no ownership inference. It also LATCHES broken so further
    # submits are refused rather than accepted-then-abandoned, and shutdown does not
    # wedge.
    ex = ConversationExecutor(max_concurrency=1, max_queue=8)

    class _RejectingPool:
        def submit(self, *a, **k):
            raise MemoryError("cannot allocate the work item")

        def shutdown(self, wait=False):
            pass

    ex._pool = _RejectingPool()

    assert ex.submit("A", lambda: None) is True   # admitted; dispatch fails + rolls back
    assert ex._running == 0                        # no phantom running
    assert "A" not in ex._active
    assert ex._broken is True                      # latched
    assert ex.submit("B", lambda: None) is False   # further submits refused
    ex.shutdown(wait=True)                          # returns — no wedge


def test_enqueue_then_raise_bails_the_wrapper_without_double_count():
    # Codex round-9 counter-path: CPython can ENQUEUE the work item and THEN raise
    # (e.g. a MemoryError allocating the thread's weakref callback) even at capacity.
    # The enqueued `_run` must BAIL (it sees the cancel latch), so `fn` never runs and
    # `_running` is not double-decremented (`-1`). The handshake is race-free because
    # the dispatch holds the lock across submit + except, and `_run` takes the lock
    # before checking the latch.
    ex = ConversationExecutor(max_concurrency=1, max_queue=8)
    real_pool = ex._pool
    ran = threading.Event()

    class _EnqueueThenRaisePool:
        def __init__(self):
            self.future = None

        def submit(self, run_fn, key, fn, slot):
            self.future = real_pool.submit(run_fn, key, fn, slot)  # ENQUEUE (runs _run)
            # Pause so the worker REACHES `_run`'s cancellation check BEFORE we raise
            # (and thus before the dispatch except sets `cancelled`). With the lock,
            # `_run` is blocked on it — the dispatch holds it across this whole call —
            # so it cannot reach the check and cannot run fn. WITHOUT the lock (the
            # mutant), `_run` reads `cancelled` (still False) and runs fn during this
            # window, which the assertions below then catch. This makes the lock the
            # thing under test, deterministically.
            time.sleep(0.3)
            raise MemoryError("allocation failed AFTER enqueue")   # ...THEN raise

        def shutdown(self, wait=False):
            real_pool.shutdown(wait=wait)

    fake = _EnqueueThenRaisePool()
    ex._pool = fake

    assert ex.submit("A", lambda: ran.set()) is True
    fake.future.result(5)                 # wait for the enqueued _run to finish (bail)
    assert not ran.is_set()               # it BAILED (cancelled); fn never ran
    assert ex._running == 0               # rolled back exactly once (not -1)
    assert "A" not in ex._active
    assert ex._broken is True
    ex.shutdown(wait=True)


def test_submit_failure_abandons_pending_so_a_waiting_drain_returns():
    # Codex round-9: a submit failure must abandon all (now-undeliverable) pending so a
    # graceful drain cannot hang. Drives a REAL waiting drain with pending work —
    # removing `_pending.clear()` leaves B/C pending forever and the drain never
    # returns. (Waking is handled by the enclosing `_run` finally, so the abandon path
    # carries no redundant notify of its own.)
    ex = ConversationExecutor(max_concurrency=1, max_queue=16)
    real_pool = ex._pool
    started = threading.Event()
    release = threading.Event()

    def blocker():
        started.set()
        release.wait(5)

    class _RejectingPool:
        def submit(self, *a, **k):
            raise MemoryError("pool exhausted")

        def shutdown(self, wait=False):
            real_pool.shutdown(wait=wait)

    assert ex.submit("A", blocker) is True        # runs on the real pool, holds slot
    assert _wait(started.is_set)
    assert ex.submit("B", lambda: None) is True   # pending
    assert ex.submit("C", lambda: None) is True   # pending
    ex._pool = _RejectingPool()                    # from now, submit fails

    done = threading.Event()
    threading.Thread(
        target=lambda: (ex.shutdown(wait=True), done.set()), daemon=True,
    ).start()
    assert _wait(lambda: ex._shutdown)            # drain has begun (blocker running)
    assert not done.is_set()                      # ...blocked: B/C pending, blocker running
    release.set()  # blocker completes -> _run redispatches B -> submit fails -> abandon
    assert done.wait(5)                           # drain returned — did NOT hang
    assert ex._pending_total() == 0               # B and C were abandoned


def test_prewarm_failure_tears_down_the_pool_and_preserves_the_original_error(monkeypatch):
    # Codex round-6/7: a construction whose pre-warm cannot start a worker must tear
    # the half-warmed pool down (no leaked threads) and fail LOUD — AND the cleanup
    # must NOT shadow the original construction error even if it itself raises.
    import tinyassets.app_ingress_workers as w

    shut = {"called": False}

    class _CantStartPool:
        def __init__(self, *a, **k):
            pass

        def submit(self, *a, **k):
            raise RuntimeError("can't start new thread")  # the ORIGINAL failure

        def shutdown(self, wait=False):
            shut["called"] = True
            raise ValueError("cleanup also blew up")       # must NOT shadow the above

    monkeypatch.setattr(w, "ThreadPoolExecutor", _CantStartPool)

    with pytest.raises(RuntimeError):                        # original, not ValueError
        w.ConversationExecutor(max_concurrency=2, max_queue=8)
    assert shut["called"] is True        # the half-warmed pool was still torn down


def test_submit_after_shutdown_is_refused():
    ex = ConversationExecutor(max_concurrency=2, max_queue=64)
    ex.shutdown(wait=True)
    assert ex.submit("A", lambda: None) is False


def test_graceful_shutdown_drains_accepted_but_pending_work():
    # A turn that submit() ACCEPTED (returned True) must still RUN on a graceful
    # shutdown, even if it was only pending (not yet running) when shutdown began
    # — a caller told True must not be silently dropped. Deterministic: the
    # blocker holds the single slot (gated) so a1/b1 are provably PENDING when
    # shutdown starts; shutdown then blocks draining until the gate releases.
    ex = ConversationExecutor(max_concurrency=1, max_queue=64)
    order: list[str] = []
    lock = threading.Lock()
    gate = threading.Event()
    started = threading.Event()

    def blocker():
        started.set()
        gate.wait(5)
        with lock:
            order.append("blocker")

    def make(label):
        def fn():
            with lock:
                order.append(label)
        return fn

    assert ex.submit("A", blocker) is True
    assert _wait(started.is_set)                 # blocker holds the only slot
    assert ex.submit("A", make("a1")) is True    # pending behind the blocker
    assert ex.submit("B", make("b1")) is True    # pending on the concurrency bound

    # shutdown(wait=True) will BLOCK draining a1/b1 until the gate releases the
    # blocker, so run it on a thread and prove it is genuinely blocked mid-drain
    # BEFORE we release (else the drain could finish before shutdown even started).
    done = threading.Event()
    threading.Thread(
        target=lambda: (ex.shutdown(wait=True), done.set()), daemon=True,
    ).start()
    assert _wait(lambda: ex._shutdown)           # shutdown has BEGUN (refuses new work)
    assert ex.submit("late", lambda: None) is False   # corroborates: shutting down
    assert not done.is_set()                     # still BLOCKED: a1/b1 not yet drained
    assert order == []                           # nothing ran (blocker holds the slot)
    gate.set()                                   # NOW release; drain finishes a1, b1
    assert done.wait(5)                          # shutdown returned only after draining
    assert order[0] == "blocker"                 # FIFO preserved through the drain
    assert set(order) == {"blocker", "a1", "b1"}  # NOTHING accepted was dropped


def test_the_global_pending_bound_caps_total_backlog_across_keys():
    # Codex #2 (round 3): the per-key cap alone let a burst across MANY distinct
    # keys grow pending without limit. The global cap bounds total backlog.
    ex = ConversationExecutor(max_concurrency=1, max_queue=8, max_total_pending=5)
    started = threading.Event()
    release = threading.Event()

    def blocker():
        started.set()
        release.wait(5)

    assert ex.submit("gate", blocker) is True    # holds the only slot
    assert _wait(started.is_set)
    # 20 DISTINCT keys, each with room in its own deque (1 < max_queue=8) but the
    # GLOBAL cap is 5 — so only 5 are admitted, not 20.
    accepted = sum(ex.submit(f"k{i}", lambda: None) for i in range(20))
    assert accepted == 5
    assert ex.submit("k-extra", lambda: None) is False   # global cap holds
    release.set()
    ex.shutdown(wait=True)


def test_shutdown_ingress_executor_drains_only_a_started_singleton():
    import tinyassets.app_ingress_workers as workers

    # Never started -> no-op, returns 0 (does not create an executor to close it).
    workers._EXECUTOR = None
    assert workers.shutdown_ingress_executor(wait=True) == 0
    assert workers._EXECUTOR is None

    # Started -> drains it and returns 0 abandoned on a clean graceful drain.
    ex = workers.get_ingress_executor()
    ran = threading.Event()
    assert ex.submit("k", lambda: ran.set()) is True
    assert _wait(ran.is_set)
    assert workers.shutdown_ingress_executor(wait=True) == 0
    assert ex.submit("k2", lambda: None) is False   # closed
    workers._EXECUTOR = None                          # isolate other tests


def test_hard_shutdown_reports_the_accepted_turns_it_abandons(caplog):
    # A hard (wait=False) shutdown cannot drain; it must not hide the loss —
    # it returns the count of accepted-but-pending turns it abandons and logs it.
    ex = ConversationExecutor(max_concurrency=1, max_queue=64)
    started = threading.Event()
    release = threading.Event()

    def blocker():
        started.set()
        release.wait(5)

    assert ex.submit("A", blocker) is True
    assert _wait(started.is_set)                  # blocker holds the only slot
    assert ex.submit("A", lambda: None) is True   # accepted, still pending
    assert ex.submit("B", lambda: None) is True   # accepted, still pending

    with caplog.at_level("WARNING"):
        abandoned = ex.shutdown(wait=False)       # immediate; cannot drain
    assert abandoned == 2                          # the loss is RETURNED, not hidden
    assert any("abandoning 2" in r.message for r in caplog.records)
    release.set()
