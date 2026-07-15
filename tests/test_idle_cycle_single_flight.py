"""Tests for tinyassets/idle_cycle.py — idle-cycle single-flight.

Root cause under test (2026-07-14): N healthy fleet workers each ran the
per-universe idle heartbeat cycle, producing N duplicate activity.log
lines. The stamp must dedupe FOREIGN-fresh overlap while never blocking a
worker on its own stamp (solo cadence unchanged) and never stalling the
heartbeat (fail open on corruption/IO errors; stale foreign stamps are
taken over).
"""

from __future__ import annotations

import json
import threading

import pytest

from tinyassets import idle_cycle


def _stamp(tmp_path):
    return tmp_path / idle_cycle.STAMP_FILENAME


# ---- acquisition semantics --------------------------------------------------


def test_first_acquisition_succeeds_and_writes_stamp(tmp_path):
    ok, reason = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-1", foreign_fresh_s=240, now_fn=lambda: 1000.0,
    )
    assert ok
    assert "no prior stamp" in reason
    data = json.loads(_stamp(tmp_path).read_text(encoding="utf-8"))
    assert data == {"worker_id": "claude-1", "started_at": 1000.0}


def test_own_stamp_never_blocks(tmp_path):
    """Solo-worker cadence unchanged: a worker re-acquires over its own
    fresh stamp immediately."""
    idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-1", foreign_fresh_s=240, now_fn=lambda: 1000.0,
    )
    ok, _ = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-1", foreign_fresh_s=240, now_fn=lambda: 1001.0,
    )
    assert ok


def test_foreign_fresh_stamp_skips(tmp_path):
    """The live double-logging shape: second worker arrives ~1s later."""
    idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-1", foreign_fresh_s=240, now_fn=lambda: 1000.0,
    )
    ok, reason = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-2", foreign_fresh_s=240, now_fn=lambda: 1001.0,
    )
    assert not ok
    assert "claude-1" in reason
    # Loser must not overwrite the winner's stamp.
    data = json.loads(_stamp(tmp_path).read_text(encoding="utf-8"))
    assert data["worker_id"] == "claude-1"


def test_foreign_stale_stamp_is_taken_over(tmp_path):
    """Failover: holder died, another worker acquires after the window."""
    idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-1", foreign_fresh_s=240, now_fn=lambda: 1000.0,
    )
    ok, reason = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-2", foreign_fresh_s=240, now_fn=lambda: 1322.0,
    )
    assert ok
    assert "claude-1" in reason  # prior stamp surfaced in the reason
    data = json.loads(_stamp(tmp_path).read_text(encoding="utf-8"))
    assert data == {"worker_id": "claude-2", "started_at": 1322.0}


def test_alternating_fleet_produces_one_cycle_per_period(tmp_path):
    """Two workers on a ~322s period with ~1s offset (the live prod shape):
    exactly one acquisition per round."""
    acquisitions = []
    t = 1000.0
    for round_start in (t, t + 322, t + 644, t + 966):
        for worker, offset in (("claude-1", 0.0), ("claude-2", 1.0)):
            ok, _ = idle_cycle.try_acquire_idle_cycle_slot(
                tmp_path, worker_id=worker, foreign_fresh_s=240,
                now_fn=lambda now=round_start + offset: now,
            )
            if ok:
                acquisitions.append(worker)
    assert len(acquisitions) == 4  # one per round, never two


def test_far_future_stamp_does_not_block_forever(tmp_path):
    """Clock-skew guard: a stamp far in the future reads as invalid."""
    _stamp(tmp_path).write_text(
        json.dumps({"worker_id": "claude-1", "started_at": 999999.0}),
        encoding="utf-8",
    )
    ok, _ = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-2", foreign_fresh_s=240, now_fn=lambda: 1000.0,
    )
    assert ok


def test_slightly_future_foreign_stamp_still_skips(tmp_path):
    """Small skew (within the window) counts as fresh."""
    _stamp(tmp_path).write_text(
        json.dumps({"worker_id": "claude-1", "started_at": 1010.0}),
        encoding="utf-8",
    )
    ok, _ = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-2", foreign_fresh_s=240, now_fn=lambda: 1000.0,
    )
    assert not ok


# ---- fail-open corruption handling ------------------------------------------


@pytest.mark.parametrize("corrupt", [
    "not json",
    "[]",
    json.dumps({"worker_id": 42, "started_at": 1000.0}),
    json.dumps({"worker_id": "x"}),
    json.dumps({"started_at": "yesterday", "worker_id": "x"}),
    "",
])
def test_corrupt_stamp_reads_as_absent_and_acquires(tmp_path, corrupt):
    _stamp(tmp_path).write_text(corrupt, encoding="utf-8")
    ok, _ = idle_cycle.try_acquire_idle_cycle_slot(
        tmp_path, worker_id="claude-2", foreign_fresh_s=240, now_fn=lambda: 1000.0,
    )
    assert ok


def test_missing_universe_dir_is_created_and_acquires(tmp_path):
    target = tmp_path / "not-yet" / "universe"
    ok, _ = idle_cycle.try_acquire_idle_cycle_slot(
        target, worker_id="claude-1", foreign_fresh_s=240, now_fn=lambda: 1000.0,
    )
    assert ok
    assert (target / idle_cycle.STAMP_FILENAME).is_file()


# ---- concurrency ------------------------------------------------------------


def test_concurrent_foreign_racers_yield_exactly_one_winner(tmp_path):
    """Two distinct workers race the same fresh window: the lock must
    serialize check-and-set so exactly one acquires."""
    results = {}
    barrier = threading.Barrier(2)

    def race(worker):
        barrier.wait()
        ok, _ = idle_cycle.try_acquire_idle_cycle_slot(
            tmp_path, worker_id=worker, foreign_fresh_s=240,
        )
        results[worker] = ok

    threads = [
        threading.Thread(target=race, args=(w,))
        for w in ("claude-1", "claude-2")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results.values()) == [False, True]


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
    monkeypatch.setenv("TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S", "junk")
    assert idle_cycle.foreign_fresh_window_s() == idle_cycle.DEFAULT_FOREIGN_FRESH_S
    monkeypatch.setenv("TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S", "-5")
    assert idle_cycle.foreign_fresh_window_s() == idle_cycle.DEFAULT_FOREIGN_FRESH_S


def test_worker_identity_precedence(monkeypatch):
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "claude-1")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "cloud-droplet-claude-1")
    assert idle_cycle.resolve_worker_identity() == "claude-1"
    monkeypatch.delenv("TINYASSETS_WORKER_ID")
    assert idle_cycle.resolve_worker_identity() == "cloud-droplet-claude-1"
    monkeypatch.delenv("UNIVERSE_SERVER_HOST_USER")
    assert idle_cycle.resolve_worker_identity() == "host"
