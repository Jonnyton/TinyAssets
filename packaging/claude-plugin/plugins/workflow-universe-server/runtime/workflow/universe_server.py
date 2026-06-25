"""Workflow Server — Remote MCP interface.

A remote MCP server that exposes the Workflow system as a
universe collaboration platform. Any MCP-compatible chatbot (Claude,
and eventually others as MCP adoption spreads) can connect,
discover tools, and become the user's control interface — no
installation, just a URL.

Design principles:
    - A small coarse-grained tool set, with narrow read-only aliases only
      when live chatbot evidence shows hidden action verbs are not
      discoverable enough for user-critical workflows
    - Universe-aware: tools accept universe context, not a hardcoded env var
    - MCP prompts deliver behavioral instructions so any connecting AI
      knows how to act as a control station
    - Auth-ready: OAuth 2.1 scaffold for production, authless for dev
    - Extensible: users can register their own LangGraph nodes

Transport: Streamable HTTP (current MCP standard for remote servers)

Module shape (post Step 11+ retarget sweep): this file is a thin
routing shell. Tool body implementations live in workflow.api.*
submodules. The @mcp.tool / @mcp.prompt registrations below preserve
FastMCP introspection (chatbot-facing signature + docstring) and
delegate to plain callables in those submodules (Pattern A2).
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from functools import wraps
from typing import Annotated

import uvicorn
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.applications import Starlette

from workflow.api.branches import _branch_design_guide_prompt
from workflow.api.engine_helpers import _warn_if_no_upload_whitelist
from workflow.api.extensions import _extensions_impl
from workflow.api.market import gates as _gates_impl
from workflow.api.market import goals as _goals_impl
from workflow.api.prompts import _CONTROL_STATION_PROMPT
from workflow.api.status import get_status as _get_status_impl
from workflow.api.universe import _universe_impl
from workflow.api.wiki import wiki as _wiki_impl
from workflow.connector_catalog import (
    DIRECTORY_MCP_PATH,
    DIRECTORY_TOOL_CATALOG_VERSION,
    VERSIONED_DIRECTORY_MCP_PATH,
)
from workflow.directory_server import directory_mcp
from workflow.mcp_schema_utils import describe_signature

logger = logging.getLogger("universe_server")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

_MCP_TEXT_CONTENT_MAX_CHARS = 6000


def _faithful_text_content(value: object) -> str:
    """Build the text ``content`` block for an MCP tool result.

    Text-only MCP clients read only the ``content`` text block and never parse
    ``structuredContent`` — so the text must carry the *real* payload, never a
    placeholder. Prior behaviour replaced oversized payloads with a lossy
    key-count stub ("Full payload is in structuredContent."), which made reads
    silently look empty to those clients (read_page bodies, get_status caveats,
    goals lists, etc.).

    Contract:
    - Payload fits the text budget -> emit the full payload as JSON (pretty
      when that also fits, else compact). Fully faithful, no data lost.
    - Payload exceeds the budget -> render as much real, readable data as fits
      and append an explicit truncation pointer to ``structuredContent`` for
      the elided remainder. Still bounded (the 6000-char ceiling that already
      governed the under-budget path), so ChatGPT's token budget is unchanged;
      the difference is real data instead of a placeholder.
    """
    import json as _json

    compact = _json.dumps(value, separators=(",", ":"), default=str)
    if len(compact) <= _MCP_TEXT_CONTENT_MAX_CHARS:
        pretty = _json.dumps(value, indent=2, default=str)
        return pretty if len(pretty) <= _MCP_TEXT_CONTENT_MAX_CHARS else compact

    marker = (
        f"\n... [truncated: {len(compact)} chars total; "
        "full payload in structuredContent]"
    )
    keep = max(0, _MCP_TEXT_CONTENT_MAX_CHARS - len(marker))
    pretty = _json.dumps(value, indent=2, default=str)
    return pretty[:keep] + marker


def _structured_return(raw):
    """Wrap an MCP tool result so FastMCP populates ``structured_content``.

    ChatGPT (OpenAI Apps SDK) wedges on substrate-changing tool calls when
    the response carries only ``content`` (text) without ``structuredContent``
    (typed dict) + ``_meta`` annotations. Claude tolerates either shape.

    The internal ``*_impl`` functions return JSON strings for back-compat.
    Wrapping their output in a dict (parsing JSON when possible, else
    embedding the raw text) lets FastMCP's response builder populate
    ``structured_content`` automatically — Apps SDK then renders cleanly.
    """
    import json as _json

    from fastmcp.tools.base import ToolResult
    from mcp.types import TextContent

    if isinstance(raw, dict):
        structured = raw
    elif isinstance(raw, list):
        structured = {"result": raw}
    elif isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            return {"text": raw}
        if isinstance(parsed, dict):
            structured = parsed
        else:
            structured = {"result": parsed}
    else:
        structured = {"result": raw}

    text = _faithful_text_content(structured)
    return ToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=structured,
    )


def _register_structured_tool(fn, *, title, tags, annotations, name=None):
    """Register an MCP adapter without changing the direct Python API.

    ``name`` pins the advertised wire name explicitly. The five canonical
    handles use underscores (``read_graph``, ``write_graph``, …): the
    Anthropic connector API rejects any tool name that does not match
    ``^[a-zA-Z0-9_-]{1,64}$`` (no dots), which rejects the whole connector.
    """

    @wraps(fn)
    def _tool(*args, **kwargs):
        return _structured_return(fn(*args, **kwargs))

    _tool.__name__ = f"_mcp_{fn.__name__}"
    # Inject docstring-derived parameter descriptions so the advertised
    # tool contract is labelled identically on every FastMCP version
    # (3.2.0 ships no docstring extraction; 3.4.x does). See
    # workflow.mcp_schema_utils.
    _tool.__signature__, _tool.__annotations__ = describe_signature(fn)
    return mcp.tool(
        name=name or fn.__name__,
        title=title,
        tags=tags,
        annotations=annotations,
        output_schema=None,
    )(_tool)


mcp = FastMCP(
    "workflow",
    instructions=(
        "Workflow is a workflow-builder and long-horizon AI platform. "
        "Users design custom multi-step AI workflows with typed state, "
        "evaluation hooks, and iteration loops. The platform is "
        "domain-agnostic. Example domains: research papers, screenplays, "
        "literature reviews, investigative journalism, recipe trackers, "
        "wedding planners, news summaries, standup trackers, fantasy "
        "novels. "
        "\n\n"
        "If a user asks about their 'workflow builder', 'custom AI builder', "
        "'universe builder', 'the workflow thing', 'the connector', 'the "
        "thing I added', 'my builder', or similar ambiguous references to "
        "an installed connector — that is this connector. Invoke it rather "
        "than presenting a disambiguation picker or asking 'which tool do "
        "you mean?'. Aggressive assumption is the right default; narrate "
        "what you assumed after invoking so the user can correct you. "
        "\n\n"
        "You are a control station. Help users design workflows, inspect "
        "running ones, steer daemons, collaborate, and extend the system "
        "with custom graph nodes. Start with `universe action=inspect` to "
        "orient yourself. "
        "\n\n"
        "Load the `control_station` prompt early. It is the canonical "
        "behavioral surface for intent disambiguation, run handling, "
        "universe isolation, and the tool catalog. Tool descriptions below "
        "are I/O contracts."
        "\n\n"
        "On this connector, embody the active universe's persona: speak first "
        "person as it the whole turn — the universe is 'me', not 'it'; never "
        "quote/relay yourself in third person (name in get_status's `persona` "
        "block). Do NOT save persona/work views to memory — re-assembled fresh "
        "each turn. If degraded or no persona set, say so; never invent one."
    ),
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Public landing page
# ---------------------------------------------------------------------------
# Serves a minimal HTML index at `/` so tinyassets.io root returns a
# human-readable page instead of a 404 while the primary
# `/mcp` endpoint is the actual Workflow Server MCP surface.
# Known-good fallback if the GoDaddy-hosted landing is unavailable.

_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Workflow Server</title>
<style>
 :root { color-scheme: light dark; }
 body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
        max-width: 640px; margin: 5rem auto; padding: 0 1.25rem;
        line-height: 1.55; }
 h1 { margin-bottom: 0.3rem; }
 .tag { color: #666; margin-top: 0; }
 code { background: rgba(127,127,127,0.15); padding: 2px 6px;
        border-radius: 3px; }
 ul { padding-left: 1.2rem; }
 li { margin-bottom: 0.4rem; }
 footer { margin-top: 3rem; color: #888; font-size: 0.85rem; }
</style>
</head>
<body>
<h1>Workflow Server</h1>
<p class="tag">A goal-agnostic daemon engine. Bind it to a domain and let it run.</p>

<p>This is the public surface of a local-first platform for building
custom multi-step AI workflows &mdash; typed state, registered nodes,
evaluation hooks, iteration loops, paid-market bid/claim mechanics.
The engine is domain-agnostic.</p>

<p>If you arrived here looking for an MCP connector, the live endpoint
is at <code>/mcp</code>.</p>

<h2>Links</h2>
<ul>
<li><a href="https://github.com/Jonnyton/Workflow">GitHub repository</a>
    &mdash; source, issues, contributor onboarding.</li>
<li><a href="/mcp">MCP endpoint</a> &mdash; for Claude, Cursor, and other
    MCP-speaking clients.</li>
</ul>

<footer>
Workflow &middot; open collaborative design commons &middot; 2026
</footer>
</body>
</html>
"""


