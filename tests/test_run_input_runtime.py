"""Common prepared worker, using real SQLite/guards and a traced executor seam."""

from __future__ import annotations

import contextvars
import threading
from concurrent.futures import Future

import pytest

from tinyassets import run_input_runtime as runtime
from tinyassets import runs
from tinyassets.auth.middleware import current_identity_or_none
from tinyassets.auth.provider import Identity
from tinyassets.branches import BranchDefinition
from tinyassets.storage import run_input_admissions as admissions
from tinyassets.storage.run_execution_lock import try_run_execution_lock


@pytest.fixture
def admitted(tmp_path):
    branch = BranchDefinition.from_dict(
        {
            "branch_def_id": "branch",
            "name": "Exact admitted branch",
            "version": 1,
            "node_defs": [
                {
                    "node_id": "work",
                    "display_name": "Work",
                    "source_code": "def run(state):\n    return state",
                }
            ],
            "graph_nodes": [{"id": "work", "node_def_id": "work", "position": 0}],
            "edges": [{"from_node": "work", "to_node": "END"}],
            "entry_point": "work",
            "state_schema": [{"name": "topic", "type": "string"}],
        }
    )
    assert not branch.validate(), branch.validate()
    run_id = runs.create_run(
        tmp_path,
        branch_def_id="branch",
        thread_id="",
        inputs={"topic": "exact"},
        actor="universe:u",
        owner_user_id="owner",
    )
    with runs._connect(tmp_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE runs SET queue_universe_id='u' WHERE run_id=?", (run_id,))
        admissions.ensure_schema(conn)
        admissions.accept_in_transaction(
            conn, run_id=run_id, owner_id="owner", universe_id="u", snapshot=branch.to_dict()
        )
    return tmp_path, run_id


def prepared(base, envelope, **transactions):
    return runtime.PreparedRunExecution(
        identity=Identity(user_id="owner", username="owner", capabilities=["read"]),
        actor="universe:u",
    )


def test_prepared_worker_keeps_exact_run_inputs_guard_and_clean_context(admitted, monkeypatch):
    base, run_id = admitted
    private = contextvars.ContextVar("sender_private", default=None)
    private.set("secret")
    calls = []
    monkeypatch.setattr(runs, "_initialize_prepared_run", lambda *a, **k: None)

    def invoke(base, **kwargs):
        assert kwargs["run_id"] == run_id
        assert kwargs["inputs"] == {"topic": "exact"}
        assert private.get() is None
        assert current_identity_or_none().user_id == "owner"
        with runs._connect(base) as conn:
            kwargs["_execution_guard"].require_held(conn)
            row = conn.execute("SELECT * FROM run_input_admissions").fetchone()
            assert row["execution_started_at"] and row["claim_token"]
        calls.append(1)
        runs.update_run_status(base, run_id, status="completed")

    monkeypatch.setattr(runs, "_invoke_prepared_branch", invoke)
    assert runtime.dispatch_admitted_run(base, run_id=run_id, prepare=prepared)
    runs.wait_for(run_id, timeout=10)
    assert calls == [1]
    assert runtime.dispatch_admitted_run(base, run_id=run_id, prepare=prepared)
    runs.wait_for(run_id, timeout=10)
    assert calls == [1]


def test_trusted_direct_options_and_post_unwind_observation(admitted, monkeypatch):
    base, run_id = admitted
    observed = threading.Event()
    calls = []

    def status_callback(*args):
        pass

    monkeypatch.setattr(runs, "_initialize_prepared_run", lambda *a, **k: None)

    def options(base, envelope, **transactions):
        return runtime.PreparedRunExecution(
            identity=prepared(base, envelope).identity,
            actor="universe:u",
            recursion_limit=123,
            concurrency_budget_override=3,
            on_node_status=status_callback,
        )

    def invoke(base, **kwargs):
        assert kwargs["recursion_limit"] == 123
        assert kwargs["concurrency_budget_override"] == 3
        assert kwargs["on_node_status"] is status_callback
        runs.update_run_status(base, run_id, status="completed")

    def settled(base, actual_run):
        try:
            assert actual_run == run_id
            with try_run_execution_lock(base, run_id=run_id) as guard:
                assert guard is not None
            calls.append(runs.get_run(base, run_id)["status"])
        finally:
            observed.set()

    monkeypatch.setattr(runs, "_invoke_prepared_branch", invoke)
    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=options, on_settled=settled)
    runs.wait_for(run_id, timeout=10)
    assert observed.wait(5) and calls == ["completed"]


