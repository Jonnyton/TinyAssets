"""Bounded, per-conversation-FIFO executor for app-ingress turns (Slice 2).

An inbound app event used to run its whole turn synchronously on the Starlette
event loop, so one long turn head-of-line-blocked every other conversation. This
executor gets the turn off the loop and runs it under two guarantees:

- **Per-conversation FIFO**: turns for the same ``(workspace, channel, thread)``
  key run strictly in submission order; a user's follow-up never overtakes its
  predecessor.
- **Bounded global concurrency**: at most ``max_concurrency`` turns (and thus
  ``claude -p`` subprocesses) run at once; the pending backlog is bounded, and a
  submission past the backlog is refused so the caller can post a truthful
  overload notice instead of dropping work or growing without limit.

A key waiting for its slot never occupies a worker thread (no pool starvation):
the executor tracks per-key queues + an ``active`` set and only dispatches a key's
next item when the previous one finishes AND a concurrency slot is free.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict, deque
from collections.abc import Callable, Hashable
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class ConversationExecutor:
    """Keyed, bounded, FIFO turn executor. Thread-safe."""

    def __init__(
        self,
        max_concurrency: int = 4,
        max_queue: int = 64,
        max_total_pending: int = 512,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if max_queue < 1:
            raise ValueError("max_queue must be >= 1")
        if max_total_pending < 1:
            raise ValueError("max_total_pending must be >= 1")
        self._max_concurrency = max_concurrency
        self._max_queue = max_queue  # per-conversation-key backlog cap
        self._max_total_pending = max_total_pending  # global backlog cap (memory)
        self._pool = ThreadPoolExecutor(
            max_workers=max_concurrency, thread_name_prefix="ingress-turn"
        )
        self._lock = threading.Lock()
        # Signalled when the executor goes idle (nothing pending, nothing
        # running). A graceful shutdown waits on this to DRAIN accepted work.
        self._idle = threading.Condition(self._lock)
        # Per-key FIFO of pending work, ORDERED for fair cross-key rotation: a key
        # that just had an item dispatched is moved to the back (Codex adapt #2),
        # so a busy key cannot starve a key that keeps arriving. A key with an
        # empty deque is removed.
        self._pending: OrderedDict[Hashable, deque[Callable[[], None]]] = OrderedDict()
        # Keys with a turn currently running (at most one running turn per key).
        self._active: set[Hashable] = set()
        # Count of turns currently running (the global concurrency bound).
        self._running = 0
        # ``_shutdown`` refuses NEW submits; ``_pool_closed`` is set only once the
        # pool is actually being torn down. Dispatch keys off _pool_closed (not
        # _shutdown) so a graceful shutdown can still DRAIN accepted-but-pending
        # work through the normal FIFO+bounded path before the pool closes.
        self._shutdown = False
        self._pool_closed = False
        # Latched once a `_pool.submit` fails (pool broken / out of resources). From
        # then on `submit` refuses new work rather than accepting-then-abandoning it.
        self._broken = False
        self._prewarm_pool()

    def _prewarm_pool(self) -> None:
        """Force all worker threads to spawn NOW, so a runtime ``submit`` never
        creates a thread.

        This is what makes dispatch partial-enqueue-safe (Codex round-5): CPython's
        ThreadPoolExecutor ENQUEUES a work item BEFORE it starts a worker thread, so
        a dispatch-time thread-creation failure could otherwise both raise AND still
        run the turn — corrupting the running count and per-key serialization. With
        the pool pre-warmed, the only remaining ``submit`` raise is the pool/
        interpreter shutdown check, which happens BEFORE the enqueue (so the turn
        never runs and a rollback is safe). If thread creation is going to fail, this
        fails LOUD at construction rather than mid-conversation.
        """
        barrier = threading.Barrier(self._max_concurrency + 1)
        try:
            for _ in range(self._max_concurrency):
                # Each task occupies its worker until ALL have started, forcing the
                # pool to spawn a distinct thread per task (an idle thread would be
                # reused).
                self._pool.submit(barrier.wait)
            barrier.wait(timeout=30)  # release them once every worker thread exists
        except BaseException:
            # A worker could not be started (or the barrier timed out): tear the
            # half-warmed pool down so we do not leak the threads that DID start,
            # then fail LOUD (a construction that cannot pre-warm is not usable). The
            # cleanup itself must NEVER shadow the original construction failure, so
            # swallow any error it raises and re-raise the original (bare `raise`).
            try:
                barrier.abort()  # release any workers already parked on the barrier
                self._pool.shutdown(wait=False)
            except BaseException:  # noqa: BLE001 - cleanup must not mask the real error
                logger.exception("ingress executor: pre-warm cleanup failed")
            raise

    def _pending_total(self) -> int:
        return sum(len(q) for q in self._pending.values())

    def submit(self, key: Hashable, fn: Callable[[], None]) -> bool:
        """Queue ``fn`` for conversation ``key``.

        Returns True if admitted, False if a bound is full (the caller should then
        post a truthful overload notice — the work is NOT queued).

        Two bounds guard a turn that must WAIT (Codex #2): a PER-KEY cap so one busy
        conversation cannot fill a shared queue and lock others out (a user-
        triggerable DoS), AND a GLOBAL cap so a burst across many distinct keys
        cannot grow memory without limit. A turn that can start immediately (its key
        is idle and a concurrency slot is free) bypasses BOTH — it dispatches at
        once rather than sitting in the backlog, so it cannot accumulate (at most
        ``max_concurrency`` such turns exist at any instant). A key's memory is
        reclaimed when its deque empties.
        """
        with self._lock:
            if self._shutdown or self._broken:
                return False
            # A conversation that can run RIGHT NOW (key idle + a free slot) is
            # admitted unconditionally — another key's backlog must never deny it.
            can_run_now = (
                key not in self._active and self._running < self._max_concurrency
            )
            if not can_run_now:
                # This turn must wait — enforce BOTH backpressure bounds.
                if len(self._pending.get(key, ())) >= self._max_queue:
                    return False  # this key's own backlog is full
                if self._pending_total() >= self._max_total_pending:
                    return False  # the global backlog is full (memory guard)
            self._pending.setdefault(key, deque()).append(fn)
            self._dispatch_locked()
            return True

    def _dispatch_locked(self) -> None:
        """Start as many eligible key-turns as slots allow. Caller holds the lock.

        Eligible = a key with pending work that is NOT already running a turn.
        A dispatched key with remaining work is moved to the BACK of the ordered
        map so different keys take turns (fair rotation, Codex adapt #2).
        """
        # Never submit into a pool that is being torn down (Codex adapt #1): the
        # in-flight ``_run`` finally re-enters here, and submitting to an
        # already-closed pool would raise / corrupt state. This guards on
        # ``_pool_closed``, NOT ``_shutdown``, so a graceful ``shutdown(wait=True)``
        # can keep dispatching accepted-but-pending work through this normal path
        # (preserving FIFO + the concurrency bound) until it fully drains.
        if self._pool_closed:
            return
        while self._running < self._max_concurrency:
            next_key = None
            for key, q in self._pending.items():
                if q and key not in self._active:
                    next_key = key
                    break
            if next_key is None:
                return  # no eligible key (all pending keys are already running)
            fn = self._pending[next_key].popleft()
            if self._pending[next_key]:
                self._pending.move_to_end(next_key)  # fair: go to the back
            else:
                del self._pending[next_key]
            self._active.add(next_key)
            self._running += 1
            # Ownership HANDSHAKE (Codex round-9): sampling `_threads`/flags to decide
            # whether a raising `submit` enqueued the work item is unsound — CPython
            # can enqueue and THEN raise (e.g. a MemoryError allocating the thread's
            # weakref callback) even at capacity. Instead, hand `_run` a per-dispatch
            # ``slot``. We hold the lock across `submit` AND this except, and `_run`
            # takes the lock before doing anything, so `_run` cannot have started here:
            # on ANY submit failure we mark the slot cancelled (an enqueued `_run` will
            # bail) and roll back — no double-count, no ownership inference.
            slot = {"cancelled": False}
            try:
                self._pool.submit(self._run, next_key, fn, slot)
            except BaseException:  # noqa: BLE001
                # The pool is unusable (shutting down, broken, or out of resources).
                # Cancel this turn's enqueued copy, roll the slot back, LATCH broken so
                # future submits are refused rather than accepted-then-dropped, and
                # abandon all pending (undeliverable now) so a graceful drain cannot
                # hang. Fail LOUD.
                slot["cancelled"] = True
                self._broken = True
                self._active.discard(next_key)
                self._running -= 1
                abandoned = self._pending_total() + 1
                self._pending.clear()
                logger.error(
                    "ingress executor: turn scheduling failed; latched broken and "
                    "abandoned %d turn(s)", abandoned,
                )
                # A waiting drain is woken by the enclosing `_run` finally (which
                # notifies after this returns) or by other still-running turns'
                # finallies — the submit path has no waiter (submits are refused during
                # shutdown), so no notify is needed here. Clearing pending is what
                # keeps the drain from hanging.
                return

    def _run(self, key: Hashable, fn: Callable[[], None], slot: dict) -> None:
        """Run one turn on a pool thread (OFF the lock), then release + redispatch.

        The first action, under the lock, is the ownership handshake: if the dispatch
        that submitted this turn saw ``submit`` raise, it marked ``slot["cancelled"]``
        and already rolled the slot back — so this (possibly still-enqueued) copy must
        BAIL without running the turn or touching the accounting. Because
        ``_dispatch_locked`` holds the lock across the ``submit`` call and its except
        handler, this check cannot race that rollback: we either see ``cancelled`` and
        bail, or we are the sole owner and run + clean up (Codex round-9).
        """
        with self._lock:
            if slot["cancelled"]:
                return  # dispatch already rolled this slot back; do not double-count
        try:
            fn()
        except Exception:  # noqa: BLE001 - one turn's failure must not wedge the pool
            logger.exception("ingress turn failed for conversation key %r", key)
        finally:
            with self._lock:
                self._active.discard(key)
                self._running -= 1
                # The just-finished key may have more queued work (its next item
                # is now eligible), and freeing a slot may let another key start.
                self._dispatch_locked()
                # Wake a graceful shutdown that is draining accepted work once the
                # executor reaches idle (nothing pending, nothing running).
                if not self._pending and self._running == 0:
                    self._idle.notify_all()

    def shutdown(self, wait: bool = False) -> int:
        """Stop accepting work, then tear down the pool. Returns turns abandoned.

        ``wait=True`` fully DRAINS accepted work: every turn ``submit`` admitted
        (running AND pending) runs to completion through the normal FIFO+bounded
        path before the pool closes — a caller told ``True`` is never silently
        dropped, and dispatch stays enabled until nothing is pending or running.
        There is deliberately NO drain deadline: a wedged RUNNING turn would block
        ``pool.shutdown(wait=True)`` identically, so a deadline could only strand
        still-pending turns without bounding anything (each turn already self-bounds
        via the provider stream caps). Returns 0.

        A hard ``wait=False`` cannot drain; it abandons still-pending turns, fails
        LOUD about the count, and RETURNS that count so the caller can react. In
        both modes the pool is closed only after the (possibly empty) drain, so the
        ``_run`` finally re-entry can never submit into an already-closed pool.
        """
        abandoned = 0
        with self._lock:
            if self._pool_closed:
                return 0
            self._shutdown = True  # refuse NEW submits immediately
            if wait:
                while self._pending or self._running > 0:
                    self._idle.wait()
            else:
                abandoned = self._pending_total()
                if abandoned:
                    logger.warning(
                        "ingress executor: hard shutdown abandoning %d accepted "
                        "queued turn(s)", abandoned,
                    )
            self._pool_closed = True  # from here _dispatch_locked is a no-op
        self._pool.shutdown(wait=wait)
        return abandoned


_EXECUTOR: ConversationExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def _int_env(name: str, default: int) -> int:
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return val if val >= 1 else default


def get_ingress_executor() -> ConversationExecutor:
    """The process-wide ingress turn executor (bounds from env, safe defaults)."""
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ConversationExecutor(
                max_concurrency=_int_env("TINYASSETS_INGRESS_MAX_CONCURRENCY", 4),
                max_queue=_int_env("TINYASSETS_INGRESS_MAX_QUEUE", 64),
                max_total_pending=_int_env(
                    "TINYASSETS_INGRESS_MAX_TOTAL_PENDING", 512
                ),
            )
        return _EXECUTOR


def shutdown_ingress_executor(wait: bool = True) -> int:
    """Drain + close the process-wide ingress executor IF it was started.

    Wired into the daemon's shutdown lifecycle so a graceful restart drains the
    accepted turns instead of dropping them (Codex #1: the executor's own
    ``shutdown`` is only useful if something actually calls it in production).
    Returns the number of accepted turns abandoned (0 if it drained cleanly or the
    executor was never created — no Slack turn ever arrived).
    """
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        ex = _EXECUTOR
    if ex is None:
        return 0
    return ex.shutdown(wait=wait)
