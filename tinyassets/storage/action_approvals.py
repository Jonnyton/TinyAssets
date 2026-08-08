"""Are you sure? — consent for costly or irreversible agent actions.

Why this is separate from authority
-----------------------------------
Every gate we have answers *"are you allowed"*: the founder grant, the provider
binding's `allowed_operations`, the operation-scope ceiling. None answers *"are
you sure"*. The agent can spend the founder's own compute and open pull requests
against their repository, and until now nothing asked first.

The AI SDK models this as first-class tool states — `approval-requested`,
`approval-responded`, `output-denied` — and its loop PAUSES for them. We cannot
pause: a universe turn is one subprocess and the founder's answer arrives in a
later message. So the shape is asynchronous instead:

1. A costly action with no approval RECORDS a pending request and refuses,
   telling the agent to ask.
2. The founder answers in chat, in their own words.
3. The agent grants the approval, and the SAME action now succeeds.

An approval is scoped to one universe and one action key, single-use by default
so "yes, run it" does not become "yes, run it forever". A founder who wants
standing consent asks for it explicitly.
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from tinyassets.storage import db_path

_KEY = re.compile(r"[a-z][a-z0-9_.:-]{2,127}\Z")

#: A pending ask that nobody answered should not sit there forever looking like
#: a live offer. Long enough for a founder to be away from their phone.
PENDING_TTL_SECONDS = 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_approvals (
    universe_id TEXT NOT NULL,
    action_key TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'granted', 'denied')),
    standing INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    decided_by TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL,
    PRIMARY KEY (universe_id, action_key)
);
"""


class ApprovalError(ValueError):
    """The request was malformed. Message reaches the model."""


@dataclass(frozen=True, slots=True)
class Approval:
    universe_id: str
    action_key: str
    state: str
    standing: bool
    detail: str


class ActionApprovalStore:
    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path(self.base_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _validate(universe_id: str, action_key: str) -> tuple[str, str]:
        uid = (universe_id or "").strip()
        key = (action_key or "").strip().lower()
        if not uid:
            raise ApprovalError("universe is required")
        if _KEY.fullmatch(key) is None:
            raise ApprovalError(
                "action_key must be lowercase letters, digits and . : _ -"
            )
        return uid, key

    def consume_if_granted(
        self, *, universe_id: str, action_key: str, now: float | None = None
    ) -> bool:
        """True if this action may proceed — and spends the approval if single-use.

        Consuming is the point. A one-off "yes" that keeps working is a standing
        grant the founder never gave, which is exactly the failure this table
        exists to prevent.
        """
        uid, key = self._validate(universe_id, action_key)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state, standing FROM action_approvals"
                " WHERE universe_id = ? AND action_key = ?",
                (uid, key),
            ).fetchone()
            if row is None or row["state"] != "granted":
                return False
            if row["standing"]:
                return True
            conn.execute(
                "DELETE FROM action_approvals"
                " WHERE universe_id = ? AND action_key = ?",
                (uid, key),
            )
            return True

    def request(
        self, *, universe_id: str, action_key: str, detail: str = "",
        now: float | None = None,
    ) -> Approval:
        """Record that this action is waiting on the founder."""
        uid, key = self._validate(universe_id, action_key)
        stamp = now if now is not None else time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO action_approvals"
                " (universe_id, action_key, state, standing, detail, updated_at)"
                " VALUES (?,?,'pending',0,?,?)"
                " ON CONFLICT(universe_id, action_key) DO UPDATE SET"
                " state='pending', detail=excluded.detail,"
                " updated_at=excluded.updated_at"
                " WHERE action_approvals.state != 'granted'",
                (uid, key, str(detail or "")[:500], stamp),
            )
        return Approval(uid, key, "pending", False, str(detail or "")[:500])

    def decide(
        self, *, universe_id: str, action_key: str, granted: bool,
        decided_by: str, standing: bool = False, now: float | None = None,
    ) -> Approval:
        uid, key = self._validate(universe_id, action_key)
        state = "granted" if granted else "denied"
        stamp = now if now is not None else time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO action_approvals"
                " (universe_id, action_key, state, standing, decided_by, updated_at)"
                " VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(universe_id, action_key) DO UPDATE SET"
                " state=excluded.state, standing=excluded.standing,"
                " decided_by=excluded.decided_by, updated_at=excluded.updated_at",
                (uid, key, state, 1 if (granted and standing) else 0,
                 (decided_by or "").strip(), stamp),
            )
        return Approval(uid, key, state, bool(granted and standing), "")

    def pending_for(
        self, *, universe_id: str, now: float | None = None
    ) -> list[Approval]:
        """Asks still waiting, excluding ones old enough to be stale."""
        uid = (universe_id or "").strip()
        cutoff = (now if now is not None else time.time()) - PENDING_TTL_SECONDS
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT action_key, state, standing, detail FROM action_approvals"
                " WHERE universe_id = ? AND state = 'pending' AND updated_at >= ?"
                " ORDER BY updated_at DESC",
                (uid, cutoff),
            ).fetchall()
        return [
            Approval(uid, r["action_key"], r["state"], bool(r["standing"]), r["detail"])
            for r in rows
        ]


__all__ = [
    "PENDING_TTL_SECONDS",
    "ActionApprovalStore",
    "Approval",
    "ApprovalError",
]
