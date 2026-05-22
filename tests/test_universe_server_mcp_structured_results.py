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


def test_mcp_tool_large_result_keeps_full_structured_content_with_compact_text(
    monkeypatch,
) -> None:
    """Large list-style results must not mirror the whole payload in text."""
    from workflow import universe_server as us

    claims = [
        {
            "claim_id": f"c-{idx}",
            "branch_def_id": f"b-{idx}",
            "goal_id": "4ff5862cc26d",
            "rung_key": "learned_failure",
            "evidence_note": "x" * 1000,
        }
        for idx in range(12)
    ]

    def _large_gates_result(**_kwargs):
        return json.dumps({
            "status": "ok",
            "goal_id": "4ff5862cc26d",
            "claims": claims,
            "count": len(claims),
        })

    monkeypatch.setattr(us, "_gates_impl", _large_gates_result)

    async def _call_gates():
        return await us.mcp.call_tool(
            "gates",
            {"action": "list_claims", "goal_id": "4ff5862cc26d"},
        )

    result = asyncio.run(_call_gates())

    assert result.structured_content["claims"] == claims
    assert result.structured_content["count"] == 12
    text = result.content[0].text
    assert "Full payload is in structuredContent" in text
    assert "x" * 1000 not in text
    assert len(text) < 500
