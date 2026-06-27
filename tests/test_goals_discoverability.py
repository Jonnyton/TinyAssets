"""#63 — Goals tool discoverability invariants.

Mission 5 probe found the bot enumerated 33 extensions + 17 universe +
wiki actions and skipped `goals` entirely. The `goals` tool IS
registered as @mcp.tool, but `control_station` didn't promote it, so
when bots asked "what can this connector do?" they listed actions
per dispatcher and forgot the goals dispatcher exists.

Locks in:
1. Goals tool is registered (regression guard).
2. control_station prompt mentions all 5 tools by name.
3. control_station explicitly tells the bot to enumerate ALL when
   asked.
4. Routing table includes goals rows so intent → goals routing fires.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def us_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us
    importlib.reload(us)


# ─── registration regression guard ──────────────────────────────────────


def test_goals_tool_is_registered_callable(us_env):
    """If `goals` ever vanishes from the module surface, the connector
    silently loses the tool. This catches that regression."""
    us = us_env
    assert hasattr(us, "goals"), "goals tool function missing from module"
    assert callable(us.goals)


def test_all_five_tools_callable(us_env):
    us = us_env
    for name in (
        "universe", "extensions", "goals", "wiki", "community_change_context",
    ):
        assert hasattr(us, name), f"missing tool: {name}"
        assert callable(getattr(us, name))


# ─── control_station prompt invariants ──────────────────────────────────


def test_control_station_mentions_all_five_tools_by_name(us_env):
    """Bot should never enumerate the surface and skip `goals` because
    the prompt left it out."""
    us = us_env
    prompt = us.control_station()
    for name in (
        "`universe`", "`extensions`", "`goals`", "`wiki`",
        "`community_change_context`",
    ):
        assert name in prompt, f"control_station omits {name}"


def test_control_station_has_tool_catalog_section(us_env):
    """Prompt should have an explicit full-tool framing so
    the bot enumerates the full surface, not action-by-action."""
    us = us_env
    prompt = us.control_station()
    # Some phrasing that ties the five together explicitly.
    assert (
        "FIVE tools" in prompt
        or "five tools" in prompt
        or "FIVE" in prompt and "tools" in prompt
    ), "no explicit five-tool framing"
    # The catalog should describe goals' purpose, not just name it.
    assert "Goal" in prompt
    assert "discover" in prompt.lower() or "discovery" in prompt.lower()


def test_control_station_routes_intent_to_goals(us_env):
    """Routing rules section should tell the bot when to use goals."""
    us = us_env
    prompt = us.control_station()
    # At least one routing row mentions a goals action.
    assert "goals action=propose" in prompt
    assert (
        "goals action=search" in prompt
        or "goals action=list" in prompt
    )
    assert "goals action=bind" in prompt or "bind" in prompt
    assert "goals action=leaderboard" in prompt


def test_control_station_enumerate_directive_is_explicit(us_env):
    """Bot should be told ENUMERATE ALL FIVE when user asks 'what can
    this do' — so missing goals is impossible."""
    us = us_env
    prompt = us.control_station()
    # The directive language should appear near the catalog.
    catalog_pos = prompt.find("Tool Catalog")
    assert catalog_pos >= 0, "Tool Catalog section header missing"
    # Some "enumerate all" / "describe all" / "list all" phrasing.
    catalog_section = prompt[catalog_pos:catalog_pos + 1500]
    assert (
        "enumerate ALL" in catalog_section
        or "describe ALL" in catalog_section
        or "list ALL" in catalog_section
        or "all five" in catalog_section.lower()
    ), "no explicit 'enumerate all five' directive in catalog section"


# ─── goals docstring still leads with intent ────────────────────────────


def test_goals_docstring_leads_with_user_intent(us_env):
    """A bot doing tools/list-style discovery should see 'declare a
    Goal' / 'discover existing Goals' in the docstring's first chunk."""
    us = us_env
    doc = us.goals.__doc__ or ""
    # First ~400 chars should orient on intent, not internals.
    head = doc[:400]
    assert "Goal" in head
    # User-intent phrasing.
    assert (
        "intent" in head.lower()
        or "discover" in head.lower()
        or "reuse" in head.lower()
        or "first-class" in head.lower()
    )
