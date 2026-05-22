"""Tests for workflow.api.quality_leaderboard.

PR-123 substrate (M2). Covers:

- Empty Goal (no branches bound) -> empty entries + parent-rec returns None.
- Single entry -> rank 1, score reflects signals.
- Multiple entries with diverse signals -> correct ranking.
- Recency decay correctness (older success ranks lower vs newer).
- Goal with many branches (realistic scale, 15+).
- Numeric tag parsing from judgments (quality:8, novelty:7, risk:3).
- Fork count signal (parent_def_id + fork_from both contribute).
- Best-effort safe_to_publish lookup in branch.stats.
- Gate-rung claim signal.
- ``recommend_parent_for_fork`` rationale shape.

Storage is exercised through the canonical helpers
(``save_goal`` / ``save_branch_definition`` / ``create_run`` /
``update_run_status`` / ``add_judgment`` / ``record_gate_claim``)
so any future schema migration is exercised here too.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from workflow.api.quality_leaderboard import (
    JUDGMENT_MAX_SCALE,
    RECENCY_HALFLIFE_DAYS,
    build_quality_leaderboard,
    recommend_parent_for_fork,
)
from workflow.daemon_server import (
    initialize_author_server,
    save_branch_definition,
    save_goal,
)
from workflow.runs import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    add_judgment,
    create_run,
    initialize_runs_db,
    update_run_status,
)

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def base_path(tmp_path: Path, monkeypatch) -> Path:
    """Per-test data root with both schema layers initialized."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    initialize_author_server(tmp_path)
    initialize_runs_db(tmp_path)
    return tmp_path


def _make_goal(base_path: Path, goal_id: str, *, name: str = "g") -> str:
    save_goal(
        base_path,
        goal=dict(
            goal_id=goal_id,
            name=name,
            description=f"test goal {goal_id}",
            author="host",
            tags=[],
            visibility="public",
        ),
    )
    return goal_id


def _make_branch(
    base_path: Path,
    *,
    branch_def_id: str,
    goal_id: str,
    name: str | None = None,
    parent_def_id: str | None = None,
    fork_from: str | None = None,
    stats: dict | None = None,
    author: str = "alice",
) -> str:
    save_branch_definition(
        base_path,
        branch_def=dict(
            branch_def_id=branch_def_id,
            name=name or branch_def_id,
            description=f"branch {branch_def_id}",
            author=author,
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id=goal_id,
            parent_def_id=parent_def_id,
            fork_from=fork_from,
            stats=stats or {},
        ),
    )
    return branch_def_id


def _record_run(
    base_path: Path,
    *,
    branch_def_id: str,
    status: str,
    finished_at: float | None = None,
) -> str:
    run_id = create_run(
        base_path,
        branch_def_id=branch_def_id,
        thread_id=branch_def_id,
        inputs={},
    )
    update_run_status(
        base_path,
        run_id,
        status=status,
        finished_at=finished_at if finished_at is not None else time.time(),
    )
    return run_id


def _record_judgment(
    base_path: Path,
    *,
    run_id: str,
    tags: list[str],
    text: str = "test judgment",
) -> None:
    add_judgment(
        base_path,
        run_id=run_id,
        text=text,
        tags=tags,
        author="judge",
    )


# ---------------------------------------------------------------------------
# Empty Goal
# ---------------------------------------------------------------------------


def test_empty_goal_returns_no_entries(base_path):
    _make_goal(base_path, "g-empty")
    board = build_quality_leaderboard(base_path, goal_id="g-empty", viewer="")
    assert board["entries"] == []
    assert board["goal_id"] == "g-empty"
    assert board["goal"] is not None
    assert board["formula"]["weights"]["judgment"] > 0
    # Recency halflife exposed for tuning visibility.
    assert board["formula"]["recency_halflife_days"] == RECENCY_HALFLIFE_DAYS


def test_unknown_goal_id_returns_empty_entries_and_none_goal(base_path):
    board = build_quality_leaderboard(base_path, goal_id="nope", viewer="")
    assert board["entries"] == []
    assert board["goal"] is None


