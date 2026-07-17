"""Per-universe credential vault tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.credential_vault import (
    VAULT_FILENAME,
    RetiredSubscriptionLaneError,
    apply_provider_auth_env,
    load_credential_vault,
    provider_auth_env_overrides,
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
                # A legacy llm_subscription record still WRITES/LOADS (so old
                # vaults can be read + migrated) — it is just never consumed as
                # spawn auth (round-12 #1).
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


# ── Retired subscription-custody lane (round-12 #1) ──────────────────────────
# Founder subscription custody is a BLOCKED lane (2026-07-02 custody research):
# a per-universe llm_subscription record is NEVER injected into a spawn. The
# platform's own subscription auth is exclusively process-global. A legacy record
# is rejected (fail loud, quarantine) rather than silently skipped or consumed.


def test_legacy_codex_subscription_record_is_rejected_not_consumed(tmp_path):
    write_credential_vault(
        tmp_path,
        [{
            "credential_type": "llm_subscription", "service": "codex",
            "auth_json_b64": "e30=",
        }],
    )
    # Codex path injects nothing itself, but a present subscription record is a
    # retired lane and must fail loud.
    with pytest.raises(RetiredSubscriptionLaneError):
        provider_auth_env_overrides(tmp_path, "codex")


def test_legacy_claude_subscription_record_is_rejected(tmp_path):
    write_credential_vault(
        tmp_path,
        [{
            "credential_type": "llm_subscription", "service": "claude",
            "claude_config_dir": str(tmp_path / "durable-claude"),
            "oauth_token": "sk-oauth-legacy",
        }],
    )
    with pytest.raises(RetiredSubscriptionLaneError):
        provider_auth_env_overrides(tmp_path, "claude-code")


def test_apply_provider_auth_env_rejects_legacy_subscription_record(tmp_path):
    write_credential_vault(
        tmp_path,
        [{
            "credential_type": "llm_subscription", "service": "claude",
            "oauth_token": "sk-oauth-legacy",
        }],
    )
    env = {"TINYASSETS_UNIVERSE": str(tmp_path)}
    with pytest.raises(RetiredSubscriptionLaneError):
        apply_provider_auth_env(env, "claude-code")
    # Never injected the legacy subscription token.
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_no_vault_records_produce_no_overrides(tmp_path):
    # A universe with no vault (the common case) injects nothing — host auth is
    # process-global (inherited env).
    assert provider_auth_env_overrides(tmp_path, "claude-code") == {}
    assert provider_auth_env_overrides(tmp_path, "codex") == {}


def test_missing_vault_loads_as_empty(tmp_path: Path):
    assert load_credential_vault(tmp_path) == []


# ── Retired-subscription migration + rollback (round-16 #2) ──────────────────


def test_quarantine_then_rollback_round_trips(tmp_path):
    """The migration quarantines llm_subscription records (vault stops crashing)
    and rollback restores them — reversible predeployment step (round-16 #2)."""
    from tinyassets.credential_vault import (
        has_legacy_subscription_records,
        quarantine_legacy_subscription_records,
        restore_quarantined_subscription_records,
    )

    write_credential_vault(tmp_path, [
        {"credential_type": "vcs", "service": "github",
         "destination": "o/r", "token": "t"},
        {"credential_type": "llm_subscription", "service": "claude",
         "oauth_token": "legacy"},
    ])
    assert has_legacy_subscription_records(tmp_path) is True

    mig = quarantine_legacy_subscription_records(tmp_path)
    assert mig["migrated"] == 1 and mig["remaining"] == 1
    assert has_legacy_subscription_records(tmp_path) is False
    # Idempotent — a second migrate is a no-op.
    assert quarantine_legacy_subscription_records(tmp_path)["migrated"] == 0

    back = restore_quarantined_subscription_records(tmp_path)
    assert back["restored"] == 1
    assert has_legacy_subscription_records(tmp_path) is True
    # Idempotent rollback — nothing left to restore.
    assert restore_quarantined_subscription_records(tmp_path)["restored"] == 0


def test_migration_script_inventory_migrate_rollback(tmp_path, monkeypatch):
    """The runnable predeployment script inventories, migrates (idempotent), and
    rolls back across universe dirs under the data root (round-16 #2)."""
    import importlib

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    # Two universes: one with a legacy record, one clean.
    (tmp_path / "u-legacy").mkdir()
    write_credential_vault(tmp_path / "u-legacy", [
        {"credential_type": "llm_subscription", "service": "codex",
         "auth_json_b64": "e30="},
    ])
    (tmp_path / "u-clean").mkdir()
    write_credential_vault(tmp_path / "u-clean", [
        {"credential_type": "vcs", "service": "github",
         "destination": "o/r", "token": "t"},
    ])

    script = importlib.import_module("scripts.migrate_retired_subscription_records")

    assert script.main(["--inventory"]) == 0
    # Migrate: only u-legacy is affected; idempotent on re-run.
    assert script.main(["--migrate"]) == 0
    assert not [r for r in _load_vault_types(tmp_path / "u-legacy")
                if r == "llm_subscription"]
    assert script.main(["--migrate"]) == 0  # idempotent
    # Rollback restores it.
    assert script.main(["--rollback"]) == 0
    assert "llm_subscription" in _load_vault_types(tmp_path / "u-legacy")


def _load_vault_types(universe_dir):
    return [r.get("credential_type") for r in load_credential_vault(universe_dir)]
