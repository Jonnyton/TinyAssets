"""A user-declared node capability is HONORED at execution, not just stored.

Live 2026-08-08 (run 25b32388ab12425a): a gather node carried ``web_search``
in ``tools_allowed``, the automation declared ``web_search`` in its
operations, and the node's LLM turn still ran without WebSearch — its own
output said "Web search requires a permission grant I don't currently have
in this environment". The declaration existed at every layer; nothing
translated it into the provider call. These tests pin the translation.
"""
from __future__ import annotations

import json

from tinyassets.branches import NodeDefinition
from tinyassets.graph_compiler import _provider_tool_grants


def test_web_search_translates_to_provider_tool():
    assert _provider_tool_grants(["web_search"]) == ("WebSearch",)


def test_mcp_action_names_pass_through_silently():
    """tools_allowed also carries MCP action names for _invoke_mcp_action's
    allowlist — they are not provider tools and must not break or leak."""
    assert _provider_tool_grants(["goals.leaderboard", "web_search"]) == (
        "WebSearch",
    )


def test_web_fetch_is_deliberately_not_granted():
    """No SSRF guard exists for node turns yet: web_fetch must NOT become a
    provider grant until one does. This test is the tripwire for that line."""
    assert _provider_tool_grants(["web_fetch"]) == ()


def test_empty_and_none_grant_nothing():
    assert _provider_tool_grants(None) == ()
    assert _provider_tool_grants([]) == ()


def test_compiled_node_threads_web_search_grant_into_provider_call():
    """The decisive test: tools_allowed=['web_search'] reaches the provider
    call as ModelConfig.allowed_tools=('WebSearch',)."""
    from tinyassets.graph_compiler import _build_prompt_template_node

    captured: dict = {}

    def fake_provider_call(prompt, system, *, role="writer", config=None):
        captured["config"] = config
        return json.dumps({"findings": "fresh"})

    node = NodeDefinition(
        node_id="gather",
        display_name="Gather",
        prompt_template="Research {topic}.",
        input_keys=["topic"],
        output_keys=["findings"],
        tools_allowed=["web_search"],
    )
    fn = _build_prompt_template_node(
        node, provider_call=fake_provider_call, event_sink=None
    )
    result = fn({"topic": "AI agent platforms"})

    assert result.get("findings")
    cfg = captured.get("config")
    assert cfg is not None, "node config was not threaded to the provider"
    assert cfg.allowed_tools == ("WebSearch",)


def test_node_without_web_capability_keeps_provider_default():
    """No declared web capability -> allowed_tools stays None (provider
    default), so this change grants nothing to existing branches."""
    from tinyassets.graph_compiler import _build_prompt_template_node

    captured: dict = {}

    def fake_provider_call(prompt, system, *, role="writer", config=None):
        captured["config"] = config
        return json.dumps({"out": "ok"})

    node = NodeDefinition(
        node_id="draft",
        display_name="Draft",
        prompt_template="Write about {x}.",
        input_keys=["x"],
        output_keys=["out"],
    )
    fn = _build_prompt_template_node(
        node, provider_call=fake_provider_call, event_sink=None
    )
    fn({"x": "thing"})

    cfg = captured.get("config")
    assert cfg is not None
    assert cfg.allowed_tools is None
