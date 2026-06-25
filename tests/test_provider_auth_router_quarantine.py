"""Router-level auth-health quarantine (2026-06-25 loop-wedge, Slice 2).

Slice 1 quarantined a dead-auth *worker* (the supervisor gate, see
``test_provider_auth_quarantine.py``). This slice gates the *router*: a
subscription provider whose login is definitively ``not_logged_in`` is skipped
in fallback chains — routing goes straight to a healthy provider instead of
burning a failed attempt + a misleading cooldown — and a pinned writer with
dead auth fails loud (hard rule #8) rather than silently routing elsewhere.

The probe is *injected* (``auth_health=``), so the default router (no probe)
is completely unaffected; that keeps every existing fake-provider test green.
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


def _auth_probe(dead: set[str]):
    """Probe: codex/claude-code report 'ok' unless in *dead*; others 'unknown'.

    Matches ``subscription_auth_health`` semantics — only the subscription
    writers are assessable; api-key/local providers return 'unknown'.
    """

    def probe(provider_name: str) -> dict[str, str]:
        if provider_name in dead:
            return {
                "provider": provider_name,
                "status": "not_logged_in",
                "detail": "test",
            }
        if provider_name in ("codex", "claude-code"):
            return {"provider": provider_name, "status": "ok", "detail": "test"}
        return {"provider": provider_name, "status": "unknown", "detail": "test"}

    return probe


@pytest.fixture
def isolated_universe_config():
    """Snapshot + restore runtime config and routing-relevant env per test.

    Clears ``WORKFLOW_PIN_WRITER`` and ``WORKFLOW_ALLOW_API_KEY_PROVIDERS`` so
    tests are hermetic regardless of the host env: with api-key providers
    enabled, ``test_all_subscription_dead_falls_to_local`` would correctly pick
    ``gemini-free`` before ``ollama-local`` and break the assertion.
    """
    _NEUTRALIZE = ("WORKFLOW_PIN_WRITER", "WORKFLOW_ALLOW_API_KEY_PROVIDERS")
    saved_config = runtime.universe_config
    saved_env = {k: os.environ.get(k) for k in _NEUTRALIZE}
    runtime.universe_config = UniverseConfig()
    for k in _NEUTRALIZE:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        runtime.universe_config = saved_config
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def _router(dead: set[str]) -> tuple[ProviderRouter, dict[str, _FakeProvider]]:
    names = [
        "claude-code", "codex", "gemini-free", "groq-free",
        "grok-free", "ollama-local",
    ]
    providers = {n: _FakeProvider(n) for n in names}
    router = ProviderRouter(
        providers=providers,
        quota=QuotaTracker(),
        auth_health=_auth_probe(dead),
    )
    return router, providers


# ---------------------------------------------------------------------------
# Fallback chain: dead-auth providers are skipped, not tried
# ---------------------------------------------------------------------------


def test_dead_auth_writer_skipped_routes_to_next(isolated_universe_config):
    """claude-code dead -> route straight to codex; claude-code never called."""
    router, providers = _router(dead={"claude-code"})

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "codex"
    assert providers["claude-code"].call_count == 0
    assert providers["codex"].call_count == 1


def test_healthy_writer_not_skipped(isolated_universe_config):
    """No spurious skipping: a healthy claude-code still wins the chain."""
    router, providers = _router(dead=set())

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "claude-code"
    assert providers["claude-code"].call_count == 1


def test_all_subscription_dead_falls_to_local(isolated_universe_config):
    """Both subscription writers dead -> fall through to local (unknown kept)."""
    router, providers = _router(dead={"claude-code", "codex"})

    resp = _run(router.call("writer", "p", "s"))

    # gemini/groq/grok are api-key (dropped by default); ollama-local probes
    # 'unknown' and must never be stranded by the auth gate.
    assert resp.provider == "ollama-local"
    assert providers["claude-code"].call_count == 0
    assert providers["codex"].call_count == 0
    assert providers["ollama-local"].call_count == 1


def test_no_probe_means_no_gating(isolated_universe_config):
    """Default router (no injected probe) is unaffected — zero blast radius."""
    names = ["claude-code", "codex", "ollama-local"]
    providers = {n: _FakeProvider(n) for n in names}
    router = ProviderRouter(providers=providers, quota=QuotaTracker())

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "claude-code"
    assert providers["claude-code"].call_count == 1


def test_dead_auth_recorded_as_auth_invalid_in_attempts(isolated_universe_config):
    """Exhaustion diagnostics carry skip_class=auth_invalid for dead providers."""
    # Allowlist down to the two subscription writers so the dead-auth filter
    # empties the chain and the structured exhaustion error surfaces.
    runtime.universe_config = UniverseConfig(
        allowed_providers=["claude-code", "codex"],
    )
    router, providers = _router(dead={"claude-code", "codex"})

    with pytest.raises(AllProvidersExhaustedError) as exc:
        _run(router.call("writer", "p", "s"))

    attempts = exc.value.attempts or []
    auth_skips = {a.provider for a in attempts if a.skip_class == "auth_invalid"}
    assert auth_skips == {"claude-code", "codex"}
    for p in providers.values():
        assert p.call_count == 0


# ---------------------------------------------------------------------------
# Pinned writer: dead auth must fail loud (hard rule #8), never silent fallback
# ---------------------------------------------------------------------------


def test_pinned_dead_auth_writer_hard_fails(isolated_universe_config):
    os.environ["WORKFLOW_PIN_WRITER"] = "claude-code"
    router, providers = _router(dead={"claude-code"})

    with pytest.raises(AllProvidersExhaustedError) as exc:
        _run(router.call("writer", "p", "s"))

    msg = str(exc.value)
    assert "claude-code" in msg
    assert "not_logged_in" in msg or "subscription login" in msg
    # No silent fallback to codex/local.
    for p in providers.values():
        assert p.call_count == 0


def test_pinned_healthy_writer_runs(isolated_universe_config):
    os.environ["WORKFLOW_PIN_WRITER"] = "codex"
    router, providers = _router(dead={"claude-code"})

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "codex"
    assert providers["codex"].call_count == 1
    assert providers["claude-code"].call_count == 0


# ---------------------------------------------------------------------------
# Policy routing + judge ensemble honour the same gate
# ---------------------------------------------------------------------------


def test_call_with_policy_skips_dead_auth(isolated_universe_config):
    router, providers = _router(dead={"claude-code"})
    policy = {
        "preferred": {"provider": "claude-code"},
        "fallback_chain": [{"provider": "codex"}],
    }

    _text, provider, _meta = _run(
        router.call_with_policy("writer", "p", "s", policy)
    )

    assert provider == "codex"
    assert providers["claude-code"].call_count == 0
    assert providers["codex"].call_count == 1


def test_judge_ensemble_skips_dead_auth_codex(isolated_universe_config):
    router, providers = _router(dead={"codex"})

    results = _run(router.call_judge_ensemble("p", "s"))

    used = {r.provider for r in results}
    assert "codex" not in used
    assert "ollama-local" in used  # 'unknown' -> kept
    assert providers["codex"].call_count == 0
