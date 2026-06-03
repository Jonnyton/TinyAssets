"""Soul-loop dispatch (Option A, ships dark) — fantasy_daemon/__main__.py.

When a universe is soul-declared with a real ``loop_branch_def_id``, the daemon
runs that user-built branch directly via ``execute_branch`` (the same path that
runs claimed BranchTasks — so it gets its own state schema + the trusted in-node
enqueue context) and skips the fantasy cycle. Gated behind
``WORKFLOW_SOUL_LOOP_DISPATCH``; default off leaves soulless/legacy universes
untouched.

See docs/design-notes/2026-06-03-soul-loop-dispatch-activation-plan.md.
"""

from __future__ import annotations

from types import SimpleNamespace

import fantasy_daemon.__main__ as dm

LEGACY = "fantasy_author:universe_cycle_wrapper"


def _stub(universe_path) -> SimpleNamespace:
    # _try_execute_soul_loop only touches self._universe_path.
    return SimpleNamespace(_universe_path=str(universe_path))


class _FakeBranch:
    @classmethod
    def from_dict(cls, _src):
        return cls()

    def validate(self):
        return []


def _patch_common(monkeypatch, tmp_path, *, loop_dispatch, captured):
    monkeypatch.setattr(
        "workflow.api.universe._universe_loop_dispatch", loop_dispatch,
    )
    monkeypatch.setattr("workflow.storage.data_dir", lambda: tmp_path)
    monkeypatch.setattr("workflow.branches.BranchDefinition", _FakeBranch)

    def _exec(base_path, **kwargs):
        captured.append(kwargs)
        return SimpleNamespace(run_id="run-1", status="completed")

    monkeypatch.setattr("workflow.runs.execute_branch", _exec)


# ── flag ─────────────────────────────────────────────────────────────────────

def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("WORKFLOW_SOUL_LOOP_DISPATCH", raising=False)
    assert dm._soul_loop_dispatch_enabled() is False


def test_flag_on(monkeypatch):
    monkeypatch.setenv("WORKFLOW_SOUL_LOOP_DISPATCH", "on")
    assert dm._soul_loop_dispatch_enabled() is True


# ── soul-loop dispatch does NOT apply → fall through to fantasy (False) ───────

def test_no_soul_falls_through(monkeypatch, tmp_path):
    captured: list = []
    _patch_common(
        monkeypatch, tmp_path,
        loop_dispatch=lambda udir: (LEGACY, {"reason": "no_soul"}),
        captured=captured,
    )
    handled = dm.DaemonController._try_execute_soul_loop(_stub(tmp_path), "u")
    assert handled is False
    assert captured == []  # never executed a branch


def test_souled_but_no_loop_declared_falls_through(monkeypatch, tmp_path):
    captured: list = []
    _patch_common(
        monkeypatch, tmp_path,
        loop_dispatch=lambda udir: ("", {"error": "universe_loop_not_declared"}),
        captured=captured,
    )
    handled = dm.DaemonController._try_execute_soul_loop(_stub(tmp_path), "u")
    assert handled is False
    assert captured == []


# ── soul-loop dispatch applies (True = handled, skip fantasy) ─────────────────

def test_declared_loop_runs_via_execute_branch_with_enqueue_context(
    monkeypatch, tmp_path,
):
    captured: list = []
    _patch_common(
        monkeypatch, tmp_path,
        loop_dispatch=lambda udir: ("cca3c93b632e", {}),
        captured=captured,
    )
    monkeypatch.setattr(
        "workflow.daemon_server.get_branch_definition",
        lambda base_path, *, branch_def_id: {"branch_def_id": branch_def_id},
    )
    handled = dm.DaemonController._try_execute_soul_loop(
        _stub(tmp_path), "my-universe",
    )
    assert handled is True
    assert len(captured) == 1
    kw = captured[0]
    # Root activation: trusted enqueue context is THIS universe, empty lineage.
    assert kw["_enqueue_universe_id"] == "my-universe"
    assert kw["_parent_branch_task_id"] == ""
    assert kw["_origin_branch_task_id"] == ""
    assert kw["run_name"] == "soul-loop-my-universe"


def _seed_pending_child(universe_path, tid="child-1"):
    from workflow.branch_tasks import BranchTask, append_task
    append_task(universe_path, BranchTask(
        branch_task_id=tid, branch_def_id="0ca6e9c97f65",
        universe_id="u", trigger_source="owner_queued",
        request_type="branch_run", status="pending",
    ))


def test_pick_inactive_when_all_dispatch_flags_off(monkeypatch, tmp_path):
    # Baseline: neither unified-execution nor soul-loop → pick stays gated off.
    monkeypatch.delenv("WORKFLOW_UNIFIED_EXECUTION", raising=False)
    monkeypatch.delenv("WORKFLOW_SOUL_LOOP_DISPATCH", raising=False)
    _seed_pending_child(tmp_path)
    claimed, _inputs = dm._try_dispatcher_pick(tmp_path, "daemon-x")
    assert claimed is None


def test_soul_loop_mode_keeps_queue_unstarved(monkeypatch, tmp_path):
    # Codex regression: with soul-loop ON (and UNIFIED_EXECUTION OFF), the
    # dispatcher pick must still claim pending child tasks the driver enqueued
    # — otherwise the driver re-runs each cycle and the children starve.
    monkeypatch.delenv("WORKFLOW_UNIFIED_EXECUTION", raising=False)
    monkeypatch.setenv("WORKFLOW_SOUL_LOOP_DISPATCH", "on")
    _seed_pending_child(tmp_path, tid="child-42")
    claimed, _inputs = dm._try_dispatcher_pick(tmp_path, "daemon-x")
    assert claimed is not None
    assert claimed.branch_task_id == "child-42"


def test_declared_loop_not_found_refuses_no_fantasy_fallback(
    monkeypatch, tmp_path,
):
    captured: list = []
    _patch_common(
        monkeypatch, tmp_path,
        loop_dispatch=lambda udir: ("ghost-branch", {}),
        captured=captured,
    )

    def _missing(base_path, *, branch_def_id):
        raise KeyError(branch_def_id)

    monkeypatch.setattr(
        "workflow.daemon_server.get_branch_definition", _missing,
    )
    handled = dm.DaemonController._try_execute_soul_loop(_stub(tmp_path), "u")
    # Souled+declared but branch missing → HANDLED (refuse), must NOT fall
    # through to the fantasy cycle, and must not execute anything.
    assert handled is True
    assert captured == []
