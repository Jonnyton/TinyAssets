"""Managed execution and recovery share ownership, but Stop never waits for it."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_workspace_family_transitions import _create
from tests.workspace_family_test_support import managed_runtime  # noqa: F401
from tinyassets import runs
from tinyassets.storage.run_execution_lock import try_run_execution_lock


def test_stop_during_active_execution_guard_is_prompt(tmp_path):
    root, _ = _create(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with try_run_execution_lock(tmp_path, run_id=root) as guard:
            assert guard is not None
            assert pool.submit(runs.request_cancel, tmp_path, root).result(timeout=2)
            with runs._connect(tmp_path) as conn:
                guard.require_held(conn)
            assert runs.is_cancel_requested(tmp_path, root)


def test_managed_scope_reuses_only_current_exact_guard(tmp_path):
    root, _ = _create(tmp_path)
    with try_run_execution_lock(tmp_path, run_id=root) as guard:
        with runs._managed_execution_scope(tmp_path, root, provided=guard) as held:
            assert held is guard
            with runs._managed_execution_scope(tmp_path, root) as inner:
                assert inner is guard
        with runs._connect(tmp_path) as conn:
            guard.require_held(conn)
    with pytest.raises(RuntimeError, match="held"):
        with runs._managed_execution_scope(tmp_path, root, provided=guard):
            pytest.fail("retired guard was accepted")


def test_competing_managed_scope_never_rewrites_owner_status(tmp_path):
    root, _ = _create(tmp_path)
    with try_run_execution_lock(tmp_path, run_id=root):
        with pytest.raises(runs.RunExecutionAuthorityLost):
            with runs._managed_execution_scope(tmp_path, root):
                pytest.fail("competing execution entered")
    assert runs.get_run(tmp_path, root)["status"] == "running"


def test_another_run_guard_is_not_reused(tmp_path):
    root, _ = _create(tmp_path)
    other, _ = _create(tmp_path)
    with try_run_execution_lock(tmp_path, run_id=other) as wrong:
        with pytest.raises(runs.RunExecutionAuthorityLost):
            with runs._managed_execution_scope(tmp_path, root, provided=wrong):
                pytest.fail("wrong run guard was reused")


def test_unstarted_settlement_cancellation_wins_and_completed_output_is_untouched(tmp_path):
    root = runs.create_run(
        tmp_path,
        branch_def_id="branch",
        thread_id="",
        inputs={},
        actor="actor",
        owner_user_id="owner",
        queue_universe_id="universe",
    )
    with try_run_execution_lock(tmp_path, run_id=root) as guard:
        assert runs.request_cancel(tmp_path, root)
        assert (
            runs.terminalize_unstarted_run(
                tmp_path,
                run_id=root,
                execution_guard=guard,
                status="failed",
                error="provider admission",
            )
            == "cancelled"
        )
        assert runs.get_run(tmp_path, root)["status"] == "cancelled"
    other, _ = _create(tmp_path)
    runs.update_run_status(tmp_path, other, status="completed", output={"kept": "exact"})
    with try_run_execution_lock(tmp_path, run_id=other) as guard:
        assert (
            runs.terminalize_unstarted_run(
                tmp_path, run_id=other, execution_guard=guard, status="interrupted", error="late"
            )
            == "completed"
        )
    assert runs.get_run(tmp_path, other)["output"] == {"kept": "exact"}


def test_unstarted_settlement_never_retires_running_work(tmp_path):
    root, _ = _create(tmp_path)
    with try_run_execution_lock(tmp_path, run_id=root) as guard:
        assert (
            runs.terminalize_unstarted_run(
                tmp_path, run_id=root, execution_guard=guard, status="interrupted", error="restart"
            )
            == "running"
        )
    with pytest.raises(RuntimeError, match="held"):
        runs.terminalize_unstarted_run(
            tmp_path, run_id=root, execution_guard=guard, status="failed", error="late"
        )


def test_unstarted_settlement_preserves_a_resumed_replacement(tmp_path):
    root, _ = _create(tmp_path)
    with runs._connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET status='resumed' WHERE run_id=?", (root,))
        conn.commit()
    with try_run_execution_lock(tmp_path, run_id=root) as guard:
        assert runs.terminalize_unstarted_run(
            tmp_path, run_id=root, execution_guard=guard,
            status="failed", error="old queued attempt"
        ) == "resumed"


@pytest.mark.parametrize("stop", [False, True])
def test_real_graph_holds_exact_guard_through_provider_settlement(tmp_path, monkeypatch, stop):
    from tests.test_branch_runner import _single_node_branch
    from tinyassets import foreground_run_provider

    branch = _single_node_branch("Echo {topic}")
    root = runs.create_run(
        tmp_path,
        branch_def_id=branch.branch_def_id,
        thread_id="",
        inputs={},
        actor="owner",
        owner_user_id="owner",
        queue_universe_id="universe",
    )
    calls = []

    def provider(*args, **kwargs):
        with try_run_execution_lock(tmp_path, run_id=root) as competing:
            assert competing is None
        calls.append("provider")
        if stop:
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(runs.request_cancel, tmp_path, root).result(timeout=2)
        return "exact result"

    def settle(actual):
        assert actual is provider
        with try_run_execution_lock(tmp_path, run_id=root) as competing:
            assert competing is None
        calls.append("settle")

    monkeypatch.setattr(foreground_run_provider, "close_foreground_run_provider", settle)
    with try_run_execution_lock(tmp_path, run_id=root) as owned:
        result = runs._invoke_prepared_branch(
            tmp_path,
            run_id=root,
            branch=branch,
            inputs={"topic": "test", "style": "plain"},
            actor="owner",
            provider_call=provider,
            recursion_limit=100,
            enqueue_universe_id="universe",
            _execution_guard=owned,
        )
        with runs._connect(tmp_path) as conn:
            owned.require_held(conn)
    assert calls == ["provider", "settle"]
    assert result.status == ("cancelled" if stop else "completed")


@pytest.mark.parametrize(
    "winner", [None, "cancelled", "interrupted", "failed", "completed", "resumed"]
)
def test_saturated_pool_free_guard_is_not_orphan_or_permission_for_late_replay(
    tmp_path,
    monkeypatch,
    winner,
):
    import threading

    from tests.test_branch_runner import _single_node_branch
    from tinyassets import foreground_run_provider

    gate = threading.Event()
    calls = []
    branch = _single_node_branch("Echo {topic}")
    monkeypatch.setattr(
        foreground_run_provider,
        "prepare_foreground_run_provider",
        lambda provider, **kwargs: provider,
    )

    def settle(*_):
        if winner == "resumed":
            raise RuntimeError("old provider claim cannot settle replacement")

    monkeypatch.setattr(foreground_run_provider, "close_foreground_run_provider", settle)
    with ThreadPoolExecutor(max_workers=1) as pool:
        blocker = pool.submit(gate.wait)
        monkeypatch.setattr(runs, "_get_executor", lambda **kwargs: pool)
        try:
            outcome = runs._execute_branch_core(
                tmp_path,
                branch=branch,
                inputs={"topic": "test", "style": "plain"},
                actor="owner",
                owner_user_id="owner",
                _enqueue_universe_id="universe",
                provider_call=lambda *a, **k: calls.append("effect") or "exact",
            )
            future = runs.get_future(outcome.run_id)
            assert future is not None and not future.done()
            with try_run_execution_lock(tmp_path, run_id=outcome.run_id) as free:
                assert free is not None
            assert runs.recover_in_flight_runs(tmp_path) == 0
            assert runs.get_run(tmp_path, outcome.run_id)["status"] == "queued"
            if winner is None:
                import multiprocessing

                from tests.test_workspace_family_transitions import _other_worker_start_and_read

                process_context = multiprocessing.get_context("spawn")
                receiving, sending = process_context.Pipe(False)
                observer = process_context.Process(
                    target=_other_worker_start_and_read,
                    args=(tmp_path, outcome.run_id, sending),
                )
                observer.start()
                try:
                    assert receiving.poll(15)
                    assert receiving.recv() == (0, "queued", 0)
                    observer.join(15)
                    assert observer.exitcode == 0
                finally:
                    observer.join(5)
                    if observer.is_alive():
                        observer.terminate()
                        observer.join(5)
                    receiving.close()
                    sending.close()
            if winner == "cancelled":
                assert runs.request_cancel(tmp_path, outcome.run_id)
            elif winner == "resumed":
                from tinyassets import workspace_family as family

                old = family.execution_member(tmp_path, outcome.run_id, for_compile=True)
                runs.update_run_status(tmp_path, outcome.run_id, status="interrupted")
                with try_run_execution_lock(tmp_path, run_id=outcome.run_id) as owner:
                    assert owner is not None
                    with family.family_fence(tmp_path, outcome.run_id) as fence:
                        with runs._connect(tmp_path) as conn:
                            conn.execute("BEGIN IMMEDIATE")
                            # No kernel allocation exists in this queued test.
                            family.resume_in_transaction(conn, fence, old, empty=lambda: True)
                            conn.execute(
                                "UPDATE runs SET status='resumed' WHERE run_id=?", (outcome.run_id,)
                            )
            elif winner is not None:
                runs.update_run_status(tmp_path, outcome.run_id, status=winner)
            gate.set()
            blocker.result(timeout=5)
            result = future.result(timeout=10)
            assert result.status == (winner or "completed")
            assert calls == ([] if winner else ["effect"])
            assert runs.get_run(tmp_path, outcome.run_id)["status"] == result.status
        finally:
            gate.set()


def test_request_thread_provider_admission_failure_respects_cancel_winner(tmp_path, monkeypatch):
    from tests.test_branch_runner import _single_node_branch
    from tinyassets import foreground_run_provider

    def fail(provider, *, run_id, **kwargs):
        assert runs.request_cancel(tmp_path, run_id)
        raise RuntimeError("provider not admitted")

    monkeypatch.setattr(foreground_run_provider, "prepare_foreground_run_provider", fail)
    outcome = runs._execute_branch_core(
        tmp_path,
        branch=_single_node_branch("Echo {topic}"),
        inputs={"topic": "test", "style": "plain"},
        actor="owner",
        owner_user_id="owner",
        _enqueue_universe_id="universe",
        provider_call=lambda *_: pytest.fail("no execution"),
    )
    assert outcome.status == "cancelled"
    assert runs.get_run(tmp_path, outcome.run_id)["status"] == "cancelled"
