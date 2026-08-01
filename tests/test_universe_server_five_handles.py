"""The live /mcp surface advertises exactly the seven canonical public tools.

The legacy fat tools stay
registered + callable for one migration release but are hidden from tools/list
and logged on call by the _DeprecatedToolVisibility middleware.
"""
from __future__ import annotations

import asyncio
import json
import logging

import tinyassets.universe_server as universe_server
from tinyassets.universe_server import (
    _DEPRECATED_TOOL_NAMES,
    mcp,
    read_graph,
    write_graph,
)

CANONICAL_PUBLIC_TOOLS = {
    "read_graph",
    "write_graph",
    "run_graph",
    "read_page",
    "write_page",
    "converse",  # 2026-07-02 relay reshape: chatbot -> universe intelligence
    "get_status",
}

EXPECTED_ANNOTATIONS = {
    "read_graph": {"readOnlyHint": True, "idempotentHint": True},
    "write_graph": {"readOnlyHint": False, "openWorldHint": False},
    "run_graph": {"readOnlyHint": False, "openWorldHint": False},
    "read_page": {"readOnlyHint": True, "idempotentHint": True},
    "write_page": {"readOnlyHint": False, "openWorldHint": True},
    "converse": {"readOnlyHint": False, "openWorldHint": False},
    "get_status": {"readOnlyHint": True, "idempotentHint": True},
}


def _advertised_tools():
    """tools/list as a real MCP client sees it (middleware applied)."""
    return asyncio.run(mcp.list_tools(run_middleware=True))


def _registered_tools():
    """Every tool registered on the server (middleware bypassed)."""
    return asyncio.run(mcp.list_tools(run_middleware=False))


def test_live_surface_advertises_exactly_canonical_public_tools() -> None:
    advertised = {tool.name for tool in _advertised_tools()}
    assert advertised == CANONICAL_PUBLIC_TOOLS
    assert "converse" in advertised  # the relay handle is user-facing
    # No enumerated legacy fat tool leaks onto the advertised surface.
    assert _DEPRECATED_TOOL_NAMES.isdisjoint(advertised)


def test_legacy_tools_stay_registered_but_hidden() -> None:
    registered = {tool.name for tool in _registered_tools()}
    advertised = {tool.name for tool in _advertised_tools()}
    # Still registered (callable) ...
    assert _DEPRECATED_TOOL_NAMES <= registered
    # ... but not advertised.
    assert _DEPRECATED_TOOL_NAMES.isdisjoint(advertised)


def test_handle_annotations_match_contract() -> None:
    tools = {tool.name: tool for tool in _advertised_tools()}
    for name, expected in EXPECTED_ANNOTATIONS.items():
        ann = tools[name].annotations
        for key, value in expected.items():
            assert getattr(ann, key) == value, f"{name}.{key}"


def test_read_graph_status_returns_operator_status() -> None:
    payload = json.loads(read_graph(target="status"))
    assert "schema_version" in payload


def test_unknown_target_is_reported() -> None:
    payload = json.loads(read_graph(target="bogus"))
    assert payload["error"] == "unknown_target"
    assert payload["handle"] == "read_graph"
    assert {
        "agents",
        "agent",
        "agent_bindings",
        "agent_binding",
    } <= set(payload["allowed_targets"])


def test_custom_agent_reads_route_through_graph_handle(monkeypatch) -> None:
    observed: list[dict[str, object]] = []

    def fake_custom_agents(**kwargs):
        observed.append(kwargs)
        return {"routed": kwargs["action"]}

    monkeypatch.setattr(
        universe_server,
        "_custom_agents_impl",
        fake_custom_agents,
        raising=False,
    )

    listed = json.loads(
        read_graph(target="agents", query="coding", tags="agent,coding", limit=5)
    )
    exact = json.loads(
        read_graph(target="agent", agent_definition_id="agent_123")
    )
    stage = json.loads(
        read_graph(target="agent", agent_stage_id="agent_stage_123")
    )
    bindings = json.loads(
        read_graph(target="agent_bindings", graph_id="universe-a", limit=7)
    )
    binding = json.loads(
        read_graph(
            target="agent_binding",
            graph_id="universe-a",
            agent_binding_id="agent_binding_123",
        )
    )

    assert [listed, exact, stage, bindings, binding] == [
        {"routed": "list_agents"},
        {"routed": "get_agent"},
        {"routed": "get_import_stage"},
        {"routed": "list_bindings"},
        {"routed": "get_binding"},
    ]
    assert observed[0]["query"] == "coding"
    assert observed[1]["definition_id"] == "agent_123"
    assert observed[2]["stage_id"] == "agent_stage_123"
    assert observed[3]["universe_id"] == "universe-a"
    assert observed[4]["binding_id"] == "agent_binding_123"


