"""Served-surface write_graph operation='patch' (edit an OWN branch in place).

Locks in the edit-surface confinement (served-agent-build-run §2.2): safe self-edit
ops pass; publish / change-visibility / fork are refused; an add_node op is run through
the SAME create per-node sanitizer (node_ref/invoke/bad-sink rejected, approval/author/
fork stripped); update_node may not become a sub-branch invoker; and the whole thing is
owner-admitted + routed to the author-gated transactional patch_branch. A regression
turns a gate red instead of silently widening the served edit surface.
"""
from __future__ import annotations

import json


def _bind(monkeypatch, *, actor="sub-9", graph="u-9", allow=("u-9",)):
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    # Admission is isolated here; downstream operation/consent guards stay real.
    from tests.engine_authority_helpers import mock_engine_admission
    mock_engine_admission(monkeypatch, allow)
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


def test_unknown_edit_operation_teaches_a_reachable_payload(monkeypatch):
    """Failure guidance must not send the agent back to the refused spelling."""
    import re

    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    refused = _patch(s, [{"op": "patch_node", "node_id": "n1", "source_code": "x"}])
    assert seen == {}
    example = json.loads(re.search(r'\{"op":"update_node".*?\}', refused["error"])[0])
    example["node_id"] = "n1"
    example["source_code"] = "def run(state):\n    return {'out': 'edited'}\n"
    accepted = _patch(s, [example])
    assert accepted["ok"] is True
    assert json.loads(seen["changes_json"]) == [example]


def test_guided_edit_persists_on_owned_branch_and_refuses_foreign(tmp_path, monkeypatch):
    """Follow actual advice through the real patch transaction and public readback."""
    import re

    from tinyassets.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    s = _bind(monkeypatch)
    initialize_author_server(tmp_path)
    branch = BranchDefinition(name="Guided edit", author="sub-9", entry_point="instance")
    branch.node_defs = [NodeDefinition(node_id="definition", display_name="Code",
        output_keys=["out"], source_code="def run(state):\n    return {'out': 'old'}\n")]
    branch.graph_nodes = [GraphNodeRef(id="instance", node_def_id="definition")]
    branch.edges = [EdgeDefinition(from_node="START", to_node="instance"),
                    EdgeDefinition(from_node="instance", to_node="END")]
    branch.state_schema = [{"name": "out", "type": "str"}]
    save_branch_definition(tmp_path, branch_def=branch.to_dict())
    rid = branch.branch_def_id
    refused = _patch(s, [{"op": "patch_node"}], branch_id=rid)
    example = json.loads(re.search(r'\{"op":"update_node".*?\}', refused["error"])[0])
    example.update(node_id="definition",
                   source_code="def run(state):\n    return {'out': '新🙂'}\n")
    result = _patch(s, [example], branch_id=rid)
    assert "error" not in result, result
    readback = json.loads(s.read_graph(target="branch", branch_id=rid))
    assert readback["node_defs"][0]["source_code"] == example["source_code"]
    monkeypatch.setattr(s, "_ACTOR_ID", "someone-else")
    assert "error" in _patch(s, [{**example, "source_code": "foreign"}], branch_id=rid)
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-9")
    assert json.loads(s.read_graph(target="branch", branch_id=rid)) == readback


def test_patch_refused_without_serving_authority(monkeypatch):
    s = _bind(monkeypatch, allow=("u-other",))
    seen = _capture(monkeypatch)
    out = _patch(s, [{"op": "set_name", "name": "x"}])
    assert "current serving owner" in out["error"]
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


