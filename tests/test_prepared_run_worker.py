"""The factored worker invokes an existing run and settles its provider once."""

import pytest

from tests.test_branch_runner import _single_node_branch
from tinyassets import foreground_run_provider, runs


@pytest.mark.parametrize(
    "result", ["completed", "cancelled", "failed", "crash", "settlement_failure"]
)
def test_prepared_worker_keeps_run_and_settlement_contract(tmp_path, monkeypatch, result):
    branch = _single_node_branch("Echo {topic}")
    inputs = {"topic": "receiver input"}
    run_id = runs.create_run(
        tmp_path,
        branch_def_id=branch.branch_def_id,
        thread_id="",
        inputs=inputs,
        actor="universe:receiver",
        owner_user_id="receiver",
        queue_universe_id="receiver",
    )
    calls = []

    def provider(text):
        return text

    def invoke(base, **kwargs):
        calls.append("invoke")
        assert base == tmp_path
        assert kwargs["run_id"] == run_id
        assert kwargs["branch"] is branch
        assert kwargs["inputs"] == inputs
        assert kwargs["provider_call"] is provider
        assert kwargs["recursion_limit"] == 37
        assert kwargs["concurrency_budget_override"] == 3
        assert kwargs["invocation_depth"] == 2
        context = kwargs["enqueue_context"]
        assert context.universe_id == "receiver"
        assert context.actor == "universe:receiver"
        assert context.origin_branch_task_id == f"run:{run_id}"
        if result == "crash":
            raise RuntimeError("private crash details")
        status = "completed" if result == "settlement_failure" else result
        runs.update_run_status(base, run_id, status=status)
        return runs.RunOutcome(run_id=run_id, status=status, output={"out": "exact"}, error="")

    def close(actual):
        calls.append("close")
        assert actual is provider
        if result == "settlement_failure":
            raise RuntimeError("injected settlement failure")

    monkeypatch.setattr(runs, "_invoke_graph", invoke)
    monkeypatch.setattr(foreground_run_provider, "close_foreground_run_provider", close)
    outcome = runs._invoke_prepared_branch(
        tmp_path,
        run_id=run_id,
        branch=branch,
        inputs=inputs,
        actor="universe:receiver",
        provider_call=provider,
        recursion_limit=37,
        concurrency_budget_override=3,
        invocation_depth=2,
        enqueue_universe_id="receiver",
    )
    assert calls == ["invoke", "close"]
    assert outcome.run_id == run_id
    assert outcome.status == ("failed" if result in {"crash", "settlement_failure"} else result)
    with runs._connect(tmp_path) as conn:
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == outcome.status


def test_reserved_run_executes_real_graph_without_second_run(tmp_path):
    branch = _single_node_branch("Echo {topic}")
    inputs = {"topic": "exact 🧪", "style": "plain"}
    run_id = runs.create_run(
        tmp_path,
        branch_def_id=branch.branch_def_id,
        thread_id="",
        inputs=inputs,
        actor="receiver",
        owner_user_id="receiver",
    )
    # Repeating pre-execution initialization after a crash must not add nodes.
    for _ in range(2):
        runs._initialize_prepared_run(tmp_path, run_id=run_id, branch=branch, actor="receiver")
    with runs._connect(tmp_path) as conn:
        assert conn.execute("SELECT count(*) FROM run_events").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM run_lineage").fetchone()[0] == 1
    called = []

    def provider(prompt, system="", **kwargs):
        called.append(prompt)
        return "receiver result 🧪"

    outcome = runs._invoke_prepared_branch(
        tmp_path,
        run_id=run_id,
        branch=branch,
        inputs=inputs,
        actor="receiver",
        provider_call=provider,
        recursion_limit=10,
    )
    assert outcome.status == "completed", outcome.error
    assert outcome.output["out"] == "receiver result 🧪"
    assert called == ["Echo exact 🧪"]
    with runs._connect(tmp_path) as conn:
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
        assert conn.execute("SELECT thread_id FROM runs").fetchone()[0] == run_id
