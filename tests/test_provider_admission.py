"""The bound between 40 concurrent handlers and a 189 MB subprocess each.

Measured 2026-08-28: `converse` is a sync MCP handler, so Starlette runs it in the anyio
threadpool (capacity 40, confirmed in production). Each turn spawns a provider CLI at
~189 MB RSS / ~77 MB PSS, floor. Nothing bounded the product of those two numbers, and
with no container memory limit the resulting OOM would kill the HOST and take the
Cloudflare tunnel with it — a total outage rather than a slow service.
"""

from __future__ import annotations

import threading
import time

import pytest

from tinyassets import provider_admission as pa


@pytest.fixture(autouse=True)
def _reset():
    pa.reset_for_tests()
    yield
    pa.reset_for_tests()


def test_concurrency_never_exceeds_the_limit(monkeypatch):
    monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "3")
    monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "10")
    live, peak, lock = [0], [0], threading.Lock()
    start = threading.Barrier(12)

    def worker():
        start.wait()
        try:
            with pa.provider_slot():
                with lock:
                    live[0] += 1
                    peak[0] = max(peak[0], live[0])
                time.sleep(0.05)
                with lock:
                    live[0] -= 1
        except pa.ProviderBusy:
            pass

    ts = [threading.Thread(target=worker) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert peak[0] <= 3, f"{peak[0]} concurrent provider calls with a limit of 3"


def test_it_refuses_rather_than_hanging_when_saturated(monkeypatch):
    """Hard Rule 8. A refusal a user can retry beats an OOM that takes everyone down."""
    monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
    monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "0.05")
    with pa.provider_slot():
        with pytest.raises(pa.ProviderBusy) as exc:
            with pa.provider_slot():
                pass
    assert "busy" in str(exc.value).lower()
    assert "try again" in str(exc.value).lower(), "a refusal must say what to do next"


def test_a_slot_is_released_when_the_call_raises(monkeypatch):
    """A slot leaked on an error is permanent capacity loss — and errors happen
    precisely when the system is already under load."""
    monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
    monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "0.05")
    with pytest.raises(ValueError):
        with pa.provider_slot():
            raise ValueError("provider blew up")
    with pa.provider_slot():  # must not raise ProviderBusy
        pass


def test_a_waiter_is_admitted_when_a_slot_frees(monkeypatch):
    """Bounding must not mean refusing everyone under transient load."""
    monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
    monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "5")
    admitted = []

    def waiter():
        with pa.provider_slot():
            admitted.append(True)

    holder_done = threading.Event()

    def holder():
        with pa.provider_slot():
            time.sleep(0.1)
        holder_done.set()

    h = threading.Thread(target=holder)
    h.start()
    time.sleep(0.02)
    w = threading.Thread(target=waiter)
    w.start()
    h.join(timeout=10)
    w.join(timeout=10)
    assert admitted == [True], "a waiter was refused even though a slot freed up"


def test_the_default_fits_the_box_it_runs_on(monkeypatch):
    """Sized from memory, not from a thread count.

    The pre-existing ceiling was the router's `_SYNC_CALL_MAX_WORKERS = 8` thread pool
    — incidental, since its own comment gives a latency rationale, so raising it for
    throughput would have multiplied memory risk invisibly. This bound is explicitly
    about the ~77 MB each subprocess costs.
    """
    monkeypatch.delenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", raising=False)
    from tinyassets.providers import router

    assert pa._DEFAULT_LIMIT <= router._SYNC_CALL_MAX_WORKERS, (
        "a bound above the thread pool that already gates these calls would never bind"
    )
    assert pa._DEFAULT_LIMIT * 77 + 390 < 2048, (
        "the default must fit the 2 GB box alongside the ~390 MB daemon"
    )


def test_a_bad_limit_falls_back_rather_than_disabling_the_bound(monkeypatch):
    for bad in ("0", "-5", "banana", ""):
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", bad)
        assert pa._positive_int(pa._LIMIT_VAR, pa._DEFAULT_LIMIT) == pa._DEFAULT_LIMIT


class TestTurnDurationInstrumentation:
    """The missing half of every users-per-box claim.

    Capacity in USERS is `slots / turn_duration`. Slots were knowable; turn duration was
    not recorded anywhere — `run_events.started_at/finished_at` sit microseconds apart
    with one event per run, so they are bookkeeping, not execution spans. This context
    manager brackets exactly the provider subprocess's lifetime, which makes it the one
    honest place to measure it.
    """

    def test_it_records_how_long_a_turn_held_its_slot(self):
        with pa.provider_slot():
            time.sleep(0.05)
        snap = pa.admission_snapshot()
        assert snap["admitted"] == 1
        assert snap["samples"] == 1
        assert snap["turn_seconds"]["p50"] >= 0.04

    def test_a_failed_turn_is_still_timed(self):
        """A turn that dies after 40 s occupied a slot for 40 s. Excluding failures
        would flatter the numbers in exactly the conditions worth measuring."""
        with pytest.raises(ValueError):
            with pa.provider_slot():
                time.sleep(0.05)
                raise ValueError("provider died")
        assert pa.admission_snapshot()["samples"] == 1

    def test_it_reports_the_capacity_number_the_question_turns_on(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "10")
        with pa.provider_slot():
            time.sleep(0.1)
        snap = pa.admission_snapshot()
        # 10 slots / ~0.1 s per turn ~= 100 turns/sec
        assert 50 < snap["sustainable_turns_per_second"] < 200, snap

    def test_refusals_are_counted_separately_from_turns(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
        monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "0.05")
        with pa.provider_slot():
            with pytest.raises(pa.ProviderBusy):
                with pa.provider_slot():
                    pass
        snap = pa.admission_snapshot()
        assert snap["refused"] == 1
        assert snap["admitted"] == 1, "a refusal must not count as a turn"

    def test_peak_concurrency_is_observed_not_assumed(self, monkeypatch):
        """Whether the bound actually binds is a fact about production, not a setting."""
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "4")
        monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "10")
        start = threading.Barrier(3)

        def worker():
            start.wait()
            with pa.provider_slot():
                time.sleep(0.08)

        ts = [threading.Thread(target=worker) for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=30)
        assert pa.admission_snapshot()["peak_concurrent"] == 3

    def test_the_sample_buffer_is_bounded(self):
        """An unbounded list on a hot path is a leak, and this one is on every turn."""
        for _ in range(pa._MAX_SAMPLES + 50):
            with pa.provider_slot():
                pass
        assert pa.admission_snapshot()["samples"] <= pa._MAX_SAMPLES

    def test_live_returns_to_zero(self):
        """A live counter that drifts up makes the bound look saturated forever."""
        for _ in range(5):
            with pa.provider_slot():
                pass
        with pytest.raises(ValueError):
            with pa.provider_slot():
                raise ValueError("boom")
        assert pa.admission_snapshot()["live"] == 0