def test_patch_update_node_allowlist_blocks_authority_fields(monkeypatch):
    """update_node may only retune content — execution/data-authority fields
    (tools_allowed/enabled/retry_policy/input_keys/output_keys) and the
    sub-branch-invoke fields are refused, so an update can't re-activate an approved
    node with new powers without re-invalidating approval (Codex #1). llm_policy is
    a routing preference, not authority, and is NOT in this cohort: it passes the
    served layer untyped and the canonical coercer decides (see the persistence
    test below, which keeps the malformed preferred_provider refusal alive)."""
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    for danger in (
        {"tools_allowed": ["enqueue_branch_run"]},
        {"enabled": True},
        {"retry_policy": {"max_retries": 99}},
        {"input_keys": ["secret"]},
        {"output_keys": ["x"]},
        {"invoke_branch_spec": {"x": 1}},
    ):
        out = _patch(s, [{"op": "update_node", "node_id": "n1", **danger}])
        assert "may not set" in out["error"], danger
    assert seen == {}
    # a non-string content field is refused; a plain content edit routes through.
    bad = _patch(s, [{"op": "update_node", "node_id": "n1", "source_code": ["x"]}])
    assert "must be a string" in bad["error"]
    _patch(s, [{"op": "update_node", "node_id": "n1", "prompt_template": "new"}])
    assert seen["action"] == "patch_branch"
    # A malformed policy is NOT refused by the served allowlist any more; it is
    # forwarded verbatim for the canonical coercer to refuse (no second grammar).
    seen.clear()
    _patch(s, [{"op": "update_node", "node_id": "n1",
                "llm_policy": {"preferred_provider": "x"}}])
    assert seen["action"] == "patch_branch"
    assert json.loads(seen["changes_json"])[0]["llm_policy"] == {"preferred_provider": "x"}


def _owned_pinned_branch(tmp_path, monkeypatch):
    """A real owned branch whose only node is pinned to a provider by name."""
    from tinyassets.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    s = _bind(monkeypatch)
    initialize_author_server(tmp_path)
    branch = BranchDefinition(name="Pinned", author="sub-9", entry_point="instance")
    branch.node_defs = [NodeDefinition(
        node_id="definition", display_name="Draft", output_keys=["out"],
        prompt_template="write", llm_policy={"preferred": {"provider": "codex"}},
        tools_allowed=["read_run_file"],
    )]
    branch.graph_nodes = [GraphNodeRef(id="instance", node_def_id="definition")]
    branch.edges = [EdgeDefinition(from_node="START", to_node="instance"),
                    EdgeDefinition(from_node="instance", to_node="END")]
    branch.state_schema = [{"name": "out", "type": "str"}]
    save_branch_definition(tmp_path, branch_def=branch.to_dict())
    return s, branch.branch_def_id


def _node(s, rid):
    return json.loads(s.read_graph(target="branch", branch_id=rid))["node_defs"][0]


def test_update_node_llm_policy_replace_clear_omit_persist(tmp_path, monkeypatch):
    """The agent repairs its OWN existing pin in place through the real served
    patch route and the real branch write: a dict replaces, a JSON string is the
    same edit, omission preserves, explicit null clears (spec: agent repairs an
    existing node model preference)."""
    s, rid = _owned_pinned_branch(tmp_path, monkeypatch)
    assert _node(s, rid)["llm_policy"] == {"preferred": {"provider": "codex"}}

    # replace by dict
    out = _patch(s, [{"op": "update_node", "node_id": "definition",
                      "llm_policy": {"preferred": {"provider": "claude-code"}}}], branch_id=rid)
    assert "error" not in out, out
    assert _node(s, rid)["llm_policy"] == {"preferred": {"provider": "claude-code"}}

    # replace by JSON string (canonical coercer grammar, no served re-typing)
    out = _patch(s, [{"op": "update_node", "node_id": "definition",
                      "llm_policy": json.dumps({"preferred": {"provider": "codex"}})}],
                 branch_id=rid)
    assert "error" not in out, out
    assert _node(s, rid)["llm_policy"] == {"preferred": {"provider": "codex"}}

    # omission: a content-only edit leaves the pin exactly as it was
    out = _patch(s, [{"op": "update_node", "node_id": "definition",
                      "prompt_template": "write better"}], branch_id=rid)
    assert "error" not in out, out
    after = _node(s, rid)
    assert after["prompt_template"] == "write better"
    assert after["llm_policy"] == {"preferred": {"provider": "codex"}}

    # explicit null clears to "follow whatever the universe serves"
    out = _patch(s, [{"op": "update_node", "node_id": "definition", "llm_policy": None}],
                 branch_id=rid)
    assert "error" not in out, out
    assert not _node(s, rid).get("llm_policy")
    # and the edit never touched execution authority
    assert after["tools_allowed"] == ["read_run_file"]


