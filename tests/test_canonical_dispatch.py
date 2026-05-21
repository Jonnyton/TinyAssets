"""PR-127 — leaderboard-driven canonical resolution.

Direct unit tests on ``workflow.api.canonical_dispatch``:

  * No canonical set + auto OFF -> no_canonical_handler error.
  * Canonical set + auto OFF -> returns stored canonical verbatim.
  * Auto ON + top entry has < min_runs -> returns stored canonical
    (or no_canonical_handler when none).
  * Auto ON + top entry has enough runs + no in-flight ->
    set_canonical fires, response carries source=leaderboard_refreshed.
  * Auto ON + in-flight run on prior canonical -> refresh deferred,
    returns stored canonical with source=leaderboard_skipped_in_flight.
  * Auto ON + leaderboard top matches stored canonical -> no swap,
    source=leaderboard_no_change.
  * Auto ON + top entry has no published branch_version -> stored
    canonical kept, source=leaderboard_skipped_no_published_version.
  * Auto ON + empty leaderboard -> stored canonical kept (or
    no_canonical_handler when none).
  * Owner exception: visibility is server-derived (the helper accepts
    an explicit ``viewer`` arg matching the
    ``quality_leaderboard.build_quality_leaderboard`` contract).

In-flight detection has its own unit covering:
  * status='running' within window -> returns the row.
  * status='queued' within window -> returns the row.
  * status='succeeded' -> None (terminal).
  * status='running' OUTSIDE the window -> None (orphaned).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from workflow.api.canonical_dispatch import (
    IN_FLIGHT_WINDOW_SECONDS,
    SOURCE_CANONICAL_STORED,
    SOURCE_LEADERBOARD_NO_CHANGE,
    SOURCE_LEADERBOARD_REFRESHED,
    SOURCE_LEADERBOARD_SKIPPED_IN_FLIGHT,
    SOURCE_LEADERBOARD_SKIPPED_INSUFFICIENT_RUNS,
    SOURCE_LEADERBOARD_SKIPPED_NO_PUBLISHED_VERSION,
    is_in_flight_for_version,
    resolve_canonical_for_run,
)
from workflow.branch_versions import publish_branch_version
from workflow.daemon_server import (
    initialize_author_server,
    save_branch_definition,
    save_goal,
    set_canonical_branch,
    update_goal,
)
from workflow.runs import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RUNNING,
    add_judgment,
    create_run,
    initialize_runs_db,
    update_run_status,
)


@pytest.fixture(autouse=True)
def _mock_selector_passthrough(monkeypatch):
    """DESIGN-008 — pass-through selector for canonical-dispatch tests.

    These tests probe ``_refresh_via_leaderboard`` and rely on the
    leaderboard returning candidates in a deterministic order. We
    mock ``dispatch_selector`` to rank candidates by
    ``completed_run_count`` desc with a stable tiebreaker on
    ``last_successful_run_at`` desc, then ``branch_def_id`` asc — the
    same effective ordering the round-1 formula produced when those
    were the dominant signals, which is what these tests pre-date.
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
        def _key(c):
            sigs = c.get("signals") or {}
            return (
                -int(sigs.get("completed_run_count") or 0),
                -float(sigs.get("last_successful_run_at") or 0.0),
                c.get("branch_def_id") or "",
            )
        ordered = sorted(candidate_branches, key=_key)
        return {
            "ok": True,
            "branch_version_id": "mock_selector@canon",
            "source": "platform_default",
            "run_id": "mock-run",
            "ranked_entries": [
                {
                    "branch_def_id": c["branch_def_id"],
                    "branch_version_id": c.get("branch_version_id", ""),
                    "score": float(
                        (c.get("signals") or {}).get(
                            "completed_run_count", 0,
                        )
                    ),
                    "rationale": "passthrough by completed_run_count",
                }
                for c in ordered
            ],
        }
    monkeypatch.setattr(
        "workflow.api.quality_leaderboard.dispatch_selector",
        _passthrough,
    )


