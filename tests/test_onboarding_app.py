"""Tests for the daemon-served onboarding app (tinyassets/onboarding).

Unit-level: exercises the dark flag, the route handler, config injection, the
per-request CSP nonce, and secret-safety. Final onboarding acceptance is a real
user against the DEPLOYED cloud daemon (tinyassets.io) — never a local run.
"""

from __future__ import annotations

import asyncio

import pytest

from tinyassets import onboarding


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TINYASSETS_ONBOARDING_APP", raising=False)
    monkeypatch.delenv("TINYASSETS_ONBOARDING_APP_CLIENT_ID", raising=False)
    yield


def _fake_prm(resource="https://tinyassets.io/mcp",
              issuer="https://inventive-van-62-staging.authkit.app"):
    return {
        "resource": resource,
        "authorization_servers": [issuer] if issuer else [],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
    }


def _render(monkeypatch, *, enabled=True, client_id="client_ABC", prm=None):
    if enabled:
        monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    if client_id is not None:
        monkeypatch.setenv("TINYASSETS_ONBOARDING_APP_CLIENT_ID", client_id)
    monkeypatch.setattr(
        "tinyassets.auth.wellknown.protected_resource_metadata",
        lambda: prm or _fake_prm(),
    )


# --------------------------------------------------------------------------- #
# dark flag
# --------------------------------------------------------------------------- #


def test_disabled_by_default():
    assert onboarding.onboarding_enabled() is False


@pytest.mark.parametrize("val,expected", [("1", True), ("true", True), ("on", True),
                                          ("0", False), ("", False), ("no", False)])
def test_flag_parsing(monkeypatch, val, expected):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", val)
    assert onboarding.onboarding_enabled() is expected


def test_handler_404_when_flag_off(monkeypatch):
    monkeypatch.setattr(
        "tinyassets.auth.wellknown.protected_resource_metadata", lambda: _fake_prm()
    )
    resp = asyncio.run(onboarding._handle_app(object()))
    assert resp.status_code == 404


def test_handler_200_html_when_enabled(monkeypatch):
    _render(monkeypatch)
    resp = asyncio.run(onboarding._handle_app(object()))
    assert resp.status_code == 200
    assert resp.media_type == "text/html"
    body = resp.body.decode("utf-8")
    assert "window.__TA_ONBOARDING__" in body
    assert "__TA_ONBOARDING_CONFIG__" not in body  # placeholder was substituted
    assert "__TA_NONCE__" not in body


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #


def test_config_configured_when_issuer_and_client_present(monkeypatch):
    _render(monkeypatch)
    cfg = onboarding.app_config()
    assert cfg["configured"] is True
    assert cfg["client_id"] == "client_ABC"
    assert cfg["authorization_endpoint"].endswith("/oauth2/authorize")
    assert cfg["token_endpoint"].endswith("/oauth2/token")
    assert cfg["resource"] == "https://tinyassets.io/mcp"
    assert "offline_access" in cfg["scopes"]


def test_config_not_configured_without_client_id(monkeypatch):
    _render(monkeypatch, client_id=None)
    cfg = onboarding.app_config()
    assert cfg["configured"] is False
    assert cfg["client_id"] == ""


def test_config_not_configured_without_issuer(monkeypatch):
    _render(monkeypatch, prm=_fake_prm(issuer=""))
    cfg = onboarding.app_config()
    assert cfg["configured"] is False
    assert cfg["authorization_endpoint"] == ""


# --------------------------------------------------------------------------- #
# CSP + nonce + injection safety
# --------------------------------------------------------------------------- #


def test_csp_nonce_is_per_request_and_matches_body(monkeypatch):
    _render(monkeypatch)
    html1, csp1 = onboarding.render_app_html()
    html2, csp2 = onboarding.render_app_html()
    assert csp1 != csp2  # fresh nonce each render
    nonce1 = csp1.split("'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce1}"' in html1        # the inline script/style carry it
    assert f"'nonce-{nonce1}'" in csp1
    # CSP locks the network surface down to self + the AuthKit origin.
    assert "connect-src 'self' https://inventive-van-62-staging.authkit.app" in csp1
    assert "default-src 'none'" in csp1
    assert "frame-ancestors 'none'" in csp1


def test_config_injection_escapes_angle_brackets(monkeypatch):
    # A client id containing </script> must not break out of the script context.
    _render(monkeypatch, client_id="</script><script>alert(1)</script>")
    html, _ = onboarding.render_app_html()
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script>" in html


def test_no_secret_leaks_into_page(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_secret_should_never_render")
    monkeypatch.setenv("WORKOS_CLIENT_SECRET", "cs_secret_should_never_render")
    _render(monkeypatch)
    html, _ = onboarding.render_app_html()
    assert "sk_secret_should_never_render" not in html
    assert "cs_secret_should_never_render" not in html


def test_response_sets_security_headers(monkeypatch):
    _render(monkeypatch)
    resp = asyncio.run(onboarding._handle_app(object()))
    assert "Content-Security-Policy" in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Cache-Control"] == "no-store"


# --------------------------------------------------------------------------- #
# route
# --------------------------------------------------------------------------- #


def test_route_is_mcp_app_get(monkeypatch):
    routes = onboarding.onboarding_routes()
    by_path = {r.path: r for r in routes}
    # The SPA page (GET) + its same-origin PKCE token-exchange proxy (POST) +
    # the one-tap OpenAI device-auth broker (POST only, identity-gated).
    assert set(by_path) == {
        "/mcp/app", "/mcp/app/token",
        "/mcp/app/openai/device/start", "/mcp/app/openai/device/poll",
    }
    assert "GET" in by_path["/mcp/app"].methods
    for post_only in ("/mcp/app/token", "/mcp/app/openai/device/start", "/mcp/app/openai/device/poll"):
        assert "POST" in by_path[post_only].methods
        assert "GET" not in by_path[post_only].methods
