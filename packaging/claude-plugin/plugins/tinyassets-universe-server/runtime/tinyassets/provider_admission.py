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

Hard Rule 8 (fail loudly, never silently) decides the behaviour at the limit: wait
briefly for a slot, then **refuse with an honest, actionable message**. A refusal a user
can retry is strictly better than an OOM that takes every other user down with it.
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

#: Concurrent provider subprocesses permitted. 15 on the 4 vCPU / 8 GB box.
#:
#: Sized from FIVE measured points with verified overlap (live PID counts, not launch
#: counts) — my first two attempts at this number were both refuted, the second because
#: two points cannot show a trend:
#:
#:     overlap  5 -> 182 MB used     overlap 25 -> 701 MB
#:     overlap  9 -> 235 MB          overlap 33 -> 875 MB
#:     overlap 17 -> 476 MB
#:
#: Consecutive marginals: 13.25, 30.125, 28.125, 21.75 MB. Carry **31 MB** — the maximum
#: observed segment rounded up, not the mean (25.9) and not my earlier "flat ~30". The
#: 13.25 segment is warm-cache noise, and calling the series flat was another story
#: fitted to too little data.
#:
#: **The ceiling is the CGROUP, not the host.** This is the error that survived into a
#: third attempt: the box has 6907 MB available, but `deploy/compose.yml` caps this
#: daemon at 4 GiB and provider + engine-MCP children live INSIDE that cgroup. Sizing
#: against host memory would have been correct only until the compose file shipped, and
#: then silently wrong. Against the committed contract, with the observed 1411.8 MiB
#: cgroup peak and the test's 300 MiB floor:
#:
#:     4096 - 1411.8 - 300 = 2384 MiB available for turns
#:     15 x 31 x 5 = 2325 MiB    -> holds at a 5x real-turn multiplier
#:     25 x 31 x 4 = 3100 MiB    -> 25 fails at 4x
#:
#: And sensitivity is not an upper bound: "10x is the first failure" only matters if a
#: real turn is known to stay under 10x, and it is not measured. The old 77 MB PSS
#: observation was already ~2.5x this floor before counting the MCP process tree.
#:
#: A separate startup limiter is the missing piece (25 simultaneous CLI launches contend
#: across 4 cores and hurt startup p99); until one exists, 15 is the safer herd size.
#:
#: Still not a throughput claim. `get_status.provider_admission` reports `refused` and
#: `peak_concurrent`; those, not this comment, should move the number next.
_LIMIT_VAR = "TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS"
_DEFAULT_LIMIT = 15

#: How long a caller waits for a slot before being told no. Long enough to ride out a
#: brief burst, short enough that a queued user gets an answer rather than a hang.
_WAIT_VAR = "TINYASSETS_PROVIDER_ADMISSION_WAIT_S"
_DEFAULT_WAIT_S = 20.0


class ProviderBusy(RuntimeError):
    """Every provider slot is taken. The caller should surface this, not swallow it."""


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
_DEFAULT_NESTED_RESERVE = 3


def _effective_limit(nested: bool) -> int:
    """Outer callers cannot take the last ``reserve`` slots; nested work can."""
    limit = _positive_int(_LIMIT_VAR, _DEFAULT_LIMIT)
    if nested:
        return limit
    reserve = _positive_int(_NESTED_RESERVE_VAR, _DEFAULT_NESTED_RESERVE)
    # Never starve outer callers entirely: a reserve at or above the limit would refuse
    # every user turn to protect children that only exist because a turn ran.
    return max(1, limit - min(reserve, limit - 1))


def _try_acquire(timeout: float, *, nested: bool = False) -> tuple[bool, int]:
    """Take a slot, or give up after ``timeout``. Blocking — see `provider_slot_async`."""
    global _live, _peak_live, _admitted
    deadline = time.monotonic() + timeout
    with _cv:
        while True:
            limit = _effective_limit(nested)
            if _live < limit:
                _live += 1
                _peak_live = max(_peak_live, _live)
                _admitted += 1
                return True, limit
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False, limit
            _cv.wait(remaining)


def _release() -> None:
    global _live
    with _cv:
        _live -= 1
        _cv.notify()


def _refuse(limit: int) -> ProviderBusy:
    global _refused
    with _cv:
        _refused += 1
    _log.warning("provider admission: all %d slots busy; refusing", limit)
    return ProviderBusy(
        f"All {limit} provider slots are busy right now. Your universe is "
        "working on other turns — try again in a moment."
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
    with _stats_lock:
        d = sorted(_durations)
    out = {
        "limit": _positive_int(_LIMIT_VAR, _DEFAULT_LIMIT),
        "admitted": admitted,
        "refused": refused,
        "live": live,
        "peak_concurrent": peak,
        "samples": len(d),
        "sample_unit": "provider attempt, not user turn",
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
    global _live, _peak_live, _admitted, _refused
    with _cv:
        _live = _peak_live = _admitted = _refused = 0
    with _stats_lock:
        _durations.clear()


@contextmanager
def provider_slot(*, nested: bool = False):
    """Hold one provider-subprocess slot, or raise :class:`ProviderBusy`.

    **Blocking.** Only for callers that are already on a worker thread. Async callers
    must use :func:`provider_slot_async`, or they stall their event loop — Codex
    reproduced exactly that: with a blocking acquire, two coroutines gathered on one
    loop refused each other because the waiter prevented the holder from finishing.

    Released on every exit path, including exceptions — a slot leaked on an error is a
    permanent capacity loss, and errors are exactly when the system is already busy.
    """
    ok, limit = _try_acquire(_positive_float(_WAIT_VAR, _DEFAULT_WAIT_S), nested=nested)
    if not ok:
        raise _refuse(limit)
    started = time.monotonic()
    try:
        yield
    finally:
        _release()
        _record(time.monotonic() - started)


@asynccontextmanager
async def provider_slot_async(*, nested: bool = False):
    """Async-safe form: waits for a slot WITHOUT blocking the event loop.

    The wait happens on a worker thread, so other coroutines on the same loop — notably
    the ones already holding slots — keep running and can release. A blocking acquire
    here turned the bound into a self-inflicted deadlock at any limit.
    """
    # Poll with a NON-blocking attempt and yield between tries, rather than handing the
    # blocking acquire to `asyncio.to_thread`. Cancelling a `to_thread` await cancels
    # only the await: the orphaned worker goes on to acquire a slot nobody will ever
    # release. Codex reproduced exactly that — `waiter_body_entered=False, admitted=2,
    # live=1` — a permanent leak I introduced while fixing the loop-blocking bug.
    #
    # A 50 ms poll costs nothing next to a provider call measured in seconds, and it is
    # cancellation-safe by construction: nothing is in flight to abandon.
    deadline = time.monotonic() + _positive_float(_WAIT_VAR, _DEFAULT_WAIT_S)
    while True:
        ok, limit = _try_acquire(0.0, nested=nested)
        if ok:
            break
        if time.monotonic() >= deadline:
            raise _refuse(limit)
        await asyncio.sleep(0.05)
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