@pytest.fixture
def base_path(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    initialize_author_server(tmp_path)
    initialize_runs_db(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Test fixtures: create goal + branches + versions + runs/judgments
# ---------------------------------------------------------------------------


def _make_goal(
    base_path: Path,
    goal_id: str,
    *,
    name: str = "g",
    auto: bool = False,
    min_runs: int = 5,
) -> dict:
    save_goal(
        base_path,
        goal=dict(
            goal_id=goal_id,
            name=name,
            description="test",
            author="host",
            tags=[],
            visibility="public",
        ),
    )
    update_goal(
        base_path,
        goal_id=goal_id,
        updates={
            "auto_canonical_via_leaderboard": auto,
            "min_completed_runs_for_canonical": min_runs,
        },
    )
    from workflow.daemon_server import get_goal
    return get_goal(base_path, goal_id=goal_id)


def _make_branch(
    base_path: Path,
    *,
    branch_def_id: str,
    goal_id: str,
    author: str = "alice",
) -> str:
    save_branch_definition(
        base_path,
        branch_def=dict(
            branch_def_id=branch_def_id,
            name=branch_def_id,
            description="",
            author=author,
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id=goal_id,
        ),
    )
    return branch_def_id


def _publish_version(
    base_path: Path,
    *,
    branch_def_id: str,
    notes: str = "v1",
    publisher: str = "host",
) -> str:
    """Publish a version using a minimal branch dict. Returns
    branch_version_id. The publish_branch_version helper expects the
    full branch payload — we synthesize one with the minimum required
    fields.
    """
    branch_dict = {
        "branch_def_id": branch_def_id,
        "name": branch_def_id,
        "description": "",
        "author": "alice",
        "graph_nodes": [],
        "edges": [],
        "state_schema": [],
        "entry_point": "",
        "node_defs": [],
        # Force version content to differ each call by stamping with
        # a fresh notes string — the version sha is content-hashed.
        "_test_notes": notes,
    }
    version = publish_branch_version(
        base_path,
        branch_dict=branch_dict,
        notes=notes,
        publisher=publisher,
    )
    return version.branch_version_id


def _record_completed_runs(
    base_path: Path, *, branch_def_id: str, n: int,
) -> None:
    """Drop N completed-status runs on the branch_def_id so the
    leaderboard's completed_run_count signal is N."""
    now = time.time()
    for _ in range(n):
        rid = create_run(
            base_path, branch_def_id=branch_def_id,
            thread_id=branch_def_id, inputs={},
        )
        update_run_status(
            base_path, rid,
            status=RUN_STATUS_COMPLETED,
            finished_at=now,
        )


def _record_judgment_for_branch(
    base_path: Path, *, branch_def_id: str, tag: str = "quality:9",
) -> None:
    """Anchor a high-quality judgment so the branch ranks first."""
    rid = create_run(
        base_path, branch_def_id=branch_def_id,
        thread_id=branch_def_id, inputs={},
    )
    update_run_status(
        base_path, rid,
        status=RUN_STATUS_COMPLETED,
        finished_at=time.time(),
    )
    add_judgment(
        base_path, run_id=rid, text="great",
        tags=[tag], author="judge",
    )


# ---------------------------------------------------------------------------
# Auto OFF — stored canonical path
# ---------------------------------------------------------------------------


def test_no_canonical_set_returns_no_canonical_handler(base_path):
    _make_goal(base_path, "g1", auto=False)
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is False
    assert resolution["error_kind"] == "no_canonical_handler"
    assert resolution["goal_id"] == "g1"


def test_unknown_goal_returns_no_goal(base_path):
    resolution = resolve_canonical_for_run(
        base_path, goal_id="never-existed", viewer="",
    )
    assert resolution["ok"] is False
    assert resolution["error_kind"] == "no_goal"


def test_canonical_stored_returned_when_auto_off(base_path):
    _make_goal(base_path, "g1", auto=False)
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    bvid = _publish_version(base_path, branch_def_id="b1")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=bvid, set_by="host",
    )
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is True
    assert resolution["branch_version_id"] == bvid
    assert resolution["branch_def_id"] == "b1"
    assert resolution["source"] == SOURCE_CANONICAL_STORED
    assert resolution["refresh_attempted"] is False


# ---------------------------------------------------------------------------
# Auto ON — happy path: refresh fires
# ---------------------------------------------------------------------------


def test_auto_refresh_swaps_canonical_when_top_meets_threshold(base_path):
    _make_goal(base_path, "g1", auto=True, min_runs=3)
    _make_branch(base_path, branch_def_id="old", goal_id="g1")
    _make_branch(base_path, branch_def_id="new", goal_id="g1")
    old_bvid = _publish_version(base_path, branch_def_id="old")
    new_bvid = _publish_version(base_path, branch_def_id="new", notes="v2")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=old_bvid, set_by="host",
    )
    # Make 'new' rank first: 5 completed runs + a 9.0 quality
    # judgment. Threshold (3) is met.
    _record_completed_runs(base_path, branch_def_id="new", n=4)
    _record_judgment_for_branch(base_path, branch_def_id="new", tag="quality:9")
    # 'old' has just one completed run (and no judgment).
    _record_completed_runs(base_path, branch_def_id="old", n=1)

    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is True
    assert resolution["branch_version_id"] == new_bvid
    assert resolution["branch_def_id"] == "new"
    assert resolution["source"] == SOURCE_LEADERBOARD_REFRESHED
    assert resolution["refresh_attempted"] is True
    assert resolution["displaced_canonical_branch_version_id"] == old_bvid
    assert resolution["candidate_branch_def_id"] == "new"
    assert resolution["candidate_completed_runs"] >= 3

    # The stored canonical actually moved.
    from workflow.daemon_server import get_goal
    refreshed_goal = get_goal(base_path, goal_id="g1")
    assert refreshed_goal["canonical_branch_version_id"] == new_bvid


