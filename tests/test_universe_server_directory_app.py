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


def test_lifespan_shutdown_drains_the_ingress_executor(monkeypatch) -> None:
    """Codex #1: the app-ingress executor's graceful drain is only useful if the
    daemon actually calls it on shutdown. Drive the REAL app lifespan (startup +
    teardown via ``with TestClient(...)``) and assert the drain runs on teardown.

    The lifespan imports ``shutdown_ingress_executor`` fresh in its ``finally``, so
    patching the module attribute is picked up at teardown time.
    """
    import tinyassets.app_ingress_workers as workers

    # Isolate from any singleton other test modules left behind: start from a fresh,
    # clean executor so the lifespan drains real (empty) state and returns cleanly.
    # (The test asserts the lifespan CALLS the drain — the wiring — not that it drains
    # arbitrary accumulated global state.)
    monkeypatch.setattr(workers, "_EXECUTOR", None, raising=False)
    workers.get_ingress_executor()  # a fresh, pre-warmed, idle singleton (running=0)

    calls = {"n": 0}
    real = workers.shutdown_ingress_executor

    def _spy(wait: bool = True) -> int:
        calls["n"] += 1
        return real(wait=wait)

    monkeypatch.setattr(workers, "shutdown_ingress_executor", _spy)

    with TestClient(create_streamable_http_app()):
        pass  # lifespan startup, then teardown on exit

    assert calls["n"] >= 1  # the daemon lifecycle drained the ingress executor
    monkeypatch.setattr(workers, "_EXECUTOR", None, raising=False)  # leave it clean


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


def test_http_app_exposes_no_universe_creation_route() -> None:
    """universe-creation task 5.1: HTTP cannot create a universe.

    There is no ``POST /v1/universes`` (or any universe-creation) REST route.
    The only public universe-birth surface is the canonical MCP tools
    (``universe action=create_universe`` and ``write_graph target=universe``),
    whose public-birth boundary lives at the shared dispatch chokepoint. This
    test fails loudly if a universe-creation HTTP route is ever mounted — and
    holds alongside the #1722 /mcp-directory retirement, since the canonical
    ``/mcp`` and discovery routes carry no "universe" path segment.
    """
    app = create_streamable_http_app()
    paths = {getattr(route, "path", "") or "" for route in app.routes}

    assert not any("universe" in path.lower() for path in paths), sorted(paths)
