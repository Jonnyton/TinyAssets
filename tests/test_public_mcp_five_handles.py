from __future__ import annotations

import asyncio
import json

from workflow import universe_server as us

PUBLIC_HANDLES = {
    "read.graph",
    "write.graph",
    "run.graph",
    "read.page",
    "write.page",
}

LEGACY_TOOL_NAMES = {
    "universe",
    "extensions",
    "goals",
    "gates",
    "wiki",
    "get_status",
    "community_change_context",
}


def _list_tools():
    return asyncio.run(us.mcp.list_tools(run_middleware=False))


def test_public_mcp_surface_is_exactly_five_handles() -> None:
    tools = {tool.name: tool for tool in _list_tools()}

    assert set(tools) == PUBLIC_HANDLES
    assert set(tools).isdisjoint(LEGACY_TOOL_NAMES)


def test_public_handle_annotations_match_read_write_run_boundaries() -> None:
    tools = {tool.name: tool for tool in _list_tools()}

    assert tools["read.graph"].annotations.readOnlyHint is True
    assert tools["read.page"].annotations.readOnlyHint is True
    assert tools["write.graph"].annotations.readOnlyHint is False
    assert tools["write.page"].annotations.readOnlyHint is False
    assert tools["run.graph"].annotations.readOnlyHint is False


def test_legacy_tool_names_are_not_advertised_as_public_paths() -> None:
    for tool in _list_tools():
        text = f"{tool.name}\n{tool.title or ''}\n{tool.description or ''}"
        for legacy_name in LEGACY_TOOL_NAMES:
            assert f"`{legacy_name}`" not in text
            assert f"{legacy_name} action=" not in text


def test_read_graph_routes_to_existing_private_universe_impl(monkeypatch) -> None:
    seen = {}

    def fake_universe_impl(**kwargs):
        seen.update(kwargs)
        return json.dumps({"status": "ok"})

    monkeypatch.setattr(us, "_universe_impl", fake_universe_impl)

    out = json.loads(us.read_graph(
        target="universe",
        operation="inspect",
        universe_id="u1",
        query="needle",
        payload_json='{"filename": "latest.md"}',
    ))

    assert out == {"status": "ok"}
    assert seen["action"] == "inspect"
    assert seen["universe_id"] == "u1"
    assert seen["query"] == "needle"
    assert seen["filename"] == "latest.md"


def test_read_graph_filters_cross_target_fields_for_real_impl() -> None:
    out = json.loads(us.read_graph(
        target="universe",
        operation="list",
        query="ignored-by-universe",
        branch_def_id="ignored-by-universe",
    ))

    assert "error" not in out


def test_write_page_routes_to_existing_private_wiki_impl(monkeypatch) -> None:
    seen = {}

    def fake_wiki_impl(**kwargs):
        seen.update(kwargs)
        return json.dumps({"status": "ok"})

    monkeypatch.setattr(us, "_wiki_impl", fake_wiki_impl)

    out = json.loads(us.write_page(
        operation="write",
        page="drafts/example.md",
        content="hello",
    ))

    assert out == {"status": "ok"}
    assert seen == {
        "action": "write",
        "page": "drafts/example.md",
        "content": "hello",
        "kind": "bug",
    }
