"""Regression guards for the optional (resolve-not-gate) OAuth auth mode.

PR-167: a third ``UNIVERSE_SERVER_AUTH`` mode that resolves a Bearer token into
the request identity when one is present, but does NOT gate anonymous requests
(so authenticated founders get a real subject while anonymous tier-1 traffic
keeps working). These tests also guard the gated-mode 401 path, which the
``auth_middleware`` refactor rewrote.
"""

from __future__ import annotations

from typing import Any

import pytest

from workflow.auth.middleware import (
    auth_middleware,
    current_identity,
    require_auth,
    set_provider,
)
from workflow.auth.provider import (
    AuthProvider,
    DevAuthProvider,
    Identity,
    OptionalOAuthProvider,
    create_provider,
)

_SUBJECT = Identity(
    user_id="oauth-subject-1", username="u", capabilities=["read"],
)


class _FakeProvider(AuthProvider):
    """Resolves token 'valid' -> identity, anything else -> None.

    Gating is configurable so the same fake exercises both the optional
    (non-gating) and the legacy gated middleware paths.
    """

    def __init__(self, *, required: bool, identity: Identity | None) -> None:
        self._required = required
        self._identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self._identity if token == "valid" else None

    def is_auth_required(self) -> bool:
        return self._required

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
def _reset_auth_context():
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


# ── create_provider() mode selection ───────────────────────────────────────

@pytest.mark.parametrize("mode", ["optional", "resolve", "OPTIONAL", " optional "])
def test_optional_mode_selects_non_gating_oauth_provider(monkeypatch, tmp_path, mode):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_AUTH", mode)
    provider = create_provider()
    assert isinstance(provider, OptionalOAuthProvider)
    assert provider.is_auth_required() is False


@pytest.mark.parametrize("mode", ["true", "1", "yes", "oauth"])
def test_gated_modes_still_require_auth(monkeypatch, tmp_path, mode):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_AUTH", mode)
    provider = create_provider()
    # OAuthProvider, NOT the optional subclass.
    assert type(provider).__name__ == "OAuthProvider"
    assert provider.is_auth_required() is True


@pytest.mark.parametrize("mode", ["false", "", "off", "nope"])
def test_falsy_modes_stay_dev_anonymous(monkeypatch, tmp_path, mode):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_AUTH", mode)
    provider = create_provider()
    assert isinstance(provider, DevAuthProvider)
    assert provider.is_auth_required() is False


# ── optional mode resolves identity WITHOUT gating ─────────────────────────

def test_optional_mode_resolves_valid_token():
    set_provider(_FakeProvider(required=False, identity=_SUBJECT))
    auth_middleware("valid")
    assert current_identity().user_id == "oauth-subject-1"
    # Resolved subject is authorized without raising.
    assert require_auth().user_id == "oauth-subject-1"


def test_optional_mode_invalid_token_is_anonymous_not_gated():
    set_provider(_FakeProvider(required=False, identity=_SUBJECT))
    auth_middleware("bad")
    assert current_identity().user_id == "anonymous"
    # The whole point: anonymous is allowed through, NOT 401'd.
    assert require_auth().user_id == "anonymous"


def test_optional_mode_absent_token_is_anonymous():
    set_provider(_FakeProvider(required=False, identity=_SUBJECT))
    auth_middleware(None)
    assert current_identity().user_id == "anonymous"
    assert require_auth().user_id == "anonymous"


# ── regression: gated mode still rejects (the rewritten 401 path) ──────────

def test_gated_mode_invalid_token_still_rejected():
    set_provider(_FakeProvider(required=True, identity=_SUBJECT))
    auth_middleware("bad")
    with pytest.raises(PermissionError):
        require_auth()


def test_gated_mode_valid_token_resolves():
    set_provider(_FakeProvider(required=True, identity=_SUBJECT))
    auth_middleware("valid")
    assert current_identity().user_id == "oauth-subject-1"
    assert require_auth().user_id == "oauth-subject-1"


# ── dev mode unchanged: a present token still resolves to anonymous ────────

def test_dev_mode_token_present_stays_anonymous():
    set_provider(DevAuthProvider())
    auth_middleware("valid")  # DevAuthProvider.resolve_token returns ANONYMOUS
    assert current_identity().user_id == "anonymous"
    assert require_auth().user_id == "anonymous"
