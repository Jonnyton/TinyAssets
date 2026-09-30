"""A bound on how many provider subprocesses may exist at once.

Measured on the live box 2026-08-28, and this is the gap it closes:

* `converse` is a **sync** MCP tool handler, so Starlette runs it in the anyio
  threadpool, whose capacity here is **40** (confirmed in production, anyio 4.14.2).
* Each turn spawns a provider CLI subprocess costing **~189 MB RSS / ~77 MB PSS** —
  and that is the floor, measured with `--version`, before any prompt, history or
  inference.
* The container has no memory limit, so an overshoot OOMs the **host**, taking the
  Cloudflare tunnel with it — a total public outage rather than a degraded service.

**The honest ceiling was 8, not 40**, and I said 40 first. `converse` reaches providers
through `call_provider` -> `ProviderRouter.call_sync`, which runs the async chain on a
thread pool of `_SYNC_CALL_MAX_WORKERS = 8`. So 8 x 77 MB is ~620 MB beside a ~390 MB
daemon: tight on a 2 GB box, not the 3.1 GB catastrophe.

That does not make an explicit bound unnecessary, and it is worth being precise about
why. The 8 was **incidental**: its own comment says it exists to stop one slow provider
serializing other sync callers — a LATENCY rationale that happens to cap memory as a side
effect. Anyone raising it for throughput, which is exactly what someone chasing capacity
would do, would silently multiply memory risk with no sign that they had. A bound whose
stated purpose is the thing it protects can be reasoned about; one that protects by
accident cannot.

Behaviour at the limit is to **WAIT**, not to refuse (founder, 2026-09-30: over the
concurrency line work waits and is never refused). The bound still exists — it is a
memory floor on a shared box, not an account limit — but a caller that arrives with
every slot taken queues for one and is told it is waiting.

The queue is not unbounded, and it is worth being precise about why, because "wait
forever" is the shape that turns a bound into a hang:

* A **sync** waiter occupies its caller's thread. `converse` runs in Starlette's anyio
  threadpool (capacity 40 here), so the depth of the sync queue is bounded by that pool,
  which is the transport's own pre-existing bound. A waiter costs a thread; it does NOT
  cost the ~189 MB subprocess the limit exists to stop. Forty parked threads are cheap
  where forty subprocesses are an OOM.
* An **async** waiter polls with `asyncio.sleep`, so it costs no thread at all and never
  stalls the loop that holds the slots it is waiting on.
* Waiting is **visible**: `on_wait` fires once when a caller actually queues, and
  `get_status.provider_admission` publishes `waiting` plus the wait-time quantiles. A
  wait nobody can see is indistinguishable from a hang, which is the real failure here.

One caller still wants an immediate answer: the Codex auth probe, a diagnostic that
should report "inconclusive" rather than queue behind real user turns. That is what
:func:`try_provider_slot` is for, and it is the only thing that raises
:class:`ProviderBusy`. A user turn never sees it.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
from contextlib import asynccontextmanager, contextmanager

_log = logging.getLogger(__name__)

#: Concurrent provider subprocesses permitted. **Stays at 6 until a real turn's
#: high-water is measured**, and the story of why is worth keeping.
#:
#: I first derived 6 from "~77 MB PSS each", taken from four concurrent processes and
#: extrapolated linearly. Suspecting that was too conservative, I re-measured with
#: verified overlap and proposed raising it to 10. Cross-family review refuted that too,
#: and my arithmetic was the problem:
#:
#:     verified overlap 13 -> MemAvailable 874 MB
#:     verified overlap 25 -> MemAvailable 403 MB
#:
#:   * I called 786/25 = 31 MB the "marginal" cost. It is the AVERAGE. The marginal
#:     slope between the two points is (874-403)/(25-13) = **39 MB**.
#:   * Per-process cost therefore ROSE with concurrency (24 MB/process at 13, 39 MB
#:     marginal from 13 to 25). My claim that page sharing improves with concurrency was
#:     the opposite of what my own two points said. I fitted a story to two data points
#:     and got the sign wrong.
#:   * My headroom check used 2048 MB total, but the probe's real baseline was 1189 MB
#:     AVAILABLE. The missing 859 MB is roughly 390 MB of daemon plus ~469 MB of kernel,
#:     Docker, tunnel and other services — none of it spendable. Against the right
#:     baseline, 10 x 39 x 3 leaves about 19 MB (12 MB on the unrounded 39.25 slope).
#:     Either way it is not headroom.
#:
#: And `--version` is not the production process tree: a real turn runs `claude -p` with
#: a system prompt, streaming state and tool policy, and when engine MCP is enabled it
#: starts a SECOND Python/FastMCP process. So the floor I measured is not one process.
#:
#: The honest position: 6 is not proven optimal, it is proven not-yet-refuted. The number
#: moves when `get_status.provider_admission` has real turns in it — `refused` rising
#: while `peak_concurrent` sits at the limit is the evidence that would justify raising
#: it, and nothing else should.
_LIMIT_VAR = "TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS"
_DEFAULT_LIMIT = 6

#: How often an async waiter re-tries. A sync waiter uses the condition variable and
#: needs no poll. There is no wait DEADLINE: the 20-second one that used to live here
#: (`TINYASSETS_PROVIDER_ADMISSION_WAIT_S`) turned a busy moment into a refusal the user
#: had to retry by hand, which is the behaviour the founder's directive removes.
_POLL_SECONDS = 0.05


class ProviderBusy(RuntimeError):
    """Every provider slot is taken, and this caller asked NOT to wait.

    Raised only by :func:`try_provider_slot`. The user-facing paths
    (:func:`provider_slot`, :func:`provider_slot_async`) wait instead.
    """


def _positive_int(var: str, default: int) -> int:
    raw = (os.environ.get(var) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        _log.warning("%s=%r is not an integer; using %d", var, raw, default)
        return default
    return value if value > 0 else default


def _positive_float(var: str, default: float) -> float:
    raw = (os.environ.get(var) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value) or value <= 0:
        return default
    return value


#: A Condition + explicit counter rather than a BoundedSemaphore.
#:
#: A semaphore has to be REPLACED when the configured limit changes, and Codex
#: reproduced what that costs: existing holders keep the old object, so two holders
#: under limit=2 plus one admission after dropping to limit=1 gave
#: `{'limit': 1, 'live': 3}` — the advertised bound violated by its own reconfiguration.
#: A counter compared against the CURRENT limit at admission time cannot do that;
#: lowering the limit simply drains as holders finish.
_cv = threading.Condition()
_live = 0
_peak_live = 0
_admitted = 0
_refused = 0
#: Callers currently QUEUED for a slot. Declared here, not only assigned inside
#: `reset_for_tests`: a module global that only a test helper creates reads fine
#: under pytest and raises `NameError` from `admission_snapshot` in production,
#: which is how a status surface breaks with a green suite.
_waiting = 0


#: Slots held back for NESTED work. A served turn holds a slot for the whole life of its
#: provider subprocess, and that subprocess is an agent that can call `run_graph` — whose
#: nodes need slots of their own. With every slot taken by outer turns, the children
#: queue behind their own parents and fail (Codex reproduced six outer holders producing
#: six AllProvidersExhaustedError and zero nested launches).
#:
#: I first deferred this as needing a design change, on the grounds that nothing marks a
#: call as nested. That was wrong, and Codex showed why: `run_graph` child calls already
#: carry a typed `provider_invocation` carrier, so the distinction is available for free
#: at the point it is needed. Arbitrary deeper recursion would still need propagated
#: depth — this covers the served-root -> child topology that is actually reachable.
_NESTED_RESERVE_VAR = "TINYASSETS_PROVIDER_NESTED_RESERVE"
_DEFAULT_NESTED_RESERVE = 1


def _effective_limit(nested: bool) -> int:
    """Outer callers cannot take the last ``reserve`` slots; nested work can."""
    limit = _positive_int(_LIMIT_VAR, _DEFAULT_LIMIT)
    if nested:
        return limit
    reserve = _positive_int(_NESTED_RESERVE_VAR, _DEFAULT_NESTED_RESERVE)
    # Never starve outer callers entirely: a reserve at or above the limit would refuse
    # every user turn to protect children that only exist because a turn ran.
    return max(1, limit - min(reserve, limit - 1))


def _take_locked(nested: bool) -> int | None:
    """Take a slot if one is free, under ``_cv``. Returns the limit if not."""
    global _live, _peak_live, _admitted
    limit = _effective_limit(nested)
    if _live < limit:
        _live += 1
        _peak_live = max(_peak_live, _live)
        _admitted += 1
        return None
    return limit


def _try_acquire_now(*, nested: bool = False) -> tuple[bool, int]:
    """Take a slot if one is free right now. Never waits."""
    with _cv:
        limit = _take_locked(nested)
        return (True, _effective_limit(nested)) if limit is None else (False, limit)


def _acquire_waiting(*, nested: bool, on_wait) -> int:
    """WAIT for a slot and take it. Blocking; returns the limit in force.

    No deadline and no refusal. ``on_wait`` fires once, with the limit, the first
    time this call actually has to queue -- a caller with a user in front of it
    turns that into a visible waiting state.
    """
    global _waiting
    announced = False
    started = time.monotonic()
    with _cv:
        while True:
            limit = _take_locked(nested)
            if limit is None:
                if announced:
                    _waiting -= 1
                    _record_wait(time.monotonic() - started)
                return _effective_limit(nested)
            if not announced:
                announced = True
                _waiting += 1
                _log.info("provider admission: all %d slots busy; waiting", limit)
                if on_wait is not None:
                    try:
                        on_wait(limit)
                    except Exception:  # noqa: BLE001 - telling someone must not fail the turn
                        _log.warning("provider admission: on_wait raised", exc_info=True)
            _cv.wait(1.0)


def _release() -> None:
    global _live
    with _cv:
        _live -= 1
        # notify_all, not notify: async waiters do not sit on the condition
        # variable, and a sync waiter woken for a slot another thread took must
        # re-check rather than the wake being consumed and lost.
        _cv.notify_all()


def _refuse(limit: int) -> ProviderBusy:
    """Only for :func:`try_provider_slot` -- a caller that asked not to wait."""
    global _refused
    with _cv:
        _refused += 1
    _log.info("provider admission: all %d slots busy; caller declined to wait", limit)
    return ProviderBusy(
        f"All {limit} provider slots are busy and this caller does not wait."
    )


#: Rolling record of what actually happened here. This exists because capacity in
#: USERS is `slots / turn_duration`, and turn duration was not recorded anywhere: the
#: `started_at`/`finished_at` columns on `run_events` sit microseconds apart with one
#: event per run, so they are bookkeeping, not execution spans. Without this you can
#: state a slots number and cannot honestly state a users-per-box number.
#:
#: Deliberately in-memory and bounded. A capacity metric that itself needs a database
#: write per turn would be adding load to the thing it measures.
_MAX_SAMPLES = 512
_stats_lock = threading.Lock()
_durations: list[float] = []
#: How long queued callers actually waited. Published so a wait that has become a
#: hang is visible as a number rather than as silence.
_waits: list[float] = []


def admission_snapshot() -> dict:
    """What the bound has actually seen. Surfaced through `get_status`.

    Deliberately reports NO derived throughput figure. The obvious one, `limit / p50`,
    is wrong twice over (Codex, 2026-08-28): Little's Law needs effective concurrency
    over MEAN service time, not the limit over a median; and these samples are provider
    *attempts*, so a fallback chain or a judge ensemble contributes several samples per
    user turn while fast failures inflate the median and slow ones deflate it. Reporting
    the raw observations and letting a human do the arithmetic beats publishing a number
    that reads authoritative and is not.
    """
    with _cv:
        live, peak, admitted, refused = _live, _peak_live, _admitted, _refused
        waiting = _waiting
    with _stats_lock:
        d = sorted(_durations)
        w = sorted(_waits)
    out = {
        "limit": _positive_int(_LIMIT_VAR, _DEFAULT_LIMIT),
        "admitted": admitted,
        # Callers that declined to wait (the auth probe). A user turn waits, so
        # this is NOT a count of refused work.
        "refused_no_wait": refused,
        "live": live,
        "waiting": waiting,
        "peak_concurrent": peak,
        "samples": len(d),
        "sample_unit": "provider attempt, not user turn",
    }
    if w:
        out["wait_seconds"] = {
            "count": len(w),
            "p50": round(w[len(w) // 2], 2),
            "max": round(w[-1], 2),
        }
    if d:
        def _q(p: float) -> float:
            # One indexing rule for every quantile. Mixing `len//2` for the median with
            # `int(len*p)-1` for the rest made p90 come out BELOW p50 on small samples
            # (two samples gave p50=0.03, p90=0.01) — a monotonicity violation that
            # reads as a measurement bug in whatever consumes it.
            idx = min(len(d) - 1, max(0, math.ceil(p * len(d)) - 1))
            return round(d[idx], 2)

        out["attempt_seconds"] = {
            "p50": _q(0.50),
            "p90": _q(0.90),
            "p99": _q(0.99),
            "mean": round(sum(d) / len(d), 2),
            "max": round(d[-1], 2),
        }
    return out


def reset_for_tests() -> None:
    global _live, _peak_live, _admitted, _refused, _waiting
    with _cv:
        _live = _peak_live = _admitted = _refused = _waiting = 0
    with _stats_lock:
        _durations.clear()
        _waits.clear()


@contextmanager
def provider_slot(*, nested: bool = False, on_wait=None):
    """WAIT for one provider-subprocess slot, then hold it. Never refuses.

    **Blocking.** Only for callers that are already on a worker thread. Async callers
    must use :func:`provider_slot_async`, or they stall their event loop — Codex
    reproduced exactly that: with a blocking acquire, two coroutines gathered on one
    loop refused each other because the waiter prevented the holder from finishing.

    ``on_wait(limit)`` fires once if this call has to queue, so a surface with a user
    in front of it can say so.

    Released on every exit path, including exceptions — a slot leaked on an error is a
    permanent capacity loss, and errors are exactly when the system is already busy.
    """
    _acquire_waiting(nested=nested, on_wait=on_wait)
    started = time.monotonic()
    try:
        yield
    finally:
        _release()
        _record(time.monotonic() - started)


@contextmanager
def try_provider_slot(*, nested: bool = False):
    """Hold a slot IF one is free right now, else raise :class:`ProviderBusy`.

    For diagnostics only. A probe that queues behind real user turns is reporting on
    a box it is itself loading, and the answer it eventually gives is about the past.
    """
    ok, limit = _try_acquire_now(nested=nested)
    if not ok:
        raise _refuse(limit)
    started = time.monotonic()
    try:
        yield
    finally:
        _release()
        _record(time.monotonic() - started)


@asynccontextmanager
async def provider_slot_async(*, nested: bool = False, on_wait=None):
    """Async-safe form: WAITS for a slot without blocking the event loop. Never refuses.

    The wait costs no thread, so other coroutines on the same loop — notably the ones
    already holding slots — keep running and can release. A blocking acquire here
    turned the bound into a self-inflicted deadlock at any limit.

    ``on_wait(limit)`` fires once if this call has to queue.
    """
    # Poll with a NON-blocking attempt and yield between tries, rather than handing a
    # blocking acquire to `asyncio.to_thread`. Cancelling a `to_thread` await cancels
    # only the await: the orphaned worker goes on to acquire a slot nobody will ever
    # release. Codex reproduced exactly that — `waiter_body_entered=False, admitted=2,
    # live=1` — a permanent leak I introduced while fixing the loop-blocking bug.
    #
    # A 50 ms poll costs nothing next to a provider call measured in seconds, and it is
    # cancellation-safe by construction: nothing is in flight to abandon. Cancellation
    # is also the only way out of this wait, which is what makes an unbounded wait
    # acceptable here: the client disconnecting cancels the task.
    global _waiting
    announced = False
    started_wait = time.monotonic()
    try:
        while True:
            ok, limit = _try_acquire_now(nested=nested)
            if ok:
                break
            if not announced:
                announced = True
                with _cv:
                    _waiting += 1
                _log.info("provider admission: all %d slots busy; awaiting one", limit)
                if on_wait is not None:
                    try:
                        on_wait(limit)
                    except Exception:  # noqa: BLE001
                        _log.warning("provider admission: on_wait raised", exc_info=True)
            await asyncio.sleep(_POLL_SECONDS)
    finally:
        if announced:
            with _cv:
                _waiting -= 1
            _record_wait(time.monotonic() - started_wait)
    started = time.monotonic()
    try:
        yield
    finally:
        _release()
        _record(time.monotonic() - started)


def _record(elapsed: float) -> None:
    """Time every exit, failures included. A turn that died after 40 s occupied a slot
    for 40 s; excluding it would flatter the numbers in the conditions worth measuring."""
    with _stats_lock:
        _durations.append(elapsed)
        if len(_durations) > _MAX_SAMPLES:
            del _durations[: len(_durations) - _MAX_SAMPLES]


def _record_wait(elapsed: float) -> None:
    """How long a queued caller waited. Bounded like `_durations`: an unbounded list
    behind an unbounded wait would be the second leak of the same shape."""
    with _stats_lock:
        _waits.append(elapsed)
        if len(_waits) > _MAX_SAMPLES:
            del _waits[: len(_waits) - _MAX_SAMPLES]