def test_update_node_llm_policy_malformed_refuses_atomically(tmp_path, monkeypatch):
    """A malformed policy is refused by the CANONICAL validator (the
    preferred_provider trap the live founder hit) and the whole batch rolls
    back: a valid sibling op in the same patch does not land either."""
    s, rid = _owned_pinned_branch(tmp_path, monkeypatch)
    before = _node(s, rid)
    for bad in (
        {"preferred_provider": "x"},           # wrong key, ignored at run time
        {"preferred": "codex"},                # preferred must be a dict
        {"preferred": {"model": "gpt"}},       # missing provider key
        ["codex"],                             # not an object
        "{not json",                           # unparseable string
    ):
        out = _patch(s, [
            {"op": "update_node", "node_id": "definition", "display_name": "Renamed"},
            {"op": "update_node", "node_id": "definition", "llm_policy": bad},
        ], branch_id=rid)
        # the transactional patch reports per-op `errors`; the served layer's own
        # refusals are a single `error` - either way nothing was written
        assert out.get("error") or out.get("errors"), bad
        assert _node(s, rid) == before, bad
    out = _patch(s, [{"op": "update_node", "node_id": "definition",
                      "llm_policy": {"preferred_provider": "x"}}], branch_id=rid)
    assert "preferred_provider" in json.dumps(out) and "not a policy key" in json.dumps(out)


def test_update_node_llm_policy_foreign_owner_and_protected_fields(tmp_path, monkeypatch):
    """Editing the pin grants nothing: a foreign actor is refused by the author
    gate, and bundling llm_policy with a protected execution field is refused
    at the served layer - both leave the persisted node byte-identical."""
    s, rid = _owned_pinned_branch(tmp_path, monkeypatch)
    before = _node(s, rid)
    monkeypatch.setattr(s, "_ACTOR_ID", "someone-else")
    out = _patch(s, [{"op": "update_node", "node_id": "definition",
                      "llm_policy": {"preferred": {"provider": "claude-code"}}}], branch_id=rid)
    assert "error" in out
    # refused by the OWNER gate downstream, not by a served field allowlist
    assert "may not set" not in out["error"], out
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-9")
    assert _node(s, rid) == before
    for protected in (
        {"tools_allowed": ["enqueue_branch_run"]},
        {"enabled": False},
        {"retry_policy": {"max_retries": 9}},
        {"input_keys": ["secret"]},
        {"output_keys": ["leak"]},
    ):
        out = _patch(s, [{"op": "update_node", "node_id": "definition",
                          "llm_policy": {"preferred": {"provider": "claude-code"}},
                          **protected}], branch_id=rid)
        # the refusal names the PROTECTED field, never llm_policy
        (field,) = protected
        assert f"may not set '{field}'" in out["error"], out
        assert _node(s, rid) == before, protected


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


def test_patch_add_node_validates_effect_instead_of_refusing_it(monkeypatch):
    """Effect-bearing add_node is ADMITTED on creation's terms (was refused when a
    per-build effect-node ceiling existed; that cap was removed by `no-graph-size-caps`,
    so the refusal was guarding a limit that no longer exists). What survives is the
    shared declaration grammar: one admitted sink per node, nothing else."""
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    _patch(s, [{"op": "add_node", "node_id": "n1",
                "effects": ["authenticated_external_call"]}])
    assert seen["action"] == "patch_branch"
    assert json.loads(seen["changes_json"]) == [
        {"op": "add_node", "node_id": "n1", "effects": ["authenticated_external_call"]},
    ]
    # ...and the same node count is not a ceiling: many effect nodes in one batch pass.
    seen.clear()
    _patch(s, [{"op": "add_node", "node_id": f"n{i}",
                "effects": ["authenticated_external_call"]} for i in range(20)])
    assert len(json.loads(seen["changes_json"])) == 20
    # The create-surface grammar still binds: unadmitted sink, repeated sink, non-array.
    for bad in (["wiki_write_back"],
                ["authenticated_external_call", "authenticated_external_call"],
                ["authenticated_external_call", "workspace"],
                "authenticated_external_call",
                [{"sink": "authenticated_external_call"}]):
        seen.clear()
        out = _patch(s, [{"op": "add_node", "node_id": "n1", "effects": bad}])
        assert "error" in out, bad
        assert seen == {}, bad


