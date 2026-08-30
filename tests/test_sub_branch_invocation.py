"""Tests for the sub-branch invocation primitive.

Covers:
- validate() catches bad invoke_branch_spec / await_run_spec shapes
- _build_invoke_branch_node: blocking mode populates output_mapping
- _build_invoke_branch_node: async mode writes run_id
- _build_await_branch_run_node: polls until terminal and maps output
- await_branch_run: timeout raises TimeoutError
- await_branch_run: missing run_id_field in state raises RuntimeError
- compile_branch: missing base_path raises CompilerError for invoke nodes
- recursion depth cap raises CompilerError at compile time
- poll_child_run_status: returns immediately for completed run
- poll_child_run_status: raises KeyError for unknown run_id
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.graph_compiler import (
    BranchExecutionContext,
    CompilerError,
    _build_await_branch_run_node,
    _build_invoke_branch_node,
)
from tinyassets.runs import (
    MAX_INVOKE_BRANCH_DEPTH,
    ChildRunAwaitTimeout,
    poll_child_run_status,
)

#: Default valid execution context for closure-unit tests that exercise
#: output-mapping / failure-policy / emit behavior (not authorization). The
#: authorization + fail-closed contract has its own dedicated tests below.
_DEFAULT_TEST_CTX = BranchExecutionContext(
    actor="tester", universe_id="u", caller_provenance="own"
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _simple_branch(node_def: NodeDefinition, entry: str = "n1") -> BranchDefinition:
    return BranchDefinition(
        branch_def_id="b1",
        name="test",
        entry_point=entry,
        node_defs=[node_def],
        graph_nodes=[GraphNodeRef(id=entry, node_def_id=node_def.node_id)],
        state_schema=[
            {"name": "child_run_id", "type": "str"},
            {"name": "result", "type": "str"},
        ],
    )


# ─── validate() shape checks ──────────────────────────────────────────────────

class TestValidateInvokeBranchSpec:
    def test_missing_branch_def_id_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={"wait_mode": "blocking"},
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("branch_def_id" in e for e in errs)

    def test_invalid_wait_mode_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={"branch_def_id": "child", "wait_mode": "fire_and_forget"},
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("wait_mode" in e for e in errs)

    def test_valid_spec_no_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {},
                "output_mapping": {},
                "wait_mode": "blocking",
            },
        )
        b = _simple_branch(nd)
        errs = [
            e for e in b.validate()
            if "invoke_branch_spec" in e or "branch_def_id" in e or "wait_mode" in e
        ]
        assert not errs

    def test_invoke_spec_plus_template_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            prompt_template="hello",
            invoke_branch_spec={"branch_def_id": "child", "wait_mode": "blocking"},
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("mutually exclusive" in e for e in errs)


class TestValidateAwaitRunSpec:
    def test_missing_run_id_field_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            await_run_spec={"output_mapping": {}},
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("run_id_field" in e for e in errs)

    def test_valid_spec_no_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            await_run_spec={"run_id_field": "child_run_id", "output_mapping": {}},
        )
        b = _simple_branch(nd)
        errs = [e for e in b.validate() if "await_run_spec" in e or "run_id_field" in e]
        assert not errs

    def test_await_spec_plus_source_code_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            source_code="x = 1",
            await_run_spec={"run_id_field": "child_run_id"},
        ).mark_approved()
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("mutually exclusive" in e for e in errs)


# ─── compile_branch: missing base_path ────────────────────────────────────────

class TestCompileBranchMissingBasePath:
    def test_invoke_branch_node_without_base_path_raises(self):
        from tinyassets.graph_compiler import compile_branch

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "wait_mode": "blocking",
                "inputs_mapping": {},
                "output_mapping": {},
            },
        )
        b = BranchDefinition(
            branch_def_id="b1", name="test", entry_point="n1",
            node_defs=[nd],
            graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
            edges=[EdgeDefinition(from_node="n1", to_node="END")],
        )
        with pytest.raises(CompilerError, match="base_path"):
            compile_branch(b)

    def test_await_run_node_without_base_path_raises(self):
        from tinyassets.graph_compiler import compile_branch

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            await_run_spec={"run_id_field": "child_run_id", "output_mapping": {}},
        )
        b = BranchDefinition(
            branch_def_id="b1", name="test", entry_point="n1",
            node_defs=[nd],
            graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
            state_schema=[{"name": "child_run_id", "type": "str"}],
            edges=[EdgeDefinition(from_node="n1", to_node="END")],
        )
        with pytest.raises(CompilerError, match="base_path"):
            compile_branch(b)


# ─── _build_invoke_branch_node: blocking ──────────────────────────────────────

class TestInvokeBranchBlocking:
    def test_blocking_populates_output_mapping(self, tmp_path, monkeypatch):
        from tinyassets.runs import RUN_STATUS_COMPLETED, RunOutcome

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {"parent_q": "q"},
                "output_mapping": {"result": "answer"},
                "wait_mode": "blocking",
            },
        )

        child_outcome = RunOutcome(
            run_id="child-run-1",
            status=RUN_STATUS_COMPLETED,
            output={"answer": "42"},
            error="",
        )

        child_branch_mock = MagicMock()
        child_branch_mock.validate.return_value = []

        _child_raw = {"branch_def_id": "child", "name": "c",
                      "visibility": "public", "node_defs": [], "edges": []}
        with (
            patch("tinyassets.daemon_server.get_branch_definition", return_value=_child_raw),
            patch("tinyassets.branches.BranchDefinition.from_dict", return_value=child_branch_mock),
            patch("tinyassets.runs.execute_branch", return_value=child_outcome) as mock_exec,
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                execution_context=_DEFAULT_TEST_CTX,
            )
            result = fn({"parent_q": "what is 6x7?"})

        assert result == {"result": "42"}
        mock_exec.assert_called_once()
        _, call_kwargs = mock_exec.call_args
        assert call_kwargs["inputs"] == {"q": "what is 6x7?"}


class TestInvokeBranchAsync:
    def test_async_writes_run_id(self, tmp_path, monkeypatch):
        from tinyassets.runs import RUN_STATUS_QUEUED, RunOutcome

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {},
                "output_mapping": {"child_run_id": "ignored"},
                "wait_mode": "async",
            },
        )

        queued_outcome = RunOutcome(
            run_id="async-child-99",
            status=RUN_STATUS_QUEUED,
            output={},
            error="",
        )

        child_branch_mock = MagicMock()
        child_branch_mock.validate.return_value = []

        _child_raw = {"branch_def_id": "child", "name": "c",
                      "visibility": "public", "node_defs": [], "edges": []}
        with (
            patch("tinyassets.daemon_server.get_branch_definition", return_value=_child_raw),
            patch("tinyassets.branches.BranchDefinition.from_dict", return_value=child_branch_mock),
            patch("tinyassets.runs.execute_branch_async", return_value=queued_outcome),
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                execution_context=_DEFAULT_TEST_CTX,
            )
            result = fn({})

        assert result == {"child_run_id": "async-child-99"}


# ─── _build_await_branch_run_node ─────────────────────────────────────────────

class TestAwaitBranchRunNode:
    def test_populates_output_from_completed_child(self, tmp_path):
        from tinyassets.runs import RUN_STATUS_COMPLETED

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            await_run_spec={
                "run_id_field": "child_run_id",
                "output_mapping": {"result": "answer"},
                "timeout_seconds": 5.0,
            },
        )

        child_record = {
            "run_id": "child-99",
            "status": RUN_STATUS_COMPLETED,
            "output": {"answer": "hello"},
        }

        with patch("tinyassets.runs.poll_child_run_status", return_value=child_record) as mock_poll:
            fn = _build_await_branch_run_node(nd, base_path=tmp_path, event_sink=None)
            result = fn({"child_run_id": "child-99"})

        assert result == {"result": "hello"}
        mock_poll.assert_called_once_with(
            tmp_path, "child-99", timeout_seconds=5.0,
            expected_actor=None, expected_universe_id=None,
        )

    def test_missing_run_id_raises_runtime_error(self, tmp_path):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            await_run_spec={
                "run_id_field": "child_run_id",
                "output_mapping": {},
            },
        )
        fn = _build_await_branch_run_node(nd, base_path=tmp_path, event_sink=None)
        with pytest.raises(RuntimeError, match="child_run_id"):
            fn({"child_run_id": ""})

    def test_timeout_propagates(self, tmp_path):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            await_run_spec={
                "run_id_field": "child_run_id",
                "output_mapping": {},
                "timeout_seconds": 0.01,
            },
        )
        with patch("tinyassets.runs.poll_child_run_status", side_effect=TimeoutError("timed out")):
            fn = _build_await_branch_run_node(nd, base_path=tmp_path, event_sink=None)
            with pytest.raises(TimeoutError):
                fn({"child_run_id": "some-run"})


# ─── recursion depth cap ──────────────────────────────────────────────────────

class TestRecursionDepthCap:
    def test_depth_at_cap_raises_compiler_error(self, tmp_path):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "wait_mode": "blocking",
                "inputs_mapping": {},
                "output_mapping": {},
            },
        )
        with pytest.raises(CompilerError, match="recursion depth cap"):
            _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                depth=MAX_INVOKE_BRANCH_DEPTH, execution_context=_DEFAULT_TEST_CTX)

    def test_depth_below_cap_is_ok(self, tmp_path):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "wait_mode": "blocking",
                "inputs_mapping": {},
                "output_mapping": {},
            },
        )
        # Should not raise
        fn = _build_invoke_branch_node(
            nd, base_path=tmp_path, event_sink=None,
            depth=MAX_INVOKE_BRANCH_DEPTH - 1, execution_context=_DEFAULT_TEST_CTX)
        assert callable(fn)


# ─── poll_child_run_status ────────────────────────────────────────────────────

class TestPollChildRunStatus:
    def test_returns_immediately_for_completed_run(self, tmp_path):
        from tinyassets.runs import (
            RUN_STATUS_COMPLETED,
            create_run,
            initialize_runs_db,
            update_run_status,
        )

        initialize_runs_db(tmp_path)
        run_id = create_run(
            tmp_path,
            branch_def_id="b1",
            thread_id="thread-poll",
            run_name="poll-test",
            actor="tester",
            inputs={},
        )
        update_run_status(tmp_path, run_id, status=RUN_STATUS_COMPLETED, finished_at=time.time())

        record = poll_child_run_status(tmp_path, run_id, timeout_seconds=5.0)
        assert record["status"] == RUN_STATUS_COMPLETED
        assert record["run_id"] == run_id

    def test_raises_key_error_for_unknown_run(self, tmp_path):
        from tinyassets.runs import initialize_runs_db

        initialize_runs_db(tmp_path)
        with pytest.raises(KeyError, match="not found"):
            poll_child_run_status(tmp_path, "nonexistent-run", timeout_seconds=1.0)

    def test_raises_timeout_for_stuck_run(self, tmp_path):
        from tinyassets.runs import (
            RUN_STATUS_RUNNING,
            create_run,
            initialize_runs_db,
            update_run_status,
        )

        initialize_runs_db(tmp_path)
        run_id = create_run(
            tmp_path,
            branch_def_id="b1",
            thread_id="thread-stuck",
            run_name="stuck",
            actor="tester",
            inputs={},
        )
        update_run_status(tmp_path, run_id, status=RUN_STATUS_RUNNING)

        with pytest.raises(TimeoutError):
            poll_child_run_status(tmp_path, run_id, timeout_seconds=0.05, poll_interval=0.01)

    def test_timeout_carries_reclaim_context_for_still_running_child(self, tmp_path):
        from tinyassets.runs import (
            RUN_STATUS_RUNNING,
            create_run,
            initialize_runs_db,
            update_run_status,
        )

        initialize_runs_db(tmp_path)
        run_id = create_run(
            tmp_path,
            branch_def_id="child-branch",
            thread_id="thread-stuck",
            run_name="stuck",
            actor="tester",
            inputs={},
        )
        update_run_status(tmp_path, run_id, status=RUN_STATUS_RUNNING)

        with pytest.raises(ChildRunAwaitTimeout) as exc_info:
            poll_child_run_status(
                tmp_path, run_id, timeout_seconds=0.05, poll_interval=0.01,
            )

        exc = exc_info.value
        assert exc.run_id == run_id
        assert exc.child_status == RUN_STATUS_RUNNING
        assert exc.child_branch_def_id == "child-branch"
        assert exc.timeout_seconds == 0.05

    def test_await_timeout_promotes_parent_to_receipt_waiting(self, tmp_path):
        from tinyassets.runs import (
            RUN_STATUS_INTERRUPTED,
            RUN_STATUS_RUNNING,
            create_run,
            execute_branch,
            get_run,
            initialize_runs_db,
            list_recent_runs,
            update_run_status,
        )

        initialize_runs_db(tmp_path)
        child_run_id = create_run(
            tmp_path,
            branch_def_id="child-branch",
            thread_id="thread-child",
            run_name="child",
            actor="tester",
            inputs={},
        )
        update_run_status(tmp_path, child_run_id, status=RUN_STATUS_RUNNING)

        branch = BranchDefinition(name="parent", entry_point="await-child")
        branch.node_defs = [
            NodeDefinition(
                node_id="await-child",
                display_name="Await Child",
                await_run_spec={
                    "run_id_field": "child_run_id",
                    "output_mapping": {"child_result": "result"},
                    "timeout_seconds": 0.05,
                },
            ),
        ]
        branch.graph_nodes = [GraphNodeRef(id="await-child", node_def_id="await-child")]
        branch.edges = [
            EdgeDefinition(from_node="START", to_node="await-child"),
            EdgeDefinition(from_node="await-child", to_node="END"),
        ]
        branch.state_schema = [
            {"name": "child_run_id", "type": "str"},
            {"name": "child_result", "type": "str"},
        ]

        outcome = execute_branch(
            tmp_path,
            branch=branch,
            inputs={"child_run_id": child_run_id},
            actor="tester",  # parent + awaited child share the actor (task 4.2 binding)
        )

        assert outcome.status == RUN_STATUS_INTERRUPTED
        assert outcome.output["selected_child_status"] == "child_invocation_receipt_waiting"
        assert outcome.output["child_invocation_receipt_gate"]["child_run_id"] == child_run_id
        gate = outcome.output["child_invocation_receipt_gate"]
        assert gate["reclaim_action"] is None
        assert "not exposed by the advertised handles" in gate["reclaim_gap"]

        parent = get_run(tmp_path, outcome.run_id)
        assert parent is not None
        assert parent["status"] == RUN_STATUS_INTERRUPTED
        assert parent["output"]["selected_child_run_id"] == child_run_id

        recent = list_recent_runs(tmp_path, limit=1)
        assert recent[0]["failure_class"] == "child_receipt_waiting"
        assert (
            "not exposed by the advertised handles"
            in recent[0]["suggested_action"]
        )
        assert "attach_existing_child_run" not in recent[0]["suggested_action"]


# ─── Phase A item 5 (Task #76a) — invoke_branch_version_spec validation ──────


class TestValidateInvokeBranchVersionSpec:
    """Schema-layer validation of the new sibling spec."""

    def test_missing_branch_version_id_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={"wait_mode": "blocking"},
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("branch_version_id" in e for e in errs)

    def test_invalid_wait_mode_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "b1@abc12345",
                "wait_mode": "fire_and_forget",
            },
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("wait_mode" in e for e in errs)

    def test_invalid_on_child_fail_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "b1@abc12345",
                "on_child_fail": "ignore",  # not in {propagate, default, retry}
            },
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("on_child_fail" in e for e in errs)

    def test_valid_spec_no_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "b1@abc12345",
                "inputs_mapping": {},
                "output_mapping": {},
                "wait_mode": "blocking",
                "on_child_fail": "propagate",
            },
        )
        b = _simple_branch(nd)
        errs = [
            e for e in b.validate()
            if "invoke_branch_version_spec" in e
            or "branch_version_id" in e
            or "on_child_fail" in e
        ]
        assert not errs

    def test_invoke_version_plus_invoke_def_is_error(self):
        """Mutex with the existing invoke_branch_spec — only one or the other."""
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child", "wait_mode": "blocking",
            },
            invoke_branch_version_spec={
                "branch_version_id": "b1@abc12345",
            },
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any(
            "invoke_branch_version_spec" in e and "invoke_branch_spec" in e
            for e in errs
        )

    def test_invoke_version_plus_template_is_error(self):
        """Mutex with prompt_template (matches invoke_branch_spec rule)."""
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            prompt_template="hello",
            invoke_branch_version_spec={
                "branch_version_id": "b1@abc12345",
            },
        )
        b = _simple_branch(nd)
        errs = b.validate()
        assert any("mutually exclusive" in e for e in errs)


def _authorized_version_child_fixture(self):
    """Default: the version resolves to a PUBLIC child (so invoke_branch
    sanitization's authorize-before-snapshot passes). Tests exercising other
    behavior (mapping/policy/retry) inherit this; auth-specific tests override it."""
    from unittest.mock import patch
    raw = {"branch_def_id": "child", "name": "c", "visibility": "public",
           "node_defs": [], "edges": []}
    with (
        patch("tinyassets.branch_versions.branch_version_def_id", return_value="child"),
        patch("tinyassets.daemon_server.get_branch_definition", return_value=raw),
    ):
        yield


class TestCompileInvokeBranchVersionNode:
    """Compiler-level wiring for the new sibling builder."""

    _auth = pytest.fixture(autouse=True)(_authorized_version_child_fixture)

    def test_compile_succeeds_with_valid_version_spec(self, tmp_path):
        from tinyassets.graph_compiler import compile_branch

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "inputs_mapping": {},
                "output_mapping": {},
            },
        )
        b = BranchDefinition(
            branch_def_id="b1", name="test", entry_point="n1",
            node_defs=[nd],
            graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
            edges=[EdgeDefinition(from_node="n1", to_node="END")],
            state_schema=[{"name": "result", "type": "str"}],
        )
        # Compilation must succeed (no live execution; no actual version lookup).
        compiled = compile_branch(b, base_path=tmp_path)
        assert compiled is not None

    def test_invoke_version_node_without_base_path_raises(self):
        from tinyassets.graph_compiler import compile_branch

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
            },
        )
        b = BranchDefinition(
            branch_def_id="b1", name="test", entry_point="n1",
            node_defs=[nd],
            graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
            edges=[EdgeDefinition(from_node="n1", to_node="END")],
        )
        with pytest.raises(CompilerError, match="base_path"):
            compile_branch(b)

    def test_build_invoke_version_node_blocking_mode(self, tmp_path):
        """Blocking mode loads the snapshot via execute_branch_version_async,
        polls for terminal status, then maps output to parent state."""
        from tinyassets.graph_compiler import _build_invoke_branch_version_node

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "inputs_mapping": {"parent_in": "child_in"},
                "output_mapping": {"parent_out": "child_out"},
            },
        )
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, execution_context=_DEFAULT_TEST_CTX)

        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec, \
             patch("tinyassets.runs.poll_child_run_status") as mock_poll:
            mock_exec.return_value = MagicMock(run_id="run-xyz")
            mock_poll.return_value = {
                "status": "completed",
                "output": {"child_out": "value-from-child"},
            }
            updates = node_fn({"parent_in": "value-from-parent"})

        assert updates == {"parent_out": "value-from-child"}
        mock_exec.assert_called_once()
        kwargs = mock_exec.call_args.kwargs
        assert kwargs["branch_version_id"] == "child@abc12345"
        assert kwargs["inputs"] == {"child_in": "value-from-parent"}
        assert kwargs["on_node_status"] is None

    def test_build_invoke_version_node_async_mode_writes_run_id(self, tmp_path):
        """Async mode writes the child run_id into the first output_mapping
        target and returns immediately (no polling)."""
        from tinyassets.graph_compiler import _build_invoke_branch_version_node

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "async",
                "inputs_mapping": {},
                "output_mapping": {"child_run_id": "ignored"},
            },
        )
        seen: list[tuple[str, str]] = []

        def on_node_status(node_id: str, status: str) -> None:
            seen.append((node_id, status))

        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None,
            execution_context=_DEFAULT_TEST_CTX,
            on_node_status=on_node_status)

        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec:
            mock_exec.return_value = MagicMock(run_id="async-run-xyz")
            updates = node_fn({})

        assert updates == {"child_run_id": "async-run-xyz"}
        mock_exec.assert_called_once()
        # The child MUST inherit the parent's per-node callback, or a nested
        # prompt runs its provider call unguarded. This assertion is the only
        # thing that fails when the launch drops it (Codex round 3 §a/§d).
        assert mock_exec.call_args.kwargs["on_node_status"] is on_node_status

    def test_build_invoke_version_node_recursion_cap(self, tmp_path):
        """Recursion-cap works through the version-spec path too."""
        from tinyassets.graph_compiler import _build_invoke_branch_version_node

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
            },
        )
        with pytest.raises(CompilerError, match="recursion depth cap"):
            _build_invoke_branch_version_node(
                nd, base_path=tmp_path, event_sink=None,
                depth=MAX_INVOKE_BRANCH_DEPTH, execution_context=_DEFAULT_TEST_CTX)


# ─── Phase A item 5 (Task #76b) — on_child_fail policy + retry + ChildFailure ─


class TestChildFailurePolicy:
    """Policy enforcement on non-completed child terminal status. Both
    invoke_branch_spec and invoke_branch_version_spec share the dispatch
    helper (`_dispatch_invoke_outcome`); tested via the version builder
    since it's the simpler mocking surface."""

    _auth = pytest.fixture(autouse=True)(_authorized_version_child_fixture)

    def test_propagate_default_raises_child_failed_error(self, tmp_path):
        from tinyassets.graph_compiler import (
            ChildFailedError,
            _build_invoke_branch_version_node,
        )

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"parent_out": "child_out"},
                # on_child_fail defaults to "propagate"
            },
        )
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, execution_context=_DEFAULT_TEST_CTX)

        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec, \
             patch("tinyassets.runs.poll_child_run_status") as mock_poll:
            mock_exec.return_value = MagicMock(run_id="run-fail")
            mock_poll.return_value = {"status": "failed", "output": {}}
            with pytest.raises(ChildFailedError) as exc_info:
                node_fn({})

        from tinyassets.runs import ChildFailure
        assert isinstance(exc_info.value.failure, ChildFailure)
        assert exc_info.value.failure.failure_class == "child_failed"
        assert exc_info.value.failure.run_id == "run-fail"
        assert exc_info.value.failure.child_status == "failed"

    def test_default_policy_substitutes_default_outputs(self, tmp_path):
        from tinyassets.graph_compiler import _build_invoke_branch_version_node

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"parent_out": "child_out"},
                "on_child_fail": "default",
                "default_outputs": {"parent_out": "fallback-value"},
            },
        )
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, execution_context=_DEFAULT_TEST_CTX)

        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec, \
             patch("tinyassets.runs.poll_child_run_status") as mock_poll:
            mock_exec.return_value = MagicMock(run_id="run-fail")
            mock_poll.return_value = {"status": "failed", "output": {}}
            updates = node_fn({})

        # Parent continues with the default value substituted into output_mapping.
        assert updates == {"parent_out": "fallback-value"}

    def test_default_policy_no_default_outputs_uses_none(self, tmp_path):
        from tinyassets.graph_compiler import _build_invoke_branch_version_node

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"parent_out": "child_out"},
                "on_child_fail": "default",
                # no default_outputs
            },
        )
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, execution_context=_DEFAULT_TEST_CTX)

        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec, \
             patch("tinyassets.runs.poll_child_run_status") as mock_poll:
            mock_exec.return_value = MagicMock(run_id="run-fail")
            mock_poll.return_value = {"status": "failed", "output": {}}
            updates = node_fn({})

        # No defaults declared → None for each declared output_mapping key.
        assert updates == {"parent_out": None}

    def test_retry_succeeds_within_budget(self, tmp_path, monkeypatch):
        """retry budget=2: first attempt fails, second succeeds → completed
        outputs returned, no propagate."""
        from tinyassets.graph_compiler import (
            _build_invoke_branch_version_node,
            _retry_budget_reset,
        )

        # Reset the threadlocal to ensure clean budget state.
        _retry_budget_reset()
        # Generous global cap to not interfere.
        monkeypatch.setenv("TINYASSETS_MAX_CHILD_RETRIES_TOTAL", "10")

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"parent_out": "child_out"},
                "on_child_fail": "retry",
                "retry_budget": 2,
            },
        )
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, execution_context=_DEFAULT_TEST_CTX)

        # First poll fails, second succeeds.
        poll_returns = [
            {"status": "failed", "output": {}},
            {"status": "completed", "output": {"child_out": "ok"}},
        ]
        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec, \
             patch("tinyassets.runs.poll_child_run_status") as mock_poll:
            mock_exec.return_value = MagicMock(run_id="run-attempt")
            mock_poll.side_effect = poll_returns
            updates = node_fn({})

        assert updates == {"parent_out": "ok"}
        # Confirm the helper actually retried (called twice).
        assert mock_exec.call_count == 2

    def test_retry_exhausted_falls_through_to_propagate(self, tmp_path, monkeypatch):
        """retry_budget=1: one retry, then exhausts → propagate raises."""
        from tinyassets.graph_compiler import (
            ChildFailedError,
            _build_invoke_branch_version_node,
            _retry_budget_reset,
        )
        _retry_budget_reset()
        monkeypatch.setenv("TINYASSETS_MAX_CHILD_RETRIES_TOTAL", "10")

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"parent_out": "child_out"},
                "on_child_fail": "retry",
                "retry_budget": 1,
            },
        )
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, execution_context=_DEFAULT_TEST_CTX)

        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec, \
             patch("tinyassets.runs.poll_child_run_status") as mock_poll:
            mock_exec.return_value = MagicMock(run_id="run-fail")
            mock_poll.return_value = {"status": "failed", "output": {}}
            with pytest.raises(ChildFailedError):
                node_fn({})

        # Initial attempt + retry_budget=1 retry = 2 attempts total.
        assert mock_exec.call_count == 2

    def test_global_cap_overrides_per_spec_budget(self, tmp_path, monkeypatch):
        """Per-spec retry_budget=10 + global cap=1 → only 1 retry across
        the parent run, then propagate."""
        from tinyassets.graph_compiler import (
            ChildFailedError,
            _build_invoke_branch_version_node,
            _retry_budget_reset,
        )
        _retry_budget_reset()
        monkeypatch.setenv("TINYASSETS_MAX_CHILD_RETRIES_TOTAL", "1")

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"parent_out": "child_out"},
                "on_child_fail": "retry",
                "retry_budget": 10,  # would allow 10 retries, but global cap=1
            },
        )
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, execution_context=_DEFAULT_TEST_CTX)

        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec, \
             patch("tinyassets.runs.poll_child_run_status") as mock_poll:
            mock_exec.return_value = MagicMock(run_id="run-fail")
            mock_poll.return_value = {"status": "failed", "output": {}}
            with pytest.raises(ChildFailedError):
                node_fn({})

        # Initial attempt + 1 retry (global cap) = 2 attempts.
        assert mock_exec.call_count == 2

    def test_failure_class_classification(self, tmp_path):
        """Each child terminal status maps to the correct failure_class."""
        from tinyassets.graph_compiler import (
            ChildFailedError,
            _build_invoke_branch_version_node,
        )

        for child_status, expected_class in (
            ("failed", "child_failed"),
            ("cancelled", "child_cancelled"),
            ("interrupted", "child_timeout"),
        ):
            nd = NodeDefinition(
                node_id="n1", display_name="N1",
                invoke_branch_version_spec={
                    "branch_version_id": "child@abc12345",
                    "wait_mode": "blocking",
                    "output_mapping": {"parent_out": "child_out"},
                },
            )
            node_fn = _build_invoke_branch_version_node(
                nd, base_path=tmp_path, event_sink=None, execution_context=_DEFAULT_TEST_CTX)
            with patch("tinyassets.runs.execute_branch_version_async") as m_exec, \
                 patch("tinyassets.runs.poll_child_run_status") as m_poll:
                m_exec.return_value = MagicMock(run_id="r")
                m_poll.return_value = {"status": child_status, "output": {}}
                with pytest.raises(ChildFailedError) as exc_info:
                    node_fn({})
            assert exc_info.value.failure.failure_class == expected_class, (
                f"child_status={child_status} → expected {expected_class}, "
                f"got {exc_info.value.failure.failure_class}"
            )