def test_recommend_parent_when_no_entries(base_path):
    _make_goal(base_path, "g-empty")
    rec = recommend_parent_for_fork(base_path, goal_id="g-empty", viewer="")
    assert rec["recommended_parent"] is None
    assert "No Branch is bound" in rec["rationale"]
    assert rec["leaderboard_size"] == 0


# ---------------------------------------------------------------------------
# Single entry
# ---------------------------------------------------------------------------


def test_single_branch_ranks_first(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    assert len(board["entries"]) == 1
    entry = board["entries"][0]
    assert entry["rank"] == 1
    assert entry["branch_def_id"] == "b1"
    # No runs, no judgments -> score is 0 (or possibly negative from
    # failed-penalty term, but we have no failed runs either).
    assert entry["score"] == 0.0
    assert entry["signals"]["completed_run_count"] == 0
    assert entry["signals"]["fork_count"] == 0
    assert entry["signals"]["has_gate_rung"] is False
    assert entry["signals"]["safe_to_publish"] is False


def test_single_branch_with_completed_run_scores_above_zero(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    _record_run(
        base_path,
        branch_def_id="b1",
        status=RUN_STATUS_COMPLETED,
        finished_at=time.time(),
    )
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    entry = board["entries"][0]
    assert entry["score"] > 0
    assert entry["signals"]["completed_run_count"] == 1
    # Recency near 1.0 for a just-finished run.
    assert entry["signals"]["recency_decay"] > 0.95


def test_completed_run_with_iso_finished_at_does_not_crash(base_path):
    """Legacy/community-authored rows may carry ISO timestamps."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    finished_at = "2026-05-22T00:00:00Z"
    started_at = "2026-05-21T23:59:00Z"

    from workflow.runs import _connect

    with _connect(base_path) as conn:
        conn.execute(
            """
            INSERT INTO runs (
                run_id, branch_def_id, thread_id, status, inputs_json,
                output_json, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-iso", "b1", "b1", RUN_STATUS_COMPLETED, "{}",
                "{}", started_at, finished_at,
            ),
        )

    now = datetime(2026, 5, 23, tzinfo=timezone.utc).timestamp()
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="", now=now)
    entry = board["entries"][0]
    expected_ts = datetime(2026, 5, 22, tzinfo=timezone.utc).timestamp()
    assert entry["signals"]["completed_run_count"] == 1
    assert entry["signals"]["last_successful_run_at"] == expected_ts
    assert entry["signals"]["age_days_since_success"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Numeric judgment parsing
# ---------------------------------------------------------------------------


def test_judgment_tag_parsing_produces_score_avg(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    run_id = _record_run(
        base_path, branch_def_id="b1",
        status=RUN_STATUS_COMPLETED, finished_at=time.time(),
    )
    _record_judgment(base_path, run_id=run_id, tags=["quality:8.0", "novelty:7.0"])
    _record_judgment(base_path, run_id=run_id, tags=["quality:9.0"])
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    entry = board["entries"][0]
    # avg of 8.0, 7.0, 9.0 = 8.0
    assert entry["signals"]["judgment_score_avg"] == pytest.approx(8.0)
    assert entry["signals"]["judgment_score_samples"] == 3
    assert entry["signals"]["judgment_count"] == 2  # two judgment rows


def test_other_numeric_tags_recorded_separately(base_path):
    """Tags like ``risk:3`` are numeric but NOT in the headline score
    average; they appear under ``other_numeric_tags``."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    run_id = _record_run(
        base_path, branch_def_id="b1",
        status=RUN_STATUS_COMPLETED, finished_at=time.time(),
    )
    _record_judgment(
        base_path, run_id=run_id,
        tags=["quality:8", "risk:3", "cost:42"],
    )
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    signals = board["entries"][0]["signals"]
    assert signals["judgment_score_avg"] == pytest.approx(8.0)
    assert signals["other_numeric_tags"] == {"risk": 1, "cost": 1}


def test_non_numeric_tags_ignored(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    run_id = _record_run(
        base_path, branch_def_id="b1",
        status=RUN_STATUS_COMPLETED, finished_at=time.time(),
    )
    _record_judgment(
        base_path, run_id=run_id,
        tags=["needs-revision", "writer:loop-2"],
    )
    signals = build_quality_leaderboard(
        base_path, goal_id="g1", viewer="",
    )["entries"][0]["signals"]
    assert signals["judgment_score_avg"] is None
    assert signals["other_numeric_tags"] == {}


# ---------------------------------------------------------------------------
# Multi-branch ranking
# ---------------------------------------------------------------------------


def test_higher_judgment_wins_over_lower(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-low", goal_id="g1")
    _make_branch(base_path, branch_def_id="b-high", goal_id="g1")
    now = time.time()
    r_low = _record_run(
        base_path, branch_def_id="b-low",
        status=RUN_STATUS_COMPLETED, finished_at=now,
    )
    r_high = _record_run(
        base_path, branch_def_id="b-high",
        status=RUN_STATUS_COMPLETED, finished_at=now,
    )
    _record_judgment(base_path, run_id=r_low, tags=["quality:3.0"])
    _record_judgment(base_path, run_id=r_high, tags=["quality:9.0"])
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="", now=now)
    ranks = {e["branch_def_id"]: e["rank"] for e in board["entries"]}
    assert ranks["b-high"] == 1
    assert ranks["b-low"] == 2


def test_recency_decay_breaks_score_ties_among_equal_quality(base_path):
    """Two branches with identical judgments but different recency.
    Fresher success should rank first."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-old", goal_id="g1")
    _make_branch(base_path, branch_def_id="b-new", goal_id="g1")
    now = 1_700_000_000.0
    # 'b-old' finished 60 days ago, 'b-new' finished today.
    sixty_days_ago = now - 60 * 86400
    r_old = _record_run(
        base_path, branch_def_id="b-old",
        status=RUN_STATUS_COMPLETED, finished_at=sixty_days_ago,
    )
    r_new = _record_run(
        base_path, branch_def_id="b-new",
        status=RUN_STATUS_COMPLETED, finished_at=now,
    )
    _record_judgment(base_path, run_id=r_old, tags=["quality:8.0"])
    _record_judgment(base_path, run_id=r_new, tags=["quality:8.0"])
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="", now=now)
    entries = board["entries"]
    assert entries[0]["branch_def_id"] == "b-new"
    assert entries[1]["branch_def_id"] == "b-old"
    # Recency decay should differ meaningfully.
    new_decay = entries[0]["signals"]["recency_decay"]
    old_decay = entries[1]["signals"]["recency_decay"]
    assert new_decay > old_decay
    # 60 days at 30-day halflife ~ exp(-2) ~ 0.135.
    assert 0.10 < old_decay < 0.20


