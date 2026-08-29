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
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_FILENAME = ".automations.db"

#: Cadence floor. A tighter loop spends the owner's subscription faster than a
#: human can notice and cancel it (design.md "Risks": runaway cadence).
MIN_INTERVAL_SECONDS = 300

#: Per-universe ceiling on live automations. Counts every non-retired row:
#: pausing does not free a slot, deleting one does. A paused row still holds an
#: owner's intent and can be resumed without passing registration again.
MAX_ACTIVE_PER_UNIVERSE = 20

TRIGGER_INTERVAL = "interval"
TRIGGER_CRON = "cron"
STATE_ACTIVE = "active"
STATE_PAUSED = "paused"

#: Refusal-ledger key convention. Shared with the consumer and the owner's
#: surface, which read the reason back out of ``assigned_queue_refusals``.
REFUSAL_KEY_PREFIX = "automation:"

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
    ) -> None:
        """Close the attempt and roll its outcome onto the automation row.

        Both writes share one transaction: an attempt whose outcome never
        reached its automation would recompute the same ``due_at`` forever,
        claim it, and skip -- an automation stuck silent with no reason.
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
                conn.execute(
                    "UPDATE automations SET last_due_at = ?, last_run_id = ?, "
                    "last_reason = ?, last_finished_at = ?, updated_at = ? "
                    "WHERE automation_id = ?",
                    (due_at, run_id, reason, stamp, stamp, automation_id),
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

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
    from tinyassets.runtime.assigned_queue_consumer import (
        assigned_queue_consumer_enabled,
    )

    base = Path(base_path)
    uid = str(universe_id or "").strip()
    owner = str(owner_principal_id or "").strip()

    if not assigned_queue_consumer_enabled():
        raise AutomationUnavailable("consumer_disabled")
    if not owner or owner == "anonymous":
        raise AutomationUnavailable("authentication_required")
    if universe_access_permission(base, universe_id=uid, actor_id=owner) != "admin":
        raise AutomationUnavailable("owner_not_admin")
    if get_founder_home(base, owner) != uid:
        raise AutomationUnavailable("not_owner_home")
    assignment = load_provider_assignment(base, universe_id=uid)
    if assignment is None or assignment.state != "ready":
        raise AutomationUnavailable("no_serving_assignment")
    resolved = _resolve_readable_branch(str(branch_def_id or "").strip(), str(base))
    if resolved is None:
        raise AutomationUnavailable("branch_not_readable")
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


def _execute(
    base_path: Path,
    automation: Automation,
    provider_call: Any,
    branch: Any,
    inputs: dict[str, Any],
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
    """
    from dataclasses import replace as _replace

    from tinyassets.runs import RUN_STATUS_FAILED, execute_branch_async, get_run, wait_for

    outcome = execute_branch_async(
        base_path,
        branch=branch,
        inputs=inputs,
        run_name=f"automation:{automation.automation_id[:8]}",
        actor=f"universe:{automation.universe_id}",
        provider_call=provider_call,
        _enqueue_universe_id=automation.universe_id,
    )
    run_id = str(getattr(outcome, "run_id", "") or "")
    if not run_id or outcome.status == RUN_STATUS_FAILED:
        # Admission already refused this run; there is no worker to wait on.
        return outcome
    # No wall-clock cap: a run stops when it is finished or genuinely fails,
    # and the graph owns its own per-node timeouts.
    wait_for(run_id)
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


def run_due_automation(
    base_path: str | Path,
    automation: Automation,
    due_at: str,
    *,
    now: datetime | None = None,
    consumer_id: str = "",
) -> str:
    """Run one due automation and return the reason recorded for it.

    Never raises: the caller is a pump across every universe, and one owner's
    broken automation must not stop another owner's working one.
    """
    # _error_reason is the consumer's bounded, path/secret-stripped formatter.
    # Imported rather than duplicated so both halves of the pump sanitise
    # identically; the function-local import keeps the two modules acyclic.
    from tinyassets.runtime.assigned_queue_consumer import _error_reason

    base = Path(base_path)
    moment = _as_utc(now or datetime.now(timezone.utc))
    store = AutomationStore(base)

    if not store.claim_attempt(automation.automation_id, due_at, now=moment):
        # Another poller, or this daemon before its restart, owns this instant.
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

        branch = _load_branch(base, automation)
        provider_call = _bind_automation_provider_call(base, automation)
        outcome = _execute(
            base, automation, provider_call, branch, dict(automation.inputs)
        )
        from tinyassets.runs import RUN_STATUS_COMPLETED

        run_id = str(getattr(outcome, "run_id", "") or "")
        status = str(getattr(outcome, "status", "") or "unknown")
        reason = (
            f"ok:ran:{run_id}"
            if status == RUN_STATUS_COMPLETED
            else f"run_failed:{status}"
        )
        store.finish_attempt(
            automation.automation_id,
            due_at,
            run_id=run_id,
            status=status,
            reason=reason,
            now=moment,
        )
        _record_refusal(base, automation, reason, moment, consumer_id)
        _append_run_ledger(automation, run_id, due_at)
        return reason
    except Exception as exc:  # noqa: BLE001 - the pump continues; the row says why
        reason = _error_reason("automation_error", exc)
        logger.exception(
            "automation run failed automation=%s due_at=%s",
            automation.automation_id,
            due_at,
        )
        try:
            store.finish_attempt(
                automation.automation_id,
                due_at,
                run_id="",
                status="error",
                reason=reason,
                now=moment,
            )
        except Exception:  # noqa: BLE001 - the refusal below is still owed
            logger.exception(
                "automation attempt close failed automation=%s",
                automation.automation_id,
            )
        _record_refusal(base, automation, reason, moment, consumer_id)
        return reason


__all__ = [
    "MAX_ACTIVE_PER_UNIVERSE",
    "MIN_INTERVAL_SECONDS",
    "REFUSAL_KEY_PREFIX",
    "Automation",
    "AutomationStore",
    "AutomationUnavailable",
    "automations_db_path",
    "due_automations",
    "register_automation",
    "run_due_automation",
]
