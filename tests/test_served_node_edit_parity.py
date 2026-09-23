"""Ordinary settings travel through the served adapter and real staged store.

The live gap (2026-09-23, `served-node-edit-parity`): an app agent could BUILD a node
with output keys and a timeout but could not revise either afterwards, so repairing
its own wiring meant rebuilding the whole workflow. Seven ordinary settings are now
editable in place — description, phase, model_hint, reasoning_effort, input_keys,
output_keys, timeout_seconds — and nothing else moved: authority stays refused, and so
do retry_policy/enabled, which the canonical updater stores but no graph runtime reads.

Every test here drives the REAL served adapter, the REAL canonical patch transaction
and a REAL branch store, and asserts PERSISTED READBACK. The first two are the lead's
red reproduction, red against the unchanged runtime before this change.
"""
from __future__ import annotations

import pytest

from tests.test_served_effect_edit_parity import (
    _bind,
    _nodes,
    _ok,
    _patch,
    _refused,
    _seed,
)


def test_owner_can_rename_existing_output_in_place(tmp_path, monkeypatch):
    server = _bind(monkeypatch, tmp_path)
    branch_id = _seed(tmp_path)
    before = _nodes(server, branch_id)
    _ok(_patch(server, branch_id, [
        {"op": "add_state_field", "name": "revised", "type": "str"},
        {"op": "update_node", "node_id": "worker", "output_keys": ["revised"],
         "source_code": "def run(state):\n    return {'revised': 'new'}\n"},
    ]))
    after = _nodes(server, branch_id)
    assert after["worker"]["output_keys"] == ["revised"]
    assert after["worker"]["node_id"] == before["worker"]["node_id"]
    assert after["checkout"] == before["checkout"]


@pytest.mark.parametrize("bind_workspace", [False, True])
def test_owner_can_lower_existing_timeout_in_place(tmp_path, monkeypatch, bind_workspace):
    server = _bind(monkeypatch, tmp_path)
    branch_id = _seed(tmp_path, timeout_seconds=3600)
    op = {"op": "update_node", "node_id": "worker", "timeout_seconds": 120}
    if bind_workspace:
        op["workspace"] = "checkout"
    _ok(_patch(server, branch_id, [op]))
    after = _nodes(server, branch_id)["worker"]
    assert after["timeout_seconds"] == 120
    assert after["workspace"] == ("checkout" if bind_workspace else "")


# --------------------------------------------------------------------------- #
# Every admitted field persists, and an omitted one is left alone
# --------------------------------------------------------------------------- #
#: (field, value written, value read back). The readback is the point: an earlier
#: round of this surface was "proved" by capture-the-call tests that asserted what
#: the adapter FORWARDED and never opened the stored row.
_ORDINARY_FIELDS = [
    ("description", "What the worker does", "What the worker does"),
    ("phase", "enrich", "enrich"),
    ("model_hint", "claude-opus-5", "claude-opus-5"),
    ("reasoning_effort", "high", "high"),
    ("input_keys", ["repo"], ["repo"]),
    ("output_keys", ["out"], ["out"]),
    ("timeout_seconds", 120, 120.0),
]


@pytest.mark.parametrize("field,sent,stored", _ORDINARY_FIELDS)
def test_each_ordinary_setting_persists_through_the_served_surface(
    tmp_path, monkeypatch, field, sent, stored,
):
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)
    _ok(_patch(s, rid, [{"op": "update_node", "node_id": "worker", field: sent}]))
    assert _nodes(s, rid)["worker"][field] == stored


