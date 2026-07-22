"""Phase 6.2.2 — Branch visibility filter.

Covers task #25 / Path A:

1. Default visibility is 'public' (including legacy rows with no
   visibility column).
2. Explicit 'private' is persisted through save + update paths.
3. `list_branch_definitions` filters private Branches to the owner
   unless `include_private=True` is set.
4. `gates.list_claims` hides claims whose Branch is private from
   non-owners; owner still sees own private.
5. `gates.leaderboard` same contract as list_claims.
6. Private Branch on public Goal is a valid state (independent axes).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def base_path(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("TINYASSETS_GATES_ENABLED", "1")
    from tinyassets.daemon_server import initialize_author_server
    initialize_author_server(base)
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)
    yield base


def _make_branch_row(**overrides) -> dict:
    base = {
        "branch_def_id": overrides.get("branch_def_id", "b-test"),
        "name": overrides.get("name", "Test branch"),
        "description": "",
        "author": overrides.get("author", "alice"),
        "domain_id": "workflow",
        "tags": [],
        "version": 1,
        "parent_def_id": None,
        "entry_point": "",
        "graph_nodes": [],
        "edges": [],
        "conditional_edges": [],
        "node_defs": [],
        "state_schema": [],
        "published": False,
        "stats": {},
    }
    base.update(overrides)
    return base


# ─── default public ──────────────────────────────────────────────────


def test_default_visibility_is_public(base_path):
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    saved = save_branch_definition(
        base_path, branch_def=_make_branch_row(branch_def_id="b1"),
    )
    assert saved["visibility"] == "public"

    reloaded = get_branch_definition(base_path, branch_def_id="b1")
    assert reloaded["visibility"] == "public"


def test_explicit_private_round_trips(base_path):
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    saved = save_branch_definition(
        base_path,
        branch_def=_make_branch_row(branch_def_id="b2", visibility="private"),
    )
    assert saved["visibility"] == "private"
    assert get_branch_definition(base_path, branch_def_id="b2")["visibility"] == "private"


def test_unknown_visibility_normalizes_to_public(base_path):
    from tinyassets.daemon_server import save_branch_definition

    saved = save_branch_definition(
        base_path,
        branch_def=_make_branch_row(branch_def_id="b3", visibility="weird"),
    )
    assert saved["visibility"] == "public"


# ─── update ──────────────────────────────────────────────────────────


def test_update_visibility_public_to_private(base_path):
    from tinyassets.daemon_server import (
        save_branch_definition,
        update_branch_definition,
    )

    save_branch_definition(
        base_path, branch_def=_make_branch_row(branch_def_id="b4"),
    )
    updated = update_branch_definition(
        base_path,
        branch_def_id="b4",
        updates={"visibility": "private"},
    )
    assert updated["visibility"] == "private"


# ─── list filter ─────────────────────────────────────────────────────


def test_list_branch_definitions_hides_others_private(base_path):
    from tinyassets.daemon_server import (
        list_branch_definitions,
        save_branch_definition,
    )

    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-public", author="alice", visibility="public",
        ),
    )
    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-bob-priv", author="bob", visibility="private",
        ),
    )
    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-alice-priv", author="alice", visibility="private",
        ),
    )

    # Alice sees: public + own private (2)
    alice_view = list_branch_definitions(base_path, viewer="alice")
    ids = {r["branch_def_id"] for r in alice_view}
    assert ids == {"b-public", "b-alice-priv"}

    # Bob sees: public + own private (2)
    bob_view = list_branch_definitions(base_path, viewer="bob")
    ids = {r["branch_def_id"] for r in bob_view}
    assert ids == {"b-public", "b-bob-priv"}

    # No viewer: strictly public (1)
    anon_view = list_branch_definitions(base_path)
    ids = {r["branch_def_id"] for r in anon_view}
    assert ids == {"b-public"}

    # include_private=True: all 3 (host mode)
    all_view = list_branch_definitions(base_path, include_private=True)
    ids = {r["branch_def_id"] for r in all_view}
    assert ids == {"b-public", "b-bob-priv", "b-alice-priv"}


# ─── gates.list_claims + leaderboard ─────────────────────────────────


def _seed_claims_for_filter_tests(base_path: Path):
    """Seed a Goal + 2 Branches (1 public, 1 private-bob) + 1 claim
    each on the same rung. Returns (goal_id, bids, rung_key)."""
    from tinyassets.daemon_server import claim_gate, save_branch_definition, save_goal

    goal_saved = save_goal(base_path, goal={
        "goal_id": "g-vis",
        "name": "Visibility test goal",
        "description": "",
        "author": "alice",
        "visibility": "public",
        "tags": [],
        "gate_ladder": [{"rung_key": "peer_reviewed", "label": "Peer reviewed"}],
    })
    gid = goal_saved["goal_id"]
    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="bp", author="alice", visibility="public",
            goal_id=gid,
        ),
    )
    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="bpr", author="bob", visibility="private",
            goal_id=gid,
        ),
    )
    claim_gate(
        base_path,
        branch_def_id="bp",
        goal_id=gid,
        rung_key="peer_reviewed",
        evidence_url="https://example.invalid/p",
        evidence_note="",
        claimed_by="alice",
    )
    claim_gate(
        base_path,
        branch_def_id="bpr",
        goal_id=gid,
        rung_key="peer_reviewed",
        evidence_url="https://example.invalid/pr",
        evidence_note="",
        claimed_by="bob",
    )
    return gid


def test_list_claims_hides_private_branch_from_non_owner(
    base_path, monkeypatch,
):
    gid = _seed_claims_for_filter_tests(base_path)
    # Alice looks (non-owner of the private Branch).
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)

    result = json.loads(mkt._action_gates_list_claims({"goal_id": gid}))
    assert result["status"] == "ok"
    bids = {c["branch_def_id"] for c in result["claims"]}
    assert bids == {"bp"}
    assert result["count"] == 1


def test_list_claims_shows_own_private_to_owner(base_path, monkeypatch):
    gid = _seed_claims_for_filter_tests(base_path)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)

    result = json.loads(mkt._action_gates_list_claims({"goal_id": gid}))
    assert result["status"] == "ok"
    bids = {c["branch_def_id"] for c in result["claims"]}
    assert bids == {"bp", "bpr"}


def test_leaderboard_hides_private_branch_from_non_owner(
    base_path, monkeypatch,
):
    gid = _seed_claims_for_filter_tests(base_path)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)

    result = json.loads(mkt._action_gates_leaderboard({"goal_id": gid}))
    assert result["status"] == "ok"
    bids = {e["branch_def_id"] for e in result["entries"]}
    assert bids == {"bp"}


def test_leaderboard_shows_own_private_to_owner(base_path, monkeypatch):
    gid = _seed_claims_for_filter_tests(base_path)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)

    result = json.loads(mkt._action_gates_leaderboard({"goal_id": gid}))
    assert result["status"] == "ok"
    bids = {e["branch_def_id"] for e in result["entries"]}
    assert bids == {"bp", "bpr"}


# ─── private Branch on public Goal is valid ──────────────────────────


def test_private_branch_on_public_goal_is_visible_to_owner(
    base_path, monkeypatch,
):
    """The collision case planner flagged: a private Branch bound to
    a public Goal. Owner sees their own claim; other users don't."""
    from tinyassets.daemon_server import (
        claim_gate,
        get_goal,
        save_branch_definition,
        save_goal,
    )

    goal_saved = save_goal(base_path, goal={
        "goal_id": "g-public",
        "name": "Public goal",
        "description": "",
        "author": "alice",
        "visibility": "public",
        "tags": [],
        "gate_ladder": [{"rung_key": "peer_reviewed", "label": "Peer reviewed"}],
    })
    assert get_goal(base_path, goal_id=goal_saved["goal_id"])["visibility"] == "public"

    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-secret", author="bob", visibility="private",
            goal_id=goal_saved["goal_id"],
        ),
    )
    claim_gate(
        base_path,
        branch_def_id="b-secret",
        goal_id=goal_saved["goal_id"],
        rung_key="peer_reviewed",
        evidence_url="https://example.invalid/secret",
        evidence_note="",
        claimed_by="bob",
    )

    # Bob owns it — sees his claim on the public leaderboard.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)
    r = json.loads(mkt._action_gates_leaderboard({"goal_id": "g-public"}))
    assert any(e["branch_def_id"] == "b-secret" for e in r["entries"])

    # Alice doesn't own it — doesn't see it, even though the Goal is public.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    importlib.reload(mkt)
    importlib.reload(br)
    r2 = json.loads(mkt._action_gates_leaderboard({"goal_id": "g-public"}))
    assert not any(e["branch_def_id"] == "b-secret" for e in r2["entries"])


