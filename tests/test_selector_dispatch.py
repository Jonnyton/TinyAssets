"""DESIGN-008 — selector-branch dispatch unit tests.

Covers ``tinyassets.api.selector_dispatch`` directly:

  * ``resolve_selector_branch_version_id`` — goal_binding vs.
    platform_default fallback.
  * ``ensure_default_selector_published`` — idempotency,
    deterministic branch_def_id, active version returned.
  * ``dispatch_selector`` — retired by Hard Rule 15 (the platform has no
    LLM): an empty candidate set still short-circuits; anything else fails
    closed with ``selector_retired`` and runs nothing. The output-parsing,
    timeout and end-to-end run tests went with the run path.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def base_path(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.runs import initialize_runs_db
    initialize_author_server(tmp_path)
    initialize_runs_db(tmp_path)
    return tmp_path


def _make_goal(
    base_path: Path,
    goal_id: str,
    *,
    selector_branch_version_id: str | None = None,
) -> dict:
    from tinyassets.daemon_server import save_goal, update_goal
    save_goal(
        base_path,
        goal=dict(
            goal_id=goal_id,
            name=goal_id,
            description="",
            author="host",
            tags=[],
            visibility="public",
        ),
    )
    if selector_branch_version_id is not None:
        update_goal(
            base_path,
            goal_id=goal_id,
            updates={
                "selector_branch_version_id": selector_branch_version_id,
            },
        )
    from tinyassets.daemon_server import get_goal
    return get_goal(base_path, goal_id=goal_id)


# ---------------------------------------------------------------------------
# ensure_default_selector_published — idempotency + active version
# ---------------------------------------------------------------------------


def test_default_selector_publishes_on_first_call(base_path):
    from tinyassets.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
        ensure_default_selector_published,
    )
    bvid = ensure_default_selector_published(base_path)
    assert bvid.startswith(DEFAULT_SELECTOR_BRANCH_DEF_ID + "@")


def test_default_selector_is_idempotent(base_path):
    from tinyassets.api.selector_dispatch import ensure_default_selector_published
    a = ensure_default_selector_published(base_path)
    b = ensure_default_selector_published(base_path)
    assert a == b


def test_default_selector_branch_def_exists_after_publish(base_path):
    from tinyassets.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
        ensure_default_selector_published,
    )
    ensure_default_selector_published(base_path)
    from tinyassets.daemon_server import get_branch_definition
    branch = get_branch_definition(
        base_path, branch_def_id=DEFAULT_SELECTOR_BRANCH_DEF_ID,
    )
    assert branch["name"] == "Platform Default Selector v1"
    assert branch["author"] == "platform"
    node_ids = [n["node_id"] for n in branch.get("node_defs", [])]
    assert "rank" in node_ids


# ---------------------------------------------------------------------------
# resolve_selector_branch_version_id — binding vs default
# ---------------------------------------------------------------------------


def test_resolve_returns_goal_binding_when_set(base_path):
    """Resolver prefers explicit ``selector_branch_version_id`` over
    the platform default.

    Round 4 (P1.C): the resolver now also verifies the bound version
    is still active. The binding must point at a REAL active version
    — a fake bvid would correctly fall back to platform default (see
    ``test_resolve_falls_back_when_bound_selector_version_missing``).
    Publish a custom selector via the default-selector helper, then
    bind to it.
    """
    from tinyassets.api.selector_dispatch import (
        ensure_default_selector_published,
        resolve_selector_branch_version_id,
    )
    # Publish a real active selector (the platform default itself is
    # fine for this test — we just need a known-active bvid for the
    # binding to point at).
    bvid = ensure_default_selector_published(base_path)
    _make_goal(
        base_path, "g1",
        selector_branch_version_id=bvid,
    )
    result = resolve_selector_branch_version_id(base_path, goal_id="g1")
    assert result["ok"] is True
    assert result["branch_version_id"] == bvid
    assert result["source"] == "goal_binding"


def test_resolve_falls_back_to_platform_default(base_path):
    _make_goal(base_path, "g1", selector_branch_version_id=None)
    from tinyassets.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
        resolve_selector_branch_version_id,
    )
    result = resolve_selector_branch_version_id(base_path, goal_id="g1")
    assert result["ok"] is True
    assert result["source"] == "platform_default"
    assert result["branch_version_id"].startswith(
        DEFAULT_SELECTOR_BRANCH_DEF_ID + "@",
    )


def test_resolve_returns_goal_not_found_for_missing_goal(base_path):
    from tinyassets.api.selector_dispatch import resolve_selector_branch_version_id
    result = resolve_selector_branch_version_id(base_path, goal_id="never")
    assert result["ok"] is False
    assert result["error_kind"] == "goal_not_found"


# ---------------------------------------------------------------------------
# dispatch_selector — empty candidate set
# ---------------------------------------------------------------------------


def test_dispatch_short_circuits_on_empty_candidates(base_path):
    _make_goal(base_path, "g1")
    from tinyassets.api.selector_dispatch import dispatch_selector
    result = dispatch_selector(
        base_path, goal_id="g1", candidate_branches=[],
        actor="viewer-1",
    )
    assert result["ok"] is True
    assert result["ranked_entries"] == []
    assert result["source"] == "empty_candidate_set"
    # No selector publish should have happened — we short-circuited
    # before resolving.
    from tinyassets.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
    )
    from tinyassets.daemon_server import get_branch_definition
    with pytest.raises(KeyError):
        get_branch_definition(
            base_path, branch_def_id=DEFAULT_SELECTOR_BRANCH_DEF_ID,
        )


def test_dispatch_fails_closed_for_any_candidates(base_path):
    """Hard Rule 15: no selector run, no publish, no provider."""
    _make_goal(base_path, "g1")
    from tinyassets.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
        dispatch_selector,
    )
    from tinyassets.daemon_server import get_branch_definition

    result = dispatch_selector(
        base_path, goal_id="g1", actor="viewer-1",
        candidate_branches=[{"branch_def_id": "b1", "signals": {}}],
        provider_call=lambda *_a, **_k: pytest.fail("no provider may be called"),
    )
    assert result["ok"] is False
    assert result["error_kind"] == "selector_retired"
    assert "platform has no LLM" in result["error"]
    with pytest.raises(KeyError):
        get_branch_definition(base_path, branch_def_id=DEFAULT_SELECTOR_BRANCH_DEF_ID)




# ---------------------------------------------------------------------------
# DESIGN-008 round 4 P1.C — rolled-back selector cannot keep dispatching
# ---------------------------------------------------------------------------


def _flip_branch_version_status(base_path, branch_version_id, status):
    """Direct SQL flip of ``branch_versions.status`` for test setup.

    Simulates the post-bind state where a rollback (or any other
    lifecycle operation) marks the version as no longer ``active``.
    """
    from tinyassets.branch_versions import _connect
    with _connect(base_path) as conn:
        conn.execute(
            "UPDATE branch_versions SET status = ? "
            "WHERE branch_version_id = ?",
            (status, branch_version_id),
        )


def _publish_custom_selector(
    base_path, branch_def_id="custom_test_selector",
):
    """Publish a custom selector branch_version distinct from the
    platform default so tests can flip ITS status without disturbing
    the fallback target."""
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )
    save_branch_definition(
        base_path,
        branch_def=dict(
            branch_def_id=branch_def_id,
            name=branch_def_id,
            description="",
            author="alice",
            tags=[],
            graph_nodes=[
                {
                    "id": "rank",
                    "type": "prompt",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                },
            ],
            edges=[
                {"from": "START", "to": "rank"},
                {"from": "rank", "to": "END"},
            ],
            state_schema=[
                {"name": "candidate_branches", "type": "str"},
                {"name": "ranked_entries", "type": "str"},
            ],
            entry_point="rank",
            published=True,
            node_defs=[
                {
                    "node_id": "rank",
                    "display_name": "Rank",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                    "prompt_template": "rank {candidate_branches}",
                },
            ],
        ),
    )
    branch_dict = get_branch_definition(
        base_path, branch_def_id=branch_def_id,
    )
    version = publish_branch_version(
        base_path, branch_dict, publisher="alice",
    )
    return version.branch_version_id


def test_resolve_falls_back_when_bound_selector_is_rolled_back(base_path):
    """Round-4 P1.C — bound selector version flipped to rolled_back
    AFTER bind must NOT keep being returned as goal_binding. Resolver
    falls back to platform default with a ``fellback_from`` diagnostic.

    Uses a CUSTOM selector so the rollback doesn't disturb the
    platform-default fallback target.
    """
    _make_goal(base_path, "g1")
    custom_bvid = _publish_custom_selector(base_path)
    from tinyassets.api.selector_dispatch import (
        resolve_selector_branch_version_id,
    )
    from tinyassets.daemon_server import update_goal
    update_goal(
        base_path,
        goal_id="g1",
        updates={"selector_branch_version_id": custom_bvid},
    )
    # Simulate rollback of the bound selector.
    _flip_branch_version_status(base_path, custom_bvid, "rolled_back")

    result = resolve_selector_branch_version_id(base_path, goal_id="g1")
    assert result["ok"] is True
    assert result["source"] == "platform_default", (
        "resolver must fall back to platform default when the bound "
        "selector is no longer active; got "
        f"source={result.get('source')!r}"
    )
    assert "fellback_from" in result
    fb = result["fellback_from"]
    assert fb["branch_version_id"] == custom_bvid
    assert fb["reason"] == "selector_version_inactive"
    assert fb["status"] == "rolled_back"


def test_resolve_falls_back_when_bound_selector_version_missing(base_path):
    """Defense in depth — bound version row missing from branch_versions
    (e.g. hard-deleted by an administrator). Resolver falls back +
    surfaces a different ``reason`` so audit tools can distinguish."""
    _make_goal(base_path, "g1")
    from tinyassets.api.selector_dispatch import resolve_selector_branch_version_id
    from tinyassets.daemon_server import update_goal
    update_goal(
        base_path,
        goal_id="g1",
        updates={"selector_branch_version_id": "phantom@deadbeef"},
    )
    result = resolve_selector_branch_version_id(base_path, goal_id="g1")
    assert result["ok"] is True
    assert result["source"] == "platform_default"
    assert result["fellback_from"]["reason"] == "selector_version_not_found"


def test_resolve_logs_fallback_with_clear_operator_guidance(
    base_path, caplog,
):
    """Stale binding must emit a WARNING naming the goal + bvid +
    status so operators can find it in logs and re-bind."""
    import logging
    _make_goal(base_path, "g-stale")
    custom_bvid = _publish_custom_selector(
        base_path, branch_def_id="stale_test_selector",
    )
    from tinyassets.api.selector_dispatch import resolve_selector_branch_version_id
    from tinyassets.daemon_server import update_goal
    update_goal(
        base_path,
        goal_id="g-stale",
        updates={"selector_branch_version_id": custom_bvid},
    )
    _flip_branch_version_status(base_path, custom_bvid, "rolled_back")
    with caplog.at_level(
        logging.WARNING, logger="tinyassets.api.selector_dispatch",
    ):
        resolve_selector_branch_version_id(base_path, goal_id="g-stale")
    matching = [
        rec for rec in caplog.records
        if rec.levelno >= logging.WARNING
        and "g-stale" in str(rec.getMessage())
        and custom_bvid in str(rec.getMessage())
    ]
    assert matching, (
        "expected WARNING naming goal + bvid; got "
        f"{[r.getMessage() for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# Round-5 P1 — platform default rolled back must fail closed
# ---------------------------------------------------------------------------


def test_ensure_default_returns_empty_when_existing_default_rolled_back(
    base_path,
):
    """Round-5 P1 — ``publish_branch_version`` is deterministic in
    ``(branch_def_id, content_hash)``. If an operator rolls back the
    platform default selector (every existing default version's
    status flipped to ``rolled_back``), a subsequent
    ``ensure_default_selector_published`` call would hit the
    deterministic re-publish path and get back the SAME rolled-back
    row. ``ensure_default_selector_published`` must detect that and
    return empty so callers surface ``default_selector_unavailable``
    rather than silently dispatching a rolled-back selector.
    """
    from tinyassets.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
        ensure_default_selector_published,
    )

    # First call mints the active default.
    bvid = ensure_default_selector_published(base_path)
    assert bvid.startswith(DEFAULT_SELECTOR_BRANCH_DEF_ID + "@")

    # Operator-style rollback: flip every existing default's status.
    _flip_branch_version_status(base_path, bvid, "rolled_back")

    # Second call sees no active version, calls publish_branch_version
    # (deterministic) which returns the existing rolled-back row.
    # ensure_default_selector_published must NOT return that bvid.
    second = ensure_default_selector_published(base_path)
    assert second == "", (
        "ensure_default_selector_published returned %r for a "
        "rolled-back default — expected '' so the caller surfaces "
        "default_selector_unavailable" % (second,)
    )


def test_resolve_surfaces_default_unavailable_when_default_rolled_back(
    base_path,
):
    """Round-5 P1 — when ``ensure_default_selector_published`` returns
    empty (rolled-back default), ``resolve_selector_branch_version_id``
    must surface a structured ``default_selector_unavailable`` error
    to the leaderboard caller rather than crashing or dispatching."""
    _make_goal(base_path, "g-default-rolled-back")
    from tinyassets.api.selector_dispatch import (
        ensure_default_selector_published,
        resolve_selector_branch_version_id,
    )

    bvid = ensure_default_selector_published(base_path)
    _flip_branch_version_status(base_path, bvid, "rolled_back")

    result = resolve_selector_branch_version_id(
        base_path, goal_id="g-default-rolled-back",
    )
    assert result["ok"] is False, result
    assert result["error_kind"] == "default_selector_unavailable"

