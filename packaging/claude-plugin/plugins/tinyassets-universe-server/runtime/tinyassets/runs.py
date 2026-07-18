"""Run orchestration for community-designed branches.

Stores run metadata and per-step events in ``<base>/.runs.db`` so Phase 4
can judge, diff, and iterate on run output. Runs are synchronous in v1
per PLAN.md discussion (see task #39 for the async follow-up) — a single
``start_run`` call compiles, invokes, and persists the final state before
returning. That makes reasoning about cancel/thread-isolation trivial:
one run per tool call, no background tasks to babysit.

DB layout:

- ``runs``   — one row per run: id, branch_def_id, status, thread_id,
               inputs_json, output_json, started_at, finished_at, error.
- ``events`` — one row per node step: run_id, step_index, node_id,
               status, started_at, finished_at, detail_json.

Concurrency-safe across processes via WAL. No long-held connection —
each operation opens, commits, closes.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from tinyassets.sandbox_policy import ExecutionScope

from tinyassets.branches import BranchDefinition
from tinyassets.graph_compiler import (
    CompilerError,
    EmptyResponseError,
    NodeEnqueueContext,
    NodeTimeoutError,
    UnapprovedNodeError,
    compile_branch,
    seed_initial_state,
)

if TYPE_CHECKING:
    from tinyassets.sandbox_policy import ExecutionScope

logger = logging.getLogger(__name__)


RUN_STATUS_QUEUED = "queued"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELLED = "cancelled"
RUN_STATUS_INTERRUPTED = "interrupted"
RUN_STATUS_RESUMED = "resumed"

NODE_STATUS_PENDING = "pending"
NODE_STATUS_RUNNING = "running"
NODE_STATUS_RAN = "ran"
NODE_STATUS_FAILED = "failed"
NODE_STATUS_SKIPPED = "skipped"


class RunCancelledError(Exception):
    """Raised from an event_sink when a run has been cancelled so the
    graph invocation unwinds cleanly. Caught by the executor and
    reported as ``status=cancelled``."""


def runs_db_path(base_path: str | Path) -> Path:
    return Path(base_path) / ".runs.db"


@contextlib.contextmanager
def _connect(base_path: str | Path) -> sqlite3.Connection:
    db = runs_db_path(base_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> float:
    return time.time()


def _resolve_owner_user_id(
    base_path: str | Path,
    daemon_id: str | None,
) -> str:
    clean_daemon_id = str(daemon_id or "").strip()
    if not clean_daemon_id:
        return ""
    try:
        from tinyassets.daemon_registry import get_daemon

        daemon = get_daemon(base_path, daemon_id=clean_daemon_id)
    except Exception:
        return ""
    return str(daemon.get("owner_user_id") or "")


def _orphaned_run_grace_seconds() -> float | None:
    """Return the read-time orphan recovery grace window.

    Background runs are owned by an in-process ``Future``. After a server
    restart, durable rows can still say ``queued``/``running`` even though no
    worker in the new process can complete them. Read paths use this window to
    avoid showing stale "running" forever while giving active workers time to
    report progress.
    """
    raw = os.environ.get("TINYASSETS_ORPHANED_RUN_GRACE_SECONDS", "3600")
    lowered = raw.strip().lower()
    if lowered in {"0", "off", "false", "no", "disabled"}:
        return None
    try:
        seconds = float(lowered)
    except ValueError:
        seconds = 3600.0
    if seconds <= 0:
        return None
    return max(60.0, seconds)


def _has_live_future(run_id: str) -> bool:
    try:
        future = get_future(run_id)
    except NameError:
        return False
    return future is not None and not future.done()


def _latest_run_progress_at(conn: sqlite3.Connection, run_id: str) -> float | None:
    row = conn.execute(
        """
        SELECT MAX(COALESCE(finished_at, started_at)) AS progress_at
        FROM run_events
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None or row["progress_at"] is None:
        return None
    try:
        return float(row["progress_at"])
    except (TypeError, ValueError):
        return None


def _mark_orphaned_run_if_needed(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    started_at: float | int | str | None,
    now: float | None = None,
) -> bool:
    if status not in (RUN_STATUS_QUEUED, RUN_STATUS_RUNNING):
        return False
    if _has_live_future(run_id):
        return False
    grace = _orphaned_run_grace_seconds()
    if grace is None:
        return False
    try:
        started = float(started_at) if started_at is not None else 0.0
    except (TypeError, ValueError):
        started = 0.0
    progress_at = _latest_run_progress_at(conn, run_id) or started
    if progress_at <= 0:
        return False
    checked_at = now or _now()
    stale_for = checked_at - progress_at
    if stale_for < grace:
        return False

    message = (
        "Run marked interrupted because no active background worker owns it "
        f"and no progress has been recorded for {int(stale_for)}s "
        f"(threshold {int(grace)}s). Rerun with the same inputs to continue."
    )
    cursor = conn.execute(
        """
        UPDATE runs
        SET status = ?, error = ?, finished_at = ?
        WHERE run_id = ? AND status IN (?, ?)
        """,
        (
            RUN_STATUS_INTERRUPTED,
            message,
            checked_at,
            run_id,
            RUN_STATUS_QUEUED,
            RUN_STATUS_RUNNING,
        ),
    )
    return cursor.rowcount > 0


def _recover_orphaned_runs_on_read(base_path: str | Path) -> int:
    """Mark stale in-flight rows as interrupted when no worker owns them.

    This complements startup recovery. Startup recovery handles rows that
    exist before a new run action initializes the executor. Read-time recovery
    handles the public-chatbot case where users keep polling after a restart
    but no new write action happens to trigger startup recovery.
    """
    initialize_runs_db(base_path)
    count = 0
    now = _now()
    with _connect(base_path) as conn:
        rows = conn.execute(
            """
            SELECT run_id, status, started_at FROM runs
            WHERE status IN (?, ?)
            """,
            (RUN_STATUS_QUEUED, RUN_STATUS_RUNNING),
        ).fetchall()
        for row in rows:
            if _mark_orphaned_run_if_needed(
                conn,
                run_id=row["run_id"],
                status=row["status"],
                started_at=row["started_at"],
                now=now,
            ):
                count += 1
    if count:
        logger.info("Recovered %d orphaned in-flight runs on read", count)
    return count


def initialize_runs_db(base_path: str | Path) -> Path:
    """Ensure runs, events, and Phase 4 judgment tables exist. Idempotent."""
    schema = """
    CREATE TABLE IF NOT EXISTS runs (
        run_id         TEXT PRIMARY KEY,
        branch_def_id  TEXT NOT NULL,
        run_name       TEXT NOT NULL DEFAULT '',
        thread_id      TEXT NOT NULL,
        status         TEXT NOT NULL DEFAULT 'queued',
        actor          TEXT NOT NULL DEFAULT 'anonymous',
        universe_id    TEXT NOT NULL DEFAULT '',
        owner_user_id  TEXT NOT NULL DEFAULT '',
        inputs_json    TEXT NOT NULL DEFAULT '{}',
        invocation_depth INTEGER NOT NULL DEFAULT 0,
        enqueue_context_json TEXT NOT NULL DEFAULT '{}',
        checkpoint_backend TEXT NOT NULL DEFAULT '',
        output_json    TEXT NOT NULL DEFAULT '{}',
        error          TEXT NOT NULL DEFAULT '',
        last_node_id   TEXT NOT NULL DEFAULT '',
        started_at     REAL NOT NULL,
        finished_at    REAL,
        provider_used  TEXT,
        model          TEXT,
        token_count    INTEGER,
        daemon_id      TEXT,
        runtime_instance_id TEXT,
        worker_id      TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_runs_branch ON runs(branch_def_id);
    CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

    CREATE TABLE IF NOT EXISTS run_events (
        run_id         TEXT NOT NULL,
        step_index     INTEGER NOT NULL,
        node_id        TEXT NOT NULL,
        status         TEXT NOT NULL,
        started_at     REAL NOT NULL,
        finished_at    REAL,
        detail_json    TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (run_id, step_index)
    );

    CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id);

    CREATE TABLE IF NOT EXISTS run_cancels (
        run_id         TEXT PRIMARY KEY,
        requested_at   REAL NOT NULL
    );

    -- Phase 4: eval + iteration hooks.

    CREATE TABLE IF NOT EXISTS run_judgments (
        judgment_id    TEXT PRIMARY KEY,
        run_id         TEXT NOT NULL,
        node_id        TEXT,
        text           TEXT NOT NULL,
        tags_json      TEXT NOT NULL DEFAULT '[]',
        author         TEXT NOT NULL,
        timestamp      TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_judgments_run
        ON run_judgments(run_id);
    CREATE INDEX IF NOT EXISTS idx_judgments_node
        ON run_judgments(node_id);

    CREATE TABLE IF NOT EXISTS run_lineage (
        run_id                    TEXT PRIMARY KEY,
        parent_run_id             TEXT,
        branch_def_id             TEXT NOT NULL,
        branch_version            INTEGER NOT NULL,
        edits_since_parent_json   TEXT NOT NULL DEFAULT '[]',
        timestamp                 TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_lineage_parent
        ON run_lineage(parent_run_id);
    CREATE INDEX IF NOT EXISTS idx_lineage_branch
        ON run_lineage(branch_def_id, branch_version);

    CREATE TABLE IF NOT EXISTS node_edit_audit (
        audit_id                    TEXT PRIMARY KEY,
        branch_def_id               TEXT NOT NULL,
        version_before              INTEGER NOT NULL,
        version_after               INTEGER NOT NULL,
        nodes_changed_json          TEXT NOT NULL,
        triggered_by_judgment_id    TEXT,
        timestamp                   TEXT NOT NULL,
        node_before_json            TEXT NOT NULL DEFAULT '{}',
        node_after_json             TEXT NOT NULL DEFAULT '{}',
        edit_kind                   TEXT NOT NULL DEFAULT 'update'
    );

    CREATE INDEX IF NOT EXISTS idx_audit_branch
        ON node_edit_audit(branch_def_id);

    CREATE TABLE IF NOT EXISTS teammate_messages (
        message_id     TEXT PRIMARY KEY,
        from_run_id    TEXT NOT NULL,
        to_node_id     TEXT NOT NULL,
        message_type   TEXT NOT NULL,
        body_json      TEXT NOT NULL DEFAULT '{}',
        reply_to_id    TEXT,
        sent_at        TEXT NOT NULL,
        acked          INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_tmsg_to_node
        ON teammate_messages(to_node_id, sent_at);
    CREATE INDEX IF NOT EXISTS idx_tmsg_from_run
        ON teammate_messages(from_run_id);

    CREATE TABLE IF NOT EXISTS run_child_attachments (
        attachment_id       TEXT PRIMARY KEY,
        parent_run_id       TEXT NOT NULL,
        child_run_id        TEXT NOT NULL,
        child_branch_def_id TEXT NOT NULL,
        output_digest       TEXT NOT NULL,
        evidence_handle     TEXT NOT NULL,
        attached_at         REAL NOT NULL,
        attachment_json     TEXT NOT NULL DEFAULT '{}',
        UNIQUE(parent_run_id, child_run_id)
    );

    CREATE INDEX IF NOT EXISTS idx_child_attachments_child
        ON run_child_attachments(child_run_id);

    CREATE TABLE IF NOT EXISTS run_receipts (
        receipt_id      TEXT PRIMARY KEY,
        run_id          TEXT NOT NULL,
        receipt_type    TEXT NOT NULL,
        subject_id      TEXT NOT NULL DEFAULT '',
        node_id         TEXT NOT NULL DEFAULT '',
        payload_json    TEXT NOT NULL DEFAULT '{}',
        created_at      REAL NOT NULL,
        -- The runs DB does not enable PRAGMA foreign_keys today, and runs
        -- are append-only. The explicit existence check in
        -- record_run_receipt is the load-bearing insert validation; this
        -- declaration is forward-compatible for future run deletion paths.
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_run_receipts_run
        ON run_receipts(run_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_run_receipts_type
        ON run_receipts(receipt_type, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_run_receipts_subject
        ON run_receipts(subject_id);
    """
    from tinyassets.branch_versions import BRANCH_VERSIONS_SCHEMA
    from tinyassets.contribution_events import (
        CONTRIBUTION_EVENTS_SCHEMA,
        migrate_contribution_events_schema,
    )
    from tinyassets.gate_events.schema import GATE_EVENT_SCHEMA
    from tinyassets.scheduler import SCHEDULER_SCHEMA
    schema = (
        schema
        + SCHEDULER_SCHEMA
        + BRANCH_VERSIONS_SCHEMA
        + GATE_EVENT_SCHEMA
        + CONTRIBUTION_EVENTS_SCHEMA
    )
    with _connect(base_path) as conn:
        conn.executescript(schema)
        # Migration: older installs may predate the body-snapshot columns
        # added for rollback support. SQLite doesn't have
        # ``ADD COLUMN IF NOT EXISTS``, so probe pragma and add on-demand.
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(node_edit_audit)")
        }
        for col, ddl in (
            ("node_before_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("node_after_json",  "TEXT NOT NULL DEFAULT '{}'"),
            ("edit_kind",        "TEXT NOT NULL DEFAULT 'update'"),
        ):
            if col not in existing:
                conn.execute(
                    f"ALTER TABLE node_edit_audit ADD COLUMN {col} {ddl}"
                )
        # Migration: add run instrumentation columns. Provider telemetry
        # landed first; executor identity fields are nullable observability.
        existing_runs = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(runs)")
        }
        for col, ddl in (
            ("provider_used", "TEXT"),
            ("model",         "TEXT"),
            ("token_count",   "INTEGER"),
            ("owner_user_id", "TEXT NOT NULL DEFAULT ''"),
            ("universe_id", "TEXT NOT NULL DEFAULT ''"),
            ("daemon_id",     "TEXT"),
            ("runtime_instance_id", "TEXT"),
            ("worker_id",     "TEXT"),
            ("invocation_depth", "INTEGER NOT NULL DEFAULT 0"),
            ("enqueue_context_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("checkpoint_backend", "TEXT NOT NULL DEFAULT ''"),
        ):
            if col not in existing_runs:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {ddl}")
        migrate_contribution_events_schema(conn)
        # Phase A item 6 (Task #65a) — branch_version_id on runs. NULL for
        # def-based runs (the existing path); populated only by
        # execute_branch_version_async for version-based runs. Required by
        # Task #48 contribution ledger + Task #53 route-back attribution.
        if "branch_version_id" not in existing_runs:
            conn.execute(
                "ALTER TABLE runs ADD COLUMN branch_version_id TEXT"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_branch_version "
            "ON runs(branch_version_id)"
        )
    return runs_db_path(base_path)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Run record shape
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@dataclass
class RunStepEvent:
    run_id: str
    step_index: int
    node_id: str
    status: str
    started_at: float
    finished_at: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "step_index": self.step_index,
            "node_id": self.node_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "detail": self.detail,
        }


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    col_names = set(row.keys())
    return {
        "run_id": row["run_id"],
        "branch_def_id": row["branch_def_id"],
        "run_name": row["run_name"],
        "thread_id": row["thread_id"],
        "status": row["status"],
        "actor": row["actor"],
        "universe_id": row["universe_id"] if "universe_id" in col_names else "",
        "owner_user_id": (
            row["owner_user_id"] if "owner_user_id" in col_names else ""
        ),
        "inputs": json.loads(row["inputs_json"] or "{}"),
        "invocation_depth": (
            int(row["invocation_depth"] or 0)
            if "invocation_depth" in col_names else 0
        ),
        "enqueue_context": json.loads(
            row["enqueue_context_json"] or "{}"
        ) if "enqueue_context_json" in col_names else {},
        "checkpoint_backend": (
            row["checkpoint_backend"]
            if "checkpoint_backend" in col_names
            else ""
        ),
        "output": json.loads(row["output_json"] or "{}"),
        "error": row["error"],
        "last_node_id": row["last_node_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "provider_used": row["provider_used"] if "provider_used" in col_names else None,
        "model": row["model"] if "model" in col_names else None,
        "token_count": row["token_count"] if "token_count" in col_names else None,
        "daemon_id": row["daemon_id"] if "daemon_id" in col_names else None,
        "runtime_instance_id": (
            row["runtime_instance_id"]
            if "runtime_instance_id" in col_names
            else None
        ),
        "worker_id": row["worker_id"] if "worker_id" in col_names else None,
    }


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    detail_raw = row["detail_json"] or "{}"
    try:
        detail = json.loads(detail_raw)
    except json.JSONDecodeError:
        detail = {}
    return {
        "step_index": row["step_index"],
        "node_id": row["node_id"],
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "detail": detail,
    }


VALID_RECEIPT_TYPES = frozenset({
    "source_acquisition_receipt",
    "claim_lineage_receipt",
    "revision_receipt",
})

_SOURCE_RECEIPT_FLAGS = (
    "fetched",
    "viewed",
    "verified",
    "snapshotted",
    "unavailable",
    "not_searched",
)

_DEFAULT_RECEIPT_PAYLOAD_MAX_BYTES = 65_536


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _receipt_payload_max_bytes() -> int:
    raw = os.environ.get(
        "TINYASSETS_RECEIPT_PAYLOAD_MAX_BYTES",
        str(_DEFAULT_RECEIPT_PAYLOAD_MAX_BYTES),
    )
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            "TINYASSETS_RECEIPT_PAYLOAD_MAX_BYTES must be an integer"
        ) from exc
    if value <= 0:
        raise ValueError("TINYASSETS_RECEIPT_PAYLOAD_MAX_BYTES must be positive")
    return value


