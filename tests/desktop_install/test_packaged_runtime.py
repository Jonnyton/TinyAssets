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


def test_packaged_daemon_start_is_blocked_until_account_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tinyassets_tray,
        "_packaged_authority_state",
        lambda: (False, "account binding required"),
    )
    manager = tinyassets_tray.UniverseServerManager()

    allowed, reason = manager._can_start("codex")

    assert allowed is False
    assert reason == "account binding required"


def test_packaged_entrypoint_refuses_unknown_role() -> None:
    from tinyassets.desktop.packaged_entrypoint import dispatch

    with pytest.raises(SystemExit, match="unknown packaged runtime role"):
        dispatch(["--packaged-role", "not-a-role"])


def test_packaged_authority_roles_are_gated_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.desktop import packaged_entrypoint

    monkeypatch.setattr(
        packaged_entrypoint,
        "_require_authority",
        lambda: (_ for _ in ()).throw(
            packaged_entrypoint.PackagedRuntimeUnavailable("account binding required")
        ),
    )

    with pytest.raises(SystemExit, match="account binding required"):
        packaged_entrypoint.dispatch(["--packaged-role", "mcp"])


def test_packaged_health_probe_creates_clean_user_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tinyassets.desktop import packaged_entrypoint

    data_root = tmp_path / "clean-user" / "TinyAssets"
    monkeypatch.setattr(packaged_entrypoint, "_data_root", lambda: data_root)

    assert packaged_entrypoint.dispatch(["--packaged-role", "health-probe"]) == 0
    assert (data_root / "logs").is_dir()


def test_clean_first_start_creates_nested_log_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    nested = tmp_path / "new-user" / "TinyAssets" / "logs"
    monkeypatch.setattr(tinyassets_tray, "LOG_DIR", nested)
    monkeypatch.setattr(
        tinyassets_tray,
        "SINGLETON_LOCK_PATH",
        tmp_path / "new-user" / "TinyAssets" / "tray.lock",
    )

    class Manager:
        def run(self) -> None:
            return None

        def kill_all(self) -> None:
            return None

    monkeypatch.setattr(tinyassets_tray, "UniverseServerManager", Manager)

    assert tinyassets_tray.main() == 0
    assert nested.is_dir()
