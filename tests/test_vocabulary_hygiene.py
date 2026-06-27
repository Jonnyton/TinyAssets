"""Vocabulary-hygiene regression tests for task #89.

LIVE-F7 (Devin session 1): Claude memory absorbed project-internal
vocabulary ('Universe Server', 'SKILL.md', 'worktree', 'soul files')
from adjacent conversations and leaked it into Devin's tier-2 chat.
System vocabulary bleed is the product experience even when the bleed
is a chatbot-vendor-primitive failure.

Mitigation (task #89): minimize project-internal vocabulary in every
surface Claude's context could absorb — server instructions, MCP
prompts, tool descriptions. Tier-3 contributor surfaces (AGENTS.md,
CONTRIBUTING.md, catalog YAML comments) are explicitly OUT of scope —
those users speak engine-vocabulary natively.

These tests pin the hygiene contract so future edits don't reintroduce
the jargon.

Rationale: docs/audits/user-chat-intelligence/2026-04-19-devin-
session1.md §2.2 LIVE-F7 + §3.2 P-E.
"""

from __future__ import annotations

import asyncio

from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
from tinyassets.universe_server import (
    _EXTENSION_GUIDE_PROMPT,
    mcp,
)

# Jargon tokens that must NOT appear in user-facing surfaces unless
# absolutely required by the API contract (e.g., `run_branch` action
# names are allowed — those are API surface, not narrative prose).
# Narrative prose uses of these tokens teach the user the jargon;
# that's what we're eliminating.
NARRATIVE_JARGON_FORBIDDEN = [
    # The literal phrase that leaked to Devin via Claude memory in LIVE-F7.
    "Universe Server",
    # Dev-toolchain leaks — no user should ever see these in chat.
    "worktree",
    "SKILL.md",
    # Project-internal concept that has no user-facing equivalent yet.
    "soul file",
    "soul files",
]


def _list_prompts_text() -> str:
    """Concatenate every MCP prompt text the server exposes."""
    prompts = asyncio.run(mcp.list_prompts(run_middleware=False))
    parts: list[str] = []
    for prompt in prompts:
        # FastMCP Prompt objects carry the rendered text accessible via
        # the callable or description. We surface description for the
        # hygiene pin (always present, user-facing).
        desc = getattr(prompt, "description", "") or ""
        parts.append(desc)
    return "\n".join(parts)


def _list_tools_text() -> str:
    """Concatenate every MCP tool description (the descriptions end up
    in Claude's tool-list context)."""
    tools = asyncio.run(mcp.list_tools(run_middleware=False))
    parts: list[str] = []
    for tool in tools:
        desc = getattr(tool, "description", "") or ""
        parts.append(desc)
    return "\n".join(parts)


def test_server_instructions_drop_universe_server_jargon() -> None:
    """Server instructions must not say 'Universe Server' (the literal
    phrase that leaked into Devin's Claude memory in LIVE-F7)."""
    text = mcp.instructions or ""
    assert "Universe Server" not in text, (
        "Server instructions must not teach 'Universe Server' vocabulary; "
        "it's the literal phrase that leaked via Claude memory to Devin "
        "(LIVE-F7). Use 'TinyAssets' (product name) instead."
    )


def test_server_instructions_drop_dev_toolchain_terms() -> None:
    """Dev-toolchain vocabulary must never appear in server instructions.
    Claude memory picks up 'worktree' / 'SKILL.md' from adjacent host
    conversations; surfaces shouldn't reinforce them."""
    text = mcp.instructions or ""
    for forbidden in ("worktree", "SKILL.md"):
        assert forbidden not in text, (
            f"Dev-toolchain term '{forbidden}' leaked into server "
            f"instructions; Claude memory will speak it back to users."
        )


def test_control_station_prompt_drops_soul_file_jargon() -> None:
    """'soul files' is pure project-internal jargon. No user-facing
    surface should teach it."""
    text = _CONTROL_STATION_PROMPT.lower()
    assert "soul file" not in text, (
        "'soul files' is engine-internal vocabulary; replace with "
        "user-facing language like 'profile files' or 'identity records'."
    )


def test_all_prompts_drop_forbidden_jargon() -> None:
    """Every MCP prompt's description is user-context-exposed. None of
    them may carry the forbidden jargon tokens."""
    text = _list_prompts_text()
    for forbidden in NARRATIVE_JARGON_FORBIDDEN:
        # Case-insensitive check so 'universe server' also fails.
        assert forbidden.lower() not in text.lower(), (
            f"Prompt description carries forbidden jargon '{forbidden}'; "
            f"replace with user-facing language."
        )


def test_all_tool_descriptions_drop_forbidden_jargon() -> None:
    """Tool descriptions are in Claude's tool-list context on every
    request. Jargon there is the highest-risk surface for memory bleed.
    """
    text = _list_tools_text()
    for forbidden in NARRATIVE_JARGON_FORBIDDEN:
        assert forbidden.lower() not in text.lower(), (
            f"Tool description carries forbidden jargon '{forbidden}'; "
            f"replace with user-facing language."
        )


def test_extension_guide_drops_forbidden_jargon() -> None:
    """The extension guide prompt is loaded when a user starts node
    authoring — extra-high-risk surface for teaching bad vocabulary."""
    text = _EXTENSION_GUIDE_PROMPT.lower()
    for forbidden in NARRATIVE_JARGON_FORBIDDEN:
        assert forbidden.lower() not in text, (
            f"Extension guide prompt carries forbidden jargon "
            f"'{forbidden}'; replace with user-facing language."
        )
