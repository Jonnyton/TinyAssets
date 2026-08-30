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
#: ``schedule_branch``, ``pause_schedule``, ``unpause_schedule``, and
#: ``unschedule_branch`` all derive EXTENSIONS_COSTLY (tinyassets/auth/provider.py);
#: ``.admin`` is included here too so this fixture keeps covering the
#: fine-grained-admin-scoped path as well, not just costly.
_FOUNDER_CAPS = [
    "tinyassets.universe.costly",
    "tinyassets.extensions.read",
    "tinyassets.extensions.write",
    "tinyassets.extensions.admin",
    "tinyassets.extensions.costly",
]

#: The exact production shape from the 2026-08-30 concern
#: (docs/concerns/2026-08-30-owner-cannot-pause-or-delete-own-schedule-from-app.md):
#: a founder session with the coarse ``costly`` grant ``schedule_branch`` needs,
#: and deliberately no fine-grained ``tinyassets.extensions.admin`` scope --
#: proves pause/unpause/unschedule no longer require the admin tier they used to.
_COSTLY_ONLY_CAPS = [
    "tinyassets.universe.costly",
    "tinyassets.extensions.read",
    "tinyassets.extensions.write",
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
    from tinyassets.api.helpers import _base_path

    authenticate(sub, _FOUNDER_CAPS)
    out = json.loads(universe_api._universe_impl(action="create_universe"))
    assert out.get("error") is None, out
    uid = out["universe_id"]
    # The real op grants the ACL and binds the home; the serving assignment is
    # separate state, and the tick refuses without it.
    set_provider_assignment(_base_path(), universe_id=uid, owner=sub)
    return uid


def set_provider_assignment(
    base: Path, *, universe_id: str, owner: str, state: str = "ready"
) -> None:
    """Write a REAL `provider_assignments` row through the real writer.

    The tick refuses a universe with no serving assignment (D1/D3: authority is
    resolved from what the universe currently has), so a firing test has to give
    it one. Written through `store_provider_assignment_in_transaction` — which
    validates the digest — so a test cannot pass against a row shape production
    would reject.
    """
    from tinyassets.provider_assignment import (
        ProviderAssignment,
        ensure_provider_assignment_schema,
        provider_assignment_digest,
        store_provider_assignment_in_transaction,
    )
    from tinyassets.storage import db_path

    fields = {
        "owner_user_id": owner,
        "universe_id": universe_id,
        "provider": "codex",
        "generation": 1,
        "binding_id": "bnd-sched",
        "credential_reference_id": "cred-sched",
        "credential_reference_generation": 1,
        "credential_reference_digest": "sha256:" + "1" * 64,
    }
    assignment = ProviderAssignment(
        state=state,
        binding_generation=1,
        binding_digest="sha256:" + "2" * 64,
        assignment_digest=provider_assignment_digest(**fields),
        updated_at="2026-08-29T00:00:00+00:00",
        **fields,
    )
    conn = sqlite3.connect(db_path(base))
    try:
        ensure_provider_assignment_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        store_provider_assignment_in_transaction(conn, assignment)
        conn.commit()
    finally:
        conn.close()


def seed_ready_universe(base: Path, *, universe_id: str, principal: str) -> None:
    """Give ``principal`` every fact the tick re-checks for ``universe_id``.

    Admin ACL, founder home, and a ready serving assignment — the three D3 gates
    `_authorization_denial` runs before each fire. Shared with
    ``tests/test_scheduler.py``, whose tick tests are about cron/interval timing
    and would otherwise pass or fail for an authorization reason instead.
    """
    from tinyassets.daemon_server import (
        grant_universe_access,
        initialize_author_server,
        set_founder_home,
    )

    (Path(base) / universe_id).mkdir(parents=True, exist_ok=True)
    initialize_author_server(base)
    grant_universe_access(
        base,
        universe_id=universe_id,
        actor_id=principal,
        permission="admin",
        granted_by=principal,
    )
    set_founder_home(base, founder_sub=principal, universe_id=universe_id)
    set_provider_assignment(base, universe_id=universe_id, owner=principal)


def refusals_for(base: Path, universe_id: str) -> dict[str, str]:
    """Refusal reasons currently recorded for a universe, keyed by ledger id."""
    from tinyassets.storage.assigned_queue_refusals import AssignedQueueRefusalStore

    return AssignedQueueRefusalStore(base).fresh_reasons(
        universe_id=universe_id, max_age_seconds=3600.0
    )


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
    """A row whose actor names a DIFFERENT universe is legacy, not authority.

    The universe on the row is FULLY authorized, so the disagreement between
    ``owner_actor`` and ``universe_id`` is the only thing left that can stop it.
    Without that setup the tick's authority check refuses first and the test
    passes without ever reaching the guard it is named for.
    """
    base, _authenticate = env
    from tinyassets.scheduler import register_schedule

    seed_ready_universe(base, universe_id="u-mine", principal="founder-a")
    register_schedule(
        base,
        branch_def_id="b1",
        owner_actor="universe:u-somewhere-else",
        universe_id="u-mine",
        owner_principal_id="founder-a",
        interval_seconds=600.0,
    )
    calls: list = []
    _capturing_scheduler(base, calls)._fire_due_schedules()
    assert calls == []


def test_a_run_fn_that_cannot_carry_the_principal_does_not_fire(env):
    """Fail loud (Hard Rule 8): dropping the principal silently would refuse later.

    Fully authorized for the same reason as above — the run_fn's shape must be
    the only thing standing between this row and a fire.
    """
    base, _authenticate = env
    from tinyassets.scheduler import Scheduler, register_schedule

    seed_ready_universe(base, universe_id="u-mine", principal="founder-a")
    register_schedule(
        base,
        branch_def_id="b1",
        owner_actor="universe:u-mine",
        universe_id="u-mine",
        owner_principal_id="founder-a",
        interval_seconds=600.0,
    )
    calls: list = []

    def four_arg_run_fn(branch_def_id, actor, inputs, run_name):
        calls.append(actor)

    Scheduler(base, four_arg_run_fn)._fire_due_schedules()
    assert calls == []


def test_the_library_pause_still_gates_on_the_row_owner(env):
    """`pause_schedule`'s own owner check, driven directly.

    The request surface now proves a CURRENT admin grant and calls in with
    ``admin=True``, so the library's owner comparison is no longer reachable
    from there. It remains the contract for every direct caller, and a public
    function whose authorization nothing exercises is one refactor from being
    silently removed.
    """
    base, _authenticate = env
    from tinyassets.scheduler import pause_schedule, register_schedule

    sid = register_schedule(
        base,
        branch_def_id="b1",
        owner_actor="universe:u-mine",
        universe_id="u-mine",
        owner_principal_id="founder-a",
        interval_seconds=600.0,
    )
    with pytest.raises(PermissionError):
        pause_schedule(base, sid, requesting_actor="mallory")
    assert _schedule_rows(base)[0]["paused"] == 0
    assert pause_schedule(base, sid, requesting_actor="founder-a") is True
    assert _schedule_rows(base)[0]["paused"] == 1


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


def test_an_owner_who_lost_admin_can_no_longer_control_the_row(env, live_scheduler):
    """Control is a CURRENT admin grant, not the principal stored at creation.

    Inverted from an earlier version that asserted the opposite. A revoked owner
    who could still pause and delete by id while being unable to LIST is an
    inconsistent authority: the stored principal would outlive the grant it was
    recorded under. They learn why from the refusal the tick records
    (`owner_lost_admin`), not from keeping control.
    """
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]

    from tinyassets.daemon_server import (
        revoke_universe_access,
        universe_access_permission,
    )

    assert revoke_universe_access(base, universe_id=uid, actor_id="founder-a") is True
    assert universe_access_permission(
        base, universe_id=uid, actor_id="founder-a"
    ) != "admin"

    paused = _ext("pause_schedule", schedule_id=sid)
    assert paused["error"] == "owner_not_admin", paused
    removed = _ext("unschedule_branch", schedule_id=sid)
    assert removed["error"] == "owner_not_admin", removed
    row = _schedule_rows(base)[0]
    assert row["paused"] == 0
    assert row["active"] == 1


