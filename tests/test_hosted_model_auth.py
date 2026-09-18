"""Hosted acquisition is owner/home-bound, one-shot, bounded and secret-blind."""

import asyncio
import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from tinyassets.onboarding import hosted_model_auth as auth

VERIFIER = "a" * 64
CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(VERIFIER.encode()).digest(),
).rstrip(b"=").decode()


@pytest.fixture(autouse=True)
def clean_flows():
    with auth._lock:
        auth._pending.clear()
    yield
    with auth._lock:
        auth._pending.clear()


def begin(**kwargs):
    return auth.begin_flow(**{
        "owner": "user-a", "universe_id": "home-a",
        "preset_id": "openrouter_user_models_v1", "challenge": CHALLENGE,
        "public_resource": "https://tinyassets.io/mcp", **kwargs,
    })


def take(handle, **kwargs):
    return auth.take_flow(**{
        "handle": handle, "owner": "user-a", "universe_id": "home-a",
        "verifier": VERIFIER, **kwargs,
    })


def test_authorize_url_uses_fixed_origin_and_distinct_callback():
    result = begin()
    url = urlsplit(result["authorize_url"])
    assert (url.scheme, url.netloc, url.path) == ("https", "openrouter.ai", "/auth")
    query = parse_qs(url.query)
    callback = urlsplit(query["callback_url"][0])
    assert callback.netloc == "tinyassets.io"
    assert auth.is_callback_path(callback.path)
    assert callback.path.endswith(result["flow"])
    assert query["code_challenge"] == [CHALLENGE]
    assert query["code_challenge_method"] == ["S256"]
    assert VERIFIER not in json.dumps(result)
    assert set(result) == {"flow", "authorize_url", "display_name", "expires_in"}


@pytest.mark.parametrize("path", ["/mcp/app", "/mcp/app/model-callback/",
    "/mcp/app/model-callback/" + "x" * 42,
    "/mcp/app/model-callback/" + "x" * 43 + "/exchange",
    "/mcp/app/model-callback/" + "x" * 43 + "\n"])
def test_callback_exemption_is_narrow(path):
    assert not auth.is_callback_path(path)


@pytest.mark.parametrize("resource", ["http://tinyassets.io/mcp", "https://u:p@tinyassets.io/mcp",
    "https://tinyassets.io/mcp?next=evil", "https://tinyassets.io/#evil", "https://tinyassets.io:bad/mcp"])
def test_rejects_unsafe_canonical_callback(resource):
    with pytest.raises(auth.HostedAuthError, match="public_callback_unavailable"):
        begin(public_resource=resource)
    assert not auth._pending


@pytest.mark.parametrize("changed,error", [
    ({"owner": "user-b"}, "unknown_model_connection"),
    ({"universe_id": "home-b"}, "current_home_changed"),
    ({"verifier": "b" * 64}, "invalid_pkce_verifier"),
    ({"verifier": "é" * 64}, "invalid_pkce_verifier"),
])
def test_foreign_or_mismatched_attempt_does_not_consume(changed, error):
    handle = begin()["flow"]
    with pytest.raises(auth.HostedAuthError, match=error):
        take(handle, **changed)
    assert take(handle).owner == "user-a"
    with pytest.raises(auth.HostedAuthError, match="unknown_model_connection"):
        take(handle)


def test_expired_flow_cannot_exchange(monkeypatch):
    handle = begin()["flow"]
    monkeypatch.setattr(auth.time, "monotonic", lambda: auth._pending[handle].expires_at)
    with pytest.raises(auth.HostedAuthError, match="unknown_model_connection"):
        take(handle)


def test_changed_preset_cannot_exchange(monkeypatch):
    handle = begin()["flow"]
    preset = auth.load_preset("openrouter_user_models_v1")
    monkeypatch.setattr(auth, "load_preset", lambda _: replace(preset, digest="changed"))
    with pytest.raises(auth.HostedAuthError, match="preset_changed"):
        take(handle)


def test_one_terminal_attempt_under_concurrent_callbacks():
    handle = begin()["flow"]
    def attempt(_):
        try:
            take(handle)
            return True
        except auth.HostedAuthError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 1


