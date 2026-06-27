"""#64 — patch_nodes: bulk-set one field across N nodes in one call.

Before, bot had to call update_node once per node to change a shared
field (e.g. raise timeout on every node). Mission 6 ate two tool-use
continues on this. patch_nodes collapses 6 calls to 1.

Semantics:
- Homogeneous: same field, same value, filtered by node_ids (default:
  all nodes on the branch).
- Atomic: if any node rejects, nothing is written.
- Whitelisted fields only (display_name, description, phase,
  prompt_template, source_code, model_hint, timeout_seconds, enabled).
- prompt_template / source_code are mutually exclusive — setting one
  clears the other (matches update_node semantics).
"""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def us_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _build_three_node_branch(us) -> str:
    bid = json.loads(us.extensions(
        action="create_branch", name="bulk-patch-probe",
    ))["branch_def_id"]
    for nid in ("capture", "tag", "archive"):
        us.extensions(
            action="add_node", branch_def_id=bid, node_id=nid,
            display_name=nid.title(),
            prompt_template=f"{nid}: {{raw}}",
            output_keys=f"{nid}_output",
        )
    for src, dst in (
        ("START", "capture"),
        ("capture", "tag"),
        ("tag", "archive"),
        ("archive", "END"),
    ):
        us.extensions(
            action="connect_nodes", branch_def_id=bid,
            from_node=src, to_node=dst,
        )
    us.extensions(
        action="set_entry_point", branch_def_id=bid, node_id="capture",
    )
    for fld in (
        "raw", "capture_output", "tag_output", "archive_output",
    ):
        us.extensions(
            action="add_state_field", branch_def_id=bid,
            field_name=fld, field_type="str",
        )
    return bid


def _node(us, bid, nid):
    branch = json.loads(us.extensions(
        action="get_branch", branch_def_id=bid,
    ))
    for n in branch["node_defs"]:
        if n["node_id"] == nid:
            return n
    return None


# ─── happy path: bulk timeout update ─────────────────────────────────────


def test_patch_nodes_updates_timeout_on_all_nodes(us_env):
    """The Mission 6 pattern: bump timeout_seconds on every node in
    one call."""
    us, _ = us_env
    bid = _build_three_node_branch(us)
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="timeout_seconds", value="300",
    ))
    assert result["status"] == "patched"
    assert result["patched_count"] == 3
    assert result["field"] == "timeout_seconds"
    assert result["value"] == 300.0
    # Every node now has timeout=300.
    for nid in ("capture", "tag", "archive"):
        assert _node(us, bid, nid)["timeout_seconds"] == 300.0


def test_patch_nodes_respects_node_ids_subset(us_env):
    us, _ = us_env
    bid = _build_three_node_branch(us)
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="timeout_seconds", value="90",
        node_ids="capture,tag",
    ))
    assert result["status"] == "patched"
    assert result["patched_count"] == 2
    # Patched nodes updated.
    assert _node(us, bid, "capture")["timeout_seconds"] == 90.0
    assert _node(us, bid, "tag")["timeout_seconds"] == 90.0
    # Excluded node retains default.
    assert _node(us, bid, "archive")["timeout_seconds"] == 300.0


def test_patch_nodes_bumps_branch_version(us_env):
    us, _ = us_env
    bid = _build_three_node_branch(us)
    before = json.loads(us.extensions(
        action="get_branch", branch_def_id=bid,
    ))["version"]
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="timeout_seconds", value="120",
    ))
    assert result["version_after"] == result["version_before"] + 1
    after = json.loads(us.extensions(
        action="get_branch", branch_def_id=bid,
    ))["version"]
    assert after == before + 1


# ─── field coercion ──────────────────────────────────────────────────────


def test_patch_nodes_coerces_bool_value(us_env):
    us, _ = us_env
    bid = _build_three_node_branch(us)
    # String "false" → bool False.
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="enabled", value="false",
    ))
    assert result["status"] == "patched"
    assert result["value"] is False
    for nid in ("capture", "tag", "archive"):
        assert _node(us, bid, nid)["enabled"] is False


def test_patch_nodes_coerces_string_display_name(us_env):
    us, _ = us_env
    bid = _build_three_node_branch(us)
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="display_name", value="renamed",
        node_ids="tag",
    ))
    assert result["status"] == "patched"
    assert _node(us, bid, "tag")["display_name"] == "renamed"


# ─── atomicity + rejections ──────────────────────────────────────────────


def test_patch_nodes_rejects_unknown_field(us_env):
    us, _ = us_env
    bid = _build_three_node_branch(us)
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="not_a_real_field", value="X",
    ))
    assert result["status"] == "rejected"
    assert "supports" in result["error"].lower()


def test_patch_nodes_rejects_unknown_node_id_atomically(us_env):
    """If any requested node_id is unknown, nothing is patched."""
    us, _ = us_env
    bid = _build_three_node_branch(us)
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="timeout_seconds", value="90",
        node_ids="capture,nonexistent,tag",
    ))
    assert result["status"] == "rejected"
    # capture and tag retained their pre-patch values (300 default).
    assert _node(us, bid, "capture")["timeout_seconds"] == 300.0
    assert _node(us, bid, "tag")["timeout_seconds"] == 300.0


def test_patch_nodes_rejects_bad_phase(us_env):
    us, _ = us_env
    bid = _build_three_node_branch(us)
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="phase", value="bogus-phase",
    ))
    assert result["status"] == "rejected"
    assert "phase" in result["error"].lower()


def test_patch_nodes_rejects_missing_branch(us_env):
    us, _ = us_env
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id="nonexistent",
        field="timeout_seconds", value="300",
    ))
    assert result["status"] == "rejected"
    assert "not found" in result["error"].lower()


def test_patch_nodes_rejects_missing_value(us_env):
    us, _ = us_env
    bid = _build_three_node_branch(us)
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="timeout_seconds",
    ))
    assert result["status"] == "rejected"
    assert "value" in result["error"].lower()


# ─── mutual exclusivity: template vs source ──────────────────────────────


def test_patch_nodes_clears_source_when_setting_template(us_env):
    us, _ = us_env
    bid = _build_three_node_branch(us)
    # First set source_code on capture via update_node.
    us.extensions(
        action="update_node", branch_def_id=bid, node_id="capture",
        source_code="def run(state): return {}",
    )
    # Now patch_nodes to set a new prompt_template — source should clear.
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="prompt_template", value="NEW: {raw}",
        node_ids="capture",
    ))
    assert result["status"] == "patched"
    node = _node(us, bid, "capture")
    assert node["prompt_template"] == "NEW: {raw}"
    assert node["source_code"] == ""


# ─── phone-legible text ──────────────────────────────────────────────────


def test_patch_nodes_text_hides_branch_def_id(us_env):
    """#58 invariant: raw branch_def_id stays out of the text channel."""
    us, _ = us_env
    bid = _build_three_node_branch(us)
    result = json.loads(us.extensions(
        action="patch_nodes", branch_def_id=bid,
        field="timeout_seconds", value="120",
    ))
    assert result["status"] == "patched"
    assert bid not in result["text"]
    assert "bulk-patch-probe" in result["text"]
    assert "3 node" in result["text"]
