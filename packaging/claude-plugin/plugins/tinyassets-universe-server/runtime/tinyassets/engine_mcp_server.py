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
# Remix caps (Codex ADAPT 2026-08-22 #6): a branch WRITE, not a run. Drops
# ``submit_request`` (that gates run submission, which remix does not do). Keeps
# ``costly`` because branch create/build is a scope-gated costly op.
_REMIX_CAPABILITIES = ("read", "list", "write", "costly")

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


def _engine_run_admit(*, fail_closed: bool = False) -> bool:
    """Atomically admit one engine-triggered write under the rolling cap, or refuse.

    A dedicated engine-admission ledger (NOT the shared runs table, which would
    over-limit legitimate browser/scheduled runs — Codex 2026-08-19 (b)). The
    count-and-insert run inside a single ``BEGIN IMMEDIATE`` transaction, so two
    parallel calls cannot both slip past the cap (atomic admission, closing the
    TOCTOU race). Old rows are pruned opportunistically so the table stays bounded.

    ``fail_closed`` (Codex ADAPT 2026-08-22 #6): run_graph passes False — its
    approved-source gate + allowlist are the primary controls, so a DB blip must
    not wedge legitimate runs. remix passes True — the rolling cap IS a real
    safety bound on an autonomous write, so a DB error refuses rather than admits.
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
        # run_graph: fail open (spam bound, not the primary control). remix: fail
        # closed (the cap is a real bound on an autonomous write).
        return not fail_closed


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
    # graph_id is PINNED to this universe so the run records under it.
    token = _bind_founder_identity(_RUN_CAPABILITIES)
    try:
        # IDOR gate (Codex ADAPT 2026-08-22 #1): the run path resolves an
        # unreadable caller-supplied branch id UNCHANGED and then loads it raw
        # (_resolve_branch_id -> get_branch_definition), so a known FOREIGN-PRIVATE
        # branch id could reach execution even though read_commons_shape returns
        # "not found". Authorize READ/execute over the branch here first — under
        # the founder identity — and make a non-readable branch indistinguishable
        # from a missing one. (A public or founder-authored branch passes; a
        # foreign-private one is refused, never run.)
        from tinyassets.api.branches import _base_path, _resolve_readable_branch

        if _resolve_readable_branch(bid, str(_base_path())) is None:
            return json.dumps({"error": f"Branch '{bid}' not found."})
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
#: Hard server-side cap on a commons browse (Codex ADAPT 2026-08-22 #7): the
#: branch catalog is global and unbounded, so cap the rows we return to the agent
#: to protect its context window as the commons grows. (Cursor pagination is a
#: follow-up.)
_COMMONS_BROWSE_MAX = 50


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
            raw = _extensions_impl(
                action="list_branches",
                scope="published",
                author=(author or "").strip(),
            )
            # Hard cap the rows (Codex #7): list_branches has no server-side limit.
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
            rows = payload.get("branches") if isinstance(payload, dict) else None
            if isinstance(rows, list) and len(rows) > _COMMONS_BROWSE_MAX:
                payload["branches"] = rows[:_COMMONS_BROWSE_MAX]
                payload["count"] = _COMMONS_BROWSE_MAX
                payload["truncated"] = True
                payload["total_available"] = len(rows)
                return json.dumps(payload, default=str)
            return raw
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
    if bool(bid) == bool(aid):
        # Exactly one (Codex #7): neither, or both (which would silently pick
        # branch_id), is a caller error.
        return json.dumps({
            "error": "pass exactly one of branch_id / agent_definition_id.",
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
    """Remix (fork) a shared commons shape into a new PRIVATE branch you own,
    which you can then inspect, edit, and run.

    This copies the shape only — nodes, edges, prompts. It never copies another
    universe's private data. Any executable source-code node inherited from
    another author lands UN-approved: you must re-approve it before it can run
    (a foreign author's approval is not trusted for your executions).

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
    # Single-founder scope gate (mirrors run_graph): remix WRITES a branch. Safe
    # for one vetted founder; refuse until multi-tenant confinement is hardened,
    # even if a server was somehow started here.
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
    # Rolling write bound — FAIL CLOSED for this autonomous write (Codex #6).
    if not _engine_run_admit(fail_closed=True):
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

    # Least-privilege branch-write caps (Codex #6) — NOT the full run set. The
    # write lands under the founder identity in the shared BranchDefinition store
    # as a new PRIVATE, founder-authored shape; cross-author source-code approval
    # is stripped in the fork path so nothing inherited runs without re-approval.
    token = _bind_founder_identity(_REMIX_CAPABILITIES)
    try:
        return _impl(
            target="branch",
            operation="remix",
            payload_json=json.dumps(spec, separators=(",", ":")),
        )
    finally:
        _current_identity.reset(token)


# NOTE (Codex ADAPT 2026-08-22, finding #5): commons PUBLISH — make a shape public
# + snapshot a new best version, with the founder's "same workflow, improved,
# updated in place" model — is DEFERRED to a follow-up slice. Publishing is a
# GLOBAL write and needs a consent gate (an autonomous agent must not silently
# flip a shape public + publish without a founder consent token), which was not in
# the reviewed proposal. Build it there with the consent gate + the fork
# auto-track dependency-subscription.


# ── Brain / harness read-write loop (2026-08-22) ─────────────────────────────
# Founder vision: the universe is the agent's EDITABLE brain + project folder —
# it reads it and writes durable changes to it, and those changes are injected
# into the NEXT turn's system prompt. The READ half already works (the daemon
# rebuilds the persona system prompt each turn from the universe's OKF brain
# files — identity/founder/origin/body + soul + self-model; see
# universe_intelligence._build_persona_system_prompt). These two tools give the
# served agent the WRITE half AS AGENCY (not the post-hoc extractor):
#
#   * read_brain  — read the agent's own brain files (what IS its system prompt).
#   * write_brain — durably write learnings to those files, so they shape the
#                   next turn.
#
# Governed, NOT raw-folder (that was the PR #2475 host-RCE reject): the write
# routes through commit_learning -> apply_soul_edit, which writes ONLY the files
# whitelisted in the universe's soul.edit.md policy, under a per-universe lock
# with compare-and-swap and managed frontmatter. This slice restricts writes to
# the SELF-DESCRIPTIVE grounding files (identity/founder/origin/body) + a learned
# name + wiki canon. soul.md is deliberately EXCLUDED: its frontmatter carries
# the executable loop_branch_def_id / effect_authority (the control-plane the
# #2475 review flagged), which must never be agent-writable through here. All of
# these files are read into the prompt as TEXT and never executed, so the write
# surface carries no code-execution path — worst case the agent rewrites its own
# self-description, which is its brain, not an escalation. Pinned to the agent's
# OWN universe; allowlisted + rate-limited (fail-closed) like the other writes.
_BRAIN_SECTIONS = {
    "identity": "identity.md",
    "founder": "founder.md",
    "origin": "origin.md",
    "body": "body.md",
}


@mcp.tool
def read_brain() -> str:
    """Read YOUR OWN brain — the durable files that ARE your system prompt every
    turn: who you are, who your founder is, where you came from, and your body /
    how you work, plus your learned self-model.

    This is your project folder / harness. Whatever you save here with
    ``write_brain`` is what you wake up already knowing next turn — read it first
    so an edit builds on what's there instead of blanking it.
    """
    import json

    err = _binding_error()
    if err is not None:
        return err

    from tinyassets.api.helpers import _universe_dir
    from tinyassets.auth.middleware import _current_identity
    from tinyassets.soul_edit import SoulEditError, read_governed_files
    from tinyassets.universe_intelligence import _read_bundle_body
    from tinyassets.universe_self_model import read_self_model

    token = _bind_founder_identity()
    try:
        udir = _universe_dir(_GRAPH_ID)
        brain = {
            section: _read_bundle_body(udir, fname)
            for section, fname in _BRAIN_SECTIONS.items()
        }
        try:
            governed = set(read_governed_files(udir))
        except SoulEditError:
            governed = set()
        editable = [s for s, f in _BRAIN_SECTIONS.items() if f in governed]
        try:
            self_model = read_self_model(udir)
        except Exception:  # noqa: BLE001 - never break a read on a bad model file
            self_model = {}
        return json.dumps({
            "brain": brain,
            "self_model": self_model,
            "editable_sections": editable,
        })
    finally:
        _current_identity.reset(token)


@mcp.tool
def write_brain(
    identity: str = "",
    founder: str = "",
    origin: str = "",
    body: str = "",
    name: str = "",
    canon_json: str = "",
) -> str:
    """Durably WRITE to your OWN brain so the change is part of your system prompt
    from your NEXT turn onward. This is how you actually LEARN and evolve — not
    just recall within one conversation.

    Pass the NEW full markdown body for any section you want to update (call
    ``read_brain`` first and edit the current text; only the sections you pass
    change). ``name`` records a name you have chosen for yourself. ``canon_json``
    optionally saves durable world-facts to your universe's knowledge.

    Args:
        identity: New body for who you are.
        founder: New body for who your founder is.
        origin: New body for where you came from.
        body: New body for your form / how you work (your harness).
        name: A name you have learned or chosen for yourself.
        canon_json: Optional JSON list of durable world-facts to save to your
            universe's knowledge; each item is {"title": ..., "content": ...}
            (an optional "category" defaults to "lore").
    """
    import json

    err = _binding_error()
    if err is not None:
        return err
    from tinyassets.engine_mcp_http import run_graph_allowlist

    if _GRAPH_ID not in run_graph_allowlist():
        return json.dumps({
            "error": (
                "brain writes are not enabled for this universe yet; they are "
                "limited to a vetted founder while multi-tenant confinement is "
                "hardened."
            ),
        })
    section_values = {
        "identity": identity,
        "founder": founder,
        "origin": origin,
        "body": body,
    }
    soul: dict[str, str] = {}
    for section, fname in _BRAIN_SECTIONS.items():
        val = (section_values.get(section) or "").strip()
        if val:
            soul[fname] = val
    canon = None
    raw_canon = (canon_json or "").strip()
    if raw_canon:
        try:
            canon = json.loads(raw_canon)
        except json.JSONDecodeError:
            return json.dumps({"error": "canon_json must be valid JSON."})
        # Normalize to the _commit_canon contract: it consumes {"title","content"}.
        # Accept "body" as an alias so a natural {"title","body"} item still saves.
        if isinstance(canon, list):
            for _item in canon:
                if (
                    isinstance(_item, dict)
                    and not _item.get("content")
                    and _item.get("body")
                ):
                    _item["content"] = _item["body"]
    learned_name = (name or "").strip()
    if not (soul or learned_name or canon):
        return json.dumps({
            "error": (
                "nothing to write; pass a section body (identity/founder/origin/"
                "body), a name, or canon_json."
            ),
        })
    if not _engine_run_admit(fail_closed=True):
        return json.dumps({
            "error": (
                f"engine write rate limit reached (max {_RUN_GRAPH_RATE_MAX} per "
                f"{_RUN_GRAPH_RATE_WINDOW_S // 60}m); try again shortly."
            ),
        })

    from tinyassets.api.helpers import _universe_dir
    from tinyassets.auth.middleware import _current_identity
    from tinyassets.universe_intelligence import commit_learning

    # Least-privilege branch-write caps (the write is governed by soul.edit.md +
    # the graph pin, not ACL). commit_learning writes ONLY governed files via
    # apply_soul_edit (soul.md excluded above) + optional wiki canon.
    token = _bind_founder_identity(_REMIX_CAPABILITIES)
    try:
        udir = _universe_dir(_GRAPH_ID)
        proposed: dict = {"name": learned_name, "soul": soul}
        if canon is not None:
            proposed["canon"] = canon
        result = commit_learning(
            udir, proposed, universe_id=_GRAPH_ID, actor_id=_ACTOR_ID
        )
        if result is None:
            return json.dumps({
                "error": (
                    "nothing was persisted — the edit was empty, ungrounded, or "
                    "rejected (e.g. a section that is not governed-editable)."
                ),
            })
        return json.dumps({"ok": True, "written": result})
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
