"""Unit tests for the onboarding app server: PKCE, authorize URL, token
exchange fields, and the /mcp proxy's auth injection + error handling.

No network: the OAuth metadata is pre-seeded and urlopen is monkeypatched.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys
import urllib.parse
from pathlib import Path

import pytest

# Load app_server.py directly (it lives outside any importable package).
_APP_SERVER = Path(__file__).resolve().parents[1] / "app_server.py"
_spec = importlib.util.spec_from_file_location("ta_app_server", _APP_SERVER)
app_server = importlib.util.module_from_spec(_spec)
sys.modules["ta_app_server"] = app_server
_spec.loader.exec_module(app_server)


@pytest.fixture(autouse=True)
def _seed_oauth(monkeypatch):
    """Short-circuit discovery so pure helpers never touch the network."""
    monkeypatch.setitem(
        app_server._OAUTH_META, "issuer", "https://as.example"
    )
    monkeypatch.setitem(
        app_server._OAUTH_META, "authorization_endpoint", "https://as.example/oauth2/authorize"
    )
    monkeypatch.setitem(
        app_server._OAUTH_META, "token_endpoint", "https://as.example/oauth2/token"
    )
    monkeypatch.setitem(
        app_server._OAUTH_META, "registration_endpoint", "https://as.example/oauth2/register"
    )
    yield


def test_pkce_pair_is_valid_s256():
    verifier, challenge = app_server.pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert challenge == expected
    assert "=" not in challenge  # unpadded per RFC 7636


def test_pkce_pair_is_random():
    assert app_server.pkce_pair()[0] != app_server.pkce_pair()[0]


def test_build_authorize_url_carries_required_params():
    url = app_server.build_authorize_url(
        client_id="client_123", state="st-abc", code_challenge="chal-xyz"
    )
    assert url.startswith("https://as.example/oauth2/authorize?")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert q["response_type"] == "code"
    assert q["client_id"] == "client_123"
    assert q["state"] == "st-abc"
    assert q["code_challenge"] == "chal-xyz"
    assert q["code_challenge_method"] == "S256"
    assert q["redirect_uri"].endswith("/callback")
    # RFC 8707: the token must be bound to the MCP resource.
    assert q["resource"] == app_server.MCP_RESOURCE
    assert "openid" in q["scope"]


def test_exchange_code_sends_pkce_verifier_and_resource(monkeypatch):
    captured = {}

    def fake_post_form(url, fields, **_kw):
        captured["url"] = url
        captured["fields"] = fields
        return {"access_token": "at-1", "refresh_token": "rt-1"}

    monkeypatch.setattr(app_server, "_http_post_form", fake_post_form)
    tokens = app_server.exchange_code(
        code="the-code", code_verifier="the-verifier", client_id="client_123"
    )
    assert tokens["access_token"] == "at-1"
    assert captured["url"] == "https://as.example/oauth2/token"
    f = captured["fields"]
    assert f["grant_type"] == "authorization_code"
    assert f["code"] == "the-code"
    assert f["code_verifier"] == "the-verifier"
    assert f["client_id"] == "client_123"
    assert f["resource"] == app_server.MCP_RESOURCE


def test_refresh_token_uses_refresh_grant(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        app_server,
        "_http_post_form",
        lambda url, fields, **_kw: captured.update(fields) or {"access_token": "at-2"},
    )
    app_server.refresh_token(refresh="rt-1", client_id="client_123")
    assert captured["grant_type"] == "refresh_token"
    assert captured["refresh_token"] == "rt-1"
    assert captured["resource"] == app_server.MCP_RESOURCE


def test_passthrough_headers_filters_to_safe_subset():
    src = {
        "content-type": "text/event-stream",
        "mcp-session-id": "sess-9",
        "www-authenticate": 'Bearer resource_metadata="x"',
        "set-cookie": "leak=1",
        "server": "cloudflare",
    }
    out = app_server._passthrough_headers(src)
    assert out == {
        "content-type": "text/event-stream",
        "mcp-session-id": "sess-9",
        "www-authenticate": 'Bearer resource_metadata="x"',
    }


class _FakeResp:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def test_proxy_mcp_injects_bearer_and_session(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None, context=None):
        seen["auth"] = req.get_header("Authorization")
        seen["session"] = req.get_header("Mcp-session-id")
        seen["data"] = req.data
        return _FakeResp(200, {"content-type": "application/json", "mcp-session-id": "s-77"}, b'{"ok":1}')

    monkeypatch.setattr(app_server.urllib.request, "urlopen", fake_urlopen)
    status, headers, body = app_server.proxy_mcp(
        b'{"jsonrpc":"2.0"}', bearer="tok-abc", mcp_session_id="s-1"
    )
    assert status == 200
    assert seen["auth"] == "Bearer tok-abc"
    assert seen["session"] == "s-1"
    assert headers["mcp-session-id"] == "s-77"
    assert body == b'{"ok":1}'


def test_proxy_mcp_no_bearer_omits_auth_header(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None, context=None):
        seen["auth"] = req.get_header("Authorization")
        return _FakeResp(200, {"content-type": "application/json"}, b"{}")

    monkeypatch.setattr(app_server.urllib.request, "urlopen", fake_urlopen)
    app_server.proxy_mcp(b"{}", bearer=None, mcp_session_id=None)
    assert seen["auth"] is None


def test_proxy_mcp_surfaces_upstream_401(monkeypatch):
    import io
    import urllib.error

    def fake_urlopen(req, timeout=None, context=None):
        raise urllib.error.HTTPError(
            app_server.MCP_URL, 401, "Unauthorized",
            {"www-authenticate": 'Bearer resource_metadata="x"'},
            io.BytesIO(b'{"error":"authentication_required"}'),
        )

    monkeypatch.setattr(app_server.urllib.request, "urlopen", fake_urlopen)
    status, headers, body = app_server.proxy_mcp(b"{}", bearer=None, mcp_session_id=None)
    assert status == 401
    assert "www-authenticate" in headers


def test_proxy_mcp_unreachable_returns_502(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=None, context=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(app_server.urllib.request, "urlopen", fake_urlopen)
    status, _headers, body = app_server.proxy_mcp(b"{}", bearer=None, mcp_session_id=None)
    assert status == 502
    assert b"mcp_unreachable" in body
