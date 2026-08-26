"""A caller can observe only its own resolved request identity, never a token."""

from __future__ import annotations

import json
from inspect import signature

from tinyassets.auth import middleware
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity


class _Provider(AuthProvider):
    def resolve_token(self, token: str):
        if token == "secret-bearer-sentinel":
            return Identity(
                user_id="founder-a",
                username="founder-a@example.test",
                capabilities=["read", "write"],
            )
        return None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata):
        return metadata

    def create_authorization(self, *args, **kwargs):
        return "code"

    def exchange_code(self, *args, **kwargs):
        return None


def test_request_identity_snapshot_reports_only_presence_and_subject() -> None:
    snapshot = getattr(middleware, "request_identity_snapshot", None)
    assert callable(snapshot), "request identity observability is missing"

    middleware.set_provider(_Provider())
    try:
        middleware.auth_middleware("secret-bearer-sentinel")
        observed = snapshot()
    finally:
        middleware.set_provider(DevAuthProvider())
        middleware.auth_middleware(None)

    assert observed == {"bearer_present": True, "subject": "founder-a"}
    encoded = json.dumps(observed)
    assert "secret-bearer-sentinel" not in encoded
    assert "founder-a@example.test" not in encoded
    assert "capabilities" not in encoded


def test_get_status_exposes_current_request_identity_without_subject_selector(
    monkeypatch,
) -> None:
    import tinyassets.universe_server as server

    middleware.set_provider(_Provider())
    monkeypatch.setattr(
        server,
        "_get_status_impl",
        lambda universe_id="": json.dumps({
            "schema_version": 1,
            "requested_universe": universe_id,
        }),
    )
    try:
        middleware.auth_middleware("secret-bearer-sentinel")
        payload = json.loads(server.get_status(universe_id="founder-b"))
    finally:
        middleware.set_provider(DevAuthProvider())
        middleware.auth_middleware(None)

    assert payload["request_identity"] == {
        "bearer_present": True,
        "subject": "founder-a",
    }
    assert payload["requested_universe"] == "founder-b"
    assert "principal" not in signature(server.get_status).parameters
    assert "subject" not in signature(server.get_status).parameters
    assert "secret-bearer-sentinel" not in json.dumps(payload)


def test_anonymous_snapshot_is_explicit() -> None:
    snapshot = getattr(middleware, "request_identity_snapshot", None)
    assert callable(snapshot), "request identity observability is missing"

    middleware.set_provider(DevAuthProvider())
    middleware.auth_middleware(None)
    assert snapshot() == {"bearer_present": False, "subject": "anonymous"}
