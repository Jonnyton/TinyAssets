"""Tests for scripts/cf_access_rollback.py.

Covers:
  (a) dry-run skips all DELETEs
  (b) no-op when target not found (app missing, token missing)
  (c) correct DELETE paths for app and service token
  (d) --rotate-token: also deletes service token
  (e) CloudflareApiError propagates
  (f) rollback_check: canonical green + internal ungated (200) = GREEN; still-gated = UNEXPECTED
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import cf_access_rollback as rb  # noqa: E402
from emergency_dns_flip import CloudflareApiError, CloudflareClient  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACCT = "acct-abc123"
ZONE = "zone-xyz789"
TOKEN = "fake-api-token"

EXISTING_APP = {
    "uid": "app-uuid-existing",
    "name": "tinyassets-mcp-worker-gate",
    "domain": rb.APP_DOMAIN,
}
OTHER_APP = {
    "uid": "other-uid",
    "name": "something-else",
    "domain": "other.example.com",
}
EXISTING_TOKEN = {
    "id": "tok-existing",
    "name": rb.SERVICE_TOKEN_NAME,
}
OTHER_TOKEN = {
    "id": "other-tok",
    "name": "unrelated-token",
}


def _make_client(responses: list[dict[str, Any]]) -> CloudflareClient:
    client = CloudflareClient.__new__(CloudflareClient)
    client.token = TOKEN
    client.base_url = "https://api.cloudflare.com/client/v4"
    it = iter(responses)
    client.request = MagicMock(side_effect=lambda *a, **kw: next(it))
    return client


# ---------------------------------------------------------------------------
# (a) Dry-run: no DELETEs issued
# ---------------------------------------------------------------------------


def test_dry_run_app_no_delete():
    """Dry-run must not DELETE the access app."""
    client = _make_client([{"result": [EXISTING_APP]}])
    result = rb._delete_access_app(client, ACCT, apply=False)
    assert result is True
    assert client.request.call_count == 1
    method = client.request.call_args_list[0][0][0]
    assert method == "GET"


def test_dry_run_token_no_delete():
    """Dry-run must not DELETE the service token."""
    client = _make_client([{"result": [EXISTING_TOKEN]}])
    result = rb._delete_service_token(client, ACCT, apply=False)
    assert result is True
    assert client.request.call_count == 1
    method = client.request.call_args_list[0][0][0]
    assert method == "GET"


# ---------------------------------------------------------------------------
# (b) No-op when target not found
# ---------------------------------------------------------------------------


def test_app_not_found_returns_false():
    """Returns False and issues no DELETE when no matching domain exists."""
    client = _make_client([{"result": [OTHER_APP]}])
    result = rb._delete_access_app(client, ACCT, apply=True)
    assert result is False
    assert client.request.call_count == 1
    # No DELETE call
    for call in client.request.call_args_list:
        assert call[0][0] != "DELETE"


def test_app_empty_list_returns_false():
    """Returns False when app list is empty."""
    client = _make_client([{"result": []}])
    result = rb._delete_access_app(client, ACCT, apply=True)
    assert result is False


def test_token_not_found_returns_false():
    """Returns False and issues no DELETE when no matching token name exists."""
    client = _make_client([{"result": [OTHER_TOKEN]}])
    result = rb._delete_service_token(client, ACCT, apply=True)
    assert result is False
    assert client.request.call_count == 1
    for call in client.request.call_args_list:
        assert call[0][0] != "DELETE"


def test_token_empty_list_returns_false():
    """Returns False when token list is empty."""
    client = _make_client([{"result": []}])
    result = rb._delete_service_token(client, ACCT, apply=True)
    assert result is False


# ---------------------------------------------------------------------------
# (c) Correct DELETE paths
# ---------------------------------------------------------------------------


def test_app_delete_path():
    """DELETE is called with the correct app UUID path."""
    client = _make_client([
        {"result": [EXISTING_APP]},   # GET apps
        {"result": {"id": "app-uuid-existing"}},  # DELETE response
    ])
    result = rb._delete_access_app(client, ACCT, apply=True)
    assert result is True
    assert client.request.call_count == 2
    delete_call = client.request.call_args_list[1]
    method, path = delete_call[0][:2]
    assert method == "DELETE"
    assert f"/accounts/{ACCT}/access/apps/{EXISTING_APP['uid']}" == path


def test_token_delete_path():
    """DELETE is called with the correct token ID path."""
    client = _make_client([
        {"result": [EXISTING_TOKEN]},  # GET tokens
        {"result": {"id": "tok-existing"}},  # DELETE response
    ])
    result = rb._delete_service_token(client, ACCT, apply=True)
    assert result is True
    assert client.request.call_count == 2
    delete_call = client.request.call_args_list[1]
    method, path = delete_call[0][:2]
    assert method == "DELETE"
    assert f"/accounts/{ACCT}/access/service_tokens/{EXISTING_TOKEN['id']}" == path


def test_app_delete_selects_matching_domain_only():
    """When multiple apps exist, only the one matching APP_DOMAIN is deleted."""
    client = _make_client([
        {"result": [OTHER_APP, EXISTING_APP]},  # GET apps — OTHER comes first
        {"result": {}},  # DELETE
    ])
    rb._delete_access_app(client, ACCT, apply=True)
    delete_call = client.request.call_args_list[1]
    path = delete_call[0][1]
    assert EXISTING_APP["uid"] in path
    assert OTHER_APP["uid"] not in path


# ---------------------------------------------------------------------------
# (d) --rotate-token also deletes service token
# ---------------------------------------------------------------------------


def test_rotate_token_deletes_both(monkeypatch):
    """main() with --apply --rotate-token issues DELETE for app and token."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", ZONE)

    responses = [
        {"result": {"account": {"id": ACCT}}},   # resolve account
        {"result": [EXISTING_APP]},               # GET apps
        {"result": {}},                           # DELETE app
        {"result": [EXISTING_TOKEN]},             # GET tokens
        {"result": {}},                           # DELETE token
    ]
    it = iter(responses)
    mock_client = MagicMock()
    mock_client.request = MagicMock(side_effect=lambda *a, **kw: next(it))

    with patch("cf_access_rollback.make_cloudflare_client", return_value=mock_client):
        _call_main(rb, ["--apply", "--rotate-token"])

    # Verify DELETE was called for both app and token
    calls = mock_client.request.call_args_list
    delete_calls = [c for c in calls if c[0][0] == "DELETE"]
    assert len(delete_calls) == 2


