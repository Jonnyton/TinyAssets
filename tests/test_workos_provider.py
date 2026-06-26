"""Tests for the WorkOS AuthKit Resource Server provider (founder-identity slice 1).

Our MCP server validates a WorkOS AuthKit access-token JWT and resolves its
``sub`` to the founder Identity. These tests sign real RS256 tokens with a
generated keypair and inject a fake JWKS client, so nothing touches the network.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from workflow.auth.provider import Identity, create_provider
from workflow.auth.workos_provider import (
    WorkOSAuthProvider,
    derive_endpoints,
)

ISSUER = "https://inventive-van-62-staging.authkit.app"
RESOURCE = "https://tinyassets.io/mcp"


@pytest.fixture(scope="module")
def keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeSigningKey:
    def __init__(self, public_key: object) -> None:
        self.key = public_key


class _FakeJWKSClient:
    """Stand-in for PyJWKClient: always returns the configured public key."""

    def __init__(self, public_key: object) -> None:
        self._key = _FakeSigningKey(public_key)

    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        return self._key


def _provider(
    keypair: rsa.RSAPrivateKey,
    *,
    issuer: str = ISSUER,
    audience: str | None = None,
) -> WorkOSAuthProvider:
    return WorkOSAuthProvider(
        issuer=issuer,
        jwks_uri="https://example.invalid/oauth2/jwks",
        audience=audience,
        jwks_client=_FakeJWKSClient(keypair.public_key()),
    )


def _sign(keypair: rsa.RSAPrivateKey, **claims: object) -> str:
    now = int(time.time())
    payload = {
        "sub": "user_workos_123",
        "iss": ISSUER,
        "iat": now,
        "exp": now + 3600,
        "email": "founder@example.com",
    }
    payload.update(claims)
    return jwt.encode(payload, keypair, algorithm="RS256", headers={"kid": "test"})


# --- derive_endpoints ------------------------------------------------------


def test_derive_endpoints_bare_domain() -> None:
    issuer, jwks = derive_endpoints("inventive-van-62-staging.authkit.app")
    assert issuer == ISSUER
    assert jwks == f"{ISSUER}/oauth2/jwks"


def test_derive_endpoints_full_origin_and_trailing_slash() -> None:
    issuer, jwks = derive_endpoints("https://foo.authkit.app/")
    assert issuer == "https://foo.authkit.app"
    assert jwks == "https://foo.authkit.app/oauth2/jwks"


def test_derive_endpoints_rejects_empty() -> None:
    with pytest.raises(ValueError):
        derive_endpoints("   ")


# --- resolve_token: happy path --------------------------------------------


def test_valid_token_resolves_to_founder_identity(keypair) -> None:
    ident = _provider(keypair).resolve_token(_sign(keypair))
    assert isinstance(ident, Identity)
    assert ident.user_id == "user_workos_123"  # sub == founder key
    assert ident.username == "founder@example.com"
    assert ident.metadata["auth_provider"] == "workos"
    assert ident.metadata["email"] == "founder@example.com"
    assert "write" in ident.capabilities


def test_username_falls_back_to_sub_without_email(keypair) -> None:
    ident = _provider(keypair).resolve_token(_sign(keypair, email=""))
    assert ident is not None
    assert ident.username == "user_workos_123"


def test_org_role_permissions_surface_in_metadata(keypair) -> None:
    token = _sign(
        keypair,
        org_id="org_1",
        role="admin",
        permissions=["a", "b"],
    )
    ident = _provider(keypair).resolve_token(token)
    assert ident is not None
    assert ident.metadata["org_id"] == "org_1"
    assert ident.metadata["role"] == "admin"
    assert ident.metadata["permissions"] == ["a", "b"]


# --- resolve_token: rejections --------------------------------------------


def test_expired_token_rejected(keypair) -> None:
    now = int(time.time())
    token = _sign(keypair, iat=now - 7200, exp=now - 3600)
    assert _provider(keypair).resolve_token(token) is None


def test_missing_sub_rejected(keypair) -> None:
    # require=["exp","sub"] -> PyJWT raises MissingRequiredClaim.
    assert _provider(keypair).resolve_token(_sign(keypair, sub="")) is None


def test_anonymous_sub_rejected(keypair) -> None:
    assert _provider(keypair).resolve_token(_sign(keypair, sub="anonymous")) is None


def test_wrong_issuer_rejected(keypair) -> None:
    token = _sign(keypair, iss="https://evil.example.com")
    assert _provider(keypair).resolve_token(token) is None


def test_bad_signature_rejected(keypair, other_key) -> None:
    # Token signed by a different key than the provider's JWKS exposes.
    token = jwt.encode(
        {"sub": "x", "iss": ISSUER, "exp": int(time.time()) + 3600},
        other_key,
        algorithm="RS256",
        headers={"kid": "test"},
    )
    assert _provider(keypair).resolve_token(token) is None


def test_empty_token_returns_none(keypair) -> None:
    p = _provider(keypair)
    assert p.resolve_token("") is None
    assert p.resolve_token("   ") is None


# --- audience binding ------------------------------------------------------


def test_audience_enforced_when_configured(keypair) -> None:
    p = _provider(keypair, audience=RESOURCE)
    assert p.resolve_token(_sign(keypair, aud=RESOURCE)) is not None
    assert p.resolve_token(_sign(keypair, aud="https://other")) is None
    assert p.resolve_token(_sign(keypair)) is None  # no aud at all


def test_audience_skipped_when_not_configured(keypair) -> None:
    # No audience on the provider -> tokens without aud still validate.
    assert _provider(keypair).resolve_token(_sign(keypair)) is not None


# --- provider contract -----------------------------------------------------


def test_is_auth_required_false(keypair) -> None:
    # Slice 1 never rejects anonymous; gating is slice 2.
    assert _provider(keypair).is_auth_required() is False


def test_flow_methods_are_not_ours(keypair) -> None:
    p = _provider(keypair)
    with pytest.raises(NotImplementedError):
        p.register_client({})
    with pytest.raises(NotImplementedError):
        p.create_authorization("c", "r", "s", "st", "cc", "S256")
    with pytest.raises(NotImplementedError):
        p.exchange_code("code", "c", "r", "v")


# --- from_env / factory ----------------------------------------------------


def test_from_env_derives_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "inventive-van-62-staging.authkit.app")
    monkeypatch.delenv("WORKOS_MCP_RESOURCE", raising=False)
    p = WorkOSAuthProvider.from_env()
    assert p._issuer == ISSUER
    assert p._jwks_uri == f"{ISSUER}/oauth2/jwks"
    assert p._audience is None


def test_from_env_reads_resource_audience(monkeypatch) -> None:
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "foo.authkit.app")
    monkeypatch.setenv("WORKOS_MCP_RESOURCE", RESOURCE)
    assert WorkOSAuthProvider.from_env()._audience == RESOURCE


def test_from_env_requires_domain(monkeypatch) -> None:
    monkeypatch.delenv("WORKOS_AUTHKIT_DOMAIN", raising=False)
    with pytest.raises(RuntimeError):
        WorkOSAuthProvider.from_env()


def test_create_provider_selects_workos(monkeypatch) -> None:
    monkeypatch.setenv("UNIVERSE_SERVER_AUTH", "workos")
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "foo.authkit.app")
    assert isinstance(create_provider(), WorkOSAuthProvider)


# --- integration: the whole point of slice 1 ------------------------------


def test_middleware_chain_yields_real_subject(keypair, monkeypatch) -> None:
    """auth_middleware -> current_identity -> _current_actor returns the real sub,
    not 'anonymous'. This is the slice-1 acceptance behavior."""
    from workflow.api import engine_helpers
    from workflow.auth import middleware as mw

    monkeypatch.delenv("UNIVERSE_SERVER_USER", raising=False)
    mw.set_provider(_provider(keypair))
    try:
        mw.auth_middleware(_sign(keypair))
        assert mw.current_identity().user_id == "user_workos_123"
        assert engine_helpers._current_actor() == "user_workos_123"
    finally:
        mw.auth_middleware(None)  # reset request-local identity to ANONYMOUS
        mw.set_provider(None)


def test_middleware_anonymous_without_token(keypair, monkeypatch) -> None:
    from workflow.auth import middleware as mw

    monkeypatch.delenv("UNIVERSE_SERVER_USER", raising=False)
    mw.set_provider(_provider(keypair))
    try:
        mw.auth_middleware(None)
        assert mw.current_identity().user_id == "anonymous"
    finally:
        mw.set_provider(None)