def test_auto_refresh_noop_when_top_matches_current(base_path):
    """Top leaderboard entry IS the current canonical — no swap, but
    refresh_attempted is True for auditability."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(base_path, branch_def_id="solo", goal_id="g1")
    bvid = _publish_version(base_path, branch_def_id="solo")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=bvid, set_by="host",
    )
    _record_completed_runs(base_path, branch_def_id="solo", n=2)

    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is True
    assert resolution["branch_version_id"] == bvid
    assert resolution["source"] == SOURCE_LEADERBOARD_NO_CHANGE
    assert resolution["refresh_attempted"] is True


# ---------------------------------------------------------------------------
# Auto ON — security gate: min_completed_runs_for_canonical threshold
# ---------------------------------------------------------------------------


def test_threshold_blocks_swap_when_top_has_insufficient_runs(base_path):
    """Adversarial: a brand-new branch with zero runs ranks first by
    judgment alone shouldn't be able to flip canonical. With
    min_runs=5 and a 1-run candidate, the stored canonical is kept."""
    _make_goal(base_path, "g1", auto=True, min_runs=5)
    _make_branch(base_path, branch_def_id="old", goal_id="g1")
    _make_branch(base_path, branch_def_id="new", goal_id="g1")
    old_bvid = _publish_version(base_path, branch_def_id="old")
    _publish_version(base_path, branch_def_id="new", notes="v2")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=old_bvid, set_by="host",
    )
    # 'new' has only 1 completed run + high judgment, but threshold=5.
    _record_completed_runs(base_path, branch_def_id="new", n=0)
    _record_judgment_for_branch(
        base_path, branch_def_id="new", tag="quality:10",
    )
    # 'old' has nothing — but threshold gate keeps stored canonical.
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is True
    assert resolution["branch_version_id"] == old_bvid
    assert resolution["source"] == (
        SOURCE_LEADERBOARD_SKIPPED_INSUFFICIENT_RUNS
    )
    assert resolution["candidate_completed_runs"] < 5
    # Canonical unchanged in storage.
    from workflow.daemon_server import get_goal
    refreshed_goal = get_goal(base_path, goal_id="g1")
    assert refreshed_goal["canonical_branch_version_id"] == old_bvid


def test_threshold_blocks_swap_no_fallback_returns_no_canonical(base_path):
    """When threshold blocks AND no prior canonical exists, the
    resolution surfaces no_canonical_handler so the caller can fall
    back to the env path."""
    _make_goal(base_path, "g1", auto=True, min_runs=5)
    _make_branch(base_path, branch_def_id="new", goal_id="g1")
    _publish_version(base_path, branch_def_id="new")
    _record_judgment_for_branch(
        base_path, branch_def_id="new", tag="quality:10",
    )
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is False
    assert resolution["error_kind"] == "no_canonical_handler"


# ---------------------------------------------------------------------------
# Auto ON — in-flight guard
# ---------------------------------------------------------------------------


def test_in_flight_run_blocks_refresh(base_path):
    """When a 'running' run is currently using the prior canonical,
    the refresh is deferred — even when a candidate qualifies."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(base_path, branch_def_id="old", goal_id="g1")
    _make_branch(base_path, branch_def_id="new", goal_id="g1")
    old_bvid = _publish_version(base_path, branch_def_id="old")
    new_bvid = _publish_version(base_path, branch_def_id="new", notes="v2")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=old_bvid, set_by="host",
    )
    _record_completed_runs(base_path, branch_def_id="new", n=4)
    _record_judgment_for_branch(
        base_path, branch_def_id="new", tag="quality:10",
    )
    # Inject an in-flight running run on the prior canonical.
    rid = create_run(
        base_path, branch_def_id="old", thread_id="old",
        inputs={}, branch_version_id=old_bvid,
    )
    update_run_status(base_path, rid, status=RUN_STATUS_RUNNING)

    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="", now=time.time(),
    )
    assert resolution["ok"] is True
    assert resolution["branch_version_id"] == old_bvid
    assert resolution["source"] == SOURCE_LEADERBOARD_SKIPPED_IN_FLIGHT
    assert resolution["in_flight_run_id"] == rid
    assert resolution["in_flight_status"] == "running"
    # Stored canonical unchanged.
    from workflow.daemon_server import get_goal
    refreshed_goal = get_goal(base_path, goal_id="g1")
    assert refreshed_goal["canonical_branch_version_id"] == old_bvid

    # Once the run finishes, a re-resolve completes the swap.
    update_run_status(
        base_path, rid, status=RUN_STATUS_COMPLETED,
        finished_at=time.time(),
    )
    resolution2 = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution2["source"] == SOURCE_LEADERBOARD_REFRESHED
    assert resolution2["branch_version_id"] == new_bvid


