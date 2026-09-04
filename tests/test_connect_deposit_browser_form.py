"""BYO-LLM deposit browser form (byo-llm-deposit-browser-form).

Requirement source:
``openspec/changes/byo-llm-deposit-browser-form/specs/byo-llm-deposit-browser-form/spec.md``.

Covers: the narrow/ordered auth exemption for /mcp/connect(/*), cookieless signed
state+session tokens (tamper/expiry/CSRF), the owner-only browser deposit reusing
the landed connect_llm handler (round-trip + non-owner zero-mutation), and secret
hygiene (no token in response/log; HMAC key vault-first, fail-closed).
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import tinyassets.connect_deposit as cd
from tinyassets.auth.middleware import (
    _auth_challenge_path,
    _is_connect_deposit_path,
    auth_middleware,
    set_provider,
)
from tinyassets.auth.provider import DevAuthProvider

_SECRET = b"unit-test-signing-secret-many-bytes-of-material-xx"  # >= 32 bytes
_TEST_CONFIG = cd._Config(
    secret=_SECRET,
    client_id="client_test",
    client_secret="secret_test",
    issuer="https://issuer.example",
    resource="https://tinyassets.io/mcp",
)


@pytest.fixture(autouse=True)
def _reset_auth() -> Any:
    set_provider(DevAuthProvider())
    auth_middleware("dev")
    yield
    set_provider(DevAuthProvider())
    auth_middleware("dev")


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # The handlers re-check the enable flag per request (runtime kill switch), so
    # a working client needs the flow enabled.
    monkeypatch.setenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", "1")
    monkeypatch.setattr(cd, "_load_config", lambda: _TEST_CONFIG)
    app = Starlette(
        routes=[
            Route("/mcp/connect/login", cd.connect_login, methods=["GET"]),
            Route("/mcp/connect/callback", cd.connect_callback, methods=["GET"]),
            Route("/mcp/connect", cd.connect_root, methods=["GET", "POST"]),
        ]
    )
    return TestClient(app)


def _make_universe(base: Path, uid: str, *, admin: str = "") -> Path:
    from tinyassets.daemon_server import grant_universe_access

    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    if admin:
        grant_universe_access(
            base, universe_id=uid, actor_id=admin, permission="admin", granted_by=admin
        )
    return udir


def _mint_session(sub: str, csrf: str, *, ttl: int = 1800) -> str:
    now = int(time.time())
    return cd._sign_token(
        {"sub": sub, "csrf": csrf, "iat": now, "exp": now + ttl, "purpose": cd._PURPOSE_SESSION},
        _SECRET,
    )


def _post(client: TestClient, **fields: str) -> Any:
    return client.post("/mcp/connect", data=fields, follow_redirects=False)


# --------------------------------------------------------------------------- #
# Narrow, ordered auth exemption.
# --------------------------------------------------------------------------- #


def test_auth_exemption_is_scoped_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", "1")
    # Exempt (not challenged): exactly /mcp/connect and /mcp/connect/*.
    assert _auth_challenge_path("/mcp/connect") is False
    assert _auth_challenge_path("/mcp/connect/login") is False
    assert _auth_challenge_path("/mcp/connect/callback") is False
    # Still challenged: /mcp and any other /mcp/* — the exemption opens nothing else.
    assert _auth_challenge_path("/mcp") is True
    assert _auth_challenge_path("/mcp/") is True
    assert _auth_challenge_path("/mcp/tools") is True
    # Sibling paths that merely share the prefix are NOT exempt.
    assert _auth_challenge_path("/mcp/connectxyz") is True
    assert _auth_challenge_path("/mcp/connect-evil") is True


def test_exemption_is_dark_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", raising=False)
    # Off by default: the connect routes are still challenged like any /mcp/* path.
    assert _auth_challenge_path("/mcp/connect/login") is True
    assert _auth_challenge_path("/mcp/connect") is True


def test_exemption_rejects_traversal_and_case_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FIX 2: the exemption is case-sensitive and traversal-safe — it can never
    cover a path that normalizes to a non-connect target."""
    monkeypatch.setenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", "1")
    # Exactly the connect routes are exempt.
    assert _is_connect_deposit_path("/mcp/connect") is True
    assert _is_connect_deposit_path("/mcp/connect/login") is True
    # Traversal / empty-segment / case / sibling variants are NOT exempt.
    for bad in (
        "/mcp/connect/../tools",
        "/mcp/connect/../../mcp/tools",
        "/mcp//connect",
        "/mcp/connect//../tools",
        "/MCP/connect",
        "/mcp/Connect",
        "/mcp/connectxyz",
    ):
        assert _is_connect_deposit_path(bad) is False, bad
    # A traversal path that is still under /mcp/ stays CHALLENGED (not opened).
    assert _auth_challenge_path("/mcp/connect/../tools") is True
    assert _auth_challenge_path("/mcp//connect") is True


