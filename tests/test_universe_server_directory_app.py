from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from tinyassets.universe_server import create_streamable_http_app, mcp

RETIRED_DIRECTORY_PATHS = (
    "/mcp-directory",
    "/mcp-directory/",
    "/mcp-directory/catalog/2026-06-24-underscore-handles",
    "/mcp-directory/catalog/future",
    "/mcp-directory/arbitrary-descendant",
    "/mcp-directory?catalog=future",
)

HTTP_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


@pytest.fixture
def client():
    with TestClient(create_streamable_http_app()) as test_client:
        yield test_client


def test_streamable_http_app_mounts_only_canonical_mcp() -> None:
    app = create_streamable_http_app()
    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/mcp" in paths
    assert not any(
        isinstance(path, str) and path.startswith("/mcp-directory") for path in paths
    )
    assert app.state.path == "/mcp"
    assert app.state.transport_type == "streamable-http"


def test_canonical_mcp_server_uses_exact_public_name() -> None:
    assert mcp.name == "TinyAssets"


@pytest.mark.parametrize("path", RETIRED_DIRECTORY_PATHS)
@pytest.mark.parametrize("method", HTTP_METHODS)
def test_retired_directory_paths_are_ordinary_404s(
    client: TestClient,
    path: str,
    method: str,
) -> None:
    response = client.request(
        method,
        path,
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-03-26",
        },
        content=b'{"jsonrpc":"2.0","id":1,"method":"initialize"}',
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert "location" not in response.headers
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == ("" if method == "HEAD" else "Not Found")


@pytest.mark.parametrize(
    "headers",
    (
        {"Accept": "text/html"},
        {"Accept": "application/json"},
        {"Accept": "text/event-stream"},
        {"Accept": "*/*", "MCP-Protocol-Version": "2025-03-26"},
        {"Accept": "application/json", "mcp-session-id": "retired-session"},
    ),
)
def test_retired_directory_path_never_enters_discovery_or_transport(
    client: TestClient,
    headers: dict[str, str],
) -> None:
    response = client.get(
        "/mcp-directory",
        headers=headers,
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert "location" not in response.headers
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Not Found"
