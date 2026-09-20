"""Run lifecycle writes serialize against family admission across processes."""

import pytest

from tests.test_graph_run_controls import controls  # noqa: F401
from tests.workspace_family_test_support import (
    managed_runtime,  # noqa: F401
    simulated_managed_runtime,
)
from tinyassets import runs
from tinyassets import workspace_family as family


def _create(base, *, parent=None):
    with simulated_managed_runtime(base):
        rid = runs.create_run(
            base,
            branch_def_id="branch",
            thread_id="",
            inputs={},
            actor="actor",
            owner_user_id="owner",
            queue_universe_id="universe",
            _workspace_parent=parent,
        )
    runs.update_run_status(base, rid, status="running")
    return rid, family.execution_member(base, rid)


def _reason(base, root):
    with runs._connect(base) as conn:
        return conn.execute(
            "SELECT workspace_budget_closing_reason FROM runs WHERE run_id=?", (root,)
        ).fetchone()[0]


def test_normal_parent_completion_retains_child_authority_then_last_child_closes(tmp_path):
    root, root_ctx = _create(tmp_path)
    child, child_ctx = _create(tmp_path, parent=root_ctx)
    runs.update_run_status(tmp_path, root, status="completed", output={"truth": "finished"})
    assert _reason(tmp_path, root) == ""
    assert family.execution_member(tmp_path, child) == child_ctx
    runs.update_run_status(tmp_path, child, status="completed")
    assert _reason(tmp_path, root) == "drained"


@pytest.mark.parametrize(
    "status,reason",
    [("failed", "failed"), ("interrupted", "interrupted"), ("cancelled", "cancelled")],
)
def test_root_failure_closes_and_reaches_active_child(tmp_path, status, reason):
    root, root_ctx = _create(tmp_path)
    child, child_ctx = _create(tmp_path, parent=root_ctx)
    runs.update_run_status(tmp_path, root, status=status)
    assert _reason(tmp_path, root) == reason
    assert runs.is_cancel_requested(tmp_path, child)
    with pytest.raises(family.FamilyRefused, match="closed"):
        _create(tmp_path, parent=child_ctx)


def test_cancel_completed_root_closes_family_without_rewriting_completed_output(tmp_path):
    root, root_ctx = _create(tmp_path)
    child, child_ctx = _create(tmp_path, parent=root_ctx)
    runs.update_run_status(tmp_path, root, status="completed", output={"truth": "finished"})
    assert runs.request_cancel(tmp_path, root)
    assert _reason(tmp_path, root) == "cancelled"
    assert runs.is_cancel_requested(tmp_path, child)
    record = runs.get_run(tmp_path, root)
    assert record["status"] == "completed" and record["output"] == {"truth": "finished"}
    with pytest.raises(family.FamilyRefused, match="closed"):
        _create(tmp_path, parent=child_ctx)


def test_child_only_cancel_preserves_sibling_and_root(tmp_path):
    root, root_ctx = _create(tmp_path)
    child, _ = _create(tmp_path, parent=root_ctx)
    sibling, sibling_ctx = _create(tmp_path, parent=root_ctx)
    assert runs.request_cancel(tmp_path, child)
    assert runs.is_cancel_requested(tmp_path, child)
    assert not runs.is_cancel_requested(tmp_path, sibling)
    assert family.execution_member(tmp_path, sibling) == sibling_ctx
    assert _reason(tmp_path, root) == ""


def test_duplicate_terminal_write_cannot_reopen_closed_root(tmp_path):
    root, _ = _create(tmp_path)
    runs.update_run_status(tmp_path, root, status="completed")
    with pytest.raises(family.FamilyRefused, match="closed"):
        runs.update_run_status(tmp_path, root, status="running")
    assert runs.get_run(tmp_path, root)["status"] == "completed"


