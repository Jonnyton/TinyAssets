"""DESIGN-008 — backfill migration test for the selector primitive.

Covers ``scripts/migrate_design_008_selector_backfill.py``:

* Existing Goals with bound branches but NULL
  ``selector_branch_version_id`` get the default selector bound.
* Goals with no bound branches are SKIPPED (no point binding a
  selector when there's nothing to rank).
* Goals with an explicit selector binding are NOT overwritten.
* Re-running the script is idempotent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.migrate_design_008_selector_backfill import run_backfill


@pytest.fixture
def base_path(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    from workflow.daemon_server import initialize_author_server
    initialize_author_server(tmp_path)
    return tmp_path


def _seed_goal_with_branches(
    base_path: Path,
    goal_id: str,
    *,
    branch_ids: list[str],
    selector_branch_version_id: str | None = None,
):
    from workflow.daemon_server import (
        save_branch_definition,
        save_goal,
        update_goal,
    )
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
    for bid in branch_ids:
        save_branch_definition(
            base_path,
            branch_def=dict(
                branch_def_id=bid,
                name=bid,
                description="",
                author="alice",
                tags=[],
                graph_nodes=[],
                edges=[],
                state_schema=[],
                entry_point="",
                published=True,
                goal_id=goal_id,
            ),
        )


def _get_goal(base_path: Path, goal_id: str) -> dict:
    from workflow.daemon_server import get_goal
    return get_goal(base_path, goal_id=goal_id)


def test_backfill_binds_default_to_goal_with_branches(base_path):
    _seed_goal_with_branches(base_path, "g1", branch_ids=["b1"])
    result = run_backfill(str(base_path))
    assert "g1" in result["updated_goal_ids"]
    goal = _get_goal(base_path, "g1")
    assert goal["selector_branch_version_id"] == result[
        "published_default_bvid"
    ]


def test_backfill_skips_goal_with_no_branches(base_path):
    _seed_goal_with_branches(base_path, "g-empty", branch_ids=[])
    result = run_backfill(str(base_path))
    assert "g-empty" not in result["updated_goal_ids"]
    goal = _get_goal(base_path, "g-empty")
    assert goal["selector_branch_version_id"] is None
    assert result["skipped_goal_count"] == 1


def test_backfill_preserves_explicit_binding(base_path):
    _seed_goal_with_branches(
        base_path, "g-custom",
        branch_ids=["b1"],
        selector_branch_version_id="custom_selector@abc12345",
    )
    result = run_backfill(str(base_path))
    assert "g-custom" not in result["updated_goal_ids"]
    goal = _get_goal(base_path, "g-custom")
    assert goal["selector_branch_version_id"] == "custom_selector@abc12345"


def test_backfill_is_idempotent(base_path):
    _seed_goal_with_branches(base_path, "g1", branch_ids=["b1"])
    first = run_backfill(str(base_path))
    second = run_backfill(str(base_path))
    assert "g1" in first["updated_goal_ids"]
    # Second run finds no NULL-selector Goals — nothing to update.
    assert second["updated_goal_ids"] == []
    # Same default selector bvid both times (deterministic).
    assert first["published_default_bvid"] == second[
        "published_default_bvid"
    ]


def test_backfill_dry_run_does_not_write(base_path):
    _seed_goal_with_branches(base_path, "g1", branch_ids=["b1"])
    result = run_backfill(str(base_path), dry_run=True)
    assert result["dry_run"] is True
    # Dry-run reports candidates but doesn't write.
    assert "g1" in result["updated_goal_ids"]
    goal = _get_goal(base_path, "g1")
    assert goal["selector_branch_version_id"] is None


def test_backfill_mixed_population(base_path):
    """Realistic seed: 3 goals — one with branches+null, one without
    branches, one with explicit binding."""
    _seed_goal_with_branches(base_path, "g-bind-me", branch_ids=["b1"])
    _seed_goal_with_branches(base_path, "g-skip", branch_ids=[])
    _seed_goal_with_branches(
        base_path, "g-keep",
        branch_ids=["b2"],
        selector_branch_version_id="custom@xx",
    )
    result = run_backfill(str(base_path))
    assert result["updated_goal_ids"] == ["g-bind-me"]
    assert result["skipped_goal_count"] == 1
    # Verify final state.
    assert (
        _get_goal(base_path, "g-bind-me")["selector_branch_version_id"]
        == result["published_default_bvid"]
    )
    assert (
        _get_goal(base_path, "g-skip")["selector_branch_version_id"]
        is None
    )
    assert (
        _get_goal(base_path, "g-keep")["selector_branch_version_id"]
        == "custom@xx"
    )
