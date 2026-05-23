"""PR-123 round-2 auth-boundary regression guards.

Codex's round-1 review on PR #970 caught two real P1 issues:

  P1.1 — Caller-controlled visibility leak. ``extensions.py`` mapped
         caller-supplied ``author`` to ``viewer`` and ``force`` to
         ``include_private``. A chatbot calling
         ``extensions action=quality_leaderboard author=alice`` saw
         alice's private branches; ``force=true`` returned every row.

  P1.2 — Fork-count signal leaked private descendant existence. The
         leaderboard hid private fork rows from the entry list but
         the public parent's ``fork_count`` aggregate still counted
         them, so the third-party viewer could infer the private
         fork's existence.

These tests lock in the fix and serve as the regression gate for any
future signal that aggregates over rows.

Threat model:
  * actor_alice  — author of one private branch ``priv-alice``.
  * actor_bob    — author of one public branch ``pub-bob`` plus one
                   private fork ``priv-bob-fork`` of a public peer.
  * actor_eve    — third party. Default test caller — should NEVER
                   see alice's or bob's private rows.
"""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_selector_passthrough(monkeypatch):
    """DESIGN-008 — pass-through selector mock for auth-boundary tests.

    The auth-boundary tests in this file probe the substrate's
    visibility filter at the leaderboard layer. Under DESIGN-008,
    leaderboard production requires a selector dispatch (one LLM
    call). These tests don't need to exercise selector behavior —
    only the candidate-set visibility filter. So we monkeypatch
    ``dispatch_selector`` to pass the candidate list straight
    through as ``ranked_entries`` (preserving input order, score
    0.0). The substrate's filter (already applied via
    ``list_branch_definitions`` + ``_fork_count`` before dispatch)
    is what's under test.
    """
    def _passthrough(
        base_path,
        *,
        goal_id,
        candidate_branches,
        actor="anonymous",
        timeout_s=None,
        **_extra,
    ):
        return {
            "ok": True,
            "branch_version_id": "mock_selector@authtest",
            "source": "platform_default",
            "run_id": "mock-run",
            "ranked_entries": [
                {
                    "branch_def_id": c["branch_def_id"],
                    "branch_version_id": c.get("branch_version_id", ""),
                    "score": 0.0,
                    "rationale": "passthrough",
                }
                for c in candidate_branches
            ],
        }
    monkeypatch.setattr(
        "workflow.api.quality_leaderboard.dispatch_selector",
        _passthrough,
    )


