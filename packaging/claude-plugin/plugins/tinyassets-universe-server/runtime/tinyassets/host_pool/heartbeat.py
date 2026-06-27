"""Host-pool heartbeat loop.

Bimodal heartbeat per design call 2026-04-20: ``updated_at`` bump via
PATCH every 5 min (configurable). DB row is the liveness source of
truth pre-Realtime; Presence takes over once Realtime wires in, at
which point this loop's cadence can drop to ~hourly or retire.

Consciously chose 5 min instead of 30s to respect the schema design's
write-amp budget (167 writes/sec at 10k hosts @ 60s = 333/s @ 30s;
dropping to 5 min = ~33/s at 10k scale, tolerable).

Runs in an asyncio task — fire-and-forget from tray startup. Handles
transient REST errors via back-off; persistent errors get logged but
don't crash the loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from tinyassets.host_pool.client import HostPoolClient, HostPoolError

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300  # 5 min
DEFAULT_MAX_BACKOFF_SECONDS = 600  # 10 min cap on retry delay


class HeartbeatLoop:
    """Asyncio-driven periodic heartbeat.

    Usage::

        loop = HeartbeatLoop(client, host_id=row.host_id)
        task = asyncio.create_task(loop.run())
        # ... tray lifetime ...
        loop.stop()
        await task

    Parameters
    ----------
    client : HostPoolClient
    host_id : str
    interval : float
        Seconds between heartbeats. Default 300 (5 min).
    on_error : optional callback
        Called with the HostPoolError when a heartbeat fails. Use to
        surface to tray UI. No return value; errors in the callback
        itself are swallowed + logged.
    sleep : injection seam for tests
    """

    def __init__(
        self,
        client: HostPoolClient,
        *,
        host_id: str,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        max_backoff: float = DEFAULT_MAX_BACKOFF_SECONDS,
        on_error: Callable[[HostPoolError], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if interval < 30:
            raise ValueError(
                f"heartbeat interval {interval}s is too aggressive — "
                f"Track A schema design budget is ≥60s; 5 min recommended"
            )
        self._client = client
        self._host_id = host_id
        self._interval = interval
        self._max_backoff = max_backoff
        self._on_error = on_error
        self._sleep = sleep
        self._stopping = asyncio.Event()
        self._backoff = 0.0

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        """Run until ``stop()`` is called.

        Loop pattern: tick → heartbeat → sleep(interval). On error,
        exponential backoff up to ``max_backoff``, logged + surfaced
        via ``on_error`` callback.
        """
        logger.info(
            "host_pool heartbeat loop starting for host_id=%s (interval=%ss)",
            self._host_id, self._interval,
        )
        while not self._stopping.is_set():
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, self._client.heartbeat, self._host_id,
                )
                self._backoff = 0.0
            except HostPoolError as exc:
                logger.warning("heartbeat failed for %s: %s", self._host_id, exc)
                if self._on_error is not None:
                    try:
                        self._on_error(exc)
                    except Exception:
                        logger.exception("heartbeat on_error callback raised")
                self._backoff = min(
                    max(self._backoff * 2, 30.0),
                    self._max_backoff,
                )

            wait = self._backoff if self._backoff else self._interval
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=wait)
                break  # stop() was called
            except asyncio.TimeoutError:
                continue
        logger.info("host_pool heartbeat loop stopped for host_id=%s", self._host_id)
