from __future__ import annotations

import ctypes
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
    [
        "failure-budget",
        "fatal-peer-error",
        "invalid-result",
        "invalid-blocked-result",
        "invalid-duplicate-merge",
    ],
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
        ("blocked-cooldown", True, "attach", "waiting"),
        ("invalid-blocked-result", True, "attach", "waiting"),
        ("invalid-duplicate-merge", True, "attach", "waiting"),
        ("idle", True, "attach", "waiting"),
        ("admission-failed", True, "attach", "waiting"),
        ("admission-missing", True, "attach", "waiting"),
        ("candidate-snapshot-failed", True, "attach", "waiting"),
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
    assert health["watchdog_version"] == 2


def test_settled_unconsumed_result_is_waiting_not_green(tmp_path: Path) -> None:
    run_dir = tmp_path / "openspec-drain-live"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    result_path = results_dir / "001.md"
    result_path.write_text(
        "done\nDRAIN_RESULT: BLOCKED assigned-target -\n",
        encoding="utf-8",
    )
    os.utime(result_path, (800, 800))
    state = {
        "status": "running",
        "identity": "drain-test",
        "attempts": 1,
        "last_result": None,
    }

    waiting = watchdog.result_handoff_waiting(
        state=state,
        run_dir=run_dir,
        now_epoch=1000,
        settle_seconds=120,
    )
    health = watchdog.build_health(
        state=state,
        controller_alive=True,
        mode="attach",
        active_run=run_dir,
        controller_pid=123,
        message="supervisor is live",
        result_waiting=waiting,
    )

    assert waiting is True
    assert health["health"] == "waiting"
    assert health["result_waiting"] is True
    assert health["message"] == "terminal result awaiting controller consumption"


