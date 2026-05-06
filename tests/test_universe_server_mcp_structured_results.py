"""Regression tests for direct wrappers vs MCP structured tool results."""

from __future__ import annotations

import asyncio
import json


def test_direct_wrappers_keep_json_string_contract() -> None:
    """Local callers still import wrappers directly and json.loads the result."""
    from workflow import universe_server as us

    status_raw = us.get_status()
    wiki_raw = us.wiki(action="list")

    assert isinstance(status_raw, str)
    assert isinstance(wiki_raw, str)
    assert json.loads(status_raw)["schema_version"] == 1
    assert "promoted" in json.loads(wiki_raw)


def test_mcp_status_tool_result_has_structured_content_and_text_content() -> None:
    """ChatGPT/Apps SDK needs structuredContent without losing text content."""
    from workflow import universe_server as us

    async def _call_status():
        return await us.mcp.call_tool("get_status", {"universe_id": ""})

    result = asyncio.run(_call_status())

    assert isinstance(result.structured_content, dict)
    assert result.structured_content["schema_version"] == 1
    assert result.content
    assert result.content[0].type == "text"
    assert json.loads(result.content[0].text)["schema_version"] == 1


def test_mcp_wiki_tool_result_has_structured_content_and_text_content(
    monkeypatch,
) -> None:
    """BUG-070 guard: `wiki` stays JSON-RPC deserializable through MCP."""
    from workflow import universe_server as us

    monkeypatch.setattr(
        us,
        "_wiki_impl",
        lambda **kwargs: json.dumps(
            {
                "promoted": [{"page": "pages/bugs/bug-070.md"}],
                "promoted_count": 1,
                "drafts": [],
                "drafts_count": 0,
                "action": kwargs["action"],
            }
        ),
    )

    async def _call_wiki():
        return await us.mcp.call_tool("wiki", {"action": "list"})

    result = asyncio.run(_call_wiki())

    assert result.structured_content == {
        "promoted": [{"page": "pages/bugs/bug-070.md"}],
        "promoted_count": 1,
        "drafts": [],
        "drafts_count": 0,
        "action": "list",
    }
    assert result.content
    assert result.content[0].type == "text"
    assert json.loads(result.content[0].text) == result.structured_content


def test_mcp_community_change_context_tool_result_has_structured_content_and_text_content(
    monkeypatch,
) -> None:
    """BUG-070 guard: review-context alias stays deserializable through MCP."""
    from workflow import universe_server as us

    monkeypatch.setattr(
        us,
        "_universe_impl",
        lambda **kwargs: json.dumps(
            {
                "kind": "community_change_context",
                "selector": kwargs["filter_text"],
                "limit": kwargs["limit"],
                "open_prs": [],
            }
        ),
    )

    async def _call_context():
        return await us.mcp.call_tool(
            "community_change_context",
            {"filter_text": "queue", "limit": 1},
        )

    result = asyncio.run(_call_context())

    assert result.structured_content == {
        "kind": "community_change_context",
        "selector": "queue",
        "limit": 1,
        "open_prs": [],
    }
    assert result.content
    assert result.content[0].type == "text"
    assert json.loads(result.content[0].text) == result.structured_content
