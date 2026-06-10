"""Tests for Q6.3 — per-universe `allowed_providers` allowlist primitive.

Spec: docs/design-notes/2026-04-27-q63-third-party-provider-privacy.md §5
Dispositions: .claude/agent-memory/navigator/q63_section4_dispositions.md
"""
from __future__ import annotations

import asyncio
import os

import pytest

from workflow import runtime_singletons as runtime
from workflow.config import UniverseConfig
from workflow.exceptions import AllProvidersExhaustedError
from workflow.providers.base import BaseProvider, ModelConfig, ProviderResponse
from workflow.providers.quota import QuotaTracker
from workflow.providers.router import ProviderRouter


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
            text=self._text,
            provider=self.name,
            model="fake",
            family="fake",
            latency_ms=0.0,
        )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def isolated_universe_config():
    """Snapshot + restore runtime_singletons.universe_config across tests."""
    saved = runtime.universe_config
    saved_pin = os.environ.get("WORKFLOW_PIN_WRITER")
    runtime.universe_config = UniverseConfig()
    if "WORKFLOW_PIN_WRITER" in os.environ:
        del os.environ["WORKFLOW_PIN_WRITER"]
    try:
        yield
    finally:
        runtime.universe_config = saved
        if saved_pin is not None:
            os.environ["WORKFLOW_PIN_WRITER"] = saved_pin
        elif "WORKFLOW_PIN_WRITER" in os.environ:
            del os.environ["WORKFLOW_PIN_WRITER"]


def _router_with_all_providers() -> tuple[
    ProviderRouter, dict[str, _FakeProvider],
]:
    """Build a router with one provider per name in the writer chain."""
    names = [
        "claude-code", "codex", "gemini-free", "groq-free",
        "grok-free", "ollama-local",
    ]
    providers = {n: _FakeProvider(n) for n in names}
    router = ProviderRouter(providers=providers, quota=QuotaTracker())
    return router, providers


# ---------------------------------------------------------------------------
# 1. Backwards-compat: allowed_providers=None -> full chain unchanged
# ---------------------------------------------------------------------------


def test_allowlist_none_preserves_full_chain(isolated_universe_config):
    runtime.universe_config = UniverseConfig(allowed_providers=None)
    router, providers = _router_with_all_providers()

    resp = _run(router.call("writer", "p", "s"))

    # First in chain (claude-code) wins; no other provider attempted.
    assert resp.provider == "claude-code"
    assert providers["claude-code"].call_count == 1
    for n, p in providers.items():
        if n != "claude-code":
            assert p.call_count == 0


# ---------------------------------------------------------------------------
# 2. Allowlist blocks third-party providers from running
# ---------------------------------------------------------------------------


def test_allowlist_blocks_third_party_in_writer_chain(isolated_universe_config):
    """allowed_providers=['ollama-local'] must skip claude-code, gemini, etc."""
    runtime.universe_config = UniverseConfig(allowed_providers=["ollama-local"])
    router, providers = _router_with_all_providers()

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "ollama-local"
    assert providers["ollama-local"].call_count == 1
    for n in ("claude-code", "codex", "gemini-free", "groq-free", "grok-free"):
        assert providers[n].call_count == 0, (
            f"{n} should not have been called under "
            f"allowed_providers=['ollama-local']"
        )


# ---------------------------------------------------------------------------
# 3. Empty filter -> AllProvidersExhaustedError (hard fail, no leak)
# ---------------------------------------------------------------------------


def test_empty_filter_raises_all_providers_exhausted(isolated_universe_config):
    """Allowlist that excludes every chain entry must hard-fail."""
    runtime.universe_config = UniverseConfig(
        allowed_providers=["does-not-exist"],
    )
    router, providers = _router_with_all_providers()

    with pytest.raises(AllProvidersExhaustedError) as exc_info:
        _run(router.call("writer", "p", "s"))

    msg = str(exc_info.value)
    assert "allowed_providers" in msg
    assert "does-not-exist" in msg
    # No provider should have been called.
    for p in providers.values():
        assert p.call_count == 0