def test_all_seven_settings_persist_in_one_batch_and_omission_preserves(
    tmp_path, monkeypatch,
):
    """One edit sets all seven; the NEXT edit touches one field and every other
    value survives. Omission-preserves is the half a naive "rebuild the node from
    the op" implementation silently breaks."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)
    sent = {field: value for field, value, _ in _ORDINARY_FIELDS}
    _ok(_patch(s, rid, [{"op": "update_node", "node_id": "worker", **sent}]))
    after = _nodes(s, rid)["worker"]
    for field, _, stored in _ORDINARY_FIELDS:
        assert after[field] == stored, field

    _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "description": "Revised"},
    ]))
    preserved = _nodes(s, rid)["worker"]
    assert preserved["description"] == "Revised"
    for field, _, stored in _ORDINARY_FIELDS:
        if field != "description":
            assert preserved[field] == stored, field
    # ...and the node was EDITED, not replaced: identity and untouched fields hold.
    assert preserved["node_id"] == "worker"
    assert preserved["source_code"] == after["source_code"]
    assert preserved["tools_allowed"] == []
    assert preserved["approved"] is False


def test_clearing_an_ordinary_setting_is_an_ordinary_edit(tmp_path, monkeypatch):
    """An agent that over-specified a node has to be able to undo it."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path, description="old", phase="plan", model_hint="gpt-x",
                reasoning_effort="high", input_keys=["repo"])
    _ok(_patch(s, rid, [{
        "op": "update_node", "node_id": "worker", "description": "",
        "phase": "custom", "model_hint": "", "reasoning_effort": "",
        "input_keys": [],
    }]))
    worker = _nodes(s, rid)["worker"]
    assert worker["description"] == ""
    assert worker["phase"] == "custom"
    assert worker["model_hint"] == ""
    assert worker["reasoning_effort"] == ""
    assert worker["input_keys"] == []


# --------------------------------------------------------------------------- #
# A malformed value persists NOTHING and leaves the branch READABLE
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    # timeout: the coercer used to be a bare float(), so each of these reached the
    # stored column. 0 reads back as the 300s default (an edit that reports success
    # and changes nothing); a negative is an already-expired deadline; nan/inf
    # are unusable deadlines (workspace read-side validation refuses them only
    # after persistence); the huge int raised OverflowError out of the
    # updater rather than returning a refusal.
    {"timeout_seconds": 0},
    {"timeout_seconds": -1},
    {"timeout_seconds": float("nan")},
    {"timeout_seconds": float("inf")},
    {"timeout_seconds": 10**400},
    {"timeout_seconds": True},
    {"timeout_seconds": "soon"},
    {"timeout_seconds": {"seconds": 60}},
    # text fields: a dict here either persists malformed into a text column
    # (description) or raises TypeError: unhashable on the phase membership test.
    {"description": {"text": "hi"}},
    {"phase": {"name": "enrich"}},
    {"phase": ["enrich"]},
    {"description": 7},
    {"phase": "not-a-phase"},
    # routing preference and IO keys, refused by their canonical coercers
    {"model_hint": ["claude-opus-5"]},
    {"reasoning_effort": "turbo"},
    {"input_keys": [{"name": "repo"}]},
    {"output_keys": 7},
    {"output_keys": ["ok", ""]},
])
def test_a_malformed_setting_refuses_the_whole_batch(tmp_path, monkeypatch, bad):
    """The bad value travels with a perfectly valid rename: atomicity is the point,
    and the staging transaction — not the served pre-check — is what provides it."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)
    before = _nodes(s, rid)

    out = _patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "display_name": "Should not stick"},
        {"op": "update_node", "node_id": "worker", **bad},
    ])
    _refused(out)

    after = _nodes(s, rid)
    assert after == before, "a refused batch must persist no part of itself"
    assert after["worker"]["display_name"] == "Worker"


def test_a_workspace_node_cannot_be_edited_past_its_timeout_bound(
    tmp_path, monkeypatch,
):
    """workspace and timeout_seconds are each valid ALONE and invalid TOGETHER: a
    workspace-bound node's timeout must satisfy 0 < t <= 1800. That pair was checked
    only on the way back IN (``NodeDefinition.__post_init__``), so the row saved and
    the very NEXT read raised — an edited branch that could not be loaded at all.
    Both orderings are exercised: raising the timeout on an already-bound node, and
    binding a workspace to an already-slow one."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path, workspace="checkout", timeout_seconds=600)
    before = _nodes(s, rid)

    for bad_op in (
        {"op": "update_node", "node_id": "worker", "timeout_seconds": 1801},
        {"op": "update_node", "node_id": "worker",
         "workspace": "checkout", "timeout_seconds": 3600},
    ):
        out = _patch(s, rid, [
            {"op": "update_node", "node_id": "worker", "display_name": "Nope"},
            bad_op,
        ])
        _refused(out)
        # READABLE, not merely unchanged: an unreadable branch raises right here.
        assert _nodes(s, rid) == before, bad_op

    # An UNBOUND node may hold a longer timeout: the ceiling is the workspace rule,
    # not a global one.
    rid2 = _seed(tmp_path)
    _ok(_patch(s, rid2, [
        {"op": "update_node", "node_id": "worker", "timeout_seconds": 3600},
    ]))
    assert _nodes(s, rid2)["worker"]["timeout_seconds"] == 3600.0
    # ...and binding a workspace to it afterwards is then refused, atomically.
    _refused(_patch(s, rid2, [
        {"op": "update_node", "node_id": "worker", "workspace": "checkout"},
    ]))
    assert _nodes(s, rid2)["worker"]["workspace"] == ""
    assert _nodes(s, rid2)["worker"]["timeout_seconds"] == 3600.0