# ── Tick-time authority: D3 refusals and auto-pause ──────────────────────────


def _fire_once(base: Path, calls: list) -> None:
    _capturing_scheduler(base, calls)._fire_due_schedules()


def _register_owned(base: Path, *, uid: str, principal: str, bid: str = "b1") -> str:
    from tinyassets.scheduler import register_schedule

    return register_schedule(
        base,
        branch_def_id=bid,
        owner_actor=f"universe:{uid}",
        universe_id=uid,
        owner_principal_id=principal,
        interval_seconds=600.0,
    )


def test_an_owner_who_lost_admin_is_refused_at_the_tick(env):
    """D3 — the tick re-checks authority; it does not trust registration."""
    base, _authenticate = env
    uid, principal = "u-lost-admin", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    sid = _register_owned(base, uid=uid, principal=principal)

    from tinyassets.daemon_server import revoke_universe_access

    assert revoke_universe_access(base, universe_id=uid, actor_id=principal) is True

    calls: list = []
    _fire_once(base, calls)

    assert calls == []
    assert refusals_for(base, uid) == {f"schedule:{sid}": "owner_lost_admin"}
    row = _schedule_rows(base)[0]
    assert row["paused"] == 1
    assert row["pause_reason"] == "owner_lost_admin"
    # Nothing ran, so the schedule has not fired.
    assert row["last_fired_at"] is None


def test_a_moved_home_is_refused_at_the_tick(env):
    """Admin without the home is not enough: the run bills the owner's own."""
    base, _authenticate = env
    uid, principal = "u-moved-home", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    sid = _register_owned(base, uid=uid, principal=principal)

    from tinyassets.daemon_server import set_founder_home

    set_founder_home(base, founder_sub=principal, universe_id="u-somewhere-else")

    calls: list = []
    _fire_once(base, calls)

    assert calls == []
    assert refusals_for(base, uid) == {f"schedule:{sid}": "not_owner_home"}
    row = _schedule_rows(base)[0]
    assert row["paused"] == 1 and row["pause_reason"] == "not_owner_home"
    assert row["last_fired_at"] is None


def test_an_assignment_that_is_not_ready_is_refused_at_the_tick(env):
    """Authority is derived from the CURRENT assignment (D1), checked up front."""
    base, _authenticate = env
    uid, principal = "u-unready", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    sid = _register_owned(base, uid=uid, principal=principal)
    set_provider_assignment(base, universe_id=uid, owner=principal, state="pending")

    calls: list = []
    _fire_once(base, calls)

    assert calls == []
    assert refusals_for(base, uid) == {f"schedule:{sid}": "no_serving_assignment"}
    row = _schedule_rows(base)[0]
    assert row["paused"] == 1 and row["pause_reason"] == "no_serving_assignment"
    assert row["last_fired_at"] is None