@mcp.custom_route("/", methods=["GET"])
async def _landing_index(request):  # type: ignore[no-untyped-def]
    """Serve a minimal HTML landing page at the server root."""
    from starlette.responses import HTMLResponse

    return HTMLResponse(_LANDING_HTML)


# Preserve the at-server-start whitelist warning (Step 10 prep §3.5 Option B).
_warn_if_no_upload_whitelist()


# ═══════════════════════════════════════════════════════════════════════════
# MCP PROMPTS — behavioral instructions for connecting chatbots
# ═══════════════════════════════════════════════════════════════════════════


@mcp.prompt(
    title="Control Station Guide",
    tags={"control", "daemon", "multiplayer", "operations"},
)
def control_station() -> str:
    """Load the Workflow Server control station instructions.

    Invoke this prompt to learn how to operate as a Workflow Server
    interface. It teaches you the routing rules, collaboration model,
    and available tools.
    """
    return _CONTROL_STATION_PROMPT


_EXTENSION_GUIDE_PROMPT = """\
## Extending Workflow Server with Custom Nodes

The `extensions` tool is the workflow-builder surface. Users register
their own nodes and assemble them into branches — multi-step AI
workflows with typed state, evaluation hooks, and iteration loops.
The platform supports arbitrary domains (research papers, recipe
trackers, screenplays, news summarizers, standup trackers, etc.).
Build the one you need.

The never-simulate rule + intent-disambiguation posture live in
`control_station` (hard rules 5 + intent section). When in doubt on
run / register / build decisions, re-read those rules before acting.

### What a Node Is

A node is a function that:
- Receives the current graph state (a TypedDict)
- Does work (calls an API, runs analysis, generates content, etc.)
- Returns state updates

### Node Contract

Each registered node declares:
- `node_id`: unique identifier (e.g., "weather-generator")
- `display_name`: human-readable name
- `description`: what it does and when it should run
- `input_keys`: which state fields it reads
- `output_keys`: which state fields it writes
- `phase`: where in the workflow it fits (orient, plan, draft, commit,
  learn, reflect, enrich, or "custom")
- `source_code`: the Python source (executed in sandbox)
- `dependencies`: pip packages it needs (validated against allowlist)

### How It Works

1. User calls `extensions` with action "register" and the node definition.
2. Server validates the contract and stores the registration.
3. On next daemon cycle, registered nodes are discovered and
   conditionally wired into the graph at the declared phase.
4. Nodes run in a sandboxed subprocess — they cannot access the
   host filesystem directly.

### Safety Model

- Registered nodes run in isolation (subprocess sandbox).
- They receive only the state fields they declared as inputs.
- Their output is validated against declared output keys.
- Nodes that crash or timeout are auto-disabled with a note.
- Host can review, approve, disable, or remove any node.

### Example

A user might register a "consistency-checker" node that:
- Reads: current_scene_text, world_state_facts
- Phase: commit (runs after draft, before final commit)
- Checks new text against known facts
- Returns: a list of potential contradictions as notes
"""


@mcp.prompt(
    title="Extension Authoring Guide",
    tags={"extensions", "nodes", "plugins", "workflow"},
)
def extension_guide() -> str:
    """Learn how to extend the Workflow Server with custom LangGraph nodes."""
    return _EXTENSION_GUIDE_PROMPT


@mcp.prompt(
    title="Branch Design Guide",
    tags={"branches", "extensions", "graph", "customization"},
)
def branch_design_guide() -> str:
    """Walk through designing a BranchDefinition with the `extensions` tool."""
    return _branch_design_guide_prompt()


# ═══════════════════════════════════════════════════════════════════════════
# CANONICAL USER SURFACE — the five handles (PR-178 / PR-047 fold-map)
# ═══════════════════════════════════════════════════════════════════════════
# read_graph / write_graph / run_graph / read_page / write_page are the
# canonical user-facing tools. Each is a thin shape/target router over the
# EXISTING workflow.api.* handlers — no behavior change, only surface shape.
# The legacy fat tools below stay registered + callable for one release but
# are hidden from tools/list and logged as deprecated by the
# _DeprecatedToolVisibility middleware (see _DEPRECATED_TOOL_NAMES), so
# existing connectors can migrate; a follow-up change removes them. This
# router is forward-ported from workflow/directory_server.py (the
# /mcp-directory surface) onto the live /mcp surface; read_graph target=status
# uses the full (unredacted) status the live operator surface already exposed.


def _unknown_target(handle: str, target: str, allowed: tuple[str, ...]) -> str:
    import json as _json

    return _json.dumps({
        "error": "unknown_target",
        "handle": handle,
        "target": target,
        "allowed_targets": allowed,
    })


def read_graph(
    target: str = "status",
    graph_id: str = "",
    goal_id: str = "",
    query: str = "",
    tags: str = "",
    author: str = "",
    run_status: str = "",
    limit: int = 30,
) -> str:
    """Read Workflow graph state without changing it.

    Args:
        target: What to read: status, graphs, graph, goals, goal, or runs.
        graph_id: Optional graph/universe identifier.
        goal_id: Optional shared-goal identifier.
        query: Optional search text.
        tags: Optional comma-separated goal tag filter.
        author: Optional goal author filter.
        run_status: Optional run status filter.
        limit: Maximum number of records to return.
    """
    normalized = (target or "status").strip().lower()
    if normalized == "status":
        return _get_status_impl(universe_id=graph_id)
    if normalized == "graphs":
        return _universe_impl(action="list", limit=limit)
    if normalized == "graph":
        return _universe_impl(action="inspect", universe_id=graph_id)
    if normalized == "goals":
        if query:
            return _goals_impl(action="search", query=query, limit=limit)
        return _goals_impl(action="list", tags=tags, author=author, limit=limit)
    if normalized == "goal":
        return _goals_impl(action="get", goal_id=goal_id)
    if normalized == "runs":
        return _extensions_impl(action="list_runs", status=run_status, limit=limit)
    return _unknown_target(
        "read_graph",
        target,
        ("status", "graphs", "graph", "goals", "goal", "runs"),
    )