# --------------------------------------------------------------------------- #
# What did NOT become editable
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("blocked", [
    # execution/data authority
    {"tools_allowed": ["enqueue_branch_run"]},
    {"invoke_branch_spec": {"branch_def_id": "b-other"}},
    {"invoke_branch_version_spec": {"branch_version_id": "b-other@abc"}},
    {"await_run_spec": {"run_id": "r-1"}},
    # provenance / ownership
    {"approved": True},
    {"approved_source_hash": "deadbeef"},
    {"author": "someone-else"},
    {"node_type": "effect"},
    # stored but inert: no graph runtime consumes either, so serving them would
    # promise a retry schedule and an off switch that do not exist.
    {"retry_policy": {"max_retries": 99}},
    {"enabled": False},
])
def test_a_blocked_field_is_refused_even_beside_a_valid_ordinary_edit(
    tmp_path, monkeypatch, blocked,
):
    """Bundling a refused field with a now-admitted one must not smuggle it through,
    and the refusal must name the BLOCKED field, not the valid neighbour."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)
    before = _nodes(s, rid)

    out = _patch(s, rid, [{
        "op": "update_node", "node_id": "worker",
        "description": "valid neighbour", "timeout_seconds": 120, **blocked,
    }])
    (field,) = blocked
    assert f"may not set '{field}'" in out["error"], out
    assert _nodes(s, rid) == before


def test_the_refusal_lists_the_fields_that_would_have_worked(tmp_path, monkeypatch):
    """The allowed-field list in the message is DERIVED from the allowlist, so a
    widening cannot leave a stale list behind telling an agent that a field it may
    now edit is refused."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)
    out = _patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "tools_allowed": ["x"]},
    ])
    for admitted in (
        "description", "phase", "model_hint", "reasoning_effort",
        "input_keys", "output_keys", "timeout_seconds",
    ):
        assert admitted in out["error"], out
    for still_refused in ("retry_policy", "enabled", "invoke_branch_spec"):
        assert still_refused not in out["error"], out


def test_a_foreign_author_cannot_edit_ordinary_settings(tmp_path, monkeypatch):
    """Ordinary does not mean unowned. The refusal comes from the OWNER gate, not
    from a field allowlist — a non-owner is not one field away from succeeding."""
    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path, author="sub-9")
    before = _nodes(s, rid)

    monkeypatch.setattr(s, "_ACTOR_ID", "someone-else")
    out = _patch(s, rid, [{
        "op": "update_node", "node_id": "worker",
        "output_keys": ["stolen"], "timeout_seconds": 1800,
    }])
    _refused(out)
    assert "may not set" not in (out.get("error") or ""), out

    monkeypatch.setattr(s, "_ACTOR_ID", "sub-9")
    assert _nodes(s, rid) == before