def test_custom_agent_writes_route_through_graph_handle(monkeypatch) -> None:
    observed: list[dict[str, object]] = []

    def fake_custom_agents(**kwargs):
        observed.append(kwargs)
        return {"routed": kwargs["action"]}

    monkeypatch.setattr(
        universe_server,
        "_custom_agents_impl",
        fake_custom_agents,
        raising=False,
    )
    monkeypatch.setattr(universe_server, "write_gate_rejection", lambda name: None)

    published = json.loads(
        write_graph(
            target="agent",
            operation="remix",
            payload_json='{"schema_version":1}',
            idempotency_key="agent-publish-request-1",
        )
    )
    imported = json.loads(
        write_graph(
            target="agent",
            operation="import",
            payload_json='{"schema_version":1}',
        )
    )
    staged = json.loads(
        write_graph(
            target="agent",
            operation="stage_import",
            payload_json='{"source_json":{},"adapter":{}}',
            idempotency_key="agent-stage-request-1",
        )
    )
    published_stage = json.loads(
        write_graph(
            target="agent",
            operation="publish_stage",
            agent_stage_id="agent_stage_123",
            idempotency_key="agent-stage-publish-1",
        )
    )
    exported = json.loads(
        write_graph(
            target="agent",
            operation="convert_export",
            agent_definition_id="agent_123",
            payload_json='{"adapter_ref":"commons:foreign-export"}',
            idempotency_key="agent-export-1",
        )
    )
    bound = json.loads(
        write_graph(
            target="agent_binding",
            operation="bind",
            graph_id="universe-a",
            agent_definition_id="agent_123",
            payload_json='{"schema_version":1}',
        )
    )
    updated = json.loads(
        write_graph(
            target="agent_binding",
            operation="update",
            graph_id="universe-a",
            agent_definition_id="agent_456",
            agent_binding_id="agent_binding_123",
            expected_revision=4,
            payload_json='{"schema_version":1}',
        )
    )

    assert [published, imported, staged, published_stage, exported, bound, updated] == [
        {"routed": "publish_agent"},
        {"routed": "import_agent"},
        {"routed": "stage_import"},
        {"routed": "publish_stage"},
        {"routed": "convert_export"},
        {"routed": "create_binding"},
        {"routed": "update_binding"},
    ]
    assert observed[0]["idempotency_key"] == "agent-publish-request-1"
    assert observed[2]["idempotency_key"] == "agent-stage-request-1"
    assert observed[3]["stage_id"] == "agent_stage_123"
    assert observed[4]["definition_id"] == "agent_123"
    assert observed[5]["definition_id"] == "agent_123"
    assert observed[6]["binding_id"] == "agent_binding_123"
    assert observed[6]["expected_revision"] == 4


def test_unknown_custom_agent_operation_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(universe_server, "write_gate_rejection", lambda name: None)

    payload = json.loads(
        write_graph(target="agent", operation="overwrite-in-place")
    )

    assert payload["error"] == "unknown_agent_operation"
    assert payload["target"] == "agent"
    assert payload["allowed_operations"] == [
        "publish",
        "remix",
        "import",
        "stage_import",
        "publish_stage",
        "convert_export",
    ]


def test_custom_agent_definition_and_binding_round_trip(monkeypatch, tmp_path) -> None:
    from tinyassets.api import permissions
    from tinyassets.daemon_server import grant_universe_access

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(universe_server, "write_gate_rejection", lambda name: None)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "alice")

    definition_payload = {
        "schema_version": 1,
        "name": "Connector coding agent",
        "description": "Creates and tests user-authored branches.",
        "tags": ["coding", "agent"],
        "components": {
            "identity": {
                "kind": "soul",
                "config": {"instructions": "Work in small verified steps."},
            },
            "workflow": {
                "kind": "branch_set",
                "config": {"refs": ["branch-test-and-iterate"]},
            },
        },
    }
    published = json.loads(
        write_graph(
            target="agent",
            operation="publish",
            payload_json=json.dumps(definition_payload),
            idempotency_key="connector-agent-round-trip",
        )
    )
    definition_id = published["agent"]["agent_definition_id"]

    public = json.loads(
        read_graph(target="agent", agent_definition_id=definition_id)
    )
    assert public["agent"]["components"]["workflow"]["kind"] == "branch_set"

    grant_universe_access(
        tmp_path,
        universe_id="universe-a",
        actor_id="alice",
        permission="admin",
        granted_by="alice",
    )
    binding_payload = {
        "schema_version": 1,
        "name": "My connector coding agent",
        "role": "Maintain the test-and-iterate loop",
        "resources": {
            "github": {"resource_binding_id": "resource-github-1"},
        },
        "channels": {
            "slack": {
                "adapter_ref": "commons:slack",
                "address_ref": "channel-address-1",
            }
        },
    }
    bound = json.loads(
        write_graph(
            target="agent_binding",
            operation="bind",
            graph_id="universe-a",
            agent_definition_id=definition_id,
            payload_json=json.dumps(binding_payload),
        )
    )
    binding_id = bound["binding"]["agent_binding_id"]

    private = json.loads(
        read_graph(
            target="agent_binding",
            graph_id="universe-a",
            agent_binding_id=binding_id,
        )
    )
    assert private["binding"]["status"] == "configured"
    assert private["binding"]["configuration"]["channels"]["slack"] == {
        "adapter_ref": "commons:slack",
        "address_ref": "channel-address-1",
    }


def test_goal_write_and_read_round_trip(monkeypatch, tmp_path) -> None:
    """write_graph(goal) routes to the same handler read_graph(goals) reads."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "canonical-handle-test")

    from tinyassets.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        proposed = json.loads(
            write_graph(
                target="goal",
                name="Canonical handle smoke goal",
                tags="pr178,smoke",
                visibility="public",
            )
        )
        assert proposed["status"] == "proposed"

        searched = json.loads(
            read_graph(target="goals", query="Canonical handle smoke")
        )
        assert searched["count"] >= 1
        assert any(
            goal["goal_id"] == proposed["goal"]["goal_id"]
            for goal in searched["goals"]
        )
    finally:
        invalidate_backend_cache()


def test_deprecated_legacy_tool_callable_and_logged(monkeypatch, tmp_path, caplog) -> None:
    """A hidden legacy tool still dispatches by plain name and logs deprecation."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    from tinyassets.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        with caplog.at_level(logging.WARNING, logger="universe_server"):
            result = asyncio.run(mcp.call_tool("universe", {"action": "list"}))
        assert result is not None
        assert "deprecated-tool-call name=universe" in caplog.text
    finally:
        invalidate_backend_cache()
