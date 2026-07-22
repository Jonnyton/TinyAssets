"""A universe with no credential of its own must not run on the host's.

Before this guard `subprocess_env_for_provider` stripped only API-key variables,
so `CLAUDE_CODE_OAUTH_TOKEN` / `CLAUDE_CONFIG_DIR` / `CODEX_HOME` survived from
the server environment into every universe's provider subprocess. Production
mounts shared host auth homes (deploy/compose.yml), so a founder who signed up
minutes ago could spend the host's subscription via `converse` or `run_graph`,
and no receipt recorded that it happened.

Each test below states the mutation that must make it fail. A test that cannot
go red is not evidence.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tinyassets.exceptions import ProviderUnavailableError
from tinyassets.providers.base import (
    API_KEY_PROVIDER_ENV_VARS,
    HOST_SUBSCRIPTION_ENV_VARS,
    subprocess_env_for_provider,
)


@pytest.fixture
def host_auth(monkeypatch):
    """Simulate the prod container: host subscription auth present in the env."""
    for name in HOST_SUBSCRIPTION_ENV_VARS:
        monkeypatch.setenv(name, f"host-value-for-{name}")
    monkeypatch.delenv("TINYASSETS_UNIVERSE", raising=False)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "0")


def test_universe_without_credential_does_not_inherit_host_auth(host_auth, tmp_path):
    """MUTATION: delete the env.pop loop in subprocess_env_for_provider -> RED."""
    universe = tmp_path / "u-newborn"
    universe.mkdir()

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert Path(env["CLAUDE_CONFIG_DIR"]).is_relative_to(universe)
    assert Path(env["CODEX_HOME"]).is_relative_to(universe)


def test_host_local_daemon_keeps_its_own_auth(host_auth):
    """The guard must not break the host's own flows.

    MUTATION: strip unconditionally (drop the `resolved is not None` condition)
    -> RED, because the host daemon would lose its own credentials.
    """
    env = subprocess_env_for_provider("claude-code", universe_dir=None)

    for name in HOST_SUBSCRIPTION_ENV_VARS:
        assert env.get(name) == f"host-value-for-{name}", (
            f"{name} was stripped for a host-local call with no universe in "
            "play; that breaks the daemon and dev loop"
        )


def test_api_keys_are_still_stripped_when_not_opted_in(host_auth, tmp_path):
    """Pre-existing protection must survive the change.

    MUTATION: remove the API-key stripping -> RED.
    """
    os.environ["OPENAI_API_KEY"] = "sk-should-not-survive"
    try:
        universe = tmp_path / "u-newborn"
        universe.mkdir()
        env = subprocess_env_for_provider("claude-code", universe_dir=universe)
        assert "OPENAI_API_KEY" not in env
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_universe_vault_auth_survives_after_host_auth_is_removed(
    host_auth, tmp_path, monkeypatch
):
    """When the vault supplies auth, that universe-owned value must survive.

    MUTATION: strip host vars after applying the overlay -> RED.
    """
    universe = tmp_path / "u-with-vault"
    universe.mkdir()

    def fake_apply(env, provider_name, *, universe_dir=None):
        env["CLAUDE_CONFIG_DIR"] = "/vault/supplied/for/this/universe"
        return env

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", fake_apply
    )

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)
    assert env.get("CLAUDE_CONFIG_DIR") == "/vault/supplied/for/this/universe", (
        "the vault supplied a credential for this universe and the guard "
        "discarded it; strip inherited host authority before the vault overlay"
    )


def test_partial_vault_overlay_cannot_retain_alternate_host_auth(
    host_auth, tmp_path, monkeypatch
):
    """MUTATION: apply the overlay before stripping inherited auth -> RED."""
    universe = tmp_path / "u-partial-vault"
    universe.mkdir()

    def fake_apply(env, provider_name, *, universe_dir=None):
        env["CLAUDE_CONFIG_DIR"] = "/vault/supplied/for/this/universe"
        return env

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", fake_apply
    )

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    assert env.get("CLAUDE_CONFIG_DIR") == "/vault/supplied/for/this/universe"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert env.get("CODEX_HOME") != "host-value-for-CODEX_HOME"
    assert Path(env["CODEX_HOME"]).is_relative_to(universe)


def test_universe_credential_resolution_failure_is_explicit(
    host_auth, tmp_path, monkeypatch
):
    """MUTATION: swallow a universe-scoped overlay exception -> RED."""
    universe = tmp_path / "u-broken-vault"
    universe.mkdir()

    def broken_apply(env, provider_name, *, universe_dir=None):
        raise RuntimeError("synthetic vault failure secret=do-not-leak")

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", broken_apply
    )

    with pytest.raises(ProviderUnavailableError, match="credential resolution") as exc:
        subprocess_env_for_provider("claude-code", universe_dir=universe)
    assert "do-not-leak" not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


def test_environment_bound_universe_does_not_inherit_host_auth(
    host_auth, tmp_path, monkeypatch
):
    """Environment binding is universe scope even without an explicit argument."""
    universe = tmp_path / "u-env-bound"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(universe))

    env = subprocess_env_for_provider("codex", universe_dir=None)

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert env.get("CLAUDE_CONFIG_DIR") != "host-value-for-CLAUDE_CONFIG_DIR"
    assert env.get("CODEX_HOME") != "host-value-for-CODEX_HOME"
    assert Path(env["CLAUDE_CONFIG_DIR"]).is_relative_to(universe)
    assert Path(env["CODEX_HOME"]).is_relative_to(universe)


def test_nonexistent_environment_binding_is_still_universe_scope(
    host_auth, tmp_path, monkeypatch
):
    """MUTATION: require the bound universe path to exist before isolation -> RED."""
    universe = tmp_path / "not-created" / "u-bound"
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(universe))

    env = subprocess_env_for_provider("codex", universe_dir=None)

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert Path(env["CLAUDE_CONFIG_DIR"]).is_relative_to(universe)
    assert Path(env["CODEX_HOME"]).is_relative_to(universe)


def test_host_api_provider_opt_in_does_not_leak_into_universe_cli(
    host_auth, tmp_path, monkeypatch
):
    """MUTATION: retain process-global API auth for a universe -> RED."""
    universe = tmp_path / "u-api-opt-in"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    for name in API_KEY_PROVIDER_ENV_VARS:
        monkeypatch.setenv(name, f"host-value-for-{name}")

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    leaked = [name for name in API_KEY_PROVIDER_ENV_VARS if name in env]
    assert not leaked, f"universe inherited host API-provider authority: {leaked}"


def test_default_cli_homes_cannot_recover_host_auth(tmp_path, monkeypatch):
    """MUTATION: delete auth-home pinning and let CLIs fall back to HOME -> RED."""
    host_home = tmp_path / "host-home"
    (host_home / ".codex").mkdir(parents=True)
    (host_home / ".claude").mkdir(parents=True)
    (host_home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
    (host_home / ".claude" / ".credentials.json").write_text(
        "{}", encoding="utf-8"
    )
    universe = tmp_path / "u-default-home"
    universe.mkdir()

    monkeypatch.setenv("HOME", str(host_home))
    monkeypatch.setenv("USERPROFILE", str(host_home))
    monkeypatch.delenv("TINYASSETS_UNIVERSE", raising=False)
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "0")
    for name in HOST_SUBSCRIPTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    env = subprocess_env_for_provider("codex", universe_dir=universe)
    effective_codex_home = Path(env.get("CODEX_HOME", host_home / ".codex"))
    effective_claude_home = Path(
        env.get("CLAUDE_CONFIG_DIR", host_home / ".claude")
    )

    assert effective_codex_home.is_relative_to(universe)
    assert effective_claude_home.is_relative_to(universe)
    assert effective_codex_home != host_home / ".codex"
    assert effective_claude_home != host_home / ".claude"


def test_host_local_execution_does_not_invoke_vault_helpers(host_auth, monkeypatch):
    """A host-local call must not depend on universe vault helpers."""

    def broken_apply(env, provider_name, *, universe_dir=None):
        raise RuntimeError("vault helper must not run for host-local execution")

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", broken_apply
    )

    env = subprocess_env_for_provider("claude-code", universe_dir=None)

    for name in HOST_SUBSCRIPTION_ENV_VARS:
        assert env.get(name) == f"host-value-for-{name}"