def test_consumed_or_unsettled_result_does_not_raise_waiting_health(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "openspec-drain-live"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    result_path = results_dir / "002.md"
    result_path.write_text(
        "DRAIN_RESULT: BLOCKED assigned-target -\n",
        encoding="utf-8",
    )
    os.utime(result_path, (950, 950))

    assert not watchdog.result_handoff_waiting(
        state={
            "status": "running",
            "attempts": 2,
            "last_consumed_attempt": 1,
        },
        run_dir=run_dir,
        now_epoch=1000,
        settle_seconds=120,
    )
    assert not watchdog.result_handoff_waiting(
        state={
            "status": "running",
            "attempts": 2,
            "last_consumed_attempt": 2,
        },
        run_dir=run_dir,
        now_epoch=1200,
        settle_seconds=120,
    )


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


def test_graceful_restart_preserves_new_run_decision_after_terminal_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    output = repo / "output"
    old_run = _run(output, "openspec-drain-failing", pid=42)
    watchdog_dir = output / "openspec-drain-watchdog"
    restart_request = watchdog_dir / "restart.request"
    live_pids = {42}
    launched: list[tuple[Path, bool]] = []
    sleeps = 0

    class StopLoop(Exception):
        pass

    class FakeProcess:
        pid = 77

        @staticmethod
        def poll() -> None:
            return None

    def request_stop(_repo: Path, run_dir: Path) -> None:
        state_path = run_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update(status="failure-budget", ended_at="now")
        state_path.write_text(json.dumps(state), encoding="utf-8")
        live_pids.discard(42)

    def launch_supervisor(**kwargs: object) -> FakeProcess:
        run_dir = kwargs["run_dir"]
        assert isinstance(run_dir, Path)
        launched.append((run_dir, bool(kwargs["resume"])))
        live_pids.add(77)
        return FakeProcess()

    def advance_loop(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            restart_request.write_text("restart\n", encoding="utf-8")
        elif launched or sleeps >= 4:
            raise StopLoop

    monkeypatch.setattr(watchdog, "_pid_is_alive", live_pids.__contains__)
    monkeypatch.setattr(watchdog, "_request_supervisor_stop", request_stop)
    monkeypatch.setattr(watchdog, "_launch_supervisor", launch_supervisor)
    monkeypatch.setattr(watchdog.time, "sleep", advance_loop)

    with pytest.raises(StopLoop):
        watchdog.main(["run", "--repo", str(repo)])

    assert len(launched) == 1
    new_run, resume = launched[0]
    assert new_run.parent == output
    assert new_run.name.startswith("openspec-drain-auto-")
    assert resume is False
    assert new_run != old_run


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


def test_health_publication_failure_is_nonfatal_and_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    health_path = tmp_path / "health.json"
    health_path.write_text('{"health": "previous"}\n', encoding="utf-8")
    real_atomic_write = watchdog.atomic_write_json
    attempts = 0

    def fail_then_recover(path: Path, payload: dict[str, object]) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("sharing violation")
        real_atomic_write(path, payload)

    monkeypatch.setattr(watchdog, "atomic_write_json", fail_then_recover)

    published = watchdog._write_health(
        health_path,
        state={"status": "running", "identity": "drain-test"},
        alive=True,
        mode="attach",
        run_dir=tmp_path / "run",
        pid=42,
        message="supervisor is live",
    )

    assert published is False
    assert json.loads(health_path.read_text(encoding="utf-8")) == {
        "health": "previous"
    }
    diagnostic = tmp_path / "health-write-errors.log"
    assert "sharing violation" in diagnostic.read_text(encoding="utf-8")
    assert not watchdog._write_health(
        health_path,
        state={"status": "running", "identity": "drain-test"},
        alive=True,
        mode="attach",
        run_dir=tmp_path / "run",
        pid=42,
        message="supervisor is live",
    )
    assert len(diagnostic.read_text(encoding="utf-8").splitlines()) == 1
    assert watchdog._write_health(
        health_path,
        state={"status": "running", "identity": "drain-test"},
        alive=True,
        mode="attach",
        run_dir=tmp_path / "run",
        pid=42,
        message="supervisor is live",
    )
    assert json.loads(health_path.read_text(encoding="utf-8"))["health"] == (
        "running"
    )


def test_watch_loop_continues_after_health_publication_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    output = repo / "output"
    _run(output, "openspec-drain-live", pid=42)
    real_atomic_write = watchdog.atomic_write_json
    publications = 0
    sleeps = 0

    class StopLoop(Exception):
        pass

    def fail_once(path: Path, payload: dict[str, object]) -> None:
        nonlocal publications
        publications += 1
        if publications == 1:
            raise PermissionError("sharing violation")
        real_atomic_write(path, payload)

    def advance_loop(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise StopLoop

    monkeypatch.setattr(watchdog, "atomic_write_json", fail_once)
    monkeypatch.setattr(watchdog, "_pid_is_alive", lambda pid: pid == 42)
    monkeypatch.setattr(watchdog.time, "sleep", advance_loop)

    with pytest.raises(StopLoop):
        watchdog.main(["run", "--repo", str(repo)])

    health = json.loads(
        (
            output / "openspec-drain-watchdog" / "health.json"
        ).read_text(encoding="utf-8")
    )
    assert publications >= 2
    assert health["controller_pid"] == 42
    assert health["watchdog_version"] == 2


def test_stop_marker_survives_sticky_launch_failure_for_session_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    stop_request = (
        repo / "output" / "openspec-drain-watchdog" / "stop.request"
    )
    live_pids = {77}

    class FakeProcess:
        pid = 77

        @staticmethod
        def poll() -> int | None:
            return None if 77 in live_pids else 2

    def launch_supervisor(**_kwargs: object) -> FakeProcess:
        return FakeProcess()

    def stop_after_first_poll(_seconds: float) -> None:
        live_pids.discard(77)
        stop_request.write_text("stop until next sign-in\n", encoding="utf-8")

    monkeypatch.setattr(watchdog, "_launch_supervisor", launch_supervisor)
    monkeypatch.setattr(watchdog, "_pid_is_alive", live_pids.__contains__)
    monkeypatch.setattr(watchdog.time, "sleep", stop_after_first_poll)

    assert watchdog.main(["run", "--repo", str(repo)]) == 0
    assert stop_request.exists()
    health = json.loads(
        (
            repo / "output" / "openspec-drain-watchdog" / "health.json"
        ).read_text(encoding="utf-8")
    )
    assert health["health"] == "down"
    assert health["message"] == "stopped until next sign-in"


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


def test_autostart_uses_a_windowless_script_host() -> None:
    installer = (
        SCRIPT.parent / "install_openspec_drain_autostart.ps1"
    ).read_text(encoding="utf-8")
    launcher = (SCRIPT.parent / "launch_openspec_drain_tray.vbs").read_text(
        encoding="utf-8"
    )

    assert '-Execute "wscript.exe"' in installer
    assert '-Execute "powershell.exe"' not in installer
    assert "launch_openspec_drain_tray.vbs" in installer
    assert "shell.Run(command, 0, True)" in launcher
    assert "openspec_drain_tray.ps1" in launcher


def test_tray_relaunches_stale_watchdog_with_bounded_cadence() -> None:
    tray = (SCRIPT.parent / "openspec_drain_tray.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Request-WatchdogRecovery" in tray
    assert "$watchdogRecoveryCooldownSeconds = 60" in tray
    assert '"watchdog health is stale"' in tray
    assert "Request-WatchdogRecovery" in tray
    assert "Test-Path -LiteralPath $stopPath" in tray
    assert "[switch]$PreserveStop" in tray


def test_autostart_has_periodic_current_user_recovery_trigger() -> None:
    installer = (
        SCRIPT.parent / "install_openspec_drain_autostart.ps1"
    ).read_text(encoding="utf-8")

    assert "$recoveryTrigger = New-ScheduledTaskTrigger -Daily" in installer
    assert "MSFT_TaskRepetitionPattern" in installer
    assert 'Interval = "PT1M"' in installer
    assert 'Duration = "P1D"' in installer
    assert "Register-ScheduledTask" in installer
    assert "$GuardTaskName" in installer
    assert "--preserve-stop" in installer
    assert "$stopRequested = Test-Path -LiteralPath $stopPath" in installer
    assert "activation deferred until next sign-in" in installer
    assert "$trayProcessPattern" in installer
    assert "$watchdogProcessPattern" in installer
    assert "Local\\TinyAssetsOpenSpecDrainControl" in installer
    assert "Local\\TinyAssetsOpenSpecDrainControl" in (
        SCRIPT.parent / "openspec_drain_tray.ps1"
    ).read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="Windows Task Scheduler integration")
def test_installer_registers_logon_and_periodic_guard_tasks() -> None:
    installer = SCRIPT.parent / "install_openspec_drain_autostart.ps1"
    task_name = f"TinyAssets Drain Integration {uuid.uuid4().hex}"
    guard_name = f"{task_name} Guard"
    install = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            "-Repo",
            str(SCRIPT.parents[1]),
            "-TaskName",
            task_name,
            "-GuardTaskName",
            guard_name,
            "-NoStart",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    try:
        assert install.returncode == 0, install.stderr
        inspect = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                (
                    "$primary=Get-ScheduledTask -TaskName '"
                    + task_name
                    + "';$guard=Get-ScheduledTask -TaskName '"
                    + guard_name
                    + "';[pscustomobject]@{PrimaryTriggers=$primary.Triggers.Count;"
                    "GuardTriggers=$guard.Triggers.Count;Interval=$guard.Triggers[0].Repetition.Interval;"
                    "GuardArgs=$guard.Actions[0].Arguments;PrimaryArgs=$primary.Actions[0].Arguments}"
                    "|ConvertTo-Json -Compress"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert inspect.returncode == 0, inspect.stderr
        registered = json.loads(inspect.stdout)
        assert registered["PrimaryTriggers"] == 1
        assert registered["GuardTriggers"] == 1
        assert registered["Interval"] == "PT1M"
        assert "--preserve-stop" in registered["GuardArgs"]
        assert "--preserve-stop" not in registered["PrimaryArgs"]
    finally:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(installer),
                "-TaskName",
                task_name,
                "-GuardTaskName",
                guard_name,
                "-Uninstall",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows Task Scheduler integration")
def test_installer_defers_activation_when_session_stop_is_active() -> None:
    installer = SCRIPT.parent / "install_openspec_drain_autostart.ps1"
    repo = SCRIPT.parents[1]
    stop_request = repo / "output" / "openspec-drain-watchdog" / "stop.request"
    task_name = f"TinyAssets Drain Stop Integration {uuid.uuid4().hex}"
    guard_name = f"{task_name} Guard"
    stop_request.parent.mkdir(parents=True, exist_ok=True)
    stop_request.write_text("stop until next sign-in\n", encoding="utf-8")
    install = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            "-Repo",
            str(repo),
            "-TaskName",
            task_name,
            "-GuardTaskName",
            guard_name,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    try:
        assert install.returncode == 0, install.stderr
        assert "activation deferred until next sign-in" in install.stdout
        assert stop_request.exists()
        inspect = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                (
                    "@(Get-ScheduledTask -TaskName '"
                    + task_name
                    + "','"
                    + guard_name
                    + "' | Select-Object -ExpandProperty State)"
                    "|ConvertTo-Json -Compress"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert inspect.returncode == 0, inspect.stderr
        assert set(json.loads(inspect.stdout)) == {3}  # Ready
    finally:
        stop_request.unlink(missing_ok=True)
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(installer),
                "-TaskName",
                task_name,
                "-GuardTaskName",
                guard_name,
                "-Uninstall",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutex integration")
def test_installer_serializes_concurrent_session_stop_before_sampling() -> None:
    installer = SCRIPT.parent / "install_openspec_drain_autostart.ps1"
    repo = SCRIPT.parents[1]
    stop_request = repo / "output" / "openspec-drain-watchdog" / "stop.request"
    task_name = f"TinyAssets Drain Stop Race {uuid.uuid4().hex}"
    guard_name = f"{task_name} Guard"
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(
        None,
        True,
        "Local\\TinyAssetsOpenSpecDrainControl",
    )
    assert mutex
    process: subprocess.Popen[str] | None = None
    try:
        stop_request.unlink(missing_ok=True)
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(installer),
                "-Repo",
                str(repo),
                "-TaskName",
                task_name,
                "-GuardTaskName",
                guard_name,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=1)
        stop_request.parent.mkdir(parents=True, exist_ok=True)
        stop_request.write_text("concurrent stop\n", encoding="utf-8")
        assert kernel32.ReleaseMutex(mutex)
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr
        assert "activation deferred until next sign-in" in stdout
        assert stop_request.exists()
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        kernel32.CloseHandle(mutex)
        stop_request.unlink(missing_ok=True)
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(installer),
                "-TaskName",
                task_name,
                "-GuardTaskName",
                guard_name,
                "-Uninstall",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
