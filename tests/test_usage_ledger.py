"""The per-universe usage ledger.

The load-bearing property is that a *failed* effect costs nothing while a *completed*
one is charged exactly once — including under replay, which is where the receipt layer
next door is state-idempotent but not accounting-idempotent.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets.storage.usage_ledger import (
    STATE_COMMITTED,
    STATE_RESERVED,
    commit_effect,
    initialize_usage_ledger,
    prune_before,
    release_effect,
    reserve_effect,
    settle_compute,
    usage_ledger_path,
    usage_summary,
)

WINDOW = 3600.0


def _reserve(tmp_path, key, limit=3, now=1000.0):
    return reserve_effect(
        tmp_path,
        settlement_key=key,
        limit=limit,
        window_seconds=WINDOW,
        now=now,
    )


def test_the_ledger_is_created_per_universe(tmp_path):
    path = initialize_usage_ledger(tmp_path)
    assert path == usage_ledger_path(tmp_path)
    assert path.is_file()
    # Idempotent.
    assert initialize_usage_ledger(tmp_path) == path


def test_reserving_refuses_once_the_budget_is_exhausted(tmp_path):
    assert _reserve(tmp_path, "e1", limit=2) is True
    assert _reserve(tmp_path, "e2", limit=2) is True
    # Third distinct effect exceeds the budget and must be refused PRE-FLIGHT.
    assert _reserve(tmp_path, "e3", limit=2) is False


def test_a_failed_effect_costs_nothing(tmp_path):
    """The whole point of the 2026-08-28 outage: failures must be free."""
    assert _reserve(tmp_path, "e1", limit=1) is True
    assert _reserve(tmp_path, "e2", limit=1) is False  # budget held by e1

    assert release_effect(tmp_path, settlement_key="e1") is True

    # The slot came back, so the next effect proceeds.
    assert _reserve(tmp_path, "e2", limit=1) is True


def test_releasing_a_committed_effect_does_not_refund_it(tmp_path):
    assert _reserve(tmp_path, "e1", limit=1) is True
    assert commit_effect(tmp_path, settlement_key="e1") is True

    # It already reached the world; it cannot be un-spent.
    assert release_effect(tmp_path, settlement_key="e1") is False
    assert _reserve(tmp_path, "e2", limit=1) is False


def test_committing_twice_charges_once(tmp_path):
    """Guards the exact hole Codex found: finalize_receipt returns True on replay."""
    assert _reserve(tmp_path, "e1", limit=5) is True

    assert commit_effect(tmp_path, settlement_key="e1") is True
    # A replayed finalization must NOT settle again.
    assert commit_effect(tmp_path, settlement_key="e1") is False

    summary = usage_summary(tmp_path, window_seconds=WINDOW, now=1000.0)
    assert summary["effects_committed"] == 1.0


def test_committing_an_unreserved_effect_settles_nothing(tmp_path):
    """No reservation means no admission happened — settlement must not invent one."""
    assert commit_effect(tmp_path, settlement_key="never-reserved") is False
    summary = usage_summary(tmp_path, window_seconds=WINDOW, now=1000.0)
    assert summary["effects_committed"] == 0.0


def test_replaying_a_reservation_does_not_take_a_second_slot(tmp_path):
    assert _reserve(tmp_path, "e1", limit=1) is True
    # Same effect retried — still the same effect, so still one slot.
    assert _reserve(tmp_path, "e1", limit=1) is True

    summary = usage_summary(tmp_path, window_seconds=WINDOW, now=1000.0)
    assert summary["effects"] == 1.0


def test_concurrent_reservations_cannot_both_take_the_last_slot(tmp_path):
    initialize_usage_ledger(tmp_path)
    assert _reserve(tmp_path, "held", limit=2) is True  # 1 of 2 used

    def attempt(n: int) -> bool:
        return reserve_effect(
            tmp_path,
            settlement_key=f"race-{n}",
            limit=2,
            window_seconds=WINDOW,
            now=1000.0,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    assert sum(1 for r in results if r) == 1, (
        "exactly one of the racing effects may take the final slot"
    )


def test_the_window_rolls(tmp_path):
    assert _reserve(tmp_path, "old", limit=1, now=1000.0) is True
    assert _reserve(tmp_path, "new", limit=1, now=1000.0) is False
    # Far enough later that the old reservation has left the window.
    assert _reserve(tmp_path, "new", limit=1, now=1000.0 + WINDOW + 1) is True


def test_compute_settles_once_per_run(tmp_path):
    assert settle_compute(
        tmp_path, run_id="r1", seconds=30.0, max_chargeable_seconds=600.0
    ) is True
    # Retried settlement must not double-charge.
    assert settle_compute(
        tmp_path, run_id="r1", seconds=30.0, max_chargeable_seconds=600.0
    ) is False

    summary = usage_summary(tmp_path, window_seconds=WINDOW)
    assert summary["compute_seconds"] == 30.0


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(900.0, 600.0), (600.0, 600.0), (10.0, 10.0), (-5.0, 0.0)],
)
def test_compute_is_clamped_to_the_chargeable_ceiling(tmp_path, seconds, expected):
    """A wedged or abandoned run must not accrue without bound."""
    settle_compute(
        tmp_path, run_id="r1", seconds=seconds, max_chargeable_seconds=600.0
    )
    summary = usage_summary(tmp_path, window_seconds=WINDOW)
    assert summary["compute_seconds"] == expected


def test_summary_separates_in_flight_from_billable(tmp_path):
    _reserve(tmp_path, "committed-one", limit=5)
    _reserve(tmp_path, "still-flying", limit=5)
    commit_effect(tmp_path, settlement_key="committed-one")

    summary = usage_summary(tmp_path, window_seconds=WINDOW, now=1000.0)
    # Both hold budget; only one is billable.
    assert summary["effects"] == 2.0
    assert summary["effects_committed"] == 1.0


def test_pruning_never_frees_a_slot_still_in_flight(tmp_path):
    _reserve(tmp_path, "in-flight", limit=5, now=1.0)
    _reserve(tmp_path, "done", limit=5, now=1.0)
    commit_effect(tmp_path, settlement_key="done", now=1.0)

    removed = prune_before(tmp_path, cutoff=1_000_000.0)

    assert removed == 1, "only the settled row is prunable"
    summary = usage_summary(tmp_path, window_seconds=1e9, now=1_000_000.0)
    assert summary["effects"] == 1.0, "the in-flight reservation still holds its slot"


def test_state_constants_are_distinct():
    assert STATE_RESERVED != STATE_COMMITTED
