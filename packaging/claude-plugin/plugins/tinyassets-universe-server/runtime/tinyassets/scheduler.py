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
  * schedule rows carry ``universe_id`` + ``owner_principal_id``, both DERIVED from
    the authenticated request at registration; removal gated to that principal or a
    universe admin. Subscription rows still carry ``owner_actor`` only.
  * Scheduled runs tag ``actor=universe:<universe_id>`` — the owning universe, never a
    synthetic ``scheduler:`` identity, which the run function rejects. A row without a
    universe and a principal is LEGACY and never fires.
  * Rate-limit: 20 active schedules + 20 subscriptions per owner (configurable).
  * skip_if_running: when True, skip tick if a run for this schedule is still RUNNING.
  * Events fire exactly once per event_id (idempotency via delivered_events table).
  * Schedules survive daemon restart — recovery reads the DB on start().
"""

from __future__ import annotations

import inspect
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

#: Floor on how often a schedule may fire, in seconds (5 minutes).
#:
#: A scheduled run spends the OWNER's own subscription (design D7 — there is no
#: separate background budget), so a one-second cadence is a way to drain the
#: person who registered it. Registration refuses below the floor instead of
#: storing a row that bills them forever. Enforced on the request surface
#: (``_action_schedule_branch``); the library entry point stays unfloored so
#: internal callers and tests can drive the tick loop deterministically.
MIN_SCHEDULE_INTERVAL_S = 300.0

# Supported event types
VALID_EVENT_TYPES = frozenset({
    "canon_change",
    "branch_run_completed",
    "canon_upload",
    "pr_open",
})

#: A Source node emits a namespaced ``source:<source_id>`` event. These are open-ended
#: (one per user-created Source), so they are admitted by PREFIX past the closed
#: ``VALID_EVENT_TYPES`` allowlist rather than enumerated (design Floor 3).
_SOURCE_EVENT_PREFIX = "source:"
_MAX_EVENT_TYPE_LEN = 320


def _is_valid_event_type(event_type: str) -> bool:
    if event_type in VALID_EVENT_TYPES:
        return True
    if not event_type.startswith(_SOURCE_EVENT_PREFIX):
        return False
    source_id = event_type[len(_SOURCE_EVENT_PREFIX):]
    return bool(source_id) and len(event_type) <= _MAX_EVENT_TYPE_LEN

# ─── Schema helpers (called from runs.initialize_runs_db) ────────────────────

SCHEDULER_SCHEMA = """
CREATE TABLE IF NOT EXISTS branch_schedules (
    schedule_id          TEXT PRIMARY KEY,
    branch_def_id        TEXT NOT NULL,
    owner_actor          TEXT NOT NULL,
    universe_id          TEXT NOT NULL DEFAULT '',
    owner_principal_id   TEXT NOT NULL DEFAULT '',
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
CREATE INDEX IF NOT EXISTS idx_schedules_universe
    ON branch_schedules(universe_id);

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
    universe_id: str = "",
    owner_principal_id: str = "",
    cron_expr: str = "",
    interval_seconds: float = 0.0,
    inputs_template: dict[str, Any] | None = None,
    skip_if_running: bool = False,
) -> str:
    """Register a schedule. Returns schedule_id.

    One of cron_expr or interval_seconds must be set.
    Rate-limited to MAX_SCHEDULES_PER_OWNER active schedules per owner.

    ``universe_id`` is the universe whose serving assignment executes the branch
    and ``owner_principal_id`` the authenticated principal that authorised it;
    ``owner_actor`` is the run actor, ``universe:<universe_id>``. All three are
    DERIVED by the caller from the request identity — never taken from a caller
    field (see ``_action_schedule_branch``). A row missing the universe or the
    principal is legacy and never fires (:func:`schedule_is_legacy`).
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
                (schedule_id, branch_def_id, owner_actor, universe_id,
                 owner_principal_id, cron_expr,
                 interval_seconds, inputs_template_json, skip_if_running, active, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,1,?)
            """,
            (
                schedule_id,
                branch_def_id,
                owner_actor,
                (universe_id or "").strip(),
                (owner_principal_id or "").strip(),
                cron_expr,
                interval_seconds,
                json.dumps(inputs_template or {}),
                int(skip_if_running),
                time.time(),
            ),
        )
    return schedule_id


