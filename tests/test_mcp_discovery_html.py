"""Tests for substrate-fix #11 / Family A Phase 1.A: MCP endpoint discovery.

When a browser GETs /mcp or /mcp-directory with Accept: text/html, the server
should return a discovery HTML page explaining the endpoint and how to connect.
Default curl and JSON probes should receive compact discovery JSON. MCP
transport requests (POST with JSON-RPC, GET with text/event-stream, or any
request with MCP transport/session headers) must pass through unchanged.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def app():
    from workflow.universe_server import create_streamable_http_app

    return create_streamable_http_app()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def test_browser_get_mcp_returns_discovery_html(client):
    """GET /mcp with Accept: text/html returns discovery HTML, not MCP error."""
    response = client.get("/mcp", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Workflow MCP Server" in body
    assert "MCP" in body  # at least mentions MCP


def test_browser_get_mcp_directory_returns_discovery_html(client):
    """GET /mcp-directory with Accept: text/html returns discovery HTML."""
    response = client.get("/mcp-directory", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Workflow MCP Server" in response.text


def test_default_get_mcp_returns_discovery_json(client):
    """Default curl-style GET returns discovery JSON, not a transport error."""
    response = client.get("/mcp", headers={"Accept": "*/*"})
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    payload = response.json()
    assert payload["type"] == "mcp_server_endpoint"
    assert payload["transport"] == "streamable-http"
    assert "text/event-stream" in payload["how_to_connect"]["client_accept_header"]


def test_json_get_mcp_directory_returns_discovery_json(client):
    """GET /mcp-directory with Accept: application/json returns discovery JSON."""
    response = client.get(
        "/mcp-directory",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["related"]["directory_endpoint"].endswith("/mcp-directory")


def test_head_mcp_returns_discovery_headers(client):
    """HEAD /mcp returns discovery headers for browser-like probes."""
    response = client.head("/mcp", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.text == ""


def test_get_with_mcp_protocol_version_header_passes_through(client):
    """Real MCP client GET with MCP-Protocol-Version header passes through to
    transport (returns whatever FastMCP returns — usually 405 or transport
    error, NOT the discovery HTML)."""
    response = client.get(
        "/mcp",
        headers={
            "Accept": "text/html",
            "MCP-Protocol-Version": "2025-03-26",
        },
    )
    # Whatever FastMCP returns; the key is it should NOT be the discovery HTML
    assert "Workflow MCP Server" not in response.text


def test_get_with_sse_accept_passes_through(client):
    """Streamable HTTP SSE leg should not receive discovery output."""
    response = client.get("/mcp", headers={"Accept": "text/event-stream"})
    assert "Workflow MCP Server" not in response.text
    assert "mcp_server_endpoint" not in response.text


def test_get_with_mcp_session_header_passes_through(client):
    """Existing Streamable HTTP sessions should not receive discovery JSON."""
    response = client.get(
        "/mcp",
        headers={
            "Accept": "application/json",
            "mcp-session-id": "session-1",
        },
    )
    assert response.status_code != 200 or "mcp_server_endpoint" not in response.text


def test_post_mcp_passes_through(client):
    """POST requests must stay owned by the MCP transport."""
    response = client.post(
        "/mcp",
        headers={"Accept": "text/html"},
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
    )
    assert "Workflow MCP Server" not in response.text
    assert "mcp_server_endpoint" not in response.text
