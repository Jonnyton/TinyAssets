"""Scheduled and event-triggered branch invocation.

Spec: docs/vetted-specs.md §Scheduled + event-triggered branch invocation.

Two primitives:
  * schedule_branch  — cron-string or interval-seconds; fires run_branch on tick.
  * subscribe_branch — event subscription; fires run_branch when event is emitted.

Persistence: SQLite tables ``branch_schedules`` and ``branch_subscriptions`` in
the universe's .runs.db (managed by tinyassets.runs.initialize_runs_db).

The ``Scheduler`` singleton drives two loops:
  * _tick_loop  — wakes every TICK_INTERVAL_S (default 10 s), fires any due schedules.
  * _event_loop — drains the in-process event queue and fires matching subscriptions.

Multi-tenant invariants (from spec):
  * schedule/subscription rows carry ``owner_actor``; removal gated to owner or admin.
  * Scheduled runs tag ``actor=scheduler:<schedule_id>`` with ``owner_actor`` in detail.
  * Rate-limit: 20 active schedules + 20 subscriptions per owner (configurable).
  * skip_if_running: when True, skip tick if a run for this schedule is still RUNNING.
  * Events fire exactly once per event_id (idempotency via delivered_events table).
  * Schedules survive daemon restart — recovery reads the DB on start().
"""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ─── Cron parser ──────────────────────────────────────────────────────────────

_FIELD_RANGES = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day-of-month
    (1, 12),   # month
    (0, 6),    # day-of-week (0=Sunday)
]

_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DOW_NAMES = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}


class CronParseError(ValueError):
    pass


def _expand_field(token: str, lo: int, hi: int) -> frozenset[int]:
    """Expand one cron field token into a frozenset of matching ints."""
    token = token.lower()

    # Named substitutions (month / dow)
    for name, val in {**_MONTH_NAMES, **_DOW_NAMES}.items():
        token = token.replace(name, str(val))

    result: set[int] = set()
    for part in token.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError:
                raise CronParseError(f"bad step: {step_s!r}")
            if step < 1:
                raise CronParseError(f"step must be ≥ 1, got {step}")

        if part == "*":
            result.update(range(lo, hi + 1, step))
        elif "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a), int(b)
            except ValueError:
                raise CronParseError(f"bad range: {part!r}")
            if not (lo <= start <= end <= hi):
                raise CronParseError(
                    f"range {start}-{end} out of [{lo},{hi}]"
                )
            result.update(range(start, end + 1, step))
        else:
            try:
                v = int(part)
            except ValueError:
                raise CronParseError(f"bad value: {part!r}")
            if not (lo <= v <= hi):
                raise CronParseError(f"{v} out of [{lo},{hi}]")
            result.add(v)
    return frozenset(result)


@dataclass(frozen=True)
class CronSchedule:
    """Parsed cron expression (5-field standard format)."""
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]
    expr: str

    @classmethod
    def parse(cls, expr: str) -> "CronSchedule":
        parts = expr.strip().split()
        if len(parts) != 5:
            raise CronParseError(
                f"cron must have 5 fields (minute hour dom month dow), got {len(parts)}: {expr!r}"
            )
        fields = [
            _expand_field(tok, lo, hi)
            for tok, (lo, hi) in zip(parts, _FIELD_RANGES)
        ]
        return cls(
            minutes=fields[0],
            hours=fields[1],
            days_of_month=fields[2],
            months=fields[3],
            days_of_week=fields[4],
            expr=expr,
        )

    def matches(self, t: time.struct_time) -> bool:
        cron_dow = (t.tm_wday + 1) % 7  # Python Mon=0…Sun=6 → cron Sun=0…Sat=6
        return (
            t.tm_min in self.minutes
            and t.tm_hour in self.hours
            and t.tm_mday in self.days_of_month
            and t.tm_mon in self.months
            and cron_dow in self.days_of_week
        )


