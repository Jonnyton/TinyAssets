"""Smoke: FastMCP instance has at least one registered tool."""

from __future__ import annotations


def test_mcp_has_registered_tools():
    from tinyassets.universe_server import mcp  # FastMCP exposes tools via _tool_manager._tools (private) OR list_tools
    # (async). For smoke, we just need evidence that at least one tool is
    # registered. The internal dict is the cheapest check; if it ever moves,
    # the fallback exercises the public path.
    tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", None)
    if tools is None:
        # Fallback: async list_tools() via a sync call.
        import asyncio

        async def _call():
            return await mcp.list_tools()

        result = asyncio.run(_call())
        assert len(result) > 0, "mcp.list_tools() returned empty"
        return

    assert len(tools) > 0, "FastMCP has zero registered tools — registration regression"
