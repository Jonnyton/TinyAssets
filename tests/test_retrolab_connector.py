from __future__ import annotations

import asyncio
import json
from pathlib import Path

from workflow import universe_server
from workflow.api import retrolab


def _tool_names() -> set[str]:
    tools = asyncio.run(universe_server.mcp.list_tools(run_middleware=False))
    return {tool.name for tool in tools}


def test_retrolab_tools_are_registered() -> None:
    assert {
        "install_retrolab_worker_windows",
        "launch_retro_game_windows",
        "verify_retro_game_windows",
    } <= _tool_names()


def test_verify_reports_not_available_off_windows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(retrolab.platform, "system", lambda: "Linux")

    result = json.loads(retrolab.verify_retro_game_windows(game_path=str(tmp_path)))

    assert result["status"] == "not_available"
    assert result["platform"] == "Linux"


def test_install_requires_confirmation_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(retrolab.platform, "system", lambda: "Windows")

    result = json.loads(retrolab.install_retrolab_worker_windows(confirm=False))

    assert result["status"] == "needs_confirmation"
    assert result["command_preview"] == [
        "winget",
        "install",
        "--id",
        "DOSBox-X.DOSBox-X",
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]


def test_install_runs_allowlisted_winget_without_shell(monkeypatch) -> None:
    calls: list[dict] = []

    class Completed:
        returncode = 0
        stdout = "installed"
        stderr = ""

    def fake_run(command, *, capture_output, text, timeout, shell=False):
        calls.append({
            "command": command,
            "capture_output": capture_output,
            "text": text,
            "timeout": timeout,
            "shell": shell,
        })
        return Completed()

    monkeypatch.setattr(retrolab.platform, "system", lambda: "Windows")
    monkeypatch.setattr(retrolab.shutil, "which", lambda name: "C:/Windows/winget.exe")
    monkeypatch.setattr(retrolab.subprocess, "run", fake_run)

    result = json.loads(retrolab.install_retrolab_worker_windows(confirm=True))

    assert result["status"] == "installed"
    assert calls == [{
        "command": [
            "winget",
            "install",
            "--id",
            "DOSBox-X.DOSBox-X",
            "--exact",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        "capture_output": True,
        "text": True,
        "timeout": 600,
        "shell": False,
    }]


def test_launch_requires_existing_local_game_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(retrolab.platform, "system", lambda: "Windows")

    result = json.loads(
        retrolab.launch_retro_game_windows(
            game_path=str(tmp_path / "missing"),
            confirm=True,
        )
    )

    assert result["status"] == "invalid_game_path"


def test_launch_uses_popen_without_shell(monkeypatch, tmp_path) -> None:
    calls: list[dict] = []
    game_dir = tmp_path / "owned-game"
    game_dir.mkdir()

    class Process:
        pid = 4242

    def fake_popen(command, *, shell=False):
        calls.append({"command": command, "shell": shell})
        return Process()

    monkeypatch.setattr(retrolab.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        retrolab.shutil,
        "which",
        lambda name: "C:/Program Files/DOSBox-X/dosbox-x.exe",
    )
    monkeypatch.setattr(retrolab.subprocess, "Popen", fake_popen)

    result = json.loads(
        retrolab.launch_retro_game_windows(
            game_path=str(game_dir),
            emulator="dosbox-x",
            confirm=True,
        )
    )

    assert result["status"] == "launched"
    assert result["pid"] == 4242
    assert calls == [{
        "command": ["C:/Program Files/DOSBox-X/dosbox-x.exe", str(game_dir)],
        "shell": False,
    }]


def test_verify_finds_installed_emulator_and_local_game(monkeypatch, tmp_path) -> None:
    game_dir = tmp_path / "owned-game"
    game_dir.mkdir()

    monkeypatch.setattr(retrolab.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        retrolab.shutil,
        "which",
        lambda name: "C:/Program Files/DOSBox-X/dosbox-x.exe",
    )

    result = json.loads(retrolab.verify_retro_game_windows(game_path=str(game_dir)))

    assert result["status"] == "ready"
    assert result["game_path_ok"] is True
    assert result["emulator"] == "dosbox-x"
    assert Path(result["game_path"]).name == "owned-game"
