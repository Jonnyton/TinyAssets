"""Per-branch inbound webhook tokens (channel-agnostic inbound, Floor 1).

A hook token is an unguessable secret that binds ONE public URL to exactly one
(universe, branch): a `POST /hooks/<token>` runs that branch as that universe. The
token is the ONLY authority — nothing in the request can redirect the run — so an
inbound POST can never trigger a different branch or act as a different universe.

Content-free: a row holds identifiers + the token only (no credential, no body). The
table is keyed by token so the receiver can resolve (universe, branch) without knowing
the universe up front; the mint/revoke surface enforces per-universe ownership.
"""

from __future__ import annotations

import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from tinyassets.storage import db_path

#: Bound the ids we persist — a webhook binding is identifiers, never a body/secret.
MAX_ID_LEN = 256

_SCHEMA = """
CREATE TABLE IF NOT EXISTS webhook_hooks (
    token          TEXT PRIMARY KEY,
    universe_id    TEXT NOT NULL,
    branch_def_id  TEXT NOT NULL,
    created_at     REAL NOT NULL,
    revoked_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_webhook_hooks_universe
    ON webhook_hooks(universe_id);
"""


def _connect(base_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(Path(base_path)))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def mint(
    base_path: str | Path,
    *,
    universe_id: str,
    branch_def_id: str,
    now: float | None = None,
) -> str:
    """Mint a fresh unguessable hook token binding ``branch_def_id`` to ``universe_id``.

    Returns the token. Caller MUST have already authorized that the universe owns the
    branch (this store does not check ownership — the mint operation does).
    """
    for name, val in (("universe_id", universe_id), ("branch_def_id", branch_def_id)):
        if not isinstance(val, str) or not val:
            raise ValueError(f"webhook_hooks: {name} must be a non-empty string")
        if len(val) > MAX_ID_LEN:
            raise ValueError(f"webhook_hooks: {name} exceeds {MAX_ID_LEN} chars")
    token = secrets.token_urlsafe(32)
    ts = time.time() if now is None else now
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO webhook_hooks (token, universe_id, branch_def_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, universe_id, branch_def_id, ts),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def resolve(base_path: str | Path, *, token: str) -> dict[str, Any] | None:
    """Return ``{universe_id, branch_def_id}`` for an ACTIVE token, else None.

    None covers unknown, revoked, and empty/malformed tokens alike — the receiver must
    answer all three identically (no enumeration signal).
    """
    if not isinstance(token, str) or not token:
        return None
    conn = _connect(base_path)
    try:
        row = conn.execute(
            """
            SELECT universe_id, branch_def_id FROM webhook_hooks
             WHERE token = ? AND revoked_at IS NULL
            """,
            (token,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def revoke(base_path: str | Path, *, token: str, now: float | None = None) -> bool:
    """Revoke a token (soft: kept for audit). Returns True if an active token was revoked."""
    ts = time.time() if now is None else now
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE webhook_hooks SET revoked_at = ? WHERE token = ? AND revoked_at IS NULL",
            (ts, token),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def list_for_universe(
    base_path: str | Path, *, universe_id: str,
) -> list[dict[str, Any]]:
    """All hooks (active + revoked) for one universe, newest first. Tokens included so the
    owner can see/rotate them; this is only ever returned to the owning universe."""
    conn = _connect(base_path)
    try:
        rows = conn.execute(
            """
            SELECT token, branch_def_id, created_at, revoked_at FROM webhook_hooks
             WHERE universe_id = ?
             ORDER BY created_at DESC
            """,
            (universe_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
