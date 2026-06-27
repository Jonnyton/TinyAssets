"""Tests for the node-performance evaluator / auto-promotion engine.

`tinyassets/node_eval.py` tracks per-node execution outcomes in a SQLite
DB and auto-promotes / auto-flags nodes based on success-rate and
eval-score thresholds. Load-bearing for the autoresearch track (§33):
an unreliable evaluator would silently promote bad nodes or flag good
ones.

Tests use a tmp_path SQLite per case — no shared state across tests.
"""

from __future__ import annotations

import time

import pytest

from tinyassets.node_eval import (
    FLAGGING_MAX_CONSECUTIVE_FAILURES,
    FLAGGING_MAX_SUCCESS_RATE,
    FLAGGING_MIN_EXECUTIONS,
    PROMOTION_MIN_EVAL_SCORE,
    PROMOTION_MIN_EXECUTIONS,
    PROMOTION_MIN_SUCCESS_RATE,
    ExecutionRecord,
    NodeEvaluator,
    NodeStats,
    NodeStatus,
)


@pytest.fixture
def evaluator(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    db = tmp_path / "node_eval.db"
    ev = NodeEvaluator(db_path=db)
    yield ev
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA wal_checkpoint(FULL)")
    conn.close()


def _record(
    evaluator: NodeEvaluator,
    node_id: str,
    *,
    success: bool,
    duration: float = 0.1,
    error: str = "",
    eval_score: float | None = None,
) -> None:
    evaluator.record(
        ExecutionRecord(
            node_id=node_id,
            universe_id="u-test",
            success=success,
            duration_seconds=duration,
            error=error,
            eval_score=eval_score,
        )
    )


# -------------------------------------------------------------------
# DB initialization + basic record/read
# -------------------------------------------------------------------


def test_initialization_creates_db_and_parent_dirs(tmp_path):
    nested = tmp_path / "nested" / "node_eval.db"
    assert not nested.parent.exists()

    NodeEvaluator(db_path=nested)

    assert nested.exists()


def test_record_and_get_stats_roundtrip(evaluator):
    _record(evaluator, "alpha", success=True, duration=0.5)
    _record(evaluator, "alpha", success=True, duration=0.3)
    _record(evaluator, "alpha", success=False, duration=1.2, error="boom")

    stats = evaluator.get_stats("alpha")

    assert isinstance(stats, NodeStats)
    assert stats.total_executions == 3
    assert stats.successful_executions == 2
    assert stats.failed_executions == 1
    assert stats.success_rate == pytest.approx(2 / 3)
    assert stats.avg_duration == pytest.approx((0.5 + 0.3 + 1.2) / 3)


def test_get_stats_unknown_node_returns_empty(evaluator):
    """An un-recorded node yields zeroed stats with PENDING status."""
    stats = evaluator.get_stats("ghost")

    assert stats.total_executions == 0
    assert stats.success_rate == 0.0
    assert stats.current_status == NodeStatus.PENDING
    assert stats.avg_eval_score is None


def test_timeout_count_is_detected_from_error_text(evaluator):
    """Executions with 'timed out' in error text count toward timeout_count."""
    _record(evaluator, "timer", success=False, error="Execution timed out after 5s")
    _record(evaluator, "timer", success=False, error="some other failure")
    _record(evaluator, "timer", success=True)

    stats = evaluator.get_stats("timer")

    assert stats.total_executions == 3
    assert stats.timeout_count == 1


# -------------------------------------------------------------------
# Auto-promotion
# -------------------------------------------------------------------


def test_auto_promotion_fires_after_trial_hits_thresholds(evaluator):
    """Trial node with ≥PROMOTION_MIN_EXECUTIONS at ≥PROMOTION_MIN_SUCCESS_RATE → PROMOTED."""
    evaluator.set_status("autopromote", NodeStatus.TRIAL)

    # PROMOTION_MIN_EXECUTIONS = 10 successful runs.
    for _ in range(PROMOTION_MIN_EXECUTIONS):
        _record(evaluator, "autopromote", success=True)

    stats = evaluator.get_stats("autopromote")
    assert stats.current_status == NodeStatus.PROMOTED
    assert stats.success_rate >= PROMOTION_MIN_SUCCESS_RATE


def test_pending_does_not_auto_promote(evaluator):
    """Auto-promotion only fires from TRIAL, not from PENDING."""
    # No explicit set_status → defaults to PENDING.
    for _ in range(PROMOTION_MIN_EXECUTIONS):
        _record(evaluator, "pending_node", success=True)

    stats = evaluator.get_stats("pending_node")
    assert stats.current_status == NodeStatus.PENDING


def test_promotion_blocked_by_low_eval_score(evaluator):
    """Even with high success rate, low avg_eval_score must block promotion."""
    evaluator.set_status("low_eval", NodeStatus.TRIAL)

    for _ in range(PROMOTION_MIN_EXECUTIONS):
        _record(
            evaluator, "low_eval",
            success=True,
            eval_score=PROMOTION_MIN_EVAL_SCORE - 0.2,
        )

    stats = evaluator.get_stats("low_eval")
    assert stats.current_status == NodeStatus.TRIAL  # NOT promoted
    assert stats.success_rate == 1.0


# -------------------------------------------------------------------
# Auto-flagging
# -------------------------------------------------------------------


def test_auto_flag_fires_on_low_success_rate(evaluator):
    """Trial node with ≥FLAGGING_MIN_EXECUTIONS at ≤FLAGGING_MAX_SUCCESS_RATE → FLAGGED."""
    evaluator.set_status("flagger", NodeStatus.TRIAL)

    # Mostly-failing pattern. FLAGGING_MIN_EXECUTIONS = 5, max success rate = 0.5.
    for i in range(FLAGGING_MIN_EXECUTIONS + 2):
        _record(evaluator, "flagger", success=(i == 0))  # 1 success out of 7

    stats = evaluator.get_stats("flagger")
    assert stats.current_status == NodeStatus.FLAGGED


def test_auto_flag_fires_on_consecutive_failures(evaluator):
    """FLAGGING_MAX_CONSECUTIVE_FAILURES failures in a row flags even a healthy history."""
    evaluator.set_status("streaky", NodeStatus.PROMOTED)

    # Healthy prior history (so overall success_rate stays well above 0.5).
    for _ in range(20):
        _record(evaluator, "streaky", success=True)

    assert evaluator.get_stats("streaky").current_status == NodeStatus.PROMOTED

    # Now 3 failures in a row → auto-flag via the consecutive-failures rule.
    for _ in range(FLAGGING_MAX_CONSECUTIVE_FAILURES):
        _record(evaluator, "streaky", success=False, error="burst")

    stats = evaluator.get_stats("streaky")
    assert stats.current_status == NodeStatus.FLAGGED
    # Overall success_rate is still above FLAGGING_MAX_SUCCESS_RATE,
    # so this must have fired via the consecutive-failures path.
    assert stats.success_rate > FLAGGING_MAX_SUCCESS_RATE


def test_promoted_can_be_flagged_on_degradation(evaluator):
    """A PROMOTED node that degrades past FLAGGING thresholds gets re-flagged."""
    evaluator.set_status("degrader", NodeStatus.PROMOTED)

    # PROMOTED can flag on either low success rate OR 3-in-a-row.
    # Use overall low rate path: 6 runs, 1 success → 16.7%.
    _record(evaluator, "degrader", success=True)
    for _ in range(5):
        _record(evaluator, "degrader", success=False)

    stats = evaluator.get_stats("degrader")
    assert stats.current_status == NodeStatus.FLAGGED


# -------------------------------------------------------------------
# Host overrides
# -------------------------------------------------------------------


def test_host_override_disable_sticks(evaluator):
    """set_status(DISABLED) persists across records."""
    evaluator.set_status("disabled_one", NodeStatus.TRIAL)
    _record(evaluator, "disabled_one", success=True)
    evaluator.set_status("disabled_one", NodeStatus.DISABLED, reason="host call", by="host")

    # More records — should not auto-promote a DISABLED node.
    for _ in range(PROMOTION_MIN_EXECUTIONS):
        _record(evaluator, "disabled_one", success=True)

    stats = evaluator.get_stats("disabled_one")
    assert stats.current_status == NodeStatus.DISABLED


def test_manual_promotion_allowed(evaluator):
    """Host can promote a node directly without waiting for thresholds."""
    evaluator.set_status("fast_track", NodeStatus.PROMOTED, by="host")

    stats = evaluator.get_stats("fast_track")
    assert stats.current_status == NodeStatus.PROMOTED


# -------------------------------------------------------------------
# Queries (leaderboard, promoted/trial/flagged lists, history)
# -------------------------------------------------------------------


def test_leaderboard_ranks_by_success_rate_then_total(evaluator):
    # Two nodes, same success rate, different volume.
    for _ in range(10):
        _record(evaluator, "volume", success=True)
    for _ in range(3):
        _record(evaluator, "novice", success=True)

    # One with a lower success rate.
    for i in range(10):
        _record(evaluator, "mediocre", success=(i % 2 == 0))

    board = evaluator.get_leaderboard(limit=10)

    ids_in_order = [row["node_id"] for row in board]
    # Both volume + novice at 100% rank above mediocre at 50%.
    assert ids_in_order.index("volume") < ids_in_order.index("mediocre")
    assert ids_in_order.index("novice") < ids_in_order.index("mediocre")
    # Tie-breaker: higher total wins.
    assert ids_in_order.index("volume") < ids_in_order.index("novice")


def test_get_promoted_nodes_lists_only_promoted(evaluator):
    evaluator.set_status("p1", NodeStatus.PROMOTED)
    evaluator.set_status("p2", NodeStatus.PROMOTED)
    evaluator.set_status("t1", NodeStatus.TRIAL)
    evaluator.set_status("f1", NodeStatus.FLAGGED)

    promoted = evaluator.get_promoted_nodes()

    assert sorted(promoted) == ["p1", "p2"]


def test_get_flagged_returns_structured_with_reason(evaluator):
    evaluator.set_status("bad", NodeStatus.FLAGGED, reason="too many crashes")

    flagged = evaluator.get_flagged_nodes()

    assert len(flagged) == 1
    assert flagged[0]["node_id"] == "bad"
    assert flagged[0]["reason"] == "too many crashes"


def test_execution_history_ordered_newest_first_with_limit(evaluator):
    for i in range(5):
        _record(evaluator, "hist", success=True, duration=float(i))
        # Force a stable timestamp ordering via a micro-sleep.
        time.sleep(0.001)

    history = evaluator.get_execution_history("hist", limit=3)

    assert len(history) == 3
    # Newest-first: durations should be descending (4, 3, 2).
    assert [round(h["duration_seconds"]) for h in history] == [4, 3, 2]


# -------------------------------------------------------------------
# Eligibility flags on NodeStats
# -------------------------------------------------------------------


def test_promotion_eligible_flag_set_on_trial_hitting_thresholds(evaluator):
    evaluator.set_status("candidate", NodeStatus.TRIAL)
    for _ in range(PROMOTION_MIN_EXECUTIONS):
        _record(evaluator, "candidate", success=True)

    stats = evaluator.get_stats("candidate")

    # Auto-promotion flipped status; eligibility should reflect the old-or-new
    # status rules (only TRIAL or FLAGGED are eligible).
    # Since it auto-promoted, it's PROMOTED — eligibility becomes False.
    assert stats.current_status == NodeStatus.PROMOTED
    assert stats.promotion_eligible is False


def test_flag_eligible_flag_set_on_low_success_rate(evaluator):
    evaluator.set_status("slipping", NodeStatus.PROMOTED)
    # 5 runs, 2 successes → 40% success rate (≤ FLAGGING_MAX_SUCCESS_RATE).
    for i in range(FLAGGING_MIN_EXECUTIONS):
        _record(evaluator, "slipping", success=(i < 2))

    stats = evaluator.get_stats("slipping")

    # Auto-flag fires; post-flag status is FLAGGED, which isn't in the
    # flag_eligible predicate (that's TRIAL/PROMOTED only).
    assert stats.current_status == NodeStatus.FLAGGED
    assert stats.flag_eligible is False


# -------------------------------------------------------------------
# to_dict surfaces
# -------------------------------------------------------------------


def test_node_stats_to_dict_rounds_and_serializes():
    stats = NodeStats(
        node_id="x",
        total_executions=3,
        successful_executions=2,
        failed_executions=1,
        avg_duration=0.123456,
        avg_eval_score=0.789012,
        success_rate=0.66666,
        current_status=NodeStatus.TRIAL,
    )

    d = stats.to_dict()

    assert d["success_rate"] == 0.667
    assert d["avg_duration"] == 0.123
    assert d["avg_eval_score"] == 0.789
    assert d["current_status"] == "trial"


def test_execution_record_to_dict_preserves_all_fields():
    rec = ExecutionRecord(
        node_id="x",
        universe_id="u",
        success=True,
        duration_seconds=1.5,
        error="",
        eval_score=0.9,
        eval_notes="good",
    )

    d = rec.to_dict()

    for key in (
        "node_id", "universe_id", "success", "duration_seconds",
        "error", "eval_score", "eval_notes", "timestamp",
    ):
        assert key in d
    assert d["eval_score"] == 0.9
    assert d["eval_notes"] == "good"
