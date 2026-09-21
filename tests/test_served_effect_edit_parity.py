"""Served create/edit parity for a node's effect and workspace DECLARATIONS.

The live gap (2026-09-21): an app agent could BUILD an effect-bearing workflow but
could not change the same declaration afterwards, so repairing one meant rebuilding
the branch. These tests drive the served ``write_graph`` surface through the REAL
patch transaction and a real branch store, because the previous round of this code
was proved by capture-the-call tests that never touched a persisted row.

What each test is actually pinning:

* an edit REPLACES / CLEARS / PRESERVES-on-omission a declaration, and an
  effect-bearing node can be ADDED to an existing branch;
* a batch containing one malformed declaration persists NOTHING (the staging
  transaction is the atomicity, not the served pre-check);
* a non-owner cannot edit at all;
* the edit fires no effect and mints no consent — a declaration NAMES a sink, and
  every authority is re-derived per dispatch at run time;
* genuine source-review provenance is SOURCE-bound: a declaration-only edit keeps
  it, changing the source clears it.
"""
from __future__ import annotations

import json

import pytest


def _bind(monkeypatch, tmp_path, *, actor="sub-9", graph="u-9", allow=("u-9",)):
    from tinyassets import engine_mcp_server as s

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    from tests.engine_authority_helpers import mock_engine_admission

    mock_engine_admission(monkeypatch, allow)
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: True)
    return s


def _seed(tmp_path, *, author="sub-9", **node_kwargs):
    """Persist a two-node branch: a checkout ancestor plus an editable worker."""
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    initialize_author_server(tmp_path)
    branch = BranchDefinition(name="Effect edit", author=author, entry_point="checkout")
    worker = NodeDefinition(
        node_id="worker",
        display_name="Worker",
        output_keys=["out"],
        source_code="def run(state):\n    return {'out': 'old'}\n",
        **node_kwargs,
    )
    branch.node_defs = [
        NodeDefinition(node_id="checkout", display_name="Checkout", output_keys=["repo"],
                       source_code="def run(state):\n    return {'repo': 'x'}\n"),
        worker,
    ]
    branch.graph_nodes = [GraphNodeRef(id="checkout", node_def_id="checkout"),
                          GraphNodeRef(id="worker", node_def_id="worker")]
    branch.edges = [EdgeDefinition(from_node="START", to_node="checkout"),
                    EdgeDefinition(from_node="checkout", to_node="worker"),
                    EdgeDefinition(from_node="worker", to_node="END")]
    branch.state_schema = [{"name": "repo", "type": "str"}, {"name": "out", "type": "str"}]
    save_branch_definition(tmp_path, branch_def=branch.to_dict())
    return branch.branch_def_id


def _patch(s, rid, changes):
    return json.loads(s.write_graph(target="branch", operation="patch", branch_id=rid,
                                    payload_json=json.dumps(changes)))


def _rejected(out) -> bool:
    """True for EVERY refusal spelling this surface uses.

    The served layer refuses with ``error``; the canonical transaction refuses a
    whole batch with ``errors``; a batch that applied cleanly but failed graph
    validation comes back ``status: "rejected"`` with an EMPTY ``errors`` list and
    the reasons under ``suggestions``. A helper that knew only the first two read
    that third one as a pass — which is how a test asserts persistence against a
    branch that was never written.
    """
    return bool(out.get("error") or out.get("errors")
                or out.get("status") == "rejected")


def _ok(out):
    assert not _rejected(out), out
    return out


def _refused(out):
    assert _rejected(out), out
    return out


def _nodes(s, rid):
    return {n["node_id"]: n for n in json.loads(s.read_graph(target="branch",
                                                             branch_id=rid))["node_defs"]}


# --------------------------------------------------------------------------- #
# Persistence: replace / clear / omit / add
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("clear_effects", [[], None])
def test_an_existing_declaration_is_replaced_cleared_and_preserved(
    tmp_path, monkeypatch, clear_effects,
):
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path, effects=["authenticated_external_call"])

    # REPLACE: swap the sink and bind the ancestor checkout, in place.
    _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker",
         "effects": ["workspace"], "workspace": "checkout"},
    ]))
    worker = _nodes(s, rid)["worker"]
    assert worker["effects"] == ["workspace"]
    assert worker["workspace"] == "checkout"

    # OMIT: an unrelated edit leaves both declarations exactly as they were.
    _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "display_name": "Renamed"},
    ]))
    worker = _nodes(s, rid)["worker"]
    assert worker["display_name"] == "Renamed"
    assert worker["effects"] == ["workspace"]
    assert worker["workspace"] == "checkout"

    # CLEAR: an empty array removes the declaration; null clears the binding.
    _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "effects": clear_effects,
         "workspace": None},
    ]))
    worker = _nodes(s, rid)["worker"]
    assert worker["effects"] == []
    assert worker["workspace"] == ""

    # The branch is EDITED, not rebuilt: same identity throughout.
    assert json.loads(s.read_graph(target="branch", branch_id=rid))["branch_def_id"] == rid


