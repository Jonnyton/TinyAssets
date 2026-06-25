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
    """ChatGPT/Apps SDK needs structuredContent without losing text content.

    The text block must carry the real payload. When the payload fits the
    budget it is faithful JSON (parseable); when oversized it is real truncated
    data with a pointer to structuredContent. Either way the payload's data is
    present in text, never replaced by a placeholder stub.
    """
    from workflow import universe_server as us

    async def _call_status():
        return await us.mcp.call_tool("get_status", {"universe_id": ""})

    result = asyncio.run(_call_status())

    assert isinstance(result.structured_content, dict)
    assert result.structured_content["schema_version"] == 1
    assert result.content
    assert result.content[0].type == "text"
    text = result.content[0].text
    # Real payload data is present in the text channel (not a placeholder).
    assert "schema_version" in text
    if "[truncated:" not in text:
        # Small payloads stay fully faithful and parseable.
        assert json.loads(text)["schema_version"] == 1
    else:
        # Oversized payloads carry real leading data + a pointer to the rest.
        assert "structuredContent" in text
        assert len(text) <= us._MCP_TEXT_CONTENT_MAX_CHARS


def test_mcp_tool_large_result_keeps_full_structured_content_with_bounded_text(
    monkeypatch,
) -> None:
    """Large results stay bounded in text but must carry REAL data, not a stub.

    Text-only MCP clients read only the ``content`` text block. The prior
    contract replaced oversized payloads with a <500-char key-count stub, which
    made reads silently look empty to those clients. New contract: full payload
    in ``structuredContent``, and the text block carries real leading data
    bounded to the text budget with an explicit pointer to ``structuredContent``
    for the elided remainder.
    """
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
    # structuredContent keeps the full payload (above). The text block must
    # now carry REAL leading data + an explicit pointer to the remainder,
    # bounded to the budget — not a lossy placeholder.
    assert "structuredContent" in text  # pointer to the full payload
    assert "truncated" in text  # explicit elision marker
    assert "c-0" in text  # real leading data is present, not a stub
    assert len(text) <= us._MCP_TEXT_CONTENT_MAX_CHARS
