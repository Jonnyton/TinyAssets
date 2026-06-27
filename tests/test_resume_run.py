"""Tests for in-flight run recovery part 2 — SqliteSaver-keyed resume.

Covers:
- resume_run() in tinyassets/runs.py: auth gate, status gate, idempotency,
  missing-checkpoint error, branch-version mismatch, successful resume dispatch.
- _action_resume_run() in tinyassets/universe_server.py: bad run_id, non-owner,
  wrong status, idempotent RESUMED, missing checkpoint, happy path.
- tinyassets/idempotency.py: IdempotencyStore set/get/has round-trip,
  @idempotent_by_step decorator at-most-once semantics.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Idempotency module tests
# ---------------------------------------------------------------------------


class TestIdempotencyStore:
    def test_set_and_get_roundtrip(self, tmp_path):
        from tinyassets.idempotency import IdempotencyStore

        store = IdempotencyStore(tmp_path / "idempotency.db")
        store.set("run-1", "step-1", {"output": "hello"})
        result = store.get("run-1", "step-1")
        assert result == {"output": "hello"}

    def test_get_missing_returns_none(self, tmp_path):
        from tinyassets.idempotency import IdempotencyStore

        store = IdempotencyStore(tmp_path / "idempotency.db")
        assert store.get("run-1", "step-1") is None

    def test_has_true_after_set(self, tmp_path):
        from tinyassets.idempotency import IdempotencyStore

        store = IdempotencyStore(tmp_path / "idempotency.db")
        store.set("run-2", "step-3", "value")
        assert store.has("run-2", "step-3") is True

    def test_has_false_before_set(self, tmp_path):
        from tinyassets.idempotency import IdempotencyStore

        store = IdempotencyStore(tmp_path / "idempotency.db")
        assert store.has("run-9", "step-9") is False

    def test_set_is_ignore_on_conflict(self, tmp_path):
        from tinyassets.idempotency import IdempotencyStore

        store = IdempotencyStore(tmp_path / "idempotency.db")
        store.set("run-1", "step-1", "first")
        store.set("run-1", "step-1", "second")  # should be silently ignored
        assert store.get("run-1", "step-1") == "first"


class TestIdempotentByStep:
    def test_function_called_once_per_pair(self, tmp_path, monkeypatch):
        import tinyassets.idempotency as idm

        monkeypatch.setattr(idm, "_store", None)
        db = tmp_path / ".idempotency.db"
        monkeypatch.setattr(idm, "_get_store", lambda base_path=None: idm.IdempotencyStore(db))

        call_count = {"n": 0}

        @idm.idempotent_by_step
        def side_effect(run_id: str, step_id: str) -> dict:
            call_count["n"] += 1
            return {"result": f"{run_id}/{step_id}"}

        result1 = side_effect("r1", "s1")
        result2 = side_effect("r1", "s1")
        assert call_count["n"] == 1
        assert result1 == result2

    def test_different_pairs_both_execute(self, tmp_path, monkeypatch):
        import tinyassets.idempotency as idm

        monkeypatch.setattr(idm, "_store", None)
        db = tmp_path / ".idempotency.db"
        monkeypatch.setattr(idm, "_get_store", lambda base_path=None: idm.IdempotencyStore(db))

        call_count = {"n": 0}

        @idm.idempotent_by_step
        def side_effect(run_id: str, step_id: str) -> str:
            call_count["n"] += 1
            return f"{run_id}/{step_id}"

        side_effect("r1", "s1")
        side_effect("r1", "s2")
        assert call_count["n"] == 2

    def test_decorator_marks_attribute(self):
        from tinyassets.idempotency import idempotent_by_step

        @idempotent_by_step
        def fn(run_id: str, step_id: str) -> None:
            pass

        assert getattr(fn, "_idempotent_by_step", False) is True


# ---------------------------------------------------------------------------
# Helpers shared across run-level tests
# ---------------------------------------------------------------------------


@pytest.fixture
def run_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")

    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, tmp_path
    importlib.reload(us)


def _setup_interrupted_run(tmp_path: Path, *, actor: str = "tester") -> str:
    """Create an INTERRUPTED run in the runs DB and return its run_id."""
    from tinyassets.runs import (
        RUN_STATUS_INTERRUPTED,
        create_run,
        initialize_runs_db,
        update_run_status,
    )

    initialize_runs_db(tmp_path)
    rid = create_run(
        tmp_path,
        branch_def_id="branch-1",
        thread_id="",
        inputs={},
        actor=actor,
    )
    update_run_status(tmp_path, rid, status=RUN_STATUS_INTERRUPTED)
    return rid


# ---------------------------------------------------------------------------
# resume_run() unit tests (tinyassets/runs.py)
# ---------------------------------------------------------------------------


class TestResumeRunFunction:
    def test_not_found_raises(self, tmp_path):
        from tinyassets.runs import ResumeError, resume_run

        with pytest.raises(ResumeError) as exc_info:
            resume_run(
                tmp_path,
                run_id="nonexistent-run",
                actor="tester",
                branch_lookup=lambda bid, v: None,
            )
        assert exc_info.value.reason == "not_found"

    def test_wrong_actor_raises_auth_failed(self, tmp_path):
        from tinyassets.runs import ResumeError, resume_run

        rid = _setup_interrupted_run(tmp_path, actor="owner")

        with pytest.raises(ResumeError) as exc_info:
            resume_run(
                tmp_path,
                run_id=rid,
                actor="attacker",
                branch_lookup=lambda bid, v: None,
            )
        assert exc_info.value.reason == "auth_failed"

    def test_non_interrupted_status_raises(self, tmp_path):
        from tinyassets.runs import (
            RUN_STATUS_COMPLETED,
            ResumeError,
            create_run,
            initialize_runs_db,
            resume_run,
            update_run_status,
        )

        initialize_runs_db(tmp_path)
        rid = create_run(tmp_path, branch_def_id="b1", thread_id="", inputs={}, actor="tester")
        update_run_status(tmp_path, rid, status=RUN_STATUS_COMPLETED)

        with pytest.raises(ResumeError) as exc_info:
            resume_run(
                tmp_path,
                run_id=rid,
                actor="tester",
                branch_lookup=lambda bid, v: None,
            )
        assert exc_info.value.reason == "not_interrupted"
        assert exc_info.value.current_status == RUN_STATUS_COMPLETED

    def test_already_resumed_is_idempotent(self, tmp_path):
        from tinyassets.runs import (
            RUN_STATUS_RESUMED,
            create_run,
            initialize_runs_db,
            resume_run,
            update_run_status,
        )

        initialize_runs_db(tmp_path)
        rid = create_run(tmp_path, branch_def_id="b1", thread_id="", inputs={}, actor="tester")
        update_run_status(tmp_path, rid, status=RUN_STATUS_RESUMED)

        outcome = resume_run(
            tmp_path,
            run_id=rid,
            actor="tester",
            branch_lookup=lambda bid, v: None,
        )
        assert outcome.run_id == rid
        assert outcome.status == RUN_STATUS_RESUMED

    def test_missing_checkpoint_raises(self, tmp_path):
        from tinyassets.runs import ResumeError, resume_run

        rid = _setup_interrupted_run(tmp_path)

        with pytest.raises(ResumeError) as exc_info:
            resume_run(
                tmp_path,
                run_id=rid,
                actor="tester",
                branch_lookup=lambda bid, v: None,
            )
        assert exc_info.value.reason == "no_checkpoint"

    def test_branch_version_mismatch_raises(self, tmp_path):
        from tinyassets.runs import ResumeError, resume_run

        rid = _setup_interrupted_run(tmp_path)

        with (
            patch("tinyassets.runs._has_checkpoint", return_value=True),
            pytest.raises(ResumeError) as exc_info,
        ):
            resume_run(
                tmp_path,
                run_id=rid,
                actor="tester",
                branch_lookup=lambda bid, v: None,  # always returns None = version missing
            )
        assert exc_info.value.reason == "branch_version_mismatch"

    def test_happy_path_dispatches_background_worker(self, tmp_path):
        from tinyassets.branches import BranchDefinition, NodeDefinition
        from tinyassets.runs import RUN_STATUS_RESUMED, resume_run

        rid = _setup_interrupted_run(tmp_path)

        dummy_branch = BranchDefinition(
            branch_def_id="branch-1",
            name="test",
            domain_id="d",
            state_schema={},
            node_defs=[NodeDefinition(node_id="n1", display_name="n1", prompt_template="hi")],
        )

        with (
            patch("tinyassets.runs._has_checkpoint", return_value=True),
            patch("tinyassets.runs._invoke_graph_resume") as mock_invoke,
        ):
            mock_invoke.return_value = MagicMock(
                run_id=rid, status=RUN_STATUS_RESUMED, output={}, error="",
            )
            outcome = resume_run(
                tmp_path,
                run_id=rid,
                actor="tester",
                branch_lookup=lambda bid, v: dummy_branch,
            )

        assert outcome.run_id == rid
        assert outcome.status == RUN_STATUS_RESUMED


# ---------------------------------------------------------------------------
# _action_resume_run() via extensions tool (universe_server.py)
# ---------------------------------------------------------------------------


class TestActionResumeRun:
    def _call(self, us, action, **kwargs):
        return json.loads(us.extensions(action=action, **kwargs))

    def _setup_run(self, tmp_path, us):
        self._call(us, "create_branch", name="throwaway")
        return _setup_interrupted_run(tmp_path)

    def test_missing_run_id_returns_error(self, run_env):
        us, _ = run_env
        result = self._call(us, "resume_run", run_id="")
        assert "error" in result

    def test_nonexistent_run_id_returns_error(self, run_env):
        us, _ = run_env
        result = self._call(us, "resume_run", run_id="does-not-exist")
        assert "error" in result
        assert "reason" in result

    def test_completed_run_returns_status_error(self, run_env):
        us, base = run_env
        self._call(us, "create_branch", name="throwaway")
        from tinyassets.runs import (
            RUN_STATUS_COMPLETED,
            create_run,
            initialize_runs_db,
            update_run_status,
        )

        initialize_runs_db(base)
        rid = create_run(base, branch_def_id="b1", thread_id="", inputs={}, actor="tester")
        update_run_status(base, rid, status=RUN_STATUS_COMPLETED)

        result = self._call(us, "resume_run", run_id=rid)
        assert "error" in result
        assert result.get("reason") == "not_interrupted"

    def test_missing_checkpoint_returns_error(self, run_env):
        us, base = run_env
        rid = self._setup_run(base, us)
        result = self._call(us, "resume_run", run_id=rid)
        assert "error" in result
        assert result.get("reason") == "no_checkpoint"

    def test_happy_path_returns_run_id_and_resumed_status(self, run_env):
        us, base = run_env
        rid = self._setup_run(base, us)

        from tinyassets.runs import RUN_STATUS_RESUMED, RunOutcome

        dummy_outcome = RunOutcome(run_id=rid, status=RUN_STATUS_RESUMED, output={}, error="")

        with patch("tinyassets.runs.resume_run", return_value=dummy_outcome):
            result = self._call(us, "resume_run", run_id=rid)

        assert result.get("run_id") == rid
        assert result.get("status") == RUN_STATUS_RESUMED

    def test_already_resumed_idempotent(self, run_env):
        us, base = run_env
        self._call(us, "create_branch", name="throwaway")
        from tinyassets.runs import (
            RUN_STATUS_RESUMED,
            create_run,
            initialize_runs_db,
            update_run_status,
        )

        initialize_runs_db(base)
        rid = create_run(base, branch_def_id="b1", thread_id="", inputs={}, actor="tester")
        update_run_status(base, rid, status=RUN_STATUS_RESUMED)

        result = self._call(us, "resume_run", run_id=rid)
        assert result.get("run_id") == rid
        assert result.get("status") == RUN_STATUS_RESUMED
