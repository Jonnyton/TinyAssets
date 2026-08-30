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
                node_defs=[node(node_id="call_github", display_name="call_github",
                                effects=effects)])
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


def test_a_completed_run_whose_effect_failed_is_the_universes_to_fix(monkeypatch):
    """Live 2026-08-30: an effect that was refused (404 on a deleted branch,
    422, a packet field) completes the run with `error` set; the snapshot
    carried no class, the list view said actionable_by "user", and the
    universe stopped and asked the founder after every one."""
    _stub_branch(monkeypatch, effects=["authenticated_external_call"])
    err = ("external write failed - write_readme/authenticated_external_call: "
           "packet.connection_id is required")
    rec = _record("completed", error=err)
    snap = runs_api._compose_run_snapshot(rec, _events(("call_github", "ran")))
    assert snap["failure_class"] == "external_write_failed"
    assert snap["actionable_by"] == "chatbot"
    assert "run again yourself" in snap["suggested_action"]
    assert "phase" not in snap


def test_the_failure_taxonomy_owns_external_write_failures():
    from tinyassets import runs as runs_module

    failed = ("external write failed - "
              "open_pr/authenticated_external_call: far side answered "
              "HTTP 422: {} [far_side_error]")
    assert (runs_module._classify_failure({"status": "completed", "error": failed})
            == "external_write_failed")
    assert runs_module.ACTIONABLE_BY["external_write_failed"] == "chatbot"
    refused = ("external write failed - call/authenticated_external_call: "
               "refused before the wire: missing_consent [missing_consent]")
    assert (runs_module._classify_failure({"status": "completed", "error": refused})
            == "external_write_refused")
    revoked = ("external write failed - call/authenticated_external_call: "
               "connection authority refused: grant_revoked [grant_revoked]")
    assert (runs_module._classify_failure({"status": "completed", "error": revoked})
            == "external_write_refused")
    assert runs_module.ACTIONABLE_BY["external_write_refused"] == "user"
    assert runs_module._classify_failure({"status": "completed", "error": "boom"}) == "error"
    assert runs_api._classify_run_outcome_error(failed)[0] == "external_write_failed"
    assert runs_api._classify_run_outcome_error(refused)[0] == "external_write_refused"
    assert "at most twice" in runs_module.EXTERNAL_WRITE_FAILED_ACTION
    assert "request rail" in runs_module.EXTERNAL_WRITE_REFUSED_ACTION


def test_a_delivered_4xx_and_a_consent_refusal_become_error_rows():
    """Codex (P1) + docs/concerns/2026-08-28-a-403-effect-completes-the-run-
    silently.md: `delivered` means the request reached the far side, not that
    it succeeded; a 404/422/403 was recorded like a 201 and a consent refusal
    carried no `error` at all, so neither reached the run's error or class."""
    from tinyassets import runs as runs_module

    evidence = {
        "create_branch": {"authenticated_external_call": {
            "delivered": True, "response": {"status": 404, "body": '{"message":"Not Found"}'}}},
        "write": {"authenticated_external_call": {
            "delivered": True, "response": {"status": 201, "body": "{}"}}},
        "post": {"authenticated_external_call": {
            "error_kind": "missing_consent", "dry_run": True}},
    }
    rows = runs_module._collect_external_write_errors(evidence)
    assert [(r["node_id"], r["error_kind"]) for r in rows] == [
        ("create_branch", "far_side_error"), ("post", "missing_consent")]
    assert "HTTP 404" in rows[0]["error"]
    summary = runs_module._external_write_error_summary(rows)
    assert "[far_side_error]" in summary and "[missing_consent]" in summary
    # ...and the summary classifies as REFUSED because a consent is involved
    assert runs_module._classify_failure(
        {"status": "completed", "error": "external write failed - " + summary}
    ) == "external_write_refused"
    only_404 = runs_module._external_write_error_summary(rows[:1])
    assert runs_module._classify_failure(
        {"status": "completed", "error": "external write failed - " + only_404}
    ) == "external_write_failed"


def test_a_refused_effect_snapshot_routes_to_the_founder(monkeypatch):
    _stub_branch(monkeypatch, effects=["authenticated_external_call"])
    err = ("external write failed - post/authenticated_external_call: refused before "
           "the wire: missing_consent [missing_consent]")
    snap = runs_api._compose_run_snapshot(_record("completed", error=err),
                                          _events(("call_github", "ran")))
    assert snap["failure_class"] == "external_write_refused"
    assert snap["actionable_by"] == "user"
    assert "request rail" in snap["suggested_action"]
