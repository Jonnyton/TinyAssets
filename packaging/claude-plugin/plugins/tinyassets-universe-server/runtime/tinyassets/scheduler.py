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
from datetime import datetime, timezone
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


def min_cron_interval_seconds(expr: str) -> float:
    """Shortest gap, in seconds, between two firings of ``expr``.

    The interval floor was only ever applied to ``interval_seconds``, so
    ``* * * * *`` sailed through and fired every minute on the owner's own
    subscription — the exact spend runaway the floor exists to stop (Codex ADAPT
    on 44caf369, `cron_every_minute_accepts=True`).

    Only the minute and hour fields can shorten the gap; day/month/weekday can
    only make a schedule fire on fewer days, never more often within one. So the
    answer is the smallest distance between consecutive matching minutes:

    * within an hour — sorted differences of the matching-minute set;
    * across the hour boundary — ``60 - max + min``, but ONLY when two matching
      hours are actually adjacent (mod 24). ``0,59 12 * * *`` fires at 12:00 and
      12:59 and is a legitimate 59-minute cadence; counting a wrap for it would
      refuse a schedule that never fires twice inside five minutes.

    A single matching minute in a single hour cannot repeat inside a day, so the
    floor is one day. Raises ``CronParseError`` on an unparseable expression.
    """
    schedule = CronSchedule.parse(expr)
    minutes = sorted(schedule.minutes)
    hours = sorted(schedule.hours)
    if not minutes or not hours:
        # No minute or no hour can ever match: it never fires. Not a floor breach.
        return float("inf")
    gaps = [b - a for a, b in zip(minutes, minutes[1:])]
    hours_adjacent = any((h + 1) % 24 in schedule.hours for h in hours)
    if hours_adjacent:
        gaps.append(60 - minutes[-1] + minutes[0])
    elif len(hours) > 1:
        # Non-adjacent hours: the shortest cross-hour gap is the smallest hour
        # distance, minus the span the minute set can claw back.
        hour_gaps = [b - a for a, b in zip(hours, hours[1:])]
        hour_gaps.append(24 - hours[-1] + hours[0])
        gaps.append(min(hour_gaps) * 60 - minutes[-1] + minutes[0])
    if not gaps:
        return 24 * 3600.0  # one matching minute, one matching hour → daily
    return min(gaps) * 60.0


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

#: Refusal-ledger key prefix for a schedule. The assigned-queue refusal store is
#: keyed by an opaque task id; namespacing keeps schedule refusals from colliding
#: with the consumer's branch-task rows while both stay readable from one place
#: (D5 — recorded refusals, one table).
REFUSAL_KEY_PREFIX = "schedule:"

#: How long an UNCHANGED refusal reason is left alone before being re-recorded.
#: The store upserts, so re-recording never grows the table, but it does cost a
#: write per tick per refused schedule; the owner's surface only needs the row to
#: look fresh. Mirrors the consumer's write-amplification guard.
_REFUSAL_REWRITE_SECONDS = 60.0

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
    pause_reason         TEXT NOT NULL DEFAULT '',
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


def legacy_owner_actors_for(universe_id: str, principals: tuple[str, ...] = ()) -> set[str]:
    """``owner_actor`` values a migrated legacy row may carry for ``universe_id``.

    A migrated row has ``universe_id=''`` — the column did not exist when it was
    written — so a universe-scoped list would never show it and its owner could
    neither see nor delete it. What it DOES carry is the pre-2.1 ``owner_actor``,
    which was either the universe (``universe:<id>``, written by the event-source
    path) or a bare principal. Recovering the universe from that is what makes a
    migrated row addressable again.
    """
    uid = (universe_id or "").strip()
    recovered = {f"universe:{uid}"} if uid else set()
    return recovered | {p.strip() for p in principals if p and p.strip()}