def test_a_resumed_schedule_clears_the_pause_reason(env, live_scheduler):
    """Resuming answers the refusal; a still-live cause re-pauses on the next tick."""
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]
    set_provider_assignment(base, universe_id=uid, owner="founder-a", state="pending")

    _fire_once(base, [])
    assert _schedule_rows(base)[0]["pause_reason"] == "no_serving_assignment"

    assert _ext("unpause_schedule", schedule_id=sid)["status"] == "unpaused"
    row = _schedule_rows(base)[0]
    assert row["paused"] == 0 and row["pause_reason"] == ""

    _fire_once(base, [])  # cause still live → refused and re-paused, not silent
    assert _schedule_rows(base)[0]["pause_reason"] == "no_serving_assignment"


def test_a_legacy_row_records_a_refusal(env):
    base, _authenticate = env
    from tinyassets.scheduler import register_schedule

    sid = register_schedule(
        base,
        branch_def_id="b1",
        owner_actor="universe:u-legacy",
        interval_seconds=600.0,
    )
    calls: list = []
    _fire_once(base, calls)
    assert calls == []
    assert refusals_for(base, "")[f"schedule:{sid}"] == "legacy_row"


def test_skip_if_running_records_a_refusal(env):
    """A silent skip is invisible to the owner; the ledger row is the record."""
    base, _authenticate = env
    uid, principal = "u-skip", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    from tinyassets.scheduler import register_schedule

    sid = register_schedule(
        base,
        branch_def_id="b1",
        owner_actor=f"universe:{uid}",
        universe_id=uid,
        owner_principal_id=principal,
        interval_seconds=600.0,
        skip_if_running=True,
    )
    conn = sqlite3.connect(base / ".runs.db")
    conn.execute(
        "INSERT INTO runs (run_id, branch_def_id, thread_id, status, actor, started_at) "
        "VALUES ('r1','b1','t1','running','x',0)"
    )
    conn.commit()
    conn.close()

    calls: list = []
    _fire_once(base, calls)
    assert calls == []
    assert refusals_for(base, uid) == {f"schedule:{sid}": "skip_if_running"}


def test_an_incompatible_run_fn_records_a_refusal(env):
    base, _authenticate = env
    uid, principal = "u-oldfn", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    sid = _register_owned(base, uid=uid, principal=principal)

    from tinyassets.scheduler import Scheduler

    calls: list = []

    def four_arg_run_fn(branch_def_id, actor, inputs, run_name):
        calls.append(actor)

    Scheduler(base, four_arg_run_fn)._fire_due_schedules()
    assert calls == []
    assert refusals_for(base, uid) == {f"schedule:{sid}": "run_fn_incompatible"}


def test_an_enqueue_failure_records_a_named_refusal(env):
    base, _authenticate = env
    uid, principal = "u-enqfail", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    sid = _register_owned(base, uid=uid, principal=principal)

    from tinyassets.scheduler import Scheduler

    def exploding_run_fn(branch_def_id, actor, inputs, run_name, *, principal_id=""):
        raise RuntimeError("branch is gone")

    Scheduler(base, exploding_run_fn)._fire_due_schedules()
    assert refusals_for(base, uid) == {f"schedule:{sid}": "enqueue_error:RuntimeError"}
    # The claim STANDS, by design: the attempt happened, and rolling it back
    # would spin the schedule against whatever rejected it on every tick. The
    # refusal names the cause; the next fire waits a full interval.
    assert _schedule_rows(base)[0]["last_fired_at"] is not None


# ── The owner can read why their schedule stopped ────────────────────────────


def test_a_revoked_owner_can_still_read_their_own_schedule(env, live_scheduler):
    """`owner_lost_admin` locks the owner out of the very surface explaining it.

    The refusal is ABOUT them, so the read must not require the grant they just
    lost. Read only — control stays admin-gated
    (`test_an_owner_who_lost_admin_can_no_longer_control_the_row`).
    """
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]

    from tinyassets.daemon_server import revoke_universe_access

    assert revoke_universe_access(base, universe_id=uid, actor_id="founder-a") is True
    _fire_once(base, [])  # first tick after the revoke: denied → paused with a reason

    listed = _ext("list_schedules")
    assert listed["scope"] == "owner", listed
    assert listed["count"] == 1
    row = listed["schedules"][0]
    assert row["schedule_id"] == sid
    assert row["paused"] == 1
    assert row["pause_reason"] == "owner_lost_admin"


def test_a_stranger_still_gets_the_refusal_not_an_empty_list(env, live_scheduler):
    """The owner fallback must not become a way to probe another universe."""
    base, authenticate = env
    uid_a = _create_universe("founder-a", authenticate)
    _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)

    _create_universe("stranger-b", authenticate)
    out = _ext("list_schedules", universe_id=uid_a)
    # They own no schedules, so the fallback finds nothing and the gate's own
    # refusal stands — the fallback never becomes a probe for another universe.
    assert out["error"] == "owner_not_admin", out