# --------------------------------------------------------------------------- #
# A published version is a SNAPSHOT: editing the branch never rewrites it
# --------------------------------------------------------------------------- #
def test_editing_settings_does_not_alter_an_earlier_pinned_version(
    tmp_path, monkeypatch,
):
    """A run admitted against a pinned branch_version_id keeps executing what was
    pinned. The guarantee is version-pinning, so this asserts the REAL branch
    version store: the earlier snapshot's node still carries the old output key and
    timeout after the branch itself has moved on."""
    from tinyassets.branch_versions import get_branch_version

    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path, timeout_seconds=600)

    pinned_id = _ok(_patch(s, rid, [
        {"op": "update_node", "node_id": "worker", "description": "first"},
    ]))["branch_version_id"]
    pinned = get_branch_version(tmp_path, pinned_id)
    assert pinned is not None and pinned.branch_def_id == rid
    pinned_worker = next(
        n for n in pinned.snapshot["node_defs"] if n["node_id"] == "worker"
    )
    assert pinned_worker["output_keys"] == ["out"]
    assert pinned_worker["timeout_seconds"] == 600.0

    _ok(_patch(s, rid, [
        {"op": "add_state_field", "name": "revised", "type": "str"},
        {"op": "update_node", "node_id": "worker", "output_keys": ["revised"],
         "timeout_seconds": 120,
         "source_code": "def run(state):\n    return {'revised': 'new'}\n"},
    ]))
    live = _nodes(s, rid)["worker"]
    assert live["output_keys"] == ["revised"]
    assert live["timeout_seconds"] == 120.0

    still = get_branch_version(tmp_path, pinned_id)
    assert still is not None
    still_worker = next(
        n for n in still.snapshot["node_defs"] if n["node_id"] == "worker"
    )
    assert still_worker["output_keys"] == ["out"]
    assert still_worker["timeout_seconds"] == 600.0
    assert still.content_hash == pinned.content_hash


def test_editing_settings_dispatches_no_work_and_mints_no_consent(
    tmp_path, monkeypatch,
):
    """Configuration is not execution: saving a timeout and an output name runs
    nothing, and the authorizations a run would need are exactly as absent after the
    edit as before it."""
    from tinyassets.effectors import authenticated_external_call as aec
    from tinyassets.effectors import workspace as ws
    from tinyassets.storage.effector_consents import is_consent_active

    s = _bind(monkeypatch, tmp_path)
    rid = _seed(tmp_path)

    def _never(*a, **kw):
        raise AssertionError("editing a setting dispatched an effect")

    monkeypatch.setattr(aec, "run_authenticated_external_call_effector", _never)
    monkeypatch.setattr(ws, "run_workspace_effector", _never)

    _ok(_patch(s, rid, [{
        "op": "update_node", "node_id": "worker",
        "timeout_seconds": 1800, "output_keys": ["out"], "reasoning_effort": "high",
    }]))
    assert _nodes(s, rid)["worker"]["timeout_seconds"] == 1800.0
    for destination in ("api.example.com", "example.com", "*"):
        assert not is_consent_active(
            tmp_path,
            sink=aec.EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
            destination=destination,
        ), destination


# --------------------------------------------------------------------------- #
# The canonical coercer, direct — the grammar the served layer deliberately
# does not copy, so it is pinned where it lives.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    0, -1, -0.5, float("nan"), float("inf"), float("-inf"), 10**400,
    True, False, "soon", "", None, ["60"], {"seconds": 60},
])
def test_the_canonical_timeout_coercer_refuses_unusable_values(bad):
    from tinyassets.api.branches import _coerce_timeout_seconds_update

    value, err = _coerce_timeout_seconds_update(bad, "timeout_seconds")
    assert err, bad
    assert value == 0.0


@pytest.mark.parametrize("good,expected", [
    (120, 120.0), (0.5, 0.5), ("300", 300.0), (1800, 1800.0), (10**6, 1e6),
])
def test_the_canonical_timeout_coercer_accepts_finite_positive_values(good, expected):
    from tinyassets.api.branches import _coerce_timeout_seconds_update

    value, err = _coerce_timeout_seconds_update(good, "timeout_seconds")
    assert err == "", (good, err)
    assert value == expected
