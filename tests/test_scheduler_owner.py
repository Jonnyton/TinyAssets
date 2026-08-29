"""Schedules belong to a person — user-owned-automations tasks 2.1 + 2.2.

Every schedule that ever came due was refused. Three separate holes produced
that, and this module pins each one shut:

  * the tick loop fired as ``scheduler:<schedule_id>``, an actor the run function
    rejects, so no scheduled run ever started;
  * registration read ``owner_actor`` out of the caller's own kwargs and defaulted
    it to ``"anonymous"`` — unauthenticated, un-ACL'd, self-issued authority;
  * a background run reached the provider session with no principal, because the
    tick thread has no request identity, so the founder-home check refused it.

These use the REAL surfaces: real authenticated principals via
``authenticate_request``, a real universe created through the real op (which is
what grants the admin ACL and binds the founder home), the real ``extensions()``
MCP dispatch, and a REAL running scheduler singleton where liveness matters —
not a monkeypatched ``is_running``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

import pytest

# ── Real fixtures ────────────────────────────────────────────────────────────

#: OAuth scopes a founder needs to create a universe and drive the schedule ops.
#: ``schedule_branch`` derives EXTENSIONS_WRITE; pause/unpause/unschedule derive
#: EXTENSIONS_ADMIN (tinyassets/auth/provider.py).
_FOUNDER_CAPS = [
    "tinyassets.universe.costly",
    "tinyassets.extensions.read",
    "tinyassets.extensions.write",
    "tinyassets.extensions.admin",
    "tinyassets.extensions.costly",
]


@pytest.fixture
def env(tmp_path: Path, monkeypatch, authenticate_request):
    """A real data dir with the author server + runs DB up, and the inbound flag OFF.

    The flag stays unset deliberately: after 2.2 the scheduler lifecycle is
    independent of it, so every test here runs in the configuration that used to
    mean "schedules silently never tick".
    """
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.delenv("TINYASSETS_INBOUND_ENABLED", raising=False)
    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.runs import initialize_runs_db
    from tinyassets.scheduler import shutdown_scheduler

    initialize_author_server(base)
    initialize_runs_db(base)  # scheduler tables, as the daemon does at boot
    shutdown_scheduler()  # no singleton leaked in from another module
    try:
        yield base, authenticate_request
    finally:
        shutdown_scheduler()


@pytest.fixture
def live_scheduler(env):
    """A genuinely running scheduler singleton, so ``is_running()`` is really True.

    Its base path is an ISOLATED directory, not the data dir under test: the tick
    loop must be alive (that is the thing registration checks) without racing the
    assertions about which schedules have fired.
    """
    base, _authenticate = env
    from tinyassets.runs import initialize_runs_db
    from tinyassets.scheduler import get_or_create_scheduler, shutdown_scheduler

    ticker = base.parent / "ticker"
    ticker.mkdir()
    initialize_runs_db(ticker)

    def _idle_run_fn(branch_def_id, actor, inputs, run_name, *, principal_id=""):
        raise AssertionError("the isolated ticker must have nothing to fire")

    shutdown_scheduler()
    scheduler = get_or_create_scheduler(ticker, _idle_run_fn)
    try:
        yield scheduler
    finally:
        shutdown_scheduler()


def _create_universe(sub: str, authenticate) -> str:
    """Authenticate as ``sub`` and create a REAL universe they own.

    The real op is what grants the admin ACL and binds the founder home — the two
    facts registration checks — so the test never asserts against a hand-built
    permission row that production would not produce.
    """
    from tinyassets.api import universe as universe_api

    authenticate(sub, _FOUNDER_CAPS)
    out = json.loads(universe_api._universe_impl(action="create_universe"))
    assert out.get("error") is None, out
    return out["universe_id"]


def _seed_branch(base: Path, *, bid: str, author: str) -> None:
    """Persist a REAL, structurally-valid, runnable branch authored by ``author``."""
    from tinyassets.daemon_server import save_branch_definition

    src = "def run(state):\n    return {'out': 'ok'}\n"
    save_branch_definition(base, branch_def={
        "branch_def_id": bid,
        "name": bid,
        "author": author,
        "domain_id": "workflow",
        "visibility": "public",
        "node_defs": [{
            "node_id": "only",
            "display_name": "Only",
            "phase": "custom",
            "input_keys": [],
            "output_keys": ["out"],
            "source_code": src,
            "approved": True,
            "approved_source_hash": hashlib.sha256(src.encode()).hexdigest(),
            "tools_allowed": [],
        }],
        "graph_nodes": [{"id": "only", "node_def_id": "only", "position": 0}],
        "edges": [
            {"from_node": "START", "to_node": "only"},
            {"from_node": "only", "to_node": "END"},
        ],
        "conditional_edges": [],
        "state_schema": [{"name": "out", "type": "str"}],
        "entry_point": "only",
    })


def _schedule_rows(base: Path) -> list[dict]:
    """Every ``branch_schedules`` row, read straight from the DB."""
    conn = sqlite3.connect(base / ".runs.db")
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM branch_schedules")]
    finally:
        conn.close()


def _ext(action: str, **kwargs) -> dict:
    """Drive the REAL MCP surface (``extensions()``), not the handler underneath."""
    from tinyassets.universe_server import extensions

    return json.loads(extensions(action=action, **kwargs))


def _capturing_scheduler(base: Path, calls: list):
    from tinyassets.scheduler import Scheduler

    def run_fn(branch_def_id, actor, inputs, run_name, *, principal_id=""):
        calls.append({
            "branch_def_id": branch_def_id,
            "actor": actor,
            "inputs": inputs,
            "run_name": run_name,
            "principal_id": principal_id,
        })

    return Scheduler(base, run_fn)


# ── Registration derives the owner; it never accepts one ─────────────────────


def test_anonymous_registration_is_refused_and_stores_nothing(env, live_scheduler):
    """The old surface accepted this and stored owner_actor='anonymous'."""
    base, authenticate = env
    authenticate(None)  # no request subject at all
    out = _ext(
        "schedule_branch",
        branch_def_id="b1",
        interval_seconds=600.0,
        owner_actor="alice",  # a self-issued claim; it must not be believed
    )
    assert "error" in out, out
    assert _schedule_rows(base) == []


def test_the_handler_itself_refuses_an_unauthenticated_request(env, live_scheduler):
    """Defence in depth: the handler does not lean on the tool's auth wrapper.

    ``extensions()`` refuses anonymous callers at the door, so the wrapper alone
    would make the handler's own gate untested — and the handler is what a future
    caller (an internal op, a new surface) would reach directly.
    """
    base, authenticate = env
    from tinyassets.api.runtime_ops import _action_schedule_branch

    authenticate(None)
    out = json.loads(
        _action_schedule_branch({"branch_def_id": "b1", "interval_seconds": 600.0})
    )
    assert out["error"] == "authentication_required", out
    assert _schedule_rows(base) == []


def test_a_caller_supplied_owner_actor_is_ignored(env, live_scheduler):
    """Registration derives the owner. The kwarg is not an authority claim."""
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    out = _ext(
        "schedule_branch",
        branch_def_id="b1",
        interval_seconds=600.0,
        owner_actor="somebody-else",
    )
    assert out["status"] == "scheduled", out
    row = _schedule_rows(base)[0]
    assert row["owner_actor"] == f"universe:{uid}"
    assert row["owner_principal_id"] == "founder-a"
    assert row["universe_id"] == uid


def test_registration_without_admin_on_the_universe_is_refused(env, live_scheduler):
    """An authenticated stranger naming someone else's universe is refused."""
    base, authenticate = env
    uid_a = _create_universe("founder-a", authenticate)
    _create_universe("stranger-b", authenticate)  # b is now the live identity
    out = _ext(
        "schedule_branch", branch_def_id="b1", interval_seconds=600.0, universe_id=uid_a
    )
    assert out["error"] == "owner_not_admin", out
    assert _schedule_rows(base) == []


