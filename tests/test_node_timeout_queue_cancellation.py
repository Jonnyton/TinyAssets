"""A node that went terminal must not launch provider work afterwards.

``_run_with_timeout`` submits every provider/source_code call to a shared
bounded ``ThreadPoolExecutor`` and measures ``timeout_s`` from ``submit()``,
not from worker-allocated start.  When the pool is saturated the 9th submit
sits in the queue burning its own deadline, ``NodeTimeoutError`` fires, the
node becomes terminal — and the queued work then *starts anyway*, holding a
worker and driving a provider call whose result nobody is waiting for.  That
is unadmitted work: it begins strictly after the deadline that admitted it.

The correction is bounded by what ``concurrent.futures`` can prove:

* **Not yet started** → ``Future.cancel()`` succeeds and the call never
  happens.  No provider was invoked, so there is no effect to settle and no
  uncertain-effect risk.
* **Already started** → ``Future.cancel()`` returns ``False`` by contract and
  the work runs to completion untouched.  Invocation settlement and
  uncertain-effect protection are preserved exactly as before; the worker
  thread is still never killed.

These tests pin both halves.  The first is the defect; the second is the
guard that the fix does not over-correct into interrupting live work.
"""

from __future__ import annotations

import concurrent.futures
import threading

import pytest

from tinyassets import graph_compiler
from tinyassets.graph_compiler import NodeTimeoutError, _run_with_timeout


@pytest.fixture()
def single_worker_pool(monkeypatch):
    """Pin the shared executor to one worker so queueing is deterministic.

    Saturation is then a single occupied worker rather than a race against
    the real 8-wide pool, so neither test depends on timing luck.
    """
    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="test-node-timeout",
    )
    monkeypatch.setattr(graph_compiler, "_TIMEOUT_EXECUTOR", pool)
    try:
        yield pool
    finally:
        pool.shutdown(wait=False)


def test_queued_work_never_starts_once_its_node_is_terminal(single_worker_pool):
    """A call still in the queue at its deadline must never be launched."""
    release_blocker = threading.Event()
    victim_started = threading.Event()

    def _blocker() -> str:
        # Holds the only worker, so the victim below can only queue.
        release_blocker.wait(timeout=10.0)
        return "blocker"

    def _victim() -> str:
        victim_started.set()
        return "victim"

    blocker_future = single_worker_pool.submit(_blocker)
    try:
        with pytest.raises(NodeTimeoutError) as exc_info:
            _run_with_timeout(_victim, timeout_s=0.1, node_id="queued_node")
        assert exc_info.value.node_id == "queued_node"

        # The node is terminal. Free the worker and give the pool every
        # chance to run the abandoned item.
        release_blocker.set()
        blocker_future.result(timeout=10.0)
        started_after_terminal = victim_started.wait(timeout=1.0)
    finally:
        release_blocker.set()

    assert not started_after_terminal, (
        "work queued behind a saturated pool started AFTER its node already "
        "failed with NodeTimeoutError — the node is terminal but its provider "
        "call runs anyway, entirely outside the deadline that admitted it"
    )


def test_work_already_running_is_left_to_settle(single_worker_pool):
    """Started work must run to completion — no interruption, no replay."""
    release_worker = threading.Event()
    call_count: list[int] = []
    finished = threading.Event()

    def _slow() -> str:
        call_count.append(1)
        release_worker.wait(timeout=10.0)
        finished.set()
        return "settled"

    try:
        with pytest.raises(NodeTimeoutError):
            _run_with_timeout(_slow, timeout_s=0.1, node_id="running_node")

        # It was already executing when the deadline fired: the timeout must
        # not have torn it down, and it must not have been re-dispatched.
        assert call_count == [1]
        release_worker.set()
        assert finished.wait(timeout=10.0), (
            "in-flight work was disturbed by the deadline; settlement and "
            "uncertain-effect protection require it to finish untouched"
        )
        assert call_count == [1], "timed-out work must never be replayed"
    finally:
        release_worker.set()
