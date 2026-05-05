from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from workflow.runtime.proc_launch import (
    launch_chocolate_doom,
    launch_dosbox_staging,
    launch_process,
    launch_retroarch,
    launch_scummvm,
)


@pytest.mark.parametrize(
    ("engine", "launcher"),
    [
        ("scummvm", launch_scummvm),
        ("chocolate-doom", launch_chocolate_doom),
        ("dosbox-staging", launch_dosbox_staging),
        ("retroarch", launch_retroarch),
    ],
)
def test_emulator_launchers_capture_stdout_and_stderr_uniformly(engine, launcher):
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=7,
            stdout=f"{engine} stdout\n",
            stderr=f"{engine} stderr\n",
        )

    log = launcher(
        [engine, "--version"],
        cwd=Path("/tmp"),
        env={"PATH": "/usr/bin"},
        timeout=2,
        runner=fake_runner,
    )

    assert log.engine == engine
    assert log.argv == (engine, "--version")
    assert log.returncode == 7
    assert log.stdout == f"{engine} stdout\n"
    assert log.stderr == f"{engine} stderr\n"
    assert log.cwd == "/tmp"
    assert log.timed_out is False
    assert log.ok is False

    args, kwargs = calls[0]
    assert args == ([engine, "--version"],)
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.PIPE
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert kwargs["check"] is False
    assert kwargs["timeout"] == 2


def test_launch_process_records_timeout_stdio():
    def fake_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=0.1,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    log = launch_process("retroarch", ["retroarch", "-L", "core"], timeout=0.1, runner=fake_runner)

    assert log.engine == "retroarch"
    assert log.returncode is None
    assert log.stdout == "partial stdout"
    assert log.stderr == "partial stderr"
    assert log.timed_out is True
    assert log.ok is False


def test_launch_process_records_spawn_failure_as_log():
    def fake_runner(*args, **kwargs):
        raise FileNotFoundError("retroarch")

    log = launch_process("retroarch", ["retroarch"], runner=fake_runner)

    assert log.returncode is None
    assert log.stdout == ""
    assert "FileNotFoundError" in log.stderr
    assert log.launch_error == log.stderr
    assert log.ok is False


def test_launch_process_normalizes_engine_aliases():
    def fake_runner(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    chocolate = launch_process("Chocolate Doom", ["chocolate-doom"], runner=fake_runner)
    dosbox = launch_process("dosbox_staging", ["dosbox"], runner=fake_runner)

    assert chocolate.engine == "chocolate-doom"
    assert dosbox.engine == "dosbox-staging"


def test_launch_process_rejects_unknown_engine_before_spawning():
    def should_not_run(*args, **kwargs):
        raise AssertionError("runner should not be called")

    with pytest.raises(ValueError, match="unsupported process launch engine"):
        launch_process("unknown", ["unknown"], runner=should_not_run)
