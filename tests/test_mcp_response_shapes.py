from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastmcp.tools import ToolResult


@pytest.fixture
def mcp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")

    from workflow import universe_server as us

    importlib.reload(us)
    yield us
    importlib.reload(us)


@pytest.mark.asyncio
async def test_substrate_changing_tool_call_returns_text_and_structured_content(mcp_env):
    """ChatGPT needs a visible text block plus structuredContent after approval."""
    us = mcp_env

    result = await us.mcp.call_tool(
        "goals",
        {
            "action": "propose",
            "name": "BUG-069 response-shape proof",
            "description": "Regression guard for access-granted finalization.",
        },
    )

    assert isinstance(result, ToolResult)
    assert result.structured_content is not None
    assert result.structured_content["status"] == "proposed"
    assert result.structured_content["goal"]["name"] == "BUG-069 response-shape proof"
    assert result.meta == {"workflow": {"response_shape": "text+structuredContent"}}

    text = result.content[0].text
    assert "BUG-069 response-shape proof" in text
    assert "Proposed Goal" in text


def test_direct_pattern_a2_wrappers_still_return_json_strings(mcp_env):
    """Direct imports remain back-compatible with the implementation layer."""
    us = mcp_env

    raw = us.goals(action="propose", name="direct-wrapper-proof")

    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert parsed["status"] == "proposed"
    assert parsed["goal"]["name"] == "direct-wrapper-proof"

