"""Tests for substrate-fix #11 / Family A Phase 1.A: MCP endpoint discovery HTML.

When a browser GETs /mcp or /mcp-directory with Accept: text/html, the server
should return a discovery HTML page explaining the endpoint and how to connect.
MCP transport requests (POST with JSON-RPC, GET with text/event-stream, or
any request with MCP-Protocol-Version header) must pass through unchanged.
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
