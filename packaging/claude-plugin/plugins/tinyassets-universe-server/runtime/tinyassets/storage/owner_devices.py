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
import urllib.parse
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
--
-- The PRIMARY KEY is the whole dedupe rule: one notification per request, per
-- item, per destination, per kind. Nothing else bounds delivery, deliberately.
--
-- An earlier shape added a per-device "one outstanding alert" latch to bound
-- an agent that raised and withdrew the same ask in a loop. It was a rate
-- limiter in disguise -- account limits are cloud storage and concurrent
-- agent-run seats, and nothing else (founder, 2026-09-30) -- and it was where
-- most of two review rounds' defects lived: a refusal path that committed a
-- latch nobody was notified for, and a release rule an agent could drive.
--
-- What bounds cost instead already exists. A run that raises a request holds a
-- seat while it does, so churn is the agent spending its owner's own seat
-- time; `MAX_PENDING` caps the unanswered pile; and this key means a retry,
-- a redelivery or a crash mid-send never notifies twice.
CREATE TABLE IF NOT EXISTS request_notifications (
    request_id    TEXT NOT NULL,
    item_id       TEXT NOT NULL DEFAULT '',
    device_id     TEXT NOT NULL,
    owner_user_id TEXT NOT NULL DEFAULT '',
    kind          TEXT NOT NULL,
    sent_at       REAL NOT NULL,
    outcome       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (request_id, item_id, device_id, kind)
);
CREATE INDEX IF NOT EXISTS ix_request_notifications_owner
    ON request_notifications(owner_user_id);"""


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


def _token_digest(platform: str, identity: str) -> str:
    """The destination digest, NAMESPACED BY PLATFORM.

    Without the namespace an FCM registration token whose characters happened
    to equal a web-push endpoint deleted that web device, even
    though the two strings do not address the same destination through
    different transports (gpt-6-astra round 2, 2026-09-29). One string, two
    protocols, two destinations.
    """
    return hashlib.sha256(
        f"{platform}\x00{identity}".encode("utf-8")
    ).hexdigest()


#: Exactly the web-push subscription fields the transport uses. Anything else a
#: browser attaches (``expirationTime``, vendor extras) is DROPPED rather than
#: stored: see :func:`_canonical_token`.
_WEB_SUBSCRIPTION_KEYS = ("p256dh", "auth")


def _canonical_token(token: Any, platform: str) -> tuple[str, str]:
    """``(stored token, destination identity)`` for one platform's token shape.

    The two are different things, and conflating them was a cross-user hole
    (gpt-6-astra, 2026-09-29). The **stored token** is what a transport needs
    to send. The **destination identity** is what makes two registrations the
    same handset -- and it has to be derived from exactly what the transport
    actually addresses, or two documents that differ only in metadata hash
    differently while pointing at the same phone. Then a handset that changed
    accounts keeps a live row under each owner, and the previous owner's
    private notifications still arrive.

    Android: the registration token is an opaque string, and is both.

    Web push: the transport addresses ``endpoint`` and encrypts to
    ``keys.p256dh``/``keys.auth`` (:mod:`tinyassets.notify.webpush`), so the
    identity is the **endpoint** and the stored document is narrowed to exactly
    those three fields. A subscription carrying ``expirationTime``, extra keys,
    rotated keys or different whitespace therefore cannot alias past the
    ownership move.

    Which branch runs is decided by the **platform**, never by the Python type
    of the argument. Keyed on the type, a web subscription handed over as a
    JSON *string* took the opaque path and its identity became the whole
    string -- so whitespace alone still aliased. A client chooses the
    serialisation; it must not choose the identity rule.
    """
    if platform == PLATFORM_ANDROID:
        if not isinstance(token, str):
            raise ValueError("an android token must be a string")
        text = token.strip()
        return text, text
    if isinstance(token, str):
        try:
            token = json.loads(token)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValueError(
                "a web push subscription must be an object, or JSON for one"
            ) from exc
    if not isinstance(token, dict):
        raise ValueError("a web push subscription must be an object")
    endpoint = str(token.get("endpoint") or "").strip()
    if not endpoint.startswith("https://"):
        raise ValueError("a web push subscription needs an https:// endpoint")
    keys = token.get("keys")
    if not isinstance(keys, dict):
        raise ValueError("a web push subscription needs keys")
    narrowed = {}
    for name in _WEB_SUBSCRIPTION_KEYS:
        value = str(keys.get(name) or "").strip()
        if not value:
            raise ValueError(f"a web push subscription needs keys.{name}")
        narrowed[name] = value
    stored = json.dumps(
        {"endpoint": endpoint, "keys": narrowed},
        sort_keys=True, separators=(",", ":"),
    )
    # The endpoint alone. NOT the narrowed document: re-subscribing in the same
    # browser can rotate the keys while keeping the endpoint, and that is the
    # same destination. Canonicalised first -- see `_canonical_endpoint`.
    return stored, _canonical_endpoint(endpoint)


def _canonical_endpoint(endpoint: str) -> str:
    """The endpoint reduced to what the transport actually addresses.

    ``urllib`` sends the scheme, host and selector; a **fragment** never leaves
    the client and host case is not significant. So
    ``https://push.example.com/abc`` and ``https://push.example.com/abc#bob``
    are one destination, and treating them as two let each owner keep a live
    row for the same browser (gpt-6-astra round 2, 2026-09-29).

    Deliberately narrow: scheme and host are lowercased, the default port is
    dropped, and the fragment is discarded. Nothing else is "normalised" --
    path case, percent-encoding and DNS aliases are NOT assumed equivalent,
    because assuming that without evidence would merge two real destinations
    into one and silently drop a device.
    """
    parts = urllib.parse.urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.port and not (parts.scheme == "https" and parts.port == 443):
        host = f"{host}:{parts.port}"
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), host, parts.path, parts.query, "")
    )


def register_device(
    base_path: str | Path,
    *,
    owner_user_id: str,
    platform: str,
    token: Any,
    label: str = "",
) -> dict[str, Any]:
    """Record a device for ``owner_user_id``. Raises ValueError on a bad argument.

    ``owner_user_id`` is the caller's server-authenticated subject.

    Re-registering the same destination for the **same** subject refreshes the
    existing row in place, keeping its ``device_id`` -- the app calls this on
    every launch, and minting a new id each time would churn ids and orphan
    whatever alert the device is holding. The stored token is refreshed, so a
    browser that re-subscribed with rotated keys on the same endpoint keeps its
    identity and gains the new keys.

    Re-registering it for a **different** subject replaces it: every prior row
    for that destination is removed before a new row is written under the
    new owner.
    """
    sub = (owner_user_id or "").strip()
    if not sub:
        raise ValueError("owner_user_id is required")
    kind = (platform or "").strip().lower()
    if kind not in PLATFORMS:
        raise ValueError("platform must be one of " + ", ".join(sorted(PLATFORMS)))
    stored, identity = _canonical_token(token, kind)
    if not stored:
        raise ValueError("token is required")
    if len(stored) > MAX_TOKEN_CHARS:
        raise ValueError(f"token is longer than {MAX_TOKEN_CHARS} characters")
    digest = _token_digest(kind, identity)
    now = time.time()
    with _connect(base_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        # Every row for this DESTINATION, whoever owns it. Matching on the
        # destination rather than the whole token document is the fix for two
        # representations of one phone each keeping a live row; matching across
        # owners rather than "where owner_user_id != ?" is the fix for the
        # caller's own stale duplicate (gpt-6-astra, 2026-09-29).
        existing = conn.execute(
            "SELECT device_id, owner_user_id FROM owner_devices "
            "WHERE token_sha256 = ?",
            (digest,),
        ).fetchall()
        mine = [r[0] for r in existing if r[1] == sub]
        theirs = [r[0] for r in existing if r[1] != sub]
        if theirs or len(mine) > 1:
            # Ownership moved, or an older duplicate exists: start clean. The
            # delivery ledger is keyed on (request, item, device, kind) and the
            # old device_id is gone, so the new owner's notifications cannot
            # dedupe against anything the previous owner was sent.
            conn.execute(
                "DELETE FROM owner_devices WHERE token_sha256 = ?", (digest,),
            )
            mine = []
        if mine:
            # The app relaunching. Same device, refreshed token.
            device_id = mine[0]
            conn.execute(
                "UPDATE owner_devices SET token_json = ?, platform = ?, "
                "last_seen_at = ?, enabled = 1, retired_at = NULL, "
                "retired_reason = '', label = CASE WHEN ? != '' THEN ? ELSE label END "
                "WHERE device_id = ?",
                (stored, kind, now, (label or "").strip()[:MAX_LABEL_CHARS],
                 (label or "").strip()[:MAX_LABEL_CHARS], device_id),
            )
            return {"device_id": device_id, "platform": kind, "replaced": 0}
        device_id = "dev_" + uuid.uuid4().hex[:24]
        conn.execute(
            "INSERT INTO owner_devices (device_id, owner_user_id, platform, "
            "token_sha256, token_json, label, enabled, created_at, last_seen_at) "
            "VALUES (?,?,?,?,?,?,1,?,?)",
            (device_id, sub, kind, digest, stored,
             (label or "").strip()[:MAX_LABEL_CHARS], now, now),
        )
    return {"device_id": device_id, "platform": kind, "replaced": len(theirs)}


#: Reasons a device row may record. A CLOSED SET, because the retirement
#: reason is the one string on this table that comes from a transport, and a
#: transport's exception text is a credential-leak channel: injecting
#: ``TransportGone("Bearer TEST-SECRET-TOKEN")`` returned that text straight
#: back out of ``list_devices`` (gpt-6-astra round 2, 2026-09-29). The shipped
#: transports only ever pass fixed codes, so that was an incomplete boundary
#: rather than a live leak -- but the boundary is where it has to be closed,
#: not in each transport.
RETIRE_REASONS = frozenset({
    "UNREGISTERED", "NOT_FOUND", "INVALID_ARGUMENT",  # FCM
    "404", "410",                                      # web push
    "owner",                                           # the person removed it
    "unknown",                                         # anything else
})


def retire_device(
    base_path: str | Path, *, owner_user_id: str, device_id: str, reason: str = "",
) -> bool:
    """The owner (or a transport reporting the destination gone) drops a device.

    Scoped to ``owner_user_id``, so naming another user's device id does
    nothing. ``reason`` is mapped onto :data:`RETIRE_REASONS` and anything
    unrecognised is stored as ``unknown`` -- never the text as given.
    """
    sub = (owner_user_id or "").strip()
    if not sub or not device_id:
        return False
    recorded = (reason or "").strip()
    if recorded not in RETIRE_REASONS:
        recorded = "unknown"
    with _connect(base_path) as conn:
        cur = conn.execute(
            "UPDATE owner_devices SET enabled = 0, retired_at = ?, "
            "retired_reason = ? WHERE device_id = ? AND owner_user_id = ? "
            "AND retired_at IS NULL",
            (time.time(), recorded, device_id, sub),
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
) -> dict[str, Any]:
    """Claim one notification and hand back the destination to send it with.

    Returns ``{"token": ...}`` when the caller may send, otherwise
    ``{"refused": "moved"}`` (this destination is no longer this owner's, or is
    retired) or ``{"refused": "replay"}`` (this exact notification was already
    claimed). Those are the only two refusals: the primary key is the whole
    dedupe rule.

    **The token comes from here, not from an earlier read.** Dispatch used to
    snapshot every destination and then send to the cached tokens, so a
    registration that moved a handset to another account mid-dispatch still
    received the previous owner's private title (gpt-6-astra, 2026-09-29).
    Reading the row and claiming the notification in ONE ``BEGIN IMMEDIATE``
    transaction means the token a transport is handed was owner-verified at
    claim time. The residual is the interval between commit and the wire, which
    no server-side check can close because the push is already in flight.

    The claim is written BEFORE the transport runs, so a crash mid-send leaves
    the notification unsent rather than sent twice -- the right way round for
    something that buzzes a phone. A send that then fails is recorded by
    :func:`record_delivery` and its row stays, so a failure is not silently
    retried forever either.
    """
    sub = (owner_user_id or "").strip()
    with _connect(base_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT token_json FROM owner_devices WHERE device_id = ? "
            "AND owner_user_id = ? AND enabled = 1 AND retired_at IS NULL",
            (device_id, sub),
        ).fetchone()
        if row is None:
            return {"refused": "moved"}
        claimed = conn.execute(
            "INSERT OR IGNORE INTO request_notifications "
            "(request_id, item_id, device_id, owner_user_id, kind, sent_at) "
            "VALUES (?,?,?,?,?,?)",
            (request_id, item_id or "", device_id, sub, kind, time.time()),
        )
        if claimed.rowcount <= 0:
            return {"refused": "replay"}
        return {"token": row[0]}


def delivered_devices(
    base_path: str | Path, *, owner_user_id: str, request_id: str,
) -> list[str]:
    """Destinations that actually received this request's notification.

    Which is exactly the set with something to clear. A device that never got
    one has nothing to take down, so it is not woken -- and this reads the
    delivery ledger rather than a second piece of state, so there is one
    record of what was sent.
    """
    sub = (owner_user_id or "").strip()
    if not sub or not request_id:
        return []
    with _connect(base_path) as conn:
        return [
            r[0] for r in conn.execute(
                "SELECT device_id FROM request_notifications "
                "WHERE request_id = ? AND owner_user_id = ? AND kind = ? "
                "AND outcome = 'sent'",
                (request_id, sub, KIND_RAISED),
            )
        ]


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


def deliveries_for(
    base_path: str | Path, *, request_id: str,
) -> list[dict[str, Any]]:
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
    "RETIRE_REASONS",
    "deliveries_for",
    "delivered_devices",
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
