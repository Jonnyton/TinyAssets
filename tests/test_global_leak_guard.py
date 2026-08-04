"""Behaviour of the session-scoped process-global leak guard.

Every integration test here compares a GUARDED run against a BARE run of the
same probe suite, and asserts the difference. Cross-family review found that
earlier versions of these tests passed unchanged when the hooks were completely
absent, so they proved nothing — a one-sided assertion on a subprocess run
cannot tell "the guard worked" from "the guard never ran".

Where a test's point is that something must NOT be reported, a bare comparison
is not enough on its own either: a run with no guard also reports nothing. Those
suites therefore carry a deliberate leak alongside the legitimate patching, so
the guarded run has to prove it is both ACTIVE (it caught the leak) and
SELECTIVE (it left the legitimate patches alone).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests import _global_leak_guard as guard

_REPO = Path(__file__).resolve().parent.parent
_LEAK_BANNER = "left a process-global patched"


def test_snapshot_captures_every_watched_attribute() -> None:
    snap = guard.snapshot()
    assert set(snap) == set(guard.WATCHED)
    assert snap[("subprocess", "run")] is subprocess.run
    assert snap[("shutil", "which")] is shutil.which


def test_escaped_is_empty_when_nothing_changed() -> None:
    assert guard.escaped(guard.snapshot()) == []


def test_escaped_reports_a_rebound_attribute() -> None:
    baseline = guard.snapshot()
    original = subprocess.run
    try:
        subprocess.run = lambda *a, **k: None
        leaked = guard.escaped(baseline)
    finally:
        subprocess.run = original
    assert len(leaked) == 1 and leaked[0].startswith("subprocess.run -> ")


def test_escaped_never_repairs() -> None:
    """Repairing is what made the per-test versions dangerous."""
    baseline = guard.snapshot()
    original = subprocess.run
    replacement = lambda *a, **k: None  # noqa: E731
    try:
        subprocess.run = replacement
        guard.escaped(baseline)
        assert subprocess.run is replacement
    finally:
        subprocess.run = original


def test_describe_names_the_attribute_and_the_usual_cause() -> None:
    text = guard.describe(["subprocess.run -> <lambda>"])
    assert "subprocess.run" in text
    assert "thread" in text


# ---------------------------------------------------------------------------
# Integration probes
# ---------------------------------------------------------------------------


def _run(
    tmp_path: Path,
    body: str,
    *,
    with_guard: bool,
    name: str = "probe",
    plugins: dict[str, str] | None = None,
    args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess:
    """Run a probe suite in a subprocess, with or without the repo conftest."""
    root = tmp_path / f"{name}-{'guarded' if with_guard else 'bare'}"
    root.mkdir(parents=True)
    (root / "test_probe.py").write_text(textwrap.dedent(body), encoding="utf-8")
    shim = (
        (
            "import sys\n"
            f"sys.path.insert(0, {str(_REPO)!r})\n"
            "from tests.conftest import *  # noqa: F401,F403\n"
        )
        if with_guard
        else "# no guard\n"
    )
    (root / "conftest.py").write_text(shim, encoding="utf-8")
    for mod, src in (plugins or {}).items():
        (root / f"{mod}.py").write_text(textwrap.dedent(src), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(root))
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", "test_probe.py", "-q", "--no-header",
            "-p", "no:cacheprovider", *args,
        ],
        capture_output=True, text=True, cwd=str(root), timeout=300, env=env,
    )


def _out(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout + proc.stderr


_LEAKING_SUITE = """
    import subprocess

    def test_leaks():
        subprocess.run = lambda *a, **k: None
"""

# Correct patching of subprocess.run at every scope that broke the earlier
# per-test designs, PLUS a deliberate shutil.which leak. The leak is what proves
# the guard was actually running; the absence of subprocess.run from the report
# is what proves it did not flag the legitimate owners.
_MIXED_SUITE = """
    import shutil
    import subprocess
    from unittest.mock import patch

    import pytest

    REPLACEMENT = lambda *a, **k: "owned"

    @pytest.fixture(scope="module")
    def module_owner():
        original = subprocess.run
        subprocess.run = REPLACEMENT
        yield
        subprocess.run = original

    # Deliberately a DIFFERENT attribute from module_owner's. Two fixtures of
    # different scope owning the same attribute is itself a leak: teardown runs
    # reverse-scope, so the session fixture restores last and reinstates the
    # module fixture's replacement. The guard caught exactly that when this
    # probe first used subprocess.run for both — the probe was wrong, not it.
    @pytest.fixture(scope="session")
    def session_owner():
        original = subprocess.check_output
        subprocess.check_output = REPLACEMENT
        yield
        subprocess.check_output = original

    def test_monkeypatch(monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)

    def test_context_manager():
        with patch("subprocess.run"):
            pass

    def test_module_scoped_owner(module_owner):
        assert subprocess.run is REPLACEMENT

    def test_session_scoped_owner(session_owner):
        assert subprocess.check_output is REPLACEMENT

    def test_leaks_a_different_attribute():
        shutil.which = lambda *a, **k: None
"""

_TRIVIAL_SUITE = """
    def test_ok():
        assert True
"""

# A competing plugin that leaks from INSIDE its own sessionfinish, as late as it
# can. Lives in its own module (not the probe conftest) because the guard's
# hooks arrive in the conftest namespace via star-import and a second
# definition there would shadow them rather than compete with them.
_LATE_LEAK_PLUGIN = """
    import subprocess

    import pytest

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(session, exitstatus):
        subprocess.run = lambda *a, **k: None