def _cron_matches(expr: str, t: time.struct_time) -> bool:
    """Return True if cron expression matches the given local time struct."""
    try:
        return CronSchedule.parse(expr).matches(t)
    except CronParseError:
        return False


# ─── Rate limits ──────────────────────────────────────────────────────────────

MAX_SCHEDULES_PER_OWNER = 20
MAX_SUBSCRIPTIONS_PER_OWNER = 20

# Supported event types
VALID_EVENT_TYPES = frozenset({
    "canon_change",
    "branch_run_completed",
    "canon_upload",
    "pr_open",
})

# ─── Schema helpers (called from runs.initialize_runs_db) ────────────────────

SCHEDULER_SCHEMA = """
CREATE TABLE IF NOT EXISTS branch_schedules (
    schedule_id          TEXT PRIMARY KEY,
    branch_def_id        TEXT NOT NULL,
    owner_actor          TEXT NOT NULL,
    cron_expr            TEXT NOT NULL DEFAULT '',
    interval_seconds     REAL NOT NULL DEFAULT 0,
    inputs_template_json TEXT NOT NULL DEFAULT '{}',
    skip_if_running      INTEGER NOT NULL DEFAULT 0,
    active               INTEGER NOT NULL DEFAULT 1,
    paused               INTEGER NOT NULL DEFAULT 0,
    created_at           REAL NOT NULL,
    last_fired_at        REAL
);

CREATE INDEX IF NOT EXISTS idx_schedules_owner
    ON branch_schedules(owner_actor);
CREATE INDEX IF NOT EXISTS idx_schedules_active
    ON branch_schedules(active);

CREATE TABLE IF NOT EXISTS branch_subscriptions (
    subscription_id      TEXT PRIMARY KEY,
    branch_def_id        TEXT NOT NULL,
    owner_actor          TEXT NOT NULL,
    event_type           TEXT NOT NULL,
    filter_json          TEXT NOT NULL DEFAULT '{}',
    inputs_mapping_json  TEXT NOT NULL DEFAULT '{}',
    active               INTEGER NOT NULL DEFAULT 1,
    created_at           REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_owner
    ON branch_subscriptions(owner_actor);
CREATE INDEX IF NOT EXISTS idx_subscriptions_event
    ON branch_subscriptions(event_type, active);

CREATE TABLE IF NOT EXISTS scheduler_delivered_events (
    event_id             TEXT PRIMARY KEY,
    subscription_id      TEXT NOT NULL,
    delivered_at         REAL NOT NULL
);
"""


# ─── Schedule / subscription CRUD ─────────────────────────────────────────────

