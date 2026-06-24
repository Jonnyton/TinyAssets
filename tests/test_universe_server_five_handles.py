"""PR-178: the live /mcp surface advertises exactly the five canonical handles.

Forward-ported from the /mcp-directory surface onto workflow.universe_server
(the process behind https://tinyassets.io/mcp). The legacy fat tools stay
registered + callable for one migration release but are hidden from tools/list
and logged on call by the _DeprecatedToolVisibility middleware.
"""
from __future__ import annotations

import asyncio
import json
import logging

from workflow.universe_server import (
    _DEPRECATED_TOOL_NAMES,
    mcp,
    read_graph,
    write_graph,
)

CANONICAL_HANDLES = {
    "read.graph",
    "write.graph",
    "run.graph",
    "read.page",
    "write.page",
}

# The advertised user surface is the five handles plus the get_status read.
ADVERTISED = CANONICAL_HANDLES | {"get_status"}

EXPECTED_ANNOTATIONS = {
    "read.graph": {"readOnlyHint": True, "idempotentHint": True},
    "write.graph": {"readOnlyHint": False, "openWorldHint": True},
    "run.graph": {"readOnlyHint": False, "openWorldHint": False},
    "read.page": {"readOnlyHint": True, "idempotentHint": True},
    "write.page": {"readOnlyHint": False, "openWorldHint": True},
}


def _advertised_tools():
    """tools/list as a real MCP client sees it (middleware applied)."""
    return asyncio.run(mcp.list_tools(run_middleware=True))


def _registered_tools():
    """Every tool registered on the server (middleware bypassed)."""
    return asyncio.run(mcp.list_tools(run_middleware=False))


def test_live_surface_advertises_exactly_five_handles_plus_status() -> None:
    advertised = {tool.name for tool in _advertised_tools()}
    assert advertised == ADVERTISED
    # No enumerated legacy fat tool leaks onto the advertised surface.
    assert _DEPRECATED_TOOL_NAMES.isdisjoint(advertised)


def test_legacy_tools_stay_registered_but_hidden() -> None:
    registered = {tool.name for tool in _registered_tools()}
    advertised = {tool.name for tool in _advertised_tools()}
    # Still registered (callable) ...
    assert _DEPRECATED_TOOL_NAMES <= registered
    # ... but not advertised.
    assert _DEPRECATED_TOOL_NAMES.isdisjoint(advertised)


def test_handle_annotations_match_contract() -> None:
    tools = {tool.name: tool for tool in _advertised_tools()}
    for name, expected in EXPECTED_ANNOTATIONS.items():
        ann = tools[name].annotations
        for key, value in expected.items():
            assert getattr(ann, key) == value, f"{name}.{key}"


def test_read_graph_status_is_full_not_directory_redacted() -> None:
    """The live operator surface keeps the full get_status (unredacted)."""
    payload = json.loads(read_graph(target="status"))
    assert "schema_version" in payload
    # The directory redactor injects this marker; the live surface must not.
    assert "directory_privacy_note" not in payload


def test_unknown_target_is_reported() -> None:
    payload = json.loads(read_graph(target="bogus"))
    assert payload["error"] == "unknown_target"
    assert payload["handle"] == "read.graph"


def test_goal_write_and_read_round_trip(monkeypatch, tmp_path) -> None:
    """write.graph(goal) routes to the same handler read.graph(goals) reads."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "five-handle-test")

    from workflow.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        proposed = json.loads(
            write_graph(
                target="goal",
                name="Five handle smoke goal",
                tags="pr178,smoke",
                visibility="public",
            )
        )
        assert proposed["status"] == "proposed"

        searched = json.loads(read_graph(target="goals", query="Five handle smoke"))
        assert searched["count"] >= 1
        assert any(
            goal["goal_id"] == proposed["goal"]["goal_id"]
            for goal in searched["goals"]
        )
    finally:
        invalidate_backend_cache()


def test_deprecated_legacy_tool_callable_and_logged(monkeypatch, tmp_path, caplog) -> None:
    """A hidden legacy tool still dispatches by plain name and logs deprecation."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))

    from workflow.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        with caplog.at_level(logging.WARNING, logger="universe_server"):
            result = asyncio.run(mcp.call_tool("universe", {"action": "list"}))
        assert result is not None
        assert "deprecated-tool-call name=universe" in caplog.text
    finally:
        invalidate_backend_cache()