def test_in_flight_queued_run_also_blocks_refresh(base_path):
    """A queued (not-yet-started) run on prior canonical also blocks
    the refresh — same swap-out-from-under semantics."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(base_path, branch_def_id="old", goal_id="g1")
    _make_branch(base_path, branch_def_id="new", goal_id="g1")
    old_bvid = _publish_version(base_path, branch_def_id="old")
    _publish_version(base_path, branch_def_id="new", notes="v2")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=old_bvid, set_by="host",
    )
    _record_completed_runs(base_path, branch_def_id="new", n=4)
    _record_judgment_for_branch(
        base_path, branch_def_id="new", tag="quality:10",
    )
    rid = create_run(
        base_path, branch_def_id="old", thread_id="old",
        inputs={}, branch_version_id=old_bvid,
    )
    # Default status from create_run is 'queued'.
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["source"] == SOURCE_LEADERBOARD_SKIPPED_IN_FLIGHT
    assert resolution["in_flight_run_id"] == rid


def test_stale_in_flight_does_not_block_refresh(base_path):
    """A 'running' row started before the in-flight window is treated
    as orphaned and does NOT block a refresh. Matches the runs.py
    orphan-recovery semantics."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(base_path, branch_def_id="old", goal_id="g1")
    _make_branch(base_path, branch_def_id="new", goal_id="g1")
    old_bvid = _publish_version(base_path, branch_def_id="old")
    new_bvid = _publish_version(base_path, branch_def_id="new", notes="v2")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=old_bvid, set_by="host",
    )
    _record_completed_runs(base_path, branch_def_id="new", n=4)
    _record_judgment_for_branch(
        base_path, branch_def_id="new", tag="quality:10",
    )
    # Inject a 'running' row but with started_at far in the past.
    rid = create_run(
        base_path, branch_def_id="old", thread_id="old",
        inputs={}, branch_version_id=old_bvid,
    )
    update_run_status(base_path, rid, status=RUN_STATUS_RUNNING)
    # Backdate the row beyond the in-flight window.
    from workflow.runs import _connect
    long_ago = time.time() - (IN_FLIGHT_WINDOW_SECONDS + 60.0)
    with _connect(base_path) as conn:
        conn.execute(
            "UPDATE runs SET started_at = ? WHERE run_id = ?",
            (long_ago, rid),
        )

    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["source"] == SOURCE_LEADERBOARD_REFRESHED
    assert resolution["branch_version_id"] == new_bvid


# ---------------------------------------------------------------------------
# Auto ON — top entry has no published version
# ---------------------------------------------------------------------------


def test_top_entry_with_no_published_version_keeps_stored_canonical(
    base_path,
):
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(base_path, branch_def_id="old", goal_id="g1")
    _make_branch(base_path, branch_def_id="new-unpublished", goal_id="g1")
    old_bvid = _publish_version(base_path, branch_def_id="old")
    # NOTE: do NOT publish 'new-unpublished'.
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=old_bvid, set_by="host",
    )
    _record_completed_runs(
        base_path, branch_def_id="new-unpublished", n=4,
    )
    _record_judgment_for_branch(
        base_path, branch_def_id="new-unpublished", tag="quality:10",
    )
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is True
    assert resolution["branch_version_id"] == old_bvid
    assert resolution["source"] == (
        SOURCE_LEADERBOARD_SKIPPED_NO_PUBLISHED_VERSION
    )


