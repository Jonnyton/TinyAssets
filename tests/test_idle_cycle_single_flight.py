"""Tests for tinyassets/idle_cycle.py — idle-cycle single-flight.

Root cause under test (2026-07-14): N healthy fleet workers each ran the
per-universe idle heartbeat cycle, producing N duplicate activity.log
lines. Two layers under test:

* run lock — a winner HOLDS it for the cycle's lifetime, so a cycle
  longer than the freshness window still excludes other workers (Codex
  adversarial review required regression);
* stamp — rate-limits between cycles: foreign-fresh skips, own stamps
  never block (solo cadence unchanged), stale foreign stamps are taken
  over (failover), corruption fails open.
"""

from __future__ import annotations

import json
import threading

import pytest

from tinyassets import idle_cycle


def _stamp(tmp_path):
    return tmp_path / idle_cycle.STAMP_FILENAME


def _acquire_released(tmp_path, worker, now, window=240):
    """Acquire and immediately release — models a completed cycle
    (subprocess exited); leaves only the stamp behind."""
    slot = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id=worker, foreign_fresh_s=window,
        now_fn=lambda: float(now),
    )
    if slot.acquired:
        slot.release()
    return slot


# ---- acquisition semantics --------------------------------------------------


def test_first_acquisition_succeeds_and_writes_stamp(tmp_path):
    slot = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-1", foreign_fresh_s=240,
        now_fn=lambda: 1000.0,
    )
    try:
        assert slot.acquired
        assert "no prior stamp" in slot.reason
        data = json.loads(_stamp(tmp_path).read_text(encoding="utf-8"))
        assert data == {"worker_id": "claude-1", "started_at": 1000.0}
    finally:
        slot.release()


def test_own_stamp_never_blocks(tmp_path):
    """Solo-worker cadence unchanged: after its cycle ends (slot
    released), a worker re-acquires over its own fresh stamp."""
    _acquire_released(tmp_path, "claude-1", 1000.0)
    slot = _acquire_released(tmp_path, "claude-1", 1001.0)
    assert slot.acquired


def test_foreign_fresh_stamp_skips(tmp_path):
    """The live double-logging shape: second worker arrives ~1s after the
    first worker's cycle COMPLETED."""
    _acquire_released(tmp_path, "claude-1", 1000.0)
    slot = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-2", foreign_fresh_s=240,
        now_fn=lambda: 1001.0,
    )
    assert not slot.acquired
    assert "claude-1" in slot.reason
    # Loser must not overwrite the winner's stamp.
    data = json.loads(_stamp(tmp_path).read_text(encoding="utf-8"))
    assert data["worker_id"] == "claude-1"


def test_running_cycle_blocks_even_past_freshness_window(tmp_path):
    """Codex-required regression: worker A started at t and is STILL
    RUNNING (slot held) at t+241 — worker B must skip on the run lock
    even though the stamp is past the freshness window."""
    slot_a = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-1", foreign_fresh_s=240,
        now_fn=lambda: 1000.0,
    )
    assert slot_a.acquired
    try:
        slot_b = idle_cycle.try_acquire_idle_cycle_slot(
            tmp_path, worker_id="claude-2", foreign_fresh_s=240,
            now_fn=lambda: 1241.0,  # stamp age 241s > 240s window
        )
        assert not slot_b.acquired
        assert "run lock" in slot_b.reason
    finally:
        slot_a.release()
    # After A finishes (lock released), B takes over normally.
    slot_b2 = _acquire_released(tmp_path, "claude-2", 1242.0)
    assert slot_b2.acquired


def test_release_is_idempotent(tmp_path):
    slot = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-1", foreign_fresh_s=240,
        now_fn=lambda: 1000.0,
    )
    slot.release()
    slot.release()  # second release is a no-op, not an error


def test_foreign_stale_stamp_is_taken_over(tmp_path):
    """Failover: holder died mid-gap; another worker acquires after the
    window."""
    _acquire_released(tmp_path, "claude-1", 1000.0)
    slot = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-2", foreign_fresh_s=240,
        now_fn=lambda: 1322.0,
    )
    try:
        assert slot.acquired
        assert "claude-1" in slot.reason  # prior stamp surfaced
        data = json.loads(_stamp(tmp_path).read_text(encoding="utf-8"))
        assert data == {"worker_id": "claude-2", "started_at": 1322.0}
    finally:
        slot.release()


def test_alternating_fleet_produces_one_cycle_per_period(tmp_path):
    """Two workers on a ~322s period with ~1s offset (the live prod
    shape): exactly one acquisition per round."""
    acquisitions = []
    t = 1000.0
    for round_start in (t, t + 322, t + 644, t + 966):
        for worker, offset in (("claude-1", 0.0), ("claude-2", 1.0)):
            slot = _acquire_released(tmp_path, worker, round_start + offset)
            if slot.acquired:
                acquisitions.append(worker)
    assert len(acquisitions) == 4  # one per round, never two


