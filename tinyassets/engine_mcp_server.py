"""Local, founder-scoped TinyAssets MCP server for the universe-intelligence turn.

Spawned as a subprocess of ``claude -p`` (the universe agent, "Tiny") via
``--mcp-config`` + ``--strict-mcp-config``, this exposes the SAME canonical MCP
handles the founder's browser chatbot has, so the universe agent can operate its
OWN universe through the identical MCP surface.

Founder directive 2026-08-12: *"all user functions are just mcp functions ... all
the same mcp commands whether it's through the app or through slack or the
browser."*

Security model — this is the P0 engine-sandbox surface (2026-07-03 live-test:
the un-sandboxed engine read platform source and ran Bash). The wiring in
``claude_provider._engine_mcp_flags`` reaches this ONLY via ``--strict-mcp-config``
(which admits exactly this one server and excludes the logged-in claude.ai
account connectors — verified 2026-08-13). This module then enforces:

  * **Identity.** Every handler call runs with ``_current_identity`` bound to the
    FOUNDER (``TINYASSETS_ENGINE_ACTOR_ID``) and a LEAST-PRIVILEGE capability set.
    No host identity, no ambient/env credential fallback. An empty actor_id binds
    ANONYMOUS, so a private-universe read simply fails closed.
  * **Graph pin.** Every handler is forced onto ``TINYASSETS_ENGINE_GRAPH_ID``.
    The agent cannot address another universe by supplying a different id — the
    pinned id is not even an exposed parameter.
  * **Read-only slice.** This slice exposes only ``read_graph`` + ``get_status``
    and binds only ``read``/``list`` capabilities — NO write/submit_request — so
    even a prompt-injected engine cannot mutate DOMAIN state or spend the
    founder's subscription through this surface. (The status read path may still
    touch internal infra sidecars — e.g. queue / auto-ship lock markers — so it
    is not byte-for-byte side-effect-free, but it changes no domain state or
    cost; Codex ADAPT 2026-08-13 #5.) ``write_graph`` / ``run_graph`` /
    ``read_page`` / ``write_page`` are deferred to reviewed follow-up slices;
    ``converse`` is never exposed (a universe relaying to itself is a fork bomb).

Enabled per-deploy by the dark ``TINYASSETS_ENGINE_MCP_TOOLS`` flag (see
``universe_intelligence._engine_mcp_enabled``).
"""
from __future__ import annotations

import os

from fastmcp import FastMCP

# The founder + universe this engine turn is bound to. Read once at startup; the
# daemon writes them into the server subprocess env via _engine_mcp_flags.
_ACTOR_ID = (os.environ.get("TINYASSETS_ENGINE_ACTOR_ID") or "").strip()
_GRAPH_ID = (os.environ.get("TINYASSETS_ENGINE_GRAPH_ID") or "").strip()

# Least-privilege identity for the read-only slice: exactly the capabilities a
# read needs. NO ``write`` / ``submit_request`` — those gate mutation and run
# submission, which this slice deliberately does not expose. ``user_id`` is the
# founder, so an ACL read of the universe's OWN (possibly private) graph passes.
_READ_CAPABILITIES = ("read", "list")


def _bind_founder_identity():
    """Bind ``_current_identity`` to the founder (read caps) for one call.

    Returns the ContextVar token so the caller can reset it. Fail-closed: with no
    actor_id we bind ANONYMOUS, and the handlers refuse private-universe reads.
    """
    from tinyassets.auth.middleware import _current_identity
    from tinyassets.auth.provider import ANONYMOUS, Identity

    if not _ACTOR_ID:
        return _current_identity.set(ANONYMOUS)
    identity = Identity(
        user_id=_ACTOR_ID,
        username=_ACTOR_ID,
        capabilities=list(_READ_CAPABILITIES),
    )
    return _current_identity.set(identity)


