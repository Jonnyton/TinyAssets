"""A caller observes only its own resolved identity, never credentials."""

from __future__ import annotations

import json
from inspect import signature
from typing import Any

import pytest

from tinyassets.auth import middleware
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity


class _Provider(AuthProvider):
    def resolve_token(self, token: str) -> Identity | None:
        if token == "secret-bearer-sentinel":
            return Identity(
                user_id="founder-a",
                username="founder-a@example.test",
                capabilities=["read", "write"],
            )
        return None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return metadata

    def create_authorization(self, *args: Any, **kwargs: Any) -> str:
        return "code"

    def exchange_code(self, *args: Any, **kwargs: Any) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_auth() -> None:
    middleware.set_provider(DevAuthProvider())
    middleware.auth_middleware(None)
    yield
    middleware.set_provider(DevAuthProvider())
    middleware.auth_middleware(None)


def test_request_identity_reports_only_bearer_presence_and_subject() -> None:
    middleware.set_provider(_Provider())
    middleware.auth_middleware("secret-bearer-sentinel")

    observed = middleware.request_identity_snapshot()

    assert observed == {"bearer_present": True, "subject": "founder-a"}
    encoded = json.dumps(observed)
    assert "secret-bearer-sentinel" not in encoded
    assert "founder-a@example.test" not in encoded
    assert "capabilities" not in encoded


def test_unresolved_identity_never_falls_back_to_ambient_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host-founder")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host-founder")
    middleware.set_provider(_Provider())
    middleware.auth_middleware("invalid-bearer")

    assert middleware.request_identity_snapshot() == {
        "bearer_present": True,
        "subject": "anonymous",
    }


def test_get_status_exposes_current_request_identity_without_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tinyassets.universe_server as server

    monkeypatch.setattr(
        server,
        "_get_status_impl",
        lambda universe_id="": json.dumps(
            {"schema_version": 1, "requested_universe": universe_id}
        ),
    )
    middleware.set_provider(_Provider())
    middleware.auth_middleware("secret-bearer-sentinel")

    payload = json.loads(server.get_status(universe_id="founder-b"))

    assert payload["request_identity"] == {
        "bearer_present": True,
        "subject": "founder-a",
    }
    assert payload["requested_universe"] == "founder-b"
    assert "principal" not in signature(server.get_status).parameters
    assert "subject" not in signature(server.get_status).parameters
    assert "secret-bearer-sentinel" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_request_context_resets_bearer_presence_after_dispatch() -> None:
    seen: list[dict[str, bool | str]] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        seen.append(middleware.request_identity_snapshot())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware.set_provider(_Provider())
    wrapped = middleware.AuthContextMiddleware(app)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": [(b"authorization", b"Bearer secret-bearer-sentinel")],
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        return None

    await wrapped(scope, receive, send)

    assert seen == [{"bearer_present": True, "subject": "founder-a"}]
    assert middleware.request_identity_snapshot() == {
        "bearer_present": False,
        "subject": "anonymous",
    }
