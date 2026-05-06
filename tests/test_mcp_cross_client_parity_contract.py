"""Guards for MCP response-shape parity and live cross-client proof.

These are static contract tests for the community patch request that absorbed
the BUG-069 class: every public MCP server surface should use the structured
tool adapter, and ui-test should require rendered proof on both ChatGPT and
Claude before shape-changing tool work ships.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

MCP_SERVER_SURFACES = (
    "workflow/mcp_server.py",
    "workflow/universe_server.py",
    "workflow/directory_server.py",
)


def _read(rel_path: str) -> str:
    return (REPO / rel_path).read_text(encoding="utf-8")


def test_all_mcp_server_surfaces_register_tools_through_structured_adapter() -> None:
    """ChatGPT and Claude must see the same text + structuredContent shape."""
    failures: list[str] = []
    for rel_path in MCP_SERVER_SURFACES:
        text = _read(rel_path)
        tool_call_lines = [
            (lineno, line.strip())
            for lineno, line in enumerate(text.splitlines(), 1)
            if ".tool(" in line
        ]

        if "def _register_structured_tool" not in text:
            failures.append(f"{rel_path}: missing _register_structured_tool")
        if "return _structured_return(fn(*args, **kwargs))" not in text:
            failures.append(f"{rel_path}: adapter does not wrap with _structured_return")
        if len(tool_call_lines) != 1:
            calls = ", ".join(f"L{lineno}: {line}" for lineno, line in tool_call_lines)
            failures.append(f"{rel_path}: expected one adapter .tool call, found {calls}")

    assert failures == []


def test_ui_test_requires_cross_client_mcp_shape_proof() -> None:
    """Rendered chatbot proof must cover both Apps SDK and Anthropic MCP."""
    skill = _read(".agents/skills/ui-test/SKILL.md")
    mirror = _read(".claude/skills/ui-test/SKILL.md")

    required_phrases = (
        "cross-client MCP alignment is a project prerequisite",
        "ChatGPT (Apps SDK strict surface)",
        "Claude.ai (Anthropic MCP)",
        "same call",
        "structuredContent",
        "both-client verification",
        "Direct MCP call works fine",
        "INSUFFICIENT",
    )

    missing = [phrase for phrase in required_phrases if phrase not in skill]

    assert missing == []
    assert mirror == skill
