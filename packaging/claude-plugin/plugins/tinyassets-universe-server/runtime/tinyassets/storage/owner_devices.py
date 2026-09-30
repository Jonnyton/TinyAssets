"""The devices a signed-in user registered, and whether they want notifying.

The requests system has been addressable from a phone since it existed -- the
row lives server-side and every surface reads it through the same
``read_graph``. What it never had is the other direction: a way to *reach* the
owner, which its own module docstring named as "device registration, which does
not exist yet". This is that registration.

The one rule everything else rests on
-------------------------------------
**A device belongs to the subject that registered it, and notifications are
looked up by that subject only.** Callers pass a server-authenticated
principal; nothing here reads a subject, universe or destination out of a
payload, and there is no function that returns another user's devices.

The second rule is the one that is easy to miss: **a token re-registered under
a different subject MOVES.** A phone that signs out of one account and into
another keeps the same FCM registration token, so leaving the old row would
deliver the previous user's notifications to whoever holds the handset now --
a cross-user delivery, which is the only floor the platform has. So
``register`` deletes every row for that token, *whatever subject owns it*,
before writing the new one.

Tokens are stored because a transport needs them to send. They are never
returned by a read: ``list_devices`` projects an id, platform, label, flags and
timestamps, so a compromised read cannot be replayed as a send.

Not a rate ledger
-----------------
``request_notifications`` exists for idempotency, not for accounting: it is how
"send this once" is enforced across a retry. Account limits are cloud storage
and concurrent agent-run seats (founder, 2026-09-30); there is deliberately no
meter here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_DB_NAME = ".owner_devices.db"

PLATFORM_ANDROID = "android"
PLATFORM_WEB = "web"
PLATFORMS = frozenset({PLATFORM_ANDROID, PLATFORM_WEB})

#: Delivery kinds. ``raised`` is the visible notification for a new request;
#: ``clear`` is the silent data message that takes it off the owner's other
#: devices once they answered on one.
KIND_RAISED = "raised"
KIND_CLEAR = "clear"

#: A registration token or web-push subscription document. Bounded so a caller
#: cannot use registration as storage.
MAX_TOKEN_CHARS = 4096
MAX_LABEL_CHARS = 60


def owner_devices_db_path(base_path: str | Path) -> Path:
    return Path(base_path) / _DB_NAME


_SCHEMA = """
CREATE TABLE IF NOT EXISTS owner_devices (
    device_id      TEXT PRIMARY KEY,
    owner_user_id  TEXT NOT NULL,
    platform       TEXT NOT NULL,
    token_sha256   TEXT NOT NULL,
    token_json     TEXT NOT NULL,
    label          TEXT NOT NULL DEFAULT '',
    enabled        INTEGER NOT NULL DEFAULT 1,
    created_at     REAL NOT NULL,
    last_seen_at   REAL NOT NULL,
    retired_at     REAL,
    retired_reason TEXT NOT NULL DEFAULT '',
    UNIQUE(owner_user_id, token_sha256)
);
CREATE INDEX IF NOT EXISTS ix_owner_devices_owner
    ON owner_devices(owner_user_id, retired_at);
-- The token is the identity of the handset, independent of who is signed in on
-- it. Indexed because every registration has to find rows for it across ALL
-- subjects in order to move it.
CREATE INDEX IF NOT EXISTS ix_owner_devices_token
    ON owner_devices(token_sha256);
