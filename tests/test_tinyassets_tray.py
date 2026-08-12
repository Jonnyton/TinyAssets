"""Credential-neutral tray daemon lifecycle tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pystray")
pytest.importorskip("PIL")

import tinyassets_tray  # noqa: E402
from tinyassets import preferences  # noqa: E402


class FakePopen:
    def __init__(self) -> None:
        self._returncode: int | None = None

    def poll(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self._returncode = 0

    def kill(self) -> None:
        self._returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self._returncode or 0

    def exit_with(self, code: int = 0) -> None:
        self._returncode = code


class FakeLog:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def write(self, _text: str) -> None:
        pass

    def flush(self) -> None:
        pass


@pytest.fixture
def mgr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    prefs_path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_PREFS_PATH", prefs_path)
    preferences.reset_cache()
    data_root = tmp_path / "data"
    universe = data_root / "testverse"
    universe.mkdir(parents=True)
    (data_root / ".active_universe").write_text("testverse", encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))
    monkeypatch.setattr(tinyassets_tray, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(tinyassets_tray, "LOG_DIR", tmp_path / "logs")
    spawned: list[dict[str, Any]] = []

    def fake_popen(cmd, **kwargs):
        spawned.append({"cmd": cmd, "kwargs": kwargs})
        return FakePopen()

    monkeypatch.setattr(tinyassets_tray.subprocess, "Popen", fake_popen)
    monkeypatch.setattr("builtins.open", lambda *_a, **_k: FakeLog())
    manager = tinyassets_tray.UniverseServerManager()
    manager._spawn_log = spawned
    yield manager
    preferences.reset_cache()


def test_tray_starts_exactly_one_credential_neutral_daemon(mgr) -> None:
    assert mgr.start_daemon() is True
    assert mgr.start_daemon() is False
    assert list(mgr.daemon_procs) == ["daemon"]


def test_spawn_has_no_provider_pin_and_strips_host_credentials(
    mgr, monkeypatch
) -> None:
    from tinyassets.providers.base import AMBIENT_PROVIDER_AUTH_ENV_VARS

    for name in AMBIENT_PROVIDER_AUTH_ENV_VARS:
        monkeypatch.setenv(name, f"host-{name.lower()}")
    assert mgr.start_daemon() is True
    record = mgr._spawn_log[-1]
    assert "--provider" not in record["cmd"]
    env = record["kwargs"]["env"]
    for name in AMBIENT_PROVIDER_AUTH_ENV_VARS:
        assert name not in env
    assert env["TINYASSETS_DAEMON_INSTANCE_KEY"] == "daemon"
    assert Path(env["TINYASSETS_DATA_DIR"]).is_absolute()


def test_spawn_uses_active_universe_inside_data_dir(mgr, tmp_path) -> None:
    assert mgr.start_daemon() is True
    cmd = mgr._spawn_log[-1]["cmd"]
    index = cmd.index("--universe")
    assert Path(cmd[index + 1]) == tmp_path / "data" / "testverse"


def test_kill_closes_daemon_log(mgr) -> None:
    mgr.start_daemon()
    _, log = mgr.daemon_procs["daemon"]
    mgr._kill_daemon()
    assert mgr.daemon_procs == {}
    assert log.closed


def test_check_health_reaps_dead_daemon(mgr) -> None:
    mgr.start_daemon()
    proc, log = mgr.daemon_procs["daemon"]
    proc.exit_with(1)
    mgr.check_health()
    assert mgr.daemon_procs == {}
    assert log.closed


def test_status_and_hover_describe_daemon_not_provider_fleet(mgr) -> None:
    mgr.start_daemon()
    assert "Daemon: Running" in mgr.status_text
    assert "testverse" in mgr.status_text
    assert "Daemon: Running" in mgr.hover_text
    assert "Providers:" not in mgr.status_text


def test_auto_start_is_one_boolean_not_provider_order(mgr) -> None:
    preferences.save_preferences({
        "default_providers": ["claude-code", "ollama-local"],
        "auto_start_default": True,
    })
    assert mgr._auto_start_daemon() is True
    preferences.save_preferences({
        "default_providers": ["claude-code"],
        "auto_start_default": False,
    })
    assert mgr._auto_start_daemon() is False


def test_active_universe_read_from_data_dir(mgr) -> None:
    assert mgr._active_universe == "testverse"


def test_universe_switch_reads_new_marker_from_data_dir(mgr, tmp_path) -> None:
    data_root = tmp_path / "data"
    (data_root / "otherverse").mkdir()
    (data_root / ".active_universe").write_text("otherverse", encoding="utf-8")
    assert mgr._check_universe_switch() is True
    assert mgr._active_universe == "otherverse"