def test_registration_outside_the_owners_home_is_refused(env, live_scheduler):
    """Admin ACL is not enough: a scheduled run bills the owner's OWN universe."""
    base, authenticate = env
    uid_a = _create_universe("founder-a", authenticate)
    uid_second = _create_universe("founder-a", authenticate)
    assert uid_second != uid_a  # the second create does NOT move their home
    out = _ext(
        "schedule_branch",
        branch_def_id="b1",
        interval_seconds=600.0,
        universe_id=uid_second,
    )
    assert out["error"] == "not_owner_home", out
    assert _schedule_rows(base) == []


def test_scheduler_unavailable_refuses_and_stores_nothing(env):
    """D4 — a row that cannot fire is refused, never stored silently."""
    base, authenticate = env
    from tinyassets.scheduler import is_running, shutdown_scheduler

    _create_universe("founder-a", authenticate)
    shutdown_scheduler()
    assert is_running() is False
    out = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)
    assert out["error"] == "scheduler_unavailable", out
    assert out["reason"] == "scheduler_not_running"
    assert _schedule_rows(base) == []


def test_a_cadence_below_the_floor_is_refused(env, live_scheduler):
    """A one-second cadence drains the owner's own subscription."""
    base, authenticate = env
    from tinyassets.scheduler import MIN_SCHEDULE_INTERVAL_S

    _create_universe("founder-a", authenticate)
    out = _ext("schedule_branch", branch_def_id="b1", interval_seconds=1.0)
    assert out["error"] == "trigger_invalid", out
    assert out["reason"] == "interval_below_floor"
    assert out["minimum_interval_seconds"] == MIN_SCHEDULE_INTERVAL_S
    assert _schedule_rows(base) == []


