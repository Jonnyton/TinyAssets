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
import time

import pytest

from tinyassets import graph_compiler
from tinyassets.branches import NodeDefinition
from tinyassets.graph_compiler import (
    NodeTimeoutError,
    _build_prompt_template_node,
    _run_with_timeout,
)


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


# ─── the residual: queue wait must come out of the provider's own cap ─────
#
# Cancelling queued work closes the case where a call spends its WHOLE budget
# in the queue. A call that waits only part of its budget still starts, and
# used to receive the node's FULL timeout as its provider cap, because the
# ModelConfig is built once per node closure. The node future then failed at
# `timeout_seconds` while the provider ran on for the length of the queue
# wait — work continuing past the deadline that admitted it, which is the same
# defect wearing a different hat.


def _node(timeout_seconds: float):
    return NodeDefinition(
        node_id="budgeted", display_name="Budgeted",
        prompt_template="Do {x}.", input_keys=["x"], output_keys=["out"],
        timeout_seconds=timeout_seconds,
    )


def _cap_after_queue_wait(pool, *, route: str, node_timeout: float, wait_s: float):
    """Run one node behind an occupied worker; return the cap it handed over."""
    captured: dict = {}
    release_blocker = threading.Event()

    def fake_provider_call(prompt, system, *, role="writer", config=None):
        captured["config"] = config
        return "done"

    class _RecordingRouter:
        available_providers = ["claude"]

        def call_with_policy_sync(
            self, role, prompt, system, policy, config=None, **kwargs,
        ):
            captured["config"] = config
            return ("done", "claude", {})

    if route == "policy":
        fn = _build_prompt_template_node(
            _node(node_timeout), provider_call=_RecordingRouter(),
            event_sink=None, llm_policy={"preferred": {}},
        )
    else:
        fn = _build_prompt_template_node(
            _node(node_timeout), provider_call=fake_provider_call, event_sink=None,
        )

    blocker_future = pool.submit(lambda: release_blocker.wait(timeout=10.0))
    outcome: list = []
    caller = threading.Thread(target=lambda: outcome.append(fn({"x": "thing"})))
    caller.start()
    try:
        # The node's call is now queued behind the occupied worker.
        time.sleep(wait_s)
        release_blocker.set()
        blocker_future.result(timeout=10.0)
        caller.join(timeout=10.0)
    finally:
        release_blocker.set()

    assert outcome and outcome[0].get("out") == "done"
    cfg = captured.get("config")
    assert cfg is not None, "node config was not threaded to the provider"
    return cfg


@pytest.mark.parametrize("route", ["bridge", "policy"])
def test_queue_wait_comes_out_of_the_provider_cap(single_worker_pool, route):
    """A call that waited in the queue gets the REMAINING budget, not the full one."""
    node_timeout = 30.0
    queue_wait = 0.4
    cfg = _cap_after_queue_wait(
        single_worker_pool, route=route,
        node_timeout=node_timeout, wait_s=queue_wait,
    )

    assert cfg.absolute_cap_s < node_timeout - (queue_wait / 2), (
        f"node waited ~{queue_wait}s in the pool queue but was still handed the "
        f"full {node_timeout}s as its provider cap ({cfg.absolute_cap_s}); the "
        "provider therefore outlives the node's own deadline by the queue wait"
    )
    # Still a usable budget — subtracting the wait must not starve the call.
    assert cfg.absolute_cap_s > node_timeout - (queue_wait * 4)
    assert cfg.stream_timeout_profile().absolute_cap_s == pytest.approx(
        cfg.absolute_cap_s
    )


def test_subtracting_a_queue_wait_never_raises_a_sub_second_node_timeout(
    single_worker_pool,
):
    """The remaining-budget floor must not exceed the node's own timeout.

    A 0.5s node queued behind a 0.4s wait has almost nothing left. Flooring
    that at a fixed 1s would hand the provider a LARGER cap than the node ever
    asked for — raising a timeout under cover of lowering one.
    """
    node_timeout = 0.5
    cfg = _cap_after_queue_wait(
        single_worker_pool, route="bridge",
        node_timeout=node_timeout, wait_s=0.4,
    )
    assert cfg.absolute_cap_s <= node_timeout, (
        f"queued sub-second node was handed {cfg.absolute_cap_s}s, more than "
        f"the {node_timeout}s it declared"
    )
    assert cfg.absolute_cap_s > 0, "the cap must stay usable, never zero"
