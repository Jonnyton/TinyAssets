"""Branch authoring actions for the `extensions` tool.

Covers the 10 ship-list actions, the ledger-wrapper guarantee, the
recipe-tracker end-to-end vignette, and the hard-rule UX flag that
`describe_branch` now points users at `run_branch`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def branch_env(tmp_path, monkeypatch):
    """Point the Workflow data root at a temp base path for the test.

    The Community Branches storage layer uses ``_base_path()`` which
    reads ``WORKFLOW_DATA_DIR`` — pointing it at a temp dir keeps
    tests isolated from real universes. Storage backend is pinned to
    ``sqlite_only`` globally by the conftest autouse fixture.
    """
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    import importlib

    from workflow import universe_server as us

    importlib.reload(us)
    yield us, Path(tmp_path)
    importlib.reload(us)


def _call(us, action, **kwargs):
    result = us.extensions(action=action, **kwargs)
    return json.loads(result)


def test_create_branch_round_trips(branch_env):
    us, _ = branch_env
    result = _call(us, "create_branch", name="Recipe tracker",
                   description="Capture recipes")
    assert result["status"] == "created"
    assert result["branch_def_id"]

    got = _call(us, "get_branch", branch_def_id=result["branch_def_id"])
    assert got["name"] == "Recipe tracker"
    assert got["description"] == "Capture recipes"


def test_create_branch_requires_name(branch_env):
    us, _ = branch_env
    result = _call(us, "create_branch", name="")
    assert "error" in result


def test_list_branches_returns_summaries(branch_env):
    us, _ = branch_env
    _call(us, "create_branch", name="A")
    _call(us, "create_branch", name="B")

    listing = _call(us, "list_branches")
    assert listing["count"] == 2
    names = sorted(b["name"] for b in listing["branches"])
    assert names == ["A", "B"]
    assert all("node_count" in b for b in listing["branches"])


def test_list_branches_published_only_filter(branch_env):
    us, _ = branch_env
    spec = {
        "name": "Published",
        "entry_point": "ready",
        "node_defs": [{
            "node_id": "ready",
            "display_name": "Ready",
            "prompt_template": "Do the work.",
        }],
        "edges": [
            {"from": "START", "to": "ready"},
            {"from": "ready", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    published = _call(us, "build_branch", spec_json=json.dumps(spec))
    _call(us, "create_branch", name="Probe draft")
    patched = _call(
        us,
        "patch_branch",
        branch_def_id=published["branch_def_id"],
        changes_json=json.dumps([{"op": "set_published", "published": True}]),
    )
    assert patched.get("status") != "rejected", patched

    listing = _call(us, "list_branches", published_only=True)
    assert listing["count"] == 1
    assert listing["branches"][0]["name"] == "Published"
    assert listing["branches"][0]["published"] is True


def test_list_branches_node_count_matches_node_defs_length(branch_env):
    """list_branches.node_count must equal get_branch.node_defs length.

    STATUS.md Approved-bugs 2026-04-22: the old formula
    ``len(graph.nodes) + len(node_defs)`` double-counted because
    graph.nodes is a compiled-topology view that overlaps with
    node_defs. Fix makes list_branches agree with describe_branch's
    canonical count (``len(branch.node_defs)``).
    """
    us, _ = branch_env
    created = _call(us, "create_branch", name="Counted")
    bid = created["branch_def_id"]

    # Populate 3 distinct node_defs so the bug shape (double-count)
    # would manifest as 6 instead of 3.
    for nid in ("alpha", "beta", "gamma"):
        _call(us, "add_node", branch_def_id=bid, node_id=nid,
              display_name=nid, prompt_template=f"do {nid}")

    # Truth: get_branch.node_defs length.
    got = _call(us, "get_branch", branch_def_id=bid)
    expected = len(got["node_defs"])
    assert expected == 3, (
        f"precondition: add_node should have created 3 node_defs; "
        f"got {expected}"
    )

    # list_branches.node_count must match.
    listing = _call(us, "list_branches")
    entry = next(b for b in listing["branches"] if b["branch_def_id"] == bid)
    assert entry["node_count"] == expected, (
        f"list_branches.node_count ({entry['node_count']}) "
        f"!= len(get_branch.node_defs) ({expected}). The old formula "
        f"len(graph.nodes) + len(node_defs) double-counted; truthful "
        f"count is len(node_defs)."
    )


def test_delete_branch(branch_env):
    us, _ = branch_env
    created = _call(us, "create_branch", name="Doomed")
    bid = created["branch_def_id"]

    deleted = _call(us, "delete_branch", branch_def_id=bid)
    assert deleted["status"] == "deleted"

    missing = _call(us, "get_branch", branch_def_id=bid)
    assert "error" in missing


def test_add_node_rejects_source_and_template_both(branch_env):
    us, _ = branch_env
    bid = _call(us, "create_branch", name="X")["branch_def_id"]

    result = _call(
        us, "add_node",
        branch_def_id=bid, node_id="n1", display_name="One",
        source_code="def run(state): pass",
        prompt_template="This is a prompt",
    )
    assert "error" in result


def test_add_node_duplicate_id_rejected(branch_env):
    us, _ = branch_env
    bid = _call(us, "create_branch", name="X")["branch_def_id"]

    first = _call(
        us, "add_node",
        branch_def_id=bid, node_id="dup", display_name="First",
        prompt_template="one",
    )
    assert first["status"] == "added"

    second = _call(
        us, "add_node",
        branch_def_id=bid, node_id="dup", display_name="Second",
        prompt_template="two",
    )
    assert "error" in second


def test_set_entry_point_updates_branch(branch_env):
    us, _ = branch_env
    bid = _call(us, "create_branch", name="X")["branch_def_id"]
    _call(
        us, "add_node",
        branch_def_id=bid, node_id="capture", display_name="Capture",
        prompt_template="...",
    )
    _call(us, "set_entry_point", branch_def_id=bid, node_id="capture")

    got = _call(us, "get_branch", branch_def_id=bid)
    assert got["entry_point"] == "capture"


def test_add_state_field_duplicate_rejected(branch_env):
    us, _ = branch_env
    bid = _call(us, "create_branch", name="X")["branch_def_id"]
    first = _call(
        us, "add_state_field",
        branch_def_id=bid, field_name="raw", field_type="str",
    )
    assert first["status"] == "added"
    dup = _call(
        us, "add_state_field",
        branch_def_id=bid, field_name="raw", field_type="str",
    )
    assert "error" in dup


def test_validate_reports_errors_on_empty_branch(branch_env):
    us, _ = branch_env
    bid = _call(us, "create_branch", name="Empty")["branch_def_id"]
    result = _call(us, "validate_branch", branch_def_id=bid)
    assert result["valid"] is False
    assert any("at least one node" in e.lower() for e in result["errors"])


def test_describe_branch_points_at_runner(branch_env):
    """Phase 3 shipped — describe_branch should direct users to run_branch."""
    us, _ = branch_env
    bid = _call(us, "create_branch", name="Empty")["branch_def_id"]
    result = _call(us, "describe_branch", branch_def_id=bid)
    assert "run_branch" in result["summary"]
    assert "inputs_json" in result["summary"]


def test_recipe_tracker_end_to_end(branch_env):
    us, base = branch_env

    created = _call(
        us, "create_branch",
        name="Recipe tracker",
        description="Capture, categorize, archive recipes",
    )
    bid = created["branch_def_id"]
    assert created["status"] == "created"

    for node_id, display, template in (
        ("capture", "Capture raw recipe",
         "Read the user's message and extract recipe."),
        ("categorize", "Categorize recipe",
         "Classify by cuisine and meal type."),
        ("archive", "Archive to library",
         "Format as a wiki entry."),
    ):
        r = _call(
            us, "add_node",
            branch_def_id=bid, node_id=node_id,
            display_name=display, prompt_template=template,
        )
        assert r["status"] == "added"

    for src, dst in (
        ("START", "capture"),
        ("capture", "categorize"),
        ("categorize", "archive"),
        ("archive", "END"),
    ):
        _call(us, "connect_nodes",
              branch_def_id=bid, from_node=src, to_node=dst)

    _call(us, "set_entry_point", branch_def_id=bid, node_id="capture")

    for fname, ftype, default in (
        ("raw_recipe", "str", ""),
        ("category", "str", ""),
        ("archived", "bool", "false"),
    ):
        r = _call(
            us, "add_state_field",
            branch_def_id=bid, field_name=fname,
            field_type=ftype, field_default=default,
        )
        assert r["status"] == "added"

    validated = _call(us, "validate_branch", branch_def_id=bid)
    assert validated["valid"] is True, validated

    described = _call(us, "describe_branch", branch_def_id=bid)
    assert described["valid"] is True
    assert "recipe tracker" in described["summary"].lower()
    assert "capture" in described["summary"]
    assert "run_branch" in described["summary"]

    # Ledger was appended — we made 1 create + 3 add_node + 4 connect_nodes
    # + 1 set_entry_point + 3 add_state_field = 12 write ops
    ledger_path = base / "ledger.json"
    assert ledger_path.exists()
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    actions = [e["action"] for e in ledger]
    assert actions.count("create_branch") == 1
    assert actions.count("add_node") == 3
    assert actions.count("connect_nodes") == 4
    assert actions.count("set_entry_point") == 1
    assert actions.count("add_state_field") == 3


def test_ledger_attribution_uses_current_actor(branch_env):
    us, base = branch_env
    os.environ["UNIVERSE_SERVER_USER"] = "alice"
    try:
        _call(us, "create_branch", name="alice's branch")
    finally:
        os.environ["UNIVERSE_SERVER_USER"] = "tester"

    ledger = json.loads((base / "ledger.json").read_text(encoding="utf-8"))
    assert any(
        e["action"] == "create_branch" and e["actor"] == "alice"
        for e in ledger
    )


def test_read_actions_do_not_hit_ledger(branch_env):
    us, base = branch_env
    bid = _call(us, "create_branch", name="X")["branch_def_id"]
    _call(us, "get_branch", branch_def_id=bid)
    _call(us, "list_branches")
    _call(us, "validate_branch", branch_def_id=bid)
    _call(us, "describe_branch", branch_def_id=bid)

    ledger = json.loads((base / "ledger.json").read_text(encoding="utf-8"))
    # Only the create_branch should be logged
    assert len(ledger) == 1
    assert ledger[0]["action"] == "create_branch"


def test_unknown_action_returns_error_with_catalog(branch_env):
    us, _ = branch_env
    result = _call(us, "flimflam")
    assert "error" in result
    avail = result.get("available_actions", [])
    assert "create_branch" in avail
    assert "describe_branch" in avail
    assert "register" in avail  # Legacy node registration still listed


def test_missing_branch_id_returns_error(branch_env):
    us, _ = branch_env
    for action in (
        "get_branch", "validate_branch", "describe_branch",
        "delete_branch", "set_entry_point", "add_state_field",
        "connect_nodes", "add_node",
    ):
        result = _call(us, action)
        assert "error" in result, f"action {action} accepted empty id"


def test_describe_branch_returns_mermaid_flowchart(branch_env):
    """Claude.ai auto-renders fenced mermaid blocks. Verify the block shape."""
    us, _ = branch_env
    bid = _call(us, "create_branch", name="Recipe tracker")["branch_def_id"]
    _call(us, "add_node", branch_def_id=bid,
          node_id="capture", display_name="Capture raw recipe",
          prompt_template="...")
    _call(us, "add_node", branch_def_id=bid,
          node_id="archive", display_name="Archive to library",
          prompt_template="...")
    _call(us, "connect_nodes", branch_def_id=bid,
          from_node="START", to_node="capture")
    _call(us, "connect_nodes", branch_def_id=bid,
          from_node="capture", to_node="archive")
    _call(us, "connect_nodes", branch_def_id=bid,
          from_node="archive", to_node="END")
    _call(us, "set_entry_point", branch_def_id=bid, node_id="capture")

    described = _call(us, "describe_branch", branch_def_id=bid)
    mermaid = described["mermaid"]
    assert mermaid.startswith("```mermaid\nflowchart")
    assert mermaid.endswith("```")
    # Nodes referenced by id
    assert 'capture["Capture raw recipe"]' in mermaid
    assert 'archive["Archive to library"]' in mermaid
    # Edges rendered as arrows
    assert "START --> capture" in mermaid
    assert "capture --> archive" in mermaid
    assert "archive --> END" in mermaid
    # Entry point is highlighted
    assert "class capture entry" in mermaid
    # Summary also contains the mermaid block so markdown clients render it
    assert "```mermaid" in described["summary"]


def test_describe_empty_branch_still_emits_mermaid(branch_env):
    """Even a zero-node branch returns a valid mermaid skeleton (START+END)."""
    us, _ = branch_env
    bid = _call(us, "create_branch", name="Empty")["branch_def_id"]

    described = _call(us, "describe_branch", branch_def_id=bid)
    mermaid = described["mermaid"]
    assert "flowchart" in mermaid
    assert "START" in mermaid
    assert "END" in mermaid


def test_mermaid_label_escapes_quotes_and_newlines(branch_env):
    """Quotes and newlines in display_name must not break the mermaid block."""
    us, _ = branch_env
    bid = _call(us, "create_branch", name="Edge cases")["branch_def_id"]
    _call(us, "add_node", branch_def_id=bid,
          node_id="weird", display_name='Node with "quotes" and\nnewline',
          prompt_template="...")

    described = _call(us, "describe_branch", branch_def_id=bid)
    mermaid = described["mermaid"]
    # Double quote replaced with single quote inside the label
    assert '"quotes"' not in mermaid
    assert "'quotes'" in mermaid
    # Newline in label collapsed to space, not a real newline breaking syntax
    assert "Node with 'quotes' and newline" in mermaid