def test_patch_update_node_effects_and_workspace_share_create_grammar(monkeypatch):
    """The edit surface may retune a node's own declarations, through the SAME
    validator creation uses — it can never admit a sink create refuses. Declaring
    fires nothing and grants nothing; the runtime re-derives every authority."""
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    _patch(s, [{"op": "update_node", "node_id": "n1",
                "effects": ["workspace"], "workspace": "checkout"}])
    assert seen["action"] == "patch_branch"
    assert json.loads(seen["changes_json"]) == [
        {"op": "update_node", "node_id": "n1",
         "effects": ["workspace"], "workspace": "checkout"},
    ]
    for bad in (["wiki_write_back"], ["workspace", "workspace"], {"sink": "workspace"}):
        seen.clear()
        out = _patch(s, [{"op": "update_node", "node_id": "n1", "effects": bad}])
        assert "error" in out, bad
        assert seen == {}, bad
    # workspace keeps its CANONICAL string/null grammar: no second grammar here, so a
    # non-string is refused downstream inside the same staging transaction (see the
    # real-store atomicity test in test_served_effect_edit_parity.py).
    seen.clear()
    _patch(s, [{"op": "update_node", "node_id": "n1", "workspace": None}])
    assert json.loads(seen["changes_json"]) == [
        {"op": "update_node", "node_id": "n1", "workspace": None},
    ]


def test_patch_rejects_malformed_metadata(monkeypatch):
    """Non-string metadata would crash SQLite or persist malformed (Codex #4)."""
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    for op in (
        {"op": "set_description", "description": {"x": 1}},
        {"op": "set_name", "name": []},
        {"op": "set_tags", "tags": "notalist"},
    ):
        out = _patch(s, [op])
        assert "must be a" in out["error"], op
    assert seen == {}


def test_patch_rejects_skill_write_ops(monkeypatch):
    """Skill add/update/set carry snapshot objects (tracked follow-up); only
    remove_skill is exposed on the served edit surface."""
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    for op in (
        {"op": "add_skill", "skill": {"id": "x"}},
        {"op": "update_skill", "skill": {"id": "x"}},
        {"op": "set_skills", "skills": []},
    ):
        assert "not allowed" in _patch(s, [op])["error"], op
    assert seen == {}
    _patch(s, [{"op": "remove_skill", "skill_id": "x"}])
    assert seen["action"] == "patch_branch"


def test_patch_rejects_non_json_and_non_list(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    bad = json.loads(s.write_graph(target="branch", operation="patch", branch_id="b-1",
                                   payload_json='{"op":"set_name"}'))
    assert "must be a JSON array" in bad["error"]
    assert seen == {}


def test_patch_rejects_dict_description_fields(monkeypatch):
    """description reaches a text column via add_node / add_state_field; a dict there
    persists malformed (Codex #4 re-review). Both refused pre-storage."""
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    for op in (
        {"op": "add_node", "node_id": "n1", "description": {"x": 1}},
        {"op": "add_state_field", "name": "s", "description": {"x": 1}},
    ):
        out = _patch(s, [op])
        assert "must be a string" in out["error"], op
    assert seen == {}


def test_patch_rejects_dict_text_metadata_class(monkeypatch):
    """The text-metadata class (Codex #4, all rounds): name/description/reducer +
    node_type must be strings across state_schema and node specs."""
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)
    for op in (
        {"op": "add_state_field", "name": "s", "reducer": {"bad": 3}},
        {"op": "add_state_field", "name": "s", "description": {"bad": 1}},
        {"op": "add_node", "node_id": "n", "node_type": {"bad": 1}},
    ):
        assert "must be a string" in _patch(s, [op])["error"], op
    assert seen == {}