def _receipt_payload_size_bytes(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            payload,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _as_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{field_name}[{idx}] must be a string")
        item = item.strip()
        if item:
            out.append(item)
    return out


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean")


def _normalize_receipt_payload(
    receipt_type: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Normalize known receipt fields while preserving extension metadata.

    Unknown payload keys outside the documented schema round-trip unchanged
    for forward compatibility. The substrate makes no claim about their
    meaning, type, or future canonical reservation; standards and domain
    packs that need their own schema should put custom material under an
    ``extensions`` object and validate it before recording the receipt.
    """
    if receipt_type not in VALID_RECEIPT_TYPES:
        raise ValueError(
            "receipt_type must be one of: "
            f"{', '.join(sorted(VALID_RECEIPT_TYPES))}"
        )
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    normalized = dict(payload)
    subject_id = ""

    if receipt_type == "source_acquisition_receipt":
        source_ref = str(
            normalized.get("source_ref")
            or normalized.get("source")
            or normalized.get("file_ref")
            or normalized.get("corpus_ref")
            or ""
        ).strip()
        if not source_ref:
            raise ValueError(
                "source_acquisition_receipt requires source_ref, source, "
                "file_ref, or corpus_ref"
            )
        normalized["source_ref"] = source_ref
        normalized.setdefault("retrieval_timestamp", _iso_now())
        normalized.setdefault("search_scope", "")
        normalized.setdefault("snapshot_hash", "")
        normalized.setdefault("rights_state", "")
        normalized.setdefault("access_state", "")
        for flag in _SOURCE_RECEIPT_FLAGS:
            normalized[flag] = _as_bool(normalized.get(flag, False), flag)
        acquired_flags = ("fetched", "viewed", "verified", "snapshotted")
        if normalized["not_searched"] and any(
            normalized[flag] for flag in acquired_flags
        ):
            raise ValueError(
                "not_searched cannot be combined with fetched, viewed, "
                "verified, or snapshotted"
            )
        if normalized["not_searched"] and normalized["unavailable"]:
            raise ValueError(
                "not_searched cannot be combined with unavailable"
            )
        if normalized["unavailable"] and any(
            normalized[flag] for flag in acquired_flags
        ):
            raise ValueError(
                "unavailable cannot be combined with fetched, viewed, "
                "verified, or snapshotted"
            )
        subject_id = source_ref

    elif receipt_type == "claim_lineage_receipt":
        claim_id = str(normalized.get("claim_id") or "").strip()
        if not claim_id:
            raise ValueError("claim_lineage_receipt requires claim_id")
        normalized["claim_id"] = claim_id
        normalized["evidence_refs"] = _as_string_list(
            normalized.get("evidence_refs"), "evidence_refs"
        )
        normalized["imported_prior_run_claims"] = _as_string_list(
            normalized.get("imported_prior_run_claims"),
            "imported_prior_run_claims",
        )
        normalized["counter_evidence_refs"] = _as_string_list(
            normalized.get("counter_evidence_refs"), "counter_evidence_refs"
        )
        normalized["changed_claims"] = _as_string_list(
            normalized.get("changed_claims"), "changed_claims"
        )
        normalized.setdefault("confidence", "")
        normalized.setdefault("status", "")
        normalized.setdefault("rationale", "")
        subject_id = claim_id

    elif receipt_type == "revision_receipt":
        old_run_id = str(normalized.get("old_run_id") or "").strip()
        old_claim_id = str(normalized.get("old_claim_id") or "").strip()
        if not old_run_id and not old_claim_id:
            raise ValueError(
                "revision_receipt requires old_run_id or old_claim_id"
            )
        normalized["old_run_id"] = old_run_id
        normalized["old_claim_id"] = old_claim_id
        normalized["new_evidence_refs"] = _as_string_list(
            normalized.get("new_evidence_refs"), "new_evidence_refs"
        )
        normalized["affected_outputs"] = _as_string_list(
            normalized.get("affected_outputs"), "affected_outputs"
        )
        normalized["recommended_reruns"] = _as_string_list(
            normalized.get("recommended_reruns"), "recommended_reruns"
        )
        normalized.setdefault("changed_status", "")
        normalized.setdefault("changed_confidence", "")
        normalized.setdefault("rationale", "")
        subject_id = old_claim_id or old_run_id

    payload_bytes = _receipt_payload_size_bytes(normalized)
    max_bytes = _receipt_payload_max_bytes()
    if payload_bytes > max_bytes:
        raise ValueError(
            f"payload exceeds max {max_bytes} bytes (got {payload_bytes})"
        )

    return normalized, subject_id


def _row_to_receipt(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "receipt_id": row["receipt_id"],
        "run_id": row["run_id"],
        "receipt_type": row["receipt_type"],
        "subject_id": row["subject_id"],
        "node_id": row["node_id"],
        "payload": payload,
        "created_at": row["created_at"],
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Persistence CRUD
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def create_run(
    base_path: str | Path,
    *,
    run_id: str | None = None,
    branch_def_id: str,
    thread_id: str,
    inputs: dict[str, Any],
    run_name: str = "",
    actor: str = "anonymous",
    universe_id: str = "",
    invocation_depth: int = 0,
    enqueue_context: "NodeEnqueueContext | None" = None,
    branch_version_id: str | None = None,
    owner_user_id: str | None = None,
    daemon_id: str | None = None,
    runtime_instance_id: str | None = None,
    worker_id: str | None = None,
    checkpoint_backend: str = "",
    _conn: sqlite3.Connection | None = None,
) -> str:
    if _conn is None:
        initialize_runs_db(base_path)
    resolved_run_id = (run_id or "").strip() or uuid.uuid4().hex[:16]
    resolved_owner_user_id = (
        str(owner_user_id or "")
        if owner_user_id is not None
        else _resolve_owner_user_id(base_path, daemon_id)
    )
    connection = (
        contextlib.nullcontext(_conn)
        if _conn is not None
        else _connect(base_path)
    )
    with connection as conn:
        conn.execute(
            """
            INSERT INTO runs (
                run_id, branch_def_id, run_name, thread_id,
                status, actor, universe_id, owner_user_id, inputs_json, started_at,
                invocation_depth, enqueue_context_json,
                checkpoint_backend,
                branch_version_id, daemon_id, runtime_instance_id,
                worker_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_run_id, branch_def_id, run_name, thread_id,
                RUN_STATUS_QUEUED, actor, (universe_id or "").strip(),
                resolved_owner_user_id,
                json.dumps(inputs, default=str), _now(),
                int(invocation_depth),
                json.dumps(
                    {
                        "universe_id": enqueue_context.universe_id,
                        "actor": enqueue_context.actor,
                        "parent_branch_task_id": enqueue_context.parent_branch_task_id,
                        "origin_branch_task_id": enqueue_context.origin_branch_task_id,
                    } if enqueue_context is not None else {}
                ),
                checkpoint_backend,
                branch_version_id,
                daemon_id,
                runtime_instance_id,
                worker_id,
            ),
        )
    return resolved_run_id


def update_run_status(
    base_path: str | Path,
    run_id: str,
    *,
    status: str | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    last_node_id: str | None = None,
    finished_at: float | None = None,
    provider_used: str | None = None,
    model: str | None = None,
    token_count: int | None = None,
) -> None:
    sets: list[str] = []
    params: list[Any] = []
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if output is not None:
        sets.append("output_json = ?")
        params.append(json.dumps(output, default=str))
    if error is not None:
        sets.append("error = ?")
        params.append(error)
    if last_node_id is not None:
        sets.append("last_node_id = ?")
        params.append(last_node_id)
    if finished_at is not None:
        sets.append("finished_at = ?")
        params.append(finished_at)
    if provider_used is not None:
        sets.append("provider_used = ?")
        params.append(provider_used)
    if model is not None:
        sets.append("model = ?")
        params.append(model)
    if token_count is not None:
        sets.append("token_count = ?")
        params.append(token_count)
    if not sets:
        return
    params.append(run_id)
    with _connect(base_path) as conn:
        conn.execute(
            f"UPDATE runs SET {', '.join(sets)} WHERE run_id = ?",
            params,
        )
        # Phase 2 emit-site (Task #72): on terminal status transition, emit
        # one execute_step contribution event for attribution. Wrapped in
        # try/except so emit failure (malformed metadata, table missing,
        # etc.) never blocks a status update — status is the load-bearing
        # semantic; emit is best-effort observability. Production observers
        # grep contribution_events._EMIT_FAILURES for non-zero.
        if status in _TERMINAL_STATUSES:
            try:
                row = conn.execute(
                    "SELECT actor, owner_user_id, daemon_id, "
                    "runtime_instance_id, worker_id, branch_def_id, "
                    "branch_version_id "
                    "FROM runs WHERE run_id = ?", (run_id,),
                ).fetchone()
                if row is not None:
                    artifact_id = row["branch_version_id"] or row["branch_def_id"]
                    # Skip emit when no artifact identifier is present —
                    # no attribution path = no event (per design discipline).
                    if artifact_id:
                        from tinyassets.contribution_events import (
                            record_contribution_event,
                        )
                        artifact_kind = (
                            "branch_version" if row["branch_version_id"]
                            else "branch_def"
                        )
                        record_contribution_event(
                            base_path,
                            event_id=f"execute_step:{run_id}:{status}",
                            event_type="execute_step",
                            actor_id=row["actor"] or "anonymous",
                            owner_user_id=row["owner_user_id"] or "",
                            daemon_id=row["daemon_id"] or "",
                            runtime_instance_id=row["runtime_instance_id"] or "",
                            worker_id=row["worker_id"] or "",
                            source_run_id=run_id,
                            source_artifact_id=artifact_id,
                            source_artifact_kind=artifact_kind,
                            weight=1.0,
                            occurred_at=_now(),
                            metadata_json=json.dumps({
                                "branch_def_id": row["branch_def_id"],
                                "branch_version_id": row["branch_version_id"],
                                "terminal_status": status,
                            }),
                            conn=conn,
                        )
            except Exception as exc:
                from tinyassets.contribution_events import _EMIT_FAILURES
                from tinyassets.contribution_events import _logger as _ce_logger
                _EMIT_FAILURES["count"] += 1
                _ce_logger.warning(
                    "execute_step emit failed for run %s (status=%s): %s; "
                    "status update preserved",
                    run_id, status, exc,
                )
            # Terminal-run cleanup: REVOKE this run's opaque workspace refs (Codex
            # S3 r20 #3) so a token captured from a finished / failed / cancelled
            # run can never be replayed. Best-effort — never blocks a status update.
            try:
                from tinyassets.sandbox_policy import release_run_workspace_refs
                release_run_workspace_refs(run_id)
            except Exception:  # noqa: BLE001 — cleanup is best-effort observability
                logger.debug("workspace-ref release failed for run %s", run_id)


def record_run_receipt(
    base_path: str | Path,
    *,
    run_id: str,
    receipt_type: str,
    payload: dict[str, Any],
    node_id: str = "",
    receipt_id: str | None = None,
) -> dict[str, Any]:
    """Persist a generic, machine-checkable receipt for a run.

    Receipts deliberately record acquisition/lineage/revision facts without
    assigning truth rank. Gates and later runs can inspect the normalized
    payload and decide how to use it. Insert-time run existence is checked
    explicitly here; the run_receipts foreign key is declarative until the
    runs DB enables SQLite foreign-key enforcement.
    """
    initialize_runs_db(base_path)
    run_id = run_id.strip()
    if not run_id:
        raise ValueError("run_id is required")

    normalized, subject_id = _normalize_receipt_payload(receipt_type, payload)
    receipt_id = receipt_id or uuid.uuid4().hex[:16]
    created_at = _now()

    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT run_id FROM runs WHERE run_id = ?", (run_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"run_id '{run_id}' not found")
        conn.execute(
            """
            INSERT INTO run_receipts (
                receipt_id, run_id, receipt_type, subject_id, node_id,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id,
                run_id,
                receipt_type,
                subject_id,
                node_id.strip(),
                json.dumps(normalized, default=str, sort_keys=True),
                created_at,
            ),
        )

    return {
        "receipt_id": receipt_id,
        "run_id": run_id,
        "receipt_type": receipt_type,
        "subject_id": subject_id,
        "node_id": node_id.strip(),
        "payload": normalized,
        "created_at": created_at,
    }


def list_run_receipts(
    base_path: str | Path,
    *,
    run_id: str = "",
    receipt_type: str = "",
    subject_id: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    initialize_runs_db(base_path)
    limit = min(max(1, int(limit)), 1000)
    clauses: list[str] = []
    params: list[Any] = []

    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id.strip())
    if receipt_type:
        if receipt_type not in VALID_RECEIPT_TYPES:
            raise ValueError(
                "receipt_type must be one of: "
                f"{', '.join(sorted(VALID_RECEIPT_TYPES))}"
            )
        clauses.append("receipt_type = ?")
        params.append(receipt_type)
    if subject_id:
        clauses.append("subject_id = ?")
        params.append(subject_id.strip())

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(base_path) as conn:
        rows = conn.execute(
            f"""
            SELECT receipt_id, run_id, receipt_type, subject_id, node_id,
                   payload_json, created_at
            FROM run_receipts
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return [_row_to_receipt(row) for row in rows]


def get_run(base_path: str | Path, run_id: str) -> dict[str, Any] | None:
    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        if _mark_orphaned_run_if_needed(
            conn,
            run_id=row["run_id"],
            status=row["status"],
            started_at=row["started_at"],
        ):
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
        result = _row_to_run(row)
        # Surface concurrency stats from the last concurrency_stats system event.
        stats_row = conn.execute(
            """
            SELECT detail_json FROM run_events
            WHERE run_id = ? AND status = 'concurrency_stats'
            ORDER BY step_index DESC LIMIT 1
            """,
            (run_id,),
        ).fetchone()
    if stats_row:
        try:
            result["concurrency"] = json.loads(stats_row["detail_json"] or "{}")
        except json.JSONDecodeError:
            result["concurrency"] = None
    else:
        result["concurrency"] = None
    return result


class ChildRunAttachmentError(ValueError):
    """Structured validation failure for attach_existing_child_run."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


_RECEIPT_WAITING_VALUES = frozenset({
    "attach_required",
    "blocked_before_child_attach",
    "receipt_waiting",
    "selected_attach_required",
    "waiting_for_child_receipt",
})


def _normalise_digest(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("sha256:"):
        return value
    if len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value):
        return f"sha256:{value.lower()}"
    return value


def _run_output_digest(output: dict[str, Any]) -> str:
    payload = json.dumps(
        output,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parent_is_receipt_waiting(output: dict[str, Any]) -> bool:
    if output.get("stable_evidence_handle"):
        return False
    for key in ("selected_child_status", "selected_branch_state", "automation_claim_status"):
        value = str(output.get(key, "")).strip().lower()
        if value in {
            "attached_completed",
            "child_attached_existing_receipt",
            "child_attached_with_handle",
        }:
            return False
    for key in (
        "parent_loop_status",
        "selected_child_status",
        "selected_branch_state",
        "automation_claim_status",
        "final_outcome_label",
    ):
        value = str(output.get(key, "")).strip().lower()
        if value in _RECEIPT_WAITING_VALUES:
            return True
        if value.endswith("_attach_required") or value.endswith("_receipt_waiting"):
            return True
    return False


def _selected_child_branch(parent_output: dict[str, Any]) -> str:
    return (
        str(parent_output.get("selected_child_branch_def_id") or "").strip()
        or str(parent_output.get("selected_loop_branch") or "").strip()
        or str(parent_output.get("child_branch_def_id") or "").strip()
    )


def attach_existing_child_run(
    base_path: str | Path,
    *,
    parent_run_id: str,
    child_run_id: str,
    child_branch_def_id: str = "",
    output_digest: str = "",
    actor: str = "anonymous",
) -> dict[str, Any]:
    """Validate and attach a completed child run receipt to a waiting parent.

    This is intentionally a receipt primitive. It only records provenance for
    an already-finished child.
    """
    initialize_runs_db(base_path)
    parent_run_id = parent_run_id.strip()
    child_run_id = child_run_id.strip()
    if not parent_run_id:
        raise ChildRunAttachmentError(
            "parent_run_id_required",
            "parent run_id is required.",
        )
    if not child_run_id:
        raise ChildRunAttachmentError(
            "child_run_id_required",
            "child_run_id is required.",
        )

    parent = get_run(base_path, parent_run_id)
    if parent is None:
        raise ChildRunAttachmentError(
            "parent_not_found",
            f"Parent run '{parent_run_id}' not found.",
            {"parent_run_id": parent_run_id},
        )
    child = get_run(base_path, child_run_id)
    if child is None:
        raise ChildRunAttachmentError(
            "child_not_found",
            f"Child run '{child_run_id}' not found.",
            {"child_run_id": child_run_id},
        )

    parent_output = copy.deepcopy(parent.get("output") or {})
    if not _parent_is_receipt_waiting(parent_output):
        raise ChildRunAttachmentError(
            "parent_not_receipt_waiting",
            "Parent run is not in a receipt-waiting state.",
            {
                "parent_run_id": parent_run_id,
                "parent_loop_status": parent_output.get("parent_loop_status", ""),
                "selected_child_status": parent_output.get("selected_child_status", ""),
            },
        )

    supplied_child_branch = child_branch_def_id.strip()
    expected_child_branch = _selected_child_branch(parent_output) or supplied_child_branch
    if not expected_child_branch:
        raise ChildRunAttachmentError(
            "child_branch_required",
            "child_branch_def_id is required when parent output has no selected child branch.",
            {"parent_run_id": parent_run_id},
        )
    actual_child_branch = str(child.get("branch_def_id") or "")
    if supplied_child_branch and supplied_child_branch != expected_child_branch:
        raise ChildRunAttachmentError(
            "child_branch_mismatch",
            "Supplied child branch does not match the parent selected child branch.",
            {
                "child_run_id": child_run_id,
                "expected_child_branch_def_id": expected_child_branch,
                "supplied_child_branch_def_id": supplied_child_branch,
                "actual_child_branch_def_id": actual_child_branch,
            },
        )
    if actual_child_branch != expected_child_branch:
        raise ChildRunAttachmentError(
            "child_branch_mismatch",
            "Child run branch does not match the selected child branch.",
            {
                "child_run_id": child_run_id,
                "expected_child_branch_def_id": expected_child_branch,
                "actual_child_branch_def_id": actual_child_branch,
            },
        )

    child_status = str(child.get("status") or "")
    if child_status != RUN_STATUS_COMPLETED:
        raise ChildRunAttachmentError(
            "child_not_completed",
            "Child run must be completed before it can be attached.",
            {"child_run_id": child_run_id, "child_status": child_status},
        )

    child_output = copy.deepcopy(child.get("output") or {})
    if not child_output:
        raise ChildRunAttachmentError(
            "child_output_missing",
            "Child run completed but has no output to attach.",
            {"child_run_id": child_run_id},
        )

    computed_digest = _run_output_digest(child_output)
    supplied_digest = _normalise_digest(output_digest)
    if supplied_digest and supplied_digest != computed_digest:
        raise ChildRunAttachmentError(
            "output_digest_mismatch",
            "Supplied child output digest does not match the stored child output.",
            {
                "child_run_id": child_run_id,
                "supplied_output_digest": supplied_digest,
                "computed_output_digest": computed_digest,
            },
        )

    digest_suffix = computed_digest.split(":", 1)[1][:16]
    evidence_handle = f"run-attachment:{parent_run_id}:{child_run_id}:{digest_suffix}"
    attachment_id = f"{parent_run_id}:{child_run_id}"
    attached_at = _now()
    receipt = {
        "attachment_id": attachment_id,
        "parent_run_id": parent_run_id,
        "child_run_id": child_run_id,
        "child_branch_def_id": actual_child_branch,
        "output_digest": computed_digest,
        "evidence_handle": evidence_handle,
        "attached_at": attached_at,
        "attached_by": actor,
        "provenance": "attached_existing_child",
        "automation_claim_status": "child_attached_with_handle",
    }

    with _connect(base_path) as conn:
        existing_child = conn.execute(
            """
            SELECT output_digest, evidence_handle FROM run_child_attachments
            WHERE child_run_id = ?
            LIMIT 1
            """,
            (child_run_id,),
        ).fetchone()
        if existing_child and existing_child["output_digest"] != computed_digest:
            raise ChildRunAttachmentError(
                "conflicting_child_digest",
                "Child run was already attached with a different output digest.",
                {
                    "child_run_id": child_run_id,
                    "existing_output_digest": existing_child["output_digest"],
                    "computed_output_digest": computed_digest,
                },
            )

        existing_pair = conn.execute(
            """
            SELECT output_digest, evidence_handle FROM run_child_attachments
            WHERE parent_run_id = ? AND child_run_id = ?
            """,
            (parent_run_id, child_run_id),
        ).fetchone()
        if existing_pair and existing_pair["output_digest"] != computed_digest:
            raise ChildRunAttachmentError(
                "conflicting_child_digest",
                "Child run was already attached to this parent with a different digest.",
                {
                    "parent_run_id": parent_run_id,
                    "child_run_id": child_run_id,
                    "existing_output_digest": existing_pair["output_digest"],
                    "computed_output_digest": computed_digest,
                },
            )
        if not existing_pair:
            conn.execute(
                """
                INSERT OR IGNORE INTO run_child_attachments (
                    attachment_id, parent_run_id, child_run_id,
                    child_branch_def_id, output_digest, evidence_handle,
                    attached_at, attachment_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    parent_run_id,
                    child_run_id,
                    actual_child_branch,
                    computed_digest,
                    evidence_handle,
                    attached_at,
                    json.dumps(receipt, sort_keys=True, default=str),
                ),
            )
            existing_pair = conn.execute(
                """
                SELECT output_digest, evidence_handle FROM run_child_attachments
                WHERE parent_run_id = ? AND child_run_id = ?
                """,
                (parent_run_id, child_run_id),
            ).fetchone()
        if existing_pair is None:
            raise ChildRunAttachmentError(
                "attachment_record_missing",
                "Child attachment record could not be written.",
                {"parent_run_id": parent_run_id, "child_run_id": child_run_id},
            )
        if existing_pair["output_digest"] != computed_digest:
            raise ChildRunAttachmentError(
                "conflicting_child_digest",
                "Child run was already attached to this parent with a different digest.",
                {
                    "parent_run_id": parent_run_id,
                    "child_run_id": child_run_id,
                    "existing_output_digest": existing_pair["output_digest"],
                    "computed_output_digest": computed_digest,
                },
            )
        evidence_handle = existing_pair["evidence_handle"]
        receipt["evidence_handle"] = evidence_handle

    parent_output.update({
        "selected_child_status": "attached_completed",
        "selected_branch_state": "child_attached_existing_receipt",
        "automation_claim_status": "child_attached_with_handle",
        "stable_evidence_handle": evidence_handle,
        "attached_child_run_id": child_run_id,
        "attached_child_branch_def_id": actual_child_branch,
        "attached_child_output_digest": computed_digest,
        "attached_child_output": child_output,
        "attached_child_receipt": receipt,
        "blocked_execution_record": {},
    })
    if "keep_reject_decision" in child_output:
        parent_output["attached_child_decision"] = child_output["keep_reject_decision"]

    update_run_status(base_path, parent_run_id, output=parent_output)
    return {
        "status": "attached",
        "parent_run_id": parent_run_id,
        "child_run_id": child_run_id,
        "child_branch_def_id": actual_child_branch,
        "selected_child_status": "attached_completed",
        "automation_claim_status": "child_attached_with_handle",
        "stable_evidence_handle": evidence_handle,
        "output_digest": computed_digest,
        "attached_child_output": child_output,
        "receipt": receipt,
    }


def list_runs(
    base_path: str | Path,
    *,
    branch_def_id: str = "",
    status: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    initialize_runs_db(base_path)
    _recover_orphaned_runs_on_read(base_path)
    clauses: list[str] = []
    params: list[Any] = []
    if branch_def_id:
        clauses.append("branch_def_id = ?")
        params.append(branch_def_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(base_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM runs {where} "
            f"ORDER BY started_at DESC LIMIT ?",
            (*params, max(1, int(limit))),
        ).fetchall()
    return [_row_to_run(r) for r in rows]


def latest_run_by_name(
    base_path: str | Path,
    *,
    run_name: str,
    branch_def_id: str = "",
) -> dict[str, Any] | None:
    """Return the newest run with ``run_name``.

    Daemon BranchTasks use deterministic run names. Looking them up lets
    restart recovery distinguish "task was requeued after a crash" from
    "the branch never produced a durable run".
    """
    initialize_runs_db(base_path)
    clauses = ["run_name = ?"]
    params: list[Any] = [run_name]
    if branch_def_id:
        clauses.append("branch_def_id = ?")
        params.append(branch_def_id)
    where = " AND ".join(clauses)
    with _connect(base_path) as conn:
        row = conn.execute(
            f"""
            SELECT * FROM runs
            WHERE {where}
            ORDER BY started_at DESC LIMIT 1
            """,
            params,
        ).fetchone()
    return _row_to_run(row) if row is not None else None


def record_event(
    base_path: str | Path,
    event: RunStepEvent,
    *,
    _conn: sqlite3.Connection | None = None,
) -> None:
    connection = (
        contextlib.nullcontext(_conn)
        if _conn is not None
        else _connect(base_path)
    )
    with connection as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO run_events (
                run_id, step_index, node_id, status,
                started_at, finished_at, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.run_id, event.step_index, event.node_id,
                event.status, event.started_at, event.finished_at,
                json.dumps(event.detail, default=str),
            ),
        )


def list_events(
    base_path: str | Path,
    run_id: str,
    *,
    since_step: int = -1,
) -> list[dict[str, Any]]:
    """Return events with ``step_index > since_step``, ascending.

    ``step_index`` is an opaque, monotonically-increasing cursor — NOT
    a node-count ordinal. One node can emit multiple events (started,
    ran, timeout, etc.) each with its own step_index, so cursor
    arithmetic ("I have N events, skip to step N") is incorrect.
    Always pass the last-seen step_index back as ``since_step``.
    """
    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM run_events
            WHERE run_id = ? AND step_index > ?
            ORDER BY step_index ASC
            """,
            (run_id, int(since_step)),
        ).fetchall()
    return [_row_to_event(r) for r in rows]


# Terminal run statuses end a long-poll immediately regardless of
# whether new events have landed. Callers don't need to wait the full
# max_wait_s once the run has resolved.
_TERMINAL_STATUSES = frozenset({
    "completed", "failed", "cancelled", "interrupted",
})


def await_run_events(
    base_path: str | Path,
    run_id: str,
    *,
    since_step: int = -1,
    max_wait_s: float = 60.0,
    poll_interval_s: float = 0.25,
) -> dict[str, Any]:
    """Long-poll for new run events. Block up to ``max_wait_s`` (#65).

    Returns as soon as any of:
    - a new event lands with ``step_index > since_step``
    - the run reaches a terminal status (completed/failed/cancelled)
    - the deadline elapses

    Returns ``{"events": [...], "status": "...", "next_cursor": N,
    "waited_s": float, "reason": "events|terminal|timeout"}``. The
    caller uses ``next_cursor`` as the next ``since_step``.

    ``step_index`` (and therefore ``next_cursor``) is an opaque,
    monotonically-increasing cursor — NOT a node-count ordinal. A
    single node may emit several events, each with its own
    step_index, so do not treat it as "number of nodes completed".
    """
    deadline = time.monotonic() + max(0.0, float(max_wait_s))
    poll_interval = max(0.05, float(poll_interval_s))
    started = time.monotonic()
    while True:
        events = list_events(base_path, run_id, since_step=since_step)
        record = get_run(base_path, run_id)
        status = (record or {}).get("status", "unknown")
        if events:
            reason = "events"
            break
        if status in _TERMINAL_STATUSES:
            reason = "terminal"
            break
        if time.monotonic() >= deadline:
            reason = "timeout"
            break
        time.sleep(poll_interval)

    next_cursor = max(
        (e.get("step_index", since_step) for e in events),
        default=since_step,
    )
    return {
        "events": events,
        "status": status,
        "next_cursor": next_cursor,
        "waited_s": round(time.monotonic() - started, 3),
        "reason": reason,
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Phase 4: judgments, lineage, node edit audit
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _iso_now() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def add_judgment(
    base_path: str | Path,
    *,
    run_id: str,
    text: str,
    node_id: str | None = None,
    tags: list[str] | None = None,
    author: str = "anonymous",
) -> dict[str, Any]:
    """Persist a user's natural-language judgment of a run or node.

    Returns the stored dict (useful for response composition).
    """
    initialize_runs_db(base_path)
    judgment_id = uuid.uuid4().hex[:16]
    ts = _iso_now()
    with _connect(base_path) as conn:
        conn.execute(
            """
            INSERT INTO run_judgments (
                judgment_id, run_id, node_id, text,
                tags_json, author, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                judgment_id, run_id, node_id, text,
                json.dumps(list(tags or []), default=str),
                author, ts,
            ),
        )
    return {
        "judgment_id": judgment_id,
        "run_id": run_id,
        "node_id": node_id,
        "text": text,
        "tags": list(tags or []),
        "author": author,
        "timestamp": ts,
    }


def list_judgments(
    base_path: str | Path,
    *,
    branch_def_id: str = "",
    run_id: str = "",
    node_id: str = "",
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return judgments filtered by branch / run / node. At least one
    filter must be set to avoid accidental full-table scans — callers
    that want everything should pass a branch_def_id."""
    initialize_runs_db(base_path)
    if not (branch_def_id or run_id or node_id):
        return []

    clauses: list[str] = []
    params: list[Any] = []
    if run_id:
        clauses.append("j.run_id = ?")
        params.append(run_id)
    if node_id:
        clauses.append("j.node_id = ?")
        params.append(node_id)
    if branch_def_id:
        # Join through runs to scope by branch.
        clauses.append(
            "j.run_id IN (SELECT run_id FROM runs WHERE branch_def_id = ?)"
        )
        params.append(branch_def_id)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(base_path) as conn:
        rows = conn.execute(
            f"""
            SELECT j.judgment_id, j.run_id, j.node_id, j.text,
                   j.tags_json, j.author, j.timestamp
            FROM run_judgments j
            {where}
            ORDER BY j.timestamp DESC
            LIMIT ?
            """,
            (*params, max(1, int(limit))),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for r in rows:
        try:
            tags = json.loads(r["tags_json"] or "[]")
        except json.JSONDecodeError:
            tags = []
        result.append({
            "judgment_id": r["judgment_id"],
            "run_id": r["run_id"],
            "node_id": r["node_id"],
            "text": r["text"],
            "tags": tags,
            "author": r["author"],
            "timestamp": r["timestamp"],
        })
    return result


def record_lineage(
    base_path: str | Path,
    *,
    run_id: str,
    parent_run_id: str | None,
    branch_def_id: str,
    branch_version: int,
    edits_since_parent: list[str] | None = None,
    _conn: sqlite3.Connection | None = None,
) -> None:
    """Store a lineage row at run start. ``parent_run_id`` is resolved by
    the caller (usually: most recent terminal run on the same branch by
    the same actor)."""
    if _conn is None:
        initialize_runs_db(base_path)
    connection = (
        contextlib.nullcontext(_conn)
        if _conn is not None
        else _connect(base_path)
    )
    with connection as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO run_lineage (
                run_id, parent_run_id, branch_def_id, branch_version,
                edits_since_parent_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, parent_run_id, branch_def_id, int(branch_version),
                json.dumps(list(edits_since_parent or []), default=str),
                _iso_now(),
            ),
        )


def get_lineage(base_path: str | Path, run_id: str) -> dict[str, Any] | None:
    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM run_lineage WHERE run_id = ?", (run_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        edits = json.loads(row["edits_since_parent_json"] or "[]")
    except json.JSONDecodeError:
        edits = []
    return {
        "run_id": row["run_id"],
        "parent_run_id": row["parent_run_id"],
        "branch_def_id": row["branch_def_id"],
        "branch_version": row["branch_version"],
        "edits_since_parent": edits,
        "timestamp": row["timestamp"],
    }


def latest_terminal_run(
    base_path: str | Path,
    *,
    branch_def_id: str,
    actor: str = "",
) -> str | None:
    """Find the most recent terminal run on this branch (optionally by
    actor) to use as ``parent_run_id`` for a new run."""
    initialize_runs_db(base_path)
    clauses = [
        "branch_def_id = ?",
        "status IN (?, ?, ?, ?)",
    ]
    params: list[Any] = [
        branch_def_id,
        RUN_STATUS_COMPLETED, RUN_STATUS_FAILED,
        RUN_STATUS_CANCELLED, RUN_STATUS_INTERRUPTED,
    ]
    if actor:
        clauses.append("actor = ?")
        params.append(actor)
    where = " AND ".join(clauses)
    with _connect(base_path) as conn:
        row = conn.execute(
            f"""
            SELECT run_id FROM runs
            WHERE {where}
            ORDER BY started_at DESC LIMIT 1
            """,
            params,
        ).fetchone()
    return row["run_id"] if row else None


def record_node_edit_audit(
    base_path: str | Path,
    *,
    branch_def_id: str,
    version_before: int,
    version_after: int,
    nodes_changed: list[str],
    triggered_by_judgment_id: str | None = None,
    node_before: dict[str, Any] | None = None,
    node_after: dict[str, Any] | None = None,
    edit_kind: str = "update",
) -> str:
    """Persist a NodeEditAudit row when a branch is edited.

    ``node_before`` / ``node_after`` are full serialized NodeDefinition
    dicts. Snapshotting the bodies means rollback can restore the exact
    previous state without re-synthesising it. ``edit_kind`` is either
    ``"update"`` (normal edit via update_node) or ``"rollback"`` (edit
    via rollback_node) so clients can distinguish forward-progress edits
    from rewinds. Returns the audit_id.
    """
    initialize_runs_db(base_path)
    audit_id = uuid.uuid4().hex[:16]
    with _connect(base_path) as conn:
        conn.execute(
            """
            INSERT INTO node_edit_audit (
                audit_id, branch_def_id, version_before, version_after,
                nodes_changed_json, triggered_by_judgment_id, timestamp,
                node_before_json, node_after_json, edit_kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id, branch_def_id,
                int(version_before), int(version_after),
                json.dumps(list(nodes_changed), default=str),
                triggered_by_judgment_id, _iso_now(),
                json.dumps(node_before or {}, default=str),
                json.dumps(node_after or {}, default=str),
                edit_kind,
            ),
        )
    return audit_id


def _audit_row_to_dict(r: sqlite3.Row) -> dict[str, Any]:
    try:
        changed = json.loads(r["nodes_changed_json"] or "[]")
    except json.JSONDecodeError:
        changed = []
    try:
        before = json.loads(r["node_before_json"] or "{}")
    except json.JSONDecodeError:
        before = {}
    try:
        after = json.loads(r["node_after_json"] or "{}")
    except json.JSONDecodeError:
        after = {}
    return {
        "audit_id": r["audit_id"],
        "branch_def_id": r["branch_def_id"],
        "version_before": r["version_before"],
        "version_after": r["version_after"],
        "nodes_changed": changed,
        "triggered_by_judgment_id": r["triggered_by_judgment_id"],
        "timestamp": r["timestamp"],
        "node_before": before,
        "node_after": after,
        "edit_kind": (
            r["edit_kind"] if "edit_kind" in r.keys() else "update"
        ),
    }


def list_node_edit_audits(
    base_path: str | Path,
    *,
    branch_def_id: str,
    node_id: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return audit rows for a branch, optionally narrowed to a single
    node. Rows are sorted newest-first. The ``node_id`` filter uses JSON
    containment against ``nodes_changed_json`` (``update_node`` writes
    single-element lists, so equality is the common case)."""
    initialize_runs_db(base_path)
    clauses: list[str] = ["branch_def_id = ?"]
    params: list[Any] = [branch_def_id]
    if node_id:
        # nodes_changed_json stores a JSON list. Exact-match tests for
        # a single-element list as well as containment for multi-node
        # edits (future when patch_branch learns to emit audits).
        clauses.append(
            "(nodes_changed_json = ? OR nodes_changed_json LIKE ?)"
        )
        params.append(json.dumps([node_id]))
        params.append(f'%"{node_id}"%')
    where = " AND ".join(clauses)
    with _connect(base_path) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM node_edit_audit
            WHERE {where}
            ORDER BY timestamp DESC LIMIT ?
            """,
            (*params, max(1, int(limit))),
        ).fetchall()
    return [_audit_row_to_dict(r) for r in rows]


def find_node_snapshot(
    base_path: str | Path,
    *,
    branch_def_id: str,
    node_id: str,
    at_version: int,
) -> dict[str, Any] | None:
    """Locate the node body as it existed at a specific branch version.

    Strategy: the audit row whose ``version_after`` equals ``at_version``
    captures the node's ``node_after`` — that's the body at that version.
    When no row matches (e.g. the target is version 1, never edited), we
    fall back to the oldest audit row's ``node_before``.
    """
    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        exact = conn.execute(
            """
            SELECT * FROM node_edit_audit
            WHERE branch_def_id = ?
              AND version_after = ?
              AND (nodes_changed_json = ? OR nodes_changed_json LIKE ?)
            ORDER BY timestamp DESC LIMIT 1
            """,
            (
                branch_def_id, int(at_version),
                json.dumps([node_id]), f'%"{node_id}"%',
            ),
        ).fetchone()
        if exact is not None:
            return _audit_row_to_dict(exact).get("node_after") or None

        oldest = conn.execute(
            """
            SELECT * FROM node_edit_audit
            WHERE branch_def_id = ?
              AND version_before = ?
              AND (nodes_changed_json = ? OR nodes_changed_json LIKE ?)
            ORDER BY timestamp ASC LIMIT 1
            """,
            (
                branch_def_id, int(at_version),
                json.dumps([node_id]), f'%"{node_id}"%',
            ),
        ).fetchone()
        if oldest is not None:
            return _audit_row_to_dict(oldest).get("node_before") or None
    return None


def node_output_from_run(
    base_path: str | Path,
    *,
    run_id: str,
    node_id: str,
) -> dict[str, Any] | None:
    """Return the output snapshot event for a specific (run_id, node_id).

    Phase 4 judgments target specific nodes, so users need the per-node
    output to judge on, not just final state.
    """
    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM run_events
            WHERE run_id = ? AND node_id = ? AND status = ?
            ORDER BY step_index DESC LIMIT 1
            """,
            (run_id, node_id, NODE_STATUS_RAN),
        ).fetchone()
    if row is None:
        return None
    detail_raw = row["detail_json"] or "{}"
    try:
        detail = json.loads(detail_raw)
    except json.JSONDecodeError:
        detail = {}
    return {
        "run_id": run_id,
        "node_id": node_id,
        "step_index": row["step_index"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "detail": detail,
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Cooperative cancel
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def request_cancel(base_path: str | Path, run_id: str) -> bool:
    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO run_cancels (run_id, requested_at) "
            "VALUES (?, ?)",
            (run_id, _now()),
        )
    return True


def is_cancel_requested(base_path: str | Path, run_id: str) -> bool:
    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM run_cancels WHERE run_id = ?", (run_id,)
        ).fetchone()
    return row is not None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Synchronous runner
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@dataclass
class ChildFailure:
    """Structured failure info for a sub-branch invocation that didn't complete.

    Phase A item 5 / Task #76b. Embedded in :class:`RunOutcome.child_failures`
    when a parent run's invoke_branch / invoke_branch_version step encounters
    a non-completed child terminal status. The downstream graph (and Task #48
    contribution ledger's ``caused_regression`` emit) reads these to decide
    whether to propagate, default, or retry — see ``on_child_fail`` policy
    in the spec.
    """

    run_id: str
    failure_class: str  # 'child_failed' | 'child_timeout' | 'child_cancelled' | 'child_unknown'
    child_status: str  # the child's terminal RUN_STATUS_*
    partial_output: dict[str, Any] | None = None


class ChildRunAwaitTimeout(TimeoutError):
    """Raised when an awaited child run is still non-terminal at the ceiling."""

    def __init__(
        self,
        message: str,
        *,
        run_id: str,
        child_status: str,
        child_branch_def_id: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.child_status = child_status
        self.child_branch_def_id = child_branch_def_id
        self.timeout_seconds = timeout_seconds


@dataclass
class RunOutcome:
    run_id: str
    status: str
    output: dict[str, Any]
    error: str = ""
    # Phase A item 5 / Task #76b — populated when a parent run's
    # invoke_branch / invoke_branch_version step sees a non-completed child
    # terminal status. Default empty list keeps existing callers untouched
    # (no behavior change for runs without sub-branch invocations).
    child_failures: list[ChildFailure] = field(default_factory=list)


def _graph_node_order(branch: BranchDefinition) -> list[str]:
    return [gn.id for gn in branch.graph_nodes]


def _nodes_reachable_from(branch: BranchDefinition, start_node: str) -> set[str]:
    if not start_node:
        return set(_graph_node_order(branch))
    adjacency: dict[str, set[str]] = {}
    for edge in branch.edges:
        source = str(edge.from_node or "")
        target = str(edge.to_node or "")
        if source and target and target != "END":
            adjacency.setdefault(source, set()).add(target)
    for edge in branch.conditional_edges:
        source = str(edge.from_node or "")
        for target_value in edge.conditions.values():
            target = str(target_value or "")
            if source and target and target != "END":
                adjacency.setdefault(source, set()).add(target)
    reachable: set[str] = set()
    frontier = [start_node]
    while frontier:
        node_id = frontier.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        frontier.extend(adjacency.get(node_id, ()))
    return reachable


def _prepare_run(
    base_path: str | Path,
    *,
    run_id: str | None = None,
    branch: BranchDefinition,
    inputs: dict[str, Any],
    run_name: str,
    actor: str,
    universe_id: str = "",
    invocation_depth: int = 0,
    enqueue_context: "NodeEnqueueContext | None" = None,
    branch_version_id: str | None = None,
    daemon_id: str | None = None,
    runtime_instance_id: str | None = None,
    worker_id: str | None = None,
    owner_user_id: str | None = None,
    lineage_parent_run_id: str = "",
    start_node: str = "",
) -> str:
    """Write the run row + pending-node events + lineage synchronously.

    Returns the ``run_id``. Fast (~a few ms); safe to call from the MCP
    handler before handing off to a background executor.

    ``branch_version_id`` is populated only for version-based runs
    (Phase A item 6, Task #65). Def-based runs leave it as None.
    """
    initialize_runs_db(base_path)
    from tinyassets.branch_bindings import declared_binding_fields

    checkpoint_backend = (
        "memory"
        if declared_binding_fields(getattr(branch, "state_schema", None))
        else "sqlite"
    )
    # Phase 4: record lineage so `compare_runs` and "what changed since
    # the last run" work. Parent is the most recent terminal run on this
    # branch by the same actor (best-effort — falls back to branch-wide
    # latest if no same-actor match).
    parent = (lineage_parent_run_id or "").strip() or None
    if parent is None:
        parent = latest_terminal_run(
            base_path, branch_def_id=branch.branch_def_id, actor=actor,
        )
        if parent is None:
            parent = latest_terminal_run(
                base_path, branch_def_id=branch.branch_def_id,
            )
    branch_version = int(getattr(branch, "version", 1) or 1)
    edits_since_parent: list[str] = []
    if parent is not None:
        parent_lineage = get_lineage(base_path, parent)
        if parent_lineage and parent_lineage["branch_version"] != branch_version:
            # Best-effort: enumerate audit rows between the versions for
            # a summary of what changed between runs.
            try:
                audits = list_node_edit_audits(
                    base_path, branch_def_id=branch.branch_def_id, limit=100,
                )
                for a in audits:
                    if (
                        a["version_before"] >= parent_lineage["branch_version"]
                        and a["version_after"] <= branch_version
                    ):
                        edits_since_parent.extend(a.get("nodes_changed", []))
            except Exception:
                logger.exception("lineage edit summary failed for %s", run_id)

    # A caller-supplied deterministic run_id is the revision idempotency key.
    # Commit its row, initial event timeline, and lineage as one unit so a crash
    # cannot leave a winner that replay mistakes for a fully prepared run.
    with _connect(base_path) as conn:
        run_id = create_run(
            base_path,
            run_id=run_id,
            branch_def_id=branch.branch_def_id,
            thread_id="",
            inputs=inputs,
            run_name=run_name,
            actor=actor,
            universe_id=universe_id,
            invocation_depth=invocation_depth,
            enqueue_context=enqueue_context,
            branch_version_id=branch_version_id,
            owner_user_id=owner_user_id,
            daemon_id=daemon_id,
            runtime_instance_id=runtime_instance_id,
            worker_id=worker_id,
            checkpoint_backend=checkpoint_backend,
            _conn=conn,
        )
        conn.execute(
            "UPDATE runs SET thread_id = ? WHERE run_id = ?",
            (run_id, run_id),
        )
        reachable_nodes = _nodes_reachable_from(branch, start_node)
        for step, node_id in enumerate(_graph_node_order(branch)):
            record_event(
                base_path,
                RunStepEvent(
                    run_id=run_id,
                    step_index=step,
                    node_id=node_id,
                    status=(
                        NODE_STATUS_PENDING
                        if node_id in reachable_nodes
                        else NODE_STATUS_SKIPPED
                    ),
                    started_at=_now(),
                ),
                _conn=conn,
            )
        record_lineage(
            base_path,
            run_id=run_id,
            parent_run_id=parent,
            branch_def_id=branch.branch_def_id,
            branch_version=branch_version,
            edits_since_parent=edits_since_parent,
            _conn=conn,
        )
    return run_id


#: Default LangGraph recursion-limit ceiling, raised from LangGraph's
#: stock 25 → 100 per the Tier-1 investigation Step 6 (BUG-019/021/022).
#: Stock 25 is too tight for branches with 3+ gate iterations; BUG-020
#: runs tripped the limit. Callers can override via the explicit
#: `recursion_limit_override` arg on execute_branch / execute_branch_async.
DEFAULT_RECURSION_LIMIT = 100


def _execution_blocked_reason(universe_dir: Path | None) -> str | None:
    """Thin wrapper over :func:`tinyassets.engine_binding.execution_blocked_reason` —
    THE single fail-closed gate. Any resolution error keeps the run BLOCKED (round-22
    #2: never fail open on unreadable credential state)."""
    if universe_dir is None:
        return None
    try:
        from tinyassets.engine_binding import execution_blocked_reason

        return execution_blocked_reason(universe_dir)
    except Exception as exc:  # noqa: BLE001 — cannot evaluate the gate → fail closed.
        return f"credential-state gate could not be evaluated ({exc}) — fail closed."


def _default_execution_scope(
    base_path: str | Path,
    universe_id: str,
) -> "ExecutionScope":
    """Resolve an explicit universe id to the shared S3/S5 scope contract."""
    from tinyassets.sandbox_policy import ExecutionScope

    uid = (universe_id or "").strip()
    if not uid:
        return ExecutionScope.legacy_unbound()
    root = Path(base_path).resolve()
    try:
        universe_dir = (root / uid).resolve()
        if not universe_dir.is_relative_to(root) or not universe_dir.is_dir():
            return ExecutionScope.unknown()
    except (OSError, RuntimeError, ValueError):
        return ExecutionScope.unknown()
    return ExecutionScope.bound(universe_dir)


def _execution_scope_for_run(
    base_path: str | Path,
    run_id: str,
) -> "ExecutionScope":
    """Load the persisted scope; actor parsing is only a migration bridge."""
    from tinyassets.sandbox_policy import ExecutionScope

    run = get_run(base_path, run_id)
    if run is None:
        return ExecutionScope.unknown()
    universe_id = str(run.get("universe_id") or "").strip()
    if not universe_id:
        actor = str(run.get("actor") or "")
        if actor.startswith("universe:"):
            universe_id = actor.removeprefix("universe:").strip()
    return _default_execution_scope(base_path, universe_id)


def _authoritative_execution_scope(
    base_path: str | Path,
    run_id: str,
    asserted_scope: "ExecutionScope | None",
) -> "ExecutionScope":
    """Return the persisted run scope, rejecting a contradictory assertion."""
    from tinyassets.sandbox_policy import ExecutionScope

    persisted = _execution_scope_for_run(base_path, run_id)
    if asserted_scope is None:
        return persisted
    asserted = ExecutionScope.coerce(asserted_scope)
    if asserted.kind is not persisted.kind:
        return ExecutionScope.unknown()
    if persisted.is_bound:
        try:
            if Path(asserted.universe_dir or "").resolve() != Path(
                persisted.universe_dir or ""
            ).resolve():
                return ExecutionScope.unknown()
        except (OSError, RuntimeError, ValueError):
            return ExecutionScope.unknown()
    return persisted


def _persisted_execution_context(
    run: dict[str, Any] | None,
) -> tuple[int, NodeEnqueueContext]:
    """Reconstruct trusted compile context stored with the original run."""
    record = run or {}
    raw = record.get("enqueue_context")
    raw = raw if isinstance(raw, dict) else {}
    return int(record.get("invocation_depth") or 0), NodeEnqueueContext(
        universe_id=str(raw.get("universe_id") or ""),
        actor=str(raw.get("actor") or ""),
        parent_branch_task_id=str(raw.get("parent_branch_task_id") or ""),
        origin_branch_task_id=str(raw.get("origin_branch_task_id") or ""),
    )


def _scope_universe_dir(
    base_path: str | Path,
    scope: "ExecutionScope | None",
) -> tuple[Path | None, str | None]:
    """Validate *scope* and return its context pin plus any block reason."""
    from tinyassets.sandbox_policy import ExecutionScope, ScopeKind

    resolved = ExecutionScope.coerce(scope)
    if resolved.is_unknown:
        return None, "execution universe is unknown — fail closed."
    if resolved.kind is ScopeKind.LEGACY_UNBOUND:
        return None, None

    root = Path(base_path).resolve()
    try:
        universe_dir = Path(resolved.universe_dir or "").resolve()
        if not universe_dir.is_relative_to(root) or not universe_dir.is_dir():
            return None, "execution universe could not be resolved — fail closed."
    except (OSError, RuntimeError, ValueError):
        return None, "execution universe could not be resolved — fail closed."
    return universe_dir, _execution_blocked_reason(universe_dir)


def _universe_id_for_scope(scope: "ExecutionScope | None") -> str:
    """Return the bound universe directory name for persistence."""
    from tinyassets.sandbox_policy import ExecutionScope

    resolved = ExecutionScope.coerce(scope)
    if not resolved.is_bound or not resolved.universe_dir:
        return ""
    return Path(resolved.universe_dir).name


def _coherent_execution_scope(
    base_path: str | Path,
    universe_id: str,
    scope: "ExecutionScope | None",
) -> "ExecutionScope":
    """Resolve scope and fail closed when explicit id and path disagree."""
    from tinyassets.sandbox_policy import ExecutionScope

    uid = (universe_id or "").strip()
    resolved = (
        ExecutionScope.coerce(scope)
        if scope is not None
        else _default_execution_scope(base_path, uid)
    )
    if not uid:
        return resolved
    expected = _default_execution_scope(base_path, uid)
    if not expected.is_bound or not resolved.is_bound:
        return ExecutionScope.unknown()
    if Path(expected.universe_dir or "").resolve() != Path(
        resolved.universe_dir or ""
    ).resolve():
        return ExecutionScope.unknown()
    return resolved


_PRIVATE_BINDING_REDACTION = "[private binding]"


def _redact_private_binding_values(value: Any, bindings: dict[str, Any]) -> Any:
    """Recursively remove private binding values from durable run telemetry."""
    private_values = [item for item in bindings.values() if item is not None]
    for private in private_values:
        if not isinstance(value, (dict, list, tuple)) and value == private:
            return _PRIVATE_BINDING_REDACTION
    if isinstance(value, str):
        redacted = value
        for private in private_values:
            candidates = {str(private)}
            try:
                candidates.add(json.dumps(private, sort_keys=True))
            except (TypeError, ValueError):
                pass
            for candidate in candidates:
                if candidate:
                    redacted = redacted.replace(candidate, _PRIVATE_BINDING_REDACTION)
        return redacted
    if isinstance(value, dict):
        return {
            key: _redact_private_binding_values(item, bindings)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_private_binding_values(item, bindings) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_private_binding_values(item, bindings) for item in value)
    return value


def _invoke_graph(
    base_path: str | Path,
    *,
    run_id: str,
    branch: BranchDefinition,
    inputs: dict[str, Any],
    provider_call: Callable[..., str] | None,
    runtime_bindings: dict[str, Any] | None = None,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    concurrency_budget_override: int | None = None,
    on_node_status: Callable[[str, str], None] | None = None,
    invocation_depth: int = 0,
    enqueue_context: "NodeEnqueueContext | None" = None,
    execution_scope: "ExecutionScope | None" = None,
    start_node: str = "",
) -> RunOutcome:
    """Authorize and pin a prepared run under its immutable tenant scope."""
    scope = _authoritative_execution_scope(base_path, run_id, execution_scope)
    universe_dir, block_reason = _scope_universe_dir(base_path, scope)
    if block_reason is not None:
        logger.error(
            "run %s BLOCKED — refusing ambient credential execution: %s",
            run_id,
            block_reason,
        )
        update_run_status(
            base_path,
            run_id,
            status=RUN_STATUS_FAILED,
            error=block_reason,
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id,
            status=RUN_STATUS_FAILED,
            output={},
            error=block_reason,
        )

    from tinyassets.execution_context import pin_execution_universe

    with pin_execution_universe(universe_dir):
        return _invoke_graph_inner(
            base_path,
            run_id=run_id,
            branch=branch,
            inputs=inputs,
            provider_call=provider_call,
            runtime_bindings=runtime_bindings,
            recursion_limit=recursion_limit,
            concurrency_budget_override=concurrency_budget_override,
            on_node_status=on_node_status,
            invocation_depth=invocation_depth,
            enqueue_context=enqueue_context,
            execution_scope=scope,
            start_node=start_node,
        )


def _invoke_graph_inner(
    base_path: str | Path,
    *,
    run_id: str,
    branch: BranchDefinition,
    inputs: dict[str, Any],
    provider_call: Callable[..., str] | None,
    runtime_bindings: dict[str, Any] | None = None,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    concurrency_budget_override: int | None = None,
    on_node_status: Callable[[str, str], None] | None = None,
    invocation_depth: int = 0,
    enqueue_context: "NodeEnqueueContext | None" = None,
    execution_scope: "ExecutionScope | None" = None,
    start_node: str = "",
) -> RunOutcome:
    """Compile + invoke the graph for an already-prepared run_id.

    Blocks until the graph finishes or is cancelled. Updates run status
    to RUNNING on entry, COMPLETED / FAILED / CANCELLED on exit.

    ``execution_scope`` is the AUTHORITATIVE tenant scope (Codex S3 r20 #2),
    threaded EXPLICITLY to the compiler so a sandbox-required node with an UNKNOWN
    scope fails closed. ``None`` → UNKNOWN (fail closed) at the choke point.
    """
    thread_id = run_id
    execution_cursor = {"step": 0}
    private_bindings = dict(runtime_bindings or {})

    def _safe_private(value: Any) -> Any:
        return _redact_private_binding_values(value, private_bindings)

    if private_bindings and provider_call is not None:
        raw_provider_call = provider_call

        def _private_safe_provider_call(*args: Any, **kwargs: Any) -> str:
            try:
                return raw_provider_call(*args, **kwargs)
            except Exception as exc:
                safe = RuntimeError(f"{type(exc).__name__}: {_safe_private(str(exc))}")
                for attr in ("chain_state", "attempts"):
                    if hasattr(exc, attr):
                        setattr(safe, attr, _safe_private(getattr(exc, attr)))
                raise safe from None

        provider_call = _private_safe_provider_call
    # Telemetry accumulator: "last" feeds runs.provider_used (legacy
    # last-wins), "model" feeds the runs.model column, "calls" becomes a
    # per-run ``provider_calls`` system event (one entry per provider-served
    # node: provider, model, latency, attempts).
    provider_tracker: dict[str, Any] = {"last": None, "model": None, "calls": []}
    run_identity = {
        "owner_user_id": "",
        "daemon_id": "",
        "runtime_instance_id": "",
        "worker_id": "",
    }
    with _connect(base_path) as conn:
        identity_row = conn.execute(
            """
            SELECT owner_user_id, daemon_id, runtime_instance_id, worker_id
            FROM runs WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    if identity_row is not None:
        run_identity = {
            "owner_user_id": identity_row["owner_user_id"] or "",
            "daemon_id": identity_row["daemon_id"] or "",
            "runtime_instance_id": identity_row["runtime_instance_id"] or "",
            "worker_id": identity_row["worker_id"] or "",
        }

    def _emit_node_status(node_id: str, status: str) -> None:
        if on_node_status is None:
            return
        try:
            on_node_status(node_id, status)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Run %s node-status callback failed for %s status=%s",
                run_id, node_id, status,
            )

    # Phase 2 design_used emit (Task #75) — pre-build a graph_node_id ->
    # NodeDefinition lookup so each "ran" event can credit the artifact
    # author without scanning branch.node_defs per step. Falls back to
    # node_id matching when graph_nodes is empty (legacy single-list
    # branches). Empty NodeDefinition.author skips emit at the
    # contribution-event layer (orphan-row prevention).
    _node_def_by_id: dict[str, Any] = {}
    _defs_index = {n.node_id: n for n in branch.node_defs}
    if branch.graph_nodes:
        for gn in branch.graph_nodes:
            ref_id = gn.node_def_id or gn.id
            if ref_id in _defs_index:
                _node_def_by_id[gn.id] = _defs_index[ref_id]
    else:
        _node_def_by_id = dict(_defs_index)

    def _on_node(node_id: str, **detail: Any) -> None:
        # #60: the compiler emits TWO events per node — phase="starting"
        # before the provider call and phase="ran" after. Each event gets
        # its own step_index so polling clients see node status transition
        # pending -> running -> ran, no more "frozen for 4 minutes" gaps.
        #
        # Cooperative cancel fires only on "ran" (between nodes).
        # Cancelling mid-provider-call would orphan the LLM call; the
        # node boundary is the right checkpoint.
        phase = detail.pop("phase", "ran")
        detail = _redact_private_binding_values(
            detail,
            dict(runtime_bindings or {}),
        )
        step = execution_cursor["step"]
        execution_cursor["step"] += 1

        if phase == "starting":
            record_event(base_path, RunStepEvent(
                run_id=run_id,
                step_index=step + _PENDING_OFFSET,
                node_id=node_id,
                status=NODE_STATUS_RUNNING,
                started_at=_now(),
                detail=detail,
            ))
            _emit_node_status(node_id, NODE_STATUS_RUNNING)
            return

        if phase == "failed":
            record_event(base_path, RunStepEvent(
                run_id=run_id,
                step_index=step + _PENDING_OFFSET,
                node_id=node_id,
                status=NODE_STATUS_FAILED,
                started_at=_now(),
                finished_at=_now(),
                detail=detail,
            ))
            return

        if is_cancel_requested(base_path, run_id):
            raise RunCancelledError(f"Run {run_id} cancelled between nodes.")
        served = detail.get("provider_served")
        if served:
            provider_tracker["last"] = str(served)
            model = detail.get("provider_model")
            if model:
                provider_tracker["model"] = str(model)
            provider_tracker["calls"].append({
                "node_id": node_id,
                "provider": str(served),
                "model": str(model or ""),
                "latency_ms": detail.get("provider_latency_ms"),
                "attempts": detail.get("provider_attempts"),
                "degraded": bool(detail.get("provider_degraded", False)),
                "at": _now(),
            })
        record_event(base_path, RunStepEvent(
            run_id=run_id,
            step_index=step + _PENDING_OFFSET,
            node_id=node_id,
            status=NODE_STATUS_RAN,
            started_at=_now(),
            finished_at=_now(),
            detail=detail,
        ))
        _emit_node_status(node_id, NODE_STATUS_RAN)

        # Phase 2 design_used emit (Task #75) — credit the NodeDefinition's
        # author for a successful step execution. Fires only at "ran" phase
        # for real artifact-referencing nodes. System events (node_id
        # prefixed with "__") and synthetic phases never trigger. Wrapped
        # in try/except so emit failure stays decoupled from run state
        # (mirrors Task #72 discipline).
        if node_id.startswith("__"):
            return
        nd = _node_def_by_id.get(node_id)
        if nd is None:
            return
        node_def_id = getattr(nd, "node_def_id", "") or getattr(nd, "node_id", "")
        author = getattr(nd, "author", "") or ""
        if not node_def_id or not author or author == "anonymous":
            return
        try:
            from tinyassets.contribution_events import record_contribution_event
            record_contribution_event(
                base_path,
                event_id=f"design_used:{run_id}:{step}:{node_def_id}",
                event_type="design_used",
                actor_id=author,
                owner_user_id=run_identity["owner_user_id"],
                daemon_id=run_identity["daemon_id"],
                runtime_instance_id=run_identity["runtime_instance_id"],
                worker_id=run_identity["worker_id"],
                source_run_id=run_id,
                source_artifact_id=node_def_id,
                source_artifact_kind="node_def",
                weight=1.0,
                occurred_at=_now(),
                metadata_json=json.dumps({
                    "step_index": step,
                    "node_def_id": node_def_id,
                    "graph_node_id": node_id,
                }),
            )
        except Exception as exc:
            from tinyassets.contribution_events import _EMIT_FAILURES
            from tinyassets.contribution_events import _logger as _ce_logger
            _EMIT_FAILURES["count"] += 1
            _ce_logger.warning(
                "design_used emit failed for run %s step %s node %s: %s; "
                "step event preserved",
                run_id, step, node_id, exc,
            )

    try:
        compiled = compile_branch(
            branch,
            start_node=start_node,
            provider_call=provider_call,
            event_sink=_on_node,
            concurrency_budget_override=concurrency_budget_override,
            base_path=base_path,
            parent_run_id=run_id,
            invocation_depth=invocation_depth,
            enqueue_context=enqueue_context,
            execution_scope=execution_scope,
        )
    except (UnapprovedNodeError, CompilerError) as exc:
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_FAILED,
            error=str(exc),
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_FAILED,
            output={}, error=str(exc),
        )
    except Exception as exc:
        logger.exception("Run %s failed during compile", run_id)
        msg = f"Compile failed: {type(exc).__name__}: {exc}"
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_FAILED,
            error=msg,
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_FAILED,
            output={}, error=msg,
        )

    update_run_status(base_path, run_id, status=RUN_STATUS_RUNNING)

    # Emit recursion_limit_applied event so get_run can surface the cap used.
    record_event(base_path, RunStepEvent(
        run_id=run_id,
        # Prepared node-state rows occupy the low cursor range.  Keep the
        # synthetic run event immediately before live execution events so it
        # cannot overwrite the first node (including a skipped predecessor).
        step_index=_PENDING_OFFSET - 1,
        node_id="__system__",
        status="recursion_limit_applied",
        started_at=_now(),
        detail={"recursion_limit": recursion_limit},
    ))

    if is_cancel_requested(base_path, run_id):
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_CANCELLED,
            error="Cancelled before execution started.",
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_CANCELLED,
            output={}, error="Cancelled before execution started.",
        )

    # Phase A item 5 / Task #76b — reset the threadlocal child-retry counter
    # so this parent run starts with a fresh global cap.
    from tinyassets.graph_compiler import ChildFailedError, _retry_budget_reset
    _retry_budget_reset()

    try:
        # Binding values may exist in live graph state, but never in the durable
        # SqliteSaver checkpoint. Bound runs are terminal-on-restart already, so
        # an in-memory checkpointer preserves the v1 contract without a second
        # private-value store.
        from tinyassets.branch_bindings import declared_binding_fields

        binding_fields = declared_binding_fields(
            getattr(branch, "state_schema", None),
        )
        missing_bindings = sorted(binding_fields - set(private_bindings))
        if missing_bindings:
            reason = (
                "This design is inert until all declared repo/policy slots "
                "are bound to its universe with write_graph target=binding."
            )
            update_run_status(
                base_path, run_id, status=RUN_STATUS_FAILED,
                error=reason, finished_at=_now(),
            )
            return RunOutcome(
                run_id=run_id, status=RUN_STATUS_FAILED,
                output={}, error=reason,
            )

        if binding_fields:
            from langgraph.checkpoint.memory import MemorySaver

            checkpointer_context = contextlib.nullcontext(MemorySaver())
        else:
            from langgraph.checkpoint.sqlite import SqliteSaver

            saver_path = str(Path(base_path) / ".langgraph_runs.db")
            Path(saver_path).parent.mkdir(parents=True, exist_ok=True)
            checkpointer_context = SqliteSaver.from_conn_string(saver_path)

        with checkpointer_context as checkpointer:
            app = compiled.graph.compile(checkpointer=checkpointer)
            # BUG-085 M3: seed state_schema defaults UNDER caller inputs so
            # state_schema-declared fields with defaults are available to
            # strict-isolation prompt placeholders from step 1.
            initial_state = seed_initial_state(
                {**inputs, **private_bindings},
                getattr(branch, "state_schema", None),
            )
            result = app.invoke(
                initial_state,
                config={
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": recursion_limit,
                },
            )
    except RunCancelledError as exc:
        msg = str(_safe_private(str(exc)))
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_CANCELLED,
            error=msg,
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_CANCELLED,
            output={}, error=msg,
        )
    except ChildFailedError as exc:
        # Phase A item 5 / Task #76b — sub-branch propagated a non-completed
        # child terminal status. Parent run terminates with the structured
        # ChildFailure surfaced on RunOutcome.child_failures so downstream
        # observers (Task #48 contribution-ledger caused_regression emit;
        # Task #53 route-back gate verdicts) can consume the failure.
        msg = str(_safe_private(str(exc)))
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_FAILED, error=msg, finished_at=_now(),
        )
        failure = exc.failure if isinstance(exc.failure, ChildFailure) else None
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_FAILED,
            output={}, error=msg,
            child_failures=[failure] if failure is not None else [],
        )
    except ChildRunAwaitTimeout as exc:
        msg = (
            f"Child invocation receipt gate timed out after "
            f"{exc.timeout_seconds}s while child run '{exc.run_id}' was "
            f"still {exc.child_status}; parent is receipt-waiting and can be "
            "reclaimed with attach_existing_child_run."
        )
        output = {
            "parent_loop_status": "receipt_waiting",
            "selected_child_status": "child_invocation_receipt_waiting",
            "selected_branch_state": "child_invocation_receipt_waiting",
            "automation_claim_status": "child_invocation_receipt_waiting",
            "child_run_id": exc.run_id,
            "selected_child_run_id": exc.run_id,
            "selected_child_branch_def_id": exc.child_branch_def_id,
            "child_invocation_receipt_gate": {
                "status": "receipt_waiting",
                "reason": "child_run_still_running_after_timeout",
                "child_run_id": exc.run_id,
                "child_status": exc.child_status,
                "child_branch_def_id": exc.child_branch_def_id,
                "timeout_seconds": exc.timeout_seconds,
                "reclaim_action": "attach_existing_child_run",
            },
        }
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_INTERRUPTED,
            output=output,
            error=msg,
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id,
            status=RUN_STATUS_INTERRUPTED,
            output=output,
            error=msg,
        )
    except Exception as exc:
        # GraphRecursionError: structured error naming the applied limit.
        try:
            from langgraph.errors import GraphRecursionError as _GRE
            if isinstance(exc, _GRE):
                msg = (
                    f"GraphRecursionError: recursion limit {recursion_limit} reached. "
                    f"Raise via recursion_limit_override on run_branch. Detail: {exc}"
                )
                msg = str(_safe_private(msg))
                update_run_status(
                    base_path, run_id,
                    status=RUN_STATUS_FAILED, error=msg, finished_at=_now(),
                )
                return RunOutcome(
                    run_id=run_id, status=RUN_STATUS_FAILED, output={}, error=msg,
                )
        except ImportError:
            pass
        # LangGraph may wrap RunCancelledError in its own exception.
        # Unwrap and handle uniformly.
        if _is_cancel_exception(exc):
            msg = f"Run {run_id} cancelled between nodes."
            update_run_status(
                base_path, run_id,
                status=RUN_STATUS_CANCELLED,
                error=msg,
                finished_at=_now(),
            )
            return RunOutcome(
                run_id=run_id, status=RUN_STATUS_CANCELLED,
                output={}, error=msg,
            )
        # #61: surface node timeouts with a distinct reason so the user
        # can tell "your evidence-intake node hit the 300s cap" from a
        # generic crash. The NodeTimeoutError message carries the
        # node_id and timeout value.
        timeout_exc = _find_timeout_exception(exc)
        if timeout_exc is not None:
            msg = str(_safe_private(f"Node timeout: {timeout_exc}"))
            step = execution_cursor["step"]
            execution_cursor["step"] += 1
            record_event(base_path, RunStepEvent(
                run_id=run_id,
                step_index=step + _PENDING_OFFSET,
                node_id=_node_id_from_timeout_exc(timeout_exc),
                status=NODE_STATUS_FAILED,
                started_at=_now(),
                finished_at=_now(),
                detail={"reason": "timeout", "message": msg},
            ))
            _emit_node_status(
                _node_id_from_timeout_exc(timeout_exc),
                NODE_STATUS_FAILED,
            )
            update_run_status(
                base_path, run_id,
                status=RUN_STATUS_FAILED,
                error=msg,
                finished_at=_now(),
            )
            return RunOutcome(
                run_id=run_id, status=RUN_STATUS_FAILED,
                output={}, error=msg,
            )
        empty_exc = _find_empty_response_exception(exc)
        if empty_exc is not None:
            msg = str(_safe_private(f"Empty LLM response: {empty_exc}"))
            step = execution_cursor["step"]
            execution_cursor["step"] += 1
            record_event(base_path, RunStepEvent(
                run_id=run_id,
                step_index=step + _PENDING_OFFSET,
                node_id=empty_exc.node_id or "(unknown)",
                status=NODE_STATUS_FAILED,
                started_at=_now(),
                finished_at=_now(),
                detail={"reason": "empty_response", "message": msg},
            ))
            _emit_node_status(
                empty_exc.node_id or "(unknown)",
                NODE_STATUS_FAILED,
            )
            update_run_status(
                base_path, run_id,
                status=RUN_STATUS_FAILED,
                error=msg,
                finished_at=_now(),
            )
            return RunOutcome(
                run_id=run_id, status=RUN_STATUS_FAILED,
                output={}, error=msg,
            )
        msg = str(_safe_private(f"{type(exc).__name__}: {exc}"))
        if private_bindings:
            logger.error("Run %s failed at invoke: %s", run_id, msg)
        else:
            logger.exception("Run %s failed at invoke", run_id)
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_FAILED,
            error=msg,
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_FAILED,
            output={}, error=msg,
        )

    output = dict(result) if isinstance(result, dict) else {"result": result}

    # Emit concurrency_stats event so get_run can surface peak + budget.
    if compiled.concurrency_tracker is not None:
        stats = compiled.concurrency_tracker.stats()
        step = execution_cursor["step"]
        execution_cursor["step"] += 1
        record_event(base_path, RunStepEvent(
            run_id=run_id,
            step_index=step + _PENDING_OFFSET,
            node_id="__system__",
            status="concurrency_stats",
            started_at=_now(),
            detail=stats,
        ))

    # Model-stamp telemetry (spec §11.3 / PR-172): one system event with the
    # full per-call list so receipts can answer "which model, how long, how
    # many tries" per provider-served node.
    if provider_tracker["calls"]:
        step = execution_cursor["step"]
        execution_cursor["step"] += 1
        record_event(base_path, RunStepEvent(
            run_id=run_id,
            step_index=step + _PENDING_OFFSET,
            node_id="__system__",
            status="provider_calls",
            started_at=_now(),
            detail={"calls": provider_tracker["calls"]},
        ))

    # PR-122 Phase 1 — external-write effectors.
    # After a successful run, walk node_defs that declared an ``effects``
    # list and route their outputs to the matching effector (today only
    # github_pull_request via ``gh pr create``). Errors are surfaced into
    # the run output's ``external_write_errors`` metadata; they never
    # raise into the user-facing run status. Hard-rule #8 (fail loudly)
    # is satisfied by the structured error fields on each evidence entry.
    _quarantine_branch_authored_external_write_keys(output)
    external_write_evidence = _run_external_write_effectors(
        branch,
        output,
        base_path=_effector_base_path(base_path, execution_scope),
        run_id=run_id,
    )

    # Effectors need the real private binding values while executing.  Apply
    # redaction only after that boundary, before any run output is persisted.
    output = _safe_private(output)
    for field_name in binding_fields:
        output.pop(field_name, None)
    if external_write_evidence:
        # PR-122 Phase 1 round-2 (Codex finding #2): the receipt is
        # system-authoritative. Overwrite unconditionally — any branch
        # that tries to forge ``external_write_results`` /
        # ``external_write_errors`` has already been moved to
        # ``_branch_authored_*`` for forensics above.
        output["external_write_results"] = _safe_private(external_write_evidence)
        errors = _collect_external_write_errors(external_write_evidence)
        if errors:
            output["external_write_errors"] = _safe_private(errors)

    # S4 / E3 (Codex r12 #1 + #5): a present node that opened + projected a PR
    # for owner review installs a durable review CHECKPOINT and the run must NOT
    # sail past it. The disposition of that checkpoint decides the run's status:
    #   - failed:    a REQUIRED review checkpoint could not be persisted →
    #                fail VISIBLY (Hard Rule 8); never complete past an
    #                un-checkpointed gate.
    #   - suspended: the checkpoint persisted → the canonical run stays
    #                INTERRUPTED (awaiting the owner's decision), NOT completed;
    #                the owner's durable decision-effect plan finalizes it.
    #   - complete:  no review checkpoint → normal completion.
    disposition, detail = _review_gate_disposition(external_write_evidence)
    if disposition == "failed":
        msg = (
            "review checkpoint could not be persisted; refusing to complete a "
            f"run past an un-checkpointed required review gate: {detail}"
        )
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_FAILED, output=output, error=msg, finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_FAILED, output=output, error=msg,
        )
    if disposition == "suspended":
        output["awaiting_owner_review"] = detail
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_INTERRUPTED, output=output, finished_at=_now(),
            provider_used=provider_tracker["last"], model=provider_tracker["model"],
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_INTERRUPTED, output=output,
            error="awaiting_owner_review",
        )

    update_run_status(
        base_path, run_id,
        status=RUN_STATUS_COMPLETED,
        output=output,
        finished_at=_now(),
        provider_used=provider_tracker["last"],
        model=provider_tracker["model"],
    )
    return RunOutcome(
        run_id=run_id, status=RUN_STATUS_COMPLETED,
        output=output, error="",
    )


# PR-122 Phase 1 round-2 (Codex finding #2): reserved system keys
# the effector writes. If a branch already filled these in via run
# output, the values are user-authored and MUST NOT be authoritative
# — they are quarantined under ``_branch_authored_*`` so the system
# receipt is the one that lands at the canonical key.
_EXTERNAL_WRITE_RESERVED_KEYS = (
    "external_write_results",
    "external_write_errors",
)


def _quarantine_branch_authored_external_write_keys(
    output: dict[str, Any],
) -> None:
    """Move any branch-authored reserved external-write keys aside.

    Called BEFORE the effector dispatch so that the effector's
    evidence wins at the canonical key. Branch-authored values are
    preserved under ``_branch_authored_<key>`` for forensics, with a
    warning so the operator notices the attempted forgery.
    """
    for system_key in _EXTERNAL_WRITE_RESERVED_KEYS:
        if system_key in output:
            quarantine_key = f"_branch_authored_{system_key}"
            output[quarantine_key] = output.pop(system_key)
            logger.warning(
                "branch output included reserved system key %r; "
                "moved to %r before effector ran",
                system_key,
                quarantine_key,
            )


def _run_external_write_effectors(
    branch: BranchDefinition,
    run_state: dict[str, Any],
    *,
    base_path: str | Path | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Dispatch external-write effectors for ``branch`` against ``run_state``.

    ``base_path`` + ``run_id`` are passed to the effector so the Phase-2
    gates (consent + idempotency) have a universe to bind to. When
    omitted (legacy or test invocations), the effector falls back to
    dry-run for any Phase-2-shaped packet — see
    ``tinyassets.effectors.github_pr.run_effects_for_branch``.

    Never raises — all errors are folded into the returned evidence map.
    Returns ``{}`` when no node declares any ``effects``.
    """
    try:
        from tinyassets.effectors import run_effects_for_branch
    except Exception:  # pragma: no cover — defensive import guard
        logger.exception("failed to import tinyassets.effectors")
        return {}
    try:
        return run_effects_for_branch(
            branch=branch,
            run_state=run_state,
            base_path=base_path,
            run_id=run_id,
        )
    except Exception:  # pragma: no cover — effectors are no-raise
        logger.exception("external-write effector dispatch crashed")
        return {}


def _effector_base_path(
    base_path: str | Path,
    execution_scope: "ExecutionScope | None",
) -> str | Path:
    """Use the run's authoritative universe for universe-scoped effect state."""
    if execution_scope is not None and execution_scope.is_bound:
        universe_dir = (execution_scope.universe_dir or "").strip()
        if universe_dir:
            return universe_dir
    return base_path


def _collect_external_write_errors(
    evidence_map: dict[str, Any],
) -> list[dict[str, Any]]:
    """Flatten the per-node evidence into a list of error rows.

    Each row: ``{"node_id": ..., "sink": ..., "error": ..., "error_kind": ...}``.
    Used to populate ``output['external_write_errors']`` for downstream
    observers (run snapshot, get_run, debugging).
    """
    errors: list[dict[str, Any]] = []
    for node_id, per_node in (evidence_map or {}).items():
        if not isinstance(per_node, dict):
            continue
        for sink, ev in per_node.items():
            if not isinstance(ev, dict):
                continue
            if ev.get("error"):
                errors.append({
                    "node_id": node_id,
                    "sink": sink,
                    "error": ev.get("error"),
                    "error_kind": ev.get("error_kind") or "unknown",
                })
    return errors


def _review_gate_disposition(
    evidence_map: dict[str, Any],
) -> tuple[str, Any]:
    """Decide how a run's review checkpoint disposes the run status (Codex r12
    #1 / #5). Returns ``(disposition, detail)`` where disposition is one of
    ``"complete"`` / ``"suspended"`` / ``"failed"``.

    Reads the present node's github_pull_request evidence:
    - ``review_queue_enqueue_error`` present ⇒ ``failed`` (a required review
      checkpoint could not be persisted — the run must not complete past it).
    - ``review_queue_run_suspended`` truthy ⇒ ``suspended`` (the run pauses
      awaiting the owner's decision).
    - otherwise ⇒ ``complete``.
    """
    suspended_detail: dict[str, Any] | None = None
    for node_id, per_node in (evidence_map or {}).items():
        if not isinstance(per_node, dict):
            continue
        for _sink, ev in per_node.items():
            if not isinstance(ev, dict):
                continue
            if ev.get("review_queue_enqueue_error"):
                return "failed", ev.get("review_queue_enqueue_error")
            if ev.get("review_queue_run_suspended"):
                suspended_detail = {
                    "node_id": node_id,
                    "pr_number": ev.get("review_queue_pr_number"),
                    "destination": ev.get("destination"),
                }
    if suspended_detail is not None:
        return "suspended", suspended_detail
    return "complete", None


_GH_CALL_KEYS = ("kind", "transport", "method", "path", "params", "summary")


_REVIEW_EVENT_STATE = {"APPROVE": "APPROVED", "REQUEST_CHANGES": "CHANGES_REQUESTED"}
_REVIEW_DECISION_DRAIN_LIMIT = 100


class _TerminalDecisionEffect(RuntimeError):
    """A replay that is permanently unsafe and must not be retried."""


def _require_review_effect_head(pull: dict[str, Any], expected_head: str) -> None:
    live_head = str(pull.get("head_sha") or "").strip()
    if live_head != expected_head:
        raise _TerminalDecisionEffect("head_moved")


def _review_already_on_github(
    github_api: Any, call_dict: dict[str, Any], *, expected_owner: str = "",
) -> bool:
    """Codex r15 #3 + REJECT #3: reconcile against GitHub's ACTUAL state before
    re-submitting — was a review with THIS commit_id, by the CONNECTED OWNER, in
    the matching state already submitted? Closes the crash-after-remote-before-
    receipt double-submit window WITHOUT accepting a DIFFERENT actor's review at
    the same commit (the security hole the REJECT reproduced).

    ``expected_owner`` is the resolved connected-owner login; an EMPTY owner
    NEVER reconciles (fail safe → re-submit with the owner's own token rather
    than trust an unattributed review). Tolerant of a client without
    ``list_pull_reviews`` (returns False → submit)."""
    params = call_dict.get("params") or {}
    commit_id = (params.get("commit_id") or "").strip()
    want_event = (params.get("event") or "").strip().upper()
    owner = (expected_owner or "").strip().lstrip("@").lower()
    path = call_dict.get("path") or ""
    # path is /repos/{owner}/{repo}/pulls/{n}/reviews
    m = re.search(r"/repos/([^/]+/[^/]+)/pulls/(\d+)/reviews", path)
    if not commit_id or not owner or m is None:
        return False
    destination, pr_number = m.group(1), int(m.group(2))
    try:
        reviews = github_api.list_pull_reviews(
            destination=destination, pr_number=pr_number,
        )
    except Exception:  # noqa: BLE001 — no reconcile method / error ⇒ submit
        return False
    want_state = _REVIEW_EVENT_STATE.get(want_event, want_event)
    for rv in reviews or []:
        if (
            (rv.get("commit_id") or "").strip() == commit_id
            and (rv.get("user_login") or "").strip().lstrip("@").lower() == owner
            and (rv.get("state") or "").strip().upper() == want_state
        ):
            return True
    return False


def execute_next_review_decision_effect(
    base_path: str | Path,
    *,
    worker_id: str,
    github_api: Any = None,
    verifier_api: Any = None,
    app_actor_id: Any = None,
    expected_owner: str = "",
    client_factory: Any = None,
    verifier_factory: Any = None,
    owner_resolver: Any = None,
    app_actor_resolver: Any = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Claim and execute one ordered review-decision effect.

    Queue lifecycle (ordering, leases, retry ownership) belongs to
    ``storage.review_queue``.  This function contains only effect policy and
    reconciliation.  Reshape emits a canonical ``BranchTask``; it never starts
    or recovers a run here.
    """
    from tinyassets import github_native as _gn
    from tinyassets.branch_tasks import BranchTask, append_task_if_absent
    from tinyassets.github_native import GitHubCall
    from tinyassets.storage import review_queue as _rq

    effect = _rq.claim_next_decision_effect(
        base_path, worker_id=worker_id, now=now
    )
    if effect is None:
        return None
    effect_id = effect["effect_id"]
    decision_id = effect["decision_id"]
    kind = effect["kind"]
    payload = effect.get("payload") or {}
    destination = str(payload.get("destination") or "").strip()
    effect_api = github_api
    effect_verifier = verifier_api
    effect_owner = expected_owner
    effect_actor_id = app_actor_id
    try:
        if kind in {"submit_review", "apply_merge_preference"}:
            effect_api = _resolve_worker_client(
                github_api, client_factory, destination
            )
            effect_verifier = _resolve_worker_client(
                verifier_api, verifier_factory, destination
            )
            if not effect_owner and owner_resolver is not None:
                effect_owner = owner_resolver(destination) or ""
            if effect_actor_id in (None, "") and app_actor_resolver is not None:
                effect_actor_id = app_actor_resolver(destination)
    except Exception as exc:  # noqa: BLE001 -- client resolution is retryable
        _rq.release_decision_effect(
            base_path,
            effect_id=effect_id,
            worker_id=worker_id,
            claim_token=effect["claim_token"],
            error=f"client_error:{exc}",
            now=now,
        )
        decision_status = _rq.get_decision_status(
            base_path, decision_id=decision_id
        )
        if decision_status == "failed":
            _surface_terminal_review_failure(
                base_path,
                decision_id=decision_id,
                effect_id=effect_id,
                kind=kind,
                reason=f"client_error:{exc}",
            )
        return {
            "decision_id": decision_id,
            "effect_id": effect_id,
            "kind": kind,
            "executed": False,
            "reason": f"client_error:{exc}",
            "terminal": decision_status == "failed",
            "decision_status": decision_status,
        }
    result: dict[str, Any]
    try:
        if kind == "submit_review":
            if effect_api is None:
                raise RuntimeError("no_client")
            pr_number = int(payload.get("pr_number") or 0)
            head = str(payload.get("expected_head_sha") or "").strip()
            event = str(payload.get("event") or "APPROVE").strip().upper()
            pull = effect_api.get_pull(
                destination=destination, pr_number=pr_number
            )
            _require_review_effect_head(pull, head)
            if event == "APPROVE":
                app_ok, app_reason = _app_authored_pr(
                    pull, expected_owner=effect_owner
                )
                if not app_ok:
                    raise RuntimeError(app_reason)
                call = _gn.review_approve(
                    destination=destination, pr_number=pr_number, head_sha=head
                )
            else:
                call = _gn.review_request_changes(
                    destination=destination,
                    pr_number=pr_number,
                    head_sha=head,
                    body=str(payload.get("body") or ""),
                )
            call_dict = call.to_dict()
            if _review_already_on_github(
                effect_api, call_dict, expected_owner=effect_owner
            ):
                result = {"detail": "already_on_github"}
            else:
                response = effect_api.run_call(call)
                if not response.get("ok"):
                    raise RuntimeError("review_call_failed")
                result = {"detail": "submitted", "status": response.get("status")}
            confirmed_pull = effect_api.get_pull(
                destination=destination, pr_number=pr_number
            )
            _require_review_effect_head(confirmed_pull, head)

        elif kind == "apply_merge_preference":
            if effect_api is None:
                raise RuntimeError("no_client")
            pr_number = int(payload.get("pr_number") or 0)
            head = str(payload.get("expected_head_sha") or "").strip()
            pull = effect_api.get_pull(
                destination=destination, pr_number=pr_number
            )
            _require_review_effect_head(pull, head)
            if pull.get("merged"):
                result = {"detail": "already_merged", "state": "merged"}
            elif pull.get("auto_merge_enabled"):
                result = {
                    "detail": "already_enabled",
                    "state": "approved_auto_merge_enabled",
                }
            else:
                from tinyassets.effectors import github_merge as _gm

                merge = _gm.run_autonomous_merge(
                    base_path,
                    destination=destination,
                    pr_number=pr_number,
                    branch_def_id=str(payload.get("branch_def_id") or ""),
                    expected_head_sha=head,
                    github_api=effect_api,
                    verifier_api=effect_verifier,
                    app_actor_id=effect_actor_id,
                    expected_owner=effect_owner,
                    now=now,
                )
                if not merge.get("ok"):
                    raise RuntimeError(
                        str(merge.get("error_kind") or "merge_preference_failed")
                    )
                if merge.get("action") == "enable_auto_merge":
                    call_dict = merge.get("github_call") or {}
                    response = effect_api.run_call(GitHubCall(**{
                        key: call_dict[key]
                        for key in _GH_CALL_KEYS
                        if key in call_dict
                    }))
                    if not response.get("ok"):
                        raise RuntimeError("enable_auto_merge_failed")
                result = {
                    "detail": str(merge.get("action") or "merge_preference_applied"),
                    "state": str(merge.get("state") or ""),
                }

        elif kind == "enqueue_revision":
            route = payload.get("route_back") or {}
            branch_task_id = str(payload.get("branch_task_id") or "").strip()
            source_run_id = str(route.get("run_id") or "").strip()
            branch_def_id = str(route.get("branch_def_id") or "").strip()
            universe_id = str(route.get("universe_id") or "").strip()
            target_node = str(route.get("target_node") or "").strip()
            if not all((branch_task_id, source_run_id, branch_def_id, universe_id,
                        target_node)):
                raise RuntimeError("invalid_revision_route")
            _created, task = append_task_if_absent(
                Path(base_path),
                BranchTask(
                    branch_task_id=branch_task_id,
                    branch_def_id=branch_def_id,
                    universe_id=universe_id,
                    trigger_source="owner_queued",
                    request_type="review_revision",
                    inputs={
                        "reshape_notes": str(route.get("owner_notes") or "").strip()
                    },
                    review_decision_id=decision_id,
                    source_run_id=source_run_id,
                    target_node=target_node,
                ),
            )
            result = {"branch_task_id": task.branch_task_id}

        elif kind == "finalize_run":
            source_run_id = str(payload.get("run_id") or "").strip()
            run_base_path = _review_run_storage_path(base_path, source_run_id)
            source = get_run(run_base_path, source_run_id)
            if source is None:
                raise RuntimeError("run_not_found")
            decision = str(payload.get("decision") or "").strip()
            output = dict(source.get("output") or {})
            if source.get("status") != RUN_STATUS_COMPLETED:
                if source.get("status") != RUN_STATUS_INTERRUPTED:
                    raise RuntimeError(
                        f"run_not_awaiting_review:{source.get('status')}"
                    )
                if "awaiting_owner_review" not in output:
                    raise RuntimeError("not_a_review_suspension")
                prior = _rq.list_decision_effects(
                    base_path, decision_id=decision_id
                )
                prior_results = {
                    row["kind"]: row.get("result") or {}
                    for row in prior
                    if row["position"] < effect["position"]
                }
                state = {
                    _rq.INTENT_APPROVE: (
                        prior_results.get("apply_merge_preference", {}).get("state")
                        or "await_owner_merge"
                    ),
                    _rq.INTENT_RESHAPE: "reshaped_revising",
                    _rq.INTENT_REJECT: "rejected",
                }.get(decision, "resumed")
                output["review_decision"] = decision
                output["review_workflow_state"] = state
                output["review_continuation_effects"] = prior_results
                output.pop("awaiting_owner_review", None)
                update_run_status(
                    run_base_path,
                    source_run_id,
                    status=RUN_STATUS_COMPLETED,
                    output=output,
                    finished_at=_now(),
                )
            _rq.ack_continuation(base_path, run_id=source_run_id)
            result = {"run_id": source_run_id, "decision": decision}

        else:
            raise RuntimeError(f"unknown_decision_effect:{kind}")
    except Exception as exc:  # noqa: BLE001 -- storage decides retry vs terminal
        permanently_unsafe = isinstance(exc, _TerminalDecisionEffect)
        settle = (
            _rq.fail_decision_effect
            if permanently_unsafe
            else _rq.release_decision_effect
        )
        settle(
            base_path,
            effect_id=effect_id,
            worker_id=worker_id,
            claim_token=effect["claim_token"],
            error=str(exc),
            now=now,
        )
        decision_status = _rq.get_decision_status(
            base_path, decision_id=decision_id
        )
        if decision_status == "failed":
            _surface_terminal_review_failure(
                base_path,
                decision_id=decision_id,
                effect_id=effect_id,
                kind=kind,
                reason=str(exc),
            )
        return {
            "decision_id": decision_id,
            "effect_id": effect_id,
            "kind": kind,
            "executed": False,
            "reason": str(exc),
            "terminal": decision_status == "failed",
            "decision_status": decision_status,
        }

    if not _rq.complete_decision_effect(
        base_path,
        effect_id=effect_id,
        worker_id=worker_id,
        claim_token=effect["claim_token"],
        result=result,
        now=now,
    ):
        return {
            "decision_id": decision_id,
            "effect_id": effect_id,
            "kind": kind,
            "executed": False,
            "reason": "claim_lost",
        }
    response = {
        "decision_id": decision_id,
        "effect_id": effect_id,
        "kind": kind,
        "executed": True,
    }
    response.update(result)
    return response


def execute_pending_review_decisions(
    base_path: str | Path,
    *,
    worker_id: str,
    github_api: Any = None,
    verifier_api: Any = None,
    app_actor_id: Any = None,
    expected_owner: str = "",
    client_factory: Any = None,
    verifier_factory: Any = None,
    owner_resolver: Any = None,
    app_actor_resolver: Any = None,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Drain a bounded batch of ready effects across independent decisions."""
    from tinyassets.storage import review_queue as _rq

    results: list[dict[str, Any]] = []
    attempts = 0
    for _ in range(_REVIEW_DECISION_DRAIN_LIMIT):
        attempts += 1
        result = execute_next_review_decision_effect(
            base_path,
            worker_id=worker_id,
            github_api=github_api,
            verifier_api=verifier_api,
            app_actor_id=app_actor_id,
            expected_owner=expected_owner,
            client_factory=client_factory,
            verifier_factory=verifier_factory,
            owner_resolver=owner_resolver,
            app_actor_resolver=app_actor_resolver,
            now=now,
        )
        if result is None:
            break
        if result.get("terminal") and not _rq.mark_decision_effect_reported(
            base_path,
            effect_id=str(result.get("effect_id") or ""),
            reported_by=worker_id,
            now=now,
        ):
            continue
        results.append(result)
    remaining = _REVIEW_DECISION_DRAIN_LIMIT - attempts
    if remaining:
        results.extend(
            _surface_unreported_terminal_review_failures(
                base_path,
                worker_id=worker_id,
                limit=remaining,
                now=now,
            )
        )
    return results


def _surface_terminal_review_failure(
    base_path: str | Path,
    *,
    decision_id: str,
    effect_id: str,
    kind: str,
    reason: str,
) -> bool:
    """Persist a terminal effect failure on its suspended source run."""
    from tinyassets.storage import review_queue as _rq

    finalize = next(
        (
            effect
            for effect in _rq.list_decision_effects(
                base_path, decision_id=decision_id
            )
            if effect["kind"] == "finalize_run"
        ),
        None,
    )
    run_id = str(((finalize or {}).get("payload") or {}).get("run_id") or "")
    if not run_id:
        return False
    run_base_path = _review_run_storage_path(base_path, run_id)
    source = get_run(run_base_path, run_id)
    if source is None or source.get("status") != RUN_STATUS_INTERRUPTED:
        return False
    output = dict(source.get("output") or {})
    if "awaiting_owner_review" not in output:
        return False
    if (
        output.get("review_decision_id") == decision_id
        and output.get("review_decision_status") == "failed"
    ):
        return False
    output.update({
        "review_decision_id": decision_id,
        "review_decision_status": "failed",
        "review_decision_failure": {
            "effect_id": effect_id,
            "kind": kind,
            "reason": reason,
        },
    })
    update_run_status(run_base_path, run_id, output=output)
    return True


def _surface_unreported_terminal_review_failures(
    base_path: str | Path,
    *,
    worker_id: str,
    limit: int,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Surface lease-expiry terminalizations that produced no worker result."""
    from tinyassets.storage import review_queue as _rq

    surfaced: list[dict[str, Any]] = []
    for effect in _rq.list_unreported_terminal_decision_effects(
        base_path, limit=limit
    ):
        decision_id = str(effect.get("decision_id") or "")
        effect_id = str(effect.get("effect_id") or "")
        reason = str(effect.get("last_error") or "effect_failed")
        _surface_terminal_review_failure(
            base_path,
            decision_id=decision_id,
            effect_id=effect_id,
            kind=str(effect.get("kind") or ""),
            reason=reason,
        )
        if not _rq.mark_decision_effect_reported(
            base_path,
            effect_id=effect_id,
            reported_by=worker_id,
            now=now,
        ):
            continue
        surfaced.append({
            "decision_id": decision_id,
            "effect_id": effect_id,
            "kind": str(effect.get("kind") or ""),
            "executed": False,
            "reason": reason,
            "terminal": True,
            "decision_status": "failed",
        })
    return surfaced


def _review_run_storage_path(base_path: str | Path, run_id: str) -> Path:
    """Resolve a review-queue universe path to its canonical run store."""
    queue_path = Path(base_path)
    if runs_db_path(queue_path).is_file() and get_run(queue_path, run_id) is not None:
        return queue_path
    parent = queue_path.parent
    if parent != queue_path and runs_db_path(parent).is_file():
        run = get_run(parent, run_id)
        if run is not None and run.get("universe_id") == queue_path.name:
            return parent
    return queue_path


def supersede_stranded_review_runs(
    base_path: str | Path, run_ids: list[str] | None,
) -> list[str]:
    """Cancel the CANONICAL runs of suspensions that were superseded by a newer
    run on the same PR (Codex r13 #5) — otherwise an older run stranded at
    INTERRUPTED waits for an owner decision that will never come. Returns the
    run_ids actually cancelled. Only an interrupted awaiting-review run is
    touched."""
    cancelled: list[str] = []
    for rid in run_ids or []:
        run_base_path = _review_run_storage_path(base_path, rid)
        run = get_run(run_base_path, rid)
        if run is None or run.get("status") != RUN_STATUS_INTERRUPTED:
            continue
        output = dict(run.get("output") or {})
        if "awaiting_owner_review" not in output:
            continue
        output["review_workflow_state"] = "superseded"
        output.pop("awaiting_owner_review", None)
        update_run_status(
            run_base_path, rid,
            status=RUN_STATUS_CANCELLED, output=output,
            error="superseded by a newer run on the same PR", finished_at=_now(),
        )
        cancelled.append(rid)
    return cancelled


def _app_authored_pr(pull: dict[str, Any], *, expected_owner: str) -> tuple[bool, str]:
    """App-authored-PR invariant (Codex r17 #4). Returns ``(ok, reason)``.

    GitHub blocks a PR author from approving their own PR, so a PR authored by the
    connected owner (e.g. via a founder PAT) could NEVER receive the required owner
    review — reject it before merge instead of merging on a self-approval that
    can't exist. App-installation-authored PRs carry ``author_type == "Bot"``; a
    human/PAT author is rejected. Fail closed when author identity is absent (can't
    verify App authorship)."""
    owner = (expected_owner or "").strip().lstrip("@").lower()
    author = (pull.get("author_login") or "").strip().lstrip("@").lower()
    author_type = (pull.get("author_type") or "").strip().lower()
    if not author:
        return False, "pr_author_unknown"
    if owner and author == owner:
        return False, "pr_authored_by_owner"  # self-approval is impossible
    if author_type != "bot":
        return False, "pr_not_app_authored"  # a human/PAT-authored PR
    return True, "app_authored"


def _owner_approval_confirmed(
    github_api: Any, *, destination: str, pr_number: int, head: str,
    expected_owner: str,
) -> bool:
    """PLATFORM-ENFORCED owner-review gate (Codex r17 #1): is there, RIGHT NOW on
    GitHub, an APPROVED review by the CONNECTED OWNER at the EXACT head (not
    dismissed/superseded)? This does NOT trust local ``WORKFLOW_APPROVED`` — so an
    UNPROTECTED repo (no required-review ruleset) still cannot be merged without a
    real owner approval on GitHub. An empty owner or head, an unreadable reviews
    list, or no matching review ⇒ False (fail closed, refuse the merge)."""
    owner = (expected_owner or "").strip().lstrip("@").lower()
    want = (head or "").strip()
    if not owner or not want:
        return False
    try:
        reviews = github_api.list_pull_reviews(
            destination=destination, pr_number=pr_number,
        )
    except Exception:  # noqa: BLE001 — can't verify ⇒ fail closed
        return False
    effective_states = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
    latest = next(
        (
            rv
            for rv in reversed(reviews or [])
            if (rv.get("user_login") or "").strip().lstrip("@").lower() == owner
            and (rv.get("state") or "").strip().upper() in effective_states
        ),
        None,
    )
    return bool(
        latest
        and (latest.get("commit_id") or "").strip() == want
        and (latest.get("state") or "").strip().upper() == "APPROVED"
    )


def execute_manual_merge(
    base_path: str | Path, *, destination: str, pr_number: int,
    expected_head_sha: str, github_api: Any = None, expected_owner: str = "",
) -> dict[str, Any]:
    """Execute the MANUAL merge (Codex r15 #1b / r17 #1) — the default flow.

    GATE (Codex r17 #1): before submitting the merge this REQUIRES a CONFIRMED
    APPROVED review by the CONNECTED OWNER at the exact reviewed head — read from
    GitHub, never local ``WORKFLOW_APPROVED``. So even an unprotected repo cannot
    merge without a real owner approval on GitHub. Head-bound: reports
    pending→merged ONLY after re-reading GitHub confirms the merge at the reviewed
    head.

    Idempotent + crash-safe (r15 #3): reconciles against GitHub state (is the PR
    ALREADY merged at this sha?) before submitting, so a replay never
    double-merges. Without a client → ``confirmed=False`` (pending), never a
    false 'merged'. Returns ``{"confirmed", "state", ...}``."""
    from tinyassets import github_native as _gn
    from tinyassets.storage import review_queue as _rq

    want = (expected_head_sha or "").strip()
    if not want:
        # Head-bound by contract (Codex REJECT #5): without the reviewed head we
        # cannot prove the head that merges is the head the owner approved.
        return {"confirmed": False, "state": "missing_expected_head",
                "reason": "manual merge requires the reviewed expected_head_sha"}
    # HEAD-BOUND receipt (Codex REJECT #5): a receipt only vouches for THIS head,
    # so a later head can't ride a prior head's confirmation.
    receipt_kind = f"manual_merge:{pr_number}:{want[:12]}"
    if _rq.has_effect_receipt(base_path, run_id=destination, effect_kind=receipt_kind):
        return {"confirmed": True, "state": "merged", "detail": "receipt"}
    if github_api is None:
        return {"confirmed": False, "state": "pending_no_client",
                "github_call": _gn.merge_pr(
                    destination=destination, pr_number=pr_number,
                    expected_head_sha=want).to_dict()}
    # Reconcile: is the PR ALREADY merged AT THE REVIEWED HEAD? A merged PR whose
    # live head != the reviewed head means head A was replaced and head B merged
    # (a real security hole the REJECT reproduced) — refuse, never confirm.
    try:
        pull = github_api.get_pull(destination=destination, pr_number=pr_number)
    except Exception as exc:  # noqa: BLE001 — can't confirm ⇒ pending
        return {"confirmed": False, "state": "pull_unreadable", "reason": str(exc)}
    live_head = (pull.get("head_sha") or "").strip()
    if pull.get("merged"):
        if live_head and live_head != want:
            return {"confirmed": False, "state": "head_replaced_merge",
                    "reason": (f"PR merged at head {live_head[:8]} != reviewed head "
                               f"{want[:8]}; a replaced head merged")}
        _rq.record_effect_receipt(
            base_path, run_id=destination, effect_kind=receipt_kind,
            detail={"reconciled": True, "head_sha": want,
                    "merge_commit_sha": pull.get("merge_commit_sha")},
        )
        return {"confirmed": True, "state": "merged", "detail": "reconciled",
                "head_sha": want, "merge_commit_sha": pull.get("merge_commit_sha")}
    if live_head and want != live_head:
        return {"confirmed": False, "state": "head_moved",
                "reason": f"reviewed head {want[:8]} != live {live_head[:8]}"}
    # APP-AUTHORED-PR INVARIANT (Codex r17 #4): reject a PR the connected owner (or
    # a non-App human/PAT) authored BEFORE merging — GitHub blocks self-approval, so
    # such a PR can never carry the required owner review.
    app_ok, app_reason = _app_authored_pr(pull, expected_owner=expected_owner)
    if not app_ok:
        return {"confirmed": False, "state": "pr_author_invalid", "reason": app_reason}
    # PLATFORM OWNER-REVIEW GATE (Codex r17 #1): require a confirmed owner approval
    # on GitHub at this exact head BEFORE merging — never trust WORKFLOW_APPROVED.
    if not _owner_approval_confirmed(
        github_api, destination=destination, pr_number=pr_number, head=want,
        expected_owner=expected_owner,
    ):
        return {"confirmed": False, "state": "owner_review_unconfirmed",
                "reason": (
                    "no confirmed GitHub APPROVED review by the connected owner "
                    f"at head {want[:8]}; refusing to merge (local approval is not "
                    "sufficient)")}
    from tinyassets.github_native import GitHubCall
    # The merge call carries sha=want, so GitHub ALSO rejects a moved head (409).
    call = _gn.merge_pr(destination=destination, pr_number=pr_number,
                        expected_head_sha=want)
    cd = call.to_dict()
    res = github_api.run_call(GitHubCall(**{k: cd[k] for k in _GH_CALL_KEYS if k in cd}))
    if not res.get("ok"):
        return {"confirmed": False, "state": "merge_failed", "reason": "merge_call_failed"}
    # Re-read GitHub to CONFIRM the merge happened AT THE REVIEWED HEAD before
    # reporting merged (head-bound receipt identity — Codex REJECT #5).
    confirm = github_api.get_pull(destination=destination, pr_number=pr_number)
    confirm_head = (confirm.get("head_sha") or "").strip()
    if not confirm.get("merged"):
        return {"confirmed": False, "state": "merge_unconfirmed"}
    if confirm_head and confirm_head != want:
        return {"confirmed": False, "state": "head_replaced_merge",
                "reason": (f"post-merge head {confirm_head[:8]} != reviewed head "
                           f"{want[:8]}")}
    _rq.record_effect_receipt(
        base_path, run_id=destination, effect_kind=receipt_kind,
        detail={"head_sha": want, "merge_commit_sha": confirm.get("merge_commit_sha")},
    )
    return {"confirmed": True, "state": "merged", "head_sha": want,
            "merge_commit_sha": confirm.get("merge_commit_sha")}


def _resolve_worker_client(
    github_api: Any, client_factory: Any, destination: str
) -> Any:
    """Resolve the credentialed client a recovery worker uses for ``destination``:
    the directly-injected ``github_api`` (tests / single-repo), else
    ``client_factory(destination)`` which the daemon builds from the per-universe
    vault BY DESTINATION. Returns None when neither yields a client (fail closed —
    the row stays queued)."""
    if github_api is not None:
        return github_api
    if client_factory is None:
        return None
    return client_factory(destination)


def execute_pending_manual_merges(
    base_path: str | Path, *, github_api: Any = None, client_factory: Any = None,
    expected_owner: str = "", owner_resolver: Any = None,
) -> list[dict[str, Any]]:
    """RECOVERY WORKER — drain the head-bound MANUAL-MERGE outbox (Codex REJECT
    #1). For each queued merge it resolves the credentialed client (injected, or
    built from the vault BY DESTINATION via ``client_factory``) AND the connected
    owner login (``expected_owner`` or ``owner_resolver(destination)``), runs the
    head-bound + owner-review-gated :func:`execute_manual_merge`, and marks the
    outbox row executed ONLY when GitHub confirms the merge at the reviewed head.
    On confirmation it reconciles the PR projection to ``merged``. Without a client
    (or a confirmed owner review) the row stays queued (honest — never falsely
    drained). The REAL daemon path the chat verb's ``pending`` merge depends on."""
    from tinyassets.storage import review_queue as _rq

    results: list[dict[str, Any]] = []
    for row in _rq.list_pending_manual_merges(base_path):
        merge_id = row["merge_id"]
        dest = (row.get("destination") or "").strip()
        pr = row.get("pr_number")
        head = (row.get("expected_head_sha") or "").strip()
        try:
            client = _resolve_worker_client(github_api, client_factory, dest)
        except Exception as exc:  # noqa: BLE001 — client build failed ⇒ retry later
            results.append({"merge_id": merge_id, "confirmed": False,
                            "reason": f"client_error:{exc}"})
            continue
        if client is None:
            results.append({"merge_id": merge_id, "confirmed": False,
                            "reason": "no_client"})
            continue
        owner = expected_owner
        if not owner and owner_resolver is not None:
            try:
                owner = owner_resolver(dest) or ""
            except Exception:  # noqa: BLE001 — unresolvable owner ⇒ gate fails closed
                owner = ""
        try:
            outcome = execute_manual_merge(
                base_path, destination=dest, pr_number=pr,
                expected_head_sha=head, github_api=client, expected_owner=owner,
            )
        except Exception as exc:  # noqa: BLE001 — leave queued for retry
            logger.exception("manual merge drain failed for %s#%s", dest, pr)
            results.append({"merge_id": merge_id, "confirmed": False,
                            "reason": f"error:{exc}"})
            continue
        if outcome.get("confirmed"):
            _rq.mark_manual_merge_executed(base_path, merge_id=merge_id)
            try:
                _rq.reconcile_projection(
                    base_path, destination=dest, pr_number=pr,
                    github_state="merged",
                    merge_commit_sha=outcome.get("merge_commit_sha") or "",
                    head_sha=head,
                )
            except Exception:  # noqa: BLE001 — merge is durable; cache is advisory
                logger.exception("projection reconcile after merge failed")
            results.append({"merge_id": merge_id, "confirmed": True, "pr_number": pr,
                            "merge_commit_sha": outcome.get("merge_commit_sha")})
        else:
            results.append({"merge_id": merge_id, "confirmed": False,
                            "state": outcome.get("state"),
                            "reason": outcome.get("reason")})
    return results


def _resolve_owner_approval_id(
    reviews: list[dict[str, Any]] | None, *, owner: str, head: str
) -> int | None:
    """The review_id of the CONNECTED OWNER's APPROVED review at ``head`` (Codex
    REJECT #4) — the EXACT id a dismissal needs, never the hardcoded 0. Matches on
    the reviewer login AND (when known) the reviewed commit, returning the most
    recent match. None when no such standing owner approval exists."""
    want_owner = (owner or "").strip().lstrip("@").lower()
    want_head = (head or "").strip()
    if not want_owner:
        return None
    resolved: int | None = None
    for rv in reviews or []:
        if (rv.get("user_login") or "").strip().lstrip("@").lower() != want_owner:
            continue
        if (rv.get("state") or "").strip().upper() != "APPROVED":
            continue
        if want_head and (rv.get("commit_id") or "").strip() != want_head:
            continue
        rid = rv.get("id")
        if isinstance(rid, int):
            resolved = rid  # most recent matching approval wins
    return resolved


def execute_pending_revocations(
    base_path: str | Path, *, github_api: Any = None, client_factory: Any = None,
) -> list[dict[str, Any]]:
    """RECOVERY WORKER — execute queued preference-tightening revocations (Codex
    r15 #2): actually DISABLE auto-merge / DISMISS the prior approval via the
    client and confirm, then mark the revocation executed. The client is the
    injected ``github_api`` or ``client_factory(destination)`` (vault-built by
    destination). Without a client the revocations stay queued (honest — nothing
    is falsely marked done). Daemon-loop registration is the integration seam.

    Dismissal (Codex REJECT #4): the EXACT owner review_id is resolved from
    GitHub via ``list_pull_reviews`` (owner login + reviewed head) — never the
    old hardcoded ``review_id=0`` that the permissive fake accepted. The dismiss
    call runs under the owner USER token (the authorized dismisser on a protected
    branch), not the App's minimal installation scope. When no standing owner
    approval exists (already dismissed / head auto-dismissed), the revocation
    goal is already met and the row is marked done."""
    from tinyassets import github_native as _gn
    from tinyassets.github_native import GitHubCall
    from tinyassets.storage import review_queue as _rq

    results: list[dict[str, Any]] = []
    for rev in _rq.list_pending_revocations(base_path):
        rev_id = rev["revocation_id"]
        dest, pr, kind = rev.get("destination") or "", rev.get("pr_number"), rev.get("kind")
        try:
            github_api_dest = _resolve_worker_client(github_api, client_factory, dest)
        except Exception as exc:  # noqa: BLE001 — client build failed ⇒ retry later
            results.append({"revocation_id": rev_id, "executed": False,
                            "reason": f"client_error:{exc}"})
            continue
        if github_api_dest is None:
            results.append({"revocation_id": rev_id, "executed": False,
                            "reason": "no_client"})
            continue
        try:
            if kind == "disable_auto_merge":
                call = _gn.disable_auto_merge(destination=dest, pr_number=pr)
            elif kind == "dismiss_prior_approval":
                # Resolve the EXACT owner review_id from GitHub (never 0).
                try:
                    reviews = github_api_dest.list_pull_reviews(
                        destination=dest, pr_number=pr
                    )
                except Exception as exc:  # noqa: BLE001 — unreadable ⇒ retry later
                    results.append({"revocation_id": rev_id, "executed": False,
                                    "reason": f"reviews_unreadable:{exc}"})
                    continue
                review_id = _resolve_owner_approval_id(
                    reviews, owner=rev.get("founder_handle") or "",
                    head=rev.get("expected_head_sha") or "",
                )
                if review_id is None:
                    # No standing owner approval to dismiss → goal already met.
                    _rq.mark_revocation_executed(base_path, revocation_id=rev_id)
                    results.append({"revocation_id": rev_id, "executed": True,
                                    "kind": kind, "pr_number": pr,
                                    "detail": "no_standing_owner_approval"})
                    continue
                call = _gn.dismiss_review(
                    destination=dest, pr_number=pr, review_id=review_id,
                    message="merge preference changed; renewed owner consent required",
                )
            else:
                results.append({"revocation_id": rev_id, "executed": False,
                                "reason": f"unknown_kind:{kind}"})
                continue
            cd = call.to_dict()
            res = github_api_dest.run_call(GitHubCall(**{
                k: cd[k] for k in _GH_CALL_KEYS if k in cd
            }))
            if not res.get("ok"):
                results.append({"revocation_id": rev_id, "executed": False,
                                "reason": "call_failed"})
                continue
            _rq.mark_revocation_executed(base_path, revocation_id=rev_id)
            results.append({"revocation_id": rev_id, "executed": True,
                            "kind": kind, "pr_number": pr})
        except Exception as exc:  # noqa: BLE001 — leave queued for retry
            logger.exception("revocation execution failed")
            results.append({"revocation_id": rev_id, "executed": False,
                            "reason": f"error:{exc}"})
    return results


def fire_due_not_before_timers(
    base_path: str | Path, *, github_api: Any = None, verifier_api: Any = None,
    app_actor_id: Any = None, expected_owner: str = "", now: float | None = None,
    client_factory: Any = None, verifier_factory: Any = None,
    owner_resolver: Any = None, app_actor_resolver: Any = None,
) -> list[dict[str, Any]]:
    """RECOVERY WORKER — the not_before timer-watcher (Codex r14 #5 / r17 #3). For
    each due timer it RE-VALIDATES the binding revision + GitHub head, RE-RUNS the
    shared fail-closed autonomous gate (VERIFIER identity + fresh base/head), and
    only then executes the auto-merge enable — marking the timer fired ONLY on
    confirmed success (idempotent via receipt). A stale binding (owner tightened)
    or moved head refuses without firing.

    Per-destination wiring (Codex r17 #3): the merge client, the ruleset-read
    VERIFIER client, the connected owner, and the App bypass-actor id are resolved
    PER DESTINATION via the factories/resolvers (the daemon builds them from the
    vault) — falling back to the single injected values for tests. Without a
    verifier the autonomous gate fails closed and the timer stays due."""
    from tinyassets.effectors import github_merge as _gm
    from tinyassets.github_native import GitHubCall
    from tinyassets.storage import review_queue as _rq

    ts = now if now is not None else _now()
    fired: list[dict[str, Any]] = []
    for timer in _rq.due_not_before_timers(base_path, now=ts):
        dest = timer.get("destination") or ""
        pr = timer.get("pr_number")
        bdid = timer.get("branch_def_id") or ""
        binding = _rq.resolve_merge_preference_binding(base_path, branch_def_id=bdid)
        ok, reason = _rq.authorize_timer_fire(
            timer, current_revision=int(binding.get("revision") or 0),
        )
        if not ok:
            fired.append({"pr_number": pr, "fired": False, "reason": reason})
            continue
        # Resolve the per-destination merge client + verifier + owner + App actor.
        try:
            github_api_dest = _resolve_worker_client(github_api, client_factory, dest)
            verifier_dest = _resolve_worker_client(verifier_api, verifier_factory, dest)
        except Exception as exc:  # noqa: BLE001 — client build failed ⇒ stay due
            fired.append({"pr_number": pr, "fired": False,
                          "reason": f"client_error:{exc}"})
            continue
        owner_dest = expected_owner or (
            (owner_resolver(dest) or "") if owner_resolver else "")
        actor_dest = app_actor_id if app_actor_id not in (None, "") else (
            (app_actor_resolver(dest) or None) if app_actor_resolver else None)
        # Re-run the shared fail-closed gate against FRESH GitHub state.
        merge = _gm.run_autonomous_merge(
            base_path, destination=dest, pr_number=pr, branch_def_id=bdid,
            expected_head_sha=timer.get("expected_head_sha") or "",
            github_api=github_api_dest, verifier_api=verifier_dest,
            app_actor_id=actor_dest, expected_owner=owner_dest,
            firing=True, now=ts,
        )
        if not merge.get("ok") or merge.get("action") != "enable_auto_merge":
            fired.append({"pr_number": pr, "fired": False,
                          "reason": merge.get("error_kind") or merge.get("action")})
            continue
        # Reconcile the remote goal before mutating.  If the prior process died
        # after GitHub accepted enablePullRequestAutoMerge but before local ack,
        # REST already reports the feature enabled and replay only repairs local
        # state.
        current_pull = github_api_dest.get_pull(destination=dest, pr_number=pr)
        if current_pull.get("auto_merge_enabled"):
            _rq.mark_timer_fired(base_path, destination=dest, pr_number=pr, now=ts)
            fired.append({"pr_number": pr, "fired": True, "detail": "reconciled"})
            continue
        receipt_key = (
            f"timer_enable_auto_merge:{pr}:"
            f"{(timer.get('expected_head_sha') or '')[:12]}:"
            f"r{int(timer.get('binding_revision') or 0)}"
        )
        if _rq.has_effect_receipt(base_path, run_id=dest, effect_kind=receipt_key) is None:
            call = merge.get("github_call") or {}
            res = github_api_dest.run_call(GitHubCall(**{
                k: call[k] for k in _GH_CALL_KEYS if k in call
            }))
            if not res.get("ok"):
                fired.append({"pr_number": pr, "fired": False, "reason": "enable_failed"})
                continue
            _rq.record_effect_receipt(
                base_path, run_id=dest, effect_kind=receipt_key,
                detail={"status": res.get("status")},
            )
        _rq.mark_timer_fired(base_path, destination=dest, pr_number=pr, now=ts)
        fired.append({"pr_number": pr, "fired": True})
    return fired


def register_review_workers(
    *, base_path: str | Path, github_api: Any = None, verifier_api: Any = None,
    app_actor_id: Any = None, expected_owner: str = "", client_factory: Any = None,
    verifier_factory: Any = None, owner_resolver: Any = None,
    app_actor_resolver: Any = None,
) -> dict[str, Callable[[], list[dict[str, Any]]]]:
    """Register the review-decision and related recovery workers.

    The daemon invokes the leased ordered decision executor, manual-merge drain,
    revocation executor, and not-before timer watcher on each tick — each
    bound to the credentialed client (``github_api`` directly, or
    ``client_factory(destination)`` / ``verifier_factory(destination)`` built from
    the vault per destination), with the owner + App-actor resolved per
    destination.

    Live wiring: :func:`run_review_recovery_for_universe` builds the factories +
    resolvers from the per-universe vault and the daemon loop calls it each cycle
    (:func:`fantasy_daemon.__main__._dispatcher_startup`)."""
    return {
        "execute_decisions": lambda: execute_pending_review_decisions(
            base_path,
            worker_id=(
                os.environ.get("TINYASSETS_WORKER_ID", "").strip()
                or f"review-worker-{os.getpid()}"
            ),
            github_api=github_api,
            verifier_api=verifier_api,
            app_actor_id=app_actor_id,
            expected_owner=expected_owner,
            client_factory=client_factory,
            verifier_factory=verifier_factory,
            owner_resolver=owner_resolver,
            app_actor_resolver=app_actor_resolver,
        ),
        "drain_manual_merges": lambda: execute_pending_manual_merges(
            base_path, github_api=github_api, client_factory=client_factory,
            expected_owner=expected_owner, owner_resolver=owner_resolver,
        ),
        "execute_revocations": lambda: execute_pending_revocations(
            base_path, github_api=github_api, client_factory=client_factory,
        ),
        "fire_timers": lambda: fire_due_not_before_timers(
            base_path, github_api=github_api, verifier_api=verifier_api,
            app_actor_id=app_actor_id, expected_owner=expected_owner,
            client_factory=client_factory, verifier_factory=verifier_factory,
            owner_resolver=owner_resolver, app_actor_resolver=app_actor_resolver,
        ),
    }


def resolve_review_revision_request(
    base_path: str | Path,
    universe_dir: str | Path,
    *,
    task: Any,
    branch: BranchDefinition,
) -> dict[str, Any]:
    """Resolve trusted inputs/identity for a claimed review-revision task.

    This is decision policy only. The BranchTask queue owns execution lifecycle,
    and :func:`execute_claimed_branch_request` owns run lifecycle.
    """
    from tinyassets.api.runs import (
        _bind_universe_context,
        _resolve_runtime_bindings,
        _run_execution_scope,
    )
    from tinyassets.daemon_registry import get_daemon
    from tinyassets.daemon_server import get_runtime_instance

    source_run_id = str(getattr(task, "source_run_id", "") or "").strip()
    source = get_run(base_path, source_run_id)
    if source is None:
        raise LookupError("reshape source run was not found")
    branch_def_id = str(getattr(task, "branch_def_id", "") or "").strip()
    if branch_def_id != str(source.get("branch_def_id") or "").strip():
        raise RuntimeError("reshape task does not match its source branch")
    universe_id = str(getattr(task, "universe_id", "") or "").strip()
    if universe_id != str(source.get("universe_id") or "").strip():
        raise RuntimeError("reshape task does not match its source universe")
    target_node = str(getattr(task, "target_node", "") or "").strip()
    if target_node not in {node.id for node in branch.graph_nodes}:
        raise LookupError("reshape target node was not found in the branch")

    runtime_bindings, refusal = _resolve_runtime_bindings(branch, universe_id)
    if refusal is not None:
        raise RuntimeError("reshape runtime bindings are unavailable")
    owner_user_id = str(source.get("owner_user_id") or "").strip()
    runtime_instance_id = str(source.get("runtime_instance_id") or "").strip()
    if not owner_user_id or not runtime_instance_id:
        raise RuntimeError("reshape source has no trusted owner or live runtime")
    try:
        runtime = get_runtime_instance(base_path, instance_id=runtime_instance_id)
    except KeyError as exc:
        raise RuntimeError("reshape source has no live runtime") from exc
    if (
        str(runtime.get("status") or "").strip() != "provisioned"
        or str(runtime.get("universe_id") or "").strip() != universe_id
    ):
        raise RuntimeError("reshape source has no executable runtime")
    runtime_metadata = runtime.get("metadata") or {}
    daemon_id = str(source.get("daemon_id") or "").strip()
    if daemon_id != str(runtime_metadata.get("daemon_id") or "").strip():
        raise RuntimeError("reshape runtime identity does not match its daemon")
    daemon = get_daemon(base_path, daemon_id=daemon_id)
    if str(runtime.get("author_id") or "").strip() != str(
        daemon.get("legacy_author_id") or ""
    ).strip():
        raise RuntimeError("reshape runtime identity does not match its daemon")
    if owner_user_id != str(daemon.get("owner_user_id") or "").strip():
        raise RuntimeError("reshape runtime identity does not match its owner")
    runtime_owner = str(runtime_metadata.get("owner_user_id") or "").strip()
    if runtime_owner and runtime_owner != owner_user_id:
        raise RuntimeError("reshape runtime identity does not match its owner")
    worker_id = str(source.get("worker_id") or "").strip()
    runtime_worker = str(runtime_metadata.get("worker_id") or "").strip()
    if not worker_id or (runtime_worker and runtime_worker != worker_id):
        raise RuntimeError("reshape runtime identity does not match its worker")

    source_state = {
        **dict(source.get("inputs") or {}),
        **dict(source.get("output") or {}),
    }
    state_fields = {
        str(field.get("name") or "")
        for field in branch.state_schema
        if str(field.get("name") or "")
    }
    inputs = {key: value for key, value in source_state.items() if key in state_fields}
    inputs["reshape_notes"] = str(
        (getattr(task, "inputs", {}) or {}).get("reshape_notes") or ""
    ).strip()
    task_id = str(getattr(task, "branch_task_id", "") or "").strip()
    revised_run_id = hashlib.sha256(
        f"claimed-branch-task\0{task_id}".encode("utf-8")
    ).hexdigest()[:32]
    try:
        from tinyassets.providers.call import call_provider as provider_call
    except ImportError:
        provider_call = None
    return {
        "run_id": revised_run_id,
        "inputs": inputs,
        "run_name": f"branch-task-{task_id}",
        "actor": str(source.get("actor") or "anonymous"),
        "provider_call": _bind_universe_context(provider_call, universe_id),
        "runtime_bindings": runtime_bindings,
        "owner_user_id": owner_user_id,
        "daemon_id": daemon_id,
        "runtime_instance_id": runtime_instance_id,
        "worker_id": worker_id,
        "lineage_parent_run_id": source_run_id,
        "start_node": target_node,
        "universe_id": universe_id,
        "execution_scope": _run_execution_scope(universe_id),
    }


def run_review_recovery_for_universe(
    universe_dir: str | Path, *, request_fn: Any = None,
) -> dict[str, list[dict[str, Any]]]:
    """Drive review recovery for one universe with vault-built clients.

    Builds, from the platform credential vault BY DESTINATION: the merge/read
    client (:func:`github_http.github_client_from_vault`), the ruleset-read
    VERIFIER client (:func:`github_http.verifier_client_from_vault`), the connected
    owner login and App bypass-actor id from the non-secret connection metadata.
    The ordered decision executor owns review submission, merge-preference
    application, revision-task enqueue, and source-run finalization. Related
    workers drain explicit manual merges, execute revocations, and fire due
    not-before timers through the verifier.

    Fail-closed everywhere: a destination with no connected credential yields no
    client, so its rows stay queued; a manual merge with no CONFIRMED owner review
    on GitHub is refused; an autonomous timer with no verifier stays due. Called
    each cycle from the daemon's per-universe startup recovery; safe to call
    repeatedly (every worker is idempotent + receipt- / outbox-guarded). Returns
    per-worker result lists for observability."""
    from tinyassets.credential_broker import github_connection_metadata
    from tinyassets.github_http import (
        github_client_from_vault,
        verifier_client_from_vault,
    )
    _client_cache: dict[str, Any] = {}
    _verifier_cache: dict[str, Any] = {}
    universe_id = Path(universe_dir).name

    def client_factory(destination: str) -> Any:
        dest = (destination or "").strip()
        if dest not in _client_cache:
            try:
                _client_cache[dest] = github_client_from_vault(
                    universe_dir, dest, request_fn=request_fn,
                )
            except Exception:  # noqa: BLE001 — no/invalid credential ⇒ fail closed
                logger.exception("building github client for %s failed", dest)
                _client_cache[dest] = None
        return _client_cache[dest]

    def verifier_factory(destination: str) -> Any:
        dest = (destination or "").strip()
        if dest not in _verifier_cache:
            try:
                _verifier_cache[dest] = verifier_client_from_vault(
                    universe_dir, dest, request_fn=request_fn,
                )
            except Exception:  # noqa: BLE001 — no ruleset-verify grant ⇒ fail closed
                logger.exception("building verifier client for %s failed", dest)
                _verifier_cache[dest] = None
        return _verifier_cache[dest]

    def owner_resolver(destination: str) -> str:
        return github_connection_metadata(
            universe_id, destination
        ).get("account_login", "")

    def app_actor_resolver(destination: str) -> str:
        return github_connection_metadata(
            universe_id, destination
        ).get("app_actor_id", "")

    worker_id = (
        os.environ.get("TINYASSETS_WORKER_ID", "").strip()
        or f"review-worker-{os.getpid()}"
    )
    decisions = execute_pending_review_decisions(
        universe_dir,
        worker_id=worker_id,
        client_factory=client_factory,
        verifier_factory=verifier_factory,
        owner_resolver=owner_resolver,
        app_actor_resolver=app_actor_resolver,
    )

    return {
        "execute_decisions": decisions,
        "drain_manual_merges": execute_pending_manual_merges(
            universe_dir, client_factory=client_factory, owner_resolver=owner_resolver,
        ),
        "execute_revocations": execute_pending_revocations(
            universe_dir, client_factory=client_factory,
        ),
        "fire_timers": fire_due_not_before_timers(
            universe_dir, client_factory=client_factory,
            verifier_factory=verifier_factory, owner_resolver=owner_resolver,
            app_actor_resolver=app_actor_resolver,
        ),
    }


def _is_cancel_exception(exc: BaseException) -> bool:
    """Detect a wrapped RunCancelledError in a chain."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, RunCancelledError):
            return True
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return False


def _find_empty_response_exception(exc: BaseException) -> EmptyResponseError | None:
    """Walk the exception chain for an EmptyResponseError."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, EmptyResponseError):
            return cur
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return None


def _find_timeout_exception(exc: BaseException) -> NodeTimeoutError | None:
    """Walk the exception chain for a NodeTimeoutError (#61).

    LangGraph wraps node errors in its own exception types; the
    underlying timeout sits on ``__cause__`` / ``__context__``.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, NodeTimeoutError):
            return cur
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return None


_TIMEOUT_NODE_RE = re.compile(r"Node '([^']+)'")


def _node_id_from_timeout_exc(exc: NodeTimeoutError) -> str:
    """Return the node_id for a NodeTimeoutError.

    Prefers the ``node_id`` attribute set by the raiser (stable contract).
    Falls back to parsing the human-readable message for older callers
    that constructed the exception without the keyword — keeps backward
    compatibility with test fixtures and third-party code.
    """
    node_id = getattr(exc, "node_id", "") or ""
    if node_id:
        return node_id
    return _node_id_from_timeout_message(str(exc))


def _node_id_from_timeout_message(message: str) -> str:
    """Extract the node_id from a NodeTimeoutError message (legacy fallback).

    Fallback to ``"(timeout)"`` when the message doesn't match. The
    node_id drives which row in the run_events timeline surfaces the
    failure. Prefer :func:`_node_id_from_timeout_exc` when the exception
    object is in hand.
    """
    m = _TIMEOUT_NODE_RE.search(message)
    return m.group(1) if m else "(timeout)"


def execute_branch(
    base_path: str | Path,
    *,
    branch: BranchDefinition,
    inputs: dict[str, Any],
    run_name: str = "",
    actor: str = "anonymous",
    provider_call: Callable[..., str] | None = None,
    runtime_bindings: dict[str, Any] | None = None,
    recursion_limit_override: int | None = None,
    concurrency_budget_override: int | None = None,
    on_node_status: Callable[[str, str], None] | None = None,
    daemon_id: str | None = None,
    runtime_instance_id: str | None = None,
    worker_id: str | None = None,
    _invocation_depth: int = 0,
    _enqueue_universe_id: str = "",
    _parent_branch_task_id: str = "",
    _origin_branch_task_id: str = "",
    execution_scope: "ExecutionScope | None" = None,
) -> RunOutcome:
    """Synchronous end-to-end execution.

    Kept for callers that want the blocking contract (tests, scripts).
    The MCP handler uses :func:`execute_branch_async` instead.

    Raises nothing: validation/runtime errors are reported via
    ``RunOutcome.status``.

    Parameters
    ----------
    recursion_limit_override
        Optional override for LangGraph's recursion limit. When ``None``
        (default), uses :data:`DEFAULT_RECURSION_LIMIT` (100). Branches
        with deep conditional loops (Tier-1 Step 6) bump this.
    execution_scope
        The AUTHORITATIVE tenant scope (Codex S3 r20 #2). When ``None``, a default
        is derived from ``_enqueue_universe_id`` (empty → legacy-unbound; a bound id
        → bound). Callers that know the scope pass it explicitly. UNKNOWN fails
        closed for sandbox-required nodes.
    """
    execution_scope = _coherent_execution_scope(
        base_path,
        _enqueue_universe_id,
        execution_scope,
    )
    persisted_universe_id = (
        (_enqueue_universe_id or "").strip()
        or _universe_id_for_scope(execution_scope)
    )
    enqueue_context = NodeEnqueueContext(
        universe_id=_enqueue_universe_id,
        actor=actor,
        parent_branch_task_id=_parent_branch_task_id,
        origin_branch_task_id=_origin_branch_task_id,
    )
    run_id = _prepare_run(
        base_path,
        branch=branch, inputs=inputs,
        run_name=run_name, actor=actor,
        universe_id=persisted_universe_id,
        invocation_depth=_invocation_depth,
        enqueue_context=enqueue_context,
        daemon_id=daemon_id,
        runtime_instance_id=runtime_instance_id,
        worker_id=worker_id,
    )
    return _invoke_graph(
        base_path,
        run_id=run_id, branch=branch, inputs=inputs,
        provider_call=provider_call,
        runtime_bindings=runtime_bindings,
        recursion_limit=recursion_limit_override or DEFAULT_RECURSION_LIMIT,
        concurrency_budget_override=concurrency_budget_override,
        on_node_status=on_node_status,
        invocation_depth=_invocation_depth,
        execution_scope=execution_scope,
        enqueue_context=enqueue_context,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Async executor pool — in-process background worker for graph runs
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Phase 3.5: the MCP tool returns a `run_id` in <1s. The graph runs in a
# background thread. `cancel_run` flips the flag, the next inter-node
# `event_sink` check unwinds the graph. Restart recovery marks in-flight
# runs as `interrupted` so clients see a clean terminal state and can
# choose to rerun.

def execute_claimed_branch_request(
    base_path: str | Path,
    *,
    run_id: str,
    branch: BranchDefinition,
    inputs: dict[str, Any],
    run_name: str,
    actor: str,
    provider_call: Callable[..., str] | None = None,
    runtime_bindings: dict[str, Any] | None = None,
    on_node_status: Callable[[str, str], None] | None = None,
    owner_user_id: str = "",
    daemon_id: str = "",
    runtime_instance_id: str = "",
    worker_id: str = "",
    lineage_parent_run_id: str = "",
    start_node: str = "",
    universe_id: str = "",
    execution_scope: "ExecutionScope | None" = None,
) -> RunOutcome:
    """Execute one request already owned by a durable queue claim.

    The queue owns cross-process exclusivity and retry leases. This adapter owns
    deterministic run identity and crash recovery, so queue consumers do not
    recreate run lifecycle handling.
    """
    request_run_id = (run_id or "").strip()
    if not request_run_id:
        raise ValueError("run_id is required for a claimed branch request")
    enqueue_context = NodeEnqueueContext(universe_id=universe_id, actor=actor)
    scope = _coherent_execution_scope(base_path, universe_id, execution_scope)
    existing = get_run(base_path, request_run_id)
    if existing is not None:
        expected = {
            "branch_def_id": branch.branch_def_id,
            "run_name": run_name,
            "actor": actor,
            "universe_id": universe_id,
            "owner_user_id": owner_user_id,
            "daemon_id": daemon_id,
            "runtime_instance_id": runtime_instance_id,
            "worker_id": worker_id,
            "inputs": inputs,
        }
        if any(existing.get(field) != value for field, value in expected.items()):
            raise RuntimeError("existing claimed-request run does not match request")
        lineage = get_lineage(base_path, request_run_id)
        if (
            lineage is None
            or lineage.get("parent_run_id") != lineage_parent_run_id
            or lineage.get("branch_def_id") != branch.branch_def_id
        ):
            raise RuntimeError("existing claimed-request run lineage does not match")
        status = str(existing.get("status") or "")
        if status in {
            RUN_STATUS_COMPLETED,
            RUN_STATUS_FAILED,
            RUN_STATUS_CANCELLED,
        }:
            return RunOutcome(
                run_id=request_run_id,
                status=status,
                output=dict(existing.get("output") or {}),
                error=str(existing.get("error") or ""),
            )
        if status in {RUN_STATUS_QUEUED, RUN_STATUS_RUNNING}:
            update_run_status(
                base_path,
                request_run_id,
                status=RUN_STATUS_INTERRUPTED,
                error="Durable request reclaimed after its execution lease ended.",
                finished_at=_now(),
            )
            status = RUN_STATUS_INTERRUPTED
        if status not in {RUN_STATUS_INTERRUPTED, RUN_STATUS_RESUMED}:
            raise RuntimeError(f"claimed-request run has invalid status: {status}")
        if _has_checkpoint(base_path, request_run_id):
            update_run_status(base_path, request_run_id, status=RUN_STATUS_RESUMED)
            return _invoke_graph_resume(
                base_path,
                run_id=request_run_id,
                branch=branch,
                thread_id=request_run_id,
                provider_call=provider_call,
                execution_scope=scope,
            )
        made_progress = any(
            event.get("status") in {
                NODE_STATUS_RUNNING,
                NODE_STATUS_RAN,
                NODE_STATUS_FAILED,
            }
            for event in list_events(base_path, request_run_id)
        )
        if made_progress:
            raise RuntimeError(
                "interrupted claimed-request run has progress but no checkpoint"
            )
        with _connect(base_path) as conn:
            conn.execute(
                "UPDATE runs SET status = ?, error = '', finished_at = NULL "
                "WHERE run_id = ?",
                (RUN_STATUS_QUEUED, request_run_id),
            )
            conn.execute(
                "DELETE FROM run_cancels WHERE run_id = ?", (request_run_id,)
            )
    else:
        _prepare_run(
            base_path,
            run_id=request_run_id,
            branch=branch,
            inputs=inputs,
            run_name=run_name,
            actor=actor,
            universe_id=universe_id,
            enqueue_context=enqueue_context,
            owner_user_id=owner_user_id,
            daemon_id=daemon_id,
            runtime_instance_id=runtime_instance_id,
            worker_id=worker_id,
            lineage_parent_run_id=lineage_parent_run_id,
            start_node=start_node,
        )
    return _invoke_graph(
        base_path,
        run_id=request_run_id,
        branch=branch,
        inputs=inputs,
        provider_call=provider_call,
        runtime_bindings=runtime_bindings,
        recursion_limit=DEFAULT_RECURSION_LIMIT,
        on_node_status=on_node_status,
        execution_scope=scope,
        enqueue_context=enqueue_context,
        start_node=start_node,
    )


_DEFAULT_MAX_WORKERS = 4
# Phase A item 5 / Task #76c — two-pool model. Top-level runs (depth=0)
# go to _parent_pool; sub-branch invocations (depth>=1) go to _child_pool.
# This prevents the parent-holds-its-own-slot-while-waiting-on-child
# deadlock that single-pool concurrency hit at depth>=4 with pool size 4.
_executor_lock = threading.Lock()
_parent_pool: ThreadPoolExecutor | None = None
_child_pool: ThreadPoolExecutor | None = None
_futures: dict[str, Future] = {}
_futures_lock = threading.Lock()


def _max_workers() -> int:
    raw = os.environ.get("TINYASSETS_RUN_MAX_CONCURRENT", "")
    try:
        val = int(raw) if raw else _DEFAULT_MAX_WORKERS
    except ValueError:
        val = _DEFAULT_MAX_WORKERS
    return max(1, val)


def _max_child_workers() -> int:
    """Pool size for sub-branch (depth>=1) invocations.

    Phase A item 5 / Task #76c. Default ``MAX_INVOKE_BRANCH_DEPTH + 1`` so
    the deepest legal chain plus one buffer slot can run without blocking.
    Env override: ``TINYASSETS_CHILD_POOL_SIZE``.
    """
    raw = os.environ.get("TINYASSETS_CHILD_POOL_SIZE", "")
    try:
        val = int(raw) if raw else MAX_INVOKE_BRANCH_DEPTH + 1
    except ValueError:
        val = MAX_INVOKE_BRANCH_DEPTH + 1
    return max(1, val)


def _runtime_max_invocation_depth() -> int:
    """Runtime cap on sub-branch invocation depth.

    Phase A item 5 / Task #76c. Defaults to ``MAX_INVOKE_BRANCH_DEPTH``
    (5) but is host-tunable via ``TINYASSETS_INVOCATION_MAX_DEPTH`` for
    power-user research workflows that need deeper chains.
    """
    raw = os.environ.get("TINYASSETS_INVOCATION_MAX_DEPTH", "")
    try:
        val = int(raw) if raw else MAX_INVOKE_BRANCH_DEPTH
    except ValueError:
        val = MAX_INVOKE_BRANCH_DEPTH
    return max(1, val)


def _get_executor(invocation_depth: int = 0) -> ThreadPoolExecutor:
    """Two-pool executor lookup. Depth-0 → _parent_pool; depth>=1 → _child_pool.

    Phase A item 5 / Task #76c. Each pool is lazy-init under the shared
    ``_executor_lock``. Child pool is sized larger than parent pool by
    default so a deep sub-branch chain can't starve top-level runs.
    """
    global _parent_pool, _child_pool
    with _executor_lock:
        if invocation_depth >= 1:
            if _child_pool is None:
                _child_pool = ThreadPoolExecutor(
                    max_workers=_max_child_workers(),
                    thread_name_prefix="tinyassets-child",
                )
            return _child_pool
        if _parent_pool is None:
            _parent_pool = ThreadPoolExecutor(
                max_workers=_max_workers(),
                thread_name_prefix="tinyassets-run",
            )
        return _parent_pool


def shutdown_executor(wait: bool = True) -> None:
    """Shut down both executor pools. Used by tests and graceful shutdown.

    Phase A item 5 / Task #76c — two-pool model means both pools must be
    drained on shutdown.
    """
    global _parent_pool, _child_pool
    with _executor_lock:
        if _parent_pool is not None:
            _parent_pool.shutdown(wait=wait)
            _parent_pool = None
        if _child_pool is not None:
            _child_pool.shutdown(wait=wait)
            _child_pool = None
    with _futures_lock:
        _futures.clear()


def _track_future(run_id: str, future: Future) -> None:
    with _futures_lock:
        _futures[run_id] = future

    def _on_done(_fut: Future) -> None:
        with _futures_lock:
            _futures.pop(run_id, None)

    future.add_done_callback(_on_done)


def get_future(run_id: str) -> Future | None:
    """Return the in-flight Future for a run, if any. Mostly used by tests."""
    with _futures_lock:
        return _futures.get(run_id)


def wait_for(run_id: str, timeout: float | None = None) -> None:
    """Block until the background worker for a run finishes. Test helper."""
    fut = get_future(run_id)
    if fut is not None:
        fut.result(timeout=timeout)


def _execute_branch_core(
    base_path: str | Path,
    *,
    run_id: str | None = None,
    branch: BranchDefinition,
    inputs: dict[str, Any],
    run_name: str = "",
    actor: str = "anonymous",
    provider_call: Callable[..., str] | None = None,
    runtime_bindings: dict[str, Any] | None = None,
    recursion_limit_override: int | None = None,
    concurrency_budget_override: int | None = None,
    on_node_status: Callable[[str, str], None] | None = None,
    branch_version_id: str | None = None,
    daemon_id: str | None = None,
    runtime_instance_id: str | None = None,
    worker_id: str | None = None,
    owner_user_id: str | None = None,
    lineage_parent_run_id: str = "",
    start_node: str = "",
    _invocation_depth: int = 0,
    _enqueue_universe_id: str = "",
    execution_scope: "ExecutionScope | None" = None,
) -> RunOutcome:
    """Shared async-execution core for def-based and version-based runs.

    Prepares the run row + pending-node events synchronously, then submits
    the graph invocation to the background executor. Returns within a few
    ms with ``status=queued``.

    ``branch_version_id`` is None for def-based runs (the public
    :func:`execute_branch_async`) and set for version-based runs (the
    Phase A item 6 :func:`execute_branch_version_async`).

    ``_invocation_depth`` (Phase A item 5 / Task #76c) routes the run to
    the appropriate executor pool — top-level runs (depth=0) to the
    parent pool, sub-branch invocations (depth>=1) to the child pool.
    Compiler builders pass ``depth+1`` when spawning a child run from
    inside an ``invoke_branch_spec`` / ``invoke_branch_version_spec``
    node body.
    """
    execution_scope = _coherent_execution_scope(
        base_path,
        _enqueue_universe_id,
        execution_scope,
    )
    persisted_universe_id = (
        (_enqueue_universe_id or "").strip()
        or _universe_id_for_scope(execution_scope)
    )
    enqueue_context = NodeEnqueueContext(
        universe_id=_enqueue_universe_id,
        actor=actor,
    )
    run_id = _prepare_run(
        base_path,
        run_id=run_id,
        branch=branch, inputs=inputs,
        run_name=run_name, actor=actor,
        universe_id=persisted_universe_id,
        invocation_depth=_invocation_depth,
        enqueue_context=enqueue_context,
        branch_version_id=branch_version_id,
        owner_user_id=owner_user_id,
        daemon_id=daemon_id,
        runtime_instance_id=runtime_instance_id,
        worker_id=worker_id,
        lineage_parent_run_id=lineage_parent_run_id,
        start_node=start_node,
    )

    executor = _get_executor(invocation_depth=_invocation_depth)
    effective_limit = recursion_limit_override or DEFAULT_RECURSION_LIMIT

    def _worker() -> RunOutcome:
        try:
            return _invoke_graph(
                base_path,
                run_id=run_id, branch=branch, inputs=inputs,
                provider_call=provider_call,
                runtime_bindings=runtime_bindings,
                recursion_limit=effective_limit,
                concurrency_budget_override=concurrency_budget_override,
                on_node_status=on_node_status,
                invocation_depth=_invocation_depth,
                enqueue_context=enqueue_context,
                execution_scope=execution_scope,
                start_node=start_node,
            )
        except Exception:
            # Belt-and-suspenders: _invoke_graph already catches and
            # writes status, but if something escapes we still don't
            # want the executor to swallow it silently.
            logger.exception("Background worker for run %s crashed", run_id)
            update_run_status(
                base_path, run_id,
                status=RUN_STATUS_FAILED,
                error="Background worker crashed; see server logs.",
                finished_at=_now(),
            )
            return RunOutcome(
                run_id=run_id, status=RUN_STATUS_FAILED,
                output={}, error="Background worker crashed.",
            )

    future = executor.submit(_worker)
    _track_future(run_id, future)

    return RunOutcome(
        run_id=run_id, status=RUN_STATUS_QUEUED,
        output={}, error="",
    )


def execute_branch_async(
    base_path: str | Path,
    *,
    run_id: str | None = None,
    branch: BranchDefinition,
    inputs: dict[str, Any],
    run_name: str = "",
    actor: str = "anonymous",
    provider_call: Callable[..., str] | None = None,
    runtime_bindings: dict[str, Any] | None = None,
    recursion_limit_override: int | None = None,
    concurrency_budget_override: int | None = None,
    on_node_status: Callable[[str, str], None] | None = None,
    owner_user_id: str | None = None,
    daemon_id: str | None = None,
    runtime_instance_id: str | None = None,
    worker_id: str | None = None,
    lineage_parent_run_id: str = "",
    start_node: str = "",
    _invocation_depth: int = 0,
    _enqueue_universe_id: str = "",
    execution_scope: "ExecutionScope | None" = None,
) -> RunOutcome:
    """Prepare a def-based run synchronously and kick off graph execution
    in the background. Returns within a few ms with ``status=queued``.

    The status will transition to ``running`` once the worker picks up
    the job, then to ``completed`` / ``failed`` / ``cancelled``. Clients
    poll ``get_run`` or ``stream_run`` for updates.

    Backed by :func:`_execute_branch_core` with ``branch_version_id=None``.
    Version-based runs use :func:`execute_branch_version_async` (Phase A
    item 6, Task #65) instead.

    Parameters
    ----------
    recursion_limit_override
        Optional override for LangGraph's recursion limit. See
        :func:`execute_branch` for rationale.
    concurrency_budget_override
        Override the branch-level concurrency_budget for this run.
    _invocation_depth
        Phase A item 5 / Task #76c — sub-branch builders pass ``depth+1``
        when spawning a child. Top-level callers leave default (0).
    execution_scope
        The AUTHORITATIVE tenant scope (Codex S3 r20 #2). MCP handlers compute it
        from the run's universe id and pass it explicitly; ``None`` → UNKNOWN
        (fail closed) for a sandbox-required node.
    """
    return _execute_branch_core(
        base_path,
        run_id=run_id,
        branch=branch,
        inputs=inputs,
        run_name=run_name,
        actor=actor,
        provider_call=provider_call,
        runtime_bindings=runtime_bindings,
        recursion_limit_override=recursion_limit_override,
        concurrency_budget_override=concurrency_budget_override,
        on_node_status=on_node_status,
        owner_user_id=owner_user_id,
        daemon_id=daemon_id,
        runtime_instance_id=runtime_instance_id,
        worker_id=worker_id,
        lineage_parent_run_id=lineage_parent_run_id,
        start_node=start_node,
        branch_version_id=None,
        _invocation_depth=_invocation_depth,
        _enqueue_universe_id=_enqueue_universe_id,
        execution_scope=execution_scope,
    )


class SnapshotSchemaDrift(Exception):
    """Raised when a published version's snapshot can't be reconstructed.

    Phase A item 6 (Task #65). Wraps the failure of
    ``BranchDefinition.from_dict(snapshot)`` when the snapshot was
    published against an older branch schema and is missing a
    now-required field, has a now-removed field, or has a type-changed
    field. Carries class-level ``failure_class`` + ``suggested_action``
    so the MCP-layer handler can read them off the class without
    instantiating a defensive copy.
    """

    failure_class = "snapshot_schema_drift"
    suggested_action = "republish at current schema version"
    actionable_by = "chatbot"


def execute_branch_version_async(
    base_path: str | Path,
    *,
    branch_version_id: str,
    inputs: dict[str, Any],
    run_name: str = "",
    actor: str = "anonymous",
    provider_call: Callable[..., str] | None = None,
    recursion_limit_override: int | None = None,
    on_node_status: Callable[[str, str], None] | None = None,
    _invocation_depth: int = 0,
    _enqueue_universe_id: str = "",
    execution_scope: "ExecutionScope | None" = None,
) -> RunOutcome:
    """Execute a published branch_version snapshot (immutable).

    Sibling to :func:`execute_branch_async`; both wrap
    :func:`_execute_branch_core`. The version-based path loads the
    immutable snapshot from ``branch_versions``, reconstructs a
    ``BranchDefinition`` from it, and threads ``branch_version_id``
    through to the new ``runs.branch_version_id`` column for
    attribution (Task #48 / Task #53 dependencies).

    Cancellation propagation
    ------------------------
    Basic cancellation is identical to def-based runs — the run gets a
    ``run_id`` like any other; ``cancel_run(run_id)`` flips the flag in
    ``run_cancels`` and ``_invoke_graph``'s event_sink unwinds. **Parent
    gate-series cancellation does NOT propagate to child version-runs
    today.** Child runs are independent ``run_id``s; the propagation
    primitive lands when Task #53 route-back is implemented (a parent
    run that route-backs to a canonical via this helper will need
    cancellation forwarding then).

    Raises
    ------
    KeyError
        ``branch_version_id`` is not found in ``branch_versions``.
    SnapshotSchemaDrift
        The snapshot exists but cannot be reconstructed into a
        ``BranchDefinition`` because the on-disk shape predates a
        required field. The exception's ``failure_class`` and
        ``suggested_action`` class attributes name the recovery path
        ("republish at current schema version").
    """
    from tinyassets.branch_versions import get_branch_version

    bv = get_branch_version(base_path, branch_version_id=branch_version_id)
    if bv is None:
        raise KeyError(
            f"branch_version_id {branch_version_id!r} not found "
            "in branch_versions"
        )
    try:
        branch = BranchDefinition.from_dict(bv.snapshot)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SnapshotSchemaDrift(
            f"Snapshot for {branch_version_id!r} cannot be reconstructed: "
            f"{exc}. Republish at current schema version."
        ) from exc
    return _execute_branch_core(
        base_path,
        branch=branch,
        inputs=inputs,
        run_name=run_name,
        actor=actor,
        provider_call=provider_call,
        recursion_limit_override=recursion_limit_override,
        on_node_status=on_node_status,
        branch_version_id=branch_version_id,
        _invocation_depth=_invocation_depth,
        _enqueue_universe_id=_enqueue_universe_id,
        execution_scope=execution_scope,
    )


class ResumeError(Exception):
    """Raised when a resume_run call cannot proceed.

    Carries a structured ``reason`` code for programmatic handling:
    - ``not_interrupted``: run is not in INTERRUPTED status.
    - ``already_resumed``: run is already in RESUMED status (idempotent return).
    - ``not_found``: run_id does not exist.
    - ``auth_failed``: caller does not own the run.
    - ``no_checkpoint``: SqliteSaver has no checkpoint for this thread_id.
    - ``branch_version_mismatch``: branch was patched since the run was created.
    """

    def __init__(self, message: str, *, reason: str = "", current_status: str = "") -> None:
        super().__init__(message)
        self.reason = reason
        self.current_status = current_status


def _has_checkpoint(base_path: str | Path, thread_id: str) -> bool:
    """Return True if SqliteSaver has a checkpoint for thread_id."""
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        saver_path = str(Path(base_path) / ".langgraph_runs.db")
        if not Path(saver_path).exists():
            return False
        with SqliteSaver.from_conn_string(saver_path) as cp:
            # LangGraph's list() yields checkpoint tuples; we just need to
            # know at least one exists.
            config = {"configurable": {"thread_id": thread_id}}
            items = list(cp.list(config))
            return bool(items)
    except Exception:
        return False


def resume_run(
    base_path: str | Path,
    *,
    run_id: str,
    actor: str,
    branch_lookup: Callable[[str, int], BranchDefinition | None],
    provider_call: Callable[..., str] | None = None,
    execution_scope: "ExecutionScope | None" = None,
) -> RunOutcome:
    """Resume an INTERRUPTED run from its SqliteSaver checkpoint.

    Parameters
    ----------
    run_id
        The run to resume.
    actor
        The caller's identity. Must match the run's ``actor`` field.
    branch_lookup
        Callable ``(branch_def_id, branch_version) -> BranchDefinition | None``.
        Used to re-compile the exact branch version used in the original run.
    provider_call
        Optional provider callable; same semantics as ``execute_branch``.

    Returns a ``RunOutcome`` with the resumed run's ID (same as input ``run_id``).

    Raises ``ResumeError`` on auth failure, wrong status, missing checkpoint,
    or branch version mismatch.
    """
    run = get_run(base_path, run_id)
    if run is None:
        raise ResumeError(
            f"Run '{run_id}' not found.", reason="not_found",
        )
    if execution_scope is None:
        execution_scope = _execution_scope_for_run(base_path, run_id)

    # Auth gate: caller must own the run.
    if run["actor"] != actor:
        raise ResumeError(
            f"Actor '{actor}' does not own run '{run_id}' "
            f"(owned by '{run['actor']}').",
            reason="auth_failed",
        )

    current_status = run["status"]

    # Idempotency: already resumed → return the same run_id, no second resume.
    if current_status == RUN_STATUS_RESUMED:
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_RESUMED,
            output=run.get("output", {}), error="",
        )

    # Status gate: only INTERRUPTED can be resumed.
    if current_status != RUN_STATUS_INTERRUPTED:
        raise ResumeError(
            f"Run '{run_id}' is '{current_status}', not 'interrupted'. "
            f"Only interrupted runs can be resumed.",
            reason="not_interrupted",
            current_status=current_status,
        )

    # Checkpoint gate.
    thread_id = run.get("thread_id") or run_id
    if not _has_checkpoint(base_path, thread_id):
        if run.get("checkpoint_backend") == "memory":
            raise ResumeError(
                f"Run '{run_id}' used a memory-only checkpoint so private "
                "binding values were never written to durable storage. "
                "Bound runs cannot resume after restart; rerun from scratch "
                "with run_branch using the same inputs.",
                reason="bound_run_memory_only",
            )
        raise ResumeError(
            f"No SqliteSaver checkpoint found for run '{run_id}'. "
            "The run predates resume support or the checkpoint was evicted. "
            "Rerun from scratch with run_branch using the same inputs.",
            reason="no_checkpoint",
        )

    # Branch version gate: re-compile the exact version used in the original run.
    lineage = get_lineage(base_path, run_id)
    branch_version = int(
        (lineage or {}).get("branch_version")
        or getattr(branch_lookup, "_fallback_version", 1)
    )
    branch_def_id = run["branch_def_id"]
    branch = branch_lookup(branch_def_id, branch_version)
    if branch is None:
        raise ResumeError(
            f"Branch '{branch_def_id}' version {branch_version} no longer exists. "
            "Cannot resume — the branch was patched and that version was removed.",
            reason="branch_version_mismatch",
        )

    # Mark RESUMED immediately (before background work starts).
    update_run_status(base_path, run_id, status=RUN_STATUS_RESUMED)

    # Emit resume_started event.
    record_event(base_path, RunStepEvent(
        run_id=run_id,
        step_index=_PENDING_OFFSET,
        node_id="__resume__",
        status="resume_started",
        started_at=_now(),
        finished_at=_now(),
        detail={
            "resume_actor": actor,
            "resumed_at": _iso_now(),
        },
    ))

    # Background worker: re-invoke graph with None inputs to trigger resume.
    executor = _get_executor()

    def _resume_worker() -> RunOutcome:
        return _invoke_graph_resume(
            base_path,
            run_id=run_id,
            branch=branch,
            thread_id=thread_id,
            provider_call=provider_call,
            execution_scope=execution_scope,
        )

    future = executor.submit(_resume_worker)
    _track_future(run_id, future)

    return RunOutcome(
        run_id=run_id, status=RUN_STATUS_RESUMED,
        output={}, error="",
    )


def _invoke_graph_resume(
    base_path: str | Path,
    *,
    run_id: str,
    branch: BranchDefinition,
    thread_id: str,
    provider_call: Callable[..., str] | None,
    execution_scope: "ExecutionScope | None" = None,
) -> RunOutcome:
    """Authorize and pin a resumed run under its persisted tenant scope."""
    run = get_run(base_path, run_id)
    scope = _authoritative_execution_scope(base_path, run_id, execution_scope)
    invocation_depth, enqueue_context = _persisted_execution_context(run)
    universe_dir, block_reason = _scope_universe_dir(base_path, scope)
    if block_reason is not None:
        logger.error(
            "resume %s BLOCKED — refusing ambient credential execution: %s",
            run_id,
            block_reason,
        )
        update_run_status(
            base_path,
            run_id,
            status=RUN_STATUS_FAILED,
            error=block_reason,
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id,
            status=RUN_STATUS_FAILED,
            output={},
            error=block_reason,
        )

    from tinyassets.execution_context import pin_execution_universe

    with pin_execution_universe(universe_dir):
        return _invoke_graph_resume_inner(
            base_path,
            run_id=run_id,
            branch=branch,
            thread_id=thread_id,
            provider_call=provider_call,
            invocation_depth=invocation_depth,
            enqueue_context=enqueue_context,
            execution_scope=scope,
        )


def _invoke_graph_resume_inner(
    base_path: str | Path,
    *,
    run_id: str,
    branch: BranchDefinition,
    thread_id: str,
    provider_call: Callable[..., str] | None,
    invocation_depth: int = 0,
    enqueue_context: "NodeEnqueueContext | None" = None,
    execution_scope: "ExecutionScope | None" = None,
) -> RunOutcome:
    """Compile branch + invoke with None inputs to resume from checkpoint.

    ``execution_scope`` is the AUTHORITATIVE tenant scope (Codex S3 r20 #2) —
    ``None`` → UNKNOWN (fail closed) for a sandbox-required node on resume."""
    execution_cursor = {"step": 1000}  # offset so resume events don't collide
    provider_tracker: dict[str, Any] = {"last": None, "model": None, "calls": []}

    def _on_node(node_id: str, **detail: Any) -> None:
        phase = detail.pop("phase", "ran")
        step = execution_cursor["step"]
        execution_cursor["step"] += 1
        if phase == "ran":
            served = detail.get("provider_served")
            if served:
                provider_tracker["last"] = served
                model = detail.get("provider_model")
                if model:
                    provider_tracker["model"] = str(model)
                provider_tracker["calls"].append({
                    "node_id": node_id,
                    "provider": str(served),
                    "model": str(model or ""),
                    "latency_ms": detail.get("provider_latency_ms"),
                    "attempts": detail.get("provider_attempts"),
                    "degraded": bool(detail.get("provider_degraded", False)),
                    "at": _now(),
                })

        if phase == "starting":
            record_event(base_path, RunStepEvent(
                run_id=run_id,
                step_index=step + _PENDING_OFFSET,
                node_id=node_id,
                status=NODE_STATUS_RUNNING,
                started_at=_now(),
                detail=detail,
            ))
            return

        if phase == "failed":
            record_event(base_path, RunStepEvent(
                run_id=run_id,
                step_index=step + _PENDING_OFFSET,
                node_id=node_id,
                status=NODE_STATUS_FAILED,
                started_at=_now(),
                finished_at=_now(),
                detail=detail,
            ))
            return

        if is_cancel_requested(base_path, run_id):
            raise RunCancelledError(f"Run {run_id} cancelled during resume.")
        record_event(base_path, RunStepEvent(
            run_id=run_id,
            step_index=step + _PENDING_OFFSET,
            node_id=node_id,
            status=NODE_STATUS_RAN,
            started_at=_now(),
            finished_at=_now(),
            detail=detail,
        ))

    try:
        compiled = compile_branch(
            branch,
            provider_call=provider_call,
            event_sink=_on_node,
            base_path=base_path,
            parent_run_id=run_id,
            invocation_depth=invocation_depth,
            enqueue_context=enqueue_context,
            execution_scope=execution_scope,
        )
    except (UnapprovedNodeError, CompilerError) as exc:
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_FAILED,
            error=str(exc),
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_FAILED,
            output={}, error=str(exc),
        )

    update_run_status(base_path, run_id, status=RUN_STATUS_RUNNING)

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        saver_path = str(Path(base_path) / ".langgraph_runs.db")
        with SqliteSaver.from_conn_string(saver_path) as checkpointer:
            app = compiled.graph.compile(checkpointer=checkpointer)
            # None inputs triggers resume from last checkpoint.
            result = app.invoke(
                None,
                config={"configurable": {"thread_id": thread_id}},
            )
    except RunCancelledError as exc:
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_CANCELLED,
            error=str(exc),
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_CANCELLED,
            output={}, error=str(exc),
        )
    except Exception as exc:
        if _is_cancel_exception(exc):
            msg = f"Run {run_id} cancelled during resume."
            update_run_status(
                base_path, run_id,
                status=RUN_STATUS_CANCELLED,
                error=msg,
                finished_at=_now(),
            )
            return RunOutcome(
                run_id=run_id, status=RUN_STATUS_CANCELLED,
                output={}, error=msg,
            )
        msg = f"Resume execution failed: {exc}"
        update_run_status(
            base_path, run_id,
            status=RUN_STATUS_FAILED,
            error=msg,
            finished_at=_now(),
        )
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_FAILED,
            output={}, error=msg,
        )

    output = dict(result) if isinstance(result, dict) else {}
    # PR-122 Phase 1 — also fire external-write effectors on resume
    # completion so a re-run that finishes via resume_run still emits
    # declared PR sinks. Same no-raise contract as the primary path.
    _quarantine_branch_authored_external_write_keys(output)
    external_write_evidence = _run_external_write_effectors(
        branch,
        output,
        base_path=_effector_base_path(base_path, execution_scope),
        run_id=run_id,
    )
    if external_write_evidence:
        # System-authoritative receipt — overwrite unconditionally
        # (see start_run for the rationale + Codex finding #2).
        output["external_write_results"] = external_write_evidence
        errors = _collect_external_write_errors(external_write_evidence)
        if errors:
            output["external_write_errors"] = errors
    update_run_status(
        base_path, run_id,
        status=RUN_STATUS_COMPLETED,
        output=output,
        finished_at=_now(),
        provider_used=provider_tracker["last"],
        model=provider_tracker["model"],
    )
    return RunOutcome(
        run_id=run_id, status=RUN_STATUS_COMPLETED,
        output=output, error="",
    )


def recover_in_flight_runs(base_path: str | Path) -> int:
    """Mark any ``queued`` or ``running`` rows as ``interrupted``.

    Called at TinyAssets Server startup to clean up runs that were in
    flight when the server died. Returns the number of rows updated.

    v1 contract: ``interrupted`` is terminal. Callers rerun with the
    same ``inputs_json`` to continue; the MCP surface exposes this via
    ``get_run.resumable=false`` (see ``_compose_run_snapshot``). Mid-run
    resume via SqliteSaver checkpoint + thread_id is a future extension
    — not available today. Hard-rule #8 (fail loudly) is satisfied by
    the descriptive error field + terminal status; do not silently
    drop interrupted runs or loop a poll expecting them to re-run.
    """
    initialize_runs_db(base_path)
    now = _now()
    with _connect(base_path) as conn:
        cursor = conn.execute(
            """
            UPDATE runs
            SET status = ?, error = ?, finished_at = ?
            WHERE status IN (?, ?)
            """,
            (
                RUN_STATUS_INTERRUPTED,
                "Server restarted while this run was in flight.",
                now,
                RUN_STATUS_QUEUED, RUN_STATUS_RUNNING,
            ),
        )
        count = cursor.rowcount
    if count:
        logger.info("Recovered %d in-flight runs as 'interrupted'", count)
    return count


# Step indices higher than the count of pending events are reserved for
# the executed events, so the two event streams don't collide on
# (run_id, step_index) primary keys.
_PENDING_OFFSET = 1_000_000


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Presentation helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def build_node_status_map(
    events: list[dict[str, Any]],
    declared_order: list[str],
) -> list[dict[str, Any]]:
    """Fold the raw event stream into a per-node status list.

    Later events dominate earlier ones: a node seen as ``ran`` wins over
    its earlier ``pending`` row. This is the shape Claude.ai visualises
    to auto-build a state diagram.
    """
    statuses: dict[str, str] = {nid: NODE_STATUS_PENDING for nid in declared_order}
    for ev in events:
        node_id = ev.get("node_id", "")
        if not node_id:
            continue
        statuses.setdefault(node_id, NODE_STATUS_PENDING)
        current = statuses[node_id]
        incoming = ev.get("status", NODE_STATUS_PENDING)
        # ran/failed trump running which trumps pending
        priority = {
            NODE_STATUS_PENDING: 0,
            NODE_STATUS_RUNNING: 1,
            NODE_STATUS_RAN: 2,
            NODE_STATUS_FAILED: 2,
        }
        if priority.get(incoming, 0) >= priority.get(current, 0):
            statuses[node_id] = incoming
    # Preserve declared order, then append any out-of-order nodes.
    ordered_ids = list(declared_order)
    for nid in statuses:
        if nid not in ordered_ids:
            ordered_ids.append(nid)
    return [
        {"node_id": nid, "status": statuses[nid]}
        for nid in ordered_ids
    ]


_VALID_STATUSES = frozenset({
    RUN_STATUS_QUEUED, RUN_STATUS_RUNNING, RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED, RUN_STATUS_CANCELLED, RUN_STATUS_INTERRUPTED,
})
_VALID_AGGREGATES = frozenset({"count", "mean", "sum", "rate"})
_MAX_QUERY_LIMIT = 1000
_DEFAULT_QUERY_LIMIT = 100


def query_runs(
    base_path: str | Path,
    *,
    branch_def_id: str = "",
    filters: dict[str, Any] | None = None,
    select: list[str] | None = None,
    aggregate: dict[str, Any] | None = None,
    limit: int = _DEFAULT_QUERY_LIMIT,
    row_filter: Callable[[Any], bool] | None = None,
) -> dict[str, Any]:
    """Query runs table with optional field projection + simple aggregation.

    Spec: docs/vetted-specs.md §Cross-run state query primitive.

    Returns:
        {"rows": [...], "count": N} for plain queries.
        {"aggregated": [...], "count": N, "group_by": field, "agg_op": op}
        for aggregate queries.

    Invariants:
        - INTERRUPTED runs excluded from aggregation unless status filter
          explicitly includes them.
        - limit default 100, max 1000.
        - select fields extracted from output_json via JSON path.
        - aggregate.fn in {"count", "mean", "sum", "rate"}.
    """
    initialize_runs_db(base_path)
    filters = filters or {}
    select = select or []
    limit = min(max(1, limit), _MAX_QUERY_LIMIT)

    clauses: list[str] = []
    params: list[Any] = []

    if branch_def_id:
        clauses.append("branch_def_id = ?")
        params.append(branch_def_id)

    if "status" in filters:
        status_val = filters["status"]
        if isinstance(status_val, list):
            placeholders = ",".join("?" * len(status_val))
            clauses.append(f"status IN ({placeholders})")
            params.extend(status_val)
        else:
            clauses.append("status = ?")
            params.append(status_val)

    if "actor" in filters:
        clauses.append("actor = ?")
        params.append(filters["actor"])

    if "since" in filters:
        clauses.append("started_at >= ?")
        params.append(float(filters["since"]))

    if "until" in filters:
        clauses.append("started_at <= ?")
        params.append(float(filters["until"]))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect(base_path) as conn:
        rows = conn.execute(
            f"SELECT run_id, branch_def_id, status, actor, "
            f"started_at, finished_at, output_json "
            f"FROM runs {where} "
            f"ORDER BY started_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()

    # Apply the caller's row-level access filter BEFORE any projection or
    # aggregation, so a denied universe's runs never contribute to selected
    # fields or aggregate values (security: no leak via select/aggregate).
    if row_filter is not None:
        rows = [r for r in rows if row_filter(r)]

    def _extract_fields(output_str: str, fields: list[str]) -> dict[str, Any]:
        try:
            state = json.loads(output_str) if output_str else {}
        except (json.JSONDecodeError, TypeError):
            state = {}
        if not fields:
            return {}
        return {f: state.get(f) for f in fields}

    _RUN_COLUMNS = frozenset({
        "run_id", "branch_def_id", "status", "actor", "started_at", "finished_at",
    })

    def _row_value(r: Any, field: str) -> Any:
        if field in _RUN_COLUMNS:
            return r[field]
        try:
            state = json.loads(r["output_json"]) if r["output_json"] else {}
        except (json.JSONDecodeError, TypeError):
            state = {}
        return state.get(field)

    if aggregate:
        group_by = aggregate.get("group_by", "")
        agg_op = aggregate.get("fn", aggregate.get("op", "count"))
        agg_field = aggregate.get("field", "")

        groups: dict[Any, list[Any]] = {}
        for r in rows:
            gv = _row_value(r, group_by) if group_by else "_all"
            av = _row_value(r, agg_field) if agg_field else 1.0
            groups.setdefault(gv, []).append(av)

        def _agg(values: list[Any], op: str) -> Any:
            nums = [v for v in values if isinstance(v, (int, float))]
            if op == "count":
                return len(values)
            if op == "sum":
                return sum(nums) if nums else 0
            if op == "mean":
                return sum(nums) / len(nums) if nums else None
            if op == "rate":
                total = len(rows) if rows else 1
                return len(values) / total if total else None
            return len(values)

        aggregated = [
            {"group": gv, "value": _agg(vals, agg_op), "n": len(vals)}
            for gv, vals in sorted(groups.items(), key=lambda kv: str(kv[0]))
        ]
        return {
            "aggregated": aggregated,
            "count": len(aggregated),
            "group_by": group_by,
            "agg_op": agg_op,
        }

    result_rows = []
    for r in rows:
        row_dict: dict[str, Any] = {
            "run_id": r["run_id"],
            "branch_def_id": r["branch_def_id"],
            "status": r["status"],
            "actor": r["actor"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
        }
        if select:
            row_dict["fields"] = _extract_fields(r["output_json"], select)
        result_rows.append(row_dict)

    return {"rows": result_rows, "count": len(result_rows)}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Sub-branch invocation helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

#: Maximum nesting depth for invoke_branch nodes. A child run increments
#: the depth counter; reaching this cap raises CompilerError at runtime.
MAX_INVOKE_BRANCH_DEPTH = 5

_TERMINAL_STATUSES = frozenset({
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_INTERRUPTED,
})


def poll_child_run_status(
    base_path: str | Path,
    run_id: str,
    *,
    timeout_seconds: float = 300.0,
    poll_interval: float = 1.0,
) -> dict[str, Any]:
    """Block until *run_id* reaches a terminal status or *timeout_seconds* elapses.

    Returns the run record dict (same shape as ``get_run``).
    Raises ``TimeoutError`` if the run does not terminate in time.
    Raises ``KeyError`` if the run does not exist at poll time.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        record = get_run(base_path, run_id)
        if record is None:
            raise KeyError(f"Child run '{run_id}' not found in runs DB.")
        if record.get("status") in _TERMINAL_STATUSES:
            return record
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ChildRunAwaitTimeout(
                f"await_branch_run: child run '{run_id}' did not complete "
                f"within {timeout_seconds}s.",
                run_id=run_id,
                child_status=str(record.get("status") or ""),
                child_branch_def_id=str(record.get("branch_def_id") or ""),
                timeout_seconds=timeout_seconds,
            )
        time.sleep(min(poll_interval, remaining))


# â”€â”€â”€ Teammate messaging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_VALID_MESSAGE_TYPES = frozenset({
    "request", "response", "broadcast",
    "plan_approval_request", "plan_approval_response",
    "shutdown_request", "shutdown_response",
})


def post_teammate_message(
    base_path: str | Path,
    *,
    from_run_id: str,
    to_node_id: str,
    message_type: str,
    body: dict[str, Any],
    reply_to_id: str | None = None,
) -> dict[str, Any]:
    """Insert a teammate message. Returns the stored message record."""
    import uuid
    from datetime import datetime, timezone

    if not from_run_id:
        raise ValueError("from_run_id is required.")
    if not to_node_id:
        raise ValueError("to_node_id is required.")
    if message_type not in _VALID_MESSAGE_TYPES:
        raise ValueError(
            f"Unknown message_type {message_type!r}; "
            f"valid: {sorted(_VALID_MESSAGE_TYPES)}"
        )
    try:
        body_json = json.dumps(body)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"body must be JSON-serializable: {exc}") from exc

    run_record = get_run(base_path, from_run_id)
    if run_record is None:
        raise KeyError(f"from_run_id '{from_run_id}' not found in runs DB.")

    message_id = str(uuid.uuid4())
    sent_at = datetime.now(timezone.utc).isoformat()

    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        conn.execute(
            """
            INSERT INTO teammate_messages
                (message_id, from_run_id, to_node_id, message_type,
                 body_json, reply_to_id, sent_at, acked)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (message_id, from_run_id, to_node_id, message_type,
             body_json, reply_to_id, sent_at),
        )
    return {
        "message_id": message_id,
        "from_run_id": from_run_id,
        "to_node_id": to_node_id,
        "message_type": message_type,
        "body": body,
        "reply_to_id": reply_to_id,
        "sent_at": sent_at,
        "acked": False,
    }


def read_teammate_messages(
    base_path: str | Path,
    *,
    node_id: str = "",
    since: str | None = None,
    message_types: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return messages for node_id (or all if node_id is empty/broadcast)."""
    initialize_runs_db(base_path)
    clauses: list[str] = []
    params: list[Any] = []

    if node_id:
        clauses.append("(to_node_id = ? OR to_node_id = '*')")
        params.append(node_id)
    if since:
        clauses.append("sent_at >= ?")
        params.append(since)
    if message_types:
        placeholders = ",".join("?" * len(message_types))
        clauses.append(f"message_type IN ({placeholders})")
        params.extend(message_types)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit = min(max(1, limit), 1000)

    with _connect(base_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM teammate_messages {where} "
            f"ORDER BY sent_at ASC LIMIT ?",
            [*params, limit],
        ).fetchall()

    results = []
    for r in rows:
        try:
            body = json.loads(r["body_json"])
        except (json.JSONDecodeError, TypeError):
            body = {}
        results.append({
            "message_id": r["message_id"],
            "from_run_id": r["from_run_id"],
            "to_node_id": r["to_node_id"],
            "message_type": r["message_type"],
            "body": body,
            "reply_to_id": r["reply_to_id"],
            "sent_at": r["sent_at"],
            "acked": bool(r["acked"]),
        })
    return results


def ack_teammate_message(
    base_path: str | Path,
    *,
    message_id: str,
    node_id: str,
) -> dict[str, Any]:
    """Mark message as acked. Idempotent. Returns acked_at timestamp."""
    from datetime import datetime, timezone

    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM teammate_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"message_id '{message_id}' not found.")
        if row["to_node_id"] != node_id and row["to_node_id"] != "*":
            raise PermissionError(
                f"node_id '{node_id}' cannot ack message addressed to "
                f"'{row['to_node_id']}'."
            )
        acked_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE teammate_messages SET acked = 1 WHERE message_id = ?",
            (message_id,),
        )
    return {"message_id": message_id, "acked_at": acked_at}


_ROUTING_EVIDENCE_CAVEAT = (
    "provider_used is populated for runs that used the policy router; "
    "token_count and model are not yet collected (no LLM billing hooks). "
    "latency_ms is derived from started_at / finished_at timestamps."
)

_ROUTING_EVIDENCE_LIMIT_CAP = 50
_ROUTING_EVIDENCE_DEFAULT_LIMIT = 10


# BUG-029: canonical failure_class → actionable_by mapping.
# Imported by `tinyassets.universe_server` so both run-failure classifiers
# (typed-exception path + string-pattern path + this list_recent_runs
# path) emit the same `actionable_by` for the same failure_class.
#
# Values:
#   "host"    — server operator must act (creds, binaries, approvals).
#   "chatbot" — chatbot can fix via another tool call (switch llm_type,
#               raise recursion_limit, retry, republish version).
#   "user"    — chatbot can only escalate raw error to the human user;
#               human judgment may identify a recovery.
#   "none"    — terminal: no fix exists, outcome is final. Chatbot must
#               NOT suggest retry or escalate to user — the run is dead
#               by design (e.g. cancelled by request).
#
# A failure_class missing from this map gets `actionable_by="user"` —
# safe-default escalate, never silently drop the field. Use "none"
# explicitly when the failure is genuinely unrecoverable; the default
# is a conservative "ask the human."
ACTIONABLE_BY: dict[str, str] = {
    # host — server-side configuration / credentials / binaries
    "empty_llm_response": "host",
    "provider_unavailable": "host",
    "provider_subprocess_failed": "host",
    "provider_exhausted": "host",
    "sandbox_unavailable": "host",
    "node_not_approved": "host",
    "permission_denied:approval_required": "host",
    "permission_denied:auth_expired": "host",
    # chatbot — recoverable via another tool call
    "quota_exhausted": "chatbot",
    "provider_overloaded": "chatbot",
    "provider_error": "chatbot",
    "recursion_limit": "chatbot",
    "timeout": "chatbot",
    "context_length_exceeded": "chatbot",
    "state_mutation_conflict": "chatbot",
    "compile_error": "chatbot",
    "snapshot_schema_drift": "chatbot",
    "interrupted": "chatbot",
    "child_receipt_waiting": "chatbot",
    # user — opaque/internal; chatbot escalates raw error for human judgment
    "unknown": "user",
    "error": "user",
    # none — terminal by design; no fix exists, no escalation needed
    "cancelled": "none",
}


_EMPTY_LLM_RESPONSE_ACTION = (
    "Ask the host to check get_status provider availability/cooldowns and fix "
    "provider credentials or CLI, then rerun; only switch llm_type if get_status "
    "shows another provider available."
)


def _classify_failure(run: dict) -> str:
    """Return a short failure class string from a run record."""
    error = run.get("error") or ""
    status = run.get("status", "")
    if status == RUN_STATUS_CANCELLED:
        return "cancelled"
    if status == RUN_STATUS_INTERRUPTED:
        output = run.get("output") or {}
        if isinstance(output, dict):
            gate = output.get("child_invocation_receipt_gate")
            if isinstance(gate, dict) and gate.get("status") == "receipt_waiting":
                return "child_receipt_waiting"
        return "interrupted"
    if not error:
        return ""
    lower = error.lower()
    if "empty" in lower and ("llm" in lower or "response" in lower or "provider" in lower):
        return "empty_llm_response"
    if "timeout" in lower:
        return "timeout"
    if "exhausted" in lower or "cooldown" in lower:
        return "provider_exhausted"
    if "sandbox" in lower or "bwrap" in lower:
        return "sandbox_unavailable"
    return "error"


def _routing_evidence_text(run: dict, latency_ms: float | None) -> str:
    """Render a 1-line chatbot-legible summary for a run record."""
    rid = run.get("run_id", "?")
    status = run.get("status", "?")
    bid = run.get("branch_def_id", "?")
    if latency_ms is not None:
        lat = f"{latency_ms / 1000:.2f}s"
        return f"{rid} — {status} in {lat} on {bid}"
    return f"{rid} — {status} on {bid}"


def list_recent_runs(
    base_path: str | Path,
    *,
    branch_def_id: str = "",
    limit: int = _ROUTING_EVIDENCE_DEFAULT_LIMIT,
) -> list[dict]:
    """Return last-N run records shaped for the get_routing_evidence MCP action.

    Each record includes derived ``latency_ms`` (from timestamps), a
    ``failure_class`` label, a ``suggested_action`` hint, and a ``caveat``
    noting absent provider/token fields. Limit is capped at
    ``_ROUTING_EVIDENCE_LIMIT_CAP`` to prevent token blowout.
    """
    effective_limit = min(max(1, int(limit)), _ROUTING_EVIDENCE_LIMIT_CAP)
    raw = list_runs(base_path, branch_def_id=branch_def_id, limit=effective_limit)

    results: list[dict] = []
    for run in raw:
        started = run.get("started_at")
        finished = run.get("finished_at")
        latency_ms: float | None = None
        if started is not None and finished is not None:
            try:
                # started_at / finished_at may be Unix float or ISO string.
                def _to_float(v: object) -> float | None:
                    if isinstance(v, (int, float)):
                        return float(v)
                    s = str(v)
                    if "T" in s:
                        from datetime import datetime as _dt
                        try:
                            return _dt.fromisoformat(s).timestamp()
                        except ValueError:
                            return _dt.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
                    try:
                        return float(s)
                    except ValueError:
                        return None
                s_ts = _to_float(started)
                f_ts = _to_float(finished)
                if s_ts is not None and f_ts is not None:
                    latency_ms = (f_ts - s_ts) * 1000
            except Exception:  # noqa: BLE001 — best-effort
                pass

        failure_class = _classify_failure(run)
        suggested_action = ""
        if failure_class == "empty_llm_response":
            suggested_action = _EMPTY_LLM_RESPONSE_ACTION
        elif failure_class == "provider_exhausted":
            suggested_action = "Wait for provider cooldown or add an alternative provider."
        elif failure_class == "timeout":
            suggested_action = "Increase node timeout or simplify the prompt."
        elif failure_class == "sandbox_unavailable":
            suggested_action = "Enable unprivileged user namespaces or run on a bwrap-capable host."
        elif failure_class == "cancelled":
            suggested_action = "Run was cancelled by request."
        elif failure_class == "interrupted":
            suggested_action = "Run was interrupted; use resume_run to continue."
        elif failure_class == "child_receipt_waiting":
            suggested_action = (
                "Wait for the child run to complete, then call "
                "attach_existing_child_run with the recorded child_run_id."
            )
        elif failure_class == "error":
            suggested_action = "Check error field for details; re-run after fixing root cause."

        results.append({
            "text": _routing_evidence_text(run, latency_ms),
            "run_id": run.get("run_id"),
            "branch_def_id": run.get("branch_def_id"),
            "run_name": run.get("run_name"),
            "status": run.get("status"),
            "actor": run.get("actor"),
            "started_at": started,
            "finished_at": finished,
            "latency_ms": latency_ms,
            "error": run.get("error"),
            "last_node_id": run.get("last_node_id"),
            "failure_class": failure_class,
            "suggested_action": suggested_action,
            # Empty failure_class → empty actionable_by (run wasn't a
            # failure). Otherwise look it up; default to "user" for any
            # class not in the table so the field is never silently
            # dropped.
            "actionable_by": (
                ACTIONABLE_BY.get(failure_class, "user") if failure_class else ""
            ),
            "provider_used": run.get("provider_used"),
            "token_count": run.get("token_count"),
            "caveat": _ROUTING_EVIDENCE_CAVEAT,
        })

    return results


__all__ = [
    "RUN_STATUS_QUEUED",
    "RUN_STATUS_RUNNING",
    "RUN_STATUS_COMPLETED",
    "RUN_STATUS_FAILED",
    "RUN_STATUS_CANCELLED",
    "RUN_STATUS_INTERRUPTED",
    "NODE_STATUS_PENDING",
    "NODE_STATUS_RUNNING",
    "NODE_STATUS_RAN",
    "NODE_STATUS_FAILED",
    "NODE_STATUS_SKIPPED",
    "ACTIONABLE_BY",
    "ChildRunAttachmentError",
    "ChildRunAwaitTimeout",
    "RunCancelledError",
    "RunOutcome",
    "RunStepEvent",
    "VALID_RECEIPT_TYPES",
    # Phase 4 storage helpers
    "add_judgment",
    "attach_existing_child_run",
    "build_node_status_map",
    "create_run",
    "execute_branch",
    "execute_branch_async",
    "execute_claimed_branch_request",
    "execute_next_review_decision_effect",
    "execute_pending_review_decisions",
    "find_node_snapshot",
    "get_future",
    "get_lineage",
    "get_run",
    "initialize_runs_db",
    "is_cancel_requested",
    "latest_terminal_run",
    "list_events",
    "list_judgments",
    "list_node_edit_audits",
    "list_run_receipts",
    "list_runs",
    "latest_run_by_name",
    "list_recent_runs",
    "node_output_from_run",
    "record_event",
    "record_lineage",
    "record_node_edit_audit",
    "record_run_receipt",
    "recover_in_flight_runs",
    "request_cancel",
    "resolve_review_revision_request",
    "runs_db_path",
    "shutdown_executor",
    "update_run_status",
    "wait_for",
    "query_runs",
    "poll_child_run_status",
    "MAX_INVOKE_BRANCH_DEPTH",
    "post_teammate_message",
    "read_teammate_messages",
    "ack_teammate_message",
]
