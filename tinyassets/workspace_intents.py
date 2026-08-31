"""Durable push intents: what was sent, so a lost outcome can be settled.

A push is not idempotent from the daemon's side. If the process dies between
sending and recording the receipt, nothing local says whether the remote took
it -- and the two wrong answers are both bad: reporting success for a push that
never landed, or retrying one that did.

So the intent is written BEFORE the wire and settled after. On resume, every
intent still ``sent`` is asked of the remote: the same sha already at the ref
is ``done`` (a repeated non-force push of the same commit is not a failure),
anything else is ``failed`` and names what was observed. Design D1, crash
safety.

The table lives in the runs database beside the pool's, because it is settled
by the same startup path.
"""

from __future__ import annotations

import secrets
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "INTENT_STATES",
    "PushIntent",
    "ensure_schema",
    "open_intents",
    "record_push_intent",
    "reconcile_push_intents",
    "settle_push_intent",
]

#: The only states an intent may hold. ``unknown`` is for one the remote could
#: not be asked about -- it stays owed rather than being guessed either way.
INTENT_STATES = ("sent", "done", "failed", "unknown")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_push_intents (
    intent_id        TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    node_id          TEXT NOT NULL,
    connection_id    TEXT NOT NULL,
    repo             TEXT NOT NULL,
    remote_ref       TEXT NOT NULL,
    expected_old_sha TEXT,
    sha              TEXT NOT NULL,
    state            TEXT NOT NULL CHECK (state IN ('sent', 'done', 'failed', 'unknown')),
    observed_sha     TEXT,
    created_at       REAL NOT NULL,
    completed_at     REAL
);
CREATE INDEX IF NOT EXISTS workspace_push_intents_state
    ON workspace_push_intents (state);
"""


@dataclass(frozen=True)
class PushIntent:
    intent_id: str
    run_id: str
    node_id: str
    connection_id: str
    repo: str
    remote_ref: str
    sha: str
    state: str
    expected_old_sha: str | None = None
    observed_sha: str | None = None
    created_at: float = 0.0
    completed_at: float | None = None


def _db(base_path: str | Path) -> Path:
    from tinyassets import runs

    return runs.runs_db_path(base_path)


def _connect(base_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(_db(base_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the table if it is not there. Safe to call on every write."""
    conn.executescript(_SCHEMA)


def record_push_intent(
    base_path: str | Path,
    *,
    run_id: str,
    node_id: str,
    connection_id: str,
    repo: str,
    remote_ref: str,
    sha: str,
    expected_old_sha: str | None = None,
    now: Callable[[], float] = time.time,
) -> str:
    """Journal the intent BEFORE the wire; return its id.

    Committed before the push is sent, so a crash mid-flight always leaves a
    row to reconcile against.
    """
    intent_id = secrets.token_hex(16)
    conn = _connect(base_path)
    try:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO workspace_push_intents (intent_id, run_id, node_id, "
            "connection_id, repo, remote_ref, expected_old_sha, sha, state, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'sent', ?)",
            (
                intent_id,
                str(run_id),
                str(node_id),
                str(connection_id),
                str(repo),
                str(remote_ref),
                expected_old_sha,
                str(sha),
                float(now()),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return intent_id


def settle_push_intent(
    base_path: str | Path,
    intent_id: str,
    state: str,
    *,
    observed_sha: str | None = None,
    now: Callable[[], float] = time.time,
) -> None:
    """Mark an intent after the wire answered. Never raises into the push path."""
    if state not in INTENT_STATES:
        raise ValueError(f"state must be one of {INTENT_STATES}, got {state!r}")
    conn = _connect(base_path)
    try:
        ensure_schema(conn)
        conn.execute(
            "UPDATE workspace_push_intents SET state = ?, observed_sha = ?, "
            "completed_at = ? WHERE intent_id = ?",
            (state, observed_sha, float(now()), str(intent_id)),
        )
        conn.commit()
    finally:
        conn.close()


def open_intents(base_path: str | Path) -> list[PushIntent]:
    """Every intent still ``sent``: the ones whose outcome nobody recorded."""
    conn = _connect(base_path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM workspace_push_intents WHERE state = 'sent' "
            "ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()
    return [
        PushIntent(
            intent_id=row["intent_id"],
            run_id=row["run_id"],
            node_id=row["node_id"],
            connection_id=row["connection_id"],
            repo=row["repo"],
            remote_ref=row["remote_ref"],
            sha=row["sha"],
            state=row["state"],
            expected_old_sha=row["expected_old_sha"],
            observed_sha=row["observed_sha"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
        for row in rows
    ]


def reconcile_push_intents(
    base_path: str | Path,
    *,
    execute: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    credential_ref_for: Callable[[str], str] | None = None,
    host: str = "github.com",
    staging_root: str | Path | None = None,
) -> list[tuple[str, str]]:
    """Settle every open intent by ASKING the remote. Returns (intent_id, state).

    The same sha already at the ref is ``done``: a repeated non-force push of
    the same commit is success, not a failure. Anything else is ``failed`` with
    the observed ref recorded. An intent the remote could not be asked about
    becomes ``unknown`` and stays owed -- never guessed in either direction.
    """
    intents = open_intents(base_path)
    if not intents:
        return []
    if execute is None:
        from tinyassets.workspace_worker import execute_workspace_operation

        execute = execute_workspace_operation

    root = (
        Path(staging_root)
        if staging_root is not None
        else Path(base_path) / ".workspace-staging"
    )
    root.mkdir(parents=True, exist_ok=True)
    settled: list[tuple[str, str]] = []
    for intent in intents:
        staging = root / f"reconcile-{intent.intent_id}"
        staging.mkdir(parents=True, exist_ok=True)
        credential_ref = ""
        if credential_ref_for is not None:
            try:
                credential_ref = credential_ref_for(intent.connection_id)
            except Exception:
                credential_ref = ""
        if not credential_ref:
            credential_ref = _credential_ref(base_path, intent.connection_id)
        answer: dict[str, Any]
        try:
            answer = execute(
                {
                    "op": "ls_remote",
                    "universe_dir": str(base_path),
                    "credential_ref": credential_ref,
                    "host": host,
                    "owner_repo": intent.repo,
                    "remote_ref": intent.remote_ref,
                    "staging_dir": str(staging),
                }
            )
        except Exception:
            answer = {"ok": False}
        if not answer.get("ok"):
            state, observed = "unknown", None
        else:
            observed = str(answer.get("observed_sha") or "")
            state = "done" if observed == intent.sha else "failed"
        settle_push_intent(base_path, intent.intent_id, state, observed_sha=observed)
        settled.append((intent.intent_id, state))
    return settled


def _credential_ref(base_path: str | Path, connection_id: str) -> str:
    """The connection's credential REFERENCE (never a secret), or empty."""
    if not connection_id:
        return ""
    try:
        from tinyassets.storage.outbound_connections import ConnectionLedger

        ledger = ConnectionLedger(Path(base_path).parent / "outbound.db")
        resource = ledger._get_connection_resource(connection_id)
        return str(getattr(resource, "credential_ref", "") or "")
    except Exception:
        return ""