# ---------------------------------------------------------------------------
# Auto ON — empty leaderboard
# ---------------------------------------------------------------------------


def test_auto_on_with_no_branches_falls_back_to_stored(base_path):
    """auto=True but no Branches bound -> empty leaderboard -> the
    stored canonical is preserved when set, otherwise
    no_canonical_handler."""
    _make_goal(base_path, "g1", auto=True, min_runs=5)
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is False
    assert resolution["error_kind"] == "no_canonical_handler"


# ---------------------------------------------------------------------------
# is_in_flight_for_version unit
# ---------------------------------------------------------------------------


def test_in_flight_detects_running(base_path):
    _make_branch(base_path, branch_def_id="b1", goal_id="")
    bvid = _publish_version(base_path, branch_def_id="b1")
    rid = create_run(
        base_path, branch_def_id="b1", thread_id="b1",
        inputs={}, branch_version_id=bvid,
    )
    update_run_status(base_path, rid, status=RUN_STATUS_RUNNING)
    row = is_in_flight_for_version(
        base_path, branch_version_id=bvid, now=time.time(),
    )
    assert row is not None
    assert row["run_id"] == rid
    assert row["status"] == "running"


def test_in_flight_detects_queued(base_path):
    _make_branch(base_path, branch_def_id="b1", goal_id="")
    bvid = _publish_version(base_path, branch_def_id="b1")
    rid = create_run(
        base_path, branch_def_id="b1", thread_id="b1",
        inputs={}, branch_version_id=bvid,
    )
    # Default is queued.
    row = is_in_flight_for_version(
        base_path, branch_version_id=bvid, now=time.time(),
    )
    assert row is not None
    assert row["run_id"] == rid


def test_in_flight_ignores_terminal_runs(base_path):
    _make_branch(base_path, branch_def_id="b1", goal_id="")
    bvid = _publish_version(base_path, branch_def_id="b1")
    for status in (RUN_STATUS_COMPLETED, RUN_STATUS_FAILED):
        rid = create_run(
            base_path, branch_def_id="b1", thread_id="b1",
            inputs={}, branch_version_id=bvid,
        )
        update_run_status(
            base_path, rid, status=status, finished_at=time.time(),
        )
    row = is_in_flight_for_version(
        base_path, branch_version_id=bvid, now=time.time(),
    )
    assert row is None


def test_in_flight_filters_other_versions(base_path):
    """Runs on a different branch_version_id don't count as in-flight
    for the version under test."""
    _make_branch(base_path, branch_def_id="b1", goal_id="")
    _make_branch(base_path, branch_def_id="b2", goal_id="")
    v1 = _publish_version(base_path, branch_def_id="b1")
    v2 = _publish_version(base_path, branch_def_id="b2")
    rid = create_run(
        base_path, branch_def_id="b2", thread_id="b2",
        inputs={}, branch_version_id=v2,
    )
    update_run_status(base_path, rid, status=RUN_STATUS_RUNNING)
    row = is_in_flight_for_version(
        base_path, branch_version_id=v1, now=time.time(),
    )
    assert row is None


def test_in_flight_window_excludes_old_runs(base_path):
    _make_branch(base_path, branch_def_id="b1", goal_id="")
    bvid = _publish_version(base_path, branch_def_id="b1")
    rid = create_run(
        base_path, branch_def_id="b1", thread_id="b1",
        inputs={}, branch_version_id=bvid,
    )
    update_run_status(base_path, rid, status=RUN_STATUS_RUNNING)
    from workflow.runs import _connect
    long_ago = time.time() - (IN_FLIGHT_WINDOW_SECONDS + 1.0)
    with _connect(base_path) as conn:
        conn.execute(
            "UPDATE runs SET started_at = ? WHERE run_id = ?",
            (long_ago, rid),
        )
    row = is_in_flight_for_version(
        base_path, branch_version_id=bvid, now=time.time(),
    )
    assert row is None


# ---------------------------------------------------------------------------
# Determinism — re-resolution returns the same answer
# ---------------------------------------------------------------------------


def test_resolution_is_deterministic_for_unchanged_state(base_path):
    _make_goal(base_path, "g1", auto=True, min_runs=2)
    _make_branch(base_path, branch_def_id="solo", goal_id="g1")
    bvid = _publish_version(base_path, branch_def_id="solo")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=bvid, set_by="host",
    )
    _record_completed_runs(base_path, branch_def_id="solo", n=3)
    now = time.time()
    r1 = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="", now=now,
    )
    r2 = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="", now=now,
    )
    assert r1["branch_version_id"] == r2["branch_version_id"]
    assert r1["source"] == r2["source"]