def test_prepared_worker_captures_exact_choices_before_real_dispatch_seam(admitted, monkeypatch):
    from tinyassets.run_admission_envelope import resolve_admitted_execution

    base, run_id = admitted
    captured = []

    def options(base, envelope, **transactions):
        return runtime.PreparedRunExecution(
            identity=prepared(base, envelope).identity, actor="universe:u",
            recursion_limit=123, concurrency_budget_override=3,
        )

    def invoke(base, **kwargs):
        # Do not stub _initialize_prepared_run: this reads its committed SQLite
        # record at the actual worker dispatch boundary, not a codec-only test.
        actual = resolve_admitted_execution(base, runs.get_run(base, run_id))
        assert actual.branch.to_dict() == kwargs["branch"].to_dict()
        assert actual.recursion_limit == kwargs["recursion_limit"] == 123
        assert actual.concurrency_budget_override == kwargs["concurrency_budget_override"] == 3
        captured.append(actual)
        runs.update_run_status(base, run_id, status="completed")

    monkeypatch.setattr(runs, "_invoke_prepared_branch", invoke)
    assert runtime.dispatch_admitted_run(base, run_id=run_id, prepare=options)
    runs.wait_for(run_id, timeout=10)
    assert len(captured) == 1


def test_observation_failure_never_rewrites_execution_and_is_logged(admitted, monkeypatch, caplog):
    base, run_id = admitted
    observed = threading.Event()
    monkeypatch.setattr(runs, "_initialize_prepared_run", lambda *a, **k: None)

    def invoke(base, **kwargs):
        runs.update_run_status(base, run_id, status="completed")

    def settled(*args):
        raise RuntimeError("fixture projection unavailable")

    original_log = runtime.logger.exception

    def logged(*args, **kwargs):
        original_log(*args, **kwargs)
        observed.set()

    monkeypatch.setattr(runtime.logger, "exception", logged)

    monkeypatch.setattr(runs, "_invoke_prepared_branch", invoke)
    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=prepared, on_settled=settled)
    runs.wait_for(run_id, timeout=10)
    assert observed.wait(5)
    assert runs.get_run(base, run_id)["status"] == "completed"
    assert "observation failed" in caplog.text


def test_observation_sees_prestart_failure_once_after_guard_unwinds(admitted):
    base, run_id = admitted
    observed = threading.Event()
    calls = []

    def denied(*args, **kwargs):
        raise PermissionError("fixture source revoked")

    def settled(base, actual_run):
        try:
            with try_run_execution_lock(base, run_id=actual_run) as guard:
                assert guard is not None
            calls.append(runs.get_run(base, actual_run)["status"])
        finally:
            observed.set()

    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=denied, on_settled=settled)
    runs.wait_for(run_id, timeout=10)
    assert observed.wait(5) and calls == ["failed"]


def test_pool_cancellation_observation_does_not_manufacture_terminal_state(admitted, monkeypatch):
    base, run_id = admitted
    future = Future()
    calls = []

    class Deferred:
        def submit(self, *args, **kwargs):
            return future

    monkeypatch.setattr(runs, "_get_executor", lambda **kwargs: Deferred())
    runtime.dispatch_admitted_run(
        base,
        run_id=run_id,
        prepare=prepared,
        on_settled=lambda root, rid: calls.append(runs.get_run(root, rid)["status"]),
    )
    assert future.cancel()
    assert calls == ["queued"]
    with runs._connect(base) as conn:
        assert (
            conn.execute("SELECT execution_started_at FROM run_input_admissions").fetchone()[0]
            is None
        )


def test_live_common_guard_prevents_start_without_status_mutation(admitted):
    base, run_id = admitted
    with try_run_execution_lock(base, run_id=run_id):
        runtime.dispatch_admitted_run(base, run_id=run_id, prepare=prepared)
        runs.wait_for(run_id, timeout=10)
    with runs._connect(base) as conn:
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == "queued"
        assert (
            conn.execute("SELECT execution_started_at FROM run_input_admissions").fetchone()[0]
            is None
        )


def test_started_marker_keeps_debt_without_replay_or_invented_kernel_proof(admitted, monkeypatch):
    base, run_id = admitted
    with try_run_execution_lock(base, run_id=run_id) as guard:
        with runs._connect(base) as conn:
            conn.execute("BEGIN IMMEDIATE")
            admissions.start_in_transaction(conn, guard, owner_id="owner", universe_id="u")
    monkeypatch.setattr(runs, "_invoke_prepared_branch", lambda *a, **k: pytest.fail("replayed"))
    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=prepared)
    runs.wait_for(run_id, timeout=10)
    with runs._connect(base) as conn:
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == "queued"
        assert conn.execute("SELECT execution_started_at FROM run_input_admissions").fetchone()[0]


def test_current_authority_refusal_starts_no_provider(admitted, monkeypatch):
    base, run_id = admitted
    monkeypatch.setattr(
        runs, "_invoke_prepared_branch", lambda *a, **k: pytest.fail("unauthorized")
    )

    def revoked(base, envelope, **transactions):
        raise ValueError("current authority revoked")

    def terminal_seam(base, *, run_id, execution_guard, status, error):
        # Traced boundary only. Cloud's actual family/cancel CAS tests are a
        # separate required integration gate, not simulated by this fixture.
        with runs._connect(base) as conn:
            execution_guard.require_held(conn)
        runs.update_run_status(base, run_id, status=status, error=error)

    monkeypatch.setattr(runs, "terminalize_unstarted_run", terminal_seam, raising=False)

    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=revoked)
    runs.wait_for(run_id, timeout=10)
    with runs._connect(base) as conn:
        assert (
            conn.execute("SELECT execution_started_at FROM run_input_admissions").fetchone()[0]
            is None
        )
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == "failed"


