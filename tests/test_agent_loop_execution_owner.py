"""The execution owner: one loop, turns as tasks, the caller's context, cancellation."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import threading
import time

import pytest

from tinyassets.agent_loop.execution_owner import ExecutionOwner

_who = contextvars.ContextVar("who", default="nobody")


@pytest.fixture
def owner():
    return ExecutionOwner(threads=8)


def test_turns_share_one_loop_on_one_thread(owner):
    async def where():
        return threading.current_thread().name, id(asyncio.get_running_loop())

    first, second = owner.run(where()), owner.run(where())
    assert first == second
    assert first[0] == "agent-loop-owner"


def test_a_turn_sees_the_callers_context_not_another_callers(owner):
    async def read():
        await asyncio.sleep(0.01)
        return _who.get()

    def caller(name):
        _who.set(name)
        return owner.run(read())

    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        names = [f"owner-{i}" for i in range(8)]
        assert list(pool.map(caller, names)) == names


def test_cancelling_the_wait_cancels_the_turn(owner):
    started, stopped = threading.Event(), threading.Event()

    async def long_turn():
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            stopped.set()

    future = owner.submit(long_turn())
    assert started.wait(5)
    future.cancel()
    assert stopped.wait(5)


def test_a_turns_exception_reaches_its_caller(owner):
    async def failing():
        raise LookupError("held")

    with pytest.raises(LookupError, match="held"):
        owner.run(failing())


def test_many_waiting_turns_run_concurrently_and_blocking_io_does_not_queue_on_32(owner):
    big = ExecutionOwner(threads=64)

    async def waits():
        await asyncio.get_running_loop().run_in_executor(None, time.sleep, 0.5)
        return 1

    started = time.monotonic()
    futures = [big.submit(waits()) for _ in range(64)]
    assert sum(f.result(10) for f in futures) == 64
    # 64 blocking waits on 64 threads finish together, not in two batches.
    assert time.monotonic() - started < 2.0


def test_a_turn_blocking_the_loop_is_measured_as_lag(owner):
    async def blocks():
        await asyncio.sleep(0.3)
        time.sleep(0.6)  # synchronous work on the shared loop

    owner.run(blocks())
    time.sleep(0.4)
    assert owner.max_lag_s >= 0.4