# ---------------------------------------------------------------------------
# Round-2 P1.1 regression — rolled-back versions cannot become canonical
# ---------------------------------------------------------------------------


def _mark_version_rolled_back(
    base_path: Path, *, branch_version_id: str, reason: str = "test",
) -> None:
    """Flip a branch_version row to status='rolled_back' via direct
    SQL. There's no public ``rollback_branch_version`` helper in
    ``workflow.branch_versions`` today, and the tests need a stable
    way to drive the rolled-back state. ISO-8601 timestamp matches the
    column's TEXT type (see _row_to_version in branch_versions.py).
    """
    from datetime import datetime, timezone

    from workflow.branch_versions import _connect, initialize_branch_versions_db

    initialize_branch_versions_db(base_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _connect(base_path) as conn:
        conn.execute(
            "UPDATE branch_versions "
            "   SET status = 'rolled_back', "
            "       rolled_back_at = ?, "
            "       rolled_back_by = 'host', "
            "       rolled_back_reason = ? "
            " WHERE branch_version_id = ?",
            (ts, reason, branch_version_id),
        )


def test_rolled_back_version_not_selected_by_auto_refresh(base_path):
    """P1.1 adversarial: publish a version, roll it back, give the
    underlying branch_def enough leaderboard signal to rank first.
    The auto-refresh path must NOT select the rolled-back version
    as canonical."""
    _make_goal(base_path, "g1", auto=True, min_runs=2)
    _make_branch(base_path, branch_def_id="rolled", goal_id="g1")
    bvid = _publish_version(base_path, branch_def_id="rolled")
    _mark_version_rolled_back(
        base_path, branch_version_id=bvid, reason="P1.1 test",
    )
    _record_completed_runs(base_path, branch_def_id="rolled", n=4)
    _record_judgment_for_branch(
        base_path, branch_def_id="rolled", tag="quality:10",
    )
    # No prior canonical, no other branches -> only candidate is the
    # rolled-back version. Resolution must REFUSE to promote it.
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is False, (
        f"P1.1 regression — rolled-back version should not be "
        f"promoted to canonical. Got: {resolution}"
    )
    assert resolution["error_kind"] == "no_canonical_handler"


def _publish_version_with_distinct_content(
    base_path: Path,
    *,
    branch_def_id: str,
    state_field_name: str,
    publisher: str = "host",
) -> str:
    """Publish a branch version with a deliberately-unique state_schema
    field so the content hash differs from any other publish under
    the same branch_def_id. The default _publish_version test helper
    is content-deterministic (same input -> same version_id), which
    makes "publish two different versions of the same branch_def_id"
    impossible without varying a real snapshot field.
    """
    from workflow.branch_versions import publish_branch_version
    branch_dict = {
        "branch_def_id": branch_def_id,
        "name": branch_def_id,
        "description": "",
        "author": "alice",
        "graph_nodes": [],
        "edges": [],
        # state_schema IS in _canonical_snapshot's whitelist; varying
        # the field name produces a distinct content hash.
        "state_schema": [{"name": state_field_name, "type": "str"}],
        "entry_point": "",
        "node_defs": [],
    }
    version = publish_branch_version(
        base_path,
        branch_dict=branch_dict,
        notes=state_field_name,
        publisher=publisher,
    )
    return version.branch_version_id


def test_rolled_back_version_falls_through_to_active_predecessor(base_path):
    """When the latest version is rolled back but an older version is
    still active, the auto-refresh selects the older active version
    instead of the rolled-back one (the active filter scans the
    version window, not just the head)."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    # Use the distinct-content helper so v1 and v2 are actually two
    # different versions of the same branch_def_id. The default
    # _publish_version helper is content-deterministic and would
    # collapse both calls to the same row.
    v1 = _publish_version_with_distinct_content(
        base_path, branch_def_id="b1", state_field_name="field_v1",
    )
    v2 = _publish_version_with_distinct_content(
        base_path, branch_def_id="b1", state_field_name="field_v2",
    )
    assert v1 != v2, (
        "Test scaffolding precondition: v1 and v2 must be distinct "
        "branch_version_ids for the active-fallback scan to be "
        "meaningful."
    )
    # Roll back the NEWER version; older one stays active.
    _mark_version_rolled_back(
        base_path, branch_version_id=v2, reason="P1.1 test",
    )
    _record_completed_runs(base_path, branch_def_id="b1", n=2)
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is True
    assert resolution["branch_version_id"] == v1, (
        "Active-version filter should skip the rolled-back v2 and "
        f"land on the active v1. Got branch_version_id={resolution.get('branch_version_id')}"
    )
    assert resolution["source"] == SOURCE_LEADERBOARD_REFRESHED


def test_rolled_back_version_keeps_stored_canonical_when_set(base_path):
    """When a stored canonical exists and the leaderboard top entry's
    only published version is rolled back, the stored canonical is
    kept (the "no published version" fallback path) rather than the
    auto-refresh writing a rolled-back version."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(base_path, branch_def_id="old", goal_id="g1")
    _make_branch(base_path, branch_def_id="new-rolled", goal_id="g1")
    old_bvid = _publish_version(base_path, branch_def_id="old")
    new_bvid = _publish_version(
        base_path, branch_def_id="new-rolled", notes="v2",
    )
    _mark_version_rolled_back(
        base_path, branch_version_id=new_bvid, reason="P1.1 test",
    )
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=old_bvid, set_by="host",
    )
    _record_completed_runs(base_path, branch_def_id="new-rolled", n=4)
    _record_judgment_for_branch(
        base_path, branch_def_id="new-rolled", tag="quality:10",
    )
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="",
    )
    assert resolution["ok"] is True
    # Stored canonical preserved — never silently swapped for the
    # rolled-back version.
    assert resolution["branch_version_id"] == old_bvid
    assert resolution["source"] == (
        SOURCE_LEADERBOARD_SKIPPED_NO_PUBLISHED_VERSION
    )


