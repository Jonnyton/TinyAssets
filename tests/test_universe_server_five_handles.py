"""The live /mcp surface advertises exactly the seven canonical public tools.

The legacy fat tools stay
registered + callable for one migration release but are hidden from tools/list
and logged on call by the _DeprecatedToolVisibility middleware.
"""
from __future__ import annotations

import asyncio
import json
import logging

from tinyassets.universe_server import (
    _DEPRECATED_TOOL_NAMES,
    mcp,
    read_graph,
    write_graph,
)

CANONICAL_PUBLIC_TOOLS = {
    "read_graph",
    "write_graph",
    "run_graph",
    "read_page",
    "write_page",
    "converse",  # 2026-07-02 relay reshape: chatbot -> universe intelligence
    "get_status",
}

EXPECTED_ANNOTATIONS = {
    "read_graph": {"readOnlyHint": True, "idempotentHint": True},
    "write_graph": {"readOnlyHint": False, "openWorldHint": False},
    "run_graph": {"readOnlyHint": False, "openWorldHint": False},
    "read_page": {"readOnlyHint": True, "idempotentHint": True},
    "write_page": {"readOnlyHint": False, "openWorldHint": True},
    "converse": {"readOnlyHint": False, "openWorldHint": False},
    "get_status": {"readOnlyHint": True, "idempotentHint": True},
}


def _advertised_tools():
    """tools/list as a real MCP client sees it (middleware applied)."""
    return asyncio.run(mcp.list_tools(run_middleware=True))


def _registered_tools():
    """Every tool registered on the server (middleware bypassed)."""
    return asyncio.run(mcp.list_tools(run_middleware=False))


def test_live_surface_advertises_exactly_canonical_public_tools() -> None:
    advertised = {tool.name for tool in _advertised_tools()}
    assert advertised == CANONICAL_PUBLIC_TOOLS
    assert "converse" in advertised  # the relay handle is user-facing
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


def test_read_graph_status_returns_operator_status() -> None:
    payload = json.loads(read_graph(target="status"))
    assert "schema_version" in payload


def test_unknown_target_is_reported() -> None:
    payload = json.loads(read_graph(target="bogus"))
    assert payload["error"] == "unknown_target"
    assert payload["handle"] == "read_graph"


def test_goal_write_and_read_round_trip(monkeypatch, tmp_path) -> None:
    """write_graph(goal) routes to the same handler read_graph(goals) reads."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "canonical-handle-test")

    from tinyassets.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        proposed = json.loads(
            write_graph(
                target="goal",
                name="Canonical handle smoke goal",
                tags="pr178,smoke",
                visibility="public",
            )
        )
        assert proposed["status"] == "proposed"

        searched = json.loads(
            read_graph(target="goals", query="Canonical handle smoke")
        )
        assert searched["count"] >= 1
        assert any(
            goal["goal_id"] == proposed["goal"]["goal_id"]
            for goal in searched["goals"]
        )
    finally:
        invalidate_backend_cache()


def test_deprecated_legacy_tool_callable_and_logged(monkeypatch, tmp_path, caplog) -> None:
    """A hidden legacy tool still dispatches by plain name and logs deprecation."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    from tinyassets.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        with caplog.at_level(logging.WARNING, logger="universe_server"):
            result = asyncio.run(mcp.call_tool("universe", {"action": "list"}))
        assert result is not None
        assert "deprecated-tool-call name=universe" in caplog.text
    finally:
        invalidate_backend_cache()