def test_far_future_stamp_does_not_block_forever(tmp_path):
    """Clock-skew guard: a stamp far in the future reads as invalid."""
    _stamp(tmp_path).write_text(
        json.dumps({"worker_id": "claude-1", "started_at": 999999.0}),
        encoding="utf-8",
    )
    slot = _acquire_released(tmp_path, "claude-2", 1000.0)
    assert slot.acquired


def test_slightly_future_foreign_stamp_still_skips(tmp_path):
    """Small skew (within the window) counts as fresh."""
    _stamp(tmp_path).write_text(
        json.dumps({"worker_id": "claude-1", "started_at": 1010.0}),
        encoding="utf-8",
    )
    slot = _acquire_released(tmp_path, "claude-2", 1000.0)
    assert not slot.acquired


# ---- fail-open corruption handling ------------------------------------------


@pytest.mark.parametrize("corrupt", [
    "not json",
    "[]",
    json.dumps({"worker_id": 42, "started_at": 1000.0}),
    json.dumps({"worker_id": "x"}),
    json.dumps({"started_at": "yesterday", "worker_id": "x"}),
    json.dumps({"worker_id": "x", "started_at": float("inf")}),
    "",
])
def test_corrupt_stamp_reads_as_absent_and_acquires(tmp_path, corrupt):
    _stamp(tmp_path).write_text(corrupt, encoding="utf-8")
    slot = _acquire_released(tmp_path, "claude-2", 1000.0)
    assert slot.acquired


def test_missing_universe_dir_is_created_and_acquires(tmp_path):
    target = tmp_path / "not-yet" / "universe"
    slot = _acquire_released(target, "claude-1", 1000.0)
    assert slot.acquired
    assert (target / idle_cycle.STAMP_FILENAME).is_file()


# ---- concurrency ------------------------------------------------------------


def test_concurrent_foreign_racers_yield_exactly_one_winner(tmp_path):
    """Two distinct workers race the same window: run lock + stamp
    serialize the check-and-set so exactly one acquires."""
    results: dict[str, idle_cycle.IdleCycleSlot] = {}
    barrier = threading.Barrier(2)

    def race(worker):
        barrier.wait()
        results[worker] = idle_cycle.try_acquire_idle_cycle_slot(
            tmp_path, worker_id=worker, foreign_fresh_s=240,
        )

    threads = [
        threading.Thread(target=race, args=(w,))
        for w in ("claude-1", "claude-2")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    try:
        assert sorted(s.acquired for s in results.values()) == [False, True]
    finally:
        for s in results.values():
            s.release()


# ---- env plumbing -----------------------------------------------------------


def test_single_flight_default_on(monkeypatch):
    monkeypatch.delenv("TINYASSETS_IDLE_CYCLE_SINGLE_FLIGHT", raising=False)
    assert idle_cycle.single_flight_enabled()


@pytest.mark.parametrize("value", ["0", "false", "off", "no", "OFF", "False"])
def test_single_flight_disabled_by_env(monkeypatch, value):
    monkeypatch.setenv("TINYASSETS_IDLE_CYCLE_SINGLE_FLIGHT", value)
    assert not idle_cycle.single_flight_enabled()


def test_window_env_override_and_defaults(monkeypatch):
    monkeypatch.delenv("TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S", raising=False)
    assert idle_cycle.foreign_fresh_window_s() == idle_cycle.DEFAULT_FOREIGN_FRESH_S
    monkeypatch.setenv("TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S", "60")
    assert idle_cycle.foreign_fresh_window_s() == 60.0


@pytest.mark.parametrize("bad", ["junk", "-5", "0", "inf", "-inf", "nan", "1e999"])
def test_window_rejects_non_finite_and_non_positive(monkeypatch, bad):
    """Codex-required: inf would make a foreign stamp block forever; nan
    silently disables the freshness comparison. Both must fall back."""
    monkeypatch.setenv("TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S", bad)
    assert idle_cycle.foreign_fresh_window_s() == idle_cycle.DEFAULT_FOREIGN_FRESH_S


def test_worker_identity_precedence(monkeypatch):
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "claude-1")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "owner-daemon-claude-1")
    assert idle_cycle.resolve_worker_identity() == "claude-1"
    monkeypatch.delenv("TINYASSETS_WORKER_ID")
    assert idle_cycle.resolve_worker_identity() == "owner-daemon-claude-1"
    monkeypatch.delenv("UNIVERSE_SERVER_HOST_USER")
    assert idle_cycle.resolve_worker_identity() == "host"