class TestOutputMappingSchemaValidation:
    """Audit gap #7 (Task #76b) — validate-time check that each
    output_mapping target is a parent state-schema field."""

    def test_invoke_branch_output_mapping_unknown_target_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "wait_mode": "blocking",
                "inputs_mapping": {},
                "output_mapping": {"unknown_field": "child_out"},
            },
        )
        b = BranchDefinition(
            branch_def_id="b1", name="t", entry_point="n1",
            node_defs=[nd],
            graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
            edges=[EdgeDefinition(from_node="n1", to_node="END")],
            state_schema=[{"name": "result", "type": "str"}],
        )
        errs = b.validate()
        assert any(
            "output_mapping target 'unknown_field'" in e for e in errs
        )

    def test_invoke_branch_version_output_mapping_unknown_target_is_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"missing_field": "child_out"},
            },
        )
        b = BranchDefinition(
            branch_def_id="b1", name="t", entry_point="n1",
            node_defs=[nd],
            graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
            edges=[EdgeDefinition(from_node="n1", to_node="END")],
            state_schema=[{"name": "result", "type": "str"}],
        )
        errs = b.validate()
        assert any(
            "output_mapping target 'missing_field'" in e for e in errs
        )

    def test_valid_output_mapping_target_no_error(self):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"result": "child_out"},
            },
        )
        b = BranchDefinition(
            branch_def_id="b1", name="t", entry_point="n1",
            node_defs=[nd],
            graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
            edges=[EdgeDefinition(from_node="n1", to_node="END")],
            state_schema=[{"name": "result", "type": "str"}],
        )
        errs = [e for e in b.validate() if "output_mapping" in e]
        assert errs == []

    def test_empty_state_schema_skips_check(self):
        """Branches without declared state_schema get warn-only — no error."""
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345",
                "wait_mode": "blocking",
                "output_mapping": {"any_field": "child_out"},
            },
        )
        b = BranchDefinition(
            branch_def_id="b1", name="t", entry_point="n1",
            node_defs=[nd],
            graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
            edges=[EdgeDefinition(from_node="n1", to_node="END")],
            # No state_schema declared.
        )
        errs = [e for e in b.validate() if "output_mapping" in e]
        assert errs == []


