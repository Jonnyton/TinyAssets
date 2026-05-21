"""External-write idempotency receipts — PR-122 Phase 2 Slice 1.

Per-universe SQLite store recording every successful external write so
that re-running a branch with the same ``idempotency_hint`` returns the
recorded evidence instead of firing the side-effect again.

Design source: ``drafts/concepts/external-write-phase-2-authority.md``
§2 "Idempotency store". The store is one of three gates the
``github_pr`` effector consults before any real ``gh pr create`` fires
(capability env + consent grant + idempotency receipt).

Schema (per-universe, file: ``${universe_dir}/.external_write_receipts.db``):

.. code-block:: sql

    CREATE TABLE IF NOT EXISTS external_write_receipts (
        idempotency_hint TEXT NOT NULL,
        sink             TEXT NOT NULL,
        evidence_json    TEXT NOT NULL,
        run_id           TEXT NOT NULL,
        created_at       REAL NOT NULL,
        PRIMARY KEY (idempotency_hint, sink)
    );

Mutation contract — **last-write-wins on the same hint** (per the
design stub). A retried run whose prior receipt has gone stale
(remote PR closed, head_branch deleted) may overwrite. Reads return
the most recent receipt.

This module is intentionally narrow: CRUD helpers + a schema-migrating
``initialize_receipts_db`` bootstrap. No dependency on
``workflow.daemon_server`` so the effector can call it without dragging
the universe-server bootstrap chain into the run path.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

_DB_FILENAME = ".external_write_receipts.db"


def receipts_db_path(universe_dir: str | Path) -> Path:
    """Resolve the per-universe receipts DB path."""
    return Path(universe_dir) / _DB_FILENAME


def _connect(universe_dir: str | Path) -> sqlite3.Connection:
    """Open the receipts DB with WAL + 30s busy timeout (run-path-safe)."""
    path = receipts_db_path(universe_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS external_write_receipts (
    idempotency_hint TEXT NOT NULL,
    sink             TEXT NOT NULL,
    evidence_json    TEXT NOT NULL,
    run_id           TEXT NOT NULL,
    created_at       REAL NOT NULL,
    PRIMARY KEY (idempotency_hint, sink)
);

CREATE INDEX IF NOT EXISTS idx_receipts_sink_created
    ON external_write_receipts(sink, created_at DESC);
"""


def initialize_receipts_db(universe_dir: str | Path) -> Path:
    """Ensure the receipts DB exists and is migrated. Returns the DB path."""
    path = receipts_db_path(universe_dir)
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    return path


def lookup_receipt(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
) -> dict[str, Any] | None:
    """Return the most recent receipt for ``(idempotency_hint, sink)``.

    Returns ``None`` when no receipt is recorded. Empty ``idempotency_hint``
    returns ``None`` — the effector treats "no hint" as "always miss" so
    the caller can opt out of dedup by omitting the field.
    """
    if not idempotency_hint:
        return None
    initialize_receipts_db(universe_dir)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            """
            SELECT idempotency_hint, sink, evidence_json, run_id, created_at
              FROM external_write_receipts
             WHERE idempotency_hint = ? AND sink = ?
            """,
            (idempotency_hint, sink),
        ).fetchone()
    if row is None:
        return None
    try:
        evidence = json.loads(row["evidence_json"])
    except (TypeError, ValueError):
        evidence = {}
    return {
        "idempotency_hint": row["idempotency_hint"],
        "sink": row["sink"],
        "evidence": evidence,
        "run_id": row["run_id"],
        "created_at": row["created_at"],
    }


def record_receipt(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
    evidence: dict[str, Any],
    run_id: str,
    created_at: float | None = None,
) -> None:
    """Write a receipt for ``(idempotency_hint, sink)``.

    Last-write-wins on the same key — an existing row is replaced. Caller
    must supply ``evidence`` as a JSON-serializable dict; non-serializable
    values raise ``TypeError`` (loud failure per hard rule #8).

    Empty ``idempotency_hint`` is a silent no-op so the effector can
    safely call ``record_receipt`` regardless of whether the packet
    supplied a hint. Receipts without a key can't be looked up later, so
    storing them is wasted work.
    """
    if not idempotency_hint:
        return
    initialize_receipts_db(universe_dir)
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    ts = created_at if created_at is not None else time.time()
    with _connect(universe_dir) as conn:
        conn.execute(
            """
            INSERT INTO external_write_receipts (
                idempotency_hint, sink, evidence_json, run_id, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(idempotency_hint, sink) DO UPDATE SET
                evidence_json = excluded.evidence_json,
                run_id        = excluded.run_id,
                created_at    = excluded.created_at
            """,
            (idempotency_hint, sink, payload, run_id, ts),
        )
        conn.commit()


def delete_receipt(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
) -> bool:
    """Remove the receipt for ``(idempotency_hint, sink)``. Returns True on hit.

    Used by the effector when a prior receipt is verified stale (remote
    PR closed/deleted/superseded) — the effector deletes the stale row
    before proceeding to a real invocation, so the new receipt lands at
    the canonical key without an UPDATE conflict ambiguity.
    """
    if not idempotency_hint:
        return False
    initialize_receipts_db(universe_dir)
    with _connect(universe_dir) as conn:
        cur = conn.execute(
            "DELETE FROM external_write_receipts "
            "WHERE idempotency_hint = ? AND sink = ?",
            (idempotency_hint, sink),
        )
        conn.commit()
        return cur.rowcount > 0


def list_receipts(
    universe_dir: str | Path,
    *,
    sink: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return receipts, most-recent first. Optional sink filter.

    Diagnostic surface for the chatbot (Phase-2 ``list_effector_receipts``
    follow-on) and tests. Bounded by ``limit``.
    """
    initialize_receipts_db(universe_dir)
    limit = max(1, min(int(limit), 1000))
    with _connect(universe_dir) as conn:
        if sink:
            rows = conn.execute(
                """
                SELECT idempotency_hint, sink, evidence_json, run_id, created_at
                  FROM external_write_receipts
                 WHERE sink = ?
              ORDER BY created_at DESC
                 LIMIT ?
                """,
                (sink, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT idempotency_hint, sink, evidence_json, run_id, created_at
                  FROM external_write_receipts
              ORDER BY created_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            evidence = json.loads(row["evidence_json"])
        except (TypeError, ValueError):
            evidence = {}
        out.append({
            "idempotency_hint": row["idempotency_hint"],
            "sink": row["sink"],
            "evidence": evidence,
            "run_id": row["run_id"],
            "created_at": row["created_at"],
        })
    return out


__all__ = [
    "receipts_db_path",
    "initialize_receipts_db",
    "lookup_receipt",
    "record_receipt",
    "delete_receipt",
    "list_receipts",
]
