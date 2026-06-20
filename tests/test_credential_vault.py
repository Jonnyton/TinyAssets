"""Per-universe credential vault tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from workflow.credential_vault import (
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
                "destination": "Jonnyton/Workflow",
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


def test_resolve_github_token_uses_exact_destination_and_purpose(tmp_path):
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": "Jonnyton/Workflow",
                "purpose": "read",
                "token": "read-token",
            },
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": "Jonnyton/Workflow",
                "purpose": "write",
                "token": "write-token",
            },
        ],
    )

    assert resolve_github_token(
        tmp_path, "Jonnyton/Workflow", purpose="write"
    ) == "write-token"
    assert resolve_github_token(
        tmp_path, "Jonnyton/Workflow", purpose="read"
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
    env = {"WORKFLOW_UNIVERSE": str(tmp_path)}

    apply_provider_auth_env(env, "claude-code")

    assert env["CLAUDE_CONFIG_DIR"] == str(configured)


def test_missing_vault_loads_as_empty(tmp_path: Path):
    assert load_credential_vault(tmp_path) == []
