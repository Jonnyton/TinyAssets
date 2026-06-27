"""Regression guards for request-scoped MCP actor identity."""

from __future__ import annotations

from typing import Any

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity


class StaticAuthProvider(AuthProvider):
    def __init__(self, identity: Identity | None) -> None:
        self.identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self.identity if token == "valid" else None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"client_id": "test-client", **metadata}

    def create_authorization(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        return "test-code"

    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        return None


@pytest.fixture(autouse=True)
def _reset_auth_context() -> None:
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def test_current_actor_prefers_authenticated_oauth_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.api.engine_helpers import _current_actor

    monkeypatch.setenv("UNIVERSE_SERVER_USER", "env-actor")
    set_provider(StaticAuthProvider(Identity(
        user_id="oauth-subject-123",
        username="display-name",
        capabilities=["tinyassets.universe.write"],
    )))

    auth_middleware("valid")

    assert _current_actor() == "oauth-subject-123"


def test_current_actor_falls_back_to_env_without_request_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.api.engine_helpers import _current_actor

    monkeypatch.setenv("UNIVERSE_SERVER_USER", "env-actor")
    set_provider(DevAuthProvider())
    auth_middleware(None)

    assert _current_actor() == "env-actor"


def test_get_status_account_user_uses_authenticated_subject(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import json

    from tinyassets.api.status import get_status

    base = tmp_path / "output"
    universe = base / "status-uni"
    universe.mkdir(parents=True)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "status-uni")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "env-actor")
    set_provider(StaticAuthProvider(Identity(
        user_id="oauth-status-subject",
        username="display-name",
        capabilities=["tinyassets.universe.read"],
    )))

    auth_middleware("valid")

    payload = json.loads(get_status())

    assert payload["session_boundary"]["account_user"] == "oauth-status-subject"


@pytest.mark.asyncio
async def test_auth_context_middleware_sets_actor_for_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.auth.middleware import AuthContextMiddleware

    seen: list[str] = []

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        seen.append(_current_actor())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    monkeypatch.setenv("UNIVERSE_SERVER_USER", "env-actor")
    set_provider(StaticAuthProvider(Identity(
        user_id="oauth-subject-456",
        username="display-name",
        capabilities=["tinyassets.universe.write"],
    )))

    middleware = AuthContextMiddleware(app)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(b"authorization", b"Bearer valid")],
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await middleware(scope, receive, send)

    assert seen == ["oauth-subject-456"]
    assert _current_actor() == "env-actor"