# ─── Phase A item 5 / Task #76c — two-pool + child_actor + design_used ─────


class TestInvokeBranchExecutionContext:
    """invoke_branch sanitization (2026-08-23): the child runs under the IMMUTABLE
    BranchExecutionContext -- as ctx.actor (never a spec child_actor, never anonymous),
    and the author-chosen child ref is authorized by DELEGATED authority (own ->
    own/public; public-foreign -> public only)."""

    @staticmethod
    def _ctx(actor="alice", provenance="own"):
        from tinyassets.graph_compiler import BranchExecutionContext
        return BranchExecutionContext(
            actor=actor, universe_id="u", caller_provenance=provenance
        )

    @staticmethod
    def _child_raw(visibility="public", author=""):
        raw = {"branch_def_id": "child", "name": "c", "visibility": visibility,
               "node_defs": [], "edges": []}
        if author:
            raw["author"] = author
        return raw

    def test_child_runs_as_context_actor_ignoring_spec_child_actor(self, tmp_path):
        from tinyassets.runs import RUN_STATUS_COMPLETED, RunOutcome

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child", "inputs_mapping": {},
                "output_mapping": {"result": "answer"}, "wait_mode": "blocking",
                "child_actor": "mallory",  # spoof attempt -- must be IGNORED
            },
        )
        child_outcome = RunOutcome(run_id="r1", status=RUN_STATUS_COMPLETED,
                                   output={"answer": "ok"}, error="")
        child_mock = MagicMock()
        child_mock.validate.return_value = []
        with (
            patch("tinyassets.daemon_server.get_branch_definition",
                  return_value=self._child_raw()),
            patch("tinyassets.branches.BranchDefinition.from_dict",
                  return_value=child_mock),
            patch("tinyassets.runs.execute_branch",
                  return_value=child_outcome) as mock_exec,
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                execution_context=self._ctx(actor="alice"),
            )
            fn({})
        assert mock_exec.call_args.kwargs["actor"] == "alice"  # ctx, not "mallory"

    def test_no_execution_context_fails_closed(self, tmp_path):
        from tinyassets.graph_compiler import CompilerError

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child", "inputs_mapping": {},
                "output_mapping": {"result": "answer"}, "wait_mode": "blocking",
            },
        )
        child_mock = MagicMock()
        child_mock.validate.return_value = []
        with (
            patch("tinyassets.daemon_server.get_branch_definition",
                  return_value=self._child_raw()),
            patch("tinyassets.branches.BranchDefinition.from_dict",
                  return_value=child_mock),
            patch("tinyassets.runs.execute_branch") as mock_exec,
        ):
            fn = _build_invoke_branch_node(nd, base_path=tmp_path, event_sink=None)
            with pytest.raises(CompilerError):
                fn({})
        assert mock_exec.call_count == 0

    def test_own_provenance_may_invoke_own_private_child(self, tmp_path):
        from tinyassets.runs import RUN_STATUS_COMPLETED, RunOutcome

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child", "inputs_mapping": {},
                "output_mapping": {"result": "answer"}, "wait_mode": "blocking",
            },
        )
        child_outcome = RunOutcome(run_id="r1", status=RUN_STATUS_COMPLETED,
                                   output={"answer": "ok"}, error="")
        child_mock = MagicMock()
        child_mock.validate.return_value = []
        child_mock.author = "alice"  # own-authored private child
        with (
            patch("tinyassets.daemon_server.get_branch_definition",
                  return_value=self._child_raw(visibility="private", author="alice")),
            patch("tinyassets.branches.BranchDefinition.from_dict",
                  return_value=child_mock),
            patch("tinyassets.runs.execute_branch",
                  return_value=child_outcome) as mock_exec,
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                execution_context=self._ctx(actor="alice", provenance="own"),
            )
            fn({})
        assert mock_exec.call_args.kwargs["actor"] == "alice"

    def test_foreign_provenance_refused_private_child(self, tmp_path):
        from tinyassets.graph_compiler import CompilerError

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "victim-private", "inputs_mapping": {},
                "output_mapping": {"result": "answer"}, "wait_mode": "blocking",
            },
        )
        child_mock = MagicMock()
        child_mock.validate.return_value = []
        child_mock.author = "victim"
        with (
            patch("tinyassets.daemon_server.get_branch_definition",
                  return_value=self._child_raw(visibility="private")),
            patch("tinyassets.branches.BranchDefinition.from_dict",
                  return_value=child_mock),
            patch("tinyassets.runs.execute_branch") as mock_exec,
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                execution_context=self._ctx(actor="victim", provenance="public-foreign"),
            )
            with pytest.raises(CompilerError):
                fn({})
        assert mock_exec.call_count == 0

    def test_foreign_provenance_may_invoke_public_child(self, tmp_path):
        from tinyassets.runs import RUN_STATUS_COMPLETED, RunOutcome

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child", "inputs_mapping": {},
                "output_mapping": {"result": "answer"}, "wait_mode": "blocking",
            },
        )
        child_outcome = RunOutcome(run_id="r1", status=RUN_STATUS_COMPLETED,
                                   output={"answer": "ok"}, error="")
        child_mock = MagicMock()
        child_mock.validate.return_value = []
        with (
            patch("tinyassets.daemon_server.get_branch_definition",
                  return_value=self._child_raw(visibility="public")),
            patch("tinyassets.branches.BranchDefinition.from_dict",
                  return_value=child_mock),
            patch("tinyassets.runs.execute_branch",
                  return_value=child_outcome) as mock_exec,
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                execution_context=self._ctx(actor="bob", provenance="public-foreign"),
            )
            fn({})
        assert mock_exec.call_args.kwargs["actor"] == "bob"

    def test_async_still_threads_depth_under_context(self, tmp_path):
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child", "inputs_mapping": {},
                "output_mapping": {"child_run_id": "ignored"}, "wait_mode": "async",
                "child_actor": "spoof",
            },
        )
        child_mock = MagicMock()
        child_mock.validate.return_value = []
        with (
            patch("tinyassets.daemon_server.get_branch_definition",
                  return_value=self._child_raw()),
            patch("tinyassets.branches.BranchDefinition.from_dict",
                  return_value=child_mock),
            patch("tinyassets.runs.execute_branch_async") as mock_async,
        ):
            mock_async.return_value = MagicMock(run_id="async-r1")
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None, depth=2,
                execution_context=self._ctx(actor="alice"),
            )
            fn({})
        kwargs = mock_async.call_args.kwargs
        assert kwargs["actor"] == "alice"  # ctx, not "spoof"
        assert kwargs["_invocation_depth"] == 3

    def test_version_authorizes_before_snapshot_and_runs_as_context_actor(self, tmp_path):
        from tinyassets.graph_compiler import _build_invoke_branch_version_node

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "child@abc12345", "wait_mode": "blocking",
                "inputs_mapping": {}, "output_mapping": {"parent_out": "child_out"},
                "child_actor": "carol",  # ignored
            },
        )
        child_mock = MagicMock()
        child_mock.validate.return_value = []
        child_mock.branch_def_id = "child"
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, depth=1,
            execution_context=self._ctx(actor="alice"),
        )
        with (
            patch("tinyassets.branch_versions.branch_version_def_id",
                  return_value="child"),
            patch("tinyassets.daemon_server.get_branch_definition",
                  return_value=self._child_raw()),
            patch("tinyassets.branches.BranchDefinition.from_dict",
                  return_value=child_mock),
            patch("tinyassets.runs.execute_branch_version_async") as mock_exec,
            patch("tinyassets.runs.poll_child_run_status") as mock_poll,
        ):
            mock_exec.return_value = MagicMock(run_id="r-x")
            mock_poll.return_value = {"status": "completed", "output": {"child_out": "v"}}
            node_fn({})
        kwargs = mock_exec.call_args.kwargs
        assert kwargs["actor"] == "alice"  # ctx, not "carol"
        assert kwargs["_invocation_depth"] == 2

    def test_version_foreign_private_refused_before_snapshot(self, tmp_path):
        from tinyassets.graph_compiler import (
            CompilerError,
            _build_invoke_branch_version_node,
        )

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_version_spec={
                "branch_version_id": "victim@abc12345", "wait_mode": "blocking",
                "inputs_mapping": {}, "output_mapping": {"parent_out": "child_out"},
            },
        )
        child_mock = MagicMock()
        child_mock.validate.return_value = []
        child_mock.author = "victim"
        child_mock.branch_def_id = "victim"
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None, depth=1,
            execution_context=self._ctx(actor="victim", provenance="public-foreign"),
        )
        with (
            patch("tinyassets.branch_versions.branch_version_def_id",
                  return_value="victim"),
            patch("tinyassets.daemon_server.get_branch_definition",
                  return_value=self._child_raw(visibility="private")),
            patch("tinyassets.branches.BranchDefinition.from_dict",
                  return_value=child_mock),
            patch("tinyassets.runs.execute_branch_version_async") as mock_exec,
            patch("tinyassets.runs.poll_child_run_status"),
        ):
            mock_exec.return_value = MagicMock(run_id="r-x")
            with pytest.raises(CompilerError):
                node_fn({})
        assert mock_exec.call_count == 0  # authorized BEFORE snapshot load


