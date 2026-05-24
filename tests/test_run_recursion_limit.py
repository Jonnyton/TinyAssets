"""recursion_limit_override exposure (Tier-1 Step 6).

Guards that the default LangGraph recursion limit is raised from 25 to
100 AND that callers can override via ``recursion_limit_override``.
"""
from __future__ import annotations

import inspect

from workflow import runs


class TestDefaultBumped:
    def test_default_recursion_limit_is_100(self):
        assert runs.DEFAULT_RECURSION_LIMIT == 100

    def test_default_is_above_langgraph_stock_25(self):
        assert runs.DEFAULT_RECURSION_LIMIT > 25


class TestExecuteBranchSignature:
    def test_execute_branch_accepts_recursion_limit_override(self):
        sig = inspect.signature(runs.execute_branch)
        assert "recursion_limit_override" in sig.parameters
        param = sig.parameters["recursion_limit_override"]
        assert param.default is None  # optional, defaults to stock default

    def test_execute_branch_async_accepts_recursion_limit_override(self):
        sig = inspect.signature(runs.execute_branch_async)
        assert "recursion_limit_override" in sig.parameters
        param = sig.parameters["recursion_limit_override"]
        assert param.default is None

    def test_invoke_graph_accepts_recursion_limit(self):
        sig = inspect.signature(runs._invoke_graph)
        assert "recursion_limit" in sig.parameters
        param = sig.parameters["recursion_limit"]
        assert param.default == runs.DEFAULT_RECURSION_LIMIT


class TestOverrideThreading:
    """The override value must flow into the app.invoke config. We patch
    compile_branch so we don't need a real provider/checkpointer; the
    test asserts the threading is correct by spying on the config.
    """

    def test_override_flows_through_to_invoke_config(self, monkeypatch, tmp_path):
        captured_configs: list[dict] = []

        class _FakeApp:
            def invoke(self, state, config):
                captured_configs.append(config)
                return state

        class _FakeCompiledGraph:
            def compile(self, checkpointer):
                return _FakeApp()

        class _FakeCompiled:
            graph = _FakeCompiledGraph()
            concurrency_tracker = None

        monkeypatch.setattr(runs, "compile_branch", lambda *a, **k: _FakeCompiled())

        # Stub the saver context manager to a trivial no-op.
        class _FakeSaver:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            @staticmethod
            def from_conn_string(_path):
                return _FakeSaver()

        import langgraph.checkpoint.sqlite as saver_mod
        monkeypatch.setattr(saver_mod, "SqliteSaver", _FakeSaver)

        # Stub status updates + event sinks — we only care about config.
        monkeypatch.setattr(runs, "update_run_status", lambda *a, **k: None)
        monkeypatch.setattr(runs, "is_cancel_requested", lambda *a, **k: False)
        monkeypatch.setattr(runs, "record_event", lambda *a, **k: None)

        # Minimal branch stub — compile_branch is patched, so shape doesn't
        # actually matter. Just needs to not blow up during attribute access.
        class _StubBranch:
            branch_def_id = "x"
            node_defs = []
            graph_nodes = []

        runs._invoke_graph(
            tmp_path,
            run_id="test-run",
            branch=_StubBranch(),
            inputs={"a": 1},
            provider_call=None,
            recursion_limit=250,
        )

        assert captured_configs, "app.invoke was not called"
        cfg = captured_configs[0]
        assert cfg["recursion_limit"] == 250
        assert cfg["configurable"]["thread_id"] == "test-run"


class TestRecursionLimitAppliedEvent:
    """recursion_limit_applied event is emitted at step_index=0."""

    def _make_stubs(self, monkeypatch):
        class _FakeApp:
            def invoke(self, state, config):
                return state

        class _FakeCompiledGraph:
            def compile(self, checkpointer):
                return _FakeApp()

        class _FakeCompiled:
            graph = _FakeCompiledGraph()
            concurrency_tracker = None

        class _FakeSaver:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            @staticmethod
            def from_conn_string(_path):
                return _FakeSaver()

        monkeypatch.setattr(runs, "compile_branch", lambda *a, **k: _FakeCompiled())
        import langgraph.checkpoint.sqlite as saver_mod
        monkeypatch.setattr(saver_mod, "SqliteSaver", _FakeSaver)
        monkeypatch.setattr(runs, "update_run_status", lambda *a, **k: None)
        monkeypatch.setattr(runs, "is_cancel_requested", lambda *a, **k: False)

        class _StubBranch:
            branch_def_id = "x"
            node_defs = []
            graph_nodes = []
        return _StubBranch()

    def test_recursion_limit_applied_event_emitted(self, monkeypatch, tmp_path):
        recorded_events = []
        monkeypatch.setattr(
            runs, "record_event",
            lambda _base, ev: recorded_events.append(ev),
        )
        stub = self._make_stubs(monkeypatch)

        runs._invoke_graph(
            tmp_path,
            run_id="test-run",
            branch=stub,
            inputs={},
            provider_call=None,
            recursion_limit=42,
        )

        system_events = [
            e for e in recorded_events
            if getattr(e, "node_id", None) == "__system__"
            and getattr(e, "status", None) == "recursion_limit_applied"
        ]
        assert system_events, "recursion_limit_applied event not emitted"
        ev = system_events[0]
        assert ev.detail.get("recursion_limit") == 42


