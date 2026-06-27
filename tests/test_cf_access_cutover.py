"""Tests for scripts/cf_access_cutover.py.

Covers:
  (a) dry-run skips all POSTs/PUTs
  (b) idempotent reuse of existing service token / access app / policy by name/domain
  (c) correct payload shape for each mutating call
  (d) three_check probes canonical (expects 200+serverInfo) and internal (expects 401/403)

No network calls — CloudflareClient.request and urllib.request.urlopen are monkeypatched.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import cf_access_cutover as cut  # noqa: E402
from emergency_dns_flip import (  # noqa: E402
    CloudflareApiError,
    CloudflareClient,
    GlobalKeyClient,
    make_cloudflare_client,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACCT = "acct-abc123"
ZONE = "zone-xyz789"
TOKEN = "fake-api-token"
WORKER = "tinyassets-mcp-worker"

# Canned API objects
EXISTING_TOKEN = {
    "id": "tok-existing",
    "name": cut.SERVICE_TOKEN_NAME,
    # no client_id/client_secret — already-persisted token
}
NEW_TOKEN = {
    "id": "tok-new",
    "name": cut.SERVICE_TOKEN_NAME,
    "client_id": "cid.abc",
    "client_secret": "csecret-xyz",
}
EXISTING_APP = {
    "uid": "app-uuid-existing",
    "name": cut.APP_NAME,
    "domain": cut.APP_DOMAIN,
}
NEW_APP = {
    "uid": "app-uuid-new",
    "name": cut.APP_NAME,
    "domain": cut.APP_DOMAIN,
}
EXISTING_POLICY = {
    "id": "pol-existing",
    "name": cut.POLICY_NAME,
}
NEW_POLICY = {
    "id": "pol-new",
    "name": cut.POLICY_NAME,
}


def _make_client(responses: list[dict[str, Any]]) -> CloudflareClient:
    """Return a CloudflareClient whose .request() yields canned responses in order."""
    client = CloudflareClient.__new__(CloudflareClient)
    client.token = TOKEN
    client.base_url = "https://api.cloudflare.com/client/v4"
    it = iter(responses)
    client.request = MagicMock(side_effect=lambda *a, **kw: next(it))
    return client


def _zone_resp(account_id: str = ACCT) -> dict:
    return {"result": {"account": {"id": account_id}}}


# ---------------------------------------------------------------------------
# (a) Dry-run: no POSTs/PUTs
# ---------------------------------------------------------------------------


def test_dry_run_service_token_no_post():
    """Dry-run must not POST to service_tokens when none exist."""
    client = _make_client([
        {"result": []},  # GET service_tokens → empty
    ])
    result = cut._find_or_create_service_token(client, ACCT, apply=False)
    assert result == {"dry_run": True}
    # Only one call: the GET
    assert client.request.call_count == 1
    method, path = client.request.call_args_list[0][0][:2]
    assert method == "GET"
    assert "service_tokens" in path


def test_dry_run_app_no_post():
    """Dry-run must not POST to access/apps when none exist."""
    client = _make_client([
        {"result": []},  # GET access/apps → empty
    ])
    result = cut._find_or_create_app(client, ACCT, apply=False)
    assert result == {"dry_run": True}
    assert client.request.call_count == 1


def test_dry_run_policy_no_post():
    """Dry-run must not POST to policies when none exist."""
    client = _make_client([
        {"result": []},  # GET policies → empty
    ])
    result = cut._ensure_policy(client, ACCT, "app-uid", "tok-id", apply=False)
    assert result == {"dry_run": True}
    assert client.request.call_count == 1


def test_dry_run_worker_secret_no_put():
    """Dry-run must not PUT worker secrets."""
    client = _make_client([])
    cut._put_worker_secret(client, ACCT, WORKER, "CF_ACCESS_CLIENT_ID", "val", apply=False)
    assert client.request.call_count == 0


# ---------------------------------------------------------------------------
# (b) Idempotent reuse
# ---------------------------------------------------------------------------


def test_reuse_existing_service_token():
    """Returns existing token without POST when name matches."""
    client = _make_client([
        {"result": [EXISTING_TOKEN]},
    ])
    result = cut._find_or_create_service_token(client, ACCT, apply=True)
    assert result["id"] == "tok-existing"
    assert client.request.call_count == 1
    # Confirm no POST happened
    method = client.request.call_args_list[0][0][0]
    assert method == "GET"


def test_reuse_existing_app_by_domain():
    """Returns existing app without POST when domain matches."""
    client = _make_client([
        {"result": [EXISTING_APP]},
    ])
    result = cut._find_or_create_app(client, ACCT, apply=True)
    assert result["uid"] == "app-uuid-existing"
    assert client.request.call_count == 1
    method = client.request.call_args_list[0][0][0]
    assert method == "GET"


def test_reuse_existing_policy_by_name():
    """Returns existing policy without POST when name matches."""
    client = _make_client([
        {"result": [EXISTING_POLICY]},
    ])
    result = cut._ensure_policy(client, ACCT, "app-uid", "tok-id", apply=True)
    assert result["id"] == "pol-existing"
    assert client.request.call_count == 1


def test_no_reuse_when_different_domain():
    """App with different domain must not be reused — creates new."""
    other_app = {**EXISTING_APP, "domain": "other.example.com", "uid": "other-uid"}
    client = _make_client([
        {"result": [other_app]},           # GET apps → different domain
        {"result": NEW_APP},               # POST → new app
    ])
    result = cut._find_or_create_app(client, ACCT, apply=True)
    assert result["uid"] == "app-uuid-new"
    assert client.request.call_count == 2


# ---------------------------------------------------------------------------
# (c) Correct payload shape for each mutating call
# ---------------------------------------------------------------------------


def test_service_token_post_payload():
    client = _make_client([
        {"result": []},           # GET → none
        {"result": NEW_TOKEN},    # POST → created
    ])
    cut._find_or_create_service_token(client, ACCT, apply=True)
    post_call = client.request.call_args_list[1]
    method, path = post_call[0][:2]
    payload = post_call[1]["payload"]
    assert method == "POST"
    assert path == f"/accounts/{ACCT}/access/service_tokens"
    assert payload["name"] == cut.SERVICE_TOKEN_NAME
    assert "duration" in payload


def test_app_post_payload():
    client = _make_client([
        {"result": []},           # GET → none
        {"result": NEW_APP},      # POST → created
    ])
    cut._find_or_create_app(client, ACCT, apply=True)
    post_call = client.request.call_args_list[1]
    method, path = post_call[0][:2]
    payload = post_call[1]["payload"]
    assert method == "POST"
    assert path == f"/accounts/{ACCT}/access/apps"
    assert payload["domain"] == cut.APP_DOMAIN
    assert payload["type"] == "self_hosted"
    assert payload["name"] == cut.APP_NAME


def test_policy_post_payload():
    service_token_id = "tok-123"
    app_uuid = "app-uuid-abc"
    client = _make_client([
        {"result": []},              # GET policies → none
        {"result": NEW_POLICY},      # POST → created
    ])
    cut._ensure_policy(client, ACCT, app_uuid, service_token_id, apply=True)
    post_call = client.request.call_args_list[1]
    method, path = post_call[0][:2]
    payload = post_call[1]["payload"]
    assert method == "POST"
    assert path == f"/accounts/{ACCT}/access/apps/{app_uuid}/policies"
    assert payload["decision"] == "non_identity"
    assert payload["name"] == cut.POLICY_NAME
    # service_token token_id must be wired correctly
    include = payload["include"]
    assert len(include) == 1
    assert include[0]["service_token"]["token_id"] == service_token_id


def test_worker_secret_put_payload_client_id():
    client = _make_client([{"result": {}}])
    cut._put_worker_secret(client, ACCT, WORKER, "CF_ACCESS_CLIENT_ID", "cid-val", apply=True)
    call = client.request.call_args_list[0]
    method, path = call[0][:2]
    payload = call[1]["payload"]
    assert method == "PUT"
    assert path == f"/accounts/{ACCT}/workers/scripts/{WORKER}/secrets"
    assert payload["name"] == "CF_ACCESS_CLIENT_ID"
    assert payload["text"] == "cid-val"
    assert payload["type"] == "secret_text"


def test_worker_secret_put_payload_client_secret():
    client = _make_client([{"result": {}}])
    cut._put_worker_secret(client, ACCT, WORKER, "CF_ACCESS_CLIENT_SECRET", "sec-val", apply=True)
    call = client.request.call_args_list[0]
    payload = call[1]["payload"]
    assert payload["name"] == "CF_ACCESS_CLIENT_SECRET"
    assert payload["text"] == "sec-val"


# ---------------------------------------------------------------------------
# (d) three_check probes correct semantics
# ---------------------------------------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, status: int, body: bytes = b""):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def test_three_check_canonical_green(capsys):
    """Canonical URL returning 200 with 'serverInfo' in body → GREEN."""
    canonical_body = json.dumps({"result": {"serverInfo": {"name": "tinyassets"}}}).encode()

    canonical_resp = _FakeHTTPResponse(200, canonical_body)
    internal_error = urllib.error.HTTPError(
        url="https://mcp.tinyassets.io/mcp",
        code=401,
        msg="Unauthorized",
        hdrs={},  # type: ignore[arg-type]
        fp=None,
    )

    def fake_urlopen(req, timeout=None):
        if "tinyassets.io/mcp" in req.full_url and "mcp." not in req.full_url:
            return canonical_resp
        raise internal_error

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        cut.three_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "GREEN" in out
    assert "canonical" in out.lower() or "tinyassets.io/mcp" in out


def test_three_check_internal_401_is_ok(capsys):
    """Internal URL returning 401 → 'OK: gated'."""
    canonical_body = json.dumps({"result": {"serverInfo": {}}}).encode()
    canonical_resp = _FakeHTTPResponse(200, canonical_body)
    internal_error = urllib.error.HTTPError(
        url="https://mcp.tinyassets.io/mcp",
        code=401,
        msg="Unauthorized",
        hdrs={},  # type: ignore[arg-type]
        fp=None,
    )

    def fake_urlopen(req, timeout=None):
        if "mcp.tinyassets.io" in req.full_url:
            raise internal_error
        return canonical_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        cut.three_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "OK" in out
    assert "401" in out


def test_three_check_internal_403_is_ok(capsys):
    """Internal URL returning 403 → 'OK: gated'."""
    canonical_body = json.dumps({"result": {"serverInfo": {}}}).encode()
    canonical_resp = _FakeHTTPResponse(200, canonical_body)
    internal_error = urllib.error.HTTPError(
        url="https://mcp.tinyassets.io/mcp",
        code=403,
        msg="Forbidden",
        hdrs={},  # type: ignore[arg-type]
        fp=None,
    )

    def fake_urlopen(req, timeout=None):
        if "mcp.tinyassets.io" in req.full_url:
            raise internal_error
        return canonical_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        cut.three_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "OK" in out
    assert "403" in out


def test_three_check_internal_200_is_unexpected(capsys):
    """Internal URL returning 200 → 'UNEXPECTED: still reachable'."""
    canonical_body = json.dumps({"result": {"serverInfo": {}}}).encode()
    canonical_resp = _FakeHTTPResponse(200, canonical_body)
    internal_resp = _FakeHTTPResponse(200, b"")

    call_count = [0]

    def fake_urlopen(req, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return canonical_resp
        return internal_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        cut.three_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "UNEXPECTED" in out


def test_three_check_canonical_failure_reported(capsys):
    """Canonical URL network failure → FAILED reported."""
    def fake_urlopen(req, timeout=None):
        raise OSError("connection refused")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        cut.three_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "FAILED" in out


# ---------------------------------------------------------------------------
# Edge: CloudflareApiError propagates from mutating calls
# ---------------------------------------------------------------------------


def test_service_token_post_api_error_propagates():
    client = _make_client([
        {"result": []},  # GET → none
    ])
    client.request = MagicMock(side_effect=[
        {"result": []},
        CloudflareApiError("permission denied"),
    ])
    with pytest.raises(CloudflareApiError, match="permission denied"):
        cut._find_or_create_service_token(client, ACCT, apply=True)


# ---------------------------------------------------------------------------
# Auth-scheme unification tests
# ---------------------------------------------------------------------------


class TestMakeCloudflareClient:
    def test_bearer_token_returns_cloudflare_client(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-abc")
        monkeypatch.delenv("CLOUDFLARE_EMAIL", raising=False)
        monkeypatch.delenv("CLOUDFLARE_GLOBAL_KEY", raising=False)
        client = make_cloudflare_client()
        assert isinstance(client, CloudflareClient)
        assert not isinstance(client, GlobalKeyClient)
        assert client.token == "tok-abc"

    def test_global_key_returns_global_key_client(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_EMAIL", "admin@example.com")
        monkeypatch.setenv("CLOUDFLARE_GLOBAL_KEY", "global-key-xyz")
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        client = make_cloudflare_client()
        assert isinstance(client, GlobalKeyClient)
        assert client._email == "admin@example.com"
        assert client._key == "global-key-xyz"

    def test_global_key_wins_over_bearer_when_both_set(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-abc")
        monkeypatch.setenv("CLOUDFLARE_EMAIL", "admin@example.com")
        monkeypatch.setenv("CLOUDFLARE_GLOBAL_KEY", "global-key-xyz")
        client = make_cloudflare_client()
        assert isinstance(client, GlobalKeyClient)

    def test_no_credentials_raises(self, monkeypatch):
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        monkeypatch.delenv("CLOUDFLARE_EMAIL", raising=False)
        monkeypatch.delenv("CLOUDFLARE_GLOBAL_KEY", raising=False)
        with pytest.raises(CloudflareApiError, match="No Cloudflare credentials"):
            make_cloudflare_client()

    def test_explicit_token_arg_overrides_env(self, monkeypatch):
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        monkeypatch.delenv("CLOUDFLARE_EMAIL", raising=False)
        monkeypatch.delenv("CLOUDFLARE_GLOBAL_KEY", raising=False)
        client = make_cloudflare_client(token="explicit-tok")
        assert isinstance(client, CloudflareClient)
        assert client.token == "explicit-tok"

    def test_explicit_global_key_args_override_env(self, monkeypatch):
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        monkeypatch.delenv("CLOUDFLARE_EMAIL", raising=False)
        monkeypatch.delenv("CLOUDFLARE_GLOBAL_KEY", raising=False)
        client = make_cloudflare_client(email="e@x.com", global_key="gk-123")
        assert isinstance(client, GlobalKeyClient)


class TestGlobalKeyClientHeaders:
    def test_request_sends_x_auth_headers(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            resp = MagicMock()
            resp.read.return_value = json.dumps(
                {"success": True, "result": {}}
            ).encode()
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=resp)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        client = GlobalKeyClient("admin@test.com", "gk-secret")
        with patch("emergency_dns_flip.urllib.request.urlopen", side_effect=fake_urlopen):
            client.request("GET", "/zones/abc")

        assert captured["headers"].get("X-auth-email") == "admin@test.com"
        assert captured["headers"].get("X-auth-key") == "gk-secret"
        assert "Authorization" not in captured["headers"]

    def test_bearer_client_sends_authorization_header(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            resp = MagicMock()
            resp.read.return_value = json.dumps(
                {"success": True, "result": {}}
            ).encode()
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=resp)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        client = CloudflareClient("bearer-tok-123")
        with patch("emergency_dns_flip.urllib.request.urlopen", side_effect=fake_urlopen):
            client.request("GET", "/zones/abc")

        assert "Authorization" in captured["headers"]
        assert captured["headers"]["Authorization"] == "Bearer bearer-tok-123"
        assert "X-auth-email" not in captured["headers"]


class TestCutoverMakeClientPrintsAuthScheme:
    def test_bearer_prints_bearer(self, monkeypatch, capsys):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-xyz")
        monkeypatch.delenv("CLOUDFLARE_EMAIL", raising=False)
        monkeypatch.delenv("CLOUDFLARE_GLOBAL_KEY", raising=False)
        cut._make_client()
        out = capsys.readouterr().out
        assert "Bearer" in out

    def test_global_key_prints_global_key(self, monkeypatch, capsys):
        monkeypatch.setenv("CLOUDFLARE_EMAIL", "e@x.com")
        monkeypatch.setenv("CLOUDFLARE_GLOBAL_KEY", "gk-abc")
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        cut._make_client()
        out = capsys.readouterr().out
        assert "Global API Key" in out