class TestInvokeBranchMappingConfidentiality:
    """Task 4.1 — a FOREIGN-provenance invoke edge must not plumb a
    credential/secret/auth-state field into a child's inputs or harvest one out of
    its output; own-provenance edges (the runner's own shapes) stay unrestricted."""

    @staticmethod
    def _ctx(provenance="public-foreign"):
        from tinyassets.graph_compiler import BranchExecutionContext
        return BranchExecutionContext(
            actor="alice", universe_id="u", caller_provenance=provenance
        )

    def test_foreign_inputs_mapping_secret_key_refused_at_compile(self, tmp_path):
        from tinyassets.graph_compiler import CompilerError
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {"parent_q": "api_key"},  # secret-named child input
                "output_mapping": {}, "wait_mode": "blocking",
            },
        )
        with pytest.raises(CompilerError, match="credential/secret"):
            _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                execution_context=self._ctx("public-foreign"),
            )

    def test_foreign_output_mapping_secret_key_refused_at_compile(self, tmp_path):
        from tinyassets.graph_compiler import CompilerError
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child", "inputs_mapping": {},
                "output_mapping": {"refresh_token": "answer"},  # secret-named parent key
                "wait_mode": "blocking",
            },
        )
        with pytest.raises(CompilerError, match="credential/secret"):
            _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                execution_context=self._ctx("public-foreign"),
            )

    def test_own_provenance_secret_mapping_allowed(self, tmp_path):
        # Differential: the SAME secret-named mapping under OWN provenance compiles
        # (a universe plumbing its own fields between its own sub-branches).
        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {"parent_q": "api_key"},
                "output_mapping": {"refresh_token": "answer"},
                "wait_mode": "blocking",
            },
        )
        fn = _build_invoke_branch_node(
            nd, base_path=tmp_path, event_sink=None,
            execution_context=self._ctx("own"),
        )
        assert callable(fn)


