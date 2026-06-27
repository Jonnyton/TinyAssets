"""Full-platform v0 FastMCP gateway skeleton.

Proves the #27 gateway → Postgres path composes end-to-end. Stubbed
auth (bearer == user_id for v0; real Supabase JWT in track C). Stubbed
embedding (caller pre-computes; same pattern the real RPC will use).

Run:
    docker compose up -d  # start postgres
    psql ... -f migrations/*.sql
    python gateway.py
    # connects FastMCP stdio transport — tests drive it programmatically.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager

import psycopg
from fastmcp import FastMCP
from pgvector.psycopg import register_vector

DSN = os.environ.get(
    "TINYASSETS_V0_DSN",
    "postgresql://workflow:workflow_v0_dev@localhost:5433/workflow_v0",
)

mcp = FastMCP(
    "workflow-v0",
    instructions=(
        "Prototype FastMCP gateway proving #25 schema + #27 gateway compose. "
        "Not for production. Bearer token is the user_id uuid directly; "
        "real build uses Supabase JWT verification."
    ),
    version="0.0.1",
)


def _check_postgres() -> str:
    """Probe Postgres reachability. Returns 'ok' or 'unreachable'.

    Plain callable — invokable from the Docker compose healthcheck
    without FastMCP runtime context. The MCP-facing `health()` tool
    below delegates here.
    """
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return "ok"
    except Exception:
        return "unreachable"


def _health_payload() -> dict:
    """Plain-callable health payload. Used by both the MCP tool and
    the Docker compose healthcheck (which imports this directly to
    avoid the FastMCP tool-wrapper callable-vs-object gotcha)."""
    return {
        "gateway": "ok",
        "postgres": _check_postgres(),
        "version": "0.0.1",
    }


@mcp.tool()
def health() -> dict:
    """Health probe — confirms gateway is alive + Postgres is reachable.

    Returns {"gateway": "ok", "postgres": "ok" | "unreachable", "version": "0.0.1"}.
    Used by Docker compose healthcheck + manual smoke tests. Delegates
    to `_health_payload()` so the compose healthcheck can invoke the
    probe without needing an MCP context.
    """
    return _health_payload()


@contextmanager
def user_conn(user_id: str):
    """Open a connection, apply v0 RLS context (app.current_user_id GUC)."""
    conn = psycopg.connect(DSN)
    register_vector(conn)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('app.current_user_id', %s, false)",
                (user_id,),
            )
        yield conn
    finally:
        conn.close()


def _extract_bearer(context: dict) -> str:
    """v0: bearer token IS the user_id. Real build: JWT decode per #27 §5.3."""
    bearer = (context or {}).get("bearer_token", "").strip()
    if not bearer:
        raise RuntimeError("missing_bearer")
    return bearer


@mcp.tool()
def discover_nodes(
    intent: str,
    intent_embedding: list[float],
    domain_hint: str | None = None,
    limit: int = 20,
    cross_domain: bool = True,
    bearer_token: str = "",  # v0: user_id uuid directly
) -> dict:
    """Wraps the discover_nodes RPC per #25 §3.1 shape.

    v0 signature requires caller to pass a 16-dim embedding explicitly.
    Real build computes via Supabase Edge Function at gateway boundary.
    """
    user_id = bearer_token or None
    with user_conn(user_id or "00000000-0000-0000-0000-000000000000") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT public.discover_nodes(%s, %s::vector(16), NULL, NULL, %s, %s, %s)",
                (intent, intent_embedding, domain_hint, limit, cross_domain),
            )
            row = cur.fetchone()
            return row[0] if row else {"candidates": []}


@mcp.tool()
def update_node(
    node_id: str,
    concept: dict,
    version: int,
    bearer_token: str = "",
) -> dict:
    """Optimistic CAS write per #25 §14.3 + #27 §4 error envelope (cas_conflict).

    v0: bearer_token is the user_id uuid.
    """
    user_id = bearer_token
    with user_conn(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.nodes
                SET concept = %s, version = version + 1, last_edited_at = now(),
                    updated_at = now()
                WHERE node_id = %s AND version = %s
                RETURNING version
                """,
                (json.dumps(concept), node_id, version),
            )
            result = cur.fetchone()
            if result is None:
                # CAS conflict — load current state for the error envelope
                cur.execute(
                    "SELECT version, concept FROM public.nodes WHERE node_id = %s",
                    (node_id,),
                )
                current = cur.fetchone()
                conn.rollback()
                if current is None:
                    return {
                        "error": {
                            "code": -32602,
                            "message": "node_not_found",
                            "data": {"kind": "not_found", "node_id": node_id},
                        }
                    }
                return {
                    "error": {
                        "code": -32005,
                        "message": "cas_conflict",
                        "data": {
                            "kind": "cas_conflict",
                            "current_version": current[0],
                        },
                    }
                }
            conn.commit()
            return {"ok": True, "new_version": result[0]}


if __name__ == "__main__":
    # FastMCP stdio transport — pytest drives via direct function calls instead.
    mcp.run()