def register_schedule(
    base_path: str | Path,
    *,
    branch_def_id: str,
    owner_actor: str,
    cron_expr: str = "",
    interval_seconds: float = 0.0,
    inputs_template: dict[str, Any] | None = None,
    skip_if_running: bool = False,
) -> str:
    """Register a schedule. Returns schedule_id.

    One of cron_expr or interval_seconds must be set.
    Rate-limited to MAX_SCHEDULES_PER_OWNER active schedules per owner.
    """
    if not cron_expr and interval_seconds <= 0:
        raise ValueError("one of cron_expr or interval_seconds must be provided")
    if cron_expr:
        CronSchedule.parse(cron_expr)  # validate up-front

    db = _runs_db(base_path)
    with _connect(db) as conn:
        active_count = conn.execute(
            "SELECT COUNT(*) FROM branch_schedules WHERE owner_actor=? AND active=1",
            (owner_actor,),
        ).fetchone()[0]
        if active_count >= MAX_SCHEDULES_PER_OWNER:
            raise ValueError(
                f"rate limit: {owner_actor!r} already has {active_count} active schedules "
                f"(max {MAX_SCHEDULES_PER_OWNER})"
            )
        schedule_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO branch_schedules
                (schedule_id, branch_def_id, owner_actor, cron_expr,
                 interval_seconds, inputs_template_json, skip_if_running, active, created_at)
            VALUES (?,?,?,?,?,?,?,1,?)
            """,
            (
                schedule_id,
                branch_def_id,
                owner_actor,
                cron_expr,
                interval_seconds,
                json.dumps(inputs_template or {}),
                int(skip_if_running),
                time.time(),
            ),
        )
    return schedule_id


def unregister_schedule(
    base_path: str | Path,
    schedule_id: str,
    *,
    requesting_actor: str,
    admin: bool = False,
) -> bool:
    """Deactivate a schedule. Owner or admin only. Returns True if deactivated."""
    db = _runs_db(base_path)
    with _connect(db) as conn:
        row = conn.execute(
            "SELECT owner_actor FROM branch_schedules WHERE schedule_id=?",
            (schedule_id,),
        ).fetchone()
        if not row:
            return False
        if not admin and row["owner_actor"] != requesting_actor:
            raise PermissionError(
                f"{requesting_actor!r} is not the owner of schedule {schedule_id!r}"
            )
        conn.execute(
            "UPDATE branch_schedules SET active=0 WHERE schedule_id=?",
            (schedule_id,),
        )
    return True


def list_schedules(
    base_path: str | Path,
    *,
    owner_actor: str = "",
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """List schedules, optionally filtered by owner."""
    db = _runs_db(base_path)
    with _connect(db) as conn:
        q = "SELECT * FROM branch_schedules"
        params: list[Any] = []
        clauses: list[str] = []
        if active_only:
            clauses.append("active=1")
        if owner_actor:
            clauses.append("owner_actor=?")
            params.append(owner_actor)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def pause_schedule(
    base_path: str | Path,
    schedule_id: str,
    *,
    requesting_actor: str,
    admin: bool = False,
) -> bool:
    """Pause a schedule so it won't fire at next tick. Owner or admin only.

    Returns True if paused, False if schedule not found. Idempotent.
    """
    db = _runs_db(base_path)
    with _connect(db) as conn:
        row = conn.execute(
            "SELECT owner_actor FROM branch_schedules WHERE schedule_id=? AND active=1",
            (schedule_id,),
        ).fetchone()
        if not row:
            return False
        if not admin and row["owner_actor"] != requesting_actor:
            raise PermissionError(
                f"{requesting_actor!r} is not the owner of schedule {schedule_id!r}"
            )
        conn.execute(
            "UPDATE branch_schedules SET paused=1 WHERE schedule_id=?",
            (schedule_id,),
        )
    return True


def unpause_schedule(
    base_path: str | Path,
    schedule_id: str,
    *,
    requesting_actor: str,
    admin: bool = False,
) -> bool:
    """Resume a paused schedule. Owner or admin only.

    Returns True if unpaused, False if schedule not found. Idempotent.
    """
    db = _runs_db(base_path)
    with _connect(db) as conn:
        row = conn.execute(
            "SELECT owner_actor FROM branch_schedules WHERE schedule_id=? AND active=1",
            (schedule_id,),
        ).fetchone()
        if not row:
            return False
        if not admin and row["owner_actor"] != requesting_actor:
            raise PermissionError(
                f"{requesting_actor!r} is not the owner of schedule {schedule_id!r}"
            )
        conn.execute(
            "UPDATE branch_schedules SET paused=0 WHERE schedule_id=?",
            (schedule_id,),
        )
    return True


def list_scheduler_subscriptions(
    base_path: str | Path,
    *,
    owner_actor: str = "",
    event_type: str = "",
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """List event subscriptions, optionally filtered by owner and/or event_type."""
    db = _runs_db(base_path)
    with _connect(db) as conn:
        q = "SELECT * FROM branch_subscriptions"
        params: list[Any] = []
        clauses: list[str] = []
        if active_only:
            clauses.append("active=1")
        if owner_actor:
            clauses.append("owner_actor=?")
            params.append(owner_actor)
        if event_type:
            clauses.append("event_type=?")
            params.append(event_type)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def register_subscription(
    base_path: str | Path,
    *,
    branch_def_id: str,
    owner_actor: str,
    event_type: str,
    filter_json: dict[str, Any] | None = None,
    inputs_mapping: dict[str, Any] | None = None,
) -> str:
    """Register an event subscription. Returns subscription_id."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"unknown event_type {event_type!r}; valid: {sorted(VALID_EVENT_TYPES)}"
        )
    db = _runs_db(base_path)
    with _connect(db) as conn:
        active_count = conn.execute(
            "SELECT COUNT(*) FROM branch_subscriptions WHERE owner_actor=? AND active=1",
            (owner_actor,),
        ).fetchone()[0]
        if active_count >= MAX_SUBSCRIPTIONS_PER_OWNER:
            raise ValueError(
                f"rate limit: {owner_actor!r} already has {active_count} active subscriptions "
                f"(max {MAX_SUBSCRIPTIONS_PER_OWNER})"
            )
        sub_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO branch_subscriptions
                (subscription_id, branch_def_id, owner_actor, event_type,
                 filter_json, inputs_mapping_json, active, created_at)
            VALUES (?,?,?,?,?,?,1,?)
            """,
            (
                sub_id,
                branch_def_id,
                owner_actor,
                event_type,
                json.dumps(filter_json or {}),
                json.dumps(inputs_mapping or {}),
                time.time(),
            ),
        )
    return sub_id


def unregister_subscription(
    base_path: str | Path,
    subscription_id: str,
    *,
    requesting_actor: str,
    admin: bool = False,
) -> bool:
    """Deactivate a subscription. Owner or admin only."""
    db = _runs_db(base_path)
    with _connect(db) as conn:
        row = conn.execute(
            "SELECT owner_actor FROM branch_subscriptions WHERE subscription_id=?",
            (subscription_id,),
        ).fetchone()
        if not row:
            return False
        if not admin and row["owner_actor"] != requesting_actor:
            raise PermissionError(
                f"{requesting_actor!r} is not the owner of subscription {subscription_id!r}"
            )
        conn.execute(
            "UPDATE branch_subscriptions SET active=0 WHERE subscription_id=?",
            (subscription_id,),
        )
    return True


# ─── Event emission ───────────────────────────────────────────────────────────

@dataclass
class SchedulerEvent:
    event_type: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    payload: dict[str, Any] = field(default_factory=dict)


def emit_event(event: SchedulerEvent) -> None:
    """Emit an event into the global scheduler's queue (if running)."""
    s = _SINGLETON
    if s is not None:
        s._event_queue.put(event)


