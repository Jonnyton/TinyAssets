from __future__ import annotations

from workflow.connector_catalog import DIRECTORY_MCP_PATH, VERSIONED_DIRECTORY_MCP_PATH
from workflow.universe_server import create_streamable_http_app


def test_streamable_http_app_mounts_legacy_and_directory_surfaces() -> None:
    app = create_streamable_http_app()
    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/mcp" in paths
    assert DIRECTORY_MCP_PATH in paths
    assert VERSIONED_DIRECTORY_MCP_PATH in paths
    assert app.state.path == f"/mcp,{DIRECTORY_MCP_PATH},{VERSIONED_DIRECTORY_MCP_PATH}"
    assert app.state.transport_type == "streamable-http"
