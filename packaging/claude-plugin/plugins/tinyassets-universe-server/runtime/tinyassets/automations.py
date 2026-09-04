"""User-owned automations: the row, the owner's controls, and the due-run path.

One universe, one owner, one recurring Branch run. This module is the whole
storage + logic half of ``openspec/changes/user-owned-automations`` task 3.1/3.2;
the MCP surface and the consumer pump call into it and add nothing of their own.

What is deliberately NOT here (design D1, PLAN.md 2026-08-29 "nothing runs
outside a user's universe"):

* **No provider.** A row records what to run and when, never which provider or
  credential runs it. Every due run resolves the universe's CURRENT
  ``provider_assignments`` row through the same foreground session a live turn
  uses, so rebinding the universe to another provider needs no re-preparation.
* **No executor identity.** No ``worker_id``, ``daemon_id`` or
  ``runtime_instance_id`` is stored or compared. The fleet-era activation layer
  wedged on exactly those: a boot-unique consumer id could never match the id
  recorded when the automation was prepared.
* **No host actor.** The run actor is ``universe:<id>`` and the provider
  principal is the automation's owner, checked at registration AND at each run
  (D3). An owner who lost admin gets a recorded refusal and an auto-paused
  automation, never a run.

Fences and failure:

* ``(automation_id, due_at)`` is the run fence (D2) -- a ``BEGIN IMMEDIATE``
  count-and-insert, the same TOCTOU-safe shape as ``_engine_run_admit``. A
  restart recomputes the same ``due_at`` and finds the row, so a due run
  launches exactly once across restarts.
* Registration fails loud (D4): a row that cannot fire right now is refused with
  a named reason rather than stored. Hard Rule 8.
* Every skip lands in ``assigned_queue_refusals`` keyed ``automation:<id>``
  (D5), and one automation's failure never propagates into the pump.

Due-time note (deviation from the build brief, deliberate): the interval trigger
floors ``now`` onto the automation's own period grid rather than always emitting
``anchor + one interval``. Both are deterministic across a restart -- the fence
requirement -- but the naive form replays every interval missed while the daemon
was down, one per poll, which spends the owner's subscription on a backlog burst
(the exact risk design.md lists). Flooring fires once for a missed window, which
is also what the cron branch does with its minute bucket.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tinyassets.principals import named_principal

logger = logging.getLogger(__name__)

DB_FILENAME = ".automations.db"

#: Cadence floor. A tighter loop spends the owner's subscription faster than a
#: human can notice and cancel it (design.md "Risks": runaway cadence).
MIN_INTERVAL_SECONDS = 300

#: Per-universe ceiling on live automations. Counts every non-retired row:
#: pausing does not free a slot, deleting one does. A paused row still holds an
#: owner's intent and can be resumed without passing registration again.
MAX_ACTIVE_PER_UNIVERSE = 200

TRIGGER_INTERVAL = "interval"
TRIGGER_CRON = "cron"
STATE_ACTIVE = "active"
STATE_PAUSED = "paused"

#: Refusal-ledger key convention. Shared with the consumer and the owner's
#: surface, which read the reason back out of ``assigned_queue_refusals``.
REFUSAL_KEY_PREFIX = "automation:"

#: Consecutive failed attempts before the automation pauses itself. A cadence
#: that fails every period is an endless spend loop on the owner's subscription
#: (Codex ADAPT 2026-08-29 §6: a foreign-authored branch registered, then failed
#: forever while staying active). Reset by any successful run.
MAX_CONSECUTIVE_FAILURES = 3

#: Default ceiling on one automation run. Not a policy on how long work may
#: take -- a served turn runs until it is finished -- but a bound on how long a
#: consumer slot and a universe lease may be held by a run nothing will ever
#: finish. On expiry the run is CANCELLED through the runs API, not abandoned.
DEFAULT_RUN_TIMEOUT_SECONDS = 10800

#: How long a cancelled run is given to actually stop before the pump gives
#: up on it. The lease is held for the whole of it -- releasing sooner would
#: let a second process start while the first is still calling the provider.
DEFAULT_CANCEL_GRACE_SECONDS = 300

#: How often a held universe lease is re-stamped while its run is in flight.
LEASE_REFRESH_SECONDS = 60

#: Cadence floor for cron, in seconds. Same floor the interval trigger uses:
#: `* * * * *` across 20 automations declares 1,200 launches/hour against a
#: foreground `run_graph` budget of 20 (Codex ADAPT 2026-08-29 §7).
MIN_CRON_GAP_SECONDS = 300

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automations (
    automation_id      TEXT PRIMARY KEY,
    universe_id        TEXT NOT NULL,
    owner_principal_id TEXT NOT NULL,
    name               TEXT NOT NULL,
    branch_def_id      TEXT NOT NULL,
    trigger_kind       TEXT NOT NULL CHECK(trigger_kind IN ('interval','cron')),
    interval_seconds   INTEGER NOT NULL DEFAULT 0,
    cron_expr          TEXT NOT NULL DEFAULT '',
    inputs_json        TEXT NOT NULL DEFAULT '{}',
    desired_state      TEXT NOT NULL CHECK(desired_state IN ('active','paused')),
    pause_reason       TEXT NOT NULL DEFAULT '',
    revision           INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    retired_at         TEXT NOT NULL DEFAULT '',
    last_due_at        TEXT NOT NULL DEFAULT '',
    last_run_id        TEXT NOT NULL DEFAULT '',
    last_reason        TEXT NOT NULL DEFAULT '',
    last_finished_at   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automations_universe
    ON automations(universe_id, retired_at, created_at);

-- One row per universe with an automation in flight. The consumer's `_active`
-- map is process-local, so a restarted process (empty map) could launch an
-- automation for a universe an OLD process is still working (Codex ADAPT
-- 2026-08-29 §8). This lease is the shared fence: it lives in the database
-- both processes read, and it fences ALL automation work for the universe,
-- not just one `(automation_id, due_at)` pair.
CREATE TABLE IF NOT EXISTS universe_leases (
    universe_id TEXT PRIMARY KEY,
    holder      TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_attempts (
    automation_id TEXT NOT NULL,
    due_at        TEXT NOT NULL,
    claimed_at    TEXT NOT NULL,
    run_id        TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'claimed',
    reason        TEXT NOT NULL DEFAULT '',
    finished_at   TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (automation_id, due_at)
);
"""

