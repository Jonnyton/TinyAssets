"""Tests for BUG-029: thundering-herd chain-drain detection + backoff.

Part A: QuotaTracker.all_api_providers_in_cooldown + get_status exposure.
Part B: ProviderRouter raises AllProvidersExhaustedError or falls through when
        any provider returns empty prose, so blank text never reaches graph
        node state as a successful LLM response.
"""
from __future__ import annotations

import asyncio

import pytest

from workflow.exceptions import AllProvidersExhaustedError
from workflow.providers.base import BaseProvider, ModelConfig, ProviderResponse
from workflow.providers.quota import QuotaTracker
from workflow.providers.router import FALLBACK_CHAINS, ProviderRouter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeProvider(BaseProvider):
    def __init__(self, name: str, text: str = "content") -> None:
        self.name = name
        self.family = "fake"
        self._text = text
        self.call_count = 0

    async def complete(
        self, prompt: str, system: str, config: ModelConfig
    ) -> ProviderResponse:
        self.call_count += 1
        return ProviderResponse(
            text=self._text, provider=self.name,
            model="fake", family="fake", latency_ms=0.0,
        )


def _run(coro):
    return asyncio.run(coro)


def _router_with_local(
    local_text: str = "content",
    threshold: int = 2,
) -> tuple[ProviderRouter, QuotaTracker, _FakeProvider]:
    """Return (router, quota, local_provider) with all API providers in cooldown."""
    quota = QuotaTracker()
    local = _FakeProvider("ollama-local", text=local_text)
    router = ProviderRouter(
        providers={"ollama-local": local},
        quota=quota,
        chain_drain_empty_threshold=threshold,
    )
    # Put all API providers in the writer chain into cooldown.
    api_chain = [p for p in FALLBACK_CHAINS["writer"] if p != "ollama-local"]
    for p in api_chain:
        quota.cooldown(p, seconds=120)
    return router, quota, local


# ---------------------------------------------------------------------------
# Part A — QuotaTracker.all_api_providers_in_cooldown
# ---------------------------------------------------------------------------


class TestAllApiProvidersInCooldown:
    def test_returns_true_when_all_api_in_cooldown(self):
        qt = QuotaTracker()
        chain = ["claude-code", "codex", "ollama-local"]
        qt.cooldown("claude-code", 120)
        qt.cooldown("codex", 120)
        assert qt.all_api_providers_in_cooldown(chain) is True

    def test_returns_false_when_one_api_available(self):
        qt = QuotaTracker()
        chain = ["claude-code", "codex", "ollama-local"]
        qt.cooldown("claude-code", 120)
        # codex not in cooldown
        assert qt.all_api_providers_in_cooldown(chain) is False

    def test_returns_false_when_chain_is_local_only(self):
        qt = QuotaTracker()
        chain = ["ollama-local"]
        # No API providers in chain — returns False (nothing to drain).
        assert qt.all_api_providers_in_cooldown(chain) is False

    def test_custom_local_providers_respected(self):
        qt = QuotaTracker()
        chain = ["api-provider", "my-local"]
        qt.cooldown("api-provider", 120)
        assert qt.all_api_providers_in_cooldown(chain, local_providers={"my-local"}) is True

    def test_returns_false_when_no_providers(self):
        qt = QuotaTracker()
        assert qt.all_api_providers_in_cooldown([]) is False

    def test_cooldown_remaining_dict_includes_all_providers(self):
        qt = QuotaTracker()
        qt.cooldown("claude-code", 60)
        result = qt.cooldown_remaining_dict(["claude-code", "codex"])
        assert "claude-code" in result
        assert result["claude-code"] > 0
        assert result["codex"] == 0


# ---------------------------------------------------------------------------
# Part B — ProviderRouter raises AllProvidersExhaustedError on chain-drain
# ---------------------------------------------------------------------------


class TestChainDrainBackoff:
    def test_normal_local_response_returned_without_raise(self):
        """When chain-drained but local produces content, return normally."""
        router, _, _ = _router_with_local(local_text="real content")
        resp = _run(router.call("writer", "p", "s"))
        assert resp.text == "real content"

    def test_first_empty_local_raises(self):
        """A blank provider response is not a successful completion."""
        router, _, _ = _router_with_local(local_text="", threshold=2)
        with pytest.raises(AllProvidersExhaustedError, match="empty response"):
            _run(router.call("writer", "p", "s"))

    def test_empty_local_raises_when_chain_drained(self):
        """Empty local output when all APIs are in cooldown forces backoff."""
        router, _, _ = _router_with_local(local_text="", threshold=2)
        with pytest.raises(AllProvidersExhaustedError, match="empty response"):
            _run(router.call("writer", "p", "s"))

    def test_raise_message_includes_provider_name_and_count(self):
        router, _, _ = _router_with_local(local_text="", threshold=2)
        with pytest.raises(AllProvidersExhaustedError) as exc_info:
            _run(router.call("writer", "p", "s"))
        msg = str(exc_info.value)
        assert "ollama-local" in msg
        assert "empty response" in msg

    def test_empty_response_puts_provider_in_cooldown(self):
        """A blank response is treated as provider failure for the next call."""
        router, quota, _ = _router_with_local(local_text="", threshold=2)

        with pytest.raises(AllProvidersExhaustedError):
            _run(router.call("writer", "p", "s"))

        assert quota.cooldown_remaining("ollama-local") > 0

    def test_threshold_1_raises_on_first_empty(self):
        router, _, _ = _router_with_local(local_text="", threshold=1)
        with pytest.raises(AllProvidersExhaustedError):
            _run(router.call("writer", "p", "s"))

    def test_empty_api_provider_falls_through_to_next_provider(self):
        """Empty API output is a provider failure, not graph node output."""
        quota = QuotaTracker()
        local = _FakeProvider("ollama-local", text="local content")
        api = _FakeProvider("claude-code", text="")
        router = ProviderRouter(
            providers={"claude-code": api, "ollama-local": local},
            quota=quota,
            chain_drain_empty_threshold=2,
        )
        # claude-code is available and tried first, but an empty response must
        # fall through instead of becoming an EmptyResponseError in graph state.
        resp = _run(router.call("writer", "p", "s"))
        assert resp.text == "local content"
        assert api.call_count == 1
        assert local.call_count == 1

    def test_all_empty_providers_raise_with_attempt_diagnostic(self):
        quota = QuotaTracker()
        api = _FakeProvider("claude-code", text="")
        local = _FakeProvider("ollama-local", text="")
        router = ProviderRouter(
            providers={"claude-code": api, "ollama-local": local},
            quota=quota,
            chain_drain_empty_threshold=2,
        )

        with pytest.raises(AllProvidersExhaustedError) as exc_info:
            _run(router.call("writer", "p", "s"))

        assert "empty response" in str(exc_info.value)
