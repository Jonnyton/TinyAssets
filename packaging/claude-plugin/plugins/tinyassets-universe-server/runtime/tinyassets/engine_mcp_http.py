"""Persistent per-universe HTTP engine MCP servers, started at daemon boot.

The founder-scoped engine MCP tools (``read_graph`` / ``get_status`` /
``run_graph``) reach the sandboxed ``claude -p`` universe-intelligence turn
through a local MCP server. The claude CLI's **stdio** MCP spawn is unreliable
in the headless served subprocess (verified live 2026-08-19: the stdio server
never launched and the CLI reported the server "still connecting", so the agent
never received its tools). The **HTTP** transport connects reliably, so the
engine server runs over HTTP.

This module starts ONE loopback HTTP engine server per SERVING universe when the
daemon boots — so the capability survives a container recreate with no manual
step (the founder's "24/7 without this computer" rule). Each server is PINNED to
exactly one ``(founder actor, universe graph)`` via env, binds ``127.0.0.1``
only, and therefore exposes just that one universe's own founder-scoped handles.
The ``{graph_id: url}`` route map is published to a file the provider reads
(``claude_provider._engine_mcp_flags``), which points that universe's served
turns at its HTTP engine server instead of a stdio spawn.

Gated by the same dark ``TINYASSETS_ENGINE_MCP_TOOLS`` flag as the tools
themselves; a no-op when the flag is off.

Follow-ups (tracked, not blockers for the durable proof):
  * restart-supervision — a crashed engine server is not currently respawned;
  * dynamic reconcile — a universe that STARTS serving after boot gets no server
    until the next boot;
  * multi-tenant identity — a per-universe pinned loopback server is simple and
    correct for isolation, but a shared server with per-request signed identity
    would scale better; the Codex confinement review governs which we ship.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

#: First loopback port; each serving universe gets the next one, in order.
ENGINE_MCP_HTTP_BASE_PORT = 8790
#: Route map file, read by ``claude_provider._engine_mcp_flags``.
ROUTES_FILENAME = ".engine_mcp_http_routes.json"


def _engine_mcp_enabled() -> bool:
    return os.environ.get("TINYASSETS_ENGINE_MCP_TOOLS", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def run_graph_allowlist() -> frozenset[str]:
    """Universe ids for which the WRITE/COSTLY ``run_graph`` handle is allowed.

    Cross-family review (Codex 2026-08-19) ADAPT: the run_graph confinement
    (author-gate + universe pin + loopback env-pinned server) is safe for a
    SINGLE isolated founder but NOT yet for multi-tenant — the loopback server
    has no per-request auth, run_graph does not verify a SAME-universe branch
    binding or execute an immutable version, and the served budget has DoS
    edges (settled-row growth, stuck reservations). Until that 8-point gate is
    met, run_graph and its HTTP engine server are limited to this explicit
    allowlist (empty = fully dark). Set ``TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES``
    (comma-separated) to the vetted test founder(s) only.
    """
    raw = os.environ.get("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", "")
    return frozenset(u.strip() for u in raw.split(",") if u.strip())


def _serving_universe_owners(base: Path) -> list[tuple[str, str]]:
    """``[(universe_id, owner_actor_id)]`` for universes with a serving binding.

    The owner is the serving agent binding's ``created_by`` — the founder whose
    identity the engine server binds. Fail-closed to an empty list.
    """
    import sqlite3

    from tinyassets.storage import db_path

    owners: list[tuple[str, str]] = []
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
    for row in rows:
        uid = str(row["universe_id"] or "").strip()
        owner = str(row["created_by"] or "").strip()
        if uid and owner:
            owners.append((uid, owner))
    return owners


def start_engine_mcp_http_servers(base: str | Path | None = None) -> list[subprocess.Popen]:
    """Start one loopback HTTP engine server per serving universe; publish routes.

    Returns the started process handles (the daemon keeps them alive for its own
    lifetime). A no-op returning ``[]`` when the engine-MCP flag is off.
    """
    if not _engine_mcp_enabled():
        return []

    from tinyassets.storage import data_dir

    root = Path(data_dir() if base is None else base)
    # Only stand up an engine server for a universe on the run_graph allowlist.
    # A pinned loopback server has no per-request auth, so limiting it to the
    # single vetted founder keeps the multi-tenant cross-universe-read surface
    # closed until the Codex hardening gate lands (see run_graph_allowlist).
    allow = run_graph_allowlist()
    if not allow:
        try:
            (root / ROUTES_FILENAME).write_text("{}", encoding="utf-8")
        except OSError:
            pass
        return []
    owners = [(u, o) for (u, o) in _serving_universe_owners(root) if u in allow]
    data_dir_env = os.environ.get("TINYASSETS_DATA_DIR", str(root))

    routes: dict[str, str] = {}
    procs: list[subprocess.Popen] = []
    for index, (universe_id, owner_actor_id) in enumerate(owners):
        port = ENGINE_MCP_HTTP_BASE_PORT + index
        child_env = dict(os.environ)
        child_env["TINYASSETS_ENGINE_ACTOR_ID"] = owner_actor_id
        child_env["TINYASSETS_ENGINE_GRAPH_ID"] = universe_id
        child_env["TINYASSETS_DATA_DIR"] = data_dir_env
        child_env["TINYASSETS_ENGINE_MCP_HTTP_PORT"] = str(port)
        try:
            proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                [sys.executable, "-m", "tinyassets.engine_mcp_server"],
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:  # noqa: BLE001 - one universe must not break the boot
            logger.exception(
                "engine http: failed to start server for %s", universe_id
            )
            continue
        procs.append(proc)
        routes[universe_id] = f"http://127.0.0.1:{port}/mcp"
        logger.info(
            "engine http: started engine MCP server for %s on 127.0.0.1:%d",
            universe_id, port,
        )

    try:
        (root / ROUTES_FILENAME).write_text(
            json.dumps(routes), encoding="utf-8"
        )
    except OSError:
        logger.exception("engine http: could not write route map")

    return procs
