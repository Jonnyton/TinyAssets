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
# Slice 2 (2026-08-19): running a branch is a WRITE + submit + COSTLY action
# (run_branch consumes model/execution budget and fires effects), so it needs the
# founder's full capability set. `costly` is REQUIRED — without it run_branch
# fails "Missing OAuth scope: tinyassets.extensions.costly" (verified live: the
# agent's run_graph call reached the server and found the branch, then hit
# exactly this gap). This matches _AUTHENTICATED_BASE_CAPABILITIES for a founder.
# Bound ONLY for the run_graph handler, never the read handlers — least privilege.
_RUN_CAPABILITIES = ("read", "list", "write", "submit_request", "costly")


def _bind_founder_identity(capabilities=_READ_CAPABILITIES):
    """Bind ``_current_identity`` to the founder for one call.

    ``capabilities`` defaults to the read-only set; the run_graph handler passes
    ``_RUN_CAPABILITIES`` so a run can submit while reads stay least-privilege.
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
        capabilities=list(capabilities),
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
        target: What to read: ``status`` (a factual daemon + serving snapshot) or
            ``graph`` (inspect your universe's graph). Any other value is refused.
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


@mcp.tool
def get_status() -> str:
    """A factual snapshot of your universe's daemon identity + routing config.

    Read-only ground truth about your universe: serving provider, release state,
    and daemon facts. Scoped to your own universe.
    """
    err = _binding_error()
    if err is not None:
        return err

    from tinyassets.auth.middleware import _current_identity
    from tinyassets.universe_server import get_status as _impl

    token = _bind_founder_identity()
    try:
        # get_status keys off ``universe_id`` (NOT graph_id) — pin the correct
        # argument (Codex #9).
        return _impl(universe_id=_GRAPH_ID)
    finally:
        _current_identity.reset(token)


@mcp.tool
def run_graph(
    branch_def_id: str = "",
    run_name: str = "",
    inputs_json: str = "",
) -> str:
    """Run one of YOUR OWN universe's graph branches end-to-end.

    This FIRES the branch's effects — e.g. an effect-only delivery branch opens a
    real GitHub pull request. Use it to actually DO the thing you built a graph
    for, rather than describing it: read your graph with ``read_graph
    target="graph"`` to find the branch, then run it here.

    Confinement (slice 2, 2026-08-19): the run executes as the FOUNDER and is
    author-gated by ``run_branch`` — a branch your universe did not author is
    refused, never run. The run is pinned to YOUR universe (its effects and
    records land under your universe, not another). Spend is bounded by the
    served-provider budget reservation and the per-run recursion limit; an
    effect-only branch spends no provider budget at all.

    Args:
        branch_def_id: The branch definition id to run (from ``read_graph
            target="graph"``). Required.
        run_name: Optional display label for this run.
        inputs_json: Optional JSON object of run inputs.
    """
    import json

    err = _binding_error()
    if err is not None:
        return err
    bid = (branch_def_id or "").strip()
    if not bid:
        return json.dumps({
            "error": "branch_def_id is required to run a graph.",
        })

    from tinyassets.auth.middleware import _current_identity
    from tinyassets.universe_server import run_graph as _impl

    # Run capabilities (write + submit_request) bound ONLY for this call. The
    # graph_id is PINNED to this universe so the run records under it; the
    # branch_def_id is author-gated by run_branch under the founder identity, so
    # a branch the founder did not author is refused rather than run (this closes
    # the run_graph IDOR the read-only slice deferred).
    token = _bind_founder_identity(_RUN_CAPABILITIES)
    try:
        return _impl(
            branch_def_id=bid,
            graph_id=_GRAPH_ID,
            run_name=(run_name or "").strip(),
            inputs_json=(inputs_json or "").strip(),
        )
    finally:
        _current_identity.reset(token)


if __name__ == "__main__":
    # Transport: HTTP when a port is pinned (the reliable path — claude CLI's
    # stdio-MCP spawn is flaky in the headless served subprocess, HTTP is not),
    # else stdio (spawned by claude -p via --mcp-config). Identity stays pinned
    # to this ONE (actor, graph) via env, so the HTTP listener serves exactly one
    # universe's own handles on loopback.
    import os as _os2
    _http_port = (_os2.environ.get("TINYASSETS_ENGINE_MCP_HTTP_PORT") or "").strip()
    if _http_port:
        mcp.run(transport="http", host="127.0.0.1", port=int(_http_port))
    else:
        mcp.run()  # stdio transport (default)
