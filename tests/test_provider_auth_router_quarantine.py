"""Router auth quarantine plus broker-backed non-ambient execution gates."""

from __future__ import annotations

import asyncio
import os

import pytest

from tinyassets import runtime_singletons as runtime
from tinyassets.config import UniverseConfig, write_universe_config_fields
from tinyassets.credential_broker import (
    MIGRATION_MARKER_FILENAME,
    deposit_engine_api_key,
)
from tinyassets.engine_binding import RetiredCredentialStateError
from tinyassets.exceptions import (
    AllProvidersExhaustedError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
    subprocess_env_for_provider,
)
from tinyassets.providers.quota import QuotaTracker
from tinyassets.providers.router import (
    ProviderRouter,
    _universe_provides_provider_auth,
)


class _FakeProvider(BaseProvider):
    def __init__(self, name: str, text: str = "content") -> None:
        self.name = name
        self.family = "fake"
        self._text = text
        self.call_count = 0

    async def complete(
        self, prompt: str, system: str, config: ModelConfig, *, universe_dir=None,
    ) -> ProviderResponse:
        self.call_count += 1
        return ProviderResponse(
            text=self._text,
            provider=self.name,
            model="fake",
            family="fake",
            latency_ms=0.0,
        )


class _RetiredProvider(_FakeProvider):
    async def complete(
        self, prompt: str, system: str, config: ModelConfig, *, universe_dir=None,
    ) -> ProviderResponse:
        self.call_count += 1
        raise RetiredCredentialStateError("retired test state")


class _ReplacingProvider(_FakeProvider):
    def __init__(self, universe) -> None:
        super().__init__("claude-code")
        self._universe = universe

    async def complete(
        self, prompt: str, system: str, config: ModelConfig, *, universe_dir=None,
    ) -> ProviderResponse:
        self.call_count += 1
        deposit_engine_api_key(
            universe_id=self._universe.name,
            founder_id="founder-1",
            service="anthropic",
            api_key="sk-ant-api03-replacement",
        )
        subprocess_env_for_provider("claude-code", universe_dir=self._universe)
        raise AssertionError("credential replacement should fail before spawn")


def _run(coro):
    return asyncio.run(coro)


def _auth_probe(dead: set[str]):
    def probe(provider_name: str) -> dict[str, str]:
        if provider_name in dead:
            return {"provider": provider_name, "status": "not_logged_in"}
        if provider_name in ("codex", "claude-code"):
            return {"provider": provider_name, "status": "ok"}
        return {"provider": provider_name, "status": "unknown"}

    return probe


@pytest.fixture
def isolated_universe_config(monkeypatch):
    names = (
        "TINYASSETS_PIN_WRITER",
        "TINYASSETS_ALLOW_API_KEY_PROVIDERS",
        "TINYASSETS_UNIVERSE",
        "TINYASSETS_BYO_VAULT_ENCRYPTED",
    )
    saved_config = runtime.universe_config
    saved_env = {name: os.environ.get(name) for name in names}
    runtime.universe_config = UniverseConfig()
    for name in names:
        monkeypatch.delenv(name, raising=False)
    yield
    runtime.universe_config = saved_config
    for name, value in saved_env.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _router(dead: set[str]) -> tuple[ProviderRouter, dict[str, _FakeProvider]]:
    names = [
        "claude-code", "codex", "gemini-free", "groq-free",
        "grok-free", "ollama-local",
    ]
    providers = {name: _FakeProvider(name) for name in names}
    return (
        ProviderRouter(
            providers=providers,
            quota=QuotaTracker(),
            auth_health=_auth_probe(dead),
        ),
        providers,
    )


@pytest.fixture
def executable_byo(monkeypatch, isolated_universe_config):
    import tinyassets.engine_binding as engine_binding

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)


def _bound_universe(data_root, name="u-bound"):
    universe = data_root / name
    universe.mkdir()
    write_universe_config_fields(
        universe, engine_source="byo_api_key", preferred_writer="claude-code"
    )
    deposit_engine_api_key(
        universe_id=universe.name,
        founder_id="founder-1",
        service="anthropic",
        api_key="sk-ant-api03-bound",
    )
    return universe


def test_dead_auth_writer_skipped_routes_to_next(isolated_universe_config):
    router, providers = _router({"claude-code"})
    assert _run(router.call("writer", "p", "s")).provider == "codex"
    assert providers["claude-code"].call_count == 0


def test_healthy_writer_not_skipped(isolated_universe_config):
    router, providers = _router(set())
    assert _run(router.call("writer", "p", "s")).provider == "claude-code"
    assert providers["claude-code"].call_count == 1


def test_all_subscription_dead_falls_to_local(isolated_universe_config):
    router, providers = _router({"claude-code", "codex"})
    assert _run(router.call("writer", "p", "s")).provider == "ollama-local"
    assert providers["ollama-local"].call_count == 1


def test_no_probe_means_no_gating(isolated_universe_config):
    providers = {
        name: _FakeProvider(name) for name in ("claude-code", "codex", "ollama-local")
    }
    router = ProviderRouter(providers=providers, quota=QuotaTracker())
    assert _run(router.call("writer", "p", "s")).provider == "claude-code"


def test_dead_auth_recorded_as_auth_invalid(isolated_universe_config):
    runtime.universe_config = UniverseConfig(
        allowed_providers=["claude-code", "codex"]
    )
    router, providers = _router({"claude-code", "codex"})
    with pytest.raises(AllProvidersExhaustedError) as exc:
        _run(router.call("writer", "p", "s"))
    assert {
        attempt.provider
        for attempt in exc.value.attempts or []
        if attempt.skip_class == "auth_invalid"
    } == {"claude-code", "codex"}
    assert all(provider.call_count == 0 for provider in providers.values())