@pytest.fixture
def us_env(tmp_path: Path, monkeypatch):
    """Daemon env where the calling actor is ``eve`` by default."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "eve")
    from workflow import universe_server as us
    importlib.reload(us)
    yield us, tmp_path
    importlib.reload(us)


def _call(us, action: str, **kwargs) -> dict:
    return json.loads(us.extensions(action=action, **kwargs))


def _seed_universe(base: Path) -> dict:
    """Populate the storage layer with the threat-model seed.

    Returns a dict of useful ids: {goal_id, pub_eve, pub_bob,
    priv_alice, priv_bob_fork, child_of_pub_bob}.
    """
    from workflow.daemon_server import (
        initialize_author_server,
        save_branch_definition,
        save_goal,
    )
    initialize_author_server(base)
    save_goal(
        base,
        goal=dict(
            goal_id="g-test",
            name="Shared Goal",
            description="",
            author="host",
            tags=[],
            visibility="public",
        ),
    )
    # Public branch authored by eve.
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id="pub-eve",
            name="Eve's public take",
            description="",
            author="eve",
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id="g-test",
            visibility="public",
        ),
    )
    # Public branch authored by bob — this is the leak target for P1.2.
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id="pub-bob",
            name="Bob's public take",
            description="",
            author="bob",
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id="g-test",
            visibility="public",
        ),
    )
    # Private branch authored by alice.
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id="priv-alice",
            name="Alice's PRIVATE take",
            description="",
            author="alice",
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id="g-test",
            visibility="private",
        ),
    )
    # Private fork of pub-bob authored by alice. Exists to test P1.2:
    # eve should NOT see this row, and the fork_count aggregate must
    # not reveal its existence either.
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id="priv-bob-fork",
            name="Alice's PRIVATE fork of Bob's take",
            description="",
            author="alice",
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id="g-test",
            visibility="private",
            parent_def_id="pub-bob",
        ),
    )
    # Public fork of pub-bob authored by eve. Visible to everyone —
    # the leaderboard should count this in fork_count regardless of
    # the viewer.
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id="pub-bob-public-fork",
            name="Eve's public fork of Bob's take",
            description="",
            author="eve",
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id="g-test",
            visibility="public",
            parent_def_id="pub-bob",
        ),
    )
    return {
        "goal_id": "g-test",
        "pub_eve": "pub-eve",
        "pub_bob": "pub-bob",
        "priv_alice": "priv-alice",
        "priv_bob_fork": "priv-bob-fork",
        "pub_bob_public_fork": "pub-bob-public-fork",
    }


# ---------------------------------------------------------------------------
# P1.1 — caller cannot impersonate another viewer
# ---------------------------------------------------------------------------


def test_default_caller_sees_only_public_and_owned_rows(us_env):
    """Baseline: eve (the calling actor) sees public + owned rows.
    Alice's + Bob's private rows are filtered out."""
    us, base = us_env
    _seed_universe(base)
    result = _call(us, "quality_leaderboard", goal_id="g-test")
    bids = {e["branch_def_id"] for e in result["entries"]}
    # Eve owns no private rows; she sees only the 3 public rows.
    assert bids == {"pub-eve", "pub-bob", "pub-bob-public-fork"}
    assert "priv-alice" not in bids
    assert "priv-bob-fork" not in bids


def test_caller_supplied_author_kwarg_does_not_grant_alices_visibility(us_env):
    """P1.1 adversarial — eve passes ``author='alice'`` hoping to read
    alice's private branches. The handler MUST ignore the caller-named
    identity and use the daemon-side actor (eve)."""
    us, base = us_env
    _seed_universe(base)
    result = _call(
        us, "quality_leaderboard", goal_id="g-test", author="alice",
    )
    bids = {e["branch_def_id"] for e in result["entries"]}
    # Same as the baseline — author=alice MUST NOT change visibility.
    assert "priv-alice" not in bids
    assert "priv-bob-fork" not in bids
    assert bids == {"pub-eve", "pub-bob", "pub-bob-public-fork"}


def test_caller_supplied_force_does_not_grant_all_private_rows(us_env):
    """P1.1 adversarial — eve passes ``force=true`` hoping to bypass
    visibility. The handler MUST ignore force for visibility."""
    us, base = us_env
    _seed_universe(base)
    result = _call(
        us, "quality_leaderboard", goal_id="g-test", force=True,
    )
    bids = {e["branch_def_id"] for e in result["entries"]}
    assert "priv-alice" not in bids
    assert "priv-bob-fork" not in bids


def test_caller_supplied_force_and_author_combined_is_still_filtered(us_env):
    """P1.1 adversarial — the combination round-1 used to surface all
    of alice's privates (author=alice + force=true). Both ignored."""
    us, base = us_env
    _seed_universe(base)
    result = _call(
        us, "quality_leaderboard",
        goal_id="g-test", author="alice", force=True,
    )
    bids = {e["branch_def_id"] for e in result["entries"]}
    assert "priv-alice" not in bids
    assert "priv-bob-fork" not in bids


def test_owner_sees_own_private_rows(us_env, monkeypatch):
    """Owner exception — alice running as the daemon-side actor DOES
    see her own private rows (this is the legitimate visibility path
    the caller-spoofing attack was trying to abuse)."""
    us, base = us_env
    _seed_universe(base)
    # Reload the daemon as alice.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    importlib.reload(us)
    try:
        result = _call(us, "quality_leaderboard", goal_id="g-test")
        bids = {e["branch_def_id"] for e in result["entries"]}
        # Alice sees the 3 public rows + her own 2 private rows.
        assert bids == {
            "pub-eve", "pub-bob", "pub-bob-public-fork",
            "priv-alice", "priv-bob-fork",
        }
    finally:
        importlib.reload(us)


