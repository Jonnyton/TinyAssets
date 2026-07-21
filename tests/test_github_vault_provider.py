"""S4/S5 integration: GitHub clients consume the vault refresh seam."""

from __future__ import annotations

import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tinyassets import github_auth as ga
from tinyassets import github_http as gh
from tinyassets.credential_broker import (
    deposit_credential,
    github_connection_metadata,
    set_github_connection_metadata,
)
from tinyassets.credentials import SecretKind
from tinyassets.github_token_refresh import encode_user_token_bundle

_DEST = "Owner/Repo"
_UNIVERSE = "u-s4"


def _universe(platform_vault_env):
    path = platform_vault_env / _UNIVERSE
    path.mkdir(exist_ok=True)
    return path


def test_connection_metadata_is_non_secret_control_plane(platform_vault_env):
    set_github_connection_metadata(
        _UNIVERSE,
        _DEST,
        app_id="4242",
        installation_id="31337",
        app_actor_id="99",
        account_login="Owner",
        client_id="Iv1.client",
    )

    assert github_connection_metadata(_UNIVERSE, _DEST) == {
        "app_id": "4242",
        "installation_id": "31337",
        "app_actor_id": "99",
        "account_login": "owner",
        "client_id": "Iv1.client",
    }


def test_provider_mints_and_caches_scoped_installation_token(platform_vault_env):
    universe = _universe(platform_vault_env)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    deposit_credential(
        universe_id=_UNIVERSE,
        founder_id="founder-1",
        provider="github",
        destination=_DEST,
        purpose="app_auth",
        kind=SecretKind.GITHUB_APP_PRIVATE_KEY,
        value=private_pem,
    )
    set_github_connection_metadata(
        _UNIVERSE,
        _DEST,
        app_id="4242",
        installation_id="31337",
        app_actor_id="99",
        account_login="owner",
        client_id="Iv1.client",
    )
    exchanges: list[dict[str, object]] = []

    def mint(_url, _headers, payload):
        exchanges.append(payload)
        return 201, {
            "token": "ghs_rotating_installation",
            "expires_at": "2099-01-01T00:00:00Z",
            "permissions": {
                "contents": "write",
                "pull_requests": "write",
                "metadata": "read",
            },
            "repositories": [{"name": "Repo", "id": 1}],
        }

    provider = gh.VaultBackedTokenProvider(
        universe,
        _DEST,
        http_post_json=mint,
        now=lambda: 1_000.0,
    )

    assert provider.get_token(purpose=ga.PURPOSE_INSTALLATION) == (
        "ghs_rotating_installation"
    )
    assert provider.get_token(purpose=ga.PURPOSE_INSTALLATION) == (
        "ghs_rotating_installation"
    )
    assert len(exchanges) == 1
    assert exchanges[0]["repositories"] == ["Repo"]


def test_provider_rotates_expired_owner_token_through_vault(platform_vault_env):
    universe = _universe(platform_vault_env)
    now = time.time()
    deposit_credential(
        universe_id=_UNIVERSE,
        founder_id="founder-1",
        provider="github",
        destination=_DEST,
        purpose="user_review",
        kind=SecretKind.GITHUB_APP_USER_TOKEN,
        value=encode_user_token_bundle(
            access_token="ghu_expired",
            refresh_token="ghr_once",
            expires_at=now - 1,
            refresh_token_expires_at=now + 10_000,
        ),
        expires_at=now + 10_000,
    )
    set_github_connection_metadata(
        _UNIVERSE,
        _DEST,
        account_login="owner",
        client_id="Iv1.client",
    )
    refreshes: list[dict[str, str]] = []

    def refresh(_url, form):
        refreshes.append(form)
        return 200, {
            "access_token": "ghu_rotated",
            "refresh_token": "ghr_next",
            "expires_in": 28_800,
            "refresh_token_expires_in": 15_724_800,
        }

    provider = gh.VaultBackedTokenProvider(
        universe,
        _DEST,
        http_post_form=refresh,
        now=lambda: now,
    )

    assert provider.get_token(purpose=ga.PURPOSE_USER_REVIEW) == "ghu_rotated"
    assert len(refreshes) == 1
    assert refreshes[0]["refresh_token"] == "ghr_once"


def test_live_client_factory_uses_vault_provider_not_static(platform_vault_env):
    universe = _universe(platform_vault_env)
    deposit_credential(
        universe_id=_UNIVERSE,
        founder_id="founder-1",
        provider="github",
        destination=_DEST,
        purpose="external_write",
        kind=SecretKind.GITHUB_PAT,
        value=b"github_pat_dynamic",
    )

    client = gh.github_client_from_vault(universe, _DEST)

    assert client is not None
    assert isinstance(client._tp, gh.VaultBackedTokenProvider)
    assert not isinstance(client._tp, ga.StaticTokenProvider)