def test_runtime_kill_switch_503_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """FIX 3: toggling the flag off on a live process stops the handlers (503),
    not just future registrations."""
    monkeypatch.setattr(cd, "_load_config", lambda: _TEST_CONFIG)
    app = Starlette(
        routes=[Route("/mcp/connect/login", cd.connect_login, methods=["GET"])]
    )
    c = TestClient(app)

    monkeypatch.setenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", "1")
    assert c.get("/mcp/connect/login", follow_redirects=False).status_code == 302

    monkeypatch.delenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", raising=False)
    assert c.get("/mcp/connect/login", follow_redirects=False).status_code == 503


def test_registration_is_dark_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", raising=False)
    monkeypatch.setattr(cd, "_routes_registered", False)
    registered: list[str] = []

    class _FakeMCP:
        def custom_route(self, path: str, methods: list[str]):  # type: ignore[no-untyped-def]
            def _decorator(fn):  # type: ignore[no-untyped-def]
                registered.append(path)
                return fn

            return _decorator

    cd.register_connect_routes(_FakeMCP())
    assert registered == []  # nothing registered while dark

    monkeypatch.setenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", "1")
    monkeypatch.setattr(cd, "_routes_registered", False)
    cd.register_connect_routes(_FakeMCP())
    assert registered == ["/mcp/connect/login", "/mcp/connect/callback", "/mcp/connect"]


# --------------------------------------------------------------------------- #
# Cookieless signed tokens.
# --------------------------------------------------------------------------- #


def test_login_redirects_with_signed_state(client: TestClient) -> None:
    resp = client.get("/mcp/connect/login", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://issuer.example/oauth2/authorize?")
    assert "resource=https%3A%2F%2Ftinyassets.io%2Fmcp" in location
    # The state param is a valid signed state token.
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(location).query)["state"][0]
    assert cd._unsign_token(state, _SECRET, purpose=cd._PURPOSE_STATE) is not None
    # A session-purpose check must NOT accept a state token (slot separation).
    assert cd._unsign_token(state, _SECRET, purpose=cd._PURPOSE_SESSION) is None


def test_callback_rejects_tampered_and_expired_state(client: TestClient) -> None:
    # Tampered/garbage state → 400, no code exchange.
    r1 = client.get("/mcp/connect/callback?code=abc&state=not-a-valid-token")
    assert r1.status_code == 400
    # Expired state (exp in the past) with a valid signature → still rejected.
    now = int(time.time())
    expired = cd._sign_token(
        {"nonce": "x", "iat": now - 10_000, "exp": now - 1, "purpose": cd._PURPOSE_STATE},
        _SECRET,
    )
    r2 = client.get(f"/mcp/connect/callback?code=abc&state={expired}")
    assert r2.status_code == 400
    # Missing code → rejected even with a valid state.
    valid_state = cd._sign_token(
        {"nonce": "y", "iat": now, "exp": now + 900, "purpose": cd._PURPOSE_STATE}, _SECRET
    )
    r3 = client.get(f"/mcp/connect/callback?state={valid_state}")
    assert r3.status_code == 400


