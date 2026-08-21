"""One-tap OpenAI linking: the device-authorization broker + its routes.

Network is replaced with an httpx MockTransport scripted to the exact shapes the
Codex CLI source documents (codex-rs/login/src/device_code_auth.rs + server.rs).
The deposit path is exercised through the REAL ``connect_llm`` handler so the
identity/ACL gates are the ones production runs.
"""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from tinyassets.onboarding import openai_device as od


def _client_with(handler):
    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)

    return factory


def _fake_jwt(claims: dict) -> str:
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{b({'alg': 'none'})}.{b(claims)}.sig"


# ---------------------------------------------------------------- start ----


def test_start_posts_codex_client_id_and_returns_public_fields_only():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(
            200, json={"device_auth_id": "dev-1", "user_code": "ABCD-EFGH", "interval": 3}
        )

    out = asyncio.run(od.start_device_auth(_client_with(handler)))
    assert seen["url"] == "https://auth.openai.com/api/accounts/deviceauth/usercode"
    assert seen["body"] == {"client_id": od.CODEX_CLIENT_ID}
    assert out == {
        "device_auth_id": "dev-1",
        "user_code": "ABCD-EFGH",
        "verification_url": "https://auth.openai.com/codex/device",
        "interval": 3,
    }


def test_start_404_means_device_login_unavailable():
    def handler(req):
        return httpx.Response(404)

    with pytest.raises(od.DeviceAuthError) as ei:
        asyncio.run(od.start_device_auth(_client_with(handler)))
    assert ei.value.code == "device_login_unavailable"
    assert ei.value.status == 503


def test_start_unreachable_is_secret_free_error():
    def handler(req):
        raise httpx.ConnectError("boom")

    with pytest.raises(od.DeviceAuthError) as ei:
        asyncio.run(od.start_device_auth(_client_with(handler)))
    assert ei.value.code == "openai_unreachable"


def test_start_rejects_oversized_or_missing_fields():
    def handler(req):
        return httpx.Response(200, json={"device_auth_id": "x" * 1000, "user_code": "A"})

    with pytest.raises(od.DeviceAuthError) as ei:
        asyncio.run(od.start_device_auth(_client_with(handler)))
    assert ei.value.code == "device_response_invalid"


# ----------------------------------------------------------------- poll ----


def test_poll_pending_on_403_and_404():
    for status in (403, 404):

        def handler(req, status=status):
            return httpx.Response(status)

        assert (
            asyncio.run(
                od.poll_device_auth(
                    device_auth_id="d", user_code="c", client_factory=_client_with(handler)
                )
            )
            is None
        )


def test_poll_success_exchanges_with_pkce_and_builds_codex_auth_json():
    calls = []
    id_token = _fake_jwt({"chatgpt_account_id": "acct_42", "email": "u@example.com"})

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.path == "/api/accounts/deviceauth/token":
            assert json.loads(req.content) == {"device_auth_id": "d", "user_code": "c"}
            return httpx.Response(
                200,
                json={
                    "authorization_code": "authcode",
                    "code_challenge": "chal",
                    "code_verifier": "verif",
                },
            )
        if req.url.path == "/oauth/token":
            form = dict(p.split("=", 1) for p in req.content.decode().split("&"))
            assert form["grant_type"] == "authorization_code"
            assert form["code"] == "authcode"
            assert form["code_verifier"] == "verif"
            assert form["client_id"] == od.CODEX_CLIENT_ID
            assert form["redirect_uri"] == "https%3A%2F%2Fauth.openai.com%2Fdeviceauth%2Fcallback"
            return httpx.Response(
                200, json={"id_token": id_token, "access_token": "acc", "refresh_token": "ref"}
            )
        raise AssertionError(f"unexpected call {req.url}")

    out = asyncio.run(
        od.poll_device_auth(device_auth_id="d", user_code="c", client_factory=_client_with(handler))
    )
    assert out is not None and set(out) == {"auth_json"}
    doc = json.loads(out["auth_json"])
    # The exact $CODEX_HOME/auth.json the Codex CLI writes after a ChatGPT login.
    assert doc["auth_mode"] == "chatgpt"
    assert doc["OPENAI_API_KEY"] is None
    assert doc["tokens"] == {
        "id_token": id_token,
        "access_token": "acc",
        "refresh_token": "ref",
        "account_id": "acct_42",
    }
    assert doc["last_refresh"].endswith("Z")
    assert [c.url.path for c in calls] == ["/api/accounts/deviceauth/token", "/oauth/token"]


def test_poll_exchange_failure_never_returns_partial_tokens():
    def handler(req):
        if req.url.path.endswith("/deviceauth/token"):
            return httpx.Response(
                200, json={"authorization_code": "a", "code_challenge": "c", "code_verifier": "v"}
            )
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(od.DeviceAuthError) as ei:
        asyncio.run(
            od.poll_device_auth(
                device_auth_id="d", user_code="c", client_factory=_client_with(handler)
            )
        )
    assert ei.value.code == "token_exchange_failed"


def test_poll_requires_fields():
    with pytest.raises(od.DeviceAuthError) as ei:
        asyncio.run(od.poll_device_auth(device_auth_id="", user_code="c"))
    assert ei.value.status == 400


def test_build_auth_json_tolerates_malformed_id_token():
    doc = json.loads(
        od.build_codex_auth_json(id_token="not-a-jwt", access_token="a", refresh_token="r")
    )
    assert "account_id" not in doc["tokens"]


# --------------------------------------------------------------- routes ----