def test_fork_count_contributes_to_score(base_path):
    """A branch with community forks ranks above one without."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-popular", goal_id="g1")
    _make_branch(base_path, branch_def_id="b-lonely", goal_id="g1")
    # 3 forks of b-popular via parent_def_id.
    _make_branch(
        base_path, branch_def_id="fork-1",
        goal_id="g1", parent_def_id="b-popular",
    )
    _make_branch(
        base_path, branch_def_id="fork-2",
        goal_id="g1", parent_def_id="b-popular",
    )
    # 1 fork via fork_from.
    _make_branch(
        base_path, branch_def_id="fork-3",
        goal_id="g1", fork_from="b-popular",
    )
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    pop_entry = next(
        e for e in board["entries"] if e["branch_def_id"] == "b-popular"
    )
    lonely_entry = next(
        e for e in board["entries"] if e["branch_def_id"] == "b-lonely"
    )
    assert pop_entry["signals"]["fork_count"] == 3
    assert lonely_entry["signals"]["fork_count"] == 0
    assert pop_entry["score"] > lonely_entry["score"]
    assert pop_entry["rank"] < lonely_entry["rank"]


def test_failed_runs_apply_penalty(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-clean", goal_id="g1")
    _make_branch(base_path, branch_def_id="b-buggy", goal_id="g1")
    now = time.time()
    _record_run(
        base_path, branch_def_id="b-clean",
        status=RUN_STATUS_COMPLETED, finished_at=now,
    )
    _record_run(
        base_path, branch_def_id="b-buggy",
        status=RUN_STATUS_COMPLETED, finished_at=now,
    )
    for _ in range(5):
        _record_run(
            base_path, branch_def_id="b-buggy",
            status=RUN_STATUS_FAILED, finished_at=now,
        )
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="", now=now)
    clean = next(
        e for e in board["entries"] if e["branch_def_id"] == "b-clean"
    )
    buggy = next(
        e for e in board["entries"] if e["branch_def_id"] == "b-buggy"
    )
    assert buggy["signals"]["failed_run_count"] == 5
    assert clean["signals"]["failed_run_count"] == 0
    # Penalty should be visible in score_components.
    assert clean["score_components"]["failed_penalty"] == 0.0
    assert buggy["score_components"]["failed_penalty"] < 0
    assert clean["score"] > buggy["score"]


# ---------------------------------------------------------------------------
# safe_to_publish best-effort signal
# ---------------------------------------------------------------------------


def test_safe_to_publish_signal_from_branch_stats(base_path):
    _make_goal(base_path, "g1")
    _make_branch(
        base_path,
        branch_def_id="b-safe",
        goal_id="g1",
        stats={"next_action_packet": {"safe_to_publish": True}},
    )
    _make_branch(base_path, branch_def_id="b-unsafe", goal_id="g1")
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    safe = next(
        e for e in board["entries"] if e["branch_def_id"] == "b-safe"
    )
    unsafe = next(
        e for e in board["entries"] if e["branch_def_id"] == "b-unsafe"
    )
    assert safe["signals"]["safe_to_publish"] is True
    assert unsafe["signals"]["safe_to_publish"] is False
    assert safe["score"] > unsafe["score"]


def test_safe_to_publish_absent_or_falsy_does_not_crash(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-no-packet", goal_id="g1")
    _make_branch(
        base_path, branch_def_id="b-empty-packet",
        goal_id="g1", stats={"next_action_packet": {}},
    )
    _make_branch(
        base_path, branch_def_id="b-not-a-dict",
        goal_id="g1", stats={"next_action_packet": "not a packet"},
    )
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    for entry in board["entries"]:
        assert entry["signals"]["safe_to_publish"] is False


# ---------------------------------------------------------------------------
# Gate-rung signal
# ---------------------------------------------------------------------------


def test_gate_rung_signal_populates_when_claim_present(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-rung", goal_id="g1")
    _make_branch(base_path, branch_def_id="b-no-rung", goal_id="g1")
    # Insert a gate claim directly.
    from workflow.storage import _connect
    with _connect(base_path) as conn:
        conn.execute(
            """
            INSERT INTO gate_claims (
                claim_id, branch_def_id, goal_id, rung_key,
                evidence_url, evidence_note, claimed_by, claimed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "c-1", "b-rung", "g1", "submission",
                "https://example.test/x", "", "host",
                "2026-01-01T00:00:00",
            ),
        )
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    rung = next(
        e for e in board["entries"] if e["branch_def_id"] == "b-rung"
    )
    no_rung = next(
        e for e in board["entries"] if e["branch_def_id"] == "b-no-rung"
    )
    assert rung["signals"]["gate_rung_top"] == "submission"
    assert rung["signals"]["has_gate_rung"] is True
    assert no_rung["signals"]["has_gate_rung"] is False
    assert rung["score"] > no_rung["score"]