def _call_main(module, argv: list[str]) -> int:
    """Invoke module.main() with patched sys.argv."""
    import sys as _sys
    old = _sys.argv[:]
    _sys.argv = ["cf_access_rollback.py"] + argv
    try:
        return module.main()
    finally:
        _sys.argv = old


def test_no_rotate_token_skips_token_delete(monkeypatch):
    """main() with --apply but no --rotate-token must NOT issue service token DELETE."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", ZONE)

    responses = [
        {"result": {"account": {"id": ACCT}}},   # resolve account
        {"result": [EXISTING_APP]},               # GET apps
        {"result": {}},                           # DELETE app
    ]
    it = iter(responses)
    mock_client = MagicMock()
    mock_client.request = MagicMock(side_effect=lambda *a, **kw: next(it))

    with patch("cf_access_rollback.make_cloudflare_client", return_value=mock_client):
        rc = _call_main(rb, ["--apply"])

    assert rc == 0
    calls = mock_client.request.call_args_list
    delete_calls = [c for c in calls if c[0][0] == "DELETE"]
    assert len(delete_calls) == 1
    assert "access/apps" in delete_calls[0][0][1]


# ---------------------------------------------------------------------------
# (e) CloudflareApiError propagates
# ---------------------------------------------------------------------------


def test_app_delete_api_error_propagates():
    client = _make_client([
        {"result": [EXISTING_APP]},
    ])
    client.request = MagicMock(side_effect=[
        {"result": [EXISTING_APP]},
        CloudflareApiError("permission denied"),
    ])
    with pytest.raises(CloudflareApiError, match="permission denied"):
        rb._delete_access_app(client, ACCT, apply=True)


def test_main_returns_1_on_api_error(monkeypatch):
    """main() returns exit code 1 when CloudflareApiError raised."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", ZONE)

    mock_client = MagicMock()
    mock_client.request = MagicMock(side_effect=[
        {"result": {"account": {"id": ACCT}}},
        CloudflareApiError("403 Forbidden"),
    ])

    with patch("cf_access_rollback.make_cloudflare_client", return_value=mock_client):
        rc = _call_main(rb, ["--apply"])

    assert rc == 1


def test_main_returns_2_missing_env():
    """main() returns exit code 2 when env vars are absent."""
    import os
    old_token = os.environ.pop("CLOUDFLARE_API_TOKEN", None)
    old_zone = os.environ.pop("CLOUDFLARE_ZONE_ID", None)
    try:
        rc = _call_main(rb, [])
        assert rc == 2
    finally:
        if old_token is not None:
            os.environ["CLOUDFLARE_API_TOKEN"] = old_token
        if old_zone is not None:
            os.environ["CLOUDFLARE_ZONE_ID"] = old_zone


# ---------------------------------------------------------------------------
# (f) rollback_check — inverted semantics vs cutover three_check
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


def test_rollback_check_canonical_green_internal_ungated(capsys):
    """Canonical 200+serverInfo = GREEN; internal 200 = GREEN: ungated."""
    canonical_body = json.dumps({"result": {"serverInfo": {"name": "workflow"}}}).encode()
    canonical_resp = _FakeHTTPResponse(200, canonical_body)
    internal_resp = _FakeHTTPResponse(200, b"")

    call_count = [0]

    def fake_urlopen(req, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            return canonical_resp
        return internal_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rb.rollback_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "GREEN" in out
    assert "ungated" in out


def test_rollback_check_internal_still_gated_401(capsys):
    """Internal 401 after rollback → UNEXPECTED: still gated."""
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
        rb.rollback_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "UNEXPECTED" in out
    assert "401" in out


def test_rollback_check_internal_still_gated_403(capsys):
    """Internal 403 after rollback → UNEXPECTED: still gated."""
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
        rb.rollback_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "UNEXPECTED" in out
    assert "403" in out


def test_rollback_check_canonical_failure(capsys):
    """Canonical failure is reported."""
    def fake_urlopen(req, timeout=None):
        raise OSError("connection refused")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rb.rollback_check("https://tinyassets.io/mcp", "https://mcp.tinyassets.io/mcp")

    out = capsys.readouterr().out
    assert "FAILED" in out