def _drive(route_path: str, body: dict | None, *, identity=None, enabled=True, monkeypatch=None):
    """Drive a route handler directly with an optional pinned identity."""
    from starlette.requests import Request

    from tinyassets.auth.middleware import identity_context
    from tinyassets.onboarding import onboarding_routes

    if monkeypatch is not None:
        monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1" if enabled else "")
    route = next(r for r in onboarding_routes() if r.path == route_path)
    raw = json.dumps(body or {}).encode()
    scope = {
        "type": "http",
        "method": "POST",
        "path": route_path,
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def run():
        req = Request(scope, receive)
        if identity is not None:
            with identity_context(identity):
                return await route.endpoint(req)
        return await route.endpoint(req)

    resp = asyncio.run(run())
    return resp.status_code, json.loads(resp.body or b"{}") if resp.body.strip().startswith(
        b"{"
    ) else resp.body


def _user(sub="user_123"):
    from tinyassets.auth.provider import Identity

    return Identity(
        user_id=sub, username=sub, display_name=sub, capabilities=["write"], metadata={}
    )


def test_routes_404_when_app_dark(monkeypatch):
    assert (
        _drive("/mcp/app/openai/device/start", {}, enabled=False, monkeypatch=monkeypatch)[0] == 404
    )
    assert (
        _drive("/mcp/app/openai/device/poll", {}, enabled=False, monkeypatch=monkeypatch)[0] == 404
    )


def test_routes_401_without_identity(monkeypatch):
    # Anonymous callers cannot start or poll a link — there is nobody to deposit for.
    assert _drive("/mcp/app/openai/device/start", {}, monkeypatch=monkeypatch)[0] == 401
    assert (
        _drive(
            "/mcp/app/openai/device/poll",
            {"device_auth_id": "d", "user_code": "c"},
            monkeypatch=monkeypatch,
        )[0]
        == 401
    )


def test_start_route_returns_code_for_signed_in_user(monkeypatch):
    async def fake_start():
        return {
            "device_auth_id": "d",
            "user_code": "AB-CD",
            "verification_url": od.VERIFICATION_URL,
            "interval": 5,
        }

    monkeypatch.setattr(od, "start_device_auth", fake_start)
    status, doc = _drive(
        "/mcp/app/openai/device/start", {}, identity=_user(), monkeypatch=monkeypatch
    )
    assert status == 200 and doc["user_code"] == "AB-CD"


def test_poll_route_pending_passthrough(monkeypatch):
    async def fake_poll(**kw):
        return None

    monkeypatch.setattr(od, "poll_device_auth", fake_poll)
    status, doc = _drive(
        "/mcp/app/openai/device/poll",
        {"device_auth_id": "d", "user_code": "c"},
        identity=_user(),
        monkeypatch=monkeypatch,
    )
    assert (status, doc) == (200, {"status": "pending"})


def test_poll_route_deposits_as_user_and_never_echoes_credential(monkeypatch):
    """On approval the route deposits through the REAL connect_llm under the
    request identity; the response carries a status only. A user with no admin
    ACL on the target universe is refused by connect_llm's own gate — proving
    the gate runs — and the token text appears nowhere in the response."""
    secret = "refresh-SECRET-xyz"

    async def fake_poll(**kw):
        return {
            "auth_json": od.build_codex_auth_json(
                id_token="t", access_token="a", refresh_token=secret
            )
        }

    monkeypatch.setattr(od, "poll_device_auth", fake_poll)
    captured = {}

    def fake_connect_llm(*, universe_id="", payload=None):
        from tinyassets.auth.middleware import current_identity

        captured["actor"] = current_identity().user_id
        captured["service"] = payload["service"]
        captured["material"] = base64.b64decode(payload["auth_material_b64"]).decode()
        return {"ok": True, "service": "codex"}

    import tinyassets.api.llm_deposit as ld

    monkeypatch.setattr(ld, "connect_llm", fake_connect_llm)
    status, doc = _drive(
        "/mcp/app/openai/device/poll",
        {"device_auth_id": "d", "user_code": "c"},
        identity=_user("user_777"),
        monkeypatch=monkeypatch,
    )
    assert (status, doc) == (200, {"status": "connected", "service": "codex"})
    assert captured["actor"] == "user_777" and captured["service"] == "codex"
    assert json.loads(captured["material"])["tokens"]["refresh_token"] == secret
    assert secret not in json.dumps(doc)


def test_poll_route_surfaces_connect_llm_refusal(monkeypatch):
    async def fake_poll(**kw):
        return {
            "auth_json": od.build_codex_auth_json(id_token="t", access_token="a", refresh_token="r")
        }

    monkeypatch.setattr(od, "poll_device_auth", fake_poll)
    import tinyassets.api.llm_deposit as ld

    monkeypatch.setattr(
        ld, "connect_llm", lambda **kw: {"error": "not_found", "resource": "connection"}
    )
    status, doc = _drive(
        "/mcp/app/openai/device/poll",
        {"device_auth_id": "d", "user_code": "c"},
        identity=_user(),
        monkeypatch=monkeypatch,
    )
    assert status == 400 and doc == {"status": "failed", "error": "not_found"}


def test_poll_route_maps_device_errors(monkeypatch):
    async def fake_poll(**kw):
        raise od.DeviceAuthError("openai_unreachable")

    monkeypatch.setattr(od, "poll_device_auth", fake_poll)
    status, doc = _drive(
        "/mcp/app/openai/device/poll",
        {"device_auth_id": "d", "user_code": "c"},
        identity=_user(),
        monkeypatch=monkeypatch,
    )
    assert (status, doc) == (502, {"error": "openai_unreachable"})
