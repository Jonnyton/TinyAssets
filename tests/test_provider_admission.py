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


def test_the_default_is_below_the_anyio_handler_pool(monkeypatch):
    """The threadpool bounds cheap handlers; this bounds ~77 MB subprocesses. A
    default at or above 40 would be no bound at all on the thing that costs memory."""
    monkeypatch.delenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", raising=False)
    assert pa._DEFAULT_LIMIT < 40
    assert pa._DEFAULT_LIMIT * 77 < 2048, (
        "the default must fit the 2 GB box alongside the ~390 MB daemon"
    )


def test_a_bad_limit_falls_back_rather_than_disabling_the_bound(monkeypatch):
    for bad in ("0", "-5", "banana", ""):
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", bad)
        assert pa._positive_int(pa._LIMIT_VAR, pa._DEFAULT_LIMIT) == pa._DEFAULT_LIMIT
