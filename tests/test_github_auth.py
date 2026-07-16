"""S4 / E4: GitHub auth strategies (TokenProvider). No storage, no network.

Covers the PAT/user static provider, the App-JWT → installation-token minting
(≤10 min JWT, 1h token cached in memory, re-minted before expiry, never
persisted/logged), and the composite purpose routing. Token values must never
appear in repr/errors.
"""

from __future__ import annotations

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tinyassets import github_auth as ga


@pytest.fixture(scope="module")
def app_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (
        key,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    )


# ── static provider ──────────────────────────────────────────────────────────


def test_static_provider_serves_its_purpose_only():
    p = ga.StaticTokenProvider("ghp_pat", purposes={ga.PURPOSE_INSTALLATION})
    assert p.get_token(purpose=ga.PURPOSE_INSTALLATION) == "ghp_pat"
    with pytest.raises(ga.TokenUnavailable):
        p.get_token(purpose=ga.PURPOSE_USER_REVIEW)


def test_static_provider_fails_closed_on_empty():
    p = ga.StaticTokenProvider("", purposes={ga.PURPOSE_USER_REVIEW})
    with pytest.raises(ga.TokenUnavailable):
        p.get_token(purpose=ga.PURPOSE_USER_REVIEW)


def test_static_provider_repr_hides_token():
    p = ga.StaticTokenProvider("gho_secret", purposes={ga.PURPOSE_USER_REVIEW})
    assert "gho_secret" not in repr(p)


# ── App provider: JWT + installation token minting ───────────────────────────


def test_app_jwt_expiry_is_within_10_minutes(app_pem):
    key, pem = app_pem
    captured = {}

    def exchange(app_jwt, inst_id):
        captured["jwt"] = app_jwt
        captured["inst"] = inst_id
        return "ghs_install", 1000.0 + 3600

    provider = ga.GitHubAppTokenProvider(
        app_id="123", private_key_pem=pem, installation_id="42",
        token_exchange=exchange, now=lambda: 1000.0,
    )
    provider.get_token(purpose=ga.PURPOSE_INSTALLATION)
    claims = pyjwt.decode(
        captured["jwt"], key.public_key(), algorithms=["RS256"],
        options={"verify_exp": False},
    )
    assert claims["iss"] == "123"
    assert claims["exp"] - claims["iat"] <= 600  # GitHub hard cap
    assert captured["inst"] == "42"


def test_installation_token_cached_and_reminted(app_pem):
    _key, pem = app_pem
    exchanges = {"n": 0}

    def exchange(app_jwt, inst_id):
        exchanges["n"] += 1
        return f"ghs_install_{exchanges['n']}", now_holder[0] + 3600

    now_holder = [1000.0]
    provider = ga.GitHubAppTokenProvider(
        app_id="1", private_key_pem=pem, installation_id="42",
        token_exchange=exchange, now=lambda: now_holder[0],
    )
    t1 = provider.get_token(purpose=ga.PURPOSE_INSTALLATION)
    t2 = provider.get_token(purpose=ga.PURPOSE_INSTALLATION)
    assert t1 == t2 and exchanges["n"] == 1  # cached, one exchange
    # Advance past expiry → re-mint.
    now_holder[0] = 1000.0 + 3600
    t3 = provider.get_token(purpose=ga.PURPOSE_INSTALLATION)
    assert t3 != t1 and exchanges["n"] == 2


def test_app_provider_refuses_user_review_purpose(app_pem):
    _key, pem = app_pem
    provider = ga.GitHubAppTokenProvider(
        app_id="1", private_key_pem=pem, installation_id="42",
        token_exchange=lambda j, i: ("ghs_x", 9e9),
    )
    with pytest.raises(ga.TokenUnavailable):
        provider.get_token(purpose=ga.PURPOSE_USER_REVIEW)


def test_app_provider_repr_hides_secrets(app_pem):
    _key, pem = app_pem
    provider = ga.GitHubAppTokenProvider(
        app_id="1", private_key_pem=pem, installation_id="42",
        token_exchange=lambda j, i: ("ghs_secrettoken", 9e9),
    )
    provider.get_token(purpose=ga.PURPOSE_INSTALLATION)
    assert "ghs_secrettoken" not in repr(provider)
    assert "PRIVATE KEY" not in repr(provider)


# ── composite routing ────────────────────────────────────────────────────────


def test_composite_routes_by_purpose():
    comp = ga.CompositeTokenProvider(
        installation=ga.StaticTokenProvider("ghs_inst", purposes={ga.PURPOSE_INSTALLATION}),
        user_review=ga.StaticTokenProvider("gho_user", purposes={ga.PURPOSE_USER_REVIEW}),
    )
    assert comp.get_token(purpose=ga.PURPOSE_INSTALLATION) == "ghs_inst"
    assert comp.get_token(purpose=ga.PURPOSE_USER_REVIEW) == "gho_user"


def test_composite_without_user_provider_fails_closed_on_review():
    comp = ga.CompositeTokenProvider(
        installation=ga.StaticTokenProvider("ghs_inst", purposes={ga.PURPOSE_INSTALLATION}),
    )
    with pytest.raises(ga.TokenUnavailable):
        comp.get_token(purpose=ga.PURPOSE_USER_REVIEW)
