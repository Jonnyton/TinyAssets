"""Tests for BUG-029: thundering-herd chain-drain detection + backoff.

Part A: QuotaTracker.all_api_providers_in_cooldown + get_status exposure.
Part B: ProviderRouter raises AllProvidersExhaustedError when chain-drained
        and local provider returns empty prose N consecutive times.
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

    def test_empty_local_raises_when_chain_drained(self):
        """Empty local output is provider exhaustion, not successful prose."""
        router, _, _ = _router_with_local(local_text="", threshold=2)
        with pytest.raises(AllProvidersExhaustedError) as exc_info:
            _run(router.call("writer", "p", "s"))

        err = exc_info.value
        assert err.attempts is not None
        assert any(
            a.provider == "ollama-local"
            and a.status == "failed"
            and a.skip_class == "empty_response"
            for a in err.attempts
        )

    def test_threshold_1_uses_chain_drained_message_on_first_empty(self):
        router, _, _ = _router_with_local(local_text="", threshold=2)
        router._chain_drain_empty_threshold = 1
        with pytest.raises(AllProvidersExhaustedError, match="empty prose"):
            _run(router.call("writer", "p", "s"))

    def test_empty_api_response_falls_back_to_local_content(self):
        """BUG-036: a silent API provider must not fail the graph before fallback."""
        quota = QuotaTracker()
        api = _FakeProvider("claude-code", text="")
        local = _FakeProvider("ollama-local", text="local content")

        # Codex is not registered in this test, so after claude-code returns
        # empty text the router should skip to ollama-local.
        router = ProviderRouter(
            providers={"claude-code": api, "ollama-local": local},
            quota=quota,
            chain_drain_empty_threshold=2,
        )

        resp = _run(router.call("writer", "p", "s"))
        assert resp.text == "local content"
        assert api.call_count == 1
        assert local.call_count == 1

    def test_all_empty_responses_exhaust_instead_of_returning_empty_text(self):
        """An all-empty chain fails loudly with diagnostics."""
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

        attempts = exc_info.value.attempts or []
        empty_attempts = [
            a for a in attempts
            if a.status == "failed" and a.skip_class == "empty_response"
        ]
        assert [a.provider for a in empty_attempts] == [
            "claude-code", "ollama-local",
        ]

    def test_empty_counter_resets_on_non_empty_response(self):
        """After a non-empty response, the local empty counter resets."""
        router, _, _ = _router_with_local(local_text="content", threshold=2)

        resp = _run(router.call("writer", "p", "s"))
        assert resp.text == "content"
        assert router._consecutive_empty == {}

    def test_threshold_1_raises_on_first_empty(self):
        router, _, _ = _router_with_local(local_text="", threshold=1)
        with pytest.raises(AllProvidersExhaustedError, match="empty prose"):
            _run(router.call("writer", "p", "s"))

    def test_empty_api_response_is_cooled_down(self):
        """Empty API output is treated like a failed provider attempt."""
        quota = QuotaTracker()
        api = _FakeProvider("claude-code", text="")
        local = _FakeProvider("ollama-local", text="local content")
        router = ProviderRouter(
            providers={"claude-code": api, "ollama-local": local},
            quota=quota,
        )

        _run(router.call("writer", "p", "s"))

        assert quota.cooldown_remaining("claude-code") > 0

    def test_empty_policy_response_falls_through_to_role_chain(self):
        """Per-node policy routing follows the same no-empty-success invariant."""
        quota = QuotaTracker()
        api = _FakeProvider("claude-code", text="")
        local = _FakeProvider("ollama-local", text="local content")
        router = ProviderRouter(
            providers={"claude-code": api, "ollama-local": local},
            quota=quota,
        )

        text, provider = _run(router.call_with_policy(
            "writer",
            "p",
            "s",
            {"preferred": {"provider": "claude-code"}},
        ))

        assert text == "local content"
        assert provider == "ollama-local"
        assert api.call_count == 1
        assert local.call_count == 1