def test_recommended_parent_for_fork_inherits_same_visibility(us_env):
    """The recommended-parent action shares the visibility surface;
    eve cannot reach a private branch via the rationale path either."""
    us, base = us_env
    _seed_universe(base)
    result = _call(
        us, "recommended_parent_for_fork",
        goal_id="g-test", author="alice", force=True,
    )
    parent = result.get("recommended_parent")
    if parent is not None:
        assert parent["branch_def_id"] != "priv-alice"
        assert parent["branch_def_id"] != "priv-bob-fork"


# ---------------------------------------------------------------------------
# P1.2 — fork_count must respect viewer visibility
# ---------------------------------------------------------------------------


def test_fork_count_excludes_private_forks_for_third_party_viewer(us_env):
    """P1.2 adversarial — pub-bob has TWO descendants on disk
    (priv-bob-fork by alice, pub-bob-public-fork by eve). Eve (third
    party) should only see the public one count toward fork_count.
    A naive raw count would expose the existence of priv-bob-fork."""
    us, base = us_env
    _seed_universe(base)
    result = _call(us, "quality_leaderboard", goal_id="g-test")
    pub_bob_entry = next(
        e for e in result["entries"] if e["branch_def_id"] == "pub-bob"
    )
    assert pub_bob_entry["signals"]["fork_count"] == 1, (
        "fork_count must exclude private forks the viewer cannot see "
        "(P1.2 leak — exposed private descendant existence)"
    )


def test_fork_count_includes_owned_private_forks_for_owner(us_env, monkeypatch):
    """Owner exception — alice running as the daemon-side actor sees
    her private fork count toward pub-bob's fork_count (2 forks: her
    private + eve's public)."""
    us, base = us_env
    _seed_universe(base)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    importlib.reload(us)
    try:
        result = _call(us, "quality_leaderboard", goal_id="g-test")
        pub_bob_entry = next(
            e for e in result["entries"]
            if e["branch_def_id"] == "pub-bob"
        )
        assert pub_bob_entry["signals"]["fork_count"] == 2
    finally:
        importlib.reload(us)


def test_fork_count_unit_at_storage_layer_respects_viewer(tmp_path):
    """Direct unit on ``_fork_count`` so the regression can't slip
    through if the dispatch wiring shifts."""
    from workflow.api.quality_leaderboard import _fork_count
    from workflow.daemon_server import (
        initialize_author_server,
        save_branch_definition,
        save_goal,
    )
    initialize_author_server(tmp_path)
    save_goal(
        tmp_path,
        goal=dict(goal_id="g", name="g", author="h", tags=[],
                  visibility="public"),
    )
    save_branch_definition(
        tmp_path,
        branch_def=dict(
            branch_def_id="parent",
            name="P", description="", author="bob", tags=[],
            graph_nodes=[], edges=[], state_schema=[], entry_point="",
            published=True, goal_id="g", visibility="public",
        ),
    )
    save_branch_definition(
        tmp_path,
        branch_def=dict(
            branch_def_id="pub-fork",
            name="PF", description="", author="bob", tags=[],
            graph_nodes=[], edges=[], state_schema=[], entry_point="",
            published=True, goal_id="g", visibility="public",
            parent_def_id="parent",
        ),
    )
    save_branch_definition(
        tmp_path,
        branch_def=dict(
            branch_def_id="priv-fork",
            name="PrivF", description="", author="alice", tags=[],
            graph_nodes=[], edges=[], state_schema=[], entry_point="",
            published=True, goal_id="g", visibility="private",
            parent_def_id="parent",
        ),
    )
    # Third-party viewer.
    assert _fork_count(tmp_path, "parent", viewer="eve") == 1
    # Owner.
    assert _fork_count(tmp_path, "parent", viewer="alice") == 2
    # No viewer (strictly public).
    assert _fork_count(tmp_path, "parent", viewer="") == 1
    # Public via fork_from column.
    save_branch_definition(
        tmp_path,
        branch_def=dict(
            branch_def_id="forkfrom-pub",
            name="FF", description="", author="charlie", tags=[],
            graph_nodes=[], edges=[], state_schema=[], entry_point="",
            published=True, goal_id="g", visibility="public",
            fork_from="parent",
        ),
    )
    assert _fork_count(tmp_path, "parent", viewer="eve") == 2


