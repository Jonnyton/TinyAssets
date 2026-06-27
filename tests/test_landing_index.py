"""Tests for the `/` landing-page handler on the MCP server.

Task #72. Serves a minimal HTML index at the server root so
tinyassets.io/ returns a human-readable page instead of 404 while
the GoDaddy-hosted landing is being restored. The `/mcp` endpoint
remains the actual MCP surface.
"""

from __future__ import annotations

import asyncio
import re

from tinyassets.universe_server import _landing_index
def _run(handler_coro):
    return asyncio.run(handler_coro)


def test_handler_returns_html_response_with_body():
    """Handler returns a Starlette HTMLResponse with a non-empty body."""
    response = _run(_landing_index(request=None))

    # HTMLResponse class check — should be importable.
    from starlette.responses import HTMLResponse
    assert isinstance(response, HTMLResponse)
    # Body contains the expected page shell.
    body = response.body.decode("utf-8")
    assert body.startswith("<!doctype html>")
    assert "<title>TinyAssets Server</title>" in body


def test_landing_body_has_required_content():
    """Landing must carry the project name, 1-line pitch, and the
    required links (GitHub + /mcp endpoint)."""
    response = _run(_landing_index(request=None))
    body = response.body.decode("utf-8")

    assert "TinyAssets Server" in body
    assert "daemon engine" in body  # 1-line pitch
    # GitHub link present.
    assert re.search(r'https?://github\.com/[^"]+', body) is not None
    # /mcp endpoint link present.
    assert '"/mcp"' in body or "'/mcp'" in body


def test_landing_content_type_is_text_html():
    response = _run(_landing_index(request=None))

    # HTMLResponse defaults to text/html media type.
    assert response.media_type == "text/html"


def test_landing_is_lightweight():
    """Body should be <10KB — pure static HTML, no heavy templating.

    Guards against future bloat that would make a simple 404-avoider
    expensive to serve.
    """
    response = _run(_landing_index(request=None))
    assert len(response.body) < 10_000


def test_no_mcp_dispatch_bypass():
    """Regression guard: the landing handler must NOT call into the
    universe() dispatcher or any MCP tool. It's a pure static response.

    If someone later adds dynamic content (e.g. "universe count"), they
    need to think about auth + caching — a bare `/` route has no auth
    by design, so leaking internal state here is a real risk.
    """
    import inspect

    from tinyassets import universe_server
    source = inspect.getsource(universe_server._landing_index)
    # Crude but effective — the handler body should reference neither
    # the internal dispatcher nor the universe tool surface.
    assert "universe(" not in source, (
        "Landing must not invoke MCP tools; it's an unauthenticated root."
    )
    assert "_dispatch_with_ledger" not in source