def test_old_worker_status_writer_cannot_adopt_resumed_epoch(tmp_path, monkeypatch):
    root, captured = _create(tmp_path)
    writer = runs._family_status_writer(captured)
    runs.update_run_status(tmp_path, root, status="interrupted")
    with family.family_fence(tmp_path, root) as fence, runs._connect(tmp_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        resumed = family.resume_in_transaction(conn, fence, captured, empty=lambda: True)
        conn.execute("UPDATE runs SET status='running' WHERE run_id=?", (root,))
    assert resumed.epoch == 2
    from tinyassets import effectors

    monkeypatch.setattr(
        effectors,
        "active_effect_chain",
        lambda *_: pytest.fail("retired worker touched new effect registry"),
    )
    with pytest.raises(family.FamilyRefused, match="stale"):
        writer(tmp_path, root, status="completed", output={"old": "result"})
    assert runs.get_run(tmp_path, root)["status"] == "running"


def test_served_stop_completed_root_reaches_active_child(controls):  # noqa: F811
    from tests.test_graph_run_controls import content

    served, base, _ = controls
    root = runs.create_run(
        base,
        branch_def_id="branch",
        thread_id="",
        inputs={},
        actor="universe:ours",
        owner_user_id="owner",
        queue_universe_id="ours",
    )
    runs.update_run_status(base, root, status="running")
    parent = family.execution_member(base, root)
    child = runs.create_run(
        base,
        branch_def_id="branch",
        thread_id="",
        inputs={},
        actor="universe:ours",
        owner_user_id="owner",
        queue_universe_id="ours",
        _workspace_parent=parent,
    )
    runs.update_run_status(base, child, status="running")
    runs.update_run_status(base, root, status="completed", output={"kept": "result"})
    result = content(served.run_graph(operation="cancel", run_id=root))
    assert result["status"] == "completed" and result["cancel_requested"] is True
    assert "family" in result["note"].lower()
    assert runs.is_cancel_requested(base, child)
    assert runs.get_run(base, root)["output"] == {"kept": "result"}


def _close_in_other_process(base, root, ready, proceed):
    with family.family_fence(base, root) as fence:
        ready.set()
        assert proceed.wait(15)
        with runs._connect(base) as conn:
            conn.execute("BEGIN IMMEDIATE")
            family.close_in_transaction(conn, fence, 1, "memory_limit")


def test_real_worker_close_wins_against_waiting_child_insertion(tmp_path):
    import multiprocessing
    import time
    from concurrent.futures import ThreadPoolExecutor

    root, parent = _create(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready, proceed = context.Event(), context.Event()
    worker = context.Process(target=_close_in_other_process, args=(tmp_path, root, ready, proceed))
    worker.start()
    try:
        assert ready.wait(15)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(_create, tmp_path, parent=parent)
            time.sleep(0.1)
            assert not pending.done()
            proceed.set()
            with pytest.raises(family.FamilyRefused, match="closed"):
                pending.result(timeout=10)
        worker.join(15)
        assert worker.exitcode == 0
        with runs._connect(tmp_path) as conn:
            assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
        assert _reason(tmp_path, root) == "memory_limit"
    finally:
        proceed.set()
        worker.join(5)
        if worker.is_alive():
            worker.terminate()
            worker.join(5)


def test_process_local_future_absence_is_not_managed_worker_death(tmp_path, monkeypatch):
    root, _ = _create(tmp_path)
    monkeypatch.setenv("TINYASSETS_ORPHANED_RUN_GRACE_SECONDS", "60")
    monkeypatch.setattr(runs, "_has_live_future", lambda *_: False)
    with runs._connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET started_at=1 WHERE run_id=?", (root,))
    assert runs.get_run(tmp_path, root)["status"] == "running"
    assert runs.recover_in_flight_runs(tmp_path) == 0
    assert runs.get_run(tmp_path, root)["status"] == "running"
    assert _reason(tmp_path, root) == ""


def _other_worker_start_and_read(base, root, pipe):
    interrupted = runs.recover_in_flight_runs(base)
    status = runs.get_run(base, root)["status"]
    swept = runs._workspace_sweep_once(base, claimant="independent-worker")
    pipe.send((interrupted, status, swept))


def test_independent_worker_start_and_read_retains_live_family_lease_and_locks(tmp_path):
    import multiprocessing

    from tests.test_workspace_family_pool import _admit
    from tinyassets import workspace_pool as pool

    root, parent = _create(tmp_path)
    with family.family_fence(tmp_path, root) as fence:
        lease = _admit(
            runs.runs_db_path(tmp_path), tmp_path, root, family.FamilyAdmission(fence, parent)
        )
    with runs._connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET started_at=1 WHERE run_id=?", (root,))
    context = multiprocessing.get_context("spawn")
    receiving, sending = context.Pipe(False)
    worker = context.Process(target=_other_worker_start_and_read, args=(tmp_path, root, sending))
    worker.start()
    try:
        assert receiving.poll(15)
        assert receiving.recv() == (0, "running", 0)
        worker.join(15)
        assert worker.exitcode == 0
        assert pool.get_lease(runs.runs_db_path(tmp_path), lease.lease_id).state == "ACTIVE"
        with runs._connect(tmp_path) as conn:
            assert conn.execute(
                "SELECT DISTINCT run_id,budget_epoch FROM workspace_locks"
            ).fetchall()
            assert conn.execute("SELECT count(*) FROM workspace_outbox").fetchone()[0] == 0
    finally:
        worker.join(5)
        if worker.is_alive():
            worker.terminate()
            worker.join(5)
        receiving.close()
        sending.close()
