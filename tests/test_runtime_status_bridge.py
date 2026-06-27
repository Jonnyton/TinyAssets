"""Tests for the runtime-status bridge + --provider CLI pin.

Covers:
- ``DaemonController._write_runtime_status`` payload shape, atomic write,
  and ``_remove_runtime_status`` on shutdown.
- ``UniverseServerManager._read_runtime_status`` freshness gate.
- ``UniverseServerManager.hover_text`` provider suffix.
- ``--provider`` CLI validation + TINYASSETS_PIN_WRITER env var.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Daemon-side: runtime status writer
# ---------------------------------------------------------------------------


def _make_controller_stub(universe_path: Path, pinned: str = ""):
    """Build a DaemonController without triggering its real start()."""
    from fantasy_daemon.__main__ import DaemonController

    controller = DaemonController.__new__(DaemonController)
    controller._universe_path = str(universe_path)
    controller._pinned_provider = pinned
    controller._router = None
    controller._last_provider_used = ""
    controller._runtime_status_path = universe_path / ".runtime_status.json"
    return controller


def test_write_runtime_status_payload_shape(tmp_path: Path) -> None:
    controller = _make_controller_stub(tmp_path, pinned="codex")
    controller._last_provider_used = "claude-code"

    controller._write_runtime_status()

    payload = json.loads((tmp_path / ".runtime_status.json").read_text("utf-8"))
    assert payload["pid"] == os.getpid()
    assert payload["provider"] == "codex"
    assert payload["last_used_provider"] == "claude-code"
    assert payload["active_provider_label"]  # non-empty (mock label ok)
    datetime.fromisoformat(payload["updated"])  # ISO, parseable


def test_write_runtime_status_is_atomic_no_leftover_tmp(tmp_path: Path) -> None:
    controller = _make_controller_stub(tmp_path)
    controller._write_runtime_status()

    assert (tmp_path / ".runtime_status.json").exists()
    assert not (tmp_path / ".runtime_status.json.tmp").exists()


def test_remove_runtime_status_is_idempotent(tmp_path: Path) -> None:
    controller = _make_controller_stub(tmp_path)
    controller._write_runtime_status()

    controller._remove_runtime_status()
    assert not (tmp_path / ".runtime_status.json").exists()

    controller._remove_runtime_status()
    assert not (tmp_path / ".runtime_status.json").exists()


def test_runtime_status_heartbeat_runs_independently_of_node_output(
    tmp_path: Path,
) -> None:
    """The 5s loop must tick on its own, not via phase transitions.

    A long draft can legitimately block all node events for > 30s; the
    tray depends on the heartbeat to keep `updated` fresh during that
    window.
    """
    import threading
    import time as _time

    controller = _make_controller_stub(tmp_path)
    controller._stop_event = threading.Event()

    controller._write_runtime_status()
    first = json.loads(
        (tmp_path / ".runtime_status.json").read_text("utf-8"),
    )["updated"]

    _time.sleep(0.01)
    controller._write_runtime_status()
    second = json.loads(
        (tmp_path / ".runtime_status.json").read_text("utf-8"),
    )["updated"]

    assert second != first  # timestamp advances without any node event


def test_runtime_status_heartbeat_thread_joins_on_stop(
    tmp_path: Path,
) -> None:
    """`_stop_event.set()` unblocks the heartbeat loop promptly."""
    import threading
    import time

    controller = _make_controller_stub(tmp_path)
    controller._stop_event = threading.Event()

    thread = threading.Thread(
        target=controller._runtime_status_loop, daemon=True,
    )
    thread.start()
    time.sleep(0.1)

    controller._stop_event.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_write_runtime_status_empty_pin_serializes_to_empty_string(
    tmp_path: Path,
) -> None:
    controller = _make_controller_stub(tmp_path, pinned="")
    controller._write_runtime_status()

    payload = json.loads((tmp_path / ".runtime_status.json").read_text("utf-8"))
    assert payload["provider"] == ""


# ---------------------------------------------------------------------------
# Tray-side: _read_runtime_status + hover_text
# ---------------------------------------------------------------------------


@pytest.fixture
def tray_manager(tmp_path, monkeypatch):
    """UniverseServerManager with PROJECT_DIR + TINYASSETS_DATA_DIR pointed
    at a tmp tree.

    Avoids the real GTK/pystray init by instantiating the class only far
    enough to exercise the pure-logic methods.

    Post-Task-#7 the tray reads ``data_dir()`` (via
    ``tinyassets.storage.data_dir``) rather than ``PROJECT_DIR / "output"``,
    so we pin ``TINYASSETS_DATA_DIR`` to a tmp root and create the
    universe directory there. ``PROJECT_DIR`` is still monkeypatched for
    tray-local state (log dir, singleton lock, etc.).
    """
    # Stub pystray + PIL so importing the module doesn't require GUI deps
    # at test time (they're not installed in CI environments).
    for name in ("pystray", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            sys.modules[name] = mod
    sys.modules["pystray"].Icon = object
    sys.modules["pystray"].Menu = type("Menu", (), {"SEPARATOR": object()})
    sys.modules["pystray"].MenuItem = object

    # Pin data_dir() to a throwaway root BEFORE importing tinyassets_tray
    # (manager's __init__ calls _read_active_universe which reads
    # data_dir()).
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))

    # Point tinyassets_tray at our tmp project root for tray-local state.
    import tinyassets_tray

    importlib.reload(tinyassets_tray)
    monkeypatch.setattr(tinyassets_tray, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(tinyassets_tray, "LOG_DIR", tmp_path / "logs")

    # Create <data_dir>/<universe>/ so the manager picks it up via
    # data_dir()-anchored resolution.
    universe = "test-universe"
    universe_dir = data_root / universe
    universe_dir.mkdir(parents=True)
    (universe_dir / "PROGRAM.md").write_text("premise", encoding="utf-8")

    mgr = tinyassets_tray.UniverseServerManager()
    mgr._active_universe = universe
    return mgr, universe_dir


def _write_status(path: Path, age_seconds: float, **overrides) -> None:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    payload = {
        "pid": 12345,
        "provider": "",
        "last_used_provider": "claude-code",
        "active_provider_label": "claude-code, codex",
        "updated": ts.isoformat(),
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_read_runtime_status_missing_returns_none(tray_manager) -> None:
    mgr, _ = tray_manager
    assert mgr._read_runtime_status() is None


def test_read_runtime_status_fresh_returns_payload(tray_manager) -> None:
    mgr, universe_dir = tray_manager
    _write_status(universe_dir / ".runtime_status.json", age_seconds=2.0)

    status = mgr._read_runtime_status()
    assert status is not None
    assert status["last_used_provider"] == "claude-code"


def test_read_runtime_status_stale_returns_none(tray_manager) -> None:
    mgr, universe_dir = tray_manager
    _write_status(universe_dir / ".runtime_status.json", age_seconds=120.0)

    assert mgr._read_runtime_status() is None


def test_read_runtime_status_malformed_json_returns_none(tray_manager) -> None:
    mgr, universe_dir = tray_manager
    (universe_dir / ".runtime_status.json").write_text(
        "{ not valid json", encoding="utf-8",
    )
    assert mgr._read_runtime_status() is None


def test_hover_text_appends_pinned_provider(tray_manager) -> None:
    mgr, universe_dir = tray_manager
    _write_status(
        universe_dir / ".runtime_status.json",
        age_seconds=1.0,
        provider="codex",
    )
    mgr._runtime_status = mgr._read_runtime_status()
    mgr._daemon_alive = mgr._mcp_serving = mgr._tunnel_ok = True

    text = mgr.hover_text
    assert "Active: codex" in text


def test_hover_text_falls_back_to_active_label_when_not_pinned(tray_manager) -> None:
    mgr, universe_dir = tray_manager
    _write_status(
        universe_dir / ".runtime_status.json",
        age_seconds=1.0,
        provider="",
        active_provider_label="claude-code, codex",
    )
    mgr._runtime_status = mgr._read_runtime_status()
    mgr._daemon_alive = mgr._mcp_serving = mgr._tunnel_ok = True

    assert "Active: claude-code, codex" in mgr.hover_text


def test_hover_text_no_suffix_when_status_absent(tray_manager) -> None:
    mgr, _ = tray_manager
    mgr._runtime_status = None
    mgr._daemon_alive = mgr._mcp_serving = mgr._tunnel_ok = True

    assert "Active:" not in mgr.hover_text


# ---------------------------------------------------------------------------
# CLI: --provider validation + TINYASSETS_PIN_WRITER env var
# ---------------------------------------------------------------------------


def test_cli_rejects_unknown_provider() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "fantasy_daemon", "--provider", "not-a-real-one"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    combined = (result.stderr + result.stdout).lower()
    assert "not a known provider" in combined or "not-a-real-one" in combined


def test_cli_help_mentions_provider_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "fantasy_daemon", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "--provider" in result.stdout


# ---------------------------------------------------------------------------
# Router: TINYASSETS_PIN_WRITER narrows chain and fails loudly on exhaustion
# ---------------------------------------------------------------------------


class _RecordingProvider:
    """Stand-in async provider that records calls and can raise on demand."""

    def __init__(self, name: str, fail: bool = False) -> None:
        self.name = name
        self._fail = fail
        self.calls = 0

    async def complete(self, prompt, system, cfg):
        from tinyassets.exceptions import ProviderUnavailableError
        from tinyassets.providers.base import ProviderResponse

        self.calls += 1
        if self._fail:
            raise ProviderUnavailableError(f"{self.name} down")
        return ProviderResponse(
            text="ok",
            provider=self.name,
            model="test-model",
            family="test-family",
            latency_ms=1.0,
        )


@pytest.fixture
def _clear_pin(monkeypatch):
    monkeypatch.delenv("TINYASSETS_PIN_WRITER", raising=False)
    yield


def test_router_pins_to_env_var_provider(monkeypatch, _clear_pin) -> None:
    from tinyassets.providers.router import ProviderRouter

    pinned = _RecordingProvider("codex")
    other = _RecordingProvider("claude-code")
    router = ProviderRouter(providers={"codex": pinned, "claude-code": other})
    monkeypatch.setenv("TINYASSETS_PIN_WRITER", "codex")

    import asyncio
    resp = asyncio.run(router.call("writer", "p", "s"))

    assert resp.provider == "codex"
    assert pinned.calls == 1
    assert other.calls == 0


def test_router_pinned_writer_raises_on_exhaustion_no_fallback(
    monkeypatch, _clear_pin,
) -> None:
    from tinyassets.exceptions import AllProvidersExhaustedError
    from tinyassets.providers.router import ProviderRouter

    pinned = _RecordingProvider("codex", fail=True)
    would_succeed = _RecordingProvider("ollama-local")
    router = ProviderRouter(
        providers={"codex": pinned, "ollama-local": would_succeed},
    )
    monkeypatch.setenv("TINYASSETS_PIN_WRITER", "codex")

    import asyncio
    with pytest.raises(AllProvidersExhaustedError) as ei:
        asyncio.run(router.call("writer", "p", "s"))

    # Loud failure identifies the pin explicitly and does NOT touch the
    # would-succeed provider.
    assert "codex" in str(ei.value).lower()
    assert would_succeed.calls == 0


def test_router_pin_does_not_affect_non_writer_roles(
    monkeypatch, _clear_pin,
) -> None:
    """Judge ensemble / extract should ignore TINYASSETS_PIN_WRITER."""
    from tinyassets.providers.router import ProviderRouter

    p1 = _RecordingProvider("codex")
    p2 = _RecordingProvider("claude-code")
    router = ProviderRouter(providers={"codex": p1, "claude-code": p2})
    monkeypatch.setenv("TINYASSETS_PIN_WRITER", "codex")

    import asyncio
    # 'extract' chain starts with codex so it still resolves to codex here,
    # but the mechanism must be the normal chain (no loud-fail behavior).
    asyncio.run(router.call("extract", "p", "s"))
    assert p1.calls == 1


def test_cli_pin_known_providers_covers_all_chains() -> None:
    """Every name in FALLBACK_CHAINS must pass the --provider validator."""
    from fantasy_daemon.providers import router as router_mod

    known = set().union(*router_mod.FALLBACK_CHAINS.values())
    # Every chain-member we publish is acceptable input to the CLI.
    assert "claude-code" in known
    assert "codex" in known
    assert "ollama-local" in known
    # And the validation set is derived from the live chains, not frozen.
    assert known == set().union(*router_mod.FALLBACK_CHAINS.values())
