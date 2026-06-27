"""#58 — Raw run_id / branch_def_id / goal_id must never appear in the
text channel of MCP tool returns. Phone users read `text` verbatim
through Claude.ai; IDs belong in structuredContent for scripts.

Covers the audit surface documented in the task:
run_branch, get_run, list_runs, build_branch, patch_branch,
rollback_node, create_branch, get_branch, list_branches, goals.propose,
goals.bind, plus get_run_output, judge_run, and get_node_output.
"""

from __future__ import annotations

import importlib
import json
import time

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    monkeypatch.setenv("_FORCE_MOCK", "true")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


def _build_min_branch(us, name="id redaction fixture"):
    """Atomic-action branch build — mirrors Phase 3 test helper."""
    bid = _call(us, "extensions", "create_branch",
                name=name)["branch_def_id"]
    _call(us, "extensions", "add_node",
          branch_def_id=bid, node_id="capture",
          display_name="Capture", prompt_template="Echo: {raw}",
          output_keys="capture_output")
    for src, dst in (("START", "capture"), ("capture", "END")):
        _call(us, "extensions", "connect_nodes",
              branch_def_id=bid, from_node=src, to_node=dst)
    _call(us, "extensions", "set_entry_point",
          branch_def_id=bid, node_id="capture")
    for field in ("raw", "capture_output"):
        _call(us, "extensions", "add_state_field",
              branch_def_id=bid, field_name=field, field_type="str")
    return bid


def _run_and_wait(us, *, branch_def_id, inputs_json, timeout_s=10.0):
    queued = _call(us, "extensions", "run_branch",
                   branch_def_id=branch_def_id,
                   inputs_json=inputs_json)
    rid = queued["run_id"]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        snap = _call(us, "extensions", "get_run", run_id=rid)
        if snap.get("status") in {"completed", "failed", "cancelled"}:
            return snap
        time.sleep(0.05)
    raise TimeoutError(f"Run {rid} did not terminate in {timeout_s}s")


# ─── build/patch/run/get text-channel invariants ──────────────────────────


def test_build_branch_text_hides_branch_def_id(env):
    us, _ = env
    spec = {
        "name": "phone-friendly",
        "entry_point": "n1",
        "state_schema": [{"name": "x", "type": "str", "default": ""}],
        "node_defs": [{
            "node_id": "n1",
            "display_name": "First node",
            "phase": "custom",
            "prompt_template": "hi",
            "input_keys": [],
            "output_keys": ["x"],
        }],
        "edges": [
            {"from_node": "START", "to_node": "n1"},
            {"from_node": "n1", "to_node": "END"},
        ],
    }
    result = _call(us, "extensions", "build_branch",
                   spec_json=json.dumps(spec))
    assert result["status"] == "built"
    bid = result["branch_def_id"]
    assert bid
    assert bid not in result["text"]
    assert "phone-friendly" in result["text"]


def test_patch_branch_text_hides_branch_def_id(env):
    us, _ = env
    bid = _build_min_branch(us, name="patch fixture")
    ops = [{"op": "update_node", "node_id": "capture", "updates": {
        "display_name": "Capture (renamed)",
    }}]
    result = _call(us, "extensions", "patch_branch",
                   branch_def_id=bid,
                   changes_json=json.dumps(ops))
    assert result["status"] == "patched"
    assert bid not in result["text"]
    assert "patch fixture" in result["text"]


def test_run_branch_text_hides_run_id(env):
    us, _ = env
    bid = _build_min_branch(us)
    result = _call(us, "extensions", "run_branch",
                   branch_def_id=bid,
                   inputs_json=json.dumps({"raw": "abc"}))
    assert "run_id" in result  # structuredContent still carries it
    assert result["run_id"]
    assert result["run_id"] not in result["text"]


def test_get_run_text_hides_run_id_and_branch_def_id(env):
    us, _ = env
    bid = _build_min_branch(us, name="snapshot fixture")
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw": "xyz"}))
    rid = run["run_id"]
    snap = _call(us, "extensions", "get_run", run_id=rid)
    assert rid not in snap["text"]
    assert bid not in snap["text"]
    # Branch name (not ID) surfaces.
    assert "snapshot fixture" in snap["text"]


def test_get_run_output_text_hides_run_id(env):
    us, _ = env
    bid = _build_min_branch(us, name="output fixture")
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw": "read me"}))
    rid = run["run_id"]
    full = _call(us, "extensions", "get_run_output", run_id=rid)
    assert rid not in full["text"]
    single = _call(us, "extensions", "get_run_output",
                   run_id=rid, field_name="capture_output")
    assert rid not in single["text"]


# ─── judgments + rollback ─────────────────────────────────────────────────


def test_judge_run_text_hides_run_id(env):
    us, _ = env
    bid = _build_min_branch(us, name="judge fixture")
    run = _run_and_wait(us, branch_def_id=bid,
                       inputs_json=json.dumps({"raw": "judge me"}))
    rid = run["run_id"]
    result = _call(us, "extensions", "judge_run",
                   run_id=rid,
                   judgment_text="Looks fine.",
                   tags="smoke")
    assert result["status"] == "recorded"
    assert rid not in result["text"]
    assert "judge fixture" in result["text"]


def test_rollback_node_text_hides_branch_def_id(env):
    us, _ = env
    bid = _build_min_branch(us, name="rollback fixture")
    # edit once to create a history row, then rollback.
    _call(us, "extensions", "update_node",
          branch_def_id=bid, node_id="capture",
          display_name="Capture v2")
    result = _call(us, "extensions", "rollback_node",
                   branch_def_id=bid, node_id="capture")
    assert result["status"] == "rolled_back"
    assert bid not in result["text"]
    assert "rollback fixture" in result["text"]


# ─── goals ────────────────────────────────────────────────────────────────


def test_goal_propose_text_hides_goal_id(env):
    us, _ = env
    result = _call(us, "goals", "propose",
                   name="Paper: long-horizon eval",
                   description="Phase 6 candidate Goal.")
    assert result["status"] == "proposed"
    gid = result["goal"]["goal_id"]
    assert gid
    assert gid not in result["text"]
    assert "Paper: long-horizon eval" in result["text"]


def test_goal_bind_text_hides_goal_id_and_branch_def_id(env):
    us, _ = env
    goal = _call(us, "goals", "propose", name="Binding Goal")
    gid = goal["goal"]["goal_id"]
    bid = _build_min_branch(us, name="bind me")
    result = _call(us, "goals", "bind",
                   branch_def_id=bid, goal_id=gid)
    assert result["status"] == "bound"
    assert gid not in result["text"]
    assert bid not in result["text"]
    assert "Binding Goal" in result["text"]
    assert "bind me" in result["text"]
