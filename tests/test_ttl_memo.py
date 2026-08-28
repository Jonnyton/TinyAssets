"""Every test here exists because a cross-family review reproduced the failure.

Codex ADAPT 2026-08-28 found four defects in two hand-rolled memos that each read as
obviously correct. These assert the fixes behaviourally — concurrently where the defect
was concurrent, because a single-threaded test cannot see a thundering herd.
"""

from __future__ import annotations

import threading
import time

import pytest

from tinyassets.ttl_memo import TTLMemo, read_ttl


def test_a_hit_does_not_recompute():
    memo, calls = TTLMemo(), []
    for _ in range(5):
        memo.get("k", lambda: calls.append(1) or "v", ttl=60)
    assert len(calls) == 1


def test_twenty_five_cold_callers_compute_once_not_twenty_five():
    """The thundering herd. Codex reproduced 25 concurrent callers running 25 walks
    at the exact concurrency where the box already saturates — the cache made the
    worst moment worse. A barrier makes them genuinely simultaneous; without one
    they trickle through the fast path and the test proves nothing."""
    memo = TTLMemo()
    calls, lock = [], threading.Lock()
    start = threading.Barrier(25)

    def compute():
        with lock:
            calls.append(1)
        time.sleep(0.05)  # long enough that others really are waiting
        return "v"

    out = []
    def worker():
        start.wait()
        out.append(memo.get("same-key", compute, ttl=60))

    threads = [threading.Thread(target=worker) for _ in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(out) == 25, "every caller must get an answer"
    assert all(v == "v" for v in out)
    assert len(calls) == 1, f"{len(calls)} concurrent computations; single-flight is not working"


def test_different_keys_still_run_in_parallel():
    """Single-flight must not become global serialization — that would trade one
    contention point for another."""
    memo = TTLMemo()
    start = threading.Barrier(4)
    seen_together = []
    live, lock = [0], threading.Lock()

    def compute():
        with lock:
            live[0] += 1
            seen_together.append(live[0])
        time.sleep(0.05)
        with lock:
            live[0] -= 1
        return "v"

    def worker(i):
        start.wait()
        memo.get(f"key-{i}", compute, ttl=60)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert max(seen_together) > 1, "distinct keys were serialized against each other"


def test_an_inflight_computation_cannot_republish_after_invalidate():
    """Codex's third finding: a caller who explicitly asked for freshness got the
    stale value back, because work already running published after the reset."""
    memo = TTLMemo()
    released = threading.Event()
    state = {"gen": "old"}

    def slow_compute():
        # Captured at START. The first version of this test read `state` on the way
        # OUT, so the stale-publication path published "new" anyway and the mutant
        # that removes the generation check stayed green — the test could not tell
        # the two apart. A slow computation returns what it saw when it began; that
        # is the whole reason republishing it is wrong.
        captured = state["gen"]
        released.wait(timeout=5)
        return captured

    t = threading.Thread(target=lambda: memo.get("k", slow_compute, ttl=60))
    t.start()
    time.sleep(0.05)          # let it enter compute()
    state["gen"] = "new"      # the world changes
    memo.invalidate()         # and someone asks for freshness
    released.set()
    t.join(timeout=10)

    assert memo.get("k", lambda: state["gen"], ttl=60) == "new", (
        "a computation that began before invalidate() republished stale state"
    )


def test_a_stale_value_is_not_served_after_expiry():
    memo, calls = TTLMemo(), []
    memo.get("k", lambda: calls.append(1) or "v", ttl=0.01)
    time.sleep(0.05)
    memo.get("k", lambda: calls.append(1) or "v", ttl=0.01)
    assert len(calls) == 2


def test_zero_ttl_never_caches():
    memo, calls = TTLMemo(), []
    for _ in range(3):
        memo.get("k", lambda: calls.append(1) or "v", ttl=0)
    assert len(calls) == 3


def test_the_miss_path_also_deep_copies():
    """Codex's mutant: leave the HIT copy in place and drop only the MISS copy. All
    17 tests passed, and the first caller could still alias and poison the store."""
    memo = TTLMemo()
    first = memo.get("k", lambda: {"depth": 1}, ttl=60)
    first["depth"] = 999
    assert memo.get("k", lambda: {"depth": 1}, ttl=60)["depth"] == 1, (
        "the MISS path handed out the stored object; the first caller poisoned it"
    )


def test_eviction_is_lru_not_clear_all():
    """Clear-all guarantees churn exactly when there are many keys — which is the
    1,000-universe case this whole change is about."""
    memo = TTLMemo(max_entries=4)
    for i in range(4):
        memo.get(f"k{i}", lambda: "v", ttl=60)
    memo.get("k3", lambda: "SHOULD-NOT-RUN", ttl=60)  # touch: now most-recent
    memo.get("k4", lambda: "v", ttl=60)               # forces one eviction

    calls = []
    memo.get("k3", lambda: calls.append("recomputed") or "v", ttl=60)
    assert not calls, "LRU evicted a recently-used key; this is clear-all behaviour"


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "Infinity"])
def test_a_non_finite_ttl_falls_back_rather_than_freezing_forever(monkeypatch, raw):
    """`inf` parses fine as a float and would mean 'never recompute'. A diagnostic
    that a typo can freeze permanently is worse than no cache at all."""
    monkeypatch.setenv("X_TTL", raw)
    assert read_ttl("X_TTL", 5.0) == 5.0


def test_a_normal_ttl_is_honoured(monkeypatch):
    monkeypatch.setenv("X_TTL", "12.5")
    assert read_ttl("X_TTL", 5.0) == 12.5
    monkeypatch.setenv("X_TTL", "garbage")
    assert read_ttl("X_TTL", 5.0) == 5.0
