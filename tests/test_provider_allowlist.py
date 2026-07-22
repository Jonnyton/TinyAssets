"""Tests for Q6.3 — per-universe `allowed_providers` allowlist primitive.

Spec: docs/design-notes/2026-04-27-q63-third-party-provider-privacy.md §5
Dispositions: .claude/agent-memory/navigator/q63_section4_dispositions.md
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time

import pytest

from tinyassets import runtime_singletons as runtime
from tinyassets.config import (
    UniverseConfig,
    load_universe_config,
    write_universe_config_fields,
)
from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
)
from tinyassets.providers.quota import QuotaTracker
from tinyassets.providers.router import ProviderRouter


class _FakeProvider(BaseProvider):
    def __init__(
        self, name: str, text: str = "content", *, unavailable: bool = False,
    ) -> None:
        self.name = name
        self.family = "fake"
        self._text = text
        self._unavailable = unavailable
        self.call_count = 0

    async def complete(
        self, prompt: str, system: str, config: ModelConfig, *, universe_dir=None,
    ) -> ProviderResponse:
        self.call_count += 1
        if self._unavailable:
            raise ProviderUnavailableError(f"{self.name} deliberately unavailable")
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
    saved_pin = os.environ.get("TINYASSETS_PIN_WRITER")
    runtime.universe_config = UniverseConfig()
    if "TINYASSETS_PIN_WRITER" in os.environ:
        del os.environ["TINYASSETS_PIN_WRITER"]
    try:
        yield
    finally:
        runtime.universe_config = saved
        if saved_pin is not None:
            os.environ["TINYASSETS_PIN_WRITER"] = saved_pin
        elif "TINYASSETS_PIN_WRITER" in os.environ:
            del os.environ["TINYASSETS_PIN_WRITER"]


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


class _RecordingQuota(QuotaTracker):
    """Quota probe whose calls prove the assignment guard ran too late."""

    def __init__(self) -> None:
        super().__init__()
        self.available_calls: list[str] = []

    def available(self, provider: str) -> bool:
        self.available_calls.append(provider)
        return True


def _explicit_context(
    tmp_path,
    *,
    state: str | None = "ready",
    allowed_providers=None,
) -> UniverseContext:
    universe = tmp_path / "explicit-universe"
    universe.mkdir(exist_ok=True)
    fields = {"allowed_providers": allowed_providers}
    if state is not None:
        fields["engine_assignment_state"] = state
    write_universe_config_fields(universe, **fields)
    return UniverseContext(
        universe_dir=universe,
        config=load_universe_config(universe),
    )


def _all_uncalled(providers: dict[str, _FakeProvider]) -> bool:
    return all(provider.call_count == 0 for provider in providers.values())


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
# 6. TINYASSETS_PIN_WRITER × allowlist: pin in allowlist -> works
# ---------------------------------------------------------------------------


def test_pin_writer_in_allowlist_succeeds(isolated_universe_config):
    """Pin and allowlist compatible: pin runs, no fallback."""
    runtime.universe_config = UniverseConfig(
        allowed_providers=["ollama-local"],
    )
    os.environ["TINYASSETS_PIN_WRITER"] = "ollama-local"
    router, providers = _router_with_all_providers()

    resp = _run(router.call("writer", "p", "s"))

    assert resp.provider == "ollama-local"
    assert providers["ollama-local"].call_count == 1


# ---------------------------------------------------------------------------
# 7. TINYASSETS_PIN_WRITER × allowlist: pin NOT in allowlist -> hard-fail
# ---------------------------------------------------------------------------


def test_pin_writer_disjoint_from_allowlist_hard_fails(
    isolated_universe_config,
):
    """Pin not in allowlist: hard-fail with explanatory message; no call."""
    runtime.universe_config = UniverseConfig(
        allowed_providers=["ollama-local"],
    )
    os.environ["TINYASSETS_PIN_WRITER"] = "claude-code"
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


# ---------------------------------------------------------------------------
# 8. Engine assignment is re-read from disk immediately before every attempt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["normal", "policy", "judge"])
def test_pending_assignment_blocks_stale_context_across_every_route(
    tmp_path,
    isolated_universe_config,
    route,
):
    """A context captured before reassignment cannot authorize from memory."""
    universe = tmp_path / f"pending-{route}"
    universe.mkdir()
    write_universe_config_fields(
        universe,
        engine_assignment_state="ready",
        preferred_writer="claude-code",
        allowed_providers=[
            "claude-code", "codex", "gemini-free", "groq-free",
            "grok-free", "ollama-local",
        ],
    )
    stale = UniverseContext(
        universe_dir=universe,
        config=load_universe_config(universe),
    )
    # Reassignment has started after the request captured its context.
    write_universe_config_fields(
        universe,
        engine_assignment_state="pending",
        allowed_providers=[],
    )

    quota = _RecordingQuota()
    auth_health_calls: list[str] = []

    def auth_health(provider: str) -> dict[str, str]:
        auth_health_calls.append(provider)
        return {"status": "ok"}

    router, providers = _router_with_all_providers()
    router._quota = quota
    router._auth_health = auth_health

    if route == "normal":
        with pytest.raises(AllProvidersExhaustedError):
            _run(router.call("writer", "p", "s", universe_context=stale))
    elif route == "policy":
        policy = {
            "preferred": {"provider": "claude-code"},
            "fallback_chain": [{"provider": "codex"}],
        }
        with pytest.raises(AllProvidersExhaustedError):
            _run(
                router.call_with_policy(
                    "writer", "p", "s", policy, universe_context=stale,
                )
            )
    else:
        assert _run(
            router.call_judge_ensemble("p", "s", universe_context=stale)
        ) == []

    assert _all_uncalled(providers)
    assert quota.available_calls == []
    assert auth_health_calls == []


@pytest.mark.parametrize(
    ("state", "allowed_providers"),
    [
        (None, ["claude-code"]),
        ("invalid", ["claude-code"]),
        ("ready", None),
        ("ready", "claude-code"),
        ("ready", ["claude-code", 7]),
    ],
    ids=[
        "missing-state",
        "invalid-state",
        "none-ceiling",
        "scalar-ceiling",
        "mixed-entry-ceiling",
    ],
)
def test_explicit_universe_rejects_invalid_fresh_assignment_state_before_gates(
    tmp_path,
    isolated_universe_config,
    state,
    allowed_providers,
):
    ctx = _explicit_context(
        tmp_path,
        state=state,
        allowed_providers=allowed_providers,
    )
    quota = _RecordingQuota()
    auth_health_calls: list[str] = []

    def auth_health(provider: str) -> dict[str, str]:
        auth_health_calls.append(provider)
        return {"status": "ok"}

    router, providers = _router_with_all_providers()
    router._quota = quota
    router._auth_health = auth_health

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call("writer", "p", "s", universe_context=ctx))

    assert _all_uncalled(providers)
    assert quota.available_calls == []
    assert auth_health_calls == []


def test_set_engine_assigned_provider_failure_never_uses_outside_ceiling(
    tmp_path,
    monkeypatch,
    isolated_universe_config,
):
    """The real assignment write and router compose into a hard ceiling."""
    from tinyassets.api import universe as universe_api

    universe = tmp_path / "assigned"
    universe.mkdir()
    monkeypatch.setattr(
        universe_api, "_request_universe", lambda universe_id="": "assigned",
    )
    monkeypatch.setattr(universe_api, "_universe_dir", lambda uid: universe)

    result = json.loads(
        universe_api._action_set_engine(
            universe_id="assigned",
            inputs_json=json.dumps(
                {"service": "anthropic", "api_key": "sk-test-not-real"}
            ),
        )
    )
    assert result["status"] == "engine_set"

    router, providers = _router_with_all_providers()
    providers["claude-code"]._unavailable = True
    ctx = UniverseContext(
        universe_dir=universe,
        config=load_universe_config(universe),
    )

    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call("writer", "p", "s", universe_context=ctx))

    assert providers["claude-code"].call_count == 1
    assert all(
        provider.call_count == 0
        for name, provider in providers.items()
        if name != "claude-code"
    )


def test_ready_byo_assignment_ignores_host_subscription_health(
    tmp_path,
    monkeypatch,
    isolated_universe_config,
):
    """Host subscription health cannot veto a universe-owned BYO key."""
    from tinyassets.api import universe as universe_api

    universe = tmp_path / "byo-health"
    universe.mkdir()
    monkeypatch.setattr(
        universe_api, "_request_universe", lambda universe_id="": "byo-health",
    )
    monkeypatch.setattr(universe_api, "_universe_dir", lambda uid: universe)
    result = json.loads(
        universe_api._action_set_engine(
            universe_id="byo-health",
            inputs_json=json.dumps(
                {"service": "openai", "api_key": "sk-test-not-real"}
            ),
        )
    )
    assert result["status"] == "engine_set"

    health_calls: list[str] = []

    def host_auth_health(provider: str) -> dict[str, str]:
        health_calls.append(provider)
        return {"status": "not_logged_in"}

    router, providers = _router_with_all_providers()
    router._auth_health = host_auth_health
    context = UniverseContext(
        universe_dir=universe,
        config=load_universe_config(universe),
    )

    response = _run(
        router.call("writer", "p", "s", universe_context=context)
    )

    assert response.provider == "codex"
    assert providers["codex"].call_count == 1
    assert health_calls == []


@pytest.mark.parametrize("route", ["normal", "policy", "judge"])
def test_assignment_lock_contention_fails_immediately_then_retry_sees_commit(
    tmp_path,
    monkeypatch,
    isolated_universe_config,
    route,
):
    """Every explicit route shares the writer lock without waiting on it."""
    from tinyassets.api import universe as universe_api
    from tinyassets.config import engine_assignment_lock
    from tinyassets.credential_vault import write_credential_vault

    universe = tmp_path / f"locked-{route}"
    universe.mkdir()
    monkeypatch.setattr(
        universe_api, "_request_universe", lambda universe_id="": universe.name,
    )
    monkeypatch.setattr(universe_api, "_universe_dir", lambda uid: universe)
    result = json.loads(
        universe_api._action_set_engine(
            universe_id=universe.name,
            inputs_json=json.dumps(
                {"service": "openai", "api_key": "sk-prior-not-real"}
            ),
        )
    )
    assert result["status"] == "engine_set"
    stale = UniverseContext(
        universe_dir=universe,
        config=load_universe_config(universe),
    )

    lock_held = threading.Event()
    finish_assignment = threading.Event()
    assignment_finished = threading.Event()

    def complete_assignment() -> None:
        with engine_assignment_lock(universe):
            # Signal while the old assignment is still ready. A router that
            # merely re-reads without sharing this lock would invoke Codex.
            lock_held.set()
            if not finish_assignment.wait(timeout=5):
                return
            write_universe_config_fields(
                universe,
                engine_assignment_state="pending",
                allowed_providers=[],
            )
            write_credential_vault(
                universe,
                [{
                    "credential_type": "llm_api_key",
                    "service": "openai",
                    "api_key": "sk-new-not-real",
                }],
            )
            write_universe_config_fields(
                universe,
                engine_assignment_state="ready",
                preferred_writer="codex",
                allowed_providers=["codex"],
            )
        assignment_finished.set()

    assignment = threading.Thread(target=complete_assignment, daemon=True)
    assignment.start()
    assert lock_held.wait(timeout=5)

    quota = _RecordingQuota()
    health_calls: list[str] = []

    def host_auth_health(provider: str) -> dict[str, str]:
        health_calls.append(provider)
        return {"status": "not_logged_in"}

    router, providers = _router_with_all_providers()
    router._quota = quota
    router._auth_health = host_auth_health
    policy = {"preferred": {"provider": "codex"}}

    started = time.monotonic()
    if route == "normal":
        with pytest.raises(AllProvidersExhaustedError):
            _run(router.call("writer", "p", "s", universe_context=stale))
    elif route == "policy":
        with pytest.raises(AllProvidersExhaustedError):
            _run(
                router.call_with_policy(
                    "writer", "p", "s", policy, universe_context=stale,
                )
            )
    else:
        assert _run(
            router.call_judge_ensemble("p", "s", universe_context=stale)
        ) == []
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert _all_uncalled(providers)
    assert quota.available_calls == []
    assert health_calls == []

    finish_assignment.set()
    assert assignment_finished.wait(timeout=5)
    assignment.join(timeout=5)
    assert not assignment.is_alive()

    if route == "normal":
        response = _run(
            router.call("writer", "p", "s", universe_context=stale)
        )
        assert response.provider == "codex"
    elif route == "policy":
        text, provider, _meta = _run(
            router.call_with_policy(
                "writer", "p", "s", policy, universe_context=stale,
            )
        )
        assert text == "content"
        assert provider == "codex"
    else:
        responses = _run(
            router.call_judge_ensemble("p", "s", universe_context=stale)
        )
        assert [response.provider for response in responses] == ["codex"]

    assert providers["codex"].call_count == 1
    assert health_calls == []
