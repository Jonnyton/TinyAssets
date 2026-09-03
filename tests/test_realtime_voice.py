"""Deterministic policy and route tests for the Realtime voice broker."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from tinyassets.onboarding import realtime_voice as rv


@pytest.fixture(autouse=True)
def _clear_mint_limits():
    rv._mint_buckets.clear()
    yield
    rv._mint_buckets.clear()


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("TINYASSETS_REALTIME_VOICE_ENABLED", "1")
    monkeypatch.setenv("TINYASSETS_ALLOW_REALTIME_VOICE_API", "1")


def _client_with(handler):
    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)

    return factory


def _owner(sub: str = "user_owner"):
    from tinyassets.auth.provider import Identity

    return Identity(
        user_id=sub,
        username=sub,
        display_name=sub,
        capabilities=["write"],
        metadata={},
    )


def _drive(
    body: dict,
    *,
    identity=None,
    origin: str = "https://tinyassets.test",
) -> tuple[int, dict, dict]:
    from starlette.requests import Request

    from tinyassets.auth.middleware import identity_context
    from tinyassets.onboarding import onboarding_routes

    route = next(r for r in onboarding_routes() if r.path == "/mcp/app/voice/session")
    raw = json.dumps(body).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(raw)).encode()),
        (b"host", b"tinyassets.test"),
    ]
    if origin:
        headers.append((b"origin", origin.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/app/voice/session",
        "headers": headers,
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def run():
        request = Request(scope, receive)
        if identity is None:
            return await route.endpoint(request)
        with identity_context(identity):
            return await route.endpoint(request)

    response = asyncio.run(run())
    return response.status_code, json.loads(response.body or b"{}"), dict(response.headers)


def _drive_status(*, identity=None) -> tuple[int, dict, dict]:
    from starlette.requests import Request

    from tinyassets.auth.middleware import identity_context
    from tinyassets.onboarding import onboarding_routes

    route = next(r for r in onboarding_routes() if r.path == "/mcp/app/voice/status")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/mcp/app/voice/status",
            "headers": [(b"host", b"tinyassets.test")],
            "query_string": b"",
        }
    )

    async def run():
        if identity is None:
            return await route.endpoint(request)
        with identity_context(identity):
            return await route.endpoint(request)

    response = asyncio.run(run())
    return response.status_code, json.loads(response.body or b"{}"), dict(response.headers)


def test_voice_requires_both_independent_flags(monkeypatch):
    for app_flag, api_flag, expected in (
        ("", "", False),
        ("1", "", False),
        ("", "1", False),
        ("yes", "true", True),
    ):
        monkeypatch.setenv("TINYASSETS_REALTIME_VOICE_ENABLED", app_flag)
        monkeypatch.setenv("TINYASSETS_ALLOW_REALTIME_VOICE_API", api_flag)
        assert rv.realtime_voice_enabled() is expected


def test_client_secret_mint_limit_is_per_identity_and_resets():
    for _ in range(rv.VOICE_MINTS_PER_WINDOW):
        assert rv.allow_client_secret_mint("owner-a", now=10.0) is True
    assert rv.allow_client_secret_mint("owner-a", now=10.0) is False
    assert rv.allow_client_secret_mint("owner-b", now=10.0) is True
    assert rv.allow_client_secret_mint(
        "owner-a", now=10.0 + rv.VOICE_MINT_WINDOW_SECONDS
    ) is True


def test_public_config_contains_no_secret(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-must-not-render")
    config = rv.public_voice_config()
    assert config == {
        "enabled": True,
        "model": "gpt-realtime-2.1",
        "calls_url": "https://api.openai.com/v1/realtime/calls",
        "disclosure_version": 2,
        "max_session_seconds": 1800,
    }
    assert "sk-ambient" not in json.dumps(config)


def test_session_policy_requires_only_the_converse_tool():
    session = rv.session_request()["session"]
    assert session["model"] == "gpt-realtime-2.1"
    assert session["tool_choice"] == "required"
    assert [tool["name"] for tool in session["tools"]] == ["converse"]
    turn = session["audio"]["input"]["turn_detection"]
    assert turn == {
        "type": "semantic_vad",
        "eagerness": "medium",
        "create_response": True,
        "interrupt_response": True,
    }


def test_capability_is_locked_without_a_user_bound_compatible_resource(
    monkeypatch, tmp_path: Path
):
    _enable(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-forbidden")
    import tinyassets.credential_vault as vault

    monkeypatch.setattr(vault, "resolve_llm_api_key", lambda *_: "")
    assert rv.voice_capability(tmp_path) == {
        "available": False,
        "state": "locked",
        "reason": "voice_compatible_resource_required",
    }


def test_capability_is_ready_only_for_bound_resource(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    import tinyassets.credential_vault as vault

    monkeypatch.setattr(vault, "resolve_llm_api_key", lambda *_: "sk-user-bound")
    assert rv.voice_capability(tmp_path) == {
        "available": True,
        "state": "ready",
        "resource": "user_bound_openai_api_credential",
    }


def test_missing_owner_key_never_uses_ambient_or_network(monkeypatch, tmp_path: Path):
    _enable(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-forbidden")
    seen = {}

    def resolve(universe_dir, env_var):
        seen.update(path=Path(universe_dir), env_var=env_var)
        return ""

    import tinyassets.credential_vault as vault

    monkeypatch.setattr(vault, "resolve_llm_api_key", resolve)

    def forbidden_client():
        raise AssertionError("network must not be reached")

    with pytest.raises(rv.RealtimeVoiceError) as caught:
        asyncio.run(
            rv.mint_client_secret(
                tmp_path, client_factory=forbidden_client
            )
        )
    assert (caught.value.code, caught.value.status) == (
        "voice_compatible_resource_required",
        409,
    )
    assert seen == {"path": tmp_path, "env_var": "OPENAI_API_KEY"}
    assert "sk-ambient-forbidden" not in repr(caught.value)


def test_mint_posts_server_owned_policy_and_returns_only_ephemeral_fields(
    monkeypatch, tmp_path: Path
):
    _enable(monkeypatch)
    owner_key = "sk-owner-secret"
    ephemeral = "ek_test_ephemeral_value_123456789"
    import tinyassets.credential_vault as vault

    monkeypatch.setattr(vault, "resolve_llm_api_key", lambda *_: owner_key)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "value": ephemeral,
                "expires_at": 1234567890,
                "id": "must-not-cross-boundary",
            },
        )

    result = asyncio.run(
        rv.mint_client_secret(
            tmp_path,
            client_factory=_client_with(handler),
        )
    )
    assert seen["url"] == rv.REALTIME_CLIENT_SECRETS_URL
    assert seen["authorization"] == f"Bearer {owner_key}"
    assert "openai-safety-identifier" not in seen["headers"]
    assert seen["body"] == rv.session_request()
    assert result == {
        "value": ephemeral,
        "expires_at": 1234567890,
        "model": rv.REALTIME_MODEL,
        "calls_url": rv.REALTIME_CALLS_URL,
        "max_session_seconds": 1800,
    }
    assert owner_key not in json.dumps(result)
    assert "must-not-cross-boundary" not in json.dumps(result)


@pytest.mark.parametrize(
    ("upstream", "code", "status"),
    [
        (401, "voice_openai_credential_rejected", 409),
        (403, "voice_openai_credential_rejected", 409),
        (429, "voice_provider_rate_limited", 503),
        (500, "voice_provider_failed", 502),
    ],
)
def test_upstream_statuses_become_stable_secret_free_errors(
    monkeypatch, tmp_path: Path, upstream: int, code: str, status: int
):
    _enable(monkeypatch)
    import tinyassets.credential_vault as vault

    monkeypatch.setattr(vault, "resolve_llm_api_key", lambda *_: "sk-never-echo")

    def handler(_request):
        return httpx.Response(upstream, json={"error": "sk-upstream-secret"})

    with pytest.raises(rv.RealtimeVoiceError) as caught:
        asyncio.run(
            rv.mint_client_secret(
                tmp_path,
                client_factory=_client_with(handler),
            )
        )
    assert (caught.value.code, caught.value.status) == (code, status)
    assert "secret" not in repr(caught.value)


def test_route_is_disabled_before_home_or_network(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.delenv("TINYASSETS_REALTIME_VOICE_ENABLED", raising=False)
    monkeypatch.delenv("TINYASSETS_ALLOW_REALTIME_VOICE_API", raising=False)
    status, body, headers = _drive({}, identity=_owner())
    assert (status, body) == (404, {"error": "voice_disabled"})
    assert headers["cache-control"] == "no-store"


def test_route_requires_identity_and_same_origin(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    _enable(monkeypatch)
    assert _drive({})[:2] == (401, {"error": "authentication_required"})
    assert _drive({}, identity=_owner(), origin="https://evil.example")[:2] == (
        403,
        {"error": "same_origin_required"},
    )


def test_route_rejects_caller_selected_universe_before_mint(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    _enable(monkeypatch)
    status, body, _headers = _drive(
        {"universe_id": "u-someone-else"}, identity=_owner()
    )
    assert (status, body) == (
        400,
        {"error": "voice_session_fields_not_allowed"},
    )


def test_route_scopes_distinct_identities_to_distinct_home_universes(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(
        onboarding, "_read_home", lambda identity: f"u-{identity.user_id}"
    )
    seen = []

    async def mint(path):
        seen.append(path)
        return {
            "value": f"ek_{path.name}_ephemeral_value_12345",
            "expires_at": 123,
            "model": rv.REALTIME_MODEL,
            "calls_url": rv.REALTIME_CALLS_URL,
            "max_session_seconds": 1800,
        }

    monkeypatch.setattr(rv, "mint_client_secret", mint)
    assert _drive({}, identity=_owner("owner-a"))[0] == 200
    assert _drive({}, identity=_owner("owner-b"))[0] == 200
    assert seen == [
        (tmp_path / "u-owner-a").resolve(),
        (tmp_path / "u-owner-b").resolve(),
    ]


def test_route_rate_limits_before_home_or_provider_access(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(rv, "allow_client_secret_mint", lambda _user_id: False)
    monkeypatch.setattr(
        onboarding,
        "_read_home",
        lambda _identity: (_ for _ in ()).throw(AssertionError("home must not resolve")),
    )
    assert _drive({}, identity=_owner())[:2] == (
        429,
        {"error": "voice_session_rate_limited"},
    )


def test_route_resolves_home_and_returns_no_store(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda identity: "u-owner-home")
    seen = {}

    async def mint(path):
        seen.update(path=path)
        return {
            "value": "ek_route_ephemeral_value_12345",
            "expires_at": 123,
            "model": rv.REALTIME_MODEL,
            "calls_url": rv.REALTIME_CALLS_URL,
            "max_session_seconds": 1800,
        }

    monkeypatch.setattr(rv, "mint_client_secret", mint)
    status, body, headers = _drive({}, identity=_owner("user_exact"))
    assert status == 200
    assert body["value"].startswith("ek_route_")
    assert seen == {"path": (tmp_path / "u-owner-home").resolve()}
    assert headers["cache-control"] == "no-store"


def test_route_missing_home_is_actionable(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda identity: "")
    assert _drive({}, identity=_owner())[:2] == (
        409,
        {"error": "no_home_universe"},
    )


def test_status_route_is_authenticated_secret_free_and_locked(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _enable(monkeypatch)
    import tinyassets.credential_vault as vault
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda _identity: "u-owner-home")
    monkeypatch.setattr(vault, "resolve_llm_api_key", lambda *_: "")
    assert _drive_status()[:2] == (401, {"error": "authentication_required"})
    status, body, headers = _drive_status(identity=_owner())
    assert status == 200
    assert body == {
        "available": False,
        "state": "locked",
        "reason": "voice_compatible_resource_required",
    }
    assert headers["cache-control"] == "no-store"
    assert "credential" not in json.dumps(body)


def test_status_route_reports_ready_without_returning_bound_secret(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _enable(monkeypatch)
    import tinyassets.credential_vault as vault
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda _identity: "u-owner-home")
    monkeypatch.setattr(vault, "resolve_llm_api_key", lambda *_: "sk-bound-secret")
    status, body, _headers = _drive_status(identity=_owner())
    assert status == 200
    assert body == {
        "available": True,
        "state": "ready",
        "resource": "user_bound_openai_api_credential",
    }
    assert "sk-bound-secret" not in json.dumps(body)