def test_an_ongoing_refusal_stays_visible_across_owner_reads(env, live_scheduler):
    """Readers treat a refusal as fresh for ~10s; a 60s rewrite gap hid it.

    Three reads spanning more than the freshness window. With the old fixed
    60-second rewrite guard the ledger row is written once and has aged out by
    the third read, so an ongoing `skip_if_running` looked like nothing was
    wrong for roughly 50 seconds in every 60.
    """
    import datetime as _dt

    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    sid = _ext(
        "schedule_branch", branch_def_id="b1", interval_seconds=600.0, skip_if_running=True
    )["schedule_id"]
    conn = sqlite3.connect(base / ".runs.db")
    conn.execute(
        "INSERT INTO runs (run_id, branch_def_id, thread_id, status, actor, started_at) "
        "VALUES ('r1','b1','t1','running','x',0)"
    )
    conn.commit()
    conn.close()

    from tinyassets.scheduler import refusal_visibility_seconds
    from tinyassets.storage.assigned_queue_refusals import AssignedQueueRefusalStore

    window = refusal_visibility_seconds()
    origin = _dt.datetime(2026, 8, 29, 12, 0, 0, tzinfo=_dt.timezone.utc)
    clock = {"mono": 0.0, "wall": origin}

    class _FrozenDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["wall"]

    import tinyassets.scheduler as sched

    monkey_mono = lambda: clock["mono"]  # noqa: E731
    original_mono, original_dt = sched.time.monotonic, sched.datetime
    sched.time.monotonic = monkey_mono
    sched.datetime = _FrozenDatetime
    store = AssignedQueueRefusalStore(base)
    seen: list[str | None] = []
    # ONE Scheduler across all three ticks: the rewrite guard is per-instance, so
    # a fresh instance per tick would re-record every time and the window under
    # test would never engage.
    ticker = _capturing_scheduler(base, [])
    try:
        # Tick, then read, three times — each pair further apart than half the
        # freshness window, which is when a rewrite is due.
        for offset in (0.0, window * 0.6, window * 1.2):
            clock["mono"] = offset
            clock["wall"] = origin + _dt.timedelta(seconds=offset)
            ticker._fire_due_schedules()
            read_at = clock["wall"] + _dt.timedelta(seconds=window * 0.4)
            fresh = store.fresh_reasons(
                universe_id=uid, max_age_seconds=window, now=read_at
            )
            seen.append(fresh.get(f"schedule:{sid}"))
    finally:
        sched.time.monotonic = original_mono
        sched.datetime = original_dt

    assert seen == ["skip_if_running"] * 3, seen


def test_an_ongoing_refusal_is_visible_at_the_real_tick_cadence(env, live_scheduler):
    """Read the OWNER'S SURFACE every second across a real tick cycle.

    The previous test ticked at 0/6/12 s, which is not what production does: the
    tick sleeps ``TICK_INTERVAL_S`` *after* each pass, so consecutive writes are
    ten seconds plus the work. With a reader window equal to that interval the
    refusal disappeared for the tail of every cycle (Codex round 3, finding b).
    Both clocks are frozen — the writer's inside the scheduler, the reader's
    inside the refusal store — so this is the real code on a simulated timeline,
    not a sleep.
    """
    import datetime as _dt

    import tinyassets.scheduler as sched
    import tinyassets.storage.assigned_queue_refusals as aqr

    base, authenticate = env
    _create_universe("founder-a", authenticate)
    _ext(
        "schedule_branch", branch_def_id="b1", interval_seconds=600.0, skip_if_running=True
    )
    conn = sqlite3.connect(base / ".runs.db")
    conn.execute(
        "INSERT INTO runs (run_id, branch_def_id, thread_id, status, actor, started_at) "
        "VALUES ('r1','b1','t1','running','x',0)"
    )
    conn.commit()
    conn.close()

    origin = _dt.datetime(2026, 8, 29, 12, 0, 0, tzinfo=_dt.timezone.utc)
    clock = {"mono": 0.0, "wall": origin}

    class _FrozenDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["wall"]

    def _advance(seconds: float) -> None:
        clock["mono"] = seconds
        clock["wall"] = origin + _dt.timedelta(seconds=seconds)

    ticker = _capturing_scheduler(base, [])
    originals = (sched.time.monotonic, sched.datetime, aqr.datetime)
    sched.time.monotonic = lambda: clock["mono"]
    sched.datetime = _FrozenDatetime
    aqr.datetime = _FrozenDatetime
    missing: list[float] = []
    try:
        # Production cadence: a pass, then TICK_INTERVAL_S of sleep, then a pass
        # that itself takes a moment.
        tick_times = [0.0, sched.TICK_INTERVAL_S + 2.5]
        for second in range(0, 26):
            for t in tick_times:
                if t <= second < t + 1:
                    _advance(t)
                    ticker._fire_due_schedules()
            _advance(float(second))
            row = _ext("list_schedules")["schedules"][0]
            if row.get("recent_reason") != "skip_if_running":
                missing.append(float(second))
    finally:
        sched.time.monotonic, sched.datetime, aqr.datetime = originals

    assert missing == [], f"recent_reason vanished at t={missing}"


def test_the_list_surfaces_a_recent_refusal_reason(env, live_scheduler):
    """A skip that does not pause leaves no mark on the row — only in the ledger."""
    base, authenticate = env
    _create_universe("founder-a", authenticate)
    _ext(
        "schedule_branch", branch_def_id="b1", interval_seconds=600.0, skip_if_running=True
    )
    conn = sqlite3.connect(base / ".runs.db")
    conn.execute(
        "INSERT INTO runs (run_id, branch_def_id, thread_id, status, actor, started_at) "
        "VALUES ('r1','b1','t1','running','x',0)"
    )
    conn.commit()
    conn.close()
    _fire_once(base, [])

    row = _ext("list_schedules")["schedules"][0]
    assert row["paused"] == 0 and row["pause_reason"] == ""  # nothing on the row
    assert row["recent_reason"] == "skip_if_running"  # the ledger says why


# ── The due-row claim ────────────────────────────────────────────────────────


