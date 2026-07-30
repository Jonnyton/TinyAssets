#!/usr/bin/env python3
"""Keep one bounded OpenSpec drain observable across Windows user sessions."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from openspec_drain_supervisor import (  # noqa: E402
    RunLock,
    _pid_is_alive,
    parse_result,
)

WATCHDOG_DIR_NAME = "openspec-drain-watchdog"
FAILURE_STATUSES = {
    "failure-budget",
    "fatal-peer-error",
    "invalid-result",
    "invalid-blocked-result",
    "invalid-duplicate-merge",
    "worker-failed",
    "merge-verification-failed",
    "transient-failure",
}
WAITING_STATUSES = {
    "admission-failed",
    "admission-missing",
    "candidate-snapshot-failed",
    "blocked",
    "blocked-cooldown",
    "idle",
    "invalid-blocked-result",
    "invalid-duplicate-merge",
    "partial",
    "partial-stalled",
    "transient-provider-error",
    "resuming",
    "starting",
    "stop-requested",
}
RESULT_HANDOFF_SETTLE_SECONDS = 120.0


@dataclass(frozen=True)
class Decision:
    action: str
    run_dir: Path | None
    controller_pid: int | None = None
    message: str = ""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_lock_pid(run_dir: Path) -> int | None:
    lock = _read_json(run_dir / "supervisor.lock")
    try:
        return int(lock["pid"]) if lock else None
    except (KeyError, TypeError, ValueError):
        return None


def _run_records(output_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not output_dir.exists():
        return []
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in output_dir.iterdir():
        if path.name != "openspec-drain" and not path.name.startswith(
            "openspec-drain-"
        ):
            continue
        if not path.is_dir() or path.name == WATCHDOG_DIR_NAME:
            continue
        state = _read_json(path / "state.json")
        if not state or state.get("status") == "dry-run":
            continue
        if not state.get("identity") or not state.get("started_at"):
            continue
        records.append((path, state))
    return records


def discover_decision(
    output_dir: Path,
    *,
    pid_alive: Callable[[int], bool] | None = None,
) -> Decision:
    """Choose attach/resume/new/down without mutating drain state."""
    pid_alive = pid_alive or _pid_is_alive
    records = _run_records(output_dir)
    unfinished = [
        record for record in records if not record[1].get("ended_at")
    ]
    if unfinished:
        run_dir, _state = max(
            unfinished,
            key=lambda record: str(record[1].get("started_at", "")),
        )
        pid = _read_lock_pid(run_dir)
        if pid is not None and pid_alive(pid):
            return Decision("attach", run_dir, pid, "attached to live drain")
        return Decision("resume", run_dir, None, "resuming interrupted drain")

    completed = [record for record in records if record[1].get("ended_at")]
    if completed:
        run_dir, state = max(
            completed,
            key=lambda record: str(record[1].get("started_at", "")),
        )
        status = str(state.get("status", "unknown"))
        if status in FAILURE_STATUSES:
            return Decision(
                "down",
                run_dir,
                None,
                f"terminal drain failure: {status}",
            )
    return Decision("new", None, None, "starting a fresh bounded drain")


def build_health(
    *,
    state: dict[str, Any] | None,
    controller_alive: bool,
    mode: str,
    active_run: Path | None,
    controller_pid: int | None,
    message: str,
    result_waiting: bool = False,
) -> dict[str, Any]:
    state = state or {}
    state_status = str(state.get("status", "unknown"))
    if mode == "down":
        health = "down"
    elif mode == "stopping":
        health = "waiting"
    elif not controller_alive:
        health = "waiting" if mode in {"recovering", "starting"} else "down"
    elif result_waiting:
        health = "waiting"
        message = "terminal result awaiting controller consumption"
    elif state_status in WAITING_STATUSES:
        health = "waiting"
    else:
        health = "running"
    return {
        "health": health,
        "mode": mode,
        "message": message,
        "updated_at": _now_iso(),
        "active_run": str(active_run.resolve()) if active_run else None,
        "controller_alive": controller_alive,
        "controller_pid": controller_pid,
        "identity": state.get("identity"),
        "controller_status": state_status,
        "result_waiting": result_waiting,
        "attempts": state.get("attempts", 0),
        "completed_slices": state.get("completed_slices", 0),
        "consecutive_failures": state.get("consecutive_failures", 0),
    }


def result_handoff_waiting(
    *,
    state: dict[str, Any] | None,
    run_dir: Path | None,
    now_epoch: float | None = None,
    settle_seconds: float = RESULT_HANDOFF_SETTLE_SECONDS,
) -> bool:
    """Detect a settled valid current-attempt result not yet in controller state."""
    if not state or not run_dir or state.get("status") != "running":
        return False
    try:
        attempt = int(state.get("attempts", 0))
    except (TypeError, ValueError):
        return False
    if attempt < 1:
        return False

    consumed_value = state.get("last_consumed_attempt")
    if consumed_value is None:
        last_result = state.get("last_result")
        if last_result is None:
            consumed = 0
        elif isinstance(last_result, dict) and last_result.get("attempt"):
            try:
                consumed = int(last_result["attempt"])
            except (TypeError, ValueError):
                return False
        else:
            return False
    else:
        try:
            consumed = int(consumed_value)
        except (TypeError, ValueError):
            return False
    if attempt <= consumed:
        return False

    result_path = run_dir / "results" / f"{attempt:03d}.md"
    now_epoch = time.time() if now_epoch is None else now_epoch
    try:
        if now_epoch - result_path.stat().st_mtime < settle_seconds:
            return False
        parse_result(
            result_path.read_text(encoding="utf-8", errors="replace")
        )
    except (OSError, ValueError):
        return False
    return True


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def supervisor_command(
    *,
    repo: Path,
    run_dir: Path,
    provider: str,
    model: str | None,
    resume: bool,
) -> list[str]:
    command = [
        sys.executable,
        str(repo / "scripts" / "openspec_drain_supervisor.py"),
        "run",
        "--repo",
        str(repo),
        "--run-dir",
        str(run_dir),
        "--provider",
        provider,
        "--hours",
        "24",
        "--max-slices",
        "100",
        "--worker-timeout",
        "5400",
        "--max-failures",
        "2",
        "--idle-minutes",
        "30",
    ]
    if model:
        command.extend(["--model", model])
    if resume:
        command.extend(
            [
                "--resume",
                "--recover-stale-lock",
                "--clear-stop",
            ]
        )
    return command


def _new_run_dir(output_dir: Path) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    candidate = output_dir / f"openspec-drain-auto-{stamp}"
    suffix = 1
    while candidate.exists():
        candidate = output_dir / f"openspec-drain-auto-{stamp}-{suffix}"
        suffix += 1
    return candidate


def _creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _launch_supervisor(
    *,
    repo: Path,
    run_dir: Path,
    provider: str,
    model: str | None,
    resume: bool,
    watchdog_dir: Path,
) -> subprocess.Popen[str]:
    watchdog_dir.mkdir(parents=True, exist_ok=True)
    log = (watchdog_dir / "controller-launch.log").open(
        "a",
        encoding="utf-8",
    )
    try:
        return subprocess.Popen(
            supervisor_command(
                repo=repo,
                run_dir=run_dir,
                provider=provider,
                model=model,
                resume=resume,
            ),
            cwd=repo,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=_creation_flags(),
        )
    finally:
        log.close()


def _request_supervisor_stop(repo: Path, run_dir: Path) -> None:
    try:
        subprocess.run(
            [
                sys.executable,
                str(repo / "scripts" / "openspec_drain_supervisor.py"),
                "stop",
                "--run-dir",
                str(run_dir),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def dead_launch_message(
    *,
    state: dict[str, Any] | None,
    returncode: int,
) -> str | None:
    """Return a sticky failure when our supervisor dies without ending its run."""
    if state and state.get("ended_at"):
        return None
    return f"supervisor exited {returncode} without a terminal state"


def _write_health(
    health_path: Path,
    *,
    state: dict[str, Any] | None,
    alive: bool,
    mode: str,
    run_dir: Path | None,
    pid: int | None,
    message: str,
) -> None:
    waiting = result_handoff_waiting(state=state, run_dir=run_dir)
    atomic_write_json(
        health_path,
        build_health(
            state=state,
            controller_alive=alive,
            mode=mode,
            active_run=run_dir,
            controller_pid=pid,
            message=message,
            result_waiting=waiting,
        ),
    )


def _watch(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    output_dir = repo / "output"
    watchdog_dir = output_dir / WATCHDOG_DIR_NAME
    health_path = watchdog_dir / "health.json"
    stop_request = watchdog_dir / "stop.request"
    restart_request = watchdog_dir / "restart.request"
    watchdog_dir.mkdir(parents=True, exist_ok=True)

    lock = RunLock(
        watchdog_dir / "watchdog.lock",
        recover=True,
    )
    try:
        lock.acquire()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    active_run: Path | None = None
    controller_pid: int | None = None
    mode = "starting"
    message = "watchdog starting"
    stop_sent = False
    restart_after_stop = False
    launched_process: subprocess.Popen[str] | None = None
    sticky_failure: str | None = None
    stop_request.unlink(missing_ok=True)
    restart_request.unlink(missing_ok=True)

    try:
        decision = discover_decision(output_dir)
        if args.dry_run:
            state = (
                _read_json(decision.run_dir / "state.json")
                if decision.run_dir
                else None
            )
            alive = bool(
                decision.controller_pid
                and _pid_is_alive(decision.controller_pid)
            )
            _write_health(
                health_path,
                state=state,
                alive=alive,
                mode=decision.action,
                run_dir=decision.run_dir,
                pid=decision.controller_pid,
                message=decision.message,
            )
            return 0

        while True:
            wants_stop = stop_request.exists()
            wants_restart = restart_request.exists()
            alive = bool(controller_pid and _pid_is_alive(controller_pid))
            state = (
                _read_json(active_run / "state.json")
                if active_run
                else None
            )
            if active_run and not alive and launched_process is not None:
                returncode = launched_process.poll()
                if returncode is not None:
                    sticky_failure = dead_launch_message(
                        state=state,
                        returncode=returncode,
                    )

            if sticky_failure and not wants_restart:
                if wants_stop:
                    stop_request.unlink(missing_ok=True)
                    _write_health(
                        health_path,
                        state=state,
                        alive=False,
                        mode="down",
                        run_dir=active_run,
                        pid=None,
                        message="stopped until next sign-in",
                    )
                    return 0
                _write_health(
                    health_path,
                    state=state,
                    alive=False,
                    mode="down",
                    run_dir=active_run,
                    pid=None,
                    message=sticky_failure,
                )
                time.sleep(args.poll_seconds)
                continue

            if (wants_stop or wants_restart) and active_run and alive:
                if not stop_sent:
                    _request_supervisor_stop(repo, active_run)
                    stop_sent = True
                restart_after_stop = wants_restart
                mode = "stopping"
                message = (
                    "stopping before restart"
                    if restart_after_stop
                    else "stopping until next sign-in"
                )
                _write_health(
                    health_path,
                    state=state,
                    alive=True,
                    mode=mode,
                    run_dir=active_run,
                    pid=controller_pid,
                    message=message,
                )
                time.sleep(args.poll_seconds)
                continue

            if active_run and not alive:
                if wants_stop and not restart_after_stop:
                    _write_health(
                        health_path,
                        state=state,
                        alive=False,
                        mode="down",
                        run_dir=active_run,
                        pid=None,
                        message="stopped until next sign-in",
                    )
                    return 0
                if wants_restart or restart_after_stop:
                    restart_request.unlink(missing_ok=True)
                    stop_request.unlink(missing_ok=True)
                    decision = Decision(
                        "new",
                        None,
                        None,
                        "explicit restart requested",
                    )
                    restart_after_stop = False
                    sticky_failure = None
                else:
                    decision = discover_decision(output_dir)
                active_run = None
                controller_pid = None
                launched_process = None
                stop_sent = False

            if active_run is None:
                if stop_request.exists():
                    _write_health(
                        health_path,
                        state=None,
                        alive=False,
                        mode="down",
                        run_dir=None,
                        pid=None,
                        message="stopped until next sign-in",
                    )
                    return 0
                if restart_request.exists():
                    restart_request.unlink(missing_ok=True)
                    decision = Decision("new", None, None, "explicit restart")
                    sticky_failure = None
                else:
                    decision = discover_decision(output_dir)

                if decision.action == "down":
                    state = (
                        _read_json(decision.run_dir / "state.json")
                        if decision.run_dir
                        else None
                    )
                    _write_health(
                        health_path,
                        state=state,
                        alive=False,
                        mode="down",
                        run_dir=decision.run_dir,
                        pid=None,
                        message=decision.message,
                    )
                    time.sleep(args.poll_seconds)
                    continue

                if decision.action == "attach":
                    active_run = decision.run_dir
                    controller_pid = decision.controller_pid
                    mode = "attach"
                    message = decision.message
                else:
                    active_run = (
                        decision.run_dir
                        if decision.action == "resume"
                        else _new_run_dir(output_dir)
                    )
                    assert active_run is not None
                    persisted_state = (
                        _read_json(active_run / "state.json")
                        if decision.action == "resume"
                        else None
                    )
                    provider = str(
                        (persisted_state or {}).get("provider")
                        or args.provider
                    )
                    model_value = (persisted_state or {}).get("model")
                    if decision.action == "resume":
                        model = (
                            str(model_value)
                            if model_value is not None
                            else None
                        )
                    else:
                        model = args.model
                    launched_process = _launch_supervisor(
                        repo=repo,
                        run_dir=active_run,
                        provider=provider,
                        model=model,
                        resume=decision.action == "resume",
                        watchdog_dir=watchdog_dir,
                    )
                    controller_pid = launched_process.pid
                    mode = (
                        "recovering"
                        if decision.action == "resume"
                        else "starting"
                    )
                    message = decision.message

            lock_pid = _read_lock_pid(active_run) if active_run else None
            if lock_pid and _pid_is_alive(lock_pid):
                controller_pid = lock_pid
                alive = True
                mode = "attach"
                message = "supervisor is live"
            else:
                alive = bool(controller_pid and _pid_is_alive(controller_pid))
            state = (
                _read_json(active_run / "state.json")
                if active_run
                else None
            )
            _write_health(
                health_path,
                state=state,
                alive=alive,
                mode=mode,
                run_dir=active_run,
                pid=controller_pid if alive else None,
                message=message,
            )
            time.sleep(args.poll_seconds)
    finally:
        lock.release()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--repo", type=Path, default=Path.cwd())
    run.add_argument("--provider", choices=["codex", "claude"], default="codex")
    run.add_argument("--model")
    run.add_argument("--poll-seconds", type=float, default=5.0)
    run.add_argument("--dry-run", action="store_true")
    for command in ("status", "stop", "restart"):
        item = subparsers.add_parser(command)
        item.add_argument("--repo", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = args.repo.resolve()
    watchdog_dir = repo / "output" / WATCHDOG_DIR_NAME
    if args.command == "status":
        health_path = watchdog_dir / "health.json"
        if not health_path.exists():
            print(f"no watchdog health: {health_path}", file=sys.stderr)
            return 1
        print(health_path.read_text(encoding="utf-8"), end="")
        return 0
    if args.command in {"stop", "restart"}:
        watchdog_dir.mkdir(parents=True, exist_ok=True)
        marker = watchdog_dir / f"{args.command}.request"
        marker.write_text(f"{args.command} requested {_now_iso()}\n", encoding="utf-8")
        print(f"{args.command} requested: {marker}")
        return 0
    if args.poll_seconds <= 0:
        print("--poll-seconds must be positive", file=sys.stderr)
        return 2
    if not repo.is_dir():
        print(f"repo is not a directory: {repo}", file=sys.stderr)
        return 2
    return _watch(args)


if __name__ == "__main__":
    raise SystemExit(main())
