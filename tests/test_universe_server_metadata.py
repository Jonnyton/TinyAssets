from __future__ import annotations

import asyncio

from tinyassets.universe_server import mcp


def _list_tools():
    return asyncio.run(mcp.list_tools(run_middleware=False))


def _list_prompts():
    return asyncio.run(mcp.list_prompts(run_middleware=False))


class TestUniverseServerMetadata:
    def test_tool_metadata_is_directory_ready(self):
        tools = {tool.name: tool for tool in _list_tools()}

        universe = tools["universe"]
        assert universe.title == "Universe Operations"
        assert {"universe", "daemon", "collaboration", "workflow"} <= universe.tags
        assert universe.annotations.readOnlyHint is False
        assert universe.annotations.destructiveHint is False
        assert universe.annotations.idempotentHint is False
        assert universe.annotations.openWorldHint is True
        assert 'action="inspect"' in universe.description

        extensions = tools["extensions"]
        assert extensions.title == "Graph Extensions"
        assert {"extensions", "nodes", "plugins", "customization"} <= extensions.tags
        assert extensions.annotations.readOnlyHint is False
        assert extensions.annotations.destructiveHint is False
        assert extensions.annotations.idempotentHint is False
        assert extensions.annotations.openWorldHint is True
        assert "extension_guide" in extensions.description

        change_context = tools["community_change_context"]
        assert change_context.title == "Community Change Context"
        assert {"community", "change-loop", "review", "github"} <= change_context.tags
        assert change_context.annotations.readOnlyHint is True
        assert change_context.annotations.destructiveHint is False
        assert change_context.annotations.idempotentHint is True
        assert change_context.annotations.openWorldHint is True
        assert "PR metadata" in change_context.description
        assert "project plan" in change_context.description

    def test_prompt_metadata_is_present(self):
        prompts = {prompt.name: prompt for prompt in _list_prompts()}

        control_station = prompts["control_station"]
        assert control_station.title == "Control Station Guide"
        assert {"control", "daemon", "multiplayer", "operations"} <= control_station.tags
        assert "TinyAssets Server" in control_station.description

        extension_guide = prompts["extension_guide"]
        assert extension_guide.title == "Extension Authoring Guide"
        assert {"extensions", "nodes", "plugins", "workflow"} <= extension_guide.tags
        assert "LangGraph nodes" in extension_guide.description
