"""Legacy process-local recovery cannot retire common admitted run ownership."""

import multiprocessing
import sqlite3

import pytest

from tinyassets import runs
from tinyassets.storage import run_input_admissions as admissions
from tinyassets.storage.run_execution_lock import try_run_execution_lock


def _other_process(base, run_id, mode, result):
    if mode == "startup":
        count = runs.recover_in_flight_runs(base)
        result.put((count, runs.get_run(base, run_id)["status"]))
    else:
        result.put((0, runs.get_run(base, run_id)["status"]))


def _reserved(base):
    run_id = runs.create_run(
        base,
        branch_def_id="branch",
        thread_id="",
        inputs={},
        actor="owner",
        owner_user_id="owner",
    )
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        # Existing reservations may acquire their admitted universe after run
        # insertion, before the ordinary initializer assigns a managed family.
        conn.execute("UPDATE runs SET queue_universe_id='universe' WHERE run_id=?", (run_id,))
        admissions.ensure_schema(conn)
        admissions.accept_in_transaction(
            conn,
            run_id=run_id,
            owner_id="owner",
            universe_id="universe",
            snapshot={"branch_def_id": "branch"},
        )
        conn.execute("UPDATE runs SET started_at=1 WHERE run_id=?", (run_id,))
        assert conn.execute("SELECT workspace_budget_root_run_id FROM runs").fetchone()[0] is None
    return run_id


@pytest.mark.parametrize("mode", ["read", "startup"])
@pytest.mark.parametrize("started", [False, True])
def test_aged_pre_family_admission_survives_other_process_recovery(
    tmp_path,
    monkeypatch,
    mode,
    started,
):
    run_id = _reserved(tmp_path)
    if started:
        with try_run_execution_lock(tmp_path, run_id=run_id) as guard:
            with runs._connect(tmp_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                assert admissions.start_in_transaction(
                    conn, guard, owner_id="owner", universe_id="universe"
                )
    # There is deliberately no local Future, held guard, or family assignment.
    # Pre-marker may be live pool work; post-marker remains ambiguous debt.
    ctx = multiprocessing.get_context("spawn")
    result = ctx.Queue()
    child = ctx.Process(target=_other_process, args=(tmp_path, run_id, mode, result))
    child.start()
    try:
        assert result.get(timeout=20) == (0, "queued")
        child.join(15)
        assert child.exitcode == 0
        with runs._connect(tmp_path) as conn:
            assert conn.execute("SELECT status FROM runs").fetchone()[0] == "queued"
            marker = conn.execute(
                "SELECT execution_started_at FROM run_input_admissions"
            ).fetchone()[0]
            assert (marker is not None) == started
    finally:
        child.join(5)
        if child.is_alive():
            child.terminate()
            child.join(5)
        result.close()


@pytest.mark.parametrize("has_empty_table", [False, True])
def test_non_admitted_recovery_needs_its_owner_dead(tmp_path, has_empty_table):
    """A read never ends a run; recovery ends it once its owner is dead."""
    from tests.run_owner_helpers import mark_owner_dead

    run_id = runs.create_run(
        tmp_path, branch_def_id="legacy", thread_id="", inputs={}, actor="owner"
    )
    with runs._connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET started_at=1")
        if has_empty_table:
            admissions.ensure_schema(conn)
    assert runs.get_run(tmp_path, run_id)["status"] == "queued"
    assert runs.recover_in_flight_runs(tmp_path) == 0, "its owner is this live process"
    mark_owner_dead(tmp_path, run_id)
    assert runs.recover_in_flight_runs(tmp_path) == 1
    assert runs.get_run(tmp_path, run_id)["status"] == "interrupted"


@pytest.mark.parametrize("malformed", ["view", "missing_column"])
def test_present_broken_admission_schema_never_enables_retirement(
    tmp_path,
    malformed,
):
    from tests.run_owner_helpers import mark_owner_dead

    run_id = runs.create_run(
        tmp_path, branch_def_id="legacy", thread_id="", inputs={}, actor="owner"
    )
    mark_owner_dead(tmp_path, run_id)
    with runs._connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET started_at=1")
        if malformed == "view":
            conn.execute("CREATE VIEW run_input_admissions AS SELECT run_id FROM runs")
        else:
            conn.execute("CREATE TABLE run_input_admissions(wrong TEXT)")
    with pytest.raises((RuntimeError, sqlite3.OperationalError)):
        runs.recover_in_flight_runs(tmp_path)
    with runs._connect(tmp_path) as conn:
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == "queued"
