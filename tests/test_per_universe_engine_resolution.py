"""Explicit per-universe provider routing and broker-auth resolution."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest

from tinyassets import runtime_singletons as runtime
from tinyassets.config import load_universe_config
from tinyassets.credential_broker import deposit_engine_api_key
from tinyassets.engine_binding import RetiredCredentialStateError
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
    subprocess_env_for_provider,
)
from tinyassets.providers.router import ProviderRouter

_KEY_A = "sk-ant-api03-" + "A" * 40
_KEY_B = "sk-ant-api03-" + "B" * 40


class _RecordingProvider(BaseProvider):
    def __init__(self, name: str, family: str) -> None:
        self.name = name
        self.family = family

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        return ProviderResponse(
            text=str(universe_dir),
            provider=self.name,
            model="test",
            family=self.family,
            latency_ms=1.0,
        )


def _write_byo_universe(root: Path, key: str, founder: str) -> Path:
    root.mkdir(parents=True)
    (root / "config.yaml").write_text(
        "preferred_writer: claude-code\nengine_source: byo_api_key\n",
        encoding="utf-8",
    )
    deposit_engine_api_key(
        universe_id=root.name,
        founder_id=founder,
        service="anthropic",
        api_key=key,
    )
    return root


@pytest.fixture
def executable_byo(monkeypatch):
    import tinyassets.engine_binding as engine_binding

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)


def test_subprocess_env_resolves_broker_key_per_explicit_universe(
    platform_vault_env, monkeypatch, executable_byo
):
    universe_a = _write_byo_universe(
        platform_vault_env / "universe_a", _KEY_A, "founder-a"
    )
    universe_b = _write_byo_universe(
        platform_vault_env / "universe_b", _KEY_B, "founder-b"
    )
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(universe_a))
    plan = [universe_a if index % 2 == 0 else universe_b for index in range(24)]

    def resolve(universe: Path) -> tuple[Path, str | None]:
        env = subprocess_env_for_provider("claude-code", universe_dir=universe)
        return universe, env.get("ANTHROPIC_API_KEY")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(resolve, plan))

    for universe, key in results:
        assert key == (_KEY_A if universe == universe_a else _KEY_B)


def test_call_sync_routes_preferred_writer_per_universe_context(
    tmp_path, monkeypatch
):
    universe_a = tmp_path / "pref_a"
    universe_b = tmp_path / "pref_b"
    universe_a.mkdir()
    universe_b.mkdir()
    (universe_a / "config.yaml").write_text(
        "preferred_writer: codex\n", encoding="utf-8"
    )
    (universe_b / "config.yaml").write_text(
        "preferred_writer: claude-code\n", encoding="utf-8"
    )
    monkeypatch.delenv("TINYASSETS_PIN_WRITER", raising=False)
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(universe_a))
    previous = runtime.universe_config
    runtime.universe_config = load_universe_config(universe_a)
    try:
        router = ProviderRouter()
        router.register(_RecordingProvider("codex", "openai"))
        router.register(_RecordingProvider("claude-code", "anthropic"))
        contexts = [
            ("a", UniverseContext(universe_a, load_universe_config(universe_a))),
            ("b", UniverseContext(universe_b, load_universe_config(universe_b))),
        ] * 8

        def call(item):
            label, context = item
            return label, router.call_sync(
                role="writer",
                prompt=label,
                system="system",
                universe_context=context,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(call, contexts))
        for label, response in results:
            expected_provider = "codex" if label == "a" else "claude-code"
            expected_universe = universe_a if label == "a" else universe_b
            assert response.provider == expected_provider
            assert response.text == str(expected_universe)
    finally:
        runtime.universe_config = previous


def test_legacy_plaintext_state_is_terminal(platform_vault_env):
    universe = platform_vault_env / "legacy"
    universe.mkdir()
    (universe / ".credential-vault.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RetiredCredentialStateError):
        subprocess_env_for_provider("claude-code", universe_dir=universe)