#: Columns added after the first shipped schema. Applied by probe on every
#: connect so a database written by the previous build keeps working.
_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("automations", "consecutive_failures", "INTEGER NOT NULL DEFAULT 0"),
)


def run_timeout_seconds() -> float:
    """Ceiling on one automation run (``AUTOMATION_RUN_TIMEOUT_SECONDS``)."""
    raw = os.environ.get("AUTOMATION_RUN_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return float(DEFAULT_RUN_TIMEOUT_SECONDS)
    value = float(raw)
    if value <= 0:
        raise ValueError("AUTOMATION_RUN_TIMEOUT_SECONDS must be positive")
    return value


class AutomationRunTimeout(Exception):
    """The run outlived ``run_timeout_seconds()``, was cancelled, and stopped."""


class AutomationRunUnstopped(AutomationRunTimeout):
    """Cancelled at timeout but STILL RUNNING after the grace period.

    A subclass so every timeout handler catches both, but the caller can tell
    the two apart where it matters: the universe lease must NOT be released
    while a provider call the owner is paying for is still in flight.
    """


def cancel_grace_seconds() -> float:
    """How long to wait for a cancelled run to actually stop."""
    raw = os.environ.get("AUTOMATION_CANCEL_GRACE_SECONDS", "").strip()
    if not raw:
        return float(DEFAULT_CANCEL_GRACE_SECONDS)
    value = float(raw)
    if value <= 0:
        raise ValueError("AUTOMATION_CANCEL_GRACE_SECONDS must be positive")
    return value


def _await_cancelled_run(run_id: str) -> bool:
    """True when the run's worker ended within the grace period.

    Cancellation is checked between nodes, so a run inside a long provider call
    keeps going after the flag is set. The caller needs to know which happened:
    a stopped run frees its universe, one still running does not.
    """
    from tinyassets.runs import wait_for

    try:
        wait_for(run_id, timeout=cancel_grace_seconds())
    except TimeoutError:
        return False
    except Exception:  # noqa: BLE001 - the worker raised, but it HAS ended
        return True
    return True


def cron_min_gap_seconds(expr: str) -> int:
    """Smallest gap, in seconds, between two minutes this cron expression fires.

    Walks one week of minute buckets, which is enough to see every
    minute/hour/day-of-month/month/day-of-week interaction the parser supports,
    and measures the smallest distance between consecutive matches INCLUDING
    the wrap from the last match back to the first. A single match in the whole
    week has no gap to measure and is reported as a week.

    The schedules lane imports this after merge -- keep the signature stable.
    """
    from tinyassets.scheduler import CronSchedule

    schedule = CronSchedule.parse(expr)
    week_minutes = 7 * 24 * 60
    # A Monday 00:00 origin, so every day-of-week is visited exactly once.
    origin = datetime(2026, 1, 5, tzinfo=timezone.utc)
    matches = [
        minute
        for minute in range(week_minutes)
        if schedule.matches((origin + timedelta(minutes=minute)).timetuple())
    ]
    if len(matches) < 2:
        return week_minutes * 60
    gaps = [
        (later - earlier) * 60
        for earlier, later in zip(matches, matches[1:])
    ]
    gaps.append((matches[0] + week_minutes - matches[-1]) * 60)
    return min(gaps)


class AutomationUnavailable(Exception):
    """A registration that cannot fire, refused instead of stored (D4).

    ``reason`` is a short snake_case token the surface maps straight onto its
    error payload, so the owner reads a cause rather than a stack trace.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Automation:
    """One stored automation row (``inputs_json`` decoded into ``inputs``)."""

    automation_id: str
    universe_id: str
    owner_principal_id: str
    name: str
    branch_def_id: str
    trigger_kind: str
    interval_seconds: int
    cron_expr: str
    inputs: dict[str, Any]
    desired_state: str
    pause_reason: str
    revision: int
    created_at: str
    updated_at: str
    retired_at: str
    last_due_at: str
    last_run_id: str
    last_reason: str
    last_finished_at: str
    consecutive_failures: int = 0


# -- Time helpers -------------------------------------------------------------


def _as_utc(moment: datetime) -> datetime:
    """Normalize to an aware UTC datetime; a naive input is read as UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    """Second-resolution UTC ISO.

    Sub-second precision would make an interval's computed ``due_at``
    un-reproducible across a restart, and that reproducibility IS the fence.
    """
    return _as_utc(moment).replace(microsecond=0).isoformat()


def _parse(stamp: str) -> datetime | None:
    text = (stamp or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


# -- Store --------------------------------------------------------------------


def automations_db_path(base_path: str | Path) -> Path:
    return Path(base_path) / DB_FILENAME


def _from_row(row: sqlite3.Row) -> Automation:
    try:
        inputs = json.loads(row["inputs_json"] or "{}")
    except (TypeError, ValueError):
        inputs = {}
    return Automation(
        automation_id=str(row["automation_id"]),
        universe_id=str(row["universe_id"]),
        owner_principal_id=str(row["owner_principal_id"]),
        name=str(row["name"]),
        branch_def_id=str(row["branch_def_id"]),
        trigger_kind=str(row["trigger_kind"]),
        interval_seconds=int(row["interval_seconds"] or 0),
        cron_expr=str(row["cron_expr"] or ""),
        inputs=inputs if isinstance(inputs, dict) else {},
        desired_state=str(row["desired_state"]),
        pause_reason=str(row["pause_reason"] or ""),
        revision=int(row["revision"] or 1),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        retired_at=str(row["retired_at"] or ""),
        last_due_at=str(row["last_due_at"] or ""),
        last_run_id=str(row["last_run_id"] or ""),
        last_reason=str(row["last_reason"] or ""),
        last_finished_at=str(row["last_finished_at"] or ""),
        consecutive_failures=int(row["consecutive_failures"] or 0),
    )


class AutomationStore:
    """SQLite rows for one data root. Reads never create the database.

    A read that created the file would give a flag-off daemon a visible side
    effect, and the consumer scans every serving universe on every poll.
    """

    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path)

    @property
    def db_path(self) -> Path:
        return automations_db_path(self.base_path)

    def _connect(self, *, create: bool) -> sqlite3.Connection | None:
        path = self.db_path
        if not create and not path.is_file():
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: the fence needs an explicit BEGIN IMMEDIATE, not
        # Python's implicit deferred-transaction wrapper.
        conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.executescript(_SCHEMA)
        for table, column, decl in _MIGRATIONS:
            existing = {
                str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        return conn

    def get(self, automation_id: str) -> Automation | None:
        conn = self._connect(create=False)
        if conn is None:
            return None
        try:
            row = conn.execute(
                "SELECT * FROM automations WHERE automation_id = ?",
                (automation_id,),
            ).fetchone()
        finally:
            conn.close()
        return None if row is None else _from_row(row)

    def list(
        self,
        *,
        universe_id: str,
        include_retired: bool = False,
    ) -> list[Automation]:
        conn = self._connect(create=False)
        if conn is None:
            return []
        query = "SELECT * FROM automations WHERE universe_id = ?"
        if not include_retired:
            query += " AND retired_at = ''"
        query += " ORDER BY created_at ASC, automation_id ASC"
        try:
            rows = conn.execute(query, (universe_id,)).fetchall()
        finally:
            conn.close()
        return [_from_row(row) for row in rows]

    def list_for_branch(
        self,
        branch_def_id: str,
        *,
        include_retired: bool = False,
    ) -> list[Automation]:
        """Every automation, in ANY universe, bound to one branch. Used by the
        branch delete guard: registration promises not to store an automation
        that cannot fire, and deleting its branch would create exactly that."""
        conn = self._connect(create=False)
        if conn is None:
            return []
        query = "SELECT * FROM automations WHERE branch_def_id = ?"
        if not include_retired:
            query += " AND retired_at = ''"
        query += " ORDER BY created_at ASC, automation_id ASC"
        try:
            rows = conn.execute(query, (branch_def_id,)).fetchall()
        finally:
            conn.close()
        return [_from_row(row) for row in rows]

    def insert(self, automation: Automation) -> Automation:
        conn = self._connect(create=True)
        if conn is None:  # pragma: no cover - create=True always connects
            raise RuntimeError("automation store connection is unavailable")
        try:
            conn.execute(
                """
                INSERT INTO automations (
                    automation_id, universe_id, owner_principal_id, name,
                    branch_def_id, trigger_kind, interval_seconds, cron_expr,
                    inputs_json, desired_state, pause_reason, revision,
                    created_at, updated_at, retired_at, last_due_at,
                    last_run_id, last_reason, last_finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    automation.automation_id,
                    automation.universe_id,
                    automation.owner_principal_id,
                    automation.name,
                    automation.branch_def_id,
                    automation.trigger_kind,
                    automation.interval_seconds,
                    automation.cron_expr,
                    json.dumps(automation.inputs, sort_keys=True),
                    automation.desired_state,
                    automation.pause_reason,
                    automation.revision,
                    automation.created_at,
                    automation.updated_at,
                    automation.retired_at,
                    automation.last_due_at,
                    automation.last_run_id,
                    automation.last_reason,
                    automation.last_finished_at,
                ),
            )
        finally:
            conn.close()
        return automation

    def claim_attempt(self, automation_id: str, due_at: str, *, now: datetime) -> bool:
        """Claim ``(automation_id, due_at)`` for exactly one caller (D2).

        The existence check and the insert run inside one ``BEGIN IMMEDIATE`` so
        two pollers -- or one poller either side of a restart -- cannot both
        pass. Returns False when the pair is already claimed.
        """
        conn = self._connect(create=True)
        if conn is None:  # pragma: no cover - create=True always connects
            raise RuntimeError("automation store connection is unavailable")
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT 1 FROM automation_attempts "
                    "WHERE automation_id = ? AND due_at = ?",
                    (automation_id, due_at),
                ).fetchone()
                if existing is not None:
                    conn.execute("ROLLBACK")
                    return False
                conn.execute(
                    "INSERT INTO automation_attempts "
                    "(automation_id, due_at, claimed_at) VALUES (?, ?, ?)",
                    (automation_id, due_at, _iso(now)),
                )
                conn.execute("COMMIT")
                return True
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def finish_attempt(
        self,
        automation_id: str,
        due_at: str,
        *,
        run_id: str,
        status: str,
        reason: str,
        now: datetime,
        row_reason: str | None = None,
        succeeded: bool | None = None,
    ) -> None:
        """Close the attempt and roll its outcome onto the automation row.

        Both writes share one transaction: an attempt whose outcome never
        reached its automation would recompute the same ``due_at`` forever,
        claim it, and skip -- an automation stuck silent with no reason.

        ``row_reason`` lets the owner-facing row differ from the refusal-ledger
        text: the ledger keeps the consumer's ``ok:ran:<run_id>`` convention
        while the row reads a plain ``ok`` (Codex ADAPT §6 -- a success written
        only into a table named "refusals" is not an owner-legible receipt).

        ``succeeded`` drives the consecutive-failure counter: True resets it,
        False increments it, None leaves it (a skip that never ran, such as a
        rate-limited attempt, is neither a success nor a failure of the work).
        """
        stamp = _iso(now)
        conn = self._connect(create=True)
        if conn is None:  # pragma: no cover - create=True always connects
            raise RuntimeError("automation store connection is unavailable")
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE automation_attempts SET run_id = ?, status = ?, "
                    "reason = ?, finished_at = ? "
                    "WHERE automation_id = ? AND due_at = ?",
                    (run_id, status, reason, stamp, automation_id, due_at),
                )
                if succeeded is True:
                    failures_sql = "consecutive_failures = 0, "
                elif succeeded is False:
                    failures_sql = (
                        "consecutive_failures = consecutive_failures + 1, "
                    )
                else:
                    failures_sql = ""
                conn.execute(
                    "UPDATE automations SET last_due_at = ?, last_run_id = ?, "
                    f"last_reason = ?, last_finished_at = ?, {failures_sql}"
                    "updated_at = ? WHERE automation_id = ?",
                    (
                        due_at,
                        run_id,
                        reason if row_reason is None else row_reason,
                        stamp,
                        stamp,
                        automation_id,
                    ),
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    # -- Cross-process per-universe lease ----------------------------------

    def acquire_universe_lease(
        self,
        universe_id: str,
        *,
        holder: str,
        now: datetime,
        ttl_seconds: float,
    ) -> bool:
        """Take the universe's automation lease, or report who already holds it.

        `_active[universe_id]` in the consumer is process-local: a restarted
        process starts with an EMPTY map and would happily launch an automation
        for a universe the old process is still working (Codex ADAPT §8). This
        lease is shared state, so both processes see it.

        An EXPIRED lease is stealable -- a process that died mid-run must not
        wedge its universe forever. TTL is the run timeout, and the holder
        re-stamps it while it works, so expiry means "nobody is refreshing".
        """
        deadline = _iso(now + timedelta(seconds=ttl_seconds))
        moment = _as_utc(now)
        conn = self._connect(create=True)
        if conn is None:  # pragma: no cover - create=True always connects
            raise RuntimeError("automation store connection is unavailable")
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT holder, expires_at FROM universe_leases "
                    "WHERE universe_id = ?",
                    (universe_id,),
                ).fetchone()
                if row is not None and str(row["holder"]) != holder:
                    expires = _parse(str(row["expires_at"]))
                    if expires is not None and expires > moment:
                        conn.execute("ROLLBACK")
                        return False
                conn.execute(
                    "INSERT INTO universe_leases (universe_id, holder, expires_at) "
                    "VALUES (?, ?, ?) ON CONFLICT(universe_id) DO UPDATE SET "
                    "holder = excluded.holder, expires_at = excluded.expires_at",
                    (universe_id, holder, deadline),
                )
                conn.execute("COMMIT")
                return True
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def refresh_universe_lease(
        self,
        universe_id: str,
        *,
        holder: str,
        now: datetime,
        ttl_seconds: float,
    ) -> bool:
        """Re-stamp a lease this holder still owns. False once it has been lost."""
        deadline = _iso(now + timedelta(seconds=ttl_seconds))
        conn = self._connect(create=True)
        if conn is None:  # pragma: no cover
            raise RuntimeError("automation store connection is unavailable")
        try:
            cursor = conn.execute(
                "UPDATE universe_leases SET expires_at = ? "
                "WHERE universe_id = ? AND holder = ?",
                (deadline, universe_id, holder),
            )
            return cursor.rowcount > 0
        finally:
            conn.close()

    def release_universe_lease(self, universe_id: str, *, holder: str) -> None:
        """Drop a lease this holder owns. Never steals another holder's row."""
        conn = self._connect(create=False)
        if conn is None:
            return
        try:
            conn.execute(
                "DELETE FROM universe_leases WHERE universe_id = ? AND holder = ?",
                (universe_id, holder),
            )
        finally:
            conn.close()

    def universe_lease_holder(self, universe_id: str, *, now: datetime) -> str:
        """The live holder of this universe's lease, or '' if unheld/expired."""
        conn = self._connect(create=False)
        if conn is None:
            return ""
        try:
            row = conn.execute(
                "SELECT holder, expires_at FROM universe_leases WHERE universe_id = ?",
                (universe_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return ""
        expires = _parse(str(row["expires_at"]))
        if expires is None or expires <= _as_utc(now):
            return ""
        return str(row["holder"])

    def set_desired_state(
        self,
        automation_id: str,
        desired: str,
        *,
        expected_revision: int,
        reason: str = "",
        now: datetime,
    ) -> Automation:
        """Owner-driven pause/resume under optimistic concurrency."""
        if desired not in {STATE_ACTIVE, STATE_PAUSED}:
            raise ValueError(f"unknown desired state {desired!r}")
        return self._write_state(
            automation_id,
            expected_revision=expected_revision,
            now=now,
            desired_state=desired,
            pause_reason=reason if desired == STATE_PAUSED else "",
        )

    def retire(
        self,
        automation_id: str,
        *,
        expected_revision: int,
        now: datetime,
    ) -> Automation:
        """The owner's delete. The row stays as the record of what ran."""
        return self._write_state(
            automation_id,
            expected_revision=expected_revision,
            now=now,
            desired_state=STATE_PAUSED,
            pause_reason="retired",
            retire=True,
        )

    def pause_for_reason(
        self,
        automation_id: str,
        *,
        reason: str,
        now: datetime,
    ) -> Automation:
        """Revision-agnostic pause for the run path (D3).

        The run path is not the owner and holds no revision expectation: an
        owner edit racing a refused run must not leave the automation active
        with authority it no longer has.
        """
        return self._write_state(
            automation_id,
            expected_revision=None,
            now=now,
            desired_state=STATE_PAUSED,
            pause_reason=reason,
        )

    def _write_state(
        self,
        automation_id: str,
        *,
        expected_revision: int | None,
        now: datetime,
        desired_state: str,
        pause_reason: str,
        retire: bool = False,
    ) -> Automation:
        stamp = _iso(now)
        conn = self._connect(create=False)
        if conn is None:
            raise ValueError(f"automation {automation_id!r} does not exist")
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM automations WHERE automation_id = ?",
                    (automation_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"automation {automation_id!r} does not exist")
                current = _from_row(row)
                if current.retired_at:
                    raise ValueError(f"automation {automation_id!r} is retired")
                if (
                    expected_revision is not None
                    and current.revision != expected_revision
                ):
                    raise ValueError(
                        f"automation {automation_id!r} is at revision "
                        f"{current.revision}, not {expected_revision}"
                    )
                conn.execute(
                    "UPDATE automations SET desired_state = ?, pause_reason = ?, "
                    "retired_at = ?, revision = ?, updated_at = ? "
                    "WHERE automation_id = ?",
                    (
                        desired_state,
                        pause_reason,
                        stamp if retire else current.retired_at,
                        current.revision + 1,
                        stamp,
                        automation_id,
                    ),
                )
                updated = conn.execute(
                    "SELECT * FROM automations WHERE automation_id = ?",
                    (automation_id,),
                ).fetchone()
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return _from_row(updated)


# -- Registration -------------------------------------------------------------


def _validated_trigger(interval_seconds: Any, cron_expr: Any) -> tuple[str, int, str]:
    from tinyassets.scheduler import CronParseError, CronSchedule

    try:
        seconds = int(interval_seconds or 0)
    except (TypeError, ValueError) as exc:
        raise AutomationUnavailable("trigger_invalid") from exc
    expr = str(cron_expr or "").strip()
    if seconds < 0:
        raise AutomationUnavailable("trigger_invalid")
    # Exactly one trigger: neither leaves nothing to fire on, both leaves two
    # answers to "when is this next due".
    if (seconds > 0) == bool(expr):
        raise AutomationUnavailable("trigger_invalid")
    if seconds > 0:
        if seconds < MIN_INTERVAL_SECONDS:
            raise AutomationUnavailable("trigger_invalid")
        return TRIGGER_INTERVAL, seconds, ""
    try:
        CronSchedule.parse(expr)
    except CronParseError as exc:
        raise AutomationUnavailable("trigger_invalid") from exc
    # The interval floor was meaningless while cron could express `* * * * *`:
    # 20 rows x 60/hour is 1,200 launches against a foreground budget of 20
    # (Codex ADAPT §7). The floor is on the SMALLEST gap the expression can
    # produce, including the wrap past the end of its cycle -- `0,3 * * * *`
    # looks hourly until you notice the three-minute gap inside each hour.
    if cron_min_gap_seconds(expr) < MIN_CRON_GAP_SECONDS:
        raise AutomationUnavailable("trigger_invalid")
    return TRIGGER_CRON, 0, expr


def register_automation(
    base_path: str | Path,
    *,
    universe_id: str,
    owner_principal_id: str,
    name: str,
    branch_def_id: str,
    interval_seconds: int = 0,
    cron_expr: str = "",
    inputs: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Automation:
    """Store one automation, or refuse with a named reason (D4).

    Every precondition a due run needs is checked HERE, in the owner's own
    request, where a refusal is a message they can act on. Storing a row that
    cannot fire would move the failure onto a background thread they never see.
    """
    from tinyassets.api.branches import _resolve_readable_branch
    from tinyassets.daemon_server import get_founder_home, universe_access_permission
    from tinyassets.provider_assignment import load_provider_assignment
    from tinyassets.provider_serving_binding import _is_open_provider
    from tinyassets.runtime.assigned_queue_consumer import (
        assigned_queue_consumer_enabled,
    )

    base = Path(base_path)
    uid = str(universe_id or "").strip()
    owner = named_principal(owner_principal_id)

    if not assigned_queue_consumer_enabled():
        raise AutomationUnavailable("consumer_disabled")
    if not owner:
        raise AutomationUnavailable("authentication_required")
    if universe_access_permission(base, universe_id=uid, actor_id=owner) != "admin":
        raise AutomationUnavailable("owner_not_admin")
    if get_founder_home(base, owner) != uid:
        raise AutomationUnavailable("not_owner_home")
    assignment = load_provider_assignment(base, universe_id=uid)
    if assignment is None or assignment.state != "ready":
        raise AutomationUnavailable("no_serving_assignment")
    # A "ready" OPEN (api_key_http) assignment is still unusable here: foreground
    # admission refuses open providers outright (foreground_run_provider.py:247).
    # Registration must refuse exactly what admission refuses, or the row is
    # stored and fails every period forever (Codex ADAPT §6).
    if _is_open_provider(str(assignment.provider or "")):
        raise AutomationUnavailable("no_serving_assignment")
    resolved = _resolve_readable_branch(str(branch_def_id or "").strip(), str(base))
    if resolved is None:
        raise AutomationUnavailable("branch_not_readable")
    # READABLE is not RUNNABLE. `_resolve_readable_branch` admits any public
    # branch, but foreground admission requires `branch.author == principal`
    # (foreground_run_provider.py:211-213). Codex registered a public
    # Bob-authored branch for Alice and every run then failed before reaching a
    # provider, leaving the automation active -- an endless cadence-driven
    # failure loop. Refuse it where the owner can read the reason.
    if str(resolved[1].get("author") or "").strip() != owner:
        raise AutomationUnavailable("branch_not_owned")
    trigger_kind, seconds, expr = _validated_trigger(interval_seconds, cron_expr)

    store = AutomationStore(base)
    if len(store.list(universe_id=uid)) >= MAX_ACTIVE_PER_UNIVERSE:
        raise AutomationUnavailable("too_many_automations")

    stamp = _iso(now or datetime.now(timezone.utc))
    return store.insert(
        Automation(
            automation_id=uuid.uuid4().hex,
            universe_id=uid,
            owner_principal_id=owner,
            name=str(name or "").strip(),
            branch_def_id=resolved[0],
            trigger_kind=trigger_kind,
            interval_seconds=seconds,
            cron_expr=expr,
            inputs=dict(inputs or {}),
            desired_state=STATE_ACTIVE,
            pause_reason="",
            revision=1,
            created_at=stamp,
            updated_at=stamp,
            retired_at="",
            last_due_at="",
            last_run_id="",
            last_reason="",
            last_finished_at="",
        )
    )


# -- Due selection ------------------------------------------------------------


def _due_instant(automation: Automation, now: datetime) -> str:
    """The ``due_at`` this automation is currently owed, or '' if none.

    Deterministic in ``now``: two pollers, or one either side of a restart, at
    the same wall-clock derive the same string, so the fence holds.
    """
    moment = _as_utc(now)
    last = _parse(automation.last_due_at)
    if automation.trigger_kind == TRIGGER_INTERVAL:
        anchor = last or _parse(automation.created_at)
        if anchor is None or automation.interval_seconds <= 0:
            return ""
        elapsed = (moment - anchor).total_seconds()
        periods = int(elapsed // automation.interval_seconds)
        if periods < 1:
            return ""
        # Floor onto the period grid: a daemon down for ten intervals owes ONE
        # run, not ten. The naive anchor+interval form replays the backlog.
        return _iso(anchor + timedelta(seconds=periods * automation.interval_seconds))
    if automation.trigger_kind == TRIGGER_CRON:
        from tinyassets.scheduler import _cron_matches

        bucket = moment.replace(second=0, microsecond=0)
        if last is not None and last >= bucket:
            return ""
        # Local time, matching the scheduler: a cron expression an owner wrote
        # means their clock, and two cron surfaces disagreeing would be worse.
        if not _cron_matches(automation.cron_expr, time.localtime(moment.timestamp())):
            return ""
        return _iso(bucket)
    return ""


def due_automations(
    base_path: str | Path,
    *,
    universe_id: str,
    now: datetime,
) -> list[tuple[Automation, str]]:
    """Active, non-retired automations owed a run at ``now``, with their due_at."""
    due: list[tuple[Automation, str]] = []
    for automation in AutomationStore(base_path).list(universe_id=universe_id):
        if automation.desired_state != STATE_ACTIVE:
            continue
        due_at = _due_instant(automation, now)
        if due_at:
            due.append((automation, due_at))
    return due


# -- Run path -----------------------------------------------------------------


def _runtime_authority_reason(base_path: Path, automation: Automation) -> str:
    """'' when this automation may run right now, else the refusal token (D3).

    Re-derived from live state on every run. Registration proved the owner held
    admin over their own home with a ready assignment; between two ticks any of
    the three can be revoked, and the RUN has to notice, not the row.
    """
    from tinyassets.daemon_server import get_founder_home, universe_access_permission
    from tinyassets.provider_assignment import load_provider_assignment

    owner = automation.owner_principal_id
    uid = automation.universe_id
    if universe_access_permission(base_path, universe_id=uid, actor_id=owner) != "admin":
        return "owner_lost_admin"
    if get_founder_home(base_path, owner) != uid:
        return "not_owner_home"
    assignment = load_provider_assignment(base_path, universe_id=uid)
    if assignment is None or assignment.state != "ready":
        return "no_serving_assignment"
    return ""


def _bind_automation_provider_call(base_path: Path, automation: Automation) -> Any:
    """The foreground run recipe, with the owner supplied explicitly.

    ``tinyassets.api.runs._bind_run_provider_call`` reads the principal off the
    request; a consumer thread has no request, so the principal comes off the
    automation row instead. Everything downstream -- founder-home validation,
    the CURRENT assignment, custody, admission, budget -- is the foreground path
    unchanged, which is what lets a provider switch need no re-preparation.
    """
    from tinyassets.config import load_universe_config
    from tinyassets.foreground_run_provider import new_foreground_run_provider_session
    from tinyassets.providers.base import UniverseContext
    from tinyassets.providers.call import bind_universe_provider_call, call_provider

    universe_dir = (base_path / automation.universe_id).resolve()
    if not universe_dir.is_relative_to(base_path.resolve()):
        raise ValueError(f"invalid universe_id: {automation.universe_id!r}")
    session = new_foreground_run_provider_session(
        base_path,
        universe_id=automation.universe_id,
        principal_id=automation.owner_principal_id,
        provider_call=call_provider,
    )
    return bind_universe_provider_call(
        session,
        UniverseContext(
            universe_dir=universe_dir,
            config=load_universe_config(universe_dir),
        ),
        operation="run_graph",
    )


def _load_branch(base_path: Path, automation: Automation) -> Any:
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition

    branch = BranchDefinition.from_dict(
        get_branch_definition(base_path, branch_def_id=automation.branch_def_id)
    )
    errors = branch.validate()
    if errors:
        raise ValueError(
            f"branch {automation.branch_def_id} failed validation: {errors}"
        )
    return branch


#: Text the graph records when a run died because the owner's authority went
#: away mid-run. Matched by `_failure_pause_reason` to pause rather than retry.
AUTHORITY_LOST_MARKER = "automation_owner_lost_admin"


def _authority_guard(base_path: Path, automation: Automation):
    """A per-node re-check of the owner's live authority (Codex ADAPT §5).

    Codex's repro: revoke the owner's admin AFTER `_runtime_authority_reason`
    returns and BEFORE the launch, and the run still reaches the provider once.
    The window is real because the foreground session re-checks founder home
    and branch authorship on every attempt but NOT the admin ACL
    (foreground_run_provider.py:114-145, 206-246).

    This closes it from the caller's side, without editing that authority
    module. The compiler emits ``phase="starting"`` BEFORE a prompt node's
    provider call (graph_compiler.py:1187-1199), which reaches this callback via
    `runs._emit_node_status`.

    It must raise a CANCEL-shaped exception, and that is not a stylistic choice.
    The compiler wraps the seam in ``except Exception`` and re-raises only what
    `_is_cancel_exception` matches -- a NAME match on ``RunCancelledError``
    (graph_compiler.py:296-304). A `RunExecutionAuthorityLost` raised here is
    logged and SWALLOWED, and the provider is then called anyway: measured, one
    real provider call still reached the fake in Codex's repro. So the guard
    raises the runner's own cancel error, the graph unwinds before the call, and
    `run_due_automation` re-reads live authority when the run comes back
    non-completed.

    Two shapes were considered and rejected, both for evidence rather than
    taste:
      * Wrapping the BOUND provider_call: `_locate_session` requires the session
        at chain depth exactly 1, so any outer wrapper makes
        `prepare_foreground_run_provider` raise and every run fail
        (foreground_run_provider.py:666-676, 730-742).
      * Wrapping the INNER `call_provider` handed to the session: the session
        routes any callable whose `__module__` is not
        `tinyassets.providers.call` down its unarmed STUB path, skipping
        `_ensure_admitted()` and `_authorize_attempt` entirely
        (foreground_run_provider.py:537-557). That would have silently disabled
        foreground admission for every automation -- a far worse hole than the
        one being closed.
    """
    from tinyassets.runs import NODE_STATUS_RUNNING, RunCancelledError

    def guard(node_id: str, status: str) -> None:
        if status != NODE_STATUS_RUNNING:
            return
        lost = _runtime_authority_reason(base_path, automation)
        if lost:
            # The message IS the diagnosis. Measured 2026-08-29: the run row
            # ends up carrying this text verbatim (status `cancelled`, error
            # `automation_owner_lost_admin:...`), so an owner can tell an
            # authority cancel from a user pressing stop by reading the run.
            # Codex round 2 §2 named `_invoke_graph`'s generic-cancel branch as
            # the writer; it is not the one that writes this row -- reverting a
            # marker-preserving patch there changed no observed output, so no
            # change was made to that authority-adjacent file.
            raise RunCancelledError(f"{AUTHORITY_LOST_MARKER}:{lost}")

    return guard


def _execute(
    base_path: Path,
    automation: Automation,
    provider_call: Any,
    branch: Any,
    inputs: dict[str, Any],
    on_run_started: Any = None,
) -> Any:
    """The one seam a test may replace. Everything authority-bearing is above it.

    Substituting this fakes the graph, never the session: the provider call
    handed in has already resolved the universe's live assignment.

    Async-then-block, NOT the synchronous ``execute_branch``: only the async
    entry points call ``prepare_foreground_run_provider``
    (``runs.py:3205``/``3634``), and an unprepared foreground session refuses
    every provider call with ``ProviderAuthorityHeldError`` -- its receipt is
    minted against a run id it would never have been given. So a run started
    through the sync path with a foreground session bound would fail at its
    first prompt node. We start it the way ``enqueue_universe_branch_run``
    does, then block this consumer thread until the run is terminal so the
    attempt records the outcome rather than "queued", and the universe's one
    active slot stays held for as long as its automation is really running.

    The wait is bounded by ``run_timeout_seconds()``. On expiry the run is
    CANCELLED through the runs API rather than abandoned, so the worker and its
    provider authority claim unwind instead of leaking (Codex ADAPT §1).
    """
    from dataclasses import replace as _replace

    from tinyassets.runs import (
        RUN_STATUS_FAILED,
        execute_branch_async,
        get_run,
        request_cancel,
        wait_for,
    )

    outcome = execute_branch_async(
        base_path,
        branch=branch,
        inputs=inputs,
        run_name=f"automation:{automation.automation_id[:8]}",
        actor=f"universe:{automation.universe_id}",
        provider_call=provider_call,
        on_node_status=_authority_guard(base_path, automation),
        _enqueue_universe_id=automation.universe_id,
    )
    run_id = str(getattr(outcome, "run_id", "") or "")
    # Publish the run id BEFORE blocking on it. Announcing it after `wait_for`
    # returned meant `stop()` could never see an active run -- the only moment
    # it needed one was while the wait was still in progress (Codex round 2 §3c).
    if callable(on_run_started) and run_id:
        on_run_started(run_id)
    if not run_id or outcome.status == RUN_STATUS_FAILED:
        # Admission already refused this run; there is no worker to wait on.
        return outcome
    try:
        wait_for(run_id, timeout=run_timeout_seconds())
    except TimeoutError as exc:
        # Cancellation is COOPERATIVE and deliberately does not interrupt an
        # active provider call. Releasing the universe now would let another
        # process start work while this one is still talking to the provider on
        # the owner's subscription (Codex round 2 §3b), so wait out a bounded
        # grace and report whether the worker actually ended.
        request_cancel(base_path, run_id)
        if _await_cancelled_run(run_id):
            raise AutomationRunTimeout(
                f"automation run {run_id} exceeded {run_timeout_seconds()}s; "
                "cancelled and stopped"
            ) from exc
        raise AutomationRunUnstopped(
            f"automation run {run_id} ignored cancellation for "
            f"{cancel_grace_seconds()}s; universe stays leased"
        ) from exc
    record = get_run(base_path, run_id) or {}
    return _replace(
        outcome,
        status=str(record.get("status") or outcome.status),
        error=str(record.get("error") or outcome.error or ""),
    )


def _record_refusal(
    base_path: Path,
    automation: Automation,
    reason: str,
    now: datetime,
    consumer_id: str,
) -> None:
    from tinyassets.storage.assigned_queue_refusals import AssignedQueueRefusalStore

    try:
        AssignedQueueRefusalStore(base_path).record(
            branch_task_id=f"{REFUSAL_KEY_PREFIX}{automation.automation_id}",
            universe_id=automation.universe_id,
            reason=reason,
            observed_at=_iso(now),
            consumer_id=consumer_id,
        )
    except Exception:  # noqa: BLE001 - the ledger must never take the pump down
        logger.exception(
            "automation refusal record failed automation=%s",
            automation.automation_id,
        )


def _append_run_ledger(automation: Automation, run_id: str, due_at: str) -> None:
    from tinyassets.api.branches import _append_global_ledger

    try:
        _append_global_ledger(
            "run_branch",
            actor=f"universe:{automation.universe_id}",
            target=run_id,
            summary=(
                f"automation={automation.automation_id} due_at={due_at} "
                f"branch={automation.branch_def_id}"
            ),
            payload=None,
        )
    except Exception as exc:  # noqa: BLE001 - ledger loss must not fail the run
        logger.warning("automation run ledger write failed: %s", exc)


#: Error text that means the run never got past admission, so retrying it next
#: period would fail identically. Pausing beats looping (Codex ADAPT §6).
_ADMISSION_REFUSED_MARKERS = (
    "ProviderAuthorityHeldError",
    "PermissionError",
    "Provider authority admission failed",
    "provider authority",
)


def _failure_pause_reason(error_text: str) -> str:
    """Why a failed run should pause the automation, or '' to retry next period."""
    text = error_text or ""
    if AUTHORITY_LOST_MARKER in text:
        return "owner_lost_admin"
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in _ADMISSION_REFUSED_MARKERS):
        return "run_admission_refused"
    return ""


def run_due_automation(
    base_path: str | Path,
    automation: Automation,
    due_at: str,
    *,
    now: datetime | None = None,
    consumer_id: str = "",
    on_run_started: Any = None,
) -> str:
    """Run one due automation and return the reason recorded for it.

    Never raises: the caller is a pump across every universe, and one owner's
    broken automation must not stop another owner's working one. Every exit
    records a reason -- there is no silent return (Codex ADAPT §6).

    ``on_run_started`` receives the run id as soon as one exists, so the
    consumer can cancel an in-flight automation on shutdown.
    """
    # _error_reason is the consumer's bounded, path/secret-stripped formatter.
    # Imported rather than duplicated so both halves of the pump sanitise
    # identically; the function-local import keeps the two modules acyclic.
    from tinyassets.runtime.assigned_queue_consumer import _error_reason

    base = Path(base_path)
    moment = _as_utc(now or datetime.now(timezone.utc))
    store = AutomationStore(base)

    # The claim is INSIDE the guarded region: a SQLite failure here used to
    # escape with no attempt row and no refusal, so the owner saw nothing at all.
    try:
        claimed = store.claim_attempt(automation.automation_id, due_at, now=moment)
    except Exception as exc:  # noqa: BLE001 - a fence failure is still an outcome
        reason = _error_reason("claim_error", exc)
        logger.exception(
            "automation claim failed automation=%s due_at=%s",
            automation.automation_id,
            due_at,
        )
        _record_refusal(base, automation, reason, moment, consumer_id)
        return reason
    if not claimed:
        # Only reachable when a restart re-derives an instant an older process
        # already owns. Rare, and previously invisible -- record it.
        _record_refusal(base, automation, "attempt_exists", moment, consumer_id)
        return "attempt_exists"

    try:
        blocked = _runtime_authority_reason(base, automation)
        if blocked:
            store.finish_attempt(
                automation.automation_id,
                due_at,
                run_id="",
                status="refused",
                reason=blocked,
                now=moment,
            )
            store.pause_for_reason(
                automation.automation_id,
                reason=blocked,
                now=moment,
            )
            _record_refusal(base, automation, blocked, moment, consumer_id)
            return blocked

        # The same rolling 20/hour engine budget a foreground `run_graph` pays
        # (Codex ADAPT §7). Counted against THIS universe, so one owner's
        # cadence cannot exhaust another's. A refusal is NOT a pause: the
        # budget refills, so the next period simply tries again.
        from tinyassets.engine_mcp_server import _admission_parts, _engine_run_admit

        ticket, _refused_by = _admission_parts(
            _engine_run_admit(universe_id=automation.universe_id, want_ticket=True)
        )
        if ticket is None:
            store.finish_attempt(
                automation.automation_id,
                due_at,
                run_id="",
                status="refused",
                reason="run_rate_limited",
                now=moment,
            )
            _record_refusal(base, automation, "run_rate_limited", moment, consumer_id)
            return "run_rate_limited"

        branch = _load_branch(base, automation)
        provider_call = _bind_automation_provider_call(base, automation)

        def _started(run_id: str) -> None:
            # Bind the admission to the run the moment it exists, so a run that
            # only READ settles off the write budget like a foreground run
            # (tinyassets.engine_admissions); _execute publishes the id before
            # it blocks on completion.
            from tinyassets.engine_admissions import attach_run

            attach_run(ticket, str(run_id or ""))
            if callable(on_run_started):
                on_run_started(run_id)

        outcome = _execute(
            base,
            automation,
            provider_call,
            branch,
            dict(automation.inputs),
            _started,
        )
        from tinyassets.runs import RUN_STATUS_COMPLETED

        run_id = str(getattr(outcome, "run_id", "") or "")
        status = str(getattr(outcome, "status", "") or "unknown")
        succeeded = status == RUN_STATUS_COMPLETED
        reason = f"ok:ran:{run_id}" if succeeded else f"run_failed:{status}"
        store.finish_attempt(
            automation.automation_id,
            due_at,
            run_id=run_id,
            status=status,
            reason=reason,
            now=moment,
            # The ledger keeps the consumer's `ok:ran:<id>` convention; the ROW
            # reads a plain `ok`, so an owner surface reads success from the
            # automation rather than from a table called "refusals".
            row_reason="ok" if succeeded else reason,
            succeeded=succeeded,
        )
        _record_refusal(base, automation, reason, moment, consumer_id)
        _append_run_ledger(automation, run_id, due_at)
        if not succeeded:
            _pause_if_hopeless(
                base,
                store,
                automation,
                str(getattr(outcome, "error", "") or ""),
                moment,
                consumer_id,
            )
        return reason
    except AutomationRunTimeout as exc:
        # The fence row STAYS: this instant was attempted and must not be
        # re-launched by the next poll. The run itself has been cancelled.
        # `run_timeout_unreleased` additionally tells the caller NOT to give
        # the universe back yet -- the worker ignored the cancel and is still
        # spending the owner's subscription (Codex round 2 §3b).
        reason = (
            "run_timeout_unreleased"
            if isinstance(exc, AutomationRunUnstopped)
            else "run_timeout"
        )
        logger.warning("automation run timed out: %s", exc)
        _close_attempt_quietly(
            store, automation, due_at, status="timeout", reason=reason, now=moment
        )
        _record_refusal(base, automation, reason, moment, consumer_id)
        _pause_if_hopeless(base, store, automation, "", moment, consumer_id)
        return reason
    except Exception as exc:  # noqa: BLE001 - the pump continues; the row says why
        reason = _error_reason("automation_error", exc)
        logger.exception(
            "automation run failed automation=%s due_at=%s",
            automation.automation_id,
            due_at,
        )
        _close_attempt_quietly(
            store, automation, due_at, status="error", reason=reason, now=moment
        )
        _record_refusal(base, automation, reason, moment, consumer_id)
        _pause_if_hopeless(base, store, automation, str(exc), moment, consumer_id)
        return reason


def _close_attempt_quietly(
    store: AutomationStore,
    automation: Automation,
    due_at: str,
    *,
    status: str,
    reason: str,
    now: datetime,
) -> None:
    try:
        store.finish_attempt(
            automation.automation_id,
            due_at,
            run_id="",
            status=status,
            reason=reason,
            now=now,
            succeeded=False,
        )
    except Exception:  # noqa: BLE001 - the refusal record is still owed
        logger.exception(
            "automation attempt close failed automation=%s",
            automation.automation_id,
        )


def _pause_if_hopeless(
    base_path: Path,
    store: AutomationStore,
    automation: Automation,
    error_text: str,
    now: datetime,
    consumer_id: str,
) -> None:
    """Stop a cadence that cannot succeed, instead of paying for it hourly.

    Three triggers, in order. Live authority loss wins: whatever ended the run,
    an owner who no longer holds admin over their own home must not be retried
    next period -- and the per-node guard cancels the run rather than failing
    it, so the reason is not in the error text to read. Then a deterministic
    admission/authority failure, which pauses on the first occurrence because
    the next period fails identically. Everything else gets
    `MAX_CONSECUTIVE_FAILURES` tries, because a transient provider or network
    failure should not retire an owner's automation.
    """
    reason = _runtime_authority_reason(base_path, automation)
    if not reason:
        reason = _failure_pause_reason(error_text)
    if not reason:
        current = store.get(automation.automation_id)
        failures = 0 if current is None else current.consecutive_failures
        if failures < MAX_CONSECUTIVE_FAILURES:
            return
        reason = "repeated_failures"
    try:
        store.pause_for_reason(automation.automation_id, reason=reason, now=now)
    except Exception:  # noqa: BLE001 - the run outcome is already recorded
        logger.exception(
            "automation auto-pause failed automation=%s", automation.automation_id
        )
        return
    _record_refusal(base_path, automation, reason, now, consumer_id)


__all__ = [
    "DEFAULT_RUN_TIMEOUT_SECONDS",
    "LEASE_REFRESH_SECONDS",
    "MAX_ACTIVE_PER_UNIVERSE",
    "MAX_CONSECUTIVE_FAILURES",
    "MIN_CRON_GAP_SECONDS",
    "MIN_INTERVAL_SECONDS",
    "REFUSAL_KEY_PREFIX",
    "Automation",
    "AutomationRunTimeout",
    "AutomationRunUnstopped",
    "AutomationStore",
    "AutomationUnavailable",
    "automations_db_path",
    "cancel_grace_seconds",
    "cron_min_gap_seconds",
    "due_automations",
    "register_automation",
    "run_due_automation",
    "run_timeout_seconds",
]
