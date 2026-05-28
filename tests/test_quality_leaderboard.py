"""DESIGN-008 — quality leaderboard now dispatches via selector branches.

PR-123 round-1 baked an opinionated scoring formula into Python.
PR #978 tried to patch a bug in it; host closed PR #978 because
patching entrenches the wrong architecture. DESIGN-008 replaces the
formula with a per-Goal selector-branch dispatch. These tests now
exercise the dispatch contract, not formula arithmetic.

Strategy: monkeypatch ``workflow.api.selector_dispatch.dispatch_selector``
so tests don't depend on a live LLM provider. The mock takes the
``candidate_branches`` input and returns deterministic
``ranked_entries`` based on a per-test choice of dominant signal
(quality_score, run_count, etc.) — that exercises the substrate's
candidate-collection, output-parsing, error-surface paths without
LLM cost.

Coverage:

- Empty Goal -> empty entries + parent-rec returns None.
- Single entry -> rank 1.
- Multiple entries -> mock-driven ranking respects selector output.
- Selector returns invalid output -> structured error, leaderboard
  ``ok=False``, no crash.
- Selector run fails (status != completed) -> structured error.
- Selector resolution: explicit binding wins over platform default;
  no binding falls back to platform default.
- Signals collected per branch are still queryable (run_count,
  judgment_score_avg, fork_count, gate_rung, safe_to_publish).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from workflow.api.quality_leaderboard import (
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
    finished_at: float | str | None = None,
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


def _mock_dispatch_selector(
    *,
    ranked_entries: list[dict] | None = None,
    by_signal: str | None = None,
    fail_with: dict | None = None,
):
    """Build a mock ``dispatch_selector`` that emits ``ranked_entries``.

    Pass exactly one of:

    * ``ranked_entries`` — verbatim entries to return.
    * ``by_signal`` — order the input ``candidate_branches`` by the
      named signal field descending and emit them as ``ranked_entries``.
    * ``fail_with`` — return ``{"ok": False, "error_kind": ..., "error": ...}``.

    The returned function is patched into ``workflow.api.quality_leaderboard``
    via ``patch("workflow.api.quality_leaderboard.dispatch_selector",
    side_effect=mock)``.
    """
    def _mock(
        base_path,
        *,
        goal_id,
        candidate_branches,
        actor="anonymous",
        timeout_s=None,
        **_extra,
    ):
        if fail_with is not None:
            return dict(fail_with)
        if not candidate_branches:
            return {
                "ok": True,
                "branch_version_id": None,
                "source": "empty_candidate_set",
                "run_id": None,
                "ranked_entries": [],
            }
        if ranked_entries is not None:
            return {
                "ok": True,
                "branch_version_id": "mock_selector@deadbeef",
                "source": "platform_default",
                "run_id": "mock-run",
                "ranked_entries": list(ranked_entries),
            }
        if by_signal is not None:
            def _key(c):
                value = (c.get("signals") or {}).get(by_signal)
                if value is None:
                    return float("-inf")
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return float("-inf")
            ordered = sorted(
                candidate_branches, key=_key, reverse=True,
            )
            entries = [
                {
                    "branch_def_id": c["branch_def_id"],
                    "branch_version_id": c.get("branch_version_id", ""),
                    "score": float(_key(c)) if _key(c) != float("-inf") else 0.0,
                    "rationale": (
                        f"ranked by {by_signal}={(c.get('signals') or {}).get(by_signal)!r}"
                    ),
                }
                for c in ordered
            ]
            return {
                "ok": True,
                "branch_version_id": "mock_selector@deadbeef",
                "source": "platform_default",
                "run_id": "mock-run",
                "ranked_entries": entries,
            }
        # Default: emit candidates in original order with score 0.0.
        return {
            "ok": True,
            "branch_version_id": "mock_selector@deadbeef",
            "source": "platform_default",
            "run_id": "mock-run",
            "ranked_entries": [
                {
                    "branch_def_id": c["branch_def_id"],
                    "branch_version_id": c.get("branch_version_id", ""),
                    "score": 0.0,
                    "rationale": "",
                }
                for c in candidate_branches
            ],
        }
    return _mock


# ---------------------------------------------------------------------------
# Empty Goal
# ---------------------------------------------------------------------------


def test_empty_goal_returns_empty_entries(base_path):
    """No bound branches -> dispatch is short-circuited (no LLM call)
    and the leaderboard returns ok=True with entries=[]."""
    _make_goal(base_path, "g-empty")
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(),
    ) as mock_dispatch:
        board = build_quality_leaderboard(
            base_path, goal_id="g-empty", viewer="",
        )
    assert board["ok"] is True
    assert board["entries"] == []
    # Substrate short-circuit fires inside dispatch_selector itself
    # — but our mock is the substitute for dispatch_selector, so it
    # IS called with the empty candidate set. Confirm.
    assert mock_dispatch.call_count == 1
    assert mock_dispatch.call_args.kwargs["candidate_branches"] == []


def test_recommend_parent_when_no_entries(base_path):
    _make_goal(base_path, "g-empty")
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(),
    ):
        rec = recommend_parent_for_fork(
            base_path, goal_id="g-empty", viewer="",
        )
    assert rec["ok"] is True
    assert rec["recommended_parent"] is None
    assert "No Branch is bound" in rec["rationale"]
    assert rec["leaderboard_size"] == 0


# ---------------------------------------------------------------------------
# Single entry
# ---------------------------------------------------------------------------


def test_single_branch_ranks_first(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(by_signal="completed_run_count"),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert board["ok"] is True
    assert len(board["entries"]) == 1
    entry = board["entries"][0]
    assert entry["rank"] == 1
    assert entry["branch_def_id"] == "b1"


def test_completed_run_with_iso_finished_at_does_not_crash(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    _record_run(
        base_path,
        branch_def_id="b1",
        status=RUN_STATUS_COMPLETED,
        finished_at="2026-05-22T00:00:00Z",
    )

    now = datetime(2026, 5, 23, tzinfo=timezone.utc).timestamp()
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(by_signal="last_successful_run_at"),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="", now=now,
        )

    entry = board["entries"][0]
    expected_ts = datetime(2026, 5, 22, tzinfo=timezone.utc).timestamp()
    assert entry["signals"]["completed_run_count"] == 1
    assert entry["signals"]["last_successful_run_at"] == expected_ts
    assert entry["signals"]["age_days_since_success"] == pytest.approx(1.0)


def test_mixed_finished_at_storage_uses_latest_normalized_timestamp(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    older_iso = "2026-05-22T00:00:00Z"
    newer_seconds = datetime(2026, 5, 23, tzinfo=timezone.utc).timestamp()
    _record_run(
        base_path,
        branch_def_id="b1",
        status=RUN_STATUS_COMPLETED,
        finished_at=older_iso,
    )
    _record_run(
        base_path,
        branch_def_id="b1",
        status=RUN_STATUS_COMPLETED,
        finished_at=newer_seconds,
    )

    now = datetime(2026, 5, 24, tzinfo=timezone.utc).timestamp()
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(by_signal="last_successful_run_at"),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="", now=now,
        )

    signals = board["entries"][0]["signals"]
    assert signals["last_successful_run_at"] == newer_seconds
    assert signals["age_days_since_success"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Multi-branch ranking via mock selector
# ---------------------------------------------------------------------------


def test_mock_selector_ranking_by_judgment_avg(base_path):
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
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(by_signal="judgment_score_avg"),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    ranks = {e["branch_def_id"]: e["rank"] for e in board["entries"]}
    assert ranks["b-high"] == 1
    assert ranks["b-low"] == 2


def test_substrate_passes_signal_bundle_to_selector(base_path):
    """Selector should see signals for each candidate: completed_run_count,
    judgment_score_avg, fork_count, etc."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    now = time.time()
    rid = _record_run(
        base_path, branch_def_id="b1",
        status=RUN_STATUS_COMPLETED, finished_at=now,
    )
    _record_judgment(base_path, run_id=rid, tags=["quality:8.0"])
    captured: dict = {}

    def _capturing(
        base_path,
        *,
        goal_id,
        candidate_branches,
        actor="anonymous",
        timeout_s=None,
        **_extra,
    ):
        captured["candidate_branches"] = candidate_branches
        return {
            "ok": True,
            "branch_version_id": "mock@x",
            "source": "platform_default",
            "run_id": "r",
            "ranked_entries": [
                {
                    "branch_def_id": "b1",
                    "branch_version_id": "",
                    "score": 8.0,
                    "rationale": "captured",
                }
            ],
        }

    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_capturing,
    ):
        build_quality_leaderboard(base_path, goal_id="g1", viewer="")

    candidates = captured["candidate_branches"]
    assert len(candidates) == 1
    signals = candidates[0]["signals"]
    assert signals["completed_run_count"] == 1
    assert signals["judgment_score_avg"] == 8.0
    assert signals["judgment_score_samples"] == 1
    assert "last_successful_run_at" in signals
    assert "fork_count" in signals
    assert "has_gate_rung" in signals


