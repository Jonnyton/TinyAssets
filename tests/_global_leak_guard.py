"""Detect a process-global patch that escaped the whole test session.

Why this exists
---------------
A test that patches a process-global and fails to restore it corrupts every
later test in the same interpreter, and the damage surfaces in the *victims*
rather than the culprit — which is why this class always reads as flaky
ordering. Two measured incidents: a threaded
``patch("...github_pr.subprocess.run")`` leaked and ~70 unrelated tests received
its canned stdout (#2199), and a ``shutil.which`` stub latched
``git_bridge.is_enabled`` and silently no-opped 138 tests. In both, the guilty
test passed.

Why this is SESSION-scoped, not per-test
----------------------------------------
Per-test detection was tried and abandoned, twice, for the same reason: at the
moment a test ends you cannot tell "leaked" from "a longer-lived fixture still
legitimately owns this".

* As an autouse fixture it ran before ``monkeypatch``'s undo and produced **34
  false positives**.
* Rebuilt as a teardown hookwrapper with an opt-out marker, it still broke
  module/session fixtures: ownership spans *items* while a marker is per-*item*,
  so an unmarked test repaired an active module fixture, and a session fixture
  finalizing in a different module could not be protected at all. Both were
  reproduced under real pytest in cross-family review.

Comparing at session start/finish has none of that ambiguity. Every legitimate
fixture — function, module, package, session — has finalized by then, so
anything still altered genuinely escaped. **No exemption mechanism is needed,
and nothing is ever repaired**, which is what made the earlier versions
dangerous.

What it costs
-------------
Attribution. This says *that* something leaked, not *which* test did it. That is
the deliberate trade: a check that cannot cry wolf, versus one that names a
culprit but corrupts correct fixtures. To attribute a reported leak, re-run with
``-p no:randomly`` and bisect, or use the message's watched-attribute name to
grep for patches of it.

Scope
-----
A **five-attribute** detector. It notices rebinding of the module attributes in
:data:`WATCHED` and nothing else. Invisible to it: a consumer alias captured by
``from subprocess import run``, and any mutation that is restored before the
session ends.
"""

from __future__ import annotations

import importlib

# (module, attribute) pairs. Kept to the two families with measured incidents.
WATCHED = (
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "check_output"),
    ("subprocess", "check_call"),
    ("shutil", "which"),
)


def snapshot() -> dict[tuple[str, str], object]:
    """Current value of every watched attribute."""
    snap: dict[tuple[str, str], object] = {}
    for module_name, attr in WATCHED:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover - stdlib, but stay fail-soft
            continue
        snap[(module_name, attr)] = getattr(module, attr, None)
    return snap


def escaped(baseline: dict[tuple[str, str], object]) -> list[str]:
    """Watched attributes still altered relative to ``baseline``.

    Returns human-readable descriptions. Deliberately does NOT repair: at
    session finish there is nothing left to protect, and repairing was the
    mechanism by which earlier versions broke correct fixtures.
    """
    out: list[str] = []
    for (module_name, attr), original in baseline.items():
        current = getattr(importlib.import_module(module_name), attr, None)
        if current is not original:
            out.append(f"{module_name}.{attr} -> {current!r}")
    return out


def describe(leaked: list[str]) -> str:
    return (
        "A test left a process-global patched for the rest of this session, "
        "which silently corrupts every test that ran after it: "
        + "; ".join(leaked)
        + ". A common cause is entering `patch(...)` from inside a thread "
        "worker — that swap is not thread-local, so two threads can interleave "
        "and leave the mock installed permanently. Hoist the patch to wrap the "
        "whole concurrent section on the calling thread. To find the culprit, "
        "grep the suite for patches of the named attribute, or bisect."
    )
