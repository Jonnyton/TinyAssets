"""A running run says which phase it is in, so a universe does not read the
seconds its effect takes to deliver as "hanging" (live 2026-08-30: two 20-second
branch-creation runs were called stuck and the job stopped)."""

from __future__ import annotations

import time

import pytest

from tinyassets.api import runs as runs_api


def _record(status, **extra):
    return {"run_id": "r1", "branch_def_id": "no-such-branch", "status": status,
            "actor": "u", "started_at": time.time(), "finished_at": None, "error": "", **extra}


def _events(*node_statuses):
    now = time.time()
    return [
        {"run_id": "r1", "step_index": 1000000 + i, "node_id": nid, "status": st,
         "started_at": now, "finished_at": now if st == "ran" else None, "detail": {}}
        for i, (nid, st) in enumerate(node_statuses)
    ]


@pytest.fixture(autouse=True)
def _isolated_base(tmp_path, monkeypatch):
    import tinyassets.daemon_server as daemon_server

    monkeypatch.setattr(runs_api, "_base_path", lambda: tmp_path)

    def _no_branch(*_a, **_k):
        raise KeyError("no-such-branch")

    monkeypatch.setattr(daemon_server, "get_branch_definition", _no_branch)


def test_a_running_run_whose_nodes_all_ran_is_delivering_its_effect():
    snap = runs_api._compose_run_snapshot(
        _record("running"), _events(("call_github", "running"), ("call_github", "ran")))
    assert snap["phase"] == "delivering_effects"
    assert "seconds" in snap["suggested_action"] and "stuck" in snap["suggested_action"]
    assert snap["actionable_by"] == "chatbot"


def test_a_running_run_with_a_node_still_running_just_says_so():
    snap = runs_api._compose_run_snapshot(_record("running"), _events(("think", "running")))
    assert snap["phase"] == "running"
    assert "again" in snap["suggested_action"]


def test_a_finished_run_carries_no_phase():
    snap = runs_api._compose_run_snapshot(_record("completed"), _events(("think", "ran")))
    assert "phase" not in snap and "suggested_action" not in snap
