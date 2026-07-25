"""Keep server-authored MCP guidance aligned with the advertised tool surface.

Authority: ``openspec/specs/live-mcp-connector-surface/spec.md``, especially
Canonical Advertised Handle Set and Remote Streamable-HTTP MCP Endpoint.
"""

from __future__ import annotations

import asyncio
import json
import re

from tinyassets import universe_server


def _run(awaitable):
    return asyncio.run(awaitable)


def _advertised_tools():
    return {
        tool.name: tool
        for tool in _run(universe_server.mcp.list_tools(run_middleware=True))
    }


def _registered_tool_names() -> set[str]:
    return {
        tool.name
        for tool in _run(universe_server.mcp.list_tools(run_middleware=False))
    }


def _instruction_surfaces() -> dict[str, str]:
    surfaces = {
        "server instructions": universe_server.mcp.instructions or "",
    }
    for prompt in _run(
        universe_server.mcp.list_prompts(run_middleware=False)
    ):
        rendered = _run(
            universe_server.mcp.render_prompt(
                prompt.name,
                run_middleware=False,
            )
        )
        body = "\n".join(
            getattr(message.content, "text", "")
            for message in rendered.messages
        )
        surfaces[f"prompt:{prompt.name}"] = "\n".join(
            filter(None, (prompt.description or "", body))
        )
    return surfaces


def _claimed_tool_names(text: str, registered_names: set[str]) -> set[str]:
    """Extract syntactic tool claims, including hidden registered tools."""
    code_span_heads = {
        match.group(1)
        for code in re.findall(r"`([^`\n]+)`", text)
        if (
            match := re.match(
                r"([A-Za-z_][A-Za-z0-9_-]*)",
                code,
            )
        )
    }
    claims = {
        name
        for name in registered_names
        if name in code_span_heads
        or re.search(
            rf"(?<![\w-]){re.escape(name)}\s+action\s*=",
            text,
        )
        or re.search(
            rf"\b(?:call|use|via|through)\s+(?:the\s+)?"
            rf"{re.escape(name)}\b",
            text,
        )
        or re.search(
            rf"\b{re.escape(name)}\s+(?:handle|tool)\b",
            text,
        )
    }
    claims.update(
        re.findall(
            r"(?m)^\s*\d+\.\s+\*\*`([A-Za-z_][A-Za-z0-9_-]*)`\*\*",
            text,
        )
    )
    claims.update(
        re.findall(
            r"`([A-Za-z_][A-Za-z0-9_-]*)`\s+(?:handle|tool)\b",
            text,
        )
    )
    return claims


def _catalog_claims(control_station: str) -> set[str]:
    match = re.search(
        r"(?ms)^## Tool Catalog\b.*?(?=^## |\Z)",
        control_station,
    )
    assert match, "control_station has no Tool Catalog section"
    return set(
        re.findall(
            r"(?m)^\s*\d+\.\s+\*\*`([A-Za-z_][A-Za-z0-9_-]*)`\*\*",
            match.group(0),
        )
    )


def test_instruction_surfaces_claim_only_live_advertised_handles() -> None:
    advertised = set(_advertised_tools())
    registered = _registered_tool_names()
    surfaces = _instruction_surfaces()

    for surface, text in surfaces.items():
        claimed = _claimed_tool_names(text, registered)
        assert claimed <= advertised, (
            f"{surface} claims tools hidden from tools/list: "
            f"{sorted(claimed - advertised)}"
        )

    assert _catalog_claims(surfaces["prompt:control_station"]) == advertised


def test_instruction_routing_examples_use_valid_handle_parameters() -> None:
    advertised = _advertised_tools()
    surfaces = _instruction_surfaces()
    example_pattern = re.compile(
        r"(?<![\w-])([A-Za-z_][A-Za-z0-9_-]*)\s+"
        r"(action|target)\s*=\s*[\"']?([A-Za-z_][A-Za-z0-9_-]*)"
    )

    for surface, text in surfaces.items():
        for handle, parameter, value in example_pattern.findall(text):
            if handle not in advertised:
                continue  # The claimed-tool invariant reports this more clearly.
            properties = advertised[handle].parameters.get("properties", {})
            assert parameter in properties, (
                f"{surface} routes {handle} with unsupported "
                f"parameter {parameter}"
            )
            if parameter != "target":
                continue
            implementation = getattr(universe_server, handle)
            response = json.loads(implementation(target="__invalid_target__"))
            assert value in response["allowed_targets"], (
                f"{surface} routes {handle} to unsupported target {value}"
            )


def test_meet_universe_description_is_relay_first() -> None:
    prompts = {
        prompt.name: prompt
        for prompt in _run(
            universe_server.mcp.list_prompts(run_middleware=False)
        )
    }
    description = prompts["meet_universe"].description or ""
    assert "converse" in description
    assert "relay" in description.lower()
    assert "get_status" not in description
    assert "AS the universe" not in description


def test_graph_target_examples_include_semantic_companion_arguments() -> None:
    pattern = re.compile(
        r"`(?P<handle>read_graph|write_graph)\s+"
        r"target=[\"'](?P<target>[A-Za-z_-]+)[\"']"
        r"(?P<arguments>[^`]*)`"
    )
    required_all = {
        ("read_graph", "goal"): {"goal_id"},
        ("write_graph", "goal"): {"name"},
        ("write_graph", "branch"): {"branch_id", "changes_json"},
        ("write_graph", "request"): {"text", "idempotency_key"},
    }
    required_any = {
        ("read_graph", "branch"): {"branch_id", "graph_id"},
        ("read_graph", "run"): {"run_id", "graph_id"},
    }
    for surface, text in _instruction_surfaces().items():
        examples = list(pattern.finditer(text))
        for example in examples:
            key = (example.group("handle"), example.group("target"))
            assigned = set(
                re.findall(
                    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=",
                    example.group("arguments"),
                )
            )
            if key in required_all:
                missing = required_all[key] - assigned
                assert not missing, (
                    f"{surface} omits {sorted(missing)} from "
                    f"{example.group(0)}"
                )
            if key in required_any:
                assert assigned & required_any[key], (
                    f"{surface} needs one of {sorted(required_any[key])} in "
                    f"{example.group(0)}"
                )
