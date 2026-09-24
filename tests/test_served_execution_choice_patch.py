"""The actual app boundary must admit the canonical execution-choice setters."""

import json

import pytest

from tests.test_engine_mcp_write_graph_patch import _owned_pinned_branch, _patch


def test_served_choices_persist_clear_and_preserve_saved_version(tmp_path, monkeypatch):
    from tinyassets.branch_versions import get_branch_version

    server, branch_id = _owned_pinned_branch(tmp_path, monkeypatch)
    policy = {"preferred": {"provider": "claude-code"}}
    result = _patch(server, [
        {"op": "set_default_llm_policy", "default_llm_policy": policy},
        {"op": "set_concurrency_budget", "concurrency_budget": 2},
    ], branch_id=branch_id)
    assert result.get("status") == "patched", result
    saved_id = result["branch_version_id"]
    readback = json.loads(server.read_graph(target="branch", branch_id=branch_id))
    assert readback["default_llm_policy"] == policy
    assert readback["concurrency_budget"] == 2
    cleared = _patch(server, [
        {"op": "set_default_llm_policy", "default_llm_policy": None},
        {"op": "set_concurrency_budget", "concurrency_budget": None},
    ], branch_id=branch_id)
    assert cleared.get("status") == "patched", cleared
    readback = json.loads(server.read_graph(target="branch", branch_id=branch_id))
    assert readback["default_llm_policy"] is None
    assert readback["concurrency_budget"] is None
    saved = get_branch_version(tmp_path, saved_id)
    assert saved.snapshot["default_llm_policy"] == policy
    assert saved.snapshot["concurrency_budget"] == 2


@pytest.mark.parametrize("bad", [
    {"op": "set_concurrency_budget", "concurrency_budget": True},
    {"op": "set_concurrency_budget", "concurrency_budget": -1},
    {"op": "set_concurrency_budget", "concurrency_budget": "2"},
    {"op": "set_concurrency_budget"},
    {"op": "set_default_llm_policy", "default_llm_policy": []},
    {"op": "set_default_llm_policy", "default_llm_policy": {"preferred_provider": "x"}},
    {"op": "set_default_llm_policy"},
    {"op": "set_published", "published": True},
])
def test_invalid_batch_leaves_owned_definition_unchanged(tmp_path, monkeypatch, bad):
    server, branch_id = _owned_pinned_branch(tmp_path, monkeypatch)
    before = json.loads(server.read_graph(target="branch", branch_id=branch_id))
    result = _patch(server, [
        {"op": "set_concurrency_budget", "concurrency_budget": 2}, bad,
    ], branch_id=branch_id)
    assert result.get("status") != "patched", result
    assert json.loads(server.read_graph(target="branch", branch_id=branch_id)) == before


def test_choices_never_grant_foreign_branch_access(tmp_path, monkeypatch):
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    server, branch_id = _owned_pinned_branch(tmp_path, monkeypatch)
    foreign = get_branch_definition(tmp_path, branch_def_id=branch_id)
    foreign.update(author="other-owner", visibility="public")
    save_branch_definition(tmp_path, branch_def=foreign)
    # Keep this caller's valid serving admission. A readable foreign public
    # definition must reach and fail the canonical AUTHOR gate, not the earlier
    # serving gate that changing _ACTOR_ID without rebinding would hit.
    before = json.loads(server.read_graph(target="branch", branch_id=branch_id))
    result = _patch(server, [
        {"op": "set_concurrency_budget", "concurrency_budget": 2},
    ], branch_id=branch_id)
    assert result["error"] == "Authenticated branch author required.", result
    assert json.loads(server.read_graph(target="branch", branch_id=branch_id)) == before


def test_field_form_guidance_names_reachable_setters(tmp_path, monkeypatch):
    server, branch_id = _owned_pinned_branch(tmp_path, monkeypatch)
    result = _patch(server, {"concurrency_budget": 2, "default_llm_policy": None},
                    branch_id=branch_id)
    assert "set_concurrency_budget" in result["error"]
    assert "set_default_llm_policy" in result["error"]
