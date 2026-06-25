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
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from workflow.api.extensions import _extensions_impl
from workflow.api.market import goals as _goals_impl
from workflow.api.status import get_status as _get_status_impl
from workflow.api.universe import _universe_impl
from workflow.api.wiki import wiki as _wiki_impl
from workflow.mcp_schema_utils import describe_signature

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


def _register_structured_tool(
    fn,
    *,
    server,
    name=None,
    title=None,
    tags=None,
    annotations=None,
):
    """Register an MCP adapter without changing the direct Python API."""

    @wraps(fn)
    def _tool(*args, **kwargs):
        return _structured_return(fn(*args, **kwargs))

    _tool.__name__ = f"_mcp_{fn.__name__}"
    # Inject docstring-derived parameter descriptions so the advertised
    # tool contract is labelled identically on every FastMCP version.
    # See workflow.mcp_schema_utils.
    _tool.__signature__, _tool.__annotations__ = describe_signature(fn)
    kwargs = {"name": name or fn.__name__, "output_schema": None}
    if title is not None:
        kwargs["title"] = title
    if tags is not None:
        kwargs["tags"] = tags
    if annotations is not None:
        kwargs["annotations"] = annotations
    return server.tool(**kwargs)(_tool)


def _unknown_target(handle: str, target: str, allowed: tuple[str, ...]) -> str:
    return json.dumps({
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
        return _directory_safe_status(universe_id=graph_id)
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
    server=directory_mcp,
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
        target: What to write: goal or request.
        name: Human-readable shared-goal name.
        description: Optional shared-goal description.
        tags: Optional comma-separated shared-goal tags.
        visibility: Shared-goal visibility, usually public.
        text: Request text to queue.
        graph_id: Optional target graph/universe identifier.
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
    return _unknown_target("write_graph", target, ("goal", "request"))


_mcp_write_graph = _register_structured_tool(
    write_graph,
    server=directory_mcp,
    name="write_graph",
    title="Write Graph",
    tags={"graph", "workflow", "write"},
    annotations=ToolAnnotations(
        title="Write Graph",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)


def run_graph(
    branch_def_id: str,
    inputs_json: str = "",
    run_name: str = "",
    graph_id: str = "",
    recursion_limit_override: int = 0,
) -> str:
    """Run a Workflow graph branch.

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
    server=directory_mcp,
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
    """Read or search Workflow wiki pages.

    Args:
        page: Optional wiki page slug or path. Empty searches by query.
        query: Optional search text or ambient relevance terms.
        category: Optional wiki category filter for searches.
        changed_since: Optional ISO timestamp for feed freshness filtering.
            With an empty page/query/category, returns pages changed after this
            timestamp.
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
    server=directory_mcp,
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
    """Write, patch, or file a Workflow wiki page.

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
    server=directory_mcp,
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