def test_pending_bounds_do_not_evict_another_owner(monkeypatch):
    monkeypatch.setattr(auth, "MAX_PER_OWNER", 1)
    first = begin()["flow"]
    with pytest.raises(auth.HostedAuthError, match="too_many_pending"):
        begin()
    other = begin(owner="user-b", universe_id="home-b")["flow"]
    assert take(first)
    assert take(other, owner="user-b", universe_id="home-b")


def test_global_pending_bound_and_expiry_release_capacity(monkeypatch):
    monkeypatch.setattr(auth, "MAX_PENDING", 1)
    first = begin()["flow"]
    with pytest.raises(auth.HostedAuthError, match="too_many_pending"):
        begin(owner="user-b", universe_id="home-b")
    expiry = auth._pending[first].expires_at
    monkeypatch.setattr(auth.time, "monotonic", lambda: expiry)
    assert begin(owner="user-b", universe_id="home-b")
    assert first not in auth._pending


def test_acquisition_transport_is_not_a_provider_name_switch(monkeypatch):
    preset = replace(auth.load_preset("openrouter_user_models_v1"), id="different_source_v1",
                     display_name="Different source", authorize_url="https://source.example/auth",
                     exchange_url="https://source.example/keys")
    monkeypatch.setattr(auth, "load_preset", lambda _: preset)
    result = begin(preset_id=preset.id)
    assert result["authorize_url"].startswith("https://source.example/auth?")
    flow = take(result["flow"])
    def handler(request):
        assert str(request.url) == preset.exchange_url
        return httpx.Response(200, json={"key": "other-source-key"})
    assert asyncio.run(auth.exchange_key(flow=flow, code="code", verifier=VERIFIER,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )) == "other-source-key"


def exchange(handler, **kwargs):
    flow = take(begin()["flow"])
    return asyncio.run(auth.exchange_key(
        flow=flow, code="test-code", verifier=VERIFIER,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **kwargs,
    ))


def test_exchange_sends_exact_protocol_and_returns_server_only_key():
    seen = []
    def handler(request):
        seen.append(request)
        assert str(request.url) == "https://openrouter.ai/api/v1/auth/keys"
        assert request.method == "POST"
        assert json.loads(request.content) == {
            "code": "test-code", "code_verifier": VERIFIER, "code_challenge_method": "S256",
        }
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"key": "test-secret"})
    assert exchange(handler) == "test-secret"
    assert len(seen) == 1
    assert not auth._pending


@pytest.mark.parametrize("status", [301, 302, 307, 400, 403, 429, 500])
def test_no_redirect_retry_or_upstream_error_leak(status):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, headers={"Location": "https://other.invalid"},
                              text="secret error body")
    with pytest.raises(auth.HostedAuthError) as error:
        exchange(handler)
    assert len(seen) == 1
    assert str(error.value) == "model_authorization_not_completed"
    assert not auth._pending


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"key":null}',
    b'{"key":""}', b'{"key":"line\\nbreak"}', b'{"key":42}',
    json.dumps({"key": "x" * 4097}).encode(), b"x" * (auth.MAX_RESPONSE_BYTES + 1),
    b"[" * 2000 + b"0" + b"]" * 2000])
def test_malformed_and_oversized_response_is_secret_blind(body):
    with pytest.raises(auth.HostedAuthError, match="model_authorization_response_invalid"):
        exchange(lambda request: httpx.Response(200, content=body))


def test_network_failure_is_uncertain_not_retried():
    seen = []
    def handler(request):
        seen.append(request)
        raise httpx.ReadError("upstream secret", request=request)
    with pytest.raises(auth.HostedAuthError) as error:
        exchange(handler)
    assert str(error.value) == "model_authorization_outcome_unknown"
    assert error.value.__suppress_context__
    assert len(seen) == 1


def test_total_exchange_deadline(monkeypatch):
    monkeypatch.setattr(auth, "EXCHANGE_TIMEOUT", .01)
    async def handler(request):
        await asyncio.sleep(.1)
        return httpx.Response(200, json={"key": "too-late"})
    with pytest.raises(auth.HostedAuthError, match="outcome_unknown"):
        exchange(handler)
