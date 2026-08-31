"""Cancel has to kill the child, not wait politely for it to finish.

Before this, `cancel_run` set a flag read only BETWEEN nodes (`runs.py`:
"cancelled between nodes"), and `node_sandbox.py` contained no reference to
cancellation at all. A node twenty minutes into `ws.run(["make", "-j8"])` kept
running after the owner pressed cancel, and `MAX_WORKSPACE_TIMEOUT_SECONDS` was
the only thing that ever stopped it.

That matters more than it looks. With the credential vault absolute, a borrowed
workflow cannot steal a secret — but it can still USE one while it runs. What
bounds that is the owner's ability to stop it. So cancellation is a safety
property, not a convenience.

These tests drive the REAL wait loop with a REAL child process and assert the
process is gone. A test that stubbed the launcher would prove the stub.
"""
from __future__ import annotations

import sys
import time

import pytest

from tinyassets.node_sandbox import (
    NodeSandbox,
    PlainSubprocessLauncher,
)

# A node that would run far past any patience the test has.
SLEEPER = "def run(state):\n    import time\n    time.sleep(120)\n    return {'r': 1}\n"
QUICK = "def run(state):\n    return {'r': 2 + 2}\n"


def _run(source: str, should_cancel=None, timeout: float = 60.0):
    return NodeSandbox(
        timeout=timeout,
        launcher=PlainSubprocessLauncher(),
        should_cancel=should_cancel,
    ).run_sync(
        node_id="n",
        source_code=source,
        input_state={},
        input_keys=[],
        output_keys=["r"],
        timeout=timeout,
    )


def test_a_cancel_stops_a_long_node_promptly() -> None:
    """The headline: a node that would run for two minutes ends in seconds."""
    started = time.monotonic()
    result = _run(SLEEPER, should_cancel=lambda: True)
    elapsed = time.monotonic() - started

    assert result.success is False
    assert result.cancelled is True, "the result must say the OWNER stopped it"
    assert "cancelled" in result.error.lower()
    # Generous: the point is "seconds, not the 120s the node asked for".
    assert elapsed < 30, f"cancel took {elapsed:.1f}s; the child was not killed"


def test_a_cancel_mid_flight_is_noticed_not_only_at_the_start() -> None:
    """The flag flips AFTER the node is already running, which is the real
    case: the owner presses cancel on a run that is under way."""
    flipped_at = time.monotonic() + 1.0
    result = _run(SLEEPER, should_cancel=lambda: time.monotonic() >= flipped_at)
    assert result.cancelled is True, result.error


def test_no_predicate_means_the_old_behaviour() -> None:
    """`should_cancel=None` must not change anything for callers that do not
    pass one — the historical path, where only the timeout could stop a node."""
    result = _run(QUICK)
    assert result.success is True, result.error
    assert result.cancelled is False


def test_a_normal_node_is_untouched_by_a_predicate_that_says_no() -> None:
    asked = {"n": 0}

    def _never():
        asked["n"] += 1
        return False

    result = _run(QUICK, should_cancel=_never)
    assert result.success is True, result.error
    assert result.cancelled is False


def test_a_raising_predicate_does_not_kill_the_run() -> None:
    """A closed handle or a transient IO error must not take down a node that
    is running fine. Failing the other way would let an unrelated fault kill
    the owner's work."""
    def _boom():
        raise RuntimeError("database went away")

    result = _run(QUICK, should_cancel=_boom)
    assert result.success is True, result.error
    assert result.cancelled is False


def test_cancel_beats_timeout_in_the_reported_reason() -> None:
    """Both conditions can be true at once; the owner's stop is the honest
    reason, and reporting a timeout would tell them their workflow is slow
    when in fact they cancelled it."""
    result = _run(SLEEPER, should_cancel=lambda: True, timeout=0.5)
    assert result.cancelled is True, result.error
    assert "timed out" not in result.error.lower()


@pytest.mark.skipif(sys.platform != "linux", reason="/proc is Linux")
def test_the_child_process_is_actually_gone(monkeypatch) -> None:
    """The assertion that cannot be faked: no process survives the cancel.

    `SandboxResult.cancelled` is a claim by the code under test. This reads the
    kernel instead — a cancel that returned promptly while leaving the child
    alive would pass every test above and still be the bug.

    The pid is captured at the REAL `subprocess.Popen` call, because the
    sandbox creates the child there directly rather than through a launcher
    method; an earlier draft of this test hooked a launcher method that does
    not exist and skipped itself into uselessness on both platforms.
    """
    import subprocess as _sp

    seen: dict[str, int] = {}
    real_popen = _sp.Popen

    def _capture(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        seen.setdefault("pid", proc.pid)
        return proc

    monkeypatch.setattr(_sp, "Popen", _capture)

    result = _run(SLEEPER, should_cancel=lambda: True)
    assert result.cancelled is True, result.error

    pid = seen.get("pid")
    assert pid is not None, "no child was spawned; this test proved nothing"

    # Gone, or a reaped zombie — both mean it is not running. A live process
    # reports a state letter other than Z/X. The letter is read after the last
    # ")" because a process name may itself contain parentheses.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with open(f"/proc/{pid}/stat") as fh:
                state = fh.read().rsplit(")", 1)[1].split()[0]
        except FileNotFoundError:
            return  # fully gone
        if state in ("Z", "X"):
            return
        time.sleep(0.2)
    pytest.fail(f"child {pid} is still alive in state {state!r} after cancel")
