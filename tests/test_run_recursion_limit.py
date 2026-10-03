"""recursion_limit_override exposure, and the absence of a ceiling.

LangGraph needs a recursion number, so there is one; it is not a limit.
100 refused a branch whose author wrote a longer loop, with "Branch loop may be
too deep" -- a structural cap on what someone may build (founder, 2026-09-30:
an account has exactly two limits, cloud bytes and concurrent agent seats).
What bounds an endless loop is the run's SEAT.
"""
from __future__ import annotations

import inspect

from tinyassets import runs


class TestThereIsNoCeiling:
    def test_the_default_is_effectively_unbounded(self):
        assert runs.DEFAULT_RECURSION_LIMIT >= 1_000_000, (
            "the default must be past any graph a person writes"
        )

    def test_no_validated_range_survives_in_the_api(self):
        """Mutation guard: re-adding the 10-1000 range is the regression."""
        from tinyassets.api import runs as runs_api

        src = inspect.getsource(runs_api)
        assert "Valid range: 10-1000" not in src
        assert "10 <= _rl_val <= 1000" not in src


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

        # Compilation requires a real persisted execution identity even when
        # the graph/provider and event recording are stubbed.
        run_id = runs.create_run(
            tmp_path, branch_def_id="x", thread_id="test-run", inputs={"a": 1},
            actor="test-owner",
        )

        runs._invoke_graph(
            tmp_path,
            run_id=run_id,
            branch=_StubBranch(),
            inputs={"a": 1},
            provider_call=None,
            recursion_limit=250,
        )

        assert captured_configs, "app.invoke was not called"
        cfg = captured_configs[0]
        assert cfg["recursion_limit"] == 250
        assert cfg["configurable"]["thread_id"] == run_id


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

        run_id = runs.create_run(
            tmp_path, branch_def_id="x", thread_id="test-run", inputs={},
            actor="test-owner",
        )

        runs._invoke_graph(
            tmp_path,
            run_id=run_id,
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
        from tinyassets.api.runs import _action_run_branch

        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        # No branch → quick error return before recursion_limit check
        import json
        result = json.loads(_action_run_branch({
            "branch_def_id": "", "recursion_limit_override": "",
        }))
        assert "error" in result  # missing branch_def_id error

    def test_valid_override_50_accepted(self, tmp_path, monkeypatch):
        import json

        from tinyassets.api.runs import _action_run_branch
        from tinyassets.runs import RUN_STATUS_QUEUED, RunOutcome

        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        monkeypatch.setattr(
            "tinyassets.api.branches._resolve_branch_id",
            lambda branch_def_id, _base_path: branch_def_id,
        )
        captured: dict[str, object] = {}

        def _fake_execute_branch_async(*args, **kwargs):
            captured.update(kwargs)
            return RunOutcome(run_id="run-1", status=RUN_STATUS_QUEUED, output={})

        monkeypatch.setattr(
            "tinyassets.runs.execute_branch_async",
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

        # `visibility: public` stated rather than omitted: an absent field now reads
        # as PRIVATE (founder 2026-09-26), and this double's subject is the
        # recursion limit, not the read gate.
        dummy_src = {"branch_def_id": "b1", "name": "test", "node_defs": [],
                     "edges": [], "visibility": "public"}
        stub_branch = MagicMock()
        stub_branch.validate.return_value = []  # no errors
        stub_branch.to_dict.return_value = dummy_src  # real scalar contract, no file manifest
        monkeypatch.setattr(
            "tinyassets.daemon_server.get_branch_definition",
            lambda *a, **k: dummy_src,
        )
        monkeypatch.setattr(
            "tinyassets.branches.BranchDefinition.from_dict",
            staticmethod(lambda _: stub_branch),
        )
        return stub_branch

    def test_a_small_override_is_the_authors_own_guard(self, tmp_path, monkeypatch):
        """5 was refused for being under 10. It is the author's number now."""
        import json

        from tinyassets.api.runs import _action_run_branch
        from tinyassets.runs import RUN_STATUS_QUEUED, RunOutcome

        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        monkeypatch.setattr(
            "tinyassets.api.branches._resolve_branch_id",
            lambda branch_def_id, _base_path: branch_def_id,
        )
        captured: dict[str, object] = {}

        def _fake_execute_branch_async(*args, **kwargs):
            captured.update(kwargs)
            return RunOutcome(run_id="run-small", status=RUN_STATUS_QUEUED, output={})

        monkeypatch.setattr(
            "tinyassets.runs.execute_branch_async", _fake_execute_branch_async,
        )
        result = json.loads(_action_run_branch({
            "branch_def_id": "b1",
            "recursion_limit_override": "5",
        }))
        assert not result.get("error"), result
        assert captured["recursion_limit_override"] == 5

    def test_a_large_override_has_no_ceiling(self, tmp_path, monkeypatch):
        """2000 was refused for being over 1000. There is no upper bound now."""
        import json

        from tinyassets.api.runs import _action_run_branch
        from tinyassets.runs import RUN_STATUS_QUEUED, RunOutcome

        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        monkeypatch.setattr(
            "tinyassets.api.branches._resolve_branch_id",
            lambda branch_def_id, _base_path: branch_def_id,
        )
        captured: dict[str, object] = {}

        def _fake_execute_branch_async(*args, **kwargs):
            captured.update(kwargs)
            return RunOutcome(run_id="run-big", status=RUN_STATUS_QUEUED, output={})

        monkeypatch.setattr(
            "tinyassets.runs.execute_branch_async", _fake_execute_branch_async,
        )
        result = json.loads(_action_run_branch({
            "branch_def_id": "b1",
            "recursion_limit_override": "250000",
        }))
        assert not result.get("error"), result
        assert captured["recursion_limit_override"] == 250000

    def test_zero_and_negative_are_still_refused(self, tmp_path, monkeypatch):
        """Not a smaller ceiling -- a graph that cannot take a step."""
        import json

        from tinyassets.api.runs import _action_run_branch

        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        for bad in ("0", "-5"):
            result = json.loads(_action_run_branch({
                "branch_def_id": "b1",
                "recursion_limit_override": bad,
            }))
            assert "error" in result, bad
            assert "positive integer" in result["error"]

    def test_override_not_integer_rejected(self, tmp_path, monkeypatch):
        import json

        from tinyassets.api.runs import _action_run_branch

        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        self._stub_valid_branch(monkeypatch)
        result = json.loads(_action_run_branch({
            "branch_def_id": "b1",
            "recursion_limit_override": "not-a-number",
        }))
        assert "error" in result


class TestGetRunRecursionLimit:
    """get_run snapshot includes recursion_limit from events."""

    def test_recursion_limit_in_snapshot_when_event_present(self):
        from tinyassets.api.runs import _compose_run_snapshot

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
        with patch("tinyassets.daemon_server.get_branch_definition", side_effect=KeyError("b1")):
            snapshot = _compose_run_snapshot(dummy_record, events)
        assert snapshot["recursion_limit"] == 75

    def test_recursion_limit_none_when_no_system_event(self):
        from tinyassets.api.runs import _compose_run_snapshot

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
        with patch("tinyassets.daemon_server.get_branch_definition", side_effect=KeyError("b1")):
            snapshot = _compose_run_snapshot(dummy_record, [])
        assert snapshot["recursion_limit"] is None
