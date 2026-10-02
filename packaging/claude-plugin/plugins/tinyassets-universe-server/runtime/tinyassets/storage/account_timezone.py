"""The owner's own clock, reported by their client and stored on the account.

Nothing in the platform knew a user's timezone before 2026-09-30. The app
formats every timestamp it DISPLAYS with `Intl.DateTimeFormat`, client-side
only (`tinyassets/onboarding/app.html`), so the browser has always known the
zone, never sent it, and there was no column to receive it. Meanwhile the
scheduler matched cron against the container's clock. The result was a universe
telling a Pacific user "7am server time" for a note that would arrive at
midnight.

One value per account, validated before it is stored. The store is
deliberately not a general preferences bag: a schedule's correctness depends on
this field, so it gets a typed home where a reader can see what is allowed.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tinyassets.schedule_timezone import UnknownTimezone, normalize_timezone
from tinyassets.storage import DB_FILENAME
from tinyassets.universe_files import connect_db

_SCHEMA = """
CREATE TABLE IF NOT EXISTS account_timezone (
    owner_user_id TEXT PRIMARY KEY,
    timezone TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _connect(base_path: str | Path, *, create: bool) -> sqlite3.Connection | None:
    path = Path(base_path) / DB_FILENAME
    if not create and not path.is_file():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_db(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(_SCHEMA)
    return conn


def _subject(owner_user_id: str) -> str:
    subject = str(owner_user_id or "").strip()
    if not subject or len(subject) > 400 or not subject.isprintable():
        raise ValueError("invalid account subject")
    return subject


def set_account_timezone(
    base_path: str | Path, *, owner_user_id: str, timezone_name: str,
) -> str:
    """Record the owner's zone. Returns the stored name.

    Raises ``UnknownTimezone`` for a name ``zoneinfo`` cannot resolve, which is
    what keeps a typo'd or hostile value out of the column that decides when
    somebody's morning runs happen. A refused report leaves the previous value
    ALONE -- a client that cannot name its zone must not be able to clear one
    the owner already has.
    """
    subject = _subject(owner_user_id)
    stored = normalize_timezone(timezone_name)  # raises UnknownTimezone
    conn = _connect(base_path, create=True)
    assert conn is not None
    try:
        with conn:
            conn.execute(
                "INSERT INTO account_timezone (owner_user_id, timezone, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(owner_user_id) DO UPDATE SET "
                "timezone = excluded.timezone, updated_at = excluded.updated_at",
                (subject, stored, datetime.now(timezone.utc).isoformat()),
            )
    finally:
        conn.close()
    return stored


def get_account_timezone(base_path: str | Path, *, owner_user_id: str) -> str:
    """The owner's stored zone, or ``""`` when none is known.

    Empty is a real answer, not an error: it means "fall back to UTC and say
    so", which is what a first-ever schedule gets before the app has loaded.
    A stored name that has since become unresolvable also reads as unknown
    rather than raising -- the tz database can drop a zone, and that must not
    take the scheduler down with it.
    """
    try:
        subject = _subject(owner_user_id)
    except ValueError:
        return ""
    conn = _connect(base_path, create=False)
    if conn is None:
        return ""
    try:
        row = conn.execute(
            "SELECT timezone FROM account_timezone WHERE owner_user_id = ?",
            (subject,),
        ).fetchone()
    except sqlite3.Error:
        return ""
    finally:
        conn.close()
    if row is None:
        return ""
    try:
        return normalize_timezone(str(row["timezone"] or ""))
    except UnknownTimezone:
        return ""