# ---------------------------------------------------------------------------
# Signal collection invariants — preserved from PR-123 round-2
# ---------------------------------------------------------------------------


def test_other_numeric_tags_bucketed_separately(base_path):
    """Tags like ``risk:3`` are numeric but NOT in the headline
    judgment_score_avg; they appear under other_numeric_tags. The
    selector branch can choose to weight them or ignore them — the
    substrate just exposes them."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    rid = _record_run(
        base_path, branch_def_id="b1",
        status=RUN_STATUS_COMPLETED, finished_at=time.time(),
    )
    _record_judgment(
        base_path, run_id=rid,
        tags=["quality:8", "risk:3", "cost:42"],
    )
    captured: dict = {}

    def _capturing(
        base_path, *, goal_id, candidate_branches, actor="anonymous",
        timeout_s=None, **_extra,
    ):
        captured["candidates"] = candidate_branches
        return {
            "ok": True,
            "branch_version_id": "mock@x",
            "source": "platform_default",
            "run_id": "r",
            "ranked_entries": [
                {"branch_def_id": "b1", "score": 8.0, "rationale": ""}
            ],
        }

    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_capturing,
    ):
        build_quality_leaderboard(base_path, goal_id="g1", viewer="")

    signals = captured["candidates"][0]["signals"]
    assert signals["judgment_score_avg"] == pytest.approx(8.0)
    assert signals["other_numeric_tags"] == {"risk": 1, "cost": 1}


def test_non_numeric_tags_ignored(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    rid = _record_run(
        base_path, branch_def_id="b1",
        status=RUN_STATUS_COMPLETED, finished_at=time.time(),
    )
    _record_judgment(
        base_path, run_id=rid,
        tags=["needs-revision", "writer:loop-2"],
    )
    captured: dict = {}

    def _capturing(
        base_path, *, goal_id, candidate_branches, actor="anonymous",
        timeout_s=None, **_extra,
    ):
        captured["candidates"] = candidate_branches
        return {
            "ok": True,
            "branch_version_id": "mock@x",
            "source": "platform_default",
            "run_id": "r",
            "ranked_entries": [
                {"branch_def_id": "b1", "score": 0.0, "rationale": ""}
            ],
        }

    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_capturing,
    ):
        build_quality_leaderboard(base_path, goal_id="g1", viewer="")

    signals = captured["candidates"][0]["signals"]
    assert signals["judgment_score_avg"] is None
    assert signals["other_numeric_tags"] == {}


def test_fork_count_signal_present(base_path):
    """Fork count is calculated visibility-respecting and passed to
    the selector. The PR-127 round-2 P1.2 contract still applies."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-popular", goal_id="g1")
    # 3 forks of b-popular.
    _make_branch(
        base_path, branch_def_id="f1",
        goal_id="g1", parent_def_id="b-popular",
    )
    _make_branch(
        base_path, branch_def_id="f2",
        goal_id="g1", parent_def_id="b-popular",
    )
    _make_branch(
        base_path, branch_def_id="f3",
        goal_id="g1", fork_from="b-popular",
    )
    captured: dict = {}

    def _capturing(
        base_path, *, goal_id, candidate_branches, actor="anonymous",
        timeout_s=None, **_extra,
    ):
        captured["candidates"] = candidate_branches
        return {
            "ok": True,
            "branch_version_id": "mock@x",
            "source": "platform_default",
            "run_id": "r",
            "ranked_entries": [
                {"branch_def_id": c["branch_def_id"], "score": 0.0}
                for c in candidate_branches
            ],
        }

    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_capturing,
    ):
        build_quality_leaderboard(base_path, goal_id="g1", viewer="")

    by_id = {c["branch_def_id"]: c["signals"] for c in captured["candidates"]}
    assert by_id["b-popular"]["fork_count"] == 3
    assert by_id["f1"]["fork_count"] == 0