# ─── MCP branch.create + branch.get ──────────────────────────────────


def test_branch_create_accepts_visibility(base_path, monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)

    result = json.loads(br._ext_branch_create({
        "name": "My secret branch",
        "visibility": "private",
    }))
    assert result["status"] == "created"
    assert result["visibility"] == "private"


def test_branch_get_hides_private_from_non_owner(base_path, monkeypatch):
    from tinyassets.daemon_server import save_branch_definition

    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-hidden", author="bob", visibility="private",
        ),
    )

    # Alice probes for it.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)

    result = json.loads(br._ext_branch_get({"branch_def_id": "b-hidden"}))
    assert "error" in result
    assert "not found" in result["error"]

    # Bob can see it.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    importlib.reload(mkt)
    importlib.reload(br)
    result = json.loads(br._ext_branch_get({"branch_def_id": "b-hidden"}))
    assert result.get("branch_def_id") == "b-hidden"
    assert result.get("visibility") == "private"


# ─── leak coverage: goals.get + goals.common_nodes ────────────────────


def test_goal_get_hides_private_branch_from_non_owner(
    base_path, monkeypatch,
):
    """Verifier-flagged leak: `goals action=get` was returning the full
    Branch list including private rows. After Path A's viewer-aware
    `branches_for_goal`, non-owners must not see another user's
    private Branch on a shared public Goal.
    """
    from tinyassets.daemon_server import save_branch_definition, save_goal

    goal_saved = save_goal(base_path, goal={
        "goal_id": "g-leak",
        "name": "Leak test goal",
        "description": "",
        "author": "alice",
        "visibility": "public",
        "tags": [],
        "gate_ladder": [],
    })
    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-public-on-public",
            author="alice",
            visibility="public",
            goal_id=goal_saved["goal_id"],
        ),
    )
    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-private-on-public",
            author="bob",
            visibility="private",
            goal_id=goal_saved["goal_id"],
        ),
    )

    # Alice (non-owner of the private branch) hits goals.get with a resolved
    # request identity. The daemon environment is not an authorization source.
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    from tinyassets.api import permissions
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "alice")
    importlib.reload(mkt)
    importlib.reload(br)

    result = json.loads(mkt._action_goal_get({"goal_id": goal_saved["goal_id"]}))
    branch_ids = {b["branch_def_id"] for b in result.get("branches", [])}
    assert branch_ids == {"b-public-on-public"}, (
        "Alice must not see Bob's private branch on a public goal"
    )

    # Bob (owner of the private branch) hits goals.get — sees both.
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "bob")
    importlib.reload(mkt)
    importlib.reload(br)
    result = json.loads(mkt._action_goal_get({"goal_id": goal_saved["goal_id"]}))
    branch_ids = {b["branch_def_id"] for b in result.get("branches", [])}
    assert branch_ids == {"b-public-on-public", "b-private-on-public"}


