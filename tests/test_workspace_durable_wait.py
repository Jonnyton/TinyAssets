"""Durable workspace waiting (OpenSpec change ``durable-workspace-wait``).

Two runs that need the same universe workspace both complete: the second
waits, visibly and without a worker thread, and starts when the first releases.
The wait keeps its place across a restart, is served in arrival order, can be
cancelled without disturbing the holder, and never replays a started run.

Only the workspace EFFECT is faked, and it takes the REAL universe lock through
``workspace_pool.admit`` with no wait. So the order in which runs acquire the
lock is the order in which the queue let them start. Everything else is the
shipping runner: admission envelope, executor, terminal outbox, sweep and
nomination.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from tinyassets import effectors, runs, workspace_pool
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)

UNIVERSE = "u-0000000000000000000000dw01"
OWNER = "owner-dww"
DEADLINE_S = 30.0


def _branch(name: str = "needs-workspace") -> BranchDefinition:
    b = BranchDefinition(name=name, entry_point="ws")
    b.node_defs = [
        NodeDefinition(
            node_id="ws", display_name="WS", prompt_template="make a packet",
            output_keys=["packet"], effects=["workspace"],
        )
    ]
    b.graph_nodes = [GraphNodeRef(id="ws", node_def_id="ws", position=0)]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="ws"),
        EdgeDefinition(from_node="ws", to_node="END"),
    ]
    b.state_schema = [{"name": "packet", "type": "str"}]
    return b


def _provider(prompt, system="", *, role="writer", fallback_response=None):
    return json.dumps({"op": "create", "storage": "scratch"})


class _Workspace:
    """The workspace effect, reduced to the lock it takes.

    ``hold`` names runs that keep running (holding the lock) until released.
    ``calls`` records every run that reached the effect, in order.
    """

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.calls: list[tuple[str, str]] = []
        self.gates: dict[str, threading.Event] = {}
        self.lock = threading.Lock()

    def hold(self, run_id: str) -> threading.Event:
        return self.gates.setdefault(run_id, threading.Event())

    def __call__(self, **kwargs):
        run_id = kwargs["run_id"]
        base = Path(kwargs["base_path"])
        try:
            workspace_pool.admit(
                runs.runs_db_path(base), universe_id=UNIVERSE, connection_id="",
                repo_key="created", storage_class="scratch", run_id=run_id,
                max_bytes=1, pool_root=self.tmp / "scratch",
                universe_root=self.tmp / "universe-root",
            )
        except workspace_pool.WorkspacePoolRefused as refused:
            with self.lock:
                self.calls.append((run_id, refused.code))
            return {"error": str(refused), "error_kind": refused.code}
        with self.lock:
            self.calls.append((run_id, "admitted"))
        gate = self.gates.get(run_id)
        if gate is not None:
            assert gate.wait(DEADLINE_S), f"{run_id} was never released"
        return {"op": "create", "ok": True}


@pytest.fixture
def world(tmp_path, monkeypatch):
    root = tmp_path / "data"
    universe = root / UNIVERSE
    universe.mkdir(parents=True)
    runs.initialize_runs_db(root)
    runs.initialize_runs_db(universe)
    fake = _Workspace(tmp_path)
    monkeypatch.setitem(effectors._EFFECTORS, "workspace", fake)
    # A waiter's turn binds fresh owner authority; the provider itself is the
    # only thing substituted, never the queue or the dispatch.
    bound: list[str] = []

    def bind(base_path, *, run_id, **_):
        bound.append(run_id)
        return _provider

    # raising=False: the same module runs unchanged against the tree before
    # this change, where it must fail on BEHAVIOUR, not on a missing name.
    monkeypatch.setattr(runs, "_bind_waiting_run_provider", bind, raising=False)
    _forget_dispatch_claims()
    yield root, universe, fake, bound
    for gate in fake.gates.values():
        gate.set()


def _forget_dispatch_claims() -> None:
    """What a new process starts with: no in-memory dispatch claims."""
    getattr(runs, "_WAITER_DISPATCHED", set()).clear()


def _admit(root: Path, name: str = "run") -> str:
    outcome = runs.execute_branch_async(
        root, branch=_branch(), inputs={}, run_name=name,
        actor=f"universe:{UNIVERSE}", owner_user_id=OWNER,
        provider_call=_provider, _enqueue_universe_id=UNIVERSE,
    )
    return outcome.run_id


def _until(predicate, what: str):
    deadline = time.monotonic() + DEADLINE_S
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def _status(root: Path, run_id: str) -> str:
    return runs.get_run(root, run_id)["status"]


def _holds_lock(universe: Path, run_id: str) -> bool:
    with workspace_pool._connect(runs.runs_db_path(universe)) as conn:
        workspace_pool.ensure_schema(conn)
        return conn.execute(
            "SELECT 1 FROM workspace_locks WHERE scope='universe' AND run_id=?", (run_id,),
        ).fetchone() is not None


def _node_ran(root: Path, run_id: str) -> bool:
    return any(
        ev["node_id"] == "ws" and ev["status"] in ("running", "ran")
        for ev in runs.list_events(root, run_id)
    )


def _seed_holder(root: Path, universe: Path, tmp: Path, run_id: str = "holder-a") -> None:
    """A run that already holds the workspace, as a previous process left it."""
    with runs._connect(root) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, branch_def_id, thread_id, status, started_at, "
            "actor, owner_user_id, queue_universe_id) VALUES (?,?,?,?,?,?,?,?)",
            (run_id, "b-holder", run_id, "running", time.time(),
             f"universe:{UNIVERSE}", OWNER, UNIVERSE),
        )
    workspace_pool.admit(
        runs.runs_db_path(universe), universe_id=UNIVERSE, connection_id="",
        repo_key="held", storage_class="scratch", run_id=run_id, max_bytes=1,
        pool_root=tmp / "scratch", universe_root=tmp / "universe-root",
    )


# --------------------------------------------------------------------------
# the acceptance: overlap, order, restart, cancel, no replay
# --------------------------------------------------------------------------


def test_two_overlapping_runs_both_complete_and_the_second_waits_visibly(world):
    root, universe, fake, _ = world
    first = _admit(root, "first")
    fake.hold(first)
    _until(lambda: _holds_lock(universe, first), "the first run to hold the workspace")

    second = _admit(root, "second")
    record = runs.get_run(root, second)
    assert record["status"] == "queued"
    assert record["workspace_wait"]["state"] == "waiting"
    assert record["workspace_wait"]["position"] == 1
    assert not _node_ran(root, second), "a waiting run executes no node"
    assert runs.get_future(second) is None, "a waiting run holds no worker"

    fake.hold(first).set()
    _until(lambda: _status(root, first) == "completed", "the first run to complete")
    _until(lambda: _status(root, second) == "completed", "the second run to complete")
    assert fake.calls == [(first, "admitted"), (second, "admitted")]
    assert "workspace_wait" not in runs.get_run(root, second)


def test_waiters_are_served_in_arrival_order(world):
    root, universe, fake, _ = world
    first = _admit(root, "first")
    fake.hold(first)
    _until(lambda: _holds_lock(universe, first), "the first run to hold the workspace")
    second = _admit(root, "second")
    fake.hold(second)
    third = _admit(root, "third")
    assert runs.get_run(root, third)["workspace_wait"]["position"] == 2

    fake.hold(first).set()
    _until(lambda: _holds_lock(universe, second), "the second run's turn")
    assert _status(root, third) == "queued"
    assert runs.get_run(root, third)["workspace_wait"]["position"] == 1
    fake.hold(second).set()
    _until(lambda: _status(root, third) == "completed", "the third run to complete")
    assert [run for run, _ in fake.calls] == [first, second, third]
    assert all(outcome == "admitted" for _, outcome in fake.calls)


def test_a_free_lock_is_reserved_for_the_first_ticket(tmp_path):
    universe = tmp_path / "u"
    universe.mkdir()
    db = runs.runs_db_path(universe)
    workspace_pool.enqueue_waiter(db, run_id="b", universe_id=UNIVERSE)
    workspace_pool.enqueue_waiter(db, run_id="c", universe_id=UNIVERSE)
    # Idempotent: re-queueing keeps the original place.
    assert workspace_pool.enqueue_waiter(db, run_id="b", universe_id=UNIVERSE).position == 1

    def admit(run_id):
        return workspace_pool.admit(
            db, universe_id=UNIVERSE, connection_id="", repo_key="r",
            storage_class="scratch", run_id=run_id, max_bytes=1,
            pool_root=tmp_path / "scratch", universe_root=tmp_path / "ur",
        )

    with pytest.raises(workspace_pool.WorkspacePoolRefused) as refused:
        admit("c")
    assert refused.value.code == workspace_pool.REFUSED_BUSY
    with pytest.raises(workspace_pool.WorkspacePoolRefused):
        admit("no-ticket")
    admit("b")
    assert workspace_pool.wait_ticket(db, "b") is None, "acquisition consumes the ticket"
    assert workspace_pool.wait_ticket(db, "c").position == 1


def test_a_started_head_does_not_lock_out_the_work_it_launches(tmp_path):
    """Once the head has been handed to a worker nothing queued can start ahead
    of it, so a run it launches (a child using the workspace first) is not
    refused by its own parent's reservation."""
    universe = tmp_path / "u"
    universe.mkdir()
    db = runs.runs_db_path(universe)
    workspace_pool.enqueue_waiter(db, run_id="parent", universe_id=UNIVERSE)
    workspace_pool.enqueue_waiter(db, run_id="later", universe_id=UNIVERSE)
    assert workspace_pool.mark_waiter_dispatched(db, "parent")
    workspace_pool.admit(
        db, universe_id=UNIVERSE, connection_id="", repo_key="r",
        storage_class="scratch", run_id="child-of-parent", max_bytes=1,
        pool_root=tmp_path / "scratch", universe_root=tmp_path / "ur",
    )
    assert workspace_pool.wait_ticket(db, "parent").position == 1
    assert workspace_pool.wait_ticket(db, "later").position == 2


