"""Persistent, supervised, per-universe HTTP engine MCP servers.

The founder-scoped engine MCP tools (``read_graph`` / ``get_status`` /
``run_graph``) reach the sandboxed ``claude -p`` universe-intelligence turn
through a local MCP server. The claude CLI's **stdio** MCP spawn is unreliable
in the headless served subprocess (verified live 2026-08-19: the stdio server
never launched and the CLI reported the server "still connecting"). The **HTTP**
transport connects reliably, so the engine server runs over HTTP.

This starts one loopback HTTP engine server per SERVING universe and KEEPS them
running — so the capability survives a container recreate AND a lone engine-server
crash, with no host tending it (the founder's "24/7 without this computer" rule).
Each server is PINNED to exactly one ``(founder actor, universe graph)`` via env,
binds ``127.0.0.1`` only, and requires a per-server bearer secret on every request
(Codex gate #6 — the loopback listener is reachable by any in-container process).

Confinement (Codex ADAPT 2026-08-19): run_graph and these servers are limited to
the ``TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES`` allowlist (empty = dark) until the
multi-tenant hardening gate lands. The ``{graph_id: {url, secret}}`` route map is
published (mode 0600) to a file the provider reads
(``claude_provider._engine_mcp_flags``).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: First loopback port; each serving universe gets the next free one.
ENGINE_MCP_HTTP_BASE_PORT = 8790
#: Route map file, read by ``claude_provider._engine_mcp_flags``.
ROUTES_FILENAME = ".engine_mcp_http_routes.json"
#: How often the supervisor respawns dead servers + reconciles serving intent.
_SUPERVISOR_INTERVAL_S = 15.0


def _engine_mcp_enabled() -> bool:
    return os.environ.get("TINYASSETS_ENGINE_MCP_TOOLS", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def run_graph_allowlist() -> frozenset[str]:
    """Universe ids for which run_graph + an HTTP engine server are allowed.

    Cross-family review (Codex 2026-08-19) ADAPT: the run_graph confinement is
    safe for a SINGLE isolated founder but NOT yet multi-tenant. Until the full
    hardening gate is met, run_graph and its HTTP server are limited to this
    explicit allowlist (empty = fully dark). Set
    ``TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES`` (comma-separated) to the vetted
    test founder(s) only.
    """
    raw = os.environ.get("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", "")
    return frozenset(u.strip() for u in raw.split(",") if u.strip())


def _serving_universe_owners(base: Path) -> list[tuple[str, str]]:
    """``[(universe_id, owner_actor_id)]`` for universes with a serving binding.

    The owner is the serving agent binding's ``created_by``. Fail-closed to [].
    """
    import sqlite3

    from tinyassets.storage import db_path

    try:
        conn = sqlite3.connect(db_path(base))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT DISTINCT universe_id, created_by "
                "FROM agent_bindings WHERE status = 'serving'"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        logger.exception("engine http: could not enumerate serving universes")
        return []
    owners: list[tuple[str, str]] = []
    for row in rows:
        uid = str(row["universe_id"] or "").strip()
        owner = str(row["created_by"] or "").strip()
        if uid and owner:
            owners.append((uid, owner))
    return owners


class _EngineServer:
    """One pinned loopback engine MCP server subprocess, with a stable secret."""

    __slots__ = ("universe_id", "owner", "port", "secret", "_data_dir", "proc")

    def __init__(self, universe_id, owner, port, data_dir_env):
        self.universe_id = universe_id
        self.owner = owner
        self.port = port
        self.secret = secrets.token_urlsafe(32)
        self._data_dir = data_dir_env
        self.proc = None

    def start(self) -> bool:
        env = dict(os.environ)
        env["TINYASSETS_ENGINE_ACTOR_ID"] = self.owner
        env["TINYASSETS_ENGINE_GRAPH_ID"] = self.universe_id
        env["TINYASSETS_DATA_DIR"] = self._data_dir
        env["TINYASSETS_ENGINE_MCP_HTTP_PORT"] = str(self.port)
        env["TINYASSETS_ENGINE_MCP_HTTP_SECRET"] = self.secret
        try:
            self.proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                [sys.executable, "-m", "tinyassets.engine_mcp_server"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "engine http: failed to start server for %s", self.universe_id
            )
            return False
        logger.info(
            "engine http: started server for %s on 127.0.0.1:%d",
            self.universe_id, self.port,
        )
        return True

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:  # noqa: BLE001
                pass


def _write_routes(root: Path, servers) -> None:
    routes = {
        s.universe_id: {
            "url": f"http://127.0.0.1:{s.port}/mcp",
            "secret": s.secret,
        }
        for s in servers
    }
    path = root / ROUTES_FILENAME
    # Atomic publish: write a private temp then rename, so a concurrent turn
    # never reads a half-written map or a URL without its secret (Codex
    # 2026-08-19 — race-free publication).
    tmp = path.with_suffix(".json.tmp")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(routes).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(str(tmp), str(path))
        os.chmod(path, 0o600)  # secrets — never world-readable
    except OSError:
        logger.exception("engine http: could not write route map")


def _desired_owners(root: Path) -> dict[str, str]:
    allow = run_graph_allowlist()
    return {u: o for (u, o) in _serving_universe_owners(root) if u in allow}


def start_engine_mcp_http_servers(base: str | Path | None = None) -> list:
    """Start one auth'd loopback engine server per allowlisted serving universe
    and a daemon supervisor that respawns crashes + reconciles serving intent.

    No-op returning ``[]`` when the engine-MCP flag is off or the allowlist is
    empty. Called once, early in daemon startup.
    """
    if not _engine_mcp_enabled():
        return []

    from tinyassets.storage import data_dir

    root = Path(data_dir() if base is None else base)
    data_dir_env = os.environ.get("TINYASSETS_DATA_DIR", str(root))

    servers: dict[str, _EngineServer] = {}
    used_ports: set[int] = set()

    def _next_port() -> int:
        port = ENGINE_MCP_HTTP_BASE_PORT
        while port in used_ports:
            port += 1
        used_ports.add(port)
        return port

    def _retire(uid: str) -> None:
        srv = servers.pop(uid, None)
        if srv is not None:
            srv.stop()
            used_ports.discard(srv.port)  # release the port (Codex 2026-08-19 d3)

    # Initial servers for whatever is serving now.
    for universe_id, owner in _desired_owners(root).items():
        srv = _EngineServer(universe_id, owner, _next_port(), data_dir_env)
        if srv.start():
            servers[universe_id] = srv
    _write_routes(root, servers.values())

    def _supervise() -> None:
        while True:
            time.sleep(_SUPERVISOR_INTERVAL_S)
            try:
                current = _desired_owners(root)
                changed = False
                # Retire universes that stopped serving / left the allowlist.
                for uid in [u for u in servers if u not in current]:
                    _retire(uid)
                    changed = True
                # Retire+replace a universe whose OWNER changed (a stale founder
                # pin would answer as the wrong identity — Codex 2026-08-19 d2).
                for uid in [u for u in servers if servers[u].owner != current.get(u)]:
                    _retire(uid)
                    changed = True
                # Respawn crashed servers for still-desired universes.
                for uid, srv in servers.items():
                    if not srv.alive():
                        logger.warning("engine http: respawning dead server %s", uid)
                        srv.start()
                        changed = True
                # Stand up servers for newly-serving (or re-owned) universes.
                for uid, owner in current.items():
                    if uid not in servers:
                        srv = _EngineServer(uid, owner, _next_port(), data_dir_env)
                        if srv.start():
                            servers[uid] = srv
                            changed = True
                if changed:
                    _write_routes(root, servers.values())
            except Exception:  # noqa: BLE001 - the supervisor must never die
                logger.exception("engine http: supervisor tick failed")

    # ALWAYS start the supervisor — even when nothing is serving yet at boot — so
    # a universe that begins serving later gets a server (Codex 2026-08-19 d1).
    threading.Thread(
        target=_supervise, name="engine-mcp-supervisor", daemon=True
    ).start()
    return list(servers.values())
