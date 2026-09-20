"""Ordinary recovery is independent of future managed-memory activation."""

import pytest

from tinyassets import runs
from tinyassets import workspace_family as family
from tinyassets.storage.run_execution_lock import try_run_execution_lock


@pytest.mark.parametrize("status", ["queued", "running"])
def test_unactivated_authenticated_run_retains_ordinary_restart_recovery(tmp_path, status):
    run_id = runs.create_run(
        tmp_path, branch_def_id="fixture", thread_id="fixture", inputs={},
        actor="owner", owner_user_id="owner", queue_universe_id="universe",
    )
    if status == "running":
        runs.update_run_status(tmp_path, run_id, status=status)
    assert runs.recover_in_flight_runs(tmp_path) == 1
    assert runs.get_run(tmp_path, run_id)["status"] == "interrupted"


@pytest.mark.parametrize("terminal", ["completed", "cancelled", "interrupted", "failed"])
def test_guarded_unassociated_run_cannot_resurrect_terminal_status(tmp_path, terminal):
    runs.initialize_runs_db(tmp_path)
    with runs._connect(tmp_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        runs._insert_run_in_transaction(
            conn, run_id="fixture", branch_def_id="fixture", thread_id="fixture",
            inputs={}, actor="owner", owner_user_id="owner", queue_universe_id="universe",
            _workspace_authenticated=False,
        )
    runs.update_run_status(tmp_path, "fixture", status=terminal)
    with try_run_execution_lock(tmp_path, run_id="fixture") as guard:
        assert guard is not None
        with runs._managed_execution_scope(tmp_path, "fixture", provided=guard):
            with pytest.raises(runs.RunExecutionAuthorityLost, match="expected prior status"):
                runs.update_run_status(tmp_path, "fixture", status="running")
    assert runs.get_run(tmp_path, "fixture")["status"] == terminal


@pytest.mark.parametrize("stop", [False, True])
def test_actual_prepared_invocation_retains_guard_without_family(tmp_path, monkeypatch, stop):
    from tests.test_workspace_family_execution_guard import (
        test_real_graph_holds_exact_guard_through_provider_settlement,
    )

    assert family._MANAGED_RUNTIME_READY.get() is None
    test_real_graph_holds_exact_guard_through_provider_settlement(tmp_path, monkeypatch, stop)
    with runs._connect(tmp_path) as conn:
        assert conn.execute(
            "SELECT count(*) FROM runs WHERE workspace_budget_root_run_id IS NOT NULL"
        ).fetchone()[0] == 0


@pytest.mark.parametrize("invalid", ["retired", "other-root", "other-process", "unknown-type"])
def test_invalid_runtime_readiness_cannot_stamp_root(tmp_path, invalid):
    ready = family._ManagedRuntimeReadiness(runs.runs_db_path(tmp_path))
    if invalid == "retired":
        ready.retire()
    elif invalid == "other-root":
        ready.database = runs.runs_db_path(tmp_path / "other").resolve()
    elif invalid == "other-process":
        ready.pid = -1
    else:
        ready = object()
    token = family._MANAGED_RUNTIME_READY.set(ready)
    try:
        with pytest.raises(family.FamilyRefused, match="readiness"):
            runs.create_run(
                tmp_path, branch_def_id="fixture", thread_id="fixture", inputs={},
                actor="owner", owner_user_id="owner", queue_universe_id="universe",
            )
    finally:
        family._MANAGED_RUNTIME_READY.reset(token)
    with runs._connect(tmp_path) as conn:
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_retiring_readiness_invalidates_an_already_copied_context(tmp_path):
    import contextvars

    from tests.workspace_family_test_support import simulated_managed_runtime

    with simulated_managed_runtime(tmp_path):
        stale = contextvars.copy_context()
    with runs._connect(tmp_path) as conn:
        with pytest.raises(family.FamilyRefused, match="retired"):
            stale.run(family.root_enrollment_enabled, conn)
