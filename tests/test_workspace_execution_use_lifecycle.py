"""Real sandbox RPC drain can outlive a node, but not execution ownership."""

import sys
import threading

import pytest

from tests.test_workspace_family_transitions import _create, _reason
from tinyassets import graph_compiler, node_sandbox, runs
from tinyassets.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition
from tinyassets.storage.run_execution_lock import try_run_execution_lock
from tinyassets.workspace_family import FamilyRefused


def test_nested_managed_scope_reuses_use_without_minting_or_retiring(tmp_path, monkeypatch):
    root, _member = _create(tmp_path)
    with runs._managed_execution_scope(tmp_path, root) as guard:
        use = runs._RUN_EXECUTION_USE.get()
        monkeypatch.setattr(guard, "issue_use", lambda _conn: pytest.fail("nested mint"))
        with runs._managed_execution_scope(tmp_path, root, provided=guard) as inner:
            assert inner is guard and runs._RUN_EXECUTION_USE.get() is use
        assert not guard._closing
        with runs._execution_use_scope():
            with runs._connect(tmp_path) as conn:
                use.require_in_use(conn)
        with pytest.raises(runs.RunExecutionAuthorityLost):
            with runs._managed_execution_scope(tmp_path, root, provided=use):
                pytest.fail("use became an owner")
    assert guard._closing


@pytest.mark.parametrize("cancel,trailing,parallel", [
    (False, False, False), (True, False, False), (False, True, False), (False, False, True),
])
def test_actual_rpc_outlives_node_but_pins_owner_and_cannot_dispatch_late(
    tmp_path, monkeypatch, cancel, trailing, parallel,
):
    root, member = _create(tmp_path)
    entered, release, node_done, owner_done = (threading.Event() for _ in range(4))
    late_refused, errors = [], []

    def slow_rpc(*_args, **_kwargs):
        use = runs._RUN_EXECUTION_USE.get()
        assert use is not None
        with runs._connect(tmp_path) as conn:
            use.require_in_use(conn)
        entered.set()
        assert release.wait(15)
        try:
            runs.create_run(
                tmp_path, branch_def_id="late", thread_id="", inputs={}, actor="actor",
                owner_user_id="owner", queue_universe_id="universe", _workspace_parent=member,
            )
        except FamilyRefused:
            late_refused.append(True)
        else:
            raise AssertionError("late callback admitted a child")
        return {}

    monkeypatch.setattr(graph_compiler, "_build_node_mcp_invoker", lambda *_a, **_k: slow_rpc)
    class TrailingLineLauncher(node_sandbox.PlainSubprocessLauncher):
        def build_argv(self, *_args):
            return [sys.executable, "-I", "-c", "import json; print(json.dumps("
                    "{'rpc': {'id': 1, 'action': 'late', 'kwargs': {}}}), end='', flush=True)"]

    monkeypatch.setattr(node_sandbox, "DEFAULT_LAUNCHER_FACTORY",
                        TrailingLineLauncher if trailing else node_sandbox.PlainSubprocessLauncher)
    node = NodeDefinition(
        node_id="rpc", display_name="rpc", timeout_seconds=1,
        source_code="def run(state):\n    return invoke_mcp_action('late')\n",
    ).mark_approved()
    terminal = "cancelled" if cancel else "failed" if parallel else "interrupted"

    app = None
    if parallel:
        from langgraph.checkpoint.memory import InMemorySaver

        branch = BranchDefinition(name="parallel-use", entry_point="rpc")
        branch.node_defs = [node, NodeDefinition(
            node_id="fail", display_name="fail",
            source_code="def run(state): raise ValueError('sibling failed')",
        ).mark_approved()]
        branch.graph_nodes = [GraphNodeRef(id=n.node_id, node_def_id=n.node_id)
                              for n in branch.node_defs]
        branch.edges = [EdgeDefinition(from_node=left, to_node=right) for left, right in
                        [("START", "rpc"), ("START", "fail"), ("rpc", "END"), ("fail", "END")]]
        branch.state_schema = [{"name": "x", "type": "int"}]
        compiled = graph_compiler.compile_branch(branch, base_path=tmp_path)
        app = compiled.graph.compile(checkpointer=InMemorySaver())

    def owner():
        try:
            with runs._managed_execution_scope(tmp_path, root):
                fn = graph_compiler._build_source_code_node(
                    node, event_sink=None, base_path=tmp_path,
                    should_cancel=lambda: runs.is_cancel_requested(tmp_path, root),
                )
                with pytest.raises((graph_compiler.NodeTimeoutError,
                                    graph_compiler.NodeCancelledError,
                                    graph_compiler.CodeNodeError)):
                    if app is not None:
                        app.invoke({"x": 1}, config={"configurable": {"thread_id": "parallel"}})
                    else:
                        fn({})
                runs.update_run_status(tmp_path, root, status=terminal)
                node_done.set()
        except BaseException as exc:
            errors.append(exc)
        finally:
            owner_done.set()

    thread = threading.Thread(target=owner)
    thread.start()
    try:
        assert entered.wait(5)
        if cancel:
            assert runs.request_cancel(tmp_path, root)
        assert node_done.wait(8), errors
        assert not owner_done.is_set()
        assert _reason(tmp_path, root) == terminal
        with try_run_execution_lock(tmp_path, run_id=root) as competing:
            assert competing is None
        release.set()
        thread.join(5)
        assert owner_done.is_set() and not errors
        assert late_refused == [True]
        with runs._connect(tmp_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        with try_run_execution_lock(tmp_path, run_id=root) as fresh:
            assert fresh is not None
    finally:
        release.set()
        thread.join(5)