class TestMcpRecursionLimitOverride:
    """_action_run_branch MCP handler validates recursion_limit_override."""

    def test_unset_uses_default(self, tmp_path, monkeypatch):
        from workflow.api.runs import _action_run_branch

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        # No branch → quick error return before recursion_limit check
        import json
        result = json.loads(_action_run_branch({
            "branch_def_id": "", "recursion_limit_override": "",
        }))
        assert "error" in result  # missing branch_def_id error

    def test_valid_override_50_accepted(self, tmp_path, monkeypatch):
        import json

        from workflow.api.runs import _action_run_branch
        from workflow.runs import RUN_STATUS_QUEUED, RunOutcome

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        monkeypatch.setattr(
            "workflow.api.branches._resolve_branch_id",
            lambda branch_def_id, _base_path: branch_def_id,
        )
        captured: dict[str, object] = {}

        def _fake_execute_branch_async(*args, **kwargs):
            captured.update(kwargs)
            return RunOutcome(run_id="run-1", status=RUN_STATUS_QUEUED, output={})

        monkeypatch.setattr(
            "workflow.runs.execute_branch_async",
            _fake_execute_branch_async,
        )

        result = json.loads(_action_run_branch({
            "branch_def_id": "b1",
            "recursion_limit_override": "50",
        }))

        assert result["run_id"] == "run-1"
        assert captured["recursion_limit_override"] == 50

    def _stub_valid_branch(self, monkeypatch):
        from unittest.mock import MagicMock

        dummy_src = {"branch_def_id": "b1", "name": "test", "node_defs": [], "edges": []}
        stub_branch = MagicMock()
        stub_branch.validate.return_value = []  # no errors
        monkeypatch.setattr(
            "workflow.daemon_server.get_branch_definition",
            lambda *a, **k: dummy_src,
        )
        monkeypatch.setattr(
            "workflow.branches.BranchDefinition.from_dict",
            staticmethod(lambda _: stub_branch),
        )
        return stub_branch

    def test_override_below_min_rejected(self, tmp_path, monkeypatch):
        import json

        from workflow.api.runs import _action_run_branch

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        result = json.loads(_action_run_branch({
            "branch_def_id": "b1",
            "recursion_limit_override": "5",
        }))
        assert "error" in result
        assert "out of range" in result["error"] or "10" in result["error"]

    def test_override_above_max_rejected(self, tmp_path, monkeypatch):
        import json

        from workflow.api.runs import _action_run_branch

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        result = json.loads(_action_run_branch({
            "branch_def_id": "b1",
            "recursion_limit_override": "2000",
        }))
        assert "error" in result
        assert "out of range" in result["error"] or "1000" in result["error"]

    def test_override_not_integer_rejected(self, tmp_path, monkeypatch):
        import json

        from workflow.api.runs import _action_run_branch

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        result = json.loads(_action_run_branch({
            "branch_def_id": "b1",
            "recursion_limit_override": "not-a-number",
        }))
        assert "error" in result


class TestGetRunRecursionLimit:
    """get_run snapshot includes recursion_limit from events."""

    def test_recursion_limit_in_snapshot_when_event_present(self):
        from workflow.api.runs import _compose_run_snapshot

        dummy_record = {
            "run_id": "r1",
            "branch_def_id": "b1",
            "status": "completed",
            "actor": "alice",
            "last_node_id": "",
            "started_at": 0.0,
            "finished_at": 1.0,
            "error": "",
        }
        events = [
            {
                "run_id": "r1",
                "step_index": 0,
                "node_id": "__system__",
                "status": "recursion_limit_applied",
                "started_at": 0.0,
                "finished_at": None,
                "detail": {"recursion_limit": 75},
            }
        ]
        from unittest.mock import patch
        with patch("workflow.daemon_server.get_branch_definition", side_effect=KeyError("b1")):
            snapshot = _compose_run_snapshot(dummy_record, events)
        assert snapshot["recursion_limit"] == 75

    def test_recursion_limit_none_when_no_system_event(self):
        from workflow.api.runs import _compose_run_snapshot

        dummy_record = {
            "run_id": "r1",
            "branch_def_id": "b1",
            "status": "completed",
            "actor": "alice",
            "last_node_id": "",
            "started_at": 0.0,
            "finished_at": 1.0,
            "error": "",
        }
        from unittest.mock import patch
        with patch("workflow.daemon_server.get_branch_definition", side_effect=KeyError("b1")):
            snapshot = _compose_run_snapshot(dummy_record, [])
        assert snapshot["recursion_limit"] is None
