"""Workspace staging: removed on every exit, swept only when its owner is dead.

Concern 2026-09-30-workspace-staging-leaks-on-failed-checkouts: 334 leaked staging
directories (2.8 GiB, possibly credentialed clones) in one production universe.
The sweep that removes them must never touch a directory a live checkout owns --
proven here with a REAL second process holding one.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from tinyassets import process_liveness
from tinyassets import workspace_staging as ws


def _entries(root: Path) -> list[str]:
    return sorted(e for e in os.listdir(root) if e != process_liveness.LIVENESS_DIR)


def _fill(path: Path, n: int = 3, size: int = 1000) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "sub").mkdir(exist_ok=True)
    for i in range(n):
        (path / "sub" / f"f{i}").write_bytes(b"s" * size)
    (path / "credential-ish").write_text("token", encoding="utf-8")


def _dead_token(root: Path) -> str:
    """A token whose liveness file exists and whose owner is gone -- what a
    killed process leaves (the kernel drops its lock, the file stays)."""
    token = "proc_" + os.urandom(12).hex()
    lock = process_liveness.liveness_path(root, token)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"")
    assert process_liveness.owner_state(root, token) == process_liveness.DEAD
    return token


# --------------------------------------------------------------------------- #
# Every exit removes it
# --------------------------------------------------------------------------- #


class TestEveryExitRemovesIt:
    def test_success(self, tmp_path):
        with ws.staging(tmp_path, "run", "node") as path:
            _fill(path)
        assert not path.exists()

    def test_exception(self, tmp_path):
        with pytest.raises(RuntimeError), ws.staging(tmp_path, "run", "node") as path:
            _fill(path)
            raise RuntimeError("checkout failed")
        assert not path.exists()

    def test_cancellation(self, tmp_path):
        class Cancelled(BaseException):
            pass

        with pytest.raises(Cancelled), ws.staging(tmp_path, "run", "node") as path:
            _fill(path)
            raise Cancelled()
        assert not path.exists()

    def test_nothing_is_left_at_any_name(self, tmp_path):
        with ws.staging(tmp_path, "run", "node") as path:
            _fill(path)
        root = ws.staging_root(tmp_path)
        # Empty parent directories of this live process may remain; no FILE
        # (the credential-bearing part) survives anywhere, and no trash does.
        left = [
            p for p in root.rglob("*")
            if p.is_file() and process_liveness.LIVENESS_DIR not in p.parts
        ]
        assert left == []
        assert not [e for e in _entries(root) if e.startswith(".trash-")]

    def test_a_removal_failure_never_masks_the_original_error(self, tmp_path, monkeypatch):
        def _broken(*_a):
            raise OSError("removal broke")

        monkeypatch.setattr(ws, "_remove_completely", _broken)
        with pytest.raises(RuntimeError, match="the real error"), ws.staging(tmp_path, "r", "n"):
            raise RuntimeError("the real error")

    def test_a_parts_segment_cannot_escape_the_root(self, tmp_path):
        with pytest.raises(ValueError):
            ws.create(tmp_path, "..", "x")


# --------------------------------------------------------------------------- #
# The sweep: owner liveness decides, never age alone
# --------------------------------------------------------------------------- #


class TestSweep:
    def test_a_dead_owners_staging_is_removed_completely(self, tmp_path):
        root = ws.staging_root(tmp_path)
        root.mkdir()
        token = _dead_token(root)
        _fill(root / token / "run" / "node")

        report = ws.sweep(tmp_path)

        assert report.removed == 1
        assert report.removed_bytes == 3 * 1000 + len("token")
        assert _entries(root) == []
        # The dead owner's liveness file goes too.
        assert process_liveness.owner_state(root, token) == process_liveness.UNKNOWN

    def test_this_live_processs_staging_is_never_swept(self, tmp_path):
        path = ws.create(tmp_path, "run", "node")
        _fill(path)

        report = ws.sweep(tmp_path)

        assert report.removed == 0 and report.kept_live == 1
        assert (path / "credential-ish").is_file()
        ws.remove(path)

    def test_an_unprovable_owner_is_never_swept(self, tmp_path):
        """A token-shaped directory with no liveness file is UNKNOWN, and unknown
        is never treated as dead."""
        root = ws.staging_root(tmp_path)
        _fill(root / ("proc_" + "a" * 24) / "run")

        report = ws.sweep(tmp_path)

        assert report.removed == 0 and report.kept_unknown == 1

    def test_the_sweep_is_idempotent(self, tmp_path):
        root = ws.staging_root(tmp_path)
        root.mkdir()
        _fill(root / _dead_token(root) / "run")
        live = ws.create(tmp_path, "run", "live")

        first = ws.sweep(tmp_path)
        second = ws.sweep(tmp_path)

        assert first.removed == 1
        assert second.removed == 0 and second.removed_bytes == 0
        assert live.is_dir()
        ws.remove(live)

    def test_an_interrupted_removal_is_finished_by_the_next_sweep(self, tmp_path, monkeypatch):
        root = ws.staging_root(tmp_path)
        root.mkdir()
        _fill(root / _dead_token(root) / "run")
        real = ws._rmtree
        calls = []

        def _fails_once(path):
            calls.append(path)
            if len(calls) == 1:
                raise OSError("interrupted mid-delete")
            real(path)

        monkeypatch.setattr(ws, "_rmtree", _fails_once)
        first = ws.sweep(tmp_path)
        # Never left under a usable name: only as trash.
        assert first.failed == 1
        assert all(e.startswith(".trash-") for e in _entries(root))

        second = ws.sweep(tmp_path)
        assert second.removed == 1
        assert _entries(root) == []

    def test_a_legacy_entry_is_removed_only_if_untouched_since_start(self, tmp_path, monkeypatch):
        root = ws.staging_root(tmp_path)
        old = root / "006c7c18cd467df3"
        fresh = root / "0091c4beef94a001"
        _fill(old / "n1-aaaa")
        _fill(fresh / "n1-bbbb")
        past = ws._PROCESS_STARTED_AT - 3600
        for p in [old, *old.rglob("*")]:
            os.utime(p, (past, past))
        for p in [fresh, *fresh.rglob("*")]:
            os.utime(p, (ws._PROCESS_STARTED_AT + 5, ws._PROCESS_STARTED_AT + 5))

        report = ws.sweep(tmp_path)

        assert report.removed == 1
        assert _entries(root) == ["0091c4beef94a001"]

    def test_a_legacy_entry_with_one_fresh_file_is_kept(self, tmp_path):
        """Newest-in-tree, not the directory's own mtime."""
        root = ws.staging_root(tmp_path)
        legacy = root / "fb2c2816ebe798fa"
        _fill(legacy / "n1-cccc")
        past = ws._PROCESS_STARTED_AT - 3600
        for p in [legacy, *legacy.rglob("*")]:
            os.utime(p, (past, past))
        os.utime(legacy / "n1-cccc" / "sub" / "f0", None)  # now

        assert ws.sweep(tmp_path).removed == 0

    def test_a_linked_root_is_not_walked(self, tmp_path):
        outside = tmp_path / "outside"
        _fill(outside / "x")
        base = tmp_path / "u"
        base.mkdir()
        try:
            os.symlink(outside, ws.staging_root(base), target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable here")

        assert ws.sweep(base).removed == 0
        assert (outside / "x" / "credential-ish").is_file()

    def test_the_data_root_sweep_covers_every_universe_and_logs_it(self, tmp_path, caplog):
        for uid in ("u-one", "u-two"):
            root = ws.staging_root(tmp_path / uid)
            root.mkdir(parents=True)
            _fill(root / _dead_token(root) / "run")

        with caplog.at_level("WARNING", logger="tinyassets.workspace_staging"):
            report = ws.sweep_data_root(tmp_path)

        assert report.removed == 2
        assert "removed 2 dir(s)" in caplog.text


def test_the_boot_sweeper_sweeps_at_once_and_runs_once(tmp_path):
    """What removes the production leftovers after deploy: the serving startup
    starts it, it sweeps immediately, and a second start is a no-op."""
    from tinyassets.universe_server import (
        start_staging_sweeper_for_serving,
        stop_workspace_sweepers_for_serving,
    )

    root = ws.staging_root(tmp_path / "u-one")
    root.mkdir(parents=True)
    leaked = root / _dead_token(root)
    _fill(leaked / "run")
    try:
        start_staging_sweeper_for_serving(tmp_path)
        assert ws.start_sweeper(tmp_path) is False
        deadline = time.monotonic() + 30
        while leaked.exists():
            assert time.monotonic() < deadline, "the boot sweep never ran"
            time.sleep(0.05)
    finally:
        stop_workspace_sweepers_for_serving()
    assert ws.stop_sweeper() is True


# --------------------------------------------------------------------------- #
# A live checkout in ANOTHER process is never swept
# --------------------------------------------------------------------------- #


def test_another_live_processs_staging_survives_until_it_dies(tmp_path):
    ready = tmp_path / "ready"
    script = textwrap.dedent(
        f"""
        import sys, time
        from pathlib import Path
        from tinyassets import workspace_staging as ws
        path = ws.create(Path({str(tmp_path)!r}), "run", "live-checkout")
        (path / "credential-ish").write_text("token")
        Path({str(ready)!r}).write_text(str(path))
        time.sleep(120)
        """
    )
    proc = subprocess.Popen([sys.executable, "-c", script])
    try:
        deadline = time.monotonic() + 60
        while not ready.exists():
            assert proc.poll() is None, "helper process died"
            assert time.monotonic() < deadline, "helper never became ready"
            time.sleep(0.05)
        live = Path(ready.read_text())

        report = ws.sweep(tmp_path)

        assert report.removed == 0 and report.kept_live == 1
        assert (live / "credential-ish").is_file()
    finally:
        proc.kill()
        proc.wait(timeout=30)

    report = ws.sweep(tmp_path)
    assert report.removed == 1
    assert not live.exists()