def test_two_schedulers_over_one_db_fire_exactly_once(env):
    """The singleton is per PROCESS; two daemons share one data root.

    Genuinely concurrent: two threads released by a barrier. The earlier
    sequential form proved nothing — the pre-CAS fire-then-update implementation
    passed it too, because running one tick fully before the other never
    overlaps the read with the write (Codex round 2, finding 3).
    """
    import threading

    base, _authenticate = env
    uid, principal = "u-race", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    _register_owned(base, uid=uid, principal=principal)

    calls: list = []
    lock = threading.Lock()
    barrier = threading.Barrier(3)
    errors: list[BaseException] = []

    def run_fn(branch_def_id, actor, inputs, run_name, *, principal_id=""):
        with lock:
            calls.append(actor)

    def tick() -> None:
        scheduler = Scheduler(base, run_fn)
        try:
            barrier.wait(timeout=10)
            scheduler._fire_due_schedules()
        except BaseException as exc:  # noqa: BLE001 - surfaced as an assertion
            errors.append(exc)

    from tinyassets.scheduler import Scheduler

    threads = [threading.Thread(target=tick) for _ in range(2)]
    for t in threads:
        t.start()
    barrier.wait(timeout=10)
    for t in threads:
        t.join(timeout=30)

    assert errors == [], errors
    assert len(calls) == 1, calls


def test_a_claim_that_loses_the_race_does_not_fire(env):
    """The claim swaps on the WHOLE observation, not only the due time."""
    base, _authenticate = env
    uid, principal = "u-cas", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    sid = _register_owned(base, uid=uid, principal=principal)

    from tinyassets.scheduler import get_schedule

    scheduler = _capturing_scheduler(base, [])
    rev = get_schedule(base, sid)["revision"]
    assert scheduler._claim_due(sid, last_fired=None, now=100.0, revision=rev) is True
    # Same revision replayed: the row moved on, so this ticker must lose.
    assert scheduler._claim_due(sid, last_fired=None, now=200.0, revision=rev) is False
    rev2 = get_schedule(base, sid)["revision"]
    assert rev2 == rev + 1
    assert scheduler._claim_due(sid, last_fired=100.0, now=300.0, revision=rev2) is True


def test_a_stale_authorized_ticker_cannot_fire_a_row_another_ticker_paused(env):
    """deny-then-claim. Codex reproduced: paused with a reason AND a run fired.

    The interleaving point is real: ticker A's authorization check runs while the
    grant still holds and returns "", THEN the grant is revoked and ticker B
    denies and pauses the row, THEN A reaches its claim. Only A's authorization
    call is wrapped — to place the revocation inside A's own race window — and it
    delegates to the real method. The claim under test is untouched.
    """
    base, _authenticate = env
    uid, principal = "u-interleave", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    sid = _register_owned(base, uid=uid, principal=principal)

    from tinyassets.daemon_server import revoke_universe_access
    from tinyassets.scheduler import get_schedule

    calls: list = []
    ticker_a = _capturing_scheduler(base, calls)
    ticker_b = _capturing_scheduler(base, calls)
    real_check = ticker_a._authorization_denial

    def check_then_let_b_deny(row):
        verdict = real_check(row)  # still authorized at this instant
        assert verdict == "", verdict
        revoke_universe_access(base, universe_id=uid, actor_id=principal)
        ticker_b._fire_due_schedules()  # B denies, pauses, bumps the revision
        return verdict

    ticker_a._authorization_denial = check_then_let_b_deny
    ticker_a._fire_due_schedules()

    assert calls == [], "a paused row was fired by a ticker holding a stale read"
    row = get_schedule(base, sid)
    assert row["paused"] == 1
    assert row["pause_reason"] == "owner_lost_admin"
    assert row["last_fired_at"] is None


def test_a_stale_denier_does_not_clobber_an_owner_resume(env):
    """resume-then-stale-pause. Codex reproduced the clobber.

    The row dict is genuinely stale — read before the owner resumed — and the
    tick's pause is a compare-and-swap on it, so the resume stands and no
    refusal is recorded for an authority state that no longer applies.
    """
    base, _authenticate = env
    uid, principal = "u-resume-race", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    sid = _register_owned(base, uid=uid, principal=principal)

    from tinyassets.daemon_server import revoke_universe_access
    from tinyassets.scheduler import get_schedule, unpause_schedule

    revoke_universe_access(base, universe_id=uid, actor_id=principal)
    stale_row = get_schedule(base, sid)  # this ticker's observation

    # The owner resumes in the window between the scan and the write.
    assert unpause_schedule(base, sid, requesting_actor=principal) is True
    resumed = get_schedule(base, sid)
    assert resumed["revision"] == stale_row["revision"] + 1

    calls: list = []
    scheduler = _capturing_scheduler(base, calls)
    scheduler._maybe_fire_schedule(stale_row, time.time(), time.gmtime())

    assert calls == []
    final = get_schedule(base, sid)
    assert final["paused"] == 0, "a stale denier undid the owner's resume"
    assert final["pause_reason"] == ""
    assert refusals_for(base, uid) == {}


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


# ── Tier fix: pause/unpause/unschedule ride costly, not admin ────────────────
#
# 2026-08-30 concern: these three sat in `_EXTENSIONS_ADMIN_ACTIONS`, so a
# founder session with the ordinary coarse `costly` grant `schedule_branch`
# already needs was refused at the OAuth scope gate before the handler's real
# owner-or-admin check (`_schedule_control_context`) ever ran. They now derive
# `tinyassets.extensions.costly`, the same tier as `schedule_branch`. These
# mutation-check tests drive the real scope resolver (`require_action_scope`
# via the real `extensions()` dispatch, through `_ext`) and the real handler —
# no monkeypatched capability set.

_SCHEDULE_CONTROL_ACTIONS = ("pause_schedule", "unpause_schedule", "unschedule_branch")