def test_an_effect_bearing_node_is_added_to_an_existing_branch(tmp_path, monkeypatch):
    """The old refusal sent the agent back to create-a-whole-new-branch. There is no
    per-branch effect-node ceiling to protect (`no-graph-size-caps`, founder
    2026-08-30), so adding one is admitted on exactly creation's terms."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)

    _ok(_patch(s, rid, [
        {"op": "add_node", "node_id": "caller", "display_name": "Caller",
         "output_keys": ["packet"], "effects": ["authenticated_external_call"],
         "source_code": "def run(state):\n    return {'packet': {}}\n",
         # Caller-supplied provenance is stripped exactly as on creation.
         "approved": True, "approved_source_hash": "deadbeef", "author": "someone"},
        {"op": "remove_edge", "from_node": "worker", "to_node": "END"},
        {"op": "add_edge", "from_node": "worker", "to_node": "caller"},
        {"op": "add_edge", "from_node": "caller", "to_node": "END"},
        {"op": "add_state_field", "name": "packet", "type": "dict"},
    ]))
    added = _nodes(s, rid)["caller"]
    assert added["effects"] == ["authenticated_external_call"]
    assert added["approved"] is False
    assert added["approved_source_hash"] == ""


# --------------------------------------------------------------------------- #
# A rejected batch persists nothing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_op", [
    # unadmitted sink (allowlist, on update and on add alike)
    {"op": "update_node", "node_id": "worker", "effects": ["wiki_write_back"]},
    {"op": "add_node", "node_id": "extra", "effects": ["wiki_write_back"]},
    # repeated sink: the effector dispatches EVERY entry, so one node would fire twice
    {"op": "update_node", "node_id": "worker",
     "effects": ["authenticated_external_call", "authenticated_external_call"]},
    # two different sinks in one node — still more than one dispatch
    {"op": "update_node", "node_id": "worker",
     "effects": ["authenticated_external_call", "workspace"]},
    # malformed shape
    {"op": "update_node", "node_id": "worker", "effects": "authenticated_external_call"},
    {"op": "update_node", "node_id": "worker", "effects": [{"sink": "workspace"}]},
    # non-string workspace: refused by the CANONICAL grammar inside the transaction
    {"op": "update_node", "node_id": "worker", "workspace": ["checkout"]},
    {"op": "update_node", "node_id": "worker", "workspace": 7},
    # the authority cohort stays refused on the served edit surface
    {"op": "update_node", "node_id": "worker", "tools_allowed": ["enqueue_branch_run"]},
])
def test_a_rejected_batch_leaves_the_stored_branch_untouched(tmp_path, monkeypatch, bad_op):
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path, effects=["workspace"], workspace="checkout")
    before = _nodes(s, rid)

    # The bad op travels with a perfectly valid one: atomicity is the point.
    out = _patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "display_name": "Should not stick"},
        bad_op,
    ])
    _refused(out)

    after = _nodes(s, rid)
    assert after == before, "a refused batch must persist no part of itself"
    assert after["worker"]["effects"] == ["workspace"]
    assert after["worker"]["workspace"] == "checkout"
    assert after["worker"]["display_name"] == "Worker"


def test_a_foreign_author_cannot_edit_a_declaration(tmp_path, monkeypatch):
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path, author="sub-9", effects=["workspace"])
    before = _nodes(s, rid)

    monkeypatch.setattr(s, "_ACTOR_ID", "someone-else")
    out = _patch(s, rid, [
        {"op": "update_node", "node_id": "worker",
         "effects": ["authenticated_external_call"]},
    ])
    _refused(out)

    monkeypatch.setattr(s, "_ACTOR_ID", "sub-9")
    assert _nodes(s, rid) == before


# --------------------------------------------------------------------------- #
# An edit is a declaration, not an authorization
# --------------------------------------------------------------------------- #
def test_editing_a_declaration_fires_nothing_and_mints_no_consent(tmp_path, monkeypatch):
    """Declaring a sink names it; it does not grant it. The run-time effector
    re-derives the connection grant, the per-destination consent and the workspace
    admission on every dispatch, so an edit can only ever name what the runtime will
    independently admit or refuse."""
    from tinyassets.effectors import authenticated_external_call as aec
    from tinyassets.effectors import workspace as ws

    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)

    def _never(*a, **kw):
        raise AssertionError("editing a declaration dispatched an effect")

    monkeypatch.setattr(aec, "run_authenticated_external_call_effector", _never)
    monkeypatch.setattr(ws, "run_workspace_effector", _never)

    _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker",
         "effects": ["authenticated_external_call"]},
    ]))
    assert _nodes(s, rid)["worker"]["effects"] == ["authenticated_external_call"]

    # ...and the consent the runtime will demand is still absent afterwards.
    from tinyassets.storage.effector_consents import is_consent_active

    universe_dir = tmp_path  # what the effector resolves from base_path
    for destination in ("api.example.com", "example.com", "*"):
        assert not is_consent_active(
            universe_dir,
            sink=aec.EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
            destination=destination,
        ), destination
    assert aec._check_consent(universe_dir, "api.example.com") is False


# --------------------------------------------------------------------------- #
# Source-review provenance stays SOURCE-bound
# --------------------------------------------------------------------------- #
def test_a_declaration_edit_keeps_source_provenance_and_a_source_edit_clears_it(
    tmp_path, monkeypatch,
):
    """Approval records WHO reviewed WHICH source — it is not an execution permit
    (sandboxed code runs by authorship). So a declaration-only edit must NOT throw
    away a genuine review, and changing the source MUST invalidate it."""
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)

    stored = BranchDefinition.from_dict(
        get_branch_definition(tmp_path, branch_def_id=rid),
    )
    worker = next(n for n in stored.node_defs if n.node_id == "worker")
    worker.mark_approved(approved_by="reviewer", reason="read it")
    save_branch_definition(tmp_path, branch_def=stored.to_dict())
    approved_hash = _nodes(s, rid)["worker"]["approved_source_hash"]
    assert approved_hash and _nodes(s, rid)["worker"]["approved"] is True

    # Declaration-only edit: the source is untouched, so the review still stands.
    _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "effects": ["workspace"],
         "workspace": "checkout"},
    ]))
    after = _nodes(s, rid)["worker"]
    assert after["effects"] == ["workspace"]
    assert after["approved"] is True
    assert after["approved_source_hash"] == approved_hash

    # Re-sending the IDENTICAL source is not a change either.
    _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "source_code": after["source_code"]},
    ]))
    assert _nodes(s, rid)["worker"]["approved"] is True

    # Changing the source invalidates the review, by the existing canonical path.
    _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker",
         "source_code": "def run(state):\n    return {'out': 'new'}\n"},
    ]))
    changed = _nodes(s, rid)["worker"]
    assert changed["approved"] is False
    assert changed["approved_source_hash"] == ""
    assert changed["effects"] == ["workspace"], "an unrelated field must not be reset"


def test_incoming_approval_metadata_is_never_accepted_on_an_edit(tmp_path, monkeypatch):
    """Approval cannot be SUPPLIED by the caller: add_node strips it, update_node has
    no such field at all. Neither route lets an edit self-certify."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)

    out = _patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "approved": True,
         "approved_source_hash": "deadbeef"},
    ])
    assert "may not set" in out["error"]
    assert _nodes(s, rid)["worker"]["approved"] is False

    _ok(_patch(s, rid, [
        {"op": "add_node", "node_id": "sneaky", "display_name": "Sneaky",
         "source_code": "def run(state):\n    return {}\n",
         "approved": True, "approved_by": "me", "approved_source_hash": "deadbeef",
         "approval_reason": "trust me", "author": "elsewhere"},
        {"op": "remove_edge", "from_node": "worker", "to_node": "END"},
        {"op": "add_edge", "from_node": "worker", "to_node": "sneaky"},
        {"op": "add_edge", "from_node": "sneaky", "to_node": "END"},
    ]))
    sneaky = _nodes(s, rid)["sneaky"]
    assert sneaky["approved"] is False
    assert sneaky["approved_source_hash"] == ""
    assert sneaky["approval_reason"] == ""