# ---------------------------------------------------------------------------
# Realistic scale — Goal with 15+ entries
# ---------------------------------------------------------------------------


def test_realistic_goal_with_fifteen_entries(base_path):
    """Smoke + correctness at the scale of Goal 4ff5862cc26d (~15+
    bound branches). Verifies rank monotonicity and that the top entry
    has the highest score."""
    _make_goal(base_path, "g-big")
    now = 1_700_000_000.0
    for i in range(18):
        bid = f"b-{i:02d}"
        _make_branch(base_path, branch_def_id=bid, goal_id="g-big")
        # Spread completed-run counts + judgment scores so ranking is
        # non-trivial.
        for _ in range(i % 5):
            rid = _record_run(
                base_path, branch_def_id=bid,
                status=RUN_STATUS_COMPLETED,
                finished_at=now - (i * 86400),  # older for higher i
            )
            _record_judgment(
                base_path, run_id=rid,
                tags=[f"quality:{(i % 9) + 1}"],
            )
    board = build_quality_leaderboard(
        base_path, goal_id="g-big", viewer="", now=now,
    )
    assert len(board["entries"]) == 18
    # Ranks are 1..18 with no gaps.
    ranks = sorted(e["rank"] for e in board["entries"])
    assert ranks == list(range(1, 19))
    # First entry's score >= every other entry's score.
    top_score = board["entries"][0]["score"]
    for entry in board["entries"][1:]:
        assert top_score >= entry["score"]


