"""Directory-safe MCP surface for public host listings.

This module exposes narrow tools intended for reviewed host directories such
as Claude's Connectors Directory and ChatGPT Apps. The legacy
``workflow.universe_server`` surface remains available at ``/mcp`` for custom
MCP clients. This directory surface is intentionally smaller: no catch-all
``action`` arguments, explicit read/write boundaries, and explicit tool
annotations for host review.
"""

from __future__ import annotations

import json
from functools import wraps
from inspect import signature
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from workflow.api.extensions import _extensions_impl
from workflow.api.market import goals as _goals_impl
from workflow.api.status import get_status as _get_status_impl
from workflow.api.universe import _universe_impl
from workflow.api.wiki import wiki as _wiki_impl

directory_mcp = FastMCP(
    "workflow-directory",
    instructions=(
        "Workflow helps users discover durable workflow goals, inspect "
        "universes, browse the public knowledge wiki, and submit bounded "
        "requests into the Workflow daemon loop. Use these tools only when "
        "the user asks for Workflow, durable AI workflow design, shared "
        "workflow goals, or project wiki/status information."
    ),
    version="0.1.0",
)


def _redact_directory_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the public-directory-safe subset of the daemon status payload."""
    redacted = dict(payload)

    active_host = redacted.get("active_host")
    if isinstance(active_host, dict):
        public_host = dict(active_host)
        public_host.pop("host_id", None)
        redacted["active_host"] = public_host

    evidence = redacted.get("evidence")
    if isinstance(evidence, dict):
        public_evidence = dict(evidence)
        public_evidence.pop("activity_log_tail", None)
        public_evidence.pop("last_n_calls", None)
        public_evidence.pop("policy_hash", None)
        redacted["evidence"] = public_evidence

    evidence_caveats = redacted.get("evidence_caveats")
    if isinstance(evidence_caveats, dict):
        public_caveats = dict(evidence_caveats)
        public_caveats.pop("activity_log_tail", None)
        public_caveats.pop("last_n_calls", None)
        if public_caveats:
            redacted["evidence_caveats"] = public_caveats
        else:
            redacted.pop("evidence_caveats", None)

    if "error" in redacted and "detail" in redacted:
        redacted["detail"] = "Internal diagnostic detail redacted from directory status."

    storage = redacted.get("storage_utilization")
    if isinstance(storage, dict):
        public_storage = dict(storage)
        per_subsystem = public_storage.get("per_subsystem")
        if isinstance(per_subsystem, dict):
            public_storage["per_subsystem"] = {
                name: {
                    key: value
                    for key, value in subsystem.items()
                    if key != "path"
                }
                if isinstance(subsystem, dict)
                else subsystem
                for name, subsystem in per_subsystem.items()
            }
        redacted["storage_utilization"] = public_storage

    next_steps = redacted.get("actionable_next_steps")
    if isinstance(next_steps, list):
        redacted["actionable_next_steps"] = [
            step
            for step in next_steps
            if "activity_log_tail" not in str(step)
            and "last_n_calls" not in str(step)
        ]

    redacted.pop("session_boundary", None)
    redacted["directory_privacy_note"] = (
        "Directory status redacts raw activity logs, recent call diagnostics, "
        "local paths, host account identifiers, and internal hashes. Use the "
        "full custom MCP surface for operator diagnostics."
    )
    return redacted


def _directory_safe_status(universe_id: str = "") -> str:
    raw = _get_status_impl(universe_id=universe_id)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(payload, dict):
        return raw
    return json.dumps(_redact_directory_status(payload), default=str)





def _structured_return(raw):
    """Wrap an MCP tool result so FastMCP populates ``structured_content``.

    ChatGPT (OpenAI Apps SDK) wedges on substrate-changing tool calls when
    the response carries only ``content`` (text) without ``structuredContent``
    (typed dict) + ``_meta`` annotations. Claude tolerates either shape.

    Mirrors the helpers in workflow.universe_server applied via PR #493 + #495.
    """
    import json as _json
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"result": raw}
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            return {"text": raw}
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    return {"result": raw}


def _register_structured_tool(fn, *, server, title=None, tags=None, annotations=None):
    """Register an MCP adapter without changing the direct Python API."""

    @wraps(fn)
    def _tool(*args, **kwargs):
        return _structured_return(fn(*args, **kwargs))

    _tool.__name__ = f"_mcp_{fn.__name__}"
    _tool.__signature__ = signature(fn).replace(return_annotation=dict)
    kwargs = {"name": fn.__name__, "output_schema": None}
    if title is not None:
        kwargs["title"] = title
    if tags is not None:
        kwargs["tags"] = tags
    if annotations is not None:
        kwargs["annotations"] = annotations
    return server.tool(**kwargs)(_tool)


def get_workflow_status(universe_id: str = "") -> str:
    """Use this when the user asks whether Workflow is reachable or safe to use.

    Args:
        universe_id: Optional universe scope. Empty uses the active universe.
    """
    return _directory_safe_status(universe_id=universe_id)


_mcp_get_workflow_status = _register_structured_tool(
    get_workflow_status,
    server=directory_mcp,
    title='Get Workflow Status',
    tags={'status', 'workflow', 'diagnostics'},
    annotations=ToolAnnotations(
        title='Get Workflow Status',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def list_workflow_universes(limit: int = 30) -> str:
    """Use this when the user wants to browse available Workflow universes.

    Args:
        limit: Maximum number of universes to return.
    """
    return _universe_impl(action="list", limit=limit)


_mcp_list_workflow_universes = _register_structured_tool(
    list_workflow_universes,
    server=directory_mcp,
    title='List Workflow Universes',
    tags={'universes', 'workflow', 'browse'},
    annotations=ToolAnnotations(
        title='List Workflow Universes',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def inspect_workflow_universe(universe_id: str = "") -> str:
    """Use this when the user wants a summary of one Workflow universe.

    Args:
        universe_id: Optional universe scope. Empty uses the active universe.
    """
    return _universe_impl(action="inspect", universe_id=universe_id)


_mcp_inspect_workflow_universe = _register_structured_tool(
    inspect_workflow_universe,
    server=directory_mcp,
    title='Inspect Workflow Universe',
    tags={'universes', 'workflow', 'inspect'},
    annotations=ToolAnnotations(
        title='Inspect Workflow Universe',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def list_workflow_goals(tags: str = "", author: str = "", limit: int = 50) -> str:
    """Use this when the user wants to browse existing shared Workflow goals.

    Args:
        tags: Optional comma-separated tag filter.
        author: Optional author filter.
        limit: Maximum number of goals to return.
    """
    return _goals_impl(action="list", tags=tags, author=author, limit=limit)


_mcp_list_workflow_goals = _register_structured_tool(
    list_workflow_goals,
    server=directory_mcp,
    title='List Workflow Goals',
    tags={'goals', 'workflow', 'browse'},
    annotations=ToolAnnotations(
        title='List Workflow Goals',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def search_workflow_goals(query: str, limit: int = 20) -> str:
    """Use this when the user wants to find Workflow goals by text or tag.

    Args:
        query: Search text.
        limit: Maximum number of goals to return.
    """
    return _goals_impl(action="search", query=query, limit=limit)


_mcp_search_workflow_goals = _register_structured_tool(
    search_workflow_goals,
    server=directory_mcp,
    title='Search Workflow Goals',
    tags={'goals', 'workflow', 'search'},
    annotations=ToolAnnotations(
        title='Search Workflow Goals',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def get_workflow_goal(goal_id: str) -> str:
    """Use this when the user wants details for a specific Workflow goal.

    Args:
        goal_id: Goal identifier to inspect.
    """
    return _goals_impl(action="get", goal_id=goal_id)


_mcp_get_workflow_goal = _register_structured_tool(
    get_workflow_goal,
    server=directory_mcp,
    title='Get Workflow Goal',
    tags={'goals', 'workflow', 'inspect'},
    annotations=ToolAnnotations(
        title='Get Workflow Goal',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def search_workflow_wiki(query: str, category: str = "", max_results: int = 10) -> str:
    """Use this when the user wants to search Workflow project knowledge.

    Args:
        query: Search text.
        category: Optional wiki category filter.
        max_results: Maximum number of wiki hits to return.
    """
    return _wiki_impl(
        action="search",
        query=query,
        category=category,
        max_results=max_results,
    )


_mcp_search_workflow_wiki = _register_structured_tool(
    search_workflow_wiki,
    server=directory_mcp,
    title='Search Workflow Wiki',
    tags={'wiki', 'knowledge', 'workflow', 'search'},
    annotations=ToolAnnotations(
        title='Search Workflow Wiki',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)

def read_workflow_wiki_page(
    page: str,
    query: str = "",
    changed_since: str = "",
    max_results: int = 10,
) -> str:
    """Use this when the user wants to read one Workflow wiki page.

    Args:
        page: Wiki page slug or path.
        query: Optional topic terms for the ambient relevance feed.
        changed_since: Optional ISO timestamp for feed freshness filtering.
        max_results: Maximum ambient feed items to return.
    """
    return _wiki_impl(
        action="read",
        page=page,
        query=query,
        changed_since=changed_since,
        max_results=max_results,
    )


_mcp_read_workflow_wiki_page = _register_structured_tool(
    read_workflow_wiki_page,
    server=directory_mcp,
    title='Read Workflow Wiki Page',
    tags={'wiki', 'knowledge', 'workflow', 'read'},
    annotations=ToolAnnotations(
        title='Read Workflow Wiki Page',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def list_workflow_runs(status: str = "", limit: int = 20) -> str:
    """Use this when the user wants recent Workflow run history.

    Args:
        status: Optional run status filter.
        limit: Maximum number of runs to return.
    """
    return _extensions_impl(action="list_runs", status=status, limit=limit)


_mcp_list_workflow_runs = _register_structured_tool(
    list_workflow_runs,
    server=directory_mcp,
    title='List Workflow Runs',
    tags={'runs', 'workflow', 'browse'},
    annotations=ToolAnnotations(
        title='List Workflow Runs',
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)


def propose_workflow_goal(
    name: str,
    description: str = "",
    tags: str = "",
    visibility: str = "public",
) -> str:
    """Use this when the user asks to create a shared Workflow goal proposal.

    Args:
        name: Human-readable goal name.
        description: Optional goal description.
        tags: Optional comma-separated tags.
        visibility: Visibility value accepted by Workflow, usually public.
    """
    return _goals_impl(
        action="propose",
        name=name,
        description=description,
        tags=tags,
        visibility=visibility,
    )


_mcp_propose_workflow_goal = _register_structured_tool(
    propose_workflow_goal,
    server=directory_mcp,
    title='Propose Workflow Goal',
    tags={'goals', 'workflow', 'create'},
    annotations=ToolAnnotations(
        title='Propose Workflow Goal',
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)


def submit_workflow_request(
    text: str,
    universe_id: str = "",
    request_type: str = "scene_direction",
    branch_id: str = "",
) -> str:
    """Use this when the user wants the Workflow daemon to handle a bounded request.

    Args:
        text: Request text to queue.
        universe_id: Optional target universe. Empty uses the active universe.
        request_type: Workflow request type.
        branch_id: Optional target branch identifier.
    """
    return _universe_impl(
        action="submit_request",
        universe_id=universe_id,
        text=text,
        request_type=request_type,
        branch_id=branch_id,
    )


_mcp_submit_workflow_request = _register_structured_tool(
    submit_workflow_request,
    server=directory_mcp,
    title='Submit Workflow Request',
    tags={'requests', 'workflow', 'queue'},
    annotations=ToolAnnotations(
        title='Submit Workflow Request',
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
