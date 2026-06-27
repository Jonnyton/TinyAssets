"""Node performance tracking and auto-promotion.

Tracks how user-contributed nodes perform over time and enables
the graph to evolve: good nodes get promoted, weak nodes get flagged
or pruned.

This is the mechanism by which the LangGraph learns through collective
use. Users contribute nodes → the system measures outcomes → the best
workflows emerge from data, not central design.

Metrics tracked per node per execution:
  - success/failure
  - execution duration
  - output quality (when downstream eval scores are available)
  - crash rate
  - timeout rate

Promotion rules:
  - Nodes start as "trial" (approved but unproven)
  - After N successful executions with positive eval signal → "promoted"
  - Promoted nodes run by default in their declared phase
  - Nodes with high failure rate → "flagged" for review
  - Host can override any state: promote, demote, disable

The eval layer is deliberately simple for V1. It tracks what we can
observe (success, timing, crashes) and creates hooks for richer
evaluation signals from the existing editorial eval system.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("universe_server.node_eval")


# ═══════════════════════════════════════════════════════════════════════════
# Node Status Levels
# ═══════════════════════════════════════════════════════════════════════════

class NodeStatus:
    """Status levels for registered nodes."""

    PENDING = "pending"          # Registered, awaiting host approval
    TRIAL = "trial"              # Approved, collecting performance data
    PROMOTED = "promoted"        # Proven reliable, runs by default
    FLAGGED = "flagged"          # High failure rate, needs review
    DISABLED = "disabled"        # Manually disabled by host
    REMOVED = "removed"          # Soft-deleted


# ═══════════════════════════════════════════════════════════════════════════
# Execution Record
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ExecutionRecord:
    """Record of a single node execution."""

    node_id: str
    universe_id: str
    success: bool
    duration_seconds: float
    error: str = ""
    eval_score: float | None = None  # From downstream eval, if available
    eval_notes: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "universe_id": self.universe_id,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "eval_score": self.eval_score,
            "eval_notes": self.eval_notes,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Node Stats (computed view)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class NodeStats:
    """Computed performance statistics for a node."""

    node_id: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    timeout_count: int = 0
    avg_duration: float = 0.0
    avg_eval_score: float | None = None
    success_rate: float = 0.0
    current_status: str = NodeStatus.PENDING
    last_execution: float | None = None
    promotion_eligible: bool = False
    flag_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": round(self.success_rate, 3),
            "avg_duration": round(self.avg_duration, 3),
            "avg_eval_score": (
                round(self.avg_eval_score, 3)
                if self.avg_eval_score is not None
                else None
            ),
            "current_status": self.current_status,
            "promotion_eligible": self.promotion_eligible,
            "flag_eligible": self.flag_eligible,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Promotion / Flagging Thresholds
# ═══════════════════════════════════════════════════════════════════════════

# These are starting values. They should be tuned based on actual data.
# The system should trend toward less prescriptive thresholds over time.

PROMOTION_MIN_EXECUTIONS = 10      # Need at least this many runs
PROMOTION_MIN_SUCCESS_RATE = 0.85  # 85%+ success rate
PROMOTION_MIN_EVAL_SCORE = 0.6    # If eval scores exist, they should be positive

FLAGGING_MIN_EXECUTIONS = 5        # Don't flag too early
FLAGGING_MAX_SUCCESS_RATE = 0.5    # Below 50% success → flag
FLAGGING_MAX_CONSECUTIVE_FAILURES = 3  # 3 failures in a row → flag


# ═══════════════════════════════════════════════════════════════════════════
# Node Evaluator
# ═══════════════════════════════════════════════════════════════════════════


class NodeEvaluator:
    """Tracks node performance and manages promotion/flagging.

    SQLite-backed for durability. One database per server instance,
    shared across all universes.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            # Route through the canonical resolver so container deploys
            # get $TINYASSETS_DATA_DIR/.node_eval.db instead of the
            # CWD-relative ``output/.node_eval.db``. See
            # tinyassets.storage.data_dir for precedence semantics.
            from tinyassets.storage import data_dir
            db_path = data_dir() / ".node_eval.db"
        self._db_path = Path(db_path)
        self._initialize_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS node_executions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id         TEXT NOT NULL,
                universe_id     TEXT NOT NULL DEFAULT '',
                success         INTEGER NOT NULL,
                duration_seconds REAL NOT NULL DEFAULT 0,
                error           TEXT NOT NULL DEFAULT '',
                eval_score      REAL,
                eval_notes      TEXT NOT NULL DEFAULT '',
                timestamp       REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_executions_node
                ON node_executions(node_id);
            CREATE INDEX IF NOT EXISTS idx_executions_timestamp
                ON node_executions(timestamp);

            CREATE TABLE IF NOT EXISTS node_status (
                node_id         TEXT PRIMARY KEY,
                status          TEXT NOT NULL DEFAULT 'pending',
                promoted_at     REAL,
                flagged_at      REAL,
                flag_reason     TEXT NOT NULL DEFAULT '',
                override_by     TEXT NOT NULL DEFAULT '',
                updated_at      REAL NOT NULL
            );
        """)
        conn.commit()
        conn.close()
        logger.info("Node eval database initialized at %s", self._db_path)

    # --- Record execution ---

    def record(self, execution: ExecutionRecord) -> None:
        """Record a node execution result."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO node_executions "
                "(node_id, universe_id, success, duration_seconds, "
                " error, eval_score, eval_notes, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    execution.node_id,
                    execution.universe_id,
                    1 if execution.success else 0,
                    execution.duration_seconds,
                    execution.error,
                    execution.eval_score,
                    execution.eval_notes,
                    execution.timestamp,
                ),
            )
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

            # Check if status should change
            self._check_transitions(conn, execution.node_id)
        finally:
            conn.close()

    # --- Stats ---

    def get_stats(self, node_id: str) -> NodeStats:
        """Get computed performance statistics for a node."""
        conn = self._connect()
        try:
            # Execution counts
            row = conn.execute(
                "SELECT "
                "  COUNT(*) as total, "
                "  SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes, "
                "  SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures, "
                "  AVG(duration_seconds) as avg_dur, "
                "  AVG(CASE WHEN eval_score IS NOT NULL THEN eval_score END) as avg_eval, "
                "  MAX(timestamp) as last_exec "
                "FROM node_executions WHERE node_id = ?",
                (node_id,),
            ).fetchone()

            total = row["total"] or 0
            successes = row["successes"] or 0
            failures = row["failures"] or 0

            # Timeout count (heuristic: error contains "timed out")
            timeout_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM node_executions "
                "WHERE node_id = ? AND error LIKE '%timed out%'",
                (node_id,),
            ).fetchone()
            timeouts = timeout_row["cnt"] if timeout_row else 0

            # Current status
            status_row = conn.execute(
                "SELECT status FROM node_status WHERE node_id = ?",
                (node_id,),
            ).fetchone()
            current_status = status_row["status"] if status_row else NodeStatus.PENDING

            success_rate = successes / total if total > 0 else 0.0
            avg_eval = row["avg_eval"] if row["avg_eval"] is not None else None

            # Check eligibility
            promotion_eligible = (
                total >= PROMOTION_MIN_EXECUTIONS
                and success_rate >= PROMOTION_MIN_SUCCESS_RATE
                and current_status in (NodeStatus.TRIAL, NodeStatus.FLAGGED)
                and (avg_eval is None or avg_eval >= PROMOTION_MIN_EVAL_SCORE)
            )

            flag_eligible = (
                total >= FLAGGING_MIN_EXECUTIONS
                and success_rate <= FLAGGING_MAX_SUCCESS_RATE
                and current_status in (NodeStatus.TRIAL, NodeStatus.PROMOTED)
            )

            return NodeStats(
                node_id=node_id,
                total_executions=total,
                successful_executions=successes,
                failed_executions=failures,
                timeout_count=timeouts,
                avg_duration=row["avg_dur"] or 0.0,
                avg_eval_score=avg_eval,
                success_rate=success_rate,
                current_status=current_status,
                last_execution=row["last_exec"],
                promotion_eligible=promotion_eligible,
                flag_eligible=flag_eligible,
            )
        finally:
            conn.close()

    # --- Status transitions ---

    def _check_transitions(self, conn: sqlite3.Connection, node_id: str) -> None:
        """Check and apply automatic status transitions."""
        stats = self._compute_stats_from_conn(conn, node_id)
        if stats is None:
            return

        current = self._get_status(conn, node_id)

        new_status = None
        reason = ""

        # Auto-promote
        if (
            current == NodeStatus.TRIAL
            and stats["total"] >= PROMOTION_MIN_EXECUTIONS
            and stats["success_rate"] >= PROMOTION_MIN_SUCCESS_RATE
        ):
            avg_eval = stats.get("avg_eval")
            if avg_eval is None or avg_eval >= PROMOTION_MIN_EVAL_SCORE:
                new_status = NodeStatus.PROMOTED
                reason = (
                    f"Auto-promoted: {stats['total']} executions, "
                    f"{stats['success_rate']:.0%} success rate"
                )

        # Auto-flag
        if (
            current in (NodeStatus.TRIAL, NodeStatus.PROMOTED)
            and stats["total"] >= FLAGGING_MIN_EXECUTIONS
            and stats["success_rate"] <= FLAGGING_MAX_SUCCESS_RATE
        ):
            new_status = NodeStatus.FLAGGED
            reason = (
                f"Auto-flagged: {stats['success_rate']:.0%} success rate "
                f"over {stats['total']} executions"
            )

        # Check consecutive failures
        if current in (NodeStatus.TRIAL, NodeStatus.PROMOTED):
            recent = conn.execute(
                "SELECT success FROM node_executions "
                "WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
                (node_id, FLAGGING_MAX_CONSECUTIVE_FAILURES),
            ).fetchall()
            if (
                len(recent) >= FLAGGING_MAX_CONSECUTIVE_FAILURES
                and all(r["success"] == 0 for r in recent)
            ):
                new_status = NodeStatus.FLAGGED
                reason = (
                    f"Auto-flagged: {FLAGGING_MAX_CONSECUTIVE_FAILURES} "
                    f"consecutive failures"
                )

        if new_status and new_status != current:
            self._set_status(conn, node_id, new_status, reason)
            logger.info(
                "Node %s: %s → %s (%s)", node_id, current, new_status, reason,
            )

    def _compute_stats_from_conn(
        self, conn: sqlite3.Connection, node_id: str,
    ) -> dict[str, Any] | None:
        """Compute basic stats using an existing connection."""
        row = conn.execute(
            "SELECT "
            "  COUNT(*) as total, "
            "  SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes, "
            "  AVG(CASE WHEN eval_score IS NOT NULL THEN eval_score END) as avg_eval "
            "FROM node_executions WHERE node_id = ?",
            (node_id,),
        ).fetchone()

        if not row or row["total"] == 0:
            return None

        total = row["total"]
        successes = row["successes"] or 0
        return {
            "total": total,
            "successes": successes,
            "success_rate": successes / total,
            "avg_eval": row["avg_eval"],
        }

    def _get_status(self, conn: sqlite3.Connection, node_id: str) -> str:
        """Get current status from DB."""
        row = conn.execute(
            "SELECT status FROM node_status WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        return row["status"] if row else NodeStatus.PENDING

    def _set_status(
        self,
        conn: sqlite3.Connection,
        node_id: str,
        status: str,
        reason: str = "",
        override_by: str = "",
    ) -> None:
        """Set node status in DB."""
        now = time.time()
        conn.execute(
            "INSERT INTO node_status (node_id, status, flag_reason, override_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET "
            "  status = excluded.status, "
            "  flag_reason = CASE WHEN excluded.status = 'flagged' "
            "    THEN excluded.flag_reason ELSE flag_reason END, "
            "  promoted_at = CASE WHEN excluded.status = 'promoted' "
            "    THEN ? ELSE promoted_at END, "
            "  flagged_at = CASE WHEN excluded.status = 'flagged' "
            "    THEN ? ELSE flagged_at END, "
            "  override_by = excluded.override_by, "
            "  updated_at = excluded.updated_at",
            (node_id, status, reason, override_by, now, now, now),
        )
        conn.commit()

    # --- Host overrides ---

    def set_status(
        self,
        node_id: str,
        status: str,
        reason: str = "",
        by: str = "host",
    ) -> None:
        """Manually set a node's status (host override)."""
        conn = self._connect()
        try:
            self._set_status(conn, node_id, status, reason, override_by=by)
            logger.info("Node %s manually set to %s by %s", node_id, status, by)
        finally:
            conn.close()

    # --- Queries ---

    def get_promoted_nodes(self) -> list[str]:
        """Get all promoted node IDs."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT node_id FROM node_status WHERE status = ?",
                (NodeStatus.PROMOTED,),
            ).fetchall()
            return [r["node_id"] for r in rows]
        finally:
            conn.close()

    def get_trial_nodes(self) -> list[str]:
        """Get all trial node IDs (approved, collecting data)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT node_id FROM node_status WHERE status = ?",
                (NodeStatus.TRIAL,),
            ).fetchall()
            return [r["node_id"] for r in rows]
        finally:
            conn.close()

    def get_flagged_nodes(self) -> list[str]:
        """Get all flagged node IDs (need review)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT node_id, flag_reason FROM node_status WHERE status = ?",
                (NodeStatus.FLAGGED,),
            ).fetchall()
            return [{"node_id": r["node_id"], "reason": r["flag_reason"]} for r in rows]
        finally:
            conn.close()

    def get_execution_history(
        self,
        node_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent execution history for a node."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM node_executions "
                "WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
                (node_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_leaderboard(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get top-performing nodes ranked by success rate and volume.

        This is the public-facing view of which nodes are working.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT "
                "  e.node_id, "
                "  COUNT(*) as total, "
                "  SUM(CASE WHEN e.success = 1 THEN 1 ELSE 0 END) as successes, "
                "  ROUND(AVG(e.duration_seconds), 3) as avg_duration, "
                "  ROUND(CAST(SUM(CASE WHEN e.success = 1 THEN 1 ELSE 0 END) "
                "    AS REAL) / COUNT(*), 3) as success_rate, "
                "  COALESCE(s.status, 'pending') as status "
                "FROM node_executions e "
                "LEFT JOIN node_status s ON e.node_id = s.node_id "
                "GROUP BY e.node_id "
                "ORDER BY success_rate DESC, total DESC "
                "LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