def test_set_canonical_directly_rejects_rolled_back_version(base_path):
    """Defense in depth: ``set_canonical_branch`` itself refuses a
    rolled-back ``branch_version_id``. Even a manual MCP call or host
    script cannot promote a dead version."""
    _make_goal(base_path, "g1", auto=False)
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    bvid = _publish_version(base_path, branch_def_id="b1")
    _mark_version_rolled_back(
        base_path, branch_version_id=bvid, reason="P1.1 test",
    )
    with pytest.raises(ValueError) as excinfo:
        set_canonical_branch(
            base_path, goal_id="g1",
            branch_version_id=bvid, set_by="host",
        )
    msg = str(excinfo.value)
    assert "rolled_back" in msg or "status" in msg
    assert "active" in msg


def test_set_canonical_accepts_active_version(base_path):
    """Sanity: active versions still pass the defense-in-depth check."""
    _make_goal(base_path, "g1", auto=False)
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    bvid = _publish_version(base_path, branch_def_id="b1")
    # No rollback — status='active' by default.
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=bvid, set_by="host",
    )
    from workflow.daemon_server import get_goal
    goal = get_goal(base_path, goal_id="g1")
    assert goal["canonical_branch_version_id"] == bvid


# ---------------------------------------------------------------------------
# Round-2 P1.2 regression — private branches cannot become global canonical
# ---------------------------------------------------------------------------


def _make_private_branch(
    base_path: Path,
    *,
    branch_def_id: str,
    goal_id: str,
    author: str,
) -> str:
    """Create a private branch authored by ``author``. Private
    branches are visible only to the author + host on viewer-scoped
    leaderboard queries (PR-970 auth-boundary contract).
    """
    save_branch_definition(
        base_path,
        branch_def=dict(
            branch_def_id=branch_def_id,
            name=branch_def_id,
            description="",
            author=author,
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id=goal_id,
            visibility="private",
        ),
    )
    return branch_def_id


