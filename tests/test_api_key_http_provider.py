"""ApiKeyHttpProvider — compute over a user-registered http provider via the
credential-blind outbound proxy (compute-agnostic slice 2.3b).

Covers: happy-path openai + anthropic via an INJECTED proxy (wire assembly is
correct + carries no secret; response decodes into a ProviderResponse); the
universe-isolation gate (a grant bound to another universe is refused BEFORE any
dispatch); absent/revoked grant refusal; HTTP status mapping (429/5xx/4xx ->
typed provider errors); malformed body fails loud; constructor validation.

The real broker worker (SSRF, credential application) is exercised by
integration/dogfood, not here — these tests inject a fake proxy for the dispatch
seam and use a REAL ConnectionLedger for the grant/isolation gate.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tinyassets.exceptions import (
    ProviderOverloadedError,
    ProviderProtocolError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from tinyassets.providers.api_key_http_provider import ApiKeyHttpProvider
from tinyassets.providers.definition import ProviderDefinition

_CONN_ID = "http_" + "b" * 32
_GRANT_ID = "http_grant_" + "a" * 32
_HOST = "api.example.com"


class _FakeProxy:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def request(self, verb: str, wire: dict[str, Any]) -> Any:
        self.calls.append((verb, wire))
        return self.response


def _seed(base: Path, *, owner: str = "founder", universe: str = "u-x") -> None:
    """Create a real http connection + grant bound to `universe` in outbound.db."""
    from tinyassets.storage.outbound_connections import ActionCap, ConnectionLedger

    ledger = ConnectionLedger(
        base / "outbound.db", verify_authenticated_principal=lambda: owner
    )
    ledger.create_connection(
        connection_id=_CONN_ID,
        owner_user_id=owner,
        connection_class="http",
        connection_type="http",
        auth_scheme="bearer",
        scopes=("http",),
        provider="http",
        destination="compute:test",
        credential_ref="vault://http/compute:test",
        allowed_endpoints=[
            {"host": _HOST, "path_template": "/v1/chat/completions", "methods": ["POST"]},
            {"host": _HOST, "path_template": "/v1/messages", "methods": ["POST"]},
        ],
    )
    ledger.grant_connection(
        grant_id=_GRANT_ID,
        connection_id=_CONN_ID,
        owner_user_id=owner,
        universe_id=universe,
        unprompted_action_cap=ActionCap("http_requests", 100, "requests"),
    )


def _definition(protocol: str = "openai_chat", *, ref: str = _GRANT_ID) -> ProviderDefinition:
    return ProviderDefinition(
        id="provdef_" + "c" * 32,
        universe_id="u-x",
        owner_user_id="founder",
        access_method="api_key_http",
        protocol=protocol,
        model="moonshotai/kimi-k2",
        ref=ref,
        visibility="private",
        created_at="2026-01-01T00:00:00+00:00",
    )


def _config() -> Any:
    return SimpleNamespace(temperature=0.2, timeout=60, max_tokens=1024)


def _run(provider: ApiKeyHttpProvider, universe_dir: Path) -> Any:
    return asyncio.run(
        provider.complete("hello", "be terse", _config(), universe_dir=universe_dir)
    )


@pytest.fixture
def base(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "u-x").mkdir(parents=True)
    (root / "u-y").mkdir(parents=True)
    return root


# --------------------------------------------------------------------------- #
# Happy path + wire assembly.
# --------------------------------------------------------------------------- #


def test_openai_happy_path_and_wire_assembly(base: Path) -> None:
    _seed(base)
    proxy = _FakeProxy(
        {
            "status": 200,
            "body": json.dumps(
                {
                    "choices": [{"message": {"content": "the answer"}}],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 4},
                }
            ),
        }
    )
    provider = ApiKeyHttpProvider(_definition(), proxy_override=proxy)
    resp = _run(provider, base / "u-x")

    assert resp.text == "the answer"
    assert resp.input_tokens == 9 and resp.output_tokens == 4
    assert resp.family == "api:openai_chat"
    assert resp.model == "moonshotai/kimi-k2"

    # Wire assembly: POST to the exact allowlisted URL, correct body, NO secret.
    verb, wire = proxy.calls[0]
    assert verb == "POST"
    assert wire["url"] == "https://api.example.com/v1/chat/completions"
    assert wire["body"]["model"] == "moonshotai/kimi-k2"
    blob = json.dumps(wire).lower()
    assert "authorization" not in blob and "bearer" not in blob


def test_anthropic_happy_path(base: Path) -> None:
    _seed(base)
    proxy = _FakeProxy(
        {
            "status": 200,
            "body": json.dumps(
                {"content": [{"type": "text", "text": "hi there"}],
                 "usage": {"input_tokens": 2, "output_tokens": 3}}
            ),
        }
    )
    provider = ApiKeyHttpProvider(_definition("anthropic_messages"), proxy_override=proxy)
    resp = _run(provider, base / "u-x")
    assert resp.text == "hi there"
    assert proxy.calls[0][1]["url"] == "https://api.example.com/v1/messages"


# --------------------------------------------------------------------------- #
# Isolation + grant gates (real ledger).
# --------------------------------------------------------------------------- #


def test_grant_bound_to_other_universe_refused(base: Path) -> None:
    _seed(base, universe="u-x")  # grant bound to u-x
    proxy = _FakeProxy({"status": 200, "body": "{}"})
    provider = ApiKeyHttpProvider(_definition(), proxy_override=proxy)
    # Running as u-y must refuse BEFORE any dispatch — cross-universe isolation.
    with pytest.raises(ProviderUnavailableError):
        _run(provider, base / "u-y")
    assert proxy.calls == []  # never dispatched


def test_absent_grant_refused(base: Path) -> None:
    # No seed → the grant does not exist.
    provider = ApiKeyHttpProvider(_definition(ref="http_grant_" + "z" * 32))
    with pytest.raises(ProviderUnavailableError):
        _run(provider, base / "u-x")


def test_missing_universe_dir_refused(base: Path) -> None:
    _seed(base)
    provider = ApiKeyHttpProvider(_definition())
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.complete("p", "s", _config(), universe_dir=None))


# --------------------------------------------------------------------------- #
# Status mapping + malformed body (fail loud).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "status,exc",
    [
        (429, ProviderRateLimitedError),
        (503, ProviderOverloadedError),
        (500, ProviderOverloadedError),
        (400, ProviderProtocolError),
        (404, ProviderProtocolError),
    ],
)
def test_http_status_maps_to_provider_error(base: Path, status: int, exc: type) -> None:
    _seed(base)
    proxy = _FakeProxy({"status": status, "body": "{}"})
    provider = ApiKeyHttpProvider(_definition(), proxy_override=proxy)
    with pytest.raises(exc):
        _run(provider, base / "u-x")


def test_malformed_body_fails_loud(base: Path) -> None:
    _seed(base)
    proxy = _FakeProxy({"status": 200, "body": "not json at all"})
    provider = ApiKeyHttpProvider(_definition(), proxy_override=proxy)
    with pytest.raises(ProviderProtocolError):
        _run(provider, base / "u-x")


def test_error_envelope_without_status_fails_loud(base: Path) -> None:
    _seed(base)
    proxy = _FakeProxy({"reason": "connect timeout"})  # no status
    provider = ApiKeyHttpProvider(_definition(), proxy_override=proxy)
    with pytest.raises(ProviderUnavailableError):
        _run(provider, base / "u-x")


# --------------------------------------------------------------------------- #
# Constructor validation.
# --------------------------------------------------------------------------- #


def test_constructor_rejects_non_api_key_http() -> None:
    bad = ProviderDefinition(
        id="provdef_x", universe_id="u", owner_user_id="o",
        access_method="subscription_cli", protocol="cli:codex", model="gpt-5",
        ref="codex", visibility="private", created_at="2026-01-01T00:00:00+00:00",
    )
    with pytest.raises(ValueError):
        ApiKeyHttpProvider(bad)
