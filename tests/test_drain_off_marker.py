"""The durable drain.off marker must stop both drain entry points.

A watchdog restart deletes ``stop.request`` and resumes orderly-stopped
drains, so a graceful stop alone is not durable. ``drain.off`` is the
machine-enforced off switch: never auto-cleared, honored by both the
watchdog and the supervisor. Removing the file is the only re-enable.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_marker(repo: Path) -> Path:
    watchdog_dir = repo / "output" / "openspec-drain-watchdog"
    watchdog_dir.mkdir(parents=True)
    marker = watchdog_dir / "drain.off"
    marker.write_text("off\n", encoding="utf-8")
    return marker


def test_watchdog_reports_off_and_keeps_marker(tmp_path: Path) -> None:
    marker = _write_marker(tmp_path)

    # Subprocess with a hard timeout: without the marker guard the
    # watchdog enters its infinite poll loop, and a hang must read as a
    # failure, not block the suite.
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "openspec_drain_watchdog.py"),
            "run",
            "--repo",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0
    health = json.loads(
        (tmp_path / "output" / "openspec-drain-watchdog" / "health.json")
        .read_text(encoding="utf-8")
    )
    assert health["mode"] == "off"
    assert marker.exists()


def test_watchdog_loop_signals_honor_off_marker(tmp_path: Path) -> None:
    watchdog = _load("openspec_drain_watchdog")
    stop_request = tmp_path / "stop.request"
    restart_request = tmp_path / "restart.request"
    off_marker = tmp_path / "drain.off"

    assert watchdog.stop_restart_signals(
        stop_request, restart_request, off_marker
    ) == (False, False)

    restart_request.write_text("restart\n", encoding="utf-8")
    assert watchdog.stop_restart_signals(
        stop_request, restart_request, off_marker
    ) == (False, True)

    # drain.off forces stop and vetoes a pending restart request.
    off_marker.write_text("off\n", encoding="utf-8")
    assert watchdog.stop_restart_signals(
        stop_request, restart_request, off_marker
    ) == (True, False)


def test_supervisor_wait_observes_off_marker_mid_run(tmp_path: Path) -> None:
    supervisor = _load("openspec_drain_supervisor")
    stop_file = tmp_path / "supervisor.stop"
    off_file = tmp_path / "drain.off"
    off_file.write_text("off\n", encoding="utf-8")

    result = supervisor.wait_interruptibly(
        stop_file=stop_file,
        seconds=30.0,
        deadline_monotonic=1_000_000.0,
        monotonic=lambda: 0.0,
        sleep=lambda _s: None,
        off_file=off_file,
    )

    assert result == "stop-requested"


def test_supervisor_refuses_run_even_with_clear_stop(
    tmp_path: Path, capsys
) -> None:
    supervisor = _load("openspec_drain_supervisor")
    marker = _write_marker(tmp_path)

    rc = supervisor.main(
        [
            "run",
            "--repo",
            str(tmp_path),
            "--run-dir",
            str(tmp_path / "output" / "run1"),
            "--clear-stop",
        ]
    )

    assert rc == 2
    assert "drain.off" in capsys.readouterr().err
    assert marker.exists()
    assert not (tmp_path / "output" / "run1" / "state.json").exists()