class TestAwaitRunActorUniverseBinding:
    """Task 4.2 — await_branch_run binds the polled run to the execution
    context's actor + universe; a foreign run id planted in state is refused."""

    def _await_node(self):
        return NodeDefinition(
            node_id="n1", display_name="N1",
            await_run_spec={"run_id_field": "child_run_id",
                            "output_mapping": {"result": "answer"}},
        )

    def test_foreign_actor_run_refused(self, tmp_path):
        from tinyassets.graph_compiler import (
            BranchExecutionContext,
            _build_await_branch_run_node,
        )
        foreign = {"run_id": "r-foreign", "status": "completed",
                   "output": {"answer": "secret"}, "actor": "mallory",
                   "queue_universe_id": "u"}
        with patch("tinyassets.runs.get_run", return_value=foreign):
            fn = _build_await_branch_run_node(
                self._await_node(), base_path=tmp_path, event_sink=None,
                execution_context=BranchExecutionContext(
                    actor="alice", universe_id="u", caller_provenance="own"),
            )
            with pytest.raises(KeyError):
                fn({"child_run_id": "r-foreign"})

    def test_foreign_universe_run_refused(self, tmp_path):
        from tinyassets.graph_compiler import (
            BranchExecutionContext,
            _build_await_branch_run_node,
        )
        foreign = {"run_id": "r-x", "status": "completed",
                   "output": {"answer": "secret"}, "actor": "alice",
                   "queue_universe_id": "other-universe"}
        with patch("tinyassets.runs.get_run", return_value=foreign):
            fn = _build_await_branch_run_node(
                self._await_node(), base_path=tmp_path, event_sink=None,
                execution_context=BranchExecutionContext(
                    actor="alice", universe_id="u", caller_provenance="own"),
            )
            with pytest.raises(KeyError):
                fn({"child_run_id": "r-x"})

    def test_own_actor_universe_run_allowed(self, tmp_path):
        from tinyassets.graph_compiler import (
            BranchExecutionContext,
            _build_await_branch_run_node,
        )
        owned = {"run_id": "r-own", "status": "completed",
                 "output": {"answer": "42"}, "actor": "alice",
                 "queue_universe_id": "u"}
        with patch("tinyassets.runs.get_run", return_value=owned):
            fn = _build_await_branch_run_node(
                self._await_node(), base_path=tmp_path, event_sink=None,
                execution_context=BranchExecutionContext(
                    actor="alice", universe_id="u", caller_provenance="own"),
            )
            assert fn({"child_run_id": "r-own"}) == {"result": "42"}


