"""Unit tests for the general LLM-call bridge (tinyassets/providers/call.py).

This is the Tier-A extraction of the engine's domain-agnostic LLM-call
primitive out of domains/fantasy_daemon/phases/_provider_stub.py. The two
behaviors Codex flagged as relocation traps are pinned here:
- the injected router (daemon seam) must be what call_provider() routes through;
- get_last_provider() must be live, not an import-time snapshot.
"""

from __future__ import annotations

import pytest

from tinyassets.providers import call as provider_call


@pytest.fixture(autouse=True)
def _restore_bridge_state():
    saved_router = provider_call.get_provider_router()
    saved_mock = provider_call.is_force_mock()
    saved_last = provider_call.get_last_provider()
    yield
    provider_call.set_provider_router(saved_router)
    provider_call.set_force_mock(saved_mock)
    provider_call._last_provider = saved_last


class _FakeResult:
    def __init__(self, text: str, provider: str) -> None:
        self.text = text
        self.provider = provider


class _FakeRouter:
    def __init__(self, text: str = "real-text", provider: str = "claude") -> None:
        self._text = text
        self._provider = provider
        self.calls: list[tuple[str, str, str]] = []

    def call_sync(self, role: str, prompt: str, system: str) -> _FakeResult:
        self.calls.append((role, prompt, system))
        return _FakeResult(self._text, self._provider)


def test_force_mock_returns_fallback_then_placeholder() -> None:
    provider_call.set_force_mock(True)
    assert provider_call.call_provider("p", fallback_response="FB") == "FB"
    assert "Mock response" in provider_call.call_provider("p")


def test_injected_router_is_used_by_call_provider() -> None:
    """Daemon-injection seam: set_provider_router() must be what call_provider() uses."""
    provider_call.set_force_mock(False)
    fake = _FakeRouter(text="injected-output", provider="codex")
    provider_call.set_provider_router(fake)
    out = provider_call.call_provider("hello", "sys", role="writer")
    assert out == "injected-output"
    assert fake.calls == [("writer", "hello", "sys")]


def test_get_last_provider_reflects_latest_call_not_snapshot() -> None:
    """get_last_provider() returns the provider of the MOST RECENT call — fixes the
    bug where `from ... import last_provider` bound an import-time "" snapshot."""
    provider_call.set_force_mock(False)
    provider_call.set_provider_router(_FakeRouter(provider="gemini"))
    provider_call.call_provider("x")
    assert provider_call.get_last_provider() == "gemini"
    provider_call.set_provider_router(_FakeRouter(provider="grok"))
    provider_call.call_provider("y")
    assert provider_call.get_last_provider() == "grok"


def test_no_router_no_fallback_raises() -> None:
    from tinyassets.exceptions import AllProvidersExhaustedError

    provider_call.set_force_mock(False)
    provider_call.set_provider_router(None)
    with pytest.raises(AllProvidersExhaustedError):
        provider_call.call_provider("x")


def test_fallback_response_used_when_router_absent() -> None:
    provider_call.set_force_mock(False)
    provider_call.set_provider_router(None)
    assert provider_call.call_provider("x", fallback_response="FB") == "FB"
