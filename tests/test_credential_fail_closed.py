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

AMBIENT_CLOUD_AUTH_VARS = (
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_CONFIG_FILE",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_ROLE_ARN",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "CLAUDE_CODE_USE_VERTEX",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "CLOUD_ML_REGION",
    "ANTHROPIC_VERTEX_PROJECT_ID",
)

AMBIENT_ROUTING_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
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
    vault_config_dir = universe / ".credentials" / "claude-custom"

    def fake_apply(env, provider_name, *, universe_dir=None):
        env["CLAUDE_CONFIG_DIR"] = str(vault_config_dir)
        return env

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", fake_apply
    )

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)
    assert env.get("CLAUDE_CONFIG_DIR") == str(vault_config_dir), (
        "the vault supplied a credential for this universe and the guard "
        "discarded it; strip inherited host authority before the vault overlay"
    )


def test_partial_vault_overlay_cannot_retain_alternate_host_auth(
    host_auth, tmp_path, monkeypatch
):
    """MUTATION: apply the overlay before stripping inherited auth -> RED."""
    universe = tmp_path / "u-partial-vault"
    universe.mkdir()
    vault_config_dir = universe / ".credentials" / "claude-custom"

    def fake_apply(env, provider_name, *, universe_dir=None):
        env["CLAUDE_CONFIG_DIR"] = str(vault_config_dir)
        return env

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", fake_apply
    )

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    assert env.get("CLAUDE_CONFIG_DIR") == str(vault_config_dir)
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


def test_universe_child_environment_is_default_deny_with_safe_runtime_basics(
    tmp_path, monkeypatch
):
    """MUTATION: copy the host env before filtering it -> RED."""
    universe = tmp_path / "u-default-deny"
    ca_bundle = tmp_path / "enterprise-ca.pem"
    ca_bundle.write_text("test-ca", encoding="utf-8")
    host_tmp = tmp_path / "host-tmp"
    host_tmp.mkdir()
    host_home = tmp_path / "host-home"
    host_home.mkdir()
    ambient = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "en_US.UTF-8",
        "LC_CTYPE": "en_US.UTF-8",
        "TZ": "UTC",
        "TERM": "xterm-256color",
        "NO_COLOR": "1",
        "PYTHONUTF8": "1",
        "SSL_CERT_FILE": str(ca_bundle),
        "HOME": str(host_home),
        "USERPROFILE": str(host_home),
        "APPDATA": str(host_home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(host_home / "AppData" / "Local"),
        "XDG_CONFIG_HOME": str(host_home / ".config"),
        "TMPDIR": str(host_tmp),
        "TMP": str(host_tmp),
        "TEMP": str(host_tmp),
        "FUTURE_PROVIDER_MASTER_TOKEN": "future-host-secret",
        "NODE_OPTIONS": "--require=/host/credential-loader.js",
        "SSL_CERT_DIR": str(tmp_path),
    }
    ambient.update({name: f"host-{name}" for name in AMBIENT_CLOUD_AUTH_VARS})
    ambient.update({name: f"http://host-secret@proxy/{name}" for name in AMBIENT_ROUTING_VARS})
    monkeypatch.setattr(os, "environ", ambient)

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    inherited_runtime = {
        "PATH",
        "LANG",
        "LC_CTYPE",
        "TZ",
        "TERM",
        "NO_COLOR",
        "PYTHONUTF8",
        "SSL_CERT_FILE",
    }
    isolated_runtime = {
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
        "TMPDIR",
        "TMP",
        "TEMP",
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "AWS_EC2_METADATA_DISABLED",
    }
    windows_runtime = {
        name
        for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE")
        if name in ambient
    }
    windows_home = {"HOMEDRIVE", "HOMEPATH"} if os.name == "nt" else set()
    assert set(env) == (
        inherited_runtime | isolated_runtime | windows_runtime | windows_home
    )
    assert env["SSL_CERT_FILE"] == str(ca_bundle)
    assert env["AWS_EC2_METADATA_DISABLED"] == "true"
    assert not (set(AMBIENT_CLOUD_AUTH_VARS) & set(env))
    assert not (set(AMBIENT_ROUTING_VARS) & set(env))
    assert "FUTURE_PROVIDER_MASTER_TOKEN" not in env
    assert "NODE_OPTIONS" not in env
    assert "SSL_CERT_DIR" not in env
    for name in ("TMPDIR", "TMP", "TEMP"):
        assert Path(env[name]).is_relative_to(universe)
        assert Path(env[name]).is_dir()
        assert Path(env[name]) != host_tmp