def test_caller_viewer_cannot_promote_their_private_branch(base_path):
    """P1.2 adversarial: actor=bob; public Goal owned by alice;
    existing public canonical; bob has a private branch authored by
    himself ranking #1 in his viewer-scoped leaderboard (because
    PR-970 surfaces the viewer's own private branches). The auto-
    refresh path MUST NOT promote bob's private branch as the Goal's
    global canonical."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    # Public canonical, currently in place.
    _make_branch(
        base_path, branch_def_id="public-incumbent",
        goal_id="g1", author="alice",
    )
    pub_bvid = _publish_version(
        base_path, branch_def_id="public-incumbent",
    )
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=pub_bvid, set_by="host",
    )
    # Give the incumbent enough completed runs to stay above threshold.
    _record_completed_runs(
        base_path, branch_def_id="public-incumbent", n=2,
    )
    # Bob's private branch — high-quality, would rank #1 if visible.
    _make_private_branch(
        base_path, branch_def_id="bob-secret",
        goal_id="g1", author="bob",
    )
    _publish_version(
        base_path, branch_def_id="bob-secret", notes="bob-v1",
    )
    _record_completed_runs(
        base_path, branch_def_id="bob-secret", n=4,
    )
    _record_judgment_for_branch(
        base_path, branch_def_id="bob-secret", tag="quality:10",
    )
    # Bob fires run_canonical. His viewer-scoped leaderboard sees
    # bob-secret at #1 (would have promoted it as canonical pre-P1.2).
    # Post-P1.2 the auto-refresh hard-codes viewer="" -> bob-secret is
    # filtered out as private + not-author-of-current-strictly-public.
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="bob",
    )
    assert resolution["ok"] is True
    # Canonical did NOT swap to the private branch.
    assert resolution["branch_version_id"] == pub_bvid, (
        "P1.2 regression — bob's private branch was promoted to the "
        "Goal's global canonical via auto-refresh. The leaderboard "
        "query inside the refresh path MUST be strictly-public "
        "regardless of caller viewer."
    )
    assert resolution["branch_def_id"] == "public-incumbent"
    # Stored canonical actually unchanged.
    from workflow.daemon_server import get_goal
    refreshed_goal = get_goal(base_path, goal_id="g1")
    assert refreshed_goal["canonical_branch_version_id"] == pub_bvid


def test_caller_viewer_does_not_unlock_private_competitor(base_path):
    """Variant: bob's private branch outranks the public incumbent on
    bob's viewer-scoped leaderboard, but the auto-refresh decision
    still ignores it. Asserts the source label is one of the
    public-leaderboard outcomes (not leaderboard_refreshed with bob's
    private as the new canonical)."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(
        base_path, branch_def_id="public", goal_id="g1", author="alice",
    )
    pub_bvid = _publish_version(base_path, branch_def_id="public")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=pub_bvid, set_by="host",
    )
    _record_completed_runs(base_path, branch_def_id="public", n=1)
    _make_private_branch(
        base_path, branch_def_id="bob-private",
        goal_id="g1", author="bob",
    )
    _publish_version(base_path, branch_def_id="bob-private", notes="b1")
    _record_completed_runs(
        base_path, branch_def_id="bob-private", n=5,
    )
    _record_judgment_for_branch(
        base_path, branch_def_id="bob-private", tag="quality:9",
    )
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="bob",
    )
    assert resolution["ok"] is True
    # The leaderboard's TOP entry (from the public-only view) is the
    # public incumbent. The refresh sees it matches the stored
    # canonical -> SOURCE_LEADERBOARD_NO_CHANGE.
    assert resolution["source"] == SOURCE_LEADERBOARD_NO_CHANGE
    assert resolution["branch_version_id"] == pub_bvid


def test_owner_viewer_does_not_unlock_their_private_branch_for_canonical(
    base_path,
):
    """Even when the caller's viewer matches the private branch's
    author, the auto-refresh write must remain global/public. The
    private branch may legitimately appear on the caller's leaderboard
    view, but it cannot become the global canonical for everyone
    else."""
    _make_goal(base_path, "g1", auto=True, min_runs=1)
    _make_branch(
        base_path, branch_def_id="public", goal_id="g1", author="host",
    )
    pub_bvid = _publish_version(base_path, branch_def_id="public")
    set_canonical_branch(
        base_path, goal_id="g1",
        branch_version_id=pub_bvid, set_by="host",
    )
    _record_completed_runs(base_path, branch_def_id="public", n=1)
    _make_private_branch(
        base_path, branch_def_id="alice-private",
        goal_id="g1", author="alice",
    )
    _publish_version(
        base_path, branch_def_id="alice-private", notes="a1",
    )
    _record_completed_runs(
        base_path, branch_def_id="alice-private", n=5,
    )
    _record_judgment_for_branch(
        base_path, branch_def_id="alice-private", tag="quality:10",
    )
    resolution = resolve_canonical_for_run(
        base_path, goal_id="g1", viewer="alice",
    )
    assert resolution["ok"] is True
    # Even though alice's viewer-scoped leaderboard would surface her
    # own private branch at #1, the auto-refresh decision is global.
    assert resolution["branch_version_id"] == pub_bvid, (
        "P1.2 regression — alice's private branch must not become "
        "the Goal's global canonical even when she's the caller."
    )