def schedule_is_legacy(row: dict[str, Any]) -> bool:
    """Whether a schedule row predates owner derivation and can never fire.

    A fireable row carries all three of: a universe, the authenticated principal
    that registered it, and a run actor that is exactly ``universe:<universe_id>``.
    Anything else is a row from before user-owned-automations 2.1 (or a row whose
    actor and universe disagree), and the tick loop refuses it rather than
    guessing an identity to run it under — Hard Rule 8, and the founder principle
    that nothing runs outside a user's universe.
    """
    universe_id = str(row.get("universe_id") or "").strip()
    principal_id = str(row.get("owner_principal_id") or "").strip()
    actor = str(row.get("owner_actor") or "").strip()
    return not (universe_id and principal_id and actor == f"universe:{universe_id}")


def _schedule_owner_principal(row: Any) -> str:
    """The identity allowed to pause/resume/delete a schedule row.

    Derived rows are owned by their ``owner_principal_id``. A legacy row has none,
    so it keeps its original ``owner_actor`` as owner — otherwise nobody could
    delete the dead rows that 2.1 leaves behind.
    """
    principal = str(row["owner_principal_id"] or "").strip()
    return principal or str(row["owner_actor"] or "")


def get_schedule(base_path: str | Path, schedule_id: str) -> dict[str, Any] | None:
    """Return one schedule row (active or not), or None.

    The owner-control actions read the row BEFORE acting so they can check the
    requester against the row's own universe and principal.
    """
    db = _runs_db(base_path)
    with _connect(db) as conn:
        row = conn.execute(
            "SELECT * FROM branch_schedules WHERE schedule_id=?",
            (schedule_id,),
        ).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["legacy"] = schedule_is_legacy(record)
    return record


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
            "SELECT owner_actor, owner_principal_id FROM branch_schedules "
            "WHERE schedule_id=?",
            (schedule_id,),
        ).fetchone()
        if not row:
            return False
        if not admin and _schedule_owner_principal(row) != requesting_actor:
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
    universe_id: str = "",
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """List schedules, optionally filtered by owner and/or universe.

    Each row carries a ``legacy`` flag so a caller's surface can say WHY a
    schedule is listed but never fires (:func:`schedule_is_legacy`).
    """
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
        if universe_id:
            clauses.append("universe_id=?")
            params.append(universe_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        rows = conn.execute(q, params).fetchall()
    records = [dict(r) for r in rows]
    for record in records:
        record["legacy"] = schedule_is_legacy(record)
    return records


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
            "SELECT owner_actor, owner_principal_id FROM branch_schedules "
            "WHERE schedule_id=? AND active=1",
            (schedule_id,),
        ).fetchone()
        if not row:
            return False
        if not admin and _schedule_owner_principal(row) != requesting_actor:
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
            "SELECT owner_actor, owner_principal_id FROM branch_schedules "
            "WHERE schedule_id=? AND active=1",
            (schedule_id,),
        ).fetchone()
        if not row:
            return False
        if not admin and _schedule_owner_principal(row) != requesting_actor:
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
    if not _is_valid_event_type(event_type):
        raise ValueError(
            f"unknown event_type {event_type!r}; valid: {sorted(VALID_EVENT_TYPES)} "
            f"or a '{_SOURCE_EVENT_PREFIX}<id>' source event"
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


def is_running() -> bool:
    """Whether the global scheduler is up and its loops are alive.

    Two callers depend on this: a Source delivery may only be published onto a
    live event queue, and schedule registration REFUSES when the tick loop is not
    running (design D4 — a stored row that can never fire is the silent failure
    this change exists to remove). Both need thread liveness, not merely the
    presence of a singleton object: a Scheduler that was constructed but never
    started, or whose loops died, would otherwise read as available.
    """
    s = _SINGLETON
    return s is not None and s.is_alive()


# ─── Scheduler singleton ──────────────────────────────────────────────────────

TICK_INTERVAL_S = 10.0  # how often the tick loop wakes


def _accepts_principal_id(run_fn: Callable[..., None]) -> bool:
    """Whether ``run_fn`` accepts the ``principal_id`` keyword.

    The run_fn contract is ``run_fn(branch_def_id, actor, inputs, run_name, *,
    principal_id="")``. The four positional arguments are unchanged, so a
    pre-existing four-argument callable still serves the EVENT path, which
    carries no principal (a webhook authorises itself with its token). A
    SCHEDULE must convey its owner principal or the run would fall back to the
    request identity — empty on the tick thread — so ``_maybe_fire_schedule``
    refuses instead of firing without it.
    """
    try:
        params = inspect.signature(run_fn).parameters.values()
    except (TypeError, ValueError):  # builtins / C callables expose no signature
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return True
    return any(
        p.name == "principal_id"
        and p.kind
        in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for p in params
    )


class Scheduler:
    """Drives schedule ticks and event subscriptions against a universe DB."""

    def __init__(
        self,
        base_path: str | Path,
        run_fn: Callable[..., None],
    ) -> None:
        """
        Args:
            base_path: universe directory (contains .runs.db).
            run_fn:    callable(branch_def_id, actor, inputs, run_name, *,
                       principal_id="") — fires a branch run. Called in a separate
                       thread; must be thread-safe. ``principal_id`` is passed only
                       for schedule firings, and only when the callable accepts it.
        """
        self._base_path = Path(base_path)
        self._run_fn = run_fn
        self._run_fn_takes_principal = _accepts_principal_id(run_fn)
        self._event_queue: queue.Queue[SchedulerEvent] = queue.Queue()
        self._stop = threading.Event()
        self._tick_thread: threading.Thread | None = None
        self._event_thread: threading.Thread | None = None
        #: schedule ids already reported as legacy, so the refusal is one log
        #: line per schedule per process rather than one every tick.
        self._legacy_reported: set[str] = set()

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

    def is_alive(self) -> bool:
        """Whether both loops are running right now."""
        return bool(
            self._tick_thread
            and self._tick_thread.is_alive()
            and self._event_thread
            and self._event_thread.is_alive()
        )

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
        if schedule_is_legacy(row):
            # Never fire a row whose owner cannot be named. Firing it would have to
            # invent an identity for the run, which is the whole defect 2.1 closes.
            # One line per schedule per process, not one per tick.
            if schedule_id not in self._legacy_reported:
                self._legacy_reported.add(schedule_id)
                logger.warning(
                    "scheduler: schedule %s is legacy (universe=%r principal=%r "
                    "actor=%r) — never fired; the owner must re-register it",
                    schedule_id,
                    row.get("universe_id"),
                    row.get("owner_principal_id"),
                    row.get("owner_actor"),
                )
            return

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
        # The run actor is the OWNING UNIVERSE (``universe:<id>``), recorded on the
        # row at registration. It used to be ``scheduler:<schedule_id>``, which the
        # run function rejects as a non-universe actor — so every schedule that ever
        # came due was refused. The owner principal rides alongside it because the
        # tick thread has no request identity for the provider session to bind to.
        actor = str(row["owner_actor"])
        principal_id = str(row["owner_principal_id"] or "").strip()
        run_name = f"scheduled:{schedule_id[:8]}"
        if not self._run_fn_takes_principal:
            logger.error(
                "scheduler: run_fn %r does not accept principal_id; refusing to fire "
                "schedule %s without its owner principal",
                getattr(self._run_fn, "__name__", self._run_fn),
                schedule_id,
            )
            return
        try:
            self._run_fn(
                row["branch_def_id"], actor, inputs, run_name, principal_id=principal_id
            )
            logger.info(
                "scheduler: fired schedule %s → branch %s as %s",
                schedule_id,
                row["branch_def_id"],
                actor,
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

    def _subscription_active(self, subscription_id: str) -> bool:
        """Whether a subscription is still active RIGHT NOW (Codex #3 revocation re-check)."""
        db = _runs_db(self._base_path)
        try:
            with _connect(db) as conn:
                row = conn.execute(
                    "SELECT 1 FROM branch_subscriptions "
                    "WHERE subscription_id=? AND active=1",
                    (subscription_id,),
                ).fetchone()
            return row is not None
        except sqlite3.Error:
            # Fail closed: if we cannot confirm it is active, do not fire.
            logger.exception("scheduler: active re-check failed for %s", subscription_id)
            return False

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
            if inputs_mapping:
                inputs = {k: event.payload.get(v, v) for k, v in inputs_mapping.items()}
            elif event.event_type.startswith(_SOURCE_EVENT_PREFIX):
                # A Source event carries the branch inputs verbatim under "inputs".
                raw_inputs = event.payload.get("inputs")
                inputs = raw_inputs if isinstance(raw_inputs, dict) else {}
            else:
                inputs = {}
            # A subscription owned by a universe fires its branch AS that universe (the
            # correct branch_run actor), never wrapped as a "subscriber:" identity. Legacy
            # (non-universe) owners keep the subscriber prefix.
            owner = str(sub["owner_actor"])
            actor = owner if owner.startswith("universe:") else f"subscriber:{owner}"
            run_name = f"event:{event.event_type}:{sub_id[:8]}"
            # Codex #3 revocation race: re-check the subscription is STILL active
            # immediately before firing. A revoke (create_source→revoke_source, or
            # unsubscribe) that landed after the snapshot above now takes effect, so an
            # in-flight event for a revoked source does not run.
            if not self._subscription_active(sub_id):
                logger.info("scheduler: subscription %s revoked before fire; skipping", sub_id)
                continue
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


def _runs_db(base_path: str | Path) -> Path:
    return Path(base_path) / ".runs.db"


#: Columns added to ``branch_schedules`` after its initial schema, with the DDL
#: fragment that adds each one. SQLite has no ``ADD COLUMN IF NOT EXISTS``, so
#: ``_connect`` probes ``PRAGMA table_info`` and adds whatever is missing — the
#: migration is idempotent and runs on an existing DB without a rebuild.
#:
#: ``universe_id`` / ``owner_principal_id`` carry the two identities a run needs
#: (user-owned-automations 2.1): which universe executes the branch, and which
#: authenticated principal authorised it. A row predating them keeps '' for both
#: and is LEGACY — it never fires, because a run with no owner would have to fall
#: back to an ambient identity, which is exactly what the founder principle
#: forbids.
_SCHEDULE_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("paused", "INTEGER NOT NULL DEFAULT 0"),
    ("universe_id", "TEXT NOT NULL DEFAULT ''"),
    ("owner_principal_id", "TEXT NOT NULL DEFAULT ''"),
)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(branch_schedules)")}
    if cols:  # table exists — an empty pragma means the schema has not been laid down yet
        missing = [(c, ddl) for c, ddl in _SCHEDULE_COLUMN_MIGRATIONS if c not in cols]
        if missing:
            for col, ddl in missing:
                conn.execute(f"ALTER TABLE branch_schedules ADD COLUMN {col} {ddl}")
            conn.commit()
    return conn


def get_or_create_scheduler(
    base_path: str | Path,
    run_fn: Callable[..., None],
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
    "MIN_SCHEDULE_INTERVAL_S",
    "emit_event",
    "get_or_create_scheduler",
    "get_schedule",
    "is_running",
    "list_schedules",
    "list_scheduler_subscriptions",
    "pause_schedule",
    "register_schedule",
    "register_subscription",
    "schedule_is_legacy",
    "shutdown_scheduler",
    "unpause_schedule",
    "unregister_schedule",
    "unregister_subscription",
]
