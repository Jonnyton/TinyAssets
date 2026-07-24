"""Transactional request-admission and queue-epoch-2 persistence.

This module is intentionally storage-only. Public request parsing, authority
composition, rollout gates, dispatcher selection, and external execution
authority live in later layers. The writer remains unreachable until those
layers explicitly call :class:`RequestAdmissionStore`.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import sqlite3
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from tinyassets.storage import db_path

PRIORITY_WEIGHT_CAP = 100
QUEUE_EPOCH = 2
QUEUE_PROTOCOL_VERSION = 2
OPERATOR_CAPABILITY = "operator_request_v1"
TERMINAL_STATUSES = frozenset({"cancelled", "succeeded", "failed"})

# Fault-injection checkpoints immediately after each aggregate mutation.
COMMIT_STEPS = (
    "request_inserted",
    "admission_inserted",
    "task_inserted",
    "event_inserted",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS request_admissions (
    admission_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    branch_task_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    idempotency_key_hash TEXT NOT NULL,
    body_digest TEXT NOT NULL,
    body_digest_version TEXT NOT NULL,
    trigger_source TEXT NOT NULL
        CHECK (trigger_source IN (
            'operator_request', 'user_request', 'owner_queued'
        )),
    accepted_priority_weight REAL NOT NULL
        CHECK (
            accepted_priority_weight = accepted_priority_weight
            AND accepted_priority_weight >= 0
            AND accepted_priority_weight <= 100
        ),
    priority_policy_version TEXT NOT NULL,
    grant_generation INTEGER NOT NULL DEFAULT 0
        CHECK (grant_generation >= 0),
    receipt_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'committed'
        CHECK (state IN ('committed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    terminal_at TEXT,
    compacted_at TEXT,
    UNIQUE (
        tenant_id, actor_id, universe_id, idempotency_key_hash
    ),
    FOREIGN KEY(request_id) REFERENCES user_requests(request_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(branch_task_id) REFERENCES branch_tasks_v2(branch_task_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS branch_tasks_v2 (
    branch_task_id TEXT PRIMARY KEY,
    admission_id TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL UNIQUE,
    universe_id TEXT NOT NULL,
    branch_def_id TEXT NOT NULL,
    inputs_json TEXT NOT NULL DEFAULT '{}',
    trigger_source TEXT NOT NULL
        CHECK (trigger_source IN (
            'operator_request', 'user_request', 'owner_queued'
        )),
    priority_weight REAL NOT NULL
        CHECK (
            priority_weight = priority_weight
            AND priority_weight >= 0
            AND priority_weight <= 100
        ),
    directed_daemon_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'running', 'cancel_requested', 'cancelled',
            'succeeded', 'failed'
        )),
    queue_epoch INTEGER NOT NULL DEFAULT 2 CHECK (queue_epoch = 2),
    protocol_version INTEGER NOT NULL DEFAULT 2
        CHECK (protocol_version = 2),
    claimed_by TEXT NOT NULL DEFAULT '',
    queued_at TEXT NOT NULL,
    claimed_at TEXT,
    heartbeat_at TEXT,
    terminal_at TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}',
    disabled INTEGER NOT NULL DEFAULT 0 CHECK (disabled IN (0, 1)),
    quarantine_reason TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(admission_id) REFERENCES request_admissions(admission_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(request_id) REFERENCES user_requests(request_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS request_admission_events (
    event_id TEXT PRIMARY KEY,
    admission_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    branch_task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(admission_id) REFERENCES request_admissions(admission_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(request_id) REFERENCES user_requests(request_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(branch_task_id) REFERENCES branch_tasks_v2(branch_task_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS branch_tasks_v2_quarantine (
    row_digest TEXT PRIMARY KEY,
    branch_task_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    row_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1 CHECK (seen_count >= 1),
    FOREIGN KEY(branch_task_id) REFERENCES branch_tasks_v2(branch_task_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS request_admission_rollouts (
    universe_id TEXT PRIMARY KEY,
    rollout_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL
        CHECK (state IN (
            'disabled', 'readers_only', 'canary', 'enabled', 'rollback'
        )),
    queue_epoch INTEGER NOT NULL DEFAULT 2 CHECK (queue_epoch = 2),
    required_capability TEXT NOT NULL DEFAULT 'operator_request_v1',
    allowed_reader_shas_json TEXT NOT NULL DEFAULT '[]',
    allowed_server_shas_json TEXT NOT NULL DEFAULT '[]',
    config_hash TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    activated_at TEXT,
    expires_at TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_request_admissions_scope
    ON request_admissions(
        tenant_id, actor_id, universe_id, idempotency_key_hash
    );
CREATE INDEX IF NOT EXISTS idx_request_admissions_universe
    ON request_admissions(universe_id, state, created_at);
CREATE INDEX IF NOT EXISTS idx_branch_tasks_v2_pickable
    ON branch_tasks_v2(status, disabled, queued_at);
CREATE INDEX IF NOT EXISTS idx_branch_tasks_v2_universe
    ON branch_tasks_v2(universe_id, status, disabled, queued_at);
CREATE INDEX IF NOT EXISTS idx_request_admission_events_admission
    ON request_admission_events(admission_id, event_at);
CREATE INDEX IF NOT EXISTS idx_request_admission_events_task
    ON request_admission_events(branch_task_id, event_at);
CREATE INDEX IF NOT EXISTS idx_branch_tasks_v2_quarantine_task
    ON branch_tasks_v2_quarantine(branch_task_id);
"""


