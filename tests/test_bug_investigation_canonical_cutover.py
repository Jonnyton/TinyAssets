"""PR-127 — `_maybe_enqueue_investigation` canonical cutover.

Tests the round-1-cheat-loop → leaderboard-canonical swap in
``workflow.bug_investigation._maybe_enqueue_investigation``:

  * No env vars set -> no enqueue (legacy behavior preserved).
  * Only ``WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID`` set ->
    cheat-loop fallback fires; existing dispatcher path used.
  * ``WORKFLOW_BUG_INVESTIGATION_GOAL_ID`` set + Goal has a canonical
    -> canonical's branch_def_id used; env fallback NOT consulted.
  * GOAL_ID set + Goal has NO canonical + BRANCH_DEF_ID set ->
    fallback to env.
  * GOAL_ID set + auto_canonical_via_leaderboard=true + qualified
    candidate -> auto-refresh fires from inside the wiki-write hook,
    new canonical is recorded BEFORE the dispatch.
  * Empty bug_id -> always skipped.

The dispatcher hop itself is mocked so the test doesn't depend on
the universe's branch_tasks.json shape; the assertion is that
``enqueue_investigation_request`` is called with the correct
``canonical_branch_def_id``.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def base_path(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", raising=False)
    monkeypatch.delenv(
        "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", raising=False,
    )
    from workflow.daemon_server import initialize_author_server
    from workflow.runs import initialize_runs_db
    initialize_author_server(tmp_path)
    initialize_runs_db(tmp_path)
    return tmp_path


def _seed_goal_with_canonical(
    base: Path,
    *,
    goal_id: str,
    branch_def_id: str,
    auto: bool = False,
    min_runs: int = 5,
) -> tuple[str, str]:
    """Seed a Goal + Branch + published version + set_canonical.

    Returns (branch_def_id, branch_version_id).
    """
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import (
        save_branch_definition,
        save_goal,
        set_canonical_branch,
        update_goal,
    )

    save_goal(
        base,
        goal=dict(
            goal_id=goal_id, name=goal_id, description="",
            author="host", tags=[], visibility="public",
        ),
    )
    update_goal(
        base, goal_id=goal_id,
        updates={
            "auto_canonical_via_leaderboard": auto,
            "min_completed_runs_for_canonical": min_runs,
        },
    )
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id=branch_def_id,
            name=branch_def_id,
            description="",
            author="host",
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id=goal_id,
        ),
    )
    version = publish_branch_version(
        base,
        branch_dict={
            "branch_def_id": branch_def_id,
            "name": branch_def_id,
            "description": "",
            "author": "host",
            "graph_nodes": [],
            "edges": [],
            "state_schema": [],
            "entry_point": "",
            "node_defs": [],
        },
        notes=f"{branch_def_id} v1",
        publisher="host",
    )
    bvid = version.branch_version_id
    set_canonical_branch(
        base, goal_id=goal_id,
        branch_version_id=bvid, set_by="host",
    )
    return branch_def_id, bvid


def _frontmatter(bug_id: str = "BUG-099") -> dict:
    return {
        "bug_id": bug_id,
        "title": "test bug",
        "component": "test",
        "severity": "P2",
        "kind": "bug",
        "observed": "x",
        "expected": "y",
        "repro": "z",
    }


# ---------------------------------------------------------------------------
# No env vars -> no enqueue (legacy "auto-trigger disabled" path)
# ---------------------------------------------------------------------------


def test_no_env_no_enqueue(base_path):
    from workflow.bug_investigation import _maybe_enqueue_investigation
    with patch(
        "workflow.bug_investigation.enqueue_investigation_request"
    ) as mock_enq:
        result = _maybe_enqueue_investigation(
            bug_id="BUG-001",
            frontmatter=_frontmatter("BUG-001"),
            base_path=base_path,
            universe_id="u",
        )
    assert result is None
    mock_enq.assert_not_called()


def test_empty_bug_id_skipped_even_with_env(base_path, monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", "fallback-branch",
    )
    from workflow.bug_investigation import _maybe_enqueue_investigation
    with patch(
        "workflow.bug_investigation.enqueue_investigation_request"
    ) as mock_enq:
        result = _maybe_enqueue_investigation(
            bug_id="",
            frontmatter=_frontmatter(""),
            base_path=base_path,
            universe_id="u",
        )
    assert result is None
    mock_enq.assert_not_called()


# ---------------------------------------------------------------------------
# Cheat-loop fallback (legacy path) — preserved during cutover window
# ---------------------------------------------------------------------------


def test_env_fallback_preserved_when_no_goal_id(base_path, monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", "fallback-branch",
    )
    from workflow.bug_investigation import _maybe_enqueue_investigation
    with patch(
        "workflow.bug_investigation.enqueue_investigation_request",
        return_value="req-1",
    ) as mock_enq:
        result = _maybe_enqueue_investigation(
            bug_id="BUG-001",
            frontmatter=_frontmatter("BUG-001"),
            base_path=base_path,
            universe_id="u",
        )
    assert result == "req-1"
    mock_enq.assert_called_once()
    call_kwargs = mock_enq.call_args.kwargs
    assert call_kwargs["canonical_branch_def_id"] == "fallback-branch"


def test_env_fallback_used_when_goal_id_has_no_canonical(
    base_path, monkeypatch,
):
    """``WORKFLOW_BUG_INVESTIGATION_GOAL_ID`` is set but the Goal has
    no canonical AND auto=False -> graceful fall to env path."""
    from workflow.daemon_server import save_goal
    save_goal(
        base_path,
        goal=dict(
            goal_id="g1", name="g1", description="",
            author="host", tags=[], visibility="public",
        ),
    )
    monkeypatch.setenv("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", "g1")
    monkeypatch.setenv(
        "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", "fallback-branch",
    )
    from workflow.bug_investigation import _maybe_enqueue_investigation
    with patch(
        "workflow.bug_investigation.enqueue_investigation_request",
        return_value="req-2",
    ) as mock_enq:
        result = _maybe_enqueue_investigation(
            bug_id="BUG-002",
            frontmatter=_frontmatter("BUG-002"),
            base_path=base_path,
            universe_id="u",
        )
    assert result == "req-2"
    mock_enq.assert_called_once()
    assert mock_enq.call_args.kwargs["canonical_branch_def_id"] == (
        "fallback-branch"
    )


# ---------------------------------------------------------------------------
# Goal canonical wins over env fallback
# ---------------------------------------------------------------------------


def test_goal_canonical_used_when_set(base_path, monkeypatch):
    bdid, _ = _seed_goal_with_canonical(
        base_path, goal_id="g1", branch_def_id="bug-handler",
    )
    monkeypatch.setenv("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", "g1")
    # Cheat env ALSO set — canonical should win.
    monkeypatch.setenv(
        "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", "should-not-be-used",
    )
    from workflow.bug_investigation import _maybe_enqueue_investigation
    with patch(
        "workflow.bug_investigation.enqueue_investigation_request",
        return_value="req-3",
    ) as mock_enq:
        result = _maybe_enqueue_investigation(
            bug_id="BUG-003",
            frontmatter=_frontmatter("BUG-003"),
            base_path=base_path,
            universe_id="u",
        )
    assert result == "req-3"
    mock_enq.assert_called_once()
    # Used the Goal's canonical branch_def_id, NOT the env fallback.
    assert (
        mock_enq.call_args.kwargs["canonical_branch_def_id"] == bdid
    )


def test_goal_canonical_with_auto_refresh(base_path, monkeypatch):
    """auto_canonical_via_leaderboard=True + a higher-ranked candidate
    => the file_bug hook auto-refreshes BEFORE dispatching, and the
    new canonical's branch_def_id is what enqueue receives."""
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import (
        save_branch_definition,
        save_goal,
        set_canonical_branch,
        update_goal,
    )
    from workflow.runs import (
        RUN_STATUS_COMPLETED,
        add_judgment,
        create_run,
        update_run_status,
    )

    # Goal + auto=True + min_runs=2.
    save_goal(
        base_path,
        goal=dict(
            goal_id="g1", name="g1", description="",
            author="host", tags=[], visibility="public",
        ),
    )
    update_goal(
        base_path, goal_id="g1",
        updates={
            "auto_canonical_via_leaderboard": True,
            "min_completed_runs_for_canonical": 2,
        },
    )
    # Old branch (currently canonical, low quality).
    save_branch_definition(
        base_path,
        branch_def=dict(
            branch_def_id="old", name="old", description="",
            author="host", tags=[], graph_nodes=[], edges=[],
            state_schema=[], entry_point="", published=True,
            goal_id="g1",
        ),
    )
    old_v = publish_branch_version(
        base_path,
        branch_dict={
            "branch_def_id": "old", "name": "old", "description": "",
            "author": "host", "graph_nodes": [], "edges": [],
            "state_schema": [], "entry_point": "", "node_defs": [],
        },
        notes="old v1", publisher="host",
    )
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=old_v.branch_version_id, set_by="host",
    )
    # New branch — higher quality + enough completed runs.
    save_branch_definition(
        base_path,
        branch_def=dict(
            branch_def_id="new", name="new", description="",
            author="host", tags=[], graph_nodes=[], edges=[],
            state_schema=[], entry_point="", published=True,
            goal_id="g1",
        ),
    )
    new_v = publish_branch_version(
        base_path,
        branch_dict={
            "branch_def_id": "new", "name": "new", "description": "",
            "author": "host", "graph_nodes": [], "edges": [],
            "state_schema": [], "entry_point": "", "node_defs": [],
        },
        notes="new v1", publisher="host",
    )
    now = time.time()
    for _ in range(3):
        rid = create_run(
            base_path, branch_def_id="new", thread_id="new", inputs={},
        )
        update_run_status(
            base_path, rid, status=RUN_STATUS_COMPLETED,
            finished_at=now,
        )
    # Add a high-quality judgment to make 'new' rank first.
    rid_j = create_run(
        base_path, branch_def_id="new", thread_id="new", inputs={},
    )
    update_run_status(
        base_path, rid_j, status=RUN_STATUS_COMPLETED, finished_at=now,
    )
    add_judgment(
        base_path, run_id=rid_j, text="great",
        tags=["quality:10"], author="judge",
    )

    monkeypatch.setenv("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", "g1")
    from workflow.bug_investigation import _maybe_enqueue_investigation
    with patch(
        "workflow.bug_investigation.enqueue_investigation_request",
        return_value="req-auto",
    ) as mock_enq:
        result = _maybe_enqueue_investigation(
            bug_id="BUG-004",
            frontmatter=_frontmatter("BUG-004"),
            base_path=base_path,
            universe_id="u",
        )
    assert result == "req-auto"
    mock_enq.assert_called_once()
    # The auto-refresh swapped canonical to 'new' BEFORE dispatch.
    assert mock_enq.call_args.kwargs["canonical_branch_def_id"] == "new"
    # Storage was actually updated.
    from workflow.daemon_server import get_goal
    refreshed_goal = get_goal(base_path, goal_id="g1")
    assert refreshed_goal["canonical_branch_version_id"] == (
        new_v.branch_version_id
    )


# ---------------------------------------------------------------------------
# Module attribute lookup still respected (existing
# test_bug_investigation_dispatcher pattern)
# ---------------------------------------------------------------------------


def test_resolve_handler_returns_empty_when_no_goal_and_no_env(base_path):
    from workflow.bug_investigation import _resolve_investigation_handler
    assert _resolve_investigation_handler(base_path) == ""


def test_resolve_handler_strips_whitespace_in_env(base_path, monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", "  legit-branch  ",
    )
    from workflow.bug_investigation import _resolve_investigation_handler
    assert _resolve_investigation_handler(base_path) == "legit-branch"
