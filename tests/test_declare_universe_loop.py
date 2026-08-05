"""End-to-end check: an existing universe can declare a Loop branch after birth."""
from __future__ import annotations
import importlib, json
from pathlib import Path
import pytest


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, authenticate_request):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    authenticate_request("tester", capabilities=[
        "tinyassets.extensions.read", "tinyassets.extensions.write",
        "tinyassets.extensions.admin", "tinyassets.universe.read",
        "tinyassets.universe.write", "tinyassets.universe.admin",
        "tinyassets.universe.costly",
    ])
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _build_branch(us) -> str:
    spec = {
        "name": "loop-branch",
        "entry_point": "step",
        "state_schema": [{"name": "x", "type": "str"}, {"name": "y", "type": "str"}],
        "node_defs": [{"node_id": "step", "display_name": "Step", "phase": "draft",
                       "prompt_template": "do {x}", "input_keys": ["x"], "output_keys": ["y"]}],
        "edges": [{"from": "step", "to": "END"}],
    }
    res = json.loads(us.extensions(action="build_branch", spec_json=json.dumps(spec)))
    assert res["status"] == "built", res
    return res["branch_def_id"]


def _birth(us) -> str:
    """Birth assigns its own opaque id; a caller-selected one is rejected."""
    created = json.loads(us.write_graph(target="universe", text="test account"))
    assert not created.get("error"), created
    uid = created.get("universe_id") or created.get("graph_id")
    assert uid, created
    return uid


def test_existing_universe_can_declare_a_loop_after_birth(env):
    us, base = env
    uid = _birth(us)

    # Before: no loop declared.
    from tinyassets.universe_soul import read_universe_soul
    soul = read_universe_soul(base / uid)
    assert soul is not None
    assert not soul.loop_branch_def_id, "fresh universe should have no loop"

    bid = _build_branch(us)
    out = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id=bid,
    ))
    assert not out.get("error"), out
    assert out["status"] == "declared"
    assert out["loop_dispatch"]["declared"] is True
    assert out["loop_dispatch"]["branch_def_id"] == bid

    # It persisted to the soul.
    assert read_universe_soul(base / uid).loop_branch_def_id == bid


def test_declaring_an_unknown_branch_is_refused(env):
    us, base = env
    uid = _birth(us)
    out = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid,
        branch_id="ffffffffffff",
    ))
    assert out.get("error") == "branch_not_found", out


def test_plain_universe_write_still_creates_and_declares_nothing(env):
    """The birth path must keep working and must not gain a loop by accident."""
    us, base = env
    uid = _birth(us)
    from tinyassets.universe_soul import read_universe_soul
    assert not read_universe_soul(base / uid).loop_branch_def_id