# ---------------------------------------------------------------------------
# Public-API signature lock: include_private is no longer a kwarg
# ---------------------------------------------------------------------------


def test_build_quality_leaderboard_signature_has_no_include_private():
    """Lock the public API surface: ``include_private`` is REMOVED
    from the public entry point so a future refactor can't reintroduce
    a caller-controllable visibility knob without a test failure."""
    import inspect

    from workflow.api.quality_leaderboard import build_quality_leaderboard
    sig = inspect.signature(build_quality_leaderboard)
    assert "include_private" not in sig.parameters
    # ``viewer`` is required (no default) so callers cannot accidentally
    # invoke the public path without explicitly committing to a viewer
    # identity. The MCP handler always supplies ``_current_actor()``.
    assert sig.parameters["viewer"].default is inspect.Parameter.empty


def test_recommend_parent_for_fork_signature_has_no_include_private():
    import inspect

    from workflow.api.quality_leaderboard import recommend_parent_for_fork
    sig = inspect.signature(recommend_parent_for_fork)
    assert "include_private" not in sig.parameters
    assert sig.parameters["viewer"].default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# Empty current_actor falls back to strictly-public, not "expose all"
# ---------------------------------------------------------------------------


def test_anonymous_actor_falls_back_to_strictly_public(us_env, monkeypatch):
    """When the daemon-side actor resolves to an empty / anonymous
    identity, the visibility filter must collapse to 'strictly public'
    rather than 'no filter' (which would expose every private row)."""
    us, base = us_env
    _seed_universe(base)
    monkeypatch.delenv("UNIVERSE_SERVER_USER", raising=False)
    importlib.reload(us)
    try:
        result = _call(us, "quality_leaderboard", goal_id="g-test")
        bids = {e["branch_def_id"] for e in result["entries"]}
        # The default actor is "anonymous" — that's a string, but no
        # branches are authored by 'anonymous', so the OR clause adds
        # nothing. Only public rows surface.
        assert bids == {"pub-eve", "pub-bob", "pub-bob-public-fork"}
        assert "priv-alice" not in bids
        assert "priv-bob-fork" not in bids
    finally:
        importlib.reload(us)


# ---------------------------------------------------------------------------
# Time-domain: ensure visibility test doesn't depend on recency decay
# ---------------------------------------------------------------------------


def test_visibility_filter_holds_even_with_signal_rich_branches(us_env):
    """Sanity check — visibility is the outer filter; signal richness
    can't unmask a private row. Seed alice's private with multiple
    judgments and verify eve still doesn't see it."""
    us, base = us_env
    seeds = _seed_universe(base)
    # Give alice's private branch a completed run + high-quality
    # judgment so it would score high if visibility were off.
    from workflow.runs import (
        RUN_STATUS_COMPLETED,
        add_judgment,
        create_run,
        update_run_status,
    )
    run_id = create_run(
        base, branch_def_id=seeds["priv_alice"],
        thread_id=seeds["priv_alice"], inputs={},
    )
    update_run_status(
        base, run_id, status=RUN_STATUS_COMPLETED, finished_at=time.time(),
    )
    add_judgment(
        base, run_id=run_id, text="excellent",
        tags=["quality:10"], author="judge",
    )
    # Eve still sees only the public branches.
    result = _call(us, "quality_leaderboard", goal_id="g-test")
    bids = {e["branch_def_id"] for e in result["entries"]}
    assert seeds["priv_alice"] not in bids
