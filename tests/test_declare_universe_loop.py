"""End-to-end check: an existing universe can declare a Loop branch after birth."""
from __future__ import annotations

import importlib
import json
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


def test_declare_loop_is_gated_as_a_write(env):
    """`declare_universe_loop` must be a WRITE, not a read.

    Regression guard for a hole I nearly shipped. `_request_universe` is a
    RESOLVER, not an authorizer — "an explicit id wins", with no ownership
    check. So an action that takes a caller-supplied `universe_id` and mutates
    soul.md is a cross-tenant write primitive unless the central
    universe-access gate treats it as a write. That gate keys off
    WRITE_ACTIONS, which the module calls the single source of truth.

    If this membership is dropped, the action is gated at READ strength while
    still mutating another founder's soul.
    """
    us, _base = env
    from tinyassets.api import universe as api

    assert "declare_universe_loop" in api.WRITE_ACTIONS, (
        "declare_universe_loop must be in WRITE_ACTIONS or the universe-access "
        "gate checks it at read strength while it mutates soul.md"
    )
    assert "declare_universe_loop" in api.UNIVERSE_ACTIONS


def test_declare_loop_refuses_a_universe_the_caller_cannot_write(env, monkeypatch):
    """An explicit universe_id must not bypass the access gate."""
    us, base = env
    uid = _birth(us)
    bid = _build_branch(us)

    from tinyassets.api import permissions

    monkeypatch.setattr(
        permissions, "universe_access_allows", lambda _uid, write=False: not write
    )
    out = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id=bid,
    ))
    assert out.get("error"), f"expected refusal, got {out}"

    from tinyassets.universe_soul import read_universe_soul
    soul = read_universe_soul(base / uid)
    assert soul is not None
    assert not soul.loop_branch_def_id, "refused call must not have mutated soul.md"


def test_clearing_a_loop_actually_clears_it(env):
    """Clearing must clear, not silently report success.

    `write_universe_soul` treats a blank `loop_branch_def_id` as "leave alone"
    — like every other field — so the first version of this action reported
    status "cleared" while the declaration remained. Found by cross-family
    review 2026-08-05.
    """
    us, base = env
    uid = _birth(us)
    bid = _build_branch(us)
    from tinyassets.universe_soul import read_universe_soul

    json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id=bid,
    ))
    assert read_universe_soul(base / uid).loop_branch_def_id == bid

    out = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id="",
    ))
    assert not out.get("error"), out
    assert out["status"] == "cleared"
    assert out["loop_dispatch"]["declared"] is False
    # The claim must match the disk.
    assert not read_universe_soul(base / uid).loop_branch_def_id, (
        "reported cleared but soul.md still carries a loop declaration"
    )


def test_another_authors_private_branch_cannot_become_my_loop(env, monkeypatch):
    """A private branch owned by someone else must not bind, and must not leak.

    The raw `get_branch_definition` ignores author/visibility, so using it made
    any KNOWN private id succeed (unauthorized binding) while an unknown id
    returned branch_not_found — a cross-tenant existence oracle. The action must
    go through the authority-aware resolver instead.
    """
    us, base = env
    uid = _birth(us)
    bid = _build_branch(us)

    # Re-label the branch as another author's private branch.
    from tinyassets.daemon_server import _connect
    with _connect(str(base)) as conn:
        conn.execute(
            "UPDATE branch_definitions SET author = ?, visibility = ? "
            "WHERE branch_def_id = ?",
            ("someone-else", "private", bid),
        )
        conn.commit()

    out = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id=bid,
    ))
    assert out.get("error") == "branch_not_found", (
        f"another author's private branch must not bind, got {out}"
    )

    from tinyassets.universe_soul import read_universe_soul
    assert not read_universe_soul(base / uid).loop_branch_def_id