# ── Firing carries the universe actor and the owner principal ────────────────


def test_a_due_schedule_fires_as_the_universe_with_its_owner_principal(
    env, live_scheduler
):
    """The defect: the actor was ``scheduler:<id>``, which the run fn refuses."""
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    created = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)
    assert created["status"] == "scheduled", created

    calls: list = []
    _capturing_scheduler(base, calls)._fire_due_schedules()

    assert len(calls) == 1, calls
    assert calls[0]["actor"] == f"universe:{uid}"
    assert calls[0]["principal_id"] == "founder-a"
    assert calls[0]["branch_def_id"] == "b1"
    assert not calls[0]["actor"].startswith("scheduler:")


def test_the_fired_actor_is_accepted_by_the_real_run_function(env, live_scheduler):
    """End-to-end shape check: the actor the tick emits is one the run fn admits.

    ``_inbound_event_run_fn`` refuses any non-``universe:`` actor before it does
    anything else, which is exactly why every scheduled run was dropped. Drive the
    REAL function and assert it got past that gate into the enqueue.
    """
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)

    from tinyassets.api import runs as runs_mod
    from tinyassets.universe_server import _inbound_event_run_fn

    seen: dict = {}

    def _capture(base_path, **kwargs):
        seen.update(kwargs)
        return "run-x"

    from tinyassets.scheduler import Scheduler

    original = runs_mod.enqueue_universe_branch_run
    runs_mod.enqueue_universe_branch_run = _capture
    try:
        Scheduler(base, _inbound_event_run_fn)._fire_due_schedules()
    finally:
        runs_mod.enqueue_universe_branch_run = original

    assert seen.get("universe_id") == uid, seen
    assert seen.get("principal_id") == "founder-a", seen


