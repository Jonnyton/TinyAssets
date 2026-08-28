"""A bound on how many provider subprocesses may exist at once.

Measured on the live box 2026-08-28, and this is the gap it closes:

* `converse` is a **sync** MCP tool handler, so Starlette runs it in the anyio
  threadpool, whose capacity here is **40** (confirmed in production, anyio 4.14.2).
* Each turn spawns a provider CLI subprocess costing **~189 MB RSS / ~77 MB PSS** —
  and that is the floor, measured with `--version`, before any prompt, history or
  inference.
* Nothing between those two numbers bounded anything. 40 x 77 MB is 3.1 GB on a 2 GB
  box.
* The container has no memory limit, so the OOM would kill the **host**, taking the
  Cloudflare tunnel with it — a total public outage rather than a degraded service.

So the failure mode for "many simultaneous users" was not slowness, it was the box
falling over, and no amount of RAM removes an unbounded spawn. A bigger box moves the
number; a bound changes the shape.

Hard Rule 8 (fail loudly, never silently) decides the behaviour at the limit: wait
briefly for a slot, then **refuse with an honest, actionable message**. A refusal a user
can retry is strictly better than an OOM that takes every other user down with it.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager

_log = logging.getLogger(__name__)

#: Concurrent provider subprocesses permitted. The default is deliberately below the
#: anyio threadpool's 40: the threadpool bounds *handlers*, and a handler is cheap,
#: while a provider subprocess is ~77 MB of private memory. Sized for the 2 GB box
#: (6 x 77 MB is ~460 MB, leaving room for the ~390 MB daemon and page cache); raise
#: it with the RAM, not with the core count.
_LIMIT_VAR = "TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS"
_DEFAULT_LIMIT = 6

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
    import math

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


_lock = threading.Lock()
_semaphore: threading.BoundedSemaphore | None = None
_semaphore_limit = 0


def _get_semaphore() -> tuple[threading.BoundedSemaphore, int]:
    """Build (or rebuild, if the configured limit changed) the shared bound."""
    global _semaphore, _semaphore_limit
    limit = _positive_int(_LIMIT_VAR, _DEFAULT_LIMIT)
    with _lock:
        if _semaphore is None or _semaphore_limit != limit:
            _semaphore = threading.BoundedSemaphore(limit)
            _semaphore_limit = limit
        return _semaphore, _semaphore_limit


def reset_for_tests() -> None:
    global _semaphore, _semaphore_limit
    with _lock:
        _semaphore = None
        _semaphore_limit = 0


@contextmanager
def provider_slot():
    """Hold one provider-subprocess slot, or raise :class:`ProviderBusy`.

    Released on every exit path, including exceptions — a slot leaked on an error is a
    permanent capacity loss, and errors are exactly when the system is already busy.
    """
    sem, limit = _get_semaphore()
    if not sem.acquire(timeout=_positive_float(_WAIT_VAR, _DEFAULT_WAIT_S)):
        _log.warning("provider admission: all %d slots busy; refusing", limit)
        raise ProviderBusy(
            f"All {limit} provider slots are busy right now. Your universe is "
            "working on other turns — try again in a moment."
        )
    try:
        yield
    finally:
        sem.release()
