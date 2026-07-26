"""Goals discoverability and canonical control-station routing invariants."""

from __future__ import annotations

import asyncio
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


def test_all_deprecated_tools_remain_callable_during_migration(us_env):
    us = us_env
    for name in us._DEPRECATED_TOOL_NAMES:
        assert hasattr(us, name), f"missing tool: {name}"
        assert callable(getattr(us, name))


# ─── control_station prompt invariants ──────────────────────────────────


def test_control_station_mentions_every_advertised_handle_by_name(us_env):
    us = us_env
    prompt = us.control_station()
    advertised = {
        tool.name
        for tool in asyncio.run(us.mcp.list_tools(run_middleware=True))
    }
    for name in advertised:
        assert f"`{name}`" in prompt, f"control_station omits {name}"


def test_control_station_has_tool_catalog_section(us_env):
    """Prompt should have an explicit full-tool framing so
    the bot enumerates the full surface, not action-by-action."""
    us = us_env
    prompt = us.control_station()
    assert "describe every advertised handle" in prompt
    assert "FIVE tools" not in prompt
    # The catalog should describe goals' purpose, not just name it.
    assert "Goal" in prompt
    assert "discover" in prompt.lower() or "discovery" in prompt.lower()


def test_control_station_routes_intent_to_goals(us_env):
    """Routing rules section should tell the bot when to use goals."""
    us = us_env
    prompt = us.control_station()
    assert 'write_graph target="goal"' in prompt
    assert 'read_graph target="goals"' in prompt
    assert 'read_graph target="goal"' in prompt
    assert "Binding a workflow to a Goal is not exposed" in prompt
    assert "Goal leaderboards are not exposed" in prompt


def test_control_station_enumerate_directive_is_explicit(us_env):
    """Bot should enumerate the whole dynamic advertised catalog."""
    us = us_env
    prompt = us.control_station()
    # The directive language should appear near the catalog.
    catalog_pos = prompt.find("Tool Catalog")
    assert catalog_pos >= 0, "Tool Catalog section header missing"
    catalog_section = prompt[catalog_pos:catalog_pos + 1500]
    assert "enumerate every handle" in catalog_section


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
