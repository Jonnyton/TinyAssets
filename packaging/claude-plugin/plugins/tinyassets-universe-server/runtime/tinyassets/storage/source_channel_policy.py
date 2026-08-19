"""Owner-settable source-channel approval policy.

A universe OWNER decides, per channel type, whether that channel requires
explicit approval before a node/effector may use it. This is the storage layer
behind ``write_graph target=source_channel operation=set_policy/get_policy``.

Two modes only:

- ``require`` (the default when no row exists): approval is required — the
  fail-closed behavior that ``_validate_source_code`` and the effector-consent
  gates already enforce. Absent policy therefore changes nothing.
- ``auto``: no approval required for that channel type in that universe. For the
  ``source_code`` channel this means a run of the owner's own private branch in
  the owner's own universe auto-approves that owner's source nodes (see
  ``tinyassets.api.source_channel``). It never affects the commons or another
  user's nodes — the run preflight scopes it to owner-authored private branches.

Per-base SQLite store (``${data_dir}/.source_channel_policy.db``), keyed by
``(universe_id, channel_type)``. Policy is a universe-level setting, so it is
stored at the shared base path (like ``branch_definitions``) rather than inside
a single universe directory.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_DB_FILENAME = ".source_channel_policy.db"

MODE_REQUIRE = "require"
MODE_AUTO = "auto"
VALID_MODES = frozenset({MODE_REQUIRE, MODE_AUTO})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_channel_policy (
    universe_id  TEXT NOT NULL,
    channel_type TEXT NOT NULL,
    mode         TEXT NOT NULL,
    set_by       TEXT NOT NULL,
    updated_at   REAL NOT NULL,
    PRIMARY KEY (universe_id, channel_type)
);
"""


def policy_db_path(base_path: str | Path) -> Path:
    return Path(base_path) / _DB_FILENAME


def _connect(base_path: str | Path) -> sqlite3.Connection:
    path = policy_db_path(base_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def initialize_policy_db(base_path: str | Path) -> None:
    with _connect(base_path) as conn:
        conn.executescript(_SCHEMA)


def set_policy(
    base_path: str | Path,
    *,
    universe_id: str,
    channel_type: str,
    mode: str,
    set_by: str,
    updated_at: float | None = None,
) -> dict[str, object]:
    """Upsert the owner's approval policy for a universe + channel type.

    ``mode`` must be one of :data:`VALID_MODES`. Raises ``ValueError`` on an
    unknown mode or empty universe/channel/actor so a bad call fails loudly
    rather than persisting a meaningless row.
    """
    uid = (universe_id or "").strip()
    channel = (channel_type or "").strip()
    mode = (mode or "").strip().lower()
    actor = (set_by or "").strip()
    if not uid:
        raise ValueError("universe_id is required")
    if not channel:
        raise ValueError("channel_type is required")
    if not actor:
        raise ValueError("set_by is required")
    if mode not in VALID_MODES:
        raise ValueError(
            f"unknown mode {mode!r}; expected one of {sorted(VALID_MODES)}"
        )
    now = time.time() if updated_at is None else updated_at
    with _connect(base_path) as conn:
        conn.executescript(_SCHEMA)
        conn.execute(
            """
            INSERT INTO source_channel_policy
                (universe_id, channel_type, mode, set_by, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(universe_id, channel_type) DO UPDATE SET
                mode = excluded.mode,
                set_by = excluded.set_by,
                updated_at = excluded.updated_at
            """,
            (uid, channel, mode, actor, now),
        )
    return {
        "universe_id": uid,
        "channel_type": channel,
        "mode": mode,
        "set_by": actor,
        "updated_at": now,
    }


def get_policy_mode(
    base_path: str | Path,
    *,
    universe_id: str,
    channel_type: str,
) -> str:
    """Return the effective mode for a universe + channel type.

    Fail-closed: a missing row, empty input, or a read error returns
    :data:`MODE_REQUIRE` so approval is required by default.
    """
    uid = (universe_id or "").strip()
    channel = (channel_type or "").strip()
    if not uid or not channel:
        return MODE_REQUIRE
    try:
        with _connect(base_path) as conn:
            conn.executescript(_SCHEMA)
            row = conn.execute(
                "SELECT mode FROM source_channel_policy "
                "WHERE universe_id = ? AND channel_type = ?",
                (uid, channel),
            ).fetchone()
    except Exception:  # noqa: BLE001 — fail closed to `require` on ANY read error
        return MODE_REQUIRE
    if row is None:
        return MODE_REQUIRE
    mode = (row["mode"] or "").strip().lower()
    return mode if mode in VALID_MODES else MODE_REQUIRE


def get_policy(
    base_path: str | Path,
    *,
    universe_id: str,
    channel_type: str,
) -> dict[str, object]:
    """Return the full policy row projection (or a default ``require`` view)."""
    uid = (universe_id or "").strip()
    channel = (channel_type or "").strip()
    with _connect(base_path) as conn:
        conn.executescript(_SCHEMA)
        row = conn.execute(
            "SELECT universe_id, channel_type, mode, set_by, updated_at "
            "FROM source_channel_policy "
            "WHERE universe_id = ? AND channel_type = ?",
            (uid, channel),
        ).fetchone()
    if row is None:
        return {
            "universe_id": uid,
            "channel_type": channel,
            "mode": MODE_REQUIRE,
            "set_by": "",
            "updated_at": None,
            "is_default": True,
        }
    return {
        "universe_id": row["universe_id"],
        "channel_type": row["channel_type"],
        "mode": row["mode"],
        "set_by": row["set_by"],
        "updated_at": row["updated_at"],
        "is_default": False,
    }