@pytest.mark.parametrize("action", _SCHEDULE_CONTROL_ACTIONS)
def test_costly_only_owner_can_control_their_own_schedule(
    env, live_scheduler, action,
) -> None:
    """A costly-only founder session must reach and pass the handler's own
    owner check for a row it owns, not be blocked one layer earlier."""
    base, authenticate = env
    _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]

    authenticate("founder-a", _COSTLY_ONLY_CAPS)
    out = _ext(action, schedule_id=sid)
    assert "error" not in out, out


@pytest.mark.parametrize("action", _SCHEDULE_CONTROL_ACTIONS)
def test_costly_only_non_owner_is_refused_by_the_handler_not_the_scope_gate(
    env, live_scheduler, action,
) -> None:
    """A costly-scoped stranger passes the (now coarser) scope gate -- that is
    the fix -- but must still be refused, by the handler's owner-or-admin
    check specifically (`owner_not_admin`), not by some other refusal that
    would mask a hole in the handler if the scope gate were ever removed."""
    base, authenticate = env
    _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]

    _create_universe("mallory", authenticate)  # an unrelated universe/ACL
    authenticate("mallory", _COSTLY_ONLY_CAPS)
    out = _ext(action, schedule_id=sid)
    assert out["error"] == "owner_not_admin", out


@pytest.mark.parametrize("action", _SCHEDULE_CONTROL_ACTIONS)
def test_costly_only_delegated_admin_can_control_a_row_they_do_not_own(
    env, live_scheduler, action,
) -> None:
    """A universe admin who is not the schedule's `owner_principal_id` must
    still be able to act: authority is a CURRENT admin ACL grant on the row's
    own universe, not identity with the row-creating principal."""
    base, authenticate = env
    from tinyassets.daemon_server import grant_universe_access

    uid = _create_universe("founder-a", authenticate)
    sid = _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)[
        "schedule_id"
    ]
    grant_universe_access(
        base, universe_id=uid, actor_id="ops-admin",
        permission="admin", granted_by="founder-a",
    )

    authenticate("ops-admin", _COSTLY_ONLY_CAPS)
    out = _ext(action, schedule_id=sid)
    assert "error" not in out, out


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


def _old_schema_db(tmp_path: Path) -> Path:
    """A ``.runs.db`` with the PRE-2.1 ``branch_schedules`` table and one row."""
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
        "VALUES ('old','b1','alice',600.0,0)"
    )
    conn.commit()
    conn.close()
    return db


