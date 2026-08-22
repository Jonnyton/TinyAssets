"""Silent session renewal for the onboarding app.

AuthKit access tokens live ~5 minutes (live phone test 2026-08-22: the app
signed the founder out mid-conversation with no message). The token proxy now
keeps the refresh token in an HttpOnly cookie scoped to itself and renews on a
``grant_type=refresh_token`` request; the page never sees the refresh token.
"""

from __future__ import annotations

import asyncio
import json

import httpx

from tinyassets import onboarding


def _drive(
    body: dict,
    *,
    cookie: str = "",
    origin: str = "https://tinyassets.io",
    content_type: str = "application/json",
    monkeypatch,
    upstream,
):
    """Drive the token route with a scripted AuthKit token endpoint."""
    from starlette.requests import Request

    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setattr(
        onboarding,
        "app_config",
        lambda: {
            "issuer": "https://authkit.example",
            "authorization_endpoint": "https://authkit.example/oauth2/authorize",
            "token_endpoint": "https://authkit.example/oauth2/token",
            "resource": "https://tinyassets.io/mcp",
            "client_id": "client_x",
            "scopes": "openid",
            "configured": True,
            "openai": {},
        },
    )
    calls: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        form = dict(p.split("=", 1) for p in req.content.decode().split("&"))
        calls.append(form)
        return upstream(form)

    real_client = httpx.AsyncClient

    class _Client(real_client):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    route = next(r for r in onboarding.onboarding_routes() if r.path == "/mcp/app/token")
    raw = json.dumps(body).encode()
    headers = [
        (b"content-type", content_type.encode()),
        (b"content-length", str(len(raw)).encode()),
        (b"host", b"tinyassets.io"),
    ]
    if origin:
        headers.append((b"origin", origin.encode()))
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/app/token",
        "headers": headers,
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    resp = asyncio.run(route.endpoint(Request(scope, receive)))
    set_cookie = [v.decode() for k, v in resp.raw_headers if k == b"set-cookie"]
    return resp.status_code, json.loads(resp.body), set_cookie, calls


def test_exchange_sets_httponly_refresh_cookie_and_never_echoes_it(monkeypatch):
    def upstream(form):
        assert form["grant_type"] == "authorization_code"
        return httpx.Response(
            200, json={"access_token": "acc1", "refresh_token": "REFRESH-SECRET", "expires_in": 300}
        )

    status, doc, cookies, _ = _drive(
        {"code": "c", "code_verifier": "v", "redirect_uri": "https://tinyassets.io/mcp/app"},
        monkeypatch=monkeypatch,
        upstream=upstream,
    )
    assert status == 200 and doc == {"access_token": "acc1", "expires_in": 300}
    assert "REFRESH-SECRET" not in json.dumps(doc)
    assert len(cookies) == 1
    c = cookies[0]
    assert c.startswith("ta_rt=REFRESH-SECRET;")
    assert "HttpOnly" in c and "Secure" in c and "SameSite=strict" in c.replace("Strict", "strict")
    assert "Path=/mcp/app/token" in c


def test_refresh_uses_cookie_only_and_rotates_it(monkeypatch):
    def upstream(form):
        assert form["grant_type"] == "refresh_token"
        assert form["refresh_token"] == "OLD"
        assert "code" not in form
        return httpx.Response(
            200, json={"access_token": "acc2", "refresh_token": "NEW", "expires_in": 300}
        )

    status, doc, cookies, calls = _drive(
        {"grant_type": "refresh_token", "refresh_token": "BODY-IS-IGNORED"},
        cookie="ta_rt=OLD",
        monkeypatch=monkeypatch,
        upstream=upstream,
    )
    assert status == 200 and doc["access_token"] == "acc2"
    assert calls[0]["refresh_token"] == "OLD"  # the body value is never used
    assert cookies and cookies[0].startswith("ta_rt=NEW;")


def test_refresh_without_cookie_is_401_and_hits_no_upstream(monkeypatch):
    def upstream(form):
        raise AssertionError("must not call AuthKit")

    status, doc, _, calls = _drive(
        {"grant_type": "refresh_token"}, monkeypatch=monkeypatch, upstream=upstream
    )
    assert (status, doc, calls) == (401, {"error": "no_refresh_token"}, [])


def test_failed_refresh_maps_error_and_keeps_cookie(monkeypatch):
    def upstream(form):
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"})

    status, doc, cookies, _ = _drive(
        {"grant_type": "refresh_token"},
        cookie="ta_rt=DEAD",
        monkeypatch=monkeypatch,
        upstream=upstream,
    )
    assert status == 401 and doc == {"error": "refresh_failed"}
    # the cookie is NOT cleared on failure (a lost rotation race must not
    # delete the winner's token); logout is the explicit clear.
    assert cookies == []


def test_unknown_grant_is_rejected(monkeypatch):
    status, doc, _, _ = _drive(
        {"grant_type": "password"}, monkeypatch=monkeypatch, upstream=lambda f: httpx.Response(500)
    )
    assert (status, doc) == (400, {"error": "unsupported_grant_type"})


def test_cross_origin_or_non_json_is_refused_before_any_grant(monkeypatch):
    """Codex: login-CSRF / session fixation — a cross-site POST (or a form
    post) must never reach AuthKit nor set the refresh cookie."""

    def upstream(form):
        raise AssertionError("must not call AuthKit")

    body = {"code": "c", "code_verifier": "v", "redirect_uri": "https://tinyassets.io/mcp/app"}
    for origin, ctype in (
        ("https://evil.example", "application/json"),
        ("", "application/json"),
        ("https://tinyassets.io", "text/plain"),
        ("https://tinyassets.io", "application/x-www-form-urlencoded"),
        ("http://tinyassets.io.evil.example", "application/json"),
    ):
        status, doc, cookies, calls = _drive(
            body, origin=origin, content_type=ctype, monkeypatch=monkeypatch, upstream=upstream
        )
        assert (status, doc, cookies, calls) == (403, {"error": "cross_origin_rejected"}, [], [])


def test_logout_clears_the_cookie_without_upstream(monkeypatch):
    def upstream(form):
        raise AssertionError("must not call AuthKit")

    status, doc, cookies, calls = _drive(
        {"grant_type": "logout"}, cookie="ta_rt=LIVE", monkeypatch=monkeypatch, upstream=upstream
    )
    assert (status, doc, calls) == (200, {"ok": True}, [])
    assert cookies and cookies[0].startswith('ta_rt=""') and "Max-Age=0" in cookies[0]
    assert "Path=/mcp/app/token" in cookies[0]


def test_exchange_failure_maps_to_stable_code(monkeypatch):
    def upstream(form):
        return httpx.Response(
            400, json={"error": "invalid_grant", "error_description": "SECRET detail"}
        )

    status, doc, _, _ = _drive(
        {"code": "c", "code_verifier": "v", "redirect_uri": "https://tinyassets.io/mcp/app"},
        monkeypatch=monkeypatch,
        upstream=upstream,
    )
    assert (status, doc) == (400, {"error": "exchange_failed"})