def test_preparer_cannot_replace_authoritative_inputs_or_snapshot(admitted, monkeypatch):
    base, run_id = admitted
    observed = []
    monkeypatch.setattr(runs, "_initialize_prepared_run", lambda *a, **k: None)

    def misleading(base, envelope, **transactions):
        envelope["inputs"] = {"topic": "different"}
        envelope["snapshot"]["name"] = "Different target"
        return prepared(base, envelope)

    def invoke(base, **kwargs):
        observed.append((kwargs["inputs"], kwargs["branch"].name))
        runs.update_run_status(base, run_id, status="completed")

    monkeypatch.setattr(runs, "_invoke_prepared_branch", invoke)
    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=misleading)
    runs.wait_for(run_id, timeout=10)
    assert observed == [({"topic": "exact"}, "Exact admitted branch")]


def test_provider_binding_after_committed_start_has_no_sql_writer(admitted, monkeypatch):
    import sqlite3

    from tinyassets.storage import _connect as author_connection

    base, run_id = admitted
    observed = []
    monkeypatch.setattr(runs, "_initialize_prepared_run", lambda *a, **k: None)

    def bind(base, envelope, branch):
        assert current_identity_or_none().user_id == "owner"
        with author_connection(base) as conn:
            conn.execute("PRAGMA busy_timeout=50")
            conn.execute("BEGIN IMMEDIATE")
        with sqlite3.connect(runs.runs_db_path(base), timeout=0.05) as conn:
            conn.execute("BEGIN IMMEDIATE")
            assert conn.execute("SELECT execution_started_at FROM run_input_admissions").fetchone()[
                0
            ]
        observed.append("bound")
        return lambda *a, **k: "provider"

    def origin(base, envelope, **transactions):
        assert transactions["author_conn"].in_transaction
        assert transactions["runs_conn"].in_transaction
        return runtime.PreparedRunExecution(prepared(base, envelope).identity, "universe:u", bind)

    def invoke(base, **kwargs):
        assert kwargs["provider_call"]() == "provider"
        runs.update_run_status(base, run_id, status="completed")

    monkeypatch.setattr(runs, "_invoke_prepared_branch", invoke)
    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=origin)
    runs.wait_for(run_id, timeout=10)
    assert observed == ["bound"]


def test_owner_change_does_not_terminalize_another_owners_run(admitted, monkeypatch):
    base, run_id = admitted
    with runs._connect(base) as conn:
        conn.execute("UPDATE runs SET owner_user_id='someone-else'")
    monkeypatch.setattr(runs, "_invoke_prepared_branch", lambda *a, **k: pytest.fail("executed"))
    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=prepared)
    runs.wait_for(run_id, timeout=10)
    with runs._connect(base) as conn:
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == "queued"


def test_terminal_or_cancelled_run_does_not_call_origin_preparer(admitted):
    base, run_id = admitted
    runs.update_run_status(base, run_id, status="cancelled")

    def forbidden(base, envelope, **transactions):
        pytest.fail("cancelled admission was prepared")

    runtime.dispatch_admitted_run(base, run_id=run_id, prepare=forbidden)
    runs.wait_for(run_id, timeout=10)


@pytest.mark.parametrize("winner", ["cancelled", "interrupted", "failed", "completed", "resumed"])
def test_saturated_pool_free_guard_is_not_death_and_late_worker_respects_winner(
    admitted,
    monkeypatch,
    winner,
):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    base, run_id = admitted
    occupied = threading.Event()
    release = threading.Event()

    def block():
        occupied.set()
        assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(block)
        assert occupied.wait(2)
        monkeypatch.setattr(runs, "_get_executor", lambda **kwargs: pool)
        monkeypatch.setattr(
            runs, "_invoke_prepared_branch", lambda *a, **k: pytest.fail("late execute")
        )
        try:
            assert runtime.dispatch_admitted_run(base, run_id=run_id, prepare=prepared)
            with try_run_execution_lock(base, run_id=run_id) as guard:
                assert guard is not None  # Healthy pool holds work, not its guard yet.
                with runs._connect(base) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    assert (
                        admissions.recovery_state_in_transaction(
                            conn, guard, owner_id="owner", universe_id="u"
                        )
                        == "pending"
                    )
                    assert conn.execute("SELECT status FROM runs").fetchone()[0] == "queued"
                # Simulate an independently authorized winner, not a recovery
                # decision based on free guard. The late worker must preserve it.
                runs.update_run_status(base, run_id, status=winner)
        finally:
            release.set()
        runs.wait_for(run_id, timeout=5)
    with runs._connect(base) as conn:
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == winner
        assert (
            conn.execute("SELECT execution_started_at FROM run_input_admissions").fetchone()[0]
            is None
        )
