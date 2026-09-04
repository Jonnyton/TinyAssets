"""Deterministic policy and route tests for provider-neutral Realtime voice."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from tinyassets.onboarding import realtime_voice as rv

_CONNECTION_ID = "voice-connection"
_GRANT_ID = "voice-grant"
_SESSION_URL = "https://bridge.example/v1/session"
_OFFER_SDP = "v=0\r\no=browser 1 1 IN IP4 127.0.0.1\r\n"
_ANSWER_SDP = "v=0\r\no=bridge 1 1 IN IP4 203.0.113.10\r\n"


@pytest.fixture(autouse=True)
def _clear_session_limits():
    rv._session_buckets.clear()
    yield
    rv._session_buckets.clear()


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("TINYASSETS_REALTIME_VOICE_ENABLED", "1")
    monkeypatch.setenv("TINYASSETS_ALLOW_REALTIME_VOICE_API", "1")
    monkeypatch.setenv("TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED", "1")


def _owner(sub: str = "user_owner"):
    from tinyassets.auth.provider import Identity

    return Identity(
        user_id=sub,
        username=sub,
        display_name=sub,
        capabilities=["write"],
        metadata={},
    )


def _seed_binding(
    base: Path,
    *,
    owner: str = "user_owner",
    universe_id: str = "u-owner-home",
) -> Path:
    from tinyassets.storage.outbound_connections import ConnectionLedger

    universe = base / universe_id
    universe.mkdir(parents=True, exist_ok=True)
    ledger = ConnectionLedger(base / "outbound.db")
    ledger.create_connection(
        connection_id=_CONNECTION_ID,
        owner_user_id=owner,
        connection_class="http",
        scopes=("POST",),
        provider="user-defined",
        destination="bridge.example",
        credential_ref="vault://http/voice-bridge",
        connection_type="http",
        auth_scheme="bearer",
        allowed_endpoints=[
            {
                "host": "bridge.example",
                "path_template": "/v1/session",
                "methods": ["POST"],
            }
        ],
    )
    ledger.grant_connection(
        grant_id=_GRANT_ID,
        connection_id=_CONNECTION_ID,
        owner_user_id=owner,
        universe_id=universe_id,
    )
    (universe / rv.VOICE_BINDING_FILENAME).write_text(
        json.dumps(
            {
                "schema": rv.VOICE_PROTOCOL,
                "connection_id": _CONNECTION_ID,
                "grant_id": _GRANT_ID,
                "session_url": _SESSION_URL,
                "service_name": "Owner Voice Bridge",
                "privacy_url": "https://bridge.example/privacy",
            }
        ),
        encoding="utf-8",
    )
    return universe


class _FakeProxy:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def request(self, verb: str, request: dict[str, Any]) -> Any:
        self.calls.append((verb, request))
        return self.response

    def close(self) -> None:
        self.closed = True


def _proxy_factory(proxy: _FakeProxy):
    def factory(_universe: Path, _owner_id: str, _binding: rv.VoiceBinding):
        return proxy

    return factory


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
        with identity_context(identity):
            return await route.endpoint(request)

    response = asyncio.run(run())
    return response.status_code, json.loads(response.body or b"{}"), dict(response.headers)


def test_voice_requires_all_independent_flags(monkeypatch):
    for app_flag, api_flag, outbound_flag, expected in (
        ("", "", "", False),
        ("1", "", "1", False),
        ("", "1", "1", False),
        ("1", "1", "", False),
        ("yes", "true", "on", True),
    ):
        monkeypatch.setenv("TINYASSETS_REALTIME_VOICE_ENABLED", app_flag)
        monkeypatch.setenv("TINYASSETS_ALLOW_REALTIME_VOICE_API", api_flag)
        monkeypatch.setenv("TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED", outbound_flag)
        assert rv.realtime_voice_enabled() is expected


def test_session_limit_is_per_identity_and_resets():
    for _ in range(rv.VOICE_SESSIONS_PER_WINDOW):
        assert rv.allow_voice_session("owner-a", now=10.0) is True
    assert rv.allow_voice_session("owner-a", now=10.0) is False
    assert rv.allow_voice_session("owner-b", now=10.0) is True
    assert rv.allow_voice_session(
        "owner-a", now=10.0 + rv.VOICE_SESSION_WINDOW_SECONDS
    ) is True


def test_public_config_contains_only_protocol_and_limits(monkeypatch):
    _enable(monkeypatch)
    config = rv.public_voice_config()
    assert config == {
        "enabled": True,
        "protocol": rv.VOICE_PROTOCOL,
        "disclosure_version": 3,
        "max_session_seconds": 1800,
    }


def test_session_policy_requires_only_the_converse_tool():
    request = rv.session_request(_OFFER_SDP)
    assert request["protocol"] == rv.VOICE_PROTOCOL
    assert request["offer_sdp"] == _OFFER_SDP
    session = request["session"]
    assert session["tool"]["name"] == "converse"
    assert session["turn_detection"] == {
        "mode": "semantic",
        "eagerness": "medium",
        "interrupt_output": True,
    }
    assert session["output"] == {
        "mode": "audio",
        "source": "tool_result",
        "verbatim": True,
    }


def test_capability_is_locked_without_user_bound_connection(monkeypatch, tmp_path):
    _enable(monkeypatch)
    assert rv.voice_capability(tmp_path / "u-missing", "owner") == {
        "available": False,
        "state": "locked",
        "reason": "voice_compatible_resource_required",
    }


def test_capability_is_ready_only_for_exact_owner_and_universe(monkeypatch, tmp_path):
    _enable(monkeypatch)
    universe = _seed_binding(tmp_path)
    assert rv.voice_capability(universe, "user_owner") == {
        "available": True,
        "state": "ready",
        "resource": "user_bound_voice_connection",
        "service_name": "Owner Voice Bridge",
        "privacy_url": "https://bridge.example/privacy",
    }
    assert rv.voice_capability(universe, "someone-else")["available"] is False


def test_capability_refuses_session_url_outside_connection_policy(monkeypatch, tmp_path):
    _enable(monkeypatch)
    universe = _seed_binding(tmp_path)
    path = universe / rv.VOICE_BINDING_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["session_url"] = "https://bridge.example/not-allowed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert rv.voice_capability(universe, "user_owner") == {
        "available": False,
        "state": "locked",
        "reason": "voice_compatible_resource_required",
    }


def test_invalid_or_symlinked_binding_fails_closed(monkeypatch, tmp_path):
    _enable(monkeypatch)
    universe = tmp_path / "u-owner-home"
    universe.mkdir()
    binding = universe / rv.VOICE_BINDING_FILENAME
    binding.write_text("{broken", encoding="utf-8")
    assert rv.voice_capability(universe, "user_owner")["reason"] == "voice_binding_invalid"
    binding.unlink()
    target = tmp_path / "binding.json"
    target.write_text("{}", encoding="utf-8")
    try:
        binding.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    assert rv.voice_capability(universe, "user_owner")["available"] is False


def test_session_uses_generic_scoped_proxy_and_returns_only_answer_fields(
    monkeypatch, tmp_path
):
    _enable(monkeypatch)
    universe = _seed_binding(tmp_path)
    proxy = _FakeProxy(
        {
            "status": 200,
            "body": {
                "protocol": rv.VOICE_PROTOCOL,
                "answer_sdp": _ANSWER_SDP,
                "expires_at": 1234567890,
                "max_session_seconds": 9999,
                "internal": "must-not-cross-boundary",
            },
        }
    )
    result = asyncio.run(
        rv.create_voice_session(
            universe,
            "user_owner",
            _OFFER_SDP,
            proxy_factory=_proxy_factory(proxy),
        )
    )
    assert proxy.calls == [
        (
            "POST",
            {
                "url": _SESSION_URL,
                "headers": {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                "body": rv.session_request(_OFFER_SDP),
            },
        )
    ]
    assert proxy.closed is True
    assert result == {
        "protocol": rv.VOICE_PROTOCOL,
        "answer_sdp": _ANSWER_SDP,
        "expires_at": 1234567890,
        "max_session_seconds": 1800,
    }
    assert "must-not-cross-boundary" not in json.dumps(result)


def test_session_refuses_invalid_offer_before_opening_proxy(monkeypatch, tmp_path):
    _enable(monkeypatch)
    universe = _seed_binding(tmp_path)
    proxy = _FakeProxy({})
    with pytest.raises(rv.RealtimeVoiceError) as caught:
        asyncio.run(
            rv.create_voice_session(
                universe,
                "user_owner",
                "not-sdp",
                proxy_factory=_proxy_factory(proxy),
            )
        )
    assert (caught.value.code, caught.value.status) == (
        "voice_session_offer_invalid",
        400,
    )
    assert proxy.calls == []


@pytest.mark.parametrize(
    ("upstream", "code", "status"),
    [
        (401, "voice_resource_rejected", 409),
        (403, "voice_resource_rejected", 409),
        (429, "voice_resource_rate_limited", 503),
        (500, "voice_resource_failed", 502),
    ],
)
def test_upstream_statuses_become_stable_secret_free_errors(
    monkeypatch, tmp_path, upstream: int, code: str, status: int
):
    _enable(monkeypatch)
    universe = _seed_binding(tmp_path)
    proxy = _FakeProxy({"status": upstream, "body": {"error": "hidden-secret"}})
    with pytest.raises(rv.RealtimeVoiceError) as caught:
        asyncio.run(
            rv.create_voice_session(
                universe,
                "user_owner",
                _OFFER_SDP,
                proxy_factory=_proxy_factory(proxy),
            )
        )
    assert (caught.value.code, caught.value.status) == (code, status)
    assert "hidden-secret" not in repr(caught.value)


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


def test_route_rejects_caller_selected_universe_before_session(monkeypatch):
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
    monkeypatch, tmp_path
):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda identity: f"u-{identity.user_id}")
    seen = []

    async def create(path, owner_id, offer_sdp):
        seen.append((path, owner_id, offer_sdp))
        return {
            "answer_sdp": _ANSWER_SDP,
            "expires_at": 123,
            "protocol": rv.VOICE_PROTOCOL,
            "max_session_seconds": 1800,
        }

    monkeypatch.setattr(rv, "create_voice_session", create)
    assert _drive({"offer_sdp": _OFFER_SDP}, identity=_owner("owner-a"))[0] == 200
    assert _drive({"offer_sdp": _OFFER_SDP}, identity=_owner("owner-b"))[0] == 200
    assert seen == [
        ((tmp_path / "u-owner-a").resolve(), "owner-a", _OFFER_SDP),
        ((tmp_path / "u-owner-b").resolve(), "owner-b", _OFFER_SDP),
    ]


def test_route_rate_limits_before_home_or_resource_access(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(rv, "allow_voice_session", lambda _user_id: False)
    monkeypatch.setattr(
        onboarding,
        "_read_home",
        lambda _identity: (_ for _ in ()).throw(AssertionError("home must not resolve")),
    )
    assert _drive({"offer_sdp": _OFFER_SDP}, identity=_owner())[:2] == (
        429,
        {"error": "voice_session_rate_limited"},
    )


def test_route_resolves_home_owner_and_returns_no_store(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda _identity: "u-owner-home")
    seen = {}

    async def create(path, owner_id, offer_sdp):
        seen.update(path=path, owner_id=owner_id, offer_sdp=offer_sdp)
        return {
            "answer_sdp": _ANSWER_SDP,
            "expires_at": 123,
            "protocol": rv.VOICE_PROTOCOL,
            "max_session_seconds": 1800,
        }

    monkeypatch.setattr(rv, "create_voice_session", create)
    status, body, headers = _drive(
        {"offer_sdp": _OFFER_SDP}, identity=_owner("user_exact")
    )
    assert status == 200
    assert body["answer_sdp"] == _ANSWER_SDP
    assert seen == {
        "path": (tmp_path / "u-owner-home").resolve(),
        "owner_id": "user_exact",
        "offer_sdp": _OFFER_SDP,
    }
    assert headers["cache-control"] == "no-store"


def test_route_missing_home_is_actionable(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda _identity: "")
    assert _drive({"offer_sdp": _OFFER_SDP}, identity=_owner())[:2] == (
        409,
        {"error": "no_home_universe"},
    )


def test_status_route_is_authenticated_secret_free_and_locked(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _enable(monkeypatch)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda _identity: "u-owner-home")
    assert _drive_status()[:2] == (401, {"error": "authentication_required"})
    status, body, headers = _drive_status(identity=_owner())
    assert status == 200
    assert body == {
        "available": False,
        "state": "locked",
        "reason": "voice_compatible_resource_required",
    }
    assert headers["cache-control"] == "no-store"


def test_status_route_reports_ready_without_returning_connection_secret(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _enable(monkeypatch)
    _seed_binding(tmp_path)
    import tinyassets.onboarding as onboarding

    monkeypatch.setattr(onboarding, "_read_home", lambda _identity: "u-owner-home")
    status, body, _headers = _drive_status(identity=_owner())
    assert status == 200
    assert body == {
        "available": True,
        "state": "ready",
        "resource": "user_bound_voice_connection",
        "service_name": "Owner Voice Bridge",
        "privacy_url": "https://bridge.example/privacy",
    }
    assert "voice-bridge" not in json.dumps(body)