class TestTwoPoolIsolation:
    """Phase A item 5 / Task #76c — top-level runs (depth=0) and
    sub-branch runs (depth>=1) route to separate ThreadPoolExecutors so
    deep chains can't starve the parent pool.
    """

    def test_get_executor_returns_distinct_pools_per_depth(self):
        from tinyassets.runs import _get_executor, shutdown_executor

        # Reset global pool state so the assertion holds independent of
        # earlier tests in this session.
        shutdown_executor()
        parent = _get_executor(invocation_depth=0)
        child1 = _get_executor(invocation_depth=1)
        child2 = _get_executor(invocation_depth=3)

        assert parent is not child1
        assert child1 is child2  # all depth>=1 share child_pool
        shutdown_executor()

    def test_shutdown_executor_drains_both_pools(self):
        import tinyassets.runs as _runs_mod
        from tinyassets.runs import (
            _get_executor,
            shutdown_executor,
        )

        # Force both pools to exist.
        _get_executor(invocation_depth=0)
        _get_executor(invocation_depth=1)
        assert _runs_mod._parent_pool is not None
        assert _runs_mod._child_pool is not None

        shutdown_executor()
        assert _runs_mod._parent_pool is None
        assert _runs_mod._child_pool is None

    def test_runtime_max_invocation_depth_env_override(self, monkeypatch):
        from tinyassets.runs import _runtime_max_invocation_depth

        monkeypatch.setenv("TINYASSETS_INVOCATION_MAX_DEPTH", "9")
        assert _runtime_max_invocation_depth() == 9

        monkeypatch.delenv("TINYASSETS_INVOCATION_MAX_DEPTH", raising=False)
        # Default should be MAX_INVOKE_BRANCH_DEPTH (5).
        assert _runtime_max_invocation_depth() == MAX_INVOKE_BRANCH_DEPTH

    def test_runtime_depth_cap_used_in_compile(self, tmp_path, monkeypatch):
        """Compile-time cap reads runtime helper, so env override
        flips the cap without a code-change."""
        monkeypatch.setenv("TINYASSETS_INVOCATION_MAX_DEPTH", "2")

        nd = NodeDefinition(
            node_id="n1", display_name="N1",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {},
                "output_mapping": {},
                "wait_mode": "blocking",
            },
        )
        # depth=2 with cap=2 should raise.
        with pytest.raises(CompilerError, match="recursion depth cap"):
            _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None, depth=2,
                execution_context=_DEFAULT_TEST_CTX,
            )
        # depth=1 with cap=2 should NOT raise.
        _build_invoke_branch_node(
            nd, base_path=tmp_path, event_sink=None, depth=1, execution_context=_DEFAULT_TEST_CTX)


