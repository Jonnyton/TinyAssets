"""Security regression tests for universe-scoped provider credential isolation."""

from __future__ import annotations

import asyncio

import pytest

from tinyassets.config import UniverseConfig
from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
    subprocess_env_for_provider,
)
from tinyassets.providers.router import ProviderRouter


class _AmbientHostProvider(BaseProvider):
    name = "claude-code"
    family = "anthropic"

    def __init__(self) -> None:
        self.call_count = 0

    async def complete(
        self, prompt, system, config: ModelConfig, *, universe_dir=None,
    ) -> ProviderResponse:
        self.call_count += 1
        return ProviderResponse(
            text="host-paid success",
            provider=self.name,
            model="host-subscription",
            family=self.family,
            latency_ms=0.0,
        )


def test_vaultless_universe_never_invokes_success_capable_host_provider(
    tmp_path, monkeypatch,
):
    """Mutation proof: deleting the universe credential gate makes this RED."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "host-oauth-must-not-pay")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "host-claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "host-codex"))
    monkeypatch.delenv("TINYASSETS_PIN_WRITER", raising=False)

    provider = _AmbientHostProvider()
    router = ProviderRouter(providers={provider.name: provider})
    ctx = UniverseContext(
        universe_dir=tmp_path / "newborn",
        config=UniverseConfig(preferred_writer="claude-code"),
    )

    with pytest.raises(AllProvidersExhaustedError):
        asyncio.run(router.call("writer", "hello", "system", universe_context=ctx))
    assert provider.call_count == 0


def test_universe_subprocess_env_strips_ambient_host_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "host-oauth")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "host-claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "host-codex"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "host-api-key")

    env = subprocess_env_for_provider(
        "claude-code", universe_dir=tmp_path / "newborn",
    )

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env.get("CLAUDE_CONFIG_DIR") != str(tmp_path / "host-claude")
    assert "CODEX_HOME" not in env


def test_host_scoped_subprocess_env_preserves_subscription_auth(tmp_path, monkeypatch):
    host_claude = str(tmp_path / "host-claude")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", host_claude)

    env = subprocess_env_for_provider("claude-code", universe_dir=None)

    assert env.get("CLAUDE_CONFIG_DIR") == host_claude
