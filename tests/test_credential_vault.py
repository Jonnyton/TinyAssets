"""Per-universe credential vault tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tinyassets.credential_vault import (
    VAULT_FILENAME,
    apply_provider_auth_env,
    claude_subscription_auth_available,
    codex_subscription_auth_available,
    ensure_claude_config_dir_from_vault,
    ensure_codex_home_from_vault,
    load_credential_vault,
    provider_auth_env_overrides,
    resolve_claude_config_dir,
    resolve_codex_home,
    resolve_github_token,
    write_credential_vault,
)


def test_vault_round_trips_typed_credentials_without_secret_summary(tmp_path):
    summary = write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": "Jonnyton/TinyAssets",
                "purpose": "write",
                "token": "ghs_secret",
            },
            {
                "credential_type": "social",
                "service": "twitter",
                "handle": "@workflow",
                "token": "social_secret",
            },
            {
                "credential_type": "llm_subscription",
                "service": "claude",
                "claude_config_dir": ".credentials/claude",
            },
        ],
    )

    assert summary["path"].endswith(VAULT_FILENAME)
    assert summary["credential_count"] == 3
    assert summary["credential_types"] == ["llm_subscription", "social", "vcs"]
    assert "ghs_secret" not in str(summary)
    loaded = load_credential_vault(tmp_path)
    assert loaded[0]["token"] == "ghs_secret"


def test_vault_rejects_unknown_credential_type(tmp_path):
    with pytest.raises(ValueError, match="unknown credential_type"):
        write_credential_vault(
            tmp_path,
            [{"credential_type": "database", "service": "postgres"}],
        )


def test_failed_atomic_replace_preserves_prior_vault_and_removes_secret_temp(
    tmp_path, monkeypatch,
):
    """A failed vault commit must retain neither new state nor secret residue."""
    write_credential_vault(
        tmp_path,
        [{
            "credential_type": "llm_api_key",
            "service": "anthropic",
            "api_key": "fake-prior-secret",
        }],
    )
    vault_path = tmp_path / VAULT_FILENAME
    prior_bytes = vault_path.read_bytes()
    real_replace = os.replace

    def fail_vault_replace(src, dst):
        if Path(dst) == vault_path:
            raise OSError("injected atomic vault replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_vault_replace)

    with pytest.raises(OSError, match="injected atomic vault replace failure"):
        write_credential_vault(
            tmp_path,
            [{
                "credential_type": "llm_api_key",
                "service": "openai",
                "api_key": "fake-new-secret-must-not-remain",
            }],
        )

    assert vault_path.read_bytes() == prior_bytes
    secret_temps = list(tmp_path.glob(".credential-vault*.tmp"))
    assert secret_temps == []


def test_resolve_github_token_uses_exact_destination_and_purpose(tmp_path):
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": "Jonnyton/TinyAssets",
                "purpose": "read",
                "token": "read-token",
            },
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": "Jonnyton/TinyAssets",
                "purpose": "write",
                "token": "write-token",
            },
        ],
    )

    assert resolve_github_token(
        tmp_path, "Jonnyton/TinyAssets", purpose="write"
    ) == "write-token"
    assert resolve_github_token(
        tmp_path, "Jonnyton/TinyAssets", purpose="read"
    ) == "read-token"
    assert resolve_github_token(tmp_path, "jonnyton/workflow", purpose="write") == ""


def test_codex_subscription_auth_can_materialize_from_vault(tmp_path):
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "llm_subscription",
                "service": "codex",
                "auth_json_b64": "e30=",
            }
        ],
    )

    codex_home = ensure_codex_home_from_vault(tmp_path)
    assert codex_home == tmp_path / ".credentials" / "codex"
    assert (codex_home / "auth.json").read_text(encoding="utf-8") == "{}"
    assert (codex_home / "config.toml").read_text(encoding="utf-8") == (
        'cli_auth_credentials_store = "file"\n'
    )
    assert resolve_codex_home(tmp_path) == codex_home
    assert codex_subscription_auth_available(tmp_path) is True


def test_codex_home_path_from_vault_is_resolved_without_env(tmp_path):
    configured = tmp_path / "durable-codex"
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "llm_subscription",
                "service": "codex",
                "codex_home": str(configured),
            }
        ],
    )

    assert ensure_codex_home_from_vault(tmp_path) == configured
    assert resolve_codex_home(tmp_path) == configured


def test_claude_config_dir_from_vault_sets_provider_env(tmp_path):
    configured = tmp_path / "durable-claude"
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "llm_subscription",
                "service": "claude",
                "claude_config_dir": str(configured),
            }
        ],
    )

    assert ensure_claude_config_dir_from_vault(tmp_path) == configured
    assert resolve_claude_config_dir(tmp_path) == configured
    assert claude_subscription_auth_available(tmp_path) is True
    assert provider_auth_env_overrides(tmp_path, "claude-code") == {
        "CLAUDE_CONFIG_DIR": str(configured)
    }


@pytest.mark.parametrize(
    ("provider", "service", "path_field"),
    [
        ("codex", "codex", "codex_home"),
        ("claude-code", "claude", "claude_config_dir"),
    ],
)
def test_vault_auth_home_must_resolve_inside_universe(
    tmp_path, provider, service, path_field,
):
    universe = tmp_path / "universe"
    universe.mkdir()
    outside = tmp_path / "host-auth-home"
    write_credential_vault(
        universe,
        [{
            "credential_type": "llm_subscription",
            "service": service,
            path_field: str(outside),
        }],
    )

    with pytest.raises(ValueError, match="inside.*universe|universe.*path"):
        provider_auth_env_overrides(universe, provider)

    assert not outside.exists()


@pytest.mark.skipif(os.name != "nt", reason="Win32 namespace spelling")
@pytest.mark.parametrize(
    ("provider", "service", "path_field", "home_var", "home_name"),
    [
        ("codex", "codex", "codex_home", "CODEX_HOME", "codex"),
        (
            "claude-code",
            "claude",
            "claude_config_dir",
            "CLAUDE_CONFIG_DIR",
            "claude",
        ),
    ],
)
def test_win32_extended_path_spelling_remains_inside_universe(
    tmp_path, provider, service, path_field, home_var, home_name,
):
    """``C:\\...`` and ``\\\\?\\C:\\...`` name the same contained home."""
    universe = tmp_path / "universe"
    universe.mkdir()
    expected = universe / ".credentials" / home_name
    extended = rf"\\?\{expected}"
    write_credential_vault(
        universe,
        [{
            "credential_type": "llm_subscription",
            "service": service,
            path_field: extended,
        }],
    )

    overrides = provider_auth_env_overrides(universe, provider)

    assert Path(overrides[home_var]).resolve() == expected.resolve()
    assert expected.is_dir()


def _make_directory_link_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError as symlink_error:
        if os.name == "nt":
            junction = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            if junction.returncode == 0:
                return
        pytest.skip(f"directory link creation unavailable: {symlink_error}")


@pytest.mark.parametrize(
    ("provider", "service", "path_field"),
    [
        ("codex", "codex", "codex_home"),
        ("claude-code", "claude", "claude_config_dir"),
    ],
)
def test_vault_auth_home_rejects_symlink_or_junction_escape(
    tmp_path, provider, service, path_field,
):
    """An inside-looking provider home cannot resolve outside the universe."""
    universe = tmp_path / "universe"
    universe.mkdir()
    outside = tmp_path / "outside-home"
    outside.mkdir()
    linked_home = universe / "linked-home"
    _make_directory_link_or_skip(linked_home, outside)
    write_credential_vault(
        universe,
        [{
            "credential_type": "llm_subscription",
            "service": service,
            path_field: str(linked_home),
        }],
    )

    with pytest.raises(ValueError, match="inside.*universe|universe.*path"):
        provider_auth_env_overrides(universe, provider)

    assert linked_home.resolve() == outside.resolve()


def test_apply_provider_auth_env_uses_workflow_universe(tmp_path):
    configured = tmp_path / "claude-dir"
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "llm_subscription",
                "service": "claude",
                "claude_config_dir": str(configured),
            }
        ],
    )
    env = {"TINYASSETS_UNIVERSE": str(tmp_path)}

    apply_provider_auth_env(env, "claude-code")

    assert env["CLAUDE_CONFIG_DIR"] == str(configured)


def test_missing_vault_loads_as_empty(tmp_path: Path):
    assert load_credential_vault(tmp_path) == []
