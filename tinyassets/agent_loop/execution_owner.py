"""The execution owner's event loop: every thin-loop turn is a task on it.

Before this, each HTTP agent turn ran ``asyncio.run`` on the worker thread
that claimed it: one event loop per turn, and the turn's whole lifetime parked
a thread. Here there is ONE long-lived loop in the process that owns execution
(target architecture D11), and a turn is an ``asyncio`` task on it. A caller on
any thread submits a turn and waits for its result; cancelling the wait
cancels the task, which cancels the box execution and closes the model stream
under it (cancellation propagates, never orphans).

The model call itself still goes through the broker's synchronous
request/close proxy, which ``ApiKeyHttpProvider`` runs on the loop's default
executor. That executor is sized for the owner's concurrency here, not left at
Python's default of ~32 threads, so 500 waiting turns do not queue behind 32
(the streaming broker contract, S6, removes the thread per waiting round).

One loop is shared, so anything synchronous a turn does ON it (a journal
write that waits on SQLite's busy timeout) stalls every turn. The owner
measures that: a watchdog records the worst scheduling lag it has seen
(``max_lag_s``) and logs each stall over :data:`LAG_WARN_SECONDS`.

Single writer. The journal is written only from tasks on this loop. The owner
lease (S8a, ``owner_generation`` on turn rows) is read through
:func:`current_owner_generation`; until S8a lands there is one owner per
process and it reports ``None``.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import logging
import os
import threading
from collections.abc import Coroutine
from typing import Any

_LOG = logging.getLogger(__name__)

#: Blocking broker calls the owner can have in flight at once.
DEFAULT_EXECUTOR_THREADS = 512
_ENV_THREADS = "TINYASSETS_AGENT_LOOP_THREADS"
#: A loop stall longer than this is logged.
LAG_WARN_SECONDS = 1.0
_LAG_TICK_SECONDS = 0.25


def current_owner_generation() -> int | None:
    """The execution owner's lease generation, once S8a provides one."""
    return None


def _executor_threads() -> int:
    raw = (os.environ.get(_ENV_THREADS) or "").strip()
    if not raw:
        return DEFAULT_EXECUTOR_THREADS
    value = int(raw)
    if value < 1:
        raise ValueError(f"{_ENV_THREADS} must be a positive integer")
    return value


class ExecutionOwner:
    """One event loop on a daemon thread, started on first use."""

    def __init__(self, *, threads: int | None = None) -> None:
        self._threads = threads
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        #: The worst scheduling delay the watchdog has measured, in seconds.
        self.max_lag_s = 0.0

    async def _watch_lag(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            due = loop.time() + _LAG_TICK_SECONDS
            await asyncio.sleep(_LAG_TICK_SECONDS)
            lag = loop.time() - due
            self.max_lag_s = max(self.max_lag_s, lag)
            if lag > LAG_WARN_SECONDS:
                _LOG.warning("agent loop stalled %.2fs: a turn ran blocking work on it", lag)

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return self._loop
            loop = asyncio.new_event_loop()
            loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(
                max_workers=self._threads or _executor_threads(),
                thread_name_prefix="agent-loop-io",
            ))
            ready = threading.Event()

            def serve() -> None:
                asyncio.set_event_loop(loop)
                loop.call_soon(ready.set)
                loop.create_task(self._watch_lag())
                loop.run_forever()

            thread = threading.Thread(target=serve, name="agent-loop-owner", daemon=True)
            thread.start()
            ready.wait()
            self._loop, self._thread = loop, thread
            return loop

    def submit(self, coroutine: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        """Run ``coroutine`` as a task on the owner loop, in the CALLER's context.

        The caller's context variables (the served request's identity, the
        owner's stop handle, the launch scope) are copied into the task, exactly
        as ``asyncio.run`` on the caller's thread would have seen them.
        Cancelling the returned future cancels the task.
        """
        loop = self._ensure()
        context = contextvars.copy_context()
        # ``run_coroutine_threadsafe`` chains cancellation both ways; the inner
        # task is what carries the caller's context.
        return asyncio.run_coroutine_threadsafe(_in_context(coroutine, context), loop)

    def run(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        """Submit and wait. If the waiting thread is interrupted, the task is cancelled."""
        future = self.submit(coroutine)
        try:
            return future.result()
        except BaseException:
            if not future.done():
                future.cancel()
            raise


async def _in_context(coroutine: Coroutine[Any, Any, Any], context: contextvars.Context) -> Any:
    # Awaiting a task that is then cancelled from outside cancels the task too.
    return await asyncio.get_running_loop().create_task(coroutine, context=context)


_OWNER = ExecutionOwner()


def execution_owner() -> ExecutionOwner:
    """The process's execution owner."""
    return _OWNER
