"""Regression coverage for self-only request identity status evidence."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

_FINGERPRINT_KEY = "test-only-identity-fingerprint-key-32-bytes"
_SUBJECT = "workos|test-founder-alpha"
_BEARER = "bearer-secret-that-must-not-appear"


class _StaticProvider(AuthProvider):
    def resolve_token(self, token: str) -> Identity | None:
        if token != _BEARER:
            return None
        return Identity(
            user_id=_SUBJECT,
            username="alpha@example.invalid",
            capabilities=["tinyassets.universe.read"],
        )

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
def _identity_context(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TINYASSETS_IDENTITY_FINGERPRINT_KEY", _FINGERPRINT_KEY)
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_USER", raising=False)
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _create_universe(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    universe_id = "status-identity-universe"
    universe_dir = tmp_path / universe_id
    universe_dir.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", universe_id)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "ambient-maintainer")
    return universe_id


def test_authenticated_status_returns_stable_self_only_fingerprint(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.api.status import get_status

    universe_id = _create_universe(tmp_path, monkeypatch)
    set_provider(_StaticProvider())
    auth_middleware(_BEARER)

    first = json.loads(get_status(universe_id))
    second = json.loads(get_status(universe_id))

    assert first["request_identity"]["bearer_present"] is True
    assert first["request_identity"]["principal_fingerprint"].startswith("v1:")
    assert first["request_identity"] == second["request_identity"]
    encoded = json.dumps(first, sort_keys=True)
    assert _SUBJECT not in encoded
    assert "alpha@example.invalid" not in encoded
    assert "ambient-maintainer" not in encoded
    assert _BEARER not in encoded
    assert _FINGERPRINT_KEY not in encoded


def test_authenticated_status_redacts_subject_from_activity_evidence(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.api.status import get_status

    universe_id = _create_universe(tmp_path, monkeypatch)
    (tmp_path / universe_id / "activity.log").write_text(
        f"[2026-07-24 12:00:00] [{_SUBJECT}] completed request\n",
        encoding="utf-8",
    )
    set_provider(_StaticProvider())
    auth_middleware(_BEARER)

    payload = json.loads(get_status(universe_id))

    assert payload["session_boundary"]["prior_session_context_available"] is True
    assert _SUBJECT not in json.dumps(payload, sort_keys=True)


def test_authenticated_first_contact_has_explicit_identity_evidence(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.api.status import get_status

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    set_provider(_StaticProvider())
    auth_middleware(_BEARER)

    payload = json.loads(get_status())

    assert payload["first_contact"]["event"] == "no_universe_yet"
    assert payload["request_identity"]["bearer_present"] is True
    assert payload["request_identity"]["principal_fingerprint"].startswith("v1:")


def test_anonymous_status_has_explicit_identity_evidence(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.api.status import get_status

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    auth_middleware(None)

    payload = json.loads(get_status("missing-universe"))

    assert payload["request_identity"]["bearer_present"] is False
    assert payload["request_identity"]["principal_fingerprint"].startswith(
        "v1:anonymous:"
    )


def test_status_alias_returns_identical_request_identity(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.universe_server import get_status, read_graph

    universe_id = _create_universe(tmp_path, monkeypatch)
    set_provider(_StaticProvider())
    auth_middleware(_BEARER)

    direct = json.loads(get_status(universe_id))
    alias = json.loads(read_graph(target="status", graph_id=universe_id))

    assert alias["request_identity"] == direct["request_identity"]


def test_missing_fingerprint_key_fails_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.api.status import get_status

    _create_universe(tmp_path, monkeypatch)
    set_provider(_StaticProvider())
    auth_middleware(_BEARER)
    monkeypatch.delenv("TINYASSETS_IDENTITY_FINGERPRINT_KEY")

    payload = json.loads(get_status())

    assert payload == {
        "schema_version": 1,
        "error": "identity_fingerprint_unavailable",
        "request_identity": {
            "bearer_present": True,
            "principal_fingerprint": None,
        },
    }


@pytest.mark.asyncio
async def test_bearer_presence_is_request_local_and_cleans_up() -> None:
    from tinyassets.auth.middleware import (
        AuthContextMiddleware,
        current_bearer_present,
    )

    seen: list[bool] = []

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        seen.append(current_bearer_present())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    set_provider(_StaticProvider())
    middleware = AuthContextMiddleware(app)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(b"authorization", f"Bearer {_BEARER}".encode())],
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        pass

    await middleware(scope, receive, send)

    assert seen == [True]
    assert current_bearer_present() is False