def test_a_legacy_row_never_fires(env):
    """A row with no universe and no principal has no owner to run as."""
    base, _authenticate = env
    from tinyassets.scheduler import register_schedule

    register_schedule(
        base, branch_def_id="b1", owner_actor="alice", interval_seconds=1.0
    )
    calls: list = []
    _capturing_scheduler(base, calls)._fire_due_schedules()
    assert calls == []


def test_an_actor_that_disagrees_with_the_universe_never_fires(env):
    """A row whose actor names a DIFFERENT universe is legacy, not authority."""
    base, _authenticate = env
    from tinyassets.scheduler import register_schedule

    register_schedule(
        base,
        branch_def_id="b1",
        owner_actor="universe:u-somewhere-else",
        universe_id="u-mine",
        owner_principal_id="founder-a",
        interval_seconds=1.0,
    )
    calls: list = []
    _capturing_scheduler(base, calls)._fire_due_schedules()
    assert calls == []


def test_a_run_fn_that_cannot_carry_the_principal_does_not_fire(env):
    """Fail loud (Hard Rule 8): dropping the principal silently would refuse later."""
    base, _authenticate = env
    from tinyassets.scheduler import Scheduler, register_schedule

    register_schedule(
        base,
        branch_def_id="b1",
        owner_actor="universe:u-mine",
        universe_id="u-mine",
        owner_principal_id="founder-a",
        interval_seconds=1.0,
    )
    calls: list = []

    def four_arg_run_fn(branch_def_id, actor, inputs, run_name):
        calls.append(actor)

    Scheduler(base, four_arg_run_fn)._fire_due_schedules()
    assert calls == []


# ── The principal reaches the provider session ───────────────────────────────


def test_enqueue_binds_the_session_with_the_given_principal(env):
    """A background run has no request identity; the principal must be passed.

    The request identity is cleared before the call, exactly as it is on the
    scheduler's tick thread. If the binding still read
    ``current_request_actor_id()`` the session would be built for ``anonymous``
    and ``_validate_founder_home`` would refuse — which is why every scheduled
    run failed even once its actor was right.
    """
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    _seed_branch(base, bid="b", author="founder-a")

    import tinyassets.foreground_run_provider as fgp
    from tinyassets.api.permissions import current_request_actor_id
    from tinyassets.api.runs import enqueue_universe_branch_run

    captured: list[dict] = []
    original = fgp.new_foreground_run_provider_session

    def _spy(base_path, **kwargs):
        captured.append(dict(kwargs))
        return original(base_path, **kwargs)

    authenticate(None)  # no request context — a background thread has none
    assert current_request_actor_id() == "anonymous"

    fgp.new_foreground_run_provider_session = _spy
    try:
        run_id = enqueue_universe_branch_run(
            base,
            universe_id=uid,
            branch_def_id="b",
            inputs={},
            run_name="sched",
            principal_id="founder-a",
        )
    finally:
        fgp.new_foreground_run_provider_session = original

    assert captured, "the run never reached the provider session"
    assert captured[0]["principal_id"] == "founder-a"
    assert captured[0]["universe_id"] == uid
    _drain_run(base, run_id)


def test_enqueue_without_a_principal_keeps_the_request_identity(env):
    """The webhook path is unchanged: no principal means the request's own."""
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    _seed_branch(base, bid="b", author="founder-a")

    import tinyassets.foreground_run_provider as fgp
    from tinyassets.api.runs import enqueue_universe_branch_run

    captured: list[dict] = []
    original = fgp.new_foreground_run_provider_session

    def _spy(base_path, **kwargs):
        captured.append(dict(kwargs))
        return original(base_path, **kwargs)

    fgp.new_foreground_run_provider_session = _spy
    try:
        run_id = enqueue_universe_branch_run(
            base, universe_id=uid, branch_def_id="b", inputs={}, run_name="webhook"
        )
    finally:
        fgp.new_foreground_run_provider_session = original

    assert captured[0]["principal_id"] == "founder-a"  # the live request subject
    _drain_run(base, run_id)


