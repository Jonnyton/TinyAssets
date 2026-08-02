from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tinyassets.auth.host_binding import HostBindingAuthValidator, HostBindingIdentity

ISSUER = "https://example.authkit.app"
HOST_RESOURCE = "https://tinyassets.io/host-binding"
MCP_RESOURCE = "https://tinyassets.io/mcp"


@pytest.fixture(scope="module")
def keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    def __init__(self, public_key: object) -> None:
        self.key = public_key


class _JWKSClient:
    def __init__(self, public_key: object) -> None:
        self._signing_key = _SigningKey(public_key)

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        return self._signing_key


def _validator(
    keypair: rsa.RSAPrivateKey,
    *,
    now: int,
) -> HostBindingAuthValidator:
    return HostBindingAuthValidator(
        issuer=ISSUER,
        jwks_uri=f"{ISSUER}/oauth2/jwks",
        audience=HOST_RESOURCE,
        jwks_client=_JWKSClient(keypair.public_key()),
        now=lambda: now,
    )


def _token(keypair: rsa.RSAPrivateKey, *, now: int, **claims: object) -> str:
    payload: dict[str, object] = {
        "iss": ISSUER,
        "sub": "user_01HOSTOWNER",
        "aud": HOST_RESOURCE,
        "iat": now,
        "auth_time": now,
        "exp": now + 3600,
        "permissions": ["host:enroll"],
    }
    payload.update(claims)
    return jwt.encode(payload, keypair, algorithm="RS256", headers={"kid": "test"})


def _resolve(
    validator: HostBindingAuthValidator,
    token: str | None,
    *,
    is_tls: bool = True,
) -> HostBindingIdentity | None:
    header = f"Bearer {token}" if token is not None else None
    return validator.resolve_authorization(
        header,
        is_tls=is_tls,
        required_permission="host:enroll",
    )


def test_dedicated_audience_subject_and_recent_interactive_auth_resolve(keypair) -> None:
    now = int(time.time())
    identity = _resolve(
        _validator(keypair, now=now),
        _token(
            keypair,
            now=now,
            aud=[HOST_RESOURCE],
            org_id="org_01EHWNCE74X7JSDV0X3SZ3KJNY",
        ),
    )

    assert identity == HostBindingIdentity(
        issuer=ISSUER,
        subject="user_01HOSTOWNER",
        audience=HOST_RESOURCE,
        auth_time=now,
        org_id="org_01EHWNCE74X7JSDV0X3SZ3KJNY",
        permissions=frozenset({"host:enroll"}),
    )


@pytest.mark.parametrize(
    "audience",
    [
        MCP_RESOURCE,
        [MCP_RESOURCE],
        [HOST_RESOURCE, MCP_RESOURCE],
        [HOST_RESOURCE, "https://other.example/resource"],
        "https://other.example/resource",
        [],
        None,
    ],
)
def test_only_the_exact_sole_host_binding_audience_is_accepted(
    keypair,
    audience: object,
) -> None:
    now = int(time.time())
    claims = {} if audience is None else {"aud": audience}
    token = _token(keypair, now=now, **claims)
    if audience is None:
        token = _token_without_claim(keypair, now=now, claim="aud")

    assert _resolve(_validator(keypair, now=now), token) is None


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.example"},
        {"sub": ""},
        {"sub": "   "},
        {"sub": " user_01HOSTOWNER"},
        {"sub": "user_01HOSTOWNER "},
        {"sub": "anonymous"},
        {"sub": 123},
        {"permissions": []},
        {"permissions": ["host:manage"]},
        {"org_id": "organization_123"},
        {"org_id": "org_"},
        {"org_id": "org_bad/slash"},
        {"org_id": 123},
    ],
)
def test_wrong_identity_permission_or_organization_claim_fails(
    keypair,
    claims: dict[str, object],
) -> None:
    now = int(time.time())
    assert (
        _resolve(
            _validator(keypair, now=now),
            _token(keypair, now=now, **claims),
        )
        is None
    )


@pytest.mark.parametrize("auth_time", [None, -1, "recent", True])
def test_missing_or_malformed_auth_time_fails(keypair, auth_time: object) -> None:
    now = int(time.time())
    token = (
        _token_without_claim(keypair, now=now, claim="auth_time")
        if auth_time is None
        else _token(keypair, now=now, auth_time=auth_time)
    )
    assert _resolve(_validator(keypair, now=now), token) is None