def test_declaring_a_loop_makes_the_universe_servable(env):
    """A declared loop must also register a project-loop daemon.

    soul.md says WHICH branch the loop runs. It does not make the universe
    servable: `cloud_worker._register_worker_runtime` calls
    `select_project_loop_daemon(base, universe_id=...)`, and a None result makes
    the worker skip runtime registration and return — silently, because
    registration is best-effort. Observed live on 2026-08-05: the universe held
    valid queued work with `runtime_instance_count: 0` and nothing claiming it.
    """
    us, base = env
    uid = _birth(us)
    bid = _build_branch(us)
    from tinyassets.daemon_registry import select_project_loop_daemon

    assert select_project_loop_daemon(str(base), universe_id=uid) is None

    out = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id=bid,
    ))
    assert not out.get("error"), out
    assert out["loop_daemon"]["serving"] is True, out

    daemon = select_project_loop_daemon(str(base), universe_id=uid)
    assert daemon is not None, "declared loop left the universe unservable"
    assert daemon["metadata"]["universe_id"] == uid
    assert daemon["has_soul"]


def test_declaring_twice_reuses_the_same_loop_daemon(env):
    """Re-declaring must not accumulate duplicate loop daemons."""
    us, base = env
    uid = _birth(us)
    bid = _build_branch(us)
    from tinyassets.daemon_registry import select_project_loop_daemon

    first = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id=bid,
    ))
    second = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id=bid,
    ))
    assert first["loop_daemon"]["daemon_id"] == second["loop_daemon"]["daemon_id"]
    assert select_project_loop_daemon(str(base), universe_id=uid) is not None


def test_a_loop_daemon_is_scoped_to_its_own_universe(env):
    """Universe A's loop daemon must not serve universe B."""
    us, base = env
    uid_a = _birth(us)
    bid = _build_branch(us)
    json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid_a, branch_id=bid,
    ))
    uid_b = _birth(us)

    from tinyassets.daemon_registry import select_project_loop_daemon
    assert select_project_loop_daemon(str(base), universe_id=uid_a) is not None
    assert select_project_loop_daemon(str(base), universe_id=uid_b) is None


def test_declare_loop_requires_costly_authority(env):
    """Creating a daemon must cost what daemon_create costs.

    Cross-family review 2026-08-05: `declare_universe_loop` registers a
    project-loop daemon, and `cloud_worker` uses that flag to select the daemon,
    register runtime authority and produce work. Explicit `daemon_create` is in
    _UNIVERSE_COSTLY_ACTIONS. A route that creates a daemon while requiring only
    universe.write lets a principal with no costly grant provision an executable
    daemon — privilege escalation through an ordinary write.
    """
    from tinyassets.auth import provider as auth_provider

    assert "declare_universe_loop" in auth_provider._UNIVERSE_COSTLY_ACTIONS
    assert "daemon_create" in auth_provider._UNIVERSE_COSTLY_ACTIONS


def test_loop_daemon_dedupe_is_owner_scoped(env):
    """A daemon planted by another owner must not be adopted as mine.

    `select_project_loop_daemon` is PERMISSIVE — without owner_user_id it
    accepts any daemon flagged for the universe. Using it as a restrictive
    dedupe would let a writer plant a default and have the owner's later
    declaration silently adopt it while reporting serving:true.
    """
    us, base = env
    uid = _birth(us)
    bid = _build_branch(us)

    from tinyassets.daemon_registry import (
        PROJECT_LOOP_FLAG,
        create_daemon,
        select_project_loop_daemon,
    )

    planted = create_daemon(
        str(base),
        display_name="planted by someone else",
        created_by="someone-else",
        soul_mode="soul",
        soul_text="planted",
        metadata={
            "universe_id": uid,
            PROJECT_LOOP_FLAG: True,
            "owner_user_id": "someone-else",
        },
    )
    # The permissive selector sees it...
    assert select_project_loop_daemon(str(base), universe_id=uid) is not None

    out = json.loads(us.write_graph(
        target="universe", operation="declare_loop", graph_id=uid, branch_id=bid,
    ))
    assert not out.get("error"), out
    # ...but the declaration must NOT adopt another owner's daemon.
    assert out["loop_daemon"]["daemon_id"] != planted["daemon_id"], (
        "adopted a project-loop daemon owned by a different principal"
    )