def test_initialize_runs_db_migrates_an_existing_schedules_table(tmp_path, monkeypatch):
    """The PRODUCTION path, which is where this broke.

    `SCHEDULER_SCHEMA` creates an index on ``branch_schedules(universe_id)``.
    Run against an install that predates the column, that index raised
    ``OperationalError: no such column: universe_id`` and took the whole of
    `initialize_runs_db` down — so the daemon could not open an existing data
    root at all. The earlier test called `scheduler._connect` directly and
    never touched the failing order.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    db = _old_schema_db(tmp_path)

    from tinyassets.runs import initialize_runs_db

    initialize_runs_db(tmp_path)  # must not raise
    initialize_runs_db(tmp_path)  # idempotent

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(branch_schedules)")}
        assert {"paused", "universe_id", "owner_principal_id", "pause_reason"} <= cols
        indexes = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "idx_schedules_universe" in indexes
        row = dict(
            conn.execute(
                "SELECT * FROM branch_schedules WHERE schedule_id='old'"
            ).fetchone()
        )
    finally:
        conn.close()
    assert row["universe_id"] == "" and row["owner_principal_id"] == ""


def test_four_concurrent_initialize_runs_db_calls_migrate_correctly(tmp_path, monkeypatch):
    """The PRODUCTION entry point raced, not just the migration primitive.

    Codex noted the four-thread test drove `migrate_scheduler_schema` directly.
    What a restarting fleet actually does is call `initialize_runs_db` from
    several processes at once, which runs the migration AND the schema script.

    SCOPE. ``initialize_runs_db`` is not concurrency-safe today and that is
    PRE-EXISTING, not something this change introduced: four concurrent callers
    raise ``database is locked`` on a FRESH database too, where the scheduler
    migration is a no-op (measured 2026-08-29 — 3 of 4 threads fresh, 2 of 4 with
    the migration, so the added `BEGIN IMMEDIATE` if anything helps). Fixing the
    schema script's lock behaviour touches every daemon boot and every test and
    belongs in its own lane. So a lock collision is retried here, exactly as a
    real caller would, and the assertions are about the MIGRATION: no thread may
    see `no such column` or `duplicate column`, and the final schema must be
    right — neither of which a retry could paper over.
    """
    import threading

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _old_schema_db(tmp_path)
    from tinyassets.runs import initialize_runs_db

    schema_errors: list[str] = []
    barrier = threading.Barrier(4)

    def initialize() -> None:
        barrier.wait(timeout=10)
        for _attempt in range(20):
            try:
                initialize_runs_db(tmp_path)
                return
            except sqlite3.OperationalError as exc:
                if "database is locked" in str(exc).lower():
                    time.sleep(0.05)
                    continue
                schema_errors.append(repr(exc))
                return
            except BaseException as exc:  # noqa: BLE001
                schema_errors.append(repr(exc))
                return
        schema_errors.append("gave up retrying a locked database")

    threads = [threading.Thread(target=initialize) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert schema_errors == [], schema_errors

    conn = sqlite3.connect(tmp_path / ".runs.db")
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(branch_schedules)")]
    finally:
        conn.close()
    assert cols.count("universe_id") == 1  # added exactly once, not four times
    assert {"pause_reason", "revision"} <= set(cols)


def test_the_migration_is_safe_when_two_connections_race(tmp_path):
    """Check-then-ALTER is atomic under one BEGIN IMMEDIATE; a loser is idempotent."""
    import threading

    from tinyassets import scheduler as sched

    db = _old_schema_db(tmp_path)
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def migrate() -> None:
        conn = sqlite3.connect(str(db), timeout=30.0)
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            barrier.wait(timeout=10)
            sched.migrate_scheduler_schema(conn)
        except BaseException as exc:  # noqa: BLE001 - the assertion is "none of these"
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=migrate) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == [], errors

    conn = sqlite3.connect(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(branch_schedules)")]
    finally:
        conn.close()
    assert cols.count("universe_id") == 1  # added exactly once, not four times


# ── Cadence floor ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "expr",
    ["* * * * *", "*/2 * * * *", "0,3 * * * *", "0,59 * * * *", "*/4 9-17 * * *"],
)
def test_a_cron_below_the_floor_is_refused(env, live_scheduler, expr):
    """`* * * * *` used to be accepted: the floor only guarded interval_seconds."""
    base, authenticate = env
    _create_universe("founder-a", authenticate)
    out = _ext("schedule_branch", branch_def_id="b1", cron_expr=expr)
    assert out["error"] == "trigger_invalid", (expr, out)
    assert out["reason"] == "cron_below_floor", (expr, out)
    assert _schedule_rows(base) == []


@pytest.mark.parametrize(
    "expr", ["0,5 * * * *", "*/5 * * * *", "0 * * * *", "30 12 * * *", "0,59 12 * * *"]
)
def test_a_cron_at_or_above_the_floor_is_accepted(env, live_scheduler, expr):
    """`0,59 12 * * *` fires twice a day 59 minutes apart — a legitimate cadence.

    The hour-boundary term only counts when two matching hours are adjacent, or
    this would be refused for a wrap that never happens.
    """
    base, authenticate = env
    _create_universe("founder-a", authenticate)
    out = _ext("schedule_branch", branch_def_id="b1", cron_expr=expr)
    assert out["status"] == "scheduled", (expr, out)
    assert len(_schedule_rows(base)) == 1


#: The expression Codex used to break the cadence floor, and the instant that
#: breaks it. US DST begins Sunday 2026-03-08 at 02:00 local, so on a
#: DST-observing host 01:59 EST → 03:00 EDT is sixty elapsed seconds while the
#: minute/hour algebra reads it as 3540.
_DST_CRON = "0,59 1,3 * mar sun"
_DST_TZ = "America/New_York"


def _spring_forward_instants() -> tuple[float, time.struct_time, time.struct_time]:
    """(epoch, its UTC struct, its America/New_York struct) on spring-forward day.

    At 2026-03-08 01:00:00Z the cron matches in UTC — minute 0, hour 1, March,
    Sunday — and does NOT match in New York, where it is still 20:00 on Saturday
    the 7th (EST, UTC-5). One instant, opposite verdicts: exactly the
    discriminator a matcher defined in UTC has to survive.
    """
    import calendar

    epoch = float(
        calendar.timegm(time.strptime("2026-03-08 01:00:00", "%Y-%m-%d %H:%M:%S"))
    )
    return epoch, time.gmtime(epoch), time.gmtime(epoch - 5 * 3600)


def test_a_dst_straddling_cron_is_judged_by_utc_arithmetic(env, live_scheduler):
    """The cadence floor's answer for `0,59 1,3 * mar sun` is exact under UTC."""
    base, authenticate = env
    from tinyassets.scheduler import min_cron_interval_seconds

    _create_universe("founder-a", authenticate)
    assert min_cron_interval_seconds(_DST_CRON) == 3540.0
    out = _ext("schedule_branch", branch_def_id="b1", cron_expr=_DST_CRON)
    assert out["status"] == "scheduled", out
    assert len(_schedule_rows(base)) == 1


def test_the_tick_matches_a_dst_straddling_cron_in_utc(env):
    """Drive the TICK on spring-forward Sunday, not just the arithmetic.

    The registration test above cannot go red if matching reverts to local time,
    because neither the floor nor registration calls the matcher (Codex round 3,
    finding e). This one fires the real `_fire_due_schedules` at an instant whose
    UTC and New-York verdicts disagree.

    ``localtime`` is patched to the zone's struct for that instant rather than
    relying on the host honouring ``TZ`` — Windows has no ``tzset`` — so the
    assertion is deterministic on any machine while still being a genuine
    DST-zone reading.
    """
    import os
    from unittest.mock import patch

    import tinyassets.scheduler as sched

    base, _authenticate = env
    uid, principal = "u-dst", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    from tinyassets.scheduler import register_schedule

    register_schedule(
        base,
        branch_def_id="b1",
        owner_actor=f"universe:{uid}",
        universe_id=uid,
        owner_principal_id=principal,
        cron_expr=_DST_CRON,
    )

    epoch, utc_struct, ny_struct = _spring_forward_instants()
    assert (utc_struct.tm_hour, utc_struct.tm_mday) == (1, 8)  # Sunday 01:00 UTC
    assert (ny_struct.tm_hour, ny_struct.tm_mday) == (20, 7)  # Saturday 20:00 EST

    os.environ["TZ"] = _DST_TZ  # realism; the assertion does not depend on it
    calls: list = []
    try:
        with (
            patch.object(sched.time, "time", return_value=epoch),
            patch.object(sched.time, "localtime", return_value=ny_struct),
        ):
            _capturing_scheduler(base, calls)._fire_due_schedules()
    finally:
        os.environ.pop("TZ", None)

    assert len(calls) == 1, (
        "the tick did not fire on the UTC minute — a local-time matcher reads "
        "this instant as Saturday 20:00 and never matches"
    )