# ---------------------------------------------------------------------------
# 4. call_judge_ensemble filters by allowlist; empty -> []
# ---------------------------------------------------------------------------


def test_judge_ensemble_filtered_by_allowlist(isolated_universe_config):
    """call_judge_ensemble must skip judges not in allowed_providers."""
    runtime.universe_config = UniverseConfig(
        allowed_providers=["codex", "ollama-local"],
    )
    router, providers = _router_with_all_providers()

    results = _run(router.call_judge_ensemble("p", "s"))

    # Only 2 judges in allowlist intersected with _JUDGE_PROVIDERS.
    assert len(results) == 2
    used = {r.provider for r in results}
    assert used == {"codex", "ollama-local"}
    for n in ("gemini-free", "groq-free", "grok-free"):
        assert providers[n].call_count == 0


def test_judge_ensemble_empty_allowlist_returns_empty_list(
    isolated_universe_config,
):
    """Filtered-to-empty judge ensemble returns [] (existing contract)."""
    runtime.universe_config = UniverseConfig(
        allowed_providers=["claude-code"],  # not in _JUDGE_PROVIDERS
    )
    router, _ = _router_with_all_providers()

    results = _run(router.call_judge_ensemble("p", "s"))

    assert results == []


# ---------------------------------------------------------------------------
# 5. call_with_policy intersects policy attempt order with allowlist
# ---------------------------------------------------------------------------


def test_call_with_policy_filters_policy_attempt_order_by_allowlist(
    isolated_universe_config,
):
    """Policy providers outside allowed_providers must not be attempted."""
    runtime.universe_config = UniverseConfig(
        allowed_providers=["ollama-local"],
    )
    router, providers = _router_with_all_providers()
    policy = {
        "preferred": {"provider": "gemini-free"},
        "fallback_chain": [
            {"provider": "groq-free"},
            {"provider": "ollama-local"},
        ],
    }

    text, provider, _meta = _run(router.call_with_policy("writer", "p", "s", policy))

    assert text == "content"
    assert provider == "ollama-local"
    assert providers["ollama-local"].call_count == 1
    for n in ("gemini-free", "groq-free"):
        assert providers[n].call_count == 0


# ---------------------------------------------------------------------------
# 6. WORKFLOW_PIN_WRITER × allowlist: pin in allowlist -> works
# ---------------------------------------------------------------------------


def test_pin_writer_in_allowlist_succeeds(isolated_universe_config):
    """Pin and allowlist compatible: pin runs, no fallback."""
    runtime.universe_config = UniverseConfig(
        allowed_providers=["ollama-local"],
    )
    os.environ["WORKFLOW_PIN_WRITER"] = "ollama-local"
    router, providers = _router_with_all_providers()

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "ollama-local"
    assert providers["ollama-local"].call_count == 1


# ---------------------------------------------------------------------------
# 7. WORKFLOW_PIN_WRITER × allowlist: pin NOT in allowlist -> hard-fail
# ---------------------------------------------------------------------------


def test_pin_writer_disjoint_from_allowlist_hard_fails(
    isolated_universe_config,
):
    """Pin not in allowlist: hard-fail with explanatory message; no call."""
    runtime.universe_config = UniverseConfig(
        allowed_providers=["ollama-local"],
    )
    os.environ["WORKFLOW_PIN_WRITER"] = "claude-code"
    router, providers = _router_with_all_providers()

    with pytest.raises(AllProvidersExhaustedError) as exc_info:
        _run(router.call("writer", "p", "s"))

    msg = str(exc_info.value)
    assert "claude-code" in msg
    assert "allowed_providers" in msg
    # No fallback to ollama-local — pin × allowlist disjoint must NOT
    # silently route to a different provider.
    for p in providers.values():
        assert p.call_count == 0