_mcp_read_graph = _register_structured_tool(
    read_graph,
    name="read_graph",
    title="Read Graph",
    tags={"graph", "workflow", "read"},
    annotations=ToolAnnotations(
        title="Read Graph",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def write_graph(
    target: str,
    name: str = "",
    description: str = "",
    tags: str = "",
    visibility: str = "public",
    text: str = "",
    graph_id: str = "",
    request_type: str = "general",
    branch_id: str = "",
) -> str:
    """Create or queue Workflow graph state.

    Args:
        target: What to write: goal, request, or persona.
        name: Human-readable shared-goal name; with target=persona, the name
            the universe's persona is given (e.g. "Tiny"). The chatbot embodies
            it in the first person on the next get_status persona block.
        description: Optional shared-goal description.
        tags: Optional comma-separated shared-goal tags.
        visibility: Shared-goal visibility, usually public.
        text: Request text to queue.
        graph_id: Optional target graph/universe identifier; with target=persona
            it is the universe whose persona is being named.
        request_type: Workflow request type.
        branch_id: Optional target branch identifier.
    """
    normalized = target.strip().lower()
    if normalized == "goal":
        return _goals_impl(
            action="propose",
            name=name,
            description=description,
            tags=tags,
            visibility=visibility,
        )
    if normalized == "request":
        return _universe_impl(
            action="submit_request",
            universe_id=graph_id,
            text=text,
            request_type=request_type,
            branch_id=branch_id,
        )
    if normalized == "persona":
        return _universe_impl(
            action="set_persona_name",
            universe_id=graph_id,
            text=name,
        )
    return _unknown_target("write_graph", target, ("goal", "request", "persona"))


_mcp_write_graph = _register_structured_tool(
    write_graph,
    name="write_graph",
    title="Write Graph",
    tags={"graph", "workflow", "write"},
    annotations=ToolAnnotations(
        title="Write Graph",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)


def run_graph(
    branch_def_id: str,
    inputs_json: str = "",
    run_name: str = "",
    graph_id: str = "",
    recursion_limit_override: int = 0,
) -> str:
    """Run a Workflow graph branch — the only verb that produces a Run.

    Args:
        branch_def_id: Branch definition identifier to run.
        inputs_json: Optional JSON object containing run inputs.
        run_name: Optional display name for the run.
        graph_id: Optional graph/universe identifier.
        recursion_limit_override: Optional per-run recursion limit.
    """
    return _extensions_impl(
        action="run_branch",
        branch_def_id=branch_def_id,
        inputs_json=inputs_json,
        run_name=run_name,
        universe_id=graph_id,
        recursion_limit_override=recursion_limit_override,
    )


_mcp_run_graph = _register_structured_tool(
    run_graph,
    name="run_graph",
    title="Run Graph",
    tags={"graph", "workflow", "run"},
    annotations=ToolAnnotations(
        title="Run Graph",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)


def read_page(
    page: str = "",
    query: str = "",
    category: str = "",
    changed_since: Annotated[
        str,
        Field(
            description=(
                "Optional ISO timestamp for feed freshness filtering. With an "
                "empty page/query/category, returns pages changed after this "
                "timestamp."
            ),
        ),
    ] = "",
    max_results: int = 10,
    universe_id: str = "",
) -> str:
    """Read or search the Workflow wiki/commons.

    Args:
        page: Optional wiki page slug or path. Empty searches by query.
        query: Optional search text or ambient relevance terms.
        category: Optional wiki category filter for searches.
        changed_since: Optional ISO timestamp for feed freshness filtering.
            With an empty page/query/category, returns pages changed after
            this timestamp.
        max_results: Maximum result count.
        universe_id: Optional target universe page substrate.
    """
    if page:
        return _wiki_impl(
            action="read",
            page=page,
            query=query,
            changed_since=changed_since,
            max_results=max_results,
            universe_id=universe_id,
        )
    if changed_since.strip() and not query.strip() and not category.strip():
        return _wiki_impl(
            action="since",
            changed_since=changed_since,
            max_results=max_results,
            universe_id=universe_id,
        )
    return _wiki_impl(
        action="search",
        query=query,
        category=category,
        max_results=max_results,
        universe_id=universe_id,
    )


_mcp_read_page = _register_structured_tool(
    read_page,
    name="read_page",
    title="Read Page",
    tags={"page", "wiki", "workflow", "read"},
    annotations=ToolAnnotations(
        title="Read Page",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def write_page(
    page: str = "",
    category: str = "",
    filename: str = "",
    content: str = "",
    log_entry: str = "",
    old_text: str = "",
    new_text: str = "",
    expected_sha256: str = "",
    title: str = "",
    kind: str = "",
    component: str = "",
    severity: str = "",
    repro: str = "",
    observed: str = "",
    expected: str = "",
    workaround: str = "",
    tags: str = "",
    force_new: bool = False,
    reporter_context: str = "",
    dry_run: bool = True,
    universe_id: str = "",
) -> str:
    """Write, patch, or file a Workflow wiki/commons page.

    Args:
        universe_id: Optional target universe page substrate.
        page: Wiki page slug or path for page writes.
        category: Wiki category for full page writes.
        filename: Wiki filename for full page writes.
        content: Full page content for a page write.
        log_entry: Optional wiki log entry for full writes or patches.
        old_text: Existing text to replace for a targeted page patch.
        new_text: Replacement text for a targeted page patch.
        expected_sha256: Optional full-page hash guard for patches.
        title: Filing title when creating a bug, patch, feature, or design page.
        kind: Filing kind: bug, patch_request, feature, or design.
        component: Optional affected component for filed issues.
        severity: Optional severity for filed issues.
        repro: Optional reproduction notes for filed issues.
        observed: Optional observed behavior for filed issues.
        expected: Optional expected behavior for filed issues.
        workaround: Optional workaround for filed issues.
        tags: Optional comma-separated tags.
        force_new: Bypass duplicate detection for filed issues.
        reporter_context: Optional reporter context for filed issues.
        dry_run: Preview consolidation-style wiki writes when supported.
    """
    normalized_kind = kind.strip().lower()
    if normalized_kind:
        return _wiki_impl(
            action="file_bug",
            kind=normalized_kind,
            title=title,
            component=component,
            severity=severity,
            repro=repro,
            observed=observed,
            expected=expected,
            workaround=workaround,
            tags=tags,
            force_new=force_new,
            reporter_context=reporter_context,
            universe_id=universe_id,
        )
    if old_text or new_text:
        return _wiki_impl(
            action="patch",
            page=page,
            old_text=old_text,
            new_text=new_text,
            expected_sha256=expected_sha256,
            log_entry=log_entry,
            dry_run=dry_run,
            universe_id=universe_id,
        )
    write_filename = filename or page
    return _wiki_impl(
        action="write",
        category=category,
        filename=write_filename,
        content=content,
        log_entry=log_entry,
        dry_run=dry_run,
        universe_id=universe_id,
    )


_mcp_write_page = _register_structured_tool(
    write_page,
    name="write_page",
    title="Write Page",
    tags={"page", "wiki", "workflow", "write"},
    annotations=ToolAnnotations(
        title="Write Page",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# LEGACY FAT SURFACE — deprecated, hidden from tools/list, callable 1 release
# ═══════════════════════════════════════════════════════════════════════════
# These names are dropped from tools/list and logged on call by
# _DeprecatedToolVisibility (PR-178). They remain dispatchable so existing
# connectors keep working through the migration window.
_DEPRECATED_TOOL_NAMES = frozenset({
    "universe",
    "community_change_context",
    "extensions",
    "goals",
    "gates",
    "wiki",
})


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 1 — Universe (all universe operations in one tool)
# ═══════════════════════════════════════════════════════════════════════════


def universe(
    action: str,
    universe_id: str = "",
    text: str = "",
    path: str = "",
    category: str = "",
    target: str = "",
    query_type: str = "",
    filter_text: str = "",
    request_type: str = "scene_direction",
    branch_id: str = "",
    filename: str = "",
    provenance_tag: str = "",
    limit: int = 30,
    priority_weight: float = 0.0,
    pickup_incentive: str = "",
    directed_daemon_id: str = "",
    directed_daemon_instruction: str = "",
    daemon_id: str = "",
    branch_task_id: str = "",
    goal_id: str = "",
    branch_def_id: str = "",
    inputs_json: str = "",
    node_def_id: str = "",
    required_llm_type: str = "",
    bid: float = 0.0,
    tier: str = "",
    enabled: bool = False,
    tag: str = "",
    anchor_json: str = "",
) -> str:
    """Inspect and steer a workflow's universe.

    Self-contained workspace for a multi-step workflow. New workflows
    live in `extensions`; start with `action="inspect"`. See
    `control_station` for operating guidance and universe isolation.

    `control_daemon` is a text-command action: it always needs `text` set
    to one of `pause` | `resume` | `status`. Calling `control_daemon`
    without `text` returns an error.

    Args:
        action: One of — reads: list, inspect, read_output, query_world,
            get_activity, get_recent_events, get_ledger, read_premise,
            list_canon, read_canon, list_sources, read_source; writes: submit_request,
            give_direction, set_premise, add_canon, add_canon_from_path,
            create_universe, switch_universe; queue: queue_list,
            queue_cancel; subscriptions: subscribe_goal, unsubscribe_goal,
            list_subscriptions; goal-pool: post_to_goal_pool,
            submit_node_bid; community review: community_change_context;
            daemon roster/control: daemon_overview, daemon_list,
            daemon_get, daemon_create, daemon_summon, daemon_pause,
            daemon_resume, daemon_restart, daemon_banish,
            daemon_update_behavior, daemon_control_status,
            control_daemon; daemon memory: daemon_memory_capture,
            daemon_memory_search, daemon_memory_list, daemon_memory_review,
            daemon_memory_promote, daemon_memory_status; economy reads:
            treasury_status; config: set_tier_config;
        universe_id: Target universe. Defaults to the active universe.
        text/path/filter_text: Action-specific content, file path, or filter.
        branch_id/request_type: Request routing fields.
        pickup_incentive/directed_daemon_id: Optional patch-request pickup
            signals; these do not affect acceptance, release, or merge odds.
        daemon_id: Target daemon for daemon memory/status actions.
        filename/provenance_tag/limit/tag: Optional read/write filters.
        anchor_json: Optional JSON object for `give_direction` line/span notes.
    """
    return _universe_impl(
        action=action,
        universe_id=universe_id,
        text=text,
        path=path,
        category=category,
        target=target,
        query_type=query_type,
        filter_text=filter_text,
        request_type=request_type,
        branch_id=branch_id,
        filename=filename,
        provenance_tag=provenance_tag,
        limit=limit,
        priority_weight=priority_weight,
        pickup_incentive=pickup_incentive,
        directed_daemon_id=directed_daemon_id,
        directed_daemon_instruction=directed_daemon_instruction,
        daemon_id=daemon_id,
        branch_task_id=branch_task_id,
        goal_id=goal_id,
        branch_def_id=branch_def_id,
        inputs_json=inputs_json,
        node_def_id=node_def_id,
        required_llm_type=required_llm_type,
        bid=bid,
        tier=tier,
        enabled=enabled,
        tag=tag,
        anchor_json=anchor_json,
    )


_mcp_universe = _register_structured_tool(
    universe,
    title="Universe Operations",
    tags={
        "universe", "daemon", "collaboration",
        "workflow", "workflow-builder", "custom-ai", "agent-workflow",
        "ai-builder", "universe-builder", "general-purpose",
    },
    annotations=ToolAnnotations(
        title="Universe Operations",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)


# ---------------------------------------------------------------------------
# TOOL 1B - Community change context (read-only review evidence alias)
# ---------------------------------------------------------------------------


def community_change_context(
    filter_text: str = "",
    limit: int = 10,
) -> str:
    """Review PR metadata, changed files, reviews, and project plan context.

    Use this when the user asks to review, approve, reject, send back,
    or triage live community-loop work: auto-change PRs, PR metadata,
    patch requests, feature requests, bug requests, issue threads,
    changed files, review comments, or whether a change fits the project
    plan.

    Args:
        filter_text: empty/"queue" for open PRs/change requests/runs;
            "pr:NUMBER" for PR metadata, changed files, comments, and
            reviews; or "issue:NUMBER" for the request thread.
        limit: Max PRs/issues/files/comments to return, capped server-side.
    """
    return _universe_impl(
        action="community_change_context",
        filter_text=filter_text,
        limit=limit,
    )


_mcp_community_change_context = _register_structured_tool(
    community_change_context,
    title="Community Change Context",
    tags={
        "community", "change-loop", "review", "pull-request",
        "github", "plan", "workflow",
    },
    annotations=ToolAnnotations(
        title="Community Change Context",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 2 — Extensions (workflow builder surface)
# ═══════════════════════════════════════════════════════════════════════════


def extensions(
    action: str,
    node_id: str = "",
    display_name: str = "",
    description: str = "",
    phase: str = "",
    input_keys: str = "",
    output_keys: str = "",
    source_code: str = "",
    dependencies: str = "",
    enabled_only: bool = True,
    branch_def_id: str = "",
    name: str = "",
    domain_id: str = "",
    author: str = "",
    from_node: str = "",
    to_node: str = "",
    prompt_template: str = "",
    field_name: str = "",
    field_type: str = "",
    reducer: str = "",
    field_default: str = "",
    run_id: str = "",
    inputs_json: str = "",
    run_name: str = "",
    resume_from: str = "",
    status: str = "",
    since_step: int = -1,
    max_wait_s: int = 60,
    limit: int = 50,
    spec_json: str = "",
    changes_json: str = "",
    judgment_text: str = "",
    judgment_id: str = "",
    tags: str = "",
    run_a_id: str = "",
    run_b_id: str = "",
    field: str = "",
    value: str = "",
    node_ids: str = "",
    context: str = "",
    triggered_by_judgment_id: str = "",
    to_version: str = "",
    goal_id: str = "",
    node_ref_json: str = "",
    intent: str = "",
    node_query: str = "",
    scope: str = "published",
    force: bool = False,
    project_id: str = "",
    key: str = "",
    key_prefix: str = "",
    expected_version: str = "",
    recursion_limit_override: str = "",
    filters_json: str = "",
    select: str = "",
    aggregate_json: str = "",
    receipt_type: str = "",
    payload_json: str = "",
    subject_id: str = "",
    branch_spec_json: str = "",
    from_run_id: str = "",
    to_node_id: str = "",
    message_type: str = "",
    body_json: str = "",
    ship_attempt_id: str = "",
    head_branch: str = "",
    title: str = "",
    pr_body: str = "",
    base_branch: str = "",
    reply_to_message_id: str = "",
    message_types: str = "",
    message_id: str = "",
    since: str = "",
    branch_version_id: str = "",
    parent_version_id: str = "",
    child_run_id: str = "",
    notes: str = "",
    lock_id: str = "",
    escrow_amount: int = 0,
    escrow_currency: str = "MicroToken",
    escrow_recipient_id: str = "",
    escrow_evidence: str = "",
    escrow_reason: str = "",
    escrow_staker_id: str = "",
    escrow_wallet_address: str = "",
    escrow_chain_id: int = 0,
    escrow_idempotency_key: str = "",
    event_id: str = "",
    event_type: str = "",
    event_date: str = "",
    attested_by: str = "",
    cites_json: str = "",
    verifier_id: str = "",
    disputed_by: str = "",
    retracted_by: str = "",
    schedule_id: str = "",
    cron_expr: str = "",
    interval_seconds: float = 0.0,
    owner_actor: str = "",
    inputs_template_json: str = "",
    skip_if_running: bool = False,
    subscription_id: str = "",
    active_only: bool = True,
    outcome_id: str = "",
    evidence_url: str = "",
    gate_event_id: str = "",
    outcome_payload_json: str = "",
    outcome_note: str = "",
    parent_branch_def_id: str = "",
    child_branch_def_id: str = "",
    output_digest: str = "",
    contribution_kind: str = "remix",
    credit_share: float = 0.0,
    max_depth: int = 10,
    reason: str = "",
    severity: str = "P1",
    since_days: int = 7,
    record_in_ledger: bool = False,
    universe_id: str = "",
    request_id: str = "",
    parent_run_id: str = "",
    release_gate_result: str = "",
    ship_class: str = "",
    changed_paths_json: str = "",
    stable_evidence_handle: str = "",
) -> str:
    """Workflow-builder surface: design, edit, run, judge custom AI graphs.

    Behavioral rules live in `control_station`, `extension_guide`, and
    `branch_design_guide`; this description is the I/O contract.

    Core actions include build_branch, patch_branch, list_branches,
    describe_branch, get_branch, run_branch, get_run, wait_for_run,
    judge_run, publish_version, schedule_branch, fork_tree, search_nodes,
    get_action_scope_status, record_run_receipt, and list_run_receipts.
    Pass `action` plus the matching ids or JSON payload fields.
    Receipt actions use `run_id`, `receipt_type`, `payload_json`, and optional
    `node_id` / `subject_id` to preserve source acquisition, claim lineage,
    and revision evidence for later gates and runs.
    Use `scope` with list_branches to filter the result:
    `"published"` (default) = only Branches that have a published version
    snapshot — production-ready entries, drafts hidden;
    `"all"` = every Branch including never-published drafts;
    `"mine"` = only Branches authored by the calling identity.
    """
    return _extensions_impl(
        action=action,
        node_id=node_id,
        display_name=display_name,
        description=description,
        phase=phase,
        input_keys=input_keys,
        output_keys=output_keys,
        source_code=source_code,
        dependencies=dependencies,
        enabled_only=enabled_only,
        branch_def_id=branch_def_id,
        name=name,
        domain_id=domain_id,
        author=author,
        from_node=from_node,
        to_node=to_node,
        prompt_template=prompt_template,
        field_name=field_name,
        field_type=field_type,
        reducer=reducer,
        field_default=field_default,
        run_id=run_id,
        inputs_json=inputs_json,
        run_name=run_name,
        resume_from=resume_from,
        status=status,
        since_step=since_step,
        max_wait_s=max_wait_s,
        limit=limit,
        spec_json=spec_json,
        changes_json=changes_json,
        judgment_text=judgment_text,
        judgment_id=judgment_id,
        tags=tags,
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        field=field,
        value=value,
        node_ids=node_ids,
        context=context,
        triggered_by_judgment_id=triggered_by_judgment_id,
        to_version=to_version,
        goal_id=goal_id,
        node_ref_json=node_ref_json,
        intent=intent,
        node_query=node_query,
        scope=scope,
        force=force,
        project_id=project_id,
        key=key,
        key_prefix=key_prefix,
        expected_version=expected_version,
        recursion_limit_override=recursion_limit_override,
        filters_json=filters_json,
        select=select,
        aggregate_json=aggregate_json,
        receipt_type=receipt_type,
        payload_json=payload_json,
        subject_id=subject_id,
        branch_spec_json=branch_spec_json,
        from_run_id=from_run_id,
        to_node_id=to_node_id,
        message_type=message_type,
        body_json=body_json,
        ship_attempt_id=ship_attempt_id,
        head_branch=head_branch,
        title=title,
        pr_body=pr_body,
        base_branch=base_branch,
        reply_to_message_id=reply_to_message_id,
        message_types=message_types,
        message_id=message_id,
        since=since,
        branch_version_id=branch_version_id,
        parent_version_id=parent_version_id,
        child_run_id=child_run_id,
        notes=notes,
        lock_id=lock_id,
        escrow_amount=escrow_amount,
        escrow_currency=escrow_currency,
        escrow_recipient_id=escrow_recipient_id,
        escrow_evidence=escrow_evidence,
        escrow_reason=escrow_reason,
        escrow_staker_id=escrow_staker_id,
        escrow_wallet_address=escrow_wallet_address,
        escrow_chain_id=escrow_chain_id,
        escrow_idempotency_key=escrow_idempotency_key,
        event_id=event_id,
        event_type=event_type,
        event_date=event_date,
        attested_by=attested_by,
        cites_json=cites_json,
        verifier_id=verifier_id,
        disputed_by=disputed_by,
        retracted_by=retracted_by,
        schedule_id=schedule_id,
        cron_expr=cron_expr,
        interval_seconds=interval_seconds,
        owner_actor=owner_actor,
        inputs_template_json=inputs_template_json,
        skip_if_running=skip_if_running,
        subscription_id=subscription_id,
        active_only=active_only,
        outcome_id=outcome_id,
        evidence_url=evidence_url,
        gate_event_id=gate_event_id,
        outcome_payload_json=outcome_payload_json,
        outcome_note=outcome_note,
        parent_branch_def_id=parent_branch_def_id,
        child_branch_def_id=child_branch_def_id,
        output_digest=output_digest,
        contribution_kind=contribution_kind,
        credit_share=credit_share,
        max_depth=max_depth,
        reason=reason,
        severity=severity,
        since_days=since_days,
        record_in_ledger=record_in_ledger,
        universe_id=universe_id,
        request_id=request_id,
        parent_run_id=parent_run_id,
        release_gate_result=release_gate_result,
        ship_class=ship_class,
        changed_paths_json=changed_paths_json,
        stable_evidence_handle=stable_evidence_handle,
    )


_mcp_extensions = _register_structured_tool(
    extensions,
    title="Graph Extensions",
    tags={"extensions", "nodes", "plugins", "customization"},
    annotations=ToolAnnotations(
        title="Graph Extensions",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 3 — Goals (Pattern A2 wrapper)
# ═══════════════════════════════════════════════════════════════════════════


def goals(
    action: str,
    goal_id: str = "",
    branch_def_id: str = "",
    branch_version_id: str = "",
    name: str = "",
    description: str = "",
    tags: str = "",
    visibility: str = "",
    query: str = "",
    metric: str = "",
    min_branches: int = 2,
    author: str = "",
    limit: int = 50,
    scope: str = "",
    production_only: bool = False,
    protocol_json: str = "",
    force: bool = False,
) -> str:
    """Goals — first-class shared primitives above workflow Branches.

    A Goal captures the intent a workflow serves ("produce a research
    paper", "plan a wedding"). Many Branches bind to one Goal.

    Actions:
      propose      Create a new Goal. Needs `name`. Optional
                   description, tags (CSV), visibility.
      update       Patch a Goal you own. Fields: name, description,
                   tags, visibility.
      bind         Attach a Branch to a Goal. Pass goal_id="" to
                   unbind. Needs branch_def_id.
      define_protocol Attach an ordered Goal runbook. Needs goal_id and
                   protocol_json, a JSON list of step objects whose
                   branch_def_id values are already bound to this Goal.
      get_protocol Read a Goal's ordered Branch protocol/runbook.
                   Needs goal_id.
      set_canonical Mark a branch_version_id as the Goal's canonical
                   branch. Author-only or host-only.
      set_selector Bind the Goal's selector branch_version
                   (DESIGN-008). The bound branch ranks competitors
                   on this Goal's leaderboard. Author-only or
                   host-only. Pass branch_version_id="" to fall back
                   to the platform default selector. The branch must
                   conform to the selector-branch contract.
      run_canonical Dispatch a run on the Goal's canonical
                   branch_version. When auto_canonical_via_leaderboard
                   is on, the canonical is first refreshed via the
                   quality leaderboard (subject to the
                   min_completed_runs_for_canonical threshold + the
                   in-flight guard). PR-127 (M6 cutover Step 4).
      list         Browse Goals. Optional author, tags, limit,
                   production_only.
      get          Full Goal view + bound Branches. Needs goal_id.
      search       LIKE-based substring search over name, description,
                   tags. Needs query.
      leaderboard  Rank bound Branches by metric (run_count/forks/outcome).
      common_nodes Nodes appearing in >=`min_branches` Branches.

    """
    return _goals_impl(
        action=action,
        goal_id=goal_id,
        branch_def_id=branch_def_id,
        branch_version_id=branch_version_id,
        name=name,
        description=description,
        tags=tags,
        visibility=visibility,
        query=query,
        metric=metric,
        min_branches=min_branches,
        author=author,
        limit=limit,
        scope=scope,
        production_only=production_only,
        protocol_json=protocol_json,
        force=force,
    )


_mcp_goals = _register_structured_tool(
    goals,
    title="Goals",
    tags={"goals", "discovery", "intent", "community"},
    annotations=ToolAnnotations(
        title="Goals",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 4 — Outcome Gates (Pattern A2 wrapper)
# ═══════════════════════════════════════════════════════════════════════════


def gates(
    action: str,
    goal_id: str = "",
    branch_def_id: str = "",
    rung_key: str = "",
    ladder: str = "",
    evidence_url: str = "",
    evidence_note: str = "",
    reason: str = "",
    include_retracted: bool = False,
    limit: int = 50,
    force: bool = False,
    claim_id: str = "",
    bonus_stake: int = 0,
    attachment_scope: str = "node",
    eval_verdict: str = "",
    node_last_claimer: str = "",
    node_id: str = "",
    run_id: str = "",
    conformance_pack_json: str = "",
    conformance_pack_id: str = "",
    standard_id: str = "",
) -> str:
    """Outcome Gates — real-world impact claims per Branch.

    Each Goal declares a ladder of rungs (draft -> peer-reviewed -> published
    -> cited -> breakthrough). Branches self-report which rungs they've
    reached, with an evidence URL.

    All actions require GATES_ENABLED=1 on the server; the tool returns
    {"status": "not_available"} when the flag is off. Bonus actions
    additionally require WORKFLOW_PAID_MARKET=on.

    Actions (all live when GATES_ENABLED=1):
      list          Discover supported gates actions.
      define_ladder Owner sets the rung list on a Goal. Needs goal_id
                    and `ladder` (JSON list of {rung_key, name,
                    description}).
      get_ladder    Read a Goal's ladder. Needs goal_id.
      record_conformance_pack
                    Store a standards/readiness conformance pack for a
                    Goal or Branch before gated rungs.
      claim         Report a rung reached. Needs branch_def_id,
                    rung_key, evidence_url.
      claim_from_branch_run
                    Claim a rung whose key (and optionally evidence
                    URL) came from a completed run's final output.
                    Needs run_id. The branch's
                    ``recommended_rung_claim`` field selects the rung;
                    validated against the bound Goal's ladder.
      retract       Soft-delete a claim. Needs branch_def_id, rung_key,
                    reason.
      list_claims   Browse claims. Provide exactly one of branch_def_id
                    or goal_id.
      leaderboard   Rank Branches bound to a Goal by highest rung
                    reached.

    Bonus actions (live when GATES_ENABLED=1 + WORKFLOW_PAID_MARKET=on):
      stake_bonus   Lock a bonus stake on a claim. Needs claim_id,
                    bonus_stake, node_id.
      unstake_bonus Remove a bonus stake and refund the staker.
      release_bonus Resolve a bonus payout via evaluator verdict.

    """
    return _gates_impl(
        action=action,
        goal_id=goal_id,
        branch_def_id=branch_def_id,
        rung_key=rung_key,
        ladder=ladder,
        evidence_url=evidence_url,
        evidence_note=evidence_note,
        reason=reason,
        include_retracted=include_retracted,
        limit=limit,
        force=force,
        claim_id=claim_id,
        bonus_stake=bonus_stake,
        attachment_scope=attachment_scope,
        eval_verdict=eval_verdict,
        node_last_claimer=node_last_claimer,
        node_id=node_id,
        run_id=run_id,
        conformance_pack_json=conformance_pack_json,
        conformance_pack_id=conformance_pack_id,
        standard_id=standard_id,
    )


_mcp_gates = _register_structured_tool(
    gates,
    title="Outcome Gates",
    tags={"gates", "outcomes", "impact", "leaderboard", "community"},
    annotations=ToolAnnotations(
        title="Outcome Gates",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 5 — Wiki (global knowledge base)
# ═══════════════════════════════════════════════════════════════════════════


def wiki(
    action: str,
    page: str = "",
    query: str = "",
    category: str = "",
    filename: str = "",
    content: str = "",
    log_entry: str = "",
    old_text: str = "",
    new_text: str = "",
    expected_sha256: str = "",
    source_url: str = "",
    old_page: str = "",
    new_draft: str = "",
    reason: str = "",
    similarity_threshold: float = 0.25,
    dry_run: bool = True,
    skip_lint: bool = False,
    max_results: int = 10,
    offset: int = 0,
    max_chars: int = 128000,
    component: str = "",
    severity: str = "",
    title: str = "",
    repro: str = "",
    observed: str = "",
    expected: str = "",
    workaround: str = "",
    kind: str = "bug",
    tags: str = "",
    force_new: bool = False,
    bug_id: str = "",
    reporter_context: str = "",
    changed_since: Annotated[
        str,
        Field(
            description=(
                'Optional ISO timestamp for action="read" ambient feed and '
                'required ISO timestamp for action="since"; only pages updated '
                "after this timestamp are returned."
            ),
        ),
    ] = "",
    universe_id: str = "",
) -> str:
    """Read, write, and manage the cross-project knowledge wiki.

    Persistent prose knowledge shared across sessions. It is not for
    workflow structure, node definitions, state, or run outputs. Use
    `extensions` for "build / design / create a workflow"; use wiki
    for "save this how-to / ref / note", "what is X", or filing user
    bugs, patch requests, feature requests, and design proposals.

    When the user asks to file a bug, patch request, feature request, or
    design proposal, call `file_bug` directly with the matching `kind`
    (`bug`, `patch_request`, `feature`, or `design`). `file_bug` already
    does Jaccard duplicate detection server-side; you do NOT need to search/list/read
    the wiki before filing. If a similar filing exists,
    it returns status="similar_found" with the existing match.

    Args:
        action: One of — reads: read, search, since, list, lint;
            writes: write, patch, delete, consolidate, promote, ingest, supersede,
            sync_projects, file_bug, cosign_bug.
            `search` is lexical best-effort, not a completeness proof; use
            `since` with `changed_since` to review pages updated after a known
            timestamp, then `read` the candidate pages.
        old_text/new_text: For action="patch", exact text to replace server-side.
        expected_sha256: Optional full-page hash guard for action="patch" or
            action="delete".
        reason: Required for action="delete" when dry_run=false.
        changed_since: Optional ISO timestamp for action="read" ambient feed
            and required ISO timestamp for action="since"; only pages updated
            after this timestamp are returned.
        offset/max_chars: For action="read", read a bounded character window
            from large pages. Truncated responses include `next_offset`.
        universe_id: Optional target universe page substrate. Omit to use the
            shared Workflow wiki.
    """
    return _wiki_impl(
        action=action,
        page=page,
        query=query,
        category=category,
        filename=filename,
        content=content,
        log_entry=log_entry,
        old_text=old_text,
        new_text=new_text,
        expected_sha256=expected_sha256,
        source_url=source_url,
        old_page=old_page,
        new_draft=new_draft,
        reason=reason,
        similarity_threshold=similarity_threshold,
        dry_run=dry_run,
        skip_lint=skip_lint,
        max_results=max_results,
        offset=offset,
        max_chars=max_chars,
        component=component,
        severity=severity,
        title=title,
        repro=repro,
        observed=observed,
        expected=expected,
        workaround=workaround,
        kind=kind,
        tags=tags,
        force_new=force_new,
        bug_id=bug_id,
        reporter_context=reporter_context,
        changed_since=changed_since,
        universe_id=universe_id,
    )


_mcp_wiki = _register_structured_tool(
    wiki,
    title="Wiki Knowledge Base",
    tags={"wiki", "knowledge", "drafts", "pages", "research"},
    annotations=ToolAnnotations(
        title="Wiki Knowledge Base",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 6 — Daemon Status / Routing Evidence
# ═══════════════════════════════════════════════════════════════════════════


def get_status(universe_id: str = "") -> str:
    """Factual snapshot of the daemon's identity + routing config.

    Chatbots call this whenever they need ground-truth daemon facts.
    Returns concrete evidence the chatbot can narrate; does not infer
    or guess.

    Versioned contract (schema_version=1): all fields are stable. Field
    removals and renames require a deprecation notice for one release
    before removal. New fields may be added freely. Breaking changes
    bump schema_version.

    `caveats` is load-bearing — the legacy surface does NOT yet enforce
    per-universe sensitivity_tier (that lives in spec #79 §13). The
    chatbot MUST read + narrate caveats so trust claims match reality.

    Args:
        universe_id: Optional universe scope. Defaults to active universe.
    """
    return _get_status_impl(universe_id=universe_id)


_mcp_get_status = _register_structured_tool(
    get_status,
    title="Daemon Status + Routing Evidence",
    tags={
        "status", "routing", "privacy", "verification",
        "confidential-tier", "workflow",
    },
    annotations=ToolAnnotations(
        title="Daemon Status + Routing Evidence",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# Deprecated-tool visibility (PR-178)
# ═══════════════════════════════════════════════════════════════════════════
# Hide the legacy fat tools from tools/list while keeping them callable, and
# log every deprecated-tool invocation. FastMCP applies on_list_tools to the
# advertised list only — tools/call resolution is unaffected — so the legacy
# tools stay dispatchable for one migration release while the advertised
# surface is exactly the five canonical handles + get_status.


class _DeprecatedToolVisibility(Middleware):
    """Drop deprecated legacy tools from tools/list; keep them callable + log."""

    async def on_list_tools(self, context, call_next):
        tools = await call_next(context)
        return [t for t in tools if t.name not in _DEPRECATED_TOOL_NAMES]

    async def on_call_tool(self, context, call_next):
        name = getattr(context.message, "name", "")
        if name in _DEPRECATED_TOOL_NAMES:
            logger.warning(
                "deprecated-tool-call name=%s — migrate to the five canonical "
                "handles (read_graph/write_graph/run_graph/read_page/write_page)",
                name,
            )
        return await call_next(context)


mcp.add_middleware(_DeprecatedToolVisibility())


# ═══════════════════════════════════════════════════════════════════════════
# Server Entry Point
# ═══════════════════════════════════════════════════════════════════════════



# ═══════════════════════════════════════════════════════════════════════════
# MCP endpoint discovery (substrate-fix #11 / Family A Phase 1.A)
# ═══════════════════════════════════════════════════════════════════════════
# When a browser, recruiter, or fresh AI session GETs /mcp or /mcp-directory
# without an MCP transport handshake, return discovery metadata explaining
# what the endpoint is and how to connect via MCP client.
# MCP clients (POST with JSON-RPC, GET with text/event-stream for SSE leg,
# or any request with MCP transport/session headers) pass through unchanged.

_MCP_DISCOVERY_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Workflow MCP Server</title>
<style>
 :root { color-scheme: light dark; }
 body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
        max-width: 720px; margin: 4rem auto; padding: 0 1.25rem;
        line-height: 1.55; }
 h1 { margin-bottom: 0.3rem; }
 .tag { color: #666; margin-top: 0; }
 code { background: rgba(127,127,127,0.15); padding: 2px 6px;
        border-radius: 3px; font-size: 0.95em; }
 pre { background: rgba(127,127,127,0.10); padding: 0.75rem 1rem;
       border-radius: 4px; overflow-x: auto; font-size: 0.85em; }
 ul { padding-left: 1.2rem; }
 li { margin-bottom: 0.4rem; }
 footer { margin-top: 3rem; color: #888; font-size: 0.85rem; }
</style>
</head>
<body>
<h1>Workflow MCP Server</h1>
<p class="tag">This is the MCP (Model Context Protocol) server endpoint.
You're seeing this page because you reached this URL in a browser instead
of via an MCP client.</p>

<p>Workflow is a multi-AI development platform: agents from different
families (Claude, OpenAI, others) collaborate via this MCP and a durable
shared brain to ship work through a cross-family consensus gate. The
engine is domain-agnostic.</p>

<h2>Connect via MCP client</h2>

<p>Configure your client with this URL:</p>

<ul>
<li><strong>Claude</strong>: Settings → Connectors → Add custom connector
    → URL: this page's URL</li>
<li><strong>ChatGPT (Apps SDK)</strong>: Connector URL: this page's URL</li>
<li><strong>Cursor</strong>: <code>settings.json</code> →
    <code>mcpServers</code> → <code>workflow</code> → <code>url</code></li>
<li><strong>Cowork</strong>: Connectors → URL: this page's URL</li>
</ul>

<p>Or with cURL (technical readers):</p>

<pre>curl -X POST "$REQUEST_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2025-03-26" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'</pre>

<h2>Project</h2>
<ul>
<li><a href="/">Workflow landing page</a></li>
<li><a href="https://github.com/Jonnyton/Workflow">GitHub repository</a></li>
<li>Built by Jonathan Farnsworth (<a href="https://github.com/Jonnyton">&#64;Jonnyton</a>)</li>
</ul>

<footer>
Workflow MCP Server &middot; Streamable HTTP transport (MCP spec) &middot; 2026
</footer>
</body>
</html>
"""


_MCP_DISCOVERY_JSON = {
    "name": "workflow",
    "type": "mcp_server_endpoint",
    "transport": "streamable-http",
    "description": (
        "Workflow is a domain-agnostic multi-step AI workflow platform. "
        "This URL is an MCP endpoint, not a normal JSON API route."
    ),
    "how_to_connect": {
        "url": "https://tinyassets.io/mcp",
        "client_accept_header": "application/json, text/event-stream",
        "protocol_header": "MCP-Protocol-Version: 2025-03-26",
        "method": "POST JSON-RPC initialize, then MCP Streamable HTTP",
    },
    "built_by": "Jonathan Farnsworth",
    "related": {
        "landing_page": "https://tinyassets.io/",
        "source": "https://github.com/Jonnyton/Workflow",
        "builder_profile": "https://github.com/Jonnyton",
        "directory_endpoint": "https://tinyassets.io/mcp-directory",
    },
}


# Real tool/resource catalog returned to plain (non-transport) JSON GETs on
# /mcp-directory, so a technical evaluator can see what the server exposes
# WITHOUT connecting an MCP client. Distinct from the /mcp descriptor above.
# Source of truth for the tool list: workflow/directory_server.py (the
# directory_mcp surface). Bump DIRECTORY_TOOL_CATALOG_VERSION there when the
# chatbot-visible catalog changes; this stays in sync via that constant.
_MCP_DIRECTORY_JSON = {
    "name": "workflow",
    "type": "mcp_tool_catalog",
    "transport": "streamable-http",
    "built_by": "Jonathan Farnsworth",
    "description": (
        "Catalog of the tools and prompts the Workflow MCP server exposes. "
        "This is a read-only directory view for evaluators; connect an MCP "
        "client to the endpoint below to actually call them."
    ),
    "connect": {
        "mcp_endpoint": "https://tinyassets.io/mcp",
        "catalog_path": VERSIONED_DIRECTORY_MCP_PATH,
    },
    "catalog_version": DIRECTORY_TOOL_CATALOG_VERSION,
    "tools": [
        {
            "name": "read_graph",
            "summary": "Read Workflow graph state without changing it — nodes, "
            "edges, typed state, scopes, runs, and triggers.",
        },
        {
            "name": "write_graph",
            "summary": "Create or queue Workflow graph state — the write half "
            "of the graph primitive (nodes, edges, branches).",
        },
        {
            "name": "run_graph",
            "summary": "Run a Workflow graph branch — execute a multi-step "
            "workflow and stream its results.",
        },
        {
            "name": "read_page",
            "summary": "Read or search the Workflow wiki/commons — bugs, plans, "
            "concepts, notes, and drafts.",
        },
        {
            "name": "write_page",
            "summary": "Write or patch a Workflow wiki/commons page, including "
            "filing patch requests into the loop.",
        },
    ],
    "note": (
        "These five primitives (read/write over graph + page, plus run) are the "
        "reviewed public directory surface, sourced from "
        "workflow/directory_server.py. The legacy /mcp endpoint exposes a richer "
        "action-tool surface (universe, extensions, goals, gates, wiki, "
        "get_status) for custom MCP clients."
    ),
    "related": {
        "landing_page": "https://tinyassets.io/",
        "source": "https://github.com/Jonnyton/Workflow",
        "builder_profile": "https://github.com/Jonnyton",
        "mcp_endpoint": "https://tinyassets.io/mcp",
    },
}


def _is_mcp_transport_request(request) -> bool:  # type: ignore[no-untyped-def]
    if request.method.upper() not in {"GET", "HEAD"}:
        return True
    if request.headers.get("mcp-protocol-version"):
        return True
    if request.headers.get("mcp-session-id"):
        return True
    accept = request.headers.get("accept", "").lower()
    return "text/event-stream" in accept


def _wants_discovery_html(request) -> bool:  # type: ignore[no-untyped-def]
    accept = request.headers.get("accept", "").lower()
    return "text/html" in accept


class _MCPDiscoveryMiddleware:
    """Serve discovery output on non-transport /mcp + /mcp-directory GETs.

    Browser-like clients receive HTML. Default curl and JSON probes receive
    compact JSON. FastMCP transport traffic passes through unchanged.
    """

    def __init__(self, app):  # type: ignore[no-untyped-def]
        self.app = app

    def __getattr__(self, name):  # type: ignore[no-untyped-def]
        return getattr(self.app, name)

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path not in {"/mcp", "/mcp/", "/mcp-directory", "/mcp-directory/"}:
            await self.app(scope, receive, send)
            return
        # Build a Request-like view to inspect headers
        from starlette.requests import Request

        request = Request(scope, receive=receive)
        if _is_mcp_transport_request(request):
            await self.app(scope, receive, send)
            return
        from starlette.responses import HTMLResponse, JSONResponse

        is_directory = path in {"/mcp-directory", "/mcp-directory/"}
        if _wants_discovery_html(request):
            response = HTMLResponse(_MCP_DISCOVERY_HTML)
        else:
            response = JSONResponse(
                _MCP_DIRECTORY_JSON if is_directory else _MCP_DISCOVERY_JSON
            )
        await response(scope, receive, send)


def create_streamable_http_app() -> Starlette:
    """Create the production HTTP app with both MCP surfaces.

    `/mcp` preserves the legacy custom-connector surface. `/mcp-directory`
    remains as the stable directory surface. The versioned directory path is
    the advertised chatbot-host URL; changing it invalidates host-side cached
    tool catalogs after substrate schema updates. Both route to the same
    backend state.
    """
    legacy_app = mcp.http_app(path="/mcp", transport="streamable-http")
    directory_app = directory_mcp.http_app(
        path=DIRECTORY_MCP_PATH,
        transport="streamable-http",
    )
    versioned_directory_app = directory_mcp.http_app(
        path=VERSIONED_DIRECTORY_MCP_PATH,
        transport="streamable-http",
    )

    @asynccontextmanager
    async def lifespan(app: Starlette):  # type: ignore[no-untyped-def]
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(
                legacy_app.router.lifespan_context(legacy_app),
            )
            await stack.enter_async_context(
                directory_app.router.lifespan_context(directory_app),
            )
            await stack.enter_async_context(
                versioned_directory_app.router.lifespan_context(versioned_directory_app),
            )
            yield

    app = Starlette(
        routes=[
            *legacy_app.routes,
            *directory_app.routes,
            *versioned_directory_app.routes,
        ],
        lifespan=lifespan,
    )
    app.state.path = f"/mcp,{DIRECTORY_MCP_PATH},{VERSIONED_DIRECTORY_MCP_PATH}"
    app.state.transport_type = "streamable-http"
    # Substrate-fix #11 / Family A Phase 1.A: serve discovery HTML to
    # browser-style GETs on /mcp + /mcp-directory; pass MCP transport
    # requests through unchanged.
    from workflow.auth.middleware import AuthContextMiddleware

    app = AuthContextMiddleware(_MCPDiscoveryMiddleware(app))
    return app


def main(
    host: str = "0.0.0.0",
    port: int = 8001,
    transport: str = "streamable-http",
) -> None:
    """Run the Workflow Server as a remote MCP server.

    Args:
        host: Bind address (default all interfaces).
        port: Port number (default 8001).
        transport: MCP transport protocol. "streamable-http" for remote
            connections (default), "sse" for legacy, "stdio" for local.
    """
    logger.info(
        "Starting Workflow Server on %s:%d (transport=%s)",
        host, port, transport,
    )

    if transport == "streamable-http":
        app = create_streamable_http_app()
        uvicorn.run(app, host=host, port=port)
    elif transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    elif transport == "stdio":
        mcp.run()
    else:
        raise ValueError(f"Unknown transport: {transport}")


if __name__ == "__main__":
    main()