def test_signed_token_tamper_is_rejected() -> None:
    now = int(time.time())
    tok = cd._sign_token({"sub": "u", "exp": now + 100, "purpose": cd._PURPOSE_SESSION}, _SECRET)
    body, _, sig = tok.partition(".")
    # Flip the signature → rejected.
    assert cd._unsign_token(f"{body}.{sig[:-2]}xx", _SECRET, purpose=cd._PURPOSE_SESSION) is None


def test_signature_is_not_malleable() -> None:
    """FIX 1: a NON-canonical signature that base64-decodes to the SAME bytes must
    be rejected. The old decode-then-byte-compare accepted it (token malleable);
    the canonical base64url string compare rejects it.
    """
    now = int(time.time())
    tok = cd._sign_token({"sub": "u", "exp": now + 100, "purpose": cd._PURPOSE_SESSION}, _SECRET)
    body, _, sig = tok.partition(".")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    # The final char of a 32-byte digest carries 4 significant + 2 dropped bits;
    # the canonical encoder zeroes the dropped bits. Flip a dropped bit → a
    # DIFFERENT char that decodes to identical bytes.
    idx = alphabet.index(sig[-1])
    alt = alphabet[(idx & ~0b11) | ((idx & 0b11) ^ 0b01)]
    malleable = f"{body}.{sig[:-1]}{alt}"
    assert malleable != tok
    # Same decoded signature bytes — this is exactly what the byte-compare accepted.
    assert cd._b64url_decode(sig) == cd._b64url_decode(sig[:-1] + alt)
    # But the canonical-string compare rejects the altered token.
    assert cd._unsign_token(malleable, _SECRET, purpose=cd._PURPOSE_SESSION) is None
    # Wrong key → rejected.
    other_key = b"another-secret-of-many-bytes-length-xx"
    assert cd._unsign_token(tok, other_key, purpose=cd._PURPOSE_SESSION) is None
    # Float exp (NaN-forge vector) → rejected.
    bad = cd._sign_token({"sub": "u", "exp": 9e99, "purpose": cd._PURPOSE_SESSION}, _SECRET)
    assert cd._unsign_token(bad, _SECRET, purpose=cd._PURPOSE_SESSION) is None


# --------------------------------------------------------------------------- #
# POST session/CSRF gates — deposit nothing on refusal.
# --------------------------------------------------------------------------- #


def test_post_rejects_missing_or_tampered_session(base: Path, client: TestClient) -> None:
    from tinyassets.credential_vault import credential_vault_path

    _make_universe(base, "u-b", admin="user_owner")
    tok = "sk-ant-oat01-x"
    # No session field.
    r1 = _post(client, service="claude", token=tok, universe="u-b", csrf="c")
    assert r1.status_code == 403
    # Tampered session.
    r2 = _post(client, session="garbage.sig", csrf="c", service="claude", token=tok, universe="u-b")
    assert r2.status_code == 403
    # Expired session.
    expired = _mint_session("user_owner", "c", ttl=-5)
    r3 = _post(client, session=expired, csrf="c", service="claude", token=tok, universe="u-b")
    assert r3.status_code == 403
    assert not credential_vault_path(base / "u-b").exists()


def test_post_rejects_csrf_mismatch(base: Path, client: TestClient) -> None:
    from tinyassets.credential_vault import credential_vault_path

    _make_universe(base, "u-csrf", admin="user_owner")
    session = _mint_session("user_owner", "the-real-csrf")
    r = _post(
        client,
        session=session,
        csrf="a-different-csrf",
        service="claude",
        token="sk-ant-oat01-x",
        universe="u-csrf",
    )
    assert r.status_code == 403
    assert not credential_vault_path(base / "u-csrf").exists()


# --------------------------------------------------------------------------- #
# Owner deposit round-trips through the reused handler; non-owner refused.
# --------------------------------------------------------------------------- #


