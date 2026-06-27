"""Bid-polling loop — surface pending requests to tray UI.

Wave 1 discipline per dispatch 2026-04-20: **NOT auto-claim.** Tray
decides. This loop only reads pending ``requests`` rows matching the
host's capability and forwards them to a caller callback.

Auto-claim cascade (per memory ``project_daemon_default_behavior``)
ships in a later iteration gated on host-mode settings. Wave 1 keeps
the surface minimal: read, notify.

Cadence: 60s default. Lower than heartbeat because discovery latency
matters more than heartbeat cadence for UX. Rate-limit-free at
expected tier-1 scale (< 100 requests / host / day first-draft).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from tinyassets.host_pool.client import HostPoolClient, HostPoolError

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 60


class BidPoller:
    """Periodic poll of ``public.requests`` matching a capability.

    Parameters
    ----------
    client : HostPoolClient
    capability_id : str
        Only requests with a matching capability_id are surfaced.
    on_requests :
        Callable invoked with the list of new request dicts whenever
        the poller sees at least one row that wasn't in the previous
        tick. Receives only NEW rows (by ``request_id``); already-
        surfaced rows aren't re-notified within the process lifetime.
    poll_interval :
        Seconds between polls. Default 60s.
    list_limit :
        Max requests fetched per tick.
    sleep : injection seam for tests.
    """

    def __init__(
        self,
        client: HostPoolClient,
        *,
        capability_id: str,
        on_requests: Callable[[list[dict[str, Any]]], None],
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        list_limit: int = 50,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._capability_id = capability_id
        self._on_requests = on_requests
        self._interval = poll_interval
        self._limit = list_limit
        self._sleep = sleep
        self._seen: set[str] = set()
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    def _tick(self) -> list[dict[str, Any]]:
        """One poll. Return only NEW requests since last tick.

        Sync + injectable so tests can drive it without asyncio.
        """
        rows = self._client.list_pending_requests(
            self._capability_id, limit=self._limit,
        )
        new_rows = []
        for row in rows:
            rid = row.get("request_id")
            if rid is None:
                continue
            if rid in self._seen:
                continue
            self._seen.add(rid)
            new_rows.append(row)
        return new_rows

    async def run(self) -> None:
        logger.info(
            "bid poller starting for capability=%s (interval=%ss)",
            self._capability_id, self._interval,
        )
        while not self._stopping.is_set():
            try:
                new_rows = await asyncio.get_running_loop().run_in_executor(
                    None, self._tick,
                )
                if new_rows:
                    try:
                        self._on_requests(new_rows)
                    except Exception:
                        logger.exception("bid poller on_requests callback raised")
            except HostPoolError as exc:
                logger.warning(
                    "bid poll failed for capability=%s: %s",
                    self._capability_id, exc,
                )
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
                break
            except asyncio.TimeoutError:
                continue
        logger.info(
            "bid poller stopped for capability=%s (saw %d unique request_ids)",
            self._capability_id, len(self._seen),
        )
