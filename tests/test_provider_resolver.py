"""provider_for_definition — resolve a ProviderDefinition to its executor.

Covers: api_key_http -> ApiKeyHttpProvider; subscription_cli -> the vendor CLI
adapter (codex/claude-code) with its stable identity preserved; unknown ref /
access_method rejected; no cross-method fallback.
"""

from __future__ import annotations

import pytest

from tinyassets.providers.api_key_http_provider import ApiKeyHttpProvider
from tinyassets.providers.definition import ProviderDefinition
from tinyassets.providers.provider_resolver import provider_for_definition


def _def(access_method: str, protocol: str, ref: str) -> ProviderDefinition:
    return ProviderDefinition(
        id="provdef_" + "d" * 32,
        universe_id="u",
        owner_user_id="o",
        access_method=access_method,
        protocol=protocol,
        model="m",
        ref=ref,
        visibility="private",
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_api_key_http_resolves_to_api_provider() -> None:
    prov = provider_for_definition(_def("api_key_http", "openai_chat", "http_grant_x"))
    assert isinstance(prov, ApiKeyHttpProvider)
    assert prov.family == "api:openai_chat"


def test_subscription_cli_codex_preserves_identity() -> None:
    prov = provider_for_definition(_def("subscription_cli", "cli:codex", "codex"))
    assert prov.name == "codex"
    assert prov.family == "openai"


def test_subscription_cli_claude_preserves_identity() -> None:
    prov = provider_for_definition(
        _def("subscription_cli", "cli:claude-code", "claude-code")
    )
    assert prov.name == "claude-code"
    assert prov.family == "anthropic"


def test_unknown_cli_ref_rejected() -> None:
    with pytest.raises(ValueError):
        provider_for_definition(_def("subscription_cli", "cli:codex", "kimi-cli"))


def test_unknown_access_method_rejected() -> None:
    # Bypass registration validation by constructing the dataclass directly.
    bad = ProviderDefinition(
        id="provdef_x", universe_id="u", owner_user_id="o",
        access_method="sdk_direct", protocol="openai_chat", model="m",
        ref="x", visibility="private", created_at="2026-01-01T00:00:00+00:00",
    )
    with pytest.raises(ValueError):
        provider_for_definition(bad)