def test_goal_common_nodes_hides_private_branch_from_non_owner(
    base_path, monkeypatch,
):
    """Verifier-flagged leak: `goals action=common_nodes` aggregates
    node_ids across all Branches under a Goal. Without filtering,
    `first_seen_in` and `branch_ids` would leak private Branch IDs.
    """
    from tinyassets.daemon_server import save_branch_definition, save_goal

    goal_saved = save_goal(base_path, goal={
        "goal_id": "g-cn",
        "name": "Common-nodes leak test",
        "description": "",
        "author": "alice",
        "visibility": "public",
        "tags": [],
        "gate_ladder": [],
    })
    # Both branches share a node_id 'shared_node'. Alice's is public,
    # Bob's is private. Common-nodes aggregation must omit Bob's
    # contribution from Alice's view.
    shared_node = {
        "node_id": "shared_node",
        "display_name": "Shared node",
    }
    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-cn-public",
            author="alice",
            visibility="public",
            goal_id=goal_saved["goal_id"],
            node_defs=[shared_node],
        ),
    )
    save_branch_definition(
        base_path,
        branch_def=_make_branch_row(
            branch_def_id="b-cn-private",
            author="bob",
            visibility="private",
            goal_id=goal_saved["goal_id"],
            node_defs=[shared_node],
        ),
    )

    # Alice asks. min_branches=1 so a single contributor surfaces.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    from tinyassets.api import branches as br
    from tinyassets.api import market as mkt
    importlib.reload(mkt)
    importlib.reload(br)
    result = json.loads(mkt._action_goal_common_nodes({
        "goal_id": goal_saved["goal_id"],
        "min_branches": 1,
        "scope": "this_goal",
    }))
    entries = result.get("entries", [])
    shared = next((e for e in entries if e["node_id"] == "shared_node"), None)
    assert shared is not None
    assert "b-cn-private" not in shared["branch_ids"], (
        "Alice's view must not leak Bob's private branch_def_id "
        "via common-nodes branch_ids"
    )
    assert shared["first_seen_in"] != "b-cn-private", (
        "first_seen_in must not point at a hidden private branch"
    )

    # Bob sees both contributions.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    importlib.reload(mkt)
    importlib.reload(br)
    result = json.loads(mkt._action_goal_common_nodes({
        "goal_id": goal_saved["goal_id"],
        "min_branches": 1,
        "scope": "this_goal",
    }))
    entries = result.get("entries", [])
    shared = next((e for e in entries if e["node_id"] == "shared_node"), None)
    assert shared is not None
    assert set(shared["branch_ids"]) == {"b-cn-public", "b-cn-private"}
