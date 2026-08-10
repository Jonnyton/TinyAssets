"""Slice 3a: the ``self_hosted_endpoint`` engine RUNTIME.

Founder invariant: a universe whose config sets
``engine_source=self_hosted_endpoint`` with a non-empty ``engine_endpoint`` runs
its writer/judge calls ONLY on that user-provided OpenAI-compatible endpoint --
never the platform fallback chain -- and FAILS CLOSED (a hard error, no platform
fallback) if the endpoint is unset or unreachable.

Every fail-closed test registers a *spy platform provider* as the first entry of
the writer/judge chain and asserts it was NEVER called. That doubles as the
mutation check the task requires: if the engine-source hook in ``router.py`` were
removed, a ``self_hosted_endpoint`` call would fall through to this spy (no
exception, ``spy.called is True``) and every fail-closed assertion below would
fail.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tinyassets.config import UniverseConfig, load_universe_config
from tinyassets.exceptions import AllProvidersExhaustedError, ProviderError
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
)
from tinyassets.providers.router import ProviderRouter
from tinyassets.providers.self_hosted_provider import SelfHostedProvider

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _SpyPlatformProvider(BaseProvider):
    """A platform provider that records whether the router ever called it.

    Registered as the FIRST chain entry (``claude-code``) so that any leak from
    the self-hosted path to the platform chain is caught: a self-hosted universe
    must never reach this provider.
    """

    def __init__(self, name: str = "claude-code") -> None:
        self.name = name
        self.family = "spy"
        self.called = False

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        self.called = True
        return ProviderResponse(
            text="PLATFORM-OUTPUT",
            provider=self.name,
            model="spy-model",
            family=self.family,
            latency_ms=1.0,
        )


class _FakeHTTPResponse:
    """Minimal context-manager stand-in for ``urllib.request.urlopen``."""

    def __init__(self, payload: dict) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._data


def _self_hosted_config(endpoint: str) -> UniverseConfig:
    return UniverseConfig(
        engine_source="self_hosted_endpoint", engine_endpoint=endpoint
    )


# ---------------------------------------------------------------------------
# (a) routes to the self-hosted endpoint, NOT the platform chain
# ---------------------------------------------------------------------------


def test_self_hosted_universe_routes_to_endpoint(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeHTTPResponse(
            {"choices": [{"message": {"content": "SELF-HOSTED-OUTPUT"}}]}
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    spy = _SpyPlatformProvider()
    router = ProviderRouter()
    router.register(spy)

    ctx = UniverseContext(config=_self_hosted_config("https://my-box.local/v1"))
    resp = router.call_sync(
        role="writer", prompt="hello", system="be terse", universe_context=ctx
    )

    assert resp.provider == "self-hosted"
    assert resp.text == "SELF-HOSTED-OUTPUT"
    # The platform chain must NEVER be touched (mutation guard).
    assert spy.called is False
    # The request went to the user's endpoint, OpenAI chat-completions shape.
    assert captured["url"] == "https://my-box.local/v1/chat/completions"
    body = captured["body"]
    assert body["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hello"},
    ]


# ---------------------------------------------------------------------------
# (b) empty endpoint fails closed
# ---------------------------------------------------------------------------


def test_empty_endpoint_fails_closed(monkeypatch):
    # urlopen must never be reached; make it explode if it is.
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("endpoint must not be called when unset"),
    )

    spy = _SpyPlatformProvider()
    router = ProviderRouter()
    router.register(spy)

    ctx = UniverseContext(config=_self_hosted_config(""))
    with pytest.raises(AllProvidersExhaustedError) as exc:
        router.call_sync(
            role="writer", prompt="hi", system="", universe_context=ctx
        )

    assert "self_hosted_endpoint" in str(exc.value)
    assert "engine_endpoint" in str(exc.value)
    # Mutation guard: no fallthrough to the platform chain.
    assert spy.called is False


# ---------------------------------------------------------------------------
# (c) unreachable endpoint fails closed (no platform fallback)
# ---------------------------------------------------------------------------


def test_unreachable_endpoint_fails_closed(monkeypatch):
    def _boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    spy = _SpyPlatformProvider()
    router = ProviderRouter()
    router.register(spy)

    ctx = UniverseContext(config=_self_hosted_config("https://down.local/v1"))
    with pytest.raises(AllProvidersExhaustedError) as exc:
        router.call_sync(
            role="writer", prompt="hi", system="", universe_context=ctx
        )

    assert "self-hosted" in str(exc.value).lower()
    # Mutation guard: an unreachable self-host endpoint must NOT widen to a
    # platform provider.
    assert spy.called is False


def test_http_error_endpoint_fails_closed(monkeypatch):
    def _http_error(req, timeout=None):
        raise urllib.error.HTTPError(
            url=req.full_url, code=500, msg="Internal Server Error",
            hdrs=None, fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", _http_error)

    spy = _SpyPlatformProvider()
    router = ProviderRouter()
    router.register(spy)

    ctx = UniverseContext(config=_self_hosted_config("https://err.local/v1"))
    with pytest.raises(AllProvidersExhaustedError):
        router.call_sync(
            role="writer", prompt="hi", system="", universe_context=ctx
        )
    assert spy.called is False


# ---------------------------------------------------------------------------
# (d) other engine sources are UNAFFECTED (normal chain)
# ---------------------------------------------------------------------------


def test_byo_api_key_universe_uses_platform_chain(monkeypatch):
    # If the endpoint were ever hit for a byo_api_key universe that'd be a bug.
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("self-host endpoint hit for byo_api_key"),
    )

    spy = _SpyPlatformProvider()
    router = ProviderRouter()
    router.register(spy)

    ctx = UniverseContext(config=UniverseConfig(engine_source="byo_api_key"))
    resp = router.call_sync(
        role="writer", prompt="hi", system="", universe_context=ctx
    )

    assert resp.provider == "claude-code"
    assert resp.text == "PLATFORM-OUTPUT"
    assert spy.called is True


def test_unset_engine_source_uses_platform_chain(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("self-host endpoint hit for unset source"),
    )

    spy = _SpyPlatformProvider()
    router = ProviderRouter()
    router.register(spy)

    # Default UniverseConfig() — the true "unset" case (defaults to byo_api_key).
    ctx = UniverseContext(config=UniverseConfig())
    resp = router.call_sync(
        role="writer", prompt="hi", system="", universe_context=ctx
    )
    assert resp.provider == "claude-code"
    assert spy.called is True


# ---------------------------------------------------------------------------
# Judge path: self-host must not fan out to the platform judge ensemble
# ---------------------------------------------------------------------------


def test_judge_ensemble_self_hosted_does_not_fan_out(monkeypatch):
    def _fake_urlopen(req, timeout=None):
        return _FakeHTTPResponse(
            {"choices": [{"message": {"content": "SELF-HOSTED-JUDGE"}}]}
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    # codex is the subscription judge; register a spy under its name.
    spy = _SpyPlatformProvider(name="codex")
    router = ProviderRouter()
    router.register(spy)

    import asyncio

    ctx = UniverseContext(config=_self_hosted_config("https://my-box.local/v1"))
    results = asyncio.run(
        router.call_judge_ensemble(
            prompt="judge this", system="", universe_context=ctx
        )
    )

    assert len(results) == 1
    assert results[0].provider == "self-hosted"
    assert results[0].text == "SELF-HOSTED-JUDGE"
    assert spy.called is False


def test_judge_ensemble_self_hosted_failure_returns_empty(monkeypatch):
    def _boom(req, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    spy = _SpyPlatformProvider(name="codex")
    router = ProviderRouter()
    router.register(spy)

    import asyncio

    ctx = UniverseContext(config=_self_hosted_config("https://down.local/v1"))
    results = asyncio.run(
        router.call_judge_ensemble(
            prompt="judge this", system="", universe_context=ctx
        )
    )

    # Fail closed: no judges, and NO platform fan-out.
    assert results == []
    assert spy.called is False


# ---------------------------------------------------------------------------
# call_provider bridge threads the self-hosted context through end-to-end
# ---------------------------------------------------------------------------


def test_call_provider_bridge_routes_self_hosted(monkeypatch):
    from tinyassets.providers import call as call_module

    def _fake_urlopen(req, timeout=None):
        return _FakeHTTPResponse(
            {"choices": [{"message": {"content": "BRIDGE-SELF-HOSTED"}}]}
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    spy = _SpyPlatformProvider()
    router = ProviderRouter()
    router.register(spy)

    ctx = UniverseContext(config=_self_hosted_config("https://my-box.local/v1"))

    saved_mock = call_module.is_force_mock()
    saved = call_module.get_provider_router()
    call_module.set_force_mock(False)
    call_module.set_provider_router(router)
    try:
        text = call_module.call_provider(
            "hello", "system", role="writer", universe_context=ctx
        )
    finally:
        call_module.set_provider_router(saved)
        call_module.set_force_mock(saved_mock)

    assert text == "BRIDGE-SELF-HOSTED"
    assert call_module.get_last_provider() == "self-hosted"
    assert spy.called is False


# ---------------------------------------------------------------------------
# Provider-level unit tests
# ---------------------------------------------------------------------------


def test_provider_url_construction():
    # Base URL ending in /v1 gets the chat-completions path appended.
    assert (
        SelfHostedProvider("https://h/v1")._url
        == "https://h/v1/chat/completions"
    )
    # Trailing slash is normalised.
    assert (
        SelfHostedProvider("https://h/v1/")._url
        == "https://h/v1/chat/completions"
    )
    # A full chat-completions URL is used as-is.
    assert (
        SelfHostedProvider("https://h/v1/chat/completions")._url
        == "https://h/v1/chat/completions"
    )


def test_provider_empty_endpoint_raises():
    with pytest.raises(ProviderError):
        SelfHostedProvider("")


def test_provider_model_env_override(monkeypatch):
    monkeypatch.setenv("TINYASSETS_SELF_HOSTED_MODEL", "my-model")
    assert SelfHostedProvider("https://h/v1")._model == "my-model"
    # Explicit constructor arg wins over the env var.
    assert SelfHostedProvider("https://h/v1", model="explicit")._model == "explicit"


def test_provider_malformed_body_raises_loud(monkeypatch):
    def _fake_urlopen(req, timeout=None):
        return _FakeHTTPResponse({"unexpected": "shape"})

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    import asyncio

    provider = SelfHostedProvider("https://h/v1")
    with pytest.raises(ProviderError):
        asyncio.run(
            provider.complete("hi", "", ModelConfig(timeout=5))
        )


def test_config_yaml_roundtrip_reads_engine_source(tmp_path):
    """load_universe_config surfaces engine_source/engine_endpoint for the hook."""
    (tmp_path / "config.yaml").write_text(
        "engine_source: self_hosted_endpoint\n"
        "engine_endpoint: https://my-box.local/v1\n",
        encoding="utf-8",
    )
    cfg = load_universe_config(tmp_path)
    assert cfg.engine_source == "self_hosted_endpoint"
    assert cfg.engine_endpoint == "https://my-box.local/v1"
