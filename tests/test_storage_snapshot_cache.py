"""The storage snapshot is memoized, because its cost grows with the platform.

Measured on the live box 2026-08-28: `inspect_storage_utilization` recursively sums
every subsystem directory, ~3,300 `stat` syscalls and 24-49 ms per call, and it sat
in the `read_graph target=status` request path. Removing it made that request 19%
faster at today's size -- but the reason it had to go is the SHAPE, not the 19%: the
walk is O(files on disk) while everything else in the request is flat, so it is the
one part that gets worse as users arrive.
"""

from __future__ import annotations

import pytest

from tinyassets import storage


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    storage.reset_storage_snapshot_cache()
    yield
    storage.reset_storage_snapshot_cache()


def _count_walks(monkeypatch) -> list[int]:
    calls = [0]
    real = storage._inspect_storage_utilization_uncached

    def counted():
        calls[0] += 1
        return real()

    monkeypatch.setattr(storage, "_inspect_storage_utilization_uncached", counted)
    return calls


def test_a_second_read_does_not_walk_the_disk_again(monkeypatch):
    calls = _count_walks(monkeypatch)
    for _ in range(5):
        storage.inspect_storage_utilization()
    assert calls[0] == 1, "the walk ran once per call; the memo is not being used"


def test_the_snapshot_is_still_correct(tmp_path, monkeypatch):
    """A cache that returns the wrong number is worse than a slow correct one."""
    monkeypatch.setenv("TINYASSETS_STORAGE_SNAPSHOT_TTL_S", "0")
    fresh = storage.inspect_storage_utilization()
    assert set(fresh) >= {
        "volume_percent",
        "volume_bytes_total",
        "volume_bytes_free",
        "per_subsystem",
        "pressure_level",
    }
    monkeypatch.delenv("TINYASSETS_STORAGE_SNAPSHOT_TTL_S")
    storage.reset_storage_snapshot_cache()
    cached = storage.inspect_storage_utilization()
    assert cached["per_subsystem"].keys() == fresh["per_subsystem"].keys()
    assert cached["pressure_level"] == fresh["pressure_level"]


def test_a_zero_ttl_disables_the_memo_entirely(monkeypatch):
    """An operator who needs the truth right now must have a way to get it.

    Note this passes with or without the explicit `ttl <= 0` early return, because
    a zero-TTL entry is already expired by the time it is read. The early return is
    a fast path, not the mechanism -- kept because it skips pointless lock churn,
    and recorded here so a later reader does not mistake this for a decorative
    assertion when they mutate that line and see green.
    """
    monkeypatch.setenv("TINYASSETS_STORAGE_SNAPSHOT_TTL_S", "0")
    calls = _count_walks(monkeypatch)
    storage.inspect_storage_utilization()
    storage.inspect_storage_utilization()
    assert calls[0] == 2


def test_an_expired_snapshot_is_recomputed(monkeypatch):
    monkeypatch.setenv("TINYASSETS_STORAGE_SNAPSHOT_TTL_S", "0.01")
    calls = _count_walks(monkeypatch)
    storage.inspect_storage_utilization()
    import time as _t

    _t.sleep(0.05)
    storage.inspect_storage_utilization()
    assert calls[0] == 2, "a stale snapshot was served past its TTL"


def test_a_caller_cannot_poison_the_next_callers_snapshot(monkeypatch):
    """The failure a shared memo introduces that the uncached version could not.

    The first version of this test mutated the FIRST result and passed even with
    the cache-hit deep copy removed -- the miss path copies anyway, so the first
    caller never holds the stored dict. Poisoning is only reachable from a cache
    HIT, so the mutation has to happen there.
    """
    storage.inspect_storage_utilization()  # miss: populates the memo
    hit = storage.inspect_storage_utilization()  # hit: this is the risky one
    hit["pressure_level"] = "critical"
    hit["per_subsystem"].clear()
    after = storage.inspect_storage_utilization()
    assert after["pressure_level"] != "critical", (
        "a cache HIT handed out the stored dict itself; mutating it poisoned "
        "every later reader"
    )
    assert after["per_subsystem"], "the memo handed out its own mutable dict"


def test_a_different_data_dir_never_serves_the_previous_ones_numbers(
    tmp_path, monkeypatch
):
    """Keyed by root: otherwise one universe's tree answers for another's, and in
    tests a tmpdir would inherit production's figures."""
    a = storage.inspect_storage_utilization()
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "filler.bin").write_bytes(b"x" * 4096)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(other))
    b = storage.inspect_storage_utilization()
    assert b["per_subsystem"]["universe_outputs"]["path"] != (
        a["per_subsystem"]["universe_outputs"]["path"]
    ), "the snapshot for a different data dir came back describing the old one"


def test_an_unparseable_ttl_falls_back_to_the_default_rather_than_disabling(
    monkeypatch,
):
    monkeypatch.setenv("TINYASSETS_STORAGE_SNAPSHOT_TTL_S", "not-a-number")
    calls = _count_walks(monkeypatch)
    storage.inspect_storage_utilization()
    storage.inspect_storage_utilization()
    assert calls[0] == 1


def test_concurrent_cold_readers_walk_the_disk_once(monkeypatch):
    """Replaces a source-inspection test that Codex showed was decorative: a mutant
    moving the walk INSIDE the lock passed it. This asserts the behaviour that
    actually matters, and it is the behaviour the review found broken -- 25 cold
    callers ran 25 walks, at the concurrency where the box already saturates."""
    import threading

    storage.reset_storage_snapshot_cache()
    calls, lock = [], threading.Lock()
    real = storage._inspect_storage_utilization_uncached

    def counted():
        with lock:
            calls.append(1)
        import time as _t

        _t.sleep(0.03)
        return real()

    monkeypatch.setattr(storage, "_inspect_storage_utilization_uncached", counted)
    start = threading.Barrier(12)

    def worker():
        start.wait()
        storage.inspect_storage_utilization()

    ts = [threading.Thread(target=worker) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert len(calls) == 1, f"{len(calls)} concurrent walks; single-flight is not wired"
