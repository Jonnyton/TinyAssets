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


def test_mcp_tool_result_has_structured_content_and_text_content() -> None:
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


def test_mcp_substrate_changing_tool_result_has_structured_and_text_content(
    monkeypatch,
    tmp_path,
) -> None:
    """BUG-069: substrate-changing calls must finalize on ChatGPT's strict surface."""
    from workflow import universe_server as us

    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(tmp_path / "wiki"))

    async def _call_file_bug():
        return await us.mcp.call_tool(
            "wiki",
            {
                "action": "file_bug",
                "component": "chatgpt.workflow_connector",
                "severity": "major",
                "title": "BUG-069 regression probe unique substrate write",
                "observed": (
                    "ChatGPT showed access granted, then Thinking forever "
                    "after a substrate-changing call."
                ),
                "expected": "The chatbot renders a visible final response.",
                "force_new": True,
            },
        )

    result = asyncio.run(_call_file_bug())

    assert isinstance(result.structured_content, dict)
    assert result.structured_content["status"] == "filed"
    assert result.structured_content["bug_id"].startswith("BUG-")
    assert result.content
    assert result.content[0].type == "text"
    assert json.loads(result.content[0].text)["status"] == "filed"
