from __future__ import annotations

from tinyassets.connector_catalog import DIRECTORY_MCP_PATH, VERSIONED_DIRECTORY_MCP_PATH
from tinyassets.universe_server import create_streamable_http_app


def test_streamable_http_app_mounts_legacy_and_directory_surfaces() -> None:
    app = create_streamable_http_app()
    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/mcp" in paths
    assert DIRECTORY_MCP_PATH in paths
    assert VERSIONED_DIRECTORY_MCP_PATH in paths
    assert app.state.path == f"/mcp,{DIRECTORY_MCP_PATH},{VERSIONED_DIRECTORY_MCP_PATH}"
    assert app.state.transport_type == "streamable-http"


def test_http_app_exposes_no_universe_creation_route() -> None:
    """universe-creation task 5.1: HTTP cannot create a universe.

    There is no ``POST /v1/universes`` (or any universe-creation) REST route.
    The only public universe-birth surfaces are the MCP tools
    (``universe action=create_universe`` and ``write_graph target=universe``),
    whose public-birth boundary lives at the shared dispatch chokepoint. This
    test fails loudly if a universe-creation HTTP route is ever mounted.
    """
    app = create_streamable_http_app()
    paths = {getattr(route, "path", "") or "" for route in app.routes}

    assert not any("universe" in path.lower() for path in paths), sorted(paths)
