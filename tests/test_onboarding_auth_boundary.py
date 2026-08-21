"""The onboarding route's auth boundary, through the REAL AuthContextMiddleware.

Reproduces the Codex-found scenario (require-auth mode) end to end at the ASGI
layer: `/mcp/app` must load anonymously (no challenge) while `/mcp` and other
`/mcp/*` paths still get the OAuth challenge. Complements the handler-level tests
in test_onboarding_app.py, which called the handler directly and so could not have
caught a middleware-level 401.
"""

from __future__ import annotations

import asyncio

import pytest

from tinyassets.auth import middleware as mw


class _RequireAuthProvider:
    """A provider in the strictest mode: challenge every unauthenticated /mcp*."""

    def resolve_token(self, token):
        return None

    def is_auth_required(self):
        return True

    def resolve_always_writes(self):
        return False

    def writes_require_identity(self):
        return True

    def challenge_unauthenticated(self):
        return True


@pytest.fixture
def require_auth_provider():
    saved = mw._provider
    mw.set_provider(_RequireAuthProvider())
    try:
        yield
    finally:
        mw._provider = saved


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"ok"})


def _drive(path: str, method: str = "GET") -> int:
    """Drive one anonymous request through AuthContextMiddleware; return status."""
    app = mw.AuthContextMiddleware(_ok_app)
    scope = {"type": "http", "method": method, "path": path, "headers": []}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts, "no response.start emitted"
    return starts[0]["status"]


def test_onboarding_path_not_challenged_in_require_auth_mode(require_auth_provider):
    # The blocker Codex found: without the exemption this returned 401.
    assert _drive("/mcp/app") == 200


def test_mcp_endpoint_still_challenges_anonymous(require_auth_provider):
    # The exemption must be scoped: the transport endpoint still challenges.
    assert _drive("/mcp") == 401


def test_other_mcp_subpath_still_challenges(require_auth_provider):
    assert _drive("/mcp/something-else") == 401


# --- pure predicate: the exemption itself ---


def test_challenge_path_exempts_only_the_app_route():
    assert mw._auth_challenge_path("/mcp/app") is False
    # The same-origin PKCE token-exchange proxy runs before any bearer exists.
    assert mw._auth_challenge_path("/mcp/app/token") is False
    assert mw._auth_challenge_path("/mcp") is True
    assert mw._auth_challenge_path("/mcp/") is True
    assert mw._auth_challenge_path("/mcp/app/callback") is True  # not the served path
    assert mw._auth_challenge_path("/mcp/app/token/x") is True  # exact-match only, no prefix bypass
    assert mw._auth_challenge_path("/.well-known/oauth-protected-resource") is False


def _drive_h(path: str, method: str = "POST", headers: dict | None = None) -> int:
    """Like _drive but with request headers, to exercise the bearer path."""
    app = mw.AuthContextMiddleware(_ok_app)
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": method, "path": path, "headers": hdrs}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert starts, "no response.start emitted"
    return starts[0]["status"]


def test_hook_route_ignores_foreign_bearer(require_auth_provider, monkeypatch):
    """A generic channel POSTing to /mcp/hooks/<token> with its OWN Authorization:
    Bearer must NOT be 401'd by the MCP challenge — the unguessable URL token +
    author-gated handler are the boundary (Codex inbound review). Without the
    carve-out an invalid bearer returned 401 before the hook handler ran."""
    tok = "a" * 43
    monkeypatch.setenv("TINYASSETS_INBOUND_ENABLED", "1")
    # foreign bearer + valid hook path -> reaches the downstream app (200)
    assert _drive_h("/mcp/hooks/" + tok, headers={"Authorization": "Bearer foreign.xyz"}) == 200
    # the same foreign bearer on the MCP endpoint is still challenged (401)
    assert _drive_h("/mcp", headers={"Authorization": "Bearer foreign.xyz"}) == 401
    # inbound OFF -> no carve-out, the hook path with a foreign bearer is 401'd
    monkeypatch.delenv("TINYASSETS_INBOUND_ENABLED", raising=False)
    assert _drive_h("/mcp/hooks/" + tok, headers={"Authorization": "Bearer foreign.xyz"}) == 401