CREATE TABLE IF NOT EXISTS owner_notify_settings (
    owner_user_id TEXT PRIMARY KEY,
    enabled       INTEGER NOT NULL DEFAULT 1,
    updated_at    REAL NOT NULL
);
-- Content-free delivery evidence: identifiers, a kind, a class. No body, no
-- field value, no token -- so this is not a second copy of the owner's content.
--
-- `owner_user_id` is here for DELETION, not for routing (routing reads
-- `owner_devices`). Account deletion derives its sweep from the schema, and its
-- recognised person-key names are `PRINCIPAL_KEYS` in
-- `tinyassets/account_deletion.py`; a table with no column from that list is
-- simply not found, and these rows would outlive the person they are about.
-- That is why the column is named exactly `owner_user_id` and not `owner_sub`.
CREATE TABLE IF NOT EXISTS request_notifications (
    request_id    TEXT NOT NULL,
    item_id       TEXT NOT NULL DEFAULT '',
    device_id     TEXT NOT NULL,
    owner_user_id TEXT NOT NULL DEFAULT '',
    kind          TEXT NOT NULL,
    sent_at       REAL NOT NULL,
    outcome       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (request_id, item_id, device_id, kind)
);"""


@contextmanager
def _connect(base_path: str | Path) -> Iterator[sqlite3.Connection]:
    db = owner_devices_db_path(base_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _canonical_token(token: Any) -> str:
    """The token as one canonical string, whatever shape the platform uses.

    Android hands over a registration token (a string). Web push hands over a
    subscription object (endpoint + keys). Both become one canonical string so
    the digest identifies the same handset across re-registrations regardless
    of key order in the JSON.
    """
    if isinstance(token, str):
        return token.strip()
    if isinstance(token, dict):
        return json.dumps(token, sort_keys=True, separators=(",", ":"))
    raise ValueError("token must be a string or an object")


def register_device(
    base_path: str | Path,
    *,
    owner_user_id: str,
    platform: str,
    token: Any,
    label: str = "",
) -> dict[str, Any]:
    """Record a device for ``owner_user_id``. Raises ValueError on a bad argument.

    ``owner_user_id`` is the caller's server-authenticated subject. Re-registering
    the same token for the same subject refreshes it in place (the app calls
    this on every launch); re-registering it for a DIFFERENT subject moves it,
    removing every prior row for that token first.
    """
    sub = (owner_user_id or "").strip()
    if not sub:
        raise ValueError("owner_user_id is required")
    kind = (platform or "").strip().lower()
    if kind not in PLATFORMS:
        raise ValueError("platform must be one of " + ", ".join(sorted(PLATFORMS)))
    canonical = _canonical_token(token)
    if not canonical:
        raise ValueError("token is required")
    if len(canonical) > MAX_TOKEN_CHARS:
        raise ValueError(f"token is longer than {MAX_TOKEN_CHARS} characters")
    digest = _token_digest(canonical)
    now = time.time()
    with _connect(base_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        # The move. A handset that changed accounts must stop receiving the
        # previous subject's notifications, so this deletes by TOKEN across
        # every subject -- not "where owner_user_id != ?", which would leave the
        # caller's own stale duplicate behind.
        conn.execute("DELETE FROM owner_devices WHERE token_sha256 = ?", (digest,))
        device_id = "dev_" + uuid.uuid4().hex[:24]
        conn.execute(
            "INSERT INTO owner_devices (device_id, owner_user_id, platform, "
            "token_sha256, token_json, label, enabled, created_at, last_seen_at) "
            "VALUES (?,?,?,?,?,?,1,?,?)",
            (device_id, sub, kind, digest, canonical,
             (label or "").strip()[:MAX_LABEL_CHARS], now, now),
        )
    return {"device_id": device_id, "platform": kind, "moved": True}


def retire_device(
    base_path: str | Path, *, owner_user_id: str, device_id: str, reason: str = "",
) -> bool:
    """The owner (or a transport reporting the destination gone) drops a device.

    Scoped to ``owner_user_id``, so naming another user's device id does nothing.
    """
    sub = (owner_user_id or "").strip()
    if not sub or not device_id:
        return False
    with _connect(base_path) as conn:
        cur = conn.execute(
            "UPDATE owner_devices SET enabled = 0, retired_at = ?, "
            "retired_reason = ? WHERE device_id = ? AND owner_user_id = ? "
            "AND retired_at IS NULL",
            (time.time(), (reason or "")[:80], device_id, sub),
        )
        return cur.rowcount > 0


def list_devices(base_path: str | Path, *, owner_user_id: str) -> list[dict[str, Any]]:
    """The caller's OWN devices. Never returns token material."""
    sub = (owner_user_id or "").strip()
    if not sub:
        return []
    with _connect(base_path) as conn:
        rows = conn.execute(
            "SELECT device_id, platform, label, enabled, created_at, "
            "last_seen_at, retired_at, retired_reason FROM owner_devices "
            "WHERE owner_user_id = ? ORDER BY created_at ASC",
            (sub,),
        ).fetchall()
    return [
        {
            "device_id": r[0], "platform": r[1], "label": r[2],
            "enabled": bool(r[3]) and r[6] is None,
            "created_at": r[4], "last_seen_at": r[5],
            "retired_at": r[6], "retired_reason": r[7],
        }
        for r in rows
    ]


def delivery_targets(base_path: str | Path, *, owner_user_id: str) -> list[dict[str, Any]]:
    """Live devices for ``owner_user_id``, WITH their tokens, for a transport.

    The only function that returns token material, and the only lookup key is
    the subject. Returns [] when the owner turned notifications off, so the
    off switch cannot be bypassed by a caller that forgot to check it.
    """
    sub = (owner_user_id or "").strip()
    if not sub:
        return []
    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT enabled FROM owner_notify_settings WHERE owner_user_id = ?", (sub,),
        ).fetchone()
        if row is not None and not bool(row[0]):
            return []
        rows = conn.execute(
            "SELECT device_id, platform, token_json FROM owner_devices "
            "WHERE owner_user_id = ? AND enabled = 1 AND retired_at IS NULL "
            "ORDER BY created_at ASC",
            (sub,),
        ).fetchall()
    return [{"device_id": r[0], "platform": r[1], "token": r[2]} for r in rows]