def list_schedules(
    base_path: str | Path,
    *,
    owner_actor: str = "",
    universe_id: str = "",
    legacy_owner_actors: tuple[str, ...] = (),
    include_orphaned_legacy: bool = False,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """List schedules, optionally filtered by owner and/or universe.

    Each row carries a ``legacy`` flag so a caller's surface can say WHY a
    schedule is listed but never fires (:func:`schedule_is_legacy`).

    ``universe_id`` scoping also admits MIGRATED legacy rows (``universe_id=''``)
    whose ``owner_actor`` is ``universe:<universe_id>`` or one of
    ``legacy_owner_actors`` — see :func:`legacy_owner_actors_for`. Without that,
    every row an existing install already has would be invisible to the only
    people entitled to delete it.

    ``include_orphaned_legacy`` additionally returns legacy rows whose universe
    cannot be recovered from ``owner_actor`` at all. **Nothing calls this today.**
    It exists so an operator cleanup path has a way to see them without the
    owner-scoped surface leaking one universe's rows into another's list; the
    request surface never sets it.
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
            if include_orphaned_legacy:
                # Every legacy row, addressable or not, alongside this universe's.
                clauses.append("(universe_id=? OR universe_id='')")
                params.append(universe_id)
            else:
                recoverable = sorted(
                    legacy_owner_actors_for(universe_id, legacy_owner_actors)
                )
                placeholders = ",".join("?" for _ in recoverable)
                clauses.append(
                    f"(universe_id=? OR (universe_id='' "
                    f"AND owner_actor IN ({placeholders})))"
                )
                params.append(universe_id)
                params.extend(recoverable)
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
            # An owner pausing by hand records no reason; only the tick's
            # auto-pause writes one, so a reason on the row always means "the
            # daemon stopped this, and here is why".
            "UPDATE branch_schedules SET paused=1, pause_reason='' WHERE schedule_id=?",
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
            # Resuming clears the auto-pause reason: the owner has answered it.
            # If the cause is still live the next tick refuses and re-pauses,
            # which is the loud, readable outcome rather than a silent no-op.
            "UPDATE branch_schedules SET paused=0, pause_reason='' WHERE schedule_id=?",
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
        #: refusal-ledger key -> (reason, monotonic time it was last written).
        self._recorded_refusals: dict[str, tuple[str, float]] = {}
        #: Identity of THIS ticker in the refusal ledger. Deliberately not a
        #: stable/host identity — it names which loop observed the refusal, and
        #: nothing derives authority from it (D1: no executor-identity pin).
        self._ticker_id = f"scheduler-{uuid.uuid4().hex[:12]}"

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
        universe_id = str(row.get("universe_id") or "").strip()

        if schedule_is_legacy(row):
            # Never fire a row whose owner cannot be named. Firing it would have to
            # invent an identity for the run, which is the whole defect 2.1 closes.
            # One log line per schedule per process; the refusal row is the durable
            # record, and it upserts, so it does not grow.
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
            self._record_refusal(schedule_id, universe_id, "legacy_row")
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
            # Not due is not a skip. Recording it would drown the ledger the owner
            # reads in rows saying nothing happened, every ten seconds.
            return

        if row["skip_if_running"]:
            if self._has_running_run(row["branch_def_id"]):
                logger.debug(
                    "scheduler: skip_if_running — skipping schedule %s", schedule_id
                )
                self._record_refusal(schedule_id, universe_id, "skip_if_running")
                return

        # D3 — authority is checked HERE, at the tick, not only at registration.
        # An owner who lost admin, moved home, or has no serving assignment must
        # not run: `_validate_founder_home` downstream checks home only, so a
        # revoked admin with an unchanged home would otherwise still fire.
        denial = self._authorization_denial(row)
        if denial:
            # D5 — one recorded refusal, and the row auto-pauses with a reason the
            # owner can read. `last_fired_at` is deliberately NOT advanced: nothing
            # ran, so the schedule has not fired.
            self._record_refusal(schedule_id, universe_id, denial)
            self._pause_for_reason(schedule_id, denial)
            logger.warning(
                "scheduler: schedule %s refused (%s) and paused", schedule_id, denial
            )
            return

        actor = str(row["owner_actor"])
        principal_id = str(row["owner_principal_id"] or "").strip()
        if not self._run_fn_takes_principal:
            logger.error(
                "scheduler: run_fn %r does not accept principal_id; refusing to fire "
                "schedule %s without its owner principal",
                getattr(self._run_fn, "__name__", self._run_fn),
                schedule_id,
            )
            self._record_refusal(schedule_id, universe_id, "run_fn_incompatible")
            return

        # Claim the due row BEFORE firing, compare-and-swap on the `last_fired_at`
        # this tick read. Two daemons sharing one data root each run a tick loop
        # (the singleton is per process, not per data root), and without the claim
        # both would enqueue before either wrote the timestamp back.
        if not self._claim_due(schedule_id, last_fired=row["last_fired_at"], now=now):
            logger.debug(
                "scheduler: schedule %s already claimed by another ticker", schedule_id
            )
            return

        inputs = json.loads(row["inputs_template_json"] or "{}")
        run_name = f"scheduled:{schedule_id[:8]}"
        try:
            self._run_fn(
                row["branch_def_id"], actor, inputs, run_name, principal_id=principal_id
            )
        except Exception as exc:  # noqa: BLE001 - one failure must not kill the loop
            logger.exception("scheduler: run_fn failed for schedule %s", schedule_id)
            # The claim stands: the attempt happened, and re-firing immediately
            # would spin against whatever rejected it. The refusal names the cause.
            self._record_refusal(
                schedule_id, universe_id, f"enqueue_error:{type(exc).__name__}"
            )
            return
        logger.info(
            "scheduler: fired schedule %s → branch %s as %s",
            schedule_id,
            row["branch_def_id"],
            actor,
        )

    # ── Tick-time authority, refusals, and the due-row claim ──

    def _authorization_denial(self, row: dict[str, Any]) -> str:
        """The reason this row may not run right now, or '' when it may.

        Checked synchronously on the tick so a refusal is recorded instead of a
        run being enqueued and failing later — by which point the scheduler has
        already treated the enqueue as a fire.
        """
        universe_id = str(row.get("universe_id") or "").strip()
        principal_id = str(row.get("owner_principal_id") or "").strip()
        base = self._base_path
        try:
            from tinyassets.daemon_server import (
                get_founder_home,
                universe_access_permission,
            )
            from tinyassets.provider_assignment import load_provider_assignment

            if universe_access_permission(
                base, universe_id=universe_id, actor_id=principal_id
            ) != "admin":
                return "owner_lost_admin"
            if get_founder_home(base, principal_id) != universe_id:
                return "not_owner_home"
            assignment = load_provider_assignment(base, universe_id=universe_id)
            if assignment is None or str(assignment.state) != "ready":
                return "no_serving_assignment"
        except Exception as exc:  # noqa: BLE001 - fail CLOSED, and say why
            logger.exception(
                "scheduler: authorization check failed for schedule %s",
                row.get("schedule_id"),
            )
            return f"authorization_error:{type(exc).__name__}"
        return ""

    def _record_refusal(self, schedule_id: str, universe_id: str, reason: str) -> None:
        """Write ONE refusal row for this schedule, keyed ``schedule:<id>``.

        Same ledger the assigned-queue consumer writes to, so the owner's surface
        reads every skipped attempt from one place (D5). The store upserts on the
        key, so a repeating reason keeps one row rather than growing the table;
        an unchanged reason is re-recorded at most once per window, mirroring the
        consumer's write-amplification guard.
        """
        key = f"{REFUSAL_KEY_PREFIX}{schedule_id}"
        previous = self._recorded_refusals.get(key)
        elapsed = time.monotonic()
        if (
            previous is not None
            and previous[0] == reason
            and elapsed - previous[1] < _REFUSAL_REWRITE_SECONDS
        ):
            return
        try:
            from tinyassets.storage.assigned_queue_refusals import (
                AssignedQueueRefusalStore,
            )

            AssignedQueueRefusalStore(self._base_path).record(
                branch_task_id=key,
                universe_id=universe_id,
                reason=reason,
                observed_at=datetime.now(timezone.utc).isoformat(),
                consumer_id=self._ticker_id,
            )
        except Exception:  # noqa: BLE001 - losing the ledger row must not kill the tick
            logger.exception(
                "scheduler: failed to record refusal %s for schedule %s",
                reason,
                schedule_id,
            )
            return
        self._recorded_refusals[key] = (reason, elapsed)

    def _pause_for_reason(self, schedule_id: str, reason: str) -> None:
        """Auto-pause a row the tick refused, recording the reason on it (D3)."""
        try:
            with _connect(_runs_db(self._base_path)) as conn:
                conn.execute(
                    "UPDATE branch_schedules SET paused=1, pause_reason=? "
                    "WHERE schedule_id=?",
                    (reason, schedule_id),
                )
        except sqlite3.Error:
            logger.exception("scheduler: failed to pause schedule %s", schedule_id)

    def _claim_due(self, schedule_id: str, *, last_fired: Any, now: float) -> bool:
        """Compare-and-swap the due row. True when THIS ticker won the claim.

        ``IS`` rather than ``=`` because ``last_fired_at`` is NULL until the first
        fire, and ``NULL = NULL`` is never true in SQL — an equality comparison
        would make every never-fired schedule unclaimable.
        """
        try:
            with _connect(_runs_db(self._base_path)) as conn:
                cursor = conn.execute(
                    "UPDATE branch_schedules SET last_fired_at=? "
                    "WHERE schedule_id=? AND last_fired_at IS ?",
                    (now, schedule_id, last_fired),
                )
                return cursor.rowcount == 1
        except sqlite3.Error:
            logger.exception("scheduler: failed to claim schedule %s", schedule_id)
            return False

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
#: the migration probes ``PRAGMA table_info`` and adds whatever is missing.
#:
#: ``universe_id`` / ``owner_principal_id`` carry the two identities a run needs
#: (user-owned-automations 2.1): which universe executes the branch, and which
#: authenticated principal authorised it. A row predating them keeps '' for both
#: and is LEGACY — it never fires, because a run with no owner would have to fall
#: back to an ambient identity, which is exactly what the founder principle
#: forbids. ``pause_reason`` carries why the tick auto-paused a row (D3/D5), so
#: the owner can read the cause on their own surface.
_SCHEDULE_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("paused", "INTEGER NOT NULL DEFAULT 0"),
    ("universe_id", "TEXT NOT NULL DEFAULT ''"),
    ("owner_principal_id", "TEXT NOT NULL DEFAULT ''"),
    ("pause_reason", "TEXT NOT NULL DEFAULT ''"),
)


def migrate_scheduler_schema(conn: sqlite3.Connection) -> None:
    """Add every post-initial ``branch_schedules`` column. Idempotent, concurrency-safe.

    **This MUST run before ``SCHEDULER_SCHEMA`` is executed**, not after.
    ``SCHEDULER_SCHEMA`` contains ``CREATE INDEX ... branch_schedules(universe_id)``;
    on an existing install that index names a column the old table does not have
    yet, so ``initialize_runs_db`` died with ``OperationalError: no such column:
    universe_id`` before any migration could run. Ordering the migration first is
    the whole fix — a migration that runs after the thing it enables is not a
    migration (Codex ADAPT on 44caf369, reproduced against an old-schema DB).

    The probe and the ALTERs run inside one ``BEGIN IMMEDIATE`` so two connections
    opening the same DB cannot both observe a missing column and both try to add
    it; the duplicate-column error is still caught, because the write lock is
    only held per connection and a process that lost a race must treat the column
    as already present rather than crash.
    """
    if not {row[1] for row in conn.execute("PRAGMA table_info(branch_schedules)")}:
        # Table not laid down yet: CREATE TABLE brings every column with it.
        return
    conn.commit()  # close any implicit transaction so BEGIN IMMEDIATE can take the lock
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Re-probe INSIDE the write lock: the check and the ALTER have to be one
        # atomic step, or the check is just a guess made before the lock.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(branch_schedules)")}
        for col, ddl in _SCHEDULE_COLUMN_MIGRATIONS:
            if col in cols:
                continue
            try:
                conn.execute(f"ALTER TABLE branch_schedules ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    migrate_scheduler_schema(conn)
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
    "REFUSAL_KEY_PREFIX",
    "emit_event",
    "get_or_create_scheduler",
    "get_schedule",
    "is_running",
    "legacy_owner_actors_for",
    "list_schedules",
    "migrate_scheduler_schema",
    "min_cron_interval_seconds",
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