def test_a_restart_keeps_a_waiting_run_queued_and_it_then_completes(world, tmp_path):
    root, universe, fake, bound = world
    _seed_holder(root, universe, tmp_path)
    waiter = _admit(root, "waiter")
    assert runs.get_run(root, waiter)["workspace_wait"]["position"] == 1

    # The new process: nothing claimed, the holder's worker is gone.
    _forget_dispatch_claims()
    runs.recover_in_flight_runs(root)

    assert _status(root, "holder-a") == "interrupted"
    _until(lambda: _status(root, waiter) == "completed", "the waiter to start and complete")
    assert fake.calls == [(waiter, "admitted")]
    assert bound == [waiter], "its turn bound fresh owner authority exactly once"


def test_read_time_orphan_recovery_leaves_a_waiter_alone(world, tmp_path, monkeypatch):
    root, universe, _, _ = world
    _seed_holder(root, universe, tmp_path)
    waiter = _admit(root, "waiter")
    monkeypatch.setenv("TINYASSETS_ORPHANED_RUN_GRACE_SECONDS", "60")
    with runs._connect(root) as conn:
        conn.execute("UPDATE runs SET started_at=? WHERE run_id=?", (time.time() - 7200, waiter))
        conn.execute("DELETE FROM run_events WHERE run_id=?", (waiter,))
    runs._recover_orphaned_runs_on_read(root)
    record = runs.get_run(root, waiter)
    assert record["status"] == "queued"
    assert record["workspace_wait"]["position"] == 1


