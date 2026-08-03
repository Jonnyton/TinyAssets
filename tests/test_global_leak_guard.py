"""Lifecycle semantics of the process-global leak guard.

Cross-family review rated "no committed tests for its own lifecycle" as
blocking, and it was right: the previous evidence was an ad-hoc probe covering
three easy cases, while three separate defects lived in the parts it did not
touch — scope ownership, teardown-error masking, and wrapper ordering.

The pure helpers are unit-tested here. The hook wiring that uses them is
exercised end-to-end by `test_guard_integration_*`, which run a real pytest in
a subprocess so the actual hook ordering is what gets checked, not a
reimplementation of it.
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


def test_snapshot_captures_every_watched_attribute() -> None:
    snap = guard.snapshot()
    assert set(snap) == {pair for pair in guard.WATCHED}
    assert snap[("subprocess", "run")] is subprocess.run
    assert snap[("shutil", "which")] is shutil.which


def test_diff_is_empty_when_nothing_changed() -> None:
    assert guard.diff(guard.snapshot()) == []


def test_diff_reports_a_rebound_attribute() -> None:
    baseline = guard.snapshot()
    original = subprocess.run
    try:
        subprocess.run = lambda *a, **k: None
        changed = guard.diff(baseline)
    finally:
        subprocess.run = original
    assert [(m, a) for m, a, _ in changed] == [("subprocess", "run")]


def test_repair_restores_the_original() -> None:
    baseline = guard.snapshot()
    original = subprocess.run
    subprocess.run = lambda *a, **k: None
    guard.repair(guard.diff(baseline))
    assert subprocess.run is original


def test_exempt_targets_defaults_to_everything_when_bare() -> None:
    """A bare marker is blunt but explicit; a specific one is narrow."""
    assert guard.exempt_targets(()) == {f"{m}.{a}" for m, a in guard.WATCHED}
    assert guard.exempt_targets(("subprocess.run",)) == {"subprocess.run"}


def test_exempt_target_is_neither_reported_nor_repaired() -> None:
    """The whole point: a scope-owning fixture must not be broken.

    Repairing an attribute a module/session fixture still owns would restore
    the original mid-scope and corrupt the tests that follow — which is exactly
    what the first version of this guard did.
    """
    baseline = guard.snapshot()
    original = subprocess.run
    replacement = lambda *a, **k: None  # noqa: E731
    try:
        subprocess.run = replacement
        changed = guard.diff(baseline, exempt={"subprocess.run"})
        assert changed == []
        guard.repair(changed)
        assert subprocess.run is replacement, (
            "an exempt attribute must be left alone, not repaired"
        )
    finally:
        subprocess.run = original


def test_describe_names_the_node_and_the_attribute() -> None:
    baseline = guard.snapshot()
    original = subprocess.run
    try:
        subprocess.run = lambda *a, **k: None
        text = guard.describe("tests/x.py::test_y", guard.diff(baseline))
    finally:
        subprocess.run = original
    assert "tests/x.py::test_y" in text
    assert "subprocess.run" in text
    assert guard.MARKER in text, "the message must say how to opt out"


def _run_pytest(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    """Run a real pytest against `body`, with the repo's conftest active."""
    test_file = tmp_path / "test_probe.py"
    test_file.write_text(textwrap.dedent(body), encoding="utf-8")
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(_REPO)!r})\n"
        "from tests.conftest import *  # noqa: F401,F403\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "--no-header",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(tmp_path), timeout=180,
    )


@pytest.mark.slow
def test_guard_integration_catches_a_leak_and_spares_correct_patching(
    tmp_path: Path,
) -> None:
    result = _run_pytest(tmp_path, """
        import subprocess
        from unittest.mock import patch

        def test_leaks():
            subprocess.run = lambda *a, **k: None

        def test_monkeypatch_is_fine(monkeypatch):
            monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)

        def test_context_manager_is_fine():
            with patch("subprocess.run"):
                pass
    """)
    out = result.stdout + result.stderr
    assert "left a process-global patched" in out, out[-2000:]
    assert "test_leaks" in out
    assert "3 passed" in out or "2 passed" in out, (
        f"only the leaking test may be reported:\n{out[-2000:]}"
    )
    assert "test_monkeypatch_is_fine" not in out.split("short test summary")[-1]


@pytest.mark.slow
def test_guard_integration_does_not_mask_an_existing_teardown_error(
    tmp_path: Path,
) -> None:
    """A finalizer that raises must still be visible.

    The guard runs after every finalizer; if it replaced their exception with
    its own, the more informative failure would vanish.
    """
    result = _run_pytest(tmp_path, """
        import subprocess
        import pytest

        @pytest.fixture
        def leaky_finalizer():
            yield
            subprocess.run = lambda *a, **k: None
            raise RuntimeError("ORIGINAL TEARDOWN FAILURE")

        def test_x(leaky_finalizer):
            pass
    """)
    out = result.stdout + result.stderr
    assert "ORIGINAL TEARDOWN FAILURE" in out, (
        f"the finalizer's own error was masked:\n{out[-2000:]}"
    )


@pytest.mark.slow
def test_guard_integration_respects_the_opt_out_marker(tmp_path: Path) -> None:
    """A module-scoped fixture that owns the attribute stays intact."""
    result = _run_pytest(tmp_path, """
        import subprocess
        import pytest

        REPLACEMENT = lambda *a, **k: "owned"

        @pytest.fixture(scope="module", autouse=True)
        def owns_subprocess_run():
            original = subprocess.run
            subprocess.run = REPLACEMENT
            yield
            subprocess.run = original

        pytestmark = pytest.mark.allow_global_patch("subprocess.run")

        def test_first():
            assert subprocess.run is REPLACEMENT

        def test_second_still_sees_the_fixtures_patch():
            assert subprocess.run is REPLACEMENT
    """)
    out = result.stdout + result.stderr
    assert "2 passed" in out, (
        f"a scope-owning fixture must not be flagged or repaired:\n{out[-2000:]}"
    )
    assert "left a process-global patched" not in out