# Targets whose universe is selected by the PINNED ``graph_id`` alone. Every
# other ``read_graph`` target (runs/run/branch/goals/agents/agent_binding/…)
# selects records through INDEPENDENT ids that a ``graph_id`` pin does not
# constrain — Codex REJECT 2026-08-13 #5/#8: those reach global or other-founder
# data (and ``run_graph``'s branch load is an IDOR). Slice 1 exposes ONLY these
# two, so the pin is a real confinement, not a decoration.
_PINNED_READ_TARGETS = frozenset({"status", "graph"})


def _binding_error() -> str | None:
    """Hard fail-closed: refuse every call unless BOTH ids are bound.

    Codex #3: an empty actor_id must not degrade to an anonymous public read — it
    must expose nothing. The wiring already refuses to launch this server without
    both ids, but defense-in-depth belongs at the call site too.
    """
    import json

    if not (_ACTOR_ID and _GRAPH_ID):
        return json.dumps({
            "error": "engine MCP is not bound to a founder + universe; refusing.",
        })
    return None


mcp = FastMCP("tinyassets")


@mcp.tool
def read_graph(target: str = "status") -> str:
    """Read your OWN universe's status or graph, without changing anything.

    Scoped to YOUR universe — you cannot read another one.

    Args:
        target: What to read: ``status`` (your universe's projected status
            snapshot) or ``graph`` (inspect your universe's graph). Any other
            value is refused.
    """
    import json

    err = _binding_error()
    if err is not None:
        return err
    normalized = (target or "status").strip().lower()
    if normalized not in _PINNED_READ_TARGETS:
        return json.dumps({
            "error": (
                f"target {normalized!r} is not available here; "
                f"use one of: {sorted(_PINNED_READ_TARGETS)}."
            ),
        })
    if normalized == "status":
        # target=status routes to the SAME full host/global status handler the
        # get_status tool wraps — it must go through the same engine-safe
        # projection, or read_graph would be a projection bypass.
        return _projected_status()

    from tinyassets.auth.middleware import _current_identity
    from tinyassets.universe_server import read_graph as _impl

    token = _bind_founder_identity()
    try:
        # graph_id is PINNED, never caller-supplied: the agent cannot address
        # another universe, and the restricted target set means graph_id is the
        # ONLY selector in play.
        return _impl(target=normalized, graph_id=_GRAPH_ID)
    finally:
        _current_identity.reset(token)


# Engine-safe projection of get_status (Codex 2026-08-13 ADAPT #3): the full
# handler is HOST/GLOBAL status — root-wide storage, deployment receipts (whose
# ``extra`` passes unknown fields through verbatim), host topology, absolute
# paths. None of that is a universe-scoped read, so the engine gets a WHITELIST
# of universe-only fields. Whitelisting (not blacklisting) means a future field
# added to get_status fails CLOSED here until deliberately admitted.
_STATUS_PROJECTION = (
    "schema_version",
    "universe_id",
    "universe_exists",
    "persona",
    "universe_serving",  # per-universe serving binding (present post-#2416)
)


def _projected_status() -> str:
    """The full status handler, reduced to the engine-safe whitelist."""
    import json

    from tinyassets.auth.middleware import _current_identity
    from tinyassets.universe_server import get_status as _impl

    token = _bind_founder_identity()
    try:
        # get_status keys off ``universe_id`` (NOT graph_id) — pin the correct
        # argument (Codex #9).
        raw = _impl(universe_id=_GRAPH_ID)
    finally:
        _current_identity.reset(token)
    try:
        full = json.loads(raw)
    except (TypeError, ValueError):
        # A non-JSON handler result must not leak unprojected — refuse instead.
        return json.dumps({"error": "status unavailable (unprojectable result)."})
    if not isinstance(full, dict):
        return json.dumps({"error": "status unavailable (unprojectable result)."})
    return json.dumps({k: full[k] for k in _STATUS_PROJECTION if k in full})


@mcp.tool
def get_status() -> str:
    """A factual snapshot of your OWN universe: identity, persona, serving state.

    Read-only, scoped to your universe. Host-level daemon internals are not
    included.
    """
    err = _binding_error()
    if err is not None:
        return err
    return _projected_status()


if __name__ == "__main__":
    mcp.run()  # stdio transport (default) — spawned by claude -p via --mcp-config
