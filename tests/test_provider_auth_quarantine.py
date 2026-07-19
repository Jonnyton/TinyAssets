"""Provider-launch quarantine coverage without the retired cloud worker.

The surviving launch boundary is ``subprocess_env_for_provider``: it resolves
the universe's engine binding, rejects an ineligible route, and scrubs ambient
host credentials before any provider process can start.
"""

from __future__ import annotations

import pytest

import tinyassets.engine_binding as engine_binding
from tinyassets.config import write_universe_config_fields
from tinyassets.credential_broker import (
    MIGRATION_MARKER_FILENAME,
    deposit_engine_api_key,
)
from tinyassets.engine_binding import (
    BYO_VAULT_ENCRYPTED_ENV,
    NON_AMBIENT_WORK_ENV,
    EngineMisconfiguredError,
    RetiredCredentialStateError,
    resolve_engine_binding,
)
from tinyassets.exceptions import ProviderUnavailableError
from tinyassets.providers.base import (
    subprocess_env_for_provider,
    subscription_auth_health,
)


@pytest.fixture
def attested_byo(monkeypatch):
    monkeypatch.setenv(BYO_VAULT_ENCRYPTED_ENV, "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)


def _bound_anthropic_universe(root, name: str = "u-bound"):
    universe = root / name
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    deposit_engine_api_key(
        universe_id=universe.name,
        founder_id="founder-1",
        service="anthropic",
        api_key="sk-ant-api03-quarantine-test",
    )
    return universe


def test_codex_auth_health_is_ok_when_auth_record_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")

    health = subscription_auth_health("codex", allow_probe=False)

    assert health["status"] == "ok"
    assert health["provider"] == "codex"


def test_codex_auth_health_is_quarantined_when_auth_record_is_absent(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    assert subscription_auth_health("codex")["status"] == "not_logged_in"


def test_claude_auth_health_accepts_explicit_oauth_token(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))

    assert subscription_auth_health("claude-code")["status"] == "ok"


def test_claude_auth_health_accepts_populated_config_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    (tmp_path / ".credentials.json").write_text("{}", encoding="utf-8")

    assert subscription_auth_health("claude-code")["status"] == "ok"


def test_claude_auth_health_quarantines_empty_config_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "absent"))

    assert subscription_auth_health("claude-code")["status"] == "not_logged_in"


@pytest.mark.parametrize("provider", ["gemini-free", ""])
def test_unprobed_provider_auth_health_is_unknown(provider):
    assert subscription_auth_health(provider)["status"] == "unknown"


@pytest.mark.parametrize(
    "provider",
    ("claude-code", "codex"),
)
def test_unbound_universe_is_quarantined_even_with_ambient_provider_auth(
    tmp_path, monkeypatch, provider
):
    universe = tmp_path / "u-legacy-unbound"
    universe.mkdir()
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-anthropic")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ambient-oauth")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai")

    binding = resolve_engine_binding(universe)

    assert binding.bound is False
    assert binding.capacity_kinds == ()
    with pytest.raises(ProviderUnavailableError, match="refusing ambient"):
        subprocess_env_for_provider(provider, universe_dir=universe)


@pytest.mark.parametrize("provider", ("claude-code", "codex"))
def test_unbound_universe_is_quarantined_without_global_provider_auth(
    tmp_path, monkeypatch, provider
):
    universe = tmp_path / "u-no-global-auth"
    universe.mkdir()
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    for name in (
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    empty_auth = tmp_path / "empty-global-auth"
    empty_auth.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(empty_auth / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(empty_auth / "codex"))

    with pytest.raises(ProviderUnavailableError, match="refusing ambient"):
        subprocess_env_for_provider(provider, universe_dir=universe)


def test_declared_broken_binding_fails_before_launch_with_flag_off(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    write_universe_config_fields(tmp_path, engine_source="byo_api_key")

    with pytest.raises(EngineMisconfiguredError, match="no active broker-backed"):
        subprocess_env_for_provider("claude-code", universe_dir=tmp_path)


def test_bound_route_quarantines_nonmatching_provider_without_ambient_fallback(
    platform_vault_env, attested_byo, monkeypatch
):
    universe = _bound_anthropic_universe(platform_vault_env)
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai")
    monkeypatch.setenv("CODEX_HOME", str(platform_vault_env / "ambient-codex"))

    with pytest.raises(ProviderUnavailableError, match="not an eligible"):
        subprocess_env_for_provider("codex", universe_dir=universe)


def test_byo_bound_route_runs_without_global_auth_and_uses_only_broker_secret(
    platform_vault_env, attested_byo, monkeypatch
):
    universe = _bound_anthropic_universe(platform_vault_env)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(platform_vault_env / "ambient-claude"))

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    assert env["ANTHROPIC_API_KEY"] == "sk-ant-api03-quarantine-test"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert env["CLAUDE_CONFIG_DIR"] == str(universe / ".engine-auth" / "claude")
    assert env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"


def test_unattested_byo_route_quarantines_instead_of_using_ambient_auth(
    platform_vault_env, monkeypatch
):
    monkeypatch.setenv(BYO_VAULT_ENCRYPTED_ENV, "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ambient-oauth")
    universe = _bound_anthropic_universe(platform_vault_env)

    with pytest.raises(ProviderUnavailableError, match="not fully attested"):
        subprocess_env_for_provider("claude-code", universe_dir=universe)


def test_retired_binding_is_terminal_and_never_falls_back_to_host_auth(
    tmp_path, monkeypatch
):
    (tmp_path / MIGRATION_MARKER_FILENAME).write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ambient-oauth")

    with pytest.raises(RetiredCredentialStateError, match="cannot use ambient"):
        subprocess_env_for_provider("claude-code", universe_dir=tmp_path)
