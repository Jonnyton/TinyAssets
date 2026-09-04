"""Runs bind to the universe RUNNING them, so external-write effectors read
that universe's credential vault + effector-consent.

Regression for the 2026-08-18 gap: connector-triggered runs never recorded
their universe (``queue_universe_id`` was ``None``), so ``_invoke_graph`` handed
the effector ``base_path`` = the flat data root instead of the universe dir. The
github_pr effector treats ``base_path`` AS the universe dir, so capability +
consent gates looked under ``/data`` and failed closed even when the owner had
granted them under ``/data/<universe_id>``. This is what blocked the Tiny
universe from opening a real pull request through the connector.
"""

from pathlib import Path

from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.runs import (
    _resolve_effector_base,
    execute_branch_async,
    get_run,
    wait_for,
)


def _one_node_branch() -> BranchDefinition:
    b = BranchDefinition(name="Uni", entry_point="n1")
    b.node_defs = [
        NodeDefinition(
            node_id="n1", display_name="N1",
            prompt_template="hello", output_keys=["n1_out"],
        )
    ]
    b.graph_nodes = [GraphNodeRef(id="n1", node_def_id="n1", position=0)]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="n1"),
        EdgeDefinition(from_node="n1", to_node="END"),
    ]
    b.state_schema = [{"name": "n1_out", "type": "str"}]
    return b


def _fake_provider(prompt, system="", *, role="writer", fallback_response=None):
    return "[ok]"


def test_resolve_effector_base_uses_universe_hint(tmp_path):
    # An explicit universe hint scopes base_path to the universe dir.
    base = str(tmp_path)
    assert _resolve_effector_base(base, "any-run", "u-x") == Path(base) / "u-x"


def test_resolve_effector_base_falls_back_to_data_root(tmp_path):
    # No hint and no run row -> the flat data root (unknown universe).
    base = str(tmp_path)
    assert _resolve_effector_base(base, "missing-run") == base


def test_resolve_effector_base_reads_run_row(tmp_path):
    # With no hint, it reads queue_universe_id off the run row.
    b = _one_node_branch()
    outcome = execute_branch_async(
        tmp_path, branch=b, inputs={},
        provider_call=_fake_provider,
        _enqueue_universe_id="u-row",
        actor="universe:u-test",
    )
    wait_for(outcome.run_id, timeout=10.0)
    assert _resolve_effector_base(str(tmp_path), outcome.run_id) == (
        Path(str(tmp_path)) / "u-row"
    )


def test_execute_branch_async_records_running_universe(tmp_path):
    # The run row records the universe running it, so downstream effector /
    # authority / consent resolution can bind to it.
    b = _one_node_branch()
    outcome = execute_branch_async(
        tmp_path, branch=b, inputs={},
        provider_call=_fake_provider,
        _enqueue_universe_id="u-tiny",
        actor="universe:u-test",
    )
    wait_for(outcome.run_id, timeout=10.0)
    record = get_run(tmp_path, outcome.run_id)
    assert record["status"] == "completed"
    assert record.get("queue_universe_id") == "u-tiny"


def test_execute_branch_async_without_universe_leaves_it_unset(tmp_path):
    # No universe threaded -> no false binding (fail-closed, not mis-bound).
    b = _one_node_branch()
    outcome = execute_branch_async(
        tmp_path, branch=b, inputs={},
        provider_call=_fake_provider,
        actor="universe:u-test",
    )
    wait_for(outcome.run_id, timeout=10.0)
    record = get_run(tmp_path, outcome.run_id)
    assert not record.get("queue_universe_id")