"""

# The mirror image: a plugin that legitimately owns a patch for the whole
# session and restores it in its own trylast sessionfinish.
_LATE_OWNER_PLUGIN = """
    import subprocess

    import pytest

    _ORIGINAL = None

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionstart(session):
        global _ORIGINAL
        _ORIGINAL = subprocess.run
        subprocess.run = lambda *a, **k: "owned"

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(session, exitstatus):
        subprocess.run = _ORIGINAL
"""


@pytest.mark.slow
def test_a_leak_is_reported_and_only_because_of_the_guard(tmp_path: Path) -> None:
    guarded = _run(tmp_path, _LEAKING_SUITE, with_guard=True)
    bare = _run(tmp_path, _LEAKING_SUITE, with_guard=False)

    assert _LEAK_BANNER in _out(guarded), _out(guarded)[-2000:]
    assert "subprocess.run" in _out(guarded)
    assert guarded.returncode != 0, "a leaked global must fail the run"

    # Control: without the guard the identical suite is silently green. If this
    # ever starts reporting, the assertions above prove nothing.
    assert _LEAK_BANNER not in _out(bare)
    assert bare.returncode == 0, _out(bare)[-2000:]


@pytest.mark.slow
def test_legitimate_owners_are_not_flagged_while_the_guard_is_demonstrably_live(
    tmp_path: Path,
) -> None:
    """monkeypatch, `with patch`, module- and session-scoped owners.

    Session scope is the case cross-family review said could not be protected
    per-test. The suite also leaks `shutil.which`, so the guarded run must
    report exactly that and nothing about `subprocess.run` — which is what makes
    this a real assertion rather than one that also passes with no guard.
    """
    guarded = _run(tmp_path, _MIXED_SUITE, with_guard=True, name="mixed")
    bare = _run(tmp_path, _MIXED_SUITE, with_guard=False, name="mixed")

    out = _out(guarded)
    assert _LEAK_BANNER in out, f"guard was not active:\n{out[-2000:]}"
    assert "shutil.which" in out, out[-2000:]
    assert "subprocess.run" not in out, (
        f"a legitimate owner of subprocess.run was flagged:\n{out[-2000:]}"
    )
    assert "5 passed" in out, out[-2000:]

    assert _LEAK_BANNER not in _out(bare)
    assert bare.returncode == 0, _out(bare)[-2000:]


@pytest.mark.slow
def test_a_plugin_leaking_after_every_other_finish_hook_is_caught(
    tmp_path: Path,
) -> None:
    """False negative from round 3: a `trylast` plugin leaking during finish.

    A plain `pytest_sessionfinish` check runs before other finish hooks unwind,
    so this leak escaped it and the run exited 0. The guard is a `tryfirst`
    wrapper checking post-yield, so it now sees the final state.
    """
    plugins = {"lateleak": _LATE_LEAK_PLUGIN}
    args = ("-p", "lateleak")
    guarded = _run(tmp_path, _TRIVIAL_SUITE, with_guard=True, name="late",
                   plugins=plugins, args=args)
    bare = _run(tmp_path, _TRIVIAL_SUITE, with_guard=False, name="late",
                plugins=plugins, args=args)

    assert _LEAK_BANNER in _out(guarded), _out(guarded)[-2000:]
    assert "subprocess.run" in _out(guarded)
    assert guarded.returncode != 0

    assert _LEAK_BANNER not in _out(bare)
    assert bare.returncode == 0, _out(bare)[-2000:]


@pytest.mark.slow
def test_a_plugin_restoring_in_its_own_finish_hook_is_not_flagged(
    tmp_path: Path,
) -> None:
    """False positive from round 3: a session-long owner restoring at finish.

    This is the reason the claim "everything has finalized by session finish"
    was too strong — it holds for fixtures but not for other plugins.
    """
    guarded = _run(tmp_path, _TRIVIAL_SUITE, with_guard=True, name="owner",
                   plugins={"lateowner": _LATE_OWNER_PLUGIN},
                   args=("-p", "lateowner"))
    out = _out(guarded)
    assert _LEAK_BANNER not in out, f"legitimate late restore was flagged:\n{out[-2000:]}"
    assert guarded.returncode == 0, out[-2000:]


@pytest.mark.slow
def test_a_worker_leak_fails_the_run_under_xdist(tmp_path: Path) -> None:
    """Round 3 finding 1: `session.exitstatus` on a worker is discarded.

    An instrumented `-n 2` probe showed the worker flipping 0 -> 1, the
    controller staying at 0, and the process exiting 0 — the leak reported
    nowhere. Workers now hand findings to the controller via `workeroutput`.
    """
    pytest.importorskip("xdist")
    args = ("-n", "2")
    guarded = _run(tmp_path, _LEAKING_SUITE, with_guard=True, name="xdist", args=args)
    bare = _run(tmp_path, _LEAKING_SUITE, with_guard=False, name="xdist", args=args)

    out = _out(guarded)
    assert _LEAK_BANNER in out, f"xdist worker leak was not reported:\n{out[-2000:]}"
    assert "subprocess.run" in out
    assert guarded.returncode != 0, f"xdist run exited 0 despite a leak:\n{out[-2000:]}"

    assert _LEAK_BANNER not in _out(bare)
    assert bare.returncode == 0, _out(bare)[-2000:]