def test_stale_auth_time_fails_even_when_iat_is_fresh(keypair) -> None:
    now = int(time.time())
    token = _token(keypair, now=now, iat=now, auth_time=now - 301)
    assert _resolve(_validator(keypair, now=now), token) is None


def test_future_auth_time_fails(keypair) -> None:
    now = int(time.time())
    assert (
        _resolve(
            _validator(keypair, now=now),
            _token(keypair, now=now, auth_time=now + 61),
        )
        is None
    )


@pytest.mark.parametrize(
    "header",
    [None, "", "Basic abc", "Bearer", "Bearer first second"],
)
def test_tls_authorization_bearer_is_the_only_request_authority(
    keypair,
    monkeypatch,
    header: str | None,
) -> None:
    now = int(time.time())
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "maintainer")
    monkeypatch.setenv("TINYASSETS_HOST_OWNER", "body-or-process-owner")
    assert (
        _validator(keypair, now=now).resolve_authorization(
            header,
            is_tls=True,
            required_permission="host:enroll",
        )
        is None
    )


def test_plain_http_refuses_an_otherwise_valid_bearer(keypair) -> None:
    now = int(time.time())
    assert (
        _resolve(
            _validator(keypair, now=now),
            _token(keypair, now=now),
            is_tls=False,
        )
        is None
    )


@pytest.mark.parametrize(
    "alternate_authority",
    [
        {"cookie_authority": True},
        {"query_authority": True},
        {"credentialed_cross_origin": True},
        {"body_owner": True},
        {"ambient_identity": True},
    ],
)
def test_alternate_or_browser_ambient_authority_refuses_a_valid_bearer(
    keypair,
    alternate_authority: dict[str, bool],
) -> None:
    now = int(time.time())
    token = _token(keypair, now=now)

    assert (
        _validator(keypair, now=now).resolve_authorization(
            f"Bearer {token}",
            is_tls=True,
            required_permission="host:enroll",
            **alternate_authority,
        )
        is None
    )


def test_from_env_requires_dedicated_resource_without_mcp_fallback(
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "example.authkit.app")
    monkeypatch.setenv("WORKOS_MCP_RESOURCE", MCP_RESOURCE)
    monkeypatch.delenv("WORKOS_HOST_BINDING_RESOURCE", raising=False)
    monkeypatch.delenv("WORKOS_ALLOW_NO_AUDIENCE", raising=False)

    with pytest.raises(RuntimeError, match="WORKOS_HOST_BINDING_RESOURCE"):
        HostBindingAuthValidator.from_env()


def test_from_env_rejects_the_global_audience_disable_override(monkeypatch) -> None:
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "example.authkit.app")
    monkeypatch.setenv("WORKOS_HOST_BINDING_RESOURCE", HOST_RESOURCE)
    monkeypatch.setenv("WORKOS_ALLOW_NO_AUDIENCE", "1")

    with pytest.raises(RuntimeError, match="WORKOS_ALLOW_NO_AUDIENCE"):
        HostBindingAuthValidator.from_env()


def test_from_env_rejects_reusing_the_mcp_resource(monkeypatch) -> None:
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "example.authkit.app")
    monkeypatch.setenv("WORKOS_HOST_BINDING_RESOURCE", MCP_RESOURCE)
    monkeypatch.setenv("WORKOS_MCP_RESOURCE", MCP_RESOURCE)
    monkeypatch.delenv("WORKOS_ALLOW_NO_AUDIENCE", raising=False)

    with pytest.raises(RuntimeError, match="must differ from WORKOS_MCP_RESOURCE"):
        HostBindingAuthValidator.from_env()


def _token_without_claim(
    keypair: rsa.RSAPrivateKey,
    *,
    now: int,
    claim: str,
) -> str:
    payload: dict[str, object] = {
        "iss": ISSUER,
        "sub": "user_01HOSTOWNER",
        "aud": HOST_RESOURCE,
        "iat": now,
        "auth_time": now,
        "exp": now + 3600,
        "permissions": ["host:enroll"],
    }
    payload.pop(claim)
    return jwt.encode(payload, keypair, algorithm="RS256", headers={"kid": "test"})
