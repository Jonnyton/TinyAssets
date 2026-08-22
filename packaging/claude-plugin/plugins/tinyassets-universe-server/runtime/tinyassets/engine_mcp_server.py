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

#: Effect-spam rate limit for run_graph (Codex gate #5): at most this many
#: engine-triggered runs per universe per rolling window.
_RUN_GRAPH_RATE_WINDOW_S = 3600
_RUN_GRAPH_RATE_MAX = 20


def _bearer_ok(authorization_header, secret) -> bool:
    """Constant-time check that the header carries exactly ``Bearer <secret>``.

    Module-level so the HTTP auth (Codex gate #6) is unit-testable. Empty secret
    is never OK — the listener refuses to serve without one.
    """
    import hmac

    if not secret:
        return False
    return hmac.compare_digest(authorization_header or "", "Bearer " + secret)


def _engine_run_admit() -> bool:
    """Atomically admit one engine-triggered run under the rolling cap, or refuse.

    A dedicated engine-admission ledger (NOT the shared runs table, which would
    over-limit legitimate browser/scheduled runs — Codex 2026-08-19 (b)). The
    count-and-insert run inside a single ``BEGIN IMMEDIATE`` transaction, so two
    parallel run_graph calls cannot both slip past the cap (atomic admission,
    closing the TOCTOU race). Old rows are pruned opportunistically so the table
    stays bounded. Fail-OPEN on any DB error: this is a spam bound, not the
    primary control (the allowlist + approved-source gate are).
    """
    import sqlite3
    import time as _time
    from pathlib import Path as _P

    data_dir = (os.environ.get("TINYASSETS_DATA_DIR") or "").strip() or "."
    db = _P(data_dir) / ".engine_run_admissions.db"
    now = _time.time()
    cutoff = now - _RUN_GRAPH_RATE_WINDOW_S
    try:
        conn = sqlite3.connect(str(db), timeout=10)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS admissions "
                "(universe_id TEXT NOT NULL, ts REAL NOT NULL)"
            )
            conn.execute("BEGIN IMMEDIATE")
            n = conn.execute(
                "SELECT COUNT(*) FROM admissions WHERE universe_id = ? AND ts >= ?",
                (_GRAPH_ID, cutoff),
            ).fetchone()[0]
            if int(n) >= _RUN_GRAPH_RATE_MAX:
                conn.rollback()
                return False
            conn.execute(
                "INSERT INTO admissions (universe_id, ts) VALUES (?, ?)",
                (_GRAPH_ID, now),
            )
            conn.execute(
                "DELETE FROM admissions WHERE ts < ?",
                (cutoff - _RUN_GRAPH_RATE_WINDOW_S,),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except sqlite3.Error:
        return True  # fail open — spam bound, not the primary control


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
    # Single-founder scope gate (Codex ADAPT 2026-08-19): run_graph is a
    # WRITE+COSTLY effect surface whose confinement is only proven for one
    # isolated founder. Refuse unless THIS universe is on the explicit allowlist,
    # even if a server was somehow started for it. Defense in depth alongside
    # engine_mcp_http, which only starts a server for allowlisted universes.
    from tinyassets.engine_mcp_http import run_graph_allowlist

    if _GRAPH_ID not in run_graph_allowlist():
        return json.dumps({
            "error": (
                "run_graph is not enabled for this universe yet; it is limited "
                "to a vetted founder while its multi-tenant confinement is "
                "hardened."
            ),
        })
    bid = (branch_def_id or "").strip()
    if not bid:
        return json.dumps({
            "error": "branch_def_id is required to run a graph.",
        })

    # Effect-spam rate limit (Codex gate #5): a prompt-injected engine could spam
    # run_graph on an already-approved effect branch (e.g. opening many PRs). Cap
    # the runs THIS universe can trigger via the engine per rolling window. The
    # approved-source-hash gate already pins WHAT runs; this bounds HOW OFTEN.
    if not _engine_run_admit():
        return json.dumps({
            "error": (
                f"run_graph rate limit reached (max {_RUN_GRAPH_RATE_MAX} per "
                f"{_RUN_GRAPH_RATE_WINDOW_S // 60}m); try again shortly."
            ),
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


# ── Shared commons (slice 3, 2026-08-22) ─────────────────────────────────────
# TinyAssets is TWO things to a founder: (1) this private universe (brain +
# harness), and (2) a SHARED COMMONS of automation SHAPES — public
# BranchDefinitions authored across every universe, remixable by anyone (design:
# universe_server.py "commons-first", Codex #1404). The founder's browser chatbot
# already browses/remixes/publishes shapes; before this slice the served agent
# had NO path to it and (live 2026-08-22) fell back to WebFetching n8n/Make when
# asked to "browse our commons". These handlers give the agent the SAME commons.
#
# Safety: browse/read are READ-ONLY over PUBLIC data — they delegate to the
# canonical handlers with the founder identity bound, so the existing viewer
# filter (list_branch_definitions viewer=founder) and author gate (get_branch's
# "not found" envelope for a private branch, branches.py:443) enforce visibility.
# Unlike the own-universe read_graph handler these are deliberately NOT
# graph-pinned: the commons IS cross-universe by design, and you can only see /
# fork what those gates already let you read. remix is a WRITE into the founder's
# OWN universe (a new PRIVATE branch, fires no effects, spends no budget); it is
# gated by the same allowlist + rate-limit as run_graph while multi-tenant
# confinement is hardened. PUBLISH to the global commons is a separate,
# consent-gated slice — deliberately NOT exposed here.
_COMMONS_LIST_KINDS = frozenset({"branches", "agents", "goals"})


@mcp.tool
def browse_commons(
    kind: str = "branches",
    query: str = "",
    author: str = "",
    limit: int = 30,
) -> str:
    """Browse the SHARED TinyAssets commons — automation shapes other universes
    published, that you can remix into your own.

    THIS is the commons to use — do NOT web-search other platforms (n8n, Make,
    Zapier). These are live, remixable TinyAssets shapes.

    Args:
        kind: What to list: ``branches`` (published workflow graph shapes — the
            main commons; each row carries a ``published_version_id`` you pass to
            ``remix_shape``), ``agents`` (public custom agent definitions), or
            ``goals`` (shared goals). Defaults to ``branches``.
        query: Optional search text (agents/goals).
        author: Optional author filter.
        limit: Max records (agents/goals).
    """
    import json

    err = _binding_error()
    if err is not None:
        return err
    normalized = (kind or "branches").strip().lower()
    if normalized not in _COMMONS_LIST_KINDS:
        return json.dumps({
            "error": (
                f"kind {normalized!r} is not available; "
                f"use one of: {sorted(_COMMONS_LIST_KINDS)}."
            ),
        })

    from tinyassets.auth.middleware import _current_identity

    # Read/list capabilities only; the viewer filter keys off the bound founder
    # identity so private non-authored records never surface.
    token = _bind_founder_identity()
    try:
        if normalized == "branches":
            from tinyassets.api.extensions import _extensions_impl

            # scope="published" = shapes with a published (remixable) version —
            # exactly the commons catalog. viewer=founder is derived from the
            # bound identity inside _ext_branch_list.
            return _extensions_impl(
                action="list_branches",
                scope="published",
                author=(author or "").strip(),
            )
        from tinyassets.universe_server import read_graph as _impl

        return _impl(
            target=normalized,
            query=(query or "").strip(),
            author=(author or "").strip(),
            limit=limit,
        )
    finally:
        _current_identity.reset(token)


@mcp.tool
def read_commons_shape(branch_id: str = "", agent_definition_id: str = "") -> str:
    """Read the FULL definition of ONE shared shape so you can decide whether to
    remix it — nodes, edges, prompts, and lineage.

    Pass exactly one id (from ``browse_commons``). You can read any PUBLIC shape
    from any universe; a private shape you did not author reads as "not found".

    Args:
        branch_id: A branch definition id (a workflow graph shape).
        agent_definition_id: A public custom-agent definition id.
    """
    import json

    err = _binding_error()
    if err is not None:
        return err
    bid = (branch_id or "").strip()
    aid = (agent_definition_id or "").strip()
    if not (bid or aid):
        return json.dumps({
            "error": "pass branch_id or agent_definition_id (from browse_commons).",
        })

    from tinyassets.auth.middleware import _current_identity
    from tinyassets.universe_server import read_graph as _impl

    token = _bind_founder_identity()
    try:
        if bid:
            # target=branch -> get_branch author-gates private non-authored
            # shapes with a "not found" envelope (branches.py:443).
            return _impl(target="branch", branch_id=bid)
        return _impl(target="agent", agent_definition_id=aid)
    finally:
        _current_identity.reset(token)


@mcp.tool
def remix_shape(
    fork_from: str = "",
    name: str = "",
    description: str = "",
) -> str:
    """Remix (fork) a shared commons shape into YOUR OWN universe as a new
    PRIVATE branch you can then inspect, edit, and run.

    This copies the shape only — nodes, edges, prompts. It never copies another
    universe's private data. The new branch is private to your universe until you
    choose to publish it.

    Args:
        fork_from: The ``published_version_id`` of the shape to remix (from a
            ``browse_commons`` row or ``read_commons_shape``). Required. Must be a
            published branch_version_id, not a branch_def_id.
        name: A name for your remixed branch. Required.
        description: Optional description of what you changed / intend.
    """
    import json

    err = _binding_error()
    if err is not None:
        return err
    # Single-founder scope gate (mirrors run_graph): remix WRITES a branch into
    # this universe. Safe for one vetted founder; refuse until multi-tenant
    # confinement is hardened, even if a server was somehow started here.
    from tinyassets.engine_mcp_http import run_graph_allowlist

    if _GRAPH_ID not in run_graph_allowlist():
        return json.dumps({
            "error": (
                "remix is not enabled for this universe yet; it is limited to a "
                "vetted founder while its multi-tenant confinement is hardened."
            ),
        })
    selector = (fork_from or "").strip()
    new_name = (name or "").strip()
    if not selector:
        return json.dumps({
            "error": "fork_from (a published branch_version_id) is required.",
        })
    if not new_name:
        return json.dumps({"error": "name is required for the remixed branch."})
    # Effect-spam bound (shared engine-write budget with run_graph).
    if not _engine_run_admit():
        return json.dumps({
            "error": (
                f"engine write rate limit reached (max {_RUN_GRAPH_RATE_MAX} per "
                f"{_RUN_GRAPH_RATE_WINDOW_S // 60}m); try again shortly."
            ),
        })

    spec = {
        "name": new_name,
        "fork_from": selector,
        "visibility": "private",
    }
    if (description or "").strip():
        spec["description"] = description.strip()

    from tinyassets.auth.middleware import _current_identity
    from tinyassets.universe_server import write_graph as _impl

    # Founder's full authenticated capability set — faithful to what the founder
    # can already do through the browser; remix is not an escalation. The write
    # lands under the founder identity, so it records in THIS universe.
    token = _bind_founder_identity(_RUN_CAPABILITIES)
    try:
        return _impl(
            target="branch",
            operation="remix",
            payload_json=json.dumps(spec, separators=(",", ":")),
        )
    finally:
        _current_identity.reset(token)


@mcp.tool
def publish_shape(branch_id: str = "", notes: str = "") -> str:
    """Publish (or UPDATE) one of YOUR OWN shapes to the shared global commons so
    other universes can find and remix it.

    Publishing makes the shape PUBLIC and snapshots its CURRENT state as a new
    version. Keep evolving the SAME branch and call this again to publish an
    improved version of the SAME workflow — e.g. after a run surfaced an error you
    fixed. Re-publishing the same branch UPDATES its commons entry in place (a new
    best version under the same shape); it does NOT spawn a separate near-duplicate
    shape, and it does NOT change anyone's existing remix/fork (those are copies —
    a remixer re-remixes to pick up your latest). So publish the SAME branch you
    have been improving rather than remixing your own work into a new branch each
    time.

    You can only publish a shape YOUR universe authored; someone else's shape
    reads as "not found".

    Args:
        branch_id: The branch definition id of YOUR shape to publish/update
            (from ``read_graph target="graph"`` or a prior ``remix_shape``).
            Required.
        notes: Optional release notes — what changed / what this version fixes.
    """
    import json

    err = _binding_error()
    if err is not None:
        return err
    from tinyassets.engine_mcp_http import run_graph_allowlist

    if _GRAPH_ID not in run_graph_allowlist():
        return json.dumps({
            "error": (
                "publish is not enabled for this universe yet; it is limited to a "
                "vetted founder while its multi-tenant confinement is hardened."
            ),
        })
    bid = (branch_id or "").strip()
    if not bid:
        return json.dumps({
            "error": "branch_id (a branch YOUR universe authored) is required.",
        })
    if not _engine_run_admit():
        return json.dumps({
            "error": (
                f"engine write rate limit reached (max {_RUN_GRAPH_RATE_MAX} per "
                f"{_RUN_GRAPH_RATE_WINDOW_S // 60}m); try again shortly."
            ),
        })

    from tinyassets.auth.middleware import _current_identity
    from tinyassets.universe_server import write_graph as _impl

    token = _bind_founder_identity(_RUN_CAPABILITIES)
    try:
        # 1. Make it public so it is visible in the commons (no-op if already
        #    public). Author-gated: a branch this universe did not author is
        #    refused here, so it never reaches publish.
        make_public = _impl(
            target="branch",
            operation="patch",
            branch_id=bid,
            changes_json=json.dumps(
                [{"op": "set_visibility", "visibility": "public"}],
                separators=(",", ":"),
            ),
        )
        try:
            if isinstance(json.loads(make_public), dict) and json.loads(
                make_public
            ).get("error"):
                return make_public
        except (json.JSONDecodeError, TypeError):
            pass
        # 2. Snapshot the current state as a new best version of the SAME shape.
        return _impl(
            target="branch",
            operation="publish",
            branch_id=bid,
            description=(notes or "").strip(),
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
        # Per-request auth (Codex gate #6): the loopback listener is reachable by
        # any in-container process, so every request must carry the shared bearer
        # secret the launcher injected (and the provider puts in the turn's
        # --mcp-config headers, invisible to the LLM). FAIL CLOSED: no secret ->
        # do not serve unauthenticated.
        import uvicorn as _uvicorn

        _secret = (
            _os2.environ.get("TINYASSETS_ENGINE_MCP_HTTP_SECRET") or ""
        ).strip()
        if not _secret:
            raise SystemExit(
                "engine MCP HTTP refuses to serve without "
                "TINYASSETS_ENGINE_MCP_HTTP_SECRET"
            )
        _inner_app = mcp.http_app()

        class _BearerAuth:
            """Reject any HTTP request lacking the exact bearer secret (401).

            Only ``http`` and ``lifespan`` scopes are handled; anything else
            (e.g. a future ``websocket`` route) is refused (Codex 2026-08-19).
            """

            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                stype = scope.get("type")
                if stype == "http":
                    headers = dict(scope.get("headers") or [])
                    provided = headers.get(b"authorization", b"").decode(
                        "latin-1"
                    )
                    if not _bearer_ok(provided, _secret):
                        await send({
                            "type": "http.response.start",
                            "status": 401,
                            "headers": [(b"content-type", b"text/plain")],
                        })
                        await send({
                            "type": "http.response.body",
                            "body": b"unauthorized",
                        })
                        return
                elif stype != "lifespan":
                    return  # refuse websocket / unknown transports
                await self.app(scope, receive, send)

        _uvicorn.run(
            _BearerAuth(_inner_app),
            host="127.0.0.1",
            port=int(_http_port),
            log_level="warning",
        )
    else:
        mcp.run()  # stdio transport (default)