def test_universe_child_replaces_every_ambient_home_and_profile_root(
    tmp_path, monkeypatch
):
    """MUTATION: retain any host discovery root -> RED."""
    universe = tmp_path / "u-isolated-roots"
    host_root = tmp_path / "host-root"
    host_root.mkdir()
    for name in (
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
    ):
        monkeypatch.setenv(name, str(host_root / name))

    env = subprocess_env_for_provider("codex", universe_dir=universe)

    for name in (
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
    ):
        assert Path(env[name]).is_relative_to(universe)
        assert not Path(env[name]).is_relative_to(host_root)
    if os.name == "nt":
        isolated_profile = Path(env["USERPROFILE"])
        assert env["HOMEDRIVE"].casefold() == isolated_profile.drive.casefold()
        assert env["HOMEPATH"] == str(isolated_profile)[len(isolated_profile.drive):]
    else:
        assert "HOMEDRIVE" not in env
        assert "HOMEPATH" not in env


def test_universe_child_accepts_only_valid_ca_bundle_files(tmp_path, monkeypatch):
    """MUTATION: copy CA directories, relative paths, or missing files -> RED."""
    universe = tmp_path / "u-ca"
    valid_bundle = tmp_path / "valid-ca.pem"
    valid_bundle.write_text("test-ca", encoding="utf-8")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(valid_bundle))
    monkeypatch.setenv("CURL_CA_BUNDLE", "relative-ca.pem")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", str(tmp_path))
    monkeypatch.setenv("CODEX_CA_CERTIFICATE", str(tmp_path / "missing.pem"))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path))

    env = subprocess_env_for_provider("codex", universe_dir=universe)

    assert env["REQUESTS_CA_BUNDLE"] == str(valid_bundle)
    assert "CURL_CA_BUNDLE" not in env
    assert "NODE_EXTRA_CA_CERTS" not in env
    assert "CODEX_CA_CERTIFICATE" not in env
    assert "SSL_CERT_DIR" not in env


def test_universe_overlay_cannot_add_arbitrary_environment_authority(
    tmp_path, monkeypatch
):
    """MUTATION: update the child env directly with every helper key -> RED."""
    universe = tmp_path / "u-hostile-overlay"

    def hostile_apply(env, provider_name, *, universe_dir=None):
        env["ANTHROPIC_API_KEY"] = "universe-owned-key"
        env["FUTURE_PROVIDER_MASTER_TOKEN"] = "must-not-enter-child"
        return env

    monkeypatch.setattr(
        "tinyassets.credential_vault.apply_provider_auth_env", hostile_apply
    )

    with pytest.raises(ProviderUnavailableError, match="credential resolution") as exc:
        subprocess_env_for_provider("claude-code", universe_dir=universe)
    assert "must-not-enter-child" not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


def test_host_local_countercase_preserves_unknown_ambient_authority(
    host_auth, monkeypatch
):
    """No-universe host tooling remains an ordinary inherited environment."""
    monkeypatch.setenv("FUTURE_PROVIDER_MASTER_TOKEN", "host-local-only")

    env = subprocess_env_for_provider("claude-code", universe_dir=None)

    assert env["FUTURE_PROVIDER_MASTER_TOKEN"] == "host-local-only"


def test_provider_base_runtime_mirror_matches_canonical():
    """The packaged runtime must not ship a weaker credential boundary."""
    repo_root = Path(__file__).resolve().parents[1]
    canonical = repo_root / "tinyassets" / "providers" / "base.py"
    packaged = (
        repo_root
        / "packaging"
        / "claude-plugin"
        / "plugins"
        / "tinyassets-universe-server"
        / "runtime"
        / "tinyassets"
        / "providers"
        / "base.py"
    )

    assert canonical.read_bytes() == packaged.read_bytes()
