from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "openspec_drain_watchdog.py"
SPEC = importlib.util.spec_from_file_location("openspec_drain_watchdog", SCRIPT)
assert SPEC is not None
watchdog = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


def _run(
    output: Path,
    name: str,
    *,
    status: str = "running",
    started_at: str = "2026-07-28T19:00:00-07:00",
    ended: bool = False,
    pid: int | None = None,
) -> Path:
    run_dir = output / name
    run_dir.mkdir(parents=True)
    state: dict[str, object] = {
        "identity": f"drain-{name}",
        "status": status,
        "started_at": started_at,
        "completed_slices": 0,
        "consecutive_failures": 0,
    }
    if ended:
        state["ended_at"] = "2026-07-28T20:00:00-07:00"
    (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    if pid is not None:
        (run_dir / "supervisor.lock").write_text(
            json.dumps({"pid": pid}),
            encoding="utf-8",
        )
    return run_dir


def test_discovery_attaches_to_live_unfinished_run_before_newer_smoke(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    live = _run(output, "openspec-drain-live", pid=42)
    _run(
        output,
        "openspec-drain-smoke",
        status="dry-run",
        started_at="2026-07-28T21:00:00-07:00",
        ended=True,
    )

    decision = watchdog.discover_decision(output, pid_alive=lambda pid: pid == 42)

    assert decision.action == "attach"
    assert decision.run_dir == live
    assert decision.controller_pid == 42


def test_discovery_resumes_dead_unfinished_run_with_same_directory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    interrupted = _run(output, "openspec-drain-interrupted", pid=99)

    decision = watchdog.discover_decision(output, pid_alive=lambda _pid: False)

    assert decision.action == "resume"
    assert decision.run_dir == interrupted


def test_discovery_includes_supervisor_default_run_directory(tmp_path: Path) -> None:
    output = tmp_path / "output"
    default_run = _run(output, "openspec-drain", pid=42)

    decision = watchdog.discover_decision(output, pid_alive=lambda _pid: True)

    assert decision.action == "attach"
    assert decision.run_dir == default_run


@pytest.mark.parametrize(
    "status",
    ["failure-budget", "fatal-peer-error", "invalid-result"],
)
def test_terminal_failure_stays_down_until_explicit_restart(
    tmp_path: Path,
    status: str,
) -> None:
    output = tmp_path / "output"
    failed = _run(output, "openspec-drain-failed", status=status, ended=True)

    decision = watchdog.discover_decision(output, pid_alive=lambda _pid: False)

    assert decision.action == "down"
    assert decision.run_dir == failed


def test_clean_terminal_run_allows_fresh_bounded_run(tmp_path: Path) -> None:
    output = tmp_path / "output"
    _run(output, "openspec-drain-done", status="slice-budget", ended=True)

    decision = watchdog.discover_decision(output, pid_alive=lambda _pid: False)

    assert decision.action == "new"
    assert decision.run_dir is None


@pytest.mark.parametrize(
    ("state_status", "controller_alive", "mode", "expected"),
    [
        ("running", True, "attach", "running"),
        ("running", True, "starting", "running"),
        ("running", True, "recovering", "running"),
        ("blocked", True, "attach", "waiting"),
        ("idle", True, "attach", "waiting"),
        ("running", False, "recovering", "waiting"),
        ("failure-budget", False, "down", "down"),
        ("running", False, "attach", "down"),
    ],
)
def test_health_mapping_is_honest(
    state_status: str,
    controller_alive: bool,
    mode: str,
    expected: str,
) -> None:
    health = watchdog.build_health(
        state={"status": state_status, "identity": "drain-test"},
        controller_alive=controller_alive,
        mode=mode,
        active_run=Path("C:/run"),
        controller_pid=123 if controller_alive else None,
        message="test",
    )

    assert health["health"] == expected
    assert health["controller_alive"] is controller_alive


def test_resume_command_preserves_identity_and_finite_budgets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_dir = repo / "output" / "openspec-drain-interrupted"

    command = watchdog.supervisor_command(
        repo=repo,
        run_dir=run_dir,
        provider="claude",
        model="opus",
        resume=True,
    )

    assert "--resume" in command
    assert "--recover-stale-lock" in command
    assert command[command.index("--provider") + 1] == "claude"
    assert command[command.index("--model") + 1] == "opus"
    assert command[command.index("--hours") + 1] == "24"
    assert command[command.index("--max-slices") + 1] == "100"
    assert command[command.index("--max-failures") + 1] == "2"


def test_dry_run_writes_health_without_launching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    output = repo / "output"
    _run(output, "openspec-drain-live", pid=42)
    watchdog_dir = output / "openspec-drain-watchdog"
    watchdog_dir.mkdir()
    (watchdog_dir / "restart.request").write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(watchdog, "_pid_is_alive", lambda pid: pid == 42)
    monkeypatch.setattr(
        watchdog.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("dry-run dispatched a process"),
    )

    exit_code = watchdog.main(
        [
            "run",
            "--repo",
            str(repo),
            "--dry-run",
        ]
    )

    health = json.loads(
        (output / "openspec-drain-watchdog" / "health.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0
    assert health["mode"] == "attach"
    assert health["active_run"].endswith("openspec-drain-live")
    assert not (watchdog_dir / "restart.request").exists()


def test_atomic_health_write_retries_windows_sharing_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "health.json"
    real_replace = watchdog.os.replace
    attempts = 0

    def flaky_replace(source: Path, destination: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("sharing violation")
        real_replace(source, destination)

    monkeypatch.setattr(watchdog.os, "replace", flaky_replace)
    monkeypatch.setattr(watchdog.time, "sleep", lambda _seconds: None)

    watchdog.atomic_write_json(path, {"health": "running"})

    assert attempts == 3
    assert json.loads(path.read_text(encoding="utf-8"))["health"] == "running"


def test_dead_fast_launch_is_a_sticky_failure() -> None:
    assert (
        watchdog.dead_launch_message(
            state={"status": "running"},
            returncode=2,
        )
        == "supervisor exited 2 without a terminal state"
    )
    assert (
        watchdog.dead_launch_message(
            state={"status": "failure-budget", "ended_at": "now"},
            returncode=2,
        )
        is None
    )


def test_stop_command_writes_request_marker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    exit_code = watchdog.main(["stop", "--repo", str(repo)])

    assert exit_code == 0
    assert (
        repo / "output" / "openspec-drain-watchdog" / "stop.request"
    ).exists()


def test_status_returns_nonzero_when_health_is_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert watchdog.main(["status", "--repo", str(repo)]) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows Task Scheduler integration")
def test_installer_uninstall_does_not_require_repo_argument() -> None:
    installer = SCRIPT.parent / "install_openspec_drain_autostart.ps1"
    task_name = f"TinyAssets Drain Missing Probe {uuid.uuid4().hex}"

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            "-TaskName",
            task_name,
            "-Uninstall",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