def test_a_cron_fires_on_the_utc_minute_not_the_local_one(env):
    """`0 12 * * *` is 12:00 UTC on every host, whatever the host clock says."""
    from unittest.mock import patch

    base, _authenticate = env
    uid, principal = "u-utc", "founder-a"
    seed_ready_universe(base, universe_id=uid, principal=principal)
    from tinyassets.scheduler import register_schedule

    register_schedule(
        base,
        branch_def_id="b1",
        owner_actor=f"universe:{uid}",
        universe_id=uid,
        owner_principal_id=principal,
        cron_expr="0 12 * * *",
    )

    noon_utc = time.strptime("2026-04-24 12:00:00", "%Y-%m-%d %H:%M:%S")
    seven_local = time.strptime("2026-04-24 07:00:00", "%Y-%m-%d %H:%M:%S")
    calls: list = []
    with patch("tinyassets.scheduler.time") as mock_time:
        mock_time.time.return_value = 1000000.0
        mock_time.gmtime.return_value = noon_utc
        mock_time.localtime.return_value = seven_local  # a UTC-5 host: must not matter
        mock_time.monotonic.return_value = 0.0
        _capturing_scheduler(base, calls)._fire_due_schedules()
    assert len(calls) == 1, calls


# ── Legacy rows stay discoverable and deletable ──────────────────────────────


def test_a_migrated_legacy_row_is_listed_and_deletable(env, live_scheduler):
    """A migrated row has universe_id='' — the column did not exist for it.

    Scoping the list purely on ``universe_id`` hid every row an existing install
    already has from the only people entitled to remove them.
    """
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    from tinyassets.scheduler import register_schedule

    by_universe = register_schedule(
        base, branch_def_id="b-uni", owner_actor=f"universe:{uid}", interval_seconds=600.0
    )
    by_principal = register_schedule(
        base, branch_def_id="b-principal", owner_actor="founder-a", interval_seconds=600.0
    )
    register_schedule(
        base, branch_def_id="b-orphan", owner_actor="someone-else", interval_seconds=600.0
    )

    listed = _ext("list_schedules")
    by_branch = {s["branch_def_id"]: s for s in listed["schedules"]}
    assert set(by_branch) == {"b-uni", "b-principal"}
    assert all(s["legacy"] is True for s in by_branch.values())
    assert all(s["universe_id"] == "" for s in by_branch.values())

    for sid in (by_universe, by_principal):
        removed = _ext("unschedule_branch", schedule_id=sid)
        assert removed["status"] == "unscheduled", removed


def test_a_delegated_admin_can_clear_a_bare_founder_legacy_row(env, live_scheduler):
    """"An admin of X can delete X's legacy rows" has to be true for any admin.

    A migrated row whose `owner_actor` is the ORIGINAL founder's bare principal
    used to be addressable only when that founder was the caller, so a delegated
    admin could not clean it up (Codex round 2, finding 6). The founder is now
    resolved from the registry, not assumed to be whoever is asking.
    """
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    from tinyassets.scheduler import register_schedule

    sid = register_schedule(
        base, branch_def_id="b-founder", owner_actor="founder-a", interval_seconds=600.0
    )

    from tinyassets.daemon_server import grant_universe_access

    grant_universe_access(
        base,
        universe_id=uid,
        actor_id="ops-admin",
        permission="admin",
        granted_by="founder-a",
    )
    from tinyassets.daemon_server import set_founder_home

    set_founder_home(base, founder_sub="ops-admin", universe_id=uid)
    authenticate("ops-admin", _FOUNDER_CAPS)

    listed = _ext("list_schedules")
    assert [s["branch_def_id"] for s in listed["schedules"]] == ["b-founder"], listed
    removed = _ext("unschedule_branch", schedule_id=sid)
    assert removed["status"] == "unscheduled", removed


def test_an_orphaned_legacy_row_is_not_controllable(env, live_scheduler):
    """No universe claims it, so no admin may act on it — inventing one is the
    thing this change exists to stop. `include_orphaned_legacy` is the only way
    to see it, and no caller sets that today."""
    base, authenticate = env
    uid = _create_universe("founder-a", authenticate)
    from tinyassets.scheduler import list_schedules, register_schedule

    sid = register_schedule(
        base, branch_def_id="b-orphan", owner_actor="someone-else", interval_seconds=600.0
    )
    out = _ext("unschedule_branch", schedule_id=sid)
    assert out["error"] == "owner_not_admin", out
    assert _ext("list_schedules")["count"] == 0

    visible = list_schedules(base, universe_id=uid, include_orphaned_legacy=True)
    assert [r["branch_def_id"] for r in visible] == ["b-orphan"]


def test_list_refuses_a_universe_that_is_not_the_callers_home(env, live_scheduler):
    """List takes the same gates as create; it used to check admin but not home."""
    base, authenticate = env
    uid_a = _create_universe("founder-a", authenticate)
    _ext("schedule_branch", branch_def_id="b1", interval_seconds=600.0)

    from tinyassets.daemon_server import grant_universe_access

    _create_universe("stranger-b", authenticate)
    grant_universe_access(
        base,
        universe_id=uid_a,
        actor_id="stranger-b",
        permission="admin",
        granted_by="founder-a",
    )
    out = _ext("list_schedules", universe_id=uid_a)
    assert out["error"] == "not_owner_home", out


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