def _drain_run(base: Path, run_id: str, timeout: float = 5.0) -> None:
    """Let a real background run reach a terminal state so it cannot leak."""
    from tinyassets.runs import get_run

    terminal = {"completed", "failed", "cancelled", "interrupted"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        if (get_run(base, run_id) or {}).get("status") in terminal:
            return
        time.sleep(0.02)


# ── Owner controls ───────────────────────────────────────────────────────────


def test_a_non_owner_cannot_pause_or_delete_someone_elses_schedule(env, live_scheduler):
    base, authenticate = env
    _create_universe("founder-a", authenticate)
    created = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)
    sid = created["schedule_id"]

    _create_universe("stranger-b", authenticate)  # b is now the live identity
    paused = _ext("pause_schedule", schedule_id=sid)
    assert "error" in paused, paused
    removed = _ext("unschedule_branch", schedule_id=sid)
    assert "error" in removed, removed

    row = _schedule_rows(base)[0]
    assert row["paused"] == 0
    assert row["active"] == 1


def test_the_owner_can_pause_resume_and_delete_their_own_schedule(env, live_scheduler):
    base, authenticate = env
    _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]

    assert _ext("pause_schedule", schedule_id=sid)["status"] == "paused"
    assert _schedule_rows(base)[0]["paused"] == 1
    assert _ext("unpause_schedule", schedule_id=sid)["status"] == "unpaused"
    assert _schedule_rows(base)[0]["paused"] == 0
    assert _ext("unschedule_branch", schedule_id=sid)["status"] == "unscheduled"
    assert _schedule_rows(base)[0]["active"] == 0


def test_the_owner_can_still_pause_after_losing_admin(env, live_scheduler):
    """Two independent grounds to control a row: the principal, or admin.

    Without this case the owner path is never exercised on its own — a founder
    acting on their own home is ALSO an admin there, so the admin branch would
    carry every "owner succeeds" assertion and a broken actor derivation would
    pass unnoticed.
    """
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]

    from tinyassets.daemon_server import revoke_universe_access, universe_access_permission

    assert revoke_universe_access(base, universe_id=uid, actor_id="founder-a") is True
    assert universe_access_permission(
        base, universe_id=uid, actor_id="founder-a"
    ) != "admin"

    assert _ext("pause_schedule", schedule_id=sid)["status"] == "paused"
    assert _schedule_rows(base)[0]["paused"] == 1
    assert _ext("unschedule_branch", schedule_id=sid)["status"] == "unscheduled"
    assert _schedule_rows(base)[0]["active"] == 0


def test_an_admin_on_the_rows_universe_can_pause_it(env, live_scheduler):
    """Admin is checked against the ROW's universe, not the request's scope."""
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]

    from tinyassets.daemon_server import grant_universe_access

    grant_universe_access(
        base,
        universe_id=uid,
        actor_id="ops-admin",
        permission="admin",
        granted_by="founder-a",
    )
    authenticate("ops-admin", _FOUNDER_CAPS)
    assert _ext("pause_schedule", schedule_id=sid)["status"] == "paused"
    assert _schedule_rows(base)[0]["paused"] == 1


def test_anonymous_cannot_pause(env, live_scheduler):
    base, authenticate = env
    _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]
    authenticate(None)
    out = _ext("pause_schedule", schedule_id=sid)
    assert "error" in out, out
    assert _schedule_rows(base)[0]["paused"] == 0


def test_list_is_scoped_to_the_requesting_universe(env, live_scheduler):
    base, authenticate = env
    uid_a = _create_universe("founder-a", authenticate)
    _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)

    uid_b = _create_universe("founder-b", authenticate)
    _ext("schedule_branch", branch_def_id="b2", interval_seconds=600.0)

    listed = _ext("list_schedules")
    assert listed["universe_id"] == uid_b
    assert listed["count"] == 1
    assert listed["schedules"][0]["branch_def_id"] == "b2"

    authenticate("founder-a", _FOUNDER_CAPS)
    listed_a = _ext("list_schedules")
    assert listed_a["universe_id"] == uid_a
    assert [s["branch_def_id"] for s in listed_a["schedules"]] == ["b1"]


