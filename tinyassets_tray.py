"""TinyAssets Server system tray launcher.

Double-click the desktop shortcut -> this script starts:
  1. One daemon per preferred provider (Author Daemons, LangGraph writing
     engines) with the writer role pinned via ``--provider <name>``
  2. MCP TinyAssets Server (Python, port 8001)
  3. Optional local Cloudflare Tunnel for dev-only debugging

A system tray icon shows live status. Hover aggregates active providers.
Right-click to start/stop per-provider daemons, change defaults, or quit.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import IO
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont
from pystray import Icon, Menu, MenuItem

from tinyassets.preferences import (
    ALL_PROVIDERS,
    LOCAL_PROVIDERS,
    load_preferences,
    save_preferences,
)
from tinyassets.singleton_lock import (
    acquire_singleton_lock,
    release_singleton_lock,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MCP_PORT = 8001
MCP_URL = "https://tinyassets.io/mcp"
ACTIVE_UNIVERSE_FILENAME = ".active_universe"
TRAY_TUNNEL_ENABLED_ENV = "TINYASSETS_TRAY_ENABLE_TUNNEL"
TUNNEL_TOKEN_ENV = "CLOUDFLARE_TUNNEL_TOKEN"
LEGACY_TUNNEL_TOKEN_ENV = "TUNNEL_TOKEN"
TRUE_VALUES = {"1", "true", "yes", "on"}

PROJECT_DIR = Path(__file__).resolve().parent
LOG_DIR = PROJECT_DIR / "logs"
SINGLETON_LOCK_PATH = LOG_DIR / ".tray.lock"

_LOCAL_PROVIDER_SET = set(LOCAL_PROVIDERS)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUE_VALUES


def _local_tunnel_enabled() -> bool:
    return _env_truthy(TRAY_TUNNEL_ENABLED_ENV)


def _local_tunnel_token() -> str:
    return (
        os.environ.get(TUNNEL_TOKEN_ENV, "").strip()
        or os.environ.get(LEGACY_TUNNEL_TOKEN_ENV, "").strip()
    )

# ---------------------------------------------------------------------------
# Icon rendering
# ---------------------------------------------------------------------------

GREEN  = (76, 175, 80)    # all healthy
YELLOW = (255, 193, 7)    # partial
RED    = (244, 67, 54)    # down
GRAY   = (158, 158, 158)  # starting


def make_icon(color: tuple, size: int = 64) -> Image.Image:
    """Draw a simple circle icon with 'U' in the center."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
    )
    try:
        font = ImageFont.truetype("arial.ttf", size // 2)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "U", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2, (size - th) / 2 - 2),
        "U",
        fill=(255, 255, 255),
        font=font,
    )
    return img


# ---------------------------------------------------------------------------
# Process manager
# ---------------------------------------------------------------------------

