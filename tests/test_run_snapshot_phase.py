"""A running run says which phase it is in, so a universe does not read the
seconds its effect takes to deliver as "hanging" (live 2026-08-30: two 20-second
branch-creation runs were called stuck and the job stopped)."""

from __future__ import annotations

import time
import types

import pytest

from tinyassets.api import runs as runs_api


def _record(status, **extra):
    return {"run_id": "r1", "branch_def_id": "b1", "status": status,
            "actor": "u", "started_at": time.time(), "finished_at": None, "error": "", **extra}


def _events(*node_statuses):
    """Every real run opens with the __system__ recursion event; mirror it."""
    now = time.time()
    rows = [{"run_id": "r1", "step_index": 0, "node_id": "__system__",
             "status": "recursion_limit_applied", "started_at": now, "finished_at": None,
             "detail": {"recursion_limit": 25}}]
    rows += [
        {"run_id": "r1", "step_index": 1000000 + i, "node_id": nid, "status": st,
         "started_at": now, "finished_at": now if st == "ran" else None, "detail": {}}
        for i, (nid, st) in enumerate(node_statuses)
    ]
    return rows


def _stub_branch(monkeypatch, *, effects):
    import tinyassets.branches as branches
    import tinyassets.daemon_server as daemon_server

    node = types.SimpleNamespace
    fake = node(name="wf",
                graph_nodes=[node(id="call_github", display_name="call_github")],
                node_defs=[node(node_id="call_github", display_name="call_github", effects=effects)])
    monkeypatch.setattr(daemon_server, "get_branch_definition", lambda *a, **k: {})
    monkeypatch.setattr(branches.BranchDefinition, "from_dict", staticmethod(lambda d: fake))


@pytest.fixture(autouse=True)
def _isolated_base(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_api, "_base_path", lambda: tmp_path)
    # the graph drawing is not under test and needs the whole branch shape
    monkeypatch.setattr(runs_api, "_run_mermaid_from_events", lambda *_a, **_k: "")


def test_a_running_run_whose_nodes_all_ran_is_delivering_its_effect(monkeypatch):
    _stub_branch(monkeypatch, effects=["authenticated_external_call"])
    snap = runs_api._compose_run_snapshot(
        _record("running"), _events(("call_github", "running"), ("call_github", "ran")))
    assert snap["phase"] == "delivering_effects"
    assert "seconds" in snap["suggested_action"] and "stuck" in snap["suggested_action"]
    assert snap["actionable_by"] == "chatbot"


def test_a_branch_with_no_effect_is_finalizing_not_delivering(monkeypatch):
    _stub_branch(monkeypatch, effects=[])
    snap = runs_api._compose_run_snapshot(_record("running"), _events(("call_github", "ran")))
    assert snap["phase"] == "finalizing"
    assert "effect" not in snap["suggested_action"]


def test_a_running_run_with_a_node_still_running_just_says_so(monkeypatch):
    _stub_branch(monkeypatch, effects=["authenticated_external_call"])
    snap = runs_api._compose_run_snapshot(_record("running"), _events(("call_github", "running")))
    assert snap["phase"] == "running"
    assert "again" in snap["suggested_action"]


def test_a_finished_run_carries_no_phase(monkeypatch):
    _stub_branch(monkeypatch, effects=["authenticated_external_call"])
    snap = runs_api._compose_run_snapshot(_record("completed"), _events(("call_github", "ran")))
    assert "phase" not in snap and "suggested_action" not in snap