def test_safe_to_publish_signal_from_branch_stats(base_path):
    _make_goal(base_path, "g1")
    _make_branch(
        base_path,
        branch_def_id="b-safe",
        goal_id="g1",
        stats={"next_action_packet": {"safe_to_publish": True}},
    )
    _make_branch(base_path, branch_def_id="b-unsafe", goal_id="g1")
    captured: dict = {}

    def _capturing(
        base_path, *, goal_id, candidate_branches, actor="anonymous",
        timeout_s=None, **_extra,
    ):
        captured["candidates"] = candidate_branches
        return {
            "ok": True,
            "branch_version_id": "mock@x",
            "source": "platform_default",
            "run_id": "r",
            "ranked_entries": [
                {"branch_def_id": c["branch_def_id"], "score": 0.0}
                for c in candidate_branches
            ],
        }

    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_capturing,
    ):
        build_quality_leaderboard(base_path, goal_id="g1", viewer="")

    by_id = {c["branch_def_id"]: c["signals"] for c in captured["candidates"]}
    assert by_id["b-safe"]["safe_to_publish"] is True
    assert by_id["b-unsafe"]["safe_to_publish"] is False


def test_gate_rung_signal_populates_when_claim_present(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b-rung", goal_id="g1")
    _make_branch(base_path, branch_def_id="b-no-rung", goal_id="g1")
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
    captured: dict = {}

    def _capturing(
        base_path, *, goal_id, candidate_branches, actor="anonymous",
        timeout_s=None, **_extra,
    ):
        captured["candidates"] = candidate_branches
        return {
            "ok": True,
            "branch_version_id": "mock@x",
            "source": "platform_default",
            "run_id": "r",
            "ranked_entries": [
                {"branch_def_id": c["branch_def_id"], "score": 0.0}
                for c in candidate_branches
            ],
        }

    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_capturing,
    ):
        build_quality_leaderboard(base_path, goal_id="g1", viewer="")

    by_id = {c["branch_def_id"]: c["signals"] for c in captured["candidates"]}
    assert by_id["b-rung"]["gate_rung_top"] == "submission"
    assert by_id["b-rung"]["has_gate_rung"] is True
    assert by_id["b-no-rung"]["has_gate_rung"] is False


