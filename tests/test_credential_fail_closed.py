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

from tinyassets.providers.base import (
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

    leaked = [n for n in HOST_SUBSCRIPTION_ENV_VARS if n in env]
    assert not leaked, (
        f"universe {universe.name} inherited host subscription auth {leaked}; "
        "a universe with no credential must fail closed, not bill the host"
    )


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


def test_guard_is_keyed_on_the_vault_supplying_nothing(host_auth, tmp_path, monkeypatch):
    """When the vault DOES supply auth, that value must survive untouched.

    Otherwise the guard would strip a founder's own credential too.
    MUTATION: pop the host vars unconditionally -> RED.
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
        "discarded it; the guard must only fire when the vault supplied nothing"
    )