def test_cancelling_a_waiting_run_settles_it_and_leaves_the_holder_alone(world, tmp_path):
    root, universe, fake, _ = world
    _seed_holder(root, universe, tmp_path)
    waiter = _admit(root, "waiter")
    assert runs.request_cancel(root, waiter) is True

    record = runs.get_run(root, waiter)
    assert record["status"] == "cancelled"
    assert "workspace_wait" not in record
    assert workspace_pool.wait_ticket(runs.runs_db_path(universe), waiter) is None
    assert _holds_lock(universe, "holder-a"), "the holder keeps its lock"
    assert _status(root, "holder-a") == "running"
    assert fake.calls == []
    assert not _node_ran(root, waiter)


def test_a_started_run_is_interrupted_on_restart_and_never_replayed(world, tmp_path, monkeypatch):
    """A run that reached ``running`` may have produced effects; restart must
    settle it exactly as before, drop its reservation and never dispatch it."""
    root, universe, fake, _ = world
    started = "started-b"
    with runs._connect(root) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, branch_def_id, thread_id, status, started_at, "
            "actor, owner_user_id, queue_universe_id) VALUES (?,?,?,?,?,?,?,?)",
            (started, "b1", started, "running", time.time(),
             f"universe:{UNIVERSE}", OWNER, UNIVERSE),
        )
    # Started while first in line and before its checkout: still holds a ticket.
    workspace_pool.enqueue_waiter(
        runs.runs_db_path(universe), run_id=started, universe_id=UNIVERSE,
    )
    dispatched: list[str] = []
    monkeypatch.setattr(runs, "_dispatch_waiting_run", lambda _b, rid: dispatched.append(rid))

    _forget_dispatch_claims()
    runs.recover_in_flight_runs(root)
    _until(
        lambda: workspace_pool.wait_ticket(runs.runs_db_path(universe), started) is None,
        "the started run's ticket to be removed",
    )
    assert _status(root, started) == "interrupted"
    assert runs.nominate_workspace_waiter(universe) is None
    assert dispatched == []
    assert fake.calls == []


def test_a_dead_head_does_not_wedge_the_queue(world):
    root, universe, _, _ = world
    db = runs.runs_db_path(universe)
    workspace_pool.enqueue_waiter(db, run_id="vanished", universe_id=UNIVERSE)
    waiter = _admit(root, "waiter")
    assert runs.get_run(root, waiter)["workspace_wait"]["position"] == 2
    runs.nominate_workspace_waiter(universe)
    _until(lambda: _status(root, waiter) == "completed", "the live waiter to run")
    assert workspace_pool.wait_ticket(db, "vanished") is None


def test_children_and_universe_less_runs_are_not_queued():
    b = _branch()
    assert runs._queues_for_workspace(
        b, owner_user_id=OWNER, universe_id=UNIVERSE, invocation_depth=0,
        workspace_parent=None,
    )
    assert not runs._queues_for_workspace(
        b, owner_user_id=OWNER, universe_id=UNIVERSE, invocation_depth=1,
        workspace_parent=None,
    )
    assert not runs._queues_for_workspace(
        b, owner_user_id=OWNER, universe_id="", invocation_depth=0, workspace_parent=None,
    )
    plain = _branch()
    plain.node_defs[0].effects = []
    assert not runs._queues_for_workspace(
        plain, owner_user_id=OWNER, universe_id=UNIVERSE, invocation_depth=0,
        workspace_parent=None,
    )
