"""Tests for tinyassets.storage.external_write_receipts.

PR-122 Phase 2 Slice 1 — the idempotency-receipt store for the
``github_pr`` effector and any future external-write sink.
"""

from __future__ import annotations

import time

import pytest

from tinyassets.storage.external_write_receipts import (
    delete_receipt,
    initialize_receipts_db,
    list_receipts,
    lookup_receipt,
    receipts_db_path,
    record_receipt,
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_initialize_creates_db_and_schema(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    path = initialize_receipts_db(universe)
    assert path.exists()
    assert path == receipts_db_path(universe)
    # Calling again is a no-op (idempotent).
    again = initialize_receipts_db(universe)
    assert again == path


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_lookup_returns_none_when_no_receipt(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    assert lookup_receipt(
        universe, idempotency_hint="never-recorded", sink="github_pull_request"
    ) is None


def test_record_then_lookup_roundtrip(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    record_receipt(
        universe,
        idempotency_hint="loop-2-cycle-001",
        sink="github_pull_request",
        evidence={"pr_url": "https://github.com/Jonnyton/TinyAssets/pull/123",
                  "pr_number": 123},
        run_id="run-abc",
        created_at=1234567890.0,
    )
    receipt = lookup_receipt(
        universe, idempotency_hint="loop-2-cycle-001", sink="github_pull_request",
    )
    assert receipt is not None
    assert receipt["idempotency_hint"] == "loop-2-cycle-001"
    assert receipt["sink"] == "github_pull_request"
    assert receipt["run_id"] == "run-abc"
    assert receipt["created_at"] == 1234567890.0
    assert receipt["evidence"]["pr_number"] == 123


def test_record_last_write_wins_on_same_key(tmp_path):
    """Per design stub §2: a retried run may overwrite a stale receipt."""
    universe = tmp_path / "u1"
    universe.mkdir()
    record_receipt(
        universe,
        idempotency_hint="hint-1",
        sink="github_pull_request",
        evidence={"pr_url": "old", "pr_number": 1},
        run_id="run-1",
        created_at=1000.0,
    )
    record_receipt(
        universe,
        idempotency_hint="hint-1",
        sink="github_pull_request",
        evidence={"pr_url": "new", "pr_number": 2},
        run_id="run-2",
        created_at=2000.0,
    )
    receipt = lookup_receipt(
        universe, idempotency_hint="hint-1", sink="github_pull_request",
    )
    assert receipt is not None
    assert receipt["run_id"] == "run-2"
    assert receipt["evidence"]["pr_number"] == 2
    assert receipt["created_at"] == 2000.0


def test_sink_namespacing_prevents_collisions(tmp_path):
    """Same hint, different sink -> two distinct receipts."""
    universe = tmp_path / "u1"
    universe.mkdir()
    record_receipt(
        universe,
        idempotency_hint="hint-shared",
        sink="github_pull_request",
        evidence={"pr_url": "pr"},
        run_id="run-a",
    )
    record_receipt(
        universe,
        idempotency_hint="hint-shared",
        sink="twitter_post",
        evidence={"tweet_url": "tweet"},
        run_id="run-b",
    )
    pr_receipt = lookup_receipt(
        universe, idempotency_hint="hint-shared", sink="github_pull_request",
    )
    tweet_receipt = lookup_receipt(
        universe, idempotency_hint="hint-shared", sink="twitter_post",
    )
    assert pr_receipt is not None
    assert pr_receipt["evidence"]["pr_url"] == "pr"
    assert tweet_receipt is not None
    assert tweet_receipt["evidence"]["tweet_url"] == "tweet"


def test_empty_hint_is_silent_no_op_on_write_and_miss_on_read(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    record_receipt(
        universe,
        idempotency_hint="",
        sink="github_pull_request",
        evidence={"would-be-stored": True},
        run_id="run-x",
    )
    assert list_receipts(universe) == []
    assert lookup_receipt(
        universe, idempotency_hint="", sink="github_pull_request",
    ) is None


def test_delete_removes_receipt_and_returns_hit(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    record_receipt(
        universe,
        idempotency_hint="hint-del",
        sink="github_pull_request",
        evidence={"pr_url": "x"},
        run_id="run-1",
    )
    hit = delete_receipt(
        universe, idempotency_hint="hint-del", sink="github_pull_request",
    )
    assert hit is True
    assert lookup_receipt(
        universe, idempotency_hint="hint-del", sink="github_pull_request",
    ) is None
    # Second delete is a miss.
    miss = delete_receipt(
        universe, idempotency_hint="hint-del", sink="github_pull_request",
    )
    assert miss is False


# ---------------------------------------------------------------------------
# list_receipts
# ---------------------------------------------------------------------------


def test_list_receipts_orders_by_created_at_desc(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    record_receipt(
        universe, idempotency_hint="a", sink="github_pull_request",
        evidence={}, run_id="r1", created_at=10.0,
    )
    record_receipt(
        universe, idempotency_hint="b", sink="github_pull_request",
        evidence={}, run_id="r2", created_at=20.0,
    )
    record_receipt(
        universe, idempotency_hint="c", sink="github_pull_request",
        evidence={}, run_id="r3", created_at=15.0,
    )
    rows = list_receipts(universe)
    assert [r["idempotency_hint"] for r in rows] == ["b", "c", "a"]


def test_list_receipts_filters_by_sink(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    record_receipt(
        universe, idempotency_hint="a", sink="github_pull_request",
        evidence={}, run_id="r1",
    )
    record_receipt(
        universe, idempotency_hint="b", sink="twitter_post",
        evidence={}, run_id="r2",
    )
    rows = list_receipts(universe, sink="twitter_post")
    assert [r["idempotency_hint"] for r in rows] == ["b"]


def test_record_rejects_non_json_serializable_evidence(tmp_path):
    """Hard rule #8 — fail loudly when caller hands us garbage."""
    universe = tmp_path / "u1"
    universe.mkdir()
    with pytest.raises(TypeError):
        record_receipt(
            universe,
            idempotency_hint="hint-bad",
            sink="github_pull_request",
            evidence={"unencodable": {1, 2, 3}},  # sets aren't JSON
            run_id="run-1",
        )


# ---------------------------------------------------------------------------
# Universe isolation
# ---------------------------------------------------------------------------


def test_universes_are_isolated(tmp_path):
    u1 = tmp_path / "u1"
    u2 = tmp_path / "u2"
    u1.mkdir()
    u2.mkdir()
    record_receipt(
        u1, idempotency_hint="hint-1", sink="github_pull_request",
        evidence={"pr_url": "u1-pr"}, run_id="run-u1",
    )
    assert lookup_receipt(
        u2, idempotency_hint="hint-1", sink="github_pull_request",
    ) is None
    u1_receipt = lookup_receipt(
        u1, idempotency_hint="hint-1", sink="github_pull_request",
    )
    assert u1_receipt is not None
    assert u1_receipt["evidence"]["pr_url"] == "u1-pr"


def test_default_created_at_uses_wall_clock(tmp_path):
    universe = tmp_path / "u1"
    universe.mkdir()
    before = time.time()
    record_receipt(
        universe,
        idempotency_hint="hint-ts",
        sink="github_pull_request",
        evidence={"pr_url": "x"},
        run_id="run-1",
    )
    after = time.time()
    receipt = lookup_receipt(
        universe, idempotency_hint="hint-ts", sink="github_pull_request",
    )
    assert receipt is not None
    assert before <= receipt["created_at"] <= after