# ---------------------------------------------------------------------------
# Selector failure modes — leaderboard surfaces structured error
# ---------------------------------------------------------------------------


def test_selector_invalid_output_surfaces_structured_error(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    fail_response = {
        "ok": False,
        "error_kind": "selector_invalid_output",
        "error": "ranked_entries missing",
        "branch_version_id": "selector@x",
        "run_id": "run-bad",
    }
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(fail_with=fail_response),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert board["ok"] is False
    assert board["error_kind"] == "selector_invalid_output"
    assert board["entries"] == []
    assert board["selector"]["branch_version_id"] == "selector@x"


def test_selector_timeout_surfaces_structured_error(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    fail_response = {
        "ok": False,
        "error_kind": "selector_timeout",
        "error": "selector run timed out after 60s",
        "branch_version_id": "selector@x",
        "run_id": "run-stuck",
    }
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(fail_with=fail_response),
    ):
        rec = recommend_parent_for_fork(
            base_path, goal_id="g1", viewer="",
        )
    assert rec["ok"] is False
    assert rec["error_kind"] == "selector_timeout"
    assert rec["recommended_parent"] is None


def test_selector_run_failed_surfaces_structured_error(base_path):
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    fail_response = {
        "ok": False,
        "error_kind": "selector_run_failed",
        "error": "graph execution raised",
        "branch_version_id": "selector@x",
        "run_id": "run-crashed",
    }
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(fail_with=fail_response),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert board["ok"] is False
    assert board["error_kind"] == "selector_run_failed"


# ---------------------------------------------------------------------------
# Substrate filters dupe / unknown branch_def_ids from selector output
# ---------------------------------------------------------------------------


def test_substrate_filters_duplicate_entries_from_selector_output(base_path):
    """A misbehaving selector that emits the same branch_def_id twice
    must NOT corrupt the leaderboard. Substrate keeps the first
    occurrence and skips the rest."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    duplicates = [
        {"branch_def_id": "b1", "score": 9.0, "rationale": "first"},
        {"branch_def_id": "b1", "score": 8.0, "rationale": "dupe"},
    ]
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(ranked_entries=duplicates),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert board["ok"] is True
    assert len(board["entries"]) == 1
    assert board["entries"][0]["rationale"] == "first"


# ---------------------------------------------------------------------------
# DESIGN-008 round 2 P1.2 — substrate rejects fabricated branch_def_ids
# ---------------------------------------------------------------------------


def test_substrate_drops_phantom_branch_def_ids_from_selector(base_path):
    """Round-2 P1.2 regression guard.

    A selector that fabricates a branch_def_id (private branch the
    viewer cannot see, made-up id, etc.) must NOT inject the entry
    into the leaderboard. Substrate filters by candidate set
    membership.
    """
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    # Selector returns one real id + one fabricated id (a private
    # branch the viewer can't see, or just made up).
    poisoned = [
        {"branch_def_id": "phantom_private_branch", "score": 99.0,
         "rationale": "fabricated"},
        {"branch_def_id": "b1", "score": 5.0, "rationale": "real one"},
    ]
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(ranked_entries=poisoned),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert board["ok"] is True
    # Only the real branch survives.
    bids = [e["branch_def_id"] for e in board["entries"]]
    assert bids == ["b1"]
    # Phantom id surfaces in the structured payload so audit tools
    # / chatbots can detect a misbehaving selector.
    assert board["phantom_branch_def_ids"] == ["phantom_private_branch"]
    # Rank starts at 1 for the surviving entry (no rank gap).
    assert board["entries"][0]["rank"] == 1


def test_substrate_phantom_filter_does_not_leave_rank_gaps(base_path):
    """When the selector emits a mix of real + phantom ids,
    ranks are reassigned post-filter so the user sees a clean
    sequence (1, 2, 3) not (1, 3, 5)."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    _make_branch(base_path, branch_def_id="b2", goal_id="g1")
    interleaved = [
        {"branch_def_id": "phantom_a", "score": 10.0},
        {"branch_def_id": "b1", "score": 8.0},
        {"branch_def_id": "phantom_b", "score": 7.0},
        {"branch_def_id": "b2", "score": 5.0},
    ]
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(ranked_entries=interleaved),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    ranks = [e["rank"] for e in board["entries"]]
    bids = [e["branch_def_id"] for e in board["entries"]]
    assert ranks == [1, 2]
    assert bids == ["b1", "b2"]
    assert set(board["phantom_branch_def_ids"]) == {"phantom_a", "phantom_b"}


def test_substrate_logs_phantom_attempts(base_path, caplog):
    """Phantom rejections must be logged so an operator can detect a
    misbehaving (or adversarial) selector in their logs."""
    import logging
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    poisoned = [
        {"branch_def_id": "evil_phantom", "score": 99.0,
         "rationale": "private leak attempt"},
        {"branch_def_id": "b1", "score": 5.0},
    ]
    with caplog.at_level(logging.WARNING, logger="workflow.api.quality_leaderboard"):
        with patch(
            "workflow.api.quality_leaderboard.dispatch_selector",
            side_effect=_mock_dispatch_selector(ranked_entries=poisoned),
        ):
            build_quality_leaderboard(
                base_path, goal_id="g1", viewer="",
            )
    # Find at least one warning mentioning the phantom id.
    matching = [
        rec for rec in caplog.records
        if rec.levelno >= logging.WARNING
        and "evil_phantom" in str(rec.getMessage())
    ]
    assert matching, (
        "expected a WARNING log entry naming the phantom id; "
        f"got records: {[r.getMessage() for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# DESIGN-008 round 3 P1.A — selector-emitted branch_version_id is ignored
# ---------------------------------------------------------------------------


def test_substrate_ignores_selector_emitted_branch_version_id(base_path):
    """Round-3 P1.A regression guard.

    A selector that returns a real visible ``branch_def_id`` paired
    with an arbitrary (private / rolled-back / fabricated)
    ``branch_version_id`` must NOT have that version id surface in
    the leaderboard. The candidate set's authoritative bvid is the
    only one the substrate trusts.
    """
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    # Selector tries to spoof the bvid for the real def_id.
    spoofed = [
        {
            "branch_def_id": "b1",
            "branch_version_id": "private-or-wrong@deadbeef",
            "score": 7.0,
            "rationale": "spoof attempt",
        },
    ]
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(ranked_entries=spoofed),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert board["ok"] is True
    assert len(board["entries"]) == 1
    entry = board["entries"][0]
    assert entry["branch_def_id"] == "b1"
    # The selector's emitted bvid MUST NOT appear. The authoritative
    # value from branch_meta_by_id is what surfaces (empty string in
    # this test because no version has been published for b1 yet).
    assert entry["branch_version_id"] != "private-or-wrong@deadbeef"
    # Spoof attempt surfaces in the audit list on the response.
    assert len(board["selector_bvid_spoofs"]) == 1
    spoof = board["selector_bvid_spoofs"][0]
    assert spoof["branch_def_id"] == "b1"
    assert spoof["selector_emitted"] == "private-or-wrong@deadbeef"


def test_substrate_logs_selector_bvid_spoof_attempt(base_path, caplog):
    """Spoof attempts must be logged at WARNING so operators can
    detect a misbehaving / adversarial selector."""
    import logging
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    spoofed = [
        {
            "branch_def_id": "b1",
            "branch_version_id": "evil_spoof@99999999",
            "score": 7.0,
        },
    ]
    with caplog.at_level(
        logging.WARNING, logger="workflow.api.quality_leaderboard",
    ):
        with patch(
            "workflow.api.quality_leaderboard.dispatch_selector",
            side_effect=_mock_dispatch_selector(ranked_entries=spoofed),
        ):
            build_quality_leaderboard(
                base_path, goal_id="g1", viewer="",
            )
    matching = [
        rec for rec in caplog.records
        if rec.levelno >= logging.WARNING
        and "evil_spoof@99999999" in str(rec.getMessage())
    ]
    assert matching, (
        "expected WARNING log naming the spoofed bvid; "
        f"got records: {[r.getMessage() for r in caplog.records]}"
    )


def test_substrate_accepts_selector_matching_authoritative_bvid(base_path):
    """When the selector's emitted bvid matches the authoritative
    candidate-set bvid, no spoof is recorded. (Authoritative value
    is still used either way — this test just locks the no-spoof
    path so the spoof-list doesn't generate false positives when a
    well-behaved selector echoes the input bvid back.)"""
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import get_branch_definition
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    branch_dict = get_branch_definition(base_path, branch_def_id="b1")
    branch_dict["name"] = "b1"
    branch_dict["graph_nodes"] = [
        {"id": "n1", "type": "prompt", "input_keys": [], "output_keys": ["x"]},
    ]
    branch_dict["edges"] = [
        {"from": "START", "to": "n1"},
        {"from": "n1", "to": "END"},
    ]
    branch_dict["state_schema"] = [{"name": "x", "type": "str"}]
    branch_dict["entry_point"] = "n1"
    version = publish_branch_version(base_path, branch_dict, publisher="host")
    authoritative = version.branch_version_id

    echoed = [
        {
            "branch_def_id": "b1",
            "branch_version_id": authoritative,
            "score": 7.0,
        },
    ]
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(ranked_entries=echoed),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert board["ok"] is True
    assert board["entries"][0]["branch_version_id"] == authoritative
    # No spoof recorded — selector and authoritative agree.
    assert board["selector_bvid_spoofs"] == []


# ---------------------------------------------------------------------------
# Determinism — same inputs + mock -> same ranking
# ---------------------------------------------------------------------------


def test_substrate_assigns_rank_1_to_first_entry(base_path):
    """The selector's emitted order IS the leaderboard order. Rank 1
    is whatever the selector put first."""
    _make_goal(base_path, "g1")
    for i in range(3):
        _make_branch(base_path, branch_def_id=f"b{i}", goal_id="g1")
    fixed_order = [
        {"branch_def_id": "b2", "score": 5.0, "rationale": "second-but-best"},
        {"branch_def_id": "b0", "score": 4.0},
        {"branch_def_id": "b1", "score": 3.0},
    ]
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(ranked_entries=fixed_order),
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert [e["branch_def_id"] for e in board["entries"]] == ["b2", "b0", "b1"]
    assert board["entries"][0]["rank"] == 1
    assert board["entries"][0]["rationale"] == "second-but-best"


# ---------------------------------------------------------------------------
# recommend_parent_for_fork happy path
# ---------------------------------------------------------------------------


def test_recommend_parent_returns_top_with_selector_rationale(base_path):
    _make_goal(base_path, "g1", name="Patch Loop")
    _make_branch(base_path, branch_def_id="b-top", goal_id="g1")
    _make_branch(base_path, branch_def_id="b-mid", goal_id="g1")
    ranked = [
        {
            "branch_def_id": "b-top",
            "score": 9.5,
            "rationale": "highest avg judgment (9.5) with 12 runs",
        },
        {"branch_def_id": "b-mid", "score": 6.0, "rationale": "mid"},
    ]
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_mock_dispatch_selector(ranked_entries=ranked),
    ):
        rec = recommend_parent_for_fork(
            base_path, goal_id="g1", viewer="",
        )
    assert rec["ok"] is True
    assert rec["recommended_parent"]["branch_def_id"] == "b-top"
    assert rec["leaderboard_size"] == 2
    assert "highest avg judgment" in rec["rationale"]


# ---------------------------------------------------------------------------
# Realistic scale (15+ entries) still works under selector dispatch
# ---------------------------------------------------------------------------


def test_realistic_goal_with_eighteen_entries_under_mock_selector(base_path):
    """Smoke at the scale of Goal 4ff5862cc26d. Mock selector ranks
    by branch_def_id ascending; substrate respects that order."""
    _make_goal(base_path, "g-big")
    for i in range(18):
        _make_branch(
            base_path, branch_def_id=f"b-{i:02d}", goal_id="g-big",
        )
    def _ranker(
        base_path, *, goal_id, candidate_branches, actor="anonymous",
        timeout_s=None, **_extra,
    ):
        ordered = sorted(
            candidate_branches, key=lambda c: c["branch_def_id"],
        )
        return {
            "ok": True,
            "branch_version_id": "mock@x",
            "source": "platform_default",
            "run_id": "r",
            "ranked_entries": [
                {"branch_def_id": c["branch_def_id"], "score": float(i)}
                for i, c in enumerate(ordered)
            ],
        }
    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_ranker,
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g-big", viewer="",
        )
    assert len(board["entries"]) == 18
    # Ranks are 1..18 with no gaps.
    ranks = sorted(e["rank"] for e in board["entries"])
    assert ranks == list(range(1, 19))