def test_list_reports_paused_legacy_and_last_fired(env, live_scheduler):
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]
    _ext("pause_schedule", schedule_id=sid)

    from tinyassets.scheduler import register_schedule

    register_schedule(
        base,
        branch_def_id="b-legacy",
        owner_actor="alice",
        universe_id=uid,  # visible in this universe, but with no principal
        interval_seconds=600.0,
    )

    listed = _ext("list_schedules")
    by_branch = {s["branch_def_id"]: s for s in listed["schedules"]}
    assert by_branch["b1"]["paused"] == 1
    assert by_branch["b1"]["legacy"] is False
    assert by_branch["b1"]["last_fired_at"] is None
    assert by_branch["b-legacy"]["legacy"] is True


# ── Lifecycle (2.2) ──────────────────────────────────────────────────────────


def test_the_scheduler_starts_with_the_inbound_flag_off(env):
    """2.2 — schedule ticks are not part of the inbound channel surface."""
    from tinyassets.scheduler import is_running, shutdown_scheduler
    from tinyassets.universe_server import (
        start_scheduler_for_serving,
        stop_scheduler_for_serving,
    )
    from tinyassets.webhook_inbound import inbound_enabled

    assert inbound_enabled() is False  # the configuration under test
    shutdown_scheduler()
    assert is_running() is False

    assert start_scheduler_for_serving() is True
    try:
        assert is_running() is True
    finally:
        stop_scheduler_for_serving()
    assert is_running() is False


def test_is_running_is_false_for_a_scheduler_that_was_never_started(env):
    """Liveness, not the mere presence of a singleton object."""
    import tinyassets.scheduler as sched

    sched.shutdown_scheduler()
    base, _authenticate = env
    never_started = sched.Scheduler(base, lambda *a, **k: None)
    original = sched._SINGLETON
    sched._SINGLETON = never_started
    try:
        assert sched.is_running() is False
    finally:
        sched._SINGLETON = original


# ── Schema migration ─────────────────────────────────────────────────────────


def test_the_new_columns_are_added_to_a_pre_existing_db(tmp_path):
    """An existing install gains the columns without a rebuild, idempotently."""
    from tinyassets import scheduler as sched

    db = tmp_path / ".runs.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE branch_schedules (
            schedule_id          TEXT PRIMARY KEY,
            branch_def_id        TEXT NOT NULL,
            owner_actor          TEXT NOT NULL,
            cron_expr            TEXT NOT NULL DEFAULT '',
            interval_seconds     REAL NOT NULL DEFAULT 0,
            inputs_template_json TEXT NOT NULL DEFAULT '{}',
            skip_if_running      INTEGER NOT NULL DEFAULT 0,
            active               INTEGER NOT NULL DEFAULT 1,
            created_at           REAL NOT NULL,
            last_fired_at        REAL
        );
        """
    )
    conn.execute(
        "INSERT INTO branch_schedules "
        "(schedule_id, branch_def_id, owner_actor, interval_seconds, created_at) "
        "VALUES ('old','b1','alice',60.0,0)"
    )
    conn.commit()
    conn.close()

    for _ in range(2):  # idempotent — a second connect must not raise
        migrated = sched._connect(db)
        try:
            cols = {r[1] for r in migrated.execute("PRAGMA table_info(branch_schedules)")}
            assert {"paused", "universe_id", "owner_principal_id"} <= cols
            row = dict(
                migrated.execute(
                    "SELECT * FROM branch_schedules WHERE schedule_id='old'"
                ).fetchone()
            )
        finally:
            migrated.close()
    assert row["universe_id"] == ""
    assert row["owner_principal_id"] == ""
    assert sched.schedule_is_legacy(row) is True