# ─── Scheduler singleton ──────────────────────────────────────────────────────

TICK_INTERVAL_S = 10.0  # how often the tick loop wakes


class Scheduler:
    """Drives schedule ticks and event subscriptions against a universe DB."""

    def __init__(
        self,
        base_path: str | Path,
        run_fn: Callable[[str, str, dict[str, Any], str], None],
    ) -> None:
        """
        Args:
            base_path: universe directory (contains .runs.db).
            run_fn:    callable(branch_def_id, actor, inputs, run_name) — fires a branch run.
                       Called in a separate thread; must be thread-safe.
        """
        self._base_path = Path(base_path)
        self._run_fn = run_fn
        self._event_queue: queue.Queue[SchedulerEvent] = queue.Queue()
        self._stop = threading.Event()
        self._tick_thread: threading.Thread | None = None
        self._event_thread: threading.Thread | None = None

    # ── Lifecycle ──

    def start(self) -> None:
        """Start tick + event loops. Idempotent if already running."""
        if self._tick_thread and self._tick_thread.is_alive():
            return
        self._stop.clear()
        self._tick_thread = threading.Thread(
            target=self._tick_loop, daemon=True, name="scheduler-tick"
        )
        self._event_thread = threading.Thread(
            target=self._event_loop, daemon=True, name="scheduler-event"
        )
        self._tick_thread.start()
        self._event_thread.start()
        logger.info("Scheduler started (base=%s)", self._base_path)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal loops to stop and wait for them to exit."""
        self._stop.set()
        self._event_queue.put(_STOP_SENTINEL)  # unblock event loop
        if self._tick_thread:
            self._tick_thread.join(timeout=timeout)
        if self._event_thread:
            self._event_thread.join(timeout=timeout)
        logger.info("Scheduler stopped")

    # ── Tick loop ──

    def _tick_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._fire_due_schedules()
            except Exception:
                logger.exception("scheduler tick error")
            self._stop.wait(TICK_INTERVAL_S)

    def _fire_due_schedules(self) -> None:
        now = time.time()
        local_now = time.localtime(now)
        db = _runs_db(self._base_path)
        try:
            with _connect(db) as conn:
                rows = conn.execute(
                    "SELECT * FROM branch_schedules WHERE active=1 AND paused=0"
                ).fetchall()
        except sqlite3.Error:
            logger.exception("scheduler: DB read failed")
            return

        for row in rows:
            try:
                self._maybe_fire_schedule(dict(row), now, local_now)
            except Exception:
                logger.exception("scheduler: error firing schedule %s", row["schedule_id"])

    def _maybe_fire_schedule(
        self,
        row: dict[str, Any],
        now: float,
        local_now: time.struct_time,
    ) -> None:
        schedule_id = row["schedule_id"]
        last_fired = row["last_fired_at"] or 0.0
        should_fire = False

        cron_expr = row["cron_expr"]
        interval_s = row["interval_seconds"]

        if cron_expr:
            # Fire if cron matches current minute and hasn't already fired this minute.
            minute_start = now - (now % 60)
            if _cron_matches(cron_expr, local_now) and last_fired < minute_start:
                should_fire = True
        elif interval_s > 0:
            if now - last_fired >= interval_s:
                should_fire = True

        if not should_fire:
            return

        if row["skip_if_running"]:
            if self._has_running_run(row["branch_def_id"]):
                logger.debug(
                    "scheduler: skip_if_running — skipping schedule %s", schedule_id
                )
                return

        inputs = json.loads(row["inputs_template_json"] or "{}")
        actor = f"scheduler:{schedule_id}"
        run_name = f"scheduled:{schedule_id[:8]}"
        try:
            self._run_fn(row["branch_def_id"], actor, inputs, run_name)
            logger.info(
                "scheduler: fired schedule %s → branch %s",
                schedule_id,
                row["branch_def_id"],
            )
        except Exception:
            logger.exception("scheduler: run_fn failed for schedule %s", schedule_id)
            return

        db = _runs_db(self._base_path)
        try:
            with _connect(db) as conn:
                conn.execute(
                    "UPDATE branch_schedules SET last_fired_at=? WHERE schedule_id=?",
                    (now, schedule_id),
                )
        except sqlite3.Error:
            logger.exception("scheduler: failed to update last_fired_at for %s", schedule_id)

    def _has_running_run(self, branch_def_id: str) -> bool:
        db = _runs_db(self._base_path)
        try:
            with _connect(db) as conn:
                row = conn.execute(
                    "SELECT 1 FROM runs WHERE branch_def_id=? AND status='running' LIMIT 1",
                    (branch_def_id,),
                ).fetchone()
            return row is not None
        except sqlite3.Error:
            return False

    # ── Event loop ──

    def _event_loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._event_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if event is _STOP_SENTINEL:
                break
            try:
                self._dispatch_event(event)
            except Exception:
                logger.exception("scheduler: event dispatch error for %s", event.event_id)

    def _dispatch_event(self, event: SchedulerEvent) -> None:
        db = _runs_db(self._base_path)
        try:
            with _connect(db) as conn:
                subs = conn.execute(
                    "SELECT * FROM branch_subscriptions WHERE event_type=? AND active=1",
                    (event.event_type,),
                ).fetchall()
        except sqlite3.Error:
            logger.exception("scheduler: DB read failed for event dispatch")
            return

        for sub in subs:
            sub_id = sub["subscription_id"]
            # Idempotency: skip if already delivered.
            delivery_key = f"{event.event_id}:{sub_id}"
            try:
                with _connect(db) as conn:
                    already = conn.execute(
                        "SELECT 1 FROM scheduler_delivered_events WHERE event_id=?",
                        (delivery_key,),
                    ).fetchone()
                    if already:
                        continue
                    # Mark delivered before firing to prevent double-fire on crash.
                    _SQL_MARK_DELIVERED = (
                        "INSERT INTO scheduler_delivered_events "
                        "(event_id, subscription_id, delivered_at) VALUES (?,?,?)"
                    )
                    conn.execute(
                        _SQL_MARK_DELIVERED,
                        (delivery_key, sub_id, time.time()),
                    )
            except sqlite3.Error:
                logger.exception("scheduler: idempotency write failed for %s", delivery_key)
                continue

            # Apply event-type filter if any.
            event_filter = json.loads(sub["filter_json"] or "{}")
            if event_filter:
                if not _matches_filter(event.payload, event_filter):
                    continue

            inputs_mapping = json.loads(sub["inputs_mapping_json"] or "{}")
            inputs = {k: event.payload.get(v, v) for k, v in inputs_mapping.items()}
            actor = f"subscriber:{sub['owner_actor']}"
            run_name = f"event:{event.event_type}:{sub_id[:8]}"
            try:
                self._run_fn(sub["branch_def_id"], actor, inputs, run_name)
                logger.info(
                    "scheduler: fired subscription %s on event %s",
                    sub_id,
                    event.event_type,
                )
            except Exception:
                logger.exception(
                    "scheduler: run_fn failed for subscription %s on event %s",
                    sub_id,
                    event.event_type,
                )


def _matches_filter(payload: dict[str, Any], filter_json: dict[str, Any]) -> bool:
    """Simple equality filter: each key in filter_json must match payload."""
    for k, v in filter_json.items():
        if payload.get(k) != v:
            return False
    return True


# ─── Internal helpers ─────────────────────────────────────────────────────────

class _StopSentinel:
    pass


_STOP_SENTINEL = _StopSentinel()
_SINGLETON: Scheduler | None = None
_SINGLETON_LOCK = threading.Lock()


def _runs_db(base_path: Path) -> Path:
    return base_path / ".runs.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    # Migrate: add paused column if not present (introduced after initial schema)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(branch_schedules)")}
    if "paused" not in cols:
        conn.execute(
            "ALTER TABLE branch_schedules ADD COLUMN paused INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    return conn


def get_or_create_scheduler(
    base_path: str | Path,
    run_fn: Callable[[str, str, dict[str, Any], str], None],
) -> Scheduler:
    """Return the process-global Scheduler, creating it if needed."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            _SINGLETON = Scheduler(base_path, run_fn)
            _SINGLETON.start()
        return _SINGLETON


def shutdown_scheduler(timeout: float = 5.0) -> None:
    """Stop the global scheduler (used in tests and daemon shutdown)."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is not None:
            _SINGLETON.stop(timeout=timeout)
            _SINGLETON = None


__all__ = [
    "CronParseError",
    "CronSchedule",
    "Scheduler",
    "SchedulerEvent",
    "SCHEDULER_SCHEMA",
    "VALID_EVENT_TYPES",
    "MAX_SCHEDULES_PER_OWNER",
    "MAX_SUBSCRIPTIONS_PER_OWNER",
    "emit_event",
    "get_or_create_scheduler",
    "list_schedules",
    "list_scheduler_subscriptions",
    "pause_schedule",
    "register_schedule",
    "register_subscription",
    "shutdown_scheduler",
    "unpause_schedule",
    "unregister_schedule",
    "unregister_subscription",
]
