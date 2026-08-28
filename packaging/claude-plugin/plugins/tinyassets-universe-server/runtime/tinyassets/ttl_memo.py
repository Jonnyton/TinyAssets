"""A TTL memo that is safe to put in front of expensive shared work.

Written after a cross-family review (Codex ADAPT, 2026-08-28) reproduced four defects
in two hand-rolled memos that each looked obviously correct. They are the same four
every naive cache has, so they are solved once here rather than twice badly:

1. **Thundering herd.** Both memos checked under a lock, computed outside it, then
   published. With 25 concurrent cold callers that ran *25* filesystem walks — at the
   exact concurrency where the box already saturates, so the cache made the worst
   moment worse. Fixed by per-key single-flight: the first caller computes, the rest
   wait for that same answer. The global lock is still never held across the work.

2. **Publication races.** A slow, older computation could overwrite a newer result, and
   worse, one already in flight could repopulate a value *after* `invalidate()` had
   returned — so a caller who explicitly asked for freshness got the stale answer back.
   Fixed with a generation counter: a computation publishes only if no invalidation
   happened while it ran.

3. **Non-finite TTLs.** `float("inf")` parsed happily and froze a value forever. A
   diagnostic that can be permanently frozen by a typo in an env var is worse than no
   cache. Rejected now, falling back to the default.

4. **Clear-all eviction.** Dropping every entry at the size bound guarantees churn
   precisely when there are many keys. LRU evicts one.
"""

from __future__ import annotations

import copy
import math
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

DEFAULT_MAX_ENTRIES = 256


def read_ttl(var: str, default: float) -> float:
    """Parse a TTL env var. Unparseable OR non-finite falls back to ``default``.

    Non-finite is the interesting case: `inf` is a perfectly good float and would
    otherwise mean "never recompute", turning a staleness bound into a permanent one.
    """
    raw = (os.environ.get(var) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value):
        return default
    return value


class TTLMemo:
    """Per-key TTL cache with single-flight and generation-safe publication.

    Values are deep-copied on the way out, on BOTH the hit and the miss path — a
    caller that mutates what it got must not be able to reach the stored object.
    """

    def __init__(self, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._inflight: dict[str, threading.Event] = {}
        self._generation = 0
        self._max_entries = max_entries

    def invalidate(self) -> None:
        """Drop everything, and disown any computation already running.

        The generation bump is the point: without it, work that started before this
        call could publish afterwards and hand the next reader exactly the stale value
        this call existed to remove.
        """
        with self._lock:
            self._entries.clear()
            self._generation += 1

    def get(self, key: str, compute: Callable[[], Any], *, ttl: float) -> Any:
        if ttl <= 0:
            return compute()

        while True:
            now = time.monotonic()
            with self._lock:
                hit = self._entries.get(key)
                if hit is not None and now < hit[0]:
                    self._entries.move_to_end(key)
                    return copy.deepcopy(hit[1])
                waiter = self._inflight.get(key)
                if waiter is None:
                    waiter = self._inflight[key] = threading.Event()
                    generation = self._generation
                    leader = True
                else:
                    leader = False

            if not leader:
                # Someone else is already doing this exact work. Wait for their
                # answer instead of duplicating a filesystem walk at the moment the
                # box is least able to afford one.
                waiter.wait(timeout=30.0)
                continue

            try:
                value = compute()
            finally:
                with self._lock:
                    self._inflight.pop(key, None)
                waiter.set()

            with self._lock:
                # Only publish if nothing invalidated while we were computing.
                if generation == self._generation:
                    self._entries[key] = (time.monotonic() + ttl, value)
                    self._entries.move_to_end(key)
                    while len(self._entries) > self._max_entries:
                        self._entries.popitem(last=False)  # LRU, not clear-all
            return copy.deepcopy(value)
