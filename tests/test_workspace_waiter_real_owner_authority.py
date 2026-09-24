"""A nominated waiter binds REAL owner authority and runs (live bug, 2026-09-24).

In the founder universe, the second of two runs contending for the workspace
failed before its first node. The failure was ``provider_unavailable``,
"Provider authority admission failed: principal deletion check requires a
transaction". The nomination path read the owner-deletion fence outside the
transaction that the fence requires. ``tests/test_workspace_durable_wait.py``
replaced ``_bind_waiting_run_provider`` with a stub, and that stub is exactly
where the proof leaked.

Nothing on that path is substituted here. The graph is a code node, so it needs
no model, and the real binding (owner-deletion fence, foreground session,
``prepare`` against the run row) runs unmodified. Only the workspace EFFECT is
the lock-taking double shared with the durable-wait suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workspace_durable_wait import (
    OWNER,
    UNIVERSE,
    _holds_lock,
    _status,
    _until,
    _Workspace,
)
from tinyassets import effectors, runs
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)

_PACKET = json.dumps({"op": "create", "storage": "scratch"})


def _code_branch() -> BranchDefinition:
    b = BranchDefinition(name="needs-workspace-code", entry_point="ws")
    # Code runs only in the universe that authored it.
    b.author = f"universe:{UNIVERSE}"
    b.node_defs = [
        NodeDefinition(
            node_id="ws", display_name="WS", input_keys=[], output_keys=["packet"],
            source_code=f"def run(state):\n    return {{'packet': {_PACKET!r}}}\n",
            effects=["workspace"],
        )
    ]
    b.graph_nodes = [GraphNodeRef(id="ws", node_def_id="ws", position=0)]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="ws"),
        EdgeDefinition(from_node="ws", to_node="END"),
    ]
    b.state_schema = [{"name": "packet", "type": "str"}]
    return b


@pytest.fixture
def world(tmp_path, monkeypatch):
    root = tmp_path / "data"
    universe = root / UNIVERSE
    universe.mkdir(parents=True)
    runs.initialize_runs_db(root)
    runs.initialize_runs_db(universe)
    from tinyassets.daemon_server import set_founder_home

    # The owner's real home, as production has it; the session reads it.
    set_founder_home(root, founder_sub=OWNER, universe_id=UNIVERSE, platform_generated=True)
    fake = _Workspace(tmp_path)
    monkeypatch.setitem(effectors._EFFECTORS, "workspace", fake)
    runs._WAITER_DISPATCHED.clear()
    yield root, universe, fake
    for gate in fake.gates.values():
        gate.set()


def _admit(root: Path, name: str, owner: str = OWNER) -> str:
    return runs.execute_branch_async(
        root, branch=_code_branch(), inputs={}, run_name=name,
        actor=f"universe:{UNIVERSE}", owner_user_id=owner,
        provider_call=None, _enqueue_universe_id=UNIVERSE,
    ).run_id


def _delete_principal(root: Path, owner: str) -> None:
    from tinyassets.account_deletion import principal_digest
    from tinyassets.storage import _connect as author_connect

    with author_connect(root) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS deleted_principals ("
            "founder_sub TEXT PRIMARY KEY, deleted_at REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO deleted_principals (founder_sub, deleted_at) VALUES (?, 0)",
            (principal_digest(owner),),
        )


def test_a_nominated_waiter_binds_real_owner_authority_and_completes(world):
    root, universe, fake = world
    holder = _admit(root, "holder")
    fake.hold(holder)
    _until(lambda: _holds_lock(universe, holder), "the holder to take the workspace")
    waiter = _admit(root, "waiter")
    assert runs.get_run(root, waiter)["workspace_wait"]["position"] == 1

    fake.hold(holder).set()
    _until(lambda: _status(root, holder) == "completed", "the holder to complete")
    _until(
        lambda: _status(root, waiter) not in ("queued", "running"),
        "the nominated waiter to finish",
    )
    record = runs.get_run(root, waiter)
    assert record["status"] == "completed", record["error"]
    assert [run for run, _ in fake.calls] == [holder, waiter]


def test_a_refused_nomination_settles_the_waiter_and_the_next_one_runs(world):
    """A waiter whose owner can no longer act must not strand the queue: it is
    settled with the reason, and the run behind it gets its turn."""
    root, universe, fake = world
    holder = _admit(root, "holder")
    fake.hold(holder)
    _until(lambda: _holds_lock(universe, holder), "the holder to take the workspace")
    refused = _admit(root, "refused", owner="owner-deleted")
    behind = _admit(root, "behind")
    assert runs.get_run(root, behind)["workspace_wait"]["position"] == 2
    _delete_principal(root, "owner-deleted")

    fake.hold(holder).set()
    _until(
        lambda: _status(root, behind) not in ("queued", "running"),
        "the run behind the refused waiter to finish",
    )
    refused_record = runs.get_run(root, refused)
    assert refused_record["status"] == "failed"
    assert "Provider authority admission failed" in refused_record["error"]
    assert "requires a transaction" not in refused_record["error"]
    assert "workspace_wait" not in refused_record
    assert runs.get_run(root, behind)["status"] == "completed", runs.get_run(root, behind)
    assert [run for run, _ in fake.calls] == [holder, behind]