# ---------------------------------------------------------------------------
# recommend_parent_for_fork
# ---------------------------------------------------------------------------


def test_recommend_parent_returns_top_with_rationale(base_path):
    _make_goal(base_path, "g1", name="Patch Loop")
    _make_branch(
        base_path, branch_def_id="b-top",
        goal_id="g1", name="High-Quality Take",
    )
    _make_branch(base_path, branch_def_id="b-other", goal_id="g1")
    now = time.time()
    rid = _record_run(
        base_path, branch_def_id="b-top",
        status=RUN_STATUS_COMPLETED, finished_at=now,
    )
    _record_judgment(base_path, run_id=rid, tags=["quality:9.5"])
    # Add a fork of b-top so the rationale has community-vote signal.
    _make_branch(
        base_path, branch_def_id="b-top-fork",
        goal_id="g1", parent_def_id="b-top",
    )
    rec = recommend_parent_for_fork(base_path, goal_id="g1", viewer="", now=now)
    assert rec["recommended_parent"] is not None
    assert rec["recommended_parent"]["branch_def_id"] == "b-top"
    rationale = rec["rationale"]
    # Rationale should mention some of the signals we exercised.
    assert "ranked first" in rationale.lower()
    assert "judgment" in rationale.lower() or "9.5" in rationale
    assert "fork" in rationale.lower()
    assert rec["leaderboard_size"] == 3  # b-top, b-other, b-top-fork


def test_recommend_parent_no_judgments_yet_tentative_phrase(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-bare", goal_id="g1")
    rec = recommend_parent_for_fork(base_path, goal_id="g1", viewer="")
    assert rec["recommended_parent"] is not None
    # When the top entry has no signals at all, the rationale should
    # call out the lack of quality data.
    rationale_lc = rec["rationale"].lower()
    assert "tentative" in rationale_lc or "no quality signals" in rationale_lc


# ---------------------------------------------------------------------------
# Formula disclosure surfaces all weights
# ---------------------------------------------------------------------------


def test_formula_disclosure_includes_all_weights(base_path):
    _make_goal(base_path, "g1")
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    weights = board["formula"]["weights"]
    expected_keys = {
        "judgment", "runs", "forks", "recency",
        "gate", "safe_publish", "failed_penalty",
    }
    assert set(weights.keys()) == expected_keys
    # judgment_max_scale is published.
    assert board["formula"]["judgment_max_scale"] == JUDGMENT_MAX_SCALE


def test_score_components_sum_to_score(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    rid = _record_run(
        base_path, branch_def_id="b1",
        status=RUN_STATUS_COMPLETED, finished_at=time.time(),
    )
    _record_judgment(base_path, run_id=rid, tags=["quality:7"])
    board = build_quality_leaderboard(base_path, goal_id="g1", viewer="")
    entry = board["entries"][0]
    component_sum = sum(entry["score_components"].values())
    assert entry["score"] == pytest.approx(component_sum, abs=1e-3)


# ---------------------------------------------------------------------------
# Determinism — same input -> same ranking
# ---------------------------------------------------------------------------


def test_ranking_is_deterministic(base_path):
    _make_goal(base_path, "g1")
    for i in range(5):
        _make_branch(base_path, branch_def_id=f"b{i}", goal_id="g1")
    now = 1_700_000_000.0
    board_a = build_quality_leaderboard(
        base_path, goal_id="g1", viewer="", now=now,
    )
    board_b = build_quality_leaderboard(
        base_path, goal_id="g1", viewer="", now=now,
    )
    assert [
        e["branch_def_id"] for e in board_a["entries"]
    ] == [
        e["branch_def_id"] for e in board_b["entries"]
    ]
