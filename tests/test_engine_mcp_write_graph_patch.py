"""Served-surface write_graph operation='patch' (edit an OWN branch in place).

Locks in the edit-surface confinement (served-agent-build-run §2.2): safe self-edit
ops pass; publish / change-visibility / fork are refused; an add_node op is run through
the SAME create per-node sanitizer (node_ref/invoke/bad-sink rejected, approval/author/
fork stripped); update_node may not become a sub-branch invoker; and the whole thing is
allowlist-gated + routed to the author-gated transactional patch_branch. A regression
turns a gate red instead of silently widening the served edit surface.
"""
from __future__ import annotations

import json


def _bind(monkeypatch, *, actor="sub-9", graph="u-9", allow=("u-9",)):
    import tinyassets.engine_mcp_http as http
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset(allow))
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: True)
    return s


def _capture(monkeypatch):
    import tinyassets.api.extensions as ext

    seen: dict = {}

    def _impl(**kw):
        seen.update(kw)
        return json.dumps({"ok": True})

    monkeypatch.setattr(ext, "_extensions_impl", _impl)
    return seen


def _patch(s, changes, *, branch_id="b-1"):
    return json.loads(s.write_graph(
        target="branch", operation="patch", branch_id=branch_id,
        payload_json=json.dumps(changes),
    ))


def test_patch_requires_branch_id(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    out = json.loads(s.write_graph(target="branch", operation="patch", payload_json="[]"))
    assert "requires branch_id" in out["error"]
    assert seen == {}


def test_patch_refused_off_allowlist(monkeypatch):
    s = _bind(monkeypatch, allow=("u-other",))
    seen = _capture(monkeypatch)
    out = _patch(s, [{"op": "set_name", "name": "x"}])
    assert "not enabled for this universe" in out["error"]
    assert seen == {}


def test_patch_rejects_publish_visibility_fork(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    for op in (
        {"op": "set_published", "published": True},
        {"op": "set_visibility", "visibility": "public"},
        {"op": "set_fork_from", "fork_from": "v-foreign"},
    ):
        out = _patch(s, [op])
        assert "not available on the served edit surface" in out["error"], op
    assert seen == {}  # never routed to patch_branch


def test_patch_add_node_reuses_create_sanitizer(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    # node_ref (foreign-approval RCE), invoke (fan-out), and a non-channel sink are all
    # refused by the shared create per-node sanitizer.
    for op in (
        {"op": "add_node", "node_ref": "foreign"},
        {"op": "add_node", "node_id": "n1", "invoke_branch_spec": {"branch_def_id": "b"}},
        {"op": "add_node", "node_id": "n1", "effects": ["wiki_write_back"]},
    ):
        out = _patch(s, [op])
        assert "error" in out, op
    assert seen == {}


def test_patch_add_node_strips_approval(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    _patch(s, [{"op": "add_node", "node_id": "n1", "approved": True,
                "approved_source_hash": "deadbeef", "author": "someone"}])
    # routed to patch_branch with the approval/author fields stripped.
    assert seen["action"] == "patch_branch"
    assert seen["branch_def_id"] == "b-1"
    sent = json.loads(seen["changes_json"])
    assert sent[0] == {"op": "add_node", "node_id": "n1"}


def test_patch_update_node_rejects_invoke(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    out = _patch(s, [{"op": "update_node", "node_id": "n1", "invoke_branch_spec": {"x": 1}}])
    assert "no sub-branch invocation" in out["error"]
    assert seen == {}
    # a plain content edit is fine and routes through.
    _patch(s, [{"op": "update_node", "node_id": "n1", "prompt_template": "new"}])
    assert seen["action"] == "patch_branch"


def test_patch_allows_safe_ops_and_routes(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    changes = [
        {"op": "set_name", "name": "renamed"},
        {"op": "add_edge", "from": "a", "to": "b"},
        {"op": "remove_node", "node_id": "old"},
        {"op": "add_node", "node_id": "n2", "prompt_template": "hi"},
    ]
    out = _patch(s, changes)
    assert out == {"ok": True}
    assert seen["action"] == "patch_branch"
    assert seen["branch_def_id"] == "b-1"
    assert json.loads(seen["changes_json"]) == changes


def test_patch_rejects_unknown_op(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    out = _patch(s, [{"op": "frobnicate"}])
    assert "not allowed on the served edit surface" in out["error"]
    assert seen == {}


def test_patch_caps_effect_nodes_in_batch(monkeypatch):
    from tinyassets import engine_mcp_server as s_mod

    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    over = [
        {"op": "add_node", "node_id": f"n{i}", "effects": ["authenticated_external_call"]}
        for i in range(s_mod._SERVED_MAX_EFFECT_NODES + 1)
    ]
    out = _patch(s, over)
    assert "too many effect-declaring nodes" in out["error"]
    assert seen == {}


def test_patch_rejects_non_json_and_non_list(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    bad = json.loads(s.write_graph(target="branch", operation="patch", branch_id="b-1",
                                   payload_json='{"op":"set_name"}'))
    assert "must be a JSON array" in bad["error"]
    assert seen == {}
