"""Which agent turns THIS process has stopped executing. Progress, never authority.

Ownership of a turn row follows the OWNER LEASE GENERATION, not this module
(change ``execution-owner-lease`` D2, replacing the boot rule that lived here): a
working row is a live owner's turn only while its ``owner_generation`` equals the
generation its command center's key is held at and that owner tree is alive.
Startup reconcile settles rows below the current generation, after acquiring the
key (``agent_turn_reconcile``).

What remains here is the one fact the generation cannot carry: a task in THIS
process that was cancelled or timed out leaves its row progressing at the
current generation with nothing executing it. The coordinator records that here
when its ``run`` returns (:meth:`BootTurns.release`), and the status projection
stops painting the row as activity. In-memory on purpose: it describes this
process, and a restart is reconciled by generation instead.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

#: Released turns remembered for the projection. A turn released longer ago than
#: this many releases has long since been settled or reconciled; the bound keeps
#: a long-lived process from growing without limit.
_RELEASED_MEMORY = 4096


class BootTurns:
    """The agent turns this process created, and which of them it stopped running."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._claimed: set[tuple[str, str]] = set()
        self._released: OrderedDict[tuple[str, str], None] = OrderedDict()

    def claim(self, universe_id: str, turn_id: str) -> None:
        """This process created that turn and is about to execute it."""
        with self._lock:
            self._claimed.add((universe_id, turn_id))
            self._released.pop((universe_id, turn_id), None)

    def release(self, universe_id: str, turn_id: str) -> None:
        """Nothing in this process is executing that turn any more.

        Called when the coordinator's ``run`` returns, however it returns.
        Idempotent; a turn never claimed here is ignored.
        """
        with self._lock:
            if (universe_id, turn_id) not in self._claimed:
                return
            self._claimed.discard((universe_id, turn_id))
            self._released[(universe_id, turn_id)] = None
            while len(self._released) > _RELEASED_MEMORY:
                self._released.popitem(last=False)

    def holds(self, universe_id: str, turn_id: str) -> bool:
        with self._lock:
            return (universe_id, turn_id) in self._claimed

    def stopped(self, universe_id: str, turn_id: str) -> bool:
        """This process created the turn and is no longer executing it."""
        with self._lock:
            return (universe_id, turn_id) in self._released


#: This process's turns.
BOOT = BootTurns()
