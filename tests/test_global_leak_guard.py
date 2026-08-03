"""Behaviour of the session-scoped process-global leak guard.

Every integration test here runs the same probe suite **twice** — once with the
repo conftest active and once with a bare conftest — and asserts the difference.
That shape is deliberate: cross-family review found that the previous
integration tests passed unchanged when the hooks were completely absent, so
they proved nothing. A one-sided assertion on a subprocess run cannot tell
"the guard worked" from "the guard never ran".
"""

from __future__ import annotations

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


def _run(tmp_path: Path, body: str, *, with_guard: bool) -> subprocess.CompletedProcess:
    """Run a probe suite in a subprocess, with or without the repo conftest."""
    root = tmp_path / ("guarded" if with_guard else "bare")
    root.mkdir()
    (root / "test_probe.py").write_text(textwrap.dedent(body), encoding="utf-8")
    shim = (
        "import sys\n"
        f"sys.path.insert(0, {str(_REPO)!r})\n"
        "from tests.conftest import *  # noqa: F401,F403\n"
    ) if with_guard else "# no guard\n"
    (root / "conftest.py").write_text(shim, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "test_probe.py", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(root), timeout=180,
    )


_LEAKING_SUITE = """
    import subprocess

    def test_leaks():
        subprocess.run = lambda *a, **k: None
"""

_CORRECT_SUITE = """
    import subprocess
    from unittest.mock import patch

    def test_monkeypatch(monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)

    def test_context_manager():
        with patch("subprocess.run"):
            pass

    def test_module_scoped_owner_restores(module_owner):
        assert subprocess.run is not None

    import pytest

    REPLACEMENT = lambda *a, **k: "owned"

    @pytest.fixture(scope="module")
    def module_owner():
        original = subprocess.run
        subprocess.run = REPLACEMENT
        yield
        subprocess.run = original
"""


@pytest.mark.slow
def test_a_leak_is_reported_and_only_because_of_the_guard(tmp_path: Path) -> None:
    """Two-sided: the banner must appear WITH the guard and not without it."""
    guarded = _run(tmp_path, _LEAKING_SUITE, with_guard=True)
    bare = _run(tmp_path, _LEAKING_SUITE, with_guard=False)

    guarded_out = guarded.stdout + guarded.stderr
    bare_out = bare.stdout + bare.stderr

    assert _LEAK_BANNER in guarded_out, (
        f"guard did not report the leak:\n{guarded_out[-2000:]}"
    )
    assert "subprocess.run" in guarded_out
    assert guarded.returncode != 0, "a leaked global must fail the run"

    # The control: without the guard the identical suite is silently green.
    # If this ever starts reporting, the assertion above proves nothing.
    assert _LEAK_BANNER not in bare_out
    assert bare.returncode == 0, (
        f"the probe suite must pass on its own merits:\n{bare_out[-2000:]}"
    )


@pytest.mark.slow
def test_correct_patching_is_not_reported(tmp_path: Path) -> None:
    """monkeypatch, `with patch(...)`, and a module-scoped owner that restores.

    The module-scoped case is the one that broke both per-test designs: its
    patch is legitimately live across items and is restored at module teardown.
    Session-scoped comparison sees it restored, so there is nothing to report
    and no exemption mechanism is needed.
    """
    guarded = _run(tmp_path, _CORRECT_SUITE, with_guard=True)
    out = guarded.stdout + guarded.stderr
    assert _LEAK_BANNER not in out, (
        f"correct patching was flagged:\n{out[-2000:]}"
    )
    assert guarded.returncode == 0, (
        f"correct patching must not fail the run:\n{out[-2000:]}"
    )
    assert "3 passed" in out, out[-2000:]
