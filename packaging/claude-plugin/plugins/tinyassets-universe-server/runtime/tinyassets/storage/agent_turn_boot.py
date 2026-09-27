"""Which agent turns THIS daemon boot is running. Progress, never authority.

A turn row is only *working* while a process is executing it. The journal has no
way to say that: ``agent_turns.state`` records how far the turn got, and a
container recreated mid-turn leaves ``native_started`` behind forever (founder,
2026-09-26: turn ``652a2f31`` sat in ``native_started`` for 35 minutes after a
22:31:54Z deploy, and the app's server-driven status line painted "your universe
is thinking" the whole time).

Boot ownership is the missing fact, and it is in-memory on purpose: a boot has no
durable identity worth writing to a row, and a row's owning process is exactly
what a restart destroys. One :class:`BootTurns` instance == one daemon boot.

Two disjuncts, both necessary:

* A turn this boot CREATED and has not finished. Claimed by the journal's
  ``create`` (the only way a turn comes into being) and released by the
  coordinator when its ``run`` returns, however it returns -- once no task is
  executing the turn, nothing in this boot is running it, whatever the row says.
* A turn created AFTER this boot started. A deploy recreates the container, so
  every process in it restarts together; a row younger than this process cannot
  be a dead container's leftover. This covers a sibling process in the same
  container that keeps its own registry.

Neither disjunct grants anything. This module decides whether a row may be
*reported* as activity and whether startup may *settle* it -- never whether an
effect may run or be replayed.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone


class BootTurns:
    """The agent turns one daemon boot is executing right now."""

    def __init__(self, *, started_at: datetime | None = None) -> None:
        self.boot_id = uuid.uuid4().hex
        when = datetime.now(timezone.utc) if started_at is None else started_at
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError("boot start must be timezone-aware")
        self.started_at = when.astimezone(timezone.utc)
        self._lock = threading.Lock()
        self._claimed: set[tuple[str, str]] = set()

    def claim(self, universe_id: str, turn_id: str) -> None:
        """This boot created that turn and is about to execute it."""
        with self._lock:
            self._claimed.add((universe_id, turn_id))

    def release(self, universe_id: str, turn_id: str) -> None:
        """Nothing in this boot is executing that turn any more.

        Called when the coordinator's ``run`` returns -- not when the turn
        reaches a terminal state. A turn whose task was cancelled mid-flight is
        no longer running even though its row still says ``native_started``, and
        that row is precisely what must stop reading as activity. Idempotent: a
        turn released twice, or never claimed, is not an error.
        """
        with self._lock:
            self._claimed.discard((universe_id, turn_id))

    def holds(self, universe_id: str, turn_id: str, *, created_at: str) -> bool:
        """Is that row a turn this boot is running?

        ``created_at`` is the journal's own ``...Z`` stamp. One unparsable or
        naive stamp answers False for the time disjunct alone: an unclaimed row
        whose age cannot be established is not evidence that this boot owns it.
        """
        with self._lock:
            if (universe_id, turn_id) in self._claimed:
                return True
        if not isinstance(created_at, str) or not created_at.endswith("Z"):
            return False
        try:
            when = datetime.fromisoformat(created_at[:-1] + "+00:00")
        except ValueError:
            return False
        if when.tzinfo is None or when.utcoffset() is None:
            return False
        return when >= self.started_at


#: This process's boot. Created at import, which is before anything can serve a
#: request or create a turn, so every row older than it predates this process.
BOOT = BootTurns()