class TestInvokeBranchDesignUsedEmit:
    """Phase A item 5 / Task #76c — successful blocking invocation emits
    a ``design_used`` contribution event crediting the child branch_def's
    author. Skipped on empty/anonymous author. Only fires on success."""

    def _seed_child_def(self, base_path, *, author="alice"):
        from tinyassets.daemon_server import (
            initialize_author_server,
            save_branch_definition,
        )
        initialize_author_server(base_path)
        save_branch_definition(
            base_path,
            branch_def={
                "branch_def_id": "child",
                "name": "child",
                "author": author,
                "node_defs": [],
                "edges": [],
                "graph_nodes": [],
                "entry_point": "",
            },
        )

    def test_emits_design_used_on_blocking_success(self, tmp_path):
        from tinyassets.contribution_events import (
            _connect as ce_connect,
        )
        from tinyassets.contribution_events import (
            initialize_contribution_events_db,
        )
        from tinyassets.runs import RUN_STATUS_COMPLETED, RunOutcome

        initialize_contribution_events_db(tmp_path)
        self._seed_child_def(tmp_path, author="alice")

        nd = NodeDefinition(
            node_id="n_invoke", display_name="X",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {},
                "output_mapping": {"result": "answer"},
                "wait_mode": "blocking",
            },
        )
        child_outcome = RunOutcome(
            run_id="cr1", status=RUN_STATUS_COMPLETED,
            output={"answer": "v"}, error="",
        )
        child_branch_mock = MagicMock()
        child_branch_mock.validate.return_value = []

        with (
            patch("tinyassets.branches.BranchDefinition.from_dict", return_value=child_branch_mock),
            patch("tinyassets.runs.execute_branch", return_value=child_outcome),
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                parent_run_id="parent-run-1", execution_context=_DEFAULT_TEST_CTX)
            fn({})

        with ce_connect(tmp_path) as conn:
            rows = conn.execute(
                "SELECT * FROM contribution_events "
                "WHERE event_type = ?",
                ("design_used",),
            ).fetchall()
        assert len(rows) == 1
        ev = rows[0]
        assert ev["actor_id"] == "alice"
        assert ev["source_run_id"] == "parent-run-1"
        assert ev["source_artifact_kind"] == "branch_def"
        assert ev["source_artifact_id"] == "child"

    def test_skips_emit_when_author_anonymous(self, tmp_path):
        from tinyassets.contribution_events import (
            _connect as ce_connect,
        )
        from tinyassets.contribution_events import (
            initialize_contribution_events_db,
        )
        from tinyassets.runs import RUN_STATUS_COMPLETED, RunOutcome

        initialize_contribution_events_db(tmp_path)
        self._seed_child_def(tmp_path, author="anonymous")

        nd = NodeDefinition(
            node_id="n_invoke", display_name="X",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {},
                "output_mapping": {"result": "answer"},
                "wait_mode": "blocking",
            },
        )
        child_outcome = RunOutcome(
            run_id="cr1", status=RUN_STATUS_COMPLETED,
            output={"answer": "v"}, error="",
        )
        child_branch_mock = MagicMock()
        child_branch_mock.validate.return_value = []
        with (
            patch("tinyassets.branches.BranchDefinition.from_dict", return_value=child_branch_mock),
            patch("tinyassets.runs.execute_branch", return_value=child_outcome),
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                parent_run_id="parent-run-1", execution_context=_DEFAULT_TEST_CTX)
            fn({})

        with ce_connect(tmp_path) as conn:
            rows = conn.execute(
                "SELECT * FROM contribution_events WHERE event_type = ?",
                ("design_used",),
            ).fetchall()
        assert rows == []

    def test_no_emit_on_child_failure(self, tmp_path):
        from tinyassets.contribution_events import (
            _connect as ce_connect,
        )
        from tinyassets.contribution_events import (
            initialize_contribution_events_db,
        )
        from tinyassets.runs import RunOutcome

        initialize_contribution_events_db(tmp_path)
        self._seed_child_def(tmp_path, author="alice")

        nd = NodeDefinition(
            node_id="n_invoke", display_name="X",
            invoke_branch_spec={
                "branch_def_id": "child",
                "inputs_mapping": {},
                "output_mapping": {"result": "answer"},
                "wait_mode": "blocking",
                "on_child_fail": "default",
                "default_outputs": {"result": "fallback"},
            },
        )
        child_outcome = RunOutcome(
            run_id="cr1", status="failed",
            output={}, error="boom",
        )
        child_branch_mock = MagicMock()
        child_branch_mock.validate.return_value = []
        with (
            patch("tinyassets.branches.BranchDefinition.from_dict", return_value=child_branch_mock),
            patch("tinyassets.runs.execute_branch", return_value=child_outcome),
        ):
            fn = _build_invoke_branch_node(
                nd, base_path=tmp_path, event_sink=None,
                parent_run_id="parent-run-1", execution_context=_DEFAULT_TEST_CTX)
            fn({})  # default policy → returns fallback updates, no raise

        with ce_connect(tmp_path) as conn:
            rows = conn.execute(
                "SELECT * FROM contribution_events WHERE event_type = ?",
                ("design_used",),
            ).fetchall()
        assert rows == []