def notifications_enabled(base_path: str | Path, *, owner_user_id: str) -> bool:
    """Whether the owner wants notifying. Default on: a device only exists here
    because the user granted the OS permission and the app registered it, so a
    server default of off would silently discard a permission they just gave."""
    sub = (owner_user_id or "").strip()
    if not sub:
        return False
    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT enabled FROM owner_notify_settings WHERE owner_user_id = ?", (sub,),
        ).fetchone()
    return True if row is None else bool(row[0])


def set_notifications_enabled(
    base_path: str | Path, *, owner_user_id: str, enabled: bool,
) -> bool:
    sub = (owner_user_id or "").strip()
    if not sub:
        return False
    with _connect(base_path) as conn:
        conn.execute(
            "INSERT INTO owner_notify_settings (owner_user_id, enabled, updated_at) "
            "VALUES (?,?,?) ON CONFLICT(owner_user_id) DO UPDATE SET "
            "enabled = excluded.enabled, updated_at = excluded.updated_at",
            (sub, 1 if enabled else 0, time.time()),
        )
    return bool(enabled)


def reserve_delivery(
    base_path: str | Path,
    *,
    request_id: str,
    device_id: str,
    kind: str,
    owner_user_id: str,
    item_id: str = "",
) -> bool:
    """Claim "this exact notification, once". False when already claimed.

    The claim is written BEFORE the transport runs, so a crash mid-send leaves
    the notification unsent rather than sent twice -- the right way round for
    something that buzzes a phone. A send that then fails is recorded by
    :func:`record_delivery`, and the row stays, so a failure is not silently
    retried forever either.

    ``owner_user_id`` is stamped so the row is reachable by account deletion;
    it is never read to choose a destination.
    """
    with _connect(base_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO request_notifications "
            "(request_id, item_id, device_id, owner_user_id, kind, sent_at) "
            "VALUES (?,?,?,?,?,?)",
            (request_id, item_id or "", device_id, (owner_user_id or "").strip(),
             kind, time.time()),
        )
        return cur.rowcount > 0


def record_delivery(
    base_path: str | Path,
    *,
    request_id: str,
    device_id: str,
    kind: str,
    outcome: str,
    item_id: str = "",
) -> None:
    """Attach the outcome CLASS to a claimed delivery. Never a body or a token."""
    with _connect(base_path) as conn:
        conn.execute(
            "UPDATE request_notifications SET outcome = ? WHERE request_id = ? "
            "AND item_id = ? AND device_id = ? AND kind = ?",
            (str(outcome)[:40], request_id, item_id or "", device_id, kind),
        )


def deliveries_for(base_path: str | Path, *, request_id: str) -> list[dict[str, Any]]:
    """The delivery ledger for one request -- identifiers and classes only."""
    with _connect(base_path) as conn:
        rows = conn.execute(
            "SELECT device_id, item_id, kind, sent_at, outcome "
            "FROM request_notifications WHERE request_id = ? ORDER BY sent_at ASC",
            (request_id,),
        ).fetchall()
    return [
        {"device_id": r[0], "item_id": r[1], "kind": r[2],
         "sent_at": r[3], "outcome": r[4]}
        for r in rows
    ]


def purge_owner(base_path: str | Path, *, owner_user_id: str) -> int:
    """Remove every device, setting and delivery row for a subject.

    Account deletion reaches these tables on its own, from the schema (every
    one of them carries ``owner_user_id``). This is the same delete by name,
    for a caller that wants it directly -- and the test that proves the column
    names are the ones the sweep looks for.
    """
    sub = (owner_user_id or "").strip()
    if not sub:
        return 0
    with _connect(base_path) as conn:
        removed = conn.execute(
            "DELETE FROM owner_devices WHERE owner_user_id = ?", (sub,),
        ).rowcount
        conn.execute(
            "DELETE FROM owner_notify_settings WHERE owner_user_id = ?", (sub,),
        )
        conn.execute(
            "DELETE FROM request_notifications WHERE owner_user_id = ?", (sub,),
        )
    return int(removed or 0)


__all__ = [
    "KIND_CLEAR",
    "KIND_RAISED",
    "MAX_TOKEN_CHARS",
    "PLATFORMS",
    "PLATFORM_ANDROID",
    "PLATFORM_WEB",
    "deliveries_for",
    "delivery_targets",
    "list_devices",
    "notifications_enabled",
    "owner_devices_db_path",
    "purge_owner",
    "record_delivery",
    "register_device",
    "reserve_delivery",
    "retire_device",
    "set_notifications_enabled",
]
