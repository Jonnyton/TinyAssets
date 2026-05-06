from __future__ import annotations

import asyncio

from workflow.universe_server import mcp


def _list_tools():
    return asyncio.run(mcp.list_tools(run_middleware=False))


def _list_prompts():
    return asyncio.run(mcp.list_prompts(run_middleware=False))


class TestUniverseServerMetadata:
    def test_tool_metadata_is_directory_ready(self):
        tools = {tool.name: tool for tool in _list_tools()}

        assert set(tools) == {
            "read.graph", "write.graph", "run.graph", "read.page", "write.page",
        }

        read_graph = tools["read.graph"]
        assert read_graph.title == "Read Graph"
        assert {"graph", "workflow", "read", "status"} <= read_graph.tags
        assert read_graph.annotations.readOnlyHint is True
        assert read_graph.annotations.destructiveHint is False
        assert read_graph.annotations.idempotentHint is True
        assert read_graph.annotations.openWorldHint is True

        write_graph = tools["write.graph"]
        assert write_graph.title == "Write Graph"
        assert {"graph", "workflow", "write", "daemon"} <= write_graph.tags
        assert write_graph.annotations.readOnlyHint is False
        assert write_graph.annotations.destructiveHint is False
        assert write_graph.annotations.idempotentHint is False
        assert write_graph.annotations.openWorldHint is True

        run_graph = tools["run.graph"]
        assert run_graph.title == "Run Graph"
        assert run_graph.annotations.readOnlyHint is False

        read_page = tools["read.page"]
        assert read_page.title == "Read Page"
        assert read_page.annotations.readOnlyHint is True

        write_page = tools["write.page"]
        assert write_page.title == "Write Page"
        assert write_page.annotations.readOnlyHint is False

    def test_prompt_metadata_is_present(self):
        prompts = {prompt.name: prompt for prompt in _list_prompts()}

        control_station = prompts["control_station"]
        assert control_station.title == "Control Station Guide"
        assert {"control", "daemon", "multiplayer", "operations"} <= control_station.tags
        assert "Workflow Server" in control_station.description

        extension_guide = prompts["extension_guide"]
        assert extension_guide.title == "Extension Authoring Guide"
        assert {"extensions", "nodes", "plugins", "workflow"} <= extension_guide.tags
        assert "LangGraph nodes" in extension_guide.description