def test_pinned_dead_auth_writer_hard_fails(
    isolated_universe_config, monkeypatch
):
    monkeypatch.setenv("TINYASSETS_PIN_WRITER", "claude-code")
    router, providers = _router({"claude-code"})
    with pytest.raises(AllProvidersExhaustedError):
        _run(router.call("writer", "p", "s"))
    assert all(provider.call_count == 0 for provider in providers.values())


def test_pinned_healthy_writer_runs(isolated_universe_config, monkeypatch):
    monkeypatch.setenv("TINYASSETS_PIN_WRITER", "codex")
    router, providers = _router({"claude-code"})
    assert _run(router.call("writer", "p", "s")).provider == "codex"
    assert providers["codex"].call_count == 1


def test_broker_auth_keeps_globally_dead_provider(
    platform_vault_env, executable_byo, isolated_universe_config
):
    universe = _bound_universe(platform_vault_env)
    router, providers = _router({"claude-code"})
    context = UniverseContext(universe, UniverseConfig(preferred_writer="claude-code"))
    assert _run(
        router.call("writer", "p", "s", universe_context=context)
    ).provider == "claude-code"
    assert providers["claude-code"].call_count == 1
    assert _universe_provides_provider_auth("claude-code", universe) is True
    assert _universe_provides_provider_auth("codex", universe) is False


@pytest.mark.parametrize("role", ["writer", "novelist"])
def test_bound_writer_routes_never_fall_through_to_platform_auth(
    platform_vault_env, executable_byo, isolated_universe_config, role
):
    universe = _bound_universe(platform_vault_env)
    router, providers = _router(set())
    context = UniverseContext(universe, UniverseConfig(preferred_writer="codex"))
    assert _run(router.call(role, "p", "s", universe_context=context)).provider == (
        "claude-code"
    )
    assert providers["codex"].call_count == 0


def test_bound_universe_rejects_ineligible_pinned_writer(
    platform_vault_env,
    executable_byo,
    isolated_universe_config,
    monkeypatch,
):
    universe = _bound_universe(platform_vault_env)
    monkeypatch.setenv("TINYASSETS_PIN_WRITER", "codex")
    router, providers = _router(set())
    with pytest.raises(AllProvidersExhaustedError):
        _run(
            router.call(
                "writer", "p", "s", universe_context=UniverseContext(universe)
            )
        )
    assert all(provider.call_count == 0 for provider in providers.values())


def test_broker_subprocess_env_scrubs_all_host_auth(
    platform_vault_env, executable_byo, monkeypatch
):
    universe = _bound_universe(platform_vault_env)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ambient-oauth")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "ambient-config")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai")
    env = subprocess_env_for_provider("claude-code", universe_dir=universe)
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-api03-bound"
    assert env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR", "OPENAI_API_KEY"):
        assert name not in env


@pytest.mark.parametrize("source", ["market_rented", "self_hosted_endpoint"])
def test_lane_switch_does_not_reuse_retained_broker_credential(
    platform_vault_env, executable_byo, source
):
    universe = _bound_universe(platform_vault_env)
    write_universe_config_fields(universe, engine_source=source)
    env = subprocess_env_for_provider("claude-code", universe_dir=universe)
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB" not in env


@pytest.mark.parametrize("entrypoint", ["call", "policy", "ensemble"])
def test_retired_provider_error_is_terminal_no_fallback(
    isolated_universe_config, monkeypatch, entrypoint
):
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    first = _RetiredProvider("claude-code" if entrypoint != "ensemble" else "codex")
    fallback = _FakeProvider("codex" if entrypoint != "ensemble" else "ollama-local")
    providers = {first.name: first, fallback.name: fallback}
    router = ProviderRouter(providers=providers, quota=QuotaTracker())
    with pytest.raises(RetiredCredentialStateError):
        if entrypoint == "call":
            _run(router.call("writer", "p", "s"))
        elif entrypoint == "policy":
            _run(
                router.call_with_policy(
                    "writer",
                    "p",
                    "s",
                    {
                        "preferred": {"provider": first.name},
                        "fallback_chain": [{"provider": fallback.name}],
                    },
                )
            )
        else:
            _run(router.call_judge_ensemble("p", "s"))
    if entrypoint != "ensemble":
        assert fallback.call_count == 0


def test_migration_marker_preflight_blocks_every_provider(
    tmp_path, isolated_universe_config
):
    (tmp_path / MIGRATION_MARKER_FILENAME).write_text("{}", encoding="utf-8")
    router, providers = _router(set())
    with pytest.raises(RetiredCredentialStateError):
        _run(
            router.call(
                "writer", "p", "s", universe_context=UniverseContext(tmp_path)
            )
        )
    assert all(provider.call_count == 0 for provider in providers.values())


def test_credential_replacement_between_route_and_spawn_fails_closed(
    platform_vault_env, executable_byo, isolated_universe_config
):
    universe = _bound_universe(platform_vault_env)
    replacing = _ReplacingProvider(universe)
    fallback = _FakeProvider("codex")
    router = ProviderRouter(
        providers={"claude-code": replacing, "codex": fallback},
        quota=QuotaTracker(),
    )
    with pytest.raises(AllProvidersExhaustedError) as exc:
        _run(
            router.call(
                "writer", "p", "s", universe_context=UniverseContext(universe)
            )
        )
    assert any(
        "changed or disappeared" in attempt.detail
        for attempt in exc.value.attempts or []
    )
    assert replacing.call_count == 1
    assert fallback.call_count == 0
