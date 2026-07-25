from __future__ import annotations

import sys
from pathlib import Path

import pytest

import tinyassets_tray


def test_source_runtime_command_preserves_python_module_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    command = tinyassets_tray._runtime_command(
        "daemon",
        ["-m", "fantasy_daemon", "--provider", "codex"],
    )

    assert command == [
        sys.executable,
        "-m",
        "fantasy_daemon",
        "--provider",
        "codex",
    ]


def test_packaged_runtime_command_reenters_frozen_executable_by_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    command = tinyassets_tray._runtime_command(
        "mcp",
        ["-m", "tinyassets.universe_server"],
    )

    assert command == [sys.executable, "--packaged-role", "mcp"]


def test_packaged_runtime_anchors_lock_and_logs_in_user_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "program" / "TinyAssets.exe"))
    monkeypatch.setattr(tinyassets_tray, "_packaged_data_dir", lambda: tmp_path / "data")

    project_dir, log_dir = tinyassets_tray._runtime_paths()

    assert project_dir == tmp_path / "program"
    assert log_dir == tmp_path / "data" / "logs"


def test_packaged_entrypoint_refuses_unknown_role() -> None:
    from tinyassets.desktop.packaged_entrypoint import dispatch

    with pytest.raises(SystemExit, match="unknown packaged runtime role"):
        dispatch(["--packaged-role", "not-a-role"])
