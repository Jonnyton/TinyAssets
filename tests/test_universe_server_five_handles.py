"""PR-178: the live /mcp surface advertises exactly the five canonical handles.

Forward-ported from the /mcp-directory surface onto tinyassets.universe_server
(the process behind https://tinyassets.io/mcp). The legacy fat tools stay
registered + callable for one migration release but are hidden from tools/list
and logged on call by the _DeprecatedToolVisibility middleware.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import tinyassets.universe_server as universe_server
from tinyassets.universe_server import (
    _DEPRECATED_TOOL_NAMES,
    mcp,
    read_graph,
    read_page,
    write_graph,
)

CANONICAL_HANDLES = {
    "read_graph",
    "write_graph",
    "run_graph",
    "read_page",
    "write_page",
    "converse",  # 2026-07-02 relay reshape: chatbot -> universe intelligence
}

# The advertised user surface is the canonical handles plus the get_status read.
ADVERTISED = CANONICAL_HANDLES | {"get_status"}

EXPECTED_ANNOTATIONS = {
    "read_graph": {"readOnlyHint": True, "idempotentHint": True},
    "write_graph": {"readOnlyHint": False, "openWorldHint": False},
    "run_graph": {"readOnlyHint": False, "openWorldHint": False},
    "read_page": {"readOnlyHint": True, "idempotentHint": True},
    "write_page": {"readOnlyHint": False, "openWorldHint": True},
    "converse": {"readOnlyHint": False, "openWorldHint": False},
}


def _advertised_tools():
    """tools/list as a real MCP client sees it (middleware applied)."""
    return asyncio.run(mcp.list_tools(run_middleware=True))


def _registered_tools():
    """Every tool registered on the server (middleware bypassed)."""
    return asyncio.run(mcp.list_tools(run_middleware=False))


def test_live_surface_advertises_exactly_canonical_handles_plus_status() -> None:
    advertised = {tool.name for tool in _advertised_tools()}
    assert advertised == ADVERTISED
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


def test_read_graph_status_is_full_not_directory_redacted() -> None:
    """The live operator surface keeps the full get_status (unredacted)."""
    payload = json.loads(read_graph(target="status"))
    assert "schema_version" in payload
    # The directory redactor injects this marker; the live surface must not.
    assert "directory_privacy_note" not in payload


def test_unknown_target_is_reported() -> None:
    payload = json.loads(read_graph(target="bogus"))
    assert payload["error"] == "unknown_target"
    assert payload["handle"] == "read_graph"


def test_write_graph_branch_without_id_routes_to_existing_build_handler(
    monkeypatch,
) -> None:
    calls = []

    def fake_extensions_impl(**kwargs):
        calls.append(kwargs)
        return json.dumps({"status": "built"})

    monkeypatch.setattr(universe_server, "_extensions_impl", fake_extensions_impl)

    payload = json.loads(
        write_graph(target="branch", spec_json='{"name":"Research tracker"}')
    )

    assert payload == {"status": "built"}
    assert calls == [
        {
            "action": "build_branch",
            "spec_json": '{"name":"Research tracker"}',
        }
    ]


def test_write_graph_branch_with_id_keeps_patch_handler(monkeypatch) -> None:
    calls = []

    def fake_extensions_impl(**kwargs):
        calls.append(kwargs)
        return json.dumps({"status": "patched"})

    monkeypatch.setattr(universe_server, "_extensions_impl", fake_extensions_impl)

    payload = json.loads(
        write_graph(
            target="branch",
            branch_id="branch-123",
            changes_json='[{"op":"set_description","description":"Updated"}]',
        )
    )

    assert payload == {"status": "patched"}
    assert calls == [
        {
            "action": "patch_branch",
            "branch_def_id": "branch-123",
            "changes_json": '[{"op":"set_description","description":"Updated"}]',
        }
    ]


def test_write_graph_rejects_mixed_branch_create_and_patch_payloads(
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        universe_server,
        "_extensions_impl",
        lambda **kwargs: calls.append(kwargs),
    )

    payload = json.loads(
        write_graph(
            target="branch",
            branch_id="branch-123",
            spec_json='{"name":"Ambiguous"}',
        )
    )

    assert payload["error"] == "ambiguous_branch_write"
    assert calls == []


def test_public_handle_schema_advertises_discovery_scope_and_branch_spec() -> None:
    tools = {tool.name: tool for tool in _advertised_tools()}

    read_properties = tools["read_page"].parameters["properties"]
    assert read_properties["scope"]["default"] == "discovery"
    assert "coordination" in read_properties["scope"]["description"]

    write_properties = tools["write_graph"].parameters["properties"]
    assert write_properties["spec_json"]["default"] == ""
    assert "workflow definition schema" in write_properties["spec_json"][
        "description"
    ].lower()


def test_workflow_definition_schema_is_in_default_discovery(
    monkeypatch, tmp_path
) -> None:
    wiki_root = tmp_path / "Wiki"
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))

    payload = json.loads(
        read_page(query="workflow definition schema", max_results=10)
    )

    match = next(
        item
        for item in payload["results"]
        if item["path"] == "pages/workflows/workflow-definition-schema.md"
    )
    assert match["title"] == "Workflow Definition Schema"


def test_documented_workflow_definition_builds_and_reads_back(
    monkeypatch, tmp_path
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    schema_page = (
        repo_root
        / "tinyassets"
        / "wiki"
        / "workflow-definition-schema.md"
    ).read_text(encoding="utf-8")
    documented_spec = schema_page.split("```json\n", 1)[1].split("\n```", 1)[0]
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "workflow-schema-test")

    from tinyassets.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        built = json.loads(write_graph(target="branch", spec_json=documented_spec))
        assert built["status"] == "built", built

        read_back = json.loads(
            read_graph(target="branch", branch_id=built["branch_def_id"])
        )
        assert read_back["name"] == "Research claims tracker"
        assert read_back["entry_point"] == "collect"
    finally:
        invalidate_backend_cache()


def test_goal_write_and_read_round_trip(monkeypatch, tmp_path) -> None:
    """write_graph(goal) routes to the same handler read_graph(goals) reads."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "five-handle-test")

    from tinyassets.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        proposed = json.loads(
            write_graph(
                target="goal",
                name="Five handle smoke goal",
                tags="pr178,smoke",
                visibility="public",
            )
        )
        assert proposed["status"] == "proposed"

        searched = json.loads(read_graph(target="goals", query="Five handle smoke"))
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