def test_owner_browser_deposit_round_trips(base: Path, client: TestClient) -> None:
    from tinyassets.credential_vault import resolve_claude_oauth_token

    _make_universe(base, "u-own", admin="user_founder")
    csrf = "csrf-nonce"
    session = _mint_session("user_founder", csrf)
    token = "sk-ant-oat01-BROWSER-DEPOSIT"

    r = _post(
        client, session=session, csrf=csrf, service="claude", token=token, universe="u-own"
    )

    assert r.status_code == 200
    assert "Subscription connected" in r.text
    # The token never appears in the rendered page.
    assert token not in r.text
    # It round-trips to the same vault the chatbot path writes.
    assert resolve_claude_oauth_token(base / "u-own") == token


def test_non_owner_browser_deposit_refused_zero_mutation(base: Path, client: TestClient) -> None:
    from tinyassets.credential_vault import credential_vault_path

    # The universe is owned by someone else; the signed-in browser subject is not
    # an admin of it.
    _make_universe(base, "u-victim", admin="user_owner")
    session = _mint_session("user_stranger", "c")
    r = _post(
        client,
        session=session,
        csrf="c",
        service="claude",
        token="sk-ant-oat01-STRANGER",
        universe="u-victim",
    )
    assert r.status_code == 400
    assert "No access to that universe" in r.text
    assert not credential_vault_path(base / "u-victim").exists()


def test_claude_token_shape_precheck_blocks_wrong_value(base: Path, client: TestClient) -> None:
    from tinyassets.credential_vault import credential_vault_path

    _make_universe(base, "u-shape", admin="user_founder")
    session = _mint_session("user_founder", "c")
    r = _post(
        client,
        session=session,
        csrf="c",
        service="claude",
        token="not-a-real-token",  # missing sk-ant- prefix
        universe="u-shape",
    )
    assert r.status_code == 400
    assert not credential_vault_path(base / "u-shape").exists()


# --------------------------------------------------------------------------- #
# Secret hygiene.
# --------------------------------------------------------------------------- #


def test_token_absent_from_logs_on_success(
    base: Path, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    _make_universe(base, "u-log", admin="user_founder")
    session = _mint_session("user_founder", "c")
    token = "sk-ant-oat01-SECRET-NEVER-LOGGED"
    with caplog.at_level("DEBUG"):
        r = _post(
            client, session=session, csrf="c", service="claude", token=token, universe="u-log"
        )
    assert r.status_code == 200
    assert token not in caplog.text
    assert base64.b64encode(token.encode()).decode() not in caplog.text


def test_config_fail_closed_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    # No connect env → fail closed (None), never a default/empty secret.
    for var in (
        "TINYASSETS_CONNECT_SESSION_SECRET",
        "TINYASSETS_CONNECT_CLIENT_ID",
        "TINYASSETS_CONNECT_CLIENT_SECRET",
        "WORKOS_AUTHKIT_DOMAIN",
        "WORKOS_MCP_RESOURCE",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TINYASSETS_CONNECT_CONFIG_DIR", "/nonexistent-connect-config-dir")
    assert cd._load_config() is None
    # A weak signing secret is rejected by the strength floor.
    assert cd._secret_is_strong("short") is False
    assert cd._secret_is_strong("x" * cd._MIN_SECRET_BYTES) is True


def test_unconfigured_routes_return_503(monkeypatch: pytest.MonkeyPatch) -> None:
    # Enabled but with no config loaded → every handler fails closed with 503.
    monkeypatch.setenv("TINYASSETS_CONNECT_DEPOSIT_ENABLED", "1")
    monkeypatch.setattr(cd, "_load_config", lambda: None)
    app = Starlette(
        routes=[
            Route("/mcp/connect/login", cd.connect_login, methods=["GET"]),
            Route("/mcp/connect", cd.connect_root, methods=["GET", "POST"]),
        ]
    )
    c = TestClient(app)
    assert c.get("/mcp/connect/login", follow_redirects=False).status_code == 503
    assert c.post("/mcp/connect", data={}).status_code == 503
