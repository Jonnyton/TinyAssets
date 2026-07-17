"""Contract tests for the vault-backed GitHub token refresh provider.

Runs against a REAL local HTTP server that mimics GitHub's actual endpoint
shapes — no permissive fakes:

* ``POST /app/installations/<id>/access_tokens`` verifies the RS256 App JWT
  signature/claims against the app's public key: 201 + token on success,
  401 on a bad JWT (GitHub's shape).
* ``POST /login/oauth/access_token`` implements one-use refresh-token
  rotation and reports grant errors the way GitHub really does: HTTP 200
  with an ``error`` field in the JSON body (status alone is not a signal).

The client under test uses its DEFAULT urllib transport against the loopback
server, so the wire shape (headers, form encoding, JSON parsing) is exercised
for real.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tinyassets.credential_broker import (
    deposit_credential,
    find_binding,
    platform_backend,
    resolve_credential,
)
from tinyassets.credentials import (
    CredentialUnavailable,
    SecretKind,
    VaultErrorCode,
)
from tinyassets.github_token_refresh import (
    GitHubTokenExchangeError,
    decode_user_token_bundle,
    encode_user_token_bundle,
    mint_installation_token,
    refresh_user_token,
)

APP_ID = "424242"
INSTALLATION_ID = "31337"
CLIENT_ID = "Iv1.testclientid"


@pytest.fixture(scope="module")
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture()
def fake_github(rsa_keypair):
    """A real HTTP server with GitHub's endpoint shapes + rotation state."""
    _private_pem, public_pem = rsa_keypair
    state = {
        "current_refresh_token": "ghr_refresh_0",
        "used_refresh_tokens": set(),
        "counter": 0,
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):  # keep test output quiet
            pass

        def _reply(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):  # noqa: N802 - http.server API
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            state["requests"].append(self.path)
            if self.path == f"/app/installations/{INSTALLATION_ID}/access_tokens":
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer "):
                    self._reply(401, {"message": "Requires authentication"})
                    return
                try:
                    pyjwt.decode(
                        auth[len("Bearer "):],
                        public_pem,
                        algorithms=["RS256"],
                        issuer=APP_ID,
                        options={"require": ["iat", "exp", "iss"]},
                    )
                except pyjwt.PyJWTError:
                    self._reply(401, {"message": "Bad credentials"})
                    return
                expires = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600)
                )
                self._reply(
                    201,
                    {
                        "token": "ghs_installation_token_1",
                        "expires_at": expires,
                        "permissions": {"contents": "write"},
                    },
                )
                return
            if self.path == "/login/oauth/access_token":
                form = dict(urllib.parse.parse_qsl(raw.decode("utf-8")))
                if form.get("client_id") != CLIENT_ID:
                    self._reply(401, {"message": "Bad client"})
                    return
                presented = form.get("refresh_token", "")
                if (
                    form.get("grant_type") != "refresh_token"
                    or presented in state["used_refresh_tokens"]
                    or presented != state["current_refresh_token"]
                ):
                    # GitHub's REAL error shape: HTTP 200 + error body.
                    self._reply(
                        200,
                        {
                            "error": "bad_refresh_token",
                            "error_description": "The refresh token is invalid.",
                        },
                    )
                    return
                # One-use rotation: consume, then mint a new pair.
                state["used_refresh_tokens"].add(presented)
                state["counter"] += 1
                state["current_refresh_token"] = f"ghr_refresh_{state['counter']}"
                self._reply(
                    200,
                    {
                        "access_token": f"ghu_access_{state['counter']}",
                        "expires_in": 28800,
                        "refresh_token": state["current_refresh_token"],
                        "refresh_token_expires_in": 15724800,
                        "token_type": "bearer",
                        "scope": "",
                    },
                )
                return
            self._reply(404, {"message": "Not Found"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()


def _deposit_app_key(pem: bytes):
    return deposit_credential(
        universe_id="u-gha", founder_id="founder-a", provider="github",
        destination="app:test-app", purpose="app_auth",
        kind=SecretKind.GITHUB_APP_PRIVATE_KEY, value=pem,
    )


def _deposit_user_bundle(refresh_token: str):
    bundle = encode_user_token_bundle(
        access_token="ghu_access_0",
        refresh_token=refresh_token,
        expires_at=time.time() + 600,
        refresh_token_expires_at=time.time() + 3600,
    )
    return deposit_credential(
        universe_id="u-gha", founder_id="founder-a", provider="github",
        destination="user:octocat", purpose="user_auth",
        kind=SecretKind.GITHUB_APP_USER_TOKEN, value=bundle,
    )


def test_installation_token_exchange(platform_vault_env, rsa_keypair, fake_github):
    private_pem, _public = rsa_keypair
    base_url, _state = fake_github
    _deposit_app_key(private_pem)
    binding = find_binding("u-gha", "github", "app_auth", "app:test-app")
    token = mint_installation_token(
        platform_backend(), binding, binding.scope,
        app_id=APP_ID, installation_id=INSTALLATION_ID, api_base=base_url,
    )
    assert token.token.reveal() == b"ghs_installation_token_1"
    assert token.expires_at > time.time() + 3000  # ~1h, parsed from ISO8601
    assert token.permissions == {"contents": "write"}
    # In-memory only + redacted.
    assert "ghs_installation_token_1" not in repr(token)


def test_installation_token_wrong_key_is_reauthorization(
    platform_vault_env, fake_github
):
    """A vaulted PEM the server does not trust -> 401 -> re-deposit required."""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_pem = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    base_url, _state = fake_github
    _deposit_app_key(wrong_pem)
    binding = find_binding("u-gha", "github", "app_auth", "app:test-app")
    with pytest.raises(CredentialUnavailable) as exc:
        mint_installation_token(
            platform_backend(), binding, binding.scope,
            app_id=APP_ID, installation_id=INSTALLATION_ID, api_base=base_url,
        )
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_user_token_refresh_rotates_through_the_vault(
    platform_vault_env, fake_github
):
    base_url, state = fake_github
    _deposit_user_bundle("ghr_refresh_0")
    binding = find_binding("u-gha", "github", "user_auth", "user:octocat")
    be = platform_backend()
    descriptor = refresh_user_token(
        be, binding, binding.scope,
        client_id=CLIENT_ID, holder="worker-1",
        token_url=f"{base_url}/login/oauth/access_token",
    )
    assert descriptor is not None
    assert descriptor.version == 2
    # The vault now holds the ROTATED pair; the old refresh token is consumed.
    with resolve_credential("u-gha", "github", "user_auth", "user:octocat") as lease:
        bundle = decode_user_token_bundle(lease.reveal())
    assert bundle["access_token"] == "ghu_access_1"
    assert bundle["refresh_token"] == "ghr_refresh_1"
    assert "ghr_refresh_0" in state["used_refresh_tokens"]
    # A second rotation redeems the NEW token exactly once more.
    descriptor2 = refresh_user_token(
        be, binding, binding.scope,
        client_id=CLIENT_ID, holder="worker-1",
        token_url=f"{base_url}/login/oauth/access_token",
    )
    assert descriptor2 is not None and descriptor2.version == 3


def test_consumed_refresh_token_forces_reauthorization(
    platform_vault_env, fake_github
):
    """The vault holds a refresh token the provider has already seen — the
    one-use semantics reject it and the caller must re-authorize. GitHub
    signals this as HTTP 200 + error body, so status alone must not pass."""
    base_url, state = fake_github
    state["used_refresh_tokens"].add("ghr_refresh_0")
    _deposit_user_bundle("ghr_refresh_0")
    binding = find_binding("u-gha", "github", "user_auth", "user:octocat")
    with pytest.raises(CredentialUnavailable) as exc:
        refresh_user_token(
            platform_backend(), binding, binding.scope,
            client_id=CLIENT_ID, holder="worker-1",
            token_url=f"{base_url}/login/oauth/access_token",
        )
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_lost_refresh_race_returns_none_without_provider_call(
    platform_vault_env, fake_github
):
    """A holder that lost consume-before-mint must NOT reach the provider —
    reaching it would burn the one-use token."""
    base_url, state = fake_github
    _deposit_user_bundle("ghr_refresh_0")
    binding = find_binding("u-gha", "github", "user_auth", "user:octocat")
    be = platform_backend()
    # A rival already claimed this version (consume-before-mint winner).
    ticket = be.begin_refresh(binding, binding.scope, "rival", at_version=1)
    assert ticket is not None
    requests_before = len(state["requests"])
    result = refresh_user_token(
        be, binding, binding.scope,
        client_id=CLIENT_ID, holder="worker-2",
        token_url=f"{base_url}/login/oauth/access_token",
    )
    assert result is None
    assert len(state["requests"]) == requests_before  # no provider call


def test_bad_client_is_operational_error(platform_vault_env, fake_github):
    base_url, _state = fake_github
    _deposit_user_bundle("ghr_refresh_0")
    binding = find_binding("u-gha", "github", "user_auth", "user:octocat")
    with pytest.raises(GitHubTokenExchangeError) as exc:
        refresh_user_token(
            platform_backend(), binding, binding.scope,
            client_id="wrong-client", holder="worker-1",
            token_url=f"{base_url}/login/oauth/access_token",
        )
    assert exc.value.status == 401
    # The error carries only status/error-code — never a token.
    assert "ghr_refresh_0" not in str(exc.value)


def test_non_loopback_http_token_url_is_refused(platform_vault_env):
    _deposit_user_bundle("ghr_refresh_0")
    binding = find_binding("u-gha", "github", "user_auth", "user:octocat")
    with pytest.raises(GitHubTokenExchangeError) as exc:
        refresh_user_token(
            platform_backend(), binding, binding.scope,
            client_id=CLIENT_ID, holder="worker-1",
            token_url="http://attacker.example/token",
        )
    assert exc.value.error_code == "insecure_token_url"