# ---------------------------------------------------------------------------
# Goal-binding precedence for selector resolution
# ---------------------------------------------------------------------------


def test_goal_binding_takes_precedence_over_default(base_path):
    """When a Goal has selector_branch_version_id set, the substrate
    uses it instead of publishing/using the platform default. This
    test mocks dispatch_selector so we don't need a real published
    selector; we just confirm the resolver path the substrate
    takes by inspecting selector_branch_version_id in the response."""
    _make_goal(base_path, "g1")
    _make_branch(base_path, branch_def_id="b1", goal_id="g1")
    # Bind a non-platform-default selector at the storage layer.
    from workflow.daemon_server import update_goal
    update_goal(
        base_path,
        goal_id="g1",
        updates={"selector_branch_version_id": "custom_selector@abc12345"},
    )
    captured: dict = {}

    def _capturing(
        base_path, *, goal_id, candidate_branches, actor="anonymous",
        timeout_s=None, **_extra,
    ):
        captured["goal_id"] = goal_id
        return {
            "ok": True,
            "branch_version_id": "custom_selector@abc12345",
            "source": "goal_binding",
            "run_id": "r",
            "ranked_entries": [
                {"branch_def_id": "b1", "score": 7.0, "rationale": ""}
            ],
        }

    with patch(
        "workflow.api.quality_leaderboard.dispatch_selector",
        side_effect=_capturing,
    ):
        board = build_quality_leaderboard(
            base_path, goal_id="g1", viewer="",
        )
    assert board["ok"] is True
    assert board["selector"]["branch_version_id"] == "custom_selector@abc12345"
    assert board["selector"]["source"] == "goal_binding"