class IdempotencyKeyBodyConflict(ValueError):
    """A scoped idempotency key was reused for a different canonical body."""


class RequestAdmissionStore:
    """SQLite implementation of the backend-neutral admission aggregate."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        id_factory: Callable[[str], str] | None = None,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        self.base_path = Path(base_path)
        self._id_factory = id_factory or _random_id
        self._busy_timeout_ms = int(busy_timeout_ms)
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Open a WAL/foreign-key/busy-timeout connection.

        Lock errors deliberately propagate. Treating a lock as an idempotency
        miss would permit duplicate effects.
        """

        path = db_path(self.base_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            yield conn
        finally:
            conn.close()

    def commit_admission(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        universe_id: str,
        idempotency_key_hash: str,
        body_digest: str,
        body_digest_version: str,
        request_type: str,
        text: str,
        branch_id: str,
        branch_def_id: str,
        trigger_source: str,
        accepted_priority_weight: float,
        policy_version: str,
        grant_generation: int,
        receipt: Mapping[str, Any],
        directed_daemon_id: str,
        created_at: str,
        authority_check: Callable[[sqlite3.Connection], Any] | None = None,
        fault_injector: (
            Callable[[str, sqlite3.Connection], Any] | None
        ) = None,
    ) -> dict[str, Any]:
        """Atomically create Request, Admission, v2 task, and committed event."""

        scope = (
            _required(tenant_id, "tenant_id"),
            _required(actor_id, "actor_id"),
            _required(universe_id, "universe_id"),
            _required(idempotency_key_hash, "idempotency_key_hash"),
        )
        _required(body_digest, "body_digest")
        _required(body_digest_version, "body_digest_version")
        _required(branch_def_id, "branch_def_id")
        _required(created_at, "created_at")
        accepted_weight = float(accepted_priority_weight)
        if (
            not math.isfinite(accepted_weight)
            or accepted_weight < 0
            or accepted_weight > PRIORITY_WEIGHT_CAP
        ):
            raise ValueError(
                "accepted_priority_weight must be finite and within [0, 100]"
            )

        for attempt in range(5):
            with self.connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if authority_check is not None:
                        authority_check(conn)

                    replay = self._lookup_replay_conn(
                        conn,
                        tenant_id=scope[0],
                        actor_id=scope[1],
                        universe_id=scope[2],
                        idempotency_key_hash=scope[3],
                        body_digest=body_digest,
                        body_digest_version=body_digest_version,
                    )
                    if replay is not None:
                        conn.commit()
                        return replay

                    request_id = self._id_factory("req")
                    admission_id = self._id_factory("adm")
                    branch_task_id = self._id_factory("bt2")
                    event_id = self._id_factory("evt")
                    result = _public_result(
                        universe_id=scope[2],
                        admission_id=admission_id,
                        request_id=request_id,
                        branch_task_id=branch_task_id,
                        trigger_source=trigger_source,
                        accepted_priority_weight=accepted_weight,
                        policy_version=policy_version,
                        directed_daemon_id=directed_daemon_id,
                        idempotent_replay=False,
                    )

                    conn.execute(
                        """
                        INSERT INTO user_requests (
                            request_id, universe_id, branch_id, user_id,
                            request_type, text, preferred_author_id, status,
                            created_at, updated_at, metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                        """,
                        (
                            request_id,
                            scope[2],
                            branch_id or None,
                            scope[1],
                            request_type,
                            text,
                            directed_daemon_id or None,
                            _epoch_seconds(created_at),
                            _epoch_seconds(created_at),
                            _json({
                                "tenant_id": scope[0],
                                "admission_id": admission_id,
                                "queue_epoch": QUEUE_EPOCH,
                            }),
                        ),
                    )
                    _inject(fault_injector, "request_inserted", conn)

                    conn.execute(
                        """
                        INSERT INTO request_admissions (
                            admission_id, request_id, branch_task_id,
                            tenant_id, actor_id, universe_id,
                            idempotency_key_hash, body_digest,
                            body_digest_version, trigger_source,
                            accepted_priority_weight,
                            priority_policy_version, grant_generation,
                            receipt_json, result_json, state,
                            created_at, updated_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            'committed', ?, ?
                        )
                        """,
                        (
                            admission_id,
                            request_id,
                            branch_task_id,
                            scope[0],
                            scope[1],
                            scope[2],
                            scope[3],
                            body_digest,
                            body_digest_version,
                            trigger_source,
                            accepted_weight,
                            policy_version,
                            grant_generation,
                            _json(dict(receipt)),
                            _json(result),
                            created_at,
                            created_at,
                        ),
                    )
                    _inject(fault_injector, "admission_inserted", conn)

                    conn.execute(
                        """
                        INSERT INTO branch_tasks_v2 (
                            branch_task_id, admission_id, request_id,
                            universe_id, branch_def_id, inputs_json,
                            trigger_source, priority_weight,
                            directed_daemon_id, status, queue_epoch,
                            protocol_version, queued_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 2, 2, ?
                        )
                        """,
                        (
                            branch_task_id,
                            admission_id,
                            request_id,
                            scope[2],
                            branch_def_id,
                            _json({
                                "request_id": request_id,
                                "request_type": request_type,
                                "branch_id": branch_id,
                            }),
                            trigger_source,
                            accepted_weight,
                            directed_daemon_id,
                            created_at,
                        ),
                    )
                    _inject(fault_injector, "task_inserted", conn)

                    conn.execute(
                        """
                        INSERT INTO request_admission_events (
                            event_id, admission_id, request_id,
                            branch_task_id, event_type, event_at, detail_json
                        ) VALUES (?, ?, ?, ?, 'committed', ?, ?)
                        """,
                        (
                            event_id,
                            admission_id,
                            request_id,
                            branch_task_id,
                            created_at,
                            _json({
                                "queue_epoch": QUEUE_EPOCH,
                                "trigger_source": trigger_source,
                            }),
                        ),
                    )
                    _inject(fault_injector, "event_inserted", conn)
                    conn.commit()
                    return result
                except sqlite3.IntegrityError as exc:
                    conn.rollback()
                    if _looks_like_random_id_collision(exc) and attempt < 4:
                        continue
                    raise
                except Exception:
                    conn.rollback()
                    raise
        raise RuntimeError("request admission ID allocation exhausted")

    def lookup_replay(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        universe_id: str,
        idempotency_key_hash: str,
        body_digest: str,
        body_digest_version: str,
    ) -> dict[str, Any] | None:
        with self.connection() as conn:
            return self._lookup_replay_conn(
                conn,
                tenant_id=tenant_id,
                actor_id=actor_id,
                universe_id=universe_id,
                idempotency_key_hash=idempotency_key_hash,
                body_digest=body_digest,
                body_digest_version=body_digest_version,
            )

    def _lookup_replay_conn(
        self,
        conn: sqlite3.Connection,
        *,
        tenant_id: str,
        actor_id: str,
        universe_id: str,
        idempotency_key_hash: str,
        body_digest: str,
        body_digest_version: str,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT body_digest, body_digest_version, result_json
            FROM request_admissions
            WHERE tenant_id = ? AND actor_id = ? AND universe_id = ?
              AND idempotency_key_hash = ?
            """,
            (
                tenant_id,
                actor_id,
                universe_id,
                idempotency_key_hash,
            ),
        ).fetchone()
        if row is None:
            return None
        if (
            row["body_digest"] != body_digest
            or row["body_digest_version"] != body_digest_version
        ):
            raise IdempotencyKeyBodyConflict(
                "idempotency_key_body_conflict"
            )
        result = json.loads(row["result_json"])
        result["idempotent_replay"] = True
        return result

    def list_v2_candidates(
        self,
        *,
        universe_id: str = "",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        clauses = ["status = 'pending'", "disabled = 0"]
        params: list[Any] = []
        if universe_id:
            clauses.append("universe_id = ?")
            params.append(universe_id)
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM branch_tasks_v2 WHERE "
                + " AND ".join(clauses)
                + " ORDER BY queued_at ASC, branch_task_id ASC LIMIT ?",
                params,
            ).fetchall()
        return [_task_row(row) for row in rows]

    def claim_v2_task(
        self,
        branch_task_id: str,
        *,
        worker_id: str,
        queue_protocol_version: int,
        capabilities: Iterable[str],
        claimed_at: str,
    ) -> dict[str, Any] | None:
        if queue_protocol_version != QUEUE_PROTOCOL_VERSION:
            return None
        if OPERATOR_CAPABILITY not in set(capabilities):
            return None
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM branch_tasks_v2
                    WHERE branch_task_id = ?
                      AND status = 'pending'
                      AND disabled = 0
                      AND queue_epoch = 2
                      AND protocol_version = 2
                    """,
                    (branch_task_id,),
                ).fetchone()
                if row is None:
                    conn.commit()
                    return None
                cursor = conn.execute(
                    """
                    UPDATE branch_tasks_v2
                    SET status = 'running', claimed_by = ?,
                        claimed_at = ?, heartbeat_at = ?
                    WHERE branch_task_id = ?
                      AND status = 'pending' AND disabled = 0
                    """,
                    (
                        _required(worker_id, "worker_id"),
                        claimed_at,
                        claimed_at,
                        branch_task_id,
                    ),
                )
                if cursor.rowcount != 1:
                    conn.rollback()
                    return None
                self._append_task_event(
                    conn,
                    row,
                    event_type="claimed",
                    event_at=claimed_at,
                    detail={"worker_id": worker_id},
                )
                claimed = conn.execute(
                    "SELECT * FROM branch_tasks_v2 "
                    "WHERE branch_task_id = ?",
                    (branch_task_id,),
                ).fetchone()
                conn.commit()
                return _task_row(claimed)
            except Exception:
                conn.rollback()
                raise

    def transition_task(
        self,
        branch_task_id: str,
        *,
        expected_statuses: set[str],
        new_status: str,
        at: str,
        detail: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not expected_statuses:
            raise ValueError("expected_statuses must not be empty")
        if new_status not in {
            "pending",
            "running",
            "cancel_requested",
            "cancelled",
            "succeeded",
            "failed",
        }:
            raise ValueError(f"invalid v2 task status: {new_status}")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM branch_tasks_v2 "
                    "WHERE branch_task_id = ?",
                    (branch_task_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(branch_task_id)
                if row["status"] not in expected_statuses:
                    raise ValueError(
                        f"expected {sorted(expected_statuses)}, "
                        f"found {row['status']}"
                    )
                terminal_at = at if new_status in TERMINAL_STATUSES else None
                conn.execute(
                    """
                    UPDATE branch_tasks_v2
                    SET status = ?, terminal_at = COALESCE(?, terminal_at),
                        detail_json = ?
                    WHERE branch_task_id = ?
                    """,
                    (
                        new_status,
                        terminal_at,
                        _json(dict(detail or {})),
                        branch_task_id,
                    ),
                )
                if terminal_at is not None:
                    conn.execute(
                        """
                        UPDATE request_admissions
                        SET terminal_at = ?, updated_at = ?
                        WHERE admission_id = ?
                        """,
                        (terminal_at, at, row["admission_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE user_requests
                        SET status = ?, updated_at = ?
                        WHERE request_id = ?
                        """,
                        (new_status, _epoch_seconds(at), row["request_id"]),
                    )
                self._append_task_event(
                    conn,
                    row,
                    event_type=new_status,
                    event_at=at,
                    detail=dict(detail or {}),
                )
                updated = conn.execute(
                    "SELECT * FROM branch_tasks_v2 "
                    "WHERE branch_task_id = ?",
                    (branch_task_id,),
                ).fetchone()
                conn.commit()
                return _task_row(updated)
            except Exception:
                conn.rollback()
                raise

    def quarantine_task(
        self,
        branch_task_id: str,
        *,
        reason: str,
        observed_at: str,
    ) -> dict[str, Any]:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM branch_tasks_v2 "
                    "WHERE branch_task_id = ?",
                    (branch_task_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(branch_task_id)
                snapshot = _task_row(row)
                snapshot.pop("disabled", None)
                snapshot.pop("quarantine_reason", None)
                digest = hashlib.sha256(
                    _json(snapshot).encode("utf-8")
                ).hexdigest()
                existing_receipt = conn.execute(
                    """
                    SELECT row_digest
                    FROM branch_tasks_v2_quarantine
                    WHERE row_digest = ?
                    """,
                    (digest,),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO branch_tasks_v2_quarantine (
                        row_digest, branch_task_id, universe_id, reason,
                        row_json, first_seen_at, last_seen_at, seen_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(row_digest) DO UPDATE SET
                        last_seen_at = excluded.last_seen_at,
                        seen_count = branch_tasks_v2_quarantine.seen_count + 1
                    """,
                    (
                        digest,
                        branch_task_id,
                        row["universe_id"],
                        _required(reason, "reason"),
                        _json(snapshot),
                        observed_at,
                        observed_at,
                    ),
                )
                conn.execute(
                    """
                    UPDATE branch_tasks_v2
                    SET disabled = 1, quarantine_reason = ?
                    WHERE branch_task_id = ?
                    """,
                    (reason, branch_task_id),
                )
                if existing_receipt is None:
                    self._append_task_event(
                        conn,
                        row,
                        event_type="quarantined",
                        event_at=observed_at,
                        detail={"reason": reason, "row_digest": digest},
                    )
                receipt = conn.execute(
                    """
                    SELECT
                        row_digest, branch_task_id, reason,
                        first_seen_at, last_seen_at
                    FROM branch_tasks_v2_quarantine
                    WHERE row_digest = ?
                    """,
                    (digest,),
                ).fetchone()
                conn.commit()
                return dict(receipt)
            except Exception:
                conn.rollback()
                raise

    def compact_terminal_details(
        self,
        *,
        terminal_before: str,
        compacted_at: str,
    ) -> int:
        """Compact terminal private detail while retaining replay tombstones."""

        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                rows = conn.execute(
                    """
                    SELECT
                        a.admission_id, a.request_id, a.branch_task_id,
                        a.universe_id, t.status
                    FROM request_admissions AS a
                    JOIN branch_tasks_v2 AS t
                      ON t.branch_task_id = a.branch_task_id
                    WHERE a.compacted_at IS NULL
                      AND a.terminal_at IS NOT NULL
                      AND a.terminal_at < ?
                      AND t.status IN ('cancelled', 'succeeded', 'failed')
                    """,
                    (terminal_before,),
                ).fetchall()
                for row in rows:
                    tombstone = {
                        "admission_id": row["admission_id"],
                        "branch_task_id": row["branch_task_id"],
                        "request_id": row["request_id"],
                        "request_status": row["status"],
                        "universe_id": row["universe_id"],
                    }
                    conn.execute(
                        """
                        UPDATE user_requests
                        SET text = '', metadata_json = ?
                        WHERE request_id = ?
                        """,
                        (
                            _json({
                                "compacted": True,
                                "queue_epoch": QUEUE_EPOCH,
                            }),
                            row["request_id"],
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE request_admissions
                        SET receipt_json = '{}', result_json = ?,
                            compacted_at = ?, updated_at = ?
                        WHERE admission_id = ?
                        """,
                        (
                            _json(tombstone),
                            compacted_at,
                            compacted_at,
                            row["admission_id"],
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE request_admission_events
                        SET detail_json = '{}'
                        WHERE admission_id = ?
                        """,
                        (row["admission_id"],),
                    )
                conn.commit()
                return len(rows)
            except Exception:
                conn.rollback()
                raise

    def delete_universe(self, universe_id: str) -> int:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM user_requests "
                        "WHERE universe_id = ?",
                        (universe_id,),
                    ).fetchone()[0]
                )
                conn.execute(
                    "DELETE FROM user_requests WHERE universe_id = ?",
                    (universe_id,),
                )
                conn.execute(
                    "DELETE FROM request_admission_rollouts "
                    "WHERE universe_id = ?",
                    (universe_id,),
                )
                conn.commit()
                return count
            except Exception:
                conn.rollback()
                raise

    def _append_task_event(
        self,
        conn: sqlite3.Connection,
        task_row: sqlite3.Row,
        *,
        event_type: str,
        event_at: str,
        detail: Mapping[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO request_admission_events (
                event_id, admission_id, request_id, branch_task_id,
                event_type, event_at, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._id_factory("evt"),
                task_row["admission_id"],
                task_row["request_id"],
                task_row["branch_task_id"],
                event_type,
                event_at,
                _json(dict(detail)),
            ),
        )


def migrate_request_admission_schema(conn: sqlite3.Connection) -> None:
    """Create the epoch-2 schema on the active pre-traffic DB connection."""

    conn.executescript(_SCHEMA)


def _public_result(
    *,
    universe_id: str,
    admission_id: str,
    request_id: str,
    branch_task_id: str,
    trigger_source: str,
    accepted_priority_weight: float,
    policy_version: str,
    directed_daemon_id: str,
    idempotent_replay: bool,
) -> dict[str, Any]:
    return {
        "universe_id": universe_id,
        "admission_id": admission_id,
        "admission_state": "committed",
        "request_id": request_id,
        "branch_task_id": branch_task_id,
        "request_status": "pending",
        "trigger_source": trigger_source,
        "accepted_priority_weight": float(accepted_priority_weight),
        "priority_weight_cap": PRIORITY_WEIGHT_CAP,
        "priority_policy_version": policy_version,
        "idempotent_replay": idempotent_replay,
        "directed_daemon_id": directed_daemon_id,
    }


def _task_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["inputs"] = json.loads(result.pop("inputs_json"))
    result["detail"] = json.loads(result.pop("detail_json"))
    result["disabled"] = bool(result["disabled"])
    return result


def _random_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _required(value: str, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def _epoch_seconds(timestamp: str) -> float:
    try:
        from datetime import datetime

        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return time.time()


def _inject(
    injector: Callable[[str, sqlite3.Connection], Any] | None,
    step: str,
    conn: sqlite3.Connection,
) -> None:
    if injector is not None:
        injector(step, conn)


def _looks_like_random_id_collision(exc: sqlite3.IntegrityError) -> bool:
    message = str(exc).lower()
    return (
        "primary key" in message
        or "request_admissions.admission_id" in message
        or "branch_tasks_v2.branch_task_id" in message
        or "request_admission_events.event_id" in message
        or "user_requests.request_id" in message
    )