class UniverseServerManager:
    """Manages daemons, local MCP, optional dev tunnel, and tab watchdog."""

    def __init__(self) -> None:
        # One entry per daemon process. The first process for a provider uses
        # the provider name as key; later same-provider processes use
        # provider#N. Value is (Popen, log_handle) so the log handle can be
        # closed on teardown (FD-leak guard).
        self.daemon_procs: dict[str, tuple[subprocess.Popen, IO]] = {}
        self.mcp_proc: subprocess.Popen | None = None
        self.tunnel_proc: subprocess.Popen | None = None
        # Tab watchdog: continuous single-tab enforcement on the
        # user-sim Chrome. Auto-started alongside MCP + tunnel so tabs
        # can't accumulate while the host is idle.
        self.watchdog_proc: subprocess.Popen | None = None
        self._icon: Icon | None = None
        self._stop_event = threading.Event()
        self._procs_lock = threading.Lock()

        # Granular startup tracking
        self._phase = "Initializing..."
        self._mcp_alive = False
        self._mcp_serving = False
        self._tunnel_alive = False
        self._tunnel_ok = False
        self._watchdog_alive = False

        # Active universe tracking
        self._active_universe = self._read_active_universe()
        self._ensure_active_universe_file()

        # Runtime-status bridge from the daemon (provider visibility).
        # Single file per-universe today (Task A); when multiple daemons
        # write the same file they race, so we rely on daemon_procs keys
        # as the authoritative "who's running" signal and only use this
        # payload for best-effort "last active provider" detail.
        self._runtime_status: dict | None = None
        self._RUNTIME_STATUS_FRESHNESS_SEC = 30.0

    # -- Universe selection ---------------------------------------------

    def _data_dir(self) -> Path:
        """Canonical on-disk root for universes + marker.

        Delegates to ``tinyassets.storage.data_dir`` so tray and daemon
        resolve the same path. Pre-2026-04-20 the tray used
        ``PROJECT_DIR / "output"`` (CWD-relative), which drifted from
        the daemon's ``data_dir()`` result whenever tray was launched
        from a CWD other than the resolved data root — the
        ``.active_universe`` marker would split between two locations
        and universe switching silently broke.
        """
        from tinyassets.storage import data_dir
        return data_dir()

    def _read_active_universe(self) -> str:
        base = self._data_dir()
        marker = base / ACTIVE_UNIVERSE_FILENAME
        if marker.exists():
            uid = marker.read_text(encoding="utf-8").strip()
            if uid and (base / uid).is_dir():
                return uid

        if base.is_dir():
            for child in sorted(base.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    if (child / "PROGRAM.md").exists():
                        return child.name
            for child in sorted(base.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    return child.name
        return "default-universe"

    def _ensure_active_universe_file(self) -> None:
        marker = self._data_dir() / ACTIVE_UNIVERSE_FILENAME
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(self._active_universe, encoding="utf-8")

    def _check_universe_switch(self) -> bool:
        base = self._data_dir()
        marker = base / ACTIVE_UNIVERSE_FILENAME
        if not marker.exists():
            return False
        uid = marker.read_text(encoding="utf-8").strip()
        if uid and uid != self._active_universe and (base / uid).is_dir():
            self._active_universe = uid
            return True
        return False

    def _read_runtime_status(self) -> dict | None:
        path = self._data_dir() / self._active_universe / ".runtime_status.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        updated = payload.get("updated", "")
        try:
            ts = datetime.fromisoformat(updated)
        except ValueError:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > self._RUNTIME_STATUS_FRESHNESS_SEC:
            return None
        return payload

    # -- Status ----------------------------------------------------------

    def _running_providers(self) -> list[str]:
        """Return provider names whose daemon subprocess is still alive."""
        with self._procs_lock:
            return [
                self._provider_for_daemon_key(name)
                for name, (proc, _) in self.daemon_procs.items()
                if proc.poll() is None
            ]

    @staticmethod
    def _provider_for_daemon_key(key: str) -> str:
        return key.split("#", 1)[0]

    def _running_provider_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for provider in self._running_providers():
            counts[provider] = counts.get(provider, 0) + 1
        return counts

    def _next_daemon_key(self, provider: str) -> str:
        ordinal = self._running_provider_counts().get(provider, 0) + 1
        key = provider if ordinal == 1 else f"{provider}#{ordinal}"
        with self._procs_lock:
            while key in self.daemon_procs:
                ordinal += 1
                key = f"{provider}#{ordinal}"
        return key

    @property
    def _any_daemon_alive(self) -> bool:
        return bool(self._running_providers())

    @property
    def status_text(self) -> str:
        parts = []
        running = self._running_providers()
        if running:
            parts.append(
                f"Daemons: {', '.join(running)} ({self._active_universe})"
            )
        else:
            parts.append(f"Daemons: None ({self._active_universe})")
        if self._mcp_serving:
            parts.append("MCP: Serving")
        elif self._mcp_alive:
            parts.append("MCP: Loading")
        else:
            parts.append("MCP: Down")
        if self._tunnel_ok:
            parts.append("Tunnel: Connected")
        elif self._tunnel_alive:
            parts.append("Tunnel: Connecting")
        else:
            parts.append("Tunnel: Down")
        if self._watchdog_alive:
            parts.append("Tab watchdog: Running")
        else:
            parts.append("Tab watchdog: Stopped")
        return " | ".join(parts)

    @property
    def hover_text(self) -> str:
        running = self._running_providers()
        if running and self._mcp_serving and self._tunnel_ok:
            base = "TinyAssets Server - Live at tinyassets.io/mcp"
        else:
            base = f"TinyAssets Server - {self._phase}"
        if running:
            return f"{base} | Active: {', '.join(running)}"
        # Fallback: if nothing in daemon_procs but a fresh runtime_status
        # file exists (e.g., daemon was spawned outside the tray), surface
        # whatever the daemon reports so the tray isn't misleadingly silent.
        suffix = self._runtime_status_suffix()
        return f"{base} | Active: {suffix}" if suffix else base

    def _runtime_status_suffix(self) -> str:
        status = self._runtime_status
        if not status:
            return ""
        pinned = (status.get("provider") or "").strip()
        if pinned:
            return pinned
        return (status.get("active_provider_label") or "").strip()

    @property
    def icon_color(self) -> tuple:
        running = bool(self._running_providers())
        if running and self._mcp_serving and self._tunnel_ok:
            return GREEN
        elif running or self._mcp_alive or self._tunnel_alive:
            return YELLOW
        elif self._stop_event.is_set():
            return RED
        else:
            return GRAY

    # -- Process lifecycle -----------------------------------------------

    def _can_start(self, provider: str) -> tuple[bool, str]:
        """Check constraint rules before spawning a daemon for *provider*.

        Returns ``(ok, reason)``. ``ok`` is False for unknown providers or
        when another local provider is already running. Subscription providers
        may run multiple same-provider daemons; the tray warns separately.
        """
        if provider not in ALL_PROVIDERS:
            return False, f"unknown provider {provider!r}"
        running = self._running_providers()
        if provider in _LOCAL_PROVIDER_SET:
            other_local = [p for p in running if p in _LOCAL_PROVIDER_SET]
            if other_local:
                return False, (
                    f"local provider {other_local[0]} already running; "
                    "only one local daemon at a time"
                )
        return True, ""

    def start_daemon_for(self, provider: str) -> bool:
        """Launch a daemon pinned to *provider*. Returns True on spawn."""
        ok, reason = self._can_start(provider)
        if not ok:
            print(f"  [skip] {provider}: {reason}")
            return False

        LOG_DIR.mkdir(exist_ok=True)
        runtime_key = self._next_daemon_key(provider)
        try:
            from tinyassets.daemon_registry import provider_capacity_warning

            warning = provider_capacity_warning(
                provider,
                running_count=self._running_provider_counts().get(provider, 0),
            )
            if warning:
                print(f"  [warn] {warning['message']}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] capacity warning unavailable for {provider}: {exc}")

        log_name = runtime_key.replace("#", ".")
        log_path = LOG_DIR / f"daemon.{log_name}.log"
        log = open(log_path, "a", encoding="utf-8")
        log.write(
            f"\n--- Daemon ({runtime_key}) start {time.strftime('%H:%M:%S')} ---\n"
        )
        log.flush()

        universe_path = self._data_dir() / self._active_universe
        env = os.environ.copy()
        # Belt and suspenders: --provider is consumed by argparse and sets
        # TINYASSETS_PIN_WRITER itself, but setting it in the env too means
        # the router pin survives even if the flag parsing changes.
        env["TINYASSETS_PIN_WRITER"] = provider
        env["TINYASSETS_DAEMON_INSTANCE_KEY"] = runtime_key
        # Pin the data root so child's data_dir() resolves to the same
        # absolute path the tray picked. Prevents CWD drift between tray
        # and daemon when they launch from different working directories.
        env["TINYASSETS_DATA_DIR"] = str(self._data_dir())

        try:
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "fantasy_author",
                    "--universe", str(universe_path),
                    "--provider", provider,
                    "--no-tray",
                ],
                cwd=str(PROJECT_DIR),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            log.close()
            raise

        with self._procs_lock:
            self.daemon_procs[runtime_key] = (proc, log)
        return True

    def start_mcp(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        env = os.environ.copy()
        # Pin the canonical data root as an absolute path so the MCP
        # subprocess's data_dir() resolves identically no matter what
        # CWD it inherits. Previously the tray used a CWD-relative
        # "output" string for the daemon data root, which made the tray
        # and MCP server drift onto different
        # on-disk trees whenever the tray wasn't launched from the repo
        # root (Task #7 / 2026-04-20 observability bug).
        env["TINYASSETS_DATA_DIR"] = str(self._data_dir())

        log = open(LOG_DIR / "mcp_server.log", "a", encoding="utf-8")
        log.write(f"\n--- MCP start {time.strftime('%H:%M:%S')} ---\n")
        log.flush()

        self.mcp_proc = subprocess.Popen(
            [
                sys.executable, "-c",
                "from tinyassets.universe_server import mcp; "
                f"mcp.run(transport='streamable-http', host='0.0.0.0', port={MCP_PORT})"
            ],
            cwd=str(PROJECT_DIR),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def start_tunnel(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)

        log = open(LOG_DIR / "tunnel.log", "a", encoding="utf-8")
        log.write(f"\n--- Tunnel start {time.strftime('%H:%M:%S')} ---\n")
        log.flush()

        if not _local_tunnel_enabled():
            self.tunnel_proc = None
            self._tunnel_alive = False
            self._tunnel_ok = False
            log.write(
                "local tunnel disabled by default; set "
                f"{TRAY_TUNNEL_ENABLED_ENV}=1 and {TUNNEL_TOKEN_ENV} for "
                "dev-only tunnel debugging\n"
            )
            log.close()
            return

        token = _local_tunnel_token()
        if not token:
            log.close()
            raise RuntimeError(
                f"{TRAY_TUNNEL_ENABLED_ENV}=1 requires {TUNNEL_TOKEN_ENV}"
            )

        self.tunnel_proc = subprocess.Popen(
            ["cloudflared", "tunnel", "run", "--token", token],
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def start_watchdog(self) -> None:
        """Launch the tab-hygiene watchdog as a background process.

        The watchdog polls the CDP endpoint every 3s and enforces the
        single-tab forever rule on the user-sim Chrome. Runs without a
        console window (pythonw on Windows, regular python elsewhere).
        If `scripts/tab_watchdog.py` is missing (partial checkout),
        skip silently — same defensive shape as the mojibake pre-commit
        hook's script-existence check.
        """
        LOG_DIR.mkdir(exist_ok=True)
        watchdog_script = PROJECT_DIR / "scripts" / "tab_watchdog.py"
        if not watchdog_script.is_file():
            # Partial checkout or upstream refactor — skip-with-warning,
            # tray still starts.
            self._phase = "Tab watchdog: script missing; skipping"
            return

        log = open(LOG_DIR / "tab_watchdog.log", "a", encoding="utf-8")
        log.write(f"\n--- Watchdog start {time.strftime('%H:%M:%S')} ---\n")
        log.flush()

        # Prefer pythonw.exe on Windows so no console flash. Falls back
        # to the current interpreter elsewhere.
        python_bin = sys.executable
        if sys.platform == "win32":
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            if pythonw.is_file():
                python_bin = str(pythonw)

        self.watchdog_proc = subprocess.Popen(
            [python_bin, str(watchdog_script)],
            cwd=str(PROJECT_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def check_health(self) -> None:
        """Poll subprocess liveness + actual HTTP readiness."""
        self._runtime_status = self._read_runtime_status()

        # Reap any daemons whose Popen has exited; close their log handles.
        with self._procs_lock:
            dead = [
                name for name, (proc, _) in self.daemon_procs.items()
                if proc.poll() is not None
            ]
            for name in dead:
                _, log = self.daemon_procs.pop(name)
                try:
                    log.close()
                except Exception:
                    pass
                if not self._stop_event.is_set():
                    self._phase = f"Daemon {name} exited"

        self._mcp_alive = (
            self.mcp_proc is not None and self.mcp_proc.poll() is None
        )
        self._tunnel_alive = (
            self.tunnel_proc is not None and self.tunnel_proc.poll() is None
        )
        self._watchdog_alive = (
            self.watchdog_proc is not None
            and self.watchdog_proc.poll() is None
        )

        if self._mcp_alive and not self._mcp_serving:
            self._phase = "MCP server started, waiting for HTTP ready..."
            self._mcp_serving = self._probe_url(
                f"http://localhost:{MCP_PORT}/mcp", timeout=3
            )
            if self._mcp_serving:
                self._phase = "MCP server ready"
        elif not self._mcp_alive:
            self._mcp_serving = False

        if self._mcp_serving and self._tunnel_alive and not self._tunnel_ok:
            self._phase = "Verifying public endpoint..."
            self._tunnel_ok = self._probe_url(MCP_URL, timeout=5)
            if self._tunnel_ok:
                if self._any_daemon_alive:
                    self._phase = "Live"
                else:
                    self._phase = "MCP live, no daemons"
        elif not self._tunnel_alive:
            self._tunnel_ok = False

        if self._any_daemon_alive and self._mcp_serving and self._tunnel_ok:
            self._phase = "Live"
        elif (
            not self._any_daemon_alive
            and not self._mcp_alive
            and not self._tunnel_alive
            and not self._stop_event.is_set()
        ):
            self._phase = "All processes down"

    @staticmethod
    def _probe_url(url: str, timeout: int = 3) -> bool:
        try:
            resp = urlopen(url, timeout=timeout)  # noqa: S310
            resp.close()
            return True
        except URLError as e:
            if hasattr(e, "code"):
                return True
            return False
        except Exception:
            return False

    def _kill_daemon_for(self, provider: str) -> None:
        """Terminate the daemon pinned to *provider* and close its log."""
        with self._procs_lock:
            keys = [
                key for key in self.daemon_procs
                if self._provider_for_daemon_key(key) == provider
            ]
            entries = [self.daemon_procs.pop(key) for key in keys]
        for proc, log in entries:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            finally:
                try:
                    log.close()
                except Exception:
                    pass

    def _kill_all_daemons(self) -> None:
        providers = {
            self._provider_for_daemon_key(key)
            for key in list(self.daemon_procs.keys())
        }
        for provider in providers:
            self._kill_daemon_for(provider)

    def kill_all(self) -> None:
        """Terminate all processes."""
        self._kill_all_daemons()
        for proc in (self.mcp_proc, self.tunnel_proc, self.watchdog_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self.mcp_proc = None
        self.tunnel_proc = None
        self.watchdog_proc = None
        self._mcp_alive = False
        self._mcp_serving = False
        self._tunnel_alive = False
        self._tunnel_ok = False
        self._watchdog_alive = False

    # -- Auto-start -----------------------------------------------------

    def _auto_start_providers(self) -> list[str]:
        """Return providers to auto-start, locals first to respect constraint."""
        prefs = load_preferences()
        if not prefs.get("auto_start_default", True):
            return []
        configured = [
            p for p in prefs.get("default_providers", [])
            if p in ALL_PROVIDERS
        ]
        # Start local providers first so the "only one local" rule doesn't
        # silently drop ollama-local when a subscription provider sits
        # earlier in the list.
        locals_first = [p for p in configured if p in _LOCAL_PROVIDER_SET]
        subs = [p for p in configured if p not in _LOCAL_PROVIDER_SET]
        return locals_first + subs

    # -- Tray menu ------------------------------------------------------

    def _make_provider_toggle(self, provider: str):
        """Return a click handler that starts or stops *provider*."""
        def _handler(icon=None, item=None) -> None:
            if provider in self._running_providers():
                self._phase = f"Stopping {provider}..."
                self._kill_daemon_for(provider)
            else:
                self._phase = f"Starting {provider}..."
                self.start_daemon_for(provider)
        return _handler

    def _is_running_checker(self, provider: str):
        def _check(item) -> bool:
            return provider in self._running_providers()
        return _check

    def _set_default_provider(self, provider: str):
        def _handler(icon=None, item=None) -> None:
            prefs = load_preferences()
            # Singular default for the radio; keep list schema so future
            # multi-default UI can extend without a migration.
            save_preferences({
                "default_providers": [provider],
                "auto_start_default": prefs.get("auto_start_default", True),
            })
        return _handler

    def _is_default_provider(self, provider: str):
        def _check(item) -> bool:
            prefs = load_preferences()
            defaults = prefs.get("default_providers", [])
            return bool(defaults) and defaults[0] == provider
        return _check

    def _toggle_auto_start(self, icon=None, item=None) -> None:
        prefs = load_preferences()
        save_preferences({
            "default_providers": prefs.get("default_providers", []),
            "auto_start_default": not prefs.get("auto_start_default", True),
        })

    def _is_auto_start_on(self, item) -> bool:
        return bool(load_preferences().get("auto_start_default", True))

    def _build_menu(self) -> Menu:
        provider_items = [
            MenuItem(
                provider,
                self._make_provider_toggle(provider),
                checked=self._is_running_checker(provider),
            )
            for provider in ALL_PROVIDERS
        ]
        default_items = [
            MenuItem(
                provider,
                self._set_default_provider(provider),
                checked=self._is_default_provider(provider),
                radio=True,
            )
            for provider in ALL_PROVIDERS
        ]

        return Menu(
            MenuItem(
                lambda _: self.status_text,
                action=None,
                enabled=False,
            ),
            Menu.SEPARATOR,
            MenuItem("Providers", Menu(*provider_items)),
            MenuItem("Set default provider", Menu(*default_items)),
            MenuItem(
                "Auto-start default",
                self._toggle_auto_start,
                checked=self._is_auto_start_on,
            ),
            Menu.SEPARATOR,
            MenuItem(
                "Open tinyassets.io/mcp",
                lambda: webbrowser.open(MCP_URL),
                enabled=lambda _: self._mcp_serving and self._tunnel_ok,
            ),
            MenuItem(
                "Open localhost:8001",
                lambda: webbrowser.open(f"http://localhost:{MCP_PORT}/mcp"),
                enabled=lambda _: self._mcp_serving,
            ),
            Menu.SEPARATOR,
            MenuItem("Restart All", self._on_restart),
            MenuItem(
                "Open Logs",
                lambda: os.startfile(str(LOG_DIR)),  # noqa: S606
            ),
            MenuItem("Quit", self._on_quit),
        )

    def _update_icon(self) -> None:
        if self._icon is None:
            return
        self._icon.icon = make_icon(self.icon_color)
        self._icon.title = self.hover_text
        # Refresh checkmarks/labels based on current state.
        self._icon.menu = self._build_menu()

    def _on_restart(self) -> None:
        """Kill everything, then auto-start daemons from preferences."""
        self._phase = "Restarting..."
        self.kill_all()
        time.sleep(1)
        for provider in self._auto_start_providers():
            self._phase = f"Starting {provider}..."
            self.start_daemon_for(provider)
            time.sleep(1)
        self._phase = "Starting MCP server on port 8001..."
        self.start_mcp()
        time.sleep(2)
        self._phase = (
            "Starting Cloudflare tunnel..."
            if _local_tunnel_enabled()
            else "Skipping local Cloudflare tunnel"
        )
        self.start_tunnel()
        self._phase = "Starting tab watchdog..."
        self.start_watchdog()

    def _on_quit(self, icon=None, item=None) -> None:
        self._stop_event.set()
        self.kill_all()
        if self._icon:
            self._icon.stop()

    # -- Monitor thread --------------------------------------------------

    def _monitor_loop(self) -> None:
        """Background thread: poll health, update icon, auto-restart."""
        restart_backoff = 0
        self._stop_event.wait(3)

        while not self._stop_event.is_set():
            self.check_health()
            self._update_icon()

            if not self._stop_event.is_set():
                if self._check_universe_switch():
                    self._phase = f"Switching to {self._active_universe}..."
                    self._kill_all_daemons()
                    time.sleep(1)
                    for provider in self._auto_start_providers():
                        self.start_daemon_for(provider)

                restarted = False
                if not self._mcp_alive and self.mcp_proc is not None:
                    self._phase = "MCP server died, restarting..."
                    self.start_mcp()
                    restarted = True
                if not self._tunnel_alive and self.tunnel_proc is not None:
                    self._phase = "Tunnel died, restarting..."
                    self.start_tunnel()
                    restarted = True
                if (
                    not self._watchdog_alive
                    and self.watchdog_proc is not None
                ):
                    self._phase = "Tab watchdog died, restarting..."
                    self.start_watchdog()
                    restarted = True

                if restarted:
                    restart_backoff = min(restart_backoff + 1, 6)
                    wait = 5 * (2 ** restart_backoff)
                elif self._any_daemon_alive and self._mcp_serving and self._tunnel_ok:
                    restart_backoff = 0
                    wait = 10
                else:
                    restart_backoff = 0
                    wait = 3

            self._stop_event.wait(wait)

    # -- Main entry ------------------------------------------------------

    def run(self) -> None:
        """Start everything and block until quit."""
        auto_start = self._auto_start_providers()
        print("Starting TinyAssets Server...")
        print(f"  Project:   {PROJECT_DIR}")
        print(f"  Universe:  {self._active_universe}")
        print(f"  Endpoint:  {MCP_URL}")
        print(f"  Providers: {auto_start or 'none (auto-start off)'}")
        print()

        # 1. Launch daemons
        for provider in auto_start:
            self._phase = f"Starting {provider} daemon..."
            if self.start_daemon_for(provider):
                print(f"  [OK] daemon ({provider}) starting")
            time.sleep(1)

        # 2. Launch MCP server
        self._phase = "Starting MCP server on port 8001..."
        self.start_mcp()
        print("  [OK] MCP server starting on port 8001")

        time.sleep(2)

        # 3. Launch optional dev tunnel
        self._phase = (
            "Starting Cloudflare tunnel..."
            if _local_tunnel_enabled()
            else "Skipping local Cloudflare tunnel"
        )
        self.start_tunnel()
        if self.tunnel_proc is not None:
            print("  [OK] Cloudflare tunnel starting")
        else:
            print("  [skip] Local Cloudflare tunnel disabled")

        # 4. Launch tab watchdog
        self._phase = "Starting tab watchdog..."
        self.start_watchdog()
        if self.watchdog_proc is not None:
            print("  [OK] Tab watchdog starting")
        else:
            print("  [skip] Tab watchdog script missing; tab hygiene degrades to entry-hook only")
        print()
        print("  Look for the 'U' icon in your system tray.")
        print("  Right-click it to manage providers or quit.")

        monitor = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor.start()

        self._icon = Icon(
            "TinyAssets Server",
            make_icon(GRAY),
            title="TinyAssets Server - Starting...",
            menu=self._build_menu(),
        )

        signal.signal(signal.SIGINT, lambda *_: self._on_quit())
        signal.signal(signal.SIGTERM, lambda *_: self._on_quit())

        self._icon.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Acquire the host-wide singleton lock and run the tray.

    Returns exit code: 0 on success, 0 also on singleton conflict (silent
    no-op so double-clicking the desktop shortcut is harmless).
    """
    LOG_DIR.mkdir(exist_ok=True)
    acq = acquire_singleton_lock(SINGLETON_LOCK_PATH)
    if not acq.acquired:
        pid_str = f" (PID {acq.existing_pid})" if acq.existing_pid else ""
        print(
            f"TinyAssets Server is already running{pid_str}. "
            "Check your system tray."
        )
        return 0

    mgr = UniverseServerManager()
    try:
        mgr.run()
    except KeyboardInterrupt:
        mgr.kill_all()
    finally:
        release_singleton_lock(acq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