class TestInvokeBranchVersionDesignUsedEmit:
    """invoke_branch_version_spec emits design_used keyed by the resolved
    branch_def_id (since branch_version snapshot is topology-only)."""

    def test_emits_design_used_for_version_blocking_success(self, tmp_path):
        from tinyassets.branch_versions import (
            initialize_branch_versions_db,
            publish_branch_version,
        )
        from tinyassets.contribution_events import (
            _connect as ce_connect,
        )
        from tinyassets.contribution_events import (
            initialize_contribution_events_db,
        )
        from tinyassets.daemon_server import (
            initialize_author_server,
            save_branch_definition,
        )
        from tinyassets.graph_compiler import _build_invoke_branch_version_node

        initialize_contribution_events_db(tmp_path)
        initialize_author_server(tmp_path)
        initialize_branch_versions_db(tmp_path)

        # Live def with a non-anonymous author.
        save_branch_definition(
            tmp_path,
            branch_def={
                "branch_def_id": "child",
                "name": "child",
                "author": "dave",
                "node_defs": [],
                "edges": [],
                "graph_nodes": [],
                "entry_point": "",
            },
        )
        # Publish a version of it.
        record = publish_branch_version(
            tmp_path,
            branch_dict={
                "branch_def_id": "child",
                "name": "child",
                "node_defs": [],
                "edges": [],
            },
        )
        bvid = record.branch_version_id

        nd = NodeDefinition(
            node_id="n_invoke", display_name="X",
            invoke_branch_version_spec={
                "branch_version_id": bvid,
                "inputs_mapping": {},
                "output_mapping": {"parent_out": "child_out"},
                "wait_mode": "blocking",
            },
        )
        node_fn = _build_invoke_branch_version_node(
            nd, base_path=tmp_path, event_sink=None,
            parent_run_id="parent-run-7", execution_context=_DEFAULT_TEST_CTX)

        with patch("tinyassets.runs.execute_branch_version_async") as mock_exec, \
             patch("tinyassets.runs.poll_child_run_status") as mock_poll:
            mock_exec.return_value = MagicMock(run_id="r-x")
            mock_poll.return_value = {
                "status": "completed",
                "output": {"child_out": "v"},
            }
            node_fn({})

        with ce_connect(tmp_path) as conn:
            rows = conn.execute(
                "SELECT * FROM contribution_events WHERE event_type = ?",
                ("design_used",),
            ).fetchall()
        assert len(rows) == 1
        ev = rows[0]
        assert ev["actor_id"] == "dave"
        assert ev["source_run_id"] == "parent-run-7"
        assert ev["source_artifact_kind"] == "branch_version"
        assert ev["source_artifact_id"] == bvid
