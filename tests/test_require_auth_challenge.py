"""Require-auth challenge: a MISSING token on the MCP endpoint returns a 401
WWW-Authenticate challenge when the provider opts in (WORKOS_REQUIRE_AUTH), so
MCP clients (which only start OAuth on a 401) actually prompt the founder to
sign in — otherwise the connector connects anonymously and first-contact never
fires. Discovery routes stay public so the client can find the AS.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tinyassets.auth.middleware import (
    AuthContextMiddleware,
    _auth_challenge_path,
    auth_middleware,
    set_provider,
)
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

_SUBJECT = Identity(user_id="founder-1", username="founder-1", capabilities=["read", "write"])


class _ChallengeProvider(AuthProvider):
    """Resolve-always provider that opts into the missing-token challenge."""

    def __init__(self, *, challenge: bool) -> None:
        self._challenge = challenge

    def resolve_token(self, token: str) -> Identity | None:
        return _SUBJECT if token == "valid" else None

    def is_auth_required(self) -> bool:
        return False

    def resolve_always_writes(self) -> bool:
        return True

    def challenge_unauthenticated(self) -> bool:
        return self._challenge

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"client_id": "t", **metadata}

    def create_authorization(self, *a: Any, **k: Any) -> str:
        return "c"

    def exchange_code(self, *a: Any, **k: Any) -> dict[str, Any] | None:
        return None


@pytest.fixture(autouse=True)
def _reset_auth():
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _drive(path: str, *, token: str | None) -> tuple[list[dict], bool]:
    """Run one request through AuthContextMiddleware; return (sent, app_called)."""
    called = {"hit": False}

    async def _app(scope, receive, send):  # noqa: ANN001, ANN202
        called["hit"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sent: list[dict] = []

    async def _send(msg):  # noqa: ANN001, ANN202
        sent.append(msg)

    async def _receive():  # noqa: ANN202
        return {"type": "http.request", "body": b""}

    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode("latin1")))
    scope = {"type": "http", "path": path, "headers": headers}
    asyncio.run(AuthContextMiddleware(_app)(scope, _receive, _send))
    return sent, called["hit"]


def _status(sent: list[dict]) -> int:
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def _www_authenticate(sent: list[dict]) -> str:
    start = next(m for m in sent if m["type"] == "http.response.start")
    for k, v in start["headers"]:
        if k == b"www-authenticate":
            return v.decode("latin1")
    return ""


def test_missing_token_on_mcp_is_challenged_when_opted_in():
    set_provider(_ChallengeProvider(challenge=True))
    sent, app_called = _drive("/mcp", token=None)
    assert not app_called                       # request never reached the app
    assert _status(sent) == 401
    wa = _www_authenticate(sent)
    assert "resource_metadata=" in wa
    assert "invalid_token" not in wa            # missing != invalid (RFC 6750)


def test_discovery_routes_stay_public_under_challenge():
    set_provider(_ChallengeProvider(challenge=True))
    for path in (
        "/.well-known/oauth-protected-resource",
        "/mcp/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
    ):
        sent, app_called = _drive(path, token=None)
        assert app_called, f"{path} must not be challenged"
        assert _status(sent) == 200


def test_valid_token_on_mcp_passes_through():
    set_provider(_ChallengeProvider(challenge=True))
    sent, app_called = _drive("/mcp", token="valid")
    assert app_called
    assert _status(sent) == 200


def test_no_challenge_when_not_opted_in_stays_anonymous():
    set_provider(_ChallengeProvider(challenge=False))
    sent, app_called = _drive("/mcp", token=None)
    assert app_called                           # anonymous read proceeds
    assert _status(sent) == 200


def test_invalid_token_still_challenged_as_invalid():
    set_provider(_ChallengeProvider(challenge=True))
    sent, app_called = _drive("/mcp", token="bad")
    assert not app_called
    assert _status(sent) == 401
    assert 'error="invalid_token"' in _www_authenticate(sent)


def test_auth_challenge_path_targets_mcp_only():
    assert _auth_challenge_path("/mcp") is True
    assert _auth_challenge_path("/mcp/") is True
    assert _auth_challenge_path("/mcp/.well-known/oauth-protected-resource") is False
    assert _auth_challenge_path("/.well-known/oauth-protected-resource") is False
    assert _auth_challenge_path("/mcp-directory") is False  # sibling public surface


def test_challenge_metadata_url_is_routed_in_production(monkeypatch):
    # In production only /mcp* is proxied to the daemon, so the challenge must
    # advertise a /mcp-prefixed (routed) PRM, not the apex root path that 404s.
    from tinyassets.auth.middleware import _challenge_prm_url

    monkeypatch.setenv("WORKOS_MCP_RESOURCE", "https://tinyassets.io/mcp")
    assert (
        _challenge_prm_url()
        == "https://tinyassets.io/mcp/.well-known/oauth-protected-resource"
    )


def test_challenge_header_is_exact(monkeypatch):
    monkeypatch.setenv("WORKOS_MCP_RESOURCE", "https://tinyassets.io/mcp")
    set_provider(_ChallengeProvider(challenge=True))
    sent, _ = _drive("/mcp", token=None)
    assert _www_authenticate(sent) == (
        'Bearer resource_metadata='
        '"https://tinyassets.io/mcp/.well-known/oauth-protected-resource"'
    )


def test_workos_provider_challenge_respects_env(monkeypatch):
    from tinyassets.auth.workos_provider import WorkOSAuthProvider

    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "example.authkit.app")
    monkeypatch.setenv("WORKOS_ALLOW_NO_AUDIENCE", "1")

    monkeypatch.delenv("WORKOS_REQUIRE_AUTH", raising=False)
    assert WorkOSAuthProvider.from_env().challenge_unauthenticated() is False

    monkeypatch.setenv("WORKOS_REQUIRE_AUTH", "1")
    assert WorkOSAuthProvider.from_env().challenge_unauthenticated() is True
