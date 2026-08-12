"""Tests for tinyassets_tray.UniverseServerManager multi-provider lifecycle.

Exercises the parts of the tray that don't depend on pystray event loops:
constraint enforcement, lifecycle bookkeeping, auto-start ordering,
hover/status rendering, and log-handle teardown.

Real subprocess spawning is replaced with a stub Popen so these tests
stay hermetic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# tinyassets_tray imports PIL + pystray at module load. Skip if unavailable.
pystray = pytest.importorskip("pystray")  # noqa: F841
PIL = pytest.importorskip("PIL")  # noqa: F841

import tinyassets_tray  # noqa: E402
from tinyassets import preferences  # noqa: E402


class FakePopen:
    """Minimal Popen stand-in: `poll()` returns None until `terminate()`."""

    def __init__(self) -> None:
        self._returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self.terminated = True
        self._returncode = 0

    def kill(self) -> None:
        self.killed = True
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

    def write(self, _s: str) -> None:
        pass

    def flush(self) -> None:
        pass


@pytest.fixture
def mgr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Return a UniverseServerManager wired to tmp_path, no real spawns."""
    # Isolate preferences.
    prefs_path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_PREFS_PATH", prefs_path)
    preferences.reset_cache()

    # Pin data_dir() to tmp so marker + universe dirs live under a
    # throwaway root. Post-Task-#7 the tray reads ``data_dir()`` rather
    # than ``PROJECT_DIR / "output"`` — we set TINYASSETS_DATA_DIR so the
    # tray's internal ``_data_dir()`` resolves into tmp.
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "testverse").mkdir()
    (data_root / ".active_universe").write_text("testverse", encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))

    # Still redirect PROJECT_DIR + LOG_DIR to tmp for tray-local state
    # (singleton lock, log files, script lookup) that is intentionally
    # install-anchored, not data-anchored.
    monkeypatch.setattr(tinyassets_tray, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(tinyassets_tray, "LOG_DIR", tmp_path / "logs")

    # Patch spawn machinery so nothing real boots.
    spawned: list[dict[str, Any]] = []

    def fake_popen(cmd, **kwargs):
        spawned.append({"cmd": cmd, "kwargs": kwargs})
        return FakePopen()

    def fake_open(path, *_args, **_kwargs):
        return FakeLog()

    monkeypatch.setattr(tinyassets_tray.subprocess, "Popen", fake_popen)
    # Replace the global `open` tinyassets_tray uses for log handles.
    monkeypatch.setattr("builtins.open", fake_open, raising=False)

    m = tinyassets_tray.UniverseServerManager()
    m._spawn_log = spawned  # test-visible handle
    yield m
    preferences.reset_cache()


# ---------------------------------------------------------------------------
# Constraint enforcement
# ---------------------------------------------------------------------------


def test_start_accepts_arbitrary_provider_name(mgr: tinyassets_tray.UniverseServerManager) -> None:
    # The provider arg is a vestigial preference surface; the credential-neutral
    # tray no longer validates it. Any name spawns the one shared daemon.
    assert mgr.start_daemon_for("bogus-provider") is True
    assert list(mgr.daemon_procs.keys()) == ["daemon"]


def test_start_refuses_second_daemon(mgr) -> None:
    assert mgr.start_daemon_for("claude-code") is True
    # Credential-neutral model: exactly one daemon at a time. A second start is
    # refused while the first is alive (no per-provider multi-daemon fan-out).
    assert mgr.start_daemon_for("claude-code") is False
    assert list(mgr.daemon_procs.keys()) == ["daemon"]
    assert mgr._running_providers() == ["daemon"]


def test_start_refuses_second_daemon_regardless_of_provider(mgr) -> None:
    # The old local/subscription distinction is gone (no _LOCAL_PROVIDER_SET /
    # ALL_PROVIDERS): the single-daemon rule applies to any provider name.
    assert mgr.start_daemon_for("ollama-local") is True
    assert mgr.start_daemon_for("fake-local") is False
    assert list(mgr.daemon_procs.keys()) == ["daemon"]


def test_start_runs_one_daemon_across_provider_classes(mgr) -> None:
    # Previously a subscription daemon could run alongside a local one; the
    # credential-neutral model runs exactly one daemon, whichever starts first.
    assert mgr.start_daemon_for("ollama-local") is True
    assert mgr.start_daemon_for("claude-code") is False
    assert set(mgr.daemon_procs.keys()) == {"daemon"}


# ---------------------------------------------------------------------------
# Lifecycle + FD hygiene
# ---------------------------------------------------------------------------


def test_kill_closes_log_handle(mgr) -> None:
    mgr.start_daemon_for("codex")
    # The daemon is keyed credential-neutrally as "daemon", not by provider.
    _, log = mgr.daemon_procs["daemon"]
    assert not log.closed

    mgr._kill_daemon_for("daemon")
    assert "daemon" not in mgr.daemon_procs
    assert log.closed


def test_kill_daemon_closes_log_handle(mgr) -> None:
    assert mgr.start_daemon_for("claude-code") is True
    # A second same-provider start is refused, so only one handle exists.
    assert mgr.start_daemon_for("claude-code") is False
    handles = [log for _, log in mgr.daemon_procs.values()]

    mgr._kill_daemon_for("daemon")

    assert mgr.daemon_procs == {}
    assert all(log.closed for log in handles)


def test_kill_all_daemons_closes_every_log(mgr) -> None:
    mgr.start_daemon_for("claude-code")
    mgr.start_daemon_for("codex")
    mgr.start_daemon_for("ollama-local")
    handles = [log for _, log in mgr.daemon_procs.values()]

    mgr._kill_all_daemons()
    assert mgr.daemon_procs == {}
    assert all(log.closed for log in handles)


def test_check_health_reaps_dead_daemons(mgr) -> None:
    mgr.start_daemon_for("codex")
    proc, log = mgr.daemon_procs["daemon"]
    proc.exit_with(1)  # simulate crash

    mgr.check_health()
    assert "daemon" not in mgr.daemon_procs
    assert log.closed


# ---------------------------------------------------------------------------
# Running-providers + hover text
# ---------------------------------------------------------------------------


def test_running_providers_filters_dead(mgr) -> None:
    mgr.start_daemon_for("codex")
    # Mark the single credential-neutral daemon dead without reaping.
    mgr.daemon_procs["daemon"][0].exit_with(0)

    running = mgr._running_providers()
    assert running == []


def test_hover_text_shows_active_daemon(mgr) -> None:
    mgr.start_daemon_for("claude-code")
    hover = mgr.hover_text
    assert "Active:" in hover
    # The active label is the credential-neutral daemon, not a provider name.
    assert "daemon" in hover


def test_hover_text_no_suffix_when_idle(mgr) -> None:
    hover = mgr.hover_text
    assert "Active:" not in hover


def test_status_text_lists_active_daemon(mgr) -> None:
    mgr.start_daemon_for("codex")
    assert "daemon" in mgr.status_text
    assert "testverse" in mgr.status_text


# ---------------------------------------------------------------------------
# Auto-start ordering
# ---------------------------------------------------------------------------


def test_auto_start_reads_preferences(mgr) -> None:
    preferences.save_preferences({
        "default_providers": ["claude-code", "ollama-local"],
        "auto_start_default": True,
    })
    # Auto-start now yields exactly one credential-neutral daemon, independent
    # of the (now vestigial) default_providers list.
    assert mgr._auto_start_providers() == ["daemon"]


def test_auto_start_respects_disabled_flag(mgr) -> None:
    preferences.save_preferences({
        "default_providers": ["claude-code"],
        "auto_start_default": False,
    })
    assert mgr._auto_start_providers() == []


def test_auto_start_ignores_default_providers_list(mgr) -> None:
    preferences.save_preferences({
        "default_providers": ["claude-code", "not-a-provider"],
        "auto_start_default": True,
    })
    # The default_providers list (bogus names included) no longer shapes
    # auto-start; the single credential-neutral daemon is returned regardless.
    assert mgr._auto_start_providers() == ["daemon"]


# ---------------------------------------------------------------------------
# Spawn command shape
# ---------------------------------------------------------------------------


def test_spawn_is_credential_neutral_and_strips_ambient_creds(mgr) -> None:
    mgr.start_daemon_for("claude-code")
    record = mgr._spawn_log[-1]
    # The provider arg is a vestigial preference surface — it is NOT passed to
    # the child and no writer pin is set. The daemon resolves the universe's
    # assigned serving credential at runtime.
    assert "--provider" not in record["cmd"]
    env = record["kwargs"]["env"]
    # Ambient credential env is stripped so nothing pins a provider/identity.
    for stripped in (
        "TINYASSETS_PIN_WRITER",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        assert stripped not in env
    assert env["TINYASSETS_DAEMON_INSTANCE_KEY"] == "daemon"
    # Task #7: daemon child must inherit the tray's data_dir() as an
    # absolute TINYASSETS_DATA_DIR, not a CWD-relative path. Previously
    # the tray set TINYASSETS_DATA_DIR="output" which drifted whenever
    # tray CWD != data_dir().
    assert "TINYASSETS_DATA_DIR" in env
    assert Path(env["TINYASSETS_DATA_DIR"]).is_absolute()
    assert env.get("TINYASSETS_DATA_DIR", None) != "output", (
        "CWD-relative literal must not leak to child"
    )


def test_spawn_writes_credential_neutral_log_name(mgr, monkeypatch) -> None:
    opened: list[Path] = []
    real_open = open

    def tracking_open(path, *args, **kwargs):
        opened.append(Path(path))
        return FakeLog()

    monkeypatch.setattr("builtins.open", tracking_open, raising=False)
    mgr.start_daemon_for("grok-free")
    # One credential-neutral daemon → one fixed log name, not per-provider.
    assert any(p.name == "daemon.daemon.log" for p in opened)
    # Restore not strictly needed; pytest unwinds monkeypatch at test end.
    _ = real_open


def test_second_daemon_spawn_is_refused(mgr, monkeypatch) -> None:
    opened: list[Path] = []

    def tracking_open(path, *args, **kwargs):
        opened.append(Path(path))
        return FakeLog()

    monkeypatch.setattr("builtins.open", tracking_open, raising=False)
    assert mgr.start_daemon_for("claude-code") is True
    # One daemon at a time: the second start is refused before any log opens,
    # so only the single credential-neutral log file is created.
    assert mgr.start_daemon_for("claude-code") is False

    assert [p.name for p in opened] == ["daemon.daemon.log"]


# ---------------------------------------------------------------------------
# Task #7 — data_dir()-anchored active-universe marker (tray-side)
# ---------------------------------------------------------------------------


def test_active_universe_read_from_data_dir(mgr, tmp_path) -> None:
    """Marker is read from data_dir()/.active_universe, not PROJECT_DIR."""
    # Fixture already seeded data_dir/.active_universe="testverse".
    # The manager picked it up on construction.
    assert mgr._active_universe == "testverse"


def test_active_universe_falls_back_to_enumeration_in_data_dir(
    tmp_path, monkeypatch,
) -> None:
    """No marker -> enumerate data_dir for a PROGRAM.md universe."""
    prefs_path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_PREFS_PATH", prefs_path)
    preferences.reset_cache()

    data_root = tmp_path / "data"
    data_root.mkdir()
    # Two universes, one with PROGRAM.md — that one should win.
    (data_root / "empty-verse").mkdir()
    premise_verse = data_root / "premise-verse"
    premise_verse.mkdir()
    (premise_verse / "PROGRAM.md").write_text("hello", encoding="utf-8")
    # No .active_universe marker on purpose.

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))
    monkeypatch.setattr(tinyassets_tray, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(tinyassets_tray, "LOG_DIR", tmp_path / "logs")

    monkeypatch.setattr(tinyassets_tray.subprocess, "Popen",
                        lambda *_a, **_k: FakePopen())
    monkeypatch.setattr("builtins.open",
                        lambda *_a, **_k: FakeLog(), raising=False)

    m = tinyassets_tray.UniverseServerManager()
    assert m._active_universe == "premise-verse"


def test_spawn_passes_data_dir_scoped_universe_path(mgr, tmp_path) -> None:
    """Child daemon's --universe arg points inside data_dir(), not
    PROJECT_DIR/output.
    """
    mgr.start_daemon_for("codex")
    record = mgr._spawn_log[-1]
    cmd = record["cmd"]
    assert "--universe" in cmd
    flag_idx = cmd.index("--universe")
    universe_arg = Path(cmd[flag_idx + 1])
    data_root = tmp_path / "data"
    assert universe_arg == data_root / "testverse"


def test_universe_switch_reads_new_marker_from_data_dir(mgr, tmp_path) -> None:
    """Writing a fresh marker into data_dir flips the active universe."""
    data_root = tmp_path / "data"
    # Create a second universe and update the marker.
    (data_root / "otherverse").mkdir()
    (data_root / ".active_universe").write_text("otherverse", encoding="utf-8")

    switched = mgr._check_universe_switch()
    assert switched is True
    assert mgr._active_universe == "otherverse"
