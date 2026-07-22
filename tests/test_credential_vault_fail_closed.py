"""Security regression tests for universe-scoped provider credential isolation."""

from __future__ import annotations

import asyncio
import base64

import pytest

from tinyassets.config import UniverseConfig
from tinyassets.credential_vault import (
    provider_credential_class,
    write_credential_vault,
)
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


def test_host_api_key_opt_in_receipt_is_not_mislabeled_subscription(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "host-api-key")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    assert provider_credential_class(None, "claude-code") == "host_api_key"


@pytest.mark.parametrize(
    ("service", "provider", "key_var", "home_var"),
    [
        ("anthropic", "claude-code", "ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR"),
        ("openai", "codex", "OPENAI_API_KEY", "CODEX_HOME"),
    ],
)
def test_byo_key_forces_isolated_provider_home(
    tmp_path, monkeypatch, service, provider, key_var, home_var,
):
    universe_dir = tmp_path / "u-byo"
    host_home = tmp_path / "host-auth-home"
    monkeypatch.setenv(home_var, str(host_home))
    write_credential_vault(universe_dir, [{
        "credential_type": "llm_api_key",
        "service": service,
        "secret_b64": base64.b64encode(b"founder-key").decode("ascii"),
    }])

    env = subprocess_env_for_provider(provider, universe_dir=universe_dir)

    assert env[key_var] == "founder-key"
    assert env[home_var] != str(host_home)
    assert str(universe_dir) in env[home_var]


@pytest.mark.parametrize(
    ("service", "provider", "key_var", "home_var", "subscription_record"),
    [
        (
            "anthropic", "claude-code", "ANTHROPIC_API_KEY",
            "CLAUDE_CONFIG_DIR",
            {
                "credential_type": "llm_subscription",
                "service": "claude",
                "claude_config_dir": "shared-claude",
                "oauth_token": "subscription-token",
            },
        ),
        (
            "openai", "codex", "OPENAI_API_KEY", "CODEX_HOME",
            {
                "credential_type": "llm_subscription",
                "service": "codex",
                "auth_json_b64": "e30=",
            },
        ),
    ],
)
def test_byo_key_is_exclusive_with_vault_subscription_auth(
    tmp_path, service, provider, key_var, home_var, subscription_record,
):
    universe_dir = tmp_path / "u-exclusive"
    write_credential_vault(universe_dir, [
        subscription_record,
        {
            "credential_type": "llm_api_key",
            "service": service,
            "secret_b64": base64.b64encode(b"founder-key").decode("ascii"),
        },
    ])

    env = subprocess_env_for_provider(provider, universe_dir=universe_dir)

    assert env[key_var] == "founder-key"
    assert env[home_var] == str(universe_dir / ".credentials" / (
        "claude" if provider == "claude-code" else "codex"
    ))
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_policy_route_reports_founder_payer_class(tmp_path, monkeypatch):
    universe_dir = tmp_path / "u-policy"
    write_credential_vault(universe_dir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(b"founder-key").decode("ascii"),
    }])
    monkeypatch.delenv("TINYASSETS_PIN_WRITER", raising=False)
    provider = _AmbientHostProvider()
    router = ProviderRouter(providers={provider.name: provider})
    ctx = UniverseContext(
        universe_dir=universe_dir,
        config=UniverseConfig(
            preferred_writer="claude-code",
            allowed_providers=["claude-code"],
        ),
    )

    text, served, meta = asyncio.run(router.call_with_policy(
        "writer",
        "hello",
        "system",
        {"preferred": {"provider": "claude-code"}},
        universe_context=ctx,
    ))

    assert text == "host-paid success"
    assert served == "claude-code"
    assert meta["credential_class"] == "founder_byo_api_key"
    assert meta["credential_owner"] == "founder"
